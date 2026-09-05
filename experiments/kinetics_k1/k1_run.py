"""K1 — the scored study.

Runs every preregistered regime through the full five-stage solver contract,
runs the verification gate and the stiffness measurement where the
preregistration declares them, exercises the invalid-declaration set, scores
the acceptance criteria, and writes the frozen artifacts.

Nothing in this module decides anything. Every threshold, band and prediction
is imported from :mod:`k1_config`, which is frozen before this runs.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy
import scipy

from src.engcore.domains.kinetics.cstr import (
    CSTRSolver,
    ReactorChemistry,
    ReactorConfigurationError,
    ReactorOperation,
    ReactorRun,
    IntegrationSettings,
    build_cstr_problem,
    measure_stiffness,
    run_verification_gate,
    solve_reactor,
)

from . import BASE_COMMIT, K1_VERSION
from .k1_config import (
    ACCEPTANCE_CRITERIA,
    CHEMISTRY,
    CROSS_METHOD,
    EXPERIMENT_ID,
    FALSIFICATION_CRITERIA,
    FLOW_M3_PER_S,
    INVALID_DECLARATIONS,
    NOMINAL_FEED_CONCENTRATION,
    NOMINAL_FEED_TEMPERATURE,
    NOMINAL_UA_W_PER_K,
    REGIMES,
    STIFFNESS_PROBE_METHOD,
    VOLUME_M3,
    config_hash,
    config_payload,
)


# =====================================================================
# Environment — recorded, never auto-harvested into provenance identity
# =====================================================================

def resolve_source_commit() -> str:
    """The revision that is actually executing, resolved at the EXPERIMENT layer.

    Deliberately here and not in the Scientific Core. The core's provenance
    module collects nothing on its own — auto-harvesting repository or machine
    state would be a privacy problem and a determinism problem — so the caller
    supplies it, and this experiment is the caller.

    Returns a sentinel rather than raising when the revision cannot be
    determined (no git, a tarball export, a dirty detached state). A provenance
    record that honestly says "unknown" is worth more than one that fails the
    run, and far more than one that quietly substitutes some other commit —
    which is the defect this function exists to prevent.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    revision = completed.stdout.strip()
    if completed.returncode != 0 or not revision:
        return "unknown"
    return revision


def environment() -> dict[str, str]:
    """Facts that could change a floating-point result, and nothing else.

    Deliberately no hostname, username or path: those are a privacy problem and
    a determinism problem, and the core's provenance module refuses to collect
    them for exactly that reason.
    """
    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "platform": platform.system(),
        "machine": platform.machine(),
    }


# =====================================================================
# Failure classification against the preregistered matrix
# =====================================================================

def classify(result) -> str:
    """Which of the preregistered cases A-E this outcome is.

    Reads only the contract surface — convergence state, the validation report
    and whether metrics were extracted — because the point of the exercise is
    whether that surface is sufficient.
    """
    convergence = result.convergence.value
    has_metrics = bool(result.values)
    if convergence == "max_iterations":
        return "A_solver_execution_failure"
    if convergence in ("failed",):
        return "A_solver_execution_failure"
    if convergence in ("not_converged", "diverged"):
        return "B_numerical_non_convergence"
    if convergence in ("converged", "not_applicable"):
        if not has_metrics:
            return "A_solver_execution_failure"
        if not result.is_usable:
            return "D_successful_but_unusable"
        return "E_valid_result"
    return "unclassified"


# =====================================================================
# The regimes
# =====================================================================

