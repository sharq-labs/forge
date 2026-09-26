"""Portfolio gates that need no provider: reference-data integrity and provenance (Gate I), no custom runtime (Gate J), no false validation (Gate H, guards)."""

from __future__ import annotations

import ast
import hashlib
import json
import os

import pytest

from engcore.scientific.units.quantity import Quantity

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "..", "forge_flagships")
MODULES = ("battery_cooling", "thermo_mechanical", "cavity_cfd", "chem_thermal")


def source(name: str) -> str:
    return open(os.path.join(PKG, f"{name}.py"), "rb").read().decode()


# ------------------------------------------------------------------------------------------------------------------ Gate J
@pytest.mark.parametrize("name", MODULES)
def test_gate_j_every_flagship_enters_through_a_system_run_request_and_the_generic_executor(name):
    src = source(name)
    assert "SystemRunRequest.build(" in src and "SystemExecutor(" in src


@pytest.mark.parametrize("name", MODULES)
def test_gate_j_no_flagship_defines_its_own_runtime_executor_or_scheduler(name):
    tree = ast.parse(source(name))
    banned = ("runtime", "executor", "orchestrator", "scheduler", "workflow")
    defined = [n.name for n in ast.walk(tree) if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and any(b in n.name.lower() for b in banned)]
    # build_multiscale_runtime / Plant.runtime construct the EXISTING BIG 9 / BIG 10 runtimes; they are not runtimes of their own
    assert set(defined) <= {"build_multiscale_runtime", "runtime"}, defined
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
            assert not (bases & {"SystemExecutor", "MultiphysicsRuntime", "MultiTimescaleRuntime"}), (node.name, bases)


# ------------------------------------------------------------------------------------------------------------------ Gate I
def test_ghia_excerpt_is_a_numerical_benchmark_with_a_content_identity_and_matches_an_independent_transcription():
    from forge_flagships.cavity_cfd import load_ghia
    ref, raw = load_ghia()
    assert ref.kind.value == "benchmark_dataset" and ref.kind.value != "experimental_dataset"
    assert "NUMERICAL" in raw["kind_note"] and len(ref.source_digest) == 64 and ref.access_url.startswith("https://")
    # the Re = 100 u column as printed on a SECOND public page (typed here from that page on 2026-09-26; the two transcriptions were made by different people, this test file was typed by us)
    independent_u = [1.0, 0.84123, 0.78871, 0.73722, 0.68717, 0.23151, 0.00332, -0.13641, -0.20581, -0.21090, -0.15662, -0.10150, -0.06434, -0.04775, -0.04192, -0.03717, 0.0]
    independent_v = [0.0, -0.05906, -0.0739, -0.0886, -0.10313, -0.16914, -0.22445, -0.24533, 0.05454, 0.17527, 0.17507, 0.16077, 0.12317, 0.1089, 0.1009, 0.0923, 0.0]
    assert list(ref.values("u")) == pytest.approx(independent_u, abs=1e-12)
    assert list(ref.values("v")) == pytest.approx(independent_v, abs=1e-4)             # the second transcription rounds some entries to 4 digits
    square = {"cavity_aspect_ratio": Quantity(1.0, "dimensionless")}
    assert ref.applicability({"reynolds": Quantity(100.0, "dimensionless"), **square}).status == "within"
    assert ref.applicability({"reynolds": Quantity(100.0, "dimensionless")}).status == "unknown"                    # the cavity shape is an envelope term: not stated, never assumed
    assert ref.applicability({"reynolds": Quantity(10.0, "dimensionless"), **square}).status == "outside"
    assert ref.applicability({"reynolds": Quantity(100.0, "dimensionless"), "cavity_aspect_ratio": Quantity(2.0, "dimensionless")}).status == "outside"
    assert ref.digest == load_ghia()[0].digest                                        # deterministic identity


def test_ghia_excerpt_stores_only_the_re_100_columns():
    d = json.loads(open(os.path.join(PKG, "data", "ghia_1982_re100_excerpt.json"), "rb").read())
    assert len(d["u_vs_y"]) == 17 and len(d["v_vs_x"]) == 17 and d["conditions"]["reynolds"] == 100.0
    assert "NOT copied" in d["license_status"] and "typographical errors in OTHER" in d["transcription_caveat"]


def test_nist_hess_reference_is_analytic_carries_source_digests_and_its_numbers_recompute():
    from forge_flagships.chem_thermal import load_hess
    ref, raw = load_hess()
    assert ref.kind.value == "analytic_reference" and ref.role == "data_consistency" and len(ref.source_digest) == 64 and len(raw["source_page_digests"]) == 3
    v = raw["values_kJ_per_mol"]
    assert -v["dHf_CO2_gas_chase1998"] + -2 * v["dHf_H2O_gas_chase1998"] + v["dHf_CH4_gas_chase1998"] == pytest.approx(-raw["derived_heat_of_combustion_kJ_per_mol"]["chase1998"])
    assert ref.values("lower_heating_value") == pytest.approx((802.31, 802.562), abs=1e-6)
    assert ref.applicability({"temperature": Quantity(298.15, "K"), "pressure": Quantity(101325.0, "Pa")}).status == "within"
    assert ref.applicability({"temperature": Quantity(300.0, "K"), "pressure": Quantity(101325.0, "Pa")}).status == "within"
    assert ref.applicability({"temperature": Quantity(1000.0, "K"), "pressure": Quantity(101325.0, "Pa")}).status == "outside"


