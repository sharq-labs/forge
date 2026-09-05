"""PERF-0 — count the integrations the K1 CSTR workflows actually perform.

Measurement only. Nothing here changes scientific behaviour: ``solve_ivp`` is
wrapped by a counting shim that forwards every argument untouched and returns
the backend's own object, so the numbers the domain computes are the numbers it
would have computed unwrapped.

The counts are *deterministic operation counts*, which is what makes them
usable as a regression signal. Wall time is recorded alongside them as
engineering telemetry only, and is never a scientific claim.

Run from the repository root:

    python benchmarks/perf_runtime_audit/bench_k1_solver_calls.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engcore.domains.kinetics.cstr import solver as cstr_solver  # noqa: E402
from src.engcore.domains.kinetics.cstr.problem import (  # noqa: E402
    build_cstr_problem,
)
from src.engcore.domains.kinetics.cstr.validation import (  # noqa: E402
    measure_stiffness,
    run_verification_gate,
    steady_states,
)
from src.engcore.domains.kinetics.cstr.validation import (  # noqa: E402
    MAX_VALID_TEMPERATURE_K,
    MIN_VALID_TEMPERATURE_K,
)
from experiments.kinetics_k1.k1_config import regime  # noqa: E402

#: Preregistered regimes only. Nothing new is invented here: a benign case, a
#: moderately stiff case, the strongly stiff case, and the regime whose result
#: the domain refuses to call usable.
REGIME_IDS = ("R1", "R2", "R3", "R8")


class _SolveCounter:
    """Counts ``solve_ivp`` invocations and records each call's backend work."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def count(self) -> int:
        return len(self.calls)

    def totals(self) -> dict[str, int]:
        keys = ("nfev", "njev", "nlu", "accepted_steps")
        return {k: sum(int(c.get(k) or 0) for c in self.calls) for k in keys}


@contextmanager
def counting_solve_ivp():
    """Wrap the solver module's ``solve_ivp`` with a transparent counting shim."""
    counter = _SolveCounter()
    original = cstr_solver.solve_ivp

    def shim(*args, **kwargs):
        # The record is created BEFORE the backend runs. An integration that
        # exhausts the evaluation budget raises out of the right-hand side, and
        # counting only calls that return would silently omit exactly the
        # most expensive invocations the domain makes.
        record: dict[str, Any] = {
            "method": kwargs.get("method"),
            "rtol": kwargs.get("rtol"),
            "nfev": 0,
            "njev": 0,
            "nlu": 0,
            "accepted_steps": 0,
            "status": -99,
            "raised": None,
            "seconds": 0.0,
        }
        counter.calls.append(record)
        started = time.perf_counter()
        try:
            solution = original(*args, **kwargs)
        except BaseException as exc:
            record["seconds"] = time.perf_counter() - started
            record["raised"] = type(exc).__name__
            raise
        record["seconds"] = time.perf_counter() - started
        times = getattr(solution, "t", None)
        record.update(
            {
                "nfev": int(getattr(solution, "nfev", 0) or 0),
                "njev": int(getattr(solution, "njev", 0) or 0),
                "nlu": int(getattr(solution, "nlu", 0) or 0),
                "accepted_steps": (
                    int(len(times) - 1) if times is not None and len(times) else 0
                ),
                "status": int(getattr(solution, "status", -99)),
            }
        )
        return solution

    cstr_solver.solve_ivp = shim
    try:
        yield counter
    finally:
        cstr_solver.solve_ivp = original


def _timed(fn, repeats: int) -> tuple[Any, dict[str, float]]:
    """Run ``fn`` ``repeats`` times; report median and spread of wall time.

    Telemetry only. The returned value is from the final repetition; every
    repetition is deterministic, so which one is returned does not matter.
    """
    samples: list[float] = []
    value = None
    for _ in range(repeats):
        started = time.perf_counter()
        value = fn()
        samples.append(time.perf_counter() - started)
    samples.sort()
    return value, {
        "median_s": statistics.median(samples),
        "min_s": samples[0],
        "max_s": samples[-1],
        "repeats": float(repeats),
    }


