"""ST-1 to ST-4: every equation, derived independently, and checked dimensionally.

Each entry states what the physics REQUIRES, reconstructed here from balances
and constitutive laws, and then what the implementation evaluates. The two are
written separately on purpose: if they had been copied from one another this
file would prove nothing.

The dimensional column is worked term by term. A passing numerical test is not
accepted as evidence of dimensional validity anywhere in this file -- a model
whose coefficient carries the wrong power of a unit can match a reference case
exactly at the one operating point the reference was built at.
"""

from __future__ import annotations

VALID = "DIMENSIONALLY_VALID"

EQUATIONS = [
    {
        "domain": "thermal",
        "model_id": "thermal.lumped.first_order_capacity",
        "implementation_file": "src/engcore/domains/thermal_models/lumped.py",
        "entry_point": "LumpedThermalSolver.solve",
        "classification": "ODE, solved in closed form",
        "steady_or_transient": "transient",
        "linearity": "linear, constant coefficients",
        "numerical_method": "none: the analytic solution is evaluated with one math.exp",
        "tolerances": "not applicable; no iteration and no discretization",
        "expected_form": "C dT/dt = Q_in - hA (T - T_amb); T(t) = T_ss + (T_0 - T_ss) exp(-t/tau)",
        "derivation": (
            "Energy balance on a body at one uniform temperature. Rearranging, "
            "dT/dt = -(hA/C)(T - T_amb - Q/hA) = -(T - T_ss)/tau with "
            "tau = C/hA and T_ss = T_amb + Q/hA, whose solution is the "
            "exponential above. Derived here; the implementation was read "
            "afterwards and evaluates exactly this."
        ),
        "variables": {"T": "kelvin", "t": "second"},
        "parameters": {
            "C": "J/K, heat capacity", "hA": "W/K, conductance to ambient",
            "Q_in": "W, imposed heat", "T_amb": "K, ambient temperature",
        },
        "expected_output": "final temperature (K), steady state (K), time constant (s)",
        "sign_convention": (
            "Q_in > 0 adds energy; the loss term is subtracted, so a body "
            "hotter than ambient cools. A sign slip on the loss term would "
            "make every body run away exponentially, which the limit checks "
            "would catch immediately."
        ),
        "assumptions": [
            "one uniform temperature", "C and hA constant over the interval",
            "one exchange path to one prescribed ambient",
        ],
        "dimensional_check": (
            "tau = C/hA = (J/K)/(W/K) = J/W = s. "
            "T_ss = T_amb + Q/hA = K + W/(W/K) = K + K = K. "
            "The exponent t/tau = s/s is dimensionless, which is required for "
            "exp() to have an argument at all."
        ),
        "dimensional_verdict": VALID,
        "asymptotics": (
            "t -> 0 gives T_0; t -> infinity gives T_ss; hA -> infinity clamps "
            "to T_amb; hA -> 0 gives adiabatic heating at Q/C."
        ),
        "existing_tests": "tests/domains/thermal/ and the lumped invariants suite",
        "existing_oracle": "none in-repo; this round supplies an RK4 integration",
    },
    {
        "domain": "thermal",
        "model_id": "thermal.conduction1d.linear_diffusion",
        "implementation_file": "src/engcore/domains/thermal/conduction1d/solver.py",
        "entry_point": "solve_slab",
        "classification": "PDE, discretized",
        "steady_or_transient": "transient",
        "linearity": "linear, constant diffusivity",
        "numerical_method": (
            "backward Euler in time, second-order central differences in "
            "space; one sparse LU factorization reused every step"
        ),
        "tolerances": "residual_atol 1e-10, boundary_atol 1e-14",
        "expected_form": "du/dt = alpha d2u/dx2, u(0,t)=u(L,t)=0, u(x,0)=sin(pi x/L)",
        "derivation": (
            "Separation of variables gives u = SUM b_n sin(n pi x/L) "
            "exp(-alpha (n pi/L)^2 t). The initial condition is already the "
            "first eigenfunction, so the series collapses to one term and the "
            "reference is exact to rounding."
        ),
        "variables": {"u": "dimensionless", "x": "meter", "t": "second"},
        "parameters": {"alpha": "m^2/s, diffusivity", "L": "m, slab length"},
        "expected_output": "the normalized field, read at the midpoint",
        "sign_convention": (
            "alpha > 0 is diffusion and smooths the profile; a negative alpha "
            "would be anti-diffusion and is ill-posed, which is why the record "
            "refuses it."
        ),
        "assumptions": [
            "one spatial dimension", "no source term",
            "homogeneous Dirichlet boundaries held exactly at zero",
            "single-mode sinusoidal initial condition",
        ],
        "dimensional_check": (
            "alpha d2u/dx2 = (m^2/s)(1/m^2) x u = u/s = du/dt. "
            "The exponent alpha (pi/L)^2 t = (m^2/s)(1/m^2)(s) is "
            "dimensionless. The Fourier number alpha dt/dx^2 = "
            "(m^2/s)(s)/(m^2) is dimensionless, as a stability parameter must be."
        ),
        "dimensional_verdict": VALID,
        "asymptotics": (
            "t -> 0 returns the initial condition; t -> infinity decays to "
            "zero under homogeneous Dirichlet ends; alpha -> 0 freezes the "
            "profile. Refinement converges at first order in dt and second in dx."
        ),
        "existing_tests": "tests/domains/thermal/conduction1d/",
        "existing_oracle": (
            "reference.py, the closed form, which a test asserts never imports "
            "the solver"
        ),
    },
    {
        "domain": "battery",
        "model_id": "battery.cell.coulomb_counting",
        "implementation_file": "src/engcore/domains/battery/solver.py",
        "entry_point": "evaluate_step",
        "classification": "ODE with an exact integral",
        "steady_or_transient": "transient",
        "linearity": "linear",
        "numerical_method": "none: the integral is exact for a constant current",
        "tolerances": "not applicable",
        "expected_form": "z(t) = z_0 - I t / (eta Q_nom)",
        "derivation": (
            "Charge conservation. dz/dt = -I/(eta Q_nom) with the usable "
            "charge eta Q_nom; integrating a constant current is exact."
        ),
        "variables": {"z": "dimensionless", "t": "second"},
        "parameters": {
            "I": "A", "Q_nom": "A*h", "eta": "dimensionless coulombic efficiency",
        },
        "expected_output": "the state of charge at the end of the interval",
        "sign_convention": (
            "I > 0 is a discharge and lowers z. eta sits in the DENOMINATOR, "
            "so a cell of efficiency below 1 depletes faster than an ideal "
            "one: the usable charge is eta Q_nom. That is a modelling choice "
            "and it is self-consistent -- the runtime equation uses the same "
            "eta Q_nom, which this round checks as a pair."
        ),
        "assumptions": ["constant current over the interval", "no self-discharge", "no feedback"],
        "dimensional_check": (
            "I t/(eta Q_nom) = (A)(s)/(A h) requires the hours conversion to "
            "be present; without it the term is 3600 times too large. The Core "
            "converts through its unit system and this audit's oracle divides "
            "by an explicit 3600, so the two disagree loudly if either is wrong."
        ),
        "dimensional_verdict": VALID,
        "asymptotics": "I -> 0 leaves z unchanged; t -> 0 leaves z unchanged.",
        "existing_tests": "tests/domains/battery/",
        "existing_oracle": "none in-repo; this round supplies charge conservation in coulombs",
    },
    {
        "domain": "battery",
        "model_id": "battery.cell.rint_ocv",
        "implementation_file": "src/engcore/domains/battery/solver.py",
        "entry_point": "evaluate_step",
        "classification": "algebraic constitutive relation",
        "steady_or_transient": "quasi-static",
        "linearity": "affine in z, linear in I",
        "numerical_method": "none",
        "tolerances": "not applicable",
        "expected_form": "V = OCV(z) - I R_int, OCV(z) = V_e + (V_f - V_e) z, Q_gen = I^2 R_int",
        "derivation": (
            "Kirchhoff's voltage law around one source in series with one "
            "resistance; Joule's law for the dissipation in that resistance."
        ),
        "variables": {"V": "volt", "z": "dimensionless"},
        "parameters": {"R_int": "ohm", "V_f": "volt", "V_e": "volt", "I": "ampere"},
        "expected_output": "terminal voltage, open-circuit voltage, heat generation",
        "sign_convention": (
            "the IR drop OPPOSES a discharge, so V < OCV for I > 0. The heat "
            "is quadratic in current and therefore positive whichever way the "
            "current flows: a resistor cannot refrigerate."
        ),
        "assumptions": ["one constant series resistance", "affine OCV chord unless a curve is declared"],
        "dimensional_check": (
            "I R = (A)(ohm) = V, so OCV - I R is volts minus volts. "
            "I^2 R = (A^2)(ohm) = W. A model that wrote I R^2 or I^2/R would "
            "be dimensionally wrong and is not."
        ),
        "dimensional_verdict": VALID,
        "asymptotics": "I -> 0 gives V = OCV; R -> 0 gives V = OCV; z -> 0 gives V_e.",
        "existing_tests": "tests/domains/battery/",
        "existing_oracle": "none in-repo; this round supplies KVL and Joule's law",
    },
    {
        "domain": "battery",
        "model_id": "battery.cell.constant_current_runtime",
        "implementation_file": "src/engcore/domains/battery/solver.py",
        "entry_point": "evaluate_step / _binding_cutoff",
        "classification": "algebraic, a first-crossing time",
        "steady_or_transient": "transient endpoint",
        "linearity": "linear",
        "numerical_method": "none: the binding cutoff is chosen by comparison, never by iteration",
        "tolerances": "not applicable",
        "expected_form": (
            "t = (z_0 - z_stop) eta Q_nom / I, with "
            "z_cut,V = (V_cut + I R - V_e)/(V_f - V_e)"
        ),
        "derivation": (
            "The charge between two states divided by the current. The voltage "
            "cutoff is inverted from the same KVL relation: setting "
            "V = V_cut in V = OCV(z) - I R and solving the affine OCV for z."
        ),
        "variables": {"t": "second"},
        "parameters": {"z_0": "dimensionless", "z_stop": "dimensionless"},
        "expected_output": "runtime to the binding cutoff",
        "sign_convention": (
            "a discharge walks z DOWN, so the binding cutoff is the HIGHER of "
            "the two candidates -- whichever is reached first on a falling "
            "trajectory. Taking the lower one would report the wrong stop."
        ),
        "assumptions": ["constant current", "the affine chord for the voltage inversion"],
        "dimensional_check": (
            "(dimensionless)(A h)/(A) = h, converted to seconds. The inversion "
            "divides volts by volts and is dimensionless, as a state of charge "
            "must be."
        ),
        "dimensional_verdict": VALID,
        "asymptotics": "z_stop -> z_0 gives t -> 0; larger I gives a shorter runtime.",
        "existing_tests": "tests/domains/battery/",
        "existing_oracle": "none in-repo; this round derives both the inversion and the runtime",
    },
    {
        "domain": "battery",
        "model_id": "battery.cell.peukert_capacity_derating",
        "implementation_file": "src/engcore/domains/battery/context.py",
        "entry_point": "peukert_effective_capacity",
        "classification": "empirical correlation",
        "steady_or_transient": "steady, a rating",
        "linearity": "power law",
        "numerical_method": "none",
        "tolerances": "not applicable",
        "expected_form": "Q_eff = Q_nom (I_ref/I)^(k-1)",
        "derivation": (
            "Peukert's law is I^k t = constant. At the reference current "
            "Q_nom = I_ref t_ref, so the constant is I_ref^(k-1) Q_nom; at "
            "another current Q = I t = constant/I^(k-1). Rearranged here."
        ),
        "variables": {"Q_eff": "A*h"},
        "parameters": {"k": "dimensionless exponent", "I_ref": "A"},
        "expected_output": "effective capacity at this current",
        "sign_convention": (
            "k > 1 makes a higher current deliver LESS charge. k = 1 is the "
            "ideal cell and the expression collapses to Q_nom."
        ),
        "assumptions": ["constant-current discharge", "k constant over the fitted range"],
        "dimensional_check": (
            "(I_ref/I) is dimensionless, so raising it to any power is "
            "legitimate, and the result carries Q_nom's units unchanged. A "
            "formulation that exponentiated a dimensional current would be "
            "meaningless."
        ),
        "dimensional_verdict": VALID,
        "asymptotics": "k -> 1 gives Q_nom; I -> I_ref gives Q_nom; larger I gives less charge.",
        "existing_tests": "tests/domains/battery/",
        "existing_oracle": "none in-repo; this round re-derives the rearrangement",
    },
    *[
        {
            "domain": "electrical",
            "model_id": model_id,
            "implementation_file": "src/engcore/domains/electrical/dc/mna.py",
            "entry_point": "solve_circuit (modified nodal analysis)",
            "classification": "linear algebraic system",
            "steady_or_transient": "steady-state DC",
            "linearity": "linear",
            "numerical_method": "modified nodal analysis, direct dense solve",
            "tolerances": "residual checks on the assembled system",
            "expected_form": expected,
            "derivation": derivation,
            "variables": {"v": "volt", "i": "ampere"},
            "parameters": {"R": "ohm", "V_src": "volt", "I_src": "ampere"},
            "expected_output": "node potentials, branch currents, powers",
            "sign_convention": sign,
            "assumptions": ["lumped elements", "linear and time-invariant", "steady state"],
            "dimensional_check": dimensional,
            "dimensional_verdict": VALID,
            "asymptotics": asymptotics,
            "existing_tests": "tests/domains/electrical/",
            "existing_oracle": (
                "the repository ships an ngspice bridge; this round adds its "
                "own ngspice netlist and an incidence-matrix nodal solve"
            ),
        }
        for model_id, expected, derivation, sign, dimensional, asymptotics in [
            (
                "electrical.dc.kcl",
                "SUM of currents leaving a node = 0",
                "Charge conservation for a lumped network: no charge accumulates at a node.",
                "currents leaving are positive; the sum is identically zero, not approximately",
                "amperes summed with amperes; the residual is an ampere and must be round-off",
                "an undriven passive network carries no current",
            ),
            (
                "electrical.dc.resistor_ohm",
                "V = I R, P = V I = I^2 R >= 0",
                "Ohm's constitutive law and Joule's law for the dissipation.",
                "V measured a -> b with I positive in the same direction, so P is absorbed and non-negative",
                "(A)(ohm) = V and (A^2)(ohm) = W",
                "R -> 0 shorts the branch; R -> infinity opens it",
            ),
            (
                "electrical.dc.ideal_voltage_source",
                "v_pos - v_neg = V_src, irrespective of current",
                "The defining relation of an ideal source; the branch current is an extra MNA unknown.",
                "the reported branch current leaves the positive node, so a delivering source absorbs negative power",
                "volts equated with volts",
                "reversing the source negates every current and leaves every dissipation unchanged",
            ),
            (
                "electrical.dc.ideal_current_source",
                "I from -> to inside the source, irrespective of terminal voltage",
                "The dual of the ideal voltage source; it injects a known current.",
                "positive current flows from_node -> to_node inside the source, so it is extracted at from_node externally",
                "amperes injected into an ampere balance",
                "the terminal voltage is whatever the network develops",
            ),
            (
                "electrical.dc.regulated_voltage_source",
                "v_pos - v_neg = V_src, asserted where (|I| R_out/|V_src|)/band <= 1",
                "The ideal relation, with a Thevenin internal drop bounding where it is asserted.",
                "same as the ideal source; the band bounds the internal drop rather than changing the relation",
                "(A)(ohm)/(V) is dimensionless, so the utilization ratio is a pure number",
                "zero output resistance recovers the ideal source exactly",
            ),
            (
                "electrical.dc.self_heated_resistor",
                "V = I R with (T_body + |P| R_th)/T_permissible <= 1",
                "Ohm's law, with the element-to-body temperature rise from a thermal resistance.",
                "dissipation is positive and raises the element above its body",
                "(W)(K/W) = K, added to a body temperature in K, divided by a permissible K: dimensionless",
                "zero thermal resistance puts the element at its body temperature",
            ),
        ]
    ],
    *[
        {
            "domain": "electrical",
            "model_id": model_id,
            "implementation_file": "src/engcore/domains/electrical/material.py",
            "entry_point": "ResistancePropertySolver.solve",
            "classification": "algebraic constitutive relation",
            "steady_or_transient": "a single evaluation at a supplied temperature",
            "linearity": "linear in temperature",
            "numerical_method": "none",
            "tolerances": "not applicable",
            "expected_form": "R(T) = R_ref (1 + alpha (T - T_ref))",
            "derivation": (
                "The first-order Taylor expansion of rho(T) about T_ref, with "
                "alpha the relative slope (1/R)(dR/dT) at the reference."
            ),
            "variables": {"R": "ohm", "T": "kelvin"},
            "parameters": {
                "R_ref": "ohm", "alpha": "1/K", "T_ref": "kelvin",
            },
            "expected_output": "resistance at the supplied temperature",
            "sign_convention": (
                "alpha > 0 is a metal and the resistance rises with "
                "temperature; alpha < 0 falls. The slope dR/dT is exactly "
                "R_ref alpha, which this round checks numerically."
            ),
            "assumptions": ["isotropic scalar resistance", "temperature supplied, never inferred"],
            "dimensional_check": (
                "alpha (T - T_ref) = (1/K)(K) is dimensionless, so the bracket "
                "is a pure number and the product carries R_ref's ohms. An "
                "alpha carrying ohms per kelvin would make the bracket "
                "dimensionally inhomogeneous -- one term a number, the other "
                "an ohm-kelvin -- which is the classic TCR unit error and is "
                "not present."
            ),
            "dimensional_verdict": VALID,
            "asymptotics": (
                "T -> T_ref gives R_ref exactly; alpha -> 0 gives a "
                "temperature-independent resistor"
            ),
            "existing_tests": "tests/domains/electrical/test_material_applicability.py",
            "existing_oracle": "none in-repo; this round supplies 50-digit arithmetic",
        }
        for model_id in (
            "electrical.material.linear_tcr_resistance",
            "electrical.material.rated_linear_tcr_resistance",
        )
    ],
    *[
        {
            "domain": "kinetics",
            "model_id": model_id,
            "implementation_file": "src/engcore/domains/kinetics/cstr/solver.py",
            "entry_point": "solve_reactor (assemble -> rhs, jacobian)",
            "classification": "coupled nonlinear ODE system",
            "steady_or_transient": "transient, stiff near ignition",
            "linearity": nonlinearity,
            "numerical_method": (
                "implicit stiff integration with an analytic Jacobian; RK45 "
                "admitted only as a measuring instrument"
            ),
            "tolerances": "solver rtol/atol, with an RHS evaluation budget",
            "expected_form": (
                "dC_A/dt = a (C_Af - C_A) - k C_A ; "
                "dT/dt = a (T_f - T) + beta k C_A - gamma (T - T_c)"
                + rate_form
            ),
            "derivation": (
                "Species balance V dC/dt = q (C_Af - C_A) - V r and energy "
                "balance V rho cp dT/dt = q rho cp (T_f - T) + (-dH) V r "
                "- UA (T - T_c), divided through by V and by V rho cp. "
                "a = q/V, beta = (-dH)/(rho cp), gamma = UA/(V rho cp). "
                "Derived here from the balances."
            ),
            "variables": {"C_A": "mol/m^3", "T": "kelvin", "t": "second"},
            "parameters": {
                "a": "1/s", "beta": "m^3 K/mol", "gamma": "1/s",
                "k0": "1/s", "E": "J/mol", "R": "J/(mol K)",
            },
            "expected_output": "concentration, temperature, conversion, peak temperature",
            "sign_convention": (
                "beta = (-dH)/(rho cp) is POSITIVE for an exotherm (dH < 0), "
                "so the reaction term raises the temperature; an endotherm "
                "flips it and must cool the tank. The cooling term is "
                "subtracted, so a jacket below the tank removes heat. Getting "
                "the enthalpy sign backwards is the single most consequential "
                "sign error available in reactor engineering, and it would "
                "still return entirely plausible temperatures."
            ),
            "assumptions": [
                "perfectly mixed", "constant volume and properties",
                "single liquid phase", "one irreversible first-order reaction",
            ],
            "dimensional_check": (
                "a (C_Af - C_A) = (1/s)(mol/m^3) = mol/(m^3 s) = dC/dt. "
                "k C_A = (1/s)(mol/m^3), the same. "
                "beta k C_A = (m^3 K/mol)(1/s)(mol/m^3) = K/s = dT/dt. "
                "gamma (T - T_c) = (1/s)(K) = K/s. "
                "beta = (J/mol)/((kg/m^3)(J/(kg K))) = (J/mol)(m^3 K/J) = "
                "m^3 K/mol, as required. "
                "gamma = (W/K)/((m^3)(kg/m^3)(J/(kg K))) = (W/K)(K/J) = 1/s. "
                "E/(R T) = (J/mol)/((J/(mol K))(K)) is dimensionless, which it "
                "must be to be an exponent."
            ),
            "dimensional_verdict": VALID,
            "asymptotics": (
                "k -> 0 washes the tank out to the feed concentration and the "
                "temperature to (a T_f + gamma T_c)/(a + gamma); UA -> 0 is "
                "adiabatic; the invariant Z = T + beta C_A bounds the "
                "temperature for any rate law"
            ),
            "existing_tests": "tests/domains/kinetics/",
            "existing_oracle": (
                "an RK45 probe in-repo; this round adds an independent RK4, "
                "steady-state root finding, and the invariant"
            ),
        }
        for model_id, nonlinearity, rate_form in [
            (
                "kinetics.cstr.nonisothermal_first_order",
                "nonlinear: Arrhenius couples the two balances",
                " ; k(T) = k0 exp(-E/(R T))",
            ),
            (
                "kinetics.cstr.nonisothermal_first_order_constant_rate",
                "linear: the Arrhenius coupling is removed",
                " ; k = k_const",
            ),
        ]
    ],
]
