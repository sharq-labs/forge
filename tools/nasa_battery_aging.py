"""Deterministic ingestion for the NASA PCoE Li-ion Battery Aging MATLAB files.

This module is tooling, not battery physics. It preserves the NASA-declared
cycle boundary and raw channels while attaching a byte-level source receipt.
It deliberately does not infer SOC, pulse/rest labels, sensor uncertainty, or
1RC parameters.

NASA documents each cell file as a top-level cell variable containing a
``cycle`` structure array. Each cycle declares ``type`` (charge, discharge or
impedance), ``ambient_temperature``, ``time`` and ``data``. Operational
charge/discharge cycles expose measured voltage/current/temperature and a time
vector; discharge also exposes delivered capacity.

The importer is fail-closed:
* raw bytes are SHA-256 receipted before parsing;
* malformed required channels are refused;
* sample vectors in charge/discharge cycles must have equal length;
* no current sign normalization is performed;
* no sub-cycle segmentation is invented.

The canonical JSON is deterministic for the same parsed MATLAB content. It is
an ingestion record, not measurement admissibility: the NASA catalog does not
state calibrated per-sample sensor uncertainty, so ``measurement_uncertainty``
is always ``"UNKNOWN"`` here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.io import loadmat


SCHEMA = "forge.nasa_battery_aging_ingestion/1"
PARSER_ID = "tools.nasa_battery_aging/1"
NASA_DATASET_ID = "nasa.li_ion_battery_aging"
NASA_RESOURCE_URL = (
    "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
)
_ALLOWED_CYCLE_TYPES = frozenset({"charge", "discharge", "impedance"})
_OPERATIONAL_REQUIRED_CHANNELS = (
    "Voltage_measured",
    "Current_measured",
    "Temperature_measured",
    "Time",
)


class NasaBatteryIngestionError(ValueError):
    """The raw dataset cannot be represented without guessing."""


@dataclass(frozen=True)
class SourceReceipt:
    filename: str
    byte_count: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }


def source_receipt(path: str | Path) -> SourceReceipt:
    """Hash the exact bytes that are about to be parsed."""
    source = Path(path)
    digest = hashlib.sha256()
    byte_count = 0
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            byte_count += len(block)
    return SourceReceipt(source.name, byte_count, digest.hexdigest())


def _python_scalar(value: Any, *, where: str) -> float:
    array = np.asarray(value)
    if array.size != 1:
        raise NasaBatteryIngestionError(
            f"{where} must be a scalar; got shape {array.shape}"
        )
    scalar = array.reshape(-1)[0]
    if isinstance(scalar, np.generic):
        scalar = scalar.item()
    if isinstance(scalar, complex):
        if scalar.imag != 0:
            raise NasaBatteryIngestionError(
                f"{where} must be real; got {scalar!r}"
            )
        scalar = scalar.real
    try:
        number = float(scalar)
    except (TypeError, ValueError) as exc:
        raise NasaBatteryIngestionError(
            f"{where} must be numeric; got {scalar!r}"
        ) from exc
    if not math.isfinite(number):
        raise NasaBatteryIngestionError(
            f"{where} must be finite; got {number!r}"
        )
    return number


def _encode_number(value: Any, *, where: str) -> float | dict[str, float]:
    """JSON-safe finite real/complex scalar without changing its value."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, complex):
        real = float(value.real)
        imag = float(value.imag)
        if not math.isfinite(real) or not math.isfinite(imag):
            raise NasaBatteryIngestionError(
                f"{where} contains a non-finite complex value"
            )
        return {"real": real, "imag": imag}
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NasaBatteryIngestionError(
            f"{where} contains a non-numeric value {value!r}"
        ) from exc
    if not math.isfinite(number):
        raise NasaBatteryIngestionError(
            f"{where} contains a non-finite value {number!r}"
        )
    return number


def _channel(
    value: Any, *, where: str
) -> list[float | dict[str, float]] | float | dict[str, float]:
    array = np.asarray(value)
    if array.ndim == 0:
        return _encode_number(array.item(), where=where)
    flattened = array.reshape(-1)
    return [
        _encode_number(item, where=f"{where}[{index}]")
        for index, item in enumerate(flattened)
    ]


