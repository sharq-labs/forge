"""Deterministic segmentation and data-quality report for a normalized series.

Everything here CLASSIFIES; nothing removes, edits or re-weights a sample.
A questionable observation is reported with its sample index and the rule
that flagged it, and stays in the series exactly as ingested.

Segmentation reads the current only. A sample is REST when the canonical
current lies inside the declared band, DISCHARGE above it and CHARGE below
it; a segment is a maximal run of one state. A transition's *bracket* is the
time between the last sample of one segment and the first of the next: the
resolution with which the record locates that current step.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

import numpy as np

from ....scientific.serialization import schema_string
from .ingest import CANONICAL_UNITS, BatteryTimeSeries, Channel, RealDataError

QUALITY_SCHEMA = schema_string("battery_time_series_quality_report")
HOLDOUT_STRUCTURE_SCHEMA = schema_string("battery_holdout_structure_report")
SEGMENTATION_VERSION = "engcore.domains.battery.real_data.segmentation/1"


class SegmentKind(str, Enum):
    REST = "rest"
    DISCHARGE = "discharge"
    CHARGE = "charge"


class TransitionKind(str, Enum):
    ONSET = "onset"                # rest -> discharge
    INTERRUPTION = "interruption"  # discharge -> rest
    CHARGE_ONSET = "charge_onset"
    CHARGE_INTERRUPTION = "charge_interruption"
    REVERSAL = "reversal"          # charge <-> discharge without a rest


@dataclass(frozen=True)
class SegmentationPolicy:
    """Declared thresholds. Their values are part of every report's identity."""

    rest_band_a: float = 0.005
    constant_current_tolerance_fraction: float = 0.01
    step_bracket_max_s: float = 0.25
    voltage_rate_flag_v_per_s: float = 0.02
    voltage_run_min_samples: int = 5

    def __post_init__(self) -> None:
        for label in ("rest_band_a", "constant_current_tolerance_fraction", "step_bracket_max_s",
                      "voltage_rate_flag_v_per_s"):
            value = float(getattr(self, label))
            if not (math.isfinite(value) and value > 0.0):
                raise RealDataError(f"segmentation policy {label} must be finite and positive")
            object.__setattr__(self, label, value)
        if int(self.voltage_run_min_samples) < 2:
            raise RealDataError("voltage_run_min_samples must be at least 2")
        object.__setattr__(self, "voltage_run_min_samples", int(self.voltage_run_min_samples))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SEGMENTATION_VERSION,
            "rest_band_a": self.rest_band_a,
            "constant_current_tolerance_fraction": self.constant_current_tolerance_fraction,
            "step_bracket_max_s": self.step_bracket_max_s,
            "voltage_rate_flag_v_per_s": self.voltage_rate_flag_v_per_s,
            "voltage_run_min_samples": self.voltage_run_min_samples,
        }


DEFAULT_SEGMENTATION = SegmentationPolicy()


@dataclass(frozen=True)
class Segment:
    index: int
    kind: SegmentKind
    first: int
    last: int
    t_start: float
    t_end: float
    current_median_a: float
    current_min_a: float
    current_max_a: float
    constant_current: bool

    @property
    def samples(self) -> int:
        return self.last - self.first + 1

    @property
    def duration_s(self) -> float:
        return self.t_end - self.t_start

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind.value,
            "first_sample": self.first,
            "last_sample": self.last,
            "samples": self.samples,
            "t_start_s": self.t_start,
            "t_end_s": self.t_end,
            "duration_s": self.duration_s,
            "current_median_a": self.current_median_a,
            "current_min_a": self.current_min_a,
            "current_max_a": self.current_max_a,
            "constant_current": self.constant_current,
        }


@dataclass(frozen=True)
class Transition:
    kind: TransitionKind
    before: int
    after: int
    last_before: int
    first_after: int
    bracket_s: float
    delta_current_a: float
    delta_voltage_v: float
    resolved: bool

    @property
    def step_resistance_ohm(self) -> float | None:
        """-dV/dI across the bracket: a data feature, not a fitted resistance."""
        if abs(self.delta_current_a) <= 0.0:
            return None
        return -self.delta_voltage_v / self.delta_current_a

    def to_dict(self) -> dict[str, Any]:
        resistance = self.step_resistance_ohm
        return {
            "kind": self.kind.value,
            "segment_before": self.before,
            "segment_after": self.after,
            "last_sample_before": self.last_before,
            "first_sample_after": self.first_after,
            "bracket_s": self.bracket_s,
            "delta_current_a": self.delta_current_a,
            "delta_voltage_v": self.delta_voltage_v,
            "resolved_step": self.resolved,
            "step_resistance_feature_ohm": resistance,
            "step_resistance_note": (
                "-dV/dI across the bracket, read from two samples; a data feature at that bracket, "
                "not a fitted or calibrated resistance"
            ),
        }


