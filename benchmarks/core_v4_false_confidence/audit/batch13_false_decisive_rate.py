"""The false-decisive rate of the CORE-011 gate, before and after I-18's t correction (audit R-33).

The audit measured 27.5 % at n = 2, 19.3 % at n = 3 and 8.7 % at n = 10 by running the full production path on
two models that are exact mirror images. This measures the GATE itself on mean-zero paired differences, which
is the same null and is cheap enough to re-run: the paired differences of two models with equal expected
pointwise scores are mean-zero by construction, and the gate sees nothing else.

    python benchmarks/core_v4_false_confidence/audit/batch13_false_decisive_rate.py
"""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "src"))

from engcore.adequacy.predictive import (  # noqa: E402
    COMPARISON_ALPHA,
    COMPARISON_MINIMUM_ABS_DELTA,
    COMPARISON_MINIMUM_N,
    COMPARISON_MINIMUM_SE_MULTIPLE,
    _critical_se_multiple,
)

TRIALS = 40_000


def main() -> int:
    rng = np.random.default_rng(20260917)
    print(f"alpha {COMPARISON_ALPHA:.4f}, minimum n {COMPARISON_MINIMUM_N}, "
          f"absolute floor {COMPARISON_MINIMUM_ABS_DELTA:g} nats, {TRIALS} trials")
    for n in (2, 3, 10, 20, 50):
        old = new = 0
        for _ in range(TRIALS):
            differences = rng.normal(0.0, 1.0, n)
            delta = float(differences.sum())
            standard_error = math.sqrt(n * float(np.var(differences, ddof=1)))
            if abs(delta) > COMPARISON_MINIMUM_ABS_DELTA and abs(delta) > COMPARISON_MINIMUM_SE_MULTIPLE * standard_error:
                old += 1
            if n >= COMPARISON_MINIMUM_N and abs(delta) > COMPARISON_MINIMUM_ABS_DELTA \
                    and abs(delta) > _critical_se_multiple(n) * standard_error:
                new += 1
        print(f"  n={n:3}  normal 2 SE gate {old / TRIALS:.4f}   t({n - 1}) gate {new / TRIALS:.4f}"
              f"{'   (below the minimum n, so never decisive)' if n < COMPARISON_MINIMUM_N else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