def run_regime(spec, *, source_commit: str) -> dict[str, Any]:
    run = spec.build()
    problem = build_cstr_problem(run, problem_id=f"k1-{spec.regime_id}")
    result = solve_reactor(
        run,
        run_id=f"k1-{spec.regime_id}",
        solver=CSTRSolver(),
        problem=problem,
        # The revision that ran, NOT the Core baseline. Passing BASE_COMMIT
        # here was the original defect: it pointed provenance at a commit that
        # predates this solver.
        source_commit=source_commit,
        core_baseline_commit=BASE_COMMIT,
        environment=environment(),
    )
    numerics = dict(result.metadata.get("numerics", {}))

    row: dict[str, Any] = {
        "regime_id": spec.regime_id,
        "name": spec.name,
        "category": spec.category,
        "failure_case_declared": spec.failure_case,
        # --- identity and provenance ---
        "solver_id": result.solver.solver_id,
        "solver_version": result.solver.version,
        "solver_backend": result.solver.backend,
        "integration_method": run.integration.method,
        "provenance_run_id": result.provenance.run_id,
        "physics_fingerprint": run.physics_fingerprint(),
        "problem_id": result.problem_id,
        "models": [list(m) for m in result.models],
        # --- outcome ---
        "convergence_state": result.convergence.value,
        "is_usable": result.is_usable,
        "validation_status": result.validation_status.value,
        "attained_levels_per_solve": sorted(
            level.value for level in result.attained_levels
        ),
        "failure_classification": classify(result),
        "warnings": list(result.warnings),
        "validation_checks": [
            {
                "name": c.name,
                "outcome": c.outcome.value,
                "establishes": c.establishes.value if c.establishes else None,
                "detail": c.detail,
            }
            for c in result.validation.checks
        ],
        # --- work and cost ---
        "rhs_evaluations": numerics.get("rhs_evaluations"),
        "scipy_nfev": numerics.get("scipy_nfev"),
        "scipy_njev": numerics.get("scipy_njev"),
        "scipy_nlu": numerics.get("scipy_nlu"),
        "accepted_steps": numerics.get("accepted_steps"),
        "wall_seconds_telemetry": result.metadata.get("wall_seconds_telemetry"),
        "fraction_of_horizon_completed": numerics.get(
            "fraction_of_horizon_completed"
        ),
        "outcome_detail": numerics.get("outcome"),
        # --- numerical declaration ---
        "rtol": run.integration.rtol,
        "atol_concentration": run.integration.atol_concentration,
        "atol_temperature": run.integration.atol_temperature,
        "rhs_budget": run.integration.max_rhs_evaluations,
        # --- physical state ---
        "min_concentration_mol_per_m3": numerics.get(
            "min_concentration_mol_per_m3"
        ),
        "max_temperature_k": numerics.get("max_temperature_k"),
        "adiabatic": run.operation.is_adiabatic,
        "adiabatic_rise_k": run.adiabatic_rise_k,
        "residence_time_s": run.operation.residence_time_s,
        "gamma_per_s": run.gamma_per_s,
    }

    # --- the reported metrics, with their units ---
    row["values"] = {
        name: {
            "magnitude": quantity.magnitude,
            "units": quantity.units,
        }
        for name, quantity in sorted(result.values.items())
    }
    row["uncertainty_kinds"] = {
        name: result.uncertainty_of(name).kind.value for name in result.values
    }

    # --- provenance completeness, checked rather than assumed ---
    row["provenance"] = {
        "software_version": result.provenance.software_version,
        # The executing revision. Distinct from the Core baseline beside it.
        "git_commit": result.provenance.git_commit,
        "source_commit": result.provenance.git_commit,
        "core_baseline_commit": result.provenance.metadata.get(
            "core_baseline_commit"
        ),
        "models": [list(m) for m in result.provenance.models],
        "solvers": [list(s) for s in result.provenance.solvers],
        "input_names": sorted(result.provenance.inputs),
        "input_units": {
            name: quantity.units
            for name, quantity in sorted(result.provenance.inputs.items())
        },
        "tolerances": dict(result.provenance.tolerances),
        "environment": dict(result.provenance.environment),
        "assumption_count": len(result.provenance.assumptions),
    }

    # --- the verification gate ---
    if spec.run_verification_gate and result.values:
        gate = run_verification_gate(
            run,
            run_id_prefix=f"k1-{spec.regime_id}-gate",
            cross_method=CROSS_METHOD,
        )
        row["gate"] = gate.to_dict()
        row["attained_levels_gate"] = [
            level.value for level in gate.levels_earned
        ]
        row["tolerance_ladder_final_relative_change"] = (
            gate.rungs[-1].max_relative_change if gate.rungs else None
        )
        row["invariant_max_relative_error"] = gate.invariant_max_rel_error
        row["steady_state_relative_error"] = gate.steady_state_rel_error
        row["steady_states_found"] = len(gate.steady_states_found)
        row["cross_method_max_relative_difference"] = (
            gate.cross_method_max_rel_difference
        )
    else:
        row["gate"] = None
        row["attained_levels_gate"] = []
        row["tolerance_ladder_final_relative_change"] = None
        row["invariant_max_relative_error"] = None
        row["steady_state_relative_error"] = None
        row["steady_states_found"] = None
        row["cross_method_max_relative_difference"] = None

    # --- the stiffness measurement ---
    if spec.measure_stiffness:
        measurement = measure_stiffness(
            run,
            explicit_method=STIFFNESS_PROBE_METHOD,
            run_id_prefix=f"k1-{spec.regime_id}-stiff",
        )
        row["stiffness"] = measurement.to_dict()
        row["stiffness_work_ratio"] = measurement.work_ratio
    else:
        row["stiffness"] = None
        row["stiffness_work_ratio"] = None

    # --- prediction scoring, done here so it cannot drift ---
    row["prediction"] = {
        "convergence": spec.predicted_convergence,
        "usable": spec.predicted_usable,
        "levels": list(spec.predicted_levels),
        "stiffness_ratio_band": (
            list(spec.stiffness_ratio_band)
            if spec.stiffness_ratio_band
            else None
        ),
        "note": spec.prediction_note,
    }
    band_ok = True
    if spec.stiffness_ratio_band and row["stiffness_work_ratio"] is not None:
        low, high = spec.stiffness_ratio_band
        ratio = row["stiffness_work_ratio"]
        band_ok = (low is None or ratio >= low) and (high is None or ratio <= high)
    row["prediction_met"] = {
        "convergence": row["convergence_state"] == spec.predicted_convergence,
        "usable": row["is_usable"] == spec.predicted_usable,
        "levels": sorted(row["attained_levels_gate"])
        == sorted(spec.predicted_levels),
        "stiffness_band": band_ok,
    }
    row["prediction_all_met"] = all(row["prediction_met"].values())
    return row


