"""Reviewer E -- INDEPENDENT stdlib-only derivations. Does not import or run FORGE code.

Each block re-states, from the cited source lines, the arithmetic FORGE performs, and evaluates it on concrete inputs.
"""
import math
from statistics import NormalDist

ND = NormalDist()


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    return sab / math.sqrt(saa * sbb)


# ---------------------------------------------------------------------------------------------- 1. mcp LHS permutation
# src/engcore/mcp/probabilistic_uq.py:47-59
def mcp_columns(count, k):
    base = [(i + 0.5) / count for i in range(count)]
    cols = []
    for column in range(k):
        stride = 2 * column + 1
        while math.gcd(stride, count) != 1:
            stride += 2
        cols.append([base[(i * stride + column) % count] for i in range(count)])
    return cols


print("== 1. mcp/probabilistic_uq stratified 'independent' columns: worst pairwise sample correlation ==")
for count in (4, 6, 8, 16, 32, 64, 256):
    for k in (2, 3, 4, 6, 8):
        cols = mcp_columns(count, k)
        worst = max(((abs(corr(cols[a], cols[b])), a, b, corr(cols[a], cols[b]))
                     for a in range(k) for b in range(a + 1, k)), key=lambda t: t[0])
        print(f"  n={count:3d} k={k}: worst |r|={worst[0]:.3f} (cols {worst[1]},{worst[2]}, r={worst[3]:+.3f})")

print("  -- Y = X0 + Xj for two U(0,1) inputs: sample sd vs independent sd sqrt(2/12)=0.408")
for count, k in ((4, 4), (8, 4), (32, 16), (32, 17), (64, 32)):
    cols = mcp_columns(count, k)
    j = k - 1
    y = [a + b for a, b in zip(cols[0], cols[j])]
    m = sum(y) / len(y)
    sd = math.sqrt(sum((v - m) ** 2 for v in y) / (len(y) - 1))
    print(f"  n={count} cols 0 and {j}: r={corr(cols[0], cols[j]):+.3f}  sd(Y)={sd:.4f}")


# ---------------------------------------------------------------------------------------------- 2. mcp quantile coverage
# np.quantile default method 'linear' (type 7): position p*(n-1), linear interpolation between order statistics.
def type7(sorted_vals, p):
    pos = p * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


print("\n== 2. mcp predictive_intervals: true probability mass inside the reported 95% interval ==")
print("   (single input, Y = X (monotone); stratified midpoints (i+0.5)/n; np.quantile type 7)")
for count in (4, 8, 16, 32, 64, 128, 256):
    u = sorted((i + 0.5) / count for i in range(count))
    lo, hi = type7(u, 0.025), type7(u, 0.975)
    # uniform input: mass = hi - lo
    z = sorted(ND.inv_cdf((i + 0.5) / count) for i in range(count))
    zlo, zhi = type7(z, 0.025), type7(z, 0.975)
    mass_n = ND.cdf(zhi) - ND.cdf(zlo)
    print(f"  n={count:3d}: uniform mass={hi - lo:.4f} (formula 0.95-0.95/n={0.95 - 0.95 / count:.4f});"
          f"  normal: interval +/-{zhi:.3f} sd, mass={mass_n:.4f}")


# ---------------------------------------------------------------------------------------------- 3. Halton multistart geometry
# src/engcore/hybrid_uq/local_gaussian.py:98-119, 478-493 (index 1..starts, unscrambled, no skip, base = d-th prime)
PR = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def rinv(n, base):
    value, fraction = 0.0, 1.0 / base
    while n > 0:
        n, digit = divmod(n, base)
        value += digit * fraction
        fraction /= base
    return value


print("\n== 3. hybrid_uq multistart Halton starts (minimum canonical search starts = max(6, 2p+2)) ==")
for p in range(2, 11):
    starts = max(6, 2 * p + 2)
    pts = [[rinv(i, PR[d]) for d in range(p)] for i in range(1, starts + 1)]
    cols = [[pt[d] for pt in pts] for d in range(p)]
    worst = max(((abs(corr(cols[a], cols[b])), a, b) for a in range(p) for b in range(a + 1, p)))
    # how many of the starts satisfy u_d = i / b_d (first digit only) in the last two dims -> collinear through 0
    a, b = p - 2, p - 1
    collinear = sum(1 for i in range(1, starts + 1) if i < PR[a] and i < PR[b])
    # quadrant coverage in the last two dims of the inner box: (lo,hi) and (hi,lo) quadrants
    off = sum(1 for pt in pts if (pt[a] - 0.5) * (pt[b] - 0.5) < 0)
    print(f"  p={p:2d} starts={starts:2d}: worst |r| over dim pairs={worst[0]:.3f} (dims {worst[1]},{worst[2]});"
          f" last two dims (bases {PR[a]},{PR[b]}): {collinear}/{starts} starts on the ray u_b=(b_a/b_b)u_a;"
          f" starts in the two off-diagonal quadrants={off}")


# ---------------------------------------------------------------------------------------------- 4. symbolic_regression sort key
# src/engcore/scientific/discovery/symbolic_regression.py:142: (item.holdout_rmse or float("inf"))
print("\n== 4. symbolic_regression ranking key for a SURVIVED candidate ==")
for rmse in (0.0, 1e-300, 0.01):
    print(f"  holdout_rmse={rmse!r}: sort key = {(rmse or float('inf')) + 1e-4 * 1}")


# ---------------------------------------------------------------------------------------------- 5. structure digest rounding
# src/engcore/blindfold/expression.py:174 round(k, 3)
print("\n== 5. blindfold structure digest exponent rounding (round(k, 3)) ==")
for k in (1.2345, 1.23449, 1.23451, 1.2354, 0.0004, 0.0005, 0.0006, 1.0004, 2.675):
    print(f"  k={k!r}: round(k,3)={round(k, 3)!r}")


# ---------------------------------------------------------------------------------------------- 6. arms._fit residual ddof
print("\n== 6. genesis_lite arms._fit residual: np.std (ddof=0) / true sigma, expectation of sqrt factor ==")
for budget, names in ((12, 3), (12, 2), (30, 4), (30, 5), (60, 5)):
    replicate = min(4, budget // 4)
    fresh = budget - replicate
    train = int(0.75 * fresh)
    dof = train - (names + 1)
    print(f"  budget={budget} names={names}: train={train}, residual dof={dof}, sqrt(dof/n)={math.sqrt(max(dof, 0) / train):.3f}")
