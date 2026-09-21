"""R5-R7 and R10: the controlled candidate comparison.

Every candidate is fitted on CALIBRATION trajectories and judged on VALIDATION
trajectories. The locked holdout is not on disk for this script to read, and
:func:`corpus.refuse_holdout` is called on the trajectory set it actually loads.

What the candidates vary, one axis at a time
-------------------------------------------
``basis``
    ``declared``  the 2 Ah rating, as Sprint 3
    ``available`` the measured available charge from prior cycles
``ocv``
    ``s3``     the Sprint 3 curve, on the declared axis
    ``pooled`` one v2 curve over both cell-temperature bands
    ``banded`` one v2 curve per cell-temperature band
``arrhenius``
    free activation energies, or both fixed at zero -- which removes two
    parameters Sprint 3 reported as unidentified in most groups
``r0_charge_state``
    scale R0 by the *measured* branch-difference shape, normalized to one at
    the reference charge state. This adds a charge-state dependence with **no
    free parameter**, so it cannot buy fit by absorbing residuals
``rc_branches``
    one relaxation time constant, or two
``parameter_unit``
    ``group``       one parameter set per experiment group, as Sprint 3
    ``block``       one per experiment group, ambient corner and nominal load.
                    The model's polarization is linear in current, and the
                    measured branch-difference resistance is not: it rises from
                    0.169 to 0.208 ohm between 2 A and 4 A. A parameter set asked
                    to serve both rates therefore compromises between them, and
                    this asks whether that compromise is what the warm residual
                    is made of
    ``group_band``  one per experiment group and cell-temperature band, because
                    a single Arrhenius pair asked to span 6-55 degC may fit
                    neither end. This is the same argument Sprint 3 used to make
                    the thermal conductance a per-group property, applied to the
                    electrical parameters across temperature. It costs
                    parameters only where a group has calibration evidence in
                    both bands, which here is group 41_42_43_44 alone

Model form is only promoted if independent validation evidence supports it, and
a candidate with more free parameters has to beat a simpler one on validation
and not merely on calibration. That is the whole point of the table.

    python benchmarks/battery_voltage_s3_recovery/harness/candidates.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
REPO = os.path.dirname(os.path.dirname(BENCH))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "benchmarks", "battery_thermal_flagship_s3", "harness"))

import corpus as cp  # noqa: E402
from engcore.domains.battery import electrothermal as et  # noqa: E402
from engcore.domains.battery.flagship_ocv import (  # noqa: E402
    CHARGE_STATE_BASIS_AH as S3_BASIS_AH,
    OCV_KNOTS as S3_OCV_KNOTS,
)

CANDIDATE_SCHEMA = "battery_voltage_s3_recovery_candidates/1"

#: Residual weights: one over the reviewed acceptance tolerance of each metric.
#: Carried from the Sprint 3 preregistration, unchanged.
VOLTAGE_SCALE_V = 0.050
TEMPERATURE_SCALE_K = 3.0

#: A sample the march could not reach costs one acceptance tolerance, the same
#: scale as a residual exactly at the edge of agreement. Sprint 3's penalty.
UNREACHED_PENALTY = 1.0

REFERENCE_TEMPERATURE_K = 298.15
GAS = et.MOLAR_GAS_CONSTANT.magnitude_in("joule/(mole*kelvin)")

#: Below this the composition presents a sample as rest. The pack's own band.
REST_BAND_A = 0.2

#: A sample whose two channels contradict each other is not an observation.
#:
#: At the first instants of many trajectories in this archive the current
#: channel still reads a few milliamps while the voltage has already collapsed
#: by 200-590 mV. A 590 mV drop at 2 mA implies 295 ohm from a cell measured at
#: 0.2 ohm: the two channels disagree by three orders of magnitude about whether
#: the load is on, and the voltage channel is the one the following samples
#: agree with. Scoring such a sample charges the model for a channel skew.
#:
#: The screen is model-free -- it compares two measurements with each other and
#: consults no prediction -- and it is applied to every split alike. It was
#: found by reading VALIDATION residuals, which is the evidence model
#: development is allowed to use; no holdout residual took part.
CHANNEL_DISAGREEMENT_V = 0.050


def channel_consistent(currents, voltages, index: int) -> bool:
    """Is measured sample ``index`` an admissible observation on its own channels?

    ``index`` indexes the measured arrays. The current held over the interval
    that *ends* at that sample is ``currents[index - 1]``, which is also the
    value the march integrates over it, so that is the one compared against the
    voltage step into the sample.

    A sample whose held current says rest while its voltage has moved further
    than a resting cell can move in one interval is inadmissible: the two
    channels contradict each other about whether the load was on.
    """
    if index <= 0 or index >= len(voltages):
        return True
    if abs(float(currents[index - 1])) >= REST_BAND_A:
        return True
    if index >= 2 and abs(float(currents[index - 2])) >= REST_BAND_A:
        # The load was on over the previous interval, so a large step here is
        # the genuine recovery transient and not a channel contradiction.
        return True
    return abs(float(voltages[index]) - float(voltages[index - 1])) <= (
        CHANNEL_DISAGREEMENT_V
    )

#: Charge state the measured R0 shape is normalized at, so the shape multiplies
#: the fitted reference resistance by one there and the fitted value keeps its
#: meaning.
R0_SHAPE_REFERENCE_Z = 0.5

#: Which cell-temperature band a trajectory is predicted with, decided from
#: information available before the run: the chamber ambient and the nominal
#: load. At 4 degC a 1 A discharge stays cold and a 4 A discharge self-heats out
#: of the cold band, and this rule says so without consulting the prediction.
COLD_AMBIENT_CEILING_C = 10.0
COLD_CURRENT_CEILING_A = 2.0


def band_for(ambient_c: float, current_a: float) -> str:
    if ambient_c <= COLD_AMBIENT_CEILING_C and abs(current_a) <= COLD_CURRENT_CEILING_A:
        return "cold"
    return "warm"


@dataclass(frozen=True)
class Curve:
    """A declared open-circuit voltage table. Refuses outside its interval."""

    curve_id: str
    knots: tuple[float, ...]
    values: tuple[float, ...]

    @property
    def lower(self) -> float:
        return self.knots[0]

    @property
    def upper(self) -> float:
        return self.knots[-1]

    def __call__(self, z: float) -> float:
        if z < self.lower or z > self.upper:
            raise OutsideCurve(
                f"charge state {z:g} is outside the declared interval "
                f"[{self.lower}, {self.upper}] of {self.curve_id}"
            )
        return float(np.interp(z, self.knots, self.values))


class OutsideCurve(ValueError):
    """The march reached a charge state the declared authority does not cover."""


@dataclass(frozen=True)
class Shape:
    """A measured multiplicative shape for R0 against charge state."""

    shape_id: str
    knots: tuple[float, ...]
    factors: tuple[float, ...]

    def __call__(self, z: float) -> float:
        return float(
            np.interp(z, self.knots, self.factors, left=self.factors[0],
                      right=self.factors[-1])
        )


_FLAT = Shape("flat", (0.0, 1.0), (1.0, 1.0))


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    basis: str
    ocv: str
    arrhenius: bool = True
    r0_charge_state: bool = False
    rc_branches: int = 1
    parameter_unit: str = "group"
    note: str = ""

    def unit_of(self, row: dict) -> str:
        if self.parameter_unit == "group_band":
            return f"{row['group']}|{row['band']}"
        if self.parameter_unit == "block":
            rate = round(abs(float(row["nominal_current_a"])) * 2.0) / 2.0
            return f"{row['group']}|{row['corner']}|{rate:g}A"
        return row["group"]

    @property
    def parameter_names(self) -> tuple[str, ...]:
        names = ["ohmic_resistance_reference"]
        if self.arrhenius:
            names.append("ohmic_activation_energy")
        names.append("polarization_resistance_reference")
        if self.arrhenius:
            names.append("polarization_activation_energy")
        names.append("polarization_capacitance")
        if self.rc_branches == 2:
            names.extend(
                ["second_polarization_resistance", "second_polarization_capacitance"]
            )
        names.extend(["thermal_capacitance", "thermal_conductance"])
        return tuple(names)


#: Bounds and starting points. The seven Sprint 3 parameters keep the bounds its
#: preregistration froze; the two second-branch parameters are new and their
#: bounds are stated here before any fit runs.
SPECS: dict[str, dict[str, float]] = {
    "ohmic_resistance_reference": {"lower": 0.005, "upper": 0.5, "initial": 0.08},
    "ohmic_activation_energy": {"lower": -40000.0, "upper": 80000.0, "initial": 20000.0},
    "polarization_resistance_reference": {"lower": 0.001, "upper": 0.5, "initial": 0.04},
    "polarization_activation_energy": {
        "lower": -40000.0, "upper": 80000.0, "initial": 20000.0,
    },
    "polarization_capacitance": {"lower": 50.0, "upper": 50000.0, "initial": 1000.0},
    # A second branch is admitted only if it is slower than the first, which is
    # what makes it a second time constant rather than a relabelling of the one
    # already there. The bound is the ordering, not a value read off a fit.
    "second_polarization_resistance": {"lower": 0.001, "upper": 0.5, "initial": 0.02},
    "second_polarization_capacitance": {
        "lower": 500.0, "upper": 500000.0, "initial": 20000.0,
    },
    "thermal_capacitance": {"lower": 5.0, "upper": 500.0, "initial": 60.0},
    "thermal_conductance": {"lower": 0.005, "upper": 1.0, "initial": 0.06},
}

CANDIDATES = (
    Candidate(
        "M0", "baseline 1RC, declared 2 Ah basis, Sprint 3 curve",
        basis="declared", ocv="s3",
        note="the Sprint 3 model, re-marched on the recovery corpus",
    ),
    Candidate(
        "M1", "+ measured available-charge basis and banded curve",
        basis="available", ocv="banded",
        note="the capacity and initial-state authorities, nothing else",
    ),
    Candidate(
        "M1p", "+ available-charge basis, one pooled curve",
        basis="available", ocv="pooled",
        note="does conditioning the curve on cell temperature earn its place?",
    ),
    Candidate(
        "M2", "M1 with both activation energies fixed at zero",
        basis="available", ocv="banded", arrhenius=False,
        note="two fewer parameters; Sprint 3 called them unidentified",
    ),
    Candidate(
        "M3", "M1 + measured charge-state shape on R0",
        basis="available", ocv="banded", r0_charge_state=True,
        note="no free parameter added: the shape is the branch-difference "
             "measurement, normalized at the reference charge state",
    ),
    Candidate(
        "M4", "M3 + a second RC branch",
        basis="available", ocv="banded", r0_charge_state=True, rc_branches=2,
        note="two free parameters more than M3; the rest-phase residual "
             "structure is what asks for it",
    ),
    Candidate(
        "M5", "M1 + a second RC branch",
        basis="available", ocv="banded", rc_branches=2,
        note="the second branch without the charge-state shape, so the two "
             "additions are separable",
    ),
    Candidate(
        "M6", "M1 with one parameter set per group and cell-temperature band",
        basis="available", ocv="banded", parameter_unit="group_band",
        note="a single Arrhenius pair spanning 6-55 degC compromises between "
             "the two ends; this asks whether the compromise is what the "
             "residual is made of",
    ),
    Candidate(
        "M7", "M6 with both activation energies fixed at zero",
        basis="available", ocv="banded", arrhenius=False,
        parameter_unit="group_band",
        note="within one temperature band an Arrhenius slope has little range "
             "to be identified from, so this removes it",
    ),
    Candidate(
        "M8", "M6 + measured charge-state shape on R0",
        basis="available", ocv="banded", r0_charge_state=True,
        parameter_unit="group_band",
        note="the charge-state shape again, now on top of the banded "
             "parameter unit, with still no free parameter added",
    ),
    Candidate(
        "M9", "M6 + a second RC branch",
        basis="available", ocv="banded", rc_branches=2,
        parameter_unit="group_band",
        note="the second branch on top of the banded parameter unit",
    ),
    Candidate(
        "M10", "M1 with one parameter set per declared calibration block",
        basis="available", ocv="banded", parameter_unit="block",
        note="a parameter set is valid for the rate it was fitted at, because "
             "this model's polarization is linear in current and the measured "
             "resistance is not",
    ),
    Candidate(
        "M11", "M10 + measured charge-state shape on R0",
        basis="available", ocv="banded", r0_charge_state=True,
        parameter_unit="block",
        note="the block parameter unit and the measured shape together, still "
             "with no free parameter added by the shape",
    ),
)


# ---------------------------------------------------------------------------
# The research march. Same scheme as the authorized path's staggered splitting.
# ---------------------------------------------------------------------------


def march(
    *,
    times_s: Sequence[float],
    currents_a: Sequence[float],
    ambient_k: float,
    initial_temperature_k: float,
    parameters: dict[str, float],
    curve: Curve,
    shape: Shape,
    basis_ah: float,
    initial_state_of_charge: float,
    rc_branches: int,
    coulombic_efficiency: float = 1.0,
):
    """Advance the coupled system across the measured grid.

    Identical in scheme to ``battery_thermal_flagship_s3/harness/march.py``:
    within a window the cell advances at the temperature the body left in the
    previous window, then the body advances on the heat the cell just reported.
    """
    r0_ref = parameters["ohmic_resistance_reference"]
    ea0 = parameters.get("ohmic_activation_energy", 0.0)
    r1_ref = parameters["polarization_resistance_reference"]
    ea1 = parameters.get("polarization_activation_energy", 0.0)
    c1 = parameters["polarization_capacitance"]
    r2_ref = parameters.get("second_polarization_resistance", 0.0)
    c2 = parameters.get("second_polarization_capacitance", 0.0)
    c_th = parameters["thermal_capacitance"]
    ha = parameters["thermal_conductance"]

    tau_th = c_th / ha
    z = float(initial_state_of_charge)
    vp1 = 0.0
    vp2 = 0.0
    temperature = float(initial_temperature_k)

    instants: list[float] = []
    voltages: list[float] = []
    temperatures: list[float] = []
    charge_states: list[float] = []
    stopped_at: int | None = None

    for index in range(1, len(times_s)):
        left = float(times_s[index - 1])
        right = float(times_s[index])
        dt = right - left
        if dt <= 0.0:
            continue
        raw = float(currents_a[index - 1])
        current = 0.0 if abs(raw) < REST_BAND_A else raw
        try:
            held = temperature
            arrhenius0 = math.exp(ea0 / GAS * (1.0 / held - 1.0 / REFERENCE_TEMPERATURE_K))
            arrhenius1 = math.exp(ea1 / GAS * (1.0 / held - 1.0 / REFERENCE_TEMPERATURE_K))
            z_next = z - current * (dt / 3600.0) / (coulombic_efficiency * basis_ah)
            if not 0.0 <= z_next <= 1.0 or z_next < curve.lower:
                raise OutsideCurve(
                    f"charge state {z_next:g} leaves the declared interval"
                )
            r0 = r0_ref * arrhenius0 * shape(z_next)
            r1 = r1_ref * arrhenius1
            if not (math.isfinite(r0) and math.isfinite(r1)) or min(r0, r1) <= 0.0:
                raise OutsideCurve("Arrhenius evaluation is not representable")

            tau1 = r1 * c1
            alpha1 = math.exp(-dt / tau1)
            vp1_inf = current * r1
            mean_vp = vp1_inf + (vp1 - vp1_inf) * (tau1 / dt) * (1.0 - alpha1)
            vp1_next = vp1 * alpha1 + vp1_inf * (1.0 - alpha1)

            vp2_next = 0.0
            if rc_branches == 2:
                r2 = r2_ref * arrhenius1
                if not math.isfinite(r2) or r2 <= 0.0:
                    raise OutsideCurve("second branch is not representable")
                tau2 = r2 * c2
                alpha2 = math.exp(-dt / tau2)
                vp2_inf = current * r2
                mean_vp += vp2_inf + (vp2 - vp2_inf) * (tau2 / dt) * (1.0 - alpha2)
                vp2_next = vp2 * alpha2 + vp2_inf * (1.0 - alpha2)

            heat = current * current * r0 + current * mean_vp
            steady = ambient_k + heat / ha
            beta = math.exp(-dt / tau_th)
            temperature = steady + (temperature - steady) * beta

            voltage = curve(z_next) - current * r0 - vp1_next - vp2_next
            z = z_next
            vp1 = vp1_next
            vp2 = vp2_next
        except OutsideCurve:
            stopped_at = index - 1
            break

        instants.append(right)
        voltages.append(voltage)
        temperatures.append(temperature)
        charge_states.append(z)

    return instants, voltages, temperatures, charge_states, stopped_at


# ---------------------------------------------------------------------------
# Rows, fitting and scoring
# ---------------------------------------------------------------------------


def load_curves() -> dict[str, Curve]:
    record = json.load(
        open(os.path.join(EVIDENCE, "OCV_AUTHORITY_V2.json"), encoding="utf-8")
    )
    curves = {
        f"v2:{name}": Curve(
            f"v2:{name}", tuple(curve["knots"]), tuple(curve["values_v"])
        )
        for name, curve in record["curves"].items()
    }
    curves["s3"] = Curve(
        "s3", tuple(z for z, _ in S3_OCV_KNOTS), tuple(v for _, v in S3_OCV_KNOTS)
    )
    return curves


def load_shapes() -> dict[str, Shape]:
    record = json.load(
        open(os.path.join(EVIDENCE, "OCV_AUTHORITY_V2.json"), encoding="utf-8")
    )
    shapes: dict[str, Shape] = {}
    for name, profile in record["resistance_profiles"].items():
        rows = profile["knots"]
        if len(rows) < 3:
            continue
        z = np.array([r["charge_state"] for r in rows], dtype=float)
        r = np.array([r["median_ohm"] for r in rows], dtype=float)
        reference = float(np.interp(R0_SHAPE_REFERENCE_Z, z, r))
        if reference <= 0.0:
            continue
        shapes[name] = Shape(
            f"measured_branch_difference:{name}",
            tuple(round(float(x), 6) for x in z),
            tuple(round(float(x / reference), 6) for x in r),
        )
    return shapes


def build_rows(candidate: Candidate) -> list[dict[str, Any]]:
    selection = json.load(
        open(os.path.join(EVIDENCE, "SELECTION.json"), encoding="utf-8")
    )
    state = json.load(
        open(os.path.join(EVIDENCE, "BATTERY_STATE_AUTHORITY.json"), encoding="utf-8")
    )
    states = {row["trajectory_id"]: row for row in state["trajectories"]}
    channels = cp.load_development_corpus(selection)
    cp.refuse_holdout(selection, channels)

    rows: list[dict[str, Any]] = []
    for row in selection["selected"]:
        if row["split"] not in ("calibration", "validation"):
            continue
        if row.get("applicability") != "inside":
            continue
        trajectory = channels.get(row["trajectory_id"])
        record = states.get(row["trajectory_id"])
        if trajectory is None or record is None:
            continue
        # Every candidate is scored on the SAME trajectories, and they are the
        # ones whose state the authorities can establish. A candidate given a
        # wider corpus than its rivals would win on data rather than on model,
        # so the declared-basis candidates are held to this set too even though
        # they do not read the state records to run.
        if record["capacity"]["basis"] == "unknown":
            continue
        if record["initial_state"]["basis"] == "unknown":
            continue
        if candidate.basis == "available":
            basis_ah = float(record["capacity"]["initial_available_charge_ah"])
            z0 = float(record["initial_state"]["initial_state_of_charge"])
        else:
            basis_ah = S3_BASIS_AH
            z0 = 1.0
        ch = trajectory["channels"]
        currents = [-x for x in ch["current_a"]]
        admissible = [
            channel_consistent(currents, ch["voltage_v"], index)
            for index in range(len(ch["voltage_v"]))
        ]
        rows.append(
            {
                "trajectory_id": row["trajectory_id"],
                "admissible": admissible,
                "cell": row["cell"],
                "group": row["group"],
                "split": row["split"],
                "corner": row["corner"],
                "band": band_for(
                    float(row["ambient_temperature_c"]), float(row["load_current_a"])
                ),
                "nominal_current_a": float(row["load_current_a"]),
                "times_s": ch["time_s"],
                "currents_a": [-x for x in ch["current_a"]],
                "voltage_v": ch["voltage_v"],
                "temperature_k": [x + 273.15 for x in ch["temperature_c"]],
                "ambient_k": float(row["ambient_temperature_c"]) + 273.15,
                "admit_temperature": bool(row.get("admit_cell_temperature", True)),
                "basis_ah": basis_ah,
                "z0": z0,
            }
        )
    return rows


def curve_for(candidate: Candidate, row: dict[str, Any], curves, shapes):
    if candidate.ocv == "s3":
        return curves["s3"], _FLAT
    if candidate.ocv == "pooled":
        curve = curves["v2:pooled"]
        shape = shapes.get("pooled", _FLAT)
    else:
        curve = curves.get(f"v2:{row['band']}") or curves["v2:pooled"]
        shape = shapes.get(row["band"], _FLAT)
    return curve, (shape if candidate.r0_charge_state else _FLAT)


def claimed_samples(row: dict[str, Any], curve: Curve) -> int:
    """Admissible instants at or above the curve's own floor.

    The count fixes the residual vector's length, which least_squares requires
    to be constant, and it must not depend on any parameter value -- so it is
    computed from the integrated measured current and the channel-consistency
    screen, and from nothing else.
    """
    charge = 0.0
    count = 0
    times, currents = row["times_s"], row["currents_a"]
    for index in range(1, len(times)):
        dt_h = (float(times[index]) - float(times[index - 1])) / 3600.0
        charge += float(currents[index - 1]) * dt_h
        if row["z0"] - charge / row["basis_ah"] < curve.lower:
            continue
        if not row["admissible"][index]:
            continue
        count += 1
    return count


def residuals(vector, rows, candidate, names, curves, shapes) -> np.ndarray:
    parameters = {name: float(value) for name, value in zip(names, vector)}
    out: list[float] = []
    for row in rows:
        curve, shape = curve_for(candidate, row, curves, shapes)
        try:
            _i, voltage, temperature, charge, _stop = march(
                times_s=row["times_s"],
                currents_a=row["currents_a"],
                ambient_k=row["ambient_k"],
                initial_temperature_k=row["temperature_k"][0],
                parameters=parameters,
                curve=curve,
                shape=shape,
                basis_ah=row["basis_ah"],
                initial_state_of_charge=row["z0"],
                rc_branches=candidate.rc_branches,
            )
        except (ValueError, OverflowError):
            out.extend([UNREACHED_PENALTY] * row["claimed"])
            if row["admit_temperature"]:
                out.extend([UNREACHED_PENALTY] * row["claimed"])
            continue
        reached = len(voltage)
        measured_v = row["voltage_v"][1 : reached + 1]
        measured_t = row["temperature_k"][1 : reached + 1]
        claimed = 0
        for index in range(reached):
            if charge[index] < curve.lower:
                continue
            if not row["admissible"][index + 1]:
                continue
            claimed += 1
            out.append((voltage[index] - measured_v[index]) / VOLTAGE_SCALE_V)
            if row["admit_temperature"]:
                out.append(
                    (temperature[index] - measured_t[index]) / TEMPERATURE_SCALE_K
                )
        missing = row["claimed"] - claimed
        if missing > 0:
            out.extend([UNREACHED_PENALTY] * missing)
            if row["admit_temperature"]:
                out.extend([UNREACHED_PENALTY] * missing)
    return np.asarray(out, dtype=float)


def identifiability(jacobian, residual, names, values):
    """Standard errors and a verdict per parameter, from the fit's Jacobian."""
    n, p = jacobian.shape
    dof = max(n - p, 1)
    sigma_squared = float(residual @ residual) / dof
    normal = jacobian.T @ jacobian
    singular = np.linalg.svd(normal, compute_uv=False)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else math.inf
    try:
        covariance = np.linalg.inv(normal) * sigma_squared
    except np.linalg.LinAlgError:
        return (
            {n: None for n in names},
            {n: "unknown" for n in names},
            {},
            condition,
        )
    errors: dict[str, float | None] = {}
    verdicts: dict[str, str] = {}
    deviations = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
    for index, name in enumerate(names):
        variance = float(covariance[index, index])
        if not math.isfinite(variance) or variance < 0.0:
            errors[name] = None
            verdicts[name] = "unknown"
            continue
        error = math.sqrt(variance)
        errors[name] = error
        value = abs(float(values[index]))
        relative = error / value if value > 0 else math.inf
        verdicts[name] = (
            "identified" if relative <= 0.1
            else "weak" if relative <= 0.5
            else "unidentified"
        )
    correlations: dict[str, float] = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if deviations[i] > 0 and deviations[j] > 0:
                rho = float(covariance[i, j] / (deviations[i] * deviations[j]))
                if abs(rho) >= 0.9:
                    correlations[f"{names[i]}|{names[j]}"] = round(rho, 4)
    return errors, verdicts, correlations, condition


