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

AND THE RESULT IS BOUND TO WHAT IT REPLAYED
--------------------------------------------
A ``ReplayOutcome`` used to say ``REPLAYED_MATCH`` and carry a run id, and
certification checked that the id matched. That is a label, not evidence: a
record naming the right run satisfied the gate whether or not anything had
been executed, and an outcome with zero comparisons satisfied it too.

So the real replay function emits a :class:`ReplayEvidence` carrying the
digests of both authorized runs, the policy, the comparison and the pack
authorities, sealed together. Certification recomputes the expected identity
from the run it is actually certifying and the policy it was actually told
to require, so evidence produced for another run, under another policy, or
against other authority cannot be borrowed by this one.

This is BINDING, not authentication. A caller can construct any record it
likes and hashing does not change that -- the trust boundary is which code
calls certification, not which code can build a dataclass. What binding buys
is the failure actually being made here: evidence from one computation
silently satisfying another computation's gate.

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
REPLAY_EVIDENCE_SCHEMA = schema_string("forge_replay_evidence")


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


@dataclass(frozen=True)
class ReplayEvidence:
    """What was replayed, against what, under which policy -- sealed together.

    The seal is a digest over every identity field. It does not prove who
    produced the record; it proves the record's fields are the ones the seal
    was computed from, and it lets certification demand a seal recomputed from
    the run it is actually certifying. Evidence built for another run, another
    policy or other pack authority will not match.
    """

    original_run_digest: str
    replayed_run_digest: str
    original_run_id: str
    replay_run_id: str
    graph_fingerprint: str
    plan_fingerprint: str
    scenario_digest: str
    composition_authority_digest: str
    execution_authority_digest: str
    policy_digest: str
    comparison_digest: str
    compared: int
    seal: str = ""

    def __post_init__(self) -> None:
        for label in ("original_run_id", "replay_run_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"replay evidence requires {label}")
            object.__setattr__(self, label, value)
        for label in (
            "original_run_digest",
            "replayed_run_digest",
            "graph_fingerprint",
            "plan_fingerprint",
            "composition_authority_digest",
            "execution_authority_digest",
            "policy_digest",
            "comparison_digest",
        ):
            digest = str(getattr(self, label)).strip().lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise InvalidScientificProblem(
                    f"replay evidence {label} must be a sha256 hex digest"
                )
            object.__setattr__(self, label, digest)
        scenario = str(self.scenario_digest).strip().lower()
        if scenario and (
            len(scenario) != 64 or any(ch not in "0123456789abcdef" for ch in scenario)
        ):
            raise InvalidScientificProblem(
                "replay evidence scenario_digest must be sha256 hex or empty"
            )
        object.__setattr__(self, "scenario_digest", scenario)
        if isinstance(self.compared, bool) or int(self.compared) != self.compared:
            raise InvalidScientificProblem("replay evidence compared must be an integer")
        if int(self.compared) < 0:
            raise InvalidScientificProblem(
                "replay evidence compared must be non-negative"
            )
        object.__setattr__(self, "compared", int(self.compared))
        if self.original_run_digest == self.replayed_run_digest:
            raise InvalidScientificProblem(
                "the replayed run carries the same digest as the original; a "
                "record identical to what it claims to reproduce was not "
                "re-executed"
            )
        object.__setattr__(self, "seal", self.expected_seal)

    def _identity(self) -> dict[str, Any]:
        return {
            "original_run_digest": self.original_run_digest,
            "replayed_run_digest": self.replayed_run_digest,
            "original_run_id": self.original_run_id,
            "replay_run_id": self.replay_run_id,
            "graph_fingerprint": self.graph_fingerprint,
            "plan_fingerprint": self.plan_fingerprint,
            "scenario_digest": self.scenario_digest,
            "composition_authority_digest": self.composition_authority_digest,
            "execution_authority_digest": self.execution_authority_digest,
            "policy_digest": self.policy_digest,
            "comparison_digest": self.comparison_digest,
            "compared": self.compared,
        }

    @property
    def expected_seal(self) -> str:
        """The seal these fields imply. Recomputed on construction and on check."""
        return evidence_digest(self._identity())

    def mismatches(
        self,
        authorized: "AuthorizedMultiphysicsRun",
        policy: "ReplayPolicy",
        *,
        require_comparisons: bool = True,
    ) -> tuple[str, ...]:
        """Why this evidence is not about that run under that policy."""
        problems: list[str] = []
        if self.seal != self.expected_seal:
            problems.append("the replay seal does not match its own fields")
        expected = {
            "original_run_digest": authorized.digest,
            "original_run_id": authorized.run.run_id,
            "graph_fingerprint": authorized.run.graph_fingerprint,
            "plan_fingerprint": authorized.run.plan_fingerprint,
            "scenario_digest": authorized.run.scenario_digest,
            "composition_authority_digest": (
                authorized.composition_snapshot.authority_digest
            ),
            "execution_authority_digest": (
                authorized.execution_snapshot.authority_digest
            ),
            "policy_digest": policy.digest,
        }
        for label, wanted in expected.items():
            found = getattr(self, label)
            if found != wanted:
                problems.append(
                    f"replay evidence {label} is {str(found)[:12] or '(none)'}... "
                    f"but this computation's is {str(wanted)[:12] or '(none)'}..."
                )
        if require_comparisons and self.compared <= 0:
            problems.append(
                "the replay compared no quantities at all; a match over nothing "
                "is not a reproduction"
            )
        return tuple(problems)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REPLAY_EVIDENCE_SCHEMA, "seal": self.seal, **self._identity()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReplayEvidence":
        require_schema(payload, REPLAY_EVIDENCE_SCHEMA)
        made = cls(
            payload["original_run_digest"],
            payload["replayed_run_digest"],
            payload["original_run_id"],
            payload["replay_run_id"],
            payload["graph_fingerprint"],
            payload["plan_fingerprint"],
            payload.get("scenario_digest", ""),
            payload["composition_authority_digest"],
            payload["execution_authority_digest"],
            payload["policy_digest"],
            payload["comparison_digest"],
            payload["compared"],
        )
        if payload.get("seal") != made.seal:
            raise InvalidScientificProblem(
                "serialized replay evidence carries a seal its own fields do not "
                "produce"
            )
        return made


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
    #: Present exactly when a real re-execution happened. Certification reads
    #: THIS, not the status field: a status is a label anyone can write, while
    #: the evidence is bound to the run, the policy and the authority it came
    #: from. An outcome without it cannot satisfy the replay gate.
    evidence: ReplayEvidence | None = None

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
        if self.evidence is not None and not isinstance(self.evidence, ReplayEvidence):
            raise InvalidScientificProblem(
                "replay evidence must be a ReplayEvidence record"
            )
        if self.status is not ReplayStatus.REFUSED_UNREPRODUCIBLE and self.evidence is None:
            raise InvalidScientificProblem(
                "a replay that ran must carry the evidence it produced; a status "
                "with nothing behind it is a label"
            )

    @property
    def verified(self) -> bool:
        """Re-executed and agreed. Says nothing about WHICH run -- see :meth:`certifies`."""
        return self.status is ReplayStatus.REPLAYED_MATCH and self.evidence is not None

    def certifies(
        self,
        authorized: AuthorizedMultiphysicsRun,
        policy: "ReplayPolicy",
        *,
        require_comparisons: bool = True,
    ) -> tuple[str, ...]:
        """Why this outcome cannot certify that run. Empty means it can.

        The question certification actually needs answered, and it is not
        "does the status say match". A verified replay of a DIFFERENT run is a
        perfectly good replay and still cannot speak for this one.
        """
        if self.status is not ReplayStatus.REPLAYED_MATCH:
            return (f"the replay status is {self.status.value}, not a match",)
        if self.evidence is None:
            return ("the replay outcome carries no sealed evidence",)
        return self.evidence.mismatches(
            authorized, policy, require_comparisons=require_comparisons
        )

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
            "evidence": None if self.evidence is None else self.evidence.to_dict(),
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
            (
                None
                if payload.get("evidence") is None
                else ReplayEvidence.from_dict(payload["evidence"])
            ),
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
    evidence = ReplayEvidence(
        original_run_digest=authorized.digest,
        replayed_run_digest=replayed.digest,
        original_run_id=authorized.run.run_id,
        replay_run_id=replay_run_id,
        graph_fingerprint=authorized.run.graph_fingerprint,
        plan_fingerprint=authorized.run.plan_fingerprint,
        scenario_digest=authorized.run.scenario_digest,
        composition_authority_digest=authorized.composition_snapshot.authority_digest,
        execution_authority_digest=authorized.execution_snapshot.authority_digest,
        policy_digest=policy.digest,
        comparison_digest=evidence_digest(
            {
                "compared": compared,
                "differences": [item.to_dict() for item in differences],
            }
        ),
        compared=compared,
    )
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
        evidence=evidence,
    )


__all__ = [
    "DEFAULT_REPLAY_POLICY",
    "REPLAY_DIFFERENCE_SCHEMA",
    "REPLAY_EVIDENCE_SCHEMA",
    "REPLAY_OUTCOME_SCHEMA",
    "REPLAY_POLICY_SCHEMA",
    "ReplayDifference",
    "ReplayEvidence",
    "ReplayOutcome",
    "ReplayPolicy",
    "ReplayStatus",
    "compare_runs",
    "replay_authorized_graph_plan",
]
