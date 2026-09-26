"""OpenModelica provider (BIG 11, second wave), process-based, bounded.

One model family: a lumped thermal capacitance with a heat input and a
convective loss, ``C dT/dt = P - hA (T - T_amb)``.  The ``.mo`` model and the
``.mos`` script are generated from the Forge problem and bound by content; omc
compiles and simulates it in a fresh workspace.  Success requires omc's own
"simulation finished successfully" message, a result file written by THIS run
and a final time equal to the requested window end.  Nothing here is validation.
"""

from __future__ import annotations

import csv
import io
import os
import time
from dataclasses import dataclass

from engcore.providers import (
    GeneratedFile, ProcessInvocation, ProcessWorkspace, ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, QuantitySeries,
    failed, minimal_environment,
)
from engcore.scenarios.timeline import TimeWindow
from engcore.scientific.units.quantity import Quantity

ADAPTER = ("forge_openmodelica", "0.1")


@dataclass(frozen=True)
class LumpedThermalProblem:
    heat_capacity: Quantity
    conductance: Quantity
    heat_input: Quantity
    ambient: Quantity
    initial_temperature: Quantity
    window: TimeWindow
    intervals: int
    tolerance: float

    def __post_init__(self) -> None:
        if not (self.heat_capacity.to("J/K").magnitude > 0 and self.conductance.to("W/K").magnitude > 0):
            raise ProviderRefusal("heat capacity and conductance must be positive")
        if not (1 <= self.intervals <= 100000 and 0 < self.tolerance < 1e-2):
            raise ProviderRefusal("explicit output intervals and solver tolerance are required")

    def to_dict(self) -> dict:
        f = lambda q, u: repr(float(q.to(u).magnitude))  # noqa: E731
        return {"C_J_K": f(self.heat_capacity, "J/K"), "hA_W_K": f(self.conductance, "W/K"), "P_W": f(self.heat_input, "W"),
                "Ta_K": f(self.ambient, "K"), "T0_K": f(self.initial_temperature, "K"), "window": self.window.to_dict(),
                "intervals": self.intervals, "tolerance": repr(self.tolerance)}


def generate(problem: LumpedThermalProblem, tag: str) -> dict[str, str]:
    d = problem.to_dict()
    span = float(problem.window.end.seconds - problem.window.start.seconds)
    model = (f"// Forge execution {tag}\nmodel ForgeLumpedThermal\n"
             f"  parameter Real C = {d['C_J_K']};\n  parameter Real hA = {d['hA_W_K']};\n  parameter Real P = {d['P_W']};\n"
             f"  parameter Real Ta = {d['Ta_K']};\n  Real T(start = {d['T0_K']}, fixed = true);\n"
             "equation\n  C * der(T) = P - hA * (T - Ta);\nend ForgeLumpedThermal;\n")
    script = ('loadFile("model.mo"); getErrorString();\n'
              f'simulate(ForgeLumpedThermal, startTime=0, stopTime={span!r}, numberOfIntervals={problem.intervals}, '
              f'tolerance={problem.tolerance!r}, outputFormat="csv"); getErrorString();\n')
    return {"model.mo": model, "run.mos": script}


class OpenModelicaProvider:
    def __init__(self, registry, *, timeout_s: float = 900.0, workspace_root: str | None = None) -> None:
        self.status = registry.require("openmodelica")
        self.timeout_s, self.workspace_root = timeout_s, workspace_root

    def simulate(self, problem: LumpedThermalProblem) -> ProviderExecutionRecord:
        configuration = {"model_family": "lumped thermal capacitance", "solver": "omc default (dassl)", "output": "csv"}
        base = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1], problem=problem.to_dict(),
                                                      configuration=configuration, output_request=("temperature",), window=problem.window)
        files = generate(problem, base.digest)
        identity = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1], problem=problem.to_dict(),
                                                          configuration=configuration, inputs=files, output_request=("temperature",), window=problem.window)
        prefix = os.path.dirname(os.path.dirname(self.status.location))
        inv = ProcessInvocation(self.status.location, self.status.executable_digest, self.status.version, ("run.mos",),
                                tuple(GeneratedFile(k, v.encode()) for k, v in sorted(files.items())),
                                minimal_environment(self.status.location, {"PATH": f"{prefix}/bin:/usr/bin:/bin", "OPENMODELICAHOME": prefix}),
                                self.timeout_s, ("ForgeLumpedThermal_res.csv",))
        ws = ProcessWorkspace(self.workspace_root)
        t0 = time.perf_counter()
        try:
            rec = ws.run(inv)
            t1 = time.perf_counter()
            if not rec.completed or "The simulation finished successfully" not in rec.stdout_tail:
                return failed(identity, f"omc did not report a successful simulation (exit {rec.exit_code}): {rec.stdout_tail[-500:]}",
                              process_digest=rec.digest, artifacts=files)
            rows = list(csv.DictReader(io.StringIO(ws.read_output("ForgeLumpedThermal_res.csv").decode())))
        finally:
            ws.cleanup()
        start = float(problem.window.start.seconds)
        span = float(problem.window.end.seconds) - start
        times = [float(r["time"]) for r in rows]
        # OpenModelica repeats the final instant (event/terminal output); keep the first occurrence of each time
        keep = [i for i, t in enumerate(times) if i == 0 or t > times[i - 1]]
        if not keep or abs(times[keep[-1]] - span) > 1e-9 * max(1.0, span):
            return failed(identity, "OpenModelica result does not reach the requested window end", process_digest=rec.digest)
        series = QuantitySeries("temperature", "K", tuple(start + times[i] for i in keep), tuple(float(rows[i]["T"]) for i in keep))
        return ProviderExecutionRecord(identity, True, "", series=(series,), artifacts=files, process_digest=rec.digest,
                                       metrics={"process_s": t1 - t0, "points": len(keep)})