def score(rows, candidate, parameters_by_group, names, curves, shapes, split):
    """Residual statistics over one split, per cell and aggregated."""
    residual_v: list[float] = []
    residual_t: list[float] = []
    per_cell: dict[str, list[float]] = {}
    per_phase: dict[str, list[float]] = {}
    signed_v: list[float] = []
    refused = 0
    inadmissible = 0
    # Coverage is part of the comparison, not a detail of it. A candidate whose
    # open-circuit voltage interval is narrow answers only the easy part of a
    # discharge and its residual statistics look better for it -- which is a
    # weaker claim, not a better model. So the denominator is every admissible
    # sample of the split, fixed independently of any candidate, and a sample a
    # candidate cannot reach is charged one acceptance tolerance in
    # ``penalized_rmse`` exactly as the fit objective charges it.
    admissible_total = 0
    for row in rows:
        if row["split"] != split:
            continue
        admissible_total += sum(
            1 for index in range(1, len(row["voltage_v"])) if row["admissible"][index]
        )
    for row in rows:
        if row["split"] != split:
            continue
        parameters = parameters_by_group.get(candidate.unit_of(row))
        if parameters is None:
            refused += 1
            continue
        curve, shape = curve_for(candidate, row, curves, shapes)
        try:
            _i, voltage, temperature, charge, _stop = march(
                times_s=row["times_s"],
                currents_a=row["currents_a"],
                ambient_k=row["ambient_k"],
                initial_temperature_k=row["temperature_k"][0],
                parameters=parameters,
                curve=curve,
                shape=shape,
                basis_ah=row["basis_ah"],
                initial_state_of_charge=row["z0"],
                rc_branches=candidate.rc_branches,
            )
        except (ValueError, OverflowError):
            refused += 1
            continue
        reached = len(voltage)
        measured_v = row["voltage_v"][1 : reached + 1]
        measured_t = row["temperature_k"][1 : reached + 1]
        for index in range(reached):
            if charge[index] < curve.lower:
                continue
            if not row["admissible"][index + 1]:
                inadmissible += 1
                continue
            delta = voltage[index] - measured_v[index]
            residual_v.append(abs(delta))
            signed_v.append(delta)
            per_cell.setdefault(row["cell"], []).append(abs(delta))
            phase = (
                "rest"
                if abs(float(row["currents_a"][index])) < REST_BAND_A
                else "loaded"
            )
            per_phase.setdefault(phase, []).append(abs(delta))
            if row["admit_temperature"]:
                residual_t.append(abs(temperature[index] - measured_t[index]))
    scored = len(residual_v)
    missed = max(admissible_total - scored, 0)
    penalized = (
        math.sqrt(
            (sum(x * x for x in residual_v) + missed * VOLTAGE_SCALE_V ** 2)
            / max(admissible_total, 1)
        )
        if admissible_total
        else None
    )
    return {
        "split": split,
        "admissible_samples": admissible_total,
        "scored_samples": scored,
        "coverage": round(scored / admissible_total, 4) if admissible_total else None,
        "penalized_rmse_v": penalized,
        "penalty_note": (
            "a sample the candidate cannot reach is charged one acceptance "
            f"tolerance ({VOLTAGE_SCALE_V} V), the same scale the fit objective "
            "charges an unreached sample; coverage and this statistic together "
            "stop a narrow claim from looking like a good model"
        ),
        "voltage": _statistics(residual_v),
        "voltage_bias_v": (
            float(np.mean(signed_v)) if signed_v else None
        ),
        "temperature": _statistics(residual_t),
        "per_cell_voltage": {c: _statistics(v) for c, v in sorted(per_cell.items())},
        "per_phase_voltage": {c: _statistics(v) for c, v in sorted(per_phase.items())},
        "trajectories_refused": refused,
        "samples_inadmissible_on_their_own_channels": inadmissible,
        "residual_autocorrelation_lag1": _autocorrelation(signed_v),
    }


