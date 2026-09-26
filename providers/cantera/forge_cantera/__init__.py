"""Cantera chemistry provider (BIG 11): equilibrium and transient reactors.

A mechanism is a scientific INPUT: :class:`Mechanism` binds the file name, the
exact bytes (sha256) and the phase; Cantera is given those exact bytes
(``Solution(yaml=...)``), so what ran is what was hashed.  A mechanism is not
universally valid chemistry: its validity range is the mechanism authors'
statement, not Forge's -- this adapter records it and asserts nothing.

Compositions are explicit mole fractions that must sum to one over species the
mechanism defines (nothing normalised or dropped silently).  A Cantera error or
a non-finite result is a failed record with no outputs.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass
from typing import Mapping

from engcore.providers import ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, QuantitySeries, failed
from engcore.scenarios.timeline import TimeWindow
from engcore.scientific.units.quantity import Quantity

ADAPTER = ("forge_cantera", "0.1")
#: elements of the mechanisms this adapter reports elemental mass fractions for (GRI-Mech 3.0: H, C, O, N, Ar); a mechanism lacking one is refused
_ELEMENTS = ("H", "C", "O", "N", "Ar")


@dataclass(frozen=True)
class Mechanism:
    file_name: str
    content: bytes
    phase: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def to_dict(self) -> dict:
        return {"file_name": self.file_name, "sha256": self.sha256, "phase": self.phase,
                "validity": "as stated by the mechanism authors; not asserted by Forge"}

    @classmethod
    def from_cantera_data(cls, file_name: str, phase: str = "") -> "Mechanism":
        """A mechanism shipped in Cantera's data directories, read as exact bytes."""
        import cantera as ct

        for d in ct.get_data_directories():
            path = os.path.join(d, file_name)
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    return cls(file_name, fh.read(), phase)
        raise ProviderRefusal(f"mechanism {file_name!r} is not in Cantera's data directories")


