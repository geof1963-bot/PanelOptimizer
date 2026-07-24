# -*- coding: utf-8 -*-
"""
***************************************************************************
*   PanelOptimizer - FreeCAD Workbench                                    *
*                                                                         *
*   BaseObject.py                                                         *
*                                                                         *
*   Base class shared by all engine modules.                              *
*                                                                         *
***************************************************************************
"""

from __future__ import annotations

import logging
from typing import Any


class BaseObject:
    """
    Base class for all PanelOptimizer engine objects.
    """

    VERSION = "3.01"

    def __init__(self) -> None:

        self._valid: bool = True

        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._infos: list[str] = []

        self._logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_error(self, message: str) -> None:
        self._errors.append(message)
        self._valid = False
        self._logger.error(message)

    def add_warning(self, message: str) -> None:
        self._warnings.append(message)
        self._logger.warning(message)

    def add_info(self, message: str) -> None:
        self._infos.append(message)
        self._logger.info(message)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._valid = True
        self.clear_messages()

    def clear_messages(self) -> None:
        self._errors.clear()
        self._warnings.clear()
        self._infos.clear()

    def is_valid(self) -> bool:
        return self._valid

    def has_errors(self) -> bool:
        return len(self._errors) > 0

    def has_warnings(self) -> bool:
        return len(self._warnings) > 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def errors(self) -> list[str]:
        return self._errors.copy()

    @property
    def warnings(self) -> list[str]:
        return self._warnings.copy()

    @property
    def infos(self) -> list[str]:
        return self._infos.copy()

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:

        return {
            "class": self.__class__.__name__,
            "version": self.VERSION,
            "valid": self._valid,
            "errors": self._errors.copy(),
            "warnings": self._warnings.copy(),
            "infos": self._infos.copy(),
        }

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}"
            f"(valid={self._valid}, "
            f"errors={len(self._errors)}, "
            f"warnings={len(self._warnings)})>"
        )

    def __str__(self) -> str:
        return self.__repr__()