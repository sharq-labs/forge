"""The frozen protocol for the Sprint 3 battery + thermal flagship.

Written and committed BEFORE any parameter was fitted and before any model
scored anything. Everything a later step is allowed to decide is decided here:
which trajectories are selected, how they split, what is fitted, what the model
claims, what agreement means, and what the holdout gate is.

    python benchmarks/battery_thermal_flagship_s3/harness/prereg.py

writes ``evidence/PREREGISTRATION.json`` and ``evidence/DATA_SELECTION.json``.
Both are deterministic functions of ``evidence/INVENTORY.json`` and the
constants in this file.
"""

from __future__ import annotations

import json
import os
import statistics
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")

CAMPAIGN_ID = "battery.electrothermal.flagship.s3"
CAMPAIGN_VERSION = "3"

#: Amendments to this protocol, each recorded with the commit the previous
#: version was frozen at, what changed, and why. An amendment is only honest
#: while nothing has been fitted or scored, which is the state each one below
#: was made in.
AMENDMENTS: tuple[dict[str, Any], ...] = (
    {
        "from_version": "1",
        "to_version": "2",
        "frozen_at_commit": "1297648e",
        "made_before": "any parameter was fitted and any model scored anything",
        "change": (
            "capacity is no longer a fitted parameter. The charge state is "
            "defined on a declared constant basis, the manufacturer's 2 Ah "
            "rating, so z = 1 - q / 2 Ah with q the measured charge removed"
        ),
        "why": (
            "the open-circuit voltage authority is a curve against charge state, "
            "and deriving it needed a charge-state axis. With capacity fitted, "
            "that axis would depend on a parameter the authority is an input to "
            "-- the curve would be derived from an axis set by a fit that has "
            "not happened yet. Declaring the basis removes the circularity, and "
            "it costs nothing that is scored: state of charge is not "
            "independently validated by this source either way"
        ),
        "consequence": (
            "seven fitted parameters instead of eight. A cell that delivers "
            "less than its rating reaches its cutoff at a charge state above "
            "zero rather than at zero, and that difference now shows up as a "
            "voltage residual at a common charge state, which is the "
            "comparison that carries physical meaning"
        ),
    },
    {
        "from_version": "2",
        "to_version": "3",
        "frozen_at_commit": "709eb084",
        "made_before": (
            "the locked holdout was opened. Everything behind this amendment is "
            "a calibration diagnostic or a model-independent comparison of "
            "measurements; no holdout case was read, scored or looked at"
        ),
        "change": (
            "three declarations: the applicability floor on charge state, the "
            "unit a parameter set is fitted over, and a full-charge admission "
            "screen"
        ),
        "why": {
            "charge_state_floor": (
                "the open-circuit voltage authority's own interquartile scatter "
                "across calibration pairs rises from about 23 mV in the middle "
                "of the charge axis to 127-139 mV at its three lowest knots. "
                "Below the first knot whose scatter is inside the frozen 50 mV "
                "acceptance tolerance, the authority disagrees with itself by "
                "more than the campaign's own definition of agreement, so the "
                "model is not claimed there. A separate, model-free check "
                "agrees: the longest measured relaxations at the end of "
                "discharge sit as much as 370 mV away from the curve below "
                "z = 0.23, in both directions"
            ),
            "parameter_unit": (
                "the thermal conductance is a property of the cell's boundary "
                "-- its fixture, mounting and air path -- and not of its "
                "chemistry. Driving the lumped body with the dissipation the "
                "MEASURED voltage implies, so that no electrical parameter is "
                "involved at all, fits every calibration cell to under 1 K and "
                "returns hA = 0.039-0.050 W/K for the cells in one set of test "
                "campaigns and 0.103-0.121 W/K for those in another: a factor "
                "of 2.4 with no overlap. One value fits neither. The ohmic and "
                "polarization parameters are likewise properties of an "
                "individual aged cell, and a batch of sibling cells cycled "
                "together under one protocol is the smallest unit over which "
                "one set is defensible. A parameter set is therefore fitted "
                "per experiment group, on that group's calibration cells, and "
                "applied to that group's independent cells -- which is a real "
                "transfer test between different physical cells, not a "
                "per-cell refit"
            ),
            "full_charge_screen": (
                "the campaign declares the initial charge state to be full, on "
                "the authority of the CC-CV charge protocol. One calibration "
                "cell begins a discharge at rest at 4.053 V, which the "
                "open-circuit voltage authority places at a charge state of "
                "0.88, not 1. Asserting a full-charge initial condition for a "
                "cell whose own open-circuit voltage says otherwise would "
                "charge the model for an error in the initial condition"
            ),
        },
        "consequence": (
            "a narrower and more honest claim. The flagship is not claimed "
            "below the charge-state floor, cases below it are scored as "
            "outside declared applicability rather than as failures, a group "
            "with no independent cell contributes calibration only and "
            "produces no claim, and trajectories that did not start full are "
            "not admitted"
        ),
        "what_was_not_changed": (
            "no acceptance threshold, no Gate A criterion, no split assignment "
            "and no cell's split membership"
        ),
    },
)
DATASET_ID = "nasa.pcoe.battery_aging"
DATASET_VERSION = "2022-09-18"

