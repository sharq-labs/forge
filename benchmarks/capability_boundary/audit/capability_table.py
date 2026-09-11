"""What each shipped model can actually represent, read off its equations.

This is the audit's own scientific reading, kept as reviewable data rather
than prose so every later count can be computed from it instead of asserted.

The method for each model, in the order the round specifies:

CB-2  Ignore the name and the marketing sentence. Read the equation the
      implementation evaluates and write down the regime it defines --
      steady or transient, linear or not, lumped or distributed, which
      coefficients are frozen, which correlations carry their own range.
CB-3  Expand the published claim into the real physical systems a competent
      caller would believe are covered, then ask of each whether those
      equations can carry it.
CB-4  Classify the published capability against that reading.

``represents`` values:

  YES        the equations carry this case
  BOUNDED    the equations do not carry it, and a declared validity condition
             refuses or UNKNOWNs it -- the boundary is enforced
  DISCLOSED  the equations do not carry it, no condition catches it, and the
             record says so in its assumptions or exclusions
  NO         the equations do not carry it, nothing refuses it, and the record
             does not say so -- a capability-boundary finding
"""

from __future__ import annotations

YES, BOUNDED, DISCLOSED, NO = "YES", "BOUNDED", "DISCLOSED", "NO"

EXACT = "EXACT"
CLAIM_TOO_BROAD = "CLAIM_TOO_BROAD"
CLAIM_TOO_NARROW = "CLAIM_TOO_NARROW"
VALIDITY_LIMIT_MISSING = "VALIDITY_LIMIT_MISSING"
ASSUMPTION_UNDISCLOSED = "ASSUMPTION_UNDISCLOSED"
APPROXIMATION_UNDISCLOSED = "APPROXIMATION_UNDISCLOSED"
REGIME_AMBIGUOUS = "REGIME_AMBIGUOUS"
UNKNOWN_SCIENTIFIC_INTENT = "UNKNOWN_SCIENTIFIC_INTENT"

