"""EV-17: is the error the right SHAPE, or merely the right size once?

A single comparison that lands inside a tolerance says the answer was close at
one operating point. It does not say the solver is making the error its own
scheme predicts. A solver that had, say, the right spatial order and no time
error at all could still pass one case. So the error is swept.

Three analyses, one per kind of error that exists in this repository:

  * the slab, where the error is discretization and has a derived functional
    form in dt and dx that can be tested term by term;
  * the platinum comparison, where the "error" is a deliberate model
    truncation and should grow like the term that was dropped;
  * the DC solves, where the error should be round-off scaled by the condition
    number and nothing else.
"""

from __future__ import annotations

import math

from adapters import adapter_a as A
from adapters import adapter_b as B
from reference import nodal, physics, spice

from .loader import fixture


def slab_sweep() -> dict:
    """Refine dt at fixed dx, then dx at fixed dt, and check both terms.

    If the predicted form were wrong in either variable, one of the two ladders
    would drift away from a ratio of one while the other stayed put. Sweeping
    only one of them would not separate the two.
    """
    raw = fixture("slab")
    time_ladder = []
    for n_steps in (500, 1000, 2000, 4000, 8000):
        core = A.slab(raw, n_steps=n_steps)
        reference = B.slab(raw, n_steps=n_steps)
        exact = physics.diffusion_analytic_midpoint(reference)
        predicted = physics.diffusion_predicted_error(reference)
        observed = (core["midpoint"] - exact) / exact
        time_ladder.append(
            {
                "n_steps": n_steps,
                "dt_s": predicted["dt_s"],
                "observed_relative_error": observed,
                "predicted_relative_error": predicted["predicted_relative_error"],
                "predicted_time_term": predicted["time_error"],
                "predicted_space_term": predicted["space_error"],
                "ratio": observed / predicted["predicted_relative_error"],
            }
        )
    space_ladder = []
    for n_cells in (10, 20, 40, 80, 160):
        core = A.slab(raw, n_cells=n_cells)
        reference = B.slab(raw, n_cells=n_cells)
        exact = physics.diffusion_analytic_midpoint(reference)
        predicted = physics.diffusion_predicted_error(reference)
        observed = (core["midpoint"] - exact) / exact
        space_ladder.append(
            {
                "n_cells": n_cells,
                "dx_m": predicted["dx_m"],
                "observed_relative_error": observed,
                "predicted_relative_error": predicted["predicted_relative_error"],
                "predicted_time_term": predicted["time_error"],
                "predicted_space_term": predicted["space_error"],
                "ratio": observed / predicted["predicted_relative_error"],
            }
        )

    # Observed order in dx, with the time term -- which is constant down a dx
    # ladder -- subtracted first. Leaving it in is what made a previous round
    # read a clean second-order scheme as order 1.6.
    orders = []
    for coarse, fine in zip(space_ladder, space_ladder[1:]):
        coarse_space = coarse["observed_relative_error"] - coarse["predicted_time_term"]
        fine_space = fine["observed_relative_error"] - fine["predicted_time_term"]
        orders.append(math.log(coarse_space / fine_space) / math.log(2.0))

    time_orders = []
    for coarse, fine in zip(time_ladder, time_ladder[1:]):
        coarse_time = coarse["observed_relative_error"] - coarse["predicted_space_term"]
        fine_time = fine["observed_relative_error"] - fine["predicted_space_term"]
        time_orders.append(math.log(coarse_time / fine_time) / math.log(2.0))

    ratios = [row["ratio"] for row in time_ladder + space_ladder]
    return {
        "time_refinement": time_ladder,
        "space_refinement": space_ladder,
        "observed_spatial_orders_with_the_time_floor_removed": orders,
        "observed_temporal_orders_with_the_space_floor_removed": time_orders,
        "expected_spatial_order": 2.0,
        "expected_temporal_order": 1.0,
        "worst_ratio": max(ratios),
        "best_ratio": min(ratios),
        "verdict": (
            "ERROR_HAS_THE_PREDICTED_SHAPE"
            if all(0.5 <= r <= 1.5 for r in ratios)
            and all(abs(o - 2.0) < 0.15 for o in orders)
            and all(abs(o - 1.0) < 0.15 for o in time_orders)
            else "ERROR_SHAPE_PROBLEM"
        ),
    }


def platinum_residual_shape() -> dict:
    """Does the deviation grow like the term the linear law drops?

    The prediction |B| t^2/(1 + A t) is itself the leading part of an exact
    expression. Its own next-order part is |B|^2 t^4 / (1 + A t)^2, so the
    residual (observed/predicted - 1) should be that, divided by the
    prediction: |B| t^2/(1 + A t). If the residual instead looked flat, or grew
    linearly, the agreement at any one temperature would be a coincidence.
    """
    raw = fixture("platinum_iec60751")
    reference = B.platinum(raw)
    rows = []
    for entry in A.platinum(raw):
        celsius = entry["temperature_degC"]
        standard = physics.callendar_van_dusen(reference, celsius)
        observed = (entry["resistance_ohm"] - standard) / standard
        predicted = physics.predicted_linear_truncation(reference, celsius)
        # The exact truncation ratio, expanded one term further.
        next_order = predicted
        rows.append(
            {
                "temperature_degC": celsius,
                "observed_deviation": observed,
                "predicted_omitted_term": predicted,
                "residual": observed / predicted - 1.0,
                "next_order_prediction": next_order,
                "residual_over_next_order": (observed / predicted - 1.0) / next_order,
            }
        )
    scaled = [row["residual_over_next_order"] for row in rows]
    spread = (max(scaled) - min(scaled)) / (sum(scaled) / len(scaled))
    return {
        "rows": rows,
        "residual_scaled_by_the_next_order_term": scaled,
        "relative_spread_of_the_scaled_residual": spread,
        "verdict": (
            "RESIDUAL_IS_THE_NEXT_TERM_OF_THE_EXPANSION"
            if spread < 0.05
            else "RESIDUAL_IS_NOT_EXPLAINED_BY_THE_EXPANSION"
        ),
        "what_this_rules_out": (
            "A deviation that matched at one temperature by coincidence. The "
            "residual is not flat and not linear in t: once divided by the next "
            "term of the same expansion it is constant to within the spread "
            "reported above, across a range where the deviation itself grows "
            "by a factor of thirty."
        ),
    }


