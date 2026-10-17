"""PyBaMM cell as a BIG 9 multiphysics participant.

The cell is an isothermal PyBaMM model evaluated at the COUPLED temperature it
receives (input port ``temperature``); it returns the window-mean heat
generation (``heat``, W).  Its state between windows is PyBaMM's own solution
(the full model state vector y); a window always restarts from the checkpointed
start solution, so implicit iterations re-solve the same window.  State identity
is the sha256 of y; completeness is DECLARED (basis recorded): PyBaMM continues a
solution from exactly that state vector through ``solver.step``.
"""

from __future__ import annotations

import hashlib
import math
from typing import Callable, Mapping

import numpy as np

from engcore.coupling import ParticipantStateContract, StateCompleteness
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.providers import ProviderExecutionIdentity, ProviderRefusal, require_library_unchanged
from engcore.scientific.multiphysics.receipts import StateVariableValue
from engcore.scientific.multiphysics.state import CheckpointRecord
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

from . import ADAPTER, FADE_MAPPING, SOC_DEFINITION, parameter_set

FIXED_OPTIONS = {"thermal": "isothermal", "calculate heat source for isothermal models": "true"}
BALANCE_KEYS = ("Negative electrode active material volume fraction", "Positive electrode active material volume fraction")
COMPLETENESS_BASIS = ("the PyBaMM Solution (full model state vector y at the window end) is the continuation state; "
                      "solver.step continues from exactly it; the model/parameters are fixed per participant")


