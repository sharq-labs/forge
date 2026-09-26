"""FLAGSHIP D - a jacketed methane/air reactor: Cantera chemistry -> heat duty -> TESPy cooling loop, with conservation and reference checks.

Engineering question
    A stoichiometric methane/air stream is burned and its exhaust is cooled by a water jacket.  What are the flame temperature and the
    exhaust composition, how much heat must the loop remove, what does the water do, and do the chemistry and the thermal-fluid
    provider agree on the energy balance?

System (one BIG 12 request)
    adiabatic_equilibrium    Cantera HP equilibrium from the reactants (GRI-Mech 3.0 bytes bound by digest)
    cooled_equilibrium       Cantera TP equilibrium at the exhaust outlet temperature (composition shifts as it cools)
    heat_duty                Q = m_mix (h_reactants - h_cooled)  - Cantera enthalpies, no invented model
    coolant_loop             TESPy water stream with the duty Q as its heat input (declared: every watt removed enters the water)
    energy_balance           Q from Cantera vs m_w dh from TESPy
    kinetic_reactor (x3)     Cantera adiabatic constant-pressure reactor from 1400 K at three integrator tolerances
    equilibrium limit        the same initial state at HP equilibrium; the kinetic end state must approach it
    heat_of_combustion       CH4 + 2 O2 at 298.15 K, complete combustion: lower heating value vs Hess's law with NIST WebBook data

The interface between the providers is an ENERGY BALANCE, not a new physical model: the water loop does not know the gas, it is handed the
heat the chemistry says must be removed.  Inputs (inlet states, flows, exhaust outlet temperature) are declared illustrative values.
Nothing here is validation of the mechanism: GRI-Mech 3.0 was optimised against experiments by its authors, and that is the authors'
claim, not a Forge result.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from engcore.engineering import (
    EnvelopeBound, EvidenceLink, LevelEntry, LevelStatus, PredeclaredCriterion, ReferenceCondition, ReferenceRecord, UncertaintyStatement, VerificationLadder,
    build_summary, compare_to_reference, contract_integrity_entry,
)
from engcore.execution.multiphysics import InitialStateValue
from engcore.materials import FluidIdentity
from engcore.scenarios import ScenarioSegment, ScenarioSpecification, TimeBasis, TimePoint, TimeWindow, Timeline
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.oracles import OracleKind
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.twins import ScientificTwin, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport, AuthorityRegistry, CallbackAuthority, ConstraintObservation, ExecutionProfile, InitialStateSpec, LiteralInput, ModelSelection, NodeInput,
    NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, OutputValue, OwnerState, ProviderBinding, ProviderRecordRef, RequestedObservable, RuntimeContext, SystemRunRequest,
)
from engcore.system_runtime._common import digest_of
from engcore.systems import ComponentDefinition, ComponentInstance, ConstraintBinding, SystemDefinition

UNKNOWN = Uncertainty.unknown("declared or derived quantity; no uncertainty was quantified")
P_ATM = 101325.0
T_REACTANTS = 300.0
T_EXHAUST_OUT = 400.0
M_MIX = 0.01                       # kg/s reactant mass flow (declared)
M_WATER = 0.3                      # kg/s cooling water (declared)
T_WATER_IN = 293.15
P_WATER = 2e5
T_KINETIC_START = 1400.0
STOICH = {"CH4": 1 / 10.52, "O2": 2 / 10.52, "N2": 7.52 / 10.52}
LHV_MIXTURE = {"CH4": 1 / 3, "O2": 2 / 3}
TFLAME_MAX = 2300.0                # K, constraint (illustrative material limit)
TWATER_MAX = 353.15                # K, constraint (illustrative)
# ---- criteria fixed BEFORE any run -------------------------------------------------------------------------------------------------
ELEMENT_TOL = 1e-9                 # relative change of any elemental mass fraction through an equilibration
ENERGY_BALANCE_REL_TOL = 1e-6      # |Q_gas - m_w dh_water| / Q_gas
LHV_TOL_KJ_PER_MOL = 0.5           # |LHV(Cantera, GRI-Mech 3.0 thermo) - Hess's law with NIST-JANAF data|
EQUILIBRIUM_APPROACH_REL = 0.01    # |T(50 ms) - T_HP_equilibrium| / T_eq for the kinetic reactor
INTEGRATOR_IGNITION_REL = 0.01     # ignition delay change between the two finest integrator settings
INTEGRATOR_T_ABS_K = 0.1           # final temperature change between the two finest integrator settings
WATER_RANGE_K = (274.0, 380.0)     # DECLARED liquid-water range of the loop (applicability)
KINETIC_SETTINGS = ((1e-6, 1e-12, 201), (1e-9, 1e-15, 501), (1e-11, 1e-17, 1001))     # (rtol, atol, samples)
KINETIC_END_S = 0.05


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_hess() -> tuple[ReferenceRecord, dict]:
    raw = open(os.path.join(os.path.dirname(__file__), "data", "nist_webbook_thermochemistry_excerpt.json"), "rb").read()
    d = json.loads(raw.decode())
    heats = d["derived_heat_of_combustion_kJ_per_mol"]
    src = sha("".join(d["source_page_digests"][k] for k in sorted(d["source_page_digests"])))
    ref = ReferenceRecord(
        d["reference_id"], d["title"], d["authors"], "NIST SRD 69 retrieved " + d["retrieved"], d["access_urls"][0], d["license_status"], OracleKind.ANALYTIC_REFERENCE,
        (ReferenceCondition("temperature", 298.15, "K"), ReferenceCondition("pressure", 101325.0, "Pa")), (("lower_heating_value", "kJ/mol"),),
        (("lower_heating_value", (-heats["chase1998"], -heats["codata_with_manion"])),), src,
        "Hess's law from WebBook gas-phase formation enthalpies (Chase 1998: CH4 -74.87, CO2 -393.52, H2O -241.83 kJ/mol; CODATA CO2/H2O with Manion 2002 CH4 -74.6): "
        f"{heats}; page sha256 {list(d['source_page_digests'].values())[0][:12]}.. and 2 more; excerpt file sha256 {hashlib.sha256(raw).hexdigest()[:16]}... "
        "The applicability envelope (290-300 K, 0.9-1.1 bar) is AUTHORED by this flagship around the table's 298.15 K / 1 atm standard state, not stated by NIST; "
        "the comparison is evaluated at 300 K, the inclusive upper edge of that envelope",
        (EnvelopeBound("temperature", 290.0, 300.0, "K"), EnvelopeBound("pressure", 9e4, 1.1e5, "Pa")), role="data_consistency",
        comparable_quantities=("lower_heating_value",))
    return ref, d


def system_definition():
    twin = lambda n: ScientificTwin(n, "1", TwinKind.CONCEPT).reference  # noqa: E731
    tf = ConstraintDefinition("max_flame_temperature", "adiabatic_flame_temperature", ConstraintOperator.LESS_EQUAL, Quantity(TFLAME_MAX, "K"))
    tw = ConstraintDefinition("max_water_outlet", "water_outlet_temperature", ConstraintOperator.LESS_EQUAL, Quantity(TWATER_MAX, "K"))
    from engcore.scientific.multiphysics import PortDefinition, PortDirection, PortKind
    from engcore.systems import ComponentConnection
    out_port = PortDefinition("heat", PortDirection.OUTPUT, PortKind.SCALAR, "heat_rate", "W")
    in_port = PortDefinition("heat", PortDirection.INPUT, PortKind.SCALAR, "heat_rate", "W")
    system = SystemDefinition("jacketed-reactor", "1",
                              (ComponentDefinition("assembly", "1"), ComponentDefinition("reactor", "1", (out_port,)), ComponentDefinition("jacket", "1", (in_port,))),
                              (ComponentInstance("plant", "assembly", "1", twin("plant")), ComponentInstance("reactor", "reactor", "1", twin("reactor"), parent_id="plant", participant_id="reactor"),
                               ComponentInstance("jacket", "jacket", "1", twin("jacket"), parent_id="plant", participant_id="jacket")),
                              (ComponentConnection("duty", "reactor-to-jacket heat duty (an energy balance, declared)", "reactor", "heat", "jacket", "heat"),),
                              constraint_bindings=(ConstraintBinding("b_tflame", "reactor", "max_flame_temperature"), ConstraintBinding("b_twater", "jacket", "max_water_outlet")),
                              constraints=(tf, tw))
    return system, {"max_flame_temperature": tf, "max_water_outlet": tw}


class Exchange:
    def __init__(self) -> None:
        self.records: dict[str, Any] = {}
        self.series: dict[str, Any] = {}
        self.files: dict[str, bytes] = {}


@dataclass
class Chemistry:
    request: SystemRunRequest
    context: RuntimeContext
    exchange: Exchange
    constraints: dict
    registry: Any
    variant: str


SPECIES = ("CH4", "O2", "CO2", "H2O", "CO", "NO", "OH")


def build_chemistry(registry=None, *, variant: str = "nominal") -> Chemistry:
    """``variant``: nominal | missing_species (a species the mechanism does not define) | below_thermo_range (exhaust outlet colder than the thermo data)."""
    from engcore.providers import default_registry
    from forge_cantera import CanteraProvider, Mechanism
    from forge_tespy import ChainProblem, HeatExchangerSpec, TESPyProvider

    registry = registry or default_registry()
    st = {p: registry.status(p) for p in ("cantera", "tespy")}
    ct_s, ts_s = st["cantera"], st["tespy"]
    ex = Exchange()
    gri = Mechanism.from_cantera_data("gri30.yaml")
    cant = CanteraProvider(registry)
    tespy = TESPyProvider(registry)
    system, defs = system_definition()
    comp = dict(STOICH)
    if variant == "missing_species":
        comp = {"CH4": 0.05, "XY9": 0.05, "O2": 0.2, "N2": 0.7}
    t_out = 100.0 if variant == "below_thermo_range" else T_EXHAUST_OUT
    ct_ref = lambda rec: ProviderRecordRef.of_record(rec)  # noqa: E731

    def q(rec, name):
        return rec.scalars[name]

    def element_residual(rec):
        return max(abs(rec.scalars[f"elem_Y_{e}"].magnitude - rec.scalars[f"elem_Y0_{e}"].magnitude) / max(rec.scalars[f"elem_Y0_{e}"].magnitude, 1e-30)
                   for e in ("C", "H", "O", "N") if rec.scalars[f"elem_Y0_{e}"].magnitude > 0)

    def eq_outcome(call, rec, extra: dict[str, Quantity]):
        ex.records[call.execution_identity] = rec
        if not rec.succeeded:
            return NodeOutcome.failed(rec.reason, provider_records=(ct_ref(rec),))
        outs = {k: OutputValue(v, UNKNOWN, f"cantera {ct_s.version} equilibrium") for k, v in extra.items()}
        return outs

    species = SPECIES

    def adiabatic(call):
        rec = cant.equilibrium(gri, comp, call.value("T0"), call.value("p"), constraint="HP", species=species)
        if not rec.succeeded:
            return NodeOutcome.failed(rec.reason, provider_records=(ct_ref(rec),))
        ex.records[call.execution_identity] = rec
        outs = {"T_adiabatic": q(rec, "temperature"), "h_reactants": q(rec, "h_mass_initial"), "X_CO2": q(rec, "X_CO2"), "X_H2O": q(rec, "X_H2O"), "X_CO": q(rec, "X_CO"),
                "X_NO": q(rec, "X_NO"), "X_OH": q(rec, "X_OH"), "element_residual": Quantity(element_residual(rec), "dimensionless")}
        lo, hi = q(rec, "thermo_T_min").magnitude, q(rec, "thermo_T_max").magnitude
        T = q(rec, "temperature").magnitude
        rep = ApplicabilityReport("thermo_range", "within" if lo <= T <= hi else "outside", digest_of({"T": T, "range": [lo, hi]}),
                                  f"equilibrium temperature {T:.1f} K against the species thermodynamic data range [{lo:g}, {hi:g}] K stored in the mechanism bytes")
        return NodeOutcome("succeeded", {k: OutputValue(v, UNKNOWN, f"cantera {ct_s.version} HP equilibrium") for k, v in outs.items()}, provider_records=(ct_ref(rec),),
                           applicability=(rep,), delegated_record_digest=rec.digest)

    def cooled(call):
        rec = cant.equilibrium(gri, comp, call.value("T_out"), call.value("p"), constraint="TP", species=species)
        if not rec.succeeded:
            return NodeOutcome.failed(rec.reason, provider_records=(ct_ref(rec),))
        ex.records[call.execution_identity] = rec
        outs = {"h_cooled": q(rec, "h_mass"), "X_CO2_out": q(rec, "X_CO2"), "X_H2O_out": q(rec, "X_H2O"), "X_CO_out": q(rec, "X_CO"),
                "element_residual": Quantity(element_residual(rec), "dimensionless")}
        lo, hi = q(rec, "thermo_T_min").magnitude, q(rec, "thermo_T_max").magnitude
        T = call.value("T_out").magnitude_in("K")
        rep = ApplicabilityReport("thermo_range", "within" if lo <= T <= hi else "outside", digest_of({"T": T, "range": [lo, hi]}),
                                  f"exhaust outlet temperature {T:.1f} K against the species thermodynamic data range [{lo:g}, {hi:g}] K")
        return NodeOutcome("succeeded", {k: OutputValue(v, UNKNOWN, f"cantera {ct_s.version} TP equilibrium") for k, v in outs.items()}, provider_records=(ct_ref(rec),),
                           applicability=(rep,), delegated_record_digest=rec.digest)

    def duty(call):
        qs = call.value("h_reactants").magnitude_in("J/kg") - call.value("h_cooled").magnitude_in("J/kg")
        if qs <= 0:
            return NodeOutcome.failed("the exhaust does not release heat between the two states: a non-positive duty is not handed to the cooling loop")
        return NodeOutcome("succeeded", {"q_specific": OutputValue(Quantity(qs, "J/kg"), UNKNOWN, "h_reactants - h_cooled (Cantera enthalpies)"),
                                         "Q_duty": OutputValue(Quantity(qs * call.value("m_mix").magnitude_in("kg/s"), "W"), UNKNOWN, "specific duty x reactant mass flow")})

    def loop(call):
        Q = call.value("Q_duty").to("W")
        rec = tespy.solve(ChainProblem("jacket", FluidIdentity("water"), call.value("m_w"), call.value("p_w"), call.value("T_w_in"), (HeatExchangerSpec("jacket", Q, 1.0),),
                                       inlet_provenance=(("duty", call.inputs["Q_duty"].producer_stamp),)))
        ref = ProviderRecordRef.of_record(rec)
        if not rec.succeeded:
            return NodeOutcome.failed(rec.reason, provider_records=(ref,))
        ex.records[call.execution_identity] = rec
        t_out = rec.scalars["c2.temperature"].magnitude
        m = rec.scalars["c1.mass_flow"].magnitude
        absorbed = m * (rec.scalars["c2.enthalpy"].magnitude - rec.scalars["c1.enthalpy"].magnitude)
        lo, hi = WATER_RANGE_K
        rep = ApplicabilityReport("water_liquid_range", "within" if lo <= rec.scalars["c1.temperature"].magnitude and t_out <= hi else "outside",
                                  digest_of({"Tin": rec.scalars["c1.temperature"].magnitude, "Tout": t_out, "range": [lo, hi]}),
                                  f"water {rec.scalars['c1.temperature'].magnitude:.2f} -> {t_out:.2f} K against the declared liquid range [{lo}, {hi}] K")
        outs = {"T_water_out": Quantity(t_out, "K"), "heat_absorbed": Quantity(absorbed, "W"), "water_rise": Quantity(t_out - rec.scalars["c1.temperature"].magnitude, "K")}
        return NodeOutcome("succeeded", {k: OutputValue(v, UNKNOWN, f"tespy {ts_s.version}") for k, v in outs.items()}, provider_records=(ref,), applicability=(rep,),
                           delegated_record_digest=rec.digest)

    def balance(call):
        gas, water = call.value("Q_duty").magnitude_in("W"), call.value("heat_absorbed").magnitude_in("W")
        return NodeOutcome("succeeded", {"residual": OutputValue(Quantity(gas - water, "W"), UNKNOWN, "Q from Cantera - m dh from TESPy"),
                                         "relative_residual": OutputValue(Quantity(abs(gas - water) / abs(gas), "dimensionless"), UNKNOWN, "of the duty")})

    def kinetic_factory(setting):
        rtol, atol, samples = setting

        def run(call):
            w = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(KINETIC_END_S, "s")))
            rec = cant.constant_pressure_reactor(gri, comp, call.value("T_start"), call.value("p"), w, samples=samples, rtol=rtol, atol=atol, species=("CH4", "CO2", "CO"))
            ref = ct_ref(rec)
            if not rec.succeeded:
                return NodeOutcome.failed(rec.reason, provider_records=(ref,))
            ex.records[call.execution_identity] = rec
            t = np.array(rec.series_for("temperature").times_s)
            T = np.array(rec.series_for("temperature").values)
            ch4 = np.array(rec.series_for("X_CH4").values)
            rate = np.gradient(T, t)
            i = int(np.argmax(rate))
            ex.series[call.execution_identity] = {"t": t.tolist(), "T": T.tolist(), "X_CH4": ch4.tolist(), "X_CO2": list(rec.series_for("X_CO2").values), "X_CO": list(rec.series_for("X_CO").values)}
            refined = float(t[i])
            if 0 < i < len(t) - 1:      # POST-HOC refinement: parabola through the three samples around the discrete maximum of dT/dt
                a, b, c = rate[i - 1], rate[i], rate[i + 1]
                denom = a - 2 * b + c
                if denom != 0:
                    refined = float(t[i] + 0.5 * (t[i + 1] - t[i - 1]) / 2 * (a - c) / denom)
            outs = {"ignition_delay": Quantity(float(t[i]), "s"), "T_final": Quantity(float(T[-1]), "K"), "max_heating_rate": Quantity(float(rate[i]), "K/s"),
                    "fuel_remaining": Quantity(float(ch4[-1] / ch4[0]), "dimensionless"), "ignition_delay_refined_post_hoc": Quantity(refined, "s")}
            return NodeOutcome("succeeded", {k: OutputValue(v, UNKNOWN, f"cantera {ct_s.version} reactor rtol={rtol:g}") for k, v in outs.items()}, provider_records=(ref,),
                               delegated_record_digest=rec.digest)
        return run

    def limit(call):
        rec = cant.equilibrium(gri, comp, call.value("T_start"), call.value("p"), constraint="HP", species=("CO2", "CO"))
        if not rec.succeeded:
            return NodeOutcome.failed(rec.reason, provider_records=(ct_ref(rec),))
        ex.records[call.execution_identity] = rec
        lo, hi = q(rec, "thermo_T_min").magnitude, q(rec, "thermo_T_max").magnitude
        T = q(rec, "temperature").magnitude
        rep = ApplicabilityReport("thermo_range", "within" if lo <= T <= hi else "outside", digest_of({"T": T, "range": [lo, hi]}),
                                  f"equilibrium temperature {T:.1f} K against the species thermodynamic data range [{lo:g}, {hi:g}] K")
        return NodeOutcome("succeeded", {"T_equilibrium": OutputValue(q(rec, "temperature"), UNKNOWN, "HP equilibrium of the kinetic initial state")}, provider_records=(ct_ref(rec),),
                           applicability=(rep,), delegated_record_digest=rec.digest)

    def approach(call):
        eq = call.value("T_equilibrium").magnitude_in("K")
        return NodeOutcome("succeeded", {"relative_gap": OutputValue(Quantity(abs(call.value("T_final").magnitude_in("K") - eq) / eq, "dimensionless"), UNKNOWN,
                                                                       "|T(50 ms) - T_HP| / T_HP")})

    def integrator(call):
        a, b = call.value("ignition_b").magnitude_in("s"), call.value("ignition_c").magnitude_in("s")
        ra, rb = call.value("refined_b").magnitude_in("s"), call.value("refined_c").magnitude_in("s")
        return NodeOutcome("succeeded", {
            "ignition_relative_change": OutputValue(Quantity(abs(b - a) / b, "dimensionless"), UNKNOWN, "two finest integrator settings, discrete maximum (criterion fixed before the run)"),
            "ignition_relative_change_refined_post_hoc": OutputValue(Quantity(abs(rb - ra) / rb, "dimensionless"), UNKNOWN, "POST HOC: parabola-refined ignition time"),
            "final_temperature_change": OutputValue(Quantity(abs(call.value("T_c").magnitude_in("K") - call.value("T_b").magnitude_in("K")), "K"), UNKNOWN, "two finest integrator settings")})

    def lhv(call):
        """Complete combustion of CH4 + 2 O2 (water as vapour) at the mechanism's LOWEST stored temperature (300 K), not at the reference's 298.15 K: 298.15 K lies below the range the
        mechanism bytes store, so the applicability check would (rightly) be 'outside'.  The heating value at 310 K gives the local temperature slope, from which the size of the 1.85 K offset to the reference
        temperature is BOUNDED (reported, from the same thermodynamic data, not used to adjust the value)."""
        T0 = call.value("T_ref")
        rec = cant.equilibrium(gri, LHV_MIXTURE, T0, call.value("p"), constraint="TP", species=("CO2", "H2O", "CH4"))
        rec2 = cant.equilibrium(gri, LHV_MIXTURE, Quantity(T0.magnitude_in("K") + 10.0, "K"), call.value("p"), constraint="TP", species=("CO2", "H2O", "CH4"))
        for r in (rec, rec2):
            if not r.succeeded:
                return NodeOutcome.failed(r.reason, provider_records=(ct_ref(r),))
        ex.records[call.execution_identity] = rec
        heat = lambda r: (q(r, "h_mole_initial").magnitude - q(r, "h_mole").magnitude) * 3.0 / 1e6      # kJ per mol of CH4 (3 mol of mixture per mol CH4)
        v0, v1 = heat(rec), heat(rec2)
        slope = (v1 - v0) / 10.0
        conversion = 1.0 - q(rec, "X_CH4").magnitude / LHV_MIXTURE["CH4"]
        lo, hi = q(rec, "thermo_T_min").magnitude, q(rec, "thermo_T_max").magnitude
        T = T0.magnitude_in("K")
        rep = ApplicabilityReport("thermo_range", "within" if lo <= T <= hi else "outside", digest_of({"T": T, "range": [lo, hi]}),
                                  f"evaluation temperature {T:.2f} K against the species thermodynamic data range [{lo:g}, {hi:g}] K")
        outs = {"lower_heating_value": Quantity(v0, "kJ/mol"), "lhv_temperature_slope": Quantity(slope, "kJ/(mol*K)"),
                "temperature_offset_bound": Quantity(abs(slope) * (T - 298.15), "kJ/mol"), "fuel_conversion": Quantity(conversion, "dimensionless")}
        return NodeOutcome("succeeded", {k: OutputValue(v, UNKNOWN, f"cantera {ct_s.version} TP equilibrium at {T:g} K, water as vapour") for k, v in outs.items()},
                           provider_records=(ct_ref(rec), ct_ref(rec2)), applicability=(rep,), delegated_record_digest=rec.digest)

    cfg = {"mechanism": gri.sha256, "composition": sorted([k, repr(v)] for k, v in comp.items()), "cantera": ct_s.version, "tespy": ts_s.version, "variant": variant}
    auth = {"adiabatic": CallbackAuthority("chem-adiabatic-equilibrium", adiabatic, config=cfg, kind="provider", deterministic=True),
            "cooled": CallbackAuthority("chem-cooled-equilibrium", cooled, config=cfg, kind="provider", deterministic=True),
            "duty": CallbackAuthority("chem-heat-duty", duty, config={"rule": "Q = m_mix (h_reactants - h_cooled)"}, deterministic=True),
            "loop": CallbackAuthority("chem-coolant-loop", loop, config={**cfg, "fluid": "water", "hx": "SimpleHeatExchanger, pr=1", "range": list(WATER_RANGE_K)}, kind="provider", deterministic=True),
            "balance": CallbackAuthority("chem-energy-balance", balance, config={}, deterministic=True),
            "limit": CallbackAuthority("chem-equilibrium-limit", limit, config=cfg, kind="provider", deterministic=True),
            "approach": CallbackAuthority("chem-equilibrium-approach", approach, config={}, deterministic=True),
            "integrator": CallbackAuthority("chem-integrator-study", integrator, config={"settings": [list(s) for s in KINETIC_SETTINGS]}, deterministic=True),
            "lhv": CallbackAuthority("chem-heat-of-combustion", lhv, config=cfg, kind="provider", deterministic=True)}
    kin = {i: CallbackAuthority(f"chem-kinetic-{i}", kinetic_factory(s), config={**cfg, "setting": list(s), "end_s": KINETIC_END_S, "T_start": T_KINETIC_START}, kind="provider", deterministic=True)
           for i, s in enumerate(KINETIC_SETTINGS)}
    lit = lambda name, v, u, why: LiteralInput(name, Quantity(v, u), Uncertainty.unknown(why))  # noqa: E731
    conf = digest_of(cfg)
    binds_c, binds_t = ("cantera",), ("tespy",)
    T0, P = lit("T0", T_REACTANTS, "K", "declared reactant temperature"), lit("p", P_ATM, "Pa", "declared pressure")
    nodes = [
        NodeSpec("adiabatic_equilibrium", NodeKind.PROVIDER_EXECUTION, auth["adiabatic"].ref,
                 tuple(NodeOutputSpec(n, u) for n, u in (("T_adiabatic", "K"), ("h_reactants", "J/kg"), ("X_CO2", "dimensionless"), ("X_H2O", "dimensionless"), ("X_CO", "dimensionless"),
                                                        ("X_NO", "dimensionless"), ("X_OH", "dimensionless"), ("element_residual", "dimensionless"))),
                 literals=(T0, P), provider_binding_ids=binds_c, applicability_checks=("thermo_range",), configuration_digest=conf),
        NodeSpec("cooled_equilibrium", NodeKind.PROVIDER_EXECUTION, auth["cooled"].ref,
                 tuple(NodeOutputSpec(n, u) for n, u in (("h_cooled", "J/kg"), ("X_CO2_out", "dimensionless"), ("X_H2O_out", "dimensionless"), ("X_CO_out", "dimensionless"),
                                                        ("element_residual", "dimensionless"))),
                 literals=(lit("T_out", t_out, "K", "declared exhaust outlet temperature"), P), provider_binding_ids=binds_c, applicability_checks=("thermo_range",), configuration_digest=conf),
        NodeSpec("heat_duty", NodeKind.AGGREGATE, auth["duty"].ref, (NodeOutputSpec("q_specific", "J/kg"), NodeOutputSpec("Q_duty", "W")),
                 inputs=(NodeInput("h_reactants", "adiabatic_equilibrium", "h_reactants", "J/kg"), NodeInput("h_cooled", "cooled_equilibrium", "h_cooled", "J/kg")),
                 literals=(lit("m_mix", M_MIX, "kg/s", "declared reactant mass flow"),), configuration_digest=conf),
        NodeSpec("coolant_loop", NodeKind.PROVIDER_EXECUTION, auth["loop"].ref, tuple(NodeOutputSpec(n, u) for n, u in (("T_water_out", "K"), ("heat_absorbed", "W"), ("water_rise", "K"))),
                 inputs=(NodeInput("Q_duty", "heat_duty", "Q_duty", "W"),),
                 literals=(lit("m_w", M_WATER, "kg/s", "declared water flow"), lit("p_w", P_WATER, "Pa", "declared loop pressure"), lit("T_w_in", T_WATER_IN, "K", "declared water inlet")),
                 provider_binding_ids=binds_t, applicability_checks=("water_liquid_range",), configuration_digest=conf),
        NodeSpec("energy_balance", NodeKind.AGGREGATE, auth["balance"].ref, (NodeOutputSpec("residual", "W"), NodeOutputSpec("relative_residual", "dimensionless")),
                 inputs=(NodeInput("Q_duty", "heat_duty", "Q_duty", "W"), NodeInput("heat_absorbed", "coolant_loop", "heat_absorbed", "W")), configuration_digest=conf),
        NodeSpec("equilibrium_limit", NodeKind.PROVIDER_EXECUTION, auth["limit"].ref, (NodeOutputSpec("T_equilibrium", "K"),),
                 literals=(lit("T_start", T_KINETIC_START, "K", "declared kinetic initial temperature"), P), provider_binding_ids=binds_c, applicability_checks=("thermo_range",),
                 configuration_digest=conf),
        NodeSpec("heat_of_combustion", NodeKind.PROVIDER_EXECUTION, auth["lhv"].ref,
                 tuple(NodeOutputSpec(n, u) for n, u in (("lower_heating_value", "kJ/mol"), ("lhv_temperature_slope", "kJ/(mol*K)"), ("temperature_offset_bound", "kJ/mol"), ("fuel_conversion", "dimensionless"))),
                 literals=(lit("T_ref", 300.0, "K", "the mechanism's lowest stored thermodynamic temperature (the reference value is at 298.15 K, below it)"), P),
                 provider_binding_ids=binds_c, applicability_checks=("thermo_range",), configuration_digest=conf)]
    for i, s in enumerate(KINETIC_SETTINGS):
        nodes.append(NodeSpec(f"kinetic_{i}", NodeKind.PROVIDER_EXECUTION, kin[i].ref,
                              tuple(NodeOutputSpec(n, u) for n, u in (("ignition_delay", "s"), ("T_final", "K"), ("max_heating_rate", "K/s"), ("fuel_remaining", "dimensionless"),
                                                     ("ignition_delay_refined_post_hoc", "s"))),
                              literals=(lit("T_start", T_KINETIC_START, "K", "declared kinetic initial temperature"), P), provider_binding_ids=binds_c, configuration_digest=conf))
    nodes.append(NodeSpec("equilibrium_approach", NodeKind.AGGREGATE, auth["approach"].ref, (NodeOutputSpec("relative_gap", "dimensionless"),),
                          inputs=(NodeInput("T_final", "kinetic_2", "T_final", "K"), NodeInput("T_equilibrium", "equilibrium_limit", "T_equilibrium", "K")), configuration_digest=conf))
    nodes.append(NodeSpec("integrator_study", NodeKind.AGGREGATE, auth["integrator"].ref, (NodeOutputSpec("ignition_relative_change", "dimensionless"), NodeOutputSpec("ignition_relative_change_refined_post_hoc", "dimensionless"),
                                                                                    NodeOutputSpec("final_temperature_change", "K")),
                          inputs=(NodeInput("ignition_b", "kinetic_1", "ignition_delay", "s"), NodeInput("ignition_c", "kinetic_2", "ignition_delay", "s"),
                                  NodeInput("T_b", "kinetic_1", "T_final", "K"), NodeInput("T_c", "kinetic_2", "T_final", "K"),
                                  NodeInput("refined_b", "kinetic_1", "ignition_delay_refined_post_hoc", "s"), NodeInput("refined_c", "kinetic_2", "ignition_delay_refined_post_hoc", "s")),
                          configuration_digest=conf))
    obs = []
    for node in nodes:
        for o in node.outputs:
            obs.append(RequestedObservable(f"{node.node_id}__{o.name}", node.node_id, o.name, o.unit))
    cd = {k: digest_of(v.to_dict()) for k, v in defs.items()}
    cobs = (ConstraintObservation("b_tflame", "max_flame_temperature", cd["max_flame_temperature"], "adiabatic_equilibrium__T_adiabatic"),
            ConstraintObservation("b_twater", "max_water_outlet", cd["max_water_outlet"], "coolant_loop__T_water_out"))
    scenario = ScenarioSpecification("jacketed-reactor", "1", Quantity(0, "s"), Quantity(1, "s"), segments=(ScenarioSegment("steady", Quantity(0, "s"), Quantity(1, "s")),))
    timeline = Timeline.from_scenario(scenario, timeline_id="jacketed-reactor", basis=TimeBasis("lab", "elapsed", "start"), histories=())
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("reactor", "component", (InitialStateValue("reference", Quantity(0.0, "dimensionless"), Uncertainty.unknown("declared placeholder")),)),))
    bindings = (ProviderBinding("cantera", "cantera", ct_s.version, ct_s.digest), ProviderBinding("tespy", "tespy", ts_s.version, ts_s.digest))
    request = SystemRunRequest.build(
        request_id=f"flagship-d-chemical-thermal-{variant}", system=system, scenario=scenario, timeline=timeline, environment=None, initial_state=initial, nodes=tuple(nodes),
        observables=tuple(obs), model_selections=(ModelSelection("reactor", "gri-mech-3.0-equilibrium-and-adiabatic-reactor", ct_s.version), ModelSelection("jacket", "tespy-water-jacket", ts_s.version)),
        provider_bindings=bindings, constraint_observations=cobs, profile=ExecutionProfile((), "off", True, ()),
        environment_absent_reason="steady flow-reactor problem with declared inlet states; no time-varying environment channel is read")
    authorities = AuthorityRegistry((*auth.values(), *kin.values()))
    context = RuntimeContext(authorities, system=system, scenario=scenario, timeline=timeline, environment=None, constraints={cd[k]: v for k, v in defs.items()}, providers=registry)
    return Chemistry(request, context, ex, defs, registry, variant)


# ==================================================================================================== verification, summary
@dataclass
class ChemistryRun:
    chemistry: Chemistry
    result: Any
    preflight: Any
    constraints: tuple
    conservation: tuple = ()
    summary: Any = None
    ladder: Any = None
    comparisons: tuple = ()
    references: tuple = ()
    uncertainty: Any = None


#: level 3 is REACHED only if EVERY one of these checks ran and was met: a check that did not run is not a pass (removing evidence must not raise the level)
LEVEL3_CHECKS = ("lhv_hess_law", "equilibrium_limit")


def level3_entry(lhv_comparison, gap: float | None) -> LevelEntry:
    """Level 3 from the Hess's-law comparison (None if that node produced nothing) and the kinetic-vs-equilibrium gap (None likewise)."""
    links: list[EvidenceLink] = []
    state: dict[str, str] = {}
    if lhv_comparison is not None:
        links.append(EvidenceLink.of_comparison(lhv_comparison))
        state["lhv_hess_law"] = lhv_comparison.outcome
    if gap is not None:
        ok = gap <= EQUILIBRIUM_APPROACH_REL
        links.append(EvidenceLink.of_record("equilibrium_limit", {"relative_gap": gap, "criterion": EQUILIBRIUM_APPROACH_REL},
                                            "analytic_limit_comparison_verifies_implementation_only", "met" if ok else "not_met",
                                            f"kinetic end state vs HP equilibrium of the same initial state: relative gap {gap:.2e} (criterion {EQUILIBRIUM_APPROACH_REL:g})"))
        state["equilibrium_limit"] = "met" if ok else "not_met"
    missing = [c for c in LEVEL3_CHECKS if c not in state]
    reached = not missing and all(v == "met" for v in state.values())
    text = {"lhv_hess_law": "heating value of methane vs Hess's law with evaluated NIST data",
            "equilibrium_limit": "the kinetic reactor converges to the equilibrium it must approach (thermodynamic consistency of mechanism and integrator)"}
    note = "; ".join(f"{text[c]}: " + (state[c].upper().replace("_", " ") if c in state else "NOT RUN (its node produced nothing)") for c in LEVEL3_CHECKS)
    status = LevelStatus.REACHED if reached else LevelStatus.ATTEMPTED_NOT_REACHED if links else LevelStatus.NOT_ATTEMPTED
    return LevelEntry(3, status, tuple(links), note)


