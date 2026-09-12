"""EV-11 to EV-18: the comparisons themselves.

Every function here produces two kinds of record.

  * CONSTRUCTION rows, from ``construction.compare``, which answer question A:
    did the Core receive the problem the fixture describes?
  * VALIDATION rows, which answer question B where external evidence exists and
    otherwise record an independent mathematical comparison as what it is.

The two are never added together, and no row's ``evidence_level`` is raised
because the number in it happens to be small. A comparison against arithmetic
written in this round is LEVEL 5 whether it agrees to 1e-16 or not; only
ngspice is LEVEL 4 and only CODATA and IEC 60751 are LEVEL 3.
"""

from __future__ import annotations

from adapters import adapter_a as A
from adapters import adapter_b as B
from reference import nodal, physics, spice

from . import construction
from .loader import fixture
from .tolerances import TOLERANCES

LEVEL_3 = "LEVEL 3 reference data"
LEVEL_4 = "LEVEL 4 external canonical implementation"
LEVEL_5 = "LEVEL 5 independent analytical"


def _peukert_product(effective_capacity_c: float, reference: dict) -> float:
    """I^k t evaluated at the CORE's effective capacity.

    Written out here rather than taken from ``physics.peukert_invariant``,
    which evaluates the same product at the reference branch's own capacity.
    A row that called that one and then labelled the result a comparison
    against the Core would not depend on the Core at all.
    """
    current = reference["current_a"]
    return current ** reference["peukert_exponent"] * (
        effective_capacity_c / current
    )


def _relative(core: float, reference: float, *, floor: float = 0.0) -> float:
    scale = max(abs(reference), floor)
    if scale == 0.0:
        return abs(core - reference)
    return abs(core - reference) / scale


def _row(
    *,
    model: str,
    case: str,
    quantity: str,
    route: str,
    evidence_level: str,
    core: float,
    reference: float,
    observed: float,
    tolerance_key: str,
    tolerance: float,
    metric: str = "relative error",
    passed: bool | None = None,
) -> dict:
    ok = observed <= tolerance if passed is None else passed
    return {
        "model": model,
        "case": case,
        "quantity": quantity,
        "route": route,
        "evidence_level": evidence_level,
        "core_value": core,
        "reference_value": reference,
        "metric": metric,
        "observed": observed,
        "tolerance": tolerance,
        "tolerance_key": tolerance_key,
        "verdict": "AGREES" if ok else "DISAGREES",
    }


# =====================================================================
# thermal.lumped.first_order_capacity
# =====================================================================


def lumped(case: str = "primary", **overrides) -> dict:
    raw = fixture("lumped_body")
    core = A.lumped(raw, **overrides)
    reference = B.lumped(raw, **overrides)
    closed = physics.lumped_closed_form(reference)
    marched = physics.lumped_rk4(reference)
    balance = physics.lumped_energy_balance(reference, core["final_temperature_k"])

    model = "thermal.lumped.first_order_capacity"
    rows = [
        _row(
            model=model,
            case=case,
            quantity="final temperature",
            route="engcore vs an RK4 march of the energy balance written in this round",
            evidence_level=LEVEL_5,
            core=core["final_temperature_k"],
            reference=marched["final_temperature_k"],
            observed=_relative(
                core["final_temperature_k"], marched["final_temperature_k"]
            ),
            tolerance_key="lumped_vs_rk4",
            tolerance=TOLERANCES["lumped_vs_rk4"]["value"],
        ),
        _row(
            model=model,
            case=case,
            quantity="final temperature",
            route="engcore vs the closed form derived from the balance in this round",
            evidence_level=LEVEL_5,
            core=core["final_temperature_k"],
            reference=closed["final_temperature_k"],
            observed=_relative(
                core["final_temperature_k"], closed["final_temperature_k"]
            ),
            tolerance_key="lumped_vs_rk4",
            tolerance=TOLERANCES["lumped_vs_rk4"]["value"],
        ),
        _row(
            model=model,
            case=case,
            quantity="steady state temperature",
            route="engcore vs T_amb + Q/hA",
            evidence_level=LEVEL_5,
            core=core["steady_state_temperature_k"],
            reference=closed["steady_state_temperature_k"],
            observed=_relative(
                core["steady_state_temperature_k"],
                closed["steady_state_temperature_k"],
            ),
            tolerance_key="lumped_vs_rk4",
            tolerance=TOLERANCES["lumped_vs_rk4"]["value"],
        ),
        _row(
            model=model,
            case=case,
            quantity="time constant",
            route="engcore vs C/hA",
            evidence_level=LEVEL_5,
            core=core["time_constant_s"],
            reference=closed["time_constant_s"],
            observed=_relative(core["time_constant_s"], closed["time_constant_s"]),
            tolerance_key="lumped_vs_rk4",
            tolerance=TOLERANCES["lumped_vs_rk4"]["value"],
        ),
        _row(
            model=model,
            case=case,
            quantity="energy balance over the interval",
            route="stored energy against heat in minus heat out, integrated independently",
            evidence_level=LEVEL_5,
            core=balance["stored_j"],
            reference=balance["supplied_j"] - balance["lost_j"],
            observed=balance["normalised_residual"],
            metric="normalised first-law residual",
            tolerance_key="lumped_energy_balance",
            tolerance=TOLERANCES["lumped_energy_balance"]["value"],
        ),
    ]
    return {
        "construction": construction.compare(
            f"lumped:{case}", core["received"], reference
        ),
        "validation": rows,
        "oracle_self_resolution": marched["self_resolution"],
        "oracle_ladder": marched["ladder"],
    }