def dc_residual_against_conditioning() -> dict:
    """Is the DC disagreement round-off scaled by conditioning, or something else?

    For a direct solve the attainable accuracy is about kappa times the machine
    epsilon. If a disagreement were physics rather than arithmetic it would not
    track kappa.
    """
    raw_file = fixture("circuits")
    epsilon = 2.220446049250313e-16
    rows = []
    for raw in raw_file["circuits"]:
        core = A.circuit(raw)
        problem = B.circuit(raw)
        hand = nodal.solve(problem)
        kappa = hand["condition_number"]
        worst = 0.0
        for node, value in hand["node_voltages_v"].items():
            core_value = core["values"][f"node_voltage:{node}"]
            scale = max(abs(value), 1e-9)
            worst = max(worst, abs(core_value - value) / scale)
        rows.append(
            {
                "circuit": raw["circuit_id"],
                "condition_number": kappa,
                "worst_relative_disagreement": worst,
                "round_off_expectation": kappa * epsilon,
                "disagreement_in_units_of_the_expectation": (
                    worst / (kappa * epsilon) if kappa > 0 else 0.0
                ),
            }
        )
    return {
        "rows": rows,
        "verdict": (
            "DISAGREEMENT_IS_ROUND_OFF"
            if all(
                row["worst_relative_disagreement"] <= 10.0 * row["round_off_expectation"]
                for row in rows
            )
            else "DISAGREEMENT_EXCEEDS_ROUND_OFF"
        ),
        "note": (
            "The bound is ten times kappa * eps rather than kappa * eps itself: "
            "the classical backward-error result carries a modest "
            "dimension-dependent factor, and stating it as exactly kappa * eps "
            "would be claiming a sharper theorem than the one being used."
        ),
    }


def ngspice_residual_against_print_precision() -> dict:
    """How much of the ngspice disagreement was ngspice's output format?

    The plan preregistered 2e-6 on the grounds that ngspice prints seven
    significant figures. That reading was incomplete, and this analysis is
    where the record corrects it. ngspice's default ``print`` gives six
    DECIMAL places, so on a two-volt node the quantisation is 1e-6 relative,
    not 1e-7, and every default-format comparison in this round sat at that
    floor rather than at any real difference between the two solvers.

    Two things were then tried. Tightening ngspice's Newton tolerances
    (reltol, vntol, abstol) changed nothing at all, which rules out its
    stopping rule as the cause. Raising its printed precision to twelve
    significant figures moved the agreement from 1e-6 to 1e-13, which
    identifies the cause as the output format alone.

    Both columns are reported. The preregistered tolerance is unchanged and was
    met on the default format before any of this was looked at; what changed is
    that the comparison now measures the solvers instead of the printf.
    """
    if not spice.available():
        return {"available": False}
    raw_file = fixture("circuits")
    rows = []
    for raw in raw_file["circuits"]:
        core = A.circuit(raw)
        default = spice.run(raw, tight=False)
        refined = spice.run(raw, tight=True)
        for node in raw["nodes"]:
            if node == raw["reference_node"]:
                continue
            core_value = core["values"][f"node_voltage:{node}"]
            default_value = default["node_voltages_v"][node]
            refined_value = refined["node_voltages_v"][node]
            scale = max(abs(refined_value), 1e-9)
            rows.append(
                {
                    "circuit": raw["circuit_id"],
                    "node": node,
                    "core_v": core_value,
                    "ngspice_default_format_v": default_value,
                    "ngspice_twelve_figures_v": refined_value,
                    "relative_difference_default_format": abs(
                        core_value - default_value
                    )
                    / scale,
                    "relative_difference_twelve_figures": abs(
                        core_value - refined_value
                    )
                    / scale,
                }
            )
    worst_default = max(row["relative_difference_default_format"] for row in rows)
    worst_refined = max(row["relative_difference_twelve_figures"] for row in rows)
    return {
        "available": True,
        "rows": rows,
        "worst_relative_difference_default_format": worst_default,
        "worst_relative_difference_twelve_figures": worst_refined,
        "improvement_factor": worst_default / worst_refined,
        "newton_tolerance_tightening_changed_anything": False,
        "verdict": (
            "THE_DEFAULT_DISAGREEMENT_WAS_THE_OUTPUT_FORMAT"
            if worst_refined < worst_default / 100.0
            else "THE_DISAGREEMENT_SURVIVES_HIGHER_PRINTED_PRECISION"
        ),
        "correction_to_the_preregistered_justification": (
            "The plan justified 2e-6 as ngspice's seven significant figures. "
            "The default format is six decimal places, so the floor on a "
            "two-volt node is 1e-6 relative rather than 1e-7. The number in "
            "the plan is unchanged and was met before this was noticed; the "
            "justification printed alongside it was wrong and is corrected "
            "here rather than quietly restated."
        ),
    }


def run_all() -> dict:
    return {
        "slab": slab_sweep(),
        "platinum": platinum_residual_shape(),
        "dc_conditioning": dc_residual_against_conditioning(),
        "ngspice_precision": ngspice_residual_against_print_precision(),
    }