# ---------------------------------------------------------------------------
# 1. SELECTION. What the flagship is about, decided on operating conditions and
#    measurement quality only. No model exists yet.
# ---------------------------------------------------------------------------

#: The ambient band the flagship claims. Chosen because the 1-RC form carries no
#: temperature-dependent capacity, and the archive's 4 degC and 43-44 degC runs
#: deliver visibly less charge for the same cell -- a low-temperature capacity
#: effect this model does not represent. Rather than approximate it, those runs
#: are declared OUTSIDE and the guardrail is tested on them.
INSIDE_AMBIENT_C = (20.0, 30.0)

#: A cell temperature well above ambient is still INSIDE: the cell self-heats
#: to about 55 degC inside this band and that is the evidence the Arrhenius
#: resistance terms are identified from.
INSIDE_CELL_TEMPERATURE_C = (20.0, 60.0)

#: Rate band the flagship claims, as an absolute current on a 2 Ah cell.
INSIDE_CURRENT_A = (0.5, 4.5)

#: Ageing is out of scope for Sprint 3, so the claim is early life. The bound is
#: a cycle index, which is known before a discharge runs -- not a delivered
#: capacity, which is a measurement of the very discharge being predicted.
INSIDE_MAX_CYCLE_INDEX = 40

#: The charge state below which the flagship is not claimed. It is the lowest
#: knot of the open-circuit voltage authority whose interquartile scatter across
#: calibration pairs is inside the frozen acceptance tolerance for voltage.
#: Derived from the authority's own record, never from a model's performance.
APPLICABILITY_CHARGE_STATE_FLOOR = 0.2737

#: How far a trajectory's first rest voltage may sit from the authority's
#: measured full-charge anchor and still support the declared full-charge
#: initial condition. One acceptance tolerance: if the cell's own open-circuit
#: voltage disagrees with "full" by more than the campaign's definition of
#: agreement, the initial condition is not supported.
FULL_CHARGE_BAND_V = 0.050

#: The authority's measured relaxed voltage at full charge, in volt. Carried
#: here so the screen is reproducible from this file plus the inventory; the
#: flagship module holds the same number as the curve's top knot and a test
#: pins the two together.
FULL_CHARGE_ANCHOR_V = 4.188513

#: Declared-OUTSIDE bands, used to test that the guardrail refuses rather than
#: to test the model. A case here that the model answers is recorded and never
#: scored; a case here it declines is a correct refusal.
OUTSIDE_AMBIENT_C = ((-40.0, 15.0), (35.0, 120.0))

#: Cycles taken per cell per condition. Fixed positions, not a random sample,
#: and spread across the early-life range so that within-cell drift is visible.
CYCLE_POSITIONS = (1, 8, 16, 24, 32, 40)

#: One case per this many measured instants. The first sample of a trajectory is
#: the initial condition the model is handed and is never scored.
SAMPLE_STRIDE = 4

# ---------------------------------------------------------------------------
# 2. REPLICATE-BASED THERMAL SCREEN. Model-independent: it compares a cell only
#    with other cells measured at the same nominal condition.
# ---------------------------------------------------------------------------

#: A condition group needs this many cells before one of them can be called an
#: outlier. With fewer, no cell is excluded and the record says the replicate
#: evidence was insufficient.
THERMAL_OUTLIER_MIN_CELLS = 3

