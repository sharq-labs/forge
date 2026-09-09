"""The ValidityAssessment record itself: coherence checking and serialization.

Distinct from ``bench_applicability``, which measures *deciding* the conditions.
This measures the record that carries the decision -- its construction (which
cross-checks the status against its own condition lists and enforces the
UNKNOWN-reason correspondence), and its round trip.

The UNKNOWN shape is measured separately from the satisfied one because it is
the expensive branch: it carries a reason per unknown condition, and both the
duplicate scan and the coverage scan run over that list.
"""

from __future__ import annotations

import common
from common import Measurement, measure

SIZES = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 10_000))


def run() -> list[Measurement]:
    from engcore.scientific.models.definition import (
        UnknownCondition,
        UnknownReason,
        ValidityAssessment,
        ValidityStatus,
        classify_conditions,
    )

    out: list[Measurement] = []
    for scale, size in SIZES:
        names = tuple(f"condition_{i:05d}" for i in range(size))
        reasons = tuple(
            UnknownCondition(name=n, reason=UnknownReason.NOT_SUPPLIED)
            for n in names
        )

        out.append(measure(
            "validity.assessment.construct.satisfied",
            lambda names=names: names,
            lambda n: ValidityAssessment(
                status=ValidityStatus.IN_DOMAIN, satisfied=n
            ),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 200, warmup=5,
            measure_memory=(size == 10_000),
        ))
        out.append(measure(
            "validity.assessment.construct.unknown",
            lambda names=names, reasons=reasons: (names, reasons),
            lambda nr: ValidityAssessment(
                status=ValidityStatus.UNKNOWN,
                unknown=nr[0], unknown_reasons=nr[1],
            ),
            scale=scale, size=size,
            samples=20 if size >= 1_000 else 100, warmup=5,
            note="reason coverage + duplicate scan over the unknown list",
        ))
        out.append(measure(
            "validity.classify_conditions",
            lambda names=names: names,
            lambda n: classify_conditions(satisfied=n, violated=(), unknown=()),
            scale=scale, size=size,
            samples=200, warmup=10, inner=20,
            note="the one statement of the status rule",
        ))

        assessment = ValidityAssessment(
            status=ValidityStatus.IN_DOMAIN, satisfied=names
        )
        payload = assessment.to_dict()
        out.append(measure(
            "validity.assessment.to_dict",
            lambda assessment=assessment: assessment, lambda a: a.to_dict(),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 200, warmup=5,
        ))
        out.append(measure(
            "validity.assessment.from_dict",
            lambda payload=payload: payload,
            lambda p: ValidityAssessment.from_dict(p),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 200, warmup=5,
        ))

    return out


if __name__ == "__main__":
    measurements = run()
    common.report("VALIDITY RECORD", measurements)
    print("\nwrote", common.write_results("bench_validity", measurements))
