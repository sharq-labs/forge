"""FDA-05 adjudication for the Genesis-lite v0.3 development path (owner-approved 2026-10-28).

The escrow and ``roles.adjudicate`` belong to the byte-pinned v0.2 substrate and are not changed. For an INDISTINGUISHABLE
answer the escrow already reports, in its signed score body, whether the pair *contains* the truth (one law passes the
accuracy rule) separately from whether it only *brackets* it. This module applies the v0.3 rule to those facts: a pair hit
that only brackets the truth is ``indistinguishable_unresolved`` and keeps only a non-positive credit (penalties stay, a
positive recovery credit becomes zero). Every other outcome is the v0.2 adjudication unchanged.

Rule source. Since the owner decision of 2026-10-29 (option B) the pair and fraction facts come from
``engcore.blindfold.escrow_v3.EscrowServiceV3``, which applies the same five rules as the independent evaluator
(``score_v3``): symmetric |a-b|/max(|a|,|b|) in the box and outside, sign-correct bracketing bounds, outside divergence over
every outside point, and exact zero predictions of zero truths. The pinned v0.2 ``escrow.py`` is unchanged. Any remaining
disagreement still invalidates the whole campaign (fail closed). The report bound by ``report_digest`` maps those facts
with the v0.2 outcome rule (a bracketing-only pair is a hit there); the v0.3 outcomes are the adjudications returned here.
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
