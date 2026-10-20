"""FDA-05, escrow half: an INDISTINGUISHABLE pair's bracket credit needs an outside-box informativeness bound.

Deep audit 2026-10-19 (R-05, EXECUTED_REPRODUCED): ``escrow._assess_pair`` credits a pair that brackets the truth
however far apart its two laws are outside the box. A pair built only from an in-box fit and the public box edges
(A/B = 1.3e30 at the region edge) earned a hit for two mutually exclusive truths: UNKNOWN became knowledge.

The bounded assessment keeps every condition of ``escrow._assess_pair`` and restricts its last one:

    the pair contains the truth (one law passes), OR it brackets the truth at PASS_FRACTION of the evaluation points
    AND at EVERY evaluation point outside the box both laws are finite, non-zero, of one sign and
    max(|A|, |B|) / min(|A|, |B|) <= 1 + w.

``w`` comes from a :class:`PairBound` (absolute, or a multiple of the universe's tolerance). The bound applies to the
bracket only: the generator's honest rival differs from its law by a factor that grows without limit outside the box
(``universe._rival``), so bounding a pair that contains the truth would refuse correct answers.

This module is ADDITIVE. ``escrow.py`` and ``roles.py`` are unchanged, so every existing campaign, configuration digest
and identity (including Genesis-lite v0.2, which pins those files) is unchanged. A bounded campaign is opted into by
running :class:`PairBoundedEscrowService` with a :class:`BoundedEvaluatorConfig`:

* the configuration digest includes the bound, and the campaign declares that digest at creation, before any kind is
  revealed; the bounded escrow refuses a campaign sealed under any other configuration;
* the bounded escrow runs ``EscrowService._score``'s own code, with ``_assess_pair`` replaced by
  :func:`assess_pair_bounded` and nothing else, so admission, sealing, truth generation and receipts are the escrow's
  (there is no second scoring procedure);
* the score receipt carries the bound, the unbounded verdict and the outside spread ratio, so a reader can see what
  the bound decided.

The independent Genesis-lite evaluator (``benchmarks/genesis_lite/v0_3/evaluator.py``) re-implements the same rule
without importing this module; the two must agree on every universe, or the run is invalid.

Certification: a new file in certified scope. UNCERTIFIED until the owner's recertification (OD-3).
"""

from __future__ import annotations

import math
import types
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import escrow as _escrow
from .escrow import EscrowRefused, EscrowService, _assess_pair, _outside_box
from .expression import evaluate
from .roles import EvaluatorConfig
from .universe import HiddenWorld

PAIR_ASSESSMENT = "forge.blindfold.pair_assessment.bounded/1"
FORMS = ("absolute", "tol_multiple")


@dataclass(frozen=True)
class PairBound:
    form: str
    value: float

    def __post_init__(self) -> None:
        if self.form not in FORMS:
            raise EscrowRefused(f"a pair bound's form is one of {FORMS}")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value) \
                or self.value <= 0:
            raise EscrowRefused("a pair bound is a finite positive number")

    def w(self, tolerance: float) -> float:
        return float(self.value) * (float(tolerance) if self.form == "tol_multiple" else 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {"form": self.form, "value": float(self.value)}


@dataclass(frozen=True)
class BoundedEvaluatorConfig(EvaluatorConfig):
    """An evaluator configuration whose digest also seals the pair bound and the assessment it selects."""

    pair_bound: PairBound | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pair_bound, PairBound):
            raise EscrowRefused("a bounded evaluator configuration names its PairBound")

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(pair_bound=self.pair_bound.to_dict(), pair_assessment=PAIR_ASSESSMENT)  # type: ignore[union-attr]
        return out


def outside_spread_ratio(laws: list[Mapping[str, Any]], truths: list[tuple[dict[str, float], float]],
                         world: HiddenWorld) -> float:
    """max over the evaluation points outside the box of max(|A|,|B|)/min(|A|,|B|); infinite when there is no such
    point, or when at one of them a law is non-finite or zero or the two laws differ in sign."""
    worst = -math.inf
    for point, _truth in truths:
        if not _outside_box(point, world):
            continue
        a, b = evaluate(laws[0], point), evaluate(laws[1], point)
        if not (math.isfinite(a) and math.isfinite(b)) or a == 0 or b == 0 or (a > 0) != (b > 0):
            return math.inf
        worst = max(worst, max(abs(a), abs(b)) / min(abs(a), abs(b)))
    return worst if worst > -math.inf else math.inf


def assess_pair_bounded(laws: list[Mapping[str, Any]], truths: list[tuple[dict[str, float], float]],
                        inbox: list[tuple[dict[str, float], float]], world: HiddenWorld, bound: PairBound) -> dict[str, Any]:
    """``escrow._assess_pair`` with the bracket restricted by ``bound`` (module docstring)."""
    base = _assess_pair(laws, truths, inbox, world)
    ratio = outside_spread_ratio(laws, truths, world)
    informative = math.isfinite(ratio) and ratio <= 1.0 + bound.w(world.tolerance)
    hit = bool(base["hit"] and (base["contains_truth"] or informative))
    return {**base, "hit": hit, "unbounded_hit": bool(base["hit"]), "informative_outside": informative,
            "outside_spread_ratio": ratio if math.isfinite(ratio) else None, "pair_bound": bound.to_dict(),
            "assessment": PAIR_ASSESSMENT}


class PairBoundedEscrowService(EscrowService):
    """An escrow whose campaigns are sealed under one :class:`BoundedEvaluatorConfig` and score pairs with its bound."""

    def __init__(self, master_seed: bytes | None = None, *, config: BoundedEvaluatorConfig, **kwargs: Any) -> None:
        if not isinstance(config, BoundedEvaluatorConfig):
            raise EscrowRefused("a pair-bounded escrow is configured with a BoundedEvaluatorConfig")
        self._bounded_config = config
        bound = config.pair_bound

        def bounded(laws: list[Mapping[str, Any]], truths: list[tuple[dict[str, float], float]],
                    inbox: list[tuple[dict[str, float], float]], world: HiddenWorld) -> dict[str, Any]:
            return assess_pair_bounded(laws, truths, inbox, world, bound)  # type: ignore[arg-type]

        namespace = dict(vars(_escrow))
        namespace["_assess_pair"] = bounded
        source = EscrowService._score
        self._bounded_score = types.MethodType(
            types.FunctionType(source.__code__, namespace, source.__name__, source.__defaults__, source.__closure__), self)
        super().__init__(master_seed, **kwargs)                 # a stored escrow replays through the bounded handlers

    def _create(self, req: Mapping[str, Any]) -> dict[str, Any]:
        if str(req.get("evaluator_config_digest", "")) != self._bounded_config.digest:
            raise EscrowRefused("this escrow scores pairs under one sealed bounded configuration; the campaign declares "
                                "another one")
        return super()._create(req)

    def _score(self, req: Mapping[str, Any]) -> dict[str, Any]:
        return self._bounded_score(req)


__all__ = ["BoundedEvaluatorConfig", "FORMS", "PAIR_ASSESSMENT", "PairBound", "PairBoundedEscrowService",
           "assess_pair_bounded", "outside_spread_ratio"]
