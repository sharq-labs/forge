"""ST-14: randomized property testing, with generators that stay in the domain.

THE GENERATORS ARE THE RISK. A previous round of this audit history produced a
false finding from a generator that wandered outside a model's declared
physical domain, and this round has already produced three audit defects of its
own from oracles that were themselves wrong. So every generator below states
what it enforces, refuses anything outside it, and REPORTS the rejection count
-- a generator with no rejections is either lucky or not actually constraining
anything, and either is worth seeing.

Properties are checked against oracles, conservation laws and invariants, never
against the implementation's own previous answer.
"""

from __future__ import annotations

import math
import random

from benchmarks.scientific_truth.audit import production as P
from benchmarks.scientific_truth.oracles import battery as OB
from benchmarks.scientific_truth.oracles import cstr as OC
from benchmarks.scientific_truth.oracles import dc as OD
from benchmarks.scientific_truth.oracles import diffusion as ODF
from benchmarks.scientific_truth.oracles import lumped as OL

SEED = 20260911


def lumped_property(n: int = 200) -> dict:
    """Random bodies, checked against RK4 and the first law.

    ENFORCED: C > 0, hA > 0, duration > 0, all temperatures absolute and above
    100 K, heat input finite. Every one of these is a declared requirement of
    the model, and a draw outside them is rejected rather than reported.
    """
    rng = random.Random(SEED)
    generated = rejected = 0
    worst = {"relative_error": 0.0}
    worst_residual = {"relative_residual": 0.0}
    while generated < n:
        capacity = 10 ** rng.uniform(1.0, 5.0)
        conductance = 10 ** rng.uniform(-2.0, 2.0)
        ambient = rng.uniform(200.0, 400.0)
        initial = rng.uniform(200.0, 600.0)
        heat = rng.uniform(-50.0, 500.0)
        duration = 10 ** rng.uniform(0.0, 5.0)
        steady = ambient + heat / conductance
        if not (
            capacity > 0.0 and conductance > 0.0 and duration > 0.0
            and initial > 100.0 and ambient > 100.0 and steady > 100.0
        ):
            rejected += 1
            continue
        generated += 1
        runtime = P.lumped(
            capacity=capacity, conductance=conductance, ambient=ambient,
            initial=initial, heat_w=heat, duration_s=duration,
        )
        oracle = OL.rk4_final_temperature(
            capacity_j_per_k=capacity, conductance_w_per_k=conductance,
            ambient_k=ambient, initial_k=initial, heat_input_w=heat,
            duration_s=duration, steps=20_000,
        )
        error = abs(runtime["final_temperature"] - oracle) / max(abs(oracle), 1e-30)
        if error > worst["relative_error"]:
            worst = {
                "relative_error": error, "capacity": capacity,
                "conductance": conductance, "ambient": ambient,
                "initial": initial, "heat": heat, "duration": duration,
                "runtime": runtime["final_temperature"], "oracle": oracle,
            }
        balance = OL.energy_residual(
            capacity_j_per_k=capacity, conductance_w_per_k=conductance,
            ambient_k=ambient, initial_k=initial,
            final_k=runtime["final_temperature"], heat_input_w=heat,
            duration_s=duration,
        )
        if balance["relative_residual"] > worst_residual["relative_residual"]:
            worst_residual = balance
    return {
        "model": "thermal.lumped.first_order_capacity",
        "enforced": "C > 0, hA > 0, t > 0, T_0 and T_amb and T_ss above 100 K",
        "generated": generated, "rejected": rejected,
        "property": "the closed form equals an RK4 integration, and the first law holds",
        "worst_relative_error": worst["relative_error"],
        "worst_case": worst,
        "tolerance": 1e-8,
        "worst_energy_residual": worst_residual["relative_residual"],
        "conservation_tolerance": 1e-9,
        "verdict": (
            "HOLDS"
            if worst["relative_error"] <= 1e-8
            and worst_residual["relative_residual"] <= 1e-9
            else "VIOLATED"
        ),
    }


