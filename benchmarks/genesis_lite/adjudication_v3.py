"""FDA-05 adjudication for the Genesis-lite v0.3 development path (owner-approved 2026-10-28).

The escrow and ``roles.adjudicate`` belong to the byte-pinned v0.2 substrate and are not changed. For an INDISTINGUISHABLE
answer the escrow already reports, in its signed score body, whether the pair *contains* the truth (one law passes the
accuracy rule) separately from whether it only *brackets* it. This module applies the v0.3 rule to those facts: a pair hit
that only brackets the truth is ``indistinguishable_unresolved`` and keeps only a non-positive credit (penalties stay, a
positive recovery credit becomes zero). Every other outcome is the v0.2 adjudication unchanged.

Limits. The pair facts come from the pinned v0.2 ``escrow._assess_pair``; the independent v0.3 evaluator
(``score_v3._pair_outcome``) implements the owner-approved v3 distance and differs from it in five places: in-box agreement
and outside divergence use |a-b|/|b| (order-dependent, b == 0 skipped) in the escrow but |a-b|/max(|a|,|b|) in v0.3;
bracketing uses lo*(1-tol)..hi*(1+tol) in the escrow but lo-tol|lo|..hi+tol|hi| in v0.3; outside points with a non-finite
truth are skipped by the escrow's divergence count but counted by v0.3; and a zero truth never counts as within tolerance in
the escrow while v0.3 accepts an exact zero prediction. Every such case surfaces as an evaluator disagreement, so the WHOLE
campaign is INVALID (fail closed), never scored under two rules; a pilot must therefore report disagreement-invalid runs
per arm. Which distance v0.3 finally adopts in the escrow itself is an open owner decision. The escrow report bound by
``report_digest`` keeps v0.2 outcomes (bracketing credited); the v0.3 outcomes are the adjudications returned here.
DEVELOPMENT_ONLY: no preregistration, custody or formal statistics.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from engcore.blindfold import EvaluatorConfig
from engcore.blindfold.roles import Adjudication

BENCHMARK_ID = "genesis_lite.blindfold_l5.v0_3"
READINESS = "DEVELOPMENT_ONLY"
#: the v0.2 credit table under its own sealed identity: the config id names the v0.3 outcome rule
CONFIG_V3 = EvaluatorConfig("forge.genesis_lite.v0_3", "1")


class AdjudicationRefused(ValueError):
    """The escrow facts do not belong to this adjudication, or the config is not the sealed v0.3 one."""


def adjudicate_v3(adjudication: Adjudication, score_body: Mapping[str, Any], config: EvaluatorConfig) -> Adjudication:
    if config.digest != CONFIG_V3.digest or adjudication.config_digest != config.digest:
        raise AdjudicationRefused("only the sealed v0.3 evaluator configuration adjudicates the v0.3 path")
    if (score_body.get("universe_id") != adjudication.universe_id
            or score_body.get("proposal_digest") != adjudication.proposal_digest
            or (score_body.get("receipt") or {}).get("digest") != adjudication.score_receipt_digest):
        raise AdjudicationRefused("the escrow score body is not the one this adjudication was receipted for")
    if adjudication.answer != "indistinguishable":
        return adjudication
    pair = score_body.get("pair") or {}
    if not pair.get("hit") or pair.get("contains_truth"):
        return adjudication                    # a miss, or a hit that contains the truth: v0.2 outcome stands
    hit_credit = config.credit_for(adjudication.universe_kind, "indistinguishable_hit")
    return replace(adjudication, outcome="indistinguishable_unresolved", credit=min(0.0, hit_credit))


__all__ = ["AdjudicationRefused", "BENCHMARK_ID", "CONFIG_V3", "READINESS", "adjudicate_v3"]
