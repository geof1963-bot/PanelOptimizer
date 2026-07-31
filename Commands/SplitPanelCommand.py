# -*- coding: utf-8 -*-
"""FreeCAD GUI command for the V4.50 lipped, dowelled four-STL workflow."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace

import FreeCAD
import FreeCADGui

from Core.Exceptions import (
    PanelOptimizerError,
    RegionConnectivityError,
    SplitOperationError,
)
from Core.DowelPlanner import DowelPlanner
from Core.LipBuilder import LipBuilder, LipParameters
from Core.MacroPartExtractor import MacroPartExtractor
from Core.MacroSplitCore import MacroGrooveParameters, MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts, export_mesh_parts
from Core.Settings import Settings
from Core.SinuousSeamPath import SinuousSeamPathFinder
from Core.SplitWorkflow import SplitDocumentWriter, validate_single_selection


def _progressive_four_part_split(
    path_finder,
    candidate_plans,
    panel_bounds,
    exact_validator,
    *,
    maximum_validations=Settings.Split.MAX_CONNECTIVITY_EXACT_VALIDATIONS,
    time_budget_s=Settings.Split.SEAM_PLANNING_TIME_BUDGET_S,
    maximum_connectivity_repairs=(
        Settings.Split.MAX_CONNECTIVITY_REPAIR_ATTEMPTS
    ),
    connectivity_time_budget_s=(
        Settings.Split.MAX_CONNECTIVITY_REPAIR_TIME_S
    ),
    clock=time.perf_counter,
):
    """Bounded best-first local simplification around exact topology feedback."""
    queue = list(candidate_plans[:1])
    seen = set()
    diagnostics = []
    rejected_seconds = 0.0
    successful_seconds = 0.0
    validations = 0
    repair_attempts = 0
    repair_signatures = set()
    repair_origins = {}
    repair_priorities = {}
    repair_history = []
    connectivity_diagnoses = []
    best_connectivity = None
    best_diagnosis = None
    initial_disconnected_region = None
    repair_started = None
    started = clock()
    accepted = None
    while (
        queue
        and validations < maximum_validations
        and clock() - started < time_budget_s
    ):
        queue.sort(key=lambda item: (
            repair_priorities.get(_plan_signature(item), (float("inf"), 0)),
            path_finder.topology_quality_key(item),
        ))
        candidate = queue.pop(0)
        signature = (
            candidate.vertical.points,
            candidate.horizontal.points,
            candidate.vertical.detour_levels,
            candidate.horizontal.detour_levels,
        )
        if signature in seen:
            continue
        seen.add(signature)
        is_connectivity_repair = signature in repair_signatures
        if is_connectivity_repair:
            if repair_attempts >= maximum_connectivity_repairs:
                diagnostics.append(
                    "Connectivity repair stopped at the configured attempt limit."
                )
                break
            if (
                repair_started is not None
                and clock() - repair_started >= connectivity_time_budget_s
            ):
                diagnostics.append(
                    "Connectivity repair stopped at the configured time limit."
                )
                break
            repair_attempts += 1
        attempt_started = clock()
        validations += 1
        try:
            attempt = exact_validator(candidate)
        except RegionConnectivityError as error:
            rejected_seconds += clock() - attempt_started
            diagnosis = error.diagnosis
            connectivity_diagnoses.append(diagnosis)
            diagnostics.append(
                "Connectivity check: "
                + " ".join(
                    f"R{region} = "
                    + (
                        "1"
                        if region < diagnosis.region_index
                        else str(diagnosis.structural_count)
                        if region == diagnosis.region_index
                        else "pending"
                    )
                    for region in range(1, 5)
                )
            )
            if initial_disconnected_region is None:
                initial_disconnected_region = diagnosis.region_index
            score = (
                diagnosis.structural_count,
                diagnosis.isolated_structural_volume_mm3,
            )
            if repair_started is None:
                repair_started = clock()
            origin = repair_origins.get(signature)
            if origin is not None:
                _parent_score, detour_id, before_level, before_count = origin
                history = (
                    f"step {repair_attempts} {detour_id} "
                    f"L{before_level}->L{before_level - 1}: "
                    f"{before_count}->{diagnosis.structural_count} structural"
                )
                repair_history.append(history)
                diagnostics.append("Connectivity repair: " + history)
            if diagnosis.region_index != initial_disconnected_region:
                diagnostics.append(
                    f"Connectivity repair: rejected because Region_"
                    f"{diagnosis.region_index} became disconnected while "
                    f"repairing Region_{initial_disconnected_region}."
                )
                continue
            if best_connectivity is not None and score >= best_connectivity:
                diagnostics.append(
                    f"Connectivity repair: candidate retained no improvement "
                    f"({diagnosis.structural_count} structural, "
                    f"{diagnosis.isolated_structural_volume_mm3:.6f} mm^3 "
                    "isolated); restoring the best state."
                )
                continue
            best_connectivity = score
            best_diagnosis = diagnosis
            secondary = diagnosis.secondary
            responsible = (
                secondary.nearest_detour_id or secondary.nearest_segment_id
            )
            diagnostics.append(
                f"Seam candidate {validations}: Region_{diagnosis.region_index} "
                f"disconnected ({diagnosis.raw_solid_count} raw, "
                f"{diagnosis.sliver_count} slivers, "
                f"{diagnosis.structural_count} structural); largest island "
                f"{secondary.volume_mm3:.6f} mm^3 at "
                f"({secondary.centroid_mm[0]:.3f}, "
                f"{secondary.centroid_mm[1]:.3f}); nearest "
                f"{secondary.nearest_seam} detour {responsible}."
            )
            children = path_finder.connectivity_repair_candidates(
                candidate, diagnosis, panel_bounds
            )
            added = 0
            for priority, child in enumerate(children):
                child_signature = (
                    child.vertical.points,
                    child.horizontal.points,
                    child.vertical.detour_levels,
                    child.horizontal.detour_levels,
                )
                if child_signature not in seen:
                    queue.append(child)
                    repair_signatures.add(child_signature)
                    repair_priorities[child_signature] = (
                        diagnosis.structural_count,
                        priority,
                    )
                    changed = _changed_detour(path_finder, candidate, child)
                    if changed is not None:
                        detour_id, before_level = changed
                        repair_origins[child_signature] = (
                            score,
                            detour_id,
                            before_level,
                            diagnosis.structural_count,
                        )
                    added += 1
            if added:
                diagnostics.append(
                    f"Connectivity repair: {added} curved local alternative(s) "
                    f"shortlisted around {responsible}."
                )
            else:
                diagnostics.append(
                    f"Connectivity repair: no safe curved local alternative "
                    f"passed the 2D precheck around {responsible}."
                )
            continue
        except SplitOperationError as error:
            rejected_seconds += clock() - attempt_started
            diagnostics.append(
                f"Seam candidate {validations}: region extraction rejected: {error}"
            )
            continue
        elapsed = clock() - attempt_started
        if attempt.region_solid_counts == (1, 1, 1, 1):
            diagnostics.append(
                "Connectivity check: R1 = 1 R2 = 1 R3 = 1 R4 = 1"
            )
            origin = repair_origins.get(signature)
            if origin is not None:
                _parent_score, detour_id, before_level, before_count = origin
                history = (
                    f"step {repair_attempts} {detour_id} "
                    f"L{before_level}->L{before_level - 1}: "
                    f"{before_count}->1 structural"
                )
                repair_history.append(history)
                diagnostics.append("Connectivity repair: " + history)
            try:
                accepted = replace(
                    attempt,
                    connectivity_repair_attempts=repair_attempts,
                    connectivity_diagnostics=tuple(connectivity_diagnoses),
                    connectivity_repair_history=tuple(repair_history),
                )
            except TypeError:
                accepted = attempt
            successful_seconds = elapsed
            diagnostics.append(
                f"Seam candidate {validations}: structural regions = "
                "1/1/1/1, accepted"
            )
            break
        raise SplitOperationError(
            "Connected-region partition returned invalid connectivity metadata."
        )
    if accepted is None and connectivity_diagnoses:
        reason = (
            diagnostics[-1] if diagnostics
            else "no local connected alternative was accepted"
        )
        terminal = (best_diagnosis or connectivity_diagnoses[-1]).with_failure(
            repair_attempts, reason
        )
        diagnostics.append(terminal.failure_message())
    return (
        accepted,
        validations,
        rejected_seconds,
        successful_seconds,
        tuple(diagnostics),
        clock() - started,
    )


def _changed_detour(path_finder, original, candidate):
    """Return the single locally reduced detour and its previous level."""
    for path in (original.vertical, original.horizontal):
        for detour_id in path.detour_ids:
            before = path_finder.detour_level(original, detour_id)
            after = path_finder.detour_level(candidate, detour_id)
            if after < before:
                return detour_id, before
    return None


def _plan_signature(plan):
    """Return the immutable route identity used by bounded search."""
    return (
        plan.vertical.points,
        plan.horizontal.points,
        plan.vertical.detour_levels,
        plan.horizontal.detour_levels,
    )


@dataclass(frozen=True, slots=True)
class _ProductionPartitionOutcome:
    """Complete seam-to-connected-regions production result."""

    macro_result: object
    seam_diagnostics: dict
    exact_validations: int
    rejected_seconds: float
    successful_seconds: float
    diagnostics: tuple[str, ...]
    planning_seconds: float


def _run_production_partition(
    source_shape,
    vertical_offset,
    horizontal_offset,
    parameters,
    *,
    path_finder=None,
    exact_validator=None,
):
    """Build seams and return exactly four connected ownership regions.

    This is the sole Split Panel partition entry. Multi-solid extraction is
    classified inside ``MacroSplitCore.cut_regions`` and reaches the existing
    progressive repair through ``RegionConnectivityError``.
    """
    finder = path_finder or SinuousSeamPathFinder()
    proposed = finder.generate(
        source_shape, vertical_offset, horizontal_offset
    )
    bounds = source_shape.BoundBox
    panel_bounds = (
        float(bounds.XMin), float(bounds.XMax),
        float(bounds.YMin), float(bounds.YMax),
    )
    plans = tuple(finder.topology_shortlist(proposed, panel_bounds))
    validator = exact_validator or (
        lambda candidate: MacroSplitCore().cut_regions(
            source_shape,
            vertical_offset,
            horizontal_offset,
            parameters,
            seam_plan=candidate,
        )
    )
    result = _progressive_four_part_split(
        finder, plans, panel_bounds, validator
    )
    macro_result, validations, rejected, successful, diagnostics, elapsed = result
    if macro_result is None:
        detail = " ".join(diagnostics[-3:])
        raise PanelOptimizerError(
            "Connectivity repair exhausted before all four ownership "
            f"regions became structural solids. {detail}"
        )
    return _ProductionPartitionOutcome(
        macro_result,
        finder.search_diagnostics,
        validations,
        rejected,
        successful,
        diagnostics,
        elapsed,
    )


class PanelOptimizerSplitPanelCommand:
    """Create, validate, and export four parts from macro-cut geometry."""

    def __init__(
        self,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
        parameters: MacroGrooveParameters = MacroGrooveParameters(),
    ) -> None:
        """Store explicit macro inputs; registered command defaults to center."""
        self._vertical_offset = vertical_offset
        self._horizontal_offset = horizontal_offset
        self._parameters = parameters

    def GetResources(self):
        """Return command label, tooltip, and optional icon path."""
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Gui",
            "Resources",
            "icons",
            "SplitPanel.svg",
        )
        return {
            "Pixmap": icon_path,
            "MenuText": "Split Panel",
            "ToolTip": "Create four grooved, dowelled, lipped parts and export STL",
        }

    def IsActive(self):
        """Enable the command whenever a FreeCAD document is active."""
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        """Run V4.30 seams, V4.40 dowels, V4.50 lips, and four-STL export."""
        document = FreeCAD.ActiveDocument
        if document is None:
            self._error("PanelOptimizer: no active document.")
            return

        FreeCAD.Console.PrintMessage(
            "PanelOptimizer Split Pipeline V4.76\n"
        )

        timings = {}
        total_started = time.perf_counter()
        interactive_wait = 0.0
        try:
            source_object = validate_single_selection(
                FreeCADGui.Selection.getSelection()
            )
            self._validate_seam_preview_names(document)
            started = time.perf_counter()
            partition = _run_production_partition(
                source_object.Shape,
                self._vertical_offset,
                self._horizontal_offset,
                self._parameters,
            )
            bounds = source_object.Shape.BoundBox
            seam_diagnostics = partition.seam_diagnostics
            timings["seams"] = time.perf_counter() - started
            macro_result = partition.macro_result
            exact_topology_validations = partition.exact_validations
            rejected_topology_seconds = partition.rejected_seconds
            successful_split_seconds = partition.successful_seconds
            topology_attempts = partition.diagnostics
            seam_planning_seconds = partition.planning_seconds
            seam_diagnostics["progressive_planning_seconds"] = (
                seam_planning_seconds
            )
            timings["topology_validation"] = rejected_topology_seconds
            timings["split"] = successful_split_seconds
            planner = DowelPlanner()
            started = time.perf_counter()
            dowel_plan = planner.plan(macro_result)
            timings["dowel_plan"] = time.perf_counter() - started
            started = time.perf_counter()
            dowel_application = planner.apply(macro_result, dowel_plan)
            timings["dowel_cut"] = time.perf_counter() - started
            started = time.perf_counter()
            lip_application = LipBuilder(
                LipParameters(
                    groove_top_width_mm=self._parameters.top_width_mm,
                )
            ).apply(
                dowel_application.macro_result,
                dowel_cutters=dowel_application.cutters,
            )
            timings["lips"] = time.perf_counter() - started
            macro_result = lip_application.macro_result
            mesh_parts = build_macro_mesh_parts(macro_result, timings=timings)
            extraction = MacroPartExtractor().extract(
                macro_result,
                str(source_object.Name),
                accept_closed_invalid=True,
                verify_overlap=False,
            )
            output_objects = SplitDocumentWriter().write(
                document,
                extraction.execution,
            )
            self._write_seam_previews(
                document,
                macro_result.seam_plan,
                float(bounds.ZMax) + 0.1,
                recompute=False,
            )
            self._write_dowel_preview(
                document,
                dowel_application.cutters,
                recompute=False,
            )
            self._write_lip_preview(
                document, lip_application.preview_shape, recompute=False
            )
            document.recompute()
            FreeCAD.Console.PrintMessage(
                "PanelOptimizer\n"
                f"Source: {source_object.Name}\n"
                f"Cuts: X = {macro_result.cut_x_mm:g}, "
                f"Y = {macro_result.cut_y_mm:g}\n"
            )
            FreeCAD.Console.PrintMessage(
                "Route search: generated "
                f"{seam_diagnostics.get('route_candidates_generated', 0)}, "
                f"pruned {seam_diagnostics.get('route_candidates_pruned', 0)}, "
                f"exact topology validations {exact_topology_validations}, "
                f"detour cache hits {seam_diagnostics.get('detour_cache_hits', 0)}, "
                f"transition cache hits "
                f"{seam_diagnostics.get('transition_cache_hits', 0)}\n"
            )
            for diagnostic in topology_attempts:
                FreeCAD.Console.PrintMessage(diagnostic + "\n")
            FreeCAD.Console.PrintMessage("Production region classification:\n")
            for index in range(4):
                FreeCAD.Console.PrintMessage(
                    f"  R{index + 1}: raw = "
                    f"{macro_result.region_raw_solid_counts[index]}, "
                    f"slivers = "
                    f"{macro_result.region_discarded_sliver_counts[index]}, "
                    f"structural = {macro_result.region_solid_counts[index]}\n"
                )
            FreeCAD.Console.PrintMessage(
                "Connectivity repair: "
                f"{macro_result.connectivity_repair_attempts} exact local "
                "attempt(s)\n"
            )
            for diagnosis in macro_result.connectivity_diagnostics:
                FreeCAD.Console.PrintMessage(
                    f"  Region_{diagnosis.region_index}: raw solids = "
                    f"{diagnosis.raw_solid_count}, slivers = "
                    f"{diagnosis.sliver_count}, structural = "
                    f"{diagnosis.structural_count}\n"
                )
                for island in diagnosis.structural_islands:
                    FreeCAD.Console.PrintMessage(
                        f"    Island {island.rank}: "
                        f"{island.volume_mm3:.3f} mm^3, centroid "
                        f"({island.centroid_mm[0]:.3f}, "
                        f"{island.centroid_mm[1]:.3f}, "
                        f"{island.centroid_mm[2]:.3f}), bounds "
                        f"{island.bounds_mm}, nearest "
                        f"{island.nearest_seam}/"
                        f"{island.nearest_detour_id or island.nearest_segment_id}, "
                        f"opening {island.opening_distance_mm:.3f} mm\n"
                    )
            FreeCAD.Console.PrintMessage(
                "Production component classification evidence:\n"
            )
            for diagnosis in macro_result.region_component_diagnostics:
                for component in diagnosis.components[1:]:
                    FreeCAD.Console.PrintMessage(
                        f"  Region_{diagnosis.region_index} component "
                        f"{component.rank}: volume = "
                        f"{component.volume_mm3:.6f} mm^3, volume ratio = "
                        f"{component.volume_ratio:.8f}, z thickness = "
                        f"{component.thickness_mm:.6f} mm, thickness ratio = "
                        f"{component.thickness_ratio:.8f}, bbox footprint = "
                        f"{component.footprint_mm2:.6f} mm^2, effective "
                        f"footprint = {component.effective_footprint_mm2:.6f} "
                        f"mm^2, original exterior contact = "
                        f"{component.touches_panel_exterior}, silhouette risk "
                        f"= {component.silhouette_risk}, classification = "
                        f"{component.classification}\n"
                    )
            for history in macro_result.connectivity_repair_history:
                FreeCAD.Console.PrintMessage(
                    f"  Repair history: {history}\n"
                )
            for diagnosis in macro_result.region_component_diagnostics:
                FreeCAD.Console.PrintMessage(
                    f"Region_{diagnosis.region_index} extraction: "
                    f"{len(diagnosis.components)} solids\n"
                )
                for component in diagnosis.components:
                    action = (
                        "ignored" if not component.is_structural else "retained"
                    )
                    FreeCAD.Console.PrintMessage(
                        f"  Component {component.rank}: "
                        f"{component.classification}; volume = "
                        f"{component.volume_mm3:.6f} mm^3; bbox = "
                        f"{component.bounds_mm}; footprint = "
                        f"{component.footprint_mm2:.6f} mm^2; thickness = "
                        f"{component.thickness_mm:.6f} mm; volume ratio = "
                        f"{component.volume_ratio:.8f}; seam distance = "
                        f"{component.seam_distance_mm:.6f} mm; opening "
                        f"distance = {component.opening_distance_mm:.6f} mm; "
                        f"touches exterior = "
                        f"{component.touches_panel_exterior}; action = {action}\n"
                    )
                    if component.rank > 1:
                        FreeCAD.Console.PrintMessage(
                            "    Sliver classifier: "
                            f"volume_ok = {component.volume_ok}; "
                            f"ratio_ok = {component.volume_ratio_ok}; "
                            f"thickness_ok = {component.thickness_ok}; "
                            f"footprint_ok = {component.footprint_ok}; "
                            f"opening_proximity_ok = "
                            f"{component.opening_proximity_ok}; "
                            f"original_exterior_contact = "
                            f"{component.touches_panel_exterior}; "
                            f"silhouette_risk = {component.silhouette_risk}; "
                            f"full_thickness = {component.full_thickness}; "
                            f"classification = {component.classification}\n"
                        )
                FreeCAD.Console.PrintMessage(
                    f"Region_{diagnosis.region_index} structural "
                    "connectivity: OK\n"
                )
            FreeCAD.Console.PrintMessage(
                "[1] Seam guides found\n"
                f"Vertical features: {len(macro_result.seam_plan.vertical.followed_feature_ids)}\n"
                f"Horizontal features: {len(macro_result.seam_plan.horizontal.followed_feature_ids)}\n"
                "[2] Regions built\n"
                + "\n".join(
                    f"R{index} area: {area:.3f} mm^2"
                    for index, area in enumerate(
                        macro_result.region_areas_mm2, start=1
                    )
                )
                + "\n[3] Region extraction\n"
                + "\n".join(
                    f"Part_{index}: {count} solid, discarded cutter crumbs "
                    f"{macro_result.region_discarded_sliver_counts[index - 1]}"
                    for index, count in enumerate(
                        macro_result.region_solid_counts, start=1
                    )
                )
                + "\n"
            )
            for path in (
                macro_result.seam_plan.vertical,
                macro_result.seam_plan.horizontal,
            ):
                FreeCAD.Console.PrintMessage(
                    f"{path.axis.title()} seam: {path.path_length_mm:.3f} mm, "
                    f"max deviation {path.maximum_deviation_mm:.3f} mm, "
                    f"features {len(path.followed_feature_ids)}, segments "
                    f"{path.segment_count_before_cleanup} -> "
                    f"{path.segment_count_after_cleanup}, transitions "
                    f"{path.smoothing_transition_count}, artificial turn "
                    f"{path.maximum_artificial_turn_before_deg:.2f} -> "
                    f"{path.maximum_artificial_turn_after_deg:.2f} deg, contour "
                    f"{path.contour_following_length_mm:.3f} mm "
                    f"({path.contour_following_ratio:.1%}), longest straight "
                    f"{path.longest_straight_segment_mm:.3f} mm\n"
                )
                if path.detour_ids:
                    FreeCAD.Console.PrintMessage(
                        "  detours "
                        + ", ".join(
                            f"{detour_id}=L{level}"
                            for detour_id, level in zip(
                                path.detour_ids, path.detour_levels
                            )
                        )
                        + "\n"
                    )
                for report in path.hole_offset_reports:
                    FreeCAD.Console.PrintMessage(
                        f"  {report.feature_id}: bounds "
                        f"{report.boundary_bounds_mm}, interior "
                        f"{report.interior_side}, envelope "
                        f"{report.cutter_envelope_mm:.3f} mm + clearance "
                        f"{report.clearance_mm:.3f} mm -> offset "
                        f"{report.final_offset_mm:.3f} mm, remaining "
                        f"{report.minimum_material_side_clearance_mm:.3f} mm, "
                        f"followed {report.followed_contour_length_mm:.3f} mm "
                        f"{report.direction_used}, offset min/max/avg "
                        f"{report.minimum_offset_mm:.3f}/"
                        f"{report.maximum_offset_mm:.3f}/"
                        f"{report.average_offset_mm:.3f} mm, original profile "
                        f"{'preserved' if report.original_profile_preserved else 'NOT preserved'}\n"
                    )
            for branch in dowel_application.plan.branches:
                selected_dowels = tuple(
                    dowel
                    for dowel in dowel_application.plan.dowels
                    if dowel.seam_branch == branch.branch_id
                )
                positions = tuple(dowel.center_xyz_mm for dowel in selected_dowels)
                useful_depths = tuple(
                    (
                        dowel.useful_depth_part_a_mm,
                        dowel.useful_depth_part_b_mm,
                    )
                    for dowel in selected_dowels
                )
                opening_breakouts = tuple(
                    dowel.bore_exits_artistic_opening
                    for dowel in selected_dowels
                )
                artistic_clearances = tuple(
                    dowel.nearest_artistic_hole_clearance_mm
                    for dowel in selected_dowels
                )
                rejection_reasons = tuple(sorted({
                    item.reason for item in branch.rejected_candidates
                }))
                FreeCAD.Console.PrintMessage(
                    f"{branch.branch_id}: "
                    f"usable {branch.usable_length_mm:.3f} mm, targets "
                    f"{branch.target_fractions}, positions {positions}, "
                    f"spacing {branch.spacing_mm}, useful depths "
                    f"{useful_depths}, opening breakout {opening_breakouts}, fallback "
                    f"artistic clearance {artistic_clearances}, "
                    f"{branch.used_two_dowel_fallback}, sampled "
                    f"{branch.sampled_point_count}, safe "
                    f"{branch.safe_candidate_count}, selected "
                    f"{len(branch.accepted_dowel_ids)}, rejected geometry "
                    f"{branch.rejected_geometry_counts or rejection_reasons}, "
                    f"cheap {branch.cheap_candidate_count}, shortlist "
                    f"{branch.shortlisted_candidate_count}, exact "
                    f"{branch.exact_validation_count}, safe intervals "
                    f"{branch.safe_interval_count}, unsupported "
                    f"{branch.unsupported_spans_mm}, largest "
                    f"{branch.largest_unsupported_span_mm:.3f} mm, "
                    f"coverage {branch.coverage_target_achieved}, spacing "
                    f"exception {branch.spacing_exception}, degraded two-dowel "
                    f"{branch.degraded_two_dowel}\n"
                )
            for report in lip_application.reports:
                FreeCAD.Console.PrintMessage(
                    f"{report.name} lips: {report.total_length_mm:.3f} mm, "
                    f"+{report.volume_added_mm3:.3f} mm^3, "
                    f"segments {report.segment_count}, trimmed "
                    f"{report.trimmed_segment_count}, rejected "
                    f"{report.rejected_segment_count}, dimensions "
                    f"{report.dimensions_before_mm} -> "
                    f"{report.dimensions_after_mm}\n"
                )
            for part in mesh_parts:
                status = "watertight - OK" if part.is_printable else "EXCEEDS LIMIT"
                FreeCAD.Console.PrintMessage(
                    f"{part.name}: {status}\n"
                )
            FreeCAD.Console.PrintMessage(
                f"{len(output_objects)} parts created.\n"
            )
            if not all(part.is_printable for part in mesh_parts):
                self._error(
                    "PanelOptimizer: STL export blocked by printable limits:\n"
                    + "\n".join(
                        f"{part.name}: "
                        + ", ".join(
                            dimension
                            for dimension, within in (
                                ("X", part.within_x_limit),
                                ("Y", part.within_y_limit),
                            )
                            if not within
                        )
                        + " exceeds configured limit"
                        for part in mesh_parts
                        if not part.is_printable
                    )
                )
                return
            wait_started = time.perf_counter()
            output_directory = self._select_output_directory()
            interactive_wait += time.perf_counter() - wait_started
            if not output_directory:
                FreeCAD.Console.PrintWarning(
                    "PanelOptimizer: STL export cancelled; four result solids "
                    "remain in PanelOptimizer_Result.\n"
                )
                timings["total"] = time.perf_counter() - total_started - interactive_wait
                self._print_performance(timings)
                return
            artifacts = export_mesh_parts(
                mesh_parts, output_directory, timings=timings
            )
            timings["total"] = time.perf_counter() - total_started - interactive_wait
            FreeCAD.Console.PrintMessage(
                f"{len(artifacts)} STL files exported.\n"
            )
            self._print_performance(timings)
        except PanelOptimizerError as error:
            self._error(f"PanelOptimizer: {error}")
        except Exception as error:
            self._error(
                "PanelOptimizer: unexpected macro split failure: "
                f"{error}"
            )

    @staticmethod
    def _validate_seam_preview_names(document) -> None:
        """Reject unowned reserved preview names before document mutation."""
        for name in (
            "PanelOptimizer_VerticalSeam",
            "PanelOptimizer_HorizontalSeam",
        ):
            output = document.getObject(name)
            if output is not None and (
                "PanelOptimizerRole" not in tuple(output.PropertiesList)
                or output.PanelOptimizerRole != "PanelOptimizer.SeamPreview.v4"
            ):
                raise PanelOptimizerError(
                    f"Existing object '{name}' is not an owned seam preview."
                )
        lips = document.getObject("PanelOptimizer_Lips")
        if lips is not None and (
            "PanelOptimizerRole" not in tuple(lips.PropertiesList)
            or lips.PanelOptimizerRole != "PanelOptimizer.LipPreview.v4"
        ):
            raise PanelOptimizerError(
                "Existing object 'PanelOptimizer_Lips' is not an owned lip preview."
            )
        dowels = document.getObject("PanelOptimizer_Dowels")
        if dowels is not None and (
            "PanelOptimizerRole" not in tuple(dowels.PropertiesList)
            or dowels.PanelOptimizerRole != "PanelOptimizer.DowelPreview.v4"
        ):
            raise PanelOptimizerError(
                "Existing object 'PanelOptimizer_Dowels' is not an owned "
                "dowel preview."
            )

    @staticmethod
    def _write_seam_previews(
        document, seam_plan, z_value, recompute=True
    ) -> tuple[object, object]:
        """Create or update two owned lightweight Part polyline previews."""
        import Part

        definitions = (
            ("PanelOptimizer_VerticalSeam", seam_plan.vertical),
            ("PanelOptimizer_HorizontalSeam", seam_plan.horizontal),
        )
        previews = []
        for name, path in definitions:
            output = document.getObject(name)
            if output is None:
                output = document.addObject("Part::Feature", name)
                output.addProperty(
                    "App::PropertyString",
                    "PanelOptimizerRole",
                    "PanelOptimizer",
                )
                output.PanelOptimizerRole = "PanelOptimizer.SeamPreview.v4"
                output.setEditorMode("PanelOptimizerRole", 1)
            elif (
                "PanelOptimizerRole" not in tuple(output.PropertiesList)
                or output.PanelOptimizerRole != "PanelOptimizer.SeamPreview.v4"
            ):
                raise PanelOptimizerError(
                    f"Existing object '{name}' is not an owned seam preview."
                )
            vectors = tuple(
                FreeCAD.Vector(point.x_mm, point.y_mm, z_value)
                for point in path.points
            )
            output.Shape = Part.makePolygon(vectors)
            output.Label = name
            previews.append(output)
        if recompute:
            document.recompute()
        return tuple(previews)

    @staticmethod
    def _write_dowel_preview(document, cutters, recompute=True) -> object:
        """Create or update one owned lightweight compound of planned holes."""
        import Part

        name = "PanelOptimizer_Dowels"
        output = document.getObject(name)
        if output is None:
            output = document.addObject("Part::Feature", name)
            output.addProperty(
                "App::PropertyString",
                "PanelOptimizerRole",
                "PanelOptimizer",
            )
            output.PanelOptimizerRole = "PanelOptimizer.DowelPreview.v4"
            output.setEditorMode("PanelOptimizerRole", 1)
        elif (
            "PanelOptimizerRole" not in tuple(output.PropertiesList)
            or output.PanelOptimizerRole != "PanelOptimizer.DowelPreview.v4"
        ):
            raise PanelOptimizerError(
                f"Existing object '{name}' is not an owned dowel preview."
            )
        output.Shape = Part.makeCompound(tuple(cutter.copy() for cutter in cutters))
        output.Label = name
        view = getattr(output, "ViewObject", None)
        if view is not None:
            view.ShapeColor = (0.95, 0.65, 0.10)
            view.Transparency = 65
        if recompute:
            document.recompute()
        return output

    @staticmethod
    def _write_lip_preview(document, preview_shape, recompute=True) -> object:
        """Create or update the owned lightweight V4.50 lip compound."""
        name = "PanelOptimizer_Lips"
        output = document.getObject(name)
        if output is None:
            output = document.addObject("Part::Feature", name)
            output.addProperty(
                "App::PropertyString",
                "PanelOptimizerRole",
                "PanelOptimizer",
            )
            output.PanelOptimizerRole = "PanelOptimizer.LipPreview.v4"
            output.setEditorMode("PanelOptimizerRole", 1)
        elif (
            "PanelOptimizerRole" not in tuple(output.PropertiesList)
            or output.PanelOptimizerRole != "PanelOptimizer.LipPreview.v4"
        ):
            raise PanelOptimizerError(
                f"Existing object '{name}' is not an owned lip preview."
            )
        output.Shape = preview_shape.copy()
        output.Label = name
        view = getattr(output, "ViewObject", None)
        if view is not None:
            view.ShapeColor = (0.20, 0.75, 0.95)
            view.Transparency = 25
        if recompute:
            document.recompute()
        return output

    @staticmethod
    def _print_performance(timings) -> None:
        """Print one concise V4.61 stage report in seconds."""
        FreeCAD.Console.PrintMessage(
            "PanelOptimizer Performance V4.74A\n"
            f"Contour prep + route search: {timings.get('seams', 0.0):.3f} s\n"
            f"Topology validation: "
            f"{timings.get('topology_validation', 0.0):.3f} s\n"
            f"Split: {timings.get('split', 0.0):.3f} s\n"
            f"Dowels plan: {timings.get('dowel_plan', 0.0):.3f} s\n"
            f"Dowels cut: {timings.get('dowel_cut', 0.0):.3f} s\n"
            f"Lips: {timings.get('lips', 0.0):.3f} s\n"
            f"Mesh: {timings.get('mesh', 0.0):.3f} s\n"
            f"Mesh repair: {timings.get('mesh_repair', 0.0):.3f} s\n"
            f"STL export: {timings.get('stl_export', 0.0):.3f} s\n"
            f"STL verify: {timings.get('stl_verify', 0.0):.3f} s\n"
            f"Total: {timings.get('total', 0.0):.3f} s\n"
        )

    @staticmethod
    def _select_output_directory() -> str:
        """Ask for the existing directory used by transactional export."""
        from PySide import QtGui

        return str(
            QtGui.QFileDialog.getExistingDirectory(
                None,
                "Select PanelOptimizer STL output directory",
                "",
                QtGui.QFileDialog.ShowDirsOnly,
            )
        )

    @staticmethod
    def _error(message: str) -> None:
        """Emit one concise command failure without changing the source."""
        FreeCAD.Console.PrintError(message.rstrip() + "\n")


if hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand(
        "PanelOptimizer_SplitPanel",
        PanelOptimizerSplitPanelCommand(),
    )