# =====================================================================
# R4 — the invalid declarations
# =====================================================================

def _chemistry_kwargs() -> dict[str, Any]:
    return {
        "k0": CHEMISTRY.k0,
        "activation_energy": CHEMISTRY.activation_energy,
        "heat_of_reaction": CHEMISTRY.heat_of_reaction,
        "density": CHEMISTRY.density,
        "heat_capacity": CHEMISTRY.heat_capacity,
    }


def _operation_kwargs() -> dict[str, Any]:
    from src.engcore.scientific.units.quantity import Quantity

    return {
        "volume": Quantity(VOLUME_M3, "m**3"),
        "flow_rate": Quantity(FLOW_M3_PER_S, "m**3/s"),
        "feed_concentration": Quantity(
            NOMINAL_FEED_CONCENTRATION, "mol/m**3"
        ),
        "feed_temperature": Quantity(NOMINAL_FEED_TEMPERATURE, "kelvin"),
        "coolant_temperature": Quantity(300.0, "kelvin"),
        "ua": Quantity(NOMINAL_UA_W_PER_K, "W/K"),
        "end_time": Quantity(600.0, "second"),
    }


def run_invalid_declaration(declaration) -> dict[str, Any]:
    """Attempt the refused declaration and record exactly how it was refused."""
    from src.engcore.scientific.units.quantity import Quantity

    row: dict[str, Any] = {
        "label": declaration.label,
        "kind": declaration.kind,
        "reason": declaration.reason,
    }
    try:
        if declaration.kind == "chemistry":
            kwargs = _chemistry_kwargs()
            kwargs.update(declaration.overrides)
            ReactorChemistry(**kwargs)
        elif declaration.kind == "operation":
            kwargs = _operation_kwargs()
            kwargs.update(declaration.overrides)
            ReactorOperation(**kwargs)
        elif declaration.kind == "integration":
            kwargs: dict[str, Any] = {"method": "BDF", "rtol": 1e-8}
            kwargs.update(declaration.overrides)
            IntegrationSettings(**kwargs)
        elif declaration.kind == "run":
            kwargs = {
                "run_label": declaration.label,
                "chemistry": CHEMISTRY,
                "operation": ReactorOperation(**_operation_kwargs()),
                "initial_concentration": Quantity(
                    NOMINAL_FEED_CONCENTRATION, "mol/m**3"
                ),
                "initial_temperature": Quantity(350.0, "kelvin"),
                "integration": IntegrationSettings(),
            }
            kwargs.update(declaration.overrides)
            ReactorRun(**kwargs)
        else:  # pragma: no cover - the config enumerates the kinds
            raise AssertionError(f"unknown kind {declaration.kind!r}")
    except ReactorConfigurationError as exc:
        row["refused"] = True
        row["error_type"] = type(exc).__name__
        row["message"] = str(exc)
        row["refused_by_domain"] = True
    except Exception as exc:
        # Refused, but not by the domain's own error type. That is a weaker
        # result and is recorded as such rather than counted as a pass.
        row["refused"] = True
        row["error_type"] = type(exc).__name__
        row["message"] = str(exc)
        row["refused_by_domain"] = False
    else:
        row["refused"] = False
        row["error_type"] = None
        row["message"] = "ACCEPTED — the envelope did not refuse it"
        row["refused_by_domain"] = False
    return row


