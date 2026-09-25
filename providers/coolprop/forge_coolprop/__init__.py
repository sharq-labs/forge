"""CoolProp thermophysical-property provider (BIG 11).

Forge ``FluidState`` (exact fluid identity + two independent variables with
units) -> explicit, recorded property request -> CoolProp ``PropsSI`` ->
``FluidPropertyRecord`` bound to the provider execution identity.

Explicit and closed: only the fluid ids in :data:`FLUIDS`, the properties in
:data:`PROPERTIES` and the input pairs in :data:`INPUTS` are accepted; anything
else is refused (never a generic "query any property").  A CoolProp error or a
non-finite value is an UNKNOWN record, never a default.  Values are computed
from reference equations of state: provider-derived data, not measurements.
"""

from __future__ import annotations

import math

from engcore.materials import FluidPropertyRecord, FluidState
from engcore.providers import ProviderExecutionIdentity, ProviderRefusal
from engcore.scientific.units.quantity import Quantity

ADAPTER = ("forge_coolprop", "0.1")
#: Forge fluid id -> CoolProp fluid name (declared mapping; no fuzzy matching)
FLUIDS = {"water": "Water", "air": "Air", "nitrogen": "Nitrogen", "r134a": "R134a", "co2": "CarbonDioxide"}
#: Forge property id -> (CoolProp output key, SI unit)
PROPERTIES = {
    "density": ("Dmass", "kg/m^3"),
    "specific_heat_capacity": ("Cpmass", "J/(kg*K)"),
    "dynamic_viscosity": ("viscosity", "Pa*s"),
    "thermal_conductivity": ("conductivity", "W/(m*K)"),
    "specific_enthalpy": ("Hmass", "J/kg"),
    "specific_entropy": ("Smass", "J/(kg*K)"),
    "vapor_quality": ("Q", "dimensionless"),
}
#: Forge independent variable -> (CoolProp input key, SI unit)
INPUTS = {"temperature": ("T", "K"), "pressure": ("P", "Pa"), "specific_enthalpy": ("Hmass", "J/kg")}
#: CoolProp's reference state is PROCESS-GLOBAL; the adapter sets it on every call
#: so a caller elsewhere in the process cannot move enthalpy/entropy zeros silently.
REFERENCE_STATE = "DEF"
RANGE_BASIS = ("equation-of-state limits Tmin/Tmax/pmax reported by CoolProp for the fluid; transport-property "
               "correlations can have narrower ranges that this check does not see")


class CoolPropProvider:
    def __init__(self, registry, *, backend: str = "HEOS") -> None:
        self.status = registry.require("coolprop")
        if backend not in ("HEOS",):
            raise ProviderRefusal(f"backend {backend!r} is not supported by this adapter")
        self.backend = backend

    def _request(self, state: FluidState, property_id: str):
        if state.fluid.components:
            raise ProviderRefusal("mixtures are not supported by this adapter")
        if state.fluid.fluid_id not in FLUIDS:
            raise ProviderRefusal(f"fluid {state.fluid.fluid_id!r} has no declared CoolProp mapping")
        if property_id not in PROPERTIES:
            raise ProviderRefusal(f"property {property_id!r} is not an explicit adapter output")
        pairs = []
        for c in state.conditions:
            if c.quantity_id not in INPUTS:
                raise ProviderRefusal(f"state variable {c.quantity_id!r} is not a supported CoolProp input")
            key, unit = INPUTS[c.quantity_id]
            pairs.append((key, c.value.to(unit).magnitude, c.value.to_dict()))
        return FLUIDS[state.fluid.fluid_id], PROPERTIES[property_id], pairs

    def resolve(self, state: FluidState, property_id: str) -> FluidPropertyRecord:
        cp_fluid, (out_key, unit), pairs = self._request(state, property_id)
        request = {"fluid": f"{self.backend}::{cp_fluid}", "output": out_key, "unit": unit,
                   "inputs": [[k, repr(v)] for k, v, _ in pairs], "reference_state": REFERENCE_STATE, "range_check": RANGE_BASIS}
        identity = ProviderExecutionIdentity.from_content(
            self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
            problem={"state": state.to_dict(), "property": property_id}, configuration=request, output_request=(property_id,))
        import CoolProp.CoolProp as CP

        (k1, v1, _), (k2, v2, _) = pairs
        base = dict(property_id=property_id, state_digest=state.digest, provider_execution_identity=identity.digest,
                    provider="coolprop", provider_version=self.status.version)
        try:
            CP.set_reference_state(cp_fluid, REFERENCE_STATE)
            limits = {k: CP.PropsSI(k, request["fluid"]) for k in ("Tmin", "Tmax", "pmax")}
            given = dict((k, v) for k, v, _ in pairs)
            outside = [f"T={given['T']!r} K outside [{limits['Tmin']!r}, {limits['Tmax']!r}]"
                       for _ in [0] if "T" in given and not limits["Tmin"] <= given["T"] <= limits["Tmax"]]
            outside += [f"P={given['P']!r} Pa above pmax={limits['pmax']!r}" for _ in [0] if "P" in given and given["P"] > limits["pmax"]]
            if outside:
                return FluidPropertyRecord(**base, status="unknown", value=None, request=request,
                                           reason="state outside the equation-of-state range: " + "; ".join(outside))
            value = CP.PropsSI(out_key, k1, v1, k2, v2, request["fluid"])
            phase = CP.PhaseSI(k1, v1, k2, v2, request["fluid"])
        except ValueError as exc:
            return FluidPropertyRecord(**base, status="unknown", value=None, request=request,
                                       reason=f"CoolProp refused the state: {exc}")
        request = {**request, "phase": phase}
        if not math.isfinite(value) or (out_key == "Q" and not 0.0 <= value <= 1.0):
            return FluidPropertyRecord(**base, status="unknown", value=None, request=request,
                                       reason=f"CoolProp returned {value!r} for {out_key} (phase {phase}); not a usable value")
        return FluidPropertyRecord(**base, status="known", value=Quantity(value, unit), request=request)