# =====================================================================
# thermal.conduction1d.linear_diffusion
# =====================================================================


def slab(case: str = "primary", **overrides) -> dict:
    raw = fixture("slab")
    core = A.slab(raw, **overrides)
    reference = B.slab(raw, **overrides)
    exact = physics.diffusion_analytic_midpoint(reference)
    predicted = physics.diffusion_predicted_error(reference)
    explicit = physics.diffusion_ftcs_midpoint(reference)

    observed_error = (core["midpoint"] - exact) / exact
    ratio = observed_error / predicted["predicted_relative_error"]
    band = TOLERANCES["diffusion_error_ratio"]
    model = "thermal.conduction1d.linear_diffusion"

    # The explicit march makes its own, differently signed, error. Both are
    # predicted from the schemes rather than measured, so the two marches can
    # be compared against each other through the difference they are PREDICTED
    # to have. That is the same metric the plan preregistered for the closed
    # form, applied to a second route; it is not a bound padded to fit.
    explicit_predicted = physics.diffusion_ftcs_predicted_error(
        reference, dx=explicit["dx_m"], dt=explicit["dt_s"]
    )
    explicit_observed = (explicit["midpoint"] - exact) / exact
    explicit_ratio = (
        explicit_observed / explicit_predicted["predicted_relative_error"]
    )
    cross_observed = (core["midpoint"] - explicit["midpoint"]) / exact
    cross_predicted = (
        predicted["predicted_relative_error"]
        - explicit_predicted["predicted_relative_error"]
    )
    cross_ratio = cross_observed / cross_predicted

    rows = [
        _row(
            model=model,
            case=case,
            quantity="midpoint value against the closed form",
            route=(
                "engcore vs the separated-variables solution derived in this "
                "round, compared through the error the declared scheme predicts"
            ),
            evidence_level=LEVEL_5,
            core=core["midpoint"],
            reference=exact,
            observed=ratio,
            metric="observed relative error divided by the predicted scheme error",
            tolerance_key="diffusion_error_ratio",
            tolerance=band["high"],
            passed=band["low"] <= ratio <= band["high"],
        ),
        _row(
            model=model,
            case=f"{case}:explicit-march-self-check",
            quantity="the explicit march against the closed form",
            route=(
                "the third route checked against its own predicted error "
                "before it is used as a reference for anything"
            ),
            evidence_level=LEVEL_5,
            core=explicit["midpoint"],
            reference=exact,
            observed=explicit_ratio,
            metric="observed relative error divided by the predicted scheme error",
            tolerance_key="diffusion_error_ratio",
            tolerance=band["high"],
            passed=band["low"] <= explicit_ratio <= band["high"],
        ),
        _row(
            model=model,
            case=case,
            quantity="midpoint value against an explicit march",
            route=(
                "engcore vs a forward-time centred-space march at r = 1/4, "
                "compared through the difference the two schemes are predicted "
                "to have -- their time errors carry opposite signs"
            ),
            evidence_level=LEVEL_5,
            core=core["midpoint"],
            reference=explicit["midpoint"],
            observed=cross_ratio,
            metric=(
                "observed difference between the two marches divided by the "
                "difference their two schemes predict"
            ),
            tolerance_key="diffusion_error_ratio",
            tolerance=band["high"],
            passed=band["low"] <= cross_ratio <= band["high"],
        ),
    ]

    return {
        "construction": construction.compare(
            f"slab:{case}", core["received"], reference
        ),
        "validation": rows,
        "predicted_error": predicted,
        "observed_error": observed_error,
        "explicit_march": {
            k: explicit[k] for k in ("midpoint", "r", "dx_m", "dt_s", "n_steps")
        },
        "analytic_midpoint": exact,
    }


# =====================================================================
# battery.cell.*
# =====================================================================


