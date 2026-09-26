"""Fast-physics subsystem contract for the multi-timescale runtime.

A :class:`FastSystem` is a Forge system execution (typically a BIG 9
``MultiphysicsRuntime`` run over real providers) seen from the slow scale:
it takes an exact :class:`FastExecutionRequest` -- resolved BIG 2 window,
slow and fast state, and the exact environment/usage inputs of that window --
and returns a :class:`FastExecutionResult` with resolved output histories,
the materials it resolved and the run digests it produced.

The multi-timescale layer never reaches into provider internals (dolfinx,
preCICE, ...); it only sees these records.  Requests are identified by
content, which is what makes EXACT fast-execution reuse safe: two operating
windows that merely look alike are never reused.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..coupling.adapters import ParticipantStateContract
from ..materials import MaterialState
from ..scenarios.timeline import TimeWindow, canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics.receipts import StateVariableValue
from ._common import identifier
from .aggregation import OutputSeries

IDENTITY_SCHEMA = "engcore.multiscale.fast_system_identity/1"


@dataclass(frozen=True)
class MaterialBinding:
    """A SLOW state variable is a condition of an identified material.

    The fast system must re-resolve that material's properties at exactly the
    requested slow-state value on every execution (no stale property reuse).
    """

    participant_id: str
    variable_id: str
    material_digest: str
    condition_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "variable_id": self.variable_id,
                "material_digest": self.material_digest, "condition_id": self.condition_id}


@dataclass(frozen=True)
class FastSystemIdentity:
    system_id: str
    version: str
    graph_fingerprint: str
    plan: Mapping[str, Any]
    providers: tuple[tuple[str, str], ...]
    configuration: Mapping[str, Any]
    contracts: tuple[ParticipantStateContract, ...]
    material_bindings: tuple[MaterialBinding, ...]
    outputs: tuple[tuple[str, str], ...]
    #: Whether a field mapping happens inside the fast system.  ``None`` is
    #: UNDECLARED and keeps the mapping-error component UNKNOWN; only an explicit
    #: ``False`` with a basis makes it NOT_APPLICABLE.
    field_mapping: bool | None = None
    field_mapping_basis: str = ""
    #: Declared: an execution is a pure function of its request (no warm
    #: starts, no state carried between executions).  Exact reuse of a cached
    #: result is allowed ONLY for a pure system; the basis is recorded.
    pure: bool = False
    purity_basis: str = ""
    #: Every participant of the fast graph; one state contract each (no contract
    #: is never "complete by omission").
    participants: tuple[str, ...] = ()
    #: Per output: (quantity_id, preserved history features, max sample duration
    #: in exact seconds "p/q").  The runtime enforces them; nothing defaults.
    output_semantics: tuple[tuple[str, tuple[str, ...], str], ...] = ()
    #: Per SLOW variable: (participant, variable, "bound" | "not_consumed", basis).
    slow_state_use: tuple[tuple[str, str, str, str], ...] = ()
    #: Declared: execution depends on time ONLY through the request (window,
    #: environment and usage records) -- no drive cycle hidden in configuration.
    time_inputs_via_request: bool = False
    time_inputs_basis: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "system_id", identifier(self.system_id, "fast system_id"))
        if not self.providers:
            raise InvalidScientificProblem("a fast system names the providers (and versions) it executes")
        ids = [c.participant_id for c in self.contracts]
        if len(set(ids)) != len(ids):
            raise InvalidScientificProblem("one state contract per fast participant")
        if self.pure and not str(self.purity_basis or "").strip():
            raise InvalidScientificProblem("a purity declaration must state its basis")
        if any(not str(v).strip() for _, v in self.providers):
            raise InvalidScientificProblem("every provider entry names an installed version")
        if self.field_mapping is not None and not str(self.field_mapping_basis).strip():
            raise InvalidScientificProblem("a field-mapping declaration states its basis")
        if self.time_inputs_via_request and not str(self.time_inputs_basis).strip():
            raise InvalidScientificProblem("the time-input declaration states its basis")
        for _, _, use, basis in self.slow_state_use:
            if use not in ("bound", "not_consumed") or not str(basis).strip():
                raise InvalidScientificProblem("slow-state use is 'bound' or 'not_consumed', with a basis")

    def output_unit(self, quantity_id: str) -> str:
        for q, unit in self.outputs:
            if q == quantity_id:
                return unit
        raise InvalidScientificProblem(f"fast system {self.system_id!r} produces no output {quantity_id!r}")

    def contract(self, participant_id: str) -> ParticipantStateContract | None:
        return next((c for c in self.contracts if c.participant_id == participant_id), None)

    @property
    def restartable(self) -> bool:
        return all(c.restartable for c in self.contracts)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": IDENTITY_SCHEMA, "system_id": self.system_id, "version": self.version,
                "graph_fingerprint": self.graph_fingerprint, "plan": dict(self.plan),
                "providers": [list(p) for p in sorted(self.providers)], "configuration": dict(self.configuration),
                "contracts": [c.to_dict() for c in sorted(self.contracts, key=lambda c: c.participant_id)],
                "material_bindings": [b.to_dict() for b in self.material_bindings],
                "outputs": [list(o) for o in sorted(self.outputs)], "field_mapping": self.field_mapping,
                "field_mapping_basis": self.field_mapping_basis, "pure": self.pure, "purity_basis": self.purity_basis,
                "participants": sorted(self.participants),
                "output_semantics": [[q, sorted(f), r] for q, f, r in sorted(self.output_semantics)],
                "slow_state_use": [list(x) for x in sorted(self.slow_state_use)],
                "time_inputs_via_request": self.time_inputs_via_request, "time_inputs_basis": self.time_inputs_basis}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def _state_list(values: Mapping[str, Mapping[str, StateVariableValue]]) -> list[dict[str, Any]]:
    return [{"participant_id": pid, "value": values[pid][k].to_dict()} for pid in sorted(values) for k in sorted(values[pid])]


@dataclass(frozen=True)
class FastExecutionRequest:
    """Exact identity of one fast execution (the cache key for exact reuse).

    State mappings are read-only snapshots: a fast system cannot write back
    into the runtime's authoritative slow state.
    """

    request_id: str
    system_digest: str
    scenario_digest: str
    timeline_digest: str
    environment_digest: str
    window: TimeWindow
    slow_state: Mapping[str, Mapping[str, StateVariableValue]]
    fast_state: Mapping[str, Mapping[str, StateVariableValue]]
    environment_context: tuple[Mapping[str, Any], ...]
    usage_context: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"system_digest": self.system_digest, "scenario_digest": self.scenario_digest,
                "timeline_digest": self.timeline_digest, "environment_digest": self.environment_digest,
                "window": self.window.to_dict(), "slow_state": _state_list(self.slow_state),
                "fast_state": _state_list(self.fast_state), "environment_context": list(self.environment_context),
                "usage_context": list(self.usage_context)}

    @property
    def identity(self) -> str:
        # request_id is a label, not identity: the same inputs are the same execution
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class FastExecutionResult:
    request_identity: str
    run_ids: tuple[str, ...]
    run_digests: tuple[str, ...]
    series: tuple[OutputSeries, ...]
    end_fast_state: Mapping[str, Mapping[str, StateVariableValue]]
    material_states: tuple[MaterialState, ...]
    resolved_properties: tuple[Mapping[str, Any], ...]
    coupled_windows: int
    coupling_iterations: int
    window_outcomes: tuple[str, ...]
    provider_versions: tuple[tuple[str, str], ...]
    #: Digests of the environment and timeline the execution actually read
    #: (echoed so the runtime can refuse a system bound to other inputs).
    consumed_environment_digest: str = ""
    consumed_timeline_digest: str = ""
    #: canonical digest of the slow state the execution actually used
    #: (``slow_state_digest(request.slow_state)``); a mismatch is refused.
    consumed_slow_state_digest: str = ""
    #: Numerical diagnostics that are not identity (e.g. wall time).
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def series_for(self, quantity_id: str) -> OutputSeries:
        for s in self.series:
            if s.quantity_id == quantity_id:
                return s
        raise InvalidScientificProblem(f"fast execution produced no {quantity_id!r} history")

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "fast_physics_execution_not_evidence", "request_identity": self.request_identity,
                "run_ids": list(self.run_ids), "run_digests": list(self.run_digests),
                "series": [s.to_dict() for s in self.series], "end_fast_state": _state_list(self.end_fast_state),
                "material_states": [m.to_dict() for m in self.material_states],
                "resolved_properties": list(self.resolved_properties), "coupled_windows": self.coupled_windows,
                "coupling_iterations": self.coupling_iterations, "window_outcomes": list(self.window_outcomes),
                "provider_versions": [list(p) for p in sorted(self.provider_versions)],
                "consumed_environment_digest": self.consumed_environment_digest,
                "consumed_timeline_digest": self.consumed_timeline_digest,
                "consumed_slow_state_digest": self.consumed_slow_state_digest}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def slow_state_digest(state: Mapping[str, Mapping[str, StateVariableValue]]) -> str:
    """The digest a fast result must echo for the slow state it says it consumed.

    A consistency check against a mis-wired wrapper -- not a proof of consumption:
    a wrapper can echo a digest it computed without using the state.
    """
    return canonical_digest(_state_list(state))


class FastSystem(ABC):
    identity: FastSystemIdentity

    @abstractmethod
    def execute(self, request: FastExecutionRequest) -> FastExecutionResult:
        """Run the fast physics for ``request.window`` from the requested state.

        Must raise (never return a partial result) when a provider fails, an
        input is UNKNOWN or a window does not converge.
        """


def check_material_reresolution(identity: FastSystemIdentity, request: FastExecutionRequest, result: FastExecutionResult) -> None:
    """Refuse a result whose materials were not resolved at the requested slow state."""
    for b in identity.material_bindings:
        requested = request.slow_state.get(b.participant_id, {}).get(b.variable_id)
        if requested is None:
            raise InvalidScientificProblem(f"material binding {b.participant_id}.{b.variable_id} has no requested slow state")
        matches = [m for m in result.material_states if m.material.digest == b.material_digest]
        if not matches:
            raise InvalidScientificProblem(f"fast execution did not resolve material {b.material_digest[:12]}... bound to "
                                           f"{b.participant_id}.{b.variable_id}")
        for m in matches:
            c = m.condition(b.condition_id)
            if c is None or c.value.magnitude_in(requested.value.units) != requested.value.magnitude:
                raise InvalidScientificProblem(
                    f"fast execution resolved material properties at a stale {b.condition_id!r} "
                    f"({None if c is None else c.value}); requested {requested.value}")
