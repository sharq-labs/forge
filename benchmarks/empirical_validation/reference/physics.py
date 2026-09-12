"""Closed forms and discrete schemes for the reference branch.

Written fresh for this round. The previous round's oracles are not imported,
even though they exist and are left untouched: a defect in one of them would
otherwise be inherited here and the two rounds would stop being separate
evidence.

Every function takes SI floats from adapter B and returns SI floats. No
engcore import appears anywhere in this file or in anything it imports.
"""

from __future__ import annotations

import math

from .integrate import bisect, refinement_ladder


# =====================================================================
# Lumped first-order body
# =====================================================================
#
#   C dT/dt = Q - hA (T - T_amb)
#
# Divide by C and let tau = C/hA, T_ss = T_amb + Q/hA. Then
# dT/dt = -(T - T_ss)/tau, whose solution through T(0) = T_0 is the
# exponential relaxation below. Derived here from the balance, not read off
# any implementation.


def lumped_closed_form(problem: dict) -> dict:
    tau = problem["heat_capacity_j_per_k"] / problem["ambient_conductance_w_per_k"]
    steady = (
        problem["ambient_temperature_k"]
        + problem["heat_input_w"] / problem["ambient_conductance_w_per_k"]
    )
    initial = problem["initial_temperature_k"]
    duration = problem["duration_s"]
    final = steady + (initial - steady) * math.exp(-duration / tau)
    return {
        "time_constant_s": tau,
        "steady_state_temperature_k": steady,
        "final_temperature_k": final,
    }


def lumped_rk4(problem: dict, *, step_counts=(25_000, 50_000, 100_000, 200_000)) -> dict:
    """The same balance integrated numerically, from the balance itself.

    An exponential and an RK4 march agreeing is not two views of one formula:
    the march never forms an exponential and would diverge from it if the
    balance had been transcribed differently.
    """
    capacity = problem["heat_capacity_j_per_k"]
    conductance = problem["ambient_conductance_w_per_k"]
    heat = problem["heat_input_w"]
    ambient = problem["ambient_temperature_k"]

    def rhs(_t, state):
        return [(heat - conductance * (state[0] - ambient)) / capacity]

    ladder = refinement_ladder(
        rhs,
        [problem["initial_temperature_k"]],
        t0=0.0,
        t1=problem["duration_s"],
        step_counts=step_counts,
    )
    return {
        "final_temperature_k": ladder["state"][0],
        "self_resolution": ladder["self_resolution"],
        "ladder": [
            {"n_steps": e["n_steps"], "final_temperature_k": e["state"][0]}
            for e in ladder["ladder"]
        ],
    }


def lumped_energy_balance(problem: dict, final_temperature_k: float) -> dict:
    """First law over the interval, with the loss integrated in closed form.

        integral_0^t hA (T - T_amb) dt' = hA tau (T_0 - T_ss)(1 - e^{-t/tau})
                                          + hA (T_ss - T_amb) t

    The stored energy is C (T_end - T_0). Heat in is Q t.
    """
    capacity = problem["heat_capacity_j_per_k"]
    conductance = problem["ambient_conductance_w_per_k"]
    heat = problem["heat_input_w"]
    ambient = problem["ambient_temperature_k"]
    initial = problem["initial_temperature_k"]
    duration = problem["duration_s"]

    tau = capacity / conductance
    steady = ambient + heat / conductance
    lost = conductance * tau * (initial - steady) * (
        1.0 - math.exp(-duration / tau)
    ) + conductance * (steady - ambient) * duration
    stored = capacity * (final_temperature_k - initial)
    supplied = heat * duration
    scale = max(abs(supplied), abs(lost), abs(stored), 1e-300)
    return {
        "stored_j": stored,
        "supplied_j": supplied,
        "lost_j": lost,
        "residual_j": stored - (supplied - lost),
        "normalised_residual": abs(stored - (supplied - lost)) / scale,
    }


# =====================================================================
# 1-D linear diffusion
# =====================================================================
#
#   du/dt = alpha u_xx,  u(0,t) = u(L,t) = 0,  u(x,0) = sin(pi x / L)
#
# Separation of variables gives u = sum_n b_n sin(n pi x/L) exp(-alpha (n pi/L)^2 t).
# For the single-mode initial condition every b_n but the first is zero, so the
# series is exact with one term. At x = L/2 the sine is exactly 1.


def diffusion_analytic_midpoint(problem: dict) -> float:
    decay = problem["diffusivity_m2_per_s"] * (math.pi / problem["length_m"]) ** 2
    return math.exp(-decay * problem["end_time_s"])