def battery(case: str = "primary", **overrides) -> dict:
    raw = fixture("battery_cell")
    core = A.battery(raw, **overrides)
    reference = B.battery(raw, **overrides)
    computed = physics.battery(reference)
    effective_c = physics.peukert_effective_capacity_c(reference)
    invariant = physics.peukert_invariant(reference, effective_c)

    exact = TOLERANCES["battery_algebra"]["value"]
    rows = [
        _row(
            model="battery.cell.coulomb_counting",
            case=case,
            quantity="final state of charge",
            route="engcore vs z0 - I t/(eta Q), evaluated in this round",
            evidence_level=LEVEL_5,
            core=core["final_state_of_charge"],
            reference=computed["final_state_of_charge"],
            observed=_relative(
                core["final_state_of_charge"], computed["final_state_of_charge"]
            ),
            tolerance_key="battery_algebra",
            tolerance=exact,
        ),
        _row(
            model="battery.cell.rint_ocv",
            case=case,
            quantity="open circuit voltage",
            route="engcore vs V_e + (V_f - V_e) z",
            evidence_level=LEVEL_5,
            core=core["open_circuit_voltage_v"],
            reference=computed["open_circuit_voltage_v"],
            observed=_relative(
                core["open_circuit_voltage_v"], computed["open_circuit_voltage_v"]
            ),
            tolerance_key="battery_algebra",
            tolerance=exact,
        ),
        _row(
            model="battery.cell.rint_ocv",
            case=case,
            quantity="terminal voltage",
            route="engcore vs OCV(z) - I R",
            evidence_level=LEVEL_5,
            core=core["terminal_voltage_v"],
            reference=computed["terminal_voltage_v"],
            observed=_relative(
                core["terminal_voltage_v"], computed["terminal_voltage_v"]
            ),
            tolerance_key="battery_algebra",
            tolerance=exact,
        ),
        _row(
            model="battery.cell.rint_ocv",
            case=case,
            quantity="joule heating",
            route="engcore vs I^2 R",
            evidence_level=LEVEL_5,
            core=core["heat_generation_w"],
            reference=computed["heat_generation_w"],
            observed=_relative(
                core["heat_generation_w"], computed["heat_generation_w"]
            ),
            tolerance_key="battery_algebra",
            tolerance=exact,
        ),
        _row(
            model="battery.cell.constant_current_runtime",
            case=case,
            quantity="voltage cutoff expressed as a state of charge",
            route="engcore vs (V_cut + I R - V_e)/(V_f - V_e)",
            evidence_level=LEVEL_5,
            core=core["binding_cutoff_state_of_charge"],
            reference=computed["voltage_cutoff_state_of_charge"],
            observed=_relative(
                core["binding_cutoff_state_of_charge"],
                computed["voltage_cutoff_state_of_charge"],
            ),
            tolerance_key="battery_algebra",
            tolerance=exact,
        ),
        _row(
            model="battery.cell.constant_current_runtime",
            case=case,
            quantity="runtime to cutoff",
            route="engcore vs (z0 - z_stop) eta Q / I",
            evidence_level=LEVEL_5,
            core=core["runtime_to_cutoff_s"],
            reference=computed["runtime_to_cutoff_s"],
            observed=_relative(
                core["runtime_to_cutoff_s"], computed["runtime_to_cutoff_s"]
            ),
            tolerance_key="battery_algebra",
            tolerance=exact,
        ),
        _row(
            model="battery.cell.peukert_capacity_derating",
            case=case,
            quantity="effective capacity",
            route="engcore vs Q_nom (I_ref/I)^(k-1)",
            evidence_level=LEVEL_5,
            core=core["effective_capacity"],
            reference=effective_c / 3600.0,
            observed=_relative(core["effective_capacity"], effective_c / 3600.0),
            tolerance_key="peukert",
            tolerance=TOLERANCES["peukert"]["value"],
        ),
        _row(
            model="battery.cell.peukert_capacity_derating",
            case=case,
            quantity="Peukert invariant I^k t",
            route=(
                "the law as Peukert stated it, I^k t constant, evaluated at the "
                "Core's effective capacity and at the reference current"
            ),
            evidence_level=LEVEL_5,
            core=_peukert_product(core["effective_capacity"] * 3600.0, reference),
            reference=invariant["reference_product"],
            observed=_relative(
                _peukert_product(core["effective_capacity"] * 3600.0, reference),
                invariant["reference_product"],
            ),
            metric="relative difference in I^k t",
            tolerance_key="peukert",
            tolerance=TOLERANCES["peukert"]["value"],
        ),
    ]

    drawn = computed["charge_drawn_c"]
    accounted = (
        reference["initial_state_of_charge"] - core["final_state_of_charge"]
    ) * reference["coulombic_efficiency"] * reference["nominal_capacity_c"]
    residual = abs(accounted - drawn)
    within_floor = residual <= computed["cancellation_floor_c"]
    relative = residual / abs(drawn) if drawn != 0.0 else residual
    rows.append(
        _row(
            model="battery.cell.coulomb_counting",
            case=case,
            quantity="charge conservation",
            route=(
                "coulombs the Core's state change accounts for against "
                "coulombs the declared current drew"
            ),
            evidence_level=LEVEL_5,
            core=accounted,
            reference=drawn,
            observed=relative,
            metric=(
                "relative charge residual, or acceptance below the "
                "cancellation floor 4 ulp(z0) eta Q"
            ),
            tolerance_key="battery_charge_conservation",
            tolerance=TOLERANCES["battery_charge_conservation"]["value"],
            passed=(
                relative <= TOLERANCES["battery_charge_conservation"]["value"]
                or within_floor
            ),
        )
    )

    return {
        "construction": construction.compare(
            f"battery:{case}", core["received"], reference
        ),
        "validation": rows,
        "cancellation_floor_c": computed["cancellation_floor_c"],
    }