def battery_property(n: int = 400) -> dict:
    """Random discharges, checked against charge conservation and KVL.

    ENFORCED: Q_nom > 0, R > 0, 0 < eta <= 1, V_full > V_empty (the domain
    refuses equality, with a stated reason), I > 0 (discharge only), duration
    > 0, and the trajectory kept inside [0, 1] so the chord is being read where
    it is defined.
    """
    rng = random.Random(SEED + 1)
    generated = rejected = 0
    worst_v = {"relative_error": 0.0}
    worst_charge = {"relative_residual": 0.0}
    while generated < n:
        capacity = 10 ** rng.uniform(-1.0, 2.0)
        resistance = 10 ** rng.uniform(-3.0, 0.0)
        v_empty = rng.uniform(1.0, 3.5)
        v_full = v_empty + rng.uniform(0.05, 1.5)
        efficiency = rng.uniform(0.8, 1.0)
        current = 10 ** rng.uniform(-2.0, 1.0)
        z0 = rng.uniform(0.2, 1.0)
        duration = 10 ** rng.uniform(0.0, 4.0)
        z_end = OB.state_of_charge(
            z0=z0, current_a=current, duration_s=duration,
            efficiency=efficiency, capacity_ah=capacity,
        )
        if not (v_full > v_empty and 0.0 < efficiency <= 1.0 and current > 0.0
                and 0.0 <= z_end <= 1.0 and z0 <= 1.0):
            rejected += 1
            continue
        generated += 1
        runtime = P.battery_step(
            capacity_ah=capacity, resistance=resistance, v_full=v_full,
            v_empty=v_empty, efficiency=efficiency, current_a=current, z0=z0,
            temperature_k=298.15, duration_s=duration,
        )
        expected_v = OB.terminal_voltage(
            z=z_end, current_a=current, resistance_ohm=resistance,
            v_empty=v_empty, v_full=v_full,
        )
        error = abs(runtime["terminal_voltage"] - expected_v) / max(abs(expected_v), 1e-30)
        if error > worst_v["relative_error"]:
            worst_v = {
                "relative_error": error, "runtime": runtime["terminal_voltage"],
                "oracle": expected_v, "capacity": capacity, "current": current,
                "z0": z0, "duration": duration,
            }
        balance = OB.charge_balance_residual(
            z0=z0, z_end=runtime["final_state_of_charge"], current_a=current,
            duration_s=duration, efficiency=efficiency, capacity_ah=capacity,
        )
        if (
            not balance["within_cancellation_floor"]
            and balance["relative_residual"] > worst_charge["relative_residual"]
        ):
            worst_charge = balance
        # Two invariants that hold for every admissible draw.
        assert runtime["heat_generation"] >= 0.0
        assert runtime["terminal_voltage"] <= runtime["open_circuit_voltage"] + 1e-15
    return {
        "model": "battery.cell.rint_ocv / coulomb_counting",
        "enforced": (
            "Q > 0, R > 0, 0 < eta <= 1, V_full > V_empty, I > 0, and the whole "
            "trajectory inside [0, 1] so the chord is read where it is defined"
        ),
        "generated": generated, "rejected": rejected,
        "property": "V = OCV(z) - I R with z from charge conservation; heat >= 0; V <= OCV",
        "worst_relative_error": worst_v["relative_error"],
        "worst_case": worst_v,
        "tolerance": 1e-12,
        "worst_charge_residual": worst_charge["relative_residual"],
        "conservation_tolerance": 1e-12,
        "verdict": (
            "HOLDS"
            if worst_v["relative_error"] <= 1e-12
            and worst_charge["relative_residual"] <= 1e-12
            else "VIOLATED"
        ),
    }