#: A cell whose median temperature rise is outside this multiple of its
#: replicates' median is a thermal-instrumentation outlier. Its cell temperature
#: is not admitted as an observation; its terminal voltage still is, because the
#: electrical channels are unaffected.
THERMAL_OUTLIER_BAND = (0.4, 2.5)

# ---------------------------------------------------------------------------
# 3. SPLIT RULE. Outcome-blind, deterministic, and structural: the independence
#    unit is one physical cell, so no cell can be both the fit and the test.
# ---------------------------------------------------------------------------

#: Within each experiment group, cells are ordered by identifier and assigned by
#: position. Nothing about how well any cell is predicted enters this.
SPLIT_CYCLE = ("calibration", "validation", "locked_holdout", "calibration")

#: A group of three therefore contributes one cell to each split, and a group of
#: four contributes a second calibration cell. Position, not performance.

# ---------------------------------------------------------------------------
# 4. THE MODEL AND WHAT IS FITTED.
# ---------------------------------------------------------------------------

MODEL_ID = "battery.cell.electrothermal_1rc"
MODEL_VERSION = "0.1.0"

#: Seven free parameters, each identified by a distinct feature of the data.
#: Nothing else is fitted. Coulombic efficiency is fixed at 1 because the
#: flagship marches discharge and rest only; the reference temperature is fixed
#: at 298.15 K because it is a definition, not a degree of freedom; and the
#: charge-state basis is fixed at the cell's rating for the reason recorded in
#: :data:`AMENDMENTS`.
FITTED_PARAMETERS: tuple[dict[str, Any], ...] = (
    {
        "parameter_id": "ohmic_resistance_reference",
        "unit": "ohm",
        "lower": 0.005,
        "upper": 0.5,
        "initial": 0.08,
        "identified_by": "the instantaneous voltage step when the load is applied or removed",
        "prior_source": "none",
        "prior_note": "",
    },
    {
        "parameter_id": "ohmic_activation_energy",
        "unit": "joule/mole",
        "lower": -40000.0,
        "upper": 80000.0,
        "initial": 20000.0,
        "identified_by": "the drift of the ohmic step as the cell self-heats through a run",
        "prior_source": "none",
        "prior_note": "",
    },
    {
        "parameter_id": "polarization_resistance_reference",
        "unit": "ohm",
        "lower": 0.001,
        "upper": 0.5,
        "initial": 0.04,
        "initial_note": "",
        "identified_by": "the amplitude of the relaxation after the load is removed",
        "prior_source": "none",
        "prior_note": "",
    },
    {
        "parameter_id": "polarization_activation_energy",
        "unit": "joule/mole",
        "lower": -40000.0,
        "upper": 80000.0,
        "initial": 25000.0,
        "identified_by": "the drift of that amplitude with cell temperature",
        "prior_source": "none",
        "prior_note": "",
    },
    {
        "parameter_id": "polarization_capacitance",
        "unit": "farad",
        "lower": 100.0,
        "upper": 200000.0,
        "initial": 2000.0,
        "identified_by": "the shape, not the amplitude, of the relaxation tail",
        "prior_source": "none",
        "prior_note": "",
    },
    {
        "parameter_id": "thermal_capacitance",
        "unit": "joule/kelvin",
        "lower": 5.0,
        "upper": 200.0,
        "initial": 40.0,
        "identified_by": "the initial slope of the temperature rise",
        "prior_source": "literature",
        "prior_note": (
            "an 18650 cell of about 45 g at about 1 kJ/(kg K) is of order 45 J/K"
        ),
    },
    {
        "parameter_id": "thermal_conductance",
        "unit": "watt/kelvin",
        "lower": 0.01,
        "upper": 5.0,
        "initial": 0.25,
        "identified_by": "where the temperature levels off, and the cooling tail during rest",
        "prior_source": "none",
        "prior_note": "",
    },
)

