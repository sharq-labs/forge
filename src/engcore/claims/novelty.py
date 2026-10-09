"""Novelty against a prior-art snapshot SEALED before the proposal.  Scientific support and novelty are separate axes.

* A :class:`PriorArtSnapshot` names its sources (the corpus manifest it was built from), its coverage criteria, the
  hypothesis KINDS it covers and its entries (canonical structure digest, source, and optionally the expression whose
  digest is part of the snapshot identity).  An empty snapshot covers nothing.
* A :class:`NoveltyLedger` is an ordered hash chain: a snapshot is SEALED in it, and a hypothesis is RECORDED as
  proposed in it.  A check is admissible only against a snapshot sealed BEFORE the proposal was recorded, so a snapshot
  cannot be assembled after seeing the hypothesis (and silently omit the matching entry).
* :func:`check_novelty` derives the structure identity ITSELF from ``statement_payload["expression"]`` with the
  canonicalizer the snapshot declares, refuses a hypothesis whose stated ``structure_digest`` disagrees, and decides by
  the methods that actually ran:

  - ``KNOWN_EQUIVALENT`` -- same canonical structure as an entry, or numerically equivalent on the declared probes;
  - ``POSSIBLY_NOVEL`` -- no match, the snapshot is non-empty and covers this kind, and every requested numeric
    comparison was decisive;
  - ``NOVELTY_UNRESOLVED`` -- no expression to compare, a kind the snapshot does not cover, an empty snapshot, or a
    numeric comparison that could not be decided (NaN, too few usable probes).

There is no NOVEL outcome: absence from a finite snapshot is "possibly novel", never "novel".  A language model's
opinion is not a method.  :func:`apply_novelty` RE-RUNS the check; a supplied check record is never trusted.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from ..sria.decision import Hypothesis, NoveltyStatus

NOVELTY_CHECK_SCHEMA = "engcore.claims.novelty_check/2"
GENESIS = "0" * 64


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class NoveltyRefused(ValueError):
    pass


class NoveltyMethod(str, Enum):
    NONE = "none"
    STRUCTURE_DIGEST = "structure_digest"
    NUMERIC_EQUIVALENCE = "numeric_equivalence"


class Equivalence(str, Enum):
    EQUIVALENT = "equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    UNDECIDED = "undecided"


@dataclass(frozen=True)
class Canonicalizer:
    """A declared structure-identity function (e.g. :func:`engcore.blindfold.expression.structure_digest`)."""

    canonicalizer_id: str
    fn: Callable[[Mapping[str, Any]], str] = field(compare=False, repr=False)


@dataclass(frozen=True)
class PriorArtEntry:
    entry_id: str
    structure_digest: str
    source_ref: str
    expression: Mapping[str, Any] | None = field(default=None, hash=False)   # optional, for numeric equivalence

    def to_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "structure_digest": self.structure_digest, "source_ref": self.source_ref,
                "expression_digest": None if self.expression is None else _digest(dict(self.expression))}


@dataclass(frozen=True)
class PriorArtSnapshot:
    snapshot_id: str
    covers_kinds: tuple[str, ...]
    entries: tuple[PriorArtEntry, ...]
    sources: tuple[str, ...] = ()          # the corpus manifest the snapshot was built from
    coverage_criteria: str = ""            # how an entry got in (search terms, inclusion rules)
    canonicalizer_id: str = ""

    def __post_init__(self) -> None:
        if not str(self.snapshot_id).strip() or not self.covers_kinds:
            raise NoveltyRefused("a prior-art snapshot has an id and declares the hypothesis kinds it covers")
        if not self.sources or not str(self.coverage_criteria).strip() or not str(self.canonicalizer_id).strip():
            raise NoveltyRefused("a prior-art snapshot names its sources, its coverage criteria and its canonicalizer; "
                                 "coverage is not a self-declaration")
        if any(not e.source_ref.strip() for e in self.entries):
            raise NoveltyRefused("every prior-art entry names its source")

    def to_dict(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "covers_kinds": sorted(self.covers_kinds), "sources": sorted(self.sources),
                "coverage_criteria": self.coverage_criteria, "canonicalizer_id": self.canonicalizer_id,
                "entries": sorted((e.to_dict() for e in self.entries), key=lambda x: x["entry_id"])}

    @property
    def digest(self) -> str:
        """Includes each entry's expression digest: removing an expression (to dodge numeric equivalence) changes it."""
        return _digest(self.to_dict())


