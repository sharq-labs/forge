"""Cross-provider comparison with declared semantics, bound to real execution records.

Two execution records from DIFFERENT, INDEPENDENT provider paths (different
provider ids and no shared declared dependency or identical provider
environment), compared on named outputs of those records in the units the
records themselves state, after a declared mapping, against a declared
tolerance.  The exact compared values are digest-bound.  Agreement is
corroboration between the two numerical paths -- never truth, never
validation.  A comparison whose region/selection was chosen after seeing the
data is labelled ``post_hoc`` and classified as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity, is_ratio_scale
from .identity import content_digest
from .records import ProviderExecutionRecord

_HEX = frozenset("0123456789abcdef")
_ENVIRONMENTS = ("conda-environment", "python-environment")


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

    @property
    def classification(self) -> str:
        return "post_hoc_solver_corroboration_not_validation" if self.declaration.post_hoc else "solver_corroboration_not_validation"

    def to_dict(self) -> dict[str, Any]:
        return {"classification": self.classification, "declaration": self.declaration.to_dict(),
                "a_provider": self.a.provider_id, "a_identity": self.a.execution_identity, "a_problem": self.a.problem_digest,
                "a_output": self.a_output, "a_selection": self.a_selection.to_dict(), "b_provider": self.b.provider_id,
                "b_identity": self.b.execution_identity, "b_problem": self.b.problem_digest, "b_output": self.b_output,
                "b_selection": self.b_selection.to_dict(), "values_digest": self.values_digest,
                "points": self.points, "max_absolute": repr(self.max_absolute), "max_relative": repr(self.max_relative),
                "within_tolerance": self.within_tolerance}

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
    """Compare the named outputs of two execution records after the declared selections/maps.

    ``a``/``b`` are execution records (provider records, or Forge-internal BIG 6 /
    BIG 8 records).  Values AND units are read from the records; the caller
    supplies only the declared, digest-bound :class:`OutputSelection`.
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