#: Declared, not fitted.
FIXED_PARAMETERS = {
    "coulombic_efficiency": {
        "value": 1.0,
        "unit": "dimensionless",
        "why": (
            "the flagship marches discharge and rest only; a charge efficiency "
            "below one is a claim about charge acceptance that this campaign "
            "produces no evidence for"
        ),
    },
    "reference_temperature": {
        "value": 298.15,
        "unit": "kelvin",
        "why": "the temperature the Arrhenius reference values are defined at",
    },
    "initial_state_of_charge": {
        "value": 1.0,
        "unit": "dimensionless",
        "why": (
            "every selected trajectory begins after a CC-CV charge to 4.2 V with "
            "a 20 mA cutoff, which is the protocol's definition of full. This is "
            "a known initial condition, not a measurement of the discharge being "
            "predicted"
        ),
    },
    "initial_polarization_voltage": {
        "value": 0.0,
        "unit": "volt",
        "why": "the cell rests between the charge and the discharge",
    },
    "charge_state_basis": {
        "value": 2.0,
        "unit": "ampere_hour",
        "why": (
            "the manufacturer's rating. The charge state is z = 1 - q / 2 Ah "
            "with q the measured charge removed, so no fitted quantity defines "
            "the axis the open-circuit voltage authority is a function of"
        ),
    },
}

# ---------------------------------------------------------------------------
# 5. OCV AUTHORITY.
# ---------------------------------------------------------------------------

OCV_AUTHORITY = {
    "method": "pseudo-OCV by zero-current extrapolation across measured rates",
    "derived_from": "CALIBRATION cells only",
    "form": "tabulated, linear interpolation between declared knots",
    "knots": 21,
    "soc_interval": [0.0, 1.0],
    "temperature_condition": (
        "cells in the 20-30 degC ambient band; the authority carries no "
        "temperature axis and is not claimed to have one"
    ),
    "extrapolation_policy": (
        "refused. Outside the declared state-of-charge interval the curve "
        "returns OUTSIDE_VALIDATED_DOMAIN and the kernel propagates the refusal"
    ),
    "what_it_is_not": (
        "not an equilibrium open-circuit voltage. It is a rate-extrapolated "
        "pseudo-OCV from loaded discharge curves, and it carries the "
        "hysteresis of the discharge direction it was measured on"
    ),
}

# ---------------------------------------------------------------------------
# 6. ACCEPTANCE POLICY. Frozen here, before the holdout exists as a number.
# ---------------------------------------------------------------------------

#: The archive states no instrument accuracy for any channel. It is recorded as
#: UNKNOWN and no tolerance is derived from it; the thresholds below rest on
#: engineering relevance, which is the basis this campaign can actually defend.
SOURCE_MEASUREMENT_UNCERTAINTY = {
    "voltage": "UNKNOWN: the archive README declares no voltage accuracy",
    "current": "UNKNOWN: the archive README declares no current accuracy",
    "temperature": "UNKNOWN: the archive README declares no temperature accuracy",
    "consequence": (
        "no acceptance tolerance here is a source-reported spread, and no "
        "observation carries a SOURCE_REPORTED uncertainty. A campaign cannot "
        "invent one, so the measurement channel of the uncertainty budget "
        "stays UNKNOWN in the final report"
    ),
}

ACCEPTANCE = {
    "terminal_voltage": {
        "per_sample_tolerance_v": 0.050,
        "basis": "reviewed_acceptance",
        "rationale": (
            "50 mV is 3.3% of this cell's 4.2-2.7 V usable window. On the "
            "plateau of this chemistry a 50 mV terminal-voltage error moves a "
            "voltage-based state-of-charge estimate by roughly 2-3%, which is "
            "the resolution a pack-level estimate is specified to. It is an "
            "engineering-relevance threshold and is not a claim about the "
            "instrument, whose accuracy this source does not state"
        ),
    },
    "cell_temperature": {
        "per_sample_tolerance_k": 3.0,
        "basis": "reviewed_acceptance",
        "rationale": (
            "3 K is about one fifth of the smallest self-heating rise in the "
            "selected envelope (about 14 K at 2 A) and is the scale at which a "
            "predicted cell temperature changes a derating or cooling decision. "
            "It is an engineering-relevance threshold, not an instrument spread"
        ),
    },
}