def diffusion_predicted_error(problem: dict) -> dict:
    """The error the declared scheme must make, term by term.

    Backward Euler in time on du/dt = -lambda u has amplification 1/(1 + lambda dt)
    against the exact e^{-lambda dt}; expanding, the relative error accumulated
    over t is lambda^2 t dt / 2 to leading order.

    The three-point central difference of sin(pi x/L) returns
    -(2/dx^2)(1 - cos(pi dx/L)) sin, whose bracket expands as
    (pi/L)^2 (1 - (pi dx/L)^2/12), so the discrete decay rate is short by the
    factor (pi dx/L)^2/12 and the solution is high by lambda t (pi dx/L)^2/12.

    Both were derived here. The sum is what the observed error is divided by.
    """
    length = problem["length_m"]
    alpha = problem["diffusivity_m2_per_s"]
    decay = alpha * (math.pi / length) ** 2
    dx = length / problem["n_cells"]
    dt = problem["end_time_s"] / problem["n_steps"]
    time_error = decay * decay * problem["end_time_s"] * dt / 2.0
    space_error = decay * problem["end_time_s"] * (math.pi * dx / length) ** 2 / 12.0
    return {
        "lambda_per_s": decay,
        "dx_m": dx,
        "dt_s": dt,
        "fourier_number": alpha * dt / (dx * dx),
        "time_error": time_error,
        "space_error": space_error,
        "predicted_relative_error": time_error + space_error,
    }


def diffusion_ftcs_predicted_error(
    problem: dict, *, dx: float, dt: float
) -> dict:
    """The SIGNED error the explicit march is predicted to make.

    Forward Euler on du/dt = -lambda u has amplification (1 - lambda dt)
    against the exact e^{-lambda dt}, so it under-predicts by lambda^2 t dt/2 --
    the same magnitude as the implicit scheme and the OPPOSITE sign. The
    central difference in space is the same term for both schemes and is
    positive in both.

    Having both signed predictions is what lets the two marches be compared
    against each other through the difference they are predicted to have,
    rather than through a bound that would have to be padded.
    """
    length = problem["length_m"]
    decay = problem["diffusivity_m2_per_s"] * (math.pi / length) ** 2
    end_time = problem["end_time_s"]
    return {
        "time_error": -decay * decay * end_time * dt / 2.0,
        "space_error": decay * end_time * (math.pi * dx / length) ** 2 / 12.0,
        "predicted_relative_error": (
            -decay * decay * end_time * dt / 2.0
            + decay * end_time * (math.pi * dx / length) ** 2 / 12.0
        ),
    }


