"""CORE-8: uncertainty transport and closure, Core -> SRIA -> claim, without invention.

These tests are about the *report's own* uncertainty record, so they wrap the real
NAFEMS T3 run and replace only that record -- the run, its checks, its levels and
its binding stay the genuine ones -- and they strip T3's declared refinement study
(Phase 2), whose own NUMERICAL record would otherwise meet the injected one in the
same channel (a conflict the bridge refuses; see test_phase2_production_uq.py).
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from claims_support import t3_claim
from engcore.claims import (
    CapabilityRegistry,
    CapabilityRun,
    InstanceReport,
    TransportState,
    UncertaintyCapability,
    UncertaintyDemand,
    UncertaintyTransportError,
    assess_claim,
    classify_record,
    transport,
    verify_assessment,
)
from engcore.mcp import example_electrothermal_payload, run_electrothermal_case
from engcore.mcp.capabilities import NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.mcp.sria_bridge import evidence_from_credibility_report
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel

K = "kelvin"
QOI = "temperature_at_probe"


def _std(u: float, source: UncertaintySource) -> Uncertainty:
    return Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(u, K), method="study", source_kind=source)


def _interval(lo: float, hi: float, source: UncertaintySource) -> Uncertainty:
    return Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(lo, K), upper=Quantity(hi, K), method="posterior", source_kind=source)


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _with_uncertainty(registry, record: Uncertainty) -> CapabilityRegistry:
    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor

    def run(case, *, run_id):
        (item,) = genuine(case, run_id=run_id).reports
        return CapabilityRun(reports=(InstanceReport(None, replace(item.report, uncertainty={QOI: record})),))

    stripped = UncertaintyCapability(quantified={}, basis="stripped: the report's own record is the only one under test")
    return CapabilityRegistry(
        replace(d, executor=run, refinement=None, uncertainty=stripped) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d
        for d in registry
    )


def _demand(*channels, k=2.0):
    return UncertaintyDemand(frozenset(channels), k, False)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "record, state, channel",
    [
        (Uncertainty.unknown(), TransportState.UNKNOWN, None),
        (_std(1.0, UncertaintySource.NUMERICAL), TransportState.ATTRIBUTED, UncertaintyChannel.NUMERICAL),
        (_std(1.0, UncertaintySource.PARAMETER), TransportState.ATTRIBUTED, UncertaintyChannel.EPISTEMIC_PARAMETER),
        (_std(1.0, UncertaintySource.MEASUREMENT), TransportState.ATTRIBUTED, UncertaintyChannel.ALEATORIC),
        (_std(1.0, UncertaintySource.MODEL_FORM), TransportState.ATTRIBUTED, UncertaintyChannel.MODEL_FORM),
        (_std(1.0, UncertaintySource.UNSPECIFIED), TransportState.UNATTRIBUTED, None),
        (_std(1.0, UncertaintySource.COMBINED), TransportState.MIXTURE, None),
    ],
    ids=["unknown", "numerical", "parameter", "measurement", "model_form", "unspecified", "combined"],
)
def test_every_record_lands_in_exactly_one_state_and_at_most_one_channel(record, state, channel) -> None:
    classified = classify_record("q", record)
    assert classified.state is state and classified.channel is channel


def test_a_predictive_result_files_its_epistemic_part_and_lists_its_total_as_a_mixture() -> None:
    moved = transport({"epistemic": _interval(1.0, 3.0, UncertaintySource.PARAMETER), "total": _interval(0.0, 4.0, UncertaintySource.COMBINED)})
    assert set(moved.channels) == {UncertaintyChannel.EPISTEMIC_PARAMETER}
    assert [(r.name, r.state) for r in moved.excluded] == [("total", TransportState.MIXTURE)]
    assert moved.to_dict()["channels"]["model_form"] == "unknown"


def test_two_different_records_for_one_channel_are_refused_not_averaged() -> None:
    with pytest.raises(UncertaintyTransportError):
        transport({"a": _std(1.0, UncertaintySource.NUMERICAL), "b": _std(2.0, UncertaintySource.NUMERICAL)})


# ---------------------------------------------------------------------------
# The bridge keeps its refusal by default and never guesses a channel
# ---------------------------------------------------------------------------


def test_the_bridge_still_refuses_an_unattributable_record_by_default_and_files_none_on_request() -> None:
    report = run_electrothermal_case(example_electrothermal_payload()).reports[0]
    name = "final_temperature"
    for source in (UncertaintySource.COMBINED, UncertaintySource.UNSPECIFIED):
        quantified = replace(report, uncertainty={**report.uncertainty, name: _std(0.5, source)})
        with pytest.raises(ValueError):
            evidence_from_credibility_report(quantified, quantity_name=name, evidence_id="e", domain_pack_ref="p", context_ref="c")
        evidence = evidence_from_credibility_report(
            quantified, quantity_name=name, evidence_id="e", domain_pack_ref="p", context_ref="c", unattributable_uncertainty="unknown"
        )
        assert dict(evidence.uncertainty.channels) == {}
        assert "filed under none" in evidence.uncertainty.notes
    with pytest.raises(ValueError, match="unattributable_uncertainty"):
        evidence_from_credibility_report(report, quantity_name=name, evidence_id="e", domain_pack_ref="p", context_ref="c", unattributable_uncertainty="guess")


# ---------------------------------------------------------------------------
# Closure: claim -> SRIA -> verdict
# ---------------------------------------------------------------------------


def test_a_quantified_attributed_channel_can_support_a_claim_that_demands_it(registry) -> None:
    wrapped = _with_uncertainty(registry, _std(0.01, UncertaintySource.NUMERICAL))
    record = assess_claim(t3_claim(uncertainty=_demand(UncertaintyChannel.NUMERICAL)), wrapped).to_dict()
    assert record["verdict"] == "supported"
    assert record["comparison"]["rule"] == "guard_band_linear_sum"
    assert record["uncertainty"]["channels"] == {"numerical": True}
    assert record["assurance"]["verdict"] == "valid"
    verify_assessment(json.loads(json.dumps(record)), wrapped)


def test_a_band_that_straddles_the_tolerance_edge_decides_nothing(registry) -> None:
    record = assess_claim(t3_claim(uncertainty=_demand(UncertaintyChannel.NUMERICAL)), _with_uncertainty(registry, _std(0.4, UncertaintySource.NUMERICAL))).to_dict()
    assert record["comparison"]["point_satisfied"] is True
    assert record["comparison"]["outcome"] == "undecided"
    assert record["verdict"] == "insufficient_evidence"


@pytest.mark.parametrize(
    "source, state",
    [(UncertaintySource.COMBINED, "mixture"), (UncertaintySource.UNSPECIFIED, "unattributed")],
)
def test_an_unattributable_record_never_enters_a_channel_and_leaves_the_demand_unmet(registry, source, state) -> None:
    record = assess_claim(t3_claim(uncertainty=_demand(UncertaintyChannel.NUMERICAL)), _with_uncertainty(registry, _std(0.01, source))).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["evidence"] is not None  # made, with every channel UNKNOWN, rather than refused
    assert record["uncertainty"]["channels"] == {"numerical": False}
    assert record["uncertainty"]["transport"]["records"][0]["state"] == state
    assert f"uncertainty.{state}" in {i["code"] for i in record["explanation"]}


def test_numerical_uncertainty_cannot_satisfy_a_model_form_demand(registry) -> None:
    record = assess_claim(t3_claim(uncertainty=_demand(UncertaintyChannel.MODEL_FORM)), _with_uncertainty(registry, _std(0.01, UncertaintySource.NUMERICAL))).to_dict()
    assert record["verdict"] == "insufficient_evidence"
    assert record["uncertainty"]["channels"] == {"model_form": False}
    assert "uncertainty:model_form" in record["assurance"]["unmet_obligations"]


def test_unknown_stays_unknown_and_is_shown_when_no_channel_is_demanded(registry) -> None:
    record = assess_claim(t3_claim(), registry).to_dict()
    assert record["verdict"] == "supported"
    assert record["uncertainty"]["transport"]["records"][0]["state"] == "unknown"
    assert set(record["uncertainty"]["transport"]["channels"].values()) == {"unknown"}


def test_losing_a_quantified_record_never_firms_up_the_answer(registry) -> None:
    demand = _demand(UncertaintyChannel.NUMERICAL)
    known = assess_claim(t3_claim(uncertainty=demand), _with_uncertainty(registry, _std(0.01, UncertaintySource.NUMERICAL))).to_dict()
    lost = assess_claim(t3_claim(uncertainty=demand), _with_uncertainty(registry, Uncertainty.unknown("dropped"))).to_dict()
    assert known["verdict"] == "supported" and lost["verdict"] == "insufficient_evidence"
