"""One preCICE participant process: runs a Forge-declared participant model through preCICE.

Models are selected by the contract's ``participant_setup[<name>]["model"]``:

* ``lumped_thermal``  -- T = T_amb + P * R_th   (declared lumped thermal resistance)
* ``heater_circuit``  -- P = circuit(T) via the BIG 6 numerical layer (HeaterCircuit)

The process prints one JSON line: the last values it wrote and the number of
coupling iterations in each time window (counted from checkpoint reloads).
"""

from __future__ import annotations

import json
import sys

import numpy as np


# Declared (reads_unit, writes_unit) of each participant model.  The contract's
# exchange units must match exactly; nothing is converted or assumed silently.
MODEL_UNITS = {"lumped_thermal": ("W", "K"), "heater_circuit": ("K", "W")}


def build_model(setup, reads_unit: str, writes_unit: str):
    """Return ``received -> written`` for a declared participant model (plain floats in the declared units)."""
    kind = setup["model"]
    if kind not in MODEL_UNITS:
        raise ValueError(f"unknown participant model {kind!r}")
    if MODEL_UNITS[kind] != (reads_unit, writes_unit):
        raise ValueError(f"{kind} reads/writes {MODEL_UNITS[kind]}, contract declares {(reads_unit, writes_unit)}; refused")
    if kind == "lumped_thermal":
        t_amb, r_th = setup["ambient_K"], setup["thermal_resistance_K_per_W"]
        return lambda received: t_amb + received * r_th
    from engcore.domains.electrical.heater_circuit import HeaterCircuit
    from engcore.scientific.units.quantity import Quantity
    c = HeaterCircuit(Quantity(setup["V"], "V"), Quantity(setup["Rs_ohm"], "ohm"), Quantity(setup["R0_ohm"], "ohm"),
                      Quantity(setup["T0_K"], "K"), Quantity(setup["alpha_per_K"], "1/K"))

    def model(received):
        record, power = c.solve(Quantity(received, "K"))
        if power is None:
            raise RuntimeError(f"electrical participant failed: {record.reason}")
        return power.to("W").magnitude
    return model


def main(spec_json: str) -> None:
    import precice

    spec = json.loads(spec_json)
    contract = spec["contract"]
    me = spec["participant"]
    setup = contract["participant_setup"][me]
    writes = next(x for x in contract["exchanges"] if x["writer"] == me)
    reads = next(x for x in contract["exchanges"] if x["writer"] != me)
    mesh_name = f"{me}Mesh"

    model = build_model(setup, reads["unit"], writes["unit"])
    participant = precice.Participant(me, spec["config"], 0, 1)
    ids = participant.set_mesh_vertices(mesh_name, np.array([[0.0, 0.0]]))
    initial_written = float(setup["initial_written"])
    if participant.requires_initial_data():
        participant.write_data(mesh_name, writes["data_name"], ids, np.array([initial_written]))
    participant.initialize()
    iterations, current, last_written = [], 0, initial_written
    while participant.is_coupling_ongoing():
        if participant.requires_writing_checkpoint():
            current = 0
        dt = participant.get_max_time_step_size()
        received = float(participant.read_data(mesh_name, reads["data_name"], ids, dt)[0])
        last_written = float(model(received))
        participant.write_data(mesh_name, writes["data_name"], ids, np.array([last_written]))
        participant.advance(dt)
        current += 1
        if participant.requires_reading_checkpoint():
            continue
        if participant.is_time_window_complete():
            iterations.append(current)
    participant.finalize()
    print(json.dumps({"participant": me, "final_written": {writes["quantity"]: last_written}, "iterations_per_window": iterations}))


if __name__ == "__main__":
    main(sys.argv[1])