class NoveltyLedger:
    """Ordered hash chain of snapshot seals and proposal records.  Order is the only clock that matters."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._sealed: dict[str, int] = {}
        self._proposed: dict[tuple[str, str], int] = {}

    @property
    def head(self) -> str:
        return self._entries[-1]["digest"] if self._entries else GENESIS

    def _add(self, kind: str, subject: str) -> int:
        e = {"sequence": len(self._entries), "previous": self.head, "kind": kind, "subject": subject}
        e["digest"] = _digest(e)
        self._entries.append(e)
        return e["sequence"]

    def seal(self, snapshot: PriorArtSnapshot) -> int:
        d = snapshot.digest
        if d not in self._sealed:
            self._sealed[d] = self._add("snapshot_sealed", d)
        return self._sealed[d]

    def record_proposal(self, hypothesis: Hypothesis) -> int:
        key = (hypothesis.hypothesis_id, hypothesis.content_digest)
        if key not in self._proposed:
            self._proposed[key] = self._add("proposed", f"{key[0]}:{key[1]}")
        return self._proposed[key]

    def ordering(self, snapshot: PriorArtSnapshot, hypothesis: Hypothesis) -> tuple[int, int]:
        sealed = self._sealed.get(snapshot.digest)
        proposed = self._proposed.get((hypothesis.hypothesis_id, hypothesis.content_digest))
        if sealed is None:
            raise NoveltyRefused("the prior-art snapshot was never sealed (or changed after it was sealed)")
        if proposed is None:
            raise NoveltyRefused("the hypothesis was never recorded as proposed; its timing against the snapshot is unknown")
        if not sealed < proposed:
            raise NoveltyRefused("the snapshot was sealed AFTER the proposal: a snapshot assembled around a result is not prior art")
        return sealed, proposed


@dataclass(frozen=True)
class EquivalenceSpec:
    """A numeric-equivalence method: probe points, tolerance and the evaluator's id, all bound into the check."""

    evaluator_id: str
    evaluate: Callable[[Mapping[str, Any], Mapping[str, float]], float] = field(compare=False, repr=False)
    probes: tuple[Mapping[str, float], ...] = ()
    rel_tol: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "probes", tuple(dict(p) for p in self.probes))
        if not str(self.evaluator_id).strip() or len(self.probes) < 2 or not (math.isfinite(self.rel_tol) and self.rel_tol > 0):
            raise NoveltyRefused("numeric equivalence names its evaluator and declares >= 2 probe points and a positive tolerance")

    def to_dict(self) -> dict[str, Any]:
        return {"evaluator_id": self.evaluator_id, "probes": [dict(sorted(p.items())) for p in self.probes], "rel_tol": self.rel_tol}

    def compare(self, a: Mapping[str, Any], b: Mapping[str, Any]) -> Equivalence:
        """Equal up to a proportionality constant on the probes.  Probes where BOTH are zero carry no information and
        are skipped; a NaN, or fewer than two informative probes, is UNDECIDED (never 'not equivalent')."""
        ratios = []
        for p in self.probes:
            va, vb = self.evaluate(a, p), self.evaluate(b, p)
            if not (math.isfinite(va) and math.isfinite(vb)):
                return Equivalence.UNDECIDED
            if va == 0 and vb == 0:
                continue
            if va == 0 or vb == 0:
                return Equivalence.NOT_EQUIVALENT
            ratios.append(va / vb)
        if len(ratios) < 2:
            return Equivalence.UNDECIDED
        r0 = ratios[0]
        return Equivalence.EQUIVALENT if all(abs(r / r0 - 1) <= self.rel_tol for r in ratios) else Equivalence.NOT_EQUIVALENT


