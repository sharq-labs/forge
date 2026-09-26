"""PyBaMM cell as a BIG 10 FastSystem: one resolved operating period per representative window.

The execution reads ambient temperature (BIG 3 channel) and cell current (BIG 2
usage history) hour by hour from the exact records of the requested window,
starts from the requested FAST state (``soc``) and applies the SLOW state
(``capacity_fade``) through the declared loss-of-active-material mapping.
Outputs are hourly means of the dense PyBaMM solution (so they preserve
integral / mean / dwell / distribution / order at 1 h resolution, NOT extrema).

Declared assumption (recorded in the identity): the cell temperature at the
start of every resolved window equals the ambient at that instant.
"""

from __future__ import annotations

import hashlib
from fractions import Fraction

import numpy as np

from engcore.coupling import ParticipantStateContract, StateCompleteness
from engcore.multiscale import FastExecutionResult, FastSystem, FastSystemIdentity, OutputSample, OutputSeries
from engcore.multiscale.fast import slow_state_digest
from engcore.providers import ProviderRefusal
from engcore.scenarios.lifecycle import HistoryFeature
from engcore.scenarios.timeline import TimePoint, TimeWindow
from engcore.scientific.multiphysics.receipts import StateVariableValue
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

from . import FADE_MAPPING, SOC_DEFINITION, BatteryProblem, PyBaMMProvider, parameter_set, segments_from_records

FEATURES = (HistoryFeature.INTEGRAL, HistoryFeature.MEAN, HistoryFeature.DWELL, HistoryFeature.DISTRIBUTION, HistoryFeature.ORDER)
OUTPUTS = (("abs_current", "A"), ("cell_temperature", "K"), ("voltage", "V"))


class BatteryFastSystem(FastSystem):
    def __init__(self, registry, environment, *, ambient_channel: str, current_history: str, parameter_set_name: str,
                 model: str, segment_s: int) -> None:
        self.provider = PyBaMMProvider(registry)
        self.environment, self.timeline = environment, environment.timeline
        self.ambient_channel, self.current_history = ambient_channel, current_history
        self.pset, _ = parameter_set(parameter_set_name)
        self.model, self.segment_s = model, segment_s
        version = self.provider.status.version
        contract = ParticipantStateContract(
            "cell", ("capacity_fade", "soc"), ("soc",), StateCompleteness.DECLARED_COMPLETE,
            "each execution builds a fresh PyBaMM simulation from (soc, capacity_fade, window records); the solution vector is "
            "not carried between executions -- the declared initial state of a window is (soc, T = ambient at window start)",
            reset_state=("cell_temperature", "particle_concentration_profiles"))
        self.identity = FastSystemIdentity(
            "pybamm-cell-period", "1", hashlib.sha256(b"single participant: pybamm cell (lumped thermal)").hexdigest(),
            {"segments": f"{segment_s} s piecewise-constant current and ambient from the window's BIG 2/BIG 3 records"},
            (("pybamm", version),),
            {"model": model, "thermal": "lumped", "parameter_set": self.pset.to_dict(), "soc_definition": SOC_DEFINITION,
             "fade_mapping": FADE_MAPPING, "initial_temperature": "equals the ambient at the window start (declared assumption)",
             "outputs": "hourly means of the dense solution"},
            (contract,), (), OUTPUTS, field_mapping=False, field_mapping_basis="0-D cell; no spatial field is transferred",
            pure=True, purity_basis="a fresh PyBaMM simulation per execution, fully determined by the request",
            participants=("cell",),
            output_semantics=tuple((q, tuple(f.value for f in FEATURES), f"{segment_s}/1") for q, _ in OUTPUTS),
            slow_state_use=(("cell", "capacity_fade", "bound", FADE_MAPPING),),
            time_inputs_via_request=True,
            time_inputs_basis="current and ambient are read hour by hour from the request window's BIG 2/BIG 3 records")
        self.executions = 0

    def execute(self, request) -> FastExecutionResult:
        self.executions += 1
        soc0 = float(request.fast_state["cell"]["soc"].value.magnitude_in("dimensionless"))
        fade = float(request.slow_state["cell"]["capacity_fade"].value.magnitude_in("dimensionless"))
        segs = segments_from_records(self.environment, self.ambient_channel, self.current_history, request.window, self.segment_s)
        rec = self.provider.run(BatteryProblem(self.model, "lumped", self.pset.name, soc0, segs[0].ambient, fade, segs))
        if not rec.succeeded:
            raise ProviderRefusal(f"PyBaMM execution failed: {rec.reason}")
        t = np.asarray(rec.series_for("voltage").times_s)
        dense = {"abs_current": np.abs(np.asarray(rec.series_for("current").values)),
                 "cell_temperature": np.asarray(rec.series_for("cell_temperature").values),
                 "voltage": np.asarray(rec.series_for("voltage").values)}
        series = []
        for q, unit in OUTPUTS:
            samples = []
            for s in segs:
                a, b = float(s.window.start.seconds), float(s.window.end.seconds)
                m = (t >= a - 1e-9) & (t <= b + 1e-9)
                tt, vv = t[m], dense[q][m]
                if tt.size < 2 or tt[0] > a + 1e-6 or tt[-1] < b - 1e-6:
                    raise ProviderRefusal(f"PyBaMM output does not cover [{a}, {b}] s for {q}")
                samples.append(OutputSample(s.window, Quantity(float(np.trapezoid(vv, tt) / (tt[-1] - tt[0])), unit)))
            series.append(OutputSeries(q, unit, tuple(samples), rec.digest, f"means over each {self.segment_s} s segment",
                                       frozenset(FEATURES)))
        soc_end = float(rec.scalars["final_soc"].magnitude)
        end_state = {"cell": {"soc": StateVariableValue("soc", Quantity(soc_end, "dimensionless"),
                                                        Uncertainty.unknown(f"declared definition: {SOC_DEFINITION}"))}}
        return FastExecutionResult(
            request.identity, (rec.identity.digest,), (rec.digest,), tuple(series), end_state, (), (), len(segs), len(segs),
            ("completed",) * len(segs), self.identity.providers, consumed_environment_digest=self.environment.digest,
            consumed_timeline_digest=self.timeline.digest, consumed_slow_state_digest=slow_state_digest(request.slow_state),
            diagnostics={"pybamm_solve_s": rec.metrics.get("solve_s")})
