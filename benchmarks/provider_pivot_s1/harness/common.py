"""Shared corpus, authorities and scoring for the provider comparison.

The corpus is the Sprint 3 recovery's, loaded through **its own** loader rather
than re-derived here. That matters for one reason above all others:
:func:`corpus.load_development_corpus` refuses to return a holdout trajectory,
and a module that re-globbed the archive would quietly recover the access the
loader exists to deny.

What this round is allowed to see
---------------------------------
``calibration`` and ``validation``, and nothing else.

``locked_holdout`` (B0041, 6 trajectories) was **opened and read** by the
recovery round, which is recorded in its own report: the model is uniformly
+128 mV high on that cell and the diagnosis is missing impedance growth. A cell
whose residuals have been read is no longer independent, so this round does not
score it, does not re-open it, and does not treat it as a Gate A. There is no
pristine holdout left in this archive and this sprint does not manufacture one.

``observed_holdout`` (B0007/B0036/B0044, 37 trajectories) is the Sprint 3
holdout, likewise read. Same treatment.

The native baseline
-------------------
``battery.cell.electrothermal_1rc@0.2.0`` at the parameters the recovery froze,
marched by the recovery's own kernel. Nothing is re-fitted for it, so the
numbers this round reports for the native model are that model's, produced the
way its own round produced them.
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
REPO = os.path.dirname(os.path.dirname(BENCH))
RECOVERY = os.path.join(REPO, "benchmarks", "battery_voltage_s3_recovery")
RECOVERY_HARNESS = os.path.join(RECOVERY, "harness")
RECOVERY_EVIDENCE = os.path.join(RECOVERY, "evidence")

sys.path.insert(0, RECOVERY_HARNESS)
sys.path.insert(0, os.path.join(REPO, "src"))

import corpus as recovery_corpus  # noqa: E402
from engcore.domains.battery import flagship_ocv_v2 as recovery_ocv  # noqa: E402
import predict as recovery_predict  # noqa: E402

from engcore.providers import pybamm_provider as pp  # noqa: E402

#: Only these two. See the module docstring.
DEVELOPMENT_SPLITS = ("calibration", "validation")

#: Kelvin offset, spelled once.
ZERO_C_K = 273.15

#: The cell the archive holds, as Forge states it. The chemistry is what NASA's
#: own description of the pack supports -- commercial 18650 lithium-cobalt-oxide
#: cells -- and it is declared here rather than inferred anywhere, because it is
#: the field the parameter-authority screen turns on.
CELL_CHEMISTRY = "LiCoO2/graphite"

#: Every scored sample. The recovery's stride, kept so the two rounds compare
#: like for like.
SAMPLE_STRIDE = getattr(recovery_predict, "SAMPLE_STRIDE", 1)

#: A DECLARED APPROXIMATION, and the only one this round makes.
#:
#: The two models do not agree about the same physical state at one end. Forge's
#: native cell defines charge state on the CLOSED interval [0, 1], where z = 1
#: means "at the measured available charge" -- and every one of the 52
#: development trajectories starts there, because that is what the state
#: authority established. PyBaMM's equivalent-circuit model carries its SoC
#: bounds as termination EVENTS, so its interval is open: at exactly 1.0 the
#: event is non-positive at the initial condition and the solve ends before its
#: first step. ``PyBaMMModelSpec.state_of_charge_interval`` declares that, and
#: the adapter refuses the point as MODEL_NOT_APPLICABLE rather than crashing.
#:
#: Left there, the provider would decline 52 of 52 trajectories on a convention
#: and the comparison would measure nothing. So the physical state "full charge
#: on the measured basis" is mapped to the largest state the ECM can represent,
#: by subtracting this margin. It is applied HERE, in the benchmark, and never
#: inside the adapter: a provider that quietly moved a caller's scientific input
#: to make its own model run is the thing this whole sprint is against.
#:
#: The margin's effect is MEASURED rather than argued. ``compare.py`` re-runs
#: the whole comparison at a tenth of it and reports the difference in every
#: metric; see ``COMPARISON.json`` -> ``state_margin_sensitivity``.
ECM_STATE_MARGIN = 1e-3


def load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def selection() -> dict[str, Any]:
    return load_json(os.path.join(RECOVERY_EVIDENCE, "SELECTION.json"))


def state_authority() -> dict[str, Any]:
    return load_json(os.path.join(RECOVERY_EVIDENCE, "BATTERY_STATE_AUTHORITY.json"))


def preregistration() -> dict[str, Any]:
    return load_json(
        os.path.join(RECOVERY_EVIDENCE, "NEW_GATE_A_PREREGISTRATION.json")
    )


def ocv_authority() -> dict[str, Any]:
    return load_json(os.path.join(RECOVERY_EVIDENCE, "OCV_AUTHORITY_V2.json"))


def native_parameter_unit(row: dict[str, Any]) -> str:
    """The recovery's own operating-block key. Copied from its predict march."""
    rate = round(abs(float(row["load_current_a"])) * 2.0) / 2.0
    return f"{row['group']}|{row['corner']}|{rate:g}A"