# =====================================================================
# electrical.material.*
# =====================================================================


def conductor(case: str = "primary", **overrides) -> dict:
    raw = fixture("conductor")
    core = A.conductor(raw, **overrides)
    reference = B.conductor(raw, **overrides)
    expected = physics.linear_tcr(reference, reference["operating_temperature_k"])

    rows = [
        _row(
            model="electrical.material.linear_tcr_resistance",
            case=case,
            quantity="resistance at the operating temperature",
            route=(
                "engcore, given rho/L/A and ppm/K, vs R_ref(1 + alpha dT) with "
                "R_ref = rho L / A recomputed independently"
            ),
            evidence_level=LEVEL_5,
            core=core["resistance_ohm"],
            reference=expected,
            observed=_relative(core["resistance_ohm"], expected),
            tolerance_key="geometry_resistance",
            tolerance=TOLERANCES["geometry_resistance"]["value"],
        ),
    ]
    # The rated record is the same constitutive law declared with material
    # limits attached. Declaring the limits is what makes it the rated model,
    # so the case is the same solve with the limits present and is reported
    # against its own model id rather than being counted twice under one.
    rows.append(
        _row(
            model="electrical.material.rated_linear_tcr_resistance",
            case=case,
            quantity="resistance at the operating temperature, limits declared",
            route=(
                "engcore with a linearization band and a maximum operating "
                "temperature declared, vs the same independent R_ref(1+alpha dT)"
            ),
            evidence_level=LEVEL_5,
            core=core["resistance_ohm"],
            reference=expected,
            observed=_relative(core["resistance_ohm"], expected),
            tolerance_key="geometry_resistance",
            tolerance=TOLERANCES["geometry_resistance"]["value"],
        )
    )
    return {
        "construction": construction.compare(
            f"conductor:{case}", core["received"], reference
        ),
        "validation": rows,
    }


def platinum(case: str = "primary", **overrides) -> dict:
    """The one place in this round where a published standard is the reference."""
    raw = fixture("platinum_iec60751")
    rows_core = A.platinum(raw, **overrides)
    reference = B.platinum(raw, **overrides)

    recomputed_w100 = physics.callendar_van_dusen(reference, 100.0) / reference[
        "r_zero_ohm"
    ]
    rows = [
        _row(
            model="electrical.material.linear_tcr_resistance",
            case=f"{case}:recitation-cross-check",
            quantity="W(100) recomputed from the recited coefficients",
            route=(
                "the recited A and B against the ratio IEC 60751 itself "
                "publishes -- a check on the recitation, not on the Core"
            ),
            evidence_level=LEVEL_3,
            core=recomputed_w100,
            reference=reference["published_W_100"],
            observed=_relative(recomputed_w100, reference["published_W_100"]),
            tolerance_key="iec60751_recitation",
            tolerance=TOLERANCES["iec60751_recitation"]["value"],
        )
    ]
    for entry in rows_core:
        celsius = entry["temperature_degC"]
        standard = physics.callendar_van_dusen(reference, celsius)
        observed_deviation = (entry["resistance_ohm"] - standard) / standard
        predicted = physics.predicted_linear_truncation(reference, celsius)
        ratio = observed_deviation / predicted
        rows.append(
            _row(
                model="electrical.material.linear_tcr_resistance",
                case=f"{case}:{celsius:g}C",
                quantity="deviation from the IEC 60751 quadratic",
                route=(
                    "engcore's linear law against the standard's quadratic, "
                    "compared through the omitted term the linear law drops"
                ),
                evidence_level=LEVEL_3,
                core=entry["resistance_ohm"],
                reference=standard,
                observed=abs(ratio - 1.0),
                metric=(
                    "|observed deviation / predicted omitted term - 1|, where "
                    "the prediction is |B| t^2 / (1 + A t)"
                ),
                tolerance_key="tcr_vs_iec60751",
                tolerance=TOLERANCES["tcr_vs_iec60751"]["value"],
            )
        )
    return {"construction": [], "validation": rows}


# =====================================================================
# electrical.dc.*
# =====================================================================


def _voltage_rows(case, circuit_id, core, hand, spice_result, reference_problem):
    rows = []
    floor = TOLERANCES["dc_vs_ngspice"]["absolute_floor_v"]
    for node, hand_value in sorted(hand["node_voltages_v"].items()):
        core_value = core["values"][f"node_voltage:{node}"]
        rows.append(
            _row(
                model="electrical.dc.kcl",
                case=f"{case}:{circuit_id}",
                quantity=f"node voltage {node}",
                route=(
                    "engcore vs modified nodal analysis assembled from the raw "
                    "fixture and solved by a hand-written Gaussian elimination"
                ),
                evidence_level=LEVEL_5,
                core=core_value,
                reference=hand_value,
                observed=_relative(core_value, hand_value, floor=floor),
                tolerance_key="dc_vs_hand_solve",
                tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
            )
        )
        if spice_result is not None:
            spice_value = spice_result["node_voltages_v"][node]
            rows.append(
                _row(
                    model="electrical.dc.kcl",
                    case=f"{case}:{circuit_id}",
                    quantity=f"node voltage {node}",
                    route=(
                        "engcore vs ngspice 42, run as a separate process on a "
                        "netlist emitted from the raw fixture"
                    ),
                    evidence_level=LEVEL_4,
                    core=core_value,
                    reference=spice_value,
                    observed=_relative(core_value, spice_value, floor=floor),
                    tolerance_key="dc_vs_ngspice",
                    tolerance=TOLERANCES["dc_vs_ngspice"]["value"],
                )
            )
    return rows


