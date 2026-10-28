"""PUBLIC noiseless truth, exclusively for development."""
CASES = ("linear", "quadratic", "mixed", "ambiguous", "outside", "constant")


def build(name):
    if name not in CASES:
        raise ValueError("unknown public fixture")
    def target(x):
        if name in ("linear", "ambiguous"):
            return 1 + 2*x
        if name == "quadratic":
            return 1 + 3*x*x
        if name == "mixed":
            return 1 + 2*x + 3*x*x
        if name == "outside":
            return x**4
        return 1.
    def part(role, x):
        return {"current": x, "voltage": [target(v) for v in x], "current_unit": "A", "voltage_unit": "V",
                "sample_ids": [f"{role}-{i}" for i in range(len(x))], "group_ids": [role]*len(x)}
    x = [-1., 1.]*10 if name == "ambiguous" else [-2 + 0.2*i for i in range(21)]
    sx = [-1., 1.]*9 if name == "ambiguous" else [-1.9 + 0.2*i for i in range(20)]
    return {"calibration": part("calibration", x), "selection": part("selection", sx), "resolution_volts": 0.01}
