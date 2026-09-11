"""MV-18/MV-19/MV-24: what each disagreement is, and where every model lands.

Every mismatch gets exactly one class. The classes are not merged, and a
disagreement is not called a model failure until the alternatives in MV-18 have
been ruled out in writing.
"""

from __future__ import annotations

CLASSES = [
    "MODEL_EMPIRICAL_MISMATCH",
    "PARAMETERIZATION_DEFECT",
    "UNIT_SCALE_DEFECT",
    "BOUNDARY_INITIAL_CONDITION_DEFECT",
    "DATASET_INTERPRETATION_DEFECT",
    "REFERENCE_DATA_DEFECT",
    "TOLERANCE_METRIC_DEFECT",
    "CALIBRATION_LEAKAGE",
    "OUT_OF_SCOPE_REFERENCE",
    "EMPIRICAL_EVIDENCE_INSUFFICIENT",
    "AUDIT_DEFECT",
    "NEEDS_DOMAIN_DECISION",
]


def findings(results, residuals) -> list[dict]:
    a = results["MV-A"]["summary"]
    replicate = results["MV-A-replicate"]["summary"]
    b = results["MV-B"]["summary"]
    c = results["MV-C"]
    d = results["MV-D"]["summary"]
    corroboration = c["table_corroboration"]

    return [
        {
            "id": "MVF-1",
            "class": "MODEL_EMPIRICAL_MISMATCH",
            "model": "battery.cell.rint_ocv",
            "configuration": "affine chord between two declared endpoints",
            "severity": "HIGH",
            "statement": (
                "Against measured relaxed open-circuit voltage on a LiFePO4 "
                "cell, the affine chord misses every held-out state of charge. "
                f"Mean absolute error {a['mean_absolute_error_v'] * 1e3:.0f} mV, "
                f"worst {a['max_absolute_error_v'] * 1e3:.0f} mV, against a "
                "measurement uncertainty of a few millivolts. The worst "
                f"residual is {a['worst_residual_in_units_of_its_own_uncertainty']:.0f} "
                "times its own expanded uncertainty."
            ),
            "mv18_alternatives_ruled_out": {
                "unit or scale error": (
                    "ruled out. The residual is exactly zero at 100% state of "
                    "charge and grows smoothly towards the bottom of the range. "
                    "A scale error moves every point together."
                ),
                "wrong parameter": (
                    "ruled out, and by two independent arguments. The chord has "
                    "exactly two parameters and both were taken from the "
                    "measurement itself, so there was nothing left to get "
                    "wrong. Independently, MV-D shows that the BEST straight "
                    "line through each of thirty measured constant-current "
                    f"discharges still departs from it by {d['min_rms_departure_v'] * 1e3:.0f} "
                    f"to {d['max_rms_departure_v'] * 1e3:.0f} mV RMS, which "
                    "bounds below what any choice of endpoints, capacity, "
                    "efficiency or resistance could achieve."
                ),
                "initial or boundary condition": (
                    "not applicable. An open-circuit measurement at rest has "
                    "neither."
                ),
                "dataset interpretation": (
                    "ruled out. The state of charge is set by the experiment's "
                    "own conditioning procedure and the open-circuit voltage is "
                    "the relaxed value at the declared 24 h, which the "
                    "integrity check pins."
                ),
                "measurement uncertainty": (
                    "ruled out. The budget is assembled from the instruments "
                    "the dataset publishes and reaches a few millivolts; the "
                    "residual is two orders of magnitude larger."
                ),
                "numerical error": (
                    "not applicable. The chord is one algebraic expression."
                ),
            },
            "second_independent_source": (
                "MV-D, thirty constant-current discharges of ten different "
                "cells under load, from a different dataset with its own DOI. "
                "MV-20 asks for a second line of evidence before a HIGH "
                "severity finding is confirmed; this is it, and it agrees."
            ),
            "replicated_on_a_second_cell": (
                f"BATT_002 (BSE, 1500 mAh): mean absolute error "
                f"{replicate['mean_absolute_error_v'] * 1e3:.0f} mV, worst "
                f"{replicate['max_absolute_error_v'] * 1e3:.0f} mV, "
                f"{replicate['worst_residual_in_units_of_its_own_uncertainty']:.0f} "
                "times its own uncertainty."
            ),
            "residual_shape": (
                "Systematic. Every residual carries the same sign and the "
                "magnitude falls monotonically from the bottom of the range to "
                "the top. This is structure, not scatter."
            ),
            "is_the_model_family_inadequate": (
                "No, and this is the finding's most important qualification. "
                "The record's own text says the chord governs 'unless the cell "
                "declares a curve for it, in which case the curve governs'. "
                "MV-B exercises that route on the same cell and passes. The "
                "model family is adequate; its DEFAULT configuration is not "
                "adequate for this chemistry."
            ),
            "production_change_made": "none",
            "why_no_production_change": (
                "MV-22: the defect is neither a parameterisation nor a "
                "construction fault, and the model family is not inadequate. "
                "What the measurement exposes is a missing applicability "
                "condition, which is a domain decision and is raised as MVF-2 "
                "rather than legislated here."
            ),
        },
        {
            "id": "MVF-2",
            "class": "NEEDS_DOMAIN_DECISION",
            "model": "battery.cell.rint_ocv",
            "severity": "MEDIUM",
            "statement": (
                "Nothing in the model's validity domain bears on whether the "
                "affine chord describes the cell. Its eleven conditions cover "
                "C-rate, state-of-charge window, temperature, resistance "
                "drift, self-heating, polarization and terminal voltage. A "
                "caller may declare a chord for a cell whose open-circuit "
                "curve departs from it by 293 mV and receive no signal at all."
            ),
            "what_the_evidence_supports": (
                "That such a condition would have something to act on: the "
                "departure is measurable, is an order of magnitude outside "
                "measurement uncertainty, and replicates across cells and "
                "across two independent experiments."
            ),
            "what_the_evidence_does_not_settle": (
                "What the condition should be. A bound on the chord residual "
                "needs a measured curve to compute against, which is exactly "
                "what a caller who declared a chord does not have. A condition "
                "on chemistry would be a lookup, not physics. This is a design "
                "question for whoever owns the battery domain and is recorded "
                "as one."
            ),
            "production_change_made": "none",
        },
        {
            "id": "MVF-3",
            "class": "AUDIT_DEFECT",
            "model": "electrical.material.linear_tcr_resistance",
            "severity": "MEDIUM",
            "statement": (
                "Six of 371 scored entries, all between 30 and 48 degC, fail "
                "the preregistered 5 percent rule. The rule is sound; the "
                "interval it was applied over is not. METRIC_PLAN.json set the "
                "lower bound at 30 degC from the table's STATED quantisation "
                "of +/-0.005 ohm. The table's measured scatter against any "
                f"quadratic is {corroboration['measured_scatter_against_the_best_fit_quadratic_ohm']:.4f} "
                "ohm, about three times that, and at 30 degC that is 29 "
                "percent of the term being tested."
            ),
            "handling": (
                "The rule and its result stand unedited, as METRIC_PLAN.json "
                "requires. A separate, labelled secondary analysis reports the "
                "same 5 percent rule over the interval the reference data can "
                "actually support: from 50 degC upward all 351 entries pass, "
                f"with a worst metric of "
                f"{c['secondary_analysis_after_the_audit_defect']['by_lower_bound']['50']['max_metric']:.4f}."
            ),
            "production_change_made": "none",
        },
        {
            "id": "MVF-4",
            "class": "REFERENCE_DATA_DEFECT",
            "model": "electrical.material.linear_tcr_resistance",
            "severity": "LOW",
            "statement": (
                "The platinum reference table departs from the best quadratic "
                "through it by up to "
                f"{corroboration['measured_scatter_against_the_best_fit_quadratic_ohm']:.4f} ohm, "
                f"{corroboration['scatter_in_units_of_the_nominal_quantisation']:.1f} times the "
                "+/-0.005 ohm its own 0.01 ohm resolution implies. No "
                "Callendar-Van Dusen pair reproduces it to its stated "
                "resolution, the pre-1995 DIN 43760 pair included, which is "
                "ruled out at 0.22 ohm."
            ),
            "what_it_does_not_undermine": (
                "The coefficients. Fitting A and B to the table returns "
                f"{corroboration['coefficient_agreement']['fitted_A_per_degC']:.9e} and "
                f"{corroboration['coefficient_agreement']['fitted_B_per_degC2']:.9e}, "
                "against the previous round's independently recited 3.9083e-3 "
                "and -5.775e-7 - agreement to six and eight parts per million. "
                "Two artifacts that never saw each other corroborate the pair."
            ),
            "production_change_made": "none",
        },
        {
            "id": "MVF-5",
            "class": "EMPIRICAL_EVIDENCE_INSUFFICIENT",
            "model": "battery.cell.coulomb_counting, battery.cell.constant_current_runtime, battery.cell.peukert_capacity_derating",
            "severity": "MEDIUM",
            "statement": (
                "The one measured constant-current discharge dataset reachable "
                "from this environment has exactly the shape these three "
                "models need - three rates on ten cells with cutoff times - and "
                "does not record the discharge current. Its labels read as 1C, "
                "C/2 and C/3; its durations are about 1.0 h, 4.0 h and 8.8 h, "
                "which contradicts that by more than a factor of two."
            ),
            "what_was_refused": (
                "Deriving the currents from the durations and the nominal "
                "capacity. The delivered capacity at each rate is precisely "
                "what Peukert's law predicts, so using it as an input would be "
                "assuming the answer, and the resulting agreement would be "
                "arithmetic dressed as evidence."
            ),
            "production_change_made": "none",
        },
        {
            "id": "MVF-6",
            "class": "OUT_OF_SCOPE_REFERENCE",
            "model": "battery.cell.rint_ocv",
            "severity": "INFORMATIONAL",
            "statement": (
                "PyBaMM ships measured half-cell open-circuit potentials from "
                "Chen 2020 and Ecker 2015. They describe electrode potentials "
                "against electrode stoichiometry, not full-cell terminal "
                "voltage against cell state of charge. Excluded before use."
            ),
            "production_change_made": "none",
        },
        {
            "id": "MVF-7",
            "class": "AUDIT_DEFECT",
            "model": "the validation harness itself",
            "severity": "LOW",
            "statement": (
                "VALIDATION_SPLIT.json counts the 0 degC table entry twice: "
                "once as the MV-C calibration row and once inside the held-out "
                "range. Its held-out count is 680 and its total 1052 for a "
                "table with 1051 entries. The rule - which entries are scored - "
                "is unaffected; only the published count was wrong."
            ),
            "handling": (
                "The preregistered file is left as committed. The integrity "
                "check reports the one-row discrepancy every run, and it is "
                "declared here so that it cannot pass silently."
            ),
            "production_change_made": "none",
        },
        {
            "id": "MVF-8",
            "class": "AUDIT_DEFECT",
            "model": "the falsification harness",
            "severity": "LOW",
            "statement": (
                "Three faults in the auditor, found by running it. Its first "
                "plant comparison measured a single-case plant against a "
                "whole-round baseline and reported four spurious misses. Its "
                "first time-shift plant stretched the discharge time axis, "
                "which leaves the residual of a straight-line fit exactly "
                "unchanged and could never have been caught. Its platinum "
                "table parser ran past the array terminator and then swallowed "
                "the digits of a trailing comment, reading 1069 and then 1054 "
                "entries for a 1051-entry table."
            ),
            "handling": (
                "All three fixed before any verdict was recorded. The parser "
                "now refuses any length but 1051, the plant comparison is "
                "built from the cases the plant ran, and the time-shift plant "
                "now corrupts the point of the relaxation trace the value is "
                "read from - which is the fault an extraction actually makes, "
                "and which is caught by a check that pins the read point."
            ),
            "production_change_made": "none",
        },
    ]


