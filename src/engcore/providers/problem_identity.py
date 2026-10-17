"""Did two solvers solve the SAME scientific problem? (Phase 2 BR11)

A provider's ``problem_digest`` is a digest of what THAT provider was asked, in
its own input language.  Two independent solvers of one mathematical problem
are asked different things -- different meshes, file formats, parameter
spellings -- so equal provider digests are neither necessary nor sufficient for
"same problem", and this module never reads them as such.

Instead a :class:`CanonicalProblem` states the problem in provider-independent
terms, one declaration per :class:`ProblemAspect` (governing equations, model
assumptions, geometry, materials, initial and boundary conditions, sources,
time interval, quantities of interest, model versions).  Quantities are
canonicalized to their base unit with the repository's identity rule, so
``1000 mm`` and ``1 m`` are one declaration; an absolute value and a
difference on an offset scale are kept apart.  Discretization, mesh, solver,
solver configuration, tolerances and provider inputs are NOT aspects: two
genuinely independent numerical approaches to one problem differ exactly there.

:func:`compare_problems` answers SAME_PROBLEM only when every required aspect is
declared on both sides and agrees; DIFFERENT_PROBLEM when a declared-on-both
aspect differs; UNDETERMINED otherwise.  UNDETERMINED never becomes SAME.

What this does not establish: that a provider's input is a faithful
translation of the canonical problem.  That is the translating adapter's claim,
recorded by :class:`ProblemBinding` and checked (as far as anything checks it)
by the adapter's qualification routes -- not here.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import (
    IDENTITY_SIGNIFICANT_DIGITS,
    Quantity,
    base_unit,
    canonical_magnitude,
    is_delta_unit,
)

PROBLEM_IDENTITY_SCHEMA = "engcore.providers.canonical_problem/1"


class ProblemAspect(str, Enum):
    GOVERNING_EQUATIONS = "governing_equations"
    MODEL_ASSUMPTIONS = "model_assumptions"
    DOMAIN_GEOMETRY = "domain_geometry"
    MATERIALS = "materials"
    INITIAL_CONDITIONS = "initial_conditions"
    BOUNDARY_CONDITIONS = "boundary_conditions"
    SOURCES_AND_LOADS = "sources_and_loads"
    TIME_INTERVAL = "time_interval"
    QUANTITIES_OF_INTEREST = "quantities_of_interest"
    MODEL_VERSIONS = "model_versions"


#: Never aspects of the scientific problem: they are how it is solved, or what one provider was asked.
EXCLUDED_ASPECTS = frozenset({
    "discretization", "mesh", "solver", "solver_configuration", "tolerances", "provider_input", "provider_digest",
})


class ProblemIdentityVerdict(str, Enum):
    SAME_PROBLEM = "same_problem"
    DIFFERENT_PROBLEM = "different_problem"
    UNDETERMINED = "undetermined"


def canonical_value(value: Any) -> Any:
    """A provider-independent, JSON-able canonical form of one declaration (refuses what it cannot canonicalize)."""
    if isinstance(value, Quantity):
        unit = str(value.units)
        base = base_unit(unit)
        return {"quantity": canonical_magnitude(value, base), "base_unit": base, "difference": bool(is_delta_unit(unit))}
    if isinstance(value, Enum):
        return canonical_value(value.value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        # one number, one form: 1 and 1.0 agree, the text "1.0" does not; quantized like a Quantity
        number = float(value)
        if not math.isfinite(number):
            raise InvalidScientificProblem("a canonical problem declaration is finite")
        number = float(f"{number:.{IDENTITY_SIGNIFICANT_DIGITS}g}")
        return {"number": repr(0.0 if number == 0.0 else number)}
    if isinstance(value, Mapping):
        return {str(k): canonical_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [canonical_value(v) for v in value]
    raise InvalidScientificProblem(
        f"{type(value).__name__} has no canonical problem form; declare it as quantities, numbers, text and mappings"
    )


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class CanonicalProblem:
    """A scientific problem stated in provider-independent terms, aspect by aspect."""

    problem_id: str
    declarations: Mapping[Any, Any]

    def __post_init__(self) -> None:
        if not str(self.problem_id).strip():
            raise InvalidScientificProblem("a canonical problem has an id")
        canonical: dict[str, Any] = {}
        for key, value in dict(self.declarations).items():
            name = str(getattr(key, "value", key)).strip()
            if name in EXCLUDED_ASPECTS:
                raise InvalidScientificProblem(
                    f"{name!r} is not an aspect of the scientific problem: it is how the problem is solved or what "
                    f"one provider was asked, and independent solvers differ there by design"
                )
            try:
                aspect = ProblemAspect(name)
            except ValueError:
                raise InvalidScientificProblem(f"unknown problem aspect {name!r}") from None
            canonical[aspect.value] = canonical_value(value)
        if not canonical:
            raise InvalidScientificProblem("a canonical problem declares at least one aspect")
        object.__setattr__(self, "problem_id", str(self.problem_id).strip())
        object.__setattr__(self, "declarations", dict(sorted(canonical.items())))

    def aspect_digest(self, aspect: ProblemAspect) -> str | None:
        """Digest of one declared aspect; None when the aspect is not declared (never a digest of nothing)."""
        name = ProblemAspect(aspect).value
        return _digest(self.declarations[name]) if name in self.declarations else None

    @property
    def digest(self) -> str:
        return _digest({"schema": PROBLEM_IDENTITY_SCHEMA, "declarations": self.declarations})

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROBLEM_IDENTITY_SCHEMA, "problem_id": self.problem_id, "declarations": dict(self.declarations),
                "digest": self.digest}


@dataclass(frozen=True)
class ProblemEquivalence:
    """The answer to "did these two describe one scientific problem", with the aspects that decided it."""

    a_problem: str
    b_problem: str
    verdict: ProblemIdentityVerdict
    required: tuple[str, ...]
    differing: tuple[str, ...]
    undeclared: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", ProblemIdentityVerdict(self.verdict))
        if self.verdict is ProblemIdentityVerdict.SAME_PROBLEM and (self.differing or self.undeclared):
            raise InvalidScientificProblem("SAME_PROBLEM leaves no aspect differing or undeclared")
        if self.verdict is ProblemIdentityVerdict.DIFFERENT_PROBLEM and not self.differing:
            raise InvalidScientificProblem("DIFFERENT_PROBLEM names the aspects that differ")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "problem_equivalence", "a_problem": self.a_problem, "b_problem": self.b_problem,
                "verdict": self.verdict.value, "required": list(self.required), "differing": list(self.differing),
                "undeclared": list(self.undeclared),
                "notice": ("equivalence of two canonical declarations; it does not establish that either provider "
                           "input is a faithful translation of them")}


#: By default every aspect must be declared on both sides.
DEFAULT_REQUIRED = tuple(aspect.value for aspect in ProblemAspect)


def compare_problems(a: CanonicalProblem, b: CanonicalProblem, *,
                     required: Iterable[Any] = DEFAULT_REQUIRED) -> ProblemEquivalence:
    if not isinstance(a, CanonicalProblem) or not isinstance(b, CanonicalProblem):
        raise InvalidScientificProblem("problem identity compares CanonicalProblem records only")
    needed = tuple(sorted({ProblemAspect(str(getattr(r, "value", r))).value for r in required}))
    if not needed:
        raise InvalidScientificProblem("problem identity requires at least one aspect")
    aspects = sorted(set(a.declarations) | set(b.declarations) | set(needed))
    differing = tuple(x for x in aspects
                      if x in a.declarations and x in b.declarations and _digest(a.declarations[x]) != _digest(b.declarations[x]))
    undeclared = tuple(x for x in aspects
                       if (x in needed and (x not in a.declarations or x not in b.declarations))
                       or ((x in a.declarations) != (x in b.declarations)))
    if differing:
        verdict = ProblemIdentityVerdict.DIFFERENT_PROBLEM
    elif undeclared:
        verdict = ProblemIdentityVerdict.UNDETERMINED
    else:
        verdict = ProblemIdentityVerdict.SAME_PROBLEM
    return ProblemEquivalence(a.digest, b.digest, verdict, needed, differing, undeclared)


@dataclass(frozen=True)
class ProblemBinding:
    """An adapter's declaration that one execution was its translation of one canonical problem.

    A declaration with its translator named, never a proof: it is what lets a
    comparison refuse records that were not even CLAIMED to solve the compared problem.
    """

    execution_identity: str
    problem_digest: str
    translator: str

    def __post_init__(self) -> None:
        for label in ("execution_identity", "problem_digest"):
            value = str(getattr(self, label)).strip().lower()
            if len(value) != 64 or set(value) - set("0123456789abcdef"):
                raise InvalidScientificProblem(f"a problem binding names a sha256 {label}")
            object.__setattr__(self, label, value)
        if not str(self.translator).strip():
            raise InvalidScientificProblem("a problem binding names the adapter that translated the problem")

    def to_dict(self) -> dict[str, Any]:
        return {"execution_identity": self.execution_identity, "problem_digest": self.problem_digest,
                "translator": self.translator, "classification": "declared_translation_not_verified"}


__all__ = [
    "CanonicalProblem", "DEFAULT_REQUIRED", "EXCLUDED_ASPECTS", "ProblemAspect", "ProblemBinding", "ProblemEquivalence",
    "ProblemIdentityVerdict", "canonical_value", "compare_problems",
]
