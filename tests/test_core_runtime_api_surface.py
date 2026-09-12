"""Part L: the public runtime API, classified, and pinned so a freeze is checkable.

A classification that lives only in a report is a classification nobody can
enforce. This file is the classification: if a symbol is added, removed or
reclassified, it fails and somebody decides deliberately.

The four classes, and what each one commits to:

``FREEZE``
    Public, supported, and intended to survive Core Freeze unchanged.
``INTERNALIZE``
    Currently public, but nothing outside the package should depend on it.
``DEPRECATE``
    Public and scheduled for removal.
``EXPERIMENTAL``
    Public, but explicitly NOT frozen: its behaviour may change, and callers
    should not build on it.
"""

from __future__ import annotations

import inspect

import engcore.execution as execution
from engcore.execution.sweep import run_sweep, rerun_failed

#: The whole public runtime surface, with its Core Freeze classification.
#:
#: Everything here is FREEZE except the worker knob, which is EXPERIMENTAL for
#: a measured reason recorded in
#: `benchmarks/core_runtime_finalization/PARALLEL.json`: thread-based execution
#: was SLOWER than sequential at every workload and worker count tried this
#: round -- 0.54x to 0.97x, never once above 1.0. A parameter whose only
#: observable effect is to make a sweep slower is not something to freeze as a
#: supported performance control.
CLASSIFICATION = {
    "run_sweep": "FREEZE",
    "rerun_failed": "FREEZE",
    "cases_from": "FREEZE",
    "SweepDefinition": "FREEZE",
    "SweepCase": "FREEZE",
    "SweepOutcome": "FREEZE",
    "SweepSummary": "FREEZE",
    "SharedContext": "FREEZE",
    "CaseStatus": "FREEZE",
    "FailurePolicy": "FREEZE",
    "SweepError": "FREEZE",
}

#: Parameters that are public but NOT frozen, and why.
EXPERIMENTAL_PARAMETERS = {
    ("run_sweep", "workers"): (
        "thread-based execution measured 0.54x-0.97x of sequential on every "
        "workload tried; parallel execution is DEFERRED and sequential is the "
        "recommended backend"
    ),
    ("rerun_failed", "workers"): (
        "same knob, same measurement, reached through the retry helper"
    ),
}


def test_the_public_surface_is_exactly_what_is_classified():
    """Adding a public symbol without classifying it fails here."""
    assert set(execution.__all__) == set(CLASSIFICATION), (
        f"unclassified: {sorted(set(execution.__all__) - set(CLASSIFICATION))}; "
        f"classified but absent: {sorted(set(CLASSIFICATION) - set(execution.__all__))}"
    )


def test_every_classified_symbol_is_actually_exported():
    for name in CLASSIFICATION:
        assert hasattr(execution, name), name


def test_nothing_public_is_deprecated_or_internalized_yet():
    """The freeze candidate has no removal debt, which is worth stating."""
    assert not [n for n, c in CLASSIFICATION.items() if c in ("DEPRECATE", "INTERNALIZE")]


def test_the_worker_knob_is_the_only_experimental_surface():
    """If a second one appears, it gets classified rather than shipped quietly."""
    assert set(EXPERIMENTAL_PARAMETERS) == {
        ("run_sweep", "workers"), ("rerun_failed", "workers")
    }


def test_the_experimental_parameters_exist_and_default_to_sequential():
    """Defaulting to 1 is what keeps a small workload from silently going slower.

    Part H's condition 6, held at the signature: a caller who does not ask for
    parallelism does not get it, so the measured slowdown cannot arrive by
    default.
    """
    for function in (run_sweep, rerun_failed):
        signature = inspect.signature(function)
        assert "workers" in signature.parameters, function.__name__
        parameter = signature.parameters["workers"]
        assert parameter.default == 1, (
            f"{function.__name__}(workers=) defaults to {parameter.default}, "
            f"not 1; threads are slower at every size measured, so a non-1 "
            f"default would make every caller slower without asking"
        )
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{function.__name__}(workers=) must stay keyword-only so it is "
            f"never passed positionally by accident"
        )


def test_no_process_backend_is_exposed():
    """Parallel execution is DEFERRED; nothing may hint otherwise.

    Measured 2.58x on a realistic payload with a PERSISTENT pool, and 0.12x
    with a pool per sweep -- so the benefit is real but depends on an
    architecture this sweep does not have, and the naive form is 8x slower than
    sequential. Deferred rather than shipped, and this test is what stops a
    half-built backend appearing on the public surface.
    """
    forbidden = {"ProcessPoolExecutor", "run_sweep_processes", "ProcessBackend",
                 "Backend", "backend", "executor", "pool"}
    assert not (forbidden & set(execution.__all__))
    assert "backend" not in inspect.signature(run_sweep).parameters