def _v(result, node: str, name: str) -> float | None:
    o = result.observable(f"{node}__{name}")
    return None if o.value is None else o.value.value.magnitude


def run_chemistry(registry=None, *, variant: str = "nominal") -> ChemistryRun:
    from engcore.system_runtime import BalanceSpec, SystemExecutor, TermSource, assess_conservation, assess_constraints, compile_plan, preflight

    ch = build_chemistry(registry, variant=variant)
    report = preflight(ch.request, compile_plan(ch.request), ch.context)
    result = SystemExecutor(ch.context).run(ch.request)
    constraints = assess_constraints(result, ch.context.system, ch.context.constraints)
    conservation = assess_conservation(result, (BalanceSpec("heat_duty", (TermSource("cantera_duty", "heat_duty__Q_duty"),), (TermSource("water_absorbed", "coolant_loop__heat_absorbed"),),
                                                            Quantity(ENERGY_BALANCE_REL_TOL * (_v(result, "heat_duty", "Q_duty") or 1.0), "W")),))
    run = ChemistryRun(ch, result, report, constraints, conservation)
    entries = [contract_integrity_entry(report, result)]
    el = [_v(result, n, "element_residual") for n in ("adiabatic_equilibrium", "cooled_equilibrium")]
    closed = [c for c in conservation if c.status == "closed"]
    if all(x is not None for x in el) and closed:
        ok = max(el) <= ELEMENT_TOL
        entries.append(LevelEntry(2, LevelStatus.REACHED if ok else LevelStatus.ATTEMPTED_NOT_REACHED,
                                  (EvidenceLink.of_record("element_balance", {"max_relative_change_by_node": dict(zip(("adiabatic_equilibrium", "cooled_equilibrium"), el)), "criterion": ELEMENT_TOL},
                                                          "conservation_residual", "met" if ok else "not_met", f"max relative change of C, H, O, N mass fractions {max(el):.2e} (criterion {ELEMENT_TOL:g})"),
                                   EvidenceLink.of_record("conservation_assessment", closed[0].to_dict(), "conservation_residual", "met", f"heat duty: Cantera vs TESPy residual {closed[0].residual.magnitude:.2e} W")),
                                  "elemental mass conserved through both equilibrations (a genuine conservation check: the solver could violate it); the heat the chemistry says must be removed equals the heat "
                                  "the water absorbs - an INTERFACE consistency (TESPy is handed that duty as its heat input, so closure cannot fail unless the solver or a unit is wrong). Criteria fixed before the run"))
    else:
        entries.append(LevelEntry(2, LevelStatus.ATTEMPTED_NOT_REACHED if conservation else LevelStatus.NOT_ATTEMPTED, (), "; ".join(f"{c.balance_id}: {c.status}" for c in conservation) or "not assessable"))
    hess, _ = load_hess()
    comparisons, references = [], []
    lhv, gap = _v(result, "heat_of_combustion", "lower_heating_value"), _v(result, "equilibrium_approach", "relative_gap")
    lhv_cmp = None
    if lhv is not None:
        crit = PredeclaredCriterion("lhv_hess_law", "lower_heating_value", "absolute_difference", Quantity(LHV_TOL_KJ_PER_MOL, "kJ/mol"),
                                    "flagships/forge_flagships/chem_thermal.py:LHV_TOL_KJ_PER_MOL (fixed before the first run)")
        bound = _v(result, "heat_of_combustion", "temperature_offset_bound")
        lhv_cmp = compare_to_reference(hess, crit, {"temperature": Quantity(300.0, "K"), "pressure": Quantity(P_ATM, "Pa")}, value=Quantity(abs(lhv - hess.values("lower_heating_value")[0]), "kJ/mol"),
                                       compared_identity=result.receipt("heat_of_combustion").execution_identity_digest,
                                       note=f"Cantera/GRI-Mech 3.0 thermo at 300 K {lhv:.3f} kJ/mol vs Hess's law at 298.15 K {hess.values('lower_heating_value')[0]:.3f} (Chase 1998) / "
                                            f"{hess.values('lower_heating_value')[1]:.3f} (CODATA with Manion 2002); the 1.85 K offset is bounded by {bound:.3f} kJ/mol from the same thermodynamic data")
        comparisons.append(lhv_cmp)
        references.append(hess)
    entries.append(level3_entry(lhv_cmp, gap))
    ic, fc = _v(result, "integrator_study", "ignition_relative_change"), _v(result, "integrator_study", "final_temperature_change")
    if ic is not None:
        ok = ic <= INTEGRATOR_IGNITION_REL and fc <= INTEGRATOR_T_ABS_K
        post = _v(result, "integrator_study", "ignition_relative_change_refined_post_hoc")
        links4 = [EvidenceLink.of_record("integrator_study", {"ignition_relative_change": ic, "final_temperature_change_K": fc, "criteria": {"ignition_relative": INTEGRATOR_IGNITION_REL, "final_temperature_K": INTEGRATOR_T_ABS_K}},
                                         "discretisation_convergence", "met" if ok else "not_met",
                               f"ignition delay (discrete maximum of dT/dt) changed {ic:.3%} between the two finest settings (criterion {INTEGRATOR_IGNITION_REL:.0%}); final temperature changed {fc:.2e} K (criterion {INTEGRATOR_T_ABS_K} K)")]
        if not ok and post is not None:
            links4.append(EvidenceLink.of_record("integrator_study_post_hoc", {"refined_ignition_relative_change": post, "criterion": INTEGRATOR_IGNITION_REL},
                                                 "post_hoc_discretisation_convergence", "met" if post <= INTEGRATOR_IGNITION_REL else "not_met",
                                                 f"POST HOC: with the ignition time refined by a parabola through the three samples around the maximum the change is {post:.3%}"))
        delay = _v(result, "kinetic_2", "ignition_delay")
        spacings = [KINETIC_END_S / (s - 1) for _, _, s in KINETIC_SETTINGS]
        spacing_text = (f"whose spacing ({min(spacings) * 1e3:.2g}-{max(spacings) * 1e3:.2g} ms) is itself {100 * min(spacings) / delay:.1f}-{100 * max(spacings) / delay:.1f} % of the ignition delay"
                        if delay else "whose spacing is not compared with the ignition delay (no delay was produced)")
        entries.append(LevelEntry(4, LevelStatus.REACHED if ok else LevelStatus.ATTEMPTED_NOT_REACHED, tuple(links4),
                                  "three integrator tolerances / output resolutions. The predeclared ignition criterion compares a discrete sample time " + spacing_text
                                  + ("; the outcome is reported as it came out" if ok else ", so a converged solution need not satisfy a criterion tighter than that; the outcome is reported as it came out, "
                                     "with a post hoc refined reading beside it")))
    else:
        entries.append(LevelEntry(4, LevelStatus.NOT_ATTEMPTED, (), "the integrator study was not produced"))
    entries += [LevelEntry(5, LevelStatus.NOT_AVAILABLE, (), "no second, independent chemistry provider exists in the ecosystem; the two chemistry solvers would share the mechanism and thermodynamic data"),
                LevelEntry(6, LevelStatus.NOT_AVAILABLE, (), "no published numerical benchmark for this system was integrated"),
                LevelEntry(7, LevelStatus.NOT_AVAILABLE, (), "no measured data (ignition delays, flame temperature, exhaust composition) were integrated; GRI-Mech 3.0 was optimised against experiments by its AUTHORS, which is their claim, not a Forge result")]
    run.ladder = VerificationLadder.of(**{f"l{e.level}": e for e in entries})
    run.comparisons, run.references = tuple(comparisons), tuple(references)
    run.uncertainty = UncertaintyStatement(
        (), ("reactant composition, temperature, pressure (declared)", "flows and outlet temperature (declared)", "GRI-Mech 3.0 rate and thermodynamic parameters (the mechanism authors' values; uncertainty not propagated)",
             "water properties (CoolProp via TESPy, uncertainty not propagated)"),
        "NOT QUANTIFIED: equilibrium and 0-D adiabatic reactor idealisations, ideal gas, no heat loss, water assumed to absorb every watt of the duty (unknown, not zero)",
        ("mechanism: GRI-Mech 3.0 bytes bound by digest (provider-bundled with Cantera); no property records for the gas",),
        "equilibrium temperatures were checked against the species thermodynamic data range stored in the mechanism and the water loop against a declared liquid range; the mechanism's "
        "KINETIC validity range is the authors' statement and is NOT established by Forge (the kinetic reactor is therefore a demonstration of execution and consistency only)",
        "the NIST-JANAF based Hess's-law value is an analytic reference built from evaluated data; it applies at 298.15 K, 1 atm and to gas-phase products only")
    run.summary = build_summary(
        f"Jacketed stoichiometric methane/air reactor with a water cooling loop ({variant})", ch.request, result, references=tuple(dict.fromkeys(references)),
        outputs=[("Adiabatic flame temperature", "adiabatic_equilibrium__T_adiabatic"), ("CO2 mole fraction (adiabatic equilibrium)", "adiabatic_equilibrium__X_CO2"),
                 ("H2O mole fraction (adiabatic equilibrium)", "adiabatic_equilibrium__X_H2O"), ("CO mole fraction (adiabatic equilibrium)", "adiabatic_equilibrium__X_CO"),
                 ("NO mole fraction (adiabatic equilibrium)", "adiabatic_equilibrium__X_NO"), ("Heat to remove from the exhaust", "heat_duty__Q_duty"),
                 ("Cooling water outlet temperature", "coolant_loop__T_water_out"), ("Cooling water temperature rise", "coolant_loop__water_rise"),
                 ("Energy-balance residual (Cantera vs TESPy)", "energy_balance__residual"), ("Kinetic ignition delay (finest setting, discrete)", "kinetic_2__ignition_delay"),
                 ("Kinetic end temperature", "kinetic_2__T_final"), ("Equilibrium temperature of the same state", "equilibrium_limit__T_equilibrium"),
                 ("Fuel remaining after 50 ms", "kinetic_2__fuel_remaining"), ("Lower heating value of methane", "heat_of_combustion__lower_heating_value")],
        constraints=constraints, conservation=conservation, ladder=run.ladder, comparisons=comparisons, uncertainty=run.uncertainty,
        trace_observable="coolant_loop__T_water_out" if _v(result, "coolant_loop", "T_water_out") is not None else "adiabatic_equilibrium__T_adiabatic",
        notes=("the reactor-to-jacket interface is an energy balance: the water loop is handed the heat the chemistry says must be removed",
               "inlet states, flows and the exhaust outlet temperature are declared illustrative values"))
    return run


def negative_controls(registry=None) -> dict:
    from engcore.system_runtime import SystemExecutor

    out = {}
    for variant in ("missing_species", "below_thermo_range"):
        ch = build_chemistry(registry, variant=variant)
        res = SystemExecutor(ch.context).run(ch.request)
        out[variant] = {"status": res.status.value, "nodes": {r.node_id: (r.status.value, (r.reason or "")[:300]) for r in res.node_receipts if not r.node_id.startswith(("env.", "mat.", "constraint."))
                                                              and r.status.value != "succeeded"}}
    return out