class Trajectory:
    """One measured discharge, in Forge's sign convention and units.

    ``current_a`` is **positive on discharge**, which is what
    ``domains.battery`` and PyBaMM both mean. The archive stores it negative,
    and the flip happens here, once, rather than in each consumer.
    """

    __slots__ = (
        "trajectory_id", "cell", "split", "band", "group", "corner",
        "time_s", "current_a", "voltage_v", "temperature_k",
        "ambient_k", "capacity_ah", "initial_soc", "native_unit",
    )

    def __init__(self, **fields: Any) -> None:
        for name in self.__slots__:
            setattr(self, name, fields[name])

    @property
    def duration_s(self) -> float:
        return float(self.time_s[-1] - self.time_s[0])

    @property
    def sample_count(self) -> int:
        return len(self.time_s)


def development_trajectories(
    splits: Sequence[str] = DEVELOPMENT_SPLITS,
) -> list[Trajectory]:
    """Every development trajectory with a usable state, in selection order.

    A trajectory whose capacity basis or initial state is UNKNOWN is dropped
    here rather than defaulted. The recovery established both authorities and
    refused fifteen trajectories at 4 degC where the charger stopped with
    current still flowing; inventing a state for those would be exactly the
    failure that round documented.
    """
    for split in splits:
        if split not in DEVELOPMENT_SPLITS:
            raise SystemExit(
                f"split {split!r} is not a development split. This round scores "
                f"calibration and validation only; the holdout splits have been "
                f"read and are not independent evidence"
            )
    chosen = selection()
    states = {r["trajectory_id"]: r for r in state_authority()["trajectories"]}
    channels = recovery_corpus.load_development_corpus(chosen)
    rows = [r for r in chosen["selected"] if r["split"] in splits]

    out: list[Trajectory] = []
    for row in rows:
        tid = row["trajectory_id"]
        record = states.get(tid)
        raw = channels.get(tid)
        if record is None or raw is None:
            continue
        if record["capacity"]["basis"] == "unknown":
            continue
        if record["initial_state"]["basis"] == "unknown":
            continue
        if row.get("applicability") != "inside":
            continue
        ch = raw["channels"]
        out.append(
            Trajectory(
                trajectory_id=tid,
                cell=row["cell"],
                split=row["split"],
                band=recovery_ocv.band_for(
                    float(row["ambient_temperature_c"]), float(row["load_current_a"])
                ),
                group=row["group"],
                corner=row["corner"],
                time_s=[float(v) for v in ch["time_s"]],
                current_a=[-float(v) for v in ch["current_a"]],
                voltage_v=[float(v) for v in ch["voltage_v"]],
                temperature_k=[float(v) + ZERO_C_K for v in ch["temperature_c"]],
                ambient_k=float(row["ambient_temperature_c"]) + ZERO_C_K,
                capacity_ah=float(record["capacity"]["initial_available_charge_ah"]),
                initial_soc=float(record["initial_state"]["initial_state_of_charge"]),
                native_unit=native_parameter_unit(row),
            )
        )
    return out


# =====================================================================
# The Forge parameter authority for this cell
# =====================================================================

