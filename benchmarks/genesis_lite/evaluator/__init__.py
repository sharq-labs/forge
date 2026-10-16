"""Genesis-lite separately implemented evaluator.

This package scores sealed proposals against a revealed answer key. It is deliberately written WITHOUT importing
``engcore`` (or anything outside the Python standard library), so the grade does not come from the FORGE scientific
authority being evaluated (Genesis §10.1, §23). It re-implements the preregistered law-assessment and pair-assessment
rules that the Blindfold escrow also applies; its outcome, credit and per-law fraction within tolerance must AGREE with
the escrow's for every universe, and any disagreement makes the run ``EVALUATOR_DISAGREEMENT`` (benchmark-invalid).

Independence is a property of CODE here (a separate implementation, no import path into the evaluated authority),
not of PEOPLE or PROCESSES: the author is the same development team, and the hidden worlds and their truths come from
FORGE's generator (a common-mode risk). Third-party evaluation (Genesis §26) is an owner decision recorded in the
preregistration.
"""

from .score import (  # noqa: F401
    CARD_KEYS, CREDIT, CREDIT_DIGEST, EVALUATOR_SCHEMA, EvaluatorRefused, audit_presented_cards, credit_digest,
    evaluate_campaign, fraction_within, in_monomial_family, region_tell, score_universe,
)

__all__ = ["CARD_KEYS", "CREDIT", "CREDIT_DIGEST", "EVALUATOR_SCHEMA", "EvaluatorRefused", "audit_presented_cards",
           "credit_digest", "evaluate_campaign", "fraction_within", "in_monomial_family", "region_tell", "score_universe"]
