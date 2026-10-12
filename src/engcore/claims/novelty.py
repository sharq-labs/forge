"""Novelty against a prior-art snapshot SEALED before the proposal.  Scientific support and novelty are separate axes.

* A :class:`PriorArtSnapshot` names its sources (the corpus manifest it was built from), its coverage criteria, the
  hypothesis KINDS it covers and its entries (canonical structure digest, source, and optionally the expression whose
  digest is part of the snapshot identity).  An empty snapshot covers nothing.
* A :class:`NoveltyLedger` (one per campaign, issued by the campaign's
  :class:`~engcore.claims.falsification.ExposureAuthority`, on its clock) is an ordered hash chain: a snapshot is
  SEALED in it, and a hypothesis is RECORDED as proposed in it.  A check is admissible only against the LATEST snapshot
  sealed BEFORE the hypothesis id, its claim or its structure was first seen anywhere on the authority's clock (a
  falsifier-registry registration counts), and snapshots only grow -- so a snapshot cannot be assembled after seeing the
  hypothesis, chosen among several, or trimmed, to omit the match.
* Canonicalizers and evaluators are REGISTERED by id (trusted setup, once); a caller cannot pass another function under
  a known id.  The canonicalizer is also SELF-TESTED against every snapshot entry that carries an expression; one that does not
  reproduce the snapshot's own digests is refused, and without any expression to test it against no POSSIBLY_NOVEL is
  issued.  When entries carry expressions the snapshot DECLARES the numeric-equivalence method (evaluator id, probes,
  tolerance), and the check must run with exactly that method.
* :func:`check_novelty` derives the structure identity ITSELF from ``statement_payload["expression"]`` with the
  canonicalizer the snapshot declares, refuses a hypothesis whose stated ``structure_digest`` disagrees, and decides by
  the methods that actually ran:

  - ``KNOWN_EQUIVALENT`` -- same canonical structure as an entry, or numerically equivalent on the declared probes;
  - ``POSSIBLY_NOVEL`` -- no match, the snapshot is non-empty and covers this kind, and every requested numeric
    comparison was decisive;
  - ``NOVELTY_UNRESOLVED`` -- no expression to compare, a kind the snapshot does not cover, an empty snapshot, or a
    numeric comparison that could not be decided (NaN, too few usable probes).

There is no NOVEL outcome: absence from a finite snapshot is "possibly novel", never "novel".  A language model's
opinion is not a method.  :func:`apply_novelty` RE-RUNS the check; a supplied check record is never trusted, and
:func:`verify_novelty` re-runs it to verify a recorded status (construction checks only shape).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

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


_CANONICALIZERS: dict[str, Callable[[Mapping[str, Any]], str]] = {}
_EVALUATORS: dict[str, Callable[[Mapping[str, Any], Mapping[str, float]], float]] = {}


def register_canonicalizer(canonicalizer_id: str, fn: Callable[[Mapping[str, Any]], str]) -> None:
    """Trusted setup: bind a canonicalizer id to its function, once.  A different function under a known id is refused."""
    _register(_CANONICALIZERS, canonicalizer_id, fn, "canonicalizer")


def register_evaluator(evaluator_id: str, fn: Callable[[Mapping[str, Any], Mapping[str, float]], float]) -> None:
    """Trusted setup: bind an evaluator id to its function, once."""
    _register(_EVALUATORS, evaluator_id, fn, "evaluator")


def _register(table: dict, key: str, fn: Callable, what: str) -> None:
    if not str(key).strip() or not callable(fn):
        raise NoveltyRefused(f"a {what} is registered under an id with a callable")
    if key in table and table[key] is not fn:
        raise NoveltyRefused(f"{what} {key!r} is already bound to another function")
    table[key] = fn


@dataclass(frozen=True)
class Canonicalizer:
    """A REGISTERED structure-identity function, resolved by id (a caller cannot pass another function under an id)."""

    canonicalizer_id: str
    fn: Callable[[Mapping[str, Any]], str] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        if _CANONICALIZERS.get(self.canonicalizer_id) is not self.fn:
            raise NoveltyRefused(f"canonicalizer {self.canonicalizer_id!r} is not registered with this function")

    @classmethod
    def resolve(cls, canonicalizer_id: str) -> "Canonicalizer":
        if canonicalizer_id not in _CANONICALIZERS:
            raise NoveltyRefused(f"no registered canonicalizer {canonicalizer_id!r}")
        return cls(canonicalizer_id, _CANONICALIZERS[canonicalizer_id])


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
    equivalence: Mapping[str, Any] | None = field(default=None, hash=False)   # declared method: EquivalenceSpec.to_dict()

    def __post_init__(self) -> None:
        if not str(self.snapshot_id).strip() or not self.covers_kinds:
            raise NoveltyRefused("a prior-art snapshot has an id and declares the hypothesis kinds it covers")
        if not self.sources or not str(self.coverage_criteria).strip() or not str(self.canonicalizer_id).strip():
            raise NoveltyRefused("a prior-art snapshot names its sources, its coverage criteria and its canonicalizer; "
                                 "coverage is not a self-declaration")
        if any(not e.source_ref.strip() for e in self.entries):
            raise NoveltyRefused("every prior-art entry names its source")
        if any(e.expression is not None for e in self.entries) and not self.equivalence:
            raise NoveltyRefused("entries carry expressions, so the snapshot declares the numeric-equivalence method to use")

    def to_dict(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "covers_kinds": sorted(self.covers_kinds), "sources": sorted(self.sources),
                "coverage_criteria": self.coverage_criteria, "canonicalizer_id": self.canonicalizer_id,
                "equivalence": None if not self.equivalence else json.loads(json.dumps(dict(self.equivalence), sort_keys=True)),
                "entries": sorted((e.to_dict() for e in self.entries), key=lambda x: x["entry_id"])}

    @property
    def digest(self) -> str:
        """Includes each entry's expression digest: removing an expression (to dodge numeric equivalence) changes it."""
        return _digest(self.to_dict())


