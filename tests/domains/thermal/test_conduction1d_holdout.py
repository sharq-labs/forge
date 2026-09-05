"""The confirmatory holdout: does the declared gate transfer to a case it was
not chosen from?

The gate thresholds were declared after an exploratory calculation had already
shown roughly where this method lands on the nominal benchmark. That makes
passing on the nominal case weak evidence. These tests check one case the
thresholds were not chosen from, against the gates completely unchanged.
"""

from __future__ import annotations

import math

import pytest

from src.engcore.domains.thermal.conduction1d import (
    ANALYTIC_REL_TOL,
    CONVERGENCE_MIN_CONTRACTION,
    MIN_RUNGS,
    VERIFICATION_LADDER,
    exact_midpoint,
    run_verification_gate,
)
from src.engcore.scientific.results.validation import ValidationLevel
from tests.domains.thermal.holdout_declaration import (
    DECLARED_REGIME_MAX_DECAY,
    HOLDOUT_ALPHA_M2_S,
    NOMINAL_ALPHA_M2_S,
    PREDICTED_FINEST_REL_ERROR,
    holdout_config_hash,
    holdout_declaration,
    holdout_slab,
)

#: Recorded before the holdout was executed.
DECLARED_CONFIG_HASH = (
    "927aa05b4cdc4d1db4a11deb1cbb0396c407c4a501669424dafbbf5e14082e1d"
)


def gate():
    return run_verification_gate(holdout_slab(), run_id_prefix="holdout-test")


def test_holdout_config_was_declared_and_is_stable():
    assert holdout_config_hash() == DECLARED_CONFIG_HASH
    declaration = holdout_declaration()
    assert declaration["changed_parameter"] == "diffusivity"
    assert declaration["nominal_alpha_m2_s"] == NOMINAL_ALPHA_M2_S
    assert declaration["holdout_alpha_m2_s"] == HOLDOUT_ALPHA_M2_S
    # Exactly one parameter changed; everything else is the nominal benchmark.
    unchanged = declaration["unchanged"]
    assert unchanged["length_m"] == 0.1
    assert unchanged["end_time_s"] == 60.0
    assert unchanged["ladder"] == [
        [r.n_cells, r.n_steps] for r in VERIFICATION_LADDER
    ]


def test_holdout_gates_are_the_frozen_ones():
    frozen = holdout_declaration()["frozen_gates"]
    assert frozen["analytic_rel_tol"] == ANALYTIC_REL_TOL == 1.0e-3
    assert frozen["convergence_min_contraction"] == (
        CONVERGENCE_MIN_CONTRACTION
    ) == 1.5
    assert frozen["min_rungs"] == MIN_RUNGS
    assert "not retuned" in frozen["status"]


def test_holdout_took_the_stressing_direction():
    """Raising alpha increases the error; lowering it would have been easy."""
    assert HOLDOUT_ALPHA_M2_S > NOMINAL_ALPHA_M2_S
    decay = HOLDOUT_ALPHA_M2_S * math.pi**2 * 60.0 / 0.1**2
    nominal_decay = NOMINAL_ALPHA_M2_S * math.pi**2 * 60.0 / 0.1**2
    assert decay > nominal_decay
    # ...and it stays inside the regime the ladder was declared to cover.
    assert decay < DECLARED_REGIME_MAX_DECAY


def test_holdout_passes_the_unchanged_gate():
    report = gate()
    errors = [r.abs_error for r in report.rungs]

    # 1. analytic error decreases across refinement
    assert all(b < a for a, b in zip(errors, errors[1:]))
    # 2. convergence gate passes
    assert report.numerically_converged is True
    # 3. finest relative analytic error below the frozen tolerance
    assert report.rungs[-1].rel_error < ANALYTIC_REL_TOL
    # 4 & 5. both levels earned
    assert ValidationLevel.NUMERICALLY_CONVERGED in report.levels_earned
    assert ValidationLevel.ANALYTICALLY_VERIFIED in report.levels_earned
    assert report.analytically_verified is True
    # The gate it was judged by is the frozen one.
    assert report.analytic_rel_tol == ANALYTIC_REL_TOL
    assert report.min_contraction_required == CONVERGENCE_MIN_CONTRACTION


def test_holdout_matches_the_prediction_made_before_execution():
    """The declared prediction is checked, not explained after the fact."""
    report = gate()
    observed = report.rungs[-1].rel_error
    assert observed == pytest.approx(PREDICTED_FINEST_REL_ERROR, rel=0.05)
    # The margin is genuinely tight, as declared — this was not a soft test.
    margin = ANALYTIC_REL_TOL / observed
    assert 1.0 < margin < 1.3


def test_holdout_is_a_different_physical_case():
    """It must not accidentally reproduce the nominal benchmark."""
    holdout_qoi = exact_midpoint(
        length_m=0.1, alpha_m2_s=HOLDOUT_ALPHA_M2_S, time_s=60.0
    )
    nominal_qoi = exact_midpoint(
        length_m=0.1, alpha_m2_s=NOMINAL_ALPHA_M2_S, time_s=60.0
    )
    assert abs(holdout_qoi - nominal_qoi) > 0.1
    report = gate()
    assert report.rungs[-1].analytic == pytest.approx(holdout_qoi, abs=1e-15)

    # ...and it is genuinely harder than the case the gate was declared on.
    from src.engcore.domains.thermal.conduction1d import (
        ConductionSlab,
        SlabDiscretization,
    )
    from src.engcore.scientific.units.quantity import Quantity

    nominal_slab = ConductionSlab(
        slab_id="nominal-for-contrast",
        length=Quantity(0.1, "meter"),
        diffusivity=Quantity(NOMINAL_ALPHA_M2_S, "m**2/s"),
        end_time=Quantity(60.0, "second"),
        discretization=SlabDiscretization(64, 80),
    )
    nominal = run_verification_gate(nominal_slab, run_id_prefix="contrast")
    assert report.rungs[-1].rel_error > nominal.rungs[-1].rel_error
    # Both still clear the same unchanged gate.
    assert nominal.analytically_verified is True
    assert report.analytically_verified is True