# =====================================================================
# Direct exercise of the states no regime produces
# =====================================================================

def probe_step_size_collapse() -> dict[str, Any]:
    """Drive case B directly, since no preregistered regime reaches it.

    WHY NO REGIME REACHES IT, AND WHY THAT IS A RESULT RATHER THAN A GAP
    ---------------------------------------------------------------------
    The CSTR system is globally bounded. As T grows, ``exp(-E/(R T))``
    saturates at ``k0``, so the reaction rate cannot outrun the flow and
    cooling terms; and the reactant is consumed, which removes the heat
    source. There is no finite-time singularity anywhere in the model, so no
    parameter choice inside the validity envelope can make the step size
    collapse. Manufacturing a regime that "produced" case B would therefore be
    a fabrication, and the preregistration says so in advance.

    What is exercised here is the ADAPTER's classification, not the reactor.
    A genuine finite-time singularity is injected into the right-hand side —
    ``dT/dt += T**2``, the Riccati blowup, whose solution reaches infinity at
    a finite time — for which no step size can satisfy the error test. This is
    a property of the injected equation, not a corrupted output: the adapter
    receives an honestly unintegrable problem and is asked what it says about
    it.

    The earlier 1.0.0 apparatus used a discontinuous sign flip instead and did
    NOT produce collapse: SciPy ground the step size down and kept going until
    the evaluation budget ran out, which the adapter correctly reported as
    MAX_ITERATIONS. See this package's version history.
    """
    from src.engcore.domains.kinetics.cstr.problem import build_cstr_problem
    from src.engcore.domains.kinetics.cstr.solver import CSTRSolver as Solver

    import numpy as np

    from .k1_config import regime

    spec = regime("R1")
    run = spec.build()
    solver = Solver()
    problem = build_cstr_problem(run, problem_id="k1-probe-collapse")
    solver.bind_run(run, problem.problem_id)
    prepared = solver.prepare(problem)

    system = prepared.payload
    original = system.rhs

    def singular(t, y):
        """The reactor's own right-hand side plus a finite-time blowup."""
        value = original(t, y)
        return value + np.array([0.0, float(y[1]) ** 2], dtype=np.float64)

    object.__setattr__(system, "rhs", singular)
    raw = solver.solve(prepared)
    report = solver.validate(prepared, raw)
    return {
        "purpose": (
            "direct exercise of the adapter's non-convergence classification "
            "against an injected finite-time singularity; NOT a scientific "
            "regime and not a statement about any reactor"
        ),
        "injected_term": "dT/dt += T**2 (Riccati blowup, singular in finite time)",
        "why_not_a_regime": (
            "the CSTR system is globally bounded — the Arrhenius factor "
            "saturates at k0 and the reactant is consumed — so no admissible "
            "parameter choice produces step-size collapse"
        ),
        "convergence_state": raw.convergence.value,
        "outcome": raw.diagnostics.get("outcome"),
        "scipy_status": raw.diagnostics.get("scipy_status"),
        "scipy_message": raw.diagnostics.get("scipy_message"),
        "partial_trajectory_preserved": bool(
            raw.diagnostics.get("partial_time_s")
        ),
        "reached_time_s": raw.diagnostics.get("reached_time_s"),
        "metrics_extracted": bool(
            Solver().extract_metrics(prepared, raw)
        ),
        "validation_status": report.status.value,
        "attained_levels": sorted(l.value for l in report.attained_levels),
    }


# =====================================================================
# The study
# =====================================================================