def base_authority(band: str) -> pp.ParameterAuthority:
    """The skeleton every derived authority for this archive descends from.

    ``source="forge_declared"``: the numbers are not PyBaMM's. There is no
    published parameter set for these cells, and pretending one of PyBaMM's
    named sets described them is the exact error this sprint's applicability
    screen exists to catch.

    The temperature band is the OCV authority's own declared band, in Kelvin.
    An authority that declared a wider band than its OCV curve was measured over
    would be claiming validity the measurement does not support.
    """
    bands = {b["band"]: b for b in ocv_authority()["cell_temperature_bands_c"]}
    declared = bands[band]
    return pp.ParameterAuthority(
        authority_id=f"forge.nasa_li_ion_18650.ecm/{band}",
        source="forge_declared",
        parameter_set_name="ECM_Example",
        defining_provider_version="pybamm",
        chemistry=CELL_CHEMISTRY,
        nominal_capacity_ah=nominal_capacity(),
        temperature_validity_k=(
            float(declared["low"]) + ZERO_C_K,
            float(declared["high"]) + ZERO_C_K,
        ),
        # The OCV authority says so in its own words: "conditioned on median
        # measured cell temperature over the loaded discharge branch. Ambient
        # is not the condition."
        temperature_basis="cell",
        units={
            "capacity": "ampere_hour",
            "resistance": "ohm",
            "capacitance": "farad",
            "temperature": "kelvin",
        },
        notes=(
            f"declared by Forge for the NASA PCoE 18650 archive, cell-temperature "
            f"band {band!r}. The open-circuit voltage is the recovery's measured "
            f"OCV_AUTHORITY_V2 curve for this band on the measured-available-charge "
            f"axis; it is a Forge measurement and is cited as one"
        ),
    )


def nominal_capacity() -> float:
    """The median measured available charge over the development corpus.

    Not the manufacturer's 2 A.h rating. The recovery established that the
    rating is 22 % above what these cells deliver at the median, and a
    parameter authority that declared the rating would be describing a cell
    this archive does not contain.
    """
    values = sorted(t.capacity_ah for t in development_trajectories())
    if not values:
        raise SystemExit("no development trajectory carries a capacity basis")
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return 0.5 * (values[middle - 1] + values[middle])


def median_cell_temperature(trajectory: "Trajectory") -> float:
    """The quantity the OCV authority conditions its bands on."""
    ordered = sorted(trajectory.temperature_k)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def cell_under_test(trajectory: "Trajectory") -> pp.CellUnderTest:
    return pp.CellUnderTest(
        cell_id=trajectory.cell,
        chemistry=CELL_CHEMISTRY,
        nominal_capacity_ah=trajectory.capacity_ah,
        ambient_temperature_k=trajectory.ambient_k,
        cell_temperature_k=median_cell_temperature(trajectory),
    )


def coulomb_counted_state(trajectory: "Trajectory") -> list[float]:
    """Charge state at each measured instant, on the measured-capacity basis.

    ``z(t) = z0 - integral(I dt) / (3600 * Q_available)``, the same relation the
    native cell model advances its state with, so the window below is the
    native model's own coordinate and not a second one.
    """
    charge = 0.0
    out = [float(trajectory.initial_soc)]
    for index in range(1, len(trajectory.time_s)):
        dt = trajectory.time_s[index] - trajectory.time_s[index - 1]
        charge += trajectory.current_a[index - 1] * dt / 3600.0
        out.append(trajectory.initial_soc - charge / trajectory.capacity_ah)
    return out


def charge_state_floor(band: str) -> float:
    """The lowest charge state the band's OCV authority was measured over.

    Read from the production curve, not restated here: ``OCV_V2_CURVES[band].lower``
    is 0.10 warm and 0.05 cold, and those are where the recovery's admitted
    contiguous block of knots begins.
    """
    return float(recovery_ocv.OCV_V2_CURVES[band].lower)


