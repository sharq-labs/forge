"""FLAGSHIP D gates: real Cantera (GRI-Mech 3.0 bytes) + TESPy through the BIG 12 runtime (WSL `sci` env)."""

from __future__ import annotations

import pytest

from engcore.engineering import LevelStatus, committed_artifacts, verify_bundle, write_bundle
from engcore.system_runtime import Availability, NodeStatus, RunStatus, compare_runs, trace_result

try:
    from engcore.providers import default_registry
    REG = default_registry()
    OK = all(REG.status(p).available for p in ("cantera", "tespy"))
except Exception:  # pragma: no cover
    OK = False
pytestmark = pytest.mark.skipif(not OK, reason="Cantera and TESPy are both required")

if OK:
    from forge_flagships import chem_thermal as ct


@pytest.fixture(scope="module")
def run():
    return ct.run_chemistry(REG)


def v(run, node, name):
    o = run.result.observable(f"{node}__{name}")
    assert o.availability is Availability.AVAILABLE, (node, name, o.reason)
    return o.value.value.magnitude


def test_gate_d_real_cantera_and_tespy_execute_and_the_numbers_are_chemically_sensible(run):
    assert run.result.status is RunStatus.SUCCEEDED
    assert {p.provider_id for p in run.result.provider_records} == {"cantera", "tespy"}
    assert 2200 < v(run, "adiabatic_equilibrium", "T_adiabatic") < 2250                # stoichiometric CH4/air, 300 K, 1 atm (~2225 K)
    assert v(run, "adiabatic_equilibrium", "X_H2O") > v(run, "adiabatic_equilibrium", "X_CO2") > v(run, "adiabatic_equilibrium", "X_CO") > 0
    assert 20e3 < v(run, "heat_duty", "Q_duty") < 35e3                                  # W for 0.01 kg/s of reactants
    assert 300 < v(run, "coolant_loop", "T_water_out") < 353.15 and v(run, "coolant_loop", "water_rise") > 15
    assert all(c.status == "satisfied" for c in run.constraints)


def test_conservation_element_balance_and_the_cross_provider_energy_balance_close(run):
    assert v(run, "adiabatic_equilibrium", "element_residual") < ct.ELEMENT_TOL and v(run, "cooled_equilibrium", "element_residual") < ct.ELEMENT_TOL
    assert abs(v(run, "energy_balance", "relative_residual")) < ct.ENERGY_BALANCE_REL_TOL
    assert run.ladder.entry(2).status is LevelStatus.REACHED


def test_reference_and_equilibrium_limits_and_the_reference_is_classified_analytic_not_experimental(run):
    assert abs(v(run, "heat_of_combustion", "lower_heating_value") - 802.31) < ct.LHV_TOL_KJ_PER_MOL
    assert v(run, "equilibrium_approach", "relative_gap") < ct.EQUILIBRIUM_APPROACH_REL
    l3 = run.ladder.entry(3)
    assert l3.status is LevelStatus.REACHED
    ref = run.references[0]
    assert ref.kind.value == "analytic_reference" and len(ref.source_digest) == 64 and ref.access_url.startswith("https://webbook.nist.gov/")
    assert run.comparisons[0].classification == "reference_data_consistency_check_not_validation"        # data consistency, classified apart from an implementation limit
    assert v(run, "heat_of_combustion", "temperature_offset_bound") < ct.LHV_TOL_KJ_PER_MOL / 5              # the 300 K vs 298.15 K offset is bounded and small against the tolerance
    assert run.result.receipt("heat_of_combustion").applicability[0].check_id == "thermo_range" and run.result.receipt("heat_of_combustion").applicability[0].status == "within"


def test_the_predeclared_integrator_criterion_is_not_met_and_the_post_hoc_reading_is_labelled(run):
    """Negative result kept: the discrete ignition time has a sampling spacing larger than the 1 % criterion."""
    l4 = run.ladder.entry(4)
    assert l4.status is LevelStatus.ATTEMPTED_NOT_REACHED
    assert v(run, "integrator_study", "ignition_relative_change") > ct.INTEGRATOR_IGNITION_REL
    assert v(run, "integrator_study", "ignition_relative_change_refined_post_hoc") < ct.INTEGRATOR_IGNITION_REL
    assert v(run, "integrator_study", "final_temperature_change") < ct.INTEGRATOR_T_ABS_K
    assert {e.classification for e in l4.evidence} == {"discretisation_convergence", "post_hoc_discretisation_convergence"}


def test_no_false_validation_and_the_scientific_status_is_the_existing_authoritys(run):
    assert run.summary.scientific_status == "insufficient_evidence"
    assert run.ladder.reference_level_reached == "none"
    for level in (5, 6, 7):
        assert run.ladder.entry(level).status is LevelStatus.NOT_AVAILABLE
    assert "NOT established by Forge" in run.summary.uncertainty.model_applicability


def test_result_trace_reaches_the_provider_executions_for_the_headline_number(run):
    trace = trace_result(run.result, "coolant_loop__T_water_out")
    assert trace.complete, trace.gaps
    assert {"provider", "provider_execution", "node", "system", "scenario"} <= set(trace.levels())


def test_negative_controls_an_unknown_species_and_an_out_of_range_state_fail_closed():
    out = ct.negative_controls(REG)
    ms = out["missing_species"]["nodes"]
    assert ms["adiabatic_equilibrium"][0] == "failed" and "not defined by the mechanism" in ms["adiabatic_equilibrium"][1]
    assert ms["coolant_loop"][0] == "blocked" and ms["heat_duty"][0] == "blocked"
    br = out["below_thermo_range"]["nodes"]
    assert br["cooled_equilibrium"][0] == "refused" and "thermo_range" in br["cooled_equilibrium"][1]
    assert br["coolant_loop"][0] == "blocked"


def test_gate_f_a_fresh_runtime_reproduces_the_run_and_the_bundle_verifies(run, tmp_path):
    again = ct.run_chemistry(REG)
    assert again.result.request_digest == run.result.request_digest
    cmp_ = compare_runs(run.result, again.result, rel_tol=1e-12)
    assert cmp_.identity_replay and cmp_.numerical_reproducibility
    d = str(tmp_path / "b")
    manifest = write_bundle(d, name="d", request=run.chemistry.request, result=run.result, summary=run.summary, references=list(run.references), artifacts=committed_artifacts(run.result, run.chemistry.exchange.files))
    assert verify_bundle(d).digest == manifest.digest