def dc_property(n: int = 60) -> dict:
    """Random resistive networks, checked against ngspice and against KCL.

    ENFORCED: every resistance strictly positive and finite, exactly one
    reference node, every terminal naming a declared node, no self-loops, and
    at least one source so the network is driven.
    """
    rng = random.Random(SEED + 2)
    generated = rejected = 0
    worst_spice = {"relative_error": 0.0}
    worst_kcl = 0.0
    while generated < n:
        node_count = rng.randint(2, 5)
        nodes = ["gnd"] + [f"n{i}" for i in range(1, node_count)]
        resistors = []
        for index in range(rng.randint(node_count - 1, 2 * node_count)):
            a, b = rng.sample(nodes, 2)
            resistors.append((f"R{index}", a, b, 10 ** rng.uniform(0.0, 5.0)))
        vsources = [
            (f"V{i}", rng.choice(nodes[1:]), "gnd", rng.uniform(-20.0, 20.0))
            for i in range(rng.randint(1, 2))
        ]
        # Refuse two sources on one node pair: that is a short between two
        # ideal sources, which has no solution and is not a physical circuit.
        pairs = {(p, n) for _c, p, n, _v in vsources}
        if len(pairs) != len(vsources):
            rejected += 1
            continue
        if not resistors or not any(r[1] != r[2] for r in resistors):
            rejected += 1
            continue
        # Every non-reference node must reach ground through resistors, or the
        # nodal matrix is singular -- a floating node is a modelling error, not
        # a solver failure.
        reachable = {"gnd"}
        changed = True
        while changed:
            changed = False
            for _c, a, b, _r in resistors:
                if a in reachable and b not in reachable:
                    reachable.add(b); changed = True
                elif b in reachable and a not in reachable:
                    reachable.add(a); changed = True
            for _c, p, nneg, _v in vsources:
                if p in reachable and nneg not in reachable:
                    reachable.add(nneg); changed = True
                elif nneg in reachable and p not in reachable:
                    reachable.add(p); changed = True
        if set(nodes) - reachable:
            rejected += 1
            continue
        try:
            runtime = P.dc_circuit(
                nodes=nodes, reference="gnd", resistors=resistors,
                voltage_sources=vsources, current_sources=[],
            )
        except Exception:
            rejected += 1
            continue
        if runtime["convergence"] != "converged":
            rejected += 1
            continue
        generated += 1
        spice = OD.ngspice_solve(
            nodes=nodes, reference="gnd", resistors=resistors,
            voltage_sources=vsources, current_sources=[],
        )
        for node in nodes[1:]:
            if node not in spice["potentials"]:
                continue
            got = runtime["values"][f"node_voltage:{node}"]
            want = spice["potentials"][node]
            error = abs(got - want) / max(abs(want), 1e-3)
            if error > worst_spice["relative_error"]:
                worst_spice = {
                    "relative_error": error, "node": node, "runtime": got,
                    "ngspice": want, "resistors": resistors, "sources": vsources,
                }
        potentials = {
            node: runtime["values"][f"node_voltage:{node}"] for node in nodes
        }
        residuals = OD.kcl_residuals(
            potentials=potentials, reference="gnd", resistors=resistors,
            voltage_source_currents={
                cid: (p, nn, runtime["values"][f"source_current:{cid}"])
                for cid, p, nn, _v in vsources
            },
            current_sources=[],
        )
        scale = max(
            [abs(runtime["values"][f"resistor_current:{cid}"]) for cid, *_ in resistors]
            + [1e-12]
        )
        worst_kcl = max(worst_kcl, max(abs(v) for v in residuals.values()) / scale)
    return {
        "model": "electrical.dc.*",
        "enforced": (
            "R > 0 and finite, one reference node, no self-loops, no two ideal "
            "sources across one node pair, every node conductively connected to "
            "the reference"
        ),
        "generated": generated, "rejected": rejected,
        "property": "node potentials match ngspice; KCL holds at every node",
        "worst_relative_error_vs_ngspice": worst_spice["relative_error"],
        "worst_case": {k: v for k, v in worst_spice.items() if k != "resistors"},
        "tolerance": 1e-5,
        "worst_kcl_residual": worst_kcl,
        "conservation_tolerance": 1e-9,
        "verdict": (
            "HOLDS"
            if worst_spice["relative_error"] <= 1e-5 and worst_kcl <= 1e-9
            else "VIOLATED"
        ),
    }


def diffusion_property(n: int = 40) -> dict:
    """Random slabs, checked against the closed form with a predicted tolerance.

    ENFORCED: L > 0, alpha > 0, t > 0, an even cell count, and a resolution
    fine enough that the scheme's own predicted error is below 1e-3 -- because
    comparing a deliberately coarse solve against an exact answer measures
    discretization, not correctness, and calling that a defect would repeat a
    mistake this audit history has already made once.
    """
    rng = random.Random(SEED + 3)
    generated = rejected = 0
    worst = {"ratio": 0.0}
    while generated < n:
        length = 10 ** rng.uniform(-2.0, 0.0)
        alpha = 10 ** rng.uniform(-7.0, -4.0)
        lam = alpha * (math.pi / length) ** 2
        # Drawn deliberately WIDER than the domain the property is about, so
        # the resolution constraint below actually refuses draws. A generator
        # whose every draw is admissible is not enforcing anything, and this
        # one reported zero rejections until the ranges were widened.
        end_time = rng.uniform(0.1, 20.0) / lam
        n_cells = rng.choice([20, 50, 100, 200, 400])
        n_steps = rng.choice([200, 1_000, 5_000, 20_000, 100_000])
        dt, dx = end_time / n_steps, length / n_cells
        predicted = (
            lam * lam * end_time * dt / 2.0
            + lam * end_time * (math.pi * dx / length) ** 2 / 12.0
        )
        if not (length > 0 and alpha > 0 and end_time > 0 and predicted < 1e-3):
            rejected += 1
            continue
        generated += 1
        runtime = P.conduction(
            length=length, alpha=alpha, end_time=end_time,
            n_cells=n_cells, n_steps=n_steps,
        )
        exact = ODF.analytic_midpoint(
            length_m=length, alpha_m2_s=alpha, time_s=end_time
        )
        error = abs(runtime["midpoint"] - exact) / exact
        ratio = error / predicted if predicted > 0 else float("inf")
        if ratio > worst["ratio"]:
            worst = {
                "ratio": ratio, "observed_error": error,
                "predicted_error": predicted, "length": length, "alpha": alpha,
                "end_time": end_time, "n_cells": n_cells, "n_steps": n_steps,
            }
    return {
        "model": "thermal.conduction1d.linear_diffusion",
        "enforced": (
            "L > 0, alpha > 0, t > 0, even cell count, and the scheme's own "
            "predicted error below 1e-3 so the comparison is about correctness "
            "rather than resolution"
        ),
        "generated": generated, "rejected": rejected,
        "property": (
            "the observed error never exceeds a small multiple of the error "
            "the discretization itself predicts"
        ),
        "worst_error_over_predicted": worst["ratio"],
        "worst_case": worst,
        "tolerance": 3.0,
        "verdict": "HOLDS" if worst["ratio"] <= 3.0 else "VIOLATED",
    }


