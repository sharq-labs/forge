"""Synthetic run records in the shape the harness writes, for the Genesis-lite lift-rule tests.

Credits are values of the frozen DEFAULT_CREDIT table (1.0 or -1.0 here) with a deterministic per-world-set pattern, so
that paired differences have spread; every universe carries an id, the independent evaluator's agreement and the
searched-family flag. ``field`` supplies every registered non-adversarial arm, because v0.2 compares against all of them.
"""

from __future__ import annotations

from benchmarks.genesis_lite import analysis, arms

KINDS = analysis.KINDS
PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")
CAMPAIGNS = [f"c{i}" for i in range(30)]
SEEDS = (0, 1)
GRID = analysis.formal_grid(CAMPAIGNS, PRESENTATIONS, SEEDS)
BASELINES = sorted(n for n, entry in arms.ARMS.items() if entry[3] in ("competence", "floor", "sanity"))
WEAK = {k: 0.3 for k in KINDS}
CAREFUL = dict(discoverable=0.3, **{k: 0.8 for k in KINDS if k != "discoverable"})
BETTER = dict(CAREFUL, discoverable=0.8)


def credit(rate: float, i: int, s: int, kind: str) -> float:
    return 1.0 if (i * 7 + s * 3 + len(kind)) % 10 < round(rate * 10) else -1.0


def records(arm, rates, *, grid=GRID, status="VALID", ids=True, id_prefix="", out_of_family=lambda ws: False,
            credit_fn=None, isolation="proposer_process"):
    out = []
    for p, c, s in sorted(grid):
        i = int(c[1:]) if c[1:].isdigit() else 0
        universes = []
        for k in KINDS:
            u = {"kind": k, "credit": credit_fn(p, c, s, k) if credit_fn else credit(rates[k], i, s, k),
                 "independent_agrees": True, "truth_in_searched_family": not (k == "discoverable" and out_of_family((p, c, s)))}
            if ids:
                u["universe_id"] = f"{id_prefix}{p}-{s}-{c}-{k}"
            universes.append(u)
        out.append({"arm": arm, "status": status, "presentation": p, "campaign_id": c, "seed": s, "isolation": isolation,
                    "universes": universes})
    return out


def field(**override):
    """Every registered non-adversarial arm (weak), careful as the strongest, plus overrides (None drops an arm)."""
    rows = []
    for name in BASELINES:
        spec = override.get(name, CAREFUL if name == "careful" else WEAK)
        if spec is None:
            continue
        rows += spec if isinstance(spec, list) else records(name, spec)
    return rows
