"""Scientific serialization: canonical JSON, the writability scan, and freezing.

Three distinct costs that a single "serialization" number would blend:

  to_dict     builds the payload and detaches every nested container
  to_json     the above, plus sorted-key canonical JSON with allow_nan=False
  unwritable  the pre-write scan that refuses non-finite floats and non-string
              mapping keys

``freeze``/``detach`` are measured here too rather than in their own module,
because they are what makes ``to_dict`` cost what it costs and reading the two
side by side is the only way to attribute it.
"""

from __future__ import annotations

import json

import common
from common import Measurement, measure

SIZES = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 10_000))


def run() -> list[Measurement]:
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ScientificResult
    from engcore.scientific.serialization import to_json, unwritable

    out: list[Measurement] = []

    for scale, size in SIZES:
        values = common.quantities(size)
        provenance = ProvenanceRecord(run_id="perf")
        result = ScientificResult(
            result_id="perf", values=values, provenance=provenance
        )

        out.append(measure(
            "serialization.result.construct",
            lambda values=values, provenance=provenance: (values, provenance),
            lambda vp: ScientificResult(
                result_id="perf", values=vp[0], provenance=vp[1]
            ),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
            measure_memory=(size == 10_000),
        ))
        out.append(measure(
            "serialization.result.to_dict",
            lambda result=result: result, lambda r: r.to_dict(),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
            measure_memory=(size == 10_000),
        ))
        out.append(measure(
            "serialization.result.to_json",
            lambda result=result: result, lambda r: to_json(r),
            scale=scale, size=size,
            samples=30 if size >= 1_000 else 100, warmup=5,
        ))
        payload = result.to_dict()
        out.append(measure(
            "serialization.result.from_dict",
            lambda payload=payload: payload,
            lambda p: ScientificResult.from_dict(p),
            scale=scale, size=size,
            samples=30 if size >= 1_000 else 100, warmup=5,
        ))
        out.append(measure(
            "serialization.unwritable_scan",
            lambda payload=payload: payload, lambda p: unwritable(p),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
        ))
        out.append(measure(
            "serialization.json_dumps_only",
            lambda payload=payload: payload,
            lambda p: json.dumps(p, sort_keys=True, allow_nan=False),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
            note="the stdlib floor this cost is read against",
        ))

    return out


if __name__ == "__main__":
    measurements = run()
    common.report("SERIALIZATION", measurements)
    print("\nwrote", common.write_results("bench_serialization", measurements))
