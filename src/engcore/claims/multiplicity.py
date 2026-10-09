"""Multiplicity accounting: a promoted result always carries how many attempts it was selected from.

"The best of 1,000,000" is not "one hypothesis tested once".  A :class:`MultiplicityLedger` counts, per campaign, every
stage a search passes candidates through -- generated, de-duplicated, admitted, rejected by hard constraints, evaluated
at each fidelity, promoted, eliminated -- plus hypotheses tested, escrow queries, adaptive decisions, compute spent,
the random seeds and the search-strategy versions.  :meth:`MultiplicityLedger.context` freezes a snapshot whose digest a
:class:`PromotedResult` must bind; a promoted result cannot be constructed without one.

The ledger also states the FAMILY over which any test-level error rate must be read (``family_size`` = hypotheses
tested), so a downstream report can apply a multiplicity correction instead of quoting a per-test rate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

MULTIPLICITY_SCHEMA = "engcore.claims.multiplicity_context/1"

COUNTERS = ("generated", "deduplicated", "admitted", "rejected_hard", "promoted", "eliminated", "hypotheses_tested",
            "escrow_queries", "adaptive_decisions")


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class MultiplicityRefused(ValueError):
    """A result presented without (or against) the multiplicity of the search that produced it."""


class MultiplicityLedger:
    def __init__(self, campaign_id: str) -> None:
        if not str(campaign_id).strip():
            raise MultiplicityRefused("a multiplicity ledger belongs to a campaign")
        self.campaign_id = campaign_id
        self._counts = {k: 0 for k in COUNTERS}
        self._per_fidelity: dict[str, int] = {}
        self._compute: dict[str, float] = {}
        self._seeds: set[str] = set()
        self._strategies: set[str] = set()

    def count(self, counter: str, n: int = 1) -> None:
        if counter not in self._counts:
            raise MultiplicityRefused(f"unknown counter {counter!r}; known: {COUNTERS}")
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise MultiplicityRefused("counts only grow by a non-negative integer")
        self._counts[counter] += n

    def evaluated(self, rung_id: str, n: int = 1) -> None:
        if not str(rung_id).strip() or isinstance(n, bool) or n < 0:
            raise MultiplicityRefused("evaluations are counted per named rung, by a non-negative integer")
        self._per_fidelity[rung_id] = self._per_fidelity.get(rung_id, 0) + n

    def compute(self, unit: str, amount: float) -> None:
        if not str(unit).strip() or not amount >= 0:
            raise MultiplicityRefused("compute is a non-negative amount in a named unit")
        self._compute[unit] = self._compute.get(unit, 0.0) + float(amount)

    def seed(self, seed: str) -> None:
        self._seeds.add(str(seed))

    def strategy(self, strategy_id: str, version: str) -> None:
        self._strategies.add(f"{strategy_id}@{version}")

    def context(self) -> "MultiplicityContext":
        if self._counts["promoted"] > self._counts["admitted"] and self._counts["admitted"]:
            raise MultiplicityRefused("more candidates promoted than admitted: the ledger missed a stage")
        return MultiplicityContext(self.campaign_id, dict(self._counts), dict(sorted(self._per_fidelity.items())),
                                   dict(sorted(self._compute.items())), tuple(sorted(self._seeds)), tuple(sorted(self._strategies)))


@dataclass(frozen=True)
class MultiplicityContext:
    campaign_id: str
    counts: Mapping[str, int] = field(hash=False)
    evaluated_per_fidelity: Mapping[str, int] = field(hash=False)
    compute: Mapping[str, float] = field(hash=False)
    seeds: tuple[str, ...]
    strategy_versions: tuple[str, ...]

    @property
    def family_size(self) -> int:
        """The number of hypotheses tested: the family over which an error rate must be read."""
        return max(1, int(self.counts.get("hypotheses_tested", 0)))

    @property
    def selected_from(self) -> int:
        """How many candidates the promoted results were selected from (generated, before de-duplication)."""
        return int(self.counts.get("generated", 0))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MULTIPLICITY_SCHEMA, "campaign_id": self.campaign_id, "counts": dict(self.counts),
                "evaluated_per_fidelity": dict(self.evaluated_per_fidelity), "compute": dict(self.compute),
                "seeds": list(self.seeds), "strategy_versions": list(self.strategy_versions), "family_size": self.family_size,
                "selected_from": self.selected_from}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def statement(self) -> str:
        return (f"selected from {self.selected_from} generated candidates ({self.counts.get('deduplicated', 0)} de-duplicated, "
                f"{self.counts.get('admitted', 0)} admitted, {self.counts.get('promoted', 0)} promoted); "
                f"{self.family_size} hypotheses tested; {self.counts.get('escrow_queries', 0)} escrow queries")


@dataclass(frozen=True)
class PromotedResult:
    """A result promoted out of a search.  It cannot exist without the multiplicity context it was selected under."""

    result_id: str
    hypothesis_id: str
    multiplicity: MultiplicityContext
    multiplicity_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.multiplicity, MultiplicityContext):
            raise MultiplicityRefused("a promoted result binds its MultiplicityContext")
        if self.multiplicity.digest != self.multiplicity_digest:
            raise MultiplicityRefused("the multiplicity digest does not match the context it claims")
        if self.multiplicity.counts.get("promoted", 0) < 1:
            raise MultiplicityRefused("the bound context records no promotion; this result was not promoted under it")

    def to_dict(self) -> dict[str, Any]:
        return {"result_id": self.result_id, "hypothesis_id": self.hypothesis_id, "multiplicity": self.multiplicity.to_dict(),
                "multiplicity_digest": self.multiplicity_digest, "multiplicity_statement": self.multiplicity.statement()}


def promote(result_id: str, hypothesis_id: str, ledger: MultiplicityLedger) -> PromotedResult:
    ctx = ledger.context()
    return PromotedResult(result_id, hypothesis_id, ctx, ctx.digest)


__all__ = ["COUNTERS", "MultiplicityContext", "MultiplicityLedger", "MultiplicityRefused", "PromotedResult", "promote"]