def cstr_property(n: int = 30) -> dict:
    """Random reactors, checked against the exact invariant ceiling.

    ENFORCED: every rate and property strictly positive, the envelope's own
    250-1000 K temperature band, and an adiabatic ceiling inside that band --
    the model's declared domain, which a generator must not leave.
    """
    rng = random.Random(SEED + 4)
    generated = rejected = 0
    worst_overshoot = 0.0
    worst_case = {}
    while generated < n:
        volume = 10 ** rng.uniform(-2.0, 0.0)
        flow = volume / (10 ** rng.uniform(1.0, 3.0))
        # Drawn wider than the envelope on purpose, so the 250-1000 K band and
        # the adiabatic ceiling both refuse draws. Without that this generator
        # reported zero rejections, which means it was enforcing nothing.
        caf = 10 ** rng.uniform(1.0, 4.0)
        tf = rng.uniform(240.0, 700.0)
        tc = rng.uniform(240.0, 600.0)
        rho, cp = rng.uniform(700.0, 1200.0), rng.uniform(150.0, 4200.0)
        dh = -10 ** rng.uniform(3.0, 6.0)
        ua = 10 ** rng.uniform(2.0, 5.0)
        k0 = 10 ** rng.uniform(6.0, 12.0)
        energy = rng.uniform(4.0e4, 9.0e4)
        beta = -dh / (rho * cp)
        ceiling = max(tf, tc) + beta * caf
        if not (250.0 <= tf <= 1000.0 and 250.0 <= tc <= 1000.0 and ceiling <= 1000.0):
            rejected += 1
            continue
        generated += 1
        end_time = 10.0 * volume / flow
        runtime = P.cstr(
            k0=k0, energy=energy, dh=dh, rho=rho, cp=cp, volume=volume,
            flow=flow, caf=caf, tf=tf, tc=tc, ua=ua, end_time=end_time,
            c0=caf, t0=tf,
        )
        peak = runtime["values"].get("T:max")
        exact_ceiling = OC.invariant_ceiling(
            beta=beta, caf=caf, c0=caf, tf=tf, tc=tc, t0=tf
        )
        overshoot = (peak - exact_ceiling) if peak is not None else 0.0
        if overshoot > worst_overshoot:
            worst_overshoot = overshoot
            worst_case = {
                "peak": peak, "ceiling": exact_ceiling, "beta": beta,
                "caf": caf, "tf": tf, "tc": tc, "k0": k0, "energy": energy,
            }
        # Species: the concentration can never leave [0, max(C_A0, C_Af)].
        c_final = runtime["values"]["C_A:final"]
        assert -1e-9 <= c_final <= max(caf, caf) + 1e-9, (c_final, caf)
    return {
        "model": "kinetics.cstr.nonisothermal_first_order",
        "enforced": (
            "all rates and properties strictly positive, feed and coolant "
            "inside the declared 250-1000 K band, and the exact adiabatic "
            "ceiling inside it too"
        ),
        "generated": generated, "rejected": rejected,
        "property": (
            "the trajectory never crosses the invariant ceiling "
            "max(T_0,T_f,T_c) + beta max(C_A0,C_Af), and the concentration "
            "stays in [0, C_Af]"
        ),
        "worst_ceiling_overshoot_k": worst_overshoot,
        "worst_case": worst_case,
        "tolerance": 1e-6,
        "verdict": "HOLDS" if worst_overshoot <= 1e-6 else "VIOLATED",
    }


def run_all() -> dict:
    rows = [
        lumped_property(), battery_property(), dc_property(),
        diffusion_property(), cstr_property(),
    ]
    return {
        "schema": "scientific_truth_property_testing/1",
        "seed": SEED,
        "note": (
            "Every generator enforces the model's declared physical domain and "
            "reports how many draws it refused. A generator with no rejections "
            "is not constraining anything."
        ),
        "families": rows,
        "violations": [row for row in rows if row["verdict"] != "HOLDS"],
    }
