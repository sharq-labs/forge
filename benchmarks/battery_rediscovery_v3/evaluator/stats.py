"""Finite-proportion intervals and the exact paired sign test of battery_rediscovery_v3 (frozen in PLAN.json).

* ``wilson(k, n)``: the Wilson score 95 % interval for k successes in n trials (z = 1.959963984540054); ``(None, None)``
  when n = 0.
* ``sign_test(wins, losses)``: the exact two-sided binomial sign test on the discordant pairs of a paired comparison,
  ``p = min(1, 2 * sum_(i <= min(w, l)) C(w + l, i) / 2^(w + l))``; 1.0 when there is no discordant pair.  Ties are
  not discordant and do not enter.
* ``paired(a, b)``: over the same decided instances, win = a correct and b not, loss = b correct and a not, tie
  otherwise.
"""

from __future__ import annotations

import math
from typing import Iterable

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2 ** n
    return min(1.0, 2.0 * tail)


def paired(a_correct: Iterable[bool], b_correct: Iterable[bool]) -> dict[str, float]:
    w = l_ = t = 0
    for x, y in zip(a_correct, b_correct, strict=True):
        if x and not y:
            w += 1
        elif y and not x:
            l_ += 1
        else:
            t += 1
    return {"win": w, "loss": l_, "tie": t, "p_sign": sign_test(w, l_)}


__all__ = ["Z95", "paired", "sign_test", "wilson"]