def run_k1() -> dict[str, Any]:
    source_commit = resolve_source_commit()
    rows = [run_regime(spec, source_commit=source_commit) for spec in REGIMES]
    invalid = [run_invalid_declaration(d) for d in INVALID_DECLARATIONS]
    collapse = probe_step_size_collapse()

    by_id = {row["regime_id"]: row for row in rows}
    cases_seen = {row["failure_classification"] for row in rows}
    cases_seen.add(collapse["convergence_state"])

    # --- acceptance scoring -------------------------------------------
    r1, r2, r3 = by_id["R1"], by_id["R2"], by_id["R3"]
    r5, r7, r8 = by_id["R5"], by_id["R7"], by_id["R8"]
    r6a, r6b = by_id["R6a"], by_id["R6b"]

    gate_levels = {
        row["regime_id"]: set(row["attained_levels_gate"]) for row in rows
    }
    per_solve_levels = {
        row["regime_id"]: set(row["attained_levels_per_solve"]) for row in rows
    }

    a1 = (
        r1["convergence_state"] == "converged"
        and r1["is_usable"]
        and {v["units"] for v in r1["values"].values()}
        >= {"mole / meter ** 3", "kelvin", "second", "dimensionless"}
    )
    a2 = (
        r2["prediction_met"]["stiffness_band"]
        and r3["prediction_met"]["stiffness_band"]
        and r1["prediction_met"]["stiffness_band"]
    )
    a3 = (
        r5["convergence_state"] == "max_iterations"
        and not r5["values"]
        and not r5["is_usable"]
        and r5["outcome_detail"] == "rhs_budget_exhausted"
    )
    a4 = (
        r8["convergence_state"] == "converged"
        and not r8["is_usable"]
        and r7["convergence_state"] == "converged"
        and r7["is_usable"]
        and not gate_levels["R7"]
    )
    a5 = all(row["refused"] and row["refused_by_domain"] for row in invalid)
    a6 = any("analytically_verified" in v for v in gate_levels.values()) and any(
        "cross_solver_validated" in v for v in gate_levels.values()
    )
    a7_map = {
        "A": any(
            row["failure_classification"] == "A_solver_execution_failure"
            for row in rows
        ),
        "B": collapse["convergence_state"] in ("not_converged", "diverged"),
        "C": all(row["refused"] for row in invalid),
        "D": any(
            row["failure_classification"] == "D_successful_but_unusable"
            for row in rows
        )
        and not gate_levels["R7"]
        and r7["is_usable"],
        "E": any(
            row["failure_classification"] == "E_valid_result" for row in rows
        ),
    }
    a7 = all(a7_map.values())
    a8 = all(
        "numerically_converged" not in levels
        for levels in per_solve_levels.values()
    )
    a9 = (
        r6a["values"]
        and r6b["values"]
        and abs(
            r6a["values"]["T:final"]["magnitude"]
            - r6b["values"]["T:final"]["magnitude"]
        )
        < 1.0e-6
        and (r6a["steady_states_found"] or 0) == 3
    )
    a10 = all(
        row["provenance"]["models"]
        and row["provenance"]["solvers"]
        and row["provenance"]["tolerances"]
        and row["provenance"]["input_names"]
        and row["physics_fingerprint"]
        for row in rows
    )

    acceptance = {
        "A1": bool(a1),
        "A2": bool(a2),
        "A3": bool(a3),
        "A4": bool(a4),
        "A5": bool(a5),
        "A6": bool(a6),
        "A7": bool(a7),
        "A8": bool(a8),
        "A9": bool(a9),
        "A10": bool(a10),
    }

    predictions_met = {row["regime_id"]: row["prediction_all_met"] for row in rows}

    return {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": K1_VERSION,
        # The frozen Core revision this builds on. Context, not execution.
        "base_commit": BASE_COMMIT,
        "core_baseline_commit": BASE_COMMIT,
        # The revision that actually produced the numbers below.
        "source_commit": source_commit,
        "config": config_payload(),
        "config_hash": config_hash(),
        "environment": environment(),
        "regimes": rows,
        "invalid_declarations": invalid,
        "step_size_collapse_probe": collapse,
        "failure_cases_represented": a7_map,
        "acceptance": acceptance,
        "acceptance_all_met": all(acceptance.values()),
        "predictions_met": predictions_met,
        "predictions_all_met": all(predictions_met.values()),
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "falsification_criteria": list(FALSIFICATION_CRITERIA),
    }


# =====================================================================
# Artifacts
# =====================================================================

