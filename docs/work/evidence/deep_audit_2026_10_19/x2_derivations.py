"""X2 cross-review: independent stdlib-only re-derivations (no engcore, no numpy).

Each section restates the arithmetic of the cited source lines from scratch.
Run: python.exe -I -S x2_derivations.py
"""
from fractions import Fraction as F
import math, random, statistics


def hr(t):
    print("\n==== " + t)


# ---------------------------------------------------------------- B-01
hr("B-01 materials/properties.py:329-367 duplicate positions in the bracket")
# data sorted by claim_id (properties.py:272); points built in that order (:330); stable sort by position (:347)
data = sorted([("a", 300, 10.0), ("b", 300, 20.0), ("c", 400, 30.0)], key=lambda d: d[0])
for ids in (("a", "b"), ("b", "a")):
    d = [(ids[0], 300, 10.0), (ids[1], 300, 20.0), ("c", 400, 30.0)]
    d = sorted(d, key=lambda x: x[0])
    pts = sorted([(F(x[1]), x) for x in d], key=lambda p: p[0])
    v = F(350)
    below = [p for p in pts if p[0] < v]
    above = [p for p in pts if p[0] > v]
    lo, hi = below[-1], above[0]
    w = (v - lo[0]) / (hi[0] - lo[0])
    val = lo[1][2] + float(w) * (hi[1][2] - lo[1][2])
    print(f"claim ids at 300K -> 10:{ids[0]} 20:{ids[1]}; lo={lo[1][0]} (k={lo[1][2]}), result={val}; used={{{lo[1][0]},{hi[1][0]}}}")

# ---------------------------------------------------------------- B-02
hr("B-02 materials/ranges.py:71-82 point test after affine conversion")
up_in_c = 300.0 - 273.15          # pint offset conversion K -> degC: (v - offset)/scale
print("300 K in degC =", repr(up_in_c), " == 26.85 ?", up_in_c == 26.85, "; < 26.85 ?", up_in_c < 26.85)
print("26.85 degC in K =", repr(26.85 + 273.15))
print("sliver width (degC):", float(F(repr(up_in_c)) - F(repr(26.85))))

# ---------------------------------------------------------------- B-03
hr("B-03 dc/validation.py:288-335 residual gate under a common-mode offset")
def dc_case(vcm, corrupt=F(1, 10000)):
    G = F(1)
    Va, Vc = vcm + F(1, 1000), vcm
    Vm = (Va + Vc) / 2
    I1 = -G * (Va - Vm)       # node a: G(Va-Vm) + I1 = 0
    I2 = -G * (Vc - Vm)
    x = [Va, Vm + corrupt, Vc, I1, I2]
    A = [[G, -G, 0, 1, 0], [-G, 2 * G, -G, 0, 0], [0, -G, G, 0, 1], [1, 0, 0, 0, 0], [0, 0, 1, 0, 0]]
    z = [0, 0, 0, Va, Vc]
    r = [sum(A[i][j] * x[j] for j in range(5)) - z[i] for i in range(5)]
    scale = [sum(abs(A[i][j]) * abs(x[j]) for j in range(5)) + abs(z[i]) for i in range(5)]
    rtol = atol = F(1, 10**9)
    floor_node = atol * max(scale[:3]); floor_src = atol * max(scale[3:])
    tol = [rtol * scale[i] + (floor_node if i < 3 else floor_src) for i in range(5)]
    passed = all(abs(r[i]) <= tol[i] for i in range(5))
    # KCL at m from components: imbalance against gross current (check_kcl's scale)
    Iam = (x[1] - x[0]) / 1; Imc = (x[1] - x[2]) / 1
    imb = abs(Iam + Imc); gross = abs(Iam) + abs(Imc)
    return float(abs(r[1])), float(tol[1]), passed, float(imb), float(gross)
for vcm in (F(0), F(1000), F(10**6)):
    rm, tm, ok, imb, gross = dc_case(vcm)
    print(f"Vcm={float(vcm):9.0f}  |r_m|={rm:.2e} tol_m={tm:.2e} residual_gate={'PASS' if ok else 'FAIL'}  KCL imbalance={imb:.1e} vs gross {gross:.1e}")
# smallest common mode at which the 20% corruption passes the residual gate
lo_, hi_ = F(1000), F(10**6)
for _ in range(60):
    mid = (lo_ + hi_) / 2
    if dc_case(mid)[2]: hi_ = mid
    else: lo_ = mid
print("residual gate first passes the +0.1 mV (20 %) corruption at Vcm ~", round(float(hi_)), "V")

