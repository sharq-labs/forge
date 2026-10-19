"""X3 independent derivation (stdlib only; never imports engcore). Re-implements, from reading the source, the
INDISTINGUISHABLE world generator (universe.py:266-394, simplified: same distributions) and the pair-hit rule
(escrow.py:570-609 == evaluator/score.py:90-117), then scores three proposer policies on clean extended cards:
  V  = vacuous pair  A = L(1+K s), B = L/(1+K s), s = sum over extended inputs of (x/high)^M or (low/x)^M, K=1e-4
  H  = extrapolation_pair-like pair  [L, L(1+0.5*sigma_hat*prod r^4)]   (arms.py:243-267)
  R  = honest refusal insufficient_evidence (credit 0.5 on indistinguishable, 0 on discoverable)
on INDISTINGUISHABLE worlds and on DISCOVERABLE-extended power-law worlds (where a pair hit earns -0.5).
"""
import itertools, math, random, sys

PASS, DIFFER = 0.9, 0.5

def rand_inputs(rng, nbase, count):
    out = []
    for i in range(count):
        dim = tuple(rng.choice((-1, 0, 0, 1, 1, 2)) for _ in range(nbase))
        if not any(dim):
            dim = tuple(1 if j == i % nbase else 0 for j in range(nbase))
        low = round(10 ** rng.uniform(-1, 0.5), 4)
        out.append((f"x{i+1}", dim, low, round(low * 10 ** rng.uniform(0.7, 1.3), 4)))
    return out

def groups_of(inputs, rng, want=2):
    names = [x[0] for x in inputs]; dims = [x[1] for x in inputs]
    combos = list(itertools.product(range(-2, 3), repeat=len(inputs))); rng.shuffle(combos)
    found = []
    for combo in combos:
        if not any(combo) or sum(1 for e in combo if e) < 2: continue
        if any(sum(e * d[i] for e, d in zip(combo, dims)) for i in range(len(dims[0]))): continue
        vec = {n: e for n, e in zip(names, combo) if e}
        if any(set(vec) == set(f) for f in found): continue
        found.append(vec)
        if len(found) == want: break
    return found

def mono(p, exps):
    return math.prod(p[n] ** e for n, e in exps.items())

def sample(rng, region):
    return {n: math.exp(rng.uniform(math.log(lo), math.log(hi))) for n, (lo, hi) in sorted(region.items())}

def ext_region(inputs, group, near, far):
    reg = {}
    for n, _d, lo, hi in inputs:
        e, span = group.get(n, 0), math.log(hi / lo)
        if e > 0: reg[n] = (hi * math.exp(near * span), hi * math.exp(far * span))
        elif e < 0: reg[n] = (lo * math.exp(-far * span), lo * math.exp(-near * span))
        else: reg[n] = (lo, hi)
    return reg

def make_world(rng, kind):
    nbase = rng.choice((2, 3))
    for _ in range(200):
        inputs = rand_inputs(rng, nbase, rng.choice((3, 4)))
        groups = groups_of(inputs, rng)
        if groups: break
    else:
        return None
    j = rng.randrange(len(inputs)); p = rng.choice((1, 1, 2, -1))
    exps = [round(rng.uniform(0.2, 2.8) * rng.choice((-1, 1)), 3) for _ in groups]
    const = 10 ** rng.uniform(-1, 1)
    box = {n: (lo, hi) for n, _d, lo, hi in inputs}
    form = rng.choice(("power", "exp")) if kind == "I" else "power"
    def law(pt):
        y = const * pt[inputs[j][0]] ** p * math.prod(mono(pt, g) ** e for g, e in zip(groups, exps))
        if form == "exp":
            return y * math.exp(-b * mono(pt, groups[0]) / (1 + mono(pt, groups[0]) / g_ref))
        return y
    corners = [dict(zip(sorted(box), c)) for c in itertools.product(*[box[n] for n in sorted(box)])]
    g_ref = max(mono(pt, groups[0]) for pt in corners); b = rng.uniform(0.3, 2.0) / g_ref
    sigma = round(rng.uniform(0.005, 0.02), 4); tol = max(0.03, 4 * sigma)
    near, far = rng.uniform(0.3, 0.5), rng.uniform(0.9, 1.3)
    budget = rng.choice((12, 30, 60))
    truth = law
    if kind == "I":
        grid = corners + [sample(rng, box) for _ in range(256)]
        gmax = max(mono(pt, groups[0]) for pt in grid); m = rng.uniform(3.0, 4.5); d = 0.5 * sigma
        rival = lambda pt: law(pt) * (1 + d * (mono(pt, groups[0]) / gmax) ** m)
        for _ in range(12):
            region = ext_region(inputs, groups[0], near, far)
            ev = [sample(rng, region) for _ in range(40)]
            if sum(abs(rival(q) - law(q)) / law(q) > 3 * tol for q in ev) >= 36: break
            near, far = near * 1.4, far * 1.4
        else:
            return None
        truth = rival if rng.random() < 0.5 else law
    else:
        region = ext_region(inputs, groups[0], near, far)
        ev = [sample(rng, region) for _ in range(40)]
    inbox = [sample(rng, box) for _ in range(40)]
    return dict(box=box, region=region, ev=[(q, truth(q)) for q in ev], inbox=[(q, truth(q)) for q in inbox],
                sigma=sigma, tol=tol, budget=budget, truth=truth)

def solve(A, y):
    n = len(A[0]); M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(n)] + [sum(A[k][i] * y[k] for k in range(len(A)))] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-14: return None
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]; M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]