def circuits(case: str = "primary", raw_circuits=None) -> dict:
    raw_file = fixture("circuits")
    circuit_list = raw_circuits if raw_circuits is not None else raw_file["circuits"]
    construction_rows: list[dict] = []
    validation_rows: list[dict] = []
    diagnostics: list[dict] = []

    for raw in circuit_list:
        core = A.circuit(raw)
        reference_problem = B.circuit(raw)
        hand = nodal.solve(reference_problem)
        branches = nodal.branch_report(reference_problem, hand)
        spice_result = spice.run(raw) if spice.available() else None
        circuit_id = raw["circuit_id"]

        received_flat = (
            {
                f"resistor_ohm:{k}": v
                for k, v in core["received"]["resistors_ohm"].items()
            }
            | {
                f"voltage_source_v:{k}": v
                for k, v in core["received"]["voltage_sources_v"].items()
            }
            | {
                f"current_source_a:{k}": v
                for k, v in core["received"]["current_sources_a"].items()
            }
            | {
                "reference_node": core["received"]["reference_node"],
                "node_count": len(core["received"]["nodes"]),
            }
        )
        reference_flat = (
            {
                f"resistor_ohm:{r['id']}": r["resistance_ohm"]
                for r in reference_problem["resistors"]
            }
            | {
                f"voltage_source_v:{s['id']}": s["voltage_v"]
                for s in reference_problem["voltage_sources"]
            }
            | {
                f"current_source_a:{s['id']}": s["current_a"]
                for s in reference_problem["current_sources"]
            }
            | {
                "reference_node": reference_problem["reference_node"],
                "node_count": len(reference_problem["nodes"]),
            }
        )
        construction_rows += construction.compare(
            f"circuit:{case}:{circuit_id}", received_flat, reference_flat
        )

        validation_rows += _voltage_rows(
            case, circuit_id, core, hand, spice_result, reference_problem
        )

        # --- electrical.dc.resistor_ohm -------------------------------------
        for resistor in reference_problem["resistors"]:
            identifier = resistor["id"]
            core_current = core["values"][f"resistor_current:{identifier}"]
            validation_rows.append(
                _row(
                    model="electrical.dc.resistor_ohm",
                    case=f"{case}:{circuit_id}",
                    quantity=f"resistor current {identifier}",
                    route="engcore vs (v_a - v_b)/R from the independent node solve",
                    evidence_level=LEVEL_5,
                    core=core_current,
                    reference=branches["resistor_currents_a"][identifier],
                    observed=_relative(
                        core_current,
                        branches["resistor_currents_a"][identifier],
                        floor=1e-15,
                    ),
                    tolerance_key="dc_vs_hand_solve",
                    tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
                )
            )
            core_power = core["values"][f"resistor_power:{identifier}"]
            validation_rows.append(
                _row(
                    model="electrical.dc.resistor_ohm",
                    case=f"{case}:{circuit_id}",
                    quantity=f"resistor dissipation {identifier} is non-negative",
                    route="a passive element cannot deliver power",
                    evidence_level=LEVEL_5,
                    core=core_power,
                    reference=branches["resistor_powers_w"][identifier],
                    observed=_relative(
                        core_power,
                        branches["resistor_powers_w"][identifier],
                        floor=1e-15,
                    ),
                    tolerance_key="dc_vs_hand_solve",
                    tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
                    passed=(
                        core_power >= 0.0
                        and _relative(
                            core_power,
                            branches["resistor_powers_w"][identifier],
                            floor=1e-15,
                        )
                        <= TOLERANCES["dc_vs_hand_solve"]["value"]
                    ),
                )
            )

        # --- electrical.dc.ideal_voltage_source -----------------------------
        for source in reference_problem["voltage_sources"]:
            identifier = source["id"]
            imposed = (
                core["values"][f"node_voltage:{source['positive_node']}"]
                - core["values"][f"node_voltage:{source['negative_node']}"]
            )
            validation_rows.append(
                _row(
                    model="electrical.dc.ideal_voltage_source",
                    case=f"{case}:{circuit_id}",
                    quantity=f"terminal difference held by {identifier}",
                    route=(
                        "the Core's own node voltages against the voltage the "
                        "raw fixture declared, converted independently"
                    ),
                    evidence_level=LEVEL_5,
                    core=imposed,
                    reference=source["voltage_v"],
                    observed=_relative(imposed, source["voltage_v"], floor=1e-15),
                    tolerance_key="dc_vs_hand_solve",
                    tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
                )
            )
            core_branch = core["values"][f"source_current:{identifier}"]
            validation_rows.append(
                _row(
                    model="electrical.dc.ideal_voltage_source",
                    case=f"{case}:{circuit_id}",
                    quantity=f"branch current through {identifier}",
                    route="engcore vs the extra MNA unknown in the hand solve",
                    evidence_level=LEVEL_5,
                    core=core_branch,
                    reference=hand["voltage_source_currents_a"][identifier],
                    observed=_relative(
                        core_branch,
                        hand["voltage_source_currents_a"][identifier],
                        floor=1e-15,
                    ),
                    tolerance_key="dc_vs_hand_solve",
                    tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
                )
            )

        # --- electrical.dc.ideal_current_source -----------------------------
        for source in reference_problem["current_sources"]:
            identifier = source["id"]
            absorbed = core["values"][f"current_source_power:{identifier}"]
            # engcore reports source powers ABSORBED, and subtracts them to
            # build its delivered total. The metric key does not carry that
            # convention, so it is stated here and the comparison is made under
            # it rather than against a sign this audit would have preferred.
            expected_absorbed = source["current_a"] * (
                core["values"][f"node_voltage:{source['from_node']}"]
                - core["values"][f"node_voltage:{source['to_node']}"]
            )
            validation_rows.append(
                _row(
                    model="electrical.dc.ideal_current_source",
                    case=f"{case}:{circuit_id}",
                    quantity=f"power absorbed by {identifier}",
                    route=(
                        "engcore vs I (v_from - v_to) with I taken from the raw "
                        "fixture and converted independently -- the current is "
                        "held irrespective of the terminal voltage, so this is "
                        "where a source that bent to the network would show"
                    ),
                    evidence_level=LEVEL_5,
                    core=absorbed,
                    reference=expected_absorbed,
                    observed=_relative(absorbed, expected_absorbed, floor=1e-15),
                    tolerance_key="dc_vs_hand_solve",
                    tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
                )
            )
            validation_rows.append(
                _row(
                    model="electrical.dc.ideal_current_source",
                    case=f"{case}:{circuit_id}",
                    quantity=(
                        f"current held by {identifier} against the declared value"
                    ),
                    route=(
                        "the current recovered from the Core's own reported "
                        "power and its own node voltages, against the raw "
                        "fixture's milliamps converted independently"
                    ),
                    evidence_level=LEVEL_5,
                    core=absorbed
                    / (
                        core["values"][f"node_voltage:{source['from_node']}"]
                        - core["values"][f"node_voltage:{source['to_node']}"]
                    ),
                    reference=source["current_a"],
                    observed=_relative(
                        absorbed
                        / (
                            core["values"][f"node_voltage:{source['from_node']}"]
                            - core["values"][f"node_voltage:{source['to_node']}"]
                        ),
                        source["current_a"],
                    ),
                    tolerance_key="dc_vs_hand_solve",
                    tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
                )
            )

        # --- electrical.dc.kcl, conservation --------------------------------
        validation_rows.append(
            _row(
                model="electrical.dc.kcl",
                case=f"{case}:{circuit_id}",
                quantity="worst nodal current balance, reference node included",
                route=(
                    "every branch current recomputed from the Core's node "
                    "voltages and summed at every node"
                ),
                evidence_level=LEVEL_5,
                core=branches["worst_kcl_residual_a"],
                reference=0.0,
                observed=branches["normalised_kcl_residual"],
                metric="worst KCL residual normalised by the largest branch current",
                tolerance_key="dc_conservation",
                tolerance=TOLERANCES["dc_conservation"]["value"],
            )
        )
        core_dissipation = core["values"]["total_resistor_dissipation"]
        core_delivered = core["values"]["total_source_delivered_power"]
        imbalance = (
            abs(core_delivered - core_dissipation) / abs(core_dissipation)
            if core_dissipation != 0.0
            else abs(core_delivered - core_dissipation)
        )
        validation_rows.append(
            _row(
                model="electrical.dc.resistor_ohm",
                case=f"{case}:{circuit_id}",
                quantity="power balance",
                route="the Core's own delivered and dissipated totals",
                evidence_level=LEVEL_5,
                core=core_delivered,
                reference=core_dissipation,
                observed=imbalance,
                metric="power imbalance normalised by total dissipation",
                tolerance_key="dc_conservation",
                tolerance=TOLERANCES["dc_conservation"]["value"],
            )
        )
        validation_rows.append(
            _row(
                model="electrical.dc.resistor_ohm",
                case=f"{case}:{circuit_id}",
                quantity="total dissipation against an independent recomputation",
                route="engcore's total against sum of (v_a-v_b)^2/R from the hand solve",
                evidence_level=LEVEL_5,
                core=core_dissipation,
                reference=branches["dissipated_w"],
                observed=_relative(core_dissipation, branches["dissipated_w"]),
                tolerance_key="dc_vs_hand_solve",
                tolerance=TOLERANCES["dc_vs_hand_solve"]["value"],
            )
        )

        # --- the two companion applicability records ------------------------
        declared = raw.get("applicability_declarations", {})
        reference_declared = B.applicability(raw)
        for component_id, entry in declared.items():
            if "output_resistance_mohm" in entry:
                source_raw = next(
                    s for s in raw["voltage_sources"] if s["id"] == component_id
                )
                source_current = core["values"][f"source_current:{component_id}"]
                result = A.regulated_source(
                    entry | {"voltage_mV": source_raw["voltage_mV"]},
                    source_current_a=source_current,
                )
                independent = (
                    abs(source_current)
                    * reference_declared[component_id]["output_resistance_ohm"]
                    / abs(
                        next(
                            s["voltage_v"]
                            for s in reference_problem["voltage_sources"]
                            if s["id"] == component_id
                        )
                    )
                ) / reference_declared[component_id]["regulation_band"]
                validation_rows.append(
                    _row(
                        model="electrical.dc.regulated_voltage_source",
                        case=f"{case}:{circuit_id}",
                        quantity="regulation budget consumed by the internal drop",
                        route=(
                            "engcore vs (|I| R_out/|V|)/band, with R_out taken "
                            "from the raw fixture in milliohms and converted "
                            "independently"
                        ),
                        evidence_level=LEVEL_5,
                        core=result["utilization"],
                        reference=independent,
                        observed=_relative(result["utilization"], independent),
                        tolerance_key="applicability_utilization",
                        tolerance=TOLERANCES["applicability_utilization"]["value"],
                    )
                )
                diagnostics.append(
                    {
                        "circuit": circuit_id,
                        "component": component_id,
                        "model": "electrical.dc.regulated_voltage_source",
                        "status": result["status"],
                        "received": result["received"],
                    }
                )
            if "element_to_body_thermal_resistance_K_per_W" in entry:
                power = core["values"][f"resistor_power:{component_id}"]
                result = A.self_heated_resistor(entry, dissipated_power_w=power)
                independent = (
                    reference_declared[component_id]["body_temperature_k"]
                    + abs(power)
                    * reference_declared[component_id][
                        "element_to_body_thermal_resistance_k_per_w"
                    ]
                ) / reference_declared[component_id][
                    "permissible_element_temperature_k"
                ]
                validation_rows.append(
                    _row(
                        model="electrical.dc.self_heated_resistor",
                        case=f"{case}:{circuit_id}",
                        quantity="element hot spot as a fraction of what it permits",
                        route=(
                            "engcore vs (T_body + |P| R_th)/T_permissible, with "
                            "the temperatures converted from degC independently"
                        ),
                        evidence_level=LEVEL_5,
                        core=result["utilization"],
                        reference=independent,
                        observed=_relative(result["utilization"], independent),
                        tolerance_key="applicability_utilization",
                        tolerance=TOLERANCES["applicability_utilization"]["value"],
                    )
                )
                diagnostics.append(
                    {
                        "circuit": circuit_id,
                        "component": component_id,
                        "model": "electrical.dc.self_heated_resistor",
                        "status": result["status"],
                        "received": result["received"],
                    }
                )

        diagnostics.append(
            {
                "circuit": circuit_id,
                "condition_number": hand["condition_number"],
                "hand_solve_residual": hand["residual_infinity_norm"],
                "unknowns": hand["unknown_count"],
                "ngspice": spice_result is not None,
                "netlist": spice_result["netlist"] if spice_result else None,
            }
        )

    return {
        "construction": construction_rows,
        "validation": validation_rows,
        "diagnostics": diagnostics,
    }


