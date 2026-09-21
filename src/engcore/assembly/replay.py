"""Computational replay: run it again and compare, rather than read it again.

WHAT WAS CALLED REPLAY BEFORE
------------------------------
The certification gate named ``replay_roundtrip_verified`` did this::

    replayed = AuthorizedMultiphysicsRun.from_dict(authorized.to_dict())
    replay_ok = replayed.digest == authorized.digest

That is a serialization roundtrip. It proves the record can be written down and
read back unchanged, which is worth proving and is not replay. It re-executes
nothing: a solver that has since changed its answer, a pack whose authority has
moved, an input that no longer resolves -- all of them pass that check, because
none of them is consulted.

So the two are separated and both are kept. :func:`replay_authorized_graph_plan`
rebuilds the participants from live registered authority, executes the same
GraphPlan again, and compares the numbers that came back against the numbers
the original run recorded. The serialization roundtrip remains its own gate
under its own name.

FAIL CLOSED ON UNREPRODUCIBLE, NOT "PROBABLY FINE"
---------------------------------------------------
Replay refuses rather than degrades. If the Composition or Execution Pack
authority digest has moved since the run, if the factory registry no longer
covers the graph, or if the scenario cannot be reconstructed, the outcome is
``REFUSED_UNREPRODUCIBLE`` with the reason -- never a pass with a caveat. The
authority checks that produce that refusal are the ones
``execute_authorized_graph_plan`` already performs; this module lets them fail
and records why.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..compositionpacks.registry import CompositionPackRegistry
from ..data.resolver import BulkDataResolver
from ..data.store import BulkDataStore
from ..executionpacks.registry import ExecutionPackRegistry
from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics import MultiphysicsRunRecord
from ..scientific.replay_core.comparison import compare_numeric
from ..scientific.replay_core.tolerance import ReplayTolerance
from ..scientific.serialization import require_schema, schema_string
from ..scientific.twins import ScientificTwin
from .multiphysics import AuthorizedMultiphysicsRun, execute_authorized_graph_plan
from .trust import evidence_digest

REPLAY_POLICY_SCHEMA = schema_string("forge_replay_policy")
REPLAY_OUTCOME_SCHEMA = schema_string("forge_replay_outcome")
REPLAY_DIFFERENCE_SCHEMA = schema_string("forge_replay_difference")


class ReplayStatus(str, Enum):
    #: Re-executed, and every compared quantity agreed within the policy.
    REPLAYED_MATCH = "replayed_match"
    #: Re-executed, and something disagreed. The differences are enumerated.
    REPLAYED_MISMATCH = "replayed_mismatch"
    #: Could not be re-executed at all. Never a pass.
    REFUSED_UNREPRODUCIBLE = "refused_unreproducible"


@dataclass(frozen=True)
class ReplayPolicy:
    """What "the same answer" means, stated before the comparison is made.

    Identity fields -- the scenario digest, the graph and plan fingerprints,
    the window count -- are compared exactly and are not subject to the
    numeric tolerance. A replay that produced the right numbers over a
    different scenario is not a replay.
    """

    policy_id: str
    version: str
    tolerance: ReplayTolerance
    compare_scenario_evidence: bool = True

    def __post_init__(self) -> None:
        for label in ("policy_id", "version"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"replay policy requires {label}")
            object.__setattr__(self, label, value)
        if not isinstance(self.tolerance, ReplayTolerance):
            raise InvalidScientificProblem("replay policy requires a ReplayTolerance")
        if not isinstance(self.compare_scenario_evidence, bool):
            raise InvalidScientificProblem(
                "compare_scenario_evidence must be a boolean"
            )

    @property
    def digest(self) -> str:
        return evidence_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPLAY_POLICY_SCHEMA,
            "policy_id": self.policy_id,
            "version": self.version,
            "absolute_tolerance": self.tolerance.absolute,
            "relative_tolerance": self.tolerance.relative,
            "compare_scenario_evidence": self.compare_scenario_evidence,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReplayPolicy":
        require_schema(payload, REPLAY_POLICY_SCHEMA)
        return cls(
            payload["policy_id"],
            payload["version"],
            ReplayTolerance(
                payload.get("absolute_tolerance", 0.0),
                payload.get("relative_tolerance", 0.0),
            ),
            payload.get("compare_scenario_evidence", True),
        )


#: The default policy: bit-identical is not required, but a run whose outputs
#: move by more than a part in 10^9 is not the same computation.
DEFAULT_REPLAY_POLICY = ReplayPolicy(
    "forge.multiphysics.replay",
    "1",
    ReplayTolerance(absolute=0.0, relative=1e-9),
)


@dataclass(frozen=True, order=True)
class ReplayDifference:
    """One quantity that did not come back the same."""

    key: str
    expected: str
    actual: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPLAY_DIFFERENCE_SCHEMA,
            "key": self.key,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReplayDifference":
        require_schema(payload, REPLAY_DIFFERENCE_SCHEMA)
        return cls(
            payload["key"], payload["expected"], payload["actual"], payload.get("detail", "")
        )


@dataclass(frozen=True)
class ReplayOutcome:
    """What happened when the computation was run a second time."""

    status: ReplayStatus
    policy_id: str
    policy_version: str
    original_run_id: str
    replay_run_id: str
    compared: int = 0
    differences: tuple[ReplayDifference, ...] = ()
    refusal_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ReplayStatus(self.status))
        differences = tuple(sorted(self.differences))
        if any(not isinstance(item, ReplayDifference) for item in differences):
            raise InvalidScientificProblem("replay differences must be ReplayDifference")
        object.__setattr__(self, "differences", differences)
        if self.status is ReplayStatus.REPLAYED_MISMATCH and not differences:
            raise InvalidScientificProblem(
                "a replay mismatch must enumerate what differed"
            )
        if self.status is ReplayStatus.REFUSED_UNREPRODUCIBLE and not str(
            self.refusal_reason
        ).strip():
            raise InvalidScientificProblem(
                "a refused replay must state why it could not be reproduced"
            )
        if self.status is ReplayStatus.REPLAYED_MATCH and differences:
            raise InvalidScientificProblem(
                "a matching replay cannot also carry differences"
            )
        object.__setattr__(self, "refusal_reason", str(self.refusal_reason).strip())

    @property
    def verified(self) -> bool:
        """True only for an actual re-execution that agreed."""
        return self.status is ReplayStatus.REPLAYED_MATCH

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPLAY_OUTCOME_SCHEMA,
            "status": self.status.value,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "original_run_id": self.original_run_id,
            "replay_run_id": self.replay_run_id,
            "compared": self.compared,
            "differences": [item.to_dict() for item in self.differences],
            "refusal_reason": self.refusal_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReplayOutcome":
        require_schema(payload, REPLAY_OUTCOME_SCHEMA)
        return cls(
            ReplayStatus(payload["status"]),
            payload["policy_id"],
            payload["policy_version"],
            payload["original_run_id"],
            payload["replay_run_id"],
            payload.get("compared", 0),
            tuple(ReplayDifference.from_dict(i) for i in payload.get("differences", ())),
            payload.get("refusal_reason", ""),
        )


def _scalar_outputs(record: MultiphysicsRunRecord) -> dict[str, float]:
    """The scalar final outputs, keyed by ``participant.port``.

    Underscore-prefixed keys are the run's own diagnostic blocks rather than
    produced quantities, and field-valued outputs carry no single magnitude, so
    neither takes part in the numeric comparison. Both are still covered by the
    identity comparisons below.
    """
    found: dict[str, float] = {}
    for key, value in record.final_outputs.items():
        if key.startswith("_") or not isinstance(value, Mapping):
            continue
        magnitude = value.get("magnitude")
        if isinstance(magnitude, (int, float)) and not isinstance(magnitude, bool):
            found[key] = float(magnitude)
    return found


def compare_runs(
    original: MultiphysicsRunRecord,
    replayed: MultiphysicsRunRecord,
    policy: ReplayPolicy,
) -> tuple[int, tuple[ReplayDifference, ...]]:
    """Compare two executions under an explicit policy. Identity first."""
    differences: list[ReplayDifference] = []

    for label, left, right in (
        ("graph_fingerprint", original.graph_fingerprint, replayed.graph_fingerprint),
        ("plan_fingerprint", original.plan_fingerprint, replayed.plan_fingerprint),
        ("scenario_digest", original.scenario_digest, replayed.scenario_digest),
        ("window_count", str(len(original.windows)), str(len(replayed.windows))),
        (
            "ended_at",
            f"{original.ended_at.magnitude_in('second'):.17g}",
            f"{replayed.ended_at.magnitude_in('second'):.17g}",
        ),
    ):
        if left != right:
            differences.append(
                ReplayDifference(label, str(left), str(right), "identity must match exactly")
            )

    if policy.compare_scenario_evidence:
        for label, left, right in (
            (
                "scenario_input_receipts",
                original.scenario_input_receipts,
                replayed.scenario_input_receipts,
            ),
            (
                "operating_condition_receipts",
                original.operating_condition_receipts,
                replayed.operating_condition_receipts,
            ),
            (
                "initial_state_receipts",
                original.initial_state_receipts,
                replayed.initial_state_receipts,
            ),
            (
                "reached_scheduled_events",
                original.reached_scheduled_events,
                replayed.reached_scheduled_events,
            ),
        ):
            if left != right:
                differences.append(
                    ReplayDifference(
                        label,
                        f"{len(left)} record(s)",
                        f"{len(right)} record(s)",
                        "scenario evidence must be reproduced exactly",
                    )
                )
        left_stop = None if original.termination is None else original.termination.condition_id
        right_stop = None if replayed.termination is None else replayed.termination.condition_id
        if left_stop != right_stop:
            differences.append(
                ReplayDifference(
                    "termination", str(left_stop), str(right_stop), "stop condition differs"
                )
            )

    expected = _scalar_outputs(original)
    actual = _scalar_outputs(replayed)
    for key in sorted(set(expected) | set(actual)):
        if key not in expected or key not in actual:
            differences.append(
                ReplayDifference(
                    f"final_outputs.{key}",
                    "present" if key in expected else "absent",
                    "present" if key in actual else "absent",
                    "the replay produced a different set of outputs",
                )
            )
            continue
        comparison = compare_numeric(expected[key], actual[key], policy.tolerance)
        if not comparison.matched:
            differences.append(
                ReplayDifference(
                    f"final_outputs.{key}",
                    f"{expected[key]:.17g}",
                    f"{actual[key]:.17g}",
                    f"error {comparison.absolute_error:.3g} exceeds "
                    f"{comparison.allowed_error:.3g}",
                )
            )
    return len(expected), tuple(differences)


def replay_authorized_graph_plan(
    authorized: AuthorizedMultiphysicsRun,
    *,
    replay_run_id: str,
    compositions: CompositionPackRegistry,
    executions: ExecutionPackRegistry,
    resolver: BulkDataResolver,
    store: BulkDataStore,
    policy: ReplayPolicy = DEFAULT_REPLAY_POLICY,
    external_uncertainty: Mapping[Any, Any] | None = None,
    topology_twins: Mapping[tuple[str, str], ScientificTwin] | None = None,
) -> ReplayOutcome:
    """Execute the recorded GraphPlan again and compare the results.

    The GraphPlan carries everything the second execution needs -- the graph,
    the coupling plan, the external inputs, the scenario with its initial state,
    schedules, operating conditions, stop conditions and quantity bindings, the
    topology, and the pinned pack authority. So replay is not a reconstruction
    from a report: it is the same authorized execution, run again, against
    authority that must still match the digests the plan was pinned to.
    """
    if not isinstance(authorized, AuthorizedMultiphysicsRun):
        raise TypeError("replay requires an AuthorizedMultiphysicsRun")
    if not isinstance(policy, ReplayPolicy):
        raise TypeError("replay requires a ReplayPolicy")

    try:
        replayed = execute_authorized_graph_plan(
            authorized.graph_plan,
            run_id=replay_run_id,
            compositions=compositions,
            executions=executions,
            resolver=resolver,
            store=store,
            external_uncertainty=external_uncertainty,
            topology_twins=topology_twins,
        )
    except Exception as exc:  # noqa: BLE001 -- the refusal is the result
        return ReplayOutcome(
            status=ReplayStatus.REFUSED_UNREPRODUCIBLE,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            original_run_id=authorized.run.run_id,
            replay_run_id=replay_run_id,
            refusal_reason=f"{type(exc).__name__}: {exc}",
        )

    compared, differences = compare_runs(authorized.run, replayed.run, policy)
    return ReplayOutcome(
        status=(
            ReplayStatus.REPLAYED_MATCH
            if not differences
            else ReplayStatus.REPLAYED_MISMATCH
        ),
        policy_id=policy.policy_id,
        policy_version=policy.version,
        original_run_id=authorized.run.run_id,
        replay_run_id=replay_run_id,
        compared=compared,
        differences=differences,
    )


__all__ = [
    "DEFAULT_REPLAY_POLICY",
    "REPLAY_DIFFERENCE_SCHEMA",
    "REPLAY_OUTCOME_SCHEMA",
    "REPLAY_POLICY_SCHEMA",
    "ReplayDifference",
    "ReplayOutcome",
    "ReplayPolicy",
    "ReplayStatus",
    "compare_runs",
    "replay_authorized_graph_plan",
]