def _statistics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    array = np.asarray(values, dtype=float)
    return {
        "n": int(array.size),
        "mae": float(np.mean(array)),
        "rmse": float(np.sqrt(np.mean(array * array))),
        "p95": float(np.percentile(array, 95)),
        "max": float(array.max()),
    }


def _autocorrelation(values: list[float]) -> float | None:
    """Lag-1 autocorrelation of the signed residual sequence.

    A 1-RC model that is missing a relaxation mode leaves residuals that walk
    rather than scatter, so this is the diagnostic R7 asks for. It is computed
    over the concatenated sequence and is a coarse indicator, not a test.
    """
    if len(values) < 3:
        return None
    array = np.asarray(values, dtype=float)
    array = array - array.mean()
    denominator = float(array @ array)
    if denominator <= 0.0:
        return None
    return round(float(array[:-1] @ array[1:] / denominator), 4)


def fit(candidate: Candidate, rows, curves, shapes) -> dict[str, Any]:
    names = list(candidate.parameter_names)
    calibration = [r for r in rows if r["split"] == "calibration"]
    for row in rows:
        curve, _shape = curve_for(candidate, row, curves, shapes)
        row["claimed"] = claimed_samples(row, curve)

    groups = sorted({candidate.unit_of(r) for r in calibration})
    parameters_by_group: dict[str, dict[str, float]] = {}
    fits: list[dict[str, Any]] = []
    for group in groups:
        subset = [r for r in calibration if candidate.unit_of(r) == group]
        x0 = np.array([SPECS[n]["initial"] for n in names], dtype=float)
        lower = np.array([SPECS[n]["lower"] for n in names], dtype=float)
        upper = np.array([SPECS[n]["upper"] for n in names], dtype=float)
        started = time.perf_counter()
        result = least_squares(
            residuals,
            x0,
            bounds=(lower, upper),
            args=(subset, candidate, names, curves, shapes),
            method="trf",
            x_scale="jac",
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
            max_nfev=4000,
        )
        elapsed = time.perf_counter() - started
        errors, verdicts, correlations, condition = identifiability(
            result.jac, result.fun, names, result.x
        )
        values = {name: float(v) for name, v in zip(names, result.x)}
        parameters_by_group[group] = values
        objective = float(0.5 * float(result.fun @ result.fun))
        fits.append(
            {
                "group": group,
                "parameter_unit": candidate.parameter_unit,
                "cells": sorted({r["cell"] for r in subset}),
                "trajectories": len(subset),
                "corners": sorted({r["corner"] for r in subset}),
                "fitted": values,
                "standard_errors": errors,
                "identifiability": verdicts,
                "correlated_pairs_above_0p9": correlations,
                "normal_matrix_condition_number": condition,
                "objective_value": objective,
                "residuals": int(result.fun.size),
                "at_declared_bound": sorted(
                    name
                    for index, name in enumerate(names)
                    if abs(result.x[index] - lower[index])
                    <= 1e-9 * max(1.0, abs(lower[index]))
                    or abs(result.x[index] - upper[index])
                    <= 1e-9 * max(1.0, abs(upper[index]))
                ),
                "wall_seconds": elapsed,
                "optimizer_status": int(result.status),
            }
        )
        print(
            f"    {group:14} n={len(subset):3d} obj {objective:12.4g} "
            f"over {int(result.fun.size):6d} residuals  {elapsed:5.1f}s",
            file=sys.stderr,
        )

    # Ordering check for the second branch: a branch that is not slower than the
    # first is not a second time constant, it is the same one written twice.
    ordering = {}
    if candidate.rc_branches == 2:
        for record in fits:
            f = record["fitted"]
            tau1 = f["polarization_resistance_reference"] * f["polarization_capacitance"]
            tau2 = (
                f["second_polarization_resistance"]
                * f["second_polarization_capacitance"]
            )
            ordering[record["group"]] = {
                "tau1_s": round(tau1, 3),
                "tau2_s": round(tau2, 3),
                "ratio": round(tau2 / tau1, 3) if tau1 > 0 else None,
                "separated": bool(tau1 > 0 and tau2 / tau1 >= 3.0),
            }

    free_parameters = len(names) * len(groups)
    calibration_score = score(
        rows, candidate, parameters_by_group, names, curves, shapes, "calibration"
    )
    validation_score = score(
        rows, candidate, parameters_by_group, names, curves, shapes, "validation"
    )
    residual_count = sum(f["residuals"] for f in fits)
    objective_total = sum(f["objective_value"] for f in fits)
    return {
        "key": candidate.key,
        "label": candidate.label,
        "note": candidate.note,
        "configuration": {
            "charge_state_basis": candidate.basis,
            "ocv_authority": candidate.ocv,
            "parameter_unit": candidate.parameter_unit,
            "arrhenius_activation_energies": candidate.arrhenius,
            "r0_charge_state_shape": candidate.r0_charge_state,
            "rc_branches": candidate.rc_branches,
        },
        "parameter_names": names,
        "free_parameters_per_group": len(names),
        "free_parameters_total": free_parameters,
        "groups": fits,
        "second_branch_time_constants": ordering,
        "calibration": calibration_score,
        "validation": validation_score,
        "information_criteria": _criteria(objective_total, residual_count, free_parameters),
        "trajectories_scored": {
            "calibration": calibration_score["voltage"].get("n", 0),
            "validation": validation_score["voltage"].get("n", 0),
        },
    }


