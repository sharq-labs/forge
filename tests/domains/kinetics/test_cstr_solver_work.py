"""How much work the CSTR workflows are allowed to do.

These are *deterministic operation counts*, not timings. A wall-clock threshold
on a shared runner is a coin flip; "the verification gate performs exactly one
integration per tolerance rung plus one cross-method arm" is a fact, and it is
the fact that a duplicated solve breaks.

The gate previously integrated the finest rung twice: once as the last rung of
the ladder, and again immediately afterwards purely to recover the trajectory
arrays the result had discarded. The second integration solved the identical
problem at identical tolerances with an identical method, so it could only ever
reach the identical answer. These tests pin it shut.
"""

from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pytest

from src.engcore.domains.kinetics.cstr import solver as solver_module
from src.engcore.domains.kinetics.cstr import (
    TOLERANCE_LADDER,
    CSTRSolver,
    solve_reactor,
    solve_reactor_bundle,
)
from src.engcore.domains.kinetics.cstr.validation import (
    measure_stiffness,
    run_verification_gate,
)

from tests.domains.kinetics.test_cstr_domain import (
    ADIABATIC,
    BENIGN,
    operation,
    reactor,
)


@contextmanager
def counted_integrations():
    """Count ``solve_ivp`` invocations, recording each call's settings.

    The record is appended BEFORE the backend runs, so an integration that
    exhausts its evaluation budget — which raises out of the right-hand side —
    is still counted. Counting only calls that return would miss exactly the
    most expensive invocations the domain makes.
    """
    calls: list[dict] = []
    original = solver_module.solve_ivp

    def shim(*args, **kwargs):
        calls.append(
            {
                "method": kwargs.get("method"),
                "rtol": kwargs.get("rtol"),
                "atol": np.asarray(kwargs.get("atol")).tolist(),
            }
        )
        return original(*args, **kwargs)

    solver_module.solve_ivp = shim
    try:
        yield calls
    finally:
        solver_module.solve_ivp = original


def test_one_solve_performs_exactly_one_integration() -> None:
    with counted_integrations() as calls:
        solve_reactor(BENIGN, run_id="work-single")
    assert len(calls) == 1


def test_the_gate_integrates_each_rung_once_plus_one_cross_method_arm() -> None:
    """No rung is integrated twice, and the finest one least of all."""
    with counted_integrations() as calls:
        run_verification_gate(ADIABATIC, run_id_prefix="work-gate")

    # One per rung, plus the single cross-method arm. Nothing else.
    assert len(calls) == len(TOLERANCE_LADDER) + 1

    ladder_calls = calls[: len(TOLERANCE_LADDER)]
    assert [c["rtol"] for c in ladder_calls] == [
        rung.rtol for rung in TOLERANCE_LADDER
    ]
    # Every ladder rung is a distinct tolerance — a repeat means a re-solve.
    assert len({c["rtol"] for c in ladder_calls}) == len(TOLERANCE_LADDER)
    assert {c["method"] for c in ladder_calls} == {ADIABATIC.integration.method}

    cross = calls[-1]
    assert cross["method"] == "Radau"
    assert cross["rtol"] == TOLERANCE_LADDER[-1].rtol


def test_the_finest_rung_is_never_integrated_twice() -> None:
    """The specific regression: exactly one solve at the finest tolerance."""
    finest = TOLERANCE_LADDER[-1]
    with counted_integrations() as calls:
        run_verification_gate(ADIABATIC, run_id_prefix="work-finest")

    at_finest_with_production_method = [
        c
        for c in calls
        if c["rtol"] == finest.rtol
        and c["method"] == ADIABATIC.integration.method
    ]
    assert len(at_finest_with_production_method) == 1, (
        "the finest rung was integrated more than once; a second solve of the "
        "same problem at the same tolerance cannot produce new information"
    )


def test_the_stiffness_probe_performs_exactly_two_integrations() -> None:
    """One stiff arm, one explicit arm. The ratio needs both and only both."""
    with counted_integrations() as calls:
        measure_stiffness(BENIGN, run_id_prefix="work-stiff")
    assert len(calls) == 2
    assert [c["method"] for c in calls] == [BENIGN.integration.method, "RK45"]


# =====================================================================
# The bundle carries the trajectory instead of the result carrying it
# =====================================================================

def test_the_bundle_returns_the_trajectory_the_solve_already_computed() -> None:
    with counted_integrations() as calls:
        bundle = solve_reactor_bundle(BENIGN, run_id="work-bundle")
    assert len(calls) == 1

    expected_points = BENIGN.integration.n_output_points
    assert bundle.trajectory.time_s.size == expected_points
    assert bundle.trajectory.concentration_mol_per_m3.size == expected_points
    assert bundle.trajectory.temperature_k.size == expected_points
    assert bundle.rhs_evaluations > 0


def test_the_public_result_still_carries_no_trajectory_arrays() -> None:
    """The compact result contract is unchanged by the bundle existing."""
    bundle = solve_reactor_bundle(BENIGN, run_id="work-compact")
    numerics = bundle.result.metadata["numerics"]
    for bulky in (
        "grid_time_s",
        "grid_concentration_mol_per_m3",
        "grid_temperature_k",
        "partial_time_s",
        "partial_concentration_mol_per_m3",
        "partial_temperature_k",
    ):
        assert bulky not in numerics


def test_solve_reactor_returns_the_bundles_own_result() -> None:
    """The wrapper adds nothing and subtracts nothing."""
    plain = solve_reactor(BENIGN, run_id="work-same")
    bundled = solve_reactor_bundle(BENIGN, run_id="work-same").result
    assert plain.convergence is bundled.convergence
    assert plain.is_usable == bundled.is_usable
    assert set(plain.values) == set(bundled.values)
    for name, quantity in plain.values.items():
        assert quantity.magnitude == bundled.values[name].magnitude
    assert [c.name for c in plain.validation.checks] == [
        c.name for c in bundled.validation.checks
    ]
    assert [c.outcome for c in plain.validation.checks] == [
        c.outcome for c in bundled.validation.checks
    ]


def test_a_run_that_does_not_complete_the_horizon_yields_an_empty_sample() -> None:
    """A partial trajectory is not a trajectory sample, and is not offered as one."""
    starved = reactor(
        "starved",
        op=operation(ua=0.0, tf=350.0, caf=2600.0, end=600.0),
        ca0=2600.0,
        t0=350.0,
        budget=500,
    )
    bundle = solve_reactor_bundle(starved, run_id="work-starved")
    assert not bundle.result.values
    assert bundle.trajectory.is_empty


@pytest.mark.parametrize(
    "attribute",
    ("time_s", "concentration_mol_per_m3", "temperature_k"),
)
def test_the_trajectory_sample_stays_a_numpy_array(attribute: str) -> None:
    bundle = solve_reactor_bundle(BENIGN, run_id="work-arrays")
    assert isinstance(getattr(bundle.trajectory, attribute), np.ndarray)
