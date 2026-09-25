"""TESPy thermal-fluid network provider (BIG 11).

Bounded topology: a declared CHAIN  source -> heat exchanger(s) -> sink.  Each
heat exchanger has a declared heat input Q and pressure ratio; the inlet state
(mass flow, pressure, temperature) and the fluid come from Forge records.  The
TESPy network is provider-specific and never becomes Forge's system ontology:
its connections are mapped onto Forge ``ComponentConnection`` records, and the
component ids are the caller's declared ids.

A network that TESPy does not report converged (status 0) is a FAILED record.
Fluid properties inside TESPy come from CoolProp (TESPy's own dependency):
a TESPy result is therefore NOT independent of CoolProp for comparison purposes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from engcore.materials import FluidIdentity
from engcore.providers import ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, failed
from engcore.scientific.units.quantity import Quantity
from engcore.systems.topology import ComponentConnection

ADAPTER = ("forge_tespy", "0.1")
FLUIDS = {"water": "water", "air": "air"}


@dataclass(frozen=True)
class HeatExchangerSpec:
    component_id: str
    heat: Quantity            # heat INTO the stream (W); negative removes heat
    pressure_ratio: float

    def to_dict(self) -> dict:
        return {"component_id": self.component_id, "heat_W": repr(float(self.heat.to("W").magnitude)), "pr": repr(float(self.pressure_ratio))}


@dataclass(frozen=True)
class ChainProblem:
    network_id: str
    fluid: FluidIdentity
    mass_flow: Quantity
    inlet_pressure: Quantity
    inlet_temperature: Quantity
    exchangers: tuple[HeatExchangerSpec, ...]
    inlet_provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.fluid.fluid_id not in FLUIDS or self.fluid.components:
            raise ProviderRefusal(f"fluid {self.fluid.fluid_id!r} has no declared TESPy mapping")
        if not self.exchangers or len({e.component_id for e in self.exchangers}) != len(self.exchangers):
            raise ProviderRefusal("the chain needs uniquely named heat exchangers")
        if not self.mass_flow.to("kg/s").magnitude > 0:
            raise ProviderRefusal("mass flow must be positive")

    def to_dict(self) -> dict:
        return {"network_id": self.network_id, "fluid": self.fluid.to_dict(), "m_kg_s": repr(float(self.mass_flow.to("kg/s").magnitude)),
                "p_Pa": repr(float(self.inlet_pressure.to("Pa").magnitude)), "T_K": repr(float(self.inlet_temperature.to("K").magnitude)),
                "exchangers": [e.to_dict() for e in self.exchangers], "inlet_provenance": [list(x) for x in self.inlet_provenance]}

    def connections(self) -> tuple[ComponentConnection, ...]:
        names = ["inlet", *(e.component_id for e in self.exchangers), "outlet"]
        return tuple(ComponentConnection(f"c{i + 1}", f"{self.network_id}:c{i + 1}", a, "out1", b, "in1")
                     for i, (a, b) in enumerate(zip(names, names[1:])))


class TESPyProvider:
    def __init__(self, registry) -> None:
        self.status = registry.require("tespy")

    def solve(self, problem: ChainProblem) -> ProviderExecutionRecord:
        from tespy.components import SimpleHeatExchanger, Sink, Source
        from tespy.connections import Connection
        from tespy.networks import Network

        outputs = tuple(f"{c.connection_id}.{q}" for c in problem.connections() for q in ("temperature", "pressure", "enthalpy", "mass_flow"))
        configuration = {"topology": [c.to_dict() for c in problem.connections()], "mode": "design",
                         "units": {"temperature": "K", "pressure": "Pa", "enthalpy": "J/kg", "heat": "W"},
                         "component_type": "SimpleHeatExchanger", "property_backend": "CoolProp (TESPy dependency)"}
        identity = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                                                          problem=problem.to_dict(), configuration=configuration, output_request=outputs)
        t0 = time.perf_counter()
        try:
            nw = Network()
            nw.units.set_defaults(temperature="K", pressure="Pa", pressure_difference="Pa", enthalpy="J/kg", heat="W")
            parts = [Source("inlet"), *(SimpleHeatExchanger(e.component_id) for e in problem.exchangers), Sink("outlet")]
            conns = [Connection(a, "out1", b, "in1", label=f"c{i + 1}") for i, (a, b) in enumerate(zip(parts, parts[1:]))]
            nw.add_conns(*conns)
            conns[0].set_attr(fluid={FLUIDS[problem.fluid.fluid_id]: 1}, m=float(problem.mass_flow.to("kg/s").magnitude),
                              p=float(problem.inlet_pressure.to("Pa").magnitude), T=float(problem.inlet_temperature.to("K").magnitude))
            for comp, spec in zip(parts[1:-1], problem.exchangers):
                comp.set_attr(Q=float(spec.heat.to("W").magnitude), pr=float(spec.pressure_ratio))
            t1 = time.perf_counter()
            nw.solve("design")
            t2 = time.perf_counter()
        except Exception as exc:
            return failed(identity, f"TESPy failed: {type(exc).__name__}: {exc}")
        if not getattr(nw, "converged", False) or getattr(nw, "status", 1) != 0:
            return failed(identity, f"TESPy did not converge (status {getattr(nw, 'status', None)})")
        scalars = {}
        for c in conns:
            scalars[f"{c.label}.temperature"] = Quantity(float(c.T.val_SI), "K")
            scalars[f"{c.label}.pressure"] = Quantity(float(c.p.val_SI), "Pa")
            scalars[f"{c.label}.enthalpy"] = Quantity(float(c.h.val_SI), "J/kg")
            scalars[f"{c.label}.mass_flow"] = Quantity(float(c.m.val_SI), "kg/s")
        return ProviderExecutionRecord(identity, True, "", scalars=scalars,
                                       artifacts={"topology": repr(configuration["topology"]), "tespy_status": "0 (converged)"},
                                       metrics={"build_s": t1 - t0, "solve_s": t2 - t1, "components": len(parts), "connections": len(conns)})