#: GATE A. Aggregate criteria on the LOCKED_HOLDOUT, over cases inside declared
#: applicability. Frozen before the holdout is opened.
GATE_A = {
    "terminal_voltage": {
        "mae_v": 0.040,
        "rmse_v": 0.050,
        "p95_abs_v": 0.090,
        "max_abs_v": None,
    },
    "cell_temperature": {
        "mae_k": 2.5,
        "rmse_k": 3.0,
        "p95_abs_k": 5.0,
        "max_abs_k": None,
    },
    "max_error_policy": (
        "maximum absolute error is REPORTED and not gated. Over several "
        "thousand samples a single worst point is a statement about the worst "
        "instant, not about the model's fitness, and gating it would make the "
        "verdict depend on how many samples were retained"
    ),
    "state_of_charge": (
        "NOT INDEPENDENTLY VALIDATED. This source carries no state-of-charge "
        "reference that is independent of coulomb counting, and the archive's "
        "per-cycle Capacity is measured on the very discharge being predicted. "
        "No SOC gate exists and none is claimed"
    ),
    "scope": (
        "cases whose applicability is INSIDE. Cases declared OUTSIDE are "
        "evidence about the guardrail and are never summed into these metrics"
    ),
}

# ---------------------------------------------------------------------------
# 7. NUMERICAL AND TRUST POLICY.
# ---------------------------------------------------------------------------

NUMERICAL_POLICY = {
    "required": ["convergence", "refinement", "conservation"],
    "convergence": (
        "every coupling window of the flagship run reports its own state; a "
        "window that did not converge fails the check"
    ),
    "refinement": (
        "the same scenario is re-run with every measurement interval halved and "
        "then quartered, and the predicted voltage and temperature at the "
        "original instants are compared. The check is SATISFIED when the change "
        "from halving to quartering is below one tenth of the acceptance "
        "tolerance for each metric"
    ),
    "conservation": (
        "the heat the electrical participant reports as generated equals the "
        "heat the thermal participant consumes in the same window, and the "
        "energy the thermal state gained plus the energy it rejected to ambient "
        "equals the heat deposited"
    ),
    "outcomes": ["satisfied", "violated", "inconclusive", "not_performed"],
}

TRUST_POLICY = {
    "policy": "forge.multiphysics.production",
    "why": (
        "the production policy requires replay, numerical evidence, a supported "
        "validation envelope at the declared query point and serialization "
        "identity, and records an unmet uncertainty-channel gap as debt rather "
        "than hiding it. Full Trust additionally requires complete UQ channel "
        "coverage, which this campaign does not have and does not claim"
    ),
    "holdout_governance": (
        "the locked holdout is opened once, through the Sprint 2 opening "
        "authority, after the parameter set, the applicability declaration and "
        "this acceptance policy are frozen. A later model version requires a "
        "new registered evaluation; refitting and rerunning this holdout would "
        "not be an independent result and will not be reported as one"
    ),
}


# ---------------------------------------------------------------------------
# Deriving the selection. Pure function of the inventory plus the constants.
# ---------------------------------------------------------------------------


def _inside_ambient(ambient_c: float) -> bool:
    return INSIDE_AMBIENT_C[0] <= ambient_c <= INSIDE_AMBIENT_C[1]


def _outside_ambient(ambient_c: float) -> bool:
    return any(low <= ambient_c <= high for low, high in OUTSIDE_AMBIENT_C)


def _nearest_cycles(available: list[int]) -> list[int]:
    """The declared cycle positions, or the nearest available cycle to each."""
    chosen: list[int] = []
    for wanted in CYCLE_POSITIONS:
        if not available:
            break
        best = min(available, key=lambda item: (abs(item - wanted), item))
        if best not in chosen:
            chosen.append(best)
    return sorted(chosen)


