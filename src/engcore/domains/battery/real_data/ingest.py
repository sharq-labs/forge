"""Canonical ingestion of measured battery time series.

This is the one place in the battery domain that turns published raw bytes
into numbers. It owns three things and nothing else:

* **identity** -- every raw file is bound to a pinned
  :class:`~engcore.scientific.corpus.SourceSnapshot` (SHA-256 and byte count)
  before a single field is parsed, and a dataset receipt is a digest over
  those pins, the declared format, the parser and normalization versions and
  the normalized content. No machine path and no wall-clock time enters it,
  so re-ingesting identical bytes with the same versions reproduces the same
  identity on any machine;
* **lineage** -- every normalized channel records its source column, source
  unit, canonical unit, the transformation applied and the basis for the
  declaration. A channel is MEASURED (a sensor channel as published) or
  SOURCE_COMPUTED (computed by the instrument or publisher, e.g. a tester's
  ampere-hour counter). DERIVED quantities -- state of charge above all --
  are never source channels: they live in :class:`DerivedChannel`, which
  names its method, version, inputs and assumptions;
* **refusal** -- nothing is cleaned. A missing or unknown column, an empty,
  NaN or infinite field, an ambiguous or dimensionally wrong unit, a
  non-increasing time stamp, mixed line endings, or data that contradict the
  declared units or sign convention refuse the whole file. No row is dropped,
  so the receipt's dropped-row count is a statement, not a filter.

What this module does not do: segment the record, judge data quality,
choose a calibration split or fit any model. Those read the
:class:`BatteryTimeSeries` this module returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

import numpy as np

from ....scientific.corpus import CorpusError, ReferenceSource, SourceSnapshot
from ....scientific.errors import InvalidScientificProblem
from ....scientific.serialization import schema_string
from ....scientific.units.quantity import Quantity, dimensionality

FORMAT_SCHEMA = schema_string("battery_raw_source_format")
SERIES_SCHEMA = schema_string("battery_normalized_time_series")
FILE_RECEIPT_SCHEMA = schema_string("battery_raw_file_receipt")
DATASET_RECEIPT_SCHEMA = schema_string("battery_dataset_receipt")
DERIVED_CHANNEL_SCHEMA = schema_string("battery_derived_channel")

#: Bumped whenever parsing changes what a byte sequence means.
PARSER_VERSION = "engcore.domains.battery.real_data.csv_parser/1"
#: Bumped whenever normalization changes a normalized value.
NORMALIZATION_VERSION = "engcore.domains.battery.real_data.normalization/1"

_RECEIPT_TAG = "engcore.domains.battery.real_data.dataset_receipt/1"
_SERIES_TAG = "engcore.domains.battery.real_data.normalized_series/1"
_FORMAT_TAG = "engcore.domains.battery.real_data.source_format/1"
_DERIVED_TAG = "engcore.domains.battery.real_data.derived_channel/1"


class RealDataError(InvalidScientificProblem):
    """Raw battery data cannot be represented without inventing a fact."""


class Channel(str, Enum):
    """The closed vocabulary of source channels.

    State of charge is deliberately absent: no battery tester measures it.
    A value computed from current and an assumed capacity is a
    :class:`DerivedChannel`, never a member of this enum.
    """

    TIME = "time"
    CURRENT = "current"
    VOLTAGE = "voltage"
    TEMPERATURE = "temperature"
    CHARGE_COUNTER = "charge_counter"


#: Canonical unit of every channel. Current is positive for discharge, the
#: convention of :mod:`engcore.domains.battery.thevenin`; the charge counter
#: is net charge INTO the cell since the counter's zero.
CANONICAL_UNITS: Mapping[Channel, str] = {
    Channel.TIME: "second",
    Channel.CURRENT: "ampere",
    Channel.VOLTAGE: "volt",
    Channel.TEMPERATURE: "kelvin",
    Channel.CHARGE_COUNTER: "ampere_hour",
}
REQUIRED_CHANNELS = (Channel.TIME, Channel.CURRENT, Channel.VOLTAGE)

#: Unit symbols that mean different things in battery data. ``C`` is coulomb
#: to the unit system, degrees Celsius to a thermocouple log and a C-rate to
#: a test plan; ``F`` is farad or Fahrenheit. A declaration must spell the
#: unit out.
AMBIGUOUS_UNIT_SYMBOLS = frozenset({"C", "c", "deg", "F", "f"})

_SOC_NAMES = frozenset({"soc", "state_of_charge", "stateofcharge", "z"})
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


class LineageKind(str, Enum):
    MEASURED = "measured"
    SOURCE_COMPUTED = "source_computed"
    DERIVED = "derived"


class CurrentSign(str, Enum):
    """Which direction a positive source current flows."""

    POSITIVE_IS_DISCHARGE = "positive_is_discharge"
    POSITIVE_IS_CHARGE = "positive_is_charge"


CANONICAL_CURRENT_SIGN = CurrentSign.POSITIVE_IS_DISCHARGE


def _text(value: object, *, label: str) -> str:
    result = str(value).strip()
    if not result:
        raise RealDataError(f"{label} must be a non-empty string")
    return result


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True)


def _tagged_digest(tag: str, value: Any) -> str:
    return hashlib.sha256(tag.encode("utf-8") + b"\x00" + _canonical_json(value).encode("utf-8")).hexdigest()


def _channel(value: object) -> Channel:
    if isinstance(value, Channel):
        return value
    name = str(value).strip()
    if name.lower().replace(" ", "_") in _SOC_NAMES:
        raise RealDataError(
            f"{name!r} cannot be a source channel: state of charge is not measured by any tester. "
            "It may enter only as a DerivedChannel that names its method, inputs and assumptions"
        )
    try:
        return Channel(name)
    except ValueError as exc:
        raise RealDataError(
            f"unknown channel {name!r}; source channels are {[c.value for c in Channel]}"
        ) from exc


def _declared_unit(unit: object, channel: Channel, *, label: str) -> str:
    spelled = str(unit).strip() if unit is not None else ""
    if not spelled:
        raise RealDataError(f"{label}: no unit declared; a unit is never guessed")
    if spelled in AMBIGUOUS_UNIT_SYMBOLS:
        raise RealDataError(
            f"{label}: unit symbol {spelled!r} is ambiguous in battery data; spell the unit out "
            "(for example 'coulomb', 'degC', 'kelvin', 'farad')"
        )
    try:
        probe = Quantity(1.0, spelled)
    except Exception as exc:  # the unit system's own refusal, re-raised as a data refusal
        raise RealDataError(f"{label}: unit {spelled!r} is not a unit the unit system knows: {exc}") from exc
    canonical = CANONICAL_UNITS[channel]
    if dimensionality(probe.units) != dimensionality(Quantity(1.0, canonical).units):
        raise RealDataError(
            f"{label}: unit {spelled!r} has dimension {dimensionality(probe.units)}, "
            f"but channel {channel.value!r} needs the dimension of {canonical!r}"
        )
    return spelled


@dataclass(frozen=True)
class ColumnDeclaration:
    """What one source column means, in which unit, and on what basis."""

    source_column: str
    channel: Channel
    source_unit: str
    lineage: LineageKind
    basis: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_column", _text(self.source_column, label="source_column"))
        object.__setattr__(self, "channel", _channel(self.channel))
        lineage = LineageKind(self.lineage)
        if lineage is LineageKind.DERIVED:
            raise RealDataError(
                f"column {self.source_column!r} is declared DERIVED; a derived quantity is not a source column"
            )
        object.__setattr__(self, "lineage", lineage)
        object.__setattr__(
            self,
            "source_unit",
            _declared_unit(self.source_unit, self.channel, label=f"column {self.source_column!r}"),
        )
        object.__setattr__(self, "basis", _text(self.basis, label=f"basis for column {self.source_column!r}"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "channel": self.channel.value,
            "source_unit": self.source_unit,
            "lineage": self.lineage.value,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class SourceFormat:
    """A versioned, explicit description of one raw file layout.

    ``header`` is the exact header record in order. Every header column must
    be declared: a column the format does not name is refused rather than
    silently ignored, and a declared column the file lacks is refused.
    """

    format_id: str
    format_version: int
    description: str
    header: tuple[str, ...]
    columns: tuple[ColumnDeclaration, ...]
    current_sign: CurrentSign
    current_sign_basis: str
    voltage_window_v: tuple[float, float]
    charge_counter_tolerance_fraction: float = 0.01
    delimiter: str = ","
    #: A "clear" current step for the passive sign test: large against the format's rest-current scatter and
    #: a voltage move far above its quantization. Declared per format, never universal.
    sign_test_current_step_a: float = 0.1
    sign_test_voltage_step_v: float = 1.0e-3

    def __post_init__(self) -> None:
        object.__setattr__(self, "format_id", _text(self.format_id, label="format_id"))
        if isinstance(self.format_version, bool) or int(self.format_version) != self.format_version or self.format_version < 1:
            raise RealDataError("format_version must be a positive integer")
        object.__setattr__(self, "format_version", int(self.format_version))
        object.__setattr__(self, "description", _text(self.description, label="format description"))
        header = tuple(_text(h, label="header column") for h in self.header)
        if len(set(header)) != len(header):
            raise RealDataError(f"format {self.format_id!r} repeats a header column")
        object.__setattr__(self, "header", header)
        columns = tuple(self.columns)
        if any(not isinstance(c, ColumnDeclaration) for c in columns):
            raise RealDataError("format columns must be ColumnDeclaration records")
        declared = [c.source_column for c in columns]
        if len(set(declared)) != len(declared):
            raise RealDataError(f"format {self.format_id!r} declares a column twice")
        channels = [c.channel for c in columns]
        if len(set(channels)) != len(channels):
            raise RealDataError(f"format {self.format_id!r} maps two columns to one channel")
        undeclared = sorted(set(header) - set(declared))
        if undeclared:
            raise RealDataError(f"format {self.format_id!r} leaves header columns {undeclared} undeclared")
        absent = sorted(set(declared) - set(header))
        if absent:
            raise RealDataError(f"format {self.format_id!r} declares columns {absent} that its header lacks")
        missing = [c.value for c in REQUIRED_CHANNELS if c not in channels]
        if missing:
            raise RealDataError(f"format {self.format_id!r} lacks required channels {missing}")
        object.__setattr__(self, "columns", tuple(sorted(columns, key=lambda c: header.index(c.source_column))))
        object.__setattr__(self, "current_sign", CurrentSign(self.current_sign))
        object.__setattr__(self, "current_sign_basis", _text(self.current_sign_basis, label="current_sign_basis"))
        low, high = (float(v) for v in self.voltage_window_v)
        if not (math.isfinite(low) and math.isfinite(high) and 0.0 <= low < high):
            raise RealDataError("voltage_window_v must be a finite (low, high) with 0 <= low < high")
        object.__setattr__(self, "voltage_window_v", (low, high))
        tol = float(self.charge_counter_tolerance_fraction)
        if not (math.isfinite(tol) and 0.0 < tol < 0.5):
            raise RealDataError("charge_counter_tolerance_fraction must lie in (0, 0.5)")
        object.__setattr__(self, "charge_counter_tolerance_fraction", tol)
        for label in ("sign_test_current_step_a", "sign_test_voltage_step_v"):
            value = float(getattr(self, label))
            if not (math.isfinite(value) and value > 0.0):
                raise RealDataError(f"{label} must be finite and positive")
            object.__setattr__(self, label, value)
        if self.delimiter not in (",", ";", "\t"):
            raise RealDataError(f"unsupported delimiter {self.delimiter!r}")

    def column_for(self, channel: Channel) -> ColumnDeclaration | None:
        for column in self.columns:
            if column.channel is channel:
                return column
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FORMAT_SCHEMA,
            "format_id": self.format_id,
            "format_version": self.format_version,
            "description": self.description,
            "header": list(self.header),
            "columns": [c.to_dict() for c in self.columns],
            "current_sign": self.current_sign.value,
            "current_sign_basis": self.current_sign_basis,
            "voltage_window_v": list(self.voltage_window_v),
            "charge_counter_tolerance_fraction": self.charge_counter_tolerance_fraction,
            "delimiter": self.delimiter,
            "sign_test_current_step_a": self.sign_test_current_step_a,
            "sign_test_voltage_step_v": self.sign_test_voltage_step_v,
        }

    @property
    def digest(self) -> str:
        return _tagged_digest(_FORMAT_TAG, self.to_dict())


@dataclass(frozen=True)
class ChannelLineage:
    channel: str
    kind: LineageKind
    source_column: str
    source_unit: str
    normalized_unit: str
    transformation: str
    basis: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", LineageKind(self.kind))

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "kind": self.kind.value,
            "source_column": self.source_column,
            "source_unit": self.source_unit,
            "normalized_unit": self.normalized_unit,
            "transformation": self.transformation,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class RawFileDeclaration:
    """Everything stated about one raw file BEFORE its bytes are read.

    ``group_id`` is the identity a calibration split assigns; ``cell_id`` and
    ``test_sequence_id`` are the physical keys a split policy reasons over.
    ``published_filename`` is the source's own name for the file -- a source
    fact, not a local path.
    """

    group_id: str
    cell_id: str
    test_sequence_id: str
    published_filename: str
    snapshot: SourceSnapshot
    source_format: SourceFormat

    def __post_init__(self) -> None:
        for label in ("group_id", "cell_id", "test_sequence_id", "published_filename"):
            object.__setattr__(self, label, _text(getattr(self, label), label=label))
        if "/" in self.published_filename or "\\" in self.published_filename:
            raise RealDataError("published_filename is the source's file name, never a path")
        if not isinstance(self.snapshot, SourceSnapshot):
            raise RealDataError("a raw file declaration needs a SourceSnapshot byte pin")
        if not isinstance(self.source_format, SourceFormat):
            raise RealDataError("a raw file declaration needs a SourceFormat")


@dataclass(frozen=True)
class BatteryTimeSeries:
    """One raw file after deterministic normalization: source channels only.

    ``row_index`` is the data-row position of every sample in the raw file,
    so a sample can always be traced to the bytes it came from. ``channels``
    holds canonical units (see :data:`CANONICAL_UNITS`).
    """

    group_id: str
    cell_id: str
    test_sequence_id: str
    raw_sha256: str
    row_index: tuple[int, ...]
    channels: Mapping[str, tuple[float, ...]]
    lineage: tuple[ChannelLineage, ...]

    def __post_init__(self) -> None:
        for label in ("group_id", "cell_id", "test_sequence_id", "raw_sha256"):
            object.__setattr__(self, label, _text(getattr(self, label), label=label))
        lineage = tuple(self.lineage)
        if any(item.kind is LineageKind.DERIVED for item in lineage):
            raise RealDataError(
                "a DERIVED channel cannot be stored among the source channels of a time series; "
                "keep it in a DerivedChannel"
            )
        channels: dict[str, tuple[float, ...]] = {}
        for name, values in dict(self.channels).items():
            channel = _channel(name)
            channels[channel.value] = tuple(float(v) for v in values)
        lineage_names = sorted(item.channel for item in lineage)
        if lineage_names != sorted(channels):
            raise RealDataError(
                f"lineage {lineage_names} does not describe exactly the stored channels {sorted(channels)}"
            )
        for channel in REQUIRED_CHANNELS:
            if channel.value not in channels:
                raise RealDataError(f"time series lacks required channel {channel.value!r}")
        lengths = {len(v) for v in channels.values()}
        rows = tuple(int(r) for r in self.row_index)
        if len(lengths) != 1 or len(rows) not in lengths:
            raise RealDataError("time series channels and row_index must have one common length")
        if not rows:
            raise RealDataError("a time series needs at least one sample")
        if any(b <= a for a, b in zip(rows, rows[1:])):
            raise RealDataError("row_index must be strictly increasing: the record order is the measurement order")
        for name, values in channels.items():
            if not all(math.isfinite(v) for v in values):
                raise RealDataError(f"channel {name!r} carries a non-finite value")
        time = channels[Channel.TIME.value]
        if any(b <= a for a, b in zip(time, time[1:])):
            raise RealDataError("time must be strictly increasing; duplicate or reversed stamps are ambiguous")
        object.__setattr__(self, "row_index", rows)
        object.__setattr__(self, "channels", dict(sorted(channels.items())))
        object.__setattr__(self, "lineage", tuple(sorted(lineage, key=lambda item: item.channel)))

    def __len__(self) -> int:
        return len(self.row_index)

    def array(self, channel: Channel | str) -> np.ndarray:
        name = _channel(channel.value if isinstance(channel, Channel) else channel).value
        if name not in self.channels:
            raise RealDataError(f"channel {name!r} is not a source channel of {self.group_id!r}")
        return np.asarray(self.channels[name], dtype=np.float64)

    def has(self, channel: Channel) -> bool:
        return channel.value in self.channels

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SERIES_SCHEMA,
            "group_id": self.group_id,
            "cell_id": self.cell_id,
            "test_sequence_id": self.test_sequence_id,
            "raw_sha256": self.raw_sha256,
            "row_index": list(self.row_index),
            "channels": {name: list(values) for name, values in self.channels.items()},
            "lineage": [item.to_dict() for item in self.lineage],
        }

    @property
    def normalized_digest(self) -> str:
        return _tagged_digest(_SERIES_TAG, self.to_dict())


@dataclass(frozen=True)
class RawFileReceipt:
    group_id: str
    cell_id: str
    test_sequence_id: str
    published_filename: str
    snapshot: SourceSnapshot
    format_id: str
    format_version: int
    format_digest: str
    line_terminator: str
    header: tuple[str, ...]
    raw_record_count: int
    normalized_record_count: int
    dropped_row_count: int
    dropped_row_reasons: Mapping[str, int]
    normalized_digest: str
    lineage: tuple[ChannelLineage, ...]
    consistency_checks: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FILE_RECEIPT_SCHEMA,
            "group_id": self.group_id,
            "cell_id": self.cell_id,
            "test_sequence_id": self.test_sequence_id,
            "published_filename": self.published_filename,
            "snapshot": self.snapshot.to_dict(),
            "format_id": self.format_id,
            "format_version": self.format_version,
            "format_digest": self.format_digest,
            "line_terminator": self.line_terminator,
            "header": list(self.header),
            "raw_record_count": self.raw_record_count,
            "normalized_record_count": self.normalized_record_count,
            "dropped_row_count": self.dropped_row_count,
            "dropped_row_reasons": dict(sorted(self.dropped_row_reasons.items())),
            "normalized_digest": self.normalized_digest,
            "lineage": [item.to_dict() for item in self.lineage],
            "consistency_checks": dict(sorted(self.consistency_checks.items())),
        }


@dataclass(frozen=True)
class BatteryDatasetReceipt:
    """The immutable identity of one ingested dataset.

    Its digest covers the source, every raw byte pin, the formats, the parser
    and normalization versions, every normalized-content digest, the record
    and drop counts and the declared assumptions. It covers no local path and
    no ingest time: those describe a machine, not the data.
    """

    dataset_id: str
    source: ReferenceSource
    files: tuple[RawFileReceipt, ...]
    declared_assumptions: tuple[str, ...]
    parser_version: str = PARSER_VERSION
    normalization_version: str = NORMALIZATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DATASET_RECEIPT_SCHEMA,
            "dataset_id": self.dataset_id,
            "source": self.source.to_dict(),
            "files": [item.to_dict() for item in self.files],
            "declared_assumptions": list(self.declared_assumptions),
            "parser_version": self.parser_version,
            "normalization_version": self.normalization_version,
            "identity_excludes": ["local file paths", "ingest wall-clock time"],
        }

    @property
    def digest(self) -> str:
        return _tagged_digest(_RECEIPT_TAG, self.to_dict())


@dataclass(frozen=True)
class BatteryDataset:
    """A receipt and the series it describes, bound one to one.

    Construction re-derives every series' normalized digest and compares it, with the raw-byte pin and the
    physical keys, against the receipt's own entry. A dataset whose series content is not the content its
    receipt names -- a held-out group's channels filed under a calibration group, an edited voltage -- cannot
    be built, so nothing downstream can carry the receipt's identity over other numbers.
    """

    receipt: BatteryDatasetReceipt
    series: tuple[BatteryTimeSeries, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, BatteryDatasetReceipt):
            raise RealDataError("a dataset needs its BatteryDatasetReceipt")
        series = tuple(self.series)
        if any(not isinstance(s, BatteryTimeSeries) for s in series):
            raise RealDataError("a dataset holds BatteryTimeSeries records")
        if len({f.group_id for f in self.receipt.files}) != len(self.receipt.files):
            raise RealDataError("the receipt lists one group_id twice; a receipt names each file once")
        for entry in self.receipt.files:
            try:
                entry.snapshot.require_from(self.receipt.source)
            except CorpusError as exc:
                raise RealDataError(str(exc)) from exc
        files = {f.group_id: f for f in self.receipt.files}
        groups = [s.group_id for s in series]
        if len(set(groups)) != len(groups) or set(groups) != set(files):
            raise RealDataError(
                f"dataset series {sorted(groups)} do not match the receipt's files {sorted(files)} one to one"
            )
        for item in series:
            entry = files[item.group_id]
            if item.normalized_digest != entry.normalized_digest:
                raise RealDataError(
                    f"series {item.group_id!r} is not the content its receipt names: its normalized digest "
                    f"{item.normalized_digest} differs from the receipt's {entry.normalized_digest}"
                )
            if item.raw_sha256 != entry.snapshot.snapshot_sha256:
                raise RealDataError(f"series {item.group_id!r} names raw bytes its receipt does not pin")
            if (item.cell_id, item.test_sequence_id) != (entry.cell_id, entry.test_sequence_id):
                raise RealDataError(f"series {item.group_id!r} changes the physical keys its receipt records")
        object.__setattr__(self, "series", series)

    def group(self, group_id: str) -> BatteryTimeSeries:
        for item in self.series:
            if item.group_id == group_id:
                return item
        raise RealDataError(f"dataset {self.receipt.dataset_id!r} has no group {group_id!r}")

    @property
    def group_ids(self) -> tuple[str, ...]:
        return tuple(item.group_id for item in self.series)


# ---------------------------------------------------------------------------
# Parsing and normalization
# ---------------------------------------------------------------------------

def _split_records(text: str) -> tuple[list[str], str]:
    if "\r\n" in text:
        terminator = "\r\n"
        remainder = text.replace("\r\n", "")
    else:
        terminator = "\n"
        remainder = text.replace("\n", "")
    if "\r" in remainder or (terminator == "\r\n" and "\n" in remainder):
        raise RealDataError("mixed line terminators: record boundaries are ambiguous")
    lines = text.split(terminator)
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines, ("CRLF" if terminator == "\r\n" else "LF")


def _parse(raw: bytes, fmt: SourceFormat) -> tuple[dict[str, list[float]], str, int]:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RealDataError(f"raw file is not ASCII text at byte {exc.start}") from exc
    lines, terminator = _split_records(text)
    if not lines:
        raise RealDataError("raw file is empty")
    header = tuple(cell.strip() for cell in lines[0].split(fmt.delimiter))
    if header != fmt.header:
        missing = [c for c in fmt.header if c not in header]
        extra = [c for c in header if c not in fmt.header]
        raise RealDataError(
            f"header {list(header)} does not match format {fmt.format_id!r}: "
            f"missing required source columns {missing}, undeclared columns {extra}"
        )
    values: dict[str, list[float]] = {name: [] for name in header}
    for row_number, line in enumerate(lines[1:]):
        if not line.strip():
            raise RealDataError(f"data row {row_number} is blank; a blank record is not a measurement")
        cells = line.split(fmt.delimiter)
        if len(cells) != len(header):
            raise RealDataError(f"data row {row_number} has {len(cells)} fields; the header has {len(header)}")
        for name, cell in zip(header, cells):
            token = cell.strip()
            if not _NUMBER.match(token):
                raise RealDataError(
                    f"data row {row_number}, column {name!r}: {token!r} is not a finite decimal number "
                    "(empty, NaN and infinite fields are refused, never repaired)"
                )
            number = float(token)
            if not math.isfinite(number):
                raise RealDataError(f"data row {row_number}, column {name!r}: {token!r} overflows to a non-finite value")
            values[name].append(number)
    count = len(lines) - 1
    if count < 2:
        raise RealDataError("a time series needs at least two data rows")
    return values, terminator, count


def _to_canonical(values: Sequence[float], unit: str, channel: Channel) -> list[float]:
    canonical = CANONICAL_UNITS[channel]
    # Element by element through the unit system: a Celsius column is affine,
    # and an affine conversion is never cached as a factor.
    return [Quantity(v, unit).magnitude_in(canonical) for v in values]


def passive_step_test(
    current_a: Sequence[float], voltage_v: Sequence[float], *, current_step_a: float, voltage_step_v: float
) -> tuple[int, int]:
    """(clear steps, steps where the voltage moves AGAINST the canonical discharge current).

    A cell is passive: across a current step its terminal voltage moves against the discharge current. A clear
    step changes the current by at least ``current_step_a`` and the voltage by at least ``voltage_step_v``.
    """
    clear, against, _, _ = _passive_steps(current_a, voltage_v, current_step_a, voltage_step_v)
    return int(clear.size), int(np.sum(against))


def _passive_steps(current_a, voltage_v, current_step_a: float, voltage_step_v: float):
    current = np.asarray(current_a, dtype=np.float64)
    voltage = np.asarray(voltage_v, dtype=np.float64)
    d_current = np.diff(current)
    d_voltage = np.diff(voltage)
    clear = np.flatnonzero((np.abs(d_current) >= current_step_a) & (np.abs(d_voltage) >= voltage_step_v))
    against = d_voltage[clear] * d_current[clear] < 0.0
    return clear, against, d_current, d_voltage


def _trapezoid_ah(time_s: np.ndarray, current_a: np.ndarray) -> np.ndarray:
    dt = np.diff(time_s)
    increments = 0.5 * (current_a[1:] + current_a[:-1]) * dt / 3600.0
    return np.concatenate([[0.0], np.cumsum(increments)])


def _normalize(
    values: Mapping[str, list[float]], fmt: SourceFormat
) -> tuple[dict[str, list[float]], list[ChannelLineage], dict[str, Any]]:
    channels: dict[str, list[float]] = {}
    lineage: list[ChannelLineage] = []
    checks: dict[str, Any] = {}
    for column in fmt.columns:
        canonical_unit = CANONICAL_UNITS[column.channel]
        converted = _to_canonical(values[column.source_column], column.source_unit, column.channel)
        transformation = (
            "identity" if column.source_unit == canonical_unit else f"unit conversion {column.source_unit} -> {canonical_unit}"
        )
        if column.channel is Channel.CURRENT and fmt.current_sign is not CANONICAL_CURRENT_SIGN:
            converted = [-v for v in converted]
            transformation += "; negated: source positive current is charge, canonical positive current is discharge"
        if column.channel is Channel.CHARGE_COUNTER and fmt.current_sign is CurrentSign.POSITIVE_IS_DISCHARGE:
            converted = [-v for v in converted]
            transformation += "; negated: canonical charge counter is net charge into the cell"
        channels[column.channel.value] = converted
        lineage.append(
            ChannelLineage(
                channel=column.channel.value,
                kind=column.lineage,
                source_column=column.source_column,
                source_unit=column.source_unit,
                normalized_unit=canonical_unit,
                transformation=transformation,
                basis=column.basis,
            )
        )

    time = np.asarray(channels[Channel.TIME.value])
    if time[0] < 0.0:
        raise RealDataError(f"elapsed time starts at {time[0]!r} s; a negative elapsed time is impossible")
    steps = np.diff(time)
    if np.any(steps <= 0.0):
        k = int(np.argmax(steps <= 0.0))
        raise RealDataError(
            f"time is not strictly increasing at data row {k + 1} ({time[k]!r} -> {time[k + 1]!r} s); "
            "duplicate or reversed stamps make the sample order ambiguous"
        )

    voltage = np.asarray(channels[Channel.VOLTAGE.value])
    low, high = fmt.voltage_window_v
    outside = np.flatnonzero((voltage < low) | (voltage > high))
    if outside.size:
        k = int(outside[0])
        raise RealDataError(
            f"voltage {voltage[k]!r} V at data row {k} lies outside the declared window {fmt.voltage_window_v} V; "
            "the declared voltage unit is contradicted by the data"
        )
    checks["voltage_window_v"] = list(fmt.voltage_window_v)
    checks["voltage_inside_window"] = True

    if Channel.CHARGE_COUNTER.value in channels:
        counter = np.asarray(channels[Channel.CHARGE_COUNTER.value])
        current = np.asarray(channels[Channel.CURRENT.value])
        expected = -_trapezoid_ah(time, current)  # canonical current is discharge-positive
        observed = counter - counter[0]
        span = float(np.ptp(observed))
        error = float(np.max(np.abs(observed - expected)))
        tolerance = fmt.charge_counter_tolerance_fraction * max(span, 1e-3)
        checks["charge_counter_span_ah"] = span
        checks["charge_counter_max_abs_error_ah"] = error
        checks["charge_counter_tolerance_ah"] = tolerance
        checks["charge_counter_integration"] = "trapezoidal integral of canonical current over the recorded time stamps"
        checks["charge_counter_scope"] = (
            "verifies the RATIO of the current and charge units together with the time unit, and that counter "
            "and current share one sign convention. It cannot detect a common scale error (a milliampere column "
            "beside a milliampere-hour counter declared as ampere and ampere_hour), and it cannot tell charge from "
            "discharge"
        )
        if not error <= tolerance:
            raise RealDataError(
                f"the source charge counter departs from the integral of the current by {error:.6g} Ah "
                f"(tolerance {tolerance:.6g} Ah over a {span:.6g} Ah span): the declared time, current or "
                "charge units, or the counter's sign relative to the current, are contradicted by the data"
            )

    # Which way is discharge is a physical fact about the cell, not about the file: a cell is passive, so
    # across a current step its terminal voltage moves AGAINST the discharge current. Every clear step in
    # the record (at least 0.1 A, and a voltage move of at least 1 mV) must agree.
    clear, against, d_current, d_voltage = _passive_steps(
        channels[Channel.CURRENT.value], voltage, fmt.sign_test_current_step_a, fmt.sign_test_voltage_step_v
    )
    checks["passive_step_test"] = {
        "steps": int(clear.size),
        "voltage_moves_against_canonical_current": int(np.sum(against)),
        "minimum_current_step_a": fmt.sign_test_current_step_a,
        "minimum_voltage_step_v": fmt.sign_test_voltage_step_v,
    }
    if clear.size and not np.all(against):
        bad = clear[~against]
        k = int(bad[0])
        raise RealDataError(
            f"the declared current sign contradicts the cell's passive step response: at data row {k + 1} the "
            f"canonical current changes by {d_current[k]:+.6g} A and the voltage by {d_voltage[k]:+.6g} V "
            f"({bad.size} of {clear.size} clear steps move the voltage WITH the discharge current)"
        )
    checks["current_sign"] = (
        f"verified: the voltage moves against the canonical current at all {clear.size} clear steps"
        if clear.size else "declared; not verifiable from this record (no clear current step)"
    )
    return channels, lineage, checks


def ingest_raw_file(raw: bytes, declaration: RawFileDeclaration) -> tuple[RawFileReceipt, BatteryTimeSeries]:
    """Verify, parse and normalize one raw file. Refuses rather than repairs."""

    if not isinstance(raw, (bytes, bytearray)):
        raise RealDataError("ingestion reads raw bytes, never decoded text")
    raw = bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    pin = declaration.snapshot
    if len(raw) != pin.byte_length or digest != pin.snapshot_sha256:
        raise RealDataError(
            f"raw bytes of {declaration.published_filename!r} do not match the pinned snapshot: "
            f"sha256 {digest} / {len(raw)} bytes against {pin.snapshot_sha256} / {pin.byte_length} bytes"
        )
    fmt = declaration.source_format
    values, terminator, count = _parse(raw, fmt)
    channels, lineage, checks = _normalize(values, fmt)
    series = BatteryTimeSeries(
        group_id=declaration.group_id,
        cell_id=declaration.cell_id,
        test_sequence_id=declaration.test_sequence_id,
        raw_sha256=digest,
        row_index=tuple(range(count)),
        channels=channels,
        lineage=tuple(lineage),
    )
    receipt = RawFileReceipt(
        group_id=declaration.group_id,
        cell_id=declaration.cell_id,
        test_sequence_id=declaration.test_sequence_id,
        published_filename=declaration.published_filename,
        snapshot=pin,
        format_id=fmt.format_id,
        format_version=fmt.format_version,
        format_digest=fmt.digest,
        line_terminator=terminator,
        header=fmt.header,
        raw_record_count=count,
        normalized_record_count=len(series),
        dropped_row_count=0,
        dropped_row_reasons={},
        normalized_digest=series.normalized_digest,
        lineage=series.lineage,
        consistency_checks=checks,
    )
    return receipt, series


def ingest_dataset(
    dataset_id: str,
    source: ReferenceSource,
    declarations: Sequence[RawFileDeclaration],
    raw_bytes: Mapping[str, bytes],
    *,
    declared_assumptions: Sequence[str],
) -> BatteryDataset:
    """Ingest every declared file; ``raw_bytes`` is keyed by ``group_id``."""

    dataset_id = _text(dataset_id, label="dataset_id")
    if not isinstance(source, ReferenceSource):
        raise RealDataError("a dataset needs a ReferenceSource")
    declarations = tuple(declarations)
    if not declarations:
        raise RealDataError("a dataset needs at least one raw file")
    groups = [d.group_id for d in declarations]
    if len(set(groups)) != len(groups):
        raise RealDataError("group_id values must be unique")
    pins = [d.snapshot.snapshot_sha256 for d in declarations]
    if len(set(pins)) != len(pins):
        raise RealDataError("the same raw bytes are declared under two groups; one file cannot be two experiments")
    if set(raw_bytes) != set(groups):
        raise RealDataError(
            f"raw bytes supplied for {sorted(raw_bytes)} but files declared for {sorted(groups)}"
        )
    for item in declarations:
        try:
            item.snapshot.require_from(source)
        except CorpusError as exc:
            raise RealDataError(str(exc)) from exc
    assumptions = tuple(_text(a, label="declared assumption") for a in declared_assumptions)
    receipts: list[RawFileReceipt] = []
    series: list[BatteryTimeSeries] = []
    for item in sorted(declarations, key=lambda d: d.group_id):
        receipt, normalized = ingest_raw_file(raw_bytes[item.group_id], item)
        receipts.append(receipt)
        series.append(normalized)
    receipt = BatteryDatasetReceipt(
        dataset_id=dataset_id,
        source=source,
        files=tuple(receipts),
        declared_assumptions=assumptions,
    )
    return BatteryDataset(receipt=receipt, series=tuple(series))


# ---------------------------------------------------------------------------
# Derived channels -- never source data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DerivedChannel:
    """A quantity Forge computed. It names everything it depends on."""

    channel: str
    values: tuple[float, ...]
    unit: str
    method: str
    derivation_version: str
    inputs: tuple[str, ...]
    input_series_digest: str
    assumptions: Mapping[str, Quantity]

    def __post_init__(self) -> None:
        for label in ("channel", "unit", "method", "derivation_version", "input_series_digest"):
            object.__setattr__(self, label, _text(getattr(self, label), label=label))
        inputs = tuple(_channel(name).value for name in self.inputs)
        if not inputs:
            raise RealDataError("a derived channel must name its input channels")
        object.__setattr__(self, "inputs", inputs)
        assumptions = dict(self.assumptions)
        if any(not isinstance(v, Quantity) for v in assumptions.values()):
            raise RealDataError("derived-channel assumptions must be Quantity records")
        object.__setattr__(self, "assumptions", dict(sorted(assumptions.items())))
        object.__setattr__(self, "values", tuple(float(v) for v in self.values))

    @property
    def kind(self) -> LineageKind:
        return LineageKind.DERIVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DERIVED_CHANNEL_SCHEMA,
            "channel": self.channel,
            "kind": LineageKind.DERIVED.value,
            "values": list(self.values),
            "unit": self.unit,
            "method": self.method,
            "derivation_version": self.derivation_version,
            "inputs": list(self.inputs),
            "input_series_digest": self.input_series_digest,
            "assumptions": {k: v.to_dict() for k, v in self.assumptions.items()},
            "is_source_data": False,
            "can_be_measurement_evidence": False,
        }

    @property
    def digest(self) -> str:
        return _tagged_digest(_DERIVED_TAG, self.to_dict())


def derive_state_of_charge(
    series: BatteryTimeSeries,
    *,
    initial_state_of_charge: Quantity,
    reference_capacity: Quantity,
) -> DerivedChannel:
    """Coulomb counting from the measured current. A derivation, labelled as one.

    The initial state of charge and the reference capacity are assumptions;
    changing either changes every value. A trace that leaves [0, 1] is refused
    rather than clipped: the assumptions contradict the record.
    """

    if not isinstance(series, BatteryTimeSeries):
        raise RealDataError("derive_state_of_charge needs a normalized BatteryTimeSeries")
    for label, quantity, unit in (
        ("initial_state_of_charge", initial_state_of_charge, "dimensionless"),
        ("reference_capacity", reference_capacity, "ampere_hour"),
    ):
        if not isinstance(quantity, Quantity):
            raise RealDataError(f"{label} must be a Quantity")
        quantity.require_compatible(Quantity(1.0, unit), context=label)
    z0 = initial_state_of_charge.magnitude_in("dimensionless")
    capacity = reference_capacity.magnitude_in("ampere_hour")
    if not 0.0 <= z0 <= 1.0:
        raise RealDataError("initial_state_of_charge must lie in [0, 1]")
    if not (math.isfinite(capacity) and capacity > 0.0):
        raise RealDataError("reference_capacity must be finite and strictly positive")
    delivered = _trapezoid_ah(series.array(Channel.TIME), series.array(Channel.CURRENT))
    soc = z0 - delivered / capacity
    if np.any(soc < 0.0) or np.any(soc > 1.0):
        k = int(np.flatnonzero((soc < 0.0) | (soc > 1.0))[0])
        raise RealDataError(
            f"derived state of charge leaves [0, 1] at sample {k} ({soc[k]:.6g}); the assumed initial state "
            "of charge or reference capacity is inconsistent with the record"
        )
    return DerivedChannel(
        channel="state_of_charge",
        values=tuple(float(v) for v in soc),
        unit="dimensionless",
        method="trapezoidal coulomb counting of the canonical (discharge-positive) current",
        derivation_version="engcore.domains.battery.real_data.soc_coulomb_counting/1",
        inputs=(Channel.TIME.value, Channel.CURRENT.value),
        input_series_digest=series.normalized_digest,
        assumptions={
            "initial_state_of_charge": initial_state_of_charge,
            "reference_capacity": reference_capacity,
        },
    )


__all__ = [
    "AMBIGUOUS_UNIT_SYMBOLS",
    "BatteryDataset",
    "BatteryDatasetReceipt",
    "BatteryTimeSeries",
    "CANONICAL_CURRENT_SIGN",
    "CANONICAL_UNITS",
    "Channel",
    "ChannelLineage",
    "ColumnDeclaration",
    "CurrentSign",
    "DerivedChannel",
    "LineageKind",
    "NORMALIZATION_VERSION",
    "PARSER_VERSION",
    "RawFileDeclaration",
    "RawFileReceipt",
    "RealDataError",
    "REQUIRED_CHANNELS",
    "SourceFormat",
    "derive_state_of_charge",
    "ingest_dataset",
    "ingest_raw_file",
    "passive_step_test",
]
