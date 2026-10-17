"""Cross-provider comparison with declared semantics, bound to real execution records.

Two execution records from DIFFERENT, INDEPENDENT provider paths (different
provider ids and no shared declared dependency or identical provider
environment), compared on named outputs of those records in the units the
records themselves state, after a declared mapping, against a declared
tolerance.  The exact compared values are digest-bound.  Agreement is
corroboration between the two numerical paths -- never truth, never
validation.  A comparison whose region/selection was chosen after seeing the
data is labelled ``post_hoc`` and classified as such.

Phase 2 BR11: :func:`compare_providers` compares outputs; it does not know
whether the two records solved the same scientific problem (each side's
``problem_digest`` is what ONE provider was asked).  :func:`corroborate` is the
cross-solver corroboration entry point: it requires a SAME_PROBLEM
:class:`~.problem_identity.ProblemEquivalence` of two canonical problems and
each record's declared :class:`~.problem_identity.ProblemBinding`, and records
what the comparison does and does not establish.  A comparison made without
them reports ``same_problem_established = False``.

Phase 3.5 WS1 (owner direction, closes OD-P2-3): same-problem admission is
MANDATORY for corroboration.  A comparison made by :func:`compare_providers`
alone is a DIAGNOSTIC: it is classified
``diagnostic_numerical_comparison_not_corroboration`` and can never reach the
independent-provider level of a verification ladder.  Only :func:`corroborate`
(a derived SAME_PROBLEM of two canonical problems, every aspect required, and
one binding per record) yields ``solver_corroboration_not_validation``.
DIFFERENT_PROBLEM and UNDETERMINED are refused there.  A STORED comparison
record is re-checked by :func:`corroboration_admission_problems` wherever it
is consumed, so a record written before this rule -- classified as
corroboration without an admission -- is refused, never promoted.  Equal
provider-input digests and matching outputs are never admission.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity, is_ratio_scale
from .identity import content_digest
from .problem_identity import (
    DEFAULT_REQUIRED,
    CanonicalProblem,
    ProblemBinding,
    ProblemEquivalence,
    ProblemIdentityVerdict,
    compare_problems,
)
from .records import ProviderExecutionRecord

_HEX = frozenset("0123456789abcdef")
_ENVIRONMENTS = ("conda-environment", "python-environment")

CORROBORATION_CLASS = "solver_corroboration_not_validation"
DIAGNOSTIC_CLASS = "diagnostic_numerical_comparison_not_corroboration"


@dataclass(frozen=True)
class OutputSelection:
    """How the compared values are taken FROM a record output (declared, digest-bound; never caller values).

    Applied in order: ``weights`` (a declared linear map -- each result point is
    ``sum(w * X[i])`` over its ``(i, w)`` terms, e.g. the mean of a cell's corner
    nodes), then ``rows``, then ``component``.
    """

    rows: tuple[int, ...] | None = None
    component: int | None = None
    weights: tuple[tuple[tuple[int, float], ...], ...] | None = None

    def __post_init__(self) -> None:
        # A selection decides what is compared, so it cannot shrink or erase the difference: each weighted point is an AFFINE
        # combination (finite weights >= 0 summing to 1, distinct indices).  Zero or scaled weights would make any two records agree,
        # and weights that do not sum to 1 would convert an offset unit (degC) wrongly.
        def index(i: Any, label: str) -> int:
            if isinstance(i, bool) or not isinstance(i, (int, np.integer)) or i < 0:
                raise InvalidScientificProblem(f"an output selection {label} must be a non-negative integer index, got {i!r}")
            return int(i)

        if self.weights is not None:
            if not self.weights or any(not terms for terms in self.weights):
                raise InvalidScientificProblem("an output selection's weights need at least one point and one term per point")
            for terms in self.weights:
                idx = [index(i, "weight index") for i, _ in terms]
                if len(set(idx)) != len(idx):
                    raise InvalidScientificProblem("an output selection point repeats an index")
                ws = [w for _, w in terms]
                if any(isinstance(w, bool) or not isinstance(w, (int, float, np.floating)) or not math.isfinite(w) or w < 0 for w in ws):
                    raise InvalidScientificProblem("an output selection's weights must be finite numbers >= 0")
                if not math.isclose(math.fsum(ws), 1.0, rel_tol=0.0, abs_tol=1e-12):
                    raise InvalidScientificProblem(f"an output selection point's weights sum to {math.fsum(ws)!r}, not 1 (an affine combination)")
        if self.rows is not None:
            rows = [index(i, "row") for i in self.rows]
            if not rows or len(set(rows)) != len(rows):
                raise InvalidScientificProblem("an output selection's rows must be non-empty and distinct")
        if self.component is not None:
            index(self.component, "component")

    def apply(self, values) -> np.ndarray:
        x = np.asarray(values, dtype=float)
        if self.weights is not None:
            x = np.stack([sum(w * x[i] for i, w in terms) for terms in self.weights])
        if self.rows is not None:
            x = x[list(self.rows)]
        if self.component is not None:
            x = x[:, self.component]
        return np.ravel(x)

    def to_dict(self) -> dict[str, Any]:
        return {"rows": None if self.rows is None else [int(i) for i in self.rows], "component": self.component,
                "weights": None if self.weights is None else [[[int(i), repr(float(w))] for i, w in t] for t in self.weights]}


def _output_values(record: Any, name: str) -> np.ndarray:
    """The named output's values exactly as the record holds them (in the record's own unit)."""
    from ..numerical.core import NumericalExecutionRecord
    from ..pde.contracts import PDEExecutionRecord

    if isinstance(record, ProviderExecutionRecord):
        if name in record.arrays:
            return np.asarray(record.arrays[name][1], dtype=float)
        for s in record.series:
            if s.quantity_id == name:
                return np.asarray(s.values, dtype=float)
        return np.asarray([float(record.scalars[name].magnitude)])
    if isinstance(record, PDEExecutionRecord):
        return np.asarray(record.field.values, dtype=float)
    if isinstance(record, NumericalExecutionRecord):
        def scalar(q) -> float:
            m = np.ravel(np.asarray(q.magnitude, dtype=float))
            if m.size != 1:
                raise InvalidScientificProblem(f"output {name!r} is not a scalar state variable")
            return float(m[0])
        if record.trajectory:
            return np.asarray([scalar(state[name]) for _, state in record.trajectory])
        return np.asarray([scalar(record.outputs[name])])
    raise InvalidScientificProblem("not an execution record")


@dataclass(frozen=True)
class ExecutionRef:
    """The comparable facts of one execution record (never a caller's stand-in)."""

    provider_id: str
    execution_identity: str
    problem_digest: str
    dependencies: tuple[tuple[str, str, str], ...]
    outputs: Mapping[str, str] = field(default_factory=dict)  # output name -> unit stated by the record

    @classmethod
    def of(cls, record: Any) -> "ExecutionRef":
        if isinstance(record, ProviderExecutionRecord):
            if not record.succeeded:
                raise InvalidScientificProblem("a failed execution is never compared")
            units = {k: str(v.units) for k, v in record.scalars.items()}
            units.update({s.quantity_id: s.unit for s in record.series})
            units.update({k: u for k, (u, _) in record.arrays.items()})
            return cls(record.identity.provider_id, record.identity.digest, record.identity.problem_digest,
                       tuple(record.identity.provider_dependencies), units)
        # Forge-internal provider records (BIG 6 numerical, BIG 8 PDE) carry their own identity
        from ..numerical.core import NumericalExecutionRecord
        from ..pde.contracts import PDEExecutionRecord

        if isinstance(record, (NumericalExecutionRecord, PDEExecutionRecord)):
            if not record.succeeded:
                raise InvalidScientificProblem("a failed execution is never compared")
            if isinstance(record, PDEExecutionRecord):
                units = {record.field.definition.quantity_id: record.field.definition.unit}
            else:
                units = {k: str(v.units) for k, v in record.outputs.items() if isinstance(v, Quantity)}
                for _, state in record.trajectory:
                    units.update({k: str(v.units) for k, v in state.items() if isinstance(v, Quantity)})
            # in-process record: its code ran in THIS interpreter's environment (bound as a dependency)
            from .catalog import python_environment_digest

            env_digest, count = python_environment_digest()
            return cls(record.provider.solver_id, record.execution_identity, record.problem_digest,
                       (("provider", record.provider.version, content_digest(record.provider.to_dict())),
                        ("python-environment", f"{count} distributions", env_digest)), units)
        raise InvalidScientificProblem(f"{type(record).__name__} is not an execution record; stand-ins are not compared")


@dataclass(frozen=True)
class ComparisonDeclaration:
    observable: str
    unit: str
    mapping: str
    absolute_tolerance: Quantity
    relative_tolerance: float
    context: str
    #: True when the compared region/selection was chosen after seeing results
    post_hoc: bool = False

    def __post_init__(self) -> None:
        for label in ("observable", "mapping", "context"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"a cross-provider comparison declares its {label}")
        # a tolerance is a SPREAD: degC -> delta, never an offset point (0.5 degC is not 273.65 K)
        self.absolute_tolerance.magnitude_as_spread_in(self.unit)
        if self.relative_tolerance < 0:
            raise InvalidScientificProblem("relative tolerance must be non-negative")
        if self.relative_tolerance > 0 and not is_ratio_scale(self.unit):
            raise InvalidScientificProblem(f"a relative tolerance on the offset scale {self.unit!r} is meaningless; use a ratio-scale unit")

    def to_dict(self) -> dict[str, Any]:
        return {"observable": self.observable, "unit": self.unit, "mapping": self.mapping,
                "absolute_tolerance": self.absolute_tolerance.to_dict(), "relative_tolerance": self.relative_tolerance,
                "context": self.context, "post_hoc": self.post_hoc}


@dataclass(frozen=True)
class ProviderComparison:
    declaration: ComparisonDeclaration
    a: ExecutionRef
    b: ExecutionRef
    a_output: str
    b_output: str
    a_selection: OutputSelection
    b_selection: OutputSelection
    values_digest: str
    points: int
    max_absolute: float
    max_relative: float
    within_tolerance: bool
    #: Phase 2 BR11: set only by :func:`corroborate`; absent, nothing says the records solved one problem
    problem_equivalence: ProblemEquivalence | None = None
    problem_bindings: tuple[ProblemBinding, ...] = ()

    @property
    def same_problem_established(self) -> bool:
        return (
            self.problem_equivalence is not None
            and self.problem_equivalence.verdict is ProblemIdentityVerdict.SAME_PROBLEM
            and tuple(self.problem_equivalence.required) == tuple(sorted(DEFAULT_REQUIRED))
            and len(self.problem_bindings) == 2
        )

    @property
    def classification(self) -> str:
        # Phase 3.5 WS1: without a derived same-problem admission a comparison is a diagnostic, never corroboration
        base = CORROBORATION_CLASS if self.same_problem_established else DIAGNOSTIC_CLASS
        return f"post_hoc_{base}" if self.declaration.post_hoc else base

    def to_dict(self) -> dict[str, Any]:
        return {"classification": self.classification, "declaration": self.declaration.to_dict(),
                "a_provider": self.a.provider_id, "a_identity": self.a.execution_identity, "a_problem": self.a.problem_digest,
                "a_output": self.a_output, "a_selection": self.a_selection.to_dict(), "b_provider": self.b.provider_id,
                "b_identity": self.b.execution_identity, "b_problem": self.b.problem_digest, "b_output": self.b_output,
                "b_selection": self.b_selection.to_dict(), "values_digest": self.values_digest,
                "points": self.points, "max_absolute": repr(self.max_absolute), "max_relative": repr(self.max_relative),
                "within_tolerance": self.within_tolerance,
                # Phase 3.5 WS1: always stated (a deliberate identity change of every comparison record)
                "same_problem_established": self.same_problem_established,
                # absent unless corroborate() admitted the problems
                **({"problem_equivalence": self.problem_equivalence.to_dict(),
                    "problem_bindings": [b.to_dict() for b in self.problem_bindings],
                    "establishes": "numerical agreement (or not) of two independent provider paths on one declared "
                                   "canonical problem, within the declared tolerance",
                    "does_not_establish": ["validation", "physical truth", "model-form adequacy",
                                           "that either provider input faithfully translates the canonical problem",
                                           "either side's numerical error"]}
                   if self.problem_equivalence is not None else {})}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


def shared_dependencies(a: ExecutionRef, b: ExecutionRef) -> list[str]:
    """Why two paths are NOT (known to be) independent; empty only when both declare their dependencies and share none."""
    shared = []
    for ref in (a, b):
        if not any(d[0] != "provider" for d in ref.dependencies):
            shared.append(f"independence UNKNOWN: {ref.provider_id} declares no dependency set")
    names_a = {d[0].lower(): d for d in a.dependencies if d[0] not in _ENVIRONMENTS + ("provider",)}
    names_b = {d[0].lower(): d for d in b.dependencies if d[0] not in _ENVIRONMENTS + ("provider",)}
    shared += sorted(set(names_a) & set(names_b))
    if a.provider_id.lower() in names_b:
        shared.append(f"{b.provider_id} depends on {a.provider_id}")
    if b.provider_id.lower() in names_a:
        shared.append(f"{a.provider_id} depends on {b.provider_id}")
    envs_a = {d[2] for d in a.dependencies if d[0] in _ENVIRONMENTS}
    envs_b = {d[2] for d in b.dependencies if d[0] in _ENVIRONMENTS}
    if envs_a & envs_b:
        shared.append("identical provider environment")
    return shared


def compare_providers(declaration: ComparisonDeclaration, a: Any, a_output: str, b: Any, b_output: str, *,
                      a_select: OutputSelection = OutputSelection(), b_select: OutputSelection = OutputSelection()) -> ProviderComparison:
    """A DIAGNOSTIC numerical comparison of the named outputs of two execution records.

    ``a``/``b`` are execution records (provider records, or Forge-internal BIG 6 /
    BIG 8 records).  Values AND units are read from the records; the caller
    supplies only the declared, digest-bound :class:`OutputSelection`.  The
    result is classified ``diagnostic_numerical_comparison_not_corroboration``
    (Phase 3.5 WS1): it says how two numbers differ, not that two solvers agreed
    on one problem.  For corroboration use :func:`corroborate`.
    """
    ra, rb = ExecutionRef.of(a), ExecutionRef.of(b)
    for ref in (ra, rb):
        if len(ref.execution_identity) != 64 or set(ref.execution_identity) - _HEX:
            raise InvalidScientificProblem("comparison sides must carry sha256 execution identities")
    if ra.provider_id == rb.provider_id:
        raise InvalidScientificProblem("a comparison needs two independent provider paths, not one provider twice")
    shared = shared_dependencies(ra, rb)
    if shared:
        raise InvalidScientificProblem(f"{ra.provider_id} and {rb.provider_id} are not independent: {shared}")
    if a_output not in ra.outputs or b_output not in rb.outputs:
        raise InvalidScientificProblem(f"compared outputs must be outputs the records produced ({a_output!r}, {b_output!r})")
    ua, ub = ra.outputs[a_output], rb.outputs[b_output]
    try:
        a_raw, b_raw = a_select.apply(_output_values(a, a_output)), b_select.apply(_output_values(b, b_output))
    except (IndexError, KeyError, ValueError) as exc:
        raise InvalidScientificProblem(f"the declared selection does not fit the record outputs: {exc}") from exc
    av = np.asarray([Quantity(float(x), ua).magnitude_in(declaration.unit) for x in a_raw])
    bv = np.asarray([Quantity(float(x), ub).magnitude_in(declaration.unit) for x in b_raw])
    if av.shape != bv.shape or av.size == 0:
        raise InvalidScientificProblem("compared values must be mapped onto the same points first")
    if not (np.all(np.isfinite(av)) and np.all(np.isfinite(bv))):
        raise InvalidScientificProblem("non-finite values are never compared")
    diff = np.abs(av - bv)
    scale = np.maximum(np.abs(av), np.abs(bv))
    rel = np.where(scale > 0, diff / np.where(scale > 0, scale, 1.0), 0.0)
    atol = declaration.absolute_tolerance.magnitude_as_spread_in(declaration.unit)
    ok = bool(np.all((diff <= atol) | (rel <= declaration.relative_tolerance)))
    values_digest = content_digest({"a": [repr(float(x)) for x in av], "b": [repr(float(x)) for x in bv]})
    return ProviderComparison(declaration, ra, rb, a_output, b_output, a_select, b_select, values_digest, int(av.size),
                              float(diff.max()), float(rel.max()), ok)


def corroborate(declaration: ComparisonDeclaration, a: Any, a_output: str, b: Any, b_output: str, *,
                problems: tuple[CanonicalProblem, CanonicalProblem], bindings: tuple[ProblemBinding, ProblemBinding],
                a_select: OutputSelection = OutputSelection(), b_select: OutputSelection = OutputSelection()) -> ProviderComparison:
    """Cross-solver corroboration: compare only after the two records are admitted as solving ONE problem.

    ``problems`` are the two CANONICAL problems; their equivalence is derived
    here with every aspect required (a caller-built equivalence, or one
    narrowed to a few aspects, is not accepted).  Refused unless that is
    SAME_PROBLEM and each binding names its record's execution identity and the
    canonical problem on its side.  The usual independence and unit rules of
    :func:`compare_providers` apply.
    """
    if len(problems) != 2 or any(not isinstance(p, CanonicalProblem) for p in problems):
        raise InvalidScientificProblem("corroboration takes the two CanonicalProblem records, not a verdict")
    problems = compare_problems(problems[0], problems[1], required=DEFAULT_REQUIRED)
    if problems.verdict is not ProblemIdentityVerdict.SAME_PROBLEM:
        raise InvalidScientificProblem(
            f"the two records are not admitted as solving one problem ({problems.verdict.value}: differing "
            f"{list(problems.differing)}, undeclared {list(problems.undeclared)}); their outputs are not compared"
        )
    if len(bindings) != 2 or any(not isinstance(item, ProblemBinding) for item in bindings):
        raise InvalidScientificProblem("corroboration needs one ProblemBinding per record")
    ra, rb = ExecutionRef.of(a), ExecutionRef.of(b)
    for ref, binding, side in ((ra, bindings[0], problems.a_problem), (rb, bindings[1], problems.b_problem)):
        if binding.execution_identity != ref.execution_identity:
            raise InvalidScientificProblem(f"the problem binding of {ref.provider_id} names another execution")
        if binding.problem_digest != side:
            raise InvalidScientificProblem(f"{ref.provider_id}'s execution is bound to another canonical problem")
    made = compare_providers(declaration, a, a_output, b, b_output, a_select=a_select, b_select=b_select)
    from dataclasses import replace

    admitted = replace(made, problem_equivalence=problems, problem_bindings=tuple(bindings))
    problems_found = corroboration_admission_problems(admitted.to_dict())
    if problems_found:  # pragma: no cover - corroborate builds an admitted record by construction
        raise InvalidScientificProblem(f"internal: an admitted comparison fails its own re-check: {problems_found}")
    return admitted


#: Phase 3.5 WS1: the one authoritative re-check of a STORED comparison record
def corroboration_admission_problems(record: Mapping[str, Any]) -> list[str]:
    """Why ``record`` (a ``ProviderComparison.to_dict()``, possibly read back from storage) is NOT admitted corroboration.

    Empty only when the record carries a SAME_PROBLEM equivalence with every
    aspect required, nothing differing or undeclared, the two canonical digests
    equal, and exactly two problem bindings that name the record's two
    executions and that canonical problem.  It re-checks consistency; it cannot
    prove that the declarations are faithful (see ``problem_identity``).
    """
    problems: list[str] = []
    equivalence = record.get("problem_equivalence")
    bindings = record.get("problem_bindings")
    if not isinstance(equivalence, Mapping):
        return ["no same-problem admission is recorded (a diagnostic comparison, or a record from before mandatory "
                "admission)"]
    if equivalence.get("verdict") != ProblemIdentityVerdict.SAME_PROBLEM.value:
        problems.append(f"the recorded problem identity is {equivalence.get('verdict')!r}, not same_problem")
    if sorted(equivalence.get("required") or ()) != sorted(DEFAULT_REQUIRED):
        problems.append("the admission did not require every problem aspect")
    if equivalence.get("differing") or equivalence.get("undeclared"):
        problems.append("the admission records differing or undeclared aspects")
    a_problem, b_problem = equivalence.get("a_problem"), equivalence.get("b_problem")
    if not a_problem or a_problem != b_problem:
        problems.append("the two canonical problem digests differ")
    if not isinstance(bindings, (list, tuple)) or len(bindings) != 2:
        problems.append("corroboration needs exactly two problem bindings")
    else:
        for binding, side in zip(bindings, ("a_identity", "b_identity")):
            if not isinstance(binding, Mapping) or binding.get("execution_identity") != record.get(side):
                problems.append(f"the binding for {side} names another execution")
            elif binding.get("problem_digest") != a_problem:
                problems.append(f"the binding for {side} names another canonical problem")
    if record.get("same_problem_established") is not True:
        problems.append("the record does not state same_problem_established = true")
    return problems
