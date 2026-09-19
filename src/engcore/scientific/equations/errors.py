"""Errors owned by the universal equation/law IR."""

from __future__ import annotations

from ..errors import ScientificCoreError


class EquationIRError(ScientificCoreError):
    """Base class for equation/law representation failures."""


class EquationDimensionError(EquationIRError):
    """A symbolic expression cannot be assigned a physically valid dimension."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(message)


class EquationEvaluationError(EquationIRError):
    """A typed equation could not be evaluated under supplied bindings."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(message)