def _state(current: np.ndarray, band: float) -> np.ndarray:
    return np.where(np.abs(current) <= band, 0, np.where(current > 0.0, 1, -1))


_KIND = {0: SegmentKind.REST, 1: SegmentKind.DISCHARGE, -1: SegmentKind.CHARGE}
_TRANSITION = {
    (SegmentKind.REST, SegmentKind.DISCHARGE): TransitionKind.ONSET,
    (SegmentKind.DISCHARGE, SegmentKind.REST): TransitionKind.INTERRUPTION,
    (SegmentKind.REST, SegmentKind.CHARGE): TransitionKind.CHARGE_ONSET,
    (SegmentKind.CHARGE, SegmentKind.REST): TransitionKind.CHARGE_INTERRUPTION,
    (SegmentKind.CHARGE, SegmentKind.DISCHARGE): TransitionKind.REVERSAL,
    (SegmentKind.DISCHARGE, SegmentKind.CHARGE): TransitionKind.REVERSAL,
}


def segment_series(
    series: BatteryTimeSeries, policy: SegmentationPolicy = DEFAULT_SEGMENTATION
) -> tuple[tuple[Segment, ...], tuple[Transition, ...]]:
    """Maximal same-state runs of the current, and the steps between them."""

    if not isinstance(series, BatteryTimeSeries):
        raise RealDataError("segment_series needs a normalized BatteryTimeSeries")
    t = series.array(Channel.TIME)
    i = series.array(Channel.CURRENT)
    v = series.array(Channel.VOLTAGE)
    state = _state(i, policy.rest_band_a)
    segments: list[Segment] = []
    start = 0
    for k in range(1, len(t) + 1):
        if k == len(t) or state[k] != state[start]:
            block = i[start:k]
            median = float(np.median(block))
            kind = _KIND[int(state[start])]
            spread = float(np.max(block) - np.min(block))
            constant = kind is not SegmentKind.REST and spread <= policy.constant_current_tolerance_fraction * abs(median)
            segments.append(
                Segment(
                    index=len(segments),
                    kind=kind,
                    first=start,
                    last=k - 1,
                    t_start=float(t[start]),
                    t_end=float(t[k - 1]),
                    current_median_a=median,
                    current_min_a=float(np.min(block)),
                    current_max_a=float(np.max(block)),
                    constant_current=bool(constant),
                )
            )
            start = k
    transitions: list[Transition] = []
    for a, b in zip(segments, segments[1:]):
        k0, k1 = a.last, b.first
        bracket = float(t[k1] - t[k0])
        transitions.append(
            Transition(
                kind=_TRANSITION[(a.kind, b.kind)],
                before=a.index,
                after=b.index,
                last_before=k0,
                first_after=k1,
                bracket_s=bracket,
                delta_current_a=float(i[k1] - i[k0]),
                delta_voltage_v=float(v[k1] - v[k0]),
                resolved=bracket <= policy.step_bracket_max_s,
            )
        )
    return tuple(segments), tuple(transitions)


def _interval_summary(t: np.ndarray) -> dict[str, Any]:
    dt = np.diff(t)
    rounded = np.round(dt, 3)
    values, counts = np.unique(rounded, return_counts=True)
    order = np.argsort(-counts, kind="stable")[:8]
    return {
        "min_s": float(np.min(dt)),
        "median_s": float(np.median(dt)),
        "max_s": float(np.max(dt)),
        "most_common_ms_rounded": [
            {"interval_s": float(values[j]), "count": int(counts[j])} for j in order
        ],
    }