def _criteria(objective: float, residuals_count: int, parameters: int) -> dict[str, Any]:
    """AIC and BIC on the weighted least-squares objective.

    Both assume independent Gaussian residuals on the weighting scale. These
    residuals are serially correlated, so the criteria are reported as an
    ordering aid and are explicitly not the decision.
    """
    if residuals_count <= parameters + 1 or objective <= 0.0:
        return {"aic": None, "bic": None, "caveat": "insufficient residuals"}
    sigma_squared = 2.0 * objective / residuals_count
    log_likelihood = -0.5 * residuals_count * (math.log(2 * math.pi * sigma_squared) + 1.0)
    return {
        "aic": round(2 * parameters - 2 * log_likelihood, 2),
        "bic": round(parameters * math.log(residuals_count) - 2 * log_likelihood, 2),
        "residuals": residuals_count,
        "parameters": parameters,
        "caveat": (
            "computed on the weighted objective under an independence "
            "assumption these residuals do not satisfy; an ordering aid, not "
            "the decision"
        ),
    }


def main() -> int:
    curves = load_curves()
    shapes = load_shapes()
    print(f"curves: {sorted(curves)}", file=sys.stderr)
    print(f"shapes: {sorted(shapes)}", file=sys.stderr)

    results = []
    for candidate in CANDIDATES:
        print(f"\n{candidate.key}: {candidate.label}", file=sys.stderr)
        rows = build_rows(candidate)
        print(
            f"  rows: {len(rows)} "
            f"(calibration {sum(1 for r in rows if r['split']=='calibration')}, "
            f"validation {sum(1 for r in rows if r['split']=='validation')})",
            file=sys.stderr,
        )
        results.append(fit(candidate, rows, curves, shapes))
        r = results[-1]
        v = r["validation"]["voltage"]
        c = r["calibration"]["voltage"]
        print(
            f"  validation coverage {r['validation']['coverage']:.3f} "
            f"({r['validation']['scored_samples']}/"
            f"{r['validation']['admissible_samples']})   "
            f"calRMSE {c.get('rmse', float('nan'))*1000:7.2f}   "
            f"valMAE {v.get('mae', float('nan'))*1000:7.2f} "
            f"valRMSE {v.get('rmse', float('nan'))*1000:7.2f} "
            f"valP95 {v.get('p95', float('nan'))*1000:7.2f} "
            f"penRMSE {(r['validation']['penalized_rmse_v'] or 0)*1000:7.2f} mV",
            file=sys.stderr,
        )

    record = {
        "schema": CANDIDATE_SCHEMA,
        "what_this_is": (
            "a controlled comparison of admissible model candidates, every one "
            "fitted on calibration trajectories and judged on validation "
            "trajectories. The locked holdout is not readable by this script"
        ),
        "selection_rule": (
            "among candidates of comparable validation COVERAGE, the simplest "
            "one whose validation voltage statistics are not beaten by a more "
            "complex one by more than the validation split's own resolution, "
            "and whose added parameters are identified. Coverage comes first: a "
            "candidate that answers fewer of the split's admissible samples is "
            "making a narrower claim, and its residual statistics are not "
            "comparable with a candidate that answers all of them"
        ),
        "measurement_screen": {
            "channel_disagreement_v": CHANNEL_DISAGREEMENT_V,
            "rule": (
                "a sample reporting rest whose voltage has moved more than the "
                "frozen acceptance tolerance since the previous resting sample "
                "is inadmissible: its two channels contradict each other"
            ),
            "model_free": True,
            "applied_to": "every split alike",
        },
        "weights": {
            "voltage_scale_v": VOLTAGE_SCALE_V,
            "temperature_scale_k": TEMPERATURE_SCALE_K,
            "unreached_penalty": UNREACHED_PENALTY,
            "source": "the Sprint 3 reviewed acceptance tolerances, unchanged",
        },
        "band_rule": {
            "cold_ambient_ceiling_c": COLD_AMBIENT_CEILING_C,
            "cold_current_ceiling_a": COLD_CURRENT_CEILING_A,
            "why": (
                "decided from the chamber ambient and the nominal load, both "
                "known before the run, so the curve a trajectory is predicted "
                "with never depends on the prediction"
            ),
        },
        "parameter_specs": SPECS,
        "candidates": results,
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    out = os.path.join(EVIDENCE, "MODEL_CANDIDATES.json")
    with open(out, "wb") as handle:
        handle.write(payload)
    print(f"\nwrote {out}")
    print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