# =====================================================================
# kinetics.cstr.*
# =====================================================================


def reactor(case: str = "primary", *, constant_rate: bool = False, **overrides) -> dict:
    raw = fixture("reactor")
    core = A.reactor(raw, constant_rate=constant_rate, **overrides)
    reference = B.reactor(raw, constant_rate=constant_rate, **overrides)
    trajectory = physics.cstr_trajectory(reference)
    ceiling = physics.cstr_invariant_ceiling(reference)
    model = (
        "kinetics.cstr.nonisothermal_first_order_constant_rate"
        if constant_rate
        else "kinetics.cstr.nonisothermal_first_order"
    )
    tolerance = TOLERANCES["cstr_trajectory"]["value"]

    rows = [
        _row(
            model=model,
            case=case,
            quantity="final concentration",
            route=(
                "engcore vs a fixed-step RK4 of the two balances, written in "
                "this round and evidenced by a refinement ladder"
            ),
            evidence_level=LEVEL_5,
            core=core["values"]["C_A:final"],
            reference=trajectory["final_concentration_mol_per_m3"],
            observed=_relative(
                core["values"]["C_A:final"],
                trajectory["final_concentration_mol_per_m3"],
            ),
            tolerance_key="cstr_trajectory",
            tolerance=tolerance,
        ),
        _row(
            model=model,
            case=case,
            quantity="final temperature",
            route="engcore vs the same RK4 march",
            evidence_level=LEVEL_5,
            core=core["values"]["T:final"],
            reference=trajectory["final_temperature_k"],
            observed=_relative(
                core["values"]["T:final"], trajectory["final_temperature_k"]
            ),
            tolerance_key="cstr_trajectory",
            tolerance=tolerance,
        ),
        _row(
            model=model,
            case=case,
            quantity="conversion",
            route="engcore vs 1 - C_A/C_Af from the independent march",
            evidence_level=LEVEL_5,
            core=core["values"]["conversion:final"],
            reference=1.0
            - trajectory["final_concentration_mol_per_m3"]
            / reference["feed_concentration_mol_per_m3"],
            observed=_relative(
                core["values"]["conversion:final"],
                1.0
                - trajectory["final_concentration_mol_per_m3"]
                / reference["feed_concentration_mol_per_m3"],
            ),
            tolerance_key="cstr_trajectory",
            tolerance=tolerance,
        ),
        _row(
            model=model,
            case=case,
            quantity="peak temperature stays under the exact invariant ceiling",
            route=(
                "Z = T + beta C_A obeys dZ/dt = a(Z_f - Z) - gamma(T - T_c), in "
                "which the reaction term cancels identically, so the bound holds "
                "whatever the rate law is"
            ),
            evidence_level=LEVEL_5,
            core=core["values"]["T:max"],
            reference=ceiling["temperature_ceiling_k"],
            observed=core["values"]["T:max"] - ceiling["temperature_ceiling_k"],
            metric="peak temperature minus the ceiling, which must not be positive",
            tolerance_key="cstr_trajectory",
            tolerance=0.0,
            passed=core["values"]["T:max"] <= ceiling["temperature_ceiling_k"],
        ),
    ]

    if not constant_rate:
        steady = physics.cstr_steady_states(reference)
        rows.append(
            _row(
                model=model,
                case=f"{case}:gas-constant",
                quantity="molar gas constant",
                route=(
                    "the value the Core stores against CODATA 2022, read from a "
                    "hashed copy of scipy's constants table"
                ),
                evidence_level=LEVEL_3,
                core=_core_gas_constant(),
                reference=reference["molar_gas_constant_j_per_mol_k"],
                observed=_relative(
                    _core_gas_constant(),
                    reference["molar_gas_constant_j_per_mol_k"],
                ),
                tolerance_key="gas_constant",
                tolerance=TOLERANCES["gas_constant"]["value"],
            )
        )
    else:
        steady = []

    return {
        "construction": construction.compare(
            f"reactor:{case}", core["received"], _strip(reference)
        ),
        "validation": rows,
        "oracle_self_resolution": trajectory["self_resolution"],
        "oracle_ladder": trajectory["ladder"],
        "invariant_ceiling": ceiling,
        "steady_states_k": steady,
        "core_values": core["values"],
    }