def quality_report(
    series: BatteryTimeSeries, policy: SegmentationPolicy = DEFAULT_SEGMENTATION
) -> dict[str, Any]:
    """A deterministic description of the record. It classifies; it never cleans."""

    segments, transitions = segment_series(series, policy)
    t = series.array(Channel.TIME)
    i = series.array(Channel.CURRENT)
    v = series.array(Channel.VOLTAGE)
    seg_of = np.empty(len(t), dtype=int)
    for seg in segments:
        seg_of[seg.first: seg.last + 1] = seg.index

    rest_mask = np.abs(i) <= policy.rest_band_a
    rest_current = np.abs(i[rest_mask])

    dv = np.diff(v)
    dt = np.diff(t)
    same_segment = seg_of[1:] == seg_of[:-1]
    rate = np.abs(dv) / dt
    flagged = np.flatnonzero(same_segment & (rate > policy.voltage_rate_flag_v_per_s))
    rate_flags = [
        {
            "sample": int(k + 1),
            "t_s": float(t[k + 1]),
            "delta_voltage_v": float(dv[k]),
            "interval_s": float(dt[k]),
            "rate_v_per_s": float(rate[k]),
            "segment_kind": segments[int(seg_of[k + 1])].kind.value,
            "classification": "rapid voltage change inside one current segment (not a current step); kept as recorded",
        }
        for k in flagged
    ]

    runs = []
    start = 0
    for k in range(1, len(v) + 1):
        if k == len(v) or v[k] != v[start]:
            if k - start >= policy.voltage_run_min_samples:
                kind = segments[int(seg_of[start])].kind
                runs.append(
                    {
                        "first_sample": int(start),
                        "samples": int(k - start),
                        "voltage_v": float(v[start]),
                        "segment_kind": kind.value,
                        "at_record_extreme": bool(v[start] in (float(np.max(v)), float(np.min(v)))),
                        "classification": (
                            "identical voltage readings while the current varies: consistent with constant-voltage "
                            "control or with clipping; not removed"
                        ),
                    }
                )
            start = k

    nonzero_steps = np.abs(dv[np.abs(dv) > 0.0])
    present = sorted(series.channels)
    absent = {
        channel.value: "not a source channel of this format"
        for channel in Channel
        if channel.value not in series.channels
    }
    charge_samples = int(np.sum(i < -policy.rest_band_a))
    ranges = {
        name: {"min": float(np.min(series.array(name))), "max": float(np.max(series.array(name))),
               "unit": CANONICAL_UNITS[Channel(name)]}
        for name in present
        if name != Channel.TIME.value
    }
    return {
        "schema": QUALITY_SCHEMA,
        "group_id": series.group_id,
        "cell_id": series.cell_id,
        "test_sequence_id": series.test_sequence_id,
        "raw_sha256": series.raw_sha256,
        "normalized_digest": series.normalized_digest,
        "segmentation_policy": policy.to_dict(),
        "record_count": len(series),
        "time": {
            "start_s": float(t[0]),
            "end_s": float(t[-1]),
            "strictly_increasing": True,
            "duplicate_timestamps": 0,
            "sample_interval": _interval_summary(t),
        },
        "channels_present": present,
        "channels_absent": absent,
        "ranges": ranges,
        "voltage_quantization_step_v": float(np.min(nonzero_steps)) if nonzero_steps.size else None,
        "rest_current": {
            "band_a": policy.rest_band_a,
            "samples_in_band": int(np.sum(rest_mask)),
            "max_abs_in_band_a": float(np.max(rest_current)) if rest_current.size else None,
            "classification": "kept as recorded; the band classifies it as rest, nothing zeroes it",
        },
        "segments": [seg.to_dict() for seg in segments],
        "transitions": [tr.to_dict() for tr in transitions],
        "within_segment_voltage_rate_flags": rate_flags,
        "constant_voltage_runs": runs,
        "battery_thevenin_1rc_domain": {
            "charge_samples": charge_samples,
            "note": (
                "battery.thevenin_1rc is declared for discharge and rest only; charge samples are outside its "
                "domain. They stay in the series and are classified, not removed."
            ),
        },
        "unsupported_records": 0,
        "dropped_records": 0,
    }


def holdout_structure_report(
    series: BatteryTimeSeries, policy: SegmentationPolicy = DEFAULT_SEGMENTATION
) -> dict[str, Any]:
    """What may be published about a HELD-OUT group before any calibration: current structure only.

    No voltage value, voltage step, step resistance or voltage range appears, so nothing a later calibration
    is tested against is exposed early.
    """

    segments, transitions = segment_series(series, policy)
    return {
        "schema": HOLDOUT_STRUCTURE_SCHEMA,
        "group_id": series.group_id,
        "cell_id": series.cell_id,
        "raw_sha256": series.raw_sha256,
        "normalized_digest": series.normalized_digest,
        "segmentation_policy": policy.to_dict(),
        "record_count": len(series),
        "role": "held out: current structure only, no voltage-derived feature",
        "segments": [
            {k: v for k, v in seg.to_dict().items()} for seg in segments
        ],
        "transitions": [
            {"kind": tr.kind.value, "bracket_s": tr.bracket_s, "delta_current_a": tr.delta_current_a,
             "resolved_step": tr.resolved}
            for tr in transitions
        ],
    }


__all__ = [
    "DEFAULT_SEGMENTATION",
    "HOLDOUT_STRUCTURE_SCHEMA",
    "holdout_structure_report",
    "QUALITY_SCHEMA",
    "SEGMENTATION_VERSION",
    "Segment",
    "SegmentKind",
    "SegmentationPolicy",
    "Transition",
    "TransitionKind",
    "quality_report",
    "segment_series",
]
