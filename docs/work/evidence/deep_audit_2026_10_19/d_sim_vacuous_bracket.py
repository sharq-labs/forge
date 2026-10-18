"""INDEPENDENT DERIVATION (stdlib only; no engcore, no repo import).

Re-implements the preregistered INDISTINGUISHABLE pair rule as written in
benchmarks/genesis_lite/evaluator/score.py:90-117 (_pair_hit) and checks whether a VACUOUS pair
A = L*(1+K*r^m), B = L*(1+K*r^m)^-1 -- which says nothing about the extrapolation except "somewhere between
a huge and a tiny value" -- is scored a HIT on synthetic extended-region worlds whose out-of-box truth departs
strongly from the in-box power law. L is a NOISY in-box fit (not the truth).
"""
import math, random

PASS_FRACTION, PAIR_DIFFER_FRACTION = 0.9, 0.5


def frac_within(f, pts, tol):
    errs = []
    for p, t in pts:
        y = f(p)
        errs.append(abs(y - t) / abs(t) if (t and math.isfinite(t) and math.isfinite(y)) else math.inf)
    return sum(e <= tol for e in errs) / len(errs)


def pair_hit(A, B, truths, inbox, box, tol, sigma):
    pts = [p for p, _ in inbox] + [p for p, _ in truths]
    if not all(math.isfinite(f(p)) for f in (A, B) for p in pts):
        return False, "nonfinite"
    mutual = max(abs(A(p) - B(p)) / abs(B(p)) for p, _ in inbox if B(p) != 0)
    if not mutual <= sigma:
        return False, f"mutual {mutual:.3g} > sigma"
    if not all(frac_within(f, inbox, tol) >= PASS_FRACTION for f in (A, B)):
        return False, "in-box fit"
    outside = [(p, t) for p, t in truths if any(not (lo <= p[n] <= hi) for n, (lo, hi) in box.items())]
    if not outside:
        return False, "no outside"
    differ = bracket = 0
    for p, t in truths:
        a, b = A(p), B(p)
        if min(a, b) * (1 - tol) <= t <= max(a, b) * (1 + tol):
            bracket += 1
        if any(not (lo <= p[n] <= hi) for n, (lo, hi) in box.items()) and b != 0 and abs(a - b) / abs(b) > tol:
            differ += 1
    if differ / len(outside) < PAIR_DIFFER_FRACTION:
        return False, "differ"
    contains = any(frac_within(f, truths, tol) >= PASS_FRACTION for f in (A, B))
    return (contains or bracket / len(truths) >= PASS_FRACTION), f"bracket {bracket}/{len(truths)} contains={contains}"


def logu(rng, lo, hi):
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def trial(rng, departure):
    # a 2-input world; box per input; region extends both inputs upward by near..far box spans (like _extended_region)
    box = {}
    for n in ("x1", "x2"):
        lo = 10 ** rng.uniform(-1, 0.5)
        box[n] = (lo, lo * 10 ** rng.uniform(0.7, 1.3))
    near, far = rng.uniform(0.3, 0.5), rng.uniform(0.9, 1.3)
    region = {n: (hi * math.exp(near * math.log(hi / lo)), hi * math.exp(far * math.log(hi / lo))) for n, (lo, hi) in box.items()}
    a, b, c0 = rng.uniform(0.3, 2.0), rng.uniform(-2.0, -0.3), 10 ** rng.uniform(-1, 1)
    sigma = rng.uniform(0.005, 0.02)
    tol = max(0.03, 4 * sigma)
    hx = {n: hi for n, (lo, hi) in box.items()}
    rr = lambda p: math.prod(p[n] / hx[n] for n in p)            # >1 only beyond the box's upper corner

    def truth(p):  # power law inside the box; strongly different outside (factor exp(departure*(log r)^2))
        base = c0 * p["x1"] ** a * p["x2"] ** b
        lr = max(0.0, math.log(rr(p)))
        return base * math.exp(departure * lr * lr)

    # the proposer's NOISY in-box fit: constant off by ~sigma, exponents off by ~0.01
    ca, cb, cc = a + rng.gauss(0, 0.01), b + rng.gauss(0, 0.01), c0 * math.exp(rng.gauss(0, sigma / 2))
    L = lambda p: cc * p["x1"] ** ca * p["x2"] ** cb
    sig_hat = sigma * rng.uniform(0.7, 1.3)                       # replicate-noise estimate
    K, m = sig_hat / 3.0, 40.0
    A = lambda p: L(p) * (1 + K * rr(p) ** m)
    B = lambda p: L(p) / (1 + K * rr(p) ** m)
    evaluation = [({n: logu(rng, *region[n]) for n in region},) for _ in range(40)]
    evaluation = [(p, truth(p)) for (p,) in evaluation]
    inbox = [({n: logu(rng, *box[n]) for n in box},) for _ in range(40)]
    inbox = [(p, truth(p)) for (p,) in inbox]
    hit, why = pair_hit(A, B, evaluation, inbox, box, tol, sigma)
    honest = frac_within(L, evaluation, tol) >= PASS_FRACTION    # the in-box law as a LAW answer
    return hit, honest, why


rng = random.Random(20261019)
for departure in (0.0, 0.5, 2.0):
    res = [trial(rng, departure) for _ in range(2000)]
    hits = sum(h for h, _, _ in res)
    honest = sum(o for _, o, _ in res)
    fails = {}
    for h, _, w in res:
        if not h:
            k = w.split()[0]
            fails[k] = fails.get(k, 0) + 1
    print(f"departure={departure}: vacuous pair HIT {hits}/2000; in-box law passes as a law {honest}/2000; miss reasons {fails}")