# ---------------------------------------------------------------- B-04
hr("B-04 conduction1d_schemes.py:414-419 / :388-399 FTCS window with max|u| <= 1")
def ftcs(n_cells, r, steps, order):
    n = n_cells - 1
    u = [math.sin(math.pi * (i + 1) / n_cells) for i in range(n)]
    main = 1.0 - 2.0 * r
    g1 = 1.0 - 4.0 * r * math.sin(math.pi / (2 * n_cells)) ** 2
    rows = []
    for k in range(1, steps + 1):
        if order == "banded":       # out=(1-2r)u; out[:-1]+=r*u[1:]; out[1:]+=r*u[:-1]
            out = [main * v for v in u]
            for i in range(n - 1): out[i] += r * u[i + 1]
            for i in range(1, n): out[i] += r * u[i - 1]
        else:                       # CSC matvec, columns ascending: y[i] = ((off*u[i-1]) + main*u[i]) + off*u[i+1]
            out = [0.0] * n
            for j in range(n):
                if j - 1 >= 0: out[j - 1] += r * u[j]
                out[j] += main * u[j]
                if j + 1 < n: out[j + 1] += r * u[j]
        u = out
        if not all(math.isfinite(v) for v in u): break
        mx = max(abs(v) for v in u)
        exact = [g1 ** k * math.sin(math.pi * (i + 1) / n_cells) for i in range(n)]
        err = max(abs(a - b) for a, b in zip(u, exact))
        rows.append((k, mx, err, g1 ** k))
    return rows
for n_cells, r, steps in ((20, 0.55, 400), (40, 0.75, 120)):
    for order in ("banded", "csc"):
        rows = ftcs(n_cells, r, steps, order)
        window = [t for t in rows if t[1] <= 1.0 + 1e-9 and t[2] >= 0.10 * t[3]]
        if window:
            k, mx, err, amp = max(window, key=lambda t: t[2] / t[3])
            print(f"n={n_cells} r={r} {order:6s}: {len(window)} steps pass amplitude_decay with error >=10% of fundamental; "
                  f"worst k={k}: max|u|={mx:.3f} err={err:.3g} fundamental={amp:.3g} (err/fund={err/amp:.2f})")
        else:
            print(f"n={n_cells} r={r} {order}: no window")

# ---------------------------------------------------------------- E-01
hr("E-01 mcp/probabilistic_uq.py:47,122,138-141 stratum midpoints + type-7 quantile")
def q7(sorted_vals, p):
    h = (len(sorted_vals) - 1) * p
    lo = math.floor(h); hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (h - lo) * (sorted_vals[hi] - sorted_vals[lo])
N = statistics.NormalDist()
for n in (4, 8, 32, 256):
    base = [(i + 0.5) / n for i in range(n)]
    lo, hi = q7(base, 0.025), q7(base, 0.975)
    nb = [N.inv_cdf(b) for b in base]
    nlo, nhi = q7(nb, 0.025), q7(nb, 0.975)
    nmass = N.cdf(nhi) - N.cdf(nlo)
    print(f"n={n:3d}: uniform mass={hi-lo:.4f} (0.95-0.95/n={0.95-0.95/n:.4f}); normal mass={nmass:.4f} half-width={nhi:.3f} sd")
# Hazen check: positions (i+0.5)/n reproduce p exactly
n = 32; base = [(i + 0.5) / n for i in range(n)]
def hazen(v, p):
    h = n * p - 0.5; lo = math.floor(h); return v[lo] + (h - lo) * (v[lo + 1] - v[lo])
print("hazen at n=32:", round(hazen(base, 0.975) - hazen(base, 0.025), 6))

# ---------------------------------------------------------------- E-02
hr("E-02 mcp/probabilistic_uq.py:54-59 lattice permutation columns")
def columns(n, k):
    base = [(i + 0.5) / n for i in range(n)]
    cols = []
    for c in range(k):
        s = 2 * c + 1
        while math.gcd(s, n) != 1: s += 2
        cols.append([base[(i * s + c) % n] for i in range(n)])
    return cols
def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)
for n, k in ((4, 3), (4, 4), (6, 4), (8, 6), (32, 2), (32, 17)):
    cols = columns(n, k)
    worst = max(((i, j, corr(cols[i], cols[j])) for i in range(k) for j in range(i + 1, k)), key=lambda t: abs(t[2]))
    print(f"n={n:2d} k={k:2d}: worst pair {worst[:2]} r={worst[2]:+.3f}")
cols = columns(4, 4)
y = [a + b for a, b in zip(cols[1], cols[2])]
print("n=4: X1+X2 samples:", y, " sd:", statistics.stdev(y))
# smallest input count k that yields an exact |r|=1 pair, per n (default n=32 included)
for n in (4, 6, 8, 10, 12, 16, 32, 64):
    found = None
    for k in range(2, 60):
        cols = columns(n, k)
        if any(abs(corr(cols[i], cols[j])) > 1 - 1e-12 for i in range(k) for j in range(i + 1, k)):
            found = k; break
    print(f"n={n:2d}: first exact |r|=1 pair at k={found} inputs")

