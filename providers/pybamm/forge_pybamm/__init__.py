"""PyBaMM battery provider (BIG 11).

Forge ``BatteryProblem`` -> explicit PyBaMM model family + thermal option +
NAMED parameter set (its full content digested; classified as a
provider-bundled literature parameter set, never Forge-sourced data) + Forge
overrides (initial SOC, initial temperature, slow-state mapping) + piecewise-
constant current / ambient segments taken from BIG 2 usage and BIG 3
environment records -> ``Simulation.step`` per segment -> Forge series.

Declared definitions (recorded in every record's artifacts, never implicit):

* SOC: coulomb counting against the nominal capacity scaled by the declared
  slow-state mapping, ``soc = soc0 - Q_discharged / (C_nom * (1 - fade))``;
* slow state ``capacity_fade`` -> uniform loss of active material: both
  electrodes' active-material volume fractions scaled by ``(1 - fade)`` -- a
  declared approximation of aging, not a mechanism PyBaMM infers;
* a segment that PyBaMM terminates early (voltage cut-off) makes the whole
  execution FAILED: the requested operation was infeasible; nothing is padded.

Nothing here is battery validation.
"""

from __future__ import annotations

import hashlib
import inspect
import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from engcore.providers import ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, QuantitySeries, failed
from engcore.scenarios.timeline import TimeWindow
from engcore.scientific.units.quantity import Quantity

ADAPTER = ("forge_pybamm", "0.1")
MODELS = ("SPM", "SPMe", "DFN")
THERMAL = {"isothermal": {}, "lumped": {"thermal": "lumped"}}
PARAMETER_SET_CLASSIFICATION = "provider_bundled_literature_parameter_set_not_forge_sourced_data"
SOC_DEFINITION = "soc = soc0 - Q_discharged / (C_nominal * (1 - capacity_fade)) (declared coulomb-counting definition)"
FADE_MAPPING = ("capacity_fade -> 'Negative/Positive electrode active material volume fraction' x (1 - capacity_fade) "
                "(declared uniform loss-of-active-material approximation)")
OUTPUTS = ("voltage", "current", "soc", "cell_temperature", "heat", "discharge_capacity")


def _value_digest(value: Any) -> str:
    if isinstance(value, (int, float)):
        return repr(float(value))
    if isinstance(value, str):
        return value
    if callable(value):
        try:
            return "fn:" + hashlib.sha256(inspect.getsource(value).encode()).hexdigest()
        except (OSError, TypeError):
            return f"fn-unsourced:{getattr(value, '__qualname__', type(value).__name__)}"
    if isinstance(value, tuple) and len(value) == 2:  # (name, (x, y)) interpolant data
        try:
            arrays = [np.ascontiguousarray(np.asarray(a, dtype="<f8")).tobytes() for a in value[1]]
            return "data:" + hashlib.sha256(b"".join(arrays)).hexdigest()
        except Exception:
            pass
    return f"{type(value).__name__}:{value!r}"


@dataclass(frozen=True)
class ParameterSetIdentity:
    name: str
    digest: str
    entries: int

    def to_dict(self) -> dict:
        return {"name": self.name, "digest": self.digest, "entries": self.entries, "classification": PARAMETER_SET_CLASSIFICATION}


def parameter_set(name: str):
    """(identity, ParameterValues) for a PyBaMM-bundled set chosen EXPLICITLY by name."""
    import pybamm

    if name not in pybamm.parameter_sets.keys():
        raise ProviderRefusal(f"PyBaMM has no parameter set {name!r}")
    pv = pybamm.ParameterValues(name)
    items = sorted((k, _value_digest(pv[k])) for k in pv.keys())
    return ParameterSetIdentity(name, hashlib.sha256(repr(items).encode()).hexdigest(), len(items)), pv


@dataclass(frozen=True)
class Segment:
    """Piecewise-constant operating segment (current > 0 discharges)."""

    window: TimeWindow
    current: Quantity
    ambient: Quantity
    provenance: tuple[tuple[str, str], ...] = ()  # e.g. (("ambient", env value digest), ("current", usage entry digest))

    def to_dict(self) -> dict:
        return {"window": self.window.to_dict(), "current_A": repr(float(self.current.to("A").magnitude)),
                "ambient_K": repr(float(self.ambient.to("K").magnitude)), "provenance": [list(p) for p in self.provenance]}


