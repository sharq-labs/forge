"""Core re-audit 2026-09-16, batch 44: a conditioned posterior says it is conditioned, and a budget is a bound.

Problem R-59 (the audit's finding 72), improvement I-28 part A of three, under
benchmarks/core_v4_false_confidence/BATCH44_THRESHOLD_PROTOCOL.json.

`condition_posterior_on_predictive_admission` is meant to fail closed above a declared budget and accepts any
finite non-negative one: at 1.0 it conditions away 99.9997% of the posterior, renormalizes by 3.4e5, and
returns an ordinary PosteriorGrid with the same dataset id, the original admissible mask and no field
recording that anything happened -- while every PosteriorGrid-accepting UQ function takes `.posterior`.
"""

from __future__ import annotations

import numpy as np
import pytest

import tests.test_k31_predictive_admission as K
from engcore import uq as UQ
from engcore.uq import UQProblemError, condition_posterior_on_predictive_admission
from engcore.uq.admission import ConditionedPosterior, PredictiveAdmissionAudit


def _symbol(name):
    assert hasattr(UQ, name) or hasattr(UQ.admission, name), (
        f"engcore.uq has no {name!r}; it is preregistered in BATCH44_THRESHOLD_PROTOCOL.json"
    )
    return getattr(UQ, name, None) or getattr(UQ.admission, name)


def _tail_heavy():
    """The audited shape: almost all the mass sits on the node predictive admission rejects."""
    return K._posterior((3.0e-6 / 2.0, 3.0e-6 / 2.0, 1.0 - 3.0e-6), dataset_id="fit-data-v1")


# ---------------------------------------------------------------------------
# a_budget_is_a_bound_and_the_core_has_a_maximum
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-59: there is no maximum at all -- any finite non-negative budget is accepted")
def test_r59_the_core_declares_a_maximum_budget():
    maximum = _symbol("MAXIMUM_CONDITIONED_UNSUPPORTED_MASS")
    assert maximum == 0.05, maximum


@pytest.mark.xfail(strict=True, reason="R-59 as audited: budget 1.0 is accepted and 99.9997% of the posterior is conditioned away, renormalized by 3.4e5")
def test_r59_a_budget_that_would_condition_most_of_the_posterior_away_is_refused():
    """As audited: budget 1.0 accepted, 99.9997% of the mass discarded, factor 3.4e5."""
    with pytest.raises(UQProblemError, match="0.05|maximum"):
        condition_posterior_on_predictive_admission(
            _tail_heavy(), K._table(), maximum_unsupported_mass=1.0)


@pytest.mark.xfail(strict=True, reason="R-59 as audited: budget 5.0 is accepted too")
def test_r59_a_budget_above_one_is_refused_too():
    with pytest.raises(UQProblemError, match="0.05|maximum"):
        condition_posterior_on_predictive_admission(
            _tail_heavy(), K._table(), maximum_unsupported_mass=5.0)


@pytest.mark.xfail(strict=True, reason="R-59: PredictiveAdmissionAudit rejects only negative budgets")
def test_r59_the_audit_record_refuses_the_same_budget():
    with pytest.raises(UQProblemError, match="0.05|maximum"):
        PredictiveAdmissionAudit(
            posterior_dataset_id="p", maximum_unsupported_mass=1.0, supported_mass=1.0,
            unsupported_mass=0.0, conditioning_factor=1.0, rejected_point_count=0,
            rejected_point_indices=(), positive_weight_rejected_point_count=0,
            positive_weight_rejected_point_indices=(), rejection_reasons=(),
            conditional_on_predictive_admission=False)


def test_r59_a_budget_inside_the_maximum_still_works():
    """The control, and the budget both in-repo callers declare, twelve orders below the cap."""
    result = condition_posterior_on_predictive_admission(
        K._posterior((0.7, 0.3, 0.0)), K._table(), maximum_unsupported_mass=1.0e-12)
    assert result.audit.unsupported_mass == 0.0 and result.posterior.weights[0] == 0.7


# ---------------------------------------------------------------------------
# a_conditioned_posterior_says_it_is_conditioned
# ---------------------------------------------------------------------------
def _conditioned():
    """A real conditioning inside the cap: 1% of the mass on the rejected node."""
    posterior = K._posterior((0.69, 0.30, 0.01), dataset_id="fit-data-v1")
    return posterior, condition_posterior_on_predictive_admission(
        posterior, K._table(), maximum_unsupported_mass=0.05)


@pytest.mark.xfail(strict=True, reason="R-59 as audited: the conditioned grid reuses the original dataset_id, so nothing downstream can tell")
def test_r59_a_conditioned_posterior_does_not_claim_the_datasets_identity():
    posterior, result = _conditioned()
    assert result.audit.conditional_on_predictive_admission is True
    assert result.posterior.dataset_id != posterior.dataset_id, (
        "the conditioned posterior is indistinguishable from the unconditioned fit to the same dataset")
    assert result.posterior.dataset_id.startswith(f"{posterior.dataset_id}|predictive-admitted:")


@pytest.mark.xfail(strict=True, reason="R-59 as audited: the conditioned grid keeps the original admissible_mask, so the summary reports admissible_fraction 1.0")
def test_r59_the_conditioned_mask_no_longer_claims_the_rejected_node():
    posterior, result = _conditioned()
    assert tuple(bool(v) for v in posterior.admissible_mask) == (True, True, True)
    assert tuple(bool(v) for v in result.posterior.admissible_mask) == (True, True, False), (
        "the summary still reports full admissibility over a node the conditioning removed")


def test_r59_the_conditioning_is_deterministic():
    _, first = _conditioned()
    _, second = _conditioned()
    assert first.posterior.dataset_id == second.posterior.dataset_id


def test_r59_the_weights_are_still_the_conditioned_weights():
    """The control: the marking does not change the numbers the conditioning produces."""
    posterior, result = _conditioned()
    weights = np.asarray(result.posterior.weights, dtype=float)
    assert weights[2] == 0.0
    assert weights[0] == pytest.approx(0.69 / 0.99, rel=1e-12)
    assert result.audit.conditioning_factor == pytest.approx(1.0 / 0.99, rel=1e-12)


# ---------------------------------------------------------------------------
# the_audit_is_bound_to_the_weights_it_describes
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-59 as audited: the audit is a separate object bound to the posterior by no digest")
def test_r59_the_audit_carries_the_digest_of_the_weights_it_describes():
    _, result = _conditioned()
    assert getattr(result.audit, "conditioned_weights_digest", ""), (
        "the audit is bound to the posterior it describes by nothing at all")


@pytest.mark.xfail(strict=True, reason="R-59: nothing stops an audit describing one conditioning travelling beside another posterior")
def test_r59_an_audit_cannot_be_recombined_with_another_posterior():
    posterior, result = _conditioned()
    other = K._posterior((0.5, 0.5, 0.0), dataset_id=result.posterior.dataset_id)
    with pytest.raises(UQProblemError, match="digest|weights"):
        ConditionedPosterior(posterior=other, audit=result.audit)


def test_r59_an_unconditioned_pair_is_still_a_valid_pair():
    """The control: the pass-through case carries no digest and is accepted."""
    result = condition_posterior_on_predictive_admission(
        K._posterior((0.7, 0.3, 0.0)), K._table(), maximum_unsupported_mass=1.0e-12)
    assert ConditionedPosterior(posterior=result.posterior, audit=result.audit) is not None
    assert getattr(result.audit, "conditioned_weights_digest", "") == ""
