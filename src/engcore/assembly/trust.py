"""Completeness, not sufficiency: did every required trust protocol actually run?

The question a certification gate used to ask was "did some validation pass?".
Subset success is not completeness. A pack declaring four validation protocols
and executing one reports four-quarters of nothing, and the record read as a
clean pass because every result present was valid.

So the two completeness reports here compare **exact sets**: what the frozen
Composition Pack snapshot says this blueprint requires, against what the
authorized run actually executed. The difference is enumerated in both
directions, because both directions are defects:

``missing``
    a required protocol never ran.
``unexpected``
    a protocol ran that the pack does not require here -- a substitution, a
    stale artifact, or a protocol belonging to another blueprint.

Version is part of identity. ``ocv_adequacy@1`` executing where
``ocv_adequacy@2`` is required is a missing protocol *and* an unexpected one,
which is exactly what a silent version drift looks like from outside.

UNENFORCEABLE IS NOT SATISFIED
-------------------------------
A snapshot written before requirements were recorded cannot state its required
set. That case reports ``enforceable=False`` and never ``complete=True``: an
old record does not get to certify itself by having nothing to compare against.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from ..compositionpacks.snapshot import CompositionPackSnapshot
from ..scientific.corpus.authority import (
    AuthorityComponent,
    AuthorityRole,
    EvidenceBinding,
)
from ..scientific.corpus.numerical import NumericalCheck, NumericalEvidence
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.serialization import require_schema, schema_string
from ..sria.uncertainty import UncertaintyChannel

PROTOCOL_COMPLETENESS_SCHEMA = schema_string("forge_protocol_completeness")
UQ_CELL_SCHEMA = schema_string("forge_uq_coverage_cell")
UQ_COVERAGE_SCHEMA = schema_string("forge_uq_coverage")


@dataclass(frozen=True)
class ProtocolCompleteness:
    """Exact-set comparison of required against executed protocols."""

    kind: str
    blueprint_id: str
    required: tuple[tuple[str, str], ...]
    executed: tuple[tuple[str, str], ...]
    enforceable: bool

    def __post_init__(self) -> None:
        for label in ("kind", "blueprint_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"protocol completeness requires {label}")
            object.__setattr__(self, label, value)
        for label in ("required", "executed"):
            items = tuple(
                sorted((str(a), str(b)) for a, b in getattr(self, label))
            )
            object.__setattr__(self, label, items)
        if not isinstance(self.enforceable, bool):
            raise InvalidScientificProblem("enforceable must be a boolean")

    @property
    def missing(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(set(self.required) - set(self.executed)))

    @property
    def unexpected(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(set(self.executed) - set(self.required)))

    @property
    def duplicated(self) -> tuple[tuple[str, str], ...]:
        seen: dict[tuple[str, str], int] = {}
        for item in self.executed:
            seen[item] = seen.get(item, 0) + 1
        return tuple(sorted(key for key, count in seen.items() if count > 1))

    @property
    def complete(self) -> bool:
        """Exact-set equality, and only when the requirement is knowable."""
        return (
            self.enforceable
            and not self.missing
            and not self.unexpected
            and not self.duplicated
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROTOCOL_COMPLETENESS_SCHEMA,
            "kind": self.kind,
            "blueprint_id": self.blueprint_id,
            "required": [list(item) for item in self.required],
            "executed": [list(item) for item in self.executed],
            "enforceable": self.enforceable,
            "missing": [list(item) for item in self.missing],
            "unexpected": [list(item) for item in self.unexpected],
            "duplicated": [list(item) for item in self.duplicated],
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProtocolCompleteness":
        require_schema(payload, PROTOCOL_COMPLETENESS_SCHEMA)
        return cls(
            payload["kind"],
            payload["blueprint_id"],
            tuple(tuple(item) for item in payload.get("required", ())),
            tuple(tuple(item) for item in payload.get("executed", ())),
            bool(payload.get("enforceable", False)),
        )


class UQCellState(str, Enum):
    """What is known about one quantity on one uncertainty channel."""

    #: A quantified result exists for this cell.
    QUANTIFIED = "quantified"
    #: A producer ran and reported the channel as not determinable. Honest, and
    #: never converted to zero.
    UNKNOWN = "unknown"
    #: Required by the pack, and nothing was produced at all.
    MISSING = "missing"
    #: Produced where the pack requires nothing. Recorded, not counted.
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, order=True)
class UQCoverageCell:
    quantity: str
    channel: UncertaintyChannel
    state: UQCellState
    method_id: str = ""

    def __post_init__(self) -> None:
        quantity = str(self.quantity).strip()
        if not quantity:
            raise InvalidScientificProblem("uq coverage cell requires a quantity")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "channel", UncertaintyChannel(self.channel))
        object.__setattr__(self, "state", UQCellState(self.state))
        object.__setattr__(self, "method_id", str(self.method_id).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UQ_CELL_SCHEMA,
            "quantity": self.quantity,
            "channel": self.channel.value,
            "state": self.state.value,
            "method_id": self.method_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UQCoverageCell":
        require_schema(payload, UQ_CELL_SCHEMA)
        return cls(
            payload["quantity"],
            UncertaintyChannel(payload["channel"]),
            UQCellState(payload["state"]),
            payload.get("method_id", ""),
        )


@dataclass(frozen=True)
class UQCoverage:
    """Quantity x uncertainty-channel, every required cell present.

    The matrix is over the *required* cells, so a channel nobody produced shows
    as ``MISSING`` rather than being absent from the report. An absent row and
    an uncovered row read identically to a human skimming, and only one of them
    is a defect.
    """

    blueprint_id: str
    cells: tuple[UQCoverageCell, ...]
    enforceable: bool

    def __post_init__(self) -> None:
        blueprint = str(self.blueprint_id).strip()
        if not blueprint:
            raise InvalidScientificProblem("uq coverage requires blueprint_id")
        object.__setattr__(self, "blueprint_id", blueprint)
        cells = tuple(sorted(self.cells))
        if any(not isinstance(item, UQCoverageCell) for item in cells):
            raise InvalidScientificProblem("uq coverage requires UQCoverageCell records")
        keys = [(item.quantity, item.channel) for item in cells]
        if len(keys) != len(set(keys)):
            raise InvalidScientificProblem("uq coverage repeats a quantity/channel cell")
        object.__setattr__(self, "cells", cells)
        if not isinstance(self.enforceable, bool):
            raise InvalidScientificProblem("enforceable must be a boolean")

    def with_state(self, state: UQCellState) -> tuple[UQCoverageCell, ...]:
        wanted = UQCellState(state)
        return tuple(item for item in self.cells if item.state is wanted)

    @property
    def missing(self) -> tuple[UQCoverageCell, ...]:
        return self.with_state(UQCellState.MISSING)

    @property
    def unknown(self) -> tuple[UQCoverageCell, ...]:
        return self.with_state(UQCellState.UNKNOWN)

    @property
    def complete(self) -> bool:
        """Every required cell quantified. UNKNOWN is not coverage.

        A pack that declares no uncertainty requirement for a blueprint has an
        empty required set, and executing nothing satisfies it exactly -- the
        same reading protocol completeness uses. What is refused is a snapshot
        that cannot state its requirements at all.
        """
        required = [
            item for item in self.cells if item.state is not UQCellState.NOT_APPLICABLE
        ]
        return self.enforceable and all(
            item.state is UQCellState.QUANTIFIED for item in required
        )

    def counts(self) -> dict[str, int]:
        result = {state.value: 0 for state in UQCellState}
        for item in self.cells:
            result[item.state.value] += 1
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UQ_COVERAGE_SCHEMA,
            "blueprint_id": self.blueprint_id,
            "cells": [item.to_dict() for item in self.cells],
            "enforceable": self.enforceable,
            "counts": self.counts(),
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UQCoverage":
        require_schema(payload, UQ_COVERAGE_SCHEMA)
        return cls(
            payload["blueprint_id"],
            tuple(UQCoverageCell.from_dict(i) for i in payload.get("cells", ())),
            bool(payload.get("enforceable", False)),
        )


def assess_protocol_completeness(
    snapshot: CompositionPackSnapshot,
    blueprint_id: str,
    kind: str,
    executed: tuple[tuple[str, str], ...],
) -> ProtocolCompleteness:
    """Compare the snapshot's required protocol set against what ran."""
    if not isinstance(snapshot, CompositionPackSnapshot):
        raise TypeError("protocol completeness requires a CompositionPackSnapshot")
    required = snapshot.required_protocols(blueprint_id, kind)
    return ProtocolCompleteness(
        kind=kind,
        blueprint_id=blueprint_id,
        required=tuple(required),
        executed=tuple(executed),
        # Whether the requirement is STATED, not whether it is non-empty.
        # A pack that requires nothing here and executed nothing is
        # complete; a snapshot that cannot say is not.
        enforceable=snapshot.declares_requirements,
    )


