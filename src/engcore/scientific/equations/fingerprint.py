"""Content fingerprints for equations and scientific-law records."""

from __future__ import annotations

import hashlib
from typing import Any

from ..serialization import to_json
from .ast import Equation
from .law import LawDefinition


def _digest(record: Any) -> str:
    return hashlib.sha256(to_json(record).encode("utf-8")).hexdigest()


def equation_fingerprint(equation: Equation) -> str:
    if not isinstance(equation, Equation):
        raise TypeError("equation_fingerprint requires Equation")
    return _digest(equation)


def law_fingerprint(law: LawDefinition) -> str:
    if not isinstance(law, LawDefinition):
        raise TypeError("law_fingerprint requires LawDefinition")
    return _digest(law)
