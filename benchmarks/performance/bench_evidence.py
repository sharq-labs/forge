"""Validation evidence: report construction, and the re-validation done on every read.

``ValidationReport.attained_levels`` deliberately re-applies two whole-report
rules on **every read** rather than trusting what construction checked. That is
load-bearing for trust -- a level only matters at the moment it is read as a
claim -- and this benchmark exists to price it rather than to argue with it.

The read is measured three ways, because the cost a consumer pays depends
entirely on how it asks:

  attained_levels      one read: two validating passes plus one comprehension
  claims x1            one level queried
  claims x6            six levels queried -- which is six full re-validations,
                       and is what a consumer checking a required-level set
                       actually does
"""

from __future__ import annotations

import common
from common import Measurement, measure

SIZES = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 10_000))


def run() -> list[Measurement]:
    from engcore.scientific.results.validation import (
        ValidationLevel,
        ValidationReport,
    )

    levels = list(ValidationLevel)[:6]
    out: list[Measurement] = []

    for scale, size in SIZES:
        checks = common.validation_checks(size)

        out.append(measure(
            "evidence.report.construct",
            lambda checks=checks: checks,
            lambda c: ValidationReport(checks=c),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
            measure_memory=(size == 10_000),
        ))

        report = ValidationReport(checks=checks)
        out.append(measure(
            "evidence.attained_levels",
            lambda report=report: report,
            lambda r: r.attained_levels,
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 200, warmup=5,
            note="re-validates the whole report on every read, by design",
        ))
        out.append(measure(
            "evidence.claims.x1",
            lambda report=report: report,
            lambda r: r.claims(ValidationLevel.NUMERICALLY_CONVERGED),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 200, warmup=5,
        ))
        out.append(measure(
            "evidence.claims.x6",
            lambda report=report: report,
            lambda r, levels=levels: [r.claims(level) for level in levels],
            scale=scale, size=size,
            samples=20 if size >= 1_000 else 100, warmup=3,
            note="six queries = six full re-validations of the same report",
        ))

    return out


def call_counts() -> dict:
    """How many times a report is walked per consumer-visible operation."""
    from engcore.scientific.results import validation as v
    from engcore.scientific.results.validation import (
        ValidationLevel,
        ValidationReport,
    )

    report = ValidationReport(checks=common.validation_checks(50))
    counts = {}
    with common.CallCounter(v, "level_is_earned") as earned:
        report.attained_levels
    counts["attained_levels"] = {"level_is_earned": earned.count, "checks": 50}
    with common.CallCounter(v, "level_is_earned") as earned:
        for level in list(ValidationLevel)[:6]:
            report.claims(level)
    counts["claims_x6"] = {"level_is_earned": earned.count, "checks": 50}
    return counts


if __name__ == "__main__":
    measurements = run()
    common.report("EVIDENCE", measurements)
    counts = call_counts()
    print("\ncall counts:")
    for name, counted in counts.items():
        print(f"  {name:24} {counted}")
    print("\nwrote", common.write_results("bench_evidence", measurements,
                                          extra={"call_counts": counts}))
