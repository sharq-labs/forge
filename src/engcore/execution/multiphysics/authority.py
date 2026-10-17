"""Which component owns coupled execution, and the status of every other coupling loop (Phase 2 BR8).

One authority
-------------
:class:`~engcore.execution.multiphysics.runtime.MultiphysicsRuntime` is the one
owner of general multiphysics iteration: participant order (Jacobi or serial
Gauss-Seidel), the fixed-point residual and which interfaces it must cover,
relaxation and IQN-ILS, divergence and stagnation, window subdivision and
step-size memory, exact window boundaries, event alignment, deterministic
checkpoint/restore, outcome classification
(:func:`~engcore.execution.multiphysics.runtime.assess_run_outcome`) and
conservation admission
(:func:`~engcore.execution.multiphysics.runtime.require_conservation`).

Domain packs join it through participants (``CallbackParticipant``,
``ExternalSolverParticipant``, and for steady result-producing problems
:class:`~engcore.execution.multiphysics.steady.ResultParticipant`), never by
writing a second loop.

Paths that are not (yet) that authority
---------------------------------------
:data:`COUPLING_PATHS` declares each one with what it does, whether it
delegates, and what is left before it can.  It is a record, not a convention:
the test suite checks that every declared module exists, and the electrothermal
fixed point -- the one remaining second loop -- is declared ``NOT_MIGRATED``
with its exact remaining work rather than renamed into compliance.

One outcome vocabulary
----------------------
:func:`fixed_point_outcome` reads the electrothermal loop's own outcome token
in the runtime's :class:`CouplingRunOutcome` terms, so a reader handles one
vocabulary.  It interprets nothing beyond the token: ``criterion_met`` is the
loop's fixed-point criterion, never a solution-error or validation statement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ...scientific.errors import InvalidScientificProblem
from .runtime import CouplingRunOutcome


class CouplingPathStatus(str, Enum):
    #: owns iteration, convergence, rollback, windows, outcome and conservation admission
    AUTHORITATIVE = "authoritative"
    #: runs its coupling through the authoritative runtime
    DELEGATES = "delegates"
    #: a second coupling loop that still decides its own convergence; migration recorded
    NOT_MIGRATED = "not_migrated"
    #: sequences solves without any fixed point (one-way coupling); nothing to migrate
    NOT_A_COUPLING_LOOP = "not_a_coupling_loop"
    #: an external coupling library iterates; Forge renders its contract and re-checks the residual itself
    EXTERNAL_ENGINE = "external_engine"


@dataclass(frozen=True)
class CouplingPath:
    path_id: str
    module: str
    status: CouplingPathStatus
    semantics: str
    remaining: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", CouplingPathStatus(self.status))
        if not str(self.path_id).strip() or not str(self.module).strip() or not str(self.semantics).strip():
            raise InvalidScientificProblem("a coupling path names its id, module and semantics")
        if self.status in (CouplingPathStatus.NOT_MIGRATED, CouplingPathStatus.EXTERNAL_ENGINE) and not str(self.remaining).strip():
            raise InvalidScientificProblem(f"coupling path {self.path_id!r} is not migrated and must say what remains")

    def to_dict(self) -> dict[str, Any]:
        return {"path_id": self.path_id, "module": self.module, "status": self.status.value,
                "semantics": self.semantics, "remaining": self.remaining}


COUPLING_PATHS: tuple[CouplingPath, ...] = (
    CouplingPath(
        "multiphysics_runtime", "engcore.execution.multiphysics.runtime", CouplingPathStatus.AUTHORITATIVE,
        "explicit and implicit windows; Jacobi and serial Gauss-Seidel; constant/Aitken relaxation and IQN-ILS "
        "(Jacobi); required-interface convergence coverage; divergence/stagnation; window subdivision and step-size "
        "memory; exact rational window boundaries; event alignment; deterministic checkpoint/restore; typed run "
        "outcomes; required conservation",
    ),
    CouplingPath(
        "system_runtime_multiphysics_node", "engcore.system_runtime.authorities", CouplingPathStatus.DELEGATES,
        "MultiphysicsAuthority runs a node through MultiphysicsRuntime and admits it only through "
        "assess_run_outcome and require_conservation",
    ),
    CouplingPath(
        "multiscale_fast_physics", "engcore.multiscale.runtime", CouplingPathStatus.DELEGATES,
        "macro windows on the slow time scale; the fast physics of each representative window is a "
        "MultiphysicsRuntime run",
    ),
    CouplingPath(
        "drone_hover_product", "engcore.systems.products.drone_coupled", CouplingPathStatus.DELEGATES,
        "implicit serial MultiphysicsRuntime plan over the propeller / electrical / battery / thermal chain",
    ),
    CouplingPath(
        "electrothermal_fixed_point", "engcore.systems.electrothermal.coupled", CouplingPathStatus.NOT_MIGRATED,
        "steady Gauss-Seidel (Picard) fixed point over ScientificResult records, torn-edge LINF criterion in one "
        "ratio-scale unit, optional under-relaxation of the TORN values only, TRANSFER_REFUSED stop",
        remaining=(
            "Phase 3.5 WS2: a code-complete migration candidate exists (runtime_adapter.run_coupled_via_runtime: "
            "torn-only relaxation via RelaxationPolicy.scope='lagged_edges', TRANSFER_REFUSED mapped, a native-shaped "
            "CoupledRun so credibility.CouplingEvidence reads it unchanged), selected by "
            "runtime_adapter.run_electrothermal_coupling with NATIVE as the default; before the product path may "
            "delegate: execute the parity tests (DV-49, DV-88..DV-90) and have the owner set "
            "RUNTIME_PATH_PARITY_VERIFIED"
        ),
    ),
    CouplingPath(
        "battery_cell_body_march", "engcore.domains.battery.coupling", CouplingPathStatus.NOT_A_COUPLING_LOOP,
        "one-way cell -> body march: the body does not drive the cell back, so there is no fixed point",
    ),
    CouplingPath(
        "provider_participants", "engcore.coupling.adapters", CouplingPathStatus.DELEGATES,
        "provider_participant / field_port / mapped_input wrap provider solves (FEniCSx, PyBaMM, ...) as participants "
        "of MultiphysicsRuntime; the runtime decides convergence",
    ),
    CouplingPath(
        "precice_scalar_two_way", "forge_precice", CouplingPathStatus.EXTERNAL_ENGINE,
        "preCICE runs the iterations between separate participant processes from a Forge-rendered "
        "ScalarTwoWayContract; Forge accepts the record only if preCICE converged AND its own fixed-point residual "
        "check on the exchanged values passes",
        remaining=(
            "a second convergence check outside the runtime: its acceptance is a provider record, not a runtime run; "
            "scalar two-way only; owner decision whether preCICE becomes a participant transport under the runtime "
            "or stays a separate external engine"
        ),
    ),
)


class CouplingMaturity(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    IMPLEMENTED_UNEXECUTED = "implemented_unexecuted"
    #: executed in an earlier tree with a recorded result; not re-run on the current tree
    EXECUTED_HISTORICALLY = "executed_historically"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ExternalCouplingMaturity:
    """Three separate claims per provider: adaptation, field exchange, and end-to-end coupled execution."""

    provider_id: str
    adaptation: CouplingMaturity
    field_exchange: CouplingMaturity
    coupled_execution: CouplingMaturity
    basis: str

    def __post_init__(self) -> None:
        for label in ("adaptation", "field_exchange", "coupled_execution"):
            object.__setattr__(self, label, CouplingMaturity(getattr(self, label)))
        if not str(self.basis).strip():
            raise InvalidScientificProblem("a coupling maturity statement cites its basis")

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "adaptation": self.adaptation.value,
                "field_exchange": self.field_exchange.value, "coupled_execution": self.coupled_execution.value,
                "basis": self.basis}


#: Phase 2 BR12: what is known about each external provider's coupling, stated per claim.  An adapter's
#: code existing is not proof that a coupled simulation executes; nothing here is a maturity stage of the ledger.
EXTERNAL_PROVIDER_COUPLING: tuple[ExternalCouplingMaturity, ...] = (
    ExternalCouplingMaturity(
        "fenicsx", CouplingMaturity.EXECUTED_HISTORICALLY, CouplingMaturity.EXECUTED_HISTORICALLY,
        CouplingMaturity.EXECUTED_HISTORICALLY,
        "providers/fenicsx/tests (incl. test_coupling_fenicsx: FEniCSx thermal <-> SciPy electrical on the runtime, "
        "mapped fields, conservation audit) recorded 133 passed in the WSL fenicsx env on a BIG-14-era tree "
        "(docs/work/PROGRESS.md); not re-run on this tree",
    ),
    ExternalCouplingMaturity(
        "openfoam", CouplingMaturity.EXECUTED_HISTORICALLY, CouplingMaturity.NOT_IMPLEMENTED,
        CouplingMaturity.NOT_IMPLEMENTED,
        "forge_openfoam runs one icoFoam cavity case to endTime (process provider, executed in the battery env "
        "historically); it has no time-window session, no boundary-condition update between windows and no "
        "interface-field read-back, so it cannot be a coupled participant",
    ),
    ExternalCouplingMaturity(
        "su2", CouplingMaturity.EXECUTED_HISTORICALLY, CouplingMaturity.NOT_IMPLEMENTED,
        CouplingMaturity.NOT_IMPLEMENTED,
        "forge_su2 runs one case per execution (process provider); no window session or interface exchange",
    ),
    ExternalCouplingMaturity(
        "fe_cfd_conjugate_heat_transfer", CouplingMaturity.BLOCKED, CouplingMaturity.BLOCKED, CouplingMaturity.BLOCKED,
        "a real FE <-> CFD conjugate heat-transfer coupling is a new capability foundation under the active-epic "
        "policy (no ledger capability exists; EXC-1 is open, so a second exception triggers the anti-loophole "
        "review): blocked pending an owner decision. Prerequisites are recorded in DEFERRED_VALIDATION.md (P2-BR12)",
    ),
)


def coupling_authority() -> CouplingPath:
    """The one authoritative coupling path."""
    authoritative = [p for p in COUPLING_PATHS if p.status is CouplingPathStatus.AUTHORITATIVE]
    if len(authoritative) != 1:
        raise InvalidScientificProblem(f"exactly one coupling authority must be declared, found {len(authoritative)}")
    return authoritative[0]


_FIXED_POINT_TOKENS = {
    "criterion_met": CouplingRunOutcome.CONVERGED,
    "iteration_limit_reached": CouplingRunOutcome.NOT_COMPLETED,
    "transfer_refused": CouplingRunOutcome.NOT_COMPLETED,
}


def fixed_point_outcome(outcome: Any) -> CouplingRunOutcome:
    """The electrothermal fixed point's own outcome token, read in the runtime's vocabulary.

    An unknown token is refused rather than guessed: a new member of that enum
    must be classified here before anything reads it.
    """
    token = str(getattr(outcome, "value", outcome)).strip()
    try:
        return _FIXED_POINT_TOKENS[token]
    except KeyError:
        raise InvalidScientificProblem(f"unclassified fixed-point outcome {token!r}") from None


__all__ = [
    "COUPLING_PATHS",
    "CouplingMaturity",
    "CouplingPath",
    "CouplingPathStatus",
    "EXTERNAL_PROVIDER_COUPLING",
    "ExternalCouplingMaturity",
    "coupling_authority",
    "fixed_point_outcome",
]
