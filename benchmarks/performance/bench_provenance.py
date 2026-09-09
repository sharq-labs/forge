"""Provenance record construction and encoding over N typed scientific inputs.

Inputs are a mix of all four ``ScientificValue`` kinds, in the proportion a real
study carries them, because encoding a ``CategoricalValue`` and encoding a
``Quantity`` do not cost the same and a benchmark over Quantities alone would
price only the cheapest quarter of the union.

Construction and serialization are separated: construction freezes and
validates, ``to_dict`` encodes and detaches, and they grow for different
reasons.
"""

from __future__ import annotations

import common
from common import Measurement, measure

SIZES = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 10_000))


def run() -> list[Measurement]:
    from engcore.scientific.results.provenance import ProvenanceRecord

    out: list[Measurement] = []
    for scale, size in SIZES:
        inputs = common.provenance_inputs(size)

        out.append(measure(
            "provenance.construct",
            lambda inputs=inputs: inputs,
            lambda i: ProvenanceRecord(run_id="perf", inputs=i),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
            measure_memory=(size == 10_000),
            note="validates the union and freezes",
        ))

        record = ProvenanceRecord(run_id="perf", inputs=inputs)
        out.append(measure(
            "provenance.to_dict",
            lambda record=record: record, lambda r: r.to_dict(),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
            measure_memory=(size == 10_000),
        ))

        payload = record.to_dict()
        out.append(measure(
            "provenance.from_dict",
            lambda payload=payload: payload,
            lambda p: ProvenanceRecord.from_dict(p),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
        ))

    # Metadata breadth and depth as separate axes: a wide flat mapping and a
    # deeply nested one reach `freeze` and `unwritable` through different
    # recursions, and one benchmark over "big metadata" would confuse them.
    for label, breadth, depth in (
        ("wide", 2_000, 1), ("deep", 10, 200), ("both", 200, 20),
    ):
        metadata = common.nested_metadata(breadth, depth)
        out.append(measure(
            f"provenance.construct.metadata_{label}",
            lambda metadata=metadata: metadata,
            lambda m: ProvenanceRecord(run_id="perf", metadata=m),
            scale="MEDIUM", size=breadth * depth,
            samples=40, warmup=5, measure_memory=True,
            note=f"breadth={breadth} depth={depth}",
        ))

    return out


if __name__ == "__main__":
    measurements = run()
    common.report("PROVENANCE", measurements)
    print("\nwrote", common.write_results("bench_provenance", measurements))
