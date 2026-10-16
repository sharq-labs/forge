"""Synthetic run records in the shape the harness writes, for the Genesis-lite lift-rule tests.

Credits are values of the frozen DEFAULT_CREDIT table (1.0 or -1.0 here) with a deterministic per-world-set pattern, so
that paired differences have spread; every universe carries an id, the independent evaluator's agreement and the
searched-family flag. ``field`` supplies every registered non-adversarial arm, because v0.2 compares against all of them.
"""

from __future__ import annotations

from benchmarks.genesis_lite import analysis, arms, preregistration
from engcore.blindfold.roles import DEFAULT_CREDIT

KINDS = analysis.KINDS
PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")
CAMPAIGNS = [f"c{i}" for i in range(30)]
SEEDS = (0, 1)
GRID = analysis.formal_grid(CAMPAIGNS, PRESENTATIONS, SEEDS)
BASELINES = sorted(n for n, entry in arms.ARMS.items() if entry[3] in ("competence", "floor", "sanity"))
WEAK = {k: 0.3 for k in KINDS}
CAREFUL = dict(discoverable=0.3, **{k: 0.8 for k in KINDS if k != "discoverable"})
BETTER = dict(CAREFUL, discoverable=0.8)
#: the reason the harness records when the literal leakage audit refuses a presented card (an arm-independent screen)
SCREEN_REASON = "leakage audit: [{'universe_id': 'bf-x', 'leak': 'hidden numbers appear on the card: [0.642]'}]"
PREREG_SHA256 = preregistration.PREREG_PATH.with_suffix(".sha256").read_bytes().split()[0].decode()


def outcome_for(kind: str, value: float) -> str:
    """An outcome whose DEFAULT_CREDIT value is ``value`` (unlisted outcomes score 0)."""
    for outcome, credit in sorted(DEFAULT_CREDIT[kind].items()):
        if credit == value:
            return outcome
    return "unlisted_outcome" if value == 0.0 else "no_such_outcome"


def credit(rate: float, i: int, s: int, kind: str) -> float:
    return 1.0 if (i * 7 + s * 3 + len(kind)) % 10 < round(rate * 10) else -1.0


def records(arm, rates, *, grid=GRID, status="VALID", ids=True, id_prefix="", out_of_family=lambda ws: False,
            credit_fn=None, isolation="proposer_process"):
    out = []
    for p, c, s in sorted(grid):
        i = int(c[1:]) if c[1:].isdigit() else 0
        universes = []
        for k in KINDS:
            value = credit_fn(p, c, s, k) if credit_fn else credit(rates[k], i, s, k)
            u = {"kind": k, "credit": value, "outcome": outcome_for(k, value), "independent_agrees": True,
                 "truth_in_searched_family": not (k == "discoverable" and out_of_family((p, c, s)))}
            if ids:
                u["universe_id"] = f"{id_prefix}{p}-{s}-{c}-{k}"
            universes.append(u)
        out.append({"arm": arm, "status": status, "presentation": p, "campaign_id": c, "seed": s, "isolation": isolation,
                    "reasons": [], "prereg_sha256": PREREG_SHA256, "universes": universes})
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