def diffusion_ftcs_midpoint(problem: dict, *, n_cells: int = 400, target_r: float = 0.25) -> dict:
    """Explicit forward-time centred-space march to u(L/2, t).

    A third route: neither the closed form nor the implicit scheme the Core
    runs. Held at r = 1/4, comfortably inside the von Neumann stability limit
    of 1/2, so what is left is discretization error only.
    """
    if n_cells % 2 != 0:
        raise ValueError("n_cells must be even so L/2 is a node")
    length = problem["length_m"]
    alpha = problem["diffusivity_m2_per_s"]
    end_time = problem["end_time_s"]
    dx = length / n_cells
    n_steps = max(1, math.ceil(end_time / (target_r * dx * dx / alpha)))
    dt = end_time / n_steps
    r = alpha * dt / (dx * dx)
    u = [math.sin(math.pi * i * dx / length) for i in range(1, n_cells)]
    for _ in range(n_steps):
        left = 0.0
        nxt = []
        for i, centre in enumerate(u):
            right = u[i + 1] if i + 1 < len(u) else 0.0
            nxt.append(centre + r * (right - 2.0 * centre + left))
            left = centre
        u = nxt
    return {"midpoint": u[n_cells // 2 - 1], "r": r, "dx_m": dx, "dt_s": dt, "n_steps": n_steps}


# =====================================================================
# Battery cell
# =====================================================================
#
# Coulomb counting at constant current:  z(t) = z_0 - I t / (eta Q)
# Affine open-circuit curve:             OCV(z) = V_e + (V_f - V_e) z
# Internal resistance:                   V = OCV(z) - I R,  Q_gen = I^2 R
# Voltage cutoff as a state of charge:   z_cut = (V_cut + I R - V_e)/(V_f - V_e)
# Runtime to a stop state:               t = (z_0 - z_stop) eta Q / I
#
# All exact algebra, derived from the definitions above.


def battery(problem: dict) -> dict:
    capacity_c = problem["nominal_capacity_c"]
    current = problem["current_a"]
    efficiency = problem["coulombic_efficiency"]
    span = (
        problem["open_circuit_voltage_at_full_v"]
        - problem["open_circuit_voltage_at_empty_v"]
    )
    empty = problem["open_circuit_voltage_at_empty_v"]

    z_end = problem["initial_state_of_charge"] - current * problem["duration_s"] / (
        efficiency * capacity_c
    )
    ocv = empty + span * z_end
    terminal = ocv - current * problem["internal_resistance_ohm"]
    heat = current * current * problem["internal_resistance_ohm"]

    cutoff_soc = None
    runtime = None
    if problem.get("cutoff_voltage_v") is not None:
        cutoff_soc = (
            problem["cutoff_voltage_v"]
            + current * problem["internal_resistance_ohm"]
            - empty
        ) / span
        runtime = (
            (problem["initial_state_of_charge"] - cutoff_soc)
            * efficiency
            * capacity_c
            / current
        )

    charge_drawn = current * problem["duration_s"]
    charge_accounted = (
        problem["initial_state_of_charge"] - z_end
    ) * efficiency * capacity_c
    # z0 - z_end is a difference of nearly equal doubles. Below this floor a
    # relative criterion is reporting cancellation, not physics.
    floor_c = (
        4.0
        * math.ulp(problem["initial_state_of_charge"])
        * efficiency
        * capacity_c
    )
    return {
        "final_state_of_charge": z_end,
        "open_circuit_voltage_v": ocv,
        "terminal_voltage_v": terminal,
        "heat_generation_w": heat,
        "voltage_cutoff_state_of_charge": cutoff_soc,
        "runtime_to_cutoff_s": runtime,
        "charge_drawn_c": charge_drawn,
        "charge_accounted_c": charge_accounted,
        "charge_residual_c": charge_accounted - charge_drawn,
        "cancellation_floor_c": floor_c,
    }


def peukert_effective_capacity_c(problem: dict) -> float:
    """Q_eff = Q_nom (I_ref/I)^(k-1), from I^k t = constant.

    Peukert's law states that I^k t is invariant. Writing the delivered charge
    as Q = I t gives Q = constant / I^(k-1); referring it to the current the
    nominal capacity was measured at removes the constant and leaves the form
    above. The derivation is repeated here because the invariant, not the
    rearrangement, is what ``peukert_invariant`` below checks.
    """
    return problem["nominal_capacity_c"] * (
        problem["peukert_reference_current_a"] / problem["current_a"]
    ) ** (problem["peukert_exponent"] - 1.0)


def peukert_invariant(problem: dict, effective_capacity_c: float) -> dict:
    """I^k t against the same product at the reference current.

    This is the law as Peukert wrote it, not the capacity form. If the Core
    evaluated the rearrangement with the exponent off by one, or inverted the
    ratio, the capacity form could still look plausible while this invariant
    would not hold.
    """
    exponent = problem["peukert_exponent"]
    current = problem["current_a"]
    reference = problem["peukert_reference_current_a"]
    runtime = effective_capacity_c / current
    reference_runtime = problem["nominal_capacity_c"] / reference
    product = current**exponent * runtime
    reference_product = reference**exponent * reference_runtime
    return {
        "product": product,
        "reference_product": reference_product,
        "relative_difference": abs(product - reference_product)
        / abs(reference_product),
    }


# =====================================================================
# Linear temperature coefficient of resistance, and the standard it truncates
# =====================================================================


def linear_tcr(problem: dict, temperature_k: float) -> float:
    return problem["reference_resistance_ohm"] * (
        1.0
        + problem["temperature_coefficient_per_k"]
        * (temperature_k - problem["reference_temperature_k"])
    )


def callendar_van_dusen(coefficients: dict, temperature_c: float) -> float:
    """R(t) = R0 (1 + A t + B t^2) for t >= 0 degC, the IEC 60751 form."""
    if temperature_c < 0.0:
        raise ValueError("the two-coefficient branch is the t >= 0 degC branch")
    return coefficients["r_zero_ohm"] * (
        1.0
        + coefficients["coefficient_A_per_degC"] * temperature_c
        + coefficients["coefficient_B_per_degC2"] * temperature_c * temperature_c
    )


def predicted_linear_truncation(coefficients: dict, temperature_c: float) -> float:
    """|B| t^2 / (1 + A t): the relative size of the term a linear law drops.

    Preregistered in VALIDATION_PLAN.json before any comparison was run.
    """
    return (
        abs(coefficients["coefficient_B_per_degC2"])
        * temperature_c
        * temperature_c
        / (1.0 + coefficients["coefficient_A_per_degC"] * temperature_c)
    )


# =====================================================================
# Non-isothermal CSTR
# =====================================================================
#
#   dC_A/dt = a (C_Af - C_A) - k(T) C_A
#   dT/dt   = a (T_f - T) + beta k(T) C_A - gamma (T - T_c)
#
# with a = q/V, beta = (-dH)/(rho c_p), gamma = UA/(V rho c_p) and
# k(T) = k0 exp(-E/(R T)). Species and energy balances on a perfectly mixed
# constant-volume tank; written out here from the balances.


def cstr_rate_constant(problem: dict, temperature_k: float) -> float:
    if problem["activation_energy_j_per_mol"] == 0.0:
        # The constant-rate model family. Deliberately NOT evaluated as
        # exp(-0/(RT)): that would be the Arrhenius expression again, and the
        # point of the alternative family is that no exponential is formed.
        return problem["k0_per_s"]
    return problem["k0_per_s"] * math.exp(
        -problem["activation_energy_j_per_mol"]
        / (problem["molar_gas_constant_j_per_mol_k"] * temperature_k)
    )


def cstr_rhs(problem: dict):
    a = problem["dilution_rate_per_s"]
    beta = problem["beta_m3_k_per_mol"]
    gamma = problem["gamma_per_s"]
    feed_c = problem["feed_concentration_mol_per_m3"]
    feed_t = problem["feed_temperature_k"]
    coolant = problem["coolant_temperature_k"]

    def rhs(_t, state):
        concentration, temperature = state
        rate = cstr_rate_constant(problem, temperature)
        return [
            a * (feed_c - concentration) - rate * concentration,
            a * (feed_t - temperature)
            + beta * rate * concentration
            - gamma * (temperature - coolant),
        ]

    return rhs


def cstr_trajectory(problem: dict, *, step_counts=(20_000, 40_000, 80_000, 160_000)) -> dict:
    ladder = refinement_ladder(
        cstr_rhs(problem),
        [
            problem["initial_concentration_mol_per_m3"],
            problem["initial_temperature_k"],
        ],
        t0=0.0,
        t1=problem["end_time_s"],
        step_counts=step_counts,
    )
    return {
        "final_concentration_mol_per_m3": ladder["state"][0],
        "final_temperature_k": ladder["state"][1],
        "self_resolution": ladder["self_resolution"],
        "ladder": [
            {
                "n_steps": e["n_steps"],
                "concentration": e["state"][0],
                "temperature": e["state"][1],
            }
            for e in ladder["ladder"]
        ],
    }


def cstr_steady_states(problem: dict, *, lower_k: float = 250.0, upper_k: float = 700.0) -> list[float]:
    """Every steady temperature, found by bisection on the energy residual.

    At steady state the species balance gives C_A = a C_Af / (a + k(T)),
    and substituting into the energy balance leaves one scalar function of T:

        f(T) = a (T_f - T) + beta k(T) a C_Af/(a + k(T)) - gamma (T - T_c)

    Its roots are the steady states. They are bracketed by scanning a fine grid
    for sign changes and then bisected -- no Brent, because the Core uses it.
    """
    a = problem["dilution_rate_per_s"]
    beta = problem["beta_m3_k_per_mol"]
    gamma = problem["gamma_per_s"]
    feed_c = problem["feed_concentration_mol_per_m3"]
    feed_t = problem["feed_temperature_k"]
    coolant = problem["coolant_temperature_k"]

    def residual(temperature):
        rate = cstr_rate_constant(problem, temperature)
        concentration = a * feed_c / (a + rate)
        return (
            a * (feed_t - temperature)
            + beta * rate * concentration
            - gamma * (temperature - coolant)
        )

    roots = []
    samples = 20_000
    previous_t = lower_k
    previous_f = residual(previous_t)
    for i in range(1, samples + 1):
        current_t = lower_k + (upper_k - lower_k) * i / samples
        current_f = residual(current_t)
        if previous_f == 0.0:
            roots.append(previous_t)
        elif previous_f * current_f < 0.0:
            roots.append(bisect(residual, previous_t, current_t))
        previous_t, previous_f = current_t, current_f
    return roots


def cstr_invariant_ceiling(problem: dict) -> dict:
    """Z = T + beta C_A obeys dZ/dt = a (Z_f - Z) - gamma (T - T_c) exactly.

    Adding beta times the species balance to the energy balance cancels the
    reaction term identically, whatever the rate law is. So the bound this
    gives on the temperature never depends on Arrhenius being right, which is
    what makes it a check on the solve rather than a restatement of it.
    """
    beta = problem["beta_m3_k_per_mol"]
    z0 = (
        problem["initial_temperature_k"]
        + beta * problem["initial_concentration_mol_per_m3"]
    )
    z_feed = (
        problem["feed_temperature_k"]
        + beta * problem["feed_concentration_mol_per_m3"]
    )
    return {
        "z_initial": z0,
        "z_feed": z_feed,
        # With gamma >= 0 and T >= T_c the cooling term only removes energy, so
        # Z stays below max(Z_0, Z_feed) and T <= Z since beta C_A >= 0.
        "temperature_ceiling_k": max(z0, z_feed),
    }