def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append

    add("# K1 — Kinetics/CSTR Solver Admission Gate: results")
    add("")
    add(f"- experiment version: `{result['experiment_version']}`")
    add(f"- base commit: `{result['base_commit']}`")
    add(f"- preregistration hash: `{result['config_hash']}`")
    env = result["environment"]
    add(
        f"- environment: python {env['python']}, numpy {env['numpy']}, "
        f"scipy {env['scipy']}, {env['platform']}/{env['machine']}"
    )
    add("")

    add("## Regime results")
    add("")
    add(
        "| regime | category | convergence | usable | case | gate levels | "
        "nfev | wall s | T_final K | X | ref error |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for row in result["regimes"]:
        values = row["values"]
        t_final = (
            f"{values['T:final']['magnitude']:.4f}" if "T:final" in values else "—"
        )
        conversion = (
            f"{values['conversion:final']['magnitude']:.5f}"
            if "conversion:final" in values
            else "—"
        )
        reference = row["steady_state_relative_error"]
        if reference is None:
            reference = row["invariant_max_relative_error"]
        reference_text = "—" if reference is None else f"{reference:.2e}"
        wall = row["wall_seconds_telemetry"]
        add(
            f"| {row['regime_id']} | {row['category']} | "
            f"`{row['convergence_state']}` | {row['is_usable']} | "
            f"{row['failure_classification'].split('_')[0]} | "
            f"{', '.join(row['attained_levels_gate']) or '—'} | "
            f"{row['rhs_evaluations']} | "
            f"{wall:.3f} | {t_final} | {conversion} | {reference_text} |"
        )
    add("")

    add("## Stiffness, measured rather than asserted")
    add("")
    add("| regime | BDF nfev | RK45 nfev | ratio | band | in band | probe outcome |")
    add("|---|---|---|---|---|---|---|")
    for row in result["regimes"]:
        stiffness = row["stiffness"]
        if not stiffness:
            continue
        band = row["prediction"]["stiffness_ratio_band"]
        band_text = (
            f"[{band[0] if band[0] is not None else '-'}, "
            f"{band[1] if band[1] is not None else '-'}]"
        )
        ratio = f"{stiffness['work_ratio']:.1f}"
        if stiffness["work_ratio_is_lower_bound"]:
            ratio = f"≥ {ratio}"
        add(
            f"| {row['regime_id']} | {stiffness['stiff_evaluations']} | "
            f"{stiffness['explicit_evaluations']} | {ratio} | {band_text} | "
            f"{row['prediction_met']['stiffness_band']} | "
            f"`{stiffness['explicit_outcome']}` |"
        )
    add("")

    add("## Validity envelope: declarations that were refused")
    add("")
    refused = sum(1 for d in result["invalid_declarations"] if d["refused"])
    by_domain = sum(
        1 for d in result["invalid_declarations"] if d["refused_by_domain"]
    )
    add(
        f"{refused} of {len(result['invalid_declarations'])} refused; "
        f"{by_domain} by the domain's own error type, before any solve."
    )
    add("")
    for declaration in result["invalid_declarations"]:
        mark = "✓" if declaration["refused_by_domain"] else "✗"
        add(f"- {mark} `{declaration['label']}` — {declaration['reason']}")
    add("")

    add("## Failure semantics: the five cases")
    add("")
    for case, seen in result["failure_cases_represented"].items():
        add(f"- case {case}: {'represented' if seen else 'NOT REPRESENTED'}")
    add("")
    probe = result["step_size_collapse_probe"]
    add(
        f"Case B is exercised directly against the adapter rather than by a "
        f"regime: `{probe['convergence_state']}`, partial trajectory preserved "
        f"= {probe['partial_trajectory_preserved']}, metrics extracted = "
        f"{probe['metrics_extracted']}."
    )
    add("")

    add("## Acceptance criteria")
    add("")
    for index, criterion in enumerate(result["acceptance_criteria"], start=1):
        key = f"A{index}"
        add(f"- **{key}** {'PASS' if result['acceptance'][key] else 'FAIL'} — {criterion}")
    add("")

    add("## Preregistered predictions")
    add("")
    for row in result["regimes"]:
        met = row["prediction_met"]
        status = "met" if row["prediction_all_met"] else "MISSED"
        add(
            f"- **{row['regime_id']}** {status} "
            f"(convergence {met['convergence']}, usable {met['usable']}, "
            f"levels {met['levels']}, stiffness band {met['stiffness_band']})"
        )
    add("")

    add("## What this does not show")
    add("")
    for item in result["config"]["non_goals"]:
        add(f"- {item}")
    return "\n".join(lines)


def main() -> int:
    result = run_k1()
    root = Path(__file__).resolve().parent

    (root / "k1_config_frozen.json").write_text(
        json.dumps(
            {
                "config": result["config"],
                "config_hash": result["config_hash"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "k1_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "k1_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if result["acceptance_all_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
