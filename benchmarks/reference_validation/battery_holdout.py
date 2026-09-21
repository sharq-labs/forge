"""Holdout campaign for Forge's existing affine Rint battery model.

A derived/mirrored CSV may be used to discover model/calibration failures, but
it is not a trusted validation issuer. Trusted experimental validation requires
a reviewed NASA snapshot, operating-point binding, uncertainty and tolerance
policy.

The runner is intentionally fail-closed. If unconstrained calibration produces
a non-physical battery (for example negative internal resistance), Forge is not
asked to simulate it. A resistance measured independently (for example from an
EIS record preceding the discharge) may be supplied explicitly; then only the
OCV chord is calibrated on the training prefix.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from engcore.domains.battery.cell import CellSpecification, DischargeLoad
from engcore.domains.battery.solver import evaluate_step
from engcore.scientific.units.quantity import Quantity

NASA_RATED_CAPACITY_AH = 2.0


@dataclass(frozen=True)
class BatterySample:
    cycle: int
    time_s: float
    voltage_v: float
    current_a: float
    temperature_c: float


@dataclass(frozen=True)
class CalibratedRint:
    nominal_capacity_ah: float
    open_circuit_voltage_at_empty_v: float
    open_circuit_voltage_at_full_v: float
    internal_resistance_ohm: float
    resistance_source: str

    @property
    def hard_physical_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if self.nominal_capacity_ah <= 0.0:
            issues.append("nominal capacity is not positive")
        if self.internal_resistance_ohm <= 0.0:
            issues.append("internal resistance is not positive")
        if self.open_circuit_voltage_at_full_v <= self.open_circuit_voltage_at_empty_v:
            issues.append("full OCV is not above empty OCV")
        return tuple(issues)

    @property
    def lithium_ion_plausibility_warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        if not 2.0 < self.open_circuit_voltage_at_empty_v < 4.0:
            warnings.append("empty OCV lies outside a broad Li-ion plausibility screen")
        if not 3.5 < self.open_circuit_voltage_at_full_v < 4.5:
            warnings.append("full OCV lies outside a broad Li-ion plausibility screen")
        return tuple(warnings)


@dataclass(frozen=True)
class VoltageMetrics:
    n: int
    rmse_v: float
    mae_v: float
    bias_v: float
    max_abs_v: float
    within_50mv_fraction: float
    within_100mv_fraction: float


def load_nasa_style_csv(path: str | Path) -> tuple[BatterySample, ...]:
    samples: list[BatterySample] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "cycle", "voltage_measured", "current_measured",
            "temperature_measured", "time",
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"NASA-style CSV is missing columns: {sorted(missing)}")
        for row in reader:
            sample = BatterySample(
                cycle=int(row["cycle"]),
                time_s=float(row["time"]),
                voltage_v=float(row["voltage_measured"]),
                # NASA discharge current is conventionally negative. Forge
                # declares discharge current positive out of the cell.
                current_a=abs(float(row["current_measured"])),
                temperature_c=float(row["temperature_measured"]),
            )
            numbers = (
                sample.time_s, sample.voltage_v,
                sample.current_a, sample.temperature_c,
            )
            if not all(math.isfinite(value) for value in numbers):
                raise ValueError("NASA-style CSV contains non-finite values")
            if sample.current_a <= 0.0:
                raise ValueError("discharge current must be positive after sign normalization")
            samples.append(sample)
    if not samples:
        raise ValueError("NASA-style CSV contains no samples")
    return tuple(samples)


def _cycle(
    samples: Iterable[BatterySample], cycle_id: int
) -> tuple[BatterySample, ...]:
    result = tuple(sorted(
        (sample for sample in samples if sample.cycle == cycle_id),
        key=lambda sample: sample.time_s,
    ))
    if len(result) < 3:
        raise ValueError(f"cycle {cycle_id} has fewer than three samples")
    return result


def _soc_coordinates(
    cycle: tuple[BatterySample, ...],
    nominal_capacity_ah: float,
) -> tuple[float, ...]:
    if nominal_capacity_ah <= 0.0:
        raise ValueError("nominal_capacity_ah must be positive")
    soc = 1.0
    values = [soc]
    for previous, sample in zip(cycle, cycle[1:]):
        dt_h = (sample.time_s - previous.time_s) / 3600.0
        if dt_h <= 0.0:
            raise ValueError("cycle time must increase strictly")
        # Right-hold: the sample current is the piecewise-constant current over
        # the preceding interval. Production execution below uses the same rule.
        soc -= sample.current_a * dt_h / nominal_capacity_ah
        values.append(soc)
    return tuple(values)


def _unconstrained_calibration(
    cycle: tuple[BatterySample, ...],
    *,
    split: int,
    nominal_capacity_ah: float,
) -> CalibratedRint:
    soc = _soc_coordinates(cycle, nominal_capacity_ah)
    design = np.asarray(
        [[1.0, soc[index], cycle[index].current_a] for index in range(1, split)],
        dtype=float,
    )
    observed = np.asarray(
        [cycle[index].voltage_v for index in range(1, split)], dtype=float
    )
    intercept, slope, current_coefficient = np.linalg.lstsq(
        design, observed, rcond=None
    )[0]
    return CalibratedRint(
        nominal_capacity_ah=nominal_capacity_ah,
        open_circuit_voltage_at_empty_v=float(intercept),
        open_circuit_voltage_at_full_v=float(intercept + slope),
        internal_resistance_ohm=float(-current_coefficient),
        resistance_source="estimated_from_training_voltage",
    )


def _calibrate_ocv_with_fixed_resistance(
    cycle: tuple[BatterySample, ...],
    *,
    split: int,
    nominal_capacity_ah: float,
    internal_resistance_ohm: float,
) -> CalibratedRint:
    if not math.isfinite(internal_resistance_ohm) or internal_resistance_ohm <= 0.0:
        raise ValueError("independent internal resistance must be finite and positive")
    soc = _soc_coordinates(cycle, nominal_capacity_ah)
    design = np.asarray(
        [[1.0, soc[index]] for index in range(1, split)], dtype=float
    )
    # OCV = V_terminal + I R.
    observed_ocv = np.asarray(
        [
            cycle[index].voltage_v
            + cycle[index].current_a * internal_resistance_ohm
            for index in range(1, split)
        ],
        dtype=float,
    )
    intercept, slope = np.linalg.lstsq(design, observed_ocv, rcond=None)[0]
    return CalibratedRint(
        nominal_capacity_ah=nominal_capacity_ah,
        open_circuit_voltage_at_empty_v=float(intercept),
        open_circuit_voltage_at_full_v=float(intercept + slope),
        internal_resistance_ohm=float(internal_resistance_ohm),
        resistance_source="independent_measurement",
    )


def calibrate_affine_rint(
    cycle: tuple[BatterySample, ...],
    *,
    calibration_fraction: float = 0.5,
    nominal_capacity_ah: float = NASA_RATED_CAPACITY_AH,
    independent_resistance_ohm: float | None = None,
) -> tuple[CalibratedRint, int]:
    if not 0.1 <= calibration_fraction <= 0.9:
        raise ValueError("calibration_fraction must lie in [0.1, 0.9]")
    split = max(3, min(len(cycle) - 1, int(len(cycle) * calibration_fraction)))
    if independent_resistance_ohm is None:
        calibrated = _unconstrained_calibration(
            cycle, split=split, nominal_capacity_ah=nominal_capacity_ah
        )
    else:
        calibrated = _calibrate_ocv_with_fixed_resistance(
            cycle,
            split=split,
            nominal_capacity_ah=nominal_capacity_ah,
            internal_resistance_ohm=independent_resistance_ohm,
        )
    return calibrated, split


def _direct_voltage_predictions(
    cycle: tuple[BatterySample, ...],
    parameters: CalibratedRint,
) -> tuple[tuple[int, float, float], ...]:
    """Diagnostic only; uses the declared equation without constructing Forge records."""
    soc = _soc_coordinates(cycle, parameters.nominal_capacity_ah)
    return tuple(
        (
            index,
            parameters.open_circuit_voltage_at_empty_v
            + (
                parameters.open_circuit_voltage_at_full_v
                - parameters.open_circuit_voltage_at_empty_v
            )
            * soc[index]
            - cycle[index].current_a * parameters.internal_resistance_ohm,
            cycle[index].voltage_v,
        )
        for index in range(1, len(cycle))
    )


def _metrics(rows: Iterable[tuple[int, float, float]]) -> VoltageMetrics:
    rows = tuple(rows)
    if not rows:
        raise ValueError("metrics require at least one row")
    errors = np.asarray([predicted - measured for _, predicted, measured in rows])
    absolute = np.abs(errors)
    return VoltageMetrics(
        n=int(errors.size),
        rmse_v=float(np.sqrt(np.mean(errors * errors))),
        mae_v=float(np.mean(absolute)),
        bias_v=float(np.mean(errors)),
        max_abs_v=float(np.max(absolute)),
        within_50mv_fraction=float(np.mean(absolute <= 0.050)),
        within_100mv_fraction=float(np.mean(absolute <= 0.100)),
    )


def _forge_predictions(
    cycle: tuple[BatterySample, ...],
    parameters: CalibratedRint,
) -> tuple[tuple[int, float, float], ...]:
    cell = CellSpecification(
        cell_id="nasa-holdout-rint",
        nominal_capacity=Quantity(parameters.nominal_capacity_ah, "ampere_hour"),
        internal_resistance=Quantity(parameters.internal_resistance_ohm, "ohm"),
        open_circuit_voltage_at_full=Quantity(
            parameters.open_circuit_voltage_at_full_v, "volt"
        ),
        open_circuit_voltage_at_empty=Quantity(
            parameters.open_circuit_voltage_at_empty_v, "volt"
        ),
        coulombic_efficiency=Quantity(1.0, "dimensionless"),
        chemistry="lithium_ion",
    )
    soc = 1.0
    predictions: list[tuple[int, float, float]] = []
    for index in range(1, len(cycle)):
        previous = cycle[index - 1]
        sample = cycle[index]
        dt_s = sample.time_s - previous.time_s
        load = DischargeLoad(
            load_id=f"cycle-{sample.cycle}-sample-{index}",
            current=Quantity(sample.current_a, "ampere"),
            initial_state_of_charge=Quantity(soc, "dimensionless"),
            cell_temperature=Quantity(sample.temperature_c, "degC"),
            duration=Quantity(dt_s, "second"),
        )
        evaluated = evaluate_step(cell, load)
        soc = evaluated.final_state_of_charge
        predictions.append(
            (index, evaluated.terminal_voltage, sample.voltage_v)
        )
    return tuple(predictions)


def run_holdout_campaign(
    path: str | Path,
    *,
    calibration_cycle: int = 0,
    transfer_cycle: int = 1,
    calibration_fraction: float = 0.5,
    nominal_capacity_ah: float = NASA_RATED_CAPACITY_AH,
    independent_resistance_ohm: float | None = None,
) -> dict[str, object]:
    samples = load_nasa_style_csv(path)
    calibration = _cycle(samples, calibration_cycle)
    transfer = _cycle(samples, transfer_cycle)
    parameters, split = calibrate_affine_rint(
        calibration,
        calibration_fraction=calibration_fraction,
        nominal_capacity_ah=nominal_capacity_ah,
        independent_resistance_ohm=independent_resistance_ohm,
    )

    direct = _direct_voltage_predictions(calibration, parameters)
    training = tuple(row for row in direct if row[0] < split)
    holdout = tuple(row for row in direct if row[0] >= split)

    report: dict[str, object] = {
        "campaign": "nasa_battery_affine_rint_holdout",
        "authority": (
            "NASA Prognostics Center of Excellence Battery Data Set "
            "(Saha & Goebel, 2007)"
        ),
        "evidence_status": "comparison_only_not_trusted_validation",
        "protocol": {
            "calibration_cycle": calibration_cycle,
            "transfer_cycle": transfer_cycle,
            "calibration_fraction": calibration_fraction,
            "nominal_capacity_ah": nominal_capacity_ah,
            "current_sign": "absolute measured current -> positive discharge",
            "current_integration": "right-hold piecewise constant",
        },
        "fitted_parameters": asdict(parameters),
        "hard_physical_issues": list(parameters.hard_physical_issues),
        "lithium_ion_plausibility_warnings": list(
            parameters.lithium_ion_plausibility_warnings
        ),
        "training_diagnostic": asdict(_metrics(training)),
        "holdout_diagnostic": asdict(_metrics(holdout)),
    }

    if parameters.hard_physical_issues:
        report["execution_status"] = "calibration_rejected_before_forge_execution"
        report["reason"] = (
            "The calibration would construct a non-physical CellSpecification; "
            "the production battery domain is therefore not executed."
        )
        return report

    forge_calibration = _forge_predictions(calibration, parameters)
    forge_transfer = _forge_predictions(transfer, parameters)
    report["execution_status"] = "forge_executed"
    report["forge_training"] = asdict(
        _metrics(row for row in forge_calibration if row[0] < split)
    )
    report["forge_holdout_same_cycle"] = asdict(
        _metrics(row for row in forge_calibration if row[0] >= split)
    )
    report["forge_transfer_cycle"] = asdict(_metrics(forge_transfer))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--calibration-cycle", type=int, default=0)
    parser.add_argument("--transfer-cycle", type=int, default=1)
    parser.add_argument("--calibration-fraction", type=float, default=0.5)
    parser.add_argument("--capacity-ah", type=float, default=NASA_RATED_CAPACITY_AH)
    parser.add_argument("--internal-resistance-ohm", type=float)
    parser.add_argument("--output")
    args = parser.parse_args()

    report = run_holdout_campaign(
        args.csv,
        calibration_cycle=args.calibration_cycle,
        transfer_cycle=args.transfer_cycle,
        calibration_fraction=args.calibration_fraction,
        nominal_capacity_ah=args.capacity_ah,
        independent_resistance_ohm=args.internal_resistance_ohm,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