def applicable_window(trajectory: "Trajectory") -> tuple[int, int]:
    """The prefix of the trajectory both models claim, as ``[start, stop)``.

    Every one of these discharges runs to a charge state near zero, and the
    open-circuit voltage authority was measured down to 0.10 (warm) and 0.05
    (cold) and no further. Below its floor the curve is HELD at its end value
    -- a declared approximation the recovery states -- so a prediction there is
    not a prediction the OCV authority supports, for either model.

    So the window is the applicability screen both models are held to, and it is
    computed once, here, from the native model's own charge-state coordinate.
    Samples outside it are not scored and are counted as refusals by both, which
    is what makes the refusal-rate column of the comparison mean the same thing
    for each.

    The first run of the PyBOP fit did not apply this and the consequence was
    visible in two ways at once: nine of thirty-three fits failed outright
    because the provider's solve terminated at its own SoC floor before the
    measured trajectory ended, and six of the survivors drove ``R0`` onto its
    lower bound -- the fitter compensating for a held OCV tail with a resistance
    it does not have. Both are the same defect: fitting a model outside the
    interval its own parameter authority was measured over.
    """
    floor = charge_state_floor(trajectory.band)
    states = coulomb_counted_state(trajectory)
    stop = len(states)
    for index, value in enumerate(states):
        if value < floor:
            stop = index
            break
    return (0, stop)


def windowed(trajectory: "Trajectory") -> "Trajectory":
    """``trajectory`` cut to :func:`applicable_window`. A new record, never a mutation."""
    start, stop = applicable_window(trajectory)
    fields = {name: getattr(trajectory, name) for name in Trajectory.__slots__}
    for channel in ("time_s", "current_a", "voltage_v", "temperature_k"):
        fields[channel] = list(getattr(trajectory, channel))[start:stop]
    return Trajectory(**fields)


def ecm_initial_state_of_charge(
    trajectory: "Trajectory", margin: float = ECM_STATE_MARGIN
) -> float:
    """The measured initial state, mapped into the ECM's open interval.

    A transformation of a scientific input, done once and named, so that every
    consumer applies the same one and a reader can find it. See
    :data:`ECM_STATE_MARGIN`.
    """
    return min(float(trajectory.initial_soc), 1.0 - float(margin))


def ecm_factory(
    band: str,
    *,
    capacity_ah: float,
    ambient_k: float,
    initial_temperature_k: float,
    r0_ohm: float,
    r1_ohm: float,
    c1_farad: float,
    initial_state_of_charge: float | None = None,
):
    """A PyBaMM ``ParameterValues`` for the equivalent-circuit model.

    Built by copying PyBaMM's ``ECM_Example`` and replacing everything that
    describes a cell. The copy is deliberate and is what
    ``ParameterAuthority.derive`` records: PyBaMM's example set is a starting
    structure, never an authority for these numbers.

    The open-circuit voltage is the recovery's measured curve, interpolated
    linearly between its knots and **held** outside the measured interval.
    Extrapolating a measured OCV curve would invent a voltage the cells never
    showed; PyBaMM's ``Interpolant`` is given ``extrapolate=True`` because
    CasADi requires a total function, and the curve is padded with its own end
    values first so that "extrapolation" is a hold rather than a trend.
    """

    def build():
        import numpy as np
        import pybamm

        curve = ocv_authority()["curves"][band]
        knots = [float(v) for v in curve["knots"]]
        volts = [float(v) for v in curve["values_v"]]
        # The hold, made explicit in the data rather than left to the
        # interpolator's behaviour at the ends.
        knots = [0.0] + knots + [1.0]
        volts = [volts[0]] + volts + [volts[-1]]
        knot_array = np.asarray(knots, dtype=float)
        volt_array = np.asarray(volts, dtype=float)

        def ocv(soc):
            return pybamm.Interpolant(
                knot_array, volt_array, soc, interpolator="linear", extrapolate=True
            )

        values = pybamm.ParameterValues("ECM_Example").copy()
        values.update(
            {
                "Cell capacity [A.h]": float(capacity_ah),
                "Nominal cell capacity [A.h]": float(capacity_ah),
                "Open-circuit voltage [V]": ocv,
                "R0 [Ohm]": float(r0_ohm),
                "R1 [Ohm]": float(r1_ohm),
                "C1 [F]": float(c1_farad),
                "Element-1 initial overpotential [V]": 0.0,
                "Entropic change [V/K]": 0.0,
                "Ambient temperature [K]": float(ambient_k),
                "Initial temperature [K]": float(initial_temperature_k),
                # The archive's own cut-offs are wider than any measured
                # sample, so the event never fires inside a scored trajectory.
                # A cut-off inside the data would end a solve early and report
                # the truncation as a short trajectory rather than as a refusal.
                "Lower voltage cut-off [V]": 1.5,
                "Upper voltage cut-off [V]": 4.9,
            },
            check_already_exists=False,
        )
        if initial_state_of_charge is not None:
            # For the PyBOP route, which builds its own simulator from these
            # values rather than going through the adapter's request. The
            # adapter sets the same key from the request it was given, so the
            # two routes start the model at the same state by construction.
            values["Initial SoC"] = float(initial_state_of_charge)
        return values

    return build


