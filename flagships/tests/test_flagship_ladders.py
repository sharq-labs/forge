"""Ladder-building rules of the flagships that need no provider (re-review findings H-A, M4, M8, M3).

The provider-backed suites exercise the same code with real solvers; these tests pin the rules themselves, so a change that lets missing
evidence raise a level fails here without CoolProp, Cantera or FEniCSx installed.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.engineering import LevelStatus, PredeclaredCriterion, compare_to_reference
from engcore.scientific.units.quantity import Quantity
from forge_flagships import cavity_cfd as cf
from forge_flagships import chem_thermal as ct
from forge_flagships import thermo_mechanical as tm


# --------------------------------------------------------------------------------------------------------------------- D: level 3
def _lhv_comparison(value_kj_per_mol: float):
    hess, _ = ct.load_hess()
    crit = PredeclaredCriterion("lhv_hess_law", "lower_heating_value", "absolute_difference", Quantity(ct.LHV_TOL_KJ_PER_MOL, "kJ/mol"), "test")
    reference = hess.values("lower_heating_value")[0]
    return compare_to_reference(hess, crit, {"temperature": Quantity(300.0, "K"), "pressure": Quantity(ct.P_ATM, "Pa")},
                                value=Quantity(abs(value_kj_per_mol - reference), "kJ/mol"), compared_identity="a" * 64)


def test_level_three_of_the_chemistry_flagship_needs_every_declared_check_to_have_run_and_been_met():
    good = _lhv_comparison(802.4)
    assert good.outcome == "met"
    both = ct.level3_entry(good, 1e-9)
    assert both.status is LevelStatus.REACHED and len(both.evidence) == 2
    # removing evidence must never raise the level: each missing check leaves the level NOT reached and says which check did not run
    only_lhv = ct.level3_entry(good, None)
    only_gap = ct.level3_entry(None, 1e-9)
    for partial, missing in ((only_lhv, "the kinetic reactor converges"), (only_gap, "heating value of methane")):
        assert partial.status is LevelStatus.ATTEMPTED_NOT_REACHED and "NOT RUN" in partial.note and missing in partial.note
    nothing = ct.level3_entry(None, None)
    assert nothing.status is LevelStatus.NOT_ATTEMPTED and not nothing.evidence
    # an unmet check keeps the level unreached and keeps its evidence visible
    bad = ct.level3_entry(_lhv_comparison(900.0), 1e-9)
    assert bad.status is LevelStatus.ATTEMPTED_NOT_REACHED and "NOT MET" in bad.note and len(bad.evidence) == 2
    worse_gap = ct.level3_entry(good, 0.5)
    assert worse_gap.status is LevelStatus.ATTEMPTED_NOT_REACHED
    # the note is built from what ran, never a fixed sentence claiming both checks
    assert "NOT RUN" not in both.note and "MET" in both.note


# ------------------------------------------------------------------------------------------------------------------------ B: L2 diagnostic
def test_the_equilibrium_diagnostic_is_read_only_where_there_is_an_axial_force_to_be_constant():
    mesh, mat = tm.plate_mesh(40, 8), tm.plate_material()
    n_cells = np.asarray(mesh.cells).shape[0]
    temperature = np.full(mesh.node_count, tm.T_REF)
    u = np.zeros((mesh.node_count, 2))
    # a solver that ignored the thermal load: zero displacement AND zero stress -> a zero spread that must not count as equilibrium
    blind = tm.structural_qoi(mesh, mat, u, temperature, native_sigma=np.zeros((n_cells, 3)))
    assert blind["section_force_spread"].magnitude == 0.0 and blind["section_force_ratio"].magnitude == 0.0
    assert not tm.equilibrium_read(blind["section_force_spread"].magnitude, blind["section_force_ratio"].magnitude)
    # a restrained plate at the bar-theory stress: a real, constant force through every section
    s = tm.uniform_constrained_stress(tm.T_COLD + tm.FLUX * tm.LENGTH / (2 * tm.K_COND))
    sigma = np.zeros((n_cells, 3))
    sigma[:, 0] = s
    real = tm.structural_qoi(mesh, mat, u, temperature, native_sigma=sigma)
    assert real["section_force_spread"].magnitude < 1e-9 and 0.6 < real["section_force_ratio"].magnitude < 0.8
    assert tm.equilibrium_read(real["section_force_spread"].magnitude, real["section_force_ratio"].magnitude)
    # a force that varies from section to section fails on the spread even when it is large
    varying = sigma.copy()
    cx = np.asarray(mesh.coordinates)[np.asarray(mesh.cells)][:, :, 0].mean(axis=1)
    varying[:, 0] = s * (1.0 + 0.5 * cx / tm.LENGTH)
    v = tm.structural_qoi(mesh, mat, u, temperature, native_sigma=varying)
    assert not tm.equilibrium_read(v["section_force_spread"].magnitude, v["section_force_ratio"].magnitude)
    assert not tm.equilibrium_read(None, 0.7) and not tm.equilibrium_read(0.0, None)                # a missing value is not a pass


# ---------------------------------------------------------------------------------------------------------------------------- C: constraint
def test_the_cavity_flux_constraint_is_bound_for_each_code_on_an_unsigned_residual():
    system, flux = cf.system_definition()
    assert {b.binding_id for b in system.constraint_bindings} == {"b_flux_openfoam", "b_flux_su2"}      # one code's result never stands for the other's
    assert flux.bound.magnitude == cf.FLUX_TOL and flux.operator.name == "LESS_EQUAL"
    # the sampled residual is signed (a physical sign: net flow in or out); the constraint observable is bounded above only, so it is the
    # UNSIGNED maximum that is observed - a residual of -1 must never be compared with an upper bound as if it were small
    y = np.linspace(0.0, cf.SIDE, 11)
    assert cf.flux_residual(y, -np.ones_like(y), cf.SIDE, 1.0) == pytest.approx(-1.0)
    src = open(cf.__file__, "rb").read().decode()
    assert '"flux_residual_abs"' in src and 'outs["flux_residual_abs"] = max(abs(outs["u_flux_residual"]), abs(outs["v_flux_residual"]))' in src
    assert "ConstraintObservation(f\"b_flux_{prov}\"" in src and "flux_residual_abs_{prov}_{finest}" in src


# ------------------------------------------------------------------------------------------------------------------ references bind quantities
def test_every_flagship_criterion_binds_to_a_quantity_its_reference_declares_comparable():
    ghia, _ = cf.load_ghia()
    hess, _ = ct.load_hess()
    free, constrained, bar = tm.analytic_references()
    from forge_flagships import battery_cooling as bc
    first_law = bc.first_law_reference()
    assert "centerline_velocity_over_lid_speed" in ghia.comparable_quantities and "lower_heating_value" in hess.comparable_quantities
    assert free.quantities[0][0] in free.comparable_quantities and constrained.quantities[0][0] in constrained.comparable_quantities
    assert "mid_section_stress_error_relative" in bar.comparable_quantities and "delta_T_relative_difference" in first_law.comparable_quantities
    # the NASA reference is considered, never compared: it declares nothing comparable
    assert bc.nasa_reference().comparable_quantities == ()


# ------------------------------------------------------------------------------------------------------------- B: level 2 builder (round 3, M4)
class _Assessment:
    """A stand-in for a ConservationAssessment (the builder reads status, balance_id, residual and to_dict)."""

    def __init__(self, status: str, residual: float | None = 1e-11):
        self.status, self.balance_id = status, "thermal_energy"
        self.residual = None if residual is None else Quantity(residual, "W")

    def to_dict(self) -> dict:
        return {"balance_id": self.balance_id, "status": self.status, "residual": None if self.residual is None else self.residual.to_dict()}


PROVIDERS = ("fenicsx", "calculix", "code_aster")


def test_level_two_of_the_structure_flagship_records_a_failing_reading_instead_of_dropping_it():
    ok_spread = {p: 1e-9 for p in PROVIDERS}
    ok_ratio = {p: 0.71 for p in PROVIDERS}
    reached = tm.level2_entry((_Assessment("closed"),), ok_spread, ok_ratio)
    assert reached.status is LevelStatus.REACHED and {e.kind for e in reached.evidence} == {"conservation_assessment", "equilibrium_diagnostic"}
    # a solver that ignored the load: the balance closes, the spread is zero, the mean force is zero -> NOT reached, and the failing reading is IN the evidence
    blind = tm.level2_entry((_Assessment("closed"),), {p: 0.0 for p in PROVIDERS}, {p: 0.0 for p in PROVIDERS})
    assert blind.status is LevelStatus.ATTEMPTED_NOT_REACHED and "axial-force diagnostic NOT MET" in blind.note
    diag = next(e for e in blind.evidence if e.kind == "equilibrium_diagnostic")
    assert diag.outcome == "not_met" and diag.record["mean_force_over_scale"] == {p: 0.0 for p in PROVIDERS}
    # a balance that did not close keeps its assessment as a not_met link
    open_balance = tm.level2_entry((_Assessment("open", residual=3.0),), ok_spread, ok_ratio)
    assert open_balance.status is LevelStatus.ATTEMPTED_NOT_REACHED and any(e.outcome == "not_met" and e.kind == "conservation_assessment" for e in open_balance.evidence)
    # a provider with no reading is not a pass
    missing = tm.level2_entry((_Assessment("closed"),), {**ok_spread, "calculix": None}, {**ok_ratio, "calculix": None})
    assert missing.status is LevelStatus.ATTEMPTED_NOT_REACHED
    # nothing assessable at all
    nothing = tm.level2_entry((), {p: None for p in PROVIDERS}, {p: None for p in PROVIDERS})
    assert nothing.status is LevelStatus.NOT_ATTEMPTED and not nothing.evidence


# --------------------------------------------------------------------------------------------------- C: level 5 builder (round 4, M-4)
class _FakeProviderComparison:
    """A stand-in for a ProviderComparison (the link builder reads classification, within_tolerance, to_dict and digest)."""

    def __init__(self, within: bool, post_hoc: bool = False, tag: str = "x"):
        self.within_tolerance = within
        self.classification = "post_hoc_solver_corroboration_not_validation" if post_hoc else "solver_corroboration_not_validation"
        self.tag = tag

    def to_dict(self) -> dict:
        return {"classification": self.classification, "within_tolerance": self.within_tolerance, "a_selection": {"rows": [1, 2]}, "b_selection": {"rows": [3]}, "tag": self.tag}

    @property
    def digest(self) -> str:
        return "d" * 64


LEVELS3 = (20, 40, 80)


def _whole(flags):
    return {n: (None if f is None else _FakeProviderComparison(bool(f), tag=str(n))) for n, f in zip(LEVELS3, flags)}


def test_level_five_of_the_cavity_flagship_records_a_missing_or_failing_whole_field_comparison_instead_of_dropping_it():
    lower = {n: _FakeProviderComparison(True, post_hoc=True, tag=f"low{n}") for n in LEVELS3}
    details = {n: f"whole field {n}x{n}" for n in LEVELS3}
    reached = cf.level5_entry(LEVELS3, dict(zip(LEVELS3, (1.0, 1.0, 1.0))), _whole((1, 1, 1)), lower, details)
    assert reached.status is LevelStatus.REACHED and len(reached.evidence) == 3 and not any(e.classification.startswith("post_hoc") for e in reached.evidence)
    # every level disagrees (the recorded result): NOT reached, the post-hoc lower-half readings sit beside it
    unmet = cf.level5_entry(LEVELS3, dict(zip(LEVELS3, (0.0, 0.0, 0.0))), _whole((0, 0, 0)), lower, details)
    assert unmet.status is LevelStatus.ATTEMPTED_NOT_REACHED and sum(e.classification.startswith("post_hoc") for e in unmet.evidence) == 3
    # the finest level failed to run: its comparison is MISSING - it must not read as 'not attempted', and the two produced comparisons stay in the evidence
    partial = cf.level5_entry(LEVELS3, {20: 0.0, 40: 0.0, 80: None}, _whole((0, 0, None)), lower, details)
    assert partial.status is LevelStatus.ATTEMPTED_NOT_REACHED
    missing = [e for e in partial.evidence if e.kind == "whole_field_missing"]
    assert len(missing) == 1 and missing[0].outcome == "not_met" and "80x80" in partial.note
    assert sum(e.kind == "provider_comparison" and not e.classification.startswith("post_hoc") for e in partial.evidence) == 2
    # a level missing while the others agree is still not a pass
    assert cf.level5_entry(LEVELS3, {20: 1.0, 40: 1.0, 80: None}, _whole((1, 1, None)), lower, details).status is LevelStatus.ATTEMPTED_NOT_REACHED
    assert cf.level5_entry(LEVELS3, {n: None for n in LEVELS3}, _whole((None, None, None)), {}, {}).status is LevelStatus.NOT_ATTEMPTED


# --------------------------------------------------------------------------------------------------- B: level 4 builder (round 4)
def _study(vm_last=60.06e6, sxx=-55.207466e6, fail_level=None):
    import math
    ux = [2.790824e-05, 2.789204e-05, 2.788798e-05, 2.788696e-05]
    vm = [58.917e6, 59.409e6, 59.817e6, vm_last]
    rows = []
    for i, (nx, ny) in enumerate(((20, 4), (40, 8), (80, 16), (160, 32))):
        row = {"nx": nx, "ny": ny, "nodes": 100 * (i + 1), "status": "succeeded", "result": "r" * 64}
        for p in tm.PROVIDERS if hasattr(tm, "PROVIDERS") else ("fenicsx", "calculix", "code_aster"):
            row |= {f"ux_mid_{p}": ux[i], f"sxx_mid_{p}": sxx, f"ux_max_{p}": 3.65e-05, f"vm_max_{p}": vm[i]}
        if fail_level == i:
            row["status"] = "failed"
            row |= {k: None for k in list(row) if k.endswith(("fenicsx", "calculix", "code_aster"))}
        rows.append(row)
    table = {"levels": rows, "orders": {}, "monotone": {}}
    for p in ("fenicsx", "calculix", "code_aster"):
        for q in ("ux_mid", "sxx_mid", "ux_max", "vm_max"):
            v = [r[f"{q}_{p}"] for r in rows]
            if any(x is None for x in v):
                continue
            d1, d2 = abs(v[-2] - v[-3]), abs(v[-1] - v[-2])
            table["orders"][f"{q}_{p}"] = None if d2 == 0 or d1 == 0 else float(math.log2(d1 / d2))
            table["monotone"][f"{q}_{p}"] = bool(d2 < d1)
    return table


def test_level_four_of_the_structure_flagship_keeps_the_pre_registered_outcome_and_survives_an_incomplete_study():
    entry, extra = tm.level4_entry(_study())
    # displacement converges at order ~2, the mid-plate stress is constant (no order exists): the pre-registered criterion is NOT met, the post hoc reading is
    assert entry.status is LevelStatus.ATTEMPTED_NOT_REACHED and extra["predeclared_criterion_met"] is False and extra["post_hoc_noise_aware_met"] is True
    assert {e.classification for e in entry.evidence} == {"discretisation_convergence", "post_hoc_discretisation_convergence"}
    assert "Pre-registered criterion" in entry.note and "NOT claimed converged" in entry.note
    # a mesh level that failed: recorded as not_met evidence, no order computed, no crash
    broken_entry, broken_extra = tm.level4_entry(_study(fail_level=3))
    assert broken_entry.status is LevelStatus.ATTEMPTED_NOT_REACHED and broken_extra["incomplete_levels"] == ["160x32"]
    assert [e.outcome for e in broken_entry.evidence] == ["not_met"] and "incomplete" in broken_entry.note
    fewer = _study()
    fewer["levels"] = fewer["levels"][:2]
    assert tm.level4_entry(fewer)[0].status is LevelStatus.ATTEMPTED_NOT_REACHED
