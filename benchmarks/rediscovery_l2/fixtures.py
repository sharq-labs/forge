"""Public noiseless controls. No final/hidden data or evaluator seeds."""
CASES = ("linear", "quadratic", "ambiguous", "neither")


def build(name):
    if name not in CASES:
        raise ValueError("unknown public development case")
    def split(role, currents):
        voltage = [2*x*x if name == "quadratic" else 2*x + (1 if name == "neither" else 0) for x in currents]
        return {"current": currents, "voltage": voltage, "current_unit": "A", "voltage_unit": "V",
                "sample_ids": [f"{role}-{i}" for i in range(len(currents))],
                "group_ids": [role] * len(currents)}
    calibration = [1.] * 21 if name == "ambiguous" else [0.1 * i for i in range(21)]
    selection = [1.] * 20 if name == "ambiguous" else [0.125 + 0.09 * i for i in range(20)]
    return {"calibration": split("calibration", calibration), "selection": split("selection", selection),
            "resolution_volts": 0.01}
