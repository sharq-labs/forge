"""PUBLIC truth: R=2 ohm; deliberately noiseless software controls, not measurements.

The positive sigma is a declared analysis resolution, not generated measurement
noise. These fixtures cannot measure uncertainty calibration or blindfold ability.
"""
from engcore.mind.repsem.roles import RoleDeclaration, RoleSource, VariableRole as R
from engcore.mind.repsem.v2 import PROBLEM_SCHEMA

CASES = ("informative", "milliamps", "uninformative", "misspecified", "unknown_noise")


def build(case):
    if case not in CASES:
        raise ValueError(f"unknown development case: {case}")
    scale = 1000. if case == "milliamps" else 1.
    current = [0.] + ([0.] * 20 if case == "uninformative" else [0.1 * n for n in range(1, 21)])
    voltage = [2. * i + (1. if case == "misspecified" else 0.) for i in current]
    variables = [RoleDeclaration(name, role, unit, RoleSource.PROBLEM_SPECIFICATION,
                                 "public synthetic development fixture").to_dict()
                 for name, role, unit in (("time", R.CONTROLLED_INPUT, "s"),
                                          ("current", R.CONTROLLED_INPUT, "mA" if scale == 1000 else "A"),
                                          ("voltage", R.MEASUREMENT, "V"),
                                          ("resistance", R.LATENT_PARAMETER, "ohm"))]
    spec = {"schema": PROBLEM_SCHEMA, "clock": "time", "observable": "voltage", "variables": variables,
            "declared_family": {"family_id": "ohmic", "parameter_bounds": {"resistance": [0.1, 10.]}, "constants": {}},
            "requested_parameters": ["resistance"], "constant_units": {}, "condition_units": {},
            "applicability": {"variables": ["current"]},
            "sets": {"calibration": [{"id": "development-calibration", "unit_id": "synthetic-unit",
                       "columns": {"time": list(range(21)), "current": [v * scale for v in current], "voltage": voltage}}]}}
    if case != "unknown_noise":
        spec["measurement_noise"] = {"sigma": 0.01, "independent": True}
    return spec