# ---------------------------------------------------------------- E-03
hr("E-03 hybrid_uq/local_gaussian.py:98-119,478-493 unscrambled Halton, starts=2p+2")
PR = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
def rad(i, b):
    v, f = 0.0, 1.0 / b
    while i > 0:
        i, d = divmod(i, b); v += d * f; f /= b
    return v
for p in (5, 6, 8, 10):
    N_ = 2 * p + 2
    a, b = PR[p - 2], PR[p - 1]
    pts = [(rad(i, a), rad(i, b)) for i in range(1, N_ + 1)]
    on_ray = sum(1 for (x, y) in pts if abs(y - x * a / b) < 1e-15)
    above = sum(1 for (x, y) in pts if y > x)   # half-plane u_b > u_a
    q_ul = sum(1 for (x, y) in pts if x < 0.5 and y > 0.5)
    q_lr = sum(1 for (x, y) in pts if x > 0.5 and y < 0.5)
    print(f"p={p:2d} N={N_:2d} last dims bases ({a},{b}): on ray {on_ray}/{N_}; u_b>u_a: {above}; quadrants UL={q_ul} LR={q_lr} "
          f"(random expectation per quadrant {N_/4:.1f})")

# ---------------------------------------------------------------- E-04
hr("E-04/D-08 discovery/symbolic_regression.py:84-146 absolute 0.05 gate on pure-noise targets")
def lstsq(X, y):
    # normal equations with intercept, Gaussian elimination (small k)
    m = len(X[0]) + 1
    Z = [[1.0] + list(r) for r in X]
    M = [[sum(Z[t][i] * Z[t][j] for t in range(len(Z))) for j in range(m)] + [sum(Z[t][i] * y[t] for t in range(len(Z)))] for i in range(m)]
    for c in range(m):
        piv = max(range(c, m), key=lambda r_: abs(M[r_][c])); M[c], M[piv] = M[piv], M[c]
        for r_ in range(m):
            if r_ != c:
                f = M[r_][c] / M[c][c]
                M[r_] = [a - f * b for a, b in zip(M[r_], M[c])]
    return [M[i][m] / M[i][i] for i in range(m)]
from itertools import combinations
rng = random.Random(20261019)
for sd in (0.01, 0.03, 0.2):
    surv_frac, top_surv = [], 0
    for rep in range(60):
        nf, ncal, nho = 10, 30, 15
        F_ = [[rng.gauss(0, 1) for _ in range(ncal + nho)] for _ in range(nf)]
        y = [rng.gauss(0, sd) for _ in range(ncal + nho)]
        cal, ho = range(ncal), range(ncal, ncal + nho)
        ycal = [y[i] for i in cal]; yho = [y[i] for i in ho]
        mean_c = sum(ycal) / ncal
        base = math.sqrt(sum((v - mean_c) ** 2 for v in yho) / nho)
        s = t = 0
        for k in (1, 2, 3):
            for idx in combinations(range(nf), k):
                beta = lstsq([[F_[j][i] for j in idx] for i in cal], ycal)
                pred = [beta[0] + sum(beta[1 + q] * F_[j][i] for q, j in enumerate(idx)) for i in ho]
                rm = math.sqrt(sum((a - b) ** 2 for a, b in zip(pred, yho)) / nho)
                t += 1
                if rm <= 0.05 and base - rm >= 0.0: s += 1
        surv_frac.append(s / t); top_surv += (s > 0)
    print(f"noise sd={sd}: mean survivor fraction {sum(surv_frac)/len(surv_frac):.2f}; datasets with >=1 survivor "
          f"(so the top-ranked candidate is a survivor): {top_surv}/60")

# ---------------------------------------------------------------- E-06
hr("E-06 execution/multiphysics/mapping.py:208-216 quad = tri(0,1,2) U tri(0,2,3)")
V = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (1.5, 0.5)]
area2 = sum(V[i][0] * V[(i + 1) % 4][1] - V[(i + 1) % 4][0] * V[i][1] for i in range(4))
def turn(a, b, c): return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
print("signed 2*area:", area2, " turns:", [turn(V[i - 1], V[i], V[(i + 1) % 4]) for i in range(4)])
def tri_contains(p, a, b, c, tol=0.0):
    d = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
    u = ((p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])) / d
    v = ((b[0] - a[0]) * (p[1] - a[1]) - (p[0] - a[0]) * (b[1] - a[1])) / d
    return u >= -tol and v >= -tol and u + v <= 1 + tol
def polygon_contains(p, poly):  # even-odd ray cast, exact for this point
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > p[1]) != (y2 > p[1]):
            xin = x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1)
            if xin > p[0]: inside = not inside
    return inside
P = (1.0, 0.6)
print("code split says inside:", tri_contains(P, V[0], V[1], V[2]) or tri_contains(P, V[0], V[2], V[3]),
      "; true polygon contains:", polygon_contains(P, V),
      "; the other diagonal split (0,1,3)U(1,2,3):", tri_contains(P, V[0], V[1], V[3]) or tri_contains(P, V[1], V[2], V[3]))