class NoveltyLedger:
    """Ordered hash chain of snapshot seals and proposal records, on the issuing authority's clock.

    Snapshots only GROW: a later snapshot must contain every entry of the earlier ones (removing prior art never raises
    novelty), and a check must use the LATEST snapshot sealed before the proposal.  The proposal time is the earliest
    sighting of the hypothesis id, its claim or its structure anywhere on the authority's clock (a falsifier registry
    registration counts), so delaying the novelty record proves nothing."""

    def __init__(self, authority: Any, campaign_id: str, issued: Any = None) -> None:
        if issued is None or issued is not getattr(authority, "_issued", None):
            raise NoveltyRefused("a novelty ledger is issued by its campaign's exposure authority (ExposureAuthority.novelty_ledger)")
        self.__authority = authority
        self.__campaign_id = campaign_id
        self._entries: list[dict[str, Any]] = []
        self._sealed: dict[str, int] = {}
        self._snapshots: list[tuple[int, PriorArtSnapshot]] = []

    @property
    def campaign_id(self) -> str:
        return self.__campaign_id

    @property
    def head(self) -> str:
        return self._entries[-1]["digest"] if self._entries else GENESIS

    @property
    def anchor(self) -> tuple[str, str]:
        return (self.__authority.fingerprint, self.__campaign_id)

    @property
    def issued(self) -> bool:
        return getattr(self.__authority, "_novelty_ledgers", {}).get(self.__campaign_id) is self

    def _add(self, kind: str, subject: str, clock: int | None = None) -> int:
        clock = self.__authority._tick() if clock is None else clock
        e = {"sequence": len(self._entries), "clock": clock, "previous": self.head, "kind": kind, "subject": subject}
        e["digest"] = _digest(e)
        self._entries.append(e)
        return clock

    def seal(self, snapshot: PriorArtSnapshot) -> int:
        d = snapshot.digest
        if d in self._sealed:
            return self._sealed[d]
        if self._snapshots:
            previous = {(e.entry_id, e.structure_digest) for e in self._snapshots[-1][1].entries}
            if not previous <= {(e.entry_id, e.structure_digest) for e in snapshot.entries}:
                raise NoveltyRefused("a later prior-art snapshot contains every entry of the earlier one: prior art is never removed")
        clock = self._add("snapshot_sealed", d)
        self._sealed[d] = clock
        self._snapshots.append((clock, snapshot))
        return clock

    def record_proposal(self, hypothesis: Hypothesis) -> int:
        """Record a proposal on the authority's clock (its id, claim and declared structure are marked as seen)."""
        keys = [f"id:{hypothesis.hypothesis_id}", f"claim:{hypothesis.claim_digest}"] + (
            [f"structure:{hypothesis.structure_digest}"] if hypothesis.structure_digest else [])
        clock = self.__authority._see(*keys)
        return self._add("proposed", f"{hypothesis.hypothesis_id}:{hypothesis.content_digest}", clock)

    def ordering(self, snapshot: PriorArtSnapshot, hypothesis: Hypothesis, structure_key: str | None) -> tuple[int, int]:
        sealed = self._sealed.get(snapshot.digest)
        if sealed is None:
            raise NoveltyRefused("the prior-art snapshot was never sealed (or changed after it was sealed)")
        keys = [f"id:{hypothesis.hypothesis_id}", f"claim:{hypothesis.claim_digest}"] + ([f"structure:{structure_key}"]
                                                                                         if structure_key else [])
        proposed = self.__authority.first_seen(*keys)
        if proposed is None:
            raise NoveltyRefused("the hypothesis was never recorded as proposed; its timing against the snapshot is unknown")
        if not sealed < proposed:
            raise NoveltyRefused("the snapshot was sealed AFTER the hypothesis (or its claim or structure) was first seen: a "
                                 "snapshot assembled around a result is not prior art")
        latest = max((c for c, _s in self._snapshots if c < proposed), default=None)
        if latest != sealed:
            raise NoveltyRefused("a check uses the LATEST snapshot sealed before the proposal (it contains every earlier one)")
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
        if _EVALUATORS.get(self.evaluator_id) is not self.evaluate:
            raise NoveltyRefused(f"evaluator {self.evaluator_id!r} is not registered with this function")
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
    if not isinstance(ledger, NoveltyLedger) or not ledger.issued:
        raise NoveltyRefused("novelty is checked against the novelty ledger its authority issued for the campaign")
    if _CANONICALIZERS.get(canonicalizer.canonicalizer_id) is not canonicalizer.fn:
        raise NoveltyRefused("the canonicalizer is not the registered one for its id")
    if canonicalizer.canonicalizer_id != snapshot.canonicalizer_id:
        raise NoveltyRefused("the canonicalizer is not the one the snapshot's structure digests were computed with")
    declared = None if not snapshot.equivalence else json.loads(json.dumps(dict(snapshot.equivalence), sort_keys=True))
    if (equivalence is None) != (declared is None) or (equivalence is not None and
                                                       json.loads(json.dumps(equivalence.to_dict(), sort_keys=True)) != declared):
        raise NoveltyRefused("the numeric-equivalence method must be exactly the one the snapshot declares")
    testable = [e for e in snapshot.entries if e.expression is not None]
    if any(canonicalizer.fn(e.expression) != e.structure_digest for e in testable):
        raise NoveltyRefused("the canonicalizer does not reproduce the snapshot's own structure digests")
    expression = hypothesis.statement_payload.get("expression") if hypothesis.statement_payload else None
    derived = canonicalizer.fn(expression) if isinstance(expression, Mapping) else None
    sealed_at, proposed_at = ledger.ordering(snapshot, hypothesis, derived)
    base = dict(hypothesis_id=hypothesis.hypothesis_id, hypothesis_content_digest=hypothesis.content_digest,
                snapshot_digest=snapshot.digest, snapshot_sealed_at=sealed_at, proposal_recorded_at=proposed_at,
                equivalence=declared)
    kind = None if hypothesis.kind is None else hypothesis.kind.value
    if derived is None:
        return NoveltyCheck(**base, methods=(NoveltyMethod.NONE,), status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="",
                            reason="the hypothesis states no expression whose structure could be compared")
    if hypothesis.structure_digest != derived:
        raise NoveltyRefused("the hypothesis's structure_digest is missing or is not the canonical structure of its stated expression")
    methods = [NoveltyMethod.STRUCTURE_DIGEST]
    for e in snapshot.entries:
        if e.structure_digest == derived:
            return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.KNOWN_EQUIVALENT, matched_entry=e.entry_id,
                                reason=f"same canonical structure as {e.entry_id} ({e.source_ref})")
    undecided = []
    if equivalence is not None:
        methods.append(NoveltyMethod.NUMERIC_EQUIVALENCE)
        for e in testable:
            verdict = equivalence.compare(expression, e.expression)
            if verdict is Equivalence.EQUIVALENT:
                return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.KNOWN_EQUIVALENT, matched_entry=e.entry_id,
                                    reason=f"numerically equivalent to {e.entry_id} on the declared probes")
            if verdict is Equivalence.UNDECIDED:
                undecided.append(e.entry_id)

    def unresolved(reason: str) -> NoveltyCheck:
        return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="", reason=reason)

    if undecided:
        return unresolved(f"numeric equivalence could not be decided against {undecided}")
    if not snapshot.entries:
        return unresolved("the snapshot is empty: absence from nothing says nothing")
    if not testable:
        return unresolved("no snapshot entry carries an expression, so the canonicalizer cannot be verified")
    if kind not in snapshot.covers_kinds:
        return unresolved(f"the snapshot does not cover hypotheses of kind {kind!r}")
    return NoveltyCheck(**base, methods=tuple(methods), status=NoveltyStatus.POSSIBLY_NOVEL, matched_entry="",
                        reason=f"no equivalent among {len(snapshot.entries)} entries of snapshot {snapshot.snapshot_id} "
                               f"(sources: {', '.join(sorted(snapshot.sources))})")