class CanteraProvider:
    def __init__(self, registry) -> None:
        self.status = registry.require("cantera")

    def _solution(self, mechanism: Mechanism):
        import cantera as ct

        text = mechanism.content.decode("utf-8")
        import re
        if re.search(r"[\w.-]+\.(yaml|yml|cti|xml)/", text):
            raise ProviderRefusal("the mechanism references another file whose bytes are not bound; inline it first")
        return ct.Solution(yaml=text, name=mechanism.phase) if mechanism.phase else ct.Solution(yaml=text)

    @staticmethod
    def _composition(gas, composition: Mapping[str, float]) -> str:
        unknown = sorted(set(composition) - set(gas.species_names))
        if unknown:
            raise ProviderRefusal(f"species {unknown} are not defined by the mechanism")
        if any(not (0 <= x <= 1) for x in composition.values()) or abs(sum(composition.values()) - 1.0) > 1e-12:
            raise ProviderRefusal("mole fractions must lie in [0, 1] and sum to one; nothing is normalised silently")
        return ", ".join(f"{k}:{repr(float(v))}" for k, v in sorted(composition.items()))

    def _identity(self, mechanism, problem, configuration, outputs, window=None):
        return ProviderExecutionIdentity.from_content(
            self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1], problem=problem,
            configuration=configuration, inputs={"mechanism": mechanism.content}, output_request=outputs, window=window)

    def equilibrium(self, mechanism: Mechanism, composition: Mapping[str, float], temperature: Quantity, pressure: Quantity,
                    *, constraint: str = "HP", species: tuple[str, ...] = ()) -> ProviderExecutionRecord:
        if constraint not in ("TP", "HP"):
            raise ProviderRefusal("equilibrium constraint is TP or HP")
        T, P = temperature.to("K").magnitude, pressure.to("Pa").magnitude
        outputs = ("temperature", "pressure", "density", "h_mass", "h_mole", "mean_molecular_weight", "h_mass_initial", "h_mole_initial", "thermo_T_min", "thermo_T_max") + tuple(f"elem_Y0_{e}" for e in _ELEMENTS) + tuple(f"elem_Y_{e}" for e in _ELEMENTS) + tuple(f"X_{s}" for s in species)
        problem = {"mechanism": mechanism.to_dict(), "composition": sorted([k, repr(float(v))] for k, v in composition.items()),
                   "T_K": repr(T), "P_Pa": repr(P), "constraint": constraint}
        ident = self._identity(mechanism, problem, {"solver": "equilibrate", "constraint": constraint}, outputs)
        t0 = time.perf_counter()
        try:
            gas = self._solution(mechanism)
            gas.TPX = T, P, self._composition(gas, composition)
            initial = {"h_mass_initial": gas.enthalpy_mass, "h_mole_initial": gas.enthalpy_mole,
                       **{f"elem_Y0_{e}": gas.elemental_mass_fraction(e) for e in gas.element_names}}
            t1 = time.perf_counter()
            gas.equilibrate(constraint)
            t2 = time.perf_counter()
        except ProviderRefusal:
            raise
        except Exception as exc:
            return failed(ident, f"Cantera equilibrium failed: {type(exc).__name__}: {exc}")
        missing = sorted(set(species) - set(gas.species_names))
        if missing:
            raise ProviderRefusal(f"requested species {missing} are not in the mechanism")
        scalars = {"temperature": Quantity(gas.T, "K"), "pressure": Quantity(gas.P, "Pa"), "density": Quantity(gas.density, "kg/m^3"),
                   "h_mass": Quantity(gas.enthalpy_mass, "J/kg"), "h_mole": Quantity(gas.enthalpy_mole, "J/kmol"),
                   "mean_molecular_weight": Quantity(gas.mean_molecular_weight, "kg/kmol"),
                   "h_mass_initial": Quantity(initial["h_mass_initial"], "J/kg"), "h_mole_initial": Quantity(initial["h_mole_initial"], "J/kmol"),
                   "thermo_T_min": Quantity(float(gas.min_temp), "K"), "thermo_T_max": Quantity(float(gas.max_temp), "K")}
        if set(gas.element_names) != set(_ELEMENTS):
            raise ProviderRefusal(f"the mechanism's elements {sorted(gas.element_names)} differ from the adapter's reported set {sorted(_ELEMENTS)}")
        for e in gas.element_names:
            scalars[f"elem_Y0_{e}"] = Quantity(float(initial[f"elem_Y0_{e}"]), "dimensionless")
            scalars[f"elem_Y_{e}"] = Quantity(float(gas.elemental_mass_fraction(e)), "dimensionless")
        scalars.update({f"X_{s}": Quantity(float(gas[s].X[0]), "dimensionless") for s in species})
        if not all(math.isfinite(float(q.magnitude)) for q in scalars.values()):
            return failed(ident, "Cantera returned a non-finite equilibrium state")
        return ProviderExecutionRecord(ident, True, "", scalars=scalars,
                                       artifacts={"mechanism.sha256": mechanism.sha256, "request": repr(problem)},
                                       metrics={"setup_s": t1 - t0, "solve_s": t2 - t1, "species": gas.n_species, "reactions": gas.n_reactions})

    def constant_pressure_reactor(self, mechanism: Mechanism, composition: Mapping[str, float], temperature: Quantity,
                                  pressure: Quantity, window: TimeWindow, *, samples: int, rtol: float, atol: float,
                                  species: tuple[str, ...] = ()) -> ProviderExecutionRecord:
        """Adiabatic ideal-gas constant-pressure reactor over the BIG 2 window, sampled at ``samples`` equal steps."""
        if samples < 2 or not (0 < rtol < 1 and 0 < atol < 1):
            raise ProviderRefusal("reactor needs >= 2 samples and explicit rtol/atol in (0, 1)")
        T, P = temperature.to("K").magnitude, pressure.to("Pa").magnitude
        start, end = float(window.start.seconds), float(window.end.seconds)
        outputs = ("temperature",) + tuple(f"X_{s}" for s in species)
        problem = {"mechanism": mechanism.to_dict(), "composition": sorted([k, repr(float(v))] for k, v in composition.items()),
                   "T0_K": repr(T), "P_Pa": repr(P), "reactor": "IdealGasConstPressureReactor(adiabatic)"}
        configuration = {"integrator": "ReactorNet(CVODES)", "rtol": repr(rtol), "atol": repr(atol), "samples": samples}
        ident = self._identity(mechanism, problem, configuration, outputs, window)
        import cantera as ct

        t0 = time.perf_counter()
        try:
            gas = self._solution(mechanism)
            gas.TPX = T, P, self._composition(gas, composition)
            reactor = ct.IdealGasConstPressureReactor(gas)
            net = ct.ReactorNet([reactor])
            net.rtol, net.atol = rtol, atol
            times, temps, xs = [start], [reactor.T], {s: [float(gas[s].X[0])] for s in species}
            for i in range(1, samples):
                t = (end - start) * i / (samples - 1)
                net.advance(t)
                times.append(start + t)
                temps.append(reactor.T)
                for s in species:
                    xs[s].append(float(reactor.thermo[s].X[0]))
        except ProviderRefusal:
            raise
        except Exception as exc:
            return failed(ident, f"Cantera reactor integration failed: {type(exc).__name__}: {exc}")
        series = (QuantitySeries("temperature", "K", tuple(times), tuple(temps)),) + tuple(
            QuantitySeries(f"X_{s}", "dimensionless", tuple(times), tuple(xs[s])) for s in species)
        return ProviderExecutionRecord(ident, True, "", series=series, artifacts={"mechanism.sha256": mechanism.sha256},
                                       metrics={"solve_s": time.perf_counter() - t0, "steps_reported": samples, "species": gas.n_species})