def _strip(reference: dict) -> dict:
    """Drop the gas constant from the construction comparison.

    The Core stores its own molar gas constant and does not accept one, so
    there is nothing to compare field by field. It is checked as a value
    instead, in its own row against CODATA, which is the honest place for it.
    """
    return {k: v for k, v in reference.items() if k != "molar_gas_constant_j_per_mol_k"}


def _core_gas_constant() -> float:
    from engcore.domains.kinetics.cstr.context import MOLAR_GAS_CONSTANT

    return MOLAR_GAS_CONSTANT.magnitude_in("joule / mole / kelvin")


def cstr_steady_state_rows(case: str = "primary") -> list[dict]:
    """The steady states, found by bisection, checked against the Core's own.

    The Core exposes steady states through its reactor context rather than
    through the transient result, so this is a separate call rather than part
    of the trajectory comparison.
    """
    raw = fixture("reactor")
    reference = B.reactor(raw)
    ours = physics.cstr_steady_states(reference)
    rows = []
    for index, temperature in enumerate(ours):
        rate = physics.cstr_rate_constant(reference, temperature)
        concentration = (
            reference["dilution_rate_per_s"]
            * reference["feed_concentration_mol_per_m3"]
            / (reference["dilution_rate_per_s"] + rate)
        )
        residual_c = (
            reference["dilution_rate_per_s"]
            * (reference["feed_concentration_mol_per_m3"] - concentration)
            - rate * concentration
        )
        rows.append(
            {
                "model": "kinetics.cstr.nonisothermal_first_order",
                "case": f"{case}:steady-state-{index}",
                "quantity": "steady temperature found by bisection",
                "route": (
                    "the steady energy residual bisected on a scanned bracket; "
                    "no Brent, because the Core uses it"
                ),
                "evidence_level": LEVEL_5,
                "temperature_k": temperature,
                "concentration_mol_per_m3": concentration,
                "species_balance_residual": residual_c,
                "metric": "species balance residual at the root",
                "verdict": "AGREES" if abs(residual_c) < 1e-9 else "DISAGREES",
            }
        )
    return rows