def test_the_nasa_battery_reference_is_pinned_by_the_repository_manifest_and_has_no_copied_data():
    from forge_flagships.battery_cooling import nasa_reference
    ref = nasa_reference()
    manifest = json.loads(open(os.path.join(HERE, "..", "..", "benchmarks", "measurements", "nasa_battery_aging", "manifest.json"), "rb").read())
    assert ref.source_digest == manifest["catalog_source_hash"] and ref.kind.value == "experimental_dataset" and ref.data == ()
    assert ref.applicability({}).status == "unknown"                                   # nothing the flagship states puts it inside the envelope


def test_the_analytic_references_of_the_structure_flagship_are_labelled_analytic_and_apply_only_inside_their_envelopes():
    from forge_flagships.thermo_mechanical import analytic_references, ALPHA
    free, constrained, bar = analytic_references()
    for ref in (free, constrained, bar):
        assert ref.kind.value == "analytic_reference"
    conds = {"temperature_rise": Quantity(40.0, "K"), "thermal_strain": Quantity(ALPHA * 40.0, "dimensionless")}
    assert free.applicability(conds).status == "within"
    assert free.applicability({**conds, "temperature_rise": Quantity(1000.0, "K")}).status == "outside"       # outside the small-strain envelope
    assert bar.applicability({"aspect_ratio": Quantity(1.0, "dimensionless"), "section_position": Quantity(0.5, "dimensionless")}).status == "outside"


def test_the_first_law_reference_is_analytic_and_states_it_shares_a_property_backend():
    from forge_flagships.battery_cooling import first_law_reference
    ref = first_law_reference()
    assert ref.kind.value == "analytic_reference" and "verifies the energy-balance implementation" in ref.extraction


# ------------------------------------------------------------------------------------------------------------------ Gate H (guards)
def test_gate_h_a_flagship_result_cannot_be_promoted_by_its_own_ladder():
    from engcore.engineering import EvidenceLink, LevelEntry, LevelStatus
    from engcore.scientific.errors import InvalidScientificProblem
    sha = hashlib.sha256(b"x").hexdigest()
    agreement = EvidenceLink.of_record("provider_comparison", {"classification": "solver_corroboration_not_validation", "within_tolerance": True, "probe": sha},
                                       "solver_corroboration_not_validation", "met")
    benchmark = EvidenceLink.of_record("reference_comparison", {"classification": "numerical_benchmark_comparison_not_validation_grant", "outcome": "met", "probe": sha},
                                       "numerical_benchmark_comparison_not_validation_grant", "met")
    LevelEntry(5, LevelStatus.REACHED, (agreement,))                                                                                      # the links themselves are valid ...
    LevelEntry(6, LevelStatus.REACHED, (benchmark,))
    with pytest.raises(InvalidScientificProblem, match="reference comparison link|numerical-benchmark comparison only"):
        LevelEntry(6, LevelStatus.REACHED, (agreement,))                                                                                  # ... agreement is not a benchmark
    with pytest.raises(InvalidScientificProblem, match="experimental-data comparison only"):
        LevelEntry(7, LevelStatus.REACHED, (benchmark,))                                                                                  # a benchmark is not an experiment


