"""EV-1: the validation surface. Every shipped model, and what can be done to it.

Two columns matter and are kept apart.

``independent_construction`` says whether the model can be reached from a raw
fixture that names no engcore type. Every model can, so this column is YES
throughout -- but it is stated per model rather than asserted once, because a
model that could only be reached through an engcore object would be a model
this round could say nothing about.

``empirical_evidence_possible`` says whether external physical or reference
evidence exists FOR THIS MODEL IN THIS ENVIRONMENT. It is NO far more often
than it is YES, and that is the honest answer rather than a gap to be filled.
Writing YES because a comparison exists against mathematics written in this
round would be exactly the confusion the round was set up to avoid.

The environment has no measured dataset and no retrievable benchmark dataset.
So:

  YES     ngspice, CODATA or IEC 60751 bears on the model directly
  PARTIAL the model's law is externally attested but no external number
          constrains it at the operating point used here
  NO      no external evidence exists in this environment
"""

from __future__ import annotations

SURFACE = [
    {
        "model_id": "thermal.lumped.first_order_capacity",
        "domain": "thermal",
        "independent_fixture": "fixtures/lumped_body.json",
        "fixture_representation": (
            "a mass in grams, a specific heat per gram, a surface area in cm2, "
            "a film coefficient, two temperatures in degC, a heater in mW and "
            "a duration in minutes. The heat capacity and the ambient "
            "conductance are derived twice, once per branch."
        ),
        "available_oracle": (
            "the closed form derived from the energy balance, an independent "
            "RK4 march of the same balance, and the first law over the interval"
        ),
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "No measured cooling curve is available here and the repository "
            "curates none. The comparison is mathematics against mathematics "
            "and is reported as LEVEL 5."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "thermal.conduction1d.linear_diffusion",
        "domain": "thermal",
        "independent_fixture": "fixtures/slab.json",
        "fixture_representation": (
            "a thickness in mm, a conductivity, a density in g/cm3 and a "
            "specific heat per gram. The diffusivity is derived twice."
        ),
        "available_oracle": (
            "the separated-variables solution, exact for the single-mode "
            "initial condition, plus an explicit FTCS march at r = 1/4 whose "
            "own error is separately predicted and checked"
        ),
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "No measured transient temperature field is available. What IS "
            "available is stronger than a loose empirical bound for the "
            "question being asked: the scheme's error has a derived functional "
            "form in dt and dx, and that form is swept."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "battery.cell.coulomb_counting",
        "domain": "battery",
        "independent_fixture": "fixtures/battery_cell.json",
        "fixture_representation": "capacity in mAh, current in mA, duration in minutes",
        "available_oracle": "z0 - I t/(eta Q) and the charge balance over the interval",
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "No measured discharge dataset is retrievable in this environment. "
            "A rich cell dataset would in any case be OUT_OF_SCOPE_FOR_MODEL "
            "for a constant-resistance affine-OCV cell, and forcing one into a "
            "fit would be calibration reported as validation."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "battery.cell.rint_ocv",
        "domain": "battery",
        "independent_fixture": "fixtures/battery_cell.json",
        "fixture_representation": "open-circuit voltages in mV, resistance in mOhm",
        "available_oracle": "OCV(z) = V_e + (V_f - V_e) z, V = OCV - I R, Q = I^2 R",
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "The affine OCV curve is the Core's declared model, not a claim "
            "about any real cell, so a measured OCV curve would falsify the "
            "cell rather than the implementation. Saying otherwise would be "
            "testing a claim the record does not make."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "battery.cell.constant_current_runtime",
        "domain": "battery",
        "independent_fixture": "fixtures/battery_cell.json",
        "fixture_representation": "a cutoff voltage in mV against the same cell",
        "available_oracle": (
            "z_cut = (V_cut + I R - V_e)/(V_f - V_e) and t = (z0 - z_stop) eta Q / I"
        ),
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": "As above; no measured runtime is available.",
        "status": "UNREVIEWED",
    },
    {
        "model_id": "battery.cell.peukert_capacity_derating",
        "domain": "battery",
        "independent_fixture": "fixtures/battery_cell.json",
        "fixture_representation": "an exponent and a reference current in mA",
        "available_oracle": (
            "Q_eff = Q_nom (I_ref/I)^(k-1), checked additionally against the "
            "law as Peukert stated it, I^k t constant"
        ),
        "external_dataset": None,
        "empirical_evidence_possible": "PARTIAL",
        "why": (
            "The law is externally attested -- Peukert 1897, and the repository "
            "cites Doerffel and Sharkh 2006 on its limits -- but no external "
            "number constrains the exponent of this fixture's cell. The "
            "invariant check is a real second statement of the law and not a "
            "rearrangement of the first, which is why this is PARTIAL rather "
            "than NO; it is not YES, because no measurement is involved."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.dc.kcl",
        "domain": "electrical",
        "independent_fixture": "fixtures/circuits.json",
        "fixture_representation": (
            "a component list in kohm, mV and mA with an explicitly named "
            "reference node"
        ),
        "available_oracle": (
            "modified nodal analysis assembled here and solved by a "
            "hand-written Gaussian elimination, plus ngspice 42 on a netlist "
            "emitted from the same fixture"
        ),
        "external_dataset": "ngspice 42",
        "empirical_evidence_possible": "YES",
        "why": (
            "ngspice is an independently written simulator, three decades old, "
            "run as a separate process on a problem statement it was given "
            "directly rather than through the Core. It is the only genuinely "
            "external solver available in this environment."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.dc.resistor_ohm",
        "domain": "electrical",
        "independent_fixture": "fixtures/circuits.json",
        "fixture_representation": "resistances in kohm",
        "available_oracle": "V = I R recomputed from the independent node solve; ngspice",
        "external_dataset": "ngspice 42",
        "empirical_evidence_possible": "YES",
        "why": "As above.",
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.dc.ideal_voltage_source",
        "domain": "electrical",
        "independent_fixture": "fixtures/circuits.json",
        "fixture_representation": (
            "source voltages in mV, including one source with neither leg on "
            "the reference node"
        ),
        "available_oracle": (
            "the extra MNA unknown in the hand solve, and ngspice's own branch "
            "current"
        ),
        "external_dataset": "ngspice 42",
        "empirical_evidence_possible": "YES",
        "why": "As above.",
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.dc.ideal_current_source",
        "domain": "electrical",
        "independent_fixture": "fixtures/circuits.json",
        "fixture_representation": "source currents in mA with a stated from/to direction",
        "available_oracle": "the hand solve's right-hand side; ngspice",
        "external_dataset": "ngspice 42",
        "empirical_evidence_possible": "YES",
        "why": "As above.",
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.dc.regulated_voltage_source",
        "domain": "electrical",
        "independent_fixture": "fixtures/circuits.json",
        "fixture_representation": (
            "an output resistance in mOhm and a regulation band, declared "
            "against one of the supplies"
        ),
        "available_oracle": "(|I| R_out/|V|)/band, recomputed independently",
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "The band is the caller's own declaration of how much droop a "
            "design tolerates. There is no external number for it, and the "
            "repository says so in the record itself. What CAN be validated "
            "independently is the utilization arithmetic and the unit chain, "
            "and that is what is done."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.dc.self_heated_resistor",
        "domain": "electrical",
        "independent_fixture": "fixtures/circuits.json",
        "fixture_representation": (
            "an element-to-body thermal resistance in K/W, a permissible "
            "element temperature in degC and a body temperature in degC"
        ),
        "available_oracle": "(T_body + |P| R_th)/T_permissible, recomputed independently",
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "A part's element-to-body thermal resistance is a datasheet figure "
            "for a specific part, and no such datasheet is retrievable here. "
            "The degC-to-kelvin chain and the arithmetic are validated; the "
            "thermal resistance itself is a declaration, not a claim."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.material.linear_tcr_resistance",
        "domain": "electrical",
        "independent_fixture": "fixtures/conductor.json, fixtures/platinum_iec60751.json",
        "fixture_representation": (
            "a resistivity in nOhm.m, a length in mm and a cross-section in "
            "mm2, with a coefficient in ppm/K; separately, the IEC 60751 "
            "coefficients for platinum"
        ),
        "available_oracle": (
            "R_ref = rho L / A recomputed independently, and the IEC 60751 "
            "Callendar-Van Dusen quadratic that the linear law truncates"
        ),
        "external_dataset": "IEC 60751 platinum coefficients",
        "empirical_evidence_possible": "YES",
        "why": (
            "A published international standard states R(t) for industrial "
            "platinum thermometers. The linear model is its first-order "
            "truncation, so what the standard can validate is the SIZE OF THE "
            "OMITTED TERM -- which is a real external constraint, and one the "
            "model would fail if its coefficient, its sign or its reference "
            "temperature were wrong. Requiring the linear model to reproduce "
            "the quadratic would be testing a claim it does not make."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "electrical.material.rated_linear_tcr_resistance",
        "domain": "electrical",
        "independent_fixture": "fixtures/conductor.json",
        "fixture_representation": (
            "the same conductor with a linearization band in K and a maximum "
            "operating temperature in degC declared"
        ),
        "available_oracle": "the same independent R_ref(1 + alpha dT)",
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "The rated record is the same constitutive law with the material's "
            "own limits attached. Declaring the limits is what makes it this "
            "model; the limits are declarations about a material and no "
            "external number for this fixture's wire exists here."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "kinetics.cstr.nonisothermal_first_order",
        "domain": "kinetics",
        "independent_fixture": "fixtures/reactor.json",
        "fixture_representation": (
            "a volume in L, a flow in L/min, a feed concentration in mol/L, "
            "temperatures in degC, a UA in kJ/min/K, a pre-exponential in "
            "1/min and energies in kJ/mol. The dilution rate, beta and gamma "
            "are derived twice."
        ),
        "available_oracle": (
            "a fixed-step RK4 of both balances with a refinement ladder, a "
            "bisection for the steady states, and the exact invariant "
            "Z = T + beta C_A whose reaction term cancels identically"
        ),
        "external_dataset": "CODATA 2022 molar gas constant",
        "empirical_evidence_possible": "PARTIAL",
        "why": (
            "One constant in this model is externally fixed and is checked "
            "against a hashed copy of the CODATA table. The kinetics are not: "
            "no measured concentration or temperature trajectory for this "
            "chemistry is available here, and inventing one to fill the column "
            "would be fabricating evidence."
        ),
        "status": "UNREVIEWED",
    },
    {
        "model_id": "kinetics.cstr.nonisothermal_first_order_constant_rate",
        "domain": "kinetics",
        "independent_fixture": "fixtures/reactor.json (constant_rate_variant)",
        "fixture_representation": (
            "the same plant with a temperature-independent rate constant in "
            "1/min and a zero activation energy"
        ),
        "available_oracle": (
            "the same RK4, with the rate constant taken as constant rather "
            "than evaluated as exp(-0/(RT)) -- the alternative model family "
            "forms no exponential at all, and the oracle does not either"
        ),
        "external_dataset": None,
        "empirical_evidence_possible": "NO",
        "why": (
            "This model is declared in the repository as a deliberate "
            "comparison approximation for model competition, not as a claim "
            "about a physical system. There is nothing external for it to be "
            "right or wrong about."
        ),
        "status": "UNREVIEWED",
    },
]

MODEL_IDS = [entry["model_id"] for entry in SURFACE]