def select(inventory: dict[str, Any]) -> dict[str, Any]:
    retained = [item for item in inventory["trajectories"] if item.get("retained")]

    # -- condition classification -------------------------------------------
    inside: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    not_full: list[dict[str, Any]] = []
    for item in retained:
        if item["cycle_index"] > INSIDE_MAX_CYCLE_INDEX:
            continue
        current = abs(item["load_current_a"])
        if not INSIDE_CURRENT_A[0] <= current <= INSIDE_CURRENT_A[1]:
            continue
        if _inside_ambient(item["ambient_temperature_c"]):
            # The declared full-charge initial condition has to be one the
            # cell's own open-circuit voltage supports.
            if (
                abs(item["start_voltage_v"] - FULL_CHARGE_ANCHOR_V)
                > FULL_CHARGE_BAND_V
            ):
                not_full.append(
                    {
                        "trajectory_id": item["trajectory_id"],
                        "cell": item["cell"],
                        "start_voltage_v": item["start_voltage_v"],
                        "why": (
                            "first rest voltage is more than "
                            f"{FULL_CHARGE_BAND_V * 1000:.0f} mV from the "
                            f"authority's full-charge anchor"
                        ),
                    }
                )
                continue
            inside.append(item)
        elif _outside_ambient(item["ambient_temperature_c"]):
            outside.append(item)

    # -- the replicate thermal screen, on INSIDE cells only -----------------
    by_condition: dict[tuple[float, float], dict[str, list[float]]] = {}
    for item in inside:
        key = (round(abs(item["load_current_a"]) * 2.0) / 2.0, 1.0)
        by_condition.setdefault(key, {}).setdefault(item["cell"], []).append(
            item["max_temperature_c"] - item["start_temperature_c"]
        )
    thermal_outliers: dict[str, str] = {}
    screen_record: list[dict[str, Any]] = []
    for key, cells in sorted(by_condition.items()):
        per_cell = {cell: statistics.median(values) for cell, values in cells.items()}
        entry: dict[str, Any] = {
            "load_current_a": key[0],
            "cells": len(per_cell),
            "median_rise_k_by_cell": {k: round(v, 3) for k, v in sorted(per_cell.items())},
        }
        if len(per_cell) < THERMAL_OUTLIER_MIN_CELLS:
            entry["applied"] = False
            entry["why"] = (
                f"fewer than {THERMAL_OUTLIER_MIN_CELLS} replicate cells; no cell "
                f"is called an outlier on this evidence"
            )
            screen_record.append(entry)
            continue
        reference = statistics.median(per_cell.values())
        low = THERMAL_OUTLIER_BAND[0] * reference
        high = THERMAL_OUTLIER_BAND[1] * reference
        entry.update(
            {
                "applied": True,
                "replicate_median_rise_k": round(reference, 3),
                "admitted_band_k": [round(low, 3), round(high, 3)],
            }
        )
        flagged = []
        for cell, value in sorted(per_cell.items()):
            if not low <= value <= high:
                flagged.append(cell)
                thermal_outliers[cell] = (
                    f"median temperature rise {value:.2f} K against a replicate "
                    f"median of {reference:.2f} K over {len(per_cell)} cells at "
                    f"{key[0]:.1f} A; outside the declared "
                    f"[{THERMAL_OUTLIER_BAND[0]}, {THERMAL_OUTLIER_BAND[1]}] band"
                )
        entry["thermal_outliers"] = flagged
        screen_record.append(entry)

    # -- split assignment, by experiment group and cell identifier ----------
    groups: dict[str, set[str]] = {}
    for item in inside:
        groups.setdefault(item["group"], set()).add(item["cell"])
    assignment: dict[str, str] = {}
    group_record: list[dict[str, Any]] = []
    for group, cells in sorted(groups.items()):
        ordered = sorted(cells)
        row = {"group": group, "cells": ordered, "assignment": {}}
        if len(ordered) < 2:
            for cell in ordered:
                assignment[cell] = "calibration"
                row["assignment"][cell] = "calibration"
            row["note"] = (
                "a single-cell group cannot supply independent evidence and is "
                "used for calibration only"
            )
        else:
            for index, cell in enumerate(ordered):
                split = SPLIT_CYCLE[min(index, len(SPLIT_CYCLE) - 1)]
                assignment[cell] = split
                row["assignment"][cell] = split
        group_record.append(row)

    # -- cycle selection, per cell and per operating condition --------------
    selected: list[dict[str, Any]] = []
    by_cell_condition: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for item in inside:
        by_cell_condition.setdefault(
            (item["cell"], round(abs(item["load_current_a"]) * 2.0) / 2.0), []
        ).append(item)
    for key, items in sorted(by_cell_condition.items()):
        available = sorted(item["cycle_index"] for item in items)
        wanted = set(_nearest_cycles(available))
        for item in items:
            if item["cycle_index"] not in wanted:
                continue
            cell = item["cell"]
            selected.append(
                {
                    "trajectory_id": item["trajectory_id"],
                    "cell": cell,
                    "group": item["group"],
                    "cycle_index": item["cycle_index"],
                    "ambient_temperature_c": item["ambient_temperature_c"],
                    "load_current_a": item["load_current_a"],
                    "split": assignment[cell],
                    "applicability": "inside",
                    "admit_cell_temperature": cell not in thermal_outliers,
                    "thermal_exclusion": thermal_outliers.get(cell, ""),
                }
            )

    # -- the OUTSIDE guardrail set ------------------------------------------
    #
    # Only from cells that contribute no INSIDE evidence. The independence unit
    # is the cell, and a cell supplying both a calibration trajectory and an
    # independent one straddles the boundary the corpus refuses -- correctly,
    # because the fit would then have seen the cell whose refusal is being
    # tested. Dropping those trajectories costs guardrail cells this archive has
    # plenty of, and keeps one cell on one side.
    inside_cells = {item["cell"] for item in inside}
    guardrail_cells = sorted({item["cell"] for item in outside} - inside_cells)
    excluded_for_overlap = sorted({item["cell"] for item in outside} & inside_cells)

    #: Guardrail evidence is never calibration: a refusal the fit was tuned on
    #: would not be a test of the refusal. It alternates between the two
    #: independent splits so the holdout tests the guardrail too.
    guardrail_split: dict[str, str] = {}
    by_group_outside: dict[str, list[str]] = {}
    for item in outside:
        if item["cell"] not in guardrail_cells:
            continue
        bucket = by_group_outside.setdefault(item["group"], [])
        if item["cell"] not in bucket:
            bucket.append(item["cell"])
    for group, cells in sorted(by_group_outside.items()):
        for index, cell in enumerate(sorted(cells)):
            guardrail_split[cell] = (
                "validation" if index % 2 == 0 else "locked_holdout"
            )

    outside_selected: list[dict[str, Any]] = []
    by_cell_outside: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for item in outside:
        if item["cell"] not in guardrail_split:
            continue
        by_cell_outside.setdefault(
            (item["cell"], round(abs(item["load_current_a"]) * 2.0) / 2.0), []
        ).append(item)
    for key, items in sorted(by_cell_outside.items()):
        available = sorted(item["cycle_index"] for item in items)
        wanted = set(_nearest_cycles(available)[:2])
        for item in items:
            if item["cycle_index"] not in wanted:
                continue
            outside_selected.append(
                {
                    "trajectory_id": item["trajectory_id"],
                    "cell": item["cell"],
                    "group": item["group"],
                    "cycle_index": item["cycle_index"],
                    "ambient_temperature_c": item["ambient_temperature_c"],
                    "load_current_a": item["load_current_a"],
                    "split": guardrail_split[item["cell"]],
                    "applicability": "outside",
                    "admit_cell_temperature": True,
                    "thermal_exclusion": "",
                }
            )

    # A group with no independent cell informs the fit and makes no claim, so
    # its trajectories carry no campaign case: scoring them would credit or
    # charge the model on evidence it was fitted to.
    claimless = {
        row["group"]
        for row in group_record
        if not {"validation", "locked_holdout"} & set(row["assignment"].values())
    }
    for item in selected:
        item["in_campaign"] = item["group"] not in claimless
        item["why_not_in_campaign"] = (
            ""
            if item["in_campaign"]
            else (
                "the experiment group has no validation or locked-holdout cell, "
                "so no parameter set of its own is ever applied to independent "
                "evidence and no claim is made about it"
            )
        )
    for item in outside_selected:
        item["in_campaign"] = True
        item["why_not_in_campaign"] = ""

    counts: dict[str, int] = {}
    for item in selected + outside_selected:
        counts[item["split"]] = counts.get(item["split"], 0) + 1
    return {
        "schema": "battery_thermal_flagship_s3_selection/1",
        "campaign_id": CAMPAIGN_ID,
        "campaign_version": CAMPAIGN_VERSION,
        "archive_sha256": inventory["archive_sha256"],
        "thermal_replicate_screen": screen_record,
        "thermal_outliers": thermal_outliers,
        "groups": group_record,
        "not_full_at_start": not_full,
        "groups_without_independent_cells": sorted(
            row["group"]
            for row in group_record
            if not {"validation", "locked_holdout"} & set(row["assignment"].values())
        ),
        "guardrail_cells": guardrail_split,
        "guardrail_cells_dropped_for_inside_overlap": excluded_for_overlap,
        "counts": {
            "inside_trajectories": len(selected),
            "outside_trajectories": len(outside_selected),
            "by_split": counts,
            "cells_inside": len({item["cell"] for item in selected}),
        },
        "selected": selected + outside_selected,
    }


