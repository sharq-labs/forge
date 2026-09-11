"""MV-23: eight controlled failures, planted to see whether the machinery bites.

Nothing under ``src/`` is touched. Each plant corrupts what the Core hands
back, or corrupts the result set's own bookkeeping, and the ordinary comparison
and the ordinary integrity checks are re-run over the ordinary preregistered
tolerances.

Five of the eight are numerical and must be caught by a residual leaving its
tolerance. Three are structural -- leakage, an out-of-scope row counted as
validation, a held-out label rewritten as calibration -- and leave every
residual looking perfectly healthy. Those three are the reason
``audit/integrity.py`` exists, and they are the ones a validation round is most
likely to get wrong without noticing.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager

from . import integrity, production, validation


@contextmanager
def _patched(name, wrapper):
    original = getattr(production, name)

    def patched(*args, **kwargs):
        return wrapper(original(*args, **kwargs))

    setattr(production, name, patched)
    try:
        yield
    finally:
        setattr(production, name, original)


def _held(bundle):
    return [r for r in bundle["rows"] if r["split"] == "HELD_OUT"]


def _failures(rows, key="within_tolerance"):
    return sum(1 for r in rows if r.get(key) is False)


def control() -> dict:
    """No plant. If this is not clean the plants below prove nothing."""
    results = validation.run_all()
    checks = integrity.run_all(results)
    numeric = 0
    for bundle in results.values():
        numeric += _failures(bundle["rows"])
    return {
        "id": "MVM-0",
        "plant": "none; the control",
        "rows_failing_tolerance": numeric,
        "integrity_checks_failing": sum(
            1 for c in checks["checks"] if not c["passed"]
        ),
        "note": (
            "The control is NOT expected to be clean. MV-A fails its "
            "preregistered tolerance at every held-out point and MV-C fails at "
            "six of 371, both for reasons adjudicated in the findings, and the "
            "split check reports the one-row discrepancy recorded as MVA-1. "
            "What the control establishes is the BASELINE each plant is "
            "measured against, so a plant only counts if it makes things worse."
        ),
    }


def _measure(results):
    """Numeric and structural failure counts for one result set."""
    return (
        sum(_failures(b["rows"]) for b in results.values()),
        integrity.run_all(results)["offences"],
    )


def _delta(identifier, plant, baseline_results, planted_results, how):
    """Compare a plant against a baseline over THE SAME cases.

    Comparing a single-case plant against a whole-round baseline is how this
    harness first reported four misses that were nothing but an
    apples-to-oranges count. The baseline is now built from exactly the cases
    the plant ran.
    """
    base_numeric, base_structural = _measure(baseline_results)
    numeric, structural = _measure(planted_results)
    caught = numeric > base_numeric or structural > base_structural
    return {
        "id": identifier,
        "plant": plant,
        "cases_exercised": sorted(planted_results),
        "rows_failing_tolerance": numeric,
        "baseline_rows_failing_tolerance": base_numeric,
        "integrity_offences": structural,
        "baseline_integrity_offences": base_structural,
        "how_it_is_caught": how,
        "verdict": "CAUGHT" if caught else "MISSED",
    }


def run_all() -> dict:
    base = control()
    clean = validation.run_all()
    plants = []

    def record(identifier, plant, results, how):
        baseline = {key: clean[key] for key in results}
        plants.append(_delta(identifier, plant, baseline, results, how))

    # --- MVM-1: a systematic +5% bias on every open-circuit voltage ---------
    with _patched("open_circuit_voltage", lambda v: None if v is None else v * 1.05):
        record("MVM-1", "+5 percent systematic bias on every Core open-circuit voltage",
               {"MV-B": validation.case_b()},
               "a 165 mV bias on a 3.3 V cell leaves the millivolt-scale tolerance")

    # --- MVM-2: a wrong slope, right at the reference point -----------------
    # The resistance is left exact at 0 degC and tilted 2 percent thereafter,
    # which a comparison that only checked one temperature would never see.
    def tilt(value):
        return 100.0 + (value - 100.0) * 1.02

    with _patched("resistance_at", tilt):
        record("MVM-2", "resistance-temperature slope 2 percent too steep, exact at the reference point",
               {"MV-C": validation.case_c()},
               "the deviation stops being the omitted quadratic term, so the ratio metric leaves its band")

    # --- MVM-3: a unit error of a thousand ----------------------------------
    with _patched("open_circuit_voltage", lambda v: None if v is None else v * 1000.0):
        record("MVM-3", "every Core open-circuit voltage multiplied by 1000",
               {"MV-B": validation.case_b()},
               "a kilovolt where a volt was measured")

    # --- MVM-4: a time shift ------------------------------------------------
    # The realistic time-shift fault in this round is reading the relaxed
    # open-circuit voltage off the wrong point of the trace. The plant reads it
    # one hour in rather than twenty-four, which is what an extraction that
    # mis-indexed the time column would do.
    with _relaxation_read_at(1.0):
        record("MVM-4", "the relaxed open-circuit voltage read at 1 h instead of 24 h",
               {"MV-A": validation.case_a(), "MV-B": validation.case_b()},
               "the cell has not finished relaxing at 1 h, so every declared endpoint and every held-out value moves")

    # --- MVM-5: calibration leakage ----------------------------------------
    leaked = validation.run_all()
    victim = next(r for r in leaked["MV-A"]["rows"] if r["split"] == "CALIBRATION")
    duplicate = copy.deepcopy(victim)
    duplicate["split"] = "HELD_OUT"
    duplicate["within_tolerance"] = True
    leaked["MV-A"]["rows"].append(duplicate)
    record("MVM-5", "a calibration point duplicated into the held-out set", leaked,
           "the leakage check finds one set of inputs carrying two splits")

    # --- MVM-6: measurement uncertainty treated as zero ---------------------
    zeroed = validation.run_all()
    for row in zeroed["MV-B"]["rows"]:
        if row["split"] == "HELD_OUT":
            row["expanded_uncertainty_k2_v"] = 0.0
    record("MVM-6", "measurement uncertainty set to zero on a passing case", zeroed,
           "a comparison scored against a zero uncertainty is refused outright")

    # --- MVM-7: an out-of-scope row counted as validation -------------------
    out_of_scope = validation.run_all()
    row = copy.deepcopy(out_of_scope["MV-A"]["rows"][0])
    row["applicability"] = "OUT_OF_SCOPE"
    row["split"] = "VALIDATION"
    row["inputs"] = dict(row["inputs"]) | {"state_of_charge": 0.99}
    out_of_scope["MV-A"]["rows"].append(row)
    record("MVM-7", "a row screened OUT_OF_SCOPE relabelled as validation", out_of_scope,
           "the applicability check refuses an out-of-scope row carrying a validation verdict")

    # --- MVM-8: a held-out label rewritten as calibration -------------------
    relabelled = validation.run_all()
    for row in relabelled["MV-A"]["rows"]:
        if row["split"] == "HELD_OUT" and not row["within_tolerance"]:
            row["split"] = "CALIBRATION"
            break
    record("MVM-8", "one failing held-out point relabelled as calibration", relabelled,
           "the split check counts the rows that actually ran against the counts the plan fixed")

    return {
        "control": base,
        "plants": plants,
        "caught": sum(1 for p in plants if p["verdict"] == "CAUGHT"),
        "missed": sum(1 for p in plants if p["verdict"] == "MISSED"),
    }


@contextmanager
def _relaxation_read_at(hours: float):
    """Read every relaxation trace at ``hours`` instead of at its final sample.

    The value AND the recorded read point both move, which is the whole point:
    a plant that corrupted the value while leaving the bookkeeping honest would
    be testing a fault nobody makes.
    """
    from . import evidence

    original = evidence.relaxation_traces

    def shifted(sheet_name):
        traces = original(sheet_name)
        for entry in traces.values():
            entry["relaxed_voltage_v"] = entry["initial_voltage_v"]
            entry["relaxed_at_hours"] = hours
        return traces

    evidence.relaxation_traces = shifted
    validation.E.relaxation_traces = shifted
    try:
        yield
    finally:
        evidence.relaxation_traces = original
        validation.E.relaxation_traces = original