@dataclass(frozen=True)
class BatteryProblem:
    model: str
    thermal: str
    parameter_set: str
    initial_soc: float
    initial_temperature: Quantity
    capacity_fade: float
    segments: tuple[Segment, ...]
    rtol: float = 1e-6
    atol: float = 1e-8
    points_per_segment: int = 13

    def __post_init__(self) -> None:
        if self.model not in MODELS or self.thermal not in THERMAL:
            raise ProviderRefusal(f"unsupported model/thermal option {self.model}/{self.thermal}")
        if not (0 < self.initial_soc < 1):
            raise ProviderRefusal("initial SOC must lie strictly inside (0, 1)")
        if not (0 <= self.capacity_fade < 0.5):
            raise ProviderRefusal("capacity_fade outside the declared mapping's range [0, 0.5)")
        segs = tuple(self.segments)
        if not segs or any(a.window.end != b.window.start for a, b in zip(segs, segs[1:])):
            raise ProviderRefusal("segments must be contiguous and non-empty (no gap is treated as rest)")
        if not (0 < self.rtol < 1e-2 and 0 < self.atol < 1e-2):
            raise ProviderRefusal("explicit solver tolerances are required")

    @property
    def window(self) -> TimeWindow:
        return TimeWindow(self.segments[0].window.start, self.segments[-1].window.end)

    def to_dict(self) -> dict:
        return {"model": self.model, "thermal": self.thermal, "parameter_set": self.parameter_set,
                "initial_soc": repr(float(self.initial_soc)), "initial_temperature_K": repr(float(self.initial_temperature.to("K").magnitude)),
                "capacity_fade": repr(float(self.capacity_fade)), "segments": [s.to_dict() for s in self.segments],
                "solver": {"solver": "IDAKLUSolver", "rtol": repr(self.rtol), "atol": repr(self.atol)},
                "points_per_segment": self.points_per_segment}


class PyBaMMProvider:
    def __init__(self, registry) -> None:
        self.status = registry.require("pybamm")

    def run(self, problem: BatteryProblem) -> ProviderExecutionRecord:
        import pybamm

        t0 = time.perf_counter()
        pset, pv = parameter_set(problem.parameter_set)
        c_nominal = float(pv["Nominal cell capacity [A.h]"])
        for key in ("Negative electrode active material volume fraction", "Positive electrode active material volume fraction"):
            pv.update({key: float(pv[key]) * (1.0 - problem.capacity_fade)})
        pv.update({"Current function [A]": "[input]", "Ambient temperature [K]": "[input]",
                   "Initial temperature [K]": float(problem.initial_temperature.to("K").magnitude)})
        configuration = {"parameter_set": pset.to_dict(), "soc_definition": SOC_DEFINITION, "fade_mapping": FADE_MAPPING,
                         "model_options": THERMAL[problem.thermal], "pybamm": self.status.version}
        identity = ProviderExecutionIdentity.from_content(
            self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1], problem=problem.to_dict(),
            configuration=configuration, output_request=OUTPUTS if problem.thermal == "lumped" else tuple(o for o in OUTPUTS if o != "cell_temperature"),
            window=problem.window)
        try:
            pv.set_initial_state(problem.initial_soc)
            model = getattr(pybamm.lithium_ion, problem.model)(options=THERMAL[problem.thermal])
            sim = pybamm.Simulation(model, parameter_values=pv, solver=pybamm.IDAKLUSolver(rtol=problem.rtol, atol=problem.atol))
            t1 = time.perf_counter()
            start = float(problem.window.start.seconds)
            sol = None
            for seg in problem.segments:
                dt = float(seg.window.end.seconds - seg.window.start.seconds)
                inputs = {"Current function [A]": float(seg.current.to("A").magnitude), "Ambient temperature [K]": float(seg.ambient.to("K").magnitude)}
                sol = sim.step(dt, npts=problem.points_per_segment, inputs=inputs, save=True)
                reached = float(sol.t[-1])
                if reached < float(seg.window.end.seconds) - start - 1e-6:
                    return failed(identity, f"PyBaMM terminated at t={reached:.1f} s before the segment end "
                                            f"{float(seg.window.end.seconds) - start:.1f} s (event, e.g. voltage cut-off); "
                                            "the requested operation is infeasible for this cell state",
                                  artifacts={"configuration": repr(configuration)})
            t2 = time.perf_counter()
            times = tuple(start + float(x) for x in sol.t)
            q = sol["Discharge capacity [A.h]"].entries
            values = {"voltage": ("V", sol["Voltage [V]"].entries), "current": ("A", sol["Current [A]"].entries),
                      "soc": ("dimensionless", problem.initial_soc - q / (c_nominal * (1.0 - problem.capacity_fade))),
                      "heat": ("W", sol["Total heating [W]"].entries), "discharge_capacity": ("A*h", q)}
            if problem.thermal == "lumped":
                values["cell_temperature"] = ("K", sol["Volume-averaged cell temperature [K]"].entries)
        except ProviderRefusal:
            raise
        except Exception as exc:
            return failed(identity, f"PyBaMM execution failed: {type(exc).__name__}: {exc}")
        series = tuple(QuantitySeries(k, u, times, tuple(float(x) for x in np.asarray(v, dtype=float))) for k, (u, v) in values.items())
        final = {k: Quantity(float(np.asarray(v)[-1]), u) for k, (u, v) in values.items() if k in ("soc", "voltage", "discharge_capacity")}
        if not all(math.isfinite(float(x.magnitude)) for x in final.values()):
            return failed(identity, "PyBaMM returned non-finite outputs")
        state_digest = hashlib.sha256(np.ascontiguousarray(np.asarray(sol.last_state.y, dtype="<f8")).tobytes()).hexdigest()
        return ProviderExecutionRecord(identity, True, "", scalars={f"final_{k}": v for k, v in final.items()}, series=series,
                                       artifacts={"configuration": repr(configuration), "parameter_set_digest": pset.digest,
                                                  "final_state_vector_sha256": state_digest},
                                       metrics={"setup_s": t1 - t0, "solve_s": t2 - t1, "states": int(np.asarray(sol.last_state.y).size),
                                                "points": len(times)})


