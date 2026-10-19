"""Independent derivation (stdlib only): can an FTCS run past r = 1/2 be corrupted at O(0.1) while
max|u| <= 1 + 1e-9 (the conduction1d_schemes 'amplitude_decay' PASS bound, conduction1d_schemes.py:641-643)?

Emulates _BandedBackend.explicit_stepper (conduction1d_schemes.py:414-419) operation-for-operation in Python
floats: out = (1-2r)*u ; out[:-1] += r*u[1:] ; out[1:] += r*u[:-1], with interior initial data
sin(pi x / L) on linspace(0, L, n+1) (conduction1d_schemes.py:361-367). The reference is the exact discrete
FTCS evolution of the fundamental: g1**k * sin(pi x/L), g1 = 1 - 4 r sin^2(pi dx / (2L)).
No FORGE code is imported.
"""
import math

def run(n_cells, r, n_steps):
    L = 1.0
    xs = [L * i / n_cells for i in range(n_cells + 1)]  # linspace endpoints exact
    u = [math.sin(math.pi * x / L) for x in xs[1:-1]]
    g1 = 1.0 - 4.0 * r * math.sin(math.pi / (2 * n_cells)) ** 2
    hits = []
    for k in range(1, n_steps + 1):
        out = [(1.0 - 2.0 * r) * v for v in u]
        for i in range(len(u) - 1):
            out[i] += r * u[i + 1]
        for i in range(1, len(u)):
            out[i] += r * u[i - 1]
        u = out
        if not all(math.isfinite(v) for v in u):
            return hits, k
        mx = max(abs(v) for v in u)
        ref = [g1 ** k * math.sin(math.pi * x / L) for x in xs[1:-1]]
        err = max(abs(a - b) for a, b in zip(u, ref))
        if mx <= 1.0 + 1e-9 and err >= 0.05:
            hits.append((k, mx, err, g1 ** k))
    return hits, None

for n_cells, r in ((20, 0.55), (20, 0.6), (40, 0.6), (40, 0.75)):
    hits, nonfinite = run(n_cells, r, 3000)
    if hits:
        k, mx, err, amp = hits[0]
        print(f"n_cells={n_cells} r={r}: first corrupted-yet-PASS step k={k}: max|u|={mx:.4f} <= 1+1e-9, "
              f"error vs discrete fundamental {err:.3f} (fundamental amplitude {amp:.3f}); "
              f"{len(hits)} such steps; non-finite at step {nonfinite}")
    else:
        print(f"n_cells={n_cells} r={r}: no corrupted-yet-PASS step found (non-finite at {nonfinite})")
