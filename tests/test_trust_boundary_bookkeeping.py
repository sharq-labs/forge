"""Impossible solver bookkeeping and unrecordable free-form fields.

TB-5, TB-6 and TB-7 of the trust-boundary hardening sprint. Each refusal lives
on the record type, so no solver adapter has to remember it:

* ``SolverSettings.tolerances`` refused NaN and infinity but accepted a
  negative bound. A tolerance is a magnitude; zero is a legitimate request
  (``RouteComparison`` already accepts it) and a negative one is not.
* ``RawSolverOutput`` accepted negative, fractional and boolean iteration
  counts and a negative or non-finite wall time, and its ``diagnostics`` --
  serialized by its own ``to_dict`` -- accepted values no record can carry.
* ``ScientificProblem.metadata`` accepted the same unrecordable values that
  ``ScientificResult.metadata``, ``ProvenanceRecord.metadata`` and
  ``SolverSettings.options`` already refuse, although ``to_dict`` records it.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from engcore.scientific.errors import InvalidScientificProblem, ScientificCoreError
from engcore.scientific.ir.problem import ScientificProblem
from engcore.scientific.solvers.protocol import (
    ConvergenceState,
    RawSolverOutput,
    SolverSettings,
)

UNRECORDABLE = {
    "object": {"handle": object()},
    "nan": {"x": float("nan")},
    "inf": {"x": float("inf")},
    "int key": {1: "k"},
    "nested object": {"outer": {"inner": object()}},
}
RECORDABLE = {"n_cells": 16, "outcome": "ok", "dx_m": 0.1, "flags": [True, "a"],
              "nested": {"k": 2}}


# ---- TB-5 SolverSettings ----------------------------------------------------
@pytest.mark.parametrize("value", [-1e-6, -1.0, -1e300])
def test_a_negative_solver_tolerance_is_refused(value):
    with pytest.raises(ScientificCoreError, match="negative"):
        SolverSettings(tolerances={"rtol": value})
    with pytest.raises(ScientificCoreError, match="negative"):
        SolverSettings.from_dict({"tolerances": {"rtol": value}})


@pytest.mark.parametrize("value", [0.0, 1e-300, 1e-6, 1.0])
def test_zero_and_positive_solver_tolerances_are_accepted(value):
    assert SolverSettings(tolerances={"rtol": value}).tolerances["rtol"] == value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_solver_tolerances_are_still_refused(value):
    with pytest.raises(ScientificCoreError, match="finite"):
        SolverSettings(tolerances={"rtol": value})


# ---- TB-6 RawSolverOutput bookkeeping ----------------------------------------
@pytest.mark.parametrize("state", list(ConvergenceState))
@pytest.mark.parametrize("iterations", [-1, -100, 2.5, True, "3"])
def test_an_impossible_iteration_count_is_refused(state, iterations):
    with pytest.raises(ScientificCoreError, match="iteration"):
        RawSolverOutput(state, iterations=iterations)


@pytest.mark.parametrize("state", list(ConvergenceState))
@pytest.mark.parametrize(
    "wall_seconds", [-1e-3, -1.0, float("nan"), float("inf"), True, "0.1"]
)
def test_an_impossible_wall_time_is_refused(state, wall_seconds):
    with pytest.raises(ScientificCoreError, match="wall"):
        RawSolverOutput(state, wall_seconds=wall_seconds)


@pytest.mark.parametrize(
    "iterations, wall_seconds",
    [(None, None), (0, 0.0), (12, 0.25), (np.int64(7), np.float64(1.5))],
)
def test_possible_bookkeeping_is_accepted_and_normalized(iterations, wall_seconds):
    raw = RawSolverOutput(
        ConvergenceState.CONVERGED, iterations=iterations, wall_seconds=wall_seconds
    )
    if iterations is None:
        assert raw.iterations is None
    else:
        assert type(raw.iterations) is int and raw.iterations == int(iterations)
    if wall_seconds is None:
        assert raw.wall_seconds is None
    else:
        assert type(raw.wall_seconds) is float
        assert raw.wall_seconds == float(wall_seconds)


def test_a_stored_record_with_negative_bookkeeping_is_refused():
    payload = RawSolverOutput(ConvergenceState.CONVERGED, iterations=3).to_dict()
    payload["iterations"] = -3
    with pytest.raises(ScientificCoreError, match="iteration"):
        RawSolverOutput.from_dict(payload)


@pytest.mark.parametrize("label", sorted(UNRECORDABLE))
def test_unrecordable_diagnostics_are_refused(label):
    for state in (ConvergenceState.CONVERGED, ConvergenceState.FAILED):
        with pytest.raises(ScientificCoreError, match="cannot be recorded"):
            RawSolverOutput(state, diagnostics=UNRECORDABLE[label])


def test_recordable_diagnostics_survive_a_json_round_trip_faithfully():
    raw = RawSolverOutput(
        ConvergenceState.CONVERGED,
        iterations=4,
        wall_seconds=0.5,
        diagnostics={**RECORDABLE, "numpy_float": np.float64(2.0)},
    )
    text = json.dumps(raw.to_dict(), allow_nan=False)
    back = RawSolverOutput.from_dict(json.loads(text))
    assert back.to_dict() == raw.to_dict()


# ---- TB-7 ScientificProblem.metadata -----------------------------------------
@pytest.mark.parametrize("label", sorted(UNRECORDABLE))
def test_unrecordable_problem_metadata_is_refused(label):
    with pytest.raises(InvalidScientificProblem, match="cannot be recorded"):
        ScientificProblem(problem_id="p", metadata=UNRECORDABLE[label])


def test_recordable_problem_metadata_survives_a_json_round_trip_faithfully():
    problem = ScientificProblem(problem_id="p", metadata=RECORDABLE)
    text = json.dumps(problem.to_dict(), allow_nan=False)
    back = ScientificProblem.from_dict(json.loads(text))
    assert back.to_dict() == problem.to_dict()
    assert back.metadata == problem.metadata