def segments_from_records(environment, ambient_channel: str, current_history: str, window: TimeWindow, step_s: int) -> tuple[Segment, ...]:
    """Segments over ``window`` read from EXACT BIG 3 / BIG 2 records.

    Ambient temperature: the BIG 3 channel value at each segment start (must be
    KNOWN).  Current: the BIG 2 USAGE history value at each segment start.  Each
    segment carries the digests of the records it was read from.  An UNKNOWN
    value refuses the problem -- never a default.
    """
    from engcore.scenarios.timeline import TimePoint, canonical_digest

    basis = window.basis_id
    start, end = window.start.seconds, window.end.seconds
    if (end - start) % step_s:
        raise ProviderRefusal("the window is not a whole number of segments")
    history = environment.timeline.history(current_history)
    channel = environment.channel(ambient_channel)
    watched = [history]
    if channel.history_id:
        watched.append(environment.timeline.history(channel.history_id))
    else:  # a SAMPLED channel: a held segment-start value must not hide samples or a ramp inside a segment
        inside = [float(s.at.seconds) for s in channel.samples if start < s.at.seconds < end and (s.at.seconds - start) % step_s]
        if inside or channel.interpolation.method.value not in ("step_hold", "none"):
            raise ProviderRefusal(f"sampled channel {ambient_channel!r} is not piecewise constant on the {step_s} s segments "
                                  f"(samples inside segments at {inside[:3]} s, interpolation {channel.interpolation.method.value!r})")
    for h in watched:
        for e in h.entries:
            for edge in (e.window.start.seconds, e.window.end.seconds):
                if start < edge < end and (edge - start) % step_s:
                    raise ProviderRefusal(f"record {h.history_id!r} changes at {float(edge):g} s inside a {step_s} s segment; "
                                          "segment starts would misrepresent it (split the segments at record changes)")
    segments = []
    t = start
    while t < end:
        at = TimePoint(basis, t)
        amb = environment.channel_value(ambient_channel, at)
        cur = history.value_at(at)
        if amb.status.value != "known" or cur.status.value != "known":
            raise ProviderRefusal(f"ambient or current UNKNOWN at {float(t):g} s; nothing is assumed")
        segments.append(Segment(TimeWindow(at, TimePoint(basis, t + step_s)), cur.value.value, amb.value.value,
                                (("ambient", canonical_digest(amb.to_dict())), ("current", canonical_digest(cur.value.to_dict())),
                                 ("ambient_source", amb.source_id), ("ambient_classification", amb.source_classification))))
        t += step_s
    return tuple(segments)