@dataclass(frozen=True)
class NoveltyCheck:
    hypothesis_id: str
    hypothesis_content_digest: str
    snapshot_digest: str
    snapshot_sealed_at: int
    proposal_recorded_at: int
    methods: tuple[NoveltyMethod, ...]
    equivalence: Mapping[str, Any] | None
    status: NoveltyStatus
    matched_entry: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": NOVELTY_CHECK_SCHEMA, "hypothesis_id": self.hypothesis_id,
                "hypothesis_content_digest": self.hypothesis_content_digest, "snapshot_digest": self.snapshot_digest,
                "snapshot_sealed_at": self.snapshot_sealed_at, "proposal_recorded_at": self.proposal_recorded_at,
                "methods": [m.value for m in self.methods], "equivalence": None if self.equivalence is None else dict(self.equivalence),
                "status": self.status.value, "matched_entry": self.matched_entry, "reason": self.reason}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def check_novelty(hypothesis: Hypothesis, snapshot: PriorArtSnapshot, ledger: NoveltyLedger, *, canonicalizer: Canonicalizer,
                  equivalence: EquivalenceSpec | None = None) -> NoveltyCheck:
    """Check ``hypothesis`` against ``snapshot``, which must have been sealed in ``ledger`` before the proposal."""
    sealed_at, proposed_at = ledger.ordering(snapshot, hypothesis)
    if canonicalizer.canonicalizer_id != snapshot.canonicalizer_id:
        raise NoveltyRefused("the canonicalizer is not the one the snapshot's structure digests were computed with")
    base = dict(hypothesis_id=hypothesis.hypothesis_id, hypothesis_content_digest=hypothesis.content_digest,
                snapshot_digest=snapshot.digest, snapshot_sealed_at=sealed_at, proposal_recorded_at=proposed_at,
                equivalence=None if equivalence is None else equivalence.to_dict())
    kind = None if hypothesis.kind is None else hypothesis.kind.value
    expression = hypothesis.statement_payload.get("expression") if hypothesis.statement_payload else None
    if not isinstance(expression, Mapping):
        return NoveltyCheck(**base, methods=(NoveltyMethod.NONE,), status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="",
                            reason="the hypothesis states no expression whose structure could be compared")
    derived = canonicalizer.fn(expression)
    if hypothesis.structure_digest and hypothesis.structure_digest != derived:
        raise NoveltyRefused("the hypothesis's structure_digest is not the canonical structure of its own stated expression")
    methods = [NoveltyMethod.STRUCTURE_DIGEST]
    for e in snapshot.entries:
        if e.structure_digest == derived:
            return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.KNOWN_EQUIVALENT, matched_entry=e.entry_id,
                                reason=f"same canonical structure as {e.entry_id} ({e.source_ref})")
    undecided = []
    if equivalence is not None:
        methods.append(NoveltyMethod.NUMERIC_EQUIVALENCE)
        for e in snapshot.entries:
            if e.expression is None:
                continue
            verdict = equivalence.compare(expression, e.expression)
            if verdict is Equivalence.EQUIVALENT:
                return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.KNOWN_EQUIVALENT, matched_entry=e.entry_id,
                                    reason=f"numerically equivalent to {e.entry_id} on the declared probes")
            if verdict is Equivalence.UNDECIDED:
                undecided.append(e.entry_id)
    if undecided:
        return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="",
                            reason=f"numeric equivalence could not be decided against {undecided}")
    if not snapshot.entries:
        return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="",
                            reason="the snapshot is empty: absence from nothing says nothing")
    if kind not in snapshot.covers_kinds:
        return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="",
                            reason=f"the snapshot does not cover hypotheses of kind {kind!r}")
    return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.POSSIBLY_NOVEL, matched_entry="",
                        reason=f"no equivalent among {len(snapshot.entries)} entries of snapshot {snapshot.snapshot_id} "
                               f"(sources: {', '.join(sorted(snapshot.sources))})")


def apply_novelty(hypothesis: Hypothesis, snapshot: PriorArtSnapshot, ledger: NoveltyLedger, *, canonicalizer: Canonicalizer,
                  equivalence: EquivalenceSpec | None = None) -> tuple[Hypothesis, NoveltyCheck]:
    """Run the check and apply it.  The status comes from a check this call ran, never from a supplied record."""
    check = check_novelty(hypothesis, snapshot, ledger, canonicalizer=canonicalizer, equivalence=equivalence)
    revised = hypothesis.revise(novelty_status=check.status, knowledge_snapshot_ref=check.snapshot_digest, novelty_basis=check.digest)
    return revised, check


__all__ = ["Canonicalizer", "Equivalence", "EquivalenceSpec", "NoveltyCheck", "NoveltyLedger", "NoveltyMethod", "NoveltyRefused",
           "PriorArtEntry", "PriorArtSnapshot", "apply_novelty", "check_novelty"]
