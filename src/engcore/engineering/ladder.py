"""The verification / validation pyramid a flagship reports against.

Seven ordered levels, each recorded as reached, attempted-and-not-reached, not attempted or not available.
This is a REPORT vocabulary: it records where evidence stops.  It grants no validation level (that authority
stays in ``engcore.scientific.oracles``) and it is not a trust verdict (that stays in the credibility layer).

    1 contract integrity            units, identities, refusals
    2 conservation / residual       balances and solver residuals computed from the run
    3 analytic / simple limit       an exact or closed-form case the implementation must reproduce
    4 discretisation convergence    mesh / time-step refinement with the observed order
    5 independent-provider          two independent providers on the same declared problem  (CORROBORATION)
    6 published numerical benchmark a numerical reference, inside its applicability envelope
    7 experimental validation       measured data, inside its applicability envelope

Guards that make a level unable to be claimed by accident:

* REACHED needs at least one evidence link, EVERY link must have outcome ``met``, none may be post hoc, and each link's
  classification must fit the level (1 contract integrity; 2 conservation residual; 3 an analytic-limit or
  reference-data-consistency comparison; 4 discretisation convergence; 5 ``solver_corroboration...``; 6 a numerical-benchmark
  comparison; 7 an experimental-data comparison);
* solver agreement can therefore reach level 5 and never 6 or 7;
* a not-met (or post-hoc) reading is recorded on an ATTEMPTED_NOT_REACHED level, with its evidence, and stays visible.

Every evidence link CARRIES the record it names (a comparison, a study, a conservation assessment, the preflight report) and its
digest is re-derived from that record, so a link cannot name something that is not in the summary and a bundle re-checks each one.  The
ladder still cannot prove that a record is authentic (a flagship that builds a false record can put it here); it refuses evidence of the
wrong kind, outcome or timing, and a reference comparison can only be issued by ``compare_to_reference``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from .reference import COMPARISON_CLASSIFICATIONS, OracleKind, ReferenceComparison

LEVELS = (
    (1, "contract_integrity"), (2, "conservation_residual"), (3, "analytic_limit"), (4, "discretisation_convergence"),
    (5, "independent_provider_corroboration"), (6, "published_numerical_benchmark"), (7, "experimental_validation"),
)
NAMES = dict(LEVELS)


class LevelStatus(str, Enum):
    REACHED = "reached"
    ATTEMPTED_NOT_REACHED = "attempted_not_reached"
    NOT_ATTEMPTED = "not_attempted"
    NOT_AVAILABLE = "not_available"


def _normalised(record: Any) -> dict[str, Any]:
    """The record as plain JSON data (tuples become lists, keys strings); non-finite numbers and non-JSON values are refused, so the
    digest computed here equals the digest of the record read back from a bundle."""
    if not isinstance(record, Mapping) or not record:
        raise InvalidScientificProblem("an evidence link carries the non-empty record it names")
    try:
        text = json.dumps(record, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidScientificProblem(f"an evidence record must be finite JSON data: {exc}") from exc
    return json.loads(text)


@dataclass(frozen=True)
class EvidenceLink:
    kind: str
    classification: str
    #: "met" | "not_met" | "not_applicable" | "n/a" (a link that is not a judged comparison)
    outcome: str
    #: the record this link names, as JSON data; ``digest`` is derived from it
    record: Mapping[str, Any]
    note: str = ""

    def __post_init__(self) -> None:
        for label in ("kind", "classification"):
            if not str(getattr(self, label)).strip():
                raise InvalidScientificProblem(f"an evidence link states its {label}")
        if self.outcome not in ("met", "not_met", "not_applicable", "n/a"):
            raise InvalidScientificProblem("an evidence outcome is met, not_met, not_applicable or n/a")
        object.__setattr__(self, "record", _normalised(self.record))
        rec = self.record
        if self.kind == "reference_comparison" and (rec.get("classification") != self.classification or rec.get("outcome") != self.outcome):
            raise InvalidScientificProblem("a reference-comparison link must state the classification and outcome of the comparison it carries")
        if self.kind == "provider_comparison" and (rec.get("classification") != self.classification
                                                   or self.outcome != ("met" if rec.get("within_tolerance") is True else "not_met")):
            raise InvalidScientificProblem("a provider-comparison link must state the classification and tolerance outcome of the comparison it carries")

    @property
    def digest(self) -> str:
        return canonical_digest(self.record)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "digest": self.digest, "classification": self.classification, "outcome": self.outcome, "note": self.note,
                "record": self.record}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceLink":
        link = cls(payload["kind"], payload["classification"], payload["outcome"], payload["record"], payload.get("note", ""))
        if payload.get("digest") != link.digest:
            raise InvalidScientificProblem(f"evidence link {payload.get('kind')!r} does not have the digest of the record it carries")
        return link

    @classmethod
    def of_record(cls, kind: str, record: Mapping[str, Any], classification: str, outcome: str, note: str = "") -> "EvidenceLink":
        return cls(kind, classification, outcome, record, note)

    @classmethod
    def of_comparison(cls, comparison: ReferenceComparison, note: str = "") -> "EvidenceLink":
        return cls("reference_comparison", comparison.classification, comparison.outcome, comparison.to_dict(), note)

    @classmethod
    def of_provider_comparison(cls, comparison: Any, note: str = "") -> "EvidenceLink":
        """From a ``ProviderComparison`` (its own classification and tolerance outcome; its own digest is kept inside the record)."""
        record = comparison.to_dict()
        for key in ("a_selection", "b_selection"):        # a selection can hold thousands of weights: it is bound here by its digest, the comparison's own digest covers it in full
            record[key] = canonical_digest(record[key])
        record["provider_comparison_digest"] = comparison.digest
        return cls("provider_comparison", comparison.classification, "met" if comparison.within_tolerance else "not_met", record, note)


#: the evidence classes each verification level accepts once REACHED (levels 5-7 are handled separately below)
_LEVEL_CLASSES = {
    1: {"contract_integrity"}, 2: {"conservation_residual"},
    3: {COMPARISON_CLASSIFICATIONS[OracleKind.ANALYTIC_REFERENCE], "reference_data_consistency_check_not_validation"},
    4: {"discretisation_convergence"},
}


@dataclass(frozen=True)
class LevelEntry:
    level: int
    status: LevelStatus
    evidence: tuple[EvidenceLink, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if self.level not in NAMES:
            raise InvalidScientificProblem("verification levels are 1..7")
        object.__setattr__(self, "status", LevelStatus(self.status))
        if self.status is LevelStatus.REACHED and not self.evidence:
            raise InvalidScientificProblem(f"level {self.level} ({NAMES[self.level]}) cannot be REACHED without evidence")
        for link in self.evidence:
            self._check_link(link)

    def _check_link(self, link: EvidenceLink) -> None:
        c = link.classification.removeprefix("post_hoc_")
        if self.status is LevelStatus.REACHED and link.outcome != "met":
            raise InvalidScientificProblem(f"level {self.level} is reached only by evidence whose criterion was MET (got {link.outcome!r})")
        if self.status is LevelStatus.REACHED and link.classification.startswith("post_hoc_"):
            raise InvalidScientificProblem(f"a post-hoc reading cannot reach level {self.level}; it may be recorded beside a level that is not reached")
        if self.status is LevelStatus.REACHED and self.level in _LEVEL_CLASSES and c not in _LEVEL_CLASSES[self.level]:
            raise InvalidScientificProblem(f"level {self.level} ({NAMES[self.level]}) does not accept evidence of class {link.classification!r}")
        if self.level == 5 and self.status is LevelStatus.REACHED:
            if not c.startswith("solver_corroboration"):
                raise InvalidScientificProblem("level 5 accepts solver corroboration evidence only")
            if link.classification.startswith("post_hoc_"):
                raise InvalidScientificProblem("a post-hoc-selected comparison cannot reach level 5 (it may be recorded as an observation)")
        if self.level == 6 and self.status is LevelStatus.REACHED and c != COMPARISON_CLASSIFICATIONS[OracleKind.BENCHMARK_DATASET]:
            raise InvalidScientificProblem("level 6 accepts a numerical-benchmark comparison only")
        if self.level == 7 and self.status is LevelStatus.REACHED and c != COMPARISON_CLASSIFICATIONS[OracleKind.EXPERIMENTAL_DATASET]:
            raise InvalidScientificProblem("level 7 accepts an experimental-data comparison only")
        if self.level in (6, 7) and self.status is LevelStatus.REACHED and link.classification.startswith("post_hoc_"):
            raise InvalidScientificProblem("a post-hoc comparison cannot reach a reference level")

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "name": NAMES[self.level], "status": self.status.value,
                "evidence": [e.to_dict() for e in self.evidence], "note": self.note}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LevelEntry":
        entry = cls(int(payload["level"]), LevelStatus(payload["status"]), tuple(EvidenceLink.from_dict(e) for e in payload["evidence"]), payload.get("note", ""))
        if payload.get("name") != NAMES[entry.level]:
            raise InvalidScientificProblem("a ladder level carries the name of another level")
        return entry


@dataclass(frozen=True)
class VerificationLadder:
    entries: tuple[LevelEntry, ...]

    def __post_init__(self) -> None:
        levels = [e.level for e in self.entries]
        if sorted(levels) != [1, 2, 3, 4, 5, 6, 7]:
            raise InvalidScientificProblem("a ladder states every one of the seven levels exactly once")
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda e: e.level)))

    @classmethod
    def of(cls, **by_level: LevelEntry) -> "VerificationLadder":
        entries = {i: LevelEntry(i, LevelStatus.NOT_ATTEMPTED) for i, _ in LEVELS}
        seen: set[int] = set()
        for e in by_level.values():
            if e.level in seen:
                raise InvalidScientificProblem(f"level {e.level} is stated twice; a later entry must not silently replace an earlier one")
            seen.add(e.level)
            entries[e.level] = e
        return cls(tuple(entries.values()))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerificationLadder":
        """Rebuild (and so re-validate every guard of) a ladder read from a summary; the derived fields must agree with the levels."""
        ladder = cls(tuple(LevelEntry.from_dict(e) for e in payload["levels"]))
        for key, derived in (("verification_reached", ladder.verification_reached), ("corroboration_reached", ladder.corroboration_reached),
                             ("reference_level_reached", ladder.reference_level_reached)):
            if payload.get(key) != derived:
                raise InvalidScientificProblem(f"the ladder states {key} = {payload.get(key)!r} but its levels give {derived!r}")
        return ladder

    def entry(self, level: int) -> LevelEntry:
        return next(e for e in self.entries if e.level == level)

    @property
    def verification_reached(self) -> int:
        """Highest level 1..N such that levels 1..N are ALL reached (verification proper: 1..4)."""
        n = 0
        for e in self.entries:
            if e.level <= 4 and e.status is LevelStatus.REACHED:
                n = e.level
            else:
                break
        return n

    @property
    def corroboration_reached(self) -> bool:
        return self.entry(5).status is LevelStatus.REACHED

    @property
    def reference_level_reached(self) -> str:
        """The strongest REFERENCE level reached: 'experimental_data', 'published_numerical_benchmark' or 'none'.

        Deliberately not called validation: a numerical-benchmark comparison is not experimental validation, and no comparison here
        grants a validation level (that authority stays in ``engcore.scientific.oracles``)."""
        if self.entry(7).status is LevelStatus.REACHED:
            return "experimental_data"
        if self.entry(6).status is LevelStatus.REACHED:
            return "published_numerical_benchmark"
        return "none"

    def to_dict(self) -> dict[str, Any]:
        return {"verification_reached": self.verification_reached, "corroboration_reached": self.corroboration_reached,
                "reference_level_reached": self.reference_level_reached, "levels": [e.to_dict() for e in self.entries],
                "classification": "report_vocabulary_not_a_validation_grant"}


def contract_integrity_entry(report: Any, result: Any) -> LevelEntry:
    """Level 1 from the run's own preflight and status: reached only if neither the preflight nor the run was REFUSED.

    DEFERRED_CHECKS is not a refusal, but the deferred checks are named: they were decided on the solved state, not in advance."""
    refused = report.status.value == "refused" or result.status.value == "refused"
    deferred = sorted({f"{d.node_id}:{d.check_id}" for d in report.deferred_checks})
    link = EvidenceLink.of_record("preflight_and_identity", report.to_dict(), "contract_integrity", "not_met" if refused else "met",
                                  f"preflight {report.status.value}; run {result.status.value}")
    solved_state_refusals = sorted(r.node_id for r in result.node_receipts if r.status.value == "refused")
    note = ("units, material-record digests, provider bindings and identities checked by BIG 12 preflight"
            + (f"; deferred to the solved state: {deferred}" if deferred else "")
            + (f"; REFUSED on the solved state: {solved_state_refusals} (the request was admissible; the solved state was not)" if solved_state_refusals else ""))
    if refused:
        return LevelEntry(1, LevelStatus.ATTEMPTED_NOT_REACHED, (link,), "the preflight or the run was REFUSED: " + note)
    return LevelEntry(1, LevelStatus.REACHED, (link,), note)
