"""Core re-audit 2026-09-16, batch 41 (hybrid half): a record no reader can interpret is refused for that reason.

Problem R-45 (the audit's finding 90, item 2), improvement I-20 part C of three, under
benchmarks/core_v4_false_confidence/BATCH41_THRESHOLD_PROTOCOL.json. The rest of the batch, which is about
records an older reader silently unbinds, is in tests/test_core_scientific_audit_batch41.py.
"""

from __future__ import annotations

import copy

import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, local_gaussian_posterior
from engcore.hybrid_uq import identifiability as ID
from engcore.hybrid_uq.identifiability import RoutedIdentifiability, assess_routed_identifiability
from engcore.hybrid_uq.vocabulary import HybridUQError


def _report_payload():
    problem = S.affine("B41")
    posterior = local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                         multistart=MultistartPolicy())
    return copy.deepcopy(assess_routed_identifiability(posterior).to_dict())


@pytest.mark.xfail(strict=True, reason="R-45 finding 90 item 2: CORE-004 changed the conditioning definition and the explanation text under the same version")
def test_r45_a_routed_identifiability_record_declares_the_core004_definition():
    assert ID.ROUTED_IDENTIFIABILITY_SCHEMA == "hybrid_uq.routed_identifiability/2", (
        "CORE-004 changed both the conditioning definition and the explanation text under the same version")


def test_r45_a_current_record_still_round_trips():
    payload = _report_payload()
    assert RoutedIdentifiability.from_dict(payload).to_dict() == payload


@pytest.mark.xfail(strict=True, reason="R-45: the refusal reports that a verdict does not follow from numbers that give the same verdict")
def test_r45_a_pre_core004_record_is_refused_for_the_reason_it_cannot_be_read():
    """The audited message named a contradiction where the only visible difference was a sentence of prose.

    The refusal is right -- a `/1` record stores a condition number computed under the definition CORE-004
    retired, and no reader can tell which definition a stored number used -- so what this fixes is the reason.
    """
    payload = _report_payload()
    payload["schema"] = "hybrid_uq.routed_identifiability/1"
    with pytest.raises(HybridUQError) as raised:
        RoutedIdentifiability.from_dict(payload)
    message = str(raised.value)
    assert "routed_identifiability/1" in message, message
    assert "CORE-004" in message or "conditioning" in message, (
        f"the refusal does not say why a /1 record cannot be interpreted: {message}")
    assert "do not follow from its own numbers" not in message, (
        "the message still reports a contradiction where the record is simply unreadable")
