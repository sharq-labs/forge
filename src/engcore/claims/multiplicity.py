"""Multiplicity accounting: a promoted result always carries how many attempts it was selected from.

"The best of 1,000,000" is not "one hypothesis tested once".  A :class:`MultiplicityLedger` (one per campaign) counts
every stage a search passes candidates through -- generated, de-duplicated (remaining after de-duplication), rejected by
hard constraints, admitted, evaluated at each fidelity, eliminated -- plus escrow queries, adaptive decisions, compute,
seeds and strategy versions.  Tested and promoted hypotheses are recorded BY ID (:meth:`MultiplicityLedger.tested`,
:func:`promote`), never as bare counts, and the stage chain must be consistent
(promoted <= admitted <= de-duplicated - rejected_hard <= generated; promoted <= tested) before any promotion.

A :class:`MultiplicityContext` is issued only by its ledger (it carries the ledger's seal) and is immutable; a
:class:`PromotedResult` must bind one that names its hypothesis as promoted.  A campaign id opens ONE ledger per
process, ever (it is not freed when the ledger is dropped), and :meth:`MultiplicityLedger.close` freezes the FINAL
context: :func:`verify_promoted` accepts a result only against it, so a promotion made early in a search cannot keep
quoting the small family it was promoted from.  Counts remain self-reported by the search; a separate campaign id is a
separate (declared) search.  ``family_size`` is the raw number of
hypotheses tested -- the family over which any test-level error rate must be read -- and a promotion out of an empty
family is refused.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

MULTIPLICITY_SCHEMA = "engcore.claims.multiplicity_context/2"

#: free counters (``count``).  ``hypotheses_tested`` and ``promoted`` are derived from recorded ids.
COUNTERS = ("generated", "deduplicated", "admitted", "rejected_hard", "eliminated", "escrow_queries", "adaptive_decisions")
_SEAL_KEY = os.urandom(32)
_OPENED: set[str] = set()                 # every campaign id that ever opened a ledger in this process


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _seal(digest: str) -> str:
    return hmac.new(_SEAL_KEY, digest.encode(), hashlib.sha256).hexdigest()


class MultiplicityRefused(ValueError):
    """A result presented without (or against) the multiplicity of the search that produced it."""


def _nonneg_int(n: Any) -> int:
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise MultiplicityRefused("counts grow by a non-negative integer")
    return n


class MultiplicityLedger:
    def __init__(self, campaign_id: str) -> None:
        if not str(campaign_id).strip():
            raise MultiplicityRefused("a multiplicity ledger belongs to a campaign")
        if campaign_id in _OPENED:
            raise MultiplicityRefused(f"campaign {campaign_id!r} already opened a ledger; a second one would restart its count")
        _OPENED.add(campaign_id)
        self._closed: "MultiplicityContext | None" = None
        self.campaign_id = campaign_id
        self._counts = {k: 0 for k in COUNTERS}
        self._per_fidelity: dict[str, int] = {}
        self._compute: dict[str, float] = {}
        self._seeds: set[str] = set()
        self._strategies: set[str] = set()
        self._tested: set[str] = set()
        self._promoted: set[str] = set()

    def _open(self) -> None:
        if self._closed is not None:
            raise MultiplicityRefused("the ledger is closed: its final context is fixed")

    def count(self, counter: str, n: int = 1) -> None:
        self._open()
        if counter not in self._counts:
            raise MultiplicityRefused(f"unknown counter {counter!r}; known: {COUNTERS} (tested/promoted are recorded by id)")
        self._counts[counter] += _nonneg_int(n)

    def tested(self, hypothesis_id: str) -> None:
        self._open()
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            raise MultiplicityRefused("a tested hypothesis has an id")
        self._tested.add(hypothesis_id)

    def evaluated(self, rung_id: str, n: int = 1) -> None:
        if not str(rung_id).strip():
            raise MultiplicityRefused("evaluations are counted per named rung")
        self._per_fidelity[rung_id] = self._per_fidelity.get(rung_id, 0) + _nonneg_int(n)

    def compute(self, unit: str, amount: float) -> None:
        if not str(unit).strip() or not (math.isfinite(float(amount)) and float(amount) >= 0):
            raise MultiplicityRefused("compute is a finite non-negative amount in a named unit")
        self._compute[unit] = self._compute.get(unit, 0.0) + float(amount)

    def seed(self, seed: str) -> None:
        if not str(seed).strip():
            raise MultiplicityRefused("a seed is named")
        self._seeds.add(str(seed))

    def strategy(self, strategy_id: str, version: str) -> None:
        if not (str(strategy_id).strip() and str(version).strip()):
            raise MultiplicityRefused("a strategy is named and versioned")
        self._strategies.add(f"{strategy_id}@{version}")

    def _check_chain(self) -> None:
        c = self._counts
        promoted = len(self._promoted)
        if not c["deduplicated"] <= c["generated"]:
            raise MultiplicityRefused("more de-duplicated candidates than generated: the ledger missed a stage")
        if not c["admitted"] + c["rejected_hard"] <= c["deduplicated"]:
            raise MultiplicityRefused("admitted + hard-rejected exceed the de-duplicated candidates: the ledger missed a stage")
        if not c["eliminated"] <= c["admitted"] or not promoted <= c["admitted"]:
            raise MultiplicityRefused("more candidates eliminated or promoted than admitted: the ledger missed a stage")
        if not self._promoted <= self._tested:
            raise MultiplicityRefused("a promoted hypothesis was never recorded as tested")

    def close(self) -> "MultiplicityContext":
        """Freeze the FINAL context; nothing more is counted.  Idempotent."""
        if self._closed is None:
            self._closed = self.context()
        return self._closed

    @property
    def final(self) -> "MultiplicityContext | None":
        return self._closed

    def _promote(self, hypothesis_id: str) -> None:
        self._open()
        if hypothesis_id not in self._tested:
            raise MultiplicityRefused("only a hypothesis recorded as tested can be promoted")
        if self._counts["generated"] < 1 or self._counts["admitted"] < len(self._promoted | {hypothesis_id}):
            raise MultiplicityRefused("a promotion needs generated and admitted candidates to have been counted")
        self._promoted.add(hypothesis_id)
        try:
            self._check_chain()
        except MultiplicityRefused:
            self._promoted.discard(hypothesis_id)
            raise

    def context(self) -> "MultiplicityContext":
        if self._closed is not None:
            return self._closed
        self._check_chain()
        counts = {**self._counts, "hypotheses_tested": len(self._tested), "promoted": len(self._promoted)}
        payload = dict(campaign_id=self.campaign_id, counts=counts, evaluated_per_fidelity=dict(sorted(self._per_fidelity.items())),
                       compute=dict(sorted(self._compute.items())), seeds=tuple(sorted(self._seeds)),
                       strategy_versions=tuple(sorted(self._strategies)), tested_ids=tuple(sorted(self._tested)),
                       promoted_ids=tuple(sorted(self._promoted)))
        digest = _digest(_context_dict(**payload))
        return MultiplicityContext(**payload, ledger_seal=_seal(digest))


def _context_dict(*, campaign_id, counts, evaluated_per_fidelity, compute, seeds, strategy_versions, tested_ids, promoted_ids) -> dict:
    return {"schema": MULTIPLICITY_SCHEMA, "campaign_id": campaign_id, "counts": dict(counts),
            "evaluated_per_fidelity": dict(evaluated_per_fidelity), "compute": dict(compute), "seeds": list(seeds),
            "strategy_versions": list(strategy_versions), "tested_ids": list(tested_ids), "promoted_ids": list(promoted_ids),
            "family_size": int(counts.get("hypotheses_tested", 0)), "selected_from": int(counts.get("generated", 0))}


@dataclass(frozen=True)
class MultiplicityContext:
    campaign_id: str
    counts: Mapping[str, int] = field(hash=False)
    evaluated_per_fidelity: Mapping[str, int] = field(hash=False)
    compute: Mapping[str, float] = field(hash=False)
    seeds: tuple[str, ...]
    strategy_versions: tuple[str, ...]
    tested_ids: tuple[str, ...]
    promoted_ids: tuple[str, ...]
    ledger_seal: str

    def __post_init__(self) -> None:
        for name in ("counts", "evaluated_per_fidelity", "compute"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        if not hmac.compare_digest(self.ledger_seal, _seal(self.digest)):
            raise MultiplicityRefused("a multiplicity context is issued by its campaign's ledger; this one was not")

    @property
    def family_size(self) -> int:
        """The number of hypotheses tested: the family over which an error rate must be read (0 if none were)."""
        return int(self.counts.get("hypotheses_tested", 0))

    @property
    def selected_from(self) -> int:
        """How many candidates the promoted results were selected from (generated, before de-duplication)."""
        return int(self.counts.get("generated", 0))

    def to_dict(self) -> dict[str, Any]:
        return _context_dict(campaign_id=self.campaign_id, counts=self.counts, evaluated_per_fidelity=self.evaluated_per_fidelity,
                             compute=self.compute, seeds=self.seeds, strategy_versions=self.strategy_versions,
                             tested_ids=self.tested_ids, promoted_ids=self.promoted_ids)

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def statement(self) -> str:
        return (f"selected from {self.selected_from} generated candidates ({self.counts.get('deduplicated', 0)} after "
                f"de-duplication, {self.counts.get('admitted', 0)} admitted, {self.counts.get('promoted', 0)} promoted); "
                f"{self.family_size} hypotheses tested; {self.counts.get('escrow_queries', 0)} escrow queries")


@dataclass(frozen=True)
class PromotedResult:
    """A result promoted out of a search.  It cannot exist without the ledger-issued context that names it promoted."""

    result_id: str
    hypothesis_id: str
    multiplicity: MultiplicityContext
    multiplicity_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.multiplicity, MultiplicityContext):
            raise MultiplicityRefused("a promoted result binds its MultiplicityContext")
        if self.multiplicity.digest != self.multiplicity_digest:
            raise MultiplicityRefused("the multiplicity digest does not match the context it claims")
        if self.hypothesis_id not in self.multiplicity.promoted_ids:
            raise MultiplicityRefused("the bound context does not record this hypothesis as promoted")
        if self.multiplicity.family_size < 1:
            raise MultiplicityRefused("a promotion out of an empty tested family is not a result")

    def to_dict(self) -> dict[str, Any]:
        return {"result_id": self.result_id, "hypothesis_id": self.hypothesis_id, "multiplicity": self.multiplicity.to_dict(),
                "multiplicity_digest": self.multiplicity_digest, "multiplicity_statement": self.multiplicity.statement()}

    def rebind(self, ledger: MultiplicityLedger) -> "PromotedResult":
        """The same result under the ledger's CURRENT context (a later search widens the family it was selected from)."""
        if ledger.campaign_id != self.multiplicity.campaign_id:
            raise MultiplicityRefused("a result is rebound only to its own campaign's ledger")
        ctx = ledger.context()
        return PromotedResult(self.result_id, self.hypothesis_id, ctx, ctx.digest)


def verify_promoted(result: PromotedResult, ledger: MultiplicityLedger) -> list[str]:
    """Why ``result`` does not carry its campaign's FINAL multiplicity (empty when it does)."""
    if ledger.campaign_id != result.multiplicity.campaign_id:
        return ["the result belongs to another campaign's ledger"]
    if ledger.final is None:
        return ["the campaign's ledger is not closed: the family the result was selected from is not final"]
    if result.multiplicity_digest != ledger.final.digest:
        return ["the result binds an earlier context than the campaign's final one (rebind it after close)"]
    return []


def promote(result_id: str, hypothesis_id: str, ledger: MultiplicityLedger) -> PromotedResult:
    """Record ``hypothesis_id`` as promoted in ``ledger`` and bind the result to the resulting context."""
    ledger._promote(hypothesis_id)
    ctx = ledger.context()
    return PromotedResult(result_id, hypothesis_id, ctx, ctx.digest)


__all__ = ["COUNTERS", "MultiplicityContext", "MultiplicityLedger", "MultiplicityRefused", "PromotedResult", "promote", "verify_promoted"]