def assess_uq_coverage(
    snapshot: CompositionPackSnapshot,
    blueprint_id: str,
    produced: Mapping[tuple[str, str], tuple[Uncertainty, str]],
) -> UQCoverage:
    """Build the quantity x channel matrix for one blueprint.

    ``produced`` maps ``(quantity, channel)`` to the uncertainty that was
    emitted and the method that emitted it. An emitted-but-unquantified record
    lands in ``UNKNOWN``, which is a different statement from ``MISSING`` and
    from a value of zero. None of the three is convertible into another.
    """
    if not isinstance(snapshot, CompositionPackSnapshot):
        raise TypeError("uq coverage requires a CompositionPackSnapshot")
    required = snapshot.required_uncertainty_cells(blueprint_id)
    cells: list[UQCoverageCell] = []
    for quantity, channel in sorted(required):
        found = produced.get((quantity, channel))
        if found is None:
            cells.append(
                UQCoverageCell(quantity, UncertaintyChannel(channel), UQCellState.MISSING)
            )
            continue
        uncertainty, method = found
        state = (
            UQCellState.QUANTIFIED
            if isinstance(uncertainty, Uncertainty) and uncertainty.is_quantified
            else UQCellState.UNKNOWN
        )
        cells.append(
            UQCoverageCell(quantity, UncertaintyChannel(channel), state, method)
        )
    for (quantity, channel), (uncertainty, method) in sorted(produced.items()):
        if (quantity, channel) in required:
            continue
        cells.append(
            UQCoverageCell(
                quantity,
                UncertaintyChannel(channel),
                UQCellState.NOT_APPLICABLE,
                method,
            )
        )
    return UQCoverage(
        blueprint_id=blueprint_id,
        cells=tuple(cells),
        enforceable=snapshot.declares_requirements,
    )