def apply_novelty(hypothesis: Hypothesis, snapshot: PriorArtSnapshot, ledger: NoveltyLedger, *, canonicalizer: Canonicalizer,
                  equivalence: EquivalenceSpec | None = None) -> tuple[Hypothesis, NoveltyCheck]:
    """Run the check and apply it.  The status comes from a check this call ran, never from a supplied record."""
    check = check_novelty(hypothesis, snapshot, ledger, canonicalizer=canonicalizer, equivalence=equivalence)
    revised = hypothesis.revise(novelty_status=check.status, knowledge_snapshot_ref=check.snapshot_digest, novelty_basis=check.digest)
    return revised, check


def verify_novelty(hypothesis: Hypothesis, snapshot: PriorArtSnapshot, ledger: NoveltyLedger, *, anchor: tuple[str, str],
                   canonicalizer: Canonicalizer, equivalence: EquivalenceSpec | None = None) -> list[str]:
    """Why ``hypothesis``'s recorded novelty is NOT what re-running the check against the expected campaign ledger gives
    (empty when it is).  Consumers gate on this; a hand-built or carried-over novelty status fails it."""
    if hypothesis.novelty_status is NoveltyStatus.NOT_CHECKED:
        return []
    if ledger.anchor != anchor:
        return ["the novelty ledger is not the expected one (authority key or campaign differs)"]
    try:
        check = check_novelty(hypothesis, snapshot, ledger, canonicalizer=canonicalizer, equivalence=equivalence)
    except NoveltyRefused as exc:
        return [str(exc)]
    problems = []
    if check.status is not hypothesis.novelty_status:
        problems.append(f"re-running the check gives {check.status.value}, not {hypothesis.novelty_status.value}")
    if hypothesis.knowledge_snapshot_ref != snapshot.digest or hypothesis.novelty_basis != check.digest:
        problems.append("the recorded snapshot or check record is not the one this content and snapshot produce")
    return problems


__all__ = ["Canonicalizer", "Equivalence", "EquivalenceSpec", "NoveltyCheck", "NoveltyLedger", "NoveltyMethod", "NoveltyRefused",
           "PriorArtEntry", "PriorArtSnapshot", "apply_novelty", "check_novelty", "register_canonicalizer", "register_evaluator",
           "verify_novelty"]
