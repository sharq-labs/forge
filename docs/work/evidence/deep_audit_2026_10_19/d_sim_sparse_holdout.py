"""INDEPENDENT DERIVATION (stdlib only; no engcore import).

Re-implements the decision rule of src/engcore/scientific/discovery/symbolic_regression.py:75-147 with the DEFAULT
SparseDiscoveryPolicy (max_terms=3, maximum_candidates=2000, holdout_rmse_limit=0.05 ABSOLUTE,
minimum_holdout_improvement=0.0) on PURE-NOISE targets (no feature carries any information), and counts how many
candidates get status SURVIVED_HOLDOUT and how often the top-ranked candidate does.
"""
import itertools, math, random


def solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            return None
        M[i], M[p] = M[p], M[i]
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                for c in range(i, n + 1):
                    M[r][c] -= f * M[i][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def ols(X, y):
    D = [[1.0] + row for row in X]
    k = len(D[0])
    A = [[sum(D[r][i] * D[r][j] for r in range(len(D))) for j in range(k)] for i in range(k)]
    b = [sum(D[r][i] * y[r] for r in range(len(D))) for i in range(k)]
    return solve(A, b)


def rmse(beta, X, y):
    return math.sqrt(sum((beta[0] + sum(bj * xj for bj, xj in zip(beta[1:], row)) - t) ** 2 for row, t in zip(X, y)) / len(y))


def run(rng, scale, n_cal=30, n_hold=15, p=10):
    n = n_cal + n_hold
    F = [[rng.uniform(0, 1) for _ in range(p)] for _ in range(n)]
    y = [0.5 + rng.gauss(0, scale) for _ in range(n)]          # pure noise: no feature matters
    cal, hold = list(range(n_cal)), list(range(n_cal, n))
    ycal, yhold = [y[i] for i in cal], [y[i] for i in hold]
    mean_cal = sum(ycal) / len(ycal)
    baseline = math.sqrt(sum((t - mean_cal) ** 2 for t in yhold) / len(yhold))
    survived, ranked = 0, []
    for k in range(1, 4):
        for idx in itertools.combinations(range(p), k):
            Xc = [[F[i][j] for j in idx] for i in cal]
            Xh = [[F[i][j] for j in idx] for i in hold]
            beta = ols(Xc, ycal)
            if beta is None:
                continue
            h = rmse(beta, Xh, yhold)
            ok = h <= 0.05 and baseline - h >= 0.0
            survived += ok
            ranked.append((not ok, (h or float("inf")) + 1e-4 * k))
    ranked.sort()
    return survived, len(ranked), not ranked[0][0]


rng = random.Random(7)
for scale in (0.01, 0.03, 0.2):
    rows = [run(rng, scale) for _ in range(60)]
    s = sum(r[0] for r in rows) / sum(r[1] for r in rows)
    top = sum(r[2] for r in rows) / len(rows)
    print(f"target noise sd {scale}: fraction of candidates SURVIVED_HOLDOUT {s:.3f}; datasets whose top candidate is a "
          f"SURVIVED_HOLDOUT {top:.2f}")
