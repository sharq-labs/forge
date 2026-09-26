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

* REACHED needs at least one evidence link, and a link carries a classification that must fit the level
  (level 5 accepts only ``solver_corroboration...``; level 6 a numerical-benchmark comparison whose
  applicability was ``within`` and whose outcome was ``met``; level 7 an experimental one likewise);
* solver agreement can therefore reach level 5 and never 6 or 7;
* a not-met comparison is recorded as ATTEMPTED_NOT_REACHED, with its evidence, and stays visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

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


@dataclass(frozen=True)
class EvidenceLink:
    kind: str
    digest: str
    classification: str
    #: "met" | "not_met" | "not_applicable" | "n/a" (a link that is not a judged comparison)
    outcome: str = "n/a"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "digest": self.digest, "classification": self.classification, "outcome": self.outcome, "note": self.note}

    @classmethod
    def of_comparison(cls, comparison: ReferenceComparison, note: str = "") -> "EvidenceLink":
        return cls("reference_comparison", comparison.digest, comparison.classification, comparison.outcome, note)


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
        if self.level in (5, 6, 7) and self.status is LevelStatus.REACHED and link.outcome != "met":
            raise InvalidScientificProblem(f"level {self.level} is reached only by a comparison whose criterion was MET (got {link.outcome!r})")
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
        for e in by_level.values():
            entries[e.level] = e
        return cls(tuple(entries.values()))

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
    def validation_reached(self) -> str:
        """The strongest reference level actually reached: 'experimental', 'published_numerical_benchmark' or 'none'."""
        if self.entry(7).status is LevelStatus.REACHED:
            return "experimental"
        if self.entry(6).status is LevelStatus.REACHED:
            return "published_numerical_benchmark"
        return "none"

    def to_dict(self) -> dict[str, Any]:
        return {"verification_reached": self.verification_reached, "corroboration_reached": self.corroboration_reached,
                "validation_reached": self.validation_reached, "levels": [e.to_dict() for e in self.entries],
                "classification": "report_vocabulary_not_a_validation_grant"}
