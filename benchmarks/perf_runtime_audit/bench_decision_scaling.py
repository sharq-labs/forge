"""PERF-0 — how candidate scoring and snapshot digesting scale.

Two questions, both measured rather than assumed:

1. Does ``CandidateEvaluator.evaluate`` scale linearly in the candidate count,
   or does something inside it grow faster?
2. How many times is ``BeliefSnapshot.digest`` — a JSON serialization plus a
   SHA-256 — recomputed during ONE evaluation?

The providers come from the existing deterministic toy benchmark, so scoring
cost here is the *machinery's* cost and not a model's.

    python benchmarks/perf_runtime_audit/bench_decision_scaling.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engcore.sria.decision import ActionFamily  # noqa: E402
from src.engcore.sria.decision import belief_snapshot as belief_snapshot_mod  # noqa: E402
from src.engcore.sria.decision.belief_snapshot import BeliefSnapshot  # noqa: E402
from tests.sria_m4_benchmark import toy_action  # noqa: E402
from tests.test_sria_m4_decision import engine, evaluate, objective  # noqa: E402


def make_candidates(n: int) -> list[Any]:
    """``n`` distinct, deterministic candidates. Reliability/cost vary by index."""
    families = (
        ActionFamily.EXPLORE,
        ActionFamily.CHARACTERIZE,
    )
    out = []
    for i in range(n):
        out.append(
            toy_action(
                f"cand_{i:06d}",
                family=families[i % len(families)],
                # Kept strictly inside (0.5, 1.0) so every candidate is
                # scorable; the point is machinery cost, not the ranking.
                reliability=0.55 + 0.4 * ((i % 100) / 100.0),
                cost=0.25 + 0.01 * (i % 50),
            )
        )
    return out


class _DigestCounter:
    """Counts ``BeliefSnapshot.digest`` computations by wrapping the property."""

    def __init__(self) -> None:
        self.count = 0
        self._original = BeliefSnapshot.digest

    def __enter__(self) -> "_DigestCounter":
        original = self._original

        def counting_digest(inner_self):
            self.count += 1
            return original.fget(inner_self)

        BeliefSnapshot.digest = property(counting_digest)
        return self

    def __exit__(self, *exc) -> None:
        BeliefSnapshot.digest = self._original


def measure_evaluate(n: int, repeats: int) -> dict[str, Any]:
    candidates = make_candidates(n)
    eng = engine()
    obj = objective()

    # Warm the path once so first-call import/JIT-ish effects are not timed.
    evaluate(candidates, eng=eng, obj=obj, rid="warm")

    samples: list[float] = []
    rec = None
    for _ in range(repeats):
        started = time.perf_counter()
        rec = evaluate(candidates, eng=eng, obj=obj, rid=f"rec-{n}")
        samples.append(time.perf_counter() - started)
    samples.sort()

    with _DigestCounter() as counter:
        evaluate(candidates, eng=eng, obj=obj, rid=f"rec-{n}-digest")
    digests = counter.count

    median = statistics.median(samples)
    return {
        "candidates": n,
        "median_s": median,
        "min_s": samples[0],
        "max_s": samples[-1],
        "microseconds_per_candidate": 1e6 * median / n,
        "snapshot_digest_computations_per_evaluate": digests,
        "outcome": rec.outcome.value,
        "scores": len(rec.scores),
    }


def measure_snapshot_digest(repeats: int) -> dict[str, Any]:
    """Cost of one ``BeliefSnapshot.digest`` in isolation."""
    from tests.sria_m4_benchmark import toy_snapshot

    snapshot = toy_snapshot()
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        snapshot.digest
        samples.append(time.perf_counter() - started)
    samples.sort()
    return {
        "median_s": statistics.median(samples),
        "min_s": samples[0],
        "repeats": repeats,
    }


def measure_basis_duplicate_detection(sizes: list[int], repeats: int) -> list[dict]:
    """Cost of ``BeliefSnapshot``'s O(N^2) decision-basis duplicate check."""
    from src.engcore.sria.decision import DependencyIdentity, DependencyKind

    rows = []
    for n in sizes:
        basis = tuple(
            DependencyIdentity(
                dependency_id=f"dep_{i:06d}",
                kind=DependencyKind.OUTCOME_MODEL,
                version="1",
            )
            for i in range(n)
        )
        samples: list[float] = []
        for _ in range(repeats):
            started = time.perf_counter()
            BeliefSnapshot(
                snapshot_id="s", campaign_id="c", decision_basis=basis
            )
            samples.append(time.perf_counter() - started)
        samples.sort()
        rows.append(
            {
                "basis_size": n,
                "median_s": statistics.median(samples),
                "min_s": samples[0],
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 100, 1000, 10000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    rows = []
    for n in args.sizes:
        row = measure_evaluate(n, args.repeats)
        rows.append(row)
        print(
            f"candidates={n:6d} median={row['median_s']:8.4f}s "
            f"us/cand={row['microseconds_per_candidate']:8.2f} "
            f"snapshot_digests/evaluate={row['snapshot_digest_computations_per_evaluate']:3d} "
            f"outcome={row['outcome']}",
            flush=True,
        )

    payload = {
        "evaluate_scaling": rows,
        "single_snapshot_digest": measure_snapshot_digest(2000),
        "basis_duplicate_detection": measure_basis_duplicate_detection(
            [10, 100, 400, 1600], 5
        ),
    }
    print(json.dumps({k: payload[k] for k in ("single_snapshot_digest",
                                              "basis_duplicate_detection")},
                     indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