def measure_regime(regime_id: str, repeats: int) -> dict[str, Any]:
    spec = regime(regime_id)
    run = spec.build()
    out: dict[str, Any] = {"regime_id": regime_id, "category": spec.category}

    # --- one ordinary solve ------------------------------------------------
    def one_solve():
        problem = build_cstr_problem(run, problem_id=f"perf-{regime_id}")
        return cstr_solver.solve_reactor(
            run,
            run_id=f"perf-{regime_id}",
            solver=cstr_solver.CSTRSolver(),
            problem=problem,
        )

    with counting_solve_ivp() as counter:
        result, timing = _timed(one_solve, repeats)
    out["single_solve"] = {
        "solve_ivp_calls": counter.count // int(timing["repeats"]),
        "work_per_call": counter.totals(),
        "convergence": result.convergence.value,
        "is_usable": bool(result.is_usable),
        "timing_telemetry": timing,
    }

    # --- the verification gate --------------------------------------------
    if spec.run_verification_gate:
        with counting_solve_ivp() as counter:
            report, timing = _timed(
                lambda: run_verification_gate(
                    run, run_id_prefix=f"perf-{regime_id}-gate"
                ),
                repeats,
            )
        per_run = counter.count // int(timing["repeats"])
        first_pass = counter.calls[:per_run]
        out["verification_gate"] = {
            "solve_ivp_calls": per_run,
            "ladder_rungs": len(report.rungs),
            "calls": [
                {
                    k: c[k]
                    for k in (
                        "method", "rtol", "nfev", "njev", "nlu", "status", "raised"
                    )
                }
                for c in first_pass
            ],
            "total_nfev": sum(int(c["nfev"]) for c in first_pass),
            "levels_earned": [level.value for level in report.levels_earned],
            "tolerance_independent": report.tolerance_independent,
            "invariant_verified": report.invariant_verified,
            "steady_state_verified": report.steady_state_verified,
            "cross_method_agrees": report.cross_method_agrees,
            "timing_telemetry": timing,
        }

    # --- the stiffness measurement ----------------------------------------
    # Deliberately one repetition: the explicit probe on a strongly stiff
    # regime deliberately burns its whole evaluation budget, so repeating it
    # costs a minute per extra pass and tells us nothing new — the counts are
    # deterministic.
    if spec.measure_stiffness:
        with counting_solve_ivp() as counter:
            stiffness, timing = _timed(
                lambda: measure_stiffness(
                    run, run_id_prefix=f"perf-{regime_id}-stiff"
                ),
                1,
            )
        out["stiffness"] = {
            "solve_ivp_calls": counter.count,
            "calls": [
                {k: c[k] for k in ("method", "nfev", "status", "raised", "seconds")}
                for c in counter.calls
            ],
            "work_ratio": stiffness.work_ratio,
            "explicit_completed": stiffness.explicit_completed,
            "timing_telemetry": timing,
        }

    # --- the independent steady-state reference ---------------------------
    _, timing = _timed(
        lambda: steady_states(
            dilution_rate_per_s=run.operation.dilution_rate_per_s,
            feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
            feed_temperature_k=run.operation.tf_k,
            coolant_temperature_k=run.operation.tc_k,
            beta_m3_k_per_mol=run.chemistry.beta_m3_k_per_mol,
            gamma_per_s=run.gamma_per_s,
            k0_per_s=run.chemistry.k0_per_s,
            activation_energy_j_per_mol=run.chemistry.e_j_per_mol,
            search_min_k=MIN_VALID_TEMPERATURE_K,
            search_max_k=MAX_VALID_TEMPERATURE_K,
        ),
        repeats,
    )
    out["steady_state_reference"] = {"timing_telemetry": timing}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    rows = [measure_regime(rid, args.repeats) for rid in REGIME_IDS]
    payload = {"regimes": rows}
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