def cell_participant(registry, spec, *, parameter_set_name: str, model: str, initial_soc: float, capacity_fade: float,
                     current_at: Callable[[Quantity], Quantity], log: list | None = None, points: int = 11,
                     model_options: Mapping[str, str] | None = None, balance: tuple[float, float] = (1.0, 1.0)) -> CallbackParticipant:
    """``capacity_fade`` is the declared slow state (0.0 = a new cell) mapped exactly as the provider maps it: uniform loss of active material.

    ``model_options`` adds PyBaMM model options (e.g. the heat of mixing) on top of the isothermal heat-source pair, which it
    may not change.  ``balance`` multiplies the negative / positive active-material volume fractions before the fade mapping:
    a declared, identified correction of the parameter set; (1, 1) is the set as shipped.  Both enter the execution identity
    and the initial state identity whenever they differ from their defaults (defaults keep the earlier identities).
    """
    status = registry.require("pybamm")
    require_library_unchanged(status, "pybamm")  # the library that runs is the one discovery bound (BIG 14 M1)
    import pybamm

    require_library_unchanged(status, "pybamm")  # and the module that was just imported is that library (M-3)
    if not (0.0 <= capacity_fade < 0.5):
        raise ProviderRefusal("capacity_fade outside the declared mapping's range [0, 0.5)")
    extra = dict(model_options or {})
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in extra.items()):
        raise ProviderRefusal("model_options must map option names to string values")
    if set(extra) & set(FIXED_OPTIONS):
        raise ProviderRefusal(f"model_options may not change {sorted(set(extra) & set(FIXED_OPTIONS))}: the coupled cell is isothermal by contract")
    balance = tuple(balance)
    if len(balance) != 2 or any(isinstance(f, bool) or not isinstance(f, (int, float)) or not math.isfinite(f) or f <= 0.0 for f in balance):
        raise ProviderRefusal("balance must be two finite, positive active-material factors (negative, positive)")
    balance = (float(balance[0]), float(balance[1]))
    pset, pv = parameter_set(parameter_set_name)
    c_nom = float(pv["Nominal cell capacity [A.h]"])
    for key, factor in zip(BALANCE_KEYS, balance):
        pv.update({key: float(pv[key]) * factor * (1.0 - capacity_fade)})
    pv.update({"Current function [A]": "[input]", "Ambient temperature [K]": "[input]"})
    pv.set_initial_state(initial_soc)
    options = {**FIXED_OPTIONS, **extra}
    declared = {}
    if extra:
        declared["model_options_added"] = dict(sorted(extra.items()))
    if balance != (1.0, 1.0):
        declared["active_material_balance"] = {"negative": repr(balance[0]), "positive": repr(balance[1])}
    sim = pybamm.Simulation(getattr(pybamm.lithium_ion, model)(options=options), parameter_values=pv,
                            solver=pybamm.IDAKLUSolver(rtol=1e-6, atol=1e-8))
    sim.build()
    held: dict = {"solution": None}
    log = log if log is not None else []
    unknown = Uncertainty.unknown("PyBaMM output uncertainty is not quantified")
    contract = ParticipantStateContract(spec.participant_id, ("soc",), ("soc",), StateCompleteness.DECLARED_COMPLETE, COMPLETENESS_BASIS)

    def soc_of(solution) -> float:
        if solution is None:
            return initial_soc
        return initial_soc - float(solution["Discharge capacity [A.h]"].entries[-1]) / (c_nom * (1.0 - capacity_fade))

    # Phase 2 BR10: the build a checkpoint's state was produced by (provider id, version, content digest, adapter)
    build = hashlib.sha256(
        f"{status.capability.provider_id}:{status.version}:{status.digest}:{ADAPTER[0]}:{ADAPTER[1]}".encode()
    ).hexdigest()

    def digest(solution=...) -> str:
        sol = held["solution"] if solution is ... else solution
        if sol is None:
            suffix = f":{sorted(declared.items())!r}" if declared else ""
            return hashlib.sha256(f"initial:{pset.digest}:{initial_soc!r}:{capacity_fade!r}{suffix}".encode()).hexdigest()
        return hashlib.sha256(np.ascontiguousarray(np.asarray(sol.last_state.y, dtype="<f8")).tobytes()).hexdigest()

    def initialize(_instant, _inputs, _uq):
        return InitializationResult({"heat": Quantity(0.1, "W")}, {"heat": unknown},
                                    diagnostics={"classification": "declared_initial_iterate_not_a_result"})

    def advance(request):
        if "temperature" not in request.inputs:
            raise ProviderRefusal("cell needs the coupled temperature; it is never defaulted")
        T = float(request.inputs["temperature"].to("K").magnitude)
        current = current_at(request.start)
        dt = float(request.end.magnitude_in("s") - request.start.magnitude_in("s"))
        inputs = {"Current function [A]": float(current.to("A").magnitude), "Ambient temperature [K]": T}
        problem = {"window_s": [repr(request.start.magnitude_in("s")), repr(request.end.magnitude_in("s"))], "inputs": {k: repr(v) for k, v in inputs.items()},
                   "start_state": digest(), "model": model, "parameter_set": pset.to_dict(), "soc_definition": SOC_DEFINITION,
                   "capacity_fade": repr(float(capacity_fade)), "fade_mapping": FADE_MAPPING, **declared}
        require_library_unchanged(status, "pybamm")  # every window: the module in memory still matches discovery
        ident = ProviderExecutionIdentity.from_content(status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1], problem=problem,
                                                       configuration={"solver": "IDAKLUSolver", "rtol": "1e-6", "atol": "1e-8", "points": points,
                                                                      "model_options": options,
                                                                      "declared_initial_heat_iterate_W": "0.1 (seeds iteration 1 only)"},
                                                       output_request=("heat", "soc"))
        sol = sim.solver.step(held["solution"], sim.built_model, dt, npts=points, inputs=inputs, save=False)
        if float(sol.t[-1] - sol.t[0]) < dt - 1e-6:
            raise ProviderRefusal(f"PyBaMM stopped early in [{request.start}, {request.end}] (event); window refused")
        heat_t = np.asarray(sol["Total heating [W]"].entries, dtype=float)
        t = np.asarray(sol.t, dtype=float)
        heat = float(np.trapezoid(heat_t, t) / (t[-1] - t[0]))
        if not np.isfinite(heat):
            raise ProviderRefusal("non-finite PyBaMM heat")
        held["solution"] = sol
        v_t = np.asarray(sol["Voltage [V]"].entries, dtype=float)
        log.append({"execution_identity": ident.digest, "window": problem["window_s"], "T_K": T, "heat_W": heat, "soc": soc_of(sol),
                    "current_A": float(current.to("A").magnitude), "voltage_V_mean": float(np.trapezoid(v_t, t) / (t[-1] - t[0])),
                    "voltage_V_end": float(v_t[-1]), "voltage_V_min": float(v_t.min()),
                    "series": {"t_s": [float(x) for x in t], "voltage_V": [float(x) for x in v_t], "heat_W": [float(x) for x in heat_t],
                               "discharge_capacity_Ah": [float(x) for x in np.asarray(sol["Discharge capacity [A.h]"].entries, dtype=float)],
                               "soc": [float(initial_soc - x / (c_nom * (1.0 - capacity_fade))) for x in np.asarray(sol["Discharge capacity [A.h]"].entries, dtype=float)]}})
        return AdvanceResult(request.end, {"heat": Quantity(heat, "W")}, {"heat": unknown}, 1, True,
                             diagnostics={"execution_identity": ident.digest, "soc_end": repr(soc_of(sol))})

    def checkpoint(instant):
        return RuntimeCheckpoint(CheckpointRecord(spec.participant_id, instant, digest(), True,
                                                  provider_state_id=f"completeness:declared_complete;build:{build}"),
                                 held["solution"])

    def restore(cp):
        # Phase 2 BR10: only this participant's own state, produced by this build, holding what its record names
        if cp.record.participant_id != spec.participant_id:
            raise ProviderRefusal(f"checkpoint of {cp.record.participant_id!r} cannot restore {spec.participant_id!r}")
        tags = [p.split(":", 1)[1] for p in str(cp.record.provider_state_id or "").split(";") if p.startswith("build:")]
        if tags != [build]:
            raise ProviderRefusal("checkpoint does not name this PyBaMM build (another build, or none recorded); "
                                  "a solver state is not restored across builds")
        if digest(cp.token) != cp.record.state_digest:
            raise ProviderRefusal("checkpoint token does not hold the state its record names (corrupted or substituted)")
        held["solution"] = cp.token

    participant = CallbackParticipant(
        spec, initialize=initialize, advance=advance, checkpoint=checkpoint, restore=restore, state_identity=lambda _t: digest(),
        public_state=lambda _t: (StateVariableValue("soc", Quantity(soc_of(held["solution"]), "dimensionless"),
                                                    Uncertainty.unknown(f"SOC by the declared definition: {SOC_DEFINITION}")),))
    participant.state_contract = contract
    return participant