def derived_authority(
    band: str,
    *,
    r0_ohm: float,
    r1_ohm: float,
    c1_farad: float,
    note: str,
    unit: str = "band",
) -> pp.ParameterAuthority:
    """The fitted numbers as their own authority, with the parent recorded.

    ``unit`` is the operating block the numbers belong to -- the recovery's own
    ``group|corner|rate`` key. It is part of the authority's identity because
    the recovery established that it has to be: the measured resistance rises
    from 0.169 to 0.208 ohm between 2 A and 4 A while a one-RC model's
    polarization is linear in current, so one resistance per temperature band
    is a resistance that is wrong at both rates. Fitting the provider per band
    reproduced exactly that, at an interquartile spread of 81 % in ``R0``.
    """
    return base_authority(band).derive(
        authority_id=f"forge.nasa_li_ion_18650.ecm/{unit}/fitted",
        overrides={
            "R0 [Ohm]": float(r0_ohm),
            "R1 [Ohm]": float(r1_ohm),
            "C1 [F]": float(c1_farad),
        },
        notes=note,
    )


# =====================================================================
# Scoring
# =====================================================================

def statistics(residuals: Sequence[float]) -> dict[str, Any]:
    """MAE, RMSE, P95 and bias. The recovery's definitions, not new ones."""
    signed = [float(v) for v in residuals if math.isfinite(float(v))]
    if not signed:
        return {"n": 0, "mae": None, "rmse": None, "p95": None, "bias": None}
    absolute = sorted(abs(v) for v in signed)
    count = len(absolute)
    index = min(int(math.ceil(0.95 * count)) - 1, count - 1)
    return {
        "n": count,
        "mae": sum(absolute) / count,
        "rmse": math.sqrt(sum(v * v for v in signed) / count),
        "p95": absolute[max(index, 0)],
        "bias": sum(signed) / count,
        "max": absolute[-1],
    }


def interpolate(times: Sequence[float], values: Sequence[float], at: Sequence[float]):
    """Linear resample of a provider trajectory onto the measured instants.

    A provider chooses its own output grid. Comparing its grid to the
    measurement's would compare different instants, so the provider's series is
    resampled onto the measured times -- and a measured instant outside the
    provider's span yields ``None``, never an extrapolated value.
    """
    out: list[float | None] = []
    n = len(times)
    j = 0
    for target in at:
        if target < times[0] or target > times[-1]:
            out.append(None)
            continue
        while j + 1 < n and times[j + 1] < target:
            j += 1
        k = min(j + 1, n - 1)
        if k == j or times[k] == times[j]:
            out.append(float(values[j]))
            continue
        weight = (target - times[j]) / (times[k] - times[j])
        out.append(float(values[j]) + weight * (float(values[k]) - float(values[j])))
    return out


def write_evidence(name: str, record: dict[str, Any]) -> str:
    os.makedirs(EVIDENCE, exist_ok=True)
    path = os.path.join(EVIDENCE, name)
    payload = json.dumps(record, indent=1, allow_nan=False).encode("utf-8") + b"\n"
    with open(path, "wb") as handle:
        handle.write(payload)
    return path
