# -*- coding: utf-8 -*-
"""Application-level selection and FreeCAD document output for V4.00."""

from __future__ import annotations

from .Exceptions import InvalidSelectionError, SplitOperationError
from .SplitterEngine import SplitExecution

__all__ = ["SplitDocumentWriter", "validate_single_selection"]


def validate_single_selection(selection: object) -> object:
    """Return exactly one selected object with a shape-like value.

    Geometry validity remains the responsibility of ``SplitterEngine``. This
    helper translates GUI selection state into explicit project exceptions and
    does not access or mutate the document.
    """
    try:
        selected = tuple(selection)
    except TypeError as error:
        raise InvalidSelectionError("Selection is unavailable.") from error
    if not selected:
        raise InvalidSelectionError("Select exactly one panel object.")
    if len(selected) != 1:
        raise InvalidSelectionError(
            "Select exactly one panel object; multiple sources are unsupported."
        )
    source_object = selected[0]
    if not hasattr(source_object, "Shape"):
        raise InvalidSelectionError("Selected object has no Shape.")
    return source_object


class SplitDocumentWriter:
    """Transactionally create or safely update four owned result objects."""

    GROUP_NAME = "PanelOptimizer_Result"
    PART_NAMES = ("Part_1", "Part_2", "Part_3", "Part_4")
    ROLE_PROPERTY = "PanelOptimizerRole"
    SOURCE_PROPERTY = "PanelOptimizerSourceId"
    RESULT_PROPERTY = "PanelOptimizerResultId"
    PART_PROPERTY = "PanelOptimizerPartId"
    GROUP_ROLE = "PanelOptimizer.SplitResultGroup.v4"
    PART_ROLE = "PanelOptimizer.PrintablePart.v4"

    def write(
        self,
        document: object,
        execution: SplitExecution,
    ) -> tuple[object, ...]:
        """Create or safely replace the deterministic result group.

        Replacement is allowed only when the existing group and all four
        reserved part names carry the exact PanelOptimizer ownership markers
        and form the expected group membership. Owned objects are updated in
        place inside a FreeCAD transaction, with explicit B-rep backups because
        delete-and-recreate rollback is not reliable for group membership.
        Hard failure restores the previous valid shapes. Unowned name
        collisions fail before mutation, and source geometry is never removed
        or hidden.
        """
        if document is None:
            raise SplitOperationError("An active document is required.")
        if len(execution.result.parts) != 4 or len(execution.shapes) != 4:
            raise SplitOperationError(
                "Document output requires exactly four split parts."
            )

        previous = self._owned_previous_result(document)
        if previous is not None:
            return self._replace_owned_result(document, execution, previous)

        try:
            document.openTransaction("PanelOptimizer four-part result")
        except Exception as error:
            raise SplitOperationError(
                "Document cannot start a transactional result update."
            ) from error

        try:
            group = document.addObject(
                "App::DocumentObjectGroup",
                self.GROUP_NAME,
            )
            group.Label = self.GROUP_NAME
            self._add_string_property(group, self.ROLE_PROPERTY, self.GROUP_ROLE)
            self._add_string_property(
                group,
                self.SOURCE_PROPERTY,
                execution.result.source_id,
            )
            self._add_string_property(
                group,
                self.RESULT_PROPERTY,
                execution.result.result_id,
            )

            objects: list[object] = []
            for expected_name, part, shape in zip(
                self.PART_NAMES,
                execution.result.parts,
                execution.shapes,
            ):
                if part.name != expected_name:
                    raise SplitOperationError(
                        "Split-part order does not match document naming."
                    )
                output = document.addObject("Part::Feature", expected_name)
                output.Label = expected_name
                output.Shape = shape.copy()
                self._add_string_property(
                    output,
                    self.ROLE_PROPERTY,
                    self.PART_ROLE,
                )
                self._add_string_property(
                    output,
                    self.SOURCE_PROPERTY,
                    part.source_id,
                )
                self._add_string_property(
                    output,
                    self.RESULT_PROPERTY,
                    part.split_result_id,
                )
                self._add_string_property(
                    output,
                    self.PART_PROPERTY,
                    part.part_id,
                )
                group.addObject(output)
                view_object = getattr(output, "ViewObject", None)
                if view_object is not None:
                    view_object.Visibility = True
                objects.append(output)
            document.recompute()
            if tuple(item.Name for item in group.Group) != self.PART_NAMES:
                raise SplitOperationError(
                    "Result group does not contain the exact ordered part set."
                )
            document.commitTransaction()
            return tuple(objects)
        except Exception as error:
            try:
                document.abortTransaction()
                self._remove_initial_result_names(document)
                document.recompute()
            except Exception as rollback_error:
                raise SplitOperationError(
                    "Result update failed and the previous document state "
                    "could not be restored."
                ) from rollback_error
            if isinstance(error, SplitOperationError):
                raise
            raise SplitOperationError(
                "Unable to create deterministic split-result objects."
            ) from error

    def _replace_owned_result(
        self,
        document: object,
        execution: SplitExecution,
        previous: tuple[object, tuple[object, ...]],
    ) -> tuple[object, ...]:
        """Replace only owned part shapes with explicit rollback backups."""
        group, output_parts = previous
        shape_backups = tuple(part.Shape.copy() for part in output_parts)
        group_source = self._property_value(group, self.SOURCE_PROPERTY)
        group_result = self._property_value(group, self.RESULT_PROPERTY)
        part_provenance = tuple(
            (
                self._property_value(part, self.SOURCE_PROPERTY),
                self._property_value(part, self.RESULT_PROPERTY),
                self._property_value(part, self.PART_PROPERTY),
            )
            for part in output_parts
        )
        try:
            document.openTransaction("PanelOptimizer replace four-part result")
        except Exception as error:
            raise SplitOperationError(
                "Document cannot start a transactional result replacement."
            ) from error

        try:
            setattr(group, self.SOURCE_PROPERTY, execution.result.source_id)
            setattr(group, self.RESULT_PROPERTY, execution.result.result_id)
            for expected_name, output, model_part, shape in zip(
                self.PART_NAMES,
                output_parts,
                execution.result.parts,
                execution.shapes,
            ):
                if model_part.name != expected_name:
                    raise SplitOperationError(
                        "Split-part order does not match document naming."
                    )
                output.Label = expected_name
                output.Shape = shape.copy()
                setattr(output, self.SOURCE_PROPERTY, model_part.source_id)
                setattr(output, self.RESULT_PROPERTY, model_part.split_result_id)
                setattr(output, self.PART_PROPERTY, model_part.part_id)
                view_object = getattr(output, "ViewObject", None)
                if view_object is not None:
                    view_object.Visibility = True
            document.recompute()
            if tuple(item.Name for item in group.Group) != self.PART_NAMES:
                raise SplitOperationError(
                    "Owned result group changed during replacement."
                )
            document.commitTransaction()
            return output_parts
        except Exception as error:
            try:
                document.abortTransaction()
            except Exception:
                pass
            try:
                restored_group = document.getObject(self.GROUP_NAME)
                restored_parts = tuple(
                    document.getObject(name) for name in self.PART_NAMES
                )
                if restored_group is None or any(
                    part is None for part in restored_parts
                ):
                    raise SplitOperationError(
                        "Owned result objects disappeared during rollback."
                    )
                setattr(restored_group, self.SOURCE_PROPERTY, group_source)
                setattr(restored_group, self.RESULT_PROPERTY, group_result)
                for restored, shape, provenance in zip(
                    restored_parts,
                    shape_backups,
                    part_provenance,
                ):
                    restored.Shape = shape
                    setattr(restored, self.SOURCE_PROPERTY, provenance[0])
                    setattr(restored, self.RESULT_PROPERTY, provenance[1])
                    setattr(restored, self.PART_PROPERTY, provenance[2])
                document.recompute()
            except Exception as rollback_error:
                raise SplitOperationError(
                    "Result replacement failed and the previous valid shapes "
                    "could not be restored."
                ) from rollback_error
            if isinstance(error, SplitOperationError):
                raise
            raise SplitOperationError(
                "Unable to replace deterministic split-result objects; the "
                "previous valid result was restored."
            ) from error

    def _owned_previous_result(
        self,
        document: object,
    ) -> tuple[object, tuple[object, ...]] | None:
        """Return a complete owned result or reject every unsafe collision."""
        try:
            group = document.getObject(self.GROUP_NAME)
            reserved_parts = tuple(
                document.getObject(name) for name in self.PART_NAMES
            )
        except Exception as error:
            raise SplitOperationError(
                "Document cannot be inspected for result-name conflicts."
            ) from error

        if group is None:
            if any(part is not None for part in reserved_parts):
                raise SplitOperationError(
                    "Document contains reserved Part_1 ... Part_4 names not "
                    "owned by a PanelOptimizer result group."
                )
            return None
        if self._property_value(group, self.ROLE_PROPERTY) != self.GROUP_ROLE:
            raise SplitOperationError(
                "Existing PanelOptimizer_Result is not an owned V4 result group."
            )
        if (
            self._property_value(group, self.SOURCE_PROPERTY) is None
            or self._property_value(group, self.RESULT_PROPERTY) is None
        ):
            raise SplitOperationError(
                "Existing owned result group lacks required provenance."
            )
        if any(part is None for part in reserved_parts):
            raise SplitOperationError(
                "Existing PanelOptimizer result is incomplete and cannot be "
                "replaced automatically."
            )
        if tuple(item.Name for item in group.Group) != self.PART_NAMES:
            raise SplitOperationError(
                "Existing PanelOptimizer result has unexpected group members."
            )
        for expected_name, part in zip(self.PART_NAMES, reserved_parts):
            if (
                part.Name != expected_name
                or self._property_value(part, self.ROLE_PROPERTY) != self.PART_ROLE
                or self._property_value(part, self.SOURCE_PROPERTY) is None
                or self._property_value(part, self.RESULT_PROPERTY) is None
                or self._property_value(part, self.PART_PROPERTY) is None
            ):
                raise SplitOperationError(
                    f"Existing object '{expected_name}' is not an owned "
                    "PanelOptimizer result part."
                )
        return group, reserved_parts

    def _remove_initial_result_names(self, document: object) -> None:
        """Remove initial-write names proven absent during preflight."""
        for name in reversed(self.PART_NAMES):
            part = document.getObject(name)
            if part is not None:
                document.removeObject(name)
        group = document.getObject(self.GROUP_NAME)
        if group is not None:
            document.removeObject(self.GROUP_NAME)

    @staticmethod
    def _add_string_property(
        document_object: object,
        property_name: str,
        value: str,
    ) -> None:
        """Add one hidden-editor ownership/provenance string property."""
        document_object.addProperty(
            "App::PropertyString",
            property_name,
            "PanelOptimizer",
        )
        setattr(document_object, property_name, str(value))
        document_object.setEditorMode(property_name, 1)

    @staticmethod
    def _property_value(document_object: object, property_name: str) -> str | None:
        """Return one existing string property without creating it."""
        if property_name not in tuple(getattr(document_object, "PropertiesList", ())):
            return None
        return str(getattr(document_object, property_name))