CAPABILITY = {
    # =================================================================
    "thermal.lumped.first_order_capacity": {
        "equations": "C dT/dt = Q_in - hA (T - T_amb); T(t) = T_ss + (T_0 - T_ss) exp(-t hA/C), T_ss = T_amb + Q_in/hA",
        "regime": {
            "dependent_variables": ["T"],
            "independent_variables": ["t"],
            "steady_or_transient": "transient",
            "linearity": "linear ODE, constant coefficients",
            "spatial": "lumped (zero-dimensional); one uniform temperature",
            "coefficients": "C and hA frozen for the whole interval",
            "boundary_conditions": "one convective path to one prescribed ambient",
            "empirical_correlations": "Nu correlations enter only through the optional hA cross-check, each carrying its own Ra/Re/Pr range",
            "dimensionless_ranges": "Bi <= 0.1; Fo >= 0.2 (conservative screen); h_r/h <= 0.1",
        },
        "real_cases": [
            ["a small PCB component on a heatsink, forced air", YES, "thin, high conductance, Bi well below 0.1"],
            ["a thick steel billet quenched in water", BOUNDED, "Bi >> 0.1; biot_number refuses"],
            ["a body cooling mainly by radiation in vacuum", BOUNDED, "radiation_to_convection_ratio refuses above 0.1"],
            ["a component that reaches its melting point", BOUNDED, "melting_temperature_utilization refuses"],
            ["a horizon shorter than the internal diffusion time", BOUNDED, "internal_fourier_number is a conservative screen and returns UNKNOWN"],
            ["a body whose hA is read off a correlation outside its fitted range", BOUNDED, "convection_flow_range_utilization and convection_property_range_utilization refuse"],
            ["a temperature swing large enough to move C or hA", BOUNDED, "capacity_excursion_ratio and conductance_excursion_ratio bound the caller's own declared budget"],
            ["mass transport or a second exchange path", DISCLOSED, "excluded in the record; one exchange path only"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "Twelve conditions, ten of them UNKNOWN on a bare declaration. Fail-closed: the model cannot reach IN_DOMAIN without the caller stating the regime.",
    },
    # =================================================================
    "thermal.conduction1d.linear_diffusion": {
        "equations": "du/dt = alpha d2u/dx2 on (0,L), u(0,t)=u(L,t)=0, u(x,0)=sin(pi x/L); exact solution u = sin(pi x/L) exp(-alpha pi^2 t/L^2)",
        "regime": {
            "dependent_variables": ["u (normalized, dimensionless)"],
            "independent_variables": ["x", "t"],
            "steady_or_transient": "transient",
            "linearity": "linear, field-independent diffusivity",
            "spatial": "one dimension, finite slab",
            "boundary_conditions": "homogeneous Dirichlet, held exactly at zero",
            "initial_condition": "fixed by the benchmark: the first Laplacian eigenfunction",
            "solver": "backward Euler in time, second-order central differences in space; unconditionally stable, first-order accurate in dt",
        },
        "real_cases": [
            ["a slab relaxing from a single-mode profile", YES, "this is exactly the declared problem"],
            ["an arbitrary initial temperature profile", DISCLOSED, "'single-mode sinusoidal initial condition' is an assumption on the record; the IC is not a caller field"],
            ["internal heat generation", DISCLOSED, "'no source or sink term' is an assumption on the record"],
            ["temperature-dependent diffusivity", DISCLOSED, "'linear diffusion with a constant, field-independent diffusivity'"],
            ["a coarse mesh or long time step", BOUNDED, "the result attains only DIMENSIONALLY_VALID; discretization_convergence and analytic_reference_agreement are reported NOT_RUN and every uncertainty is UNKNOWN with the reason stated"],
            ["an explicit scheme past its stability limit", BOUNDED, "the explicit FTCS realization carries its own von Neumann fourier_number condition"],
            ["convection, radiation or phase change", DISCLOSED, "excluded in the assumptions"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "A coarse solve returns a badly inaccurate number, but the result contract refuses to dress it up: the strongest level attained is DIMENSIONALLY_VALID and the two checks that would establish accuracy are explicitly NOT_RUN.",
    },
    # =================================================================
    "battery.cell.rint_ocv": {
        "equations": "V = OCV(z) - I R_int, OCV(z) = V_empty + (V_full - V_empty) z, Q_gen = I^2 R_int",
        "regime": {
            "dependent_variables": ["V_terminal", "OCV", "Q_gen"],
            "independent_variables": ["z (state of charge)"],
            "steady_or_transient": "quasi-static: one algebraic evaluation per step",
            "linearity": "affine in z, linear in I",
            "coefficients": "one constant R_int for the whole run; OCV an affine chord unless a curve is declared",
            "equilibrium": "no diffusion or double-layer relaxation; no hysteresis",
            "chemistry": "chemistry-agnostic in form; the chord is a caller declaration, not a chemistry claim",
        },
        "real_cases": [
            ["a constant-OCV source with series resistance", YES, "the chord is exact when V_full = V_empty"],
            ["lead-acid over a mid-SOC window", YES, "OCV is close to affine there"],
            ["Li-ion NMC over a declared mid-SOC window", BOUNDED, "soc_window_margin makes the caller state where the chord holds, and names the knee and plateau it fails at"],
            ["LFP across its flat plateau", BOUNDED, "same window condition; a measured curve may be declared instead of the chord"],
            ["a cell near empty where charge-transfer resistance rises", BOUNDED, "soc_window_margin refuses outside the declared window"],
            ["a cell whose R_int moves with temperature", BOUNDED, "internal_resistance_drift_ratio refuses beyond the declared span"],
            ["a pulse load", BOUNDED, "pulse_c_rate_utilization and pulse_duration_utilization"],
            ["polarization dynamics within the step", BOUNDED, "polarization_unmodelled_fraction bounds the unmodelled fraction"],
            ["charging", DISCLOSED, "the record states in both assumptions and exclusions that charging is not modelled and that no condition here would catch it"],
            ["reversible entropic heat", DISCLOSED, "excluded, and the record says it is of the same order at low rate"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "The chord's weakness is not hidden: the condition that bounds it cites Plett on why OCV is tabulated rather than chorded.",
    },
    # =================================================================
    "battery.cell.coulomb_counting": {
        "equations": "z(t) = z_0 - I t / (eta Q_nom); exact integration of dz/dt = -I/(eta Q_nom) for constant I",
        "regime": {
            "dependent_variables": ["z"],
            "independent_variables": ["t"],
            "steady_or_transient": "transient, exact for a current constant over the interval",
            "linearity": "linear",
            "coefficients": "eta and Q_nom frozen",
            "feedback": "none; an error in z_0 persists undiminished",
        },
        "real_cases": [
            ["a constant-current discharge inside a declared window", YES, "the integral is exact"],
            ["a discharge that walks past empty", BOUNDED, "soc_window_margin refuses with a declared window, and is UNKNOWN without one"],
            ["a load that varies within the step", BOUNDED, "soc_step_resolution_ratio bounds how far one step may walk"],
            ["a cell far from the temperature Q_nom was rated at", BOUNDED, "capacity_temperature_drift_ratio, citing IEC 61960-3"],
            ["rate derating of the available capacity", DISCLOSED, "excluded here and offered as a separate model the caller may refuse"],
            ["self-discharge", DISCLOSED, "excluded beyond the declared coulombic efficiency"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "Verified: with no window declared the model returns UNKNOWN rather than IN_DOMAIN, and with one declared it refuses a trajectory that leaves it.",
    },
    # =================================================================
    "battery.cell.peukert_capacity_derating": {
        "equations": "Q_eff = Q_nom (I_ref / I)^(k-1), the rearrangement of Peukert's I^k t = constant",
        "regime": {
            "dependent_variables": ["Q_eff"],
            "independent_variables": ["I"],
            "linearity": "power law; a fit, not a derivation",
            "coefficients": "k constant over the declared current and temperature range only",
            "chemistry": "established for lead-acid; applicability to lithium-ion is contested in the cited source",
        },
        "real_cases": [
            ["lead-acid near the fitted current", YES, "the law's own domain"],
            ["a current decades away from the fit", BOUNDED, "peukert_extrapolation_ratio bounds |log10(I/I_ref)| against the declared fit width"],
            ["lithium-ion", DISCLOSED, "the record cites Doerffel & Sharkh on the contest and ships the model UNVALIDATED"],
            ["a current below I_ref, which would raise the capacity", BOUNDED, "peukert_capacity_ratio <= 1 refuses a derating that increases capacity"],
            ["a temperature away from the fit", BOUNDED, "peukert_temperature_drift_ratio"],
            ["a varying load", DISCLOSED, "excluded; the law is defined over a constant-current discharge"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "The most honest record in the repository about its own weakness: EMPIRICAL_CORRELATION, UNVALIDATED, and it cites the paper that disputes it.",
    },
    # =================================================================
    "battery.cell.constant_current_runtime": {
        "equations": "t = (z_0 - z_stop) eta Q_nom / I, z_stop the higher of the declared SOC cutoff and the SOC at the declared terminal-voltage cutoff",
        "regime": {
            "dependent_variables": ["t_run"],
            "independent_variables": ["z_0", "z_stop", "I"],
            "steady_or_transient": "an elapsed time to a first-crossing event",
            "linearity": "linear",
            "monotonicity": "a discharge at constant I walks z monotonically DOWN; a cutoff above z_0 is never reached",
        },
        "real_cases": [
            ["a discharge from a full cell to a declared cutoff", YES, "the intended case"],
            ["two cutoffs that disagree about which bites first", BOUNDED, "cutoff_consistency_margin compares the two"],
            ["a run beyond the declared SOC window", BOUNDED, "soc_window_margin"],
            ["a current above the continuous rating", BOUNDED, "continuous_c_rate_utilization"],
            ["a cutoff declared ABOVE the starting state of charge", NO,
             "t = (z_0 - z_stop) eta Q_nom / I is negative. No condition compares z_stop against z_0: cutoff_consistency_margin compares the two cutoffs with each other, not either with the start. The model reports IN_DOMAIN and the solver emits the negative time."],
            ["charging", DISCLOSED, "excluded, and the record says no condition here would catch it"],
        ],
        "classification": VALIDITY_LIMIT_MISSING,
        "finding": "CB-3",
        "resolution": (
            "FIXED. A cutoff_reachability_margin >= 0 condition now "
            "compares the binding cutoff against the starting state of "
            "charge, so the case reads BOUNDED rather than NO. Guarded by "
            "test_the_runtime_model_refuses_a_cutoff_above_where_the_"
            "discharge_starts."
        ),
        "note": "The solver comment states the intent explicitly: a negative runtime is 'reported rather than clipped: the runtime model's own conditions are where that is judged'. They do not judge it.",
    },
    # =================================================================
    "electrical.dc.kcl": {
        "equations": "sum of signed currents leaving a node = 0",
        "regime": {
            "steady_or_transient": "steady-state DC",
            "linearity": "exact conservation law, no approximation",
            "spatial": "lumped; no charge accumulation at nodes",
            "dimensionless_ranges": "L/lambda <= 0.1, satisfied by this model's own scope because a DC model has f = 0",
        },
        "real_cases": [
            ["any lumped DC network", YES, "charge conservation is exact here"],
            ["a circuit at non-zero frequency comparable with its size", BOUNDED, "lumped_electrical_length is stated and would bite; at DC it is identically zero"],
            ["transmission-line and field effects", DISCLOSED, "excluded"],
        ],
        "classification": EXACT,
        "finding": None,
    },
    # =================================================================
    "electrical.dc.resistor_ohm": {
        "equations": "V = I R; P = V I = I^2 R >= 0",
        "regime": {
            "steady_or_transient": "steady-state DC",
            "linearity": "linear, time-invariant",
            "coefficients": "R constant and temperature-independent",
        },
        "real_cases": [
            ["a metal-film resistor inside its ratings", YES, "the intended case"],
            ["zero or negative resistance", BOUNDED, "refused at construction: a short is an ideal 0 V source and a negative resistance is an active device"],
            ["dissipation above the element's rating", BOUNDED, "dissipated_power_utilization, with a derating line per IEC 60115-1 when declared"],
            ["voltage above the element's working-voltage rating", BOUNDED, "working_voltage_utilization"],
            ["a resistance that moves as the element heats", DISCLOSED, "'temperature-independent resistance' is an assumption and an exclusion; electrical.dc.self_heated_resistor is where that assumption is checked"],
        ],
        "classification": EXACT,
        "finding": None,
    },
    # =================================================================
    "electrical.dc.self_heated_resistor": {
        "equations": "V = I R, with (T_body + |P| R_th,element-to-body) / T_permissible <= 1",
        "regime": {
            "steady_or_transient": "steady-state DC with an imposed body temperature",
            "spatial": "element uniform apart from the single element-to-body drop this record computes",
            "coefficients": "one resistance describes the element over the whole run",
        },
        "real_cases": [
            ["an element whose hot spot stays below its permissible temperature", YES, "the intended case"],
            ["an element driven past its own temperature limit", BOUNDED, "element_hot_spot_utilization refuses"],
            ["an element whose resistance changes as it heats", DISCLOSED, "excluded explicitly: 'any change of resistance over the run; one resistance describes the element throughout'"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "The constant-resistance approximation is disclosed rather than bounded. Bounding it would require a TCR declaration this record does not take, which is a different model (electrical.material) rather than a missing condition here.",
    },
    # =================================================================
    "electrical.dc.ideal_voltage_source": {
        "equations": "V(+) - V(-) = source_voltage, irrespective of current",
        "regime": {
            "steady_or_transient": "steady-state DC",
            "ideality": "zero internal impedance, unlimited current compliance",
        },
        "real_cases": [
            ["a stiff supply well inside its current rating", YES, "the idealisation holds"],
            ["a supply driven past its current rating", BOUNDED, "source_current_utilization refuses when a maximum_current is declared"],
            ["a supply with a real output impedance", DISCLOSED, "excluded here; electrical.dc.regulated_voltage_source is the companion record for it"],
        ],
        "classification": EXACT,
        "finding": None,
    },
    # =================================================================
    "electrical.dc.ideal_current_source": {
        "equations": "I from_node -> to_node fixed, irrespective of terminal voltage",
        "regime": {
            "steady_or_transient": "steady-state DC",
            "ideality": "infinite output impedance, unlimited compliance voltage",
        },
        "real_cases": [
            ["a current source well inside its compliance", YES, "the idealisation holds"],
            ["a load that drives the source past its compliance voltage", BOUNDED, "compliance_voltage_utilization refuses when a compliance_voltage is declared"],
            ["finite output impedance", DISCLOSED, "excluded"],
        ],
        "classification": EXACT,
        "finding": None,
    },
    # =================================================================
    "electrical.dc.regulated_voltage_source": {
        "equations": "V(+) - V(-) = source_voltage, asserted where (|I| R_out / |V_src|) / regulation_band <= 1",
        "regime": {
            "steady_or_transient": "steady-state DC",
            "ideality": "Thevenin equivalent: one constant open-circuit voltage, one constant output resistance",
        },
        "real_cases": [
            ["a regulated supply inside its published regulation band", YES, "the intended case"],
            ["a supply loaded past its regulation band", BOUNDED, "source_regulation_utilization refuses"],
            ["a supply with internal dynamics or foldback", DISCLOSED, "excluded; the source is a static Thevenin equivalent"],
        ],
        "classification": EXACT,
        "finding": None,
    },
    # =================================================================
    "electrical.material.linear_tcr_resistance": {
        "equations": "R(T) = R_ref (1 + alpha (T - T_ref))",
        "regime": {
            "dependent_variables": ["R"],
            "independent_variables": ["T"],
            "steady_or_transient": "a single algebraic evaluation at a supplied temperature",
            "linearity": "first-order Taylor expansion of rho(T) about T_ref",
            "coefficients": "one alpha for the whole declared range",
            "material": "isotropic scalar; no strain, ageing, frequency or field dependence",
            "dimensionless_ranges": "none declared; the sibling record declares three",
        },
        "real_cases": [
            ["a copper or platinum conductor near its reference temperature", YES, "the linear tangent is accurate there"],
            ["a thermistor of either sign", DISCLOSED, "excluded explicitly; an NTC is exponential in 1/T and a PTC switches over a few kelvin"],
            ["a semiconductor or alloy read off a local tangent (negative alpha)", NO,
             "the input record explicitly admits this case and justifies it by 'the band is how far that tangent is claimed to carry' -- but this record declares no band. Any (alpha, T_ref) whose line crosses zero inside 200-450 K yields R <= 0 with every condition SATISFIED."],
            ["a conductor evaluated far from its reference temperature", DISCLOSED, "the 200-450 K condition is a fixed window; the material-specific band is the rated sibling's claim, and requiring it here would need a declaration this record does not take"],
            ["a conductor above its maximum operating temperature", DISCLOSED, "the rated sibling's claim; needs a material declaration"],
            ["a conductor below the Bloch-Grueneisen linear floor", DISCLOSED, "the rated sibling's claim; needs a Debye temperature"],
            ["self-heating", DISCLOSED, "excluded; T is supplied and never inferred"],
        ],
        "classification": VALIDITY_LIMIT_MISSING,
        "finding": "CB-1",
        "resolution": (
            "FIXED. A linear_resistance_ratio > 0 condition now refuses a "
            "line that has crossed zero, so the case reads BOUNDED rather "
            "than NO. Guarded by "
            "test_the_linear_tcr_model_refuses_a_line_that_has_crossed_zero."
        ),
        "note": "Of the four conditions the rated sibling adds, three need a material declaration this record does not take and their absence is justified. linear_resistance_ratio needs nothing but the three inputs this record already requires.",
    },
    # =================================================================
    "electrical.material.rated_linear_tcr_resistance": {
        "equations": "the same R(T) = R_ref (1 + alpha (T - T_ref)), claimed only inside the material's own declared limits",
        "regime": {
            "linearity": "first-order Taylor, with the excursion bounded by the material's declared band",
            "dimensionless_ranges": "|T - T_ref|/band <= 1; T/T_max <= 1; T/theta_D >= 1/3 (Bloch-Grueneisen linear regime); 1 + alpha (T - T_ref) > 0",
        },
        "real_cases": [
            ["a conductor with a full material datasheet", YES, "the intended case"],
            ["a conductor read outside its linearization band", BOUNDED, "linearization_excursion_ratio, evaluated at the furthest state the run occupies"],
            ["a conductor above its maximum operating temperature", BOUNDED, "operating_temperature_utilization"],
            ["a conductor below the linear-resistivity regime", BOUNDED, "reduced_debye_temperature floors T/theta_D at 1/3"],
            ["a line that crosses zero", BOUNDED, "linear_resistance_ratio > 0"],
            ["a material that declares no limits", BOUNDED, "each condition is UNKNOWN unless its limit is declared; the claim is not awarded by default"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "This record is the source of truth for CB-1: it declares the positivity bound and calls it 'the physics of the quantity, not a tolerance'.",
    },
    # =================================================================
    "kinetics.cstr.nonisothermal_first_order": {
        "equations": "dC_A/dt = (C_Af - C_A)/tau - k(T) C_A ; dT/dt = (T_f - T)/tau + beta k(T) C_A - gamma (T - T_c) ; k(T) = k0 exp(-E/RT)",
        "regime": {
            "dependent_variables": ["C_A", "T"],
            "independent_variables": ["t"],
            "steady_or_transient": "transient, and stiff near ignition",
            "linearity": "nonlinear: Arrhenius coupling between the two balances",
            "spatial": "perfectly mixed, zero-dimensional",
            "phases": "single liquid phase, no boiling, no vapour space",
            "coefficients": "constant density, heat capacity, heat of reaction, UA; jacket at a prescribed constant temperature",
            "invariants": "Z = T + beta C_A obeys dZ/dt = (Z_f - Z)/tau - gamma (T - T_c), so T <= max(T_0,T_f,T_c) + beta max(C_A0,C_Af) with or without cooling",
        },
        "real_cases": [
            ["a cooled exothermic liquid-phase reactor inside its envelope", YES, "the intended case"],
            ["a declaration whose adiabatic ceiling leaves the single-phase envelope", BOUNDED, "adiabatic_ceiling_temperature refuses on the exact invariant, before any solve"],
            ["ignition and multiple steady states", YES, "the equations carry this; it is why the model exists"],
            ["a solvent that would boil well below 1000 K", DISCLOSED, "assumptions and exclusions both name boiling and a vapour space; no boiling point is declarable, so the envelope is a fixed conservative band rather than a solvent-specific one"],
            ["reverse or side reactions", DISCLOSED, "excluded"],
            ["jacket dynamics", DISCLOSED, "excluded; prescribed constant jacket temperature and constant UA"],
        ],
        "classification": EXACT,
        "finding": None,
        "note": "The adiabatic ceiling is an exact upper bound, not an estimate, and is decidable from the declaration alone.",
    },
    # =================================================================
    "kinetics.cstr.nonisothermal_first_order_constant_rate": {
        "equations": "the same two balances with k held constant: dC_A/dt = (C_Af - C_A)/tau - k_const C_A ; dT/dt = (T_f - T)/tau + beta k_const C_A - gamma (T - T_c)",
        "regime": {
            "dependent_variables": ["C_A", "T"],
            "steady_or_transient": "transient",
            "linearity": "linear in (C_A, T): the Arrhenius coupling is removed",
            "spatial": "perfectly mixed, zero-dimensional",
            "phases": "single liquid phase, no boiling -- the record claims the SAME envelope as the primary model",
            "invariants": "the SAME Z = T + beta C_A invariant: the reaction rate cancels exactly out of dZ/dt, so the bound is independent of the rate law",
        },
        "real_cases": [
            ["a controlled comparison against the Arrhenius model", YES, "what the model exists for"],
            ["a reactor whose temperature swing is small enough that k barely moves", YES, "the approximation is defensible there and is disclosed as an approximation"],
            ["a declaration whose adiabatic ceiling leaves the single-phase envelope", NO,
             "the record claims the 'Same single-phase CSTR envelope as the primary model' and states a 250-1000 K temperature condition, but does not reserve or state a condition over adiabatic_ceiling_temperature. The quantity is computed and present in the very context this model is assessed against; the model simply does not look at it, and reports IN_DOMAIN."],
            ["a real system with Arrhenius dependence", DISCLOSED, "the record says plainly that this is a comparison approximation, not a claim that the dependence is absent"],
        ],
        "classification": VALIDITY_LIMIT_MISSING,
        "finding": "CB-2",
        "resolution": (
            "FIXED. An adiabatic_ceiling_temperature <= 1000 K condition "
            "now bounds the constant-rate record on the same invariant as "
            "its sibling, so the case reads BOUNDED rather than NO. "
            "Guarded by test_both_cstr_models_refuse_a_declaration_whose_"
            "ceiling_leaves_the_envelope."
        ),
        "note": "The invariant derivation is rate-law-independent: adding beta times the species balance to the energy balance cancels the reaction term whatever k is. The primary model's own record states the derivation.",
    },
}
