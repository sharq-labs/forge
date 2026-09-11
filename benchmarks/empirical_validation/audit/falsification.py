"""EV-20: does the comparison harness actually fail when it should?

A harness that reports agreement is worth nothing until it has been shown to
report disagreement. Six faults are injected into what the Core hands back --
not into the Core, which is never modified -- and the ordinary comparison is
re-run over the ordinary metrics and the ordinary preregistered tolerances.

Each injection names the failure mode it stands for. A bias and a scale error
are the two a unit fault produces; a wrong slope is what a coefficient error
produces and is invisible at the reference point; an outlier is one bad case
among good ones, which an audit reporting only worst-case numbers can hide; a
time shift is the fault a wrong time base produces and looks like nothing else;
a sign inversion is the fault a convention error produces.

The control run injects nothing. If the control does not come back clean the
injections prove nothing, so it is reported alongside them.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager

from adapters import adapter_a

from . import validation


def _scale_numbers(value, factor: float):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value * factor
    if isinstance(value, dict):
        return {k: _scale_numbers(v, factor) for k, v in value.items()}
    if isinstance(value, list):
        return [_scale_numbers(v, factor) for v in value]
    return value


@contextmanager
def _patched(name: str, wrapper):
    original = getattr(adapter_a, name)

    def patched(*args, **kwargs):
        return wrapper(original(*args, **kwargs))

    setattr(adapter_a, name, patched)
    try:
        yield
    finally:
        setattr(adapter_a, name, original)


def _scale_results_only(result: dict, factor: float, *, skip=("received",)) -> dict:
    out = copy.deepcopy(result)
    for key in out:
        if key in skip:
            continue
        out[key] = _scale_numbers(out[key], factor)
    return out


def _count(bundle) -> tuple[int, int]:
    rows = bundle["validation"] if isinstance(bundle, dict) else bundle
    return len(rows), sum(1 for row in rows if row["verdict"] == "DISAGREES")


def control() -> dict:
    total = failed = 0
    for bundle in (
        validation.lumped(),
        validation.slab(),
        validation.battery(),
        validation.conductor(),
        validation.platinum(),
        validation.circuits(),
        validation.reactor(),
    ):
        rows, bad = _count(bundle)
        total += rows
        failed += bad
    return {
        "id": "F-0",
        "injection": "none; the control",
        "rows": total,
        "disagreements": failed,
        "verdict": "GREEN" if failed == 0 else "CONTROL_FAILED",
    }


def bias_five_percent() -> dict:
    with _patched("lumped", lambda r: _scale_results_only(r, 1.05)):
        rows, bad = _count(validation.lumped())
    return _record("F-1", "every returned temperature biased by +5 percent", rows, bad)


def wrong_slope() -> dict:
    """A coefficient error: right at the reference point, wrong everywhere else.

    The platinum comparison is the one place a slope fault is separable from a
    bias, because the linear law is pinned at 0 degC and the deviation being
    tested grows with temperature.
    """

    def tilt(rows):
        out = []
        for row in rows:
            celsius = row["temperature_degC"]
            # R0 untouched; the temperature coefficient effectively 2% high.
            out.append(
                {
                    "temperature_degC": celsius,
                    "resistance_ohm": 100.0
                    + (row["resistance_ohm"] - 100.0) * 1.02,
                }
            )
        return out

    with _patched("platinum", tilt):
        rows, bad = _count(validation.platinum())
    return _record("F-2", "the resistance-temperature slope 2 percent too steep", rows, bad)


def single_outlier() -> dict:
    """One case wrong among many right ones."""
    state = {"seen": 0}

    def spoil(result):
        state["seen"] += 1
        if state["seen"] != 2:
            return result
        out = copy.deepcopy(result)
        out["values"] = dict(out["values"])
        for key in out["values"]:
            if key.startswith("node_voltage:") and out["values"][key] != 0.0:
                out["values"][key] *= 1.000001
        return out

    with _patched("circuit", spoil):
        rows, bad = _count(validation.circuits())
    return _record(
        "F-3",
        "one circuit out of five shifted by one part per million, the rest untouched",
        rows,
        bad,
    )


def scale_by_thousand() -> dict:
    with _patched("battery", lambda r: _scale_results_only(r, 1000.0)):
        rows, bad = _count(validation.battery())
    return _record("F-4", "every returned battery value multiplied by 1000", rows, bad)


def time_shift() -> dict:
    """The Core asked for a slightly different interval than the fixture states.

    Nothing is scaled and no sign changes; the trajectory is simply read one
    percent later than it should be. A comparison that only checked magnitudes
    and signs would miss it.
    """
    raw = validation.fixture("reactor")
    shifted = copy.deepcopy(raw)
    shifted["quantities"]["end_time_min"] *= 1.01

    original = adapter_a.reactor

    def patched(_fixture, **kwargs):
        return original(shifted, **kwargs)

    adapter_a.reactor = patched
    try:
        rows, bad = _count(validation.reactor())
    finally:
        adapter_a.reactor = original
    return _record("F-5", "the reactor integrated one percent past the declared end time", rows, bad)


def sign_inversion() -> dict:
    def flip(result):
        out = copy.deepcopy(result)
        out["values"] = dict(out["values"])
        for key in list(out["values"]):
            if key.startswith("resistor_current:"):
                out["values"][key] = -out["values"][key]
        return out

    with _patched("circuit", flip):
        rows, bad = _count(validation.circuits())
    return _record("F-6", "every resistor current's sign inverted", rows, bad)


def _record(identifier, injection, rows, bad) -> dict:
    return {
        "id": identifier,
        "injection": injection,
        "rows": rows,
        "disagreements": bad,
        "verdict": "CAUGHT" if bad > 0 else "MISSED",
    }


INJECTIONS = [
    bias_five_percent,
    wrong_slope,
    single_outlier,
    scale_by_thousand,
    time_shift,
    sign_inversion,
]


def run_all() -> dict:
    return {
        "control": control(),
        "injections": [injection() for injection in INJECTIONS],
    }