def test_the_numeric_criteria_are_pinned_to_the_preregistration_file_and_recorded_failures_stay_recorded():
    """Review finding M1: editing a criterion constant flips a recorded failure to MET under the same label - so the constants are pinned here, in a reviewable file."""
    from forge_flagships import battery_cooling as bc, cavity_cfd as cf, chem_thermal as ct, thermo_mechanical as tm
    reg = json.loads(open(os.path.join(PKG, "data", "predeclared_criteria.json"), "rb").read())
    live = {
        "battery.HEAT_BALANCE_TOL_WH": bc.HEAT_BALANCE_TOL_WH, "battery.FIRST_LAW_REL_TOL": bc.FIRST_LAW_REL_TOL,
        "battery.REFINEMENT_TOL.peak_cell_temperature_K": bc.REFINEMENT_TOL["peak_cell_temperature"].magnitude,
        "battery.REFINEMENT_TOL.voltage_end_of_discharge_V": bc.REFINEMENT_TOL["voltage_end_of_discharge"].magnitude, "battery.REFINEMENT_PEAK_HEAT_REL": bc.REFINEMENT_PEAK_HEAT_REL,
        "structure.DISP_AGREEMENT_TOL_m": tm.DISP_AGREEMENT_TOL.magnitude, "structure.STRESS_AGREEMENT_TOL_Pa": tm.STRESS_AGREEMENT_TOL.magnitude,
        "structure.BAR_THEORY_REL_TOL": tm.BAR_THEORY_REL_TOL, "structure.ANALYTIC_REL_TOL": tm.ANALYTIC_REL_TOL, "structure.HEAT_BALANCE_REL_TOL": tm.HEAT_BALANCE_REL_TOL,
        "structure.CONVERGENCE_ORDER_MIN": tm.CONVERGENCE_ORDER_MIN, "cavity.WHOLE_FIELD_TOL": cf.WHOLE_FIELD_TOL, "cavity.GHIA_TOL": cf.GHIA_TOL, "cavity.FLUX_TOL": cf.FLUX_TOL,
        "cavity.STEADY_TOL_M_S": cf.STEADY_TOL_M_S, "chemistry.ELEMENT_TOL": ct.ELEMENT_TOL, "chemistry.ENERGY_BALANCE_REL_TOL": ct.ENERGY_BALANCE_REL_TOL,
        "chemistry.LHV_TOL_KJ_PER_MOL": ct.LHV_TOL_KJ_PER_MOL, "chemistry.EQUILIBRIUM_APPROACH_REL": ct.EQUILIBRIUM_APPROACH_REL, "chemistry.INTEGRATOR_IGNITION_REL": ct.INTEGRATOR_IGNITION_REL,
        "chemistry.INTEGRATOR_T_ABS_K": ct.INTEGRATOR_T_ABS_K, "battery.FIRST_LAW_MIN_HEAT_W": bc.FIRST_LAW_MIN_HEAT_W, "cavity.INTRINSIC_ORDER_MIN_post_hoc": cf.INTRINSIC_ORDER_MIN,
        "structure.EQUILIBRIUM_SPREAD_TOL": tm.EQUILIBRIUM_SPREAD_TOL, "structure.FORCE_FLOOR_RATIO": tm.FORCE_FLOOR_RATIO, "structure.NOISE_BAND_REL_post_hoc": tm.NOISE_BAND_REL,
    }
    assert live == reg["criteria"]
    assert set(reg["recorded_outcomes_of_criteria_that_were_not_met_as_written"]) >= {"structure.CONVERGENCE_ORDER_MIN", "cavity.WHOLE_FIELD_TOL", "chemistry.INTEGRATOR_IGNITION_REL", "battery.window_refinement_monotone"}
    assert cf.WHOLE_FIELD_TOL == 0.03                                                # the BIG 11 whole-field criterion, unchanged


@pytest.mark.parametrize("name", MODULES)
def test_every_flagship_builds_level_one_from_the_runs_own_preflight_and_status_and_takes_bundle_files_only_from_succeeded_nodes(name):
    src = source(name)
    assert "contract_integrity_entry(report, result)" in src
    assert "LevelEntry(1, LevelStatus.REACHED" not in src                             # no unconditional level-1 claim


# ------------------------------------------------------------------------------------------------------- committed evidence
DOCS = os.path.join(HERE, "..", "..", "docs", "flagships")
REPORTS = {"battery_normal": "battery_cooling_lifecycle.md", "structure_flagship": "thermo_mechanical_structure.md",
           "cavity_re100": "cavity_cfd_benchmark.md", "chemistry_nominal": "chemical_thermal_system.md"}


@pytest.mark.parametrize("bundle", sorted(REPORTS))
def test_the_committed_run_bundles_verify_and_each_report_was_generated_from_its_own_bundle(bundle):
    """A report that does not name its bundle's request / plan / result digests is stale (review finding M4/M5): the pair is checked together."""
    from engcore.engineering import verify_bundle
    manifest = verify_bundle(os.path.join(DOCS, "runs", bundle))                          # re-hashes every file and re-derives the result
    report = open(os.path.join(DOCS, REPORTS[bundle]), "rb").read().decode("utf-8")
    assert f"`request {manifest.request_digest[:16]}  plan {manifest.plan_digest[:16]}  result {manifest.result_digest[:16]}`" in report
    summary = json.loads(open(os.path.join(DOCS, "runs", bundle, "summary.json"), "rb").read())
    assert summary["scientific_status"] == "insufficient_evidence"


def test_the_committed_hot_case_bundle_verifies_and_reports_its_violated_constraints():
    """The hot case has no report of its own (its numbers are the second column of the battery report); its bundle is still re-verified."""
    from engcore.engineering import verify_bundle
    verify_bundle(os.path.join(DOCS, "runs", "battery_hot"))
    summary = json.loads(open(os.path.join(DOCS, "runs", "battery_hot", "summary.json"), "rb").read())
    assert summary["scientific_status"] == "insufficient_evidence" and any(c["status"] == "violated" for c in summary["constraints"])


def test_the_committed_negative_control_bundles_are_refusals_or_failures_and_carry_no_side_files():
    from engcore.engineering import verify_bundle
    for name in ("battery_overload", "battery_outside_window", "structure_over_range"):
        manifest = verify_bundle(os.path.join(DOCS, "runs", name))
        result = json.loads(open(os.path.join(DOCS, "runs", name, "result.json"), "rb").read())
        assert not any(f.startswith("artifacts/") for f, _ in manifest.files), name       # no refused/failed node's file is bundled
        assert result["status"] == "failed", name                                        # a refused or failed node ends the run as not succeeded