def evidence_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "PROTOCOL_COMPLETENESS_SCHEMA",
    "UQ_CELL_SCHEMA",
    "UQ_COVERAGE_SCHEMA",
    "ProtocolCompleteness",
    "UQCellState",
    "UQCoverage",
    "UQCoverageCell",
    "AuthorityComponent",
    "AuthorityRole",
    "EvidenceBinding",
    "NumericalCompleteness",
    "NumericalRequirement",
    "assess_numerical_completeness",
    "assess_protocol_completeness",
    "authorized_run_binding",
    "assess_uq_coverage",
    "evidence_digest",
]


def authorized_run_binding(authorized) -> EvidenceBinding:
    """The authority identity of one authorized run, as evidence must name it.

    This is the single place a computation's binding is derived, so validation
    evidence, numerical evidence and anything added later are all checked
    against the same statement of what the run actually was. Every participant
    contributes its model, realization and solver, because evidence about a
    model is about a model whether or not the run used ten others beside it.
    """
    run = authorized.run
    plan = authorized.graph_plan
    components: list[AuthorityComponent] = [
        # THE RUN CARRIES THE AUTHORIZED DIGEST. A run id alone is a name two
        # different computations can share; the digest is the computation.
        AuthorityComponent(AuthorityRole.RUN, run.run_id, digest=authorized.digest),
        AuthorityComponent(
            AuthorityRole.GRAPH, run.graph_id, digest=run.graph_fingerprint
        ),
        AuthorityComponent(
            AuthorityRole.COUPLING_PLAN, run.plan_id, digest=run.plan_fingerprint
        ),
        AuthorityComponent(AuthorityRole.BLUEPRINT, plan.blueprint_id, plan.blueprint_version),
        AuthorityComponent(
            AuthorityRole.COMPOSITION_PACK,
            authorized.composition_snapshot.pack_id,
            authorized.composition_snapshot.pack_version,
            authorized.composition_snapshot.authority_digest,
        ),
        AuthorityComponent(
            AuthorityRole.EXECUTION_PACK,
            authorized.execution_snapshot.pack_id,
            authorized.execution_snapshot.pack_version,
            authorized.execution_snapshot.authority_digest,
        ),
    ]
    if plan.scenario is not None:
        components.append(
            AuthorityComponent(
                AuthorityRole.SCENARIO,
                plan.scenario.scenario_id,
                plan.scenario.version,
                plan.scenario.digest,
            )
        )
    for pack_id, pack_version, digest in (
        authorized.composition_snapshot.dependency_authority_digests
    ):
        components.append(
            AuthorityComponent(
                AuthorityRole.DOMAIN_PACK, pack_id, pack_version, digest
            )
        )
    for participant in run.graph.participants:
        components.append(
            AuthorityComponent(
                AuthorityRole.MODEL, participant.model_id, participant.model_version
            )
        )
        components.append(
            AuthorityComponent(
                AuthorityRole.REALIZATION,
                participant.realization_id,
                participant.realization_version,
            )
        )
        components.append(
            AuthorityComponent(
                AuthorityRole.SOLVER, participant.solver_id, participant.solver_version
            )
        )
    unique: dict[tuple[str, str, str], AuthorityComponent] = {}
    for item in components:
        unique.setdefault(item.key, item)
    return EvidenceBinding(f"run:{run.run_id}", tuple(unique.values()))


