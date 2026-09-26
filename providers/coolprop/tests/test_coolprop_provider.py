"""Proof C (part): real CoolProp executions through the Forge fluid-property boundary."""

from __future__ import annotations

import pytest

from engcore.materials import FluidIdentity, FluidState
from engcore.providers import ProviderRefusal, ProviderRegistry, ProviderUnavailable
from engcore.scenarios import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from forge_coolprop import CoolPropProvider, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("coolprop").available
pytestmark = pytest.mark.skipif(not OK, reason="CoolProp unavailable")


def water(t, p=Quantity(101325, "Pa")):
    return FluidState(FluidIdentity("water"), (NamedQuantity("temperature", t), NamedQuantity("pressure", p)))


def test_explicit_properties_are_computed_records_bound_to_request_and_provider():
    prov = CoolPropProvider(REG)
    s = water(Quantity(25, "degC"))  # affine input converted exactly to K by Forge units
    rec = {p: prov.resolve(s, p) for p in ("density", "specific_heat_capacity", "dynamic_viscosity", "thermal_conductivity",
                                            "specific_enthalpy", "specific_entropy")}
    assert all(r.status == "known" for r in rec.values())
    assert rec["density"].value.magnitude == pytest.approx(997.05, rel=1e-3)  # IAPWS-95 at 25 C, 1 atm (reference EOS value)
    assert rec["thermal_conductivity"].value.magnitude == pytest.approx(0.607, rel=1e-2)
    d = rec["density"]
    assert d.classification == "provider_derived_property_not_measurement" and d.uncertainty.kind.value == "unknown"
    assert d.request["fluid"] == "HEOS::Water" and d.request["phase"] == "liquid" and d.provider_version == REG.status("coolprop").version
    # identity follows content: another state or another property is another execution
    assert prov.resolve(water(Quantity(30, "degC")), "density").provider_execution_identity != d.provider_execution_identity
    assert rec["specific_heat_capacity"].provider_execution_identity != d.provider_execution_identity


def test_two_phase_quality_and_refusals_are_explicit():
    prov = CoolPropProvider(REG)
    sat = FluidState(FluidIdentity("water"), (NamedQuantity("pressure", Quantity(101325, "Pa")),
                                              NamedQuantity("specific_enthalpy", Quantity(1.5e6, "J/kg"))))
    q = prov.resolve(sat, "vapor_quality")
    assert q.status == "known" and 0 < q.value.magnitude < 1 and q.request["phase"] == "twophase"
    below = prov.resolve(water(Quantity(1, "K")), "density")  # far below the triple point
    assert below.status == "unknown" and below.value is None and "outside the equation-of-state range" in below.reason
    above = prov.resolve(water(Quantity(5000, "K")), "density")  # above the EOS Tmax: never an extrapolated number
    assert above.status == "unknown" and "outside the equation-of-state range" in above.reason
    with pytest.raises(ProviderRefusal, match="no declared CoolProp mapping"):
        prov.resolve(FluidState(FluidIdentity("unobtainium"), water(Quantity(300, "K")).conditions), "density")
    with pytest.raises(ProviderRefusal, match="not an explicit adapter output"):
        prov.resolve(water(Quantity(300, "K")), "speed_of_light")


def test_absent_provider_is_refused_not_substituted():
    reg = ProviderRegistry()
    reg.register_unavailable(descriptor.CAPABILITY, "simulated: CoolProp not installed in this environment")
    with pytest.raises(ProviderUnavailable, match="no other provider is substituted"):
        CoolPropProvider(reg)


def test_request_is_content_only_and_the_reference_state_is_pinned():
    import CoolProp.CoolProp as CP

    prov = CoolPropProvider(REG)
    a = prov.resolve(water(Quantity(320, "K")), "specific_enthalpy")
    CP.set_reference_state("Water", "NBP")  # someone else in the process moves the global enthalpy zero ...
    b = prov.resolve(water(Quantity(320, "K")), "specific_enthalpy")
    assert b.value == a.value and b.request == a.request and b.digest == a.digest  # ... the adapter re-pins DEF
    assert a.request["reference_state"] == "DEF" and "solve_seconds" not in a.request