ACCOUNTING = {
    "battery.cell.rint_ocv": {
        "verdict": "EMPIRICAL_PARTIAL",
        "why": (
            "Two configurations, opposite results, on the same cell and the "
            "same measurement. With a declared measured curve it reproduces "
            "held-out open-circuit voltage inside the preregistered tolerance. "
            "With the affine chord it misses by up to 293 mV. Reporting either "
            "alone would be reporting half the evidence."
        ),
    },
    "electrical.material.linear_tcr_resistance": {
        "verdict": "EMPIRICAL_PARTIAL",
        "why": (
            "Against a standards-body reference table its deviation is the "
            "omitted quadratic term to better than 5 percent from 50 degC "
            "upward, and the residual's quadratic coefficient matches |B| R0 "
            "to four significant figures. It is PARTIAL and not VALIDATED "
            "because six scored entries at the low end fail the rule as "
            "preregistered, because the reference is a transcription rather "
            "than the licensed document, and because it is a standardised "
            "relation rather than a measurement of a specimen."
        ),
    },
    "electrical.material.rated_linear_tcr_resistance": {
        "verdict": "EMPIRICAL_PARTIAL",
        "why": (
            "Its constitutive law is the one above and carries that evidence. "
            "The claim that distinguishes it - the linearization band and the "
            "maximum operating temperature - has no measured rating behind it "
            "for any conductor used here."
        ),
    },
    "electrical.dc.kcl": {"verdict": "REFERENCE_VALIDATED_ONLY", "why": "ngspice 42, LEVEL 4, from the previous round. No physical measurement."},
    "electrical.dc.resistor_ohm": {"verdict": "REFERENCE_VALIDATED_ONLY", "why": "ngspice 42, LEVEL 4, from the previous round."},
    "electrical.dc.ideal_voltage_source": {"verdict": "REFERENCE_VALIDATED_ONLY", "why": "ngspice 42, LEVEL 4, from the previous round."},
    "electrical.dc.ideal_current_source": {"verdict": "REFERENCE_VALIDATED_ONLY", "why": "ngspice 42, LEVEL 4, from the previous round."},
    "electrical.dc.regulated_voltage_source": {"verdict": "REFERENCE_VALIDATED_ONLY", "why": "Covered numerically by the previous round; its regulation band is a caller's declaration with no external number to be right about."},
    "electrical.dc.self_heated_resistor": {"verdict": "REFERENCE_VALIDATED_ONLY", "why": "Covered numerically by the previous round; no datasheet with a measured element-to-body thermal resistance is reachable."},
    "thermal.lumped.first_order_capacity": {"verdict": "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", "why": "No measured transient with independently known C and hA is reachable. Rounds 5 and 6 validated it mathematically and against an independently constructed problem; neither is a measurement."},
    "thermal.conduction1d.linear_diffusion": {"verdict": "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", "why": "No measured transient is reachable, and the quantity this model predicts - the decay of an exactly half-sine initial profile - is not one an experiment produces."},
    "battery.cell.coulomb_counting": {"verdict": "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", "why": "See MVF-5: the only measured constant-current discharge dataset available does not record the current."},
    "battery.cell.constant_current_runtime": {"verdict": "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", "why": "See MVF-5."},
    "battery.cell.peukert_capacity_derating": {"verdict": "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", "why": "See MVF-5. This is the model the available data comes closest to fitting, and the gap is one column."},
    "kinetics.cstr.nonisothermal_first_order": {"verdict": "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", "why": "The one measured reactor experiment found was rejected at the provenance lock. CODATA fixes a constant the model is handed and validates nothing the model predicts."},
    "kinetics.cstr.nonisothermal_first_order_constant_rate": {"verdict": "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED", "why": "Declared in the repository as a comparison approximation rather than a claim about a physical system."},
}
