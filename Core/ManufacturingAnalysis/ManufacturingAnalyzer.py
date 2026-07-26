# -*- coding: utf-8 -*-
"""Orchestration of the implemented manufacturing evaluations."""

from __future__ import annotations

from ..Exceptions import ManufacturingAnalysisError
from ..Models import (
    GeometricAnalysis,
    GeometrySnapshot,
    ManufacturingAnalysis,
    ManufacturingProfile,
    TopologyAnalysis,
)
from .ConstraintEvaluator import ConstraintEvaluator

__all__ = ["ManufacturingAnalyzer"]


class ManufacturingAnalyzer:
    """Coordinate constraint evaluation and deterministic overall status."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        geometric: GeometricAnalysis,
        profile: ManufacturingProfile,
    ) -> ManufacturingAnalysis:
        """Return manufacturing interpretation for one immutable profile.

        Constraint failures are valid results and never exceptions. Exceptions
        indicate inability to perform a configured evaluation.
        """
        try:
            evaluations = ConstraintEvaluator().evaluate(
                geometry,
                topology,
                geometric,
                profile,
            )
            warnings = ()
            return ManufacturingAnalysis(
                profile_id=profile.profile_id,
                profile_version=profile.profile_version,
                settings_version=profile.settings_version,
                overall_status=self._overall_status(evaluations, warnings),
                constraint_evaluations=evaluations,
                warnings=warnings,
            )
        except ManufacturingAnalysisError:
            raise
        except Exception as error:
            raise ManufacturingAnalysisError(
                "Unable to evaluate manufacturing constraints."
            ) from error

    @staticmethod
    def _overall_status(
        evaluations: tuple[object, ...],
        warnings: tuple[object, ...],
    ) -> str:
        """Derive status without weighting, scoring, or subjective aggregation."""
        if any(
            item.constraint_level == "hard" and item.status == "fail"
            for item in evaluations
        ):
            return "fail"
        if warnings or any(item.status == "warning" for item in evaluations):
            return "warning"
        if evaluations:
            return "pass"
        return "not_evaluated"
