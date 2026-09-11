"""Standing guards over this round's measured claims.

Most pin published numbers against the artifacts they came from. The rest are
live: they re-derive the finding from the measurement, so that if anyone later
adds the applicability condition MVF-2 asks for, the measurement it has to
respect is written down here and not only in prose.

The expensive rebuild runs the whole round, ngspice-free but with the full
1051-point table and thirty discharge curves.
"""

import json
import pathlib
import sys

import pytest

ROUND = pathlib.Path(__file__).resolve().parent.parent

# Appended, never inserted: this directory contains a `tests` directory of its
# own, and putting it at the front of sys.path shadows the repository's own
# `tests` namespace package for every other suite in the session. Done here
# rather than in a conftest.py, because a conftest here would be imported as a
# top-level module named `conftest`, which an earlier round's conftest already
# claims and which repository suites import from.
if str(ROUND) not in sys.path:
    sys.path.append(str(ROUND))


def _artifact(name):
    return json.loads((ROUND / name).read_text(encoding="utf-8"))


# =====================================================================
# The surface and the accounting
# =====================================================================

SHIPPED = {
    "thermal.lumped.first_order_capacity",
    "thermal.conduction1d.linear_diffusion",
    "battery.cell.rint_ocv",
    "battery.cell.coulomb_counting",
    "battery.cell.constant_current_runtime",
    "battery.cell.peukert_capacity_derating",
    "electrical.dc.kcl",
    "electrical.dc.resistor_ohm",
    "electrical.dc.ideal_voltage_source",
    "electrical.dc.ideal_current_source",
    "electrical.dc.regulated_voltage_source",
    "electrical.dc.self_heated_resistor",
    "electrical.material.linear_tcr_resistance",
    "electrical.material.rated_linear_tcr_resistance",
    "kinetics.cstr.nonisothermal_first_order",
    "kinetics.cstr.nonisothermal_first_order_constant_rate",
}


def test_every_shipped_model_is_on_the_evidence_surface():
    surface = _artifact("MODEL_EVIDENCE_SURFACE.json")
    assert {m["model_id"] for m in surface["models"]} == SHIPPED


def test_every_shipped_model_is_accounted_for_at_the_end():
    accounting = _artifact("MODEL_ACCOUNTING.json")
    assert set(accounting["models"]) == SHIPPED


def test_no_model_is_claimed_empirically_validated_without_an_external_source():
    accounting = _artifact("MODEL_ACCOUNTING.json")
    surface = {m["model_id"]: m for m in _artifact("MODEL_EVIDENCE_SURFACE.json")["models"]}
    for model_id, entry in accounting["models"].items():
        if entry["verdict"] in ("EMPIRICALLY_VALIDATED_WITHIN_SCOPE", "EMPIRICAL_PARTIAL"):
            assert surface[model_id]["empirical_validation_possible"] in ("YES", "PARTIAL"), model_id


def test_most_of_the_surface_has_no_empirical_evidence_and_says_so():
    """A round that had drifted into claiming broad coverage would fail here."""
    accounting = _artifact("MODEL_ACCOUNTING.json")
    counts = accounting["counts"]
    assert counts.get("EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", 0) >= 7
    assert counts.get("EMPIRICALLY_VALIDATED_WITHIN_SCOPE", 0) == 0
    assert sum(counts.values()) == 16


# =====================================================================
# Provenance
# =====================================================================


def test_every_used_source_has_provenance_and_a_hash():
    provenance = _artifact("EVIDENCE_PROVENANCE.json")
    results = _artifact("VALIDATION_RESULTS.json")
    declared = {s["source_id"] for s in provenance["sources_accepted"]}
    used = {
        row["source_id"]
        for case in results["cases"].values()
        for row in case["rows"]
    }
    assert used <= declared
    for source in provenance["sources_accepted"]:
        if source["source_id"] in used:
            assert source.get("sha256")
            assert source.get("evidence_level")
            assert source.get("url") or source.get("local_filename")


def test_the_local_evidence_files_still_hash_to_what_was_recorded():
    import hashlib

    provenance = _artifact("EVIDENCE_PROVENANCE.json")
    recorded = {
        pathlib.Path(s["local_filename"]).name: s["sha256"]
        for s in provenance["sources_accepted"]
        if s.get("local_filename")
    }
    for path in (ROUND / "evidence").iterdir():
        if path.name in recorded:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == recorded[path.name], path.name


