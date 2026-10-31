"""A3 development calibration: one-sided type-I error of candidate paired tests on synthetic NULL paired differences.

Development planning input for the v0.4 preregistration (ACTIVE_PLAN "Blindfold Step 1 gap closure"), not a formal
result. No repository data is read. Usage: python power_typeI_check.py [reps]

Null worlds: paired differences D in [-12, 12] with E[D] = 0 exactly (the boundary of H0: E[D] <= 0), from
(a) a symmetric two-point law, (b) a skewed three-point law, (c) a discrete law shaped like a pilot spread.
Tests: Hoeffding (as analysis_v3), empirical-Bernstein (Maurer & Pontil 2009), paired sign-flip randomization.
"""
import math
import random
import statistics
import sys

R = 24.0
ALPHA = 0.05


def hoeffding_reject(d):
    n, m = len(d), statistics.fmean(d)
    return math.exp(-2 * n * max(m, 0.0) ** 2 / R ** 2) <= ALPHA


def bernstein_reject(d):
    n, m = len(d), statistics.fmean(d)
    v = statistics.variance(d)
    L = math.log(2 / ALPHA)
    return m - math.sqrt(2 * v * L / n) - 7 * R * L / (3 * (n - 1)) > 0


def signflip_reject(d, rng, draws=999):
    obs = statistics.fmean(d)
    hits = sum(statistics.fmean([x if rng.random() < .5 else -x for x in d]) >= obs for _ in range(draws))
    return (hits + 1) / (draws + 1) <= ALPHA


LAWS = {
    "symmetric_two_point": ([-1.0, 1.0], [.5, .5]),
    "skewed_three_point": ([-6.0, 0.5, 1.0], [0.1, 0.4, 0.5]),     # mean -0.6 + 0.2 + 0.5 = 0.1 -> recentred below
    "pilot_like": ([-2.0, -1.0, 0.0, 1.0, 2.0], [.05, .2, .5, .2, .05]),
}


def centred(values, weights):
    mu = sum(v * w for v, w in zip(values, weights))
    return [v - mu for v in values], weights


def main(reps):
    rng = random.Random(20261030)
    print(f"reps={reps} alpha={ALPHA}")
    for name, (vals, w) in LAWS.items():
        vals, w = centred(vals, w)
        assert all(abs(v) <= 12 for v in vals)
        for n in (120, 480):
            rej = {"hoeffding": 0, "emp_bernstein": 0, "sign_flip": 0}
            for _ in range(reps):
                d = rng.choices(vals, w, k=n)
                rej["hoeffding"] += hoeffding_reject(d)
                rej["emp_bernstein"] += bernstein_reject(d)
                rej["sign_flip"] += signflip_reject(d, rng, draws=199)
            print(f"{name:20s} n={n:4d} " + " ".join(f"{k}={v / reps:.4f}" for k, v in rej.items()))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400)