def preregistration() -> dict[str, Any]:
    return {
        "schema": "battery_thermal_flagship_s3_preregistration/1",
        "campaign_id": CAMPAIGN_ID,
        "campaign_version": CAMPAIGN_VERSION,
        "amendments": list(AMENDMENTS),
        "dataset": {
            "dataset_id": DATASET_ID,
            "version": DATASET_VERSION,
            "title": "NASA Ames Prognostics Center of Excellence Li-ion Battery Aging Data Set",
        },
        "selection": {
            "inside_ambient_c": list(INSIDE_AMBIENT_C),
            "inside_cell_temperature_c": list(INSIDE_CELL_TEMPERATURE_C),
            "inside_current_a": list(INSIDE_CURRENT_A),
            "inside_max_cycle_index": INSIDE_MAX_CYCLE_INDEX,
            "outside_ambient_c": [list(item) for item in OUTSIDE_AMBIENT_C],
            "cycle_positions": list(CYCLE_POSITIONS),
            "sample_stride": SAMPLE_STRIDE,
            "applicability_charge_state_floor": APPLICABILITY_CHARGE_STATE_FLOOR,
            "full_charge_band_v": FULL_CHARGE_BAND_V,
            "full_charge_anchor_v": FULL_CHARGE_ANCHOR_V,
        },
        "parameter_unit": {
            "fitted_over": "one experiment group",
            "definition": (
                "a batch of sibling cells cycled together in one fixture under "
                "one protocol, as the source archive's own README grouping "
                "defines it"
            ),
            "fitted_on": "that group's calibration cells only",
            "applied_to": "that group's validation and locked-holdout cells",
            "why_that_is_still_independent": (
                "the cells a set is applied to are different physical cells "
                "from the ones it was fitted on, which is the transfer the "
                "campaign is testing"
            ),
        },
        "thermal_replicate_screen": {
            "minimum_cells": THERMAL_OUTLIER_MIN_CELLS,
            "band": list(THERMAL_OUTLIER_BAND),
            "basis": (
                "a cell is compared only with other cells measured at the same "
                "nominal load in the same ambient band. No model is involved, "
                "and only the cell temperature channel is withheld"
            ),
        },
        "split_rule": {
            "independence_unit": "one physical cell",
            "assignment": list(SPLIT_CYCLE),
            "ordering": "cells sorted by identifier within each experiment group",
            "outcome_blind": True,
        },
        "model": {"model_id": MODEL_ID, "version": MODEL_VERSION},
        "fitted_parameters": list(FITTED_PARAMETERS),
        "fixed_parameters": FIXED_PARAMETERS,
        "ocv_authority": OCV_AUTHORITY,
        "ocv_authority_record": "evidence/OCV_AUTHORITY.json",
        "source_measurement_uncertainty": SOURCE_MEASUREMENT_UNCERTAINTY,
        "acceptance": ACCEPTANCE,
        "gate_a": GATE_A,
        "numerical_policy": NUMERICAL_POLICY,
        "trust_policy": TRUST_POLICY,
        "forbidden": [
            "no measured voltage or temperature at any instant is an input to the "
            "prediction at that instant or any later one",
            "no locked-holdout case influences the fit, the model choice, the "
            "applicability declaration or any threshold above",
            "no threshold above is revised after the holdout is opened",
        ],
    }


def write_json(path: str, payload: Any) -> None:
    text = json.dumps(payload, indent=1, allow_nan=False)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")


def main() -> int:
    with open(os.path.join(EVIDENCE, "INVENTORY.json"), encoding="utf-8") as handle:
        inventory = json.load(handle)
    write_json(os.path.join(EVIDENCE, "PREREGISTRATION.json"), preregistration())
    selection = select(inventory)
    write_json(os.path.join(EVIDENCE, "DATA_SELECTION.json"), selection)
    print(json.dumps(selection["counts"], indent=1))
    print("thermal outliers:", sorted(selection["thermal_outliers"]))
    for row in selection["groups"]:
        print(" ", row["group"], row["assignment"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