def fit(world, rng):
    names = sorted(world["box"]); rows, ys = [], []
    for _ in range(world["budget"]):
        q = sample(rng, world["box"])
        y = world["truth"](q) * math.exp(rng.gauss(0, world["sigma"]))
        rows.append([1.0] + [math.log(q[n]) for n in names]); ys.append(math.log(y))
    coef = solve(rows, ys)
    if coef is None: return None, None
    res = [y - sum(c * a for c, a in zip(coef, r)) for r, y in zip(rows, ys)]
    shat = math.sqrt(sum(e * e for e in res) / max(1, len(res) - len(coef)))
    return (lambda q: math.exp(coef[0] + sum(c * math.log(q[n]) for c, n in zip(coef[1:], names)))), shat

def finite(x): return x is not None and math.isfinite(x)

def frac_within(law, pts, tol):
    ok = 0
    for q, t in pts:
        v = law(q)
        ok += finite(v) and finite(t) and t != 0 and abs(v - t) / abs(t) <= tol
    return ok / len(pts)

def outside(q, box): return any(not (lo <= q[n] <= hi) for n, (lo, hi) in box.items())

def pair_hit(A, B, w):
    tol, sigma, box = w["tol"], w["sigma"], w["box"]
    pts = [q for q, _ in w["inbox"]] + [q for q, _ in w["ev"]]
    try:
        if not all(finite(A(q)) and finite(B(q)) for q in pts): return False
    except OverflowError:
        return False
    mutual = max(abs(A(q) - B(q)) / abs(B(q)) for q, _ in w["inbox"] if B(q) != 0)
    if not mutual <= sigma: return False
    if not (frac_within(A, w["inbox"], tol) >= PASS and frac_within(B, w["inbox"], tol) >= PASS): return False
    outs = [(q, t) for q, t in w["ev"] if outside(q, box)]
    if not outs: return False
    differ = bracket = 0
    for q, t in w["ev"]:
        a, b = A(q), B(q)
        if min(a, b) * (1 - tol) <= t <= max(a, b) * (1 + tol): bracket += 1
        if outside(q, box) and b != 0 and abs(a - b) / abs(b) > tol: differ += 1
    if differ / len(outs) < DIFFER: return False
    return frac_within(A, w["ev"], tol) >= PASS or frac_within(B, w["ev"], tol) >= PASS or bracket / len(w["ev"]) >= PASS

def ext_terms(w):
    terms = []
    for n, (lo, hi) in w["region"].items():
        blo, bhi = w["box"][n]
        if hi > bhi * (1 + 1e-9): terms.append((n, +1, bhi, hi / bhi))
        elif lo < blo * (1 - 1e-9): terms.append((n, -1, blo, blo / lo))
    return terms

def vacuous(L, w, K=1e-4):
    terms = ext_terms(w)
    worst = max(r for *_x, r in terms)
    M = max(8.0, min(60.0, 250.0 / math.log(worst)))          # keep K*s far below overflow at the region's far corner
    def s(q):
        return sum((q[n] / b) ** M if sgn > 0 else (b / q[n]) ** M for n, sgn, b, _r in terms)
    return (lambda q: L(q) * (1 + K * s(q))), (lambda q: L(q) / (1 + K * s(q))), M

def heuristic(L, shat, w):
    terms = ext_terms(w); d = 0.5 * shat
    f = lambda q: math.prod((q[n] / b) ** 4 if sgn > 0 else (b / q[n]) ** 4 for n, sgn, b, _r in terms)
    return L, (lambda q: L(q) * (1 + d * f(q)))

def main(n=int(sys.argv[1]) if len(sys.argv) > 1 else 1500):
    rng = random.Random(20261019)
    for kind in ("I", "D"):
        stats = dict(worlds=0, vac_hit=0, heur_hit=0, law_pass=0, fit_fail=0, Ms=[])
        while stats["worlds"] < n:
            w = make_world(rng, kind)
            if w is None: continue
            L, shat = fit(w, rng)
            if L is None: continue
            stats["worlds"] += 1
            A, B, M = vacuous(L, w); stats["Ms"].append(M)
            stats["vac_hit"] += pair_hit(A, B, w)
            HA, HB = heuristic(L, shat, w)
            stats["heur_hit"] += pair_hit(HA, HB, w)
            stats["law_pass"] += frac_within(L, w["ev"], w["tol"]) >= PASS
            stats["fit_fail"] += frac_within(L, w["inbox"], w["tol"]) < PASS
        k = stats["worlds"]
        Ms = sorted(stats["Ms"])
        print(f"kind={kind} worlds={k} vacuous_hit={stats['vac_hit']/k:.3f} heuristic_hit={stats['heur_hit']/k:.3f} "
              f"in-box-fit-fails={stats['fit_fail']/k:.3f} law_pass={stats['law_pass']/k:.3f} M[min,med,max]="
              f"{Ms[0]:.1f},{Ms[len(Ms)//2]:.1f},{Ms[-1]:.1f}")
        if kind == "I":
            vh, hh, lp = stats["vac_hit"]/k, stats["heur_hit"]/k, stats["law_pass"]/k
            print(f"  expected credit on I:  vacuous {vh*1 + (1-vh)*-1:+.3f}   heuristic {hh - (1-hh):+.3f}   refusal +0.500   "
                  f"law {lp*0 + (1-lp)*-1:+.3f}")
        else:
            vh = stats["vac_hit"]/k
            print(f"  expected credit on D-ext: vacuous {vh*-0.5 + (1-vh)*-1:+.3f}   refusal +0.000   law(fit) "
                  f"{stats['law_pass']/k - (1 - stats['law_pass']/k):+.3f}")

if __name__ == "__main__":
    main()