def test_rejected_sources_carry_a_reason():
    provenance = _artifact("EVIDENCE_PROVENANCE.json")
    assert len(provenance["sources_searched_and_rejected"]) >= 5
    for entry in provenance["sources_searched_and_rejected"]:
        assert entry["rejected_because"]
        assert entry["would_have_covered"]


def test_no_level_4_or_5_source_is_counted_as_empirical():
    provenance = _artifact("EVIDENCE_PROVENANCE.json")
    for source in provenance["sources_accepted"]:
        assert source["evidence_level"] in ("LEVEL 1", "LEVEL 2", "LEVEL 3")
    rejected = " ".join(
        e["source"] + e["rejected_because"]
        for e in provenance["sources_searched_and_rejected"]
    )
    assert "ngspice" in rejected


# =====================================================================
# Calibration independence and uncertainty
# =====================================================================


def test_no_calibration_leakage():
    results = _artifact("VALIDATION_RESULTS.json")
    leakage = next(
        c for c in results["integrity"]["checks"] if c["check"] == "calibration leakage"
    )
    assert leakage["passed"], leakage["offenders"]


def test_no_comparison_is_scored_against_a_zero_uncertainty():
    results = _artifact("VALIDATION_RESULTS.json")
    check = next(
        c for c in results["integrity"]["checks"]
        if c["check"].startswith("measurement uncertainty")
    )
    assert check["passed"], check["offenders"]


def test_relaxed_values_come_from_the_end_of_their_traces():
    results = _artifact("VALIDATION_RESULTS.json")
    check = next(
        c for c in results["integrity"]["checks"]
        if c["check"].startswith("relaxed values")
    )
    assert check["passed"], check["offenders"]


def test_calibration_rows_carry_no_verdict():
    results = _artifact("VALIDATION_RESULTS.json")
    for case in results["cases"].values():
        for row in case["rows"]:
            if row["split"] == "CALIBRATION":
                assert row.get("within_tolerance") is None, row["inputs"]


# =====================================================================
# The findings themselves, re-derived from the measurement
# =====================================================================


def _round_audit():
    """This round's audit package, addressed unambiguously.

    Not ``from audit import ...``. Two rounds ship a top-level package by that
    name, both directories are on sys.path once the whole benchmarks tree is
    collected in one session, and the bare name resolves to whichever was
    imported first -- which is the other round's, alphabetically. The
    fully-qualified path cannot be captured, and the assertion below refuses to
    proceed if it somehow is.
    """
    from benchmarks.model_measurement_validation import audit

    assert pathlib.Path(audit.__file__).resolve().parent.parent == ROUND, (
        f"loaded the wrong round's audit package: {audit.__file__}"
    )
    return audit


def test_the_audit_package_resolves_to_this_round():
    """Guards the import hazard itself, so it cannot come back unnoticed."""
    _round_audit()


def test_the_affine_chord_misses_measured_open_circuit_voltage():
    """The MVF-1 measurement, recomputed rather than read off a file.

    If an applicability condition is ever added for the chord, this is the
    number it has to respect: a LiFePO4 cell whose measured open-circuit
    voltage departs from its own chord by more than a quarter of a volt.
    """
    audit = _round_audit()
    production, validation = audit.production, audit.validation

    charge = validation.E.relaxation_traces("24h_Charge_APR")
    discharge = validation.E.relaxation_traces("24h_Discharge_APR")
    cell = production.cell_with_chord(
        ocv_full_v=charge[1.0]["relaxed_voltage_v"],
        ocv_empty_v=discharge[0.0]["relaxed_voltage_v"],
        capacity_mah=1100.0, resistance_mohm=12.6,
    )
    worst = max(
        abs(production.open_circuit_voltage(cell, soc) - charge[soc]["relaxed_voltage_v"])
        for soc in charge if soc not in (1.0,)
    )
    assert worst > 0.25, f"worst chord residual {worst:.4f} V"


def test_the_declared_curve_route_reproduces_held_out_measurement():
    """MVF-1's qualification: the model family is not the problem."""
    results = _artifact("VALIDATION_RESULTS.json")
    held = [r for r in results["cases"]["MV-B"]["rows"] if r["split"] == "HELD_OUT"]
    assert len(held) == 2
    assert all(r["within_tolerance"] for r in held)
    assert max(abs(r["residual_v"]) for r in held) < 0.02