def _sequence(value: Any, *, where: str) -> list[Any]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, np.ndarray):
        return list(value.reshape(-1))
    if isinstance(value, (list, tuple)):
        return list(value)
    raise NasaBatteryIngestionError(
        f"{where} must be a structure array or sequence; got {type(value).__name__}"
    )


def _record(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NasaBatteryIngestionError(
            f"{where} must be a structure; got {type(value).__name__}"
        )
    return value


def _cycle_type(value: Any, *, where: str) -> str:
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise NasaBatteryIngestionError(
                f"{where} must contain one operation type"
            )
        value = value.reshape(-1)[0]
    if isinstance(value, np.generic):
        value = value.item()
    cycle_type = str(value).strip().lower()
    if cycle_type not in _ALLOWED_CYCLE_TYPES:
        raise NasaBatteryIngestionError(
            f"{where} has unsupported cycle type {cycle_type!r}; "
            f"expected one of {sorted(_ALLOWED_CYCLE_TYPES)}"
        )
    return cycle_type


def _matlab_date_vector(value: Any, *, where: str) -> list[float]:
    array = np.asarray(value).reshape(-1)
    if array.size != 6:
        raise NasaBatteryIngestionError(
            f"{where} must be the six-element MATLAB date vector; got {array.size}"
        )
    return [
        _python_scalar(item, where=f"{where}[{index}]")
        for index, item in enumerate(array)
    ]


def _validate_operational_channels(
    data: Mapping[str, Any], *, cycle_type: str, where: str
) -> None:
    missing = [
        name for name in _OPERATIONAL_REQUIRED_CHANNELS if name not in data
    ]
    if missing:
        raise NasaBatteryIngestionError(
            f"{where} {cycle_type} cycle is missing required channels {missing}"
        )

    lengths: dict[str, int] = {}
    for name in _OPERATIONAL_REQUIRED_CHANNELS:
        array = np.asarray(data[name]).reshape(-1)
        lengths[name] = int(array.size)
        for index, item in enumerate(array):
            _encode_number(item, where=f"{where}.data.{name}[{index}]")
    if len(set(lengths.values())) != 1:
        raise NasaBatteryIngestionError(
            f"{where} sample channels are not aligned: {lengths}"
        )
    if next(iter(lengths.values()), 0) == 0:
        raise NasaBatteryIngestionError(
            f"{where} has no operational samples"
        )

    time = np.asarray(data["Time"], dtype=float).reshape(-1)
    if not np.all(np.isfinite(time)):
        raise NasaBatteryIngestionError(
            f"{where}.data.Time contains non-finite values"
        )
    if np.any(np.diff(time) < 0):
        raise NasaBatteryIngestionError(
            f"{where}.data.Time must be non-decreasing"
        )

    if cycle_type == "discharge":
        if "Capacity" not in data:
            raise NasaBatteryIngestionError(
                f"{where} discharge cycle has no Capacity"
            )
        capacity = _python_scalar(
            data["Capacity"], where=f"{where}.data.Capacity"
        )
        if capacity <= 0:
            raise NasaBatteryIngestionError(
                f"{where}.data.Capacity must be strictly positive"
            )


def _canonical_cycle(raw_cycle: Any, index: int) -> dict[str, Any]:
    where = f"cycle[{index}]"
    cycle = _record(raw_cycle, where=where)
    for required in ("type", "ambient_temperature", "time", "data"):
        if required not in cycle:
            raise NasaBatteryIngestionError(
                f"{where} is missing required field {required!r}"
            )

    cycle_type = _cycle_type(cycle["type"], where=f"{where}.type")
    ambient = _python_scalar(
        cycle["ambient_temperature"],
        where=f"{where}.ambient_temperature",
    )
    started = _matlab_date_vector(cycle["time"], where=f"{where}.time")
    data = _record(cycle["data"], where=f"{where}.data")

    if cycle_type in {"charge", "discharge"}:
        _validate_operational_channels(
            data, cycle_type=cycle_type, where=where
        )

    channels = {
        str(name): _channel(value, where=f"{where}.data.{name}")
        for name, value in sorted(data.items(), key=lambda item: str(item[0]))
    }
    record: dict[str, Any] = {
        "cycle_index": index,
        "cycle_type": cycle_type,
        "ambient_temperature_degC": ambient,
        "start_time_matlab_date_vector": started,
        "channels": channels,
        "measurement_uncertainty": "UNKNOWN",
    }
    if cycle_type in {"charge", "discharge"}:
        record["sample_count"] = len(channels["Time"])
        record["current_sign_convention"] = (
            "NASA Current_measured preserved exactly as recorded; "
            "Forge performs no sign normalization during ingestion"
        )
    if cycle_type == "discharge":
        record["delivered_capacity_Ah"] = _python_scalar(
            data["Capacity"], where=f"{where}.data.Capacity"
        )
    return record


def _select_cell(
    loaded: Mapping[str, Any], requested_cell_id: str | None
) -> tuple[str, Mapping[str, Any]]:
    payload = {
        str(key): value
        for key, value in loaded.items()
        if not str(key).startswith("__")
    }
    if requested_cell_id is not None:
        try:
            value = payload[requested_cell_id]
        except KeyError as exc:
            raise NasaBatteryIngestionError(
                f"MAT file has no cell variable {requested_cell_id!r}; "
                f"available variables: {sorted(payload)}"
            ) from exc
        return requested_cell_id, _record(
            value, where=f"cell {requested_cell_id!r}"
        )
    if len(payload) != 1:
        raise NasaBatteryIngestionError(
            "expected exactly one non-metadata cell variable; "
            f"found {sorted(payload)}. Pass --cell-id explicitly if needed"
        )
    cell_id, value = next(iter(payload.items()))
    return cell_id, _record(value, where=f"cell {cell_id!r}")


def canonicalize_loaded_mat(
    loaded: Mapping[str, Any],
    *,
    receipt: SourceReceipt,
    cell_id: str | None = None,
) -> dict[str, Any]:
    """Convert ``scipy.io.loadmat(..., simplify_cells=True)`` output."""
    selected_id, cell = _select_cell(loaded, cell_id)
    if "cycle" not in cell:
        raise NasaBatteryIngestionError(
            f"cell {selected_id!r} has no 'cycle' structure array"
        )
    raw_cycles = _sequence(
        cell["cycle"], where=f"cell {selected_id!r}.cycle"
    )
    cycles = [
        _canonical_cycle(raw_cycle, index)
        for index, raw_cycle in enumerate(raw_cycles)
    ]
    if not cycles:
        raise NasaBatteryIngestionError(
            f"cell {selected_id!r} contains no cycles"
        )

    record = {
        "schema": SCHEMA,
        "parser": PARSER_ID,
        "dataset_id": NASA_DATASET_ID,
        "resource_url": NASA_RESOURCE_URL,
        "source": receipt.to_dict(),
        "cell_id": selected_id,
        "cycle_count": len(cycles),
        "cycle_types": {
            kind: sum(1 for cycle in cycles if cycle["cycle_type"] == kind)
            for kind in sorted(_ALLOWED_CYCLE_TYPES)
        },
        "cycles": cycles,
        "scientific_limits": {
            "soc": "NOT_INFERRED",
            "pulse_rest_segments": "NOT_INFERRED",
            "sensor_uncertainty": "UNKNOWN",
            "one_rc_parameters": "NOT_IDENTIFIED",
        },
    }
    canonical = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    record["canonical_sha256"] = hashlib.sha256(canonical).hexdigest()
    return record


def ingest_mat_file(
    path: str | Path, *, cell_id: str | None = None
) -> dict[str, Any]:
    """Receipt and parse one NASA cell MAT file."""
    source = Path(path)
    receipt = source_receipt(source)
    try:
        loaded = loadmat(source, simplify_cells=True)
    except Exception as exc:
        raise NasaBatteryIngestionError(
            f"could not parse MATLAB file {source}: {exc}"
        ) from exc
    return canonicalize_loaded_mat(
        loaded, receipt=receipt, cell_id=cell_id
    )


def write_canonical_json(
    record: Mapping[str, Any], output: str | Path
) -> None:
    Path(output).write_text(
        json.dumps(
            record,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Receipt and deterministically canonicalize one NASA PCoE "
            "Li-ion Battery Aging MATLAB cell file."
        )
    )
    parser.add_argument("mat_file", type=Path)
    parser.add_argument("--cell-id")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    record = ingest_mat_file(args.mat_file, cell_id=args.cell_id)
    write_canonical_json(record, args.out)
    print(
        f"{record['cell_id']}: {record['cycle_count']} cycles; "
        f"source sha256={record['source']['sha256']}; "
        f"canonical sha256={record['canonical_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
