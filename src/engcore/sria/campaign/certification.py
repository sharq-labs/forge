"""V0.1 — the smallest campaign-scoped certification requirement.

E3 established one production failure precisely: a campaign can refuse
scientific STOP while a declared adequacy obligation is outstanding, but it
cannot route itself to the finite evidence that would resolve the refusal. The
refusal is real — the Arbiter-owned stopping review returns a non-approving
outcome — and then the loop pauses, because selection has no branch for "the
economics say stop, but a declared requirement says not yet".

This module is the missing declaration, and nothing more.

WHY NOT ``ObligationSet``
-------------------------
:class:`~engcore.sria.assurance.obligations.ObligationSet` is evaluated by the
Arbiter against the critic assessments of ONE evidence record. A campaign-scoped
requirement placed there is looked for among that record's checks, never found,
and makes every piece of evidence INCONCLUSIVE — blocking all admission. That
is not a hypothesis: E3 ran it and recorded ``admitted=False``, ``belief_size=0``.
So the requirement needs its own home, and this is the smallest one that can
express what E3 demonstrated.

WHY STATUS IS DERIVED, NOT STORED
---------------------------------
A requirement carries no mutable status field. Status is computed from the
campaign's own hash-chained event log, which is the same idiom the runner
already uses to decide whether an iteration is in progress. Storing it would
create a second source of truth that a resume could silently contradict, and
the log already records everything the answer needs.

WHAT COUNTS AS SATISFYING EVIDENCE
----------------------------------
Two conditions, both necessary:

* the action's evidence was **admitted** — an execution that produced nothing
  belief-bearing has not discharged anything; and
* its selection carried a **prediction reference**, recorded in the
  ``ACTION_SELECTED`` event, which the log orders strictly before
  ``EXECUTION_STARTED``.

The second is the minimum honest form of E2's commitment rule. A validation
action whose prediction was written after its observation tests nothing, and a
requirement discharged by such an action would certify a check that never
happened. This module does not compute predictions, does not store them, and
does not know what is inside one — it only refuses to count an action that
does not reference one.

WHAT ``prediction_ref`` IS NOT
------------------------------
It is a V0.1 *contract*, not a production predictive-commitment solution, and
the difference matters enough to state rather than imply. V0.1 checks exactly
one thing: that a non-empty reference was recorded in the tamper-evident log
before the action executed. It does **not** verify that the reference names a
real predictive distribution, that the distribution was computed from the
evidence snapshot the requirement is about, that it was sealed against later
edits, or that its content hash matches anything. Those checks exist — E2
built and tested them — and they remain experiment-side on purpose, because
promoting them would mean promoting a predictive-checking framework, which
this milestone explicitly does not do.

So the guarantee here is narrow and should be quoted narrowly: a required
action that referenced no prediction cannot discharge a requirement. A caller
that supplies a meaningless reference will satisfy this contract and will not
have tested anything, and V0.1 cannot tell the difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string

CERTIFICATION_REQUIREMENT_SCHEMA = schema_string("sria_certification_requirement")


class RequirementStatus(str, Enum):
    """Whether the declared certification evidence has been obtained.

    Note what is absent: there is no PASSED. Whether the evidence, once
    obtained, supports certification is a scientific judgement belonging to the
    stopping criterion and the Arbiter. This enum only reports whether the
    declared test was performed.
    """

    OUTSTANDING = "outstanding"
    SATISFIED = "satisfied"
    #: Declared, still outstanding, and no longer purchasable. Distinct from
    #: OUTSTANDING on purpose: "not yet bought" and "can never be bought" call
    #: for different responses, and neither is a finding about the model.
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class CertificationRequirement:
    """A finite, declared set of actions that must run before certification.

    Deliberately not a rule, a query, a predicate or a plan — a list of action
    ids the campaign declared in advance. E3 demonstrated exactly this much and
    no more, so this expresses exactly this much and no more.
    """

    requirement_id: str
    required_action_ids: tuple[str, ...]
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "required_action_ids", tuple(self.required_action_ids)
        )
        for label in ("requirement_id", "source"):
            if not str(getattr(self, label)).strip():
                raise ValueError(
                    f"a certification requirement needs {label}; an "
                    f"unattributed requirement cannot be reviewed"
                )
        if not self.required_action_ids:
            raise ValueError(
                "a certification requirement with no required actions would be "
                "satisfied by doing nothing; declare the evidence or declare "
                "no requirement"
            )
        duplicates = {
            a for a in self.required_action_ids
            if self.required_action_ids.count(a) > 1
        }
        if duplicates:
            raise ValueError(f"duplicate required actions: {sorted(duplicates)}")

    def outstanding(self, satisfied_action_ids: Iterable[str]) -> tuple[str, ...]:
        """Required actions not yet discharged, in declared order."""
        done = set(satisfied_action_ids)
        return tuple(a for a in self.required_action_ids if a not in done)

    def status(
        self,
        satisfied_action_ids: Iterable[str],
        *,
        reachable_action_ids: Iterable[str] | None = None,
    ) -> RequirementStatus:
        """SATISFIED, OUTSTANDING, or UNREACHABLE.

        ``reachable_action_ids`` is what the campaign could still buy — offered
        as a candidate and affordable from the pool its family may draw on. An
        outstanding requirement with nothing reachable is UNREACHABLE, which is
        a budget or availability fact and never a model-adequacy one.
        """
        remaining = self.outstanding(satisfied_action_ids)
        if not remaining:
            return RequirementStatus.SATISFIED
        if reachable_action_ids is None:
            return RequirementStatus.OUTSTANDING
        if set(remaining) & set(reachable_action_ids):
            return RequirementStatus.OUTSTANDING
        return RequirementStatus.UNREACHABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CERTIFICATION_REQUIREMENT_SCHEMA,
            "requirement_id": self.requirement_id,
            "required_action_ids": list(self.required_action_ids),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CertificationRequirement":
        require_schema(payload, CERTIFICATION_REQUIREMENT_SCHEMA)
        return cls(
            requirement_id=payload["requirement_id"],
            required_action_ids=tuple(payload.get("required_action_ids", ())),
            source=payload["source"],
        )