def test_the_platinum_transcription_corroborates_the_recited_coefficients():
    results = _artifact("VALIDATION_RESULTS.json")
    corroboration = results["cases"]["MV-C"]["table_corroboration"]
    assert corroboration["verdict"] == "TRANSCRIPTION_CORROBORATES_THE_RECITED_COEFFICIENTS"
    agreement = corroboration["coefficient_agreement"]
    assert agreement["relative_difference_A"] < 1e-4
    assert agreement["relative_difference_B"] < 1e-4


def test_the_linear_law_residual_is_the_omitted_quadratic_term():
    """The strongest positive result in the round, to four significant figures."""
    shapes = _artifact("RESIDUAL_ANALYSIS.json")["analyses"]
    curvature = shapes["MV-C"]["curvature_coefficient"]
    predicted = 5.775e-7 * 100.0
    assert abs(curvature - predicted) / predicted < 3e-4


def test_the_discharge_curves_bound_the_chord_error_independently():
    results = _artifact("VALIDATION_RESULTS.json")
    summary = results["cases"]["MV-D"]["summary"]
    assert summary["n_curves"] == 30
    assert summary["min_rms_departure_v"] > 0.05
    assert summary["all_exceed_measurement_uncertainty"]


def test_three_battery_models_are_insufficient_not_failing():
    accounting = _artifact("MODEL_ACCOUNTING.json")["models"]
    for model_id in ("battery.cell.coulomb_counting",
                     "battery.cell.constant_current_runtime",
                     "battery.cell.peukert_capacity_derating"):
        assert accounting[model_id]["verdict"] == "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED"


# =====================================================================
# Falsification and gates
# =====================================================================


def test_every_planted_failure_was_caught():
    plants = _artifact("FALSIFICATION.json")
    assert plants["missed"] == 0
    assert plants["caught"] == 8


@pytest.mark.parametrize("index", range(8))
def test_each_plant_individually(index):
    plants = _artifact("FALSIFICATION.json")["plants"]
    assert plants[index]["verdict"] == "CAUGHT", plants[index]["plant"]


def test_the_structural_plants_are_invisible_to_residuals():
    """MVM-5, 7 and 8 change no number; if a residual caught them the plant was wrong."""
    plants = {p["id"]: p for p in _artifact("FALSIFICATION.json")["plants"]}
    for identifier in ("MVM-5", "MVM-8"):
        plant = plants[identifier]
        assert plant["rows_failing_tolerance"] <= plant["baseline_rows_failing_tolerance"]
        assert plant["integrity_offences"] > plant["baseline_integrity_offences"]


def test_the_gates_report_the_failure_rather_than_arguing_it_away():
    gates = _artifact("SAFETY_GATES.json")
    by_id = {g["id"]: g for g in gates["gates"]}
    assert by_id["MV-7"]["verdict"] == "FAIL"
    assert gates["passed"] == 10
    assert gates["failed"] == 1


def test_the_core_was_not_touched():
    gates = {g["id"]: g for g in _artifact("SAFETY_GATES.json")["gates"]}
    evidence = gates["MV-10"]["evidence"]
    assert evidence["matches"]
    assert evidence["files_touched_under_src_or_tests"] == []
    assert evidence["production_changes_made"] == 0


def test_earlier_rounds_are_untouched():
    gates = {g["id"]: g for g in _artifact("SAFETY_GATES.json")["gates"]}
    assert gates["MV-11"]["evidence"]["modified"] == []


# =====================================================================
# The report
# =====================================================================


def test_the_report_and_the_artifacts_agree():
    audit = _artifact("CONSISTENCY_AUDIT.json")
    assert audit["verdict"] == "CONSISTENT"
    assert audit["inconsistencies"] == 0
    assert audit["forbidden_reasoning_found"] == []


def test_the_consistency_checker_can_fail():
    audit = _artifact("CONSISTENCY_AUDIT.json")
    assert audit["checker_self_falsification"]["verdict"] == "CHECKER_CAN_FAIL"


@pytest.mark.expensive
def test_rebuilding_everything_reproduces_the_published_gates():
    payload = _round_audit().build_gates.build()
    assert payload["passed"] == 10
    assert payload["failed"] == 1
    assert payload["_built"]["plants"]["missed"] == 0
