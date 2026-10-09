"""Novelty against a FROZEN prior-art snapshot.  Scientific support and novelty are separate axes.

A :class:`PriorArtSnapshot` is frozen (digest) before the check.  It lists known structures (canonical structure
digests, e.g. :func:`engcore.blindfold.expression.structure_digest`) with their sources, and declares which hypothesis
KINDS it covers.  :func:`check_novelty` decides, by a declared method only:

* ``KNOWN_EQUIVALENT`` -- the structure digest matches a snapshot entry, or a supplied numeric-equivalence evaluator
  finds the hypothesis indistinguishable from an entry on the declared probe points;
* ``POSSIBLY_NOVEL`` -- no match, and the snapshot covers this hypothesis kind;
* ``NOVELTY_UNRESOLVED`` -- the snapshot does not cover the kind, or the hypothesis has no structure identity to check.

There is no NOVEL outcome: absence from a finite snapshot is "possibly novel", never "novel".  A language model's
opinion is not a method here; the methods are structure identity and numeric equivalence.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from ..sria.decision import Hypothesis, NoveltyStatus

NOVELTY_CHECK_SCHEMA = "engcore.claims.novelty_check/1"


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class NoveltyRefused(ValueError):
    pass


class NoveltyMethod(str, Enum):
    STRUCTURE_DIGEST = "structure_digest"
    NUMERIC_EQUIVALENCE = "numeric_equivalence"


@dataclass(frozen=True)
class PriorArtEntry:
    entry_id: str
    structure_digest: str
    source_ref: str
    expression: Mapping[str, Any] | None = field(default=None, hash=False)   # optional, for numeric equivalence


@dataclass(frozen=True)
class PriorArtSnapshot:
    snapshot_id: str
    covers_kinds: tuple[str, ...]
    entries: tuple[PriorArtEntry, ...]

    def __post_init__(self) -> None:
        if not str(self.snapshot_id).strip() or not self.covers_kinds:
            raise NoveltyRefused("a prior-art snapshot has an id and declares the hypothesis kinds it covers")
        if any(not e.source_ref.strip() for e in self.entries):
            raise NoveltyRefused("every prior-art entry names its source")

    def to_dict(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "covers_kinds": sorted(self.covers_kinds),
                "entries": sorted(({"entry_id": e.entry_id, "structure_digest": e.structure_digest, "source_ref": e.source_ref}
                                   for e in self.entries), key=lambda x: x["entry_id"])}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class NoveltyCheck:
    hypothesis_id: str
    hypothesis_content_digest: str
    snapshot_digest: str
    method: NoveltyMethod
    status: NoveltyStatus
    matched_entry: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": NOVELTY_CHECK_SCHEMA, "hypothesis_id": self.hypothesis_id,
                "hypothesis_content_digest": self.hypothesis_content_digest, "snapshot_digest": self.snapshot_digest,
                "method": self.method.value, "status": self.status.value, "matched_entry": self.matched_entry, "reason": self.reason}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def check_novelty(hypothesis: Hypothesis, snapshot: PriorArtSnapshot, *, frozen_digest: str,
                  equivalence: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None,
                  expression: Mapping[str, Any] | None = None) -> NoveltyCheck:
    """Check ``hypothesis`` against ``snapshot``, which must still hash to ``frozen_digest`` (frozen before the check)."""
    if snapshot.digest != frozen_digest:
        raise NoveltyRefused("the prior-art snapshot changed after it was frozen; a snapshot edited around a result is not prior art")
    base = dict(hypothesis_id=hypothesis.hypothesis_id, hypothesis_content_digest=hypothesis.content_digest,
                snapshot_digest=snapshot.digest)
    kind = None if hypothesis.kind is None else hypothesis.kind.value
    if not hypothesis.structure_digest:
        return NoveltyCheck(**base, method=NoveltyMethod.STRUCTURE_DIGEST, status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="",
                            reason="the hypothesis has no canonical structure identity to compare")
    for e in snapshot.entries:
        if e.structure_digest == hypothesis.structure_digest:
            return NoveltyCheck(**base, method=NoveltyMethod.STRUCTURE_DIGEST, status=NoveltyStatus.KNOWN_EQUIVALENT,
                                matched_entry=e.entry_id, reason=f"same canonical structure as {e.entry_id} ({e.source_ref})")
    if equivalence is not None and expression is not None:
        for e in snapshot.entries:
            if e.expression is not None and equivalence(expression, e.expression):
                return NoveltyCheck(**base, method=NoveltyMethod.NUMERIC_EQUIVALENCE, status=NoveltyStatus.KNOWN_EQUIVALENT,
                                    matched_entry=e.entry_id, reason=f"numerically equivalent to {e.entry_id} on the probe points")
    if kind not in snapshot.covers_kinds:
        return NoveltyCheck(**base, method=NoveltyMethod.STRUCTURE_DIGEST, status=NoveltyStatus.NOVELTY_UNRESOLVED, matched_entry="",
                            reason=f"the snapshot does not cover hypotheses of kind {kind!r}")
    return NoveltyCheck(**base, method=NoveltyMethod.NUMERIC_EQUIVALENCE if equivalence else NoveltyMethod.STRUCTURE_DIGEST,
                        status=NoveltyStatus.POSSIBLY_NOVEL, matched_entry="",
                        reason=f"no equivalent among {len(snapshot.entries)} entries of frozen snapshot {snapshot.snapshot_id}")


def apply_novelty(hypothesis: Hypothesis, check: NoveltyCheck) -> Hypothesis:
    if check.hypothesis_content_digest != hypothesis.content_digest:
        raise NoveltyRefused("the novelty check judged other content than this revision")
    return hypothesis.revise(novelty_status=check.status, knowledge_snapshot_ref=check.snapshot_digest, novelty_basis=check.digest)


def numeric_equivalence(evaluate: Callable[[Mapping[str, Any], Mapping[str, float]], float], probes: Sequence[Mapping[str, float]], *,
                        rel_tol: float) -> Callable[[Mapping[str, Any], Mapping[str, Any]], bool]:
    """Equivalence on declared probe points up to a proportionality constant (laws differing only in a constant are the
    same law with another constant).  NaN on any probe is not equivalence."""
    if not probes or not rel_tol > 0:
        raise NoveltyRefused("numeric equivalence needs probe points and a positive tolerance")

    def eq(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
        ratios = []
        for p in probes:
            va, vb = evaluate(a, p), evaluate(b, p)
            if not (math.isfinite(va) and math.isfinite(vb)) or vb == 0:
                return False
            ratios.append(va / vb)
        r0 = ratios[0]
        return r0 != 0 and all(abs(r / r0 - 1) <= rel_tol for r in ratios)
    return eq


__all__ = ["NoveltyCheck", "NoveltyMethod", "NoveltyRefused", "PriorArtEntry", "PriorArtSnapshot", "apply_novelty", "check_novelty",
           "numeric_equivalence"]