@dataclass(frozen=True)
class NumericalRequirement:
    """Which numerical checks an authority requires. Stated, possibly empty.

    The distinction that matters is the one :class:`ProtocolCompleteness`
    already draws: "requires none" and "has not said" are different, and only
    the first can be satisfied by producing nothing. A caller-supplied tuple
    could not express the second at all, so an omitted argument silently meant
    "everything required passed".
    """

    requirement_id: str
    checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        requirement = str(self.requirement_id).strip()
        if not requirement:
            raise InvalidScientificProblem("numerical requirement needs an id")
        object.__setattr__(self, "requirement_id", requirement)
        object.__setattr__(
            self,
            "checks",
            tuple(sorted({NumericalCheck(item).value for item in self.checks})),
        )

    @property
    def required_checks(self) -> tuple[NumericalCheck, ...]:
        return tuple(NumericalCheck(item) for item in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {"requirement_id": self.requirement_id, "checks": list(self.checks)}


@dataclass(frozen=True)
class NumericalCompleteness:
    """What was required, what ran, and what did not. Never a bare boolean."""

    requirement_id: str
    required: tuple[str, ...]
    performed: tuple[str, ...]
    #: Ran and came out satisfied. The only state that covers a requirement.
    satisfied: tuple[str, ...]
    violated: tuple[str, ...]
    #: Ran and decided nothing. Kept separate from both success and failure,
    #: because it is neither and collapsing it into either loses the finding.
    inconclusive: tuple[str, ...]
    not_performed: tuple[str, ...]
    enforceable: bool

    def __post_init__(self) -> None:
        for label in (
            "required",
            "performed",
            "satisfied",
            "violated",
            "inconclusive",
            "not_performed",
        ):
            object.__setattr__(
                self, label, tuple(sorted(str(i) for i in getattr(self, label)))
            )
        if not isinstance(self.enforceable, bool):
            raise InvalidScientificProblem("enforceable must be a boolean")

    @property
    def missing(self) -> tuple[str, ...]:
        """Required checks that were not performed at all."""
        return tuple(sorted(set(self.required) - set(self.performed)))

    @property
    def unresolved(self) -> tuple[str, ...]:
        """Required checks that ran and settled nothing."""
        return tuple(sorted(set(self.required) & set(self.inconclusive)))

    @property
    def failed(self) -> tuple[str, ...]:
        """Required checks that ran and came out violated."""
        return tuple(sorted(set(self.required) & set(self.violated)))

    @property
    def complete(self) -> bool:
        """Every required check explicitly SATISFIED.

        Deliberately not "performed and not violated". A required check that
        ran inconclusively has not been covered -- the question it exists to
        answer is still open -- so it shows up in :attr:`unresolved` and this
        stays False.
        """
        return self.enforceable and set(self.required) <= set(self.satisfied)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "required": list(self.required),
            "performed": list(self.performed),
            "satisfied": list(self.satisfied),
            "violated": list(self.violated),
            "inconclusive": list(self.inconclusive),
            "not_performed": list(self.not_performed),
            "missing": list(self.missing),
            "unresolved": list(self.unresolved),
            "failed": list(self.failed),
            "enforceable": self.enforceable,
            "complete": self.complete,
        }


def assess_numerical_completeness(
    requirement: NumericalRequirement | None,
    evidence: NumericalEvidence | None,
) -> NumericalCompleteness:
    """Compare an authority's stated numerical requirement against the roster.

    An unstated requirement is ``enforceable=False`` and can never be complete.
    A stated-but-empty requirement is enforceable and is satisfied by an
    evidence roster that violates nothing -- the same reading protocol
    completeness uses for an empty required protocol set.
    """
    observed = dict(
        performed=() if evidence is None else evidence.performed_checks,
        satisfied=() if evidence is None else evidence.satisfied_checks,
        violated=() if evidence is None else evidence.violated_checks,
        inconclusive=() if evidence is None else evidence.inconclusive_checks,
        not_performed=() if evidence is None else evidence.absent_checks,
    )
    if requirement is None:
        return NumericalCompleteness(
            requirement_id="(undeclared)", required=(), enforceable=False, **observed
        )
    return NumericalCompleteness(
        requirement_id=requirement.requirement_id,
        required=requirement.checks,
        enforceable=True,
        **observed,
    )
