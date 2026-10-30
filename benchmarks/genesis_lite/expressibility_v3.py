"""EXC-4 pilot report helper: per-world grammar expressibility and the three pre-declared contrasts (DESCRIPTIVE).

Run ONLY after the pilot, with its revealed root (the reveal protocol: the answer key exists only after every universe
is sealed). Nothing here feeds back into any arm.

* **Expressibility** of a world's hidden law in the EXC-4 grammar, against the structures actually enumerated on the
  basis the arm itself would derive from the world's public card: every structure is fitted to the noiseless truth at
  :data:`PROBE_POINTS` log-uniform points of the query box; the world is ``EXPRESSIBLE_BY_FIT`` when some fit reproduces
  ln y to :data:`EXACT` everywhere. A local fit can miss an exact representation, so ``NOT_FOUND_BY_FIT`` is an upper
  bound on non-expressibility, never a proof. A hidden law that uses a passive covariate is ``OUTSIDE_GRAMMAR`` (the
  grammar never enters covariates); a world without a law is ``NO_LAW``.
* **Contrasts** (paired by escrow universe id: every arm saw the same worlds), per EXC-4 field 2:
  (i) ``grammar_enumeration`` - ``monomial_enumeration`` on discoverable worlds, split by the harness's
  ``truth_in_searched_family`` (monomial family) and by grammar expressibility; (ii) ``grammar_enumeration`` -
  ``pysr_symbolic``; (iii) false-law rate (answer ``law`` or ``indistinguishable``) on no_solution, confounded and
  insufficient_evidence worlds, ``grammar_enumeration`` vs ``careful``.

DEVELOPMENT_DESCRIPTIVE: counts and means only; no interval, test, rate, lift or ranking claim.

    python -m benchmarks.genesis_lite.expressibility_v3 --runs <runs.jsonl> --root-file <root hex file> --out <json>
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random
from typing import Any, Mapping

import numpy as np

from engcore.blindfold.expression import evaluate, validate
from engcore.blindfold.universe import generate_universe
from engcore.mind.grammar import DimensionRefused, InputDimension, analyse, enumerate_structures, fit, log_f

from .answer_key import _seed
from .arms_grammar_v3 import design_matrix
from .harness import KINDS, MIX
from .pilot_v3 import master_seed

PROBE_POINTS = 120
EXACT = 1e-6
GRAMMAR, MONOMIAL, PYSR, CAREFUL = "grammar_enumeration", "monomial_enumeration", "pysr_symbolic", "careful"
CONTROL_KINDS = ("no_solution", "confounded", "insufficient_evidence")


def worlds(master: bytes, campaign_id: str) -> list[Any]:
    """The campaign's hidden worlds, as the escrow and the answer key derive them (same kind order and seeds)."""
    from engcore.blindfold.universe import UniverseKind
    kinds = sorted((UniverseKind(k) for k, n in sorted(MIX.items()) for _ in range(int(n))), key=lambda k: k.value)
    random.Random(_seed(master, campaign_id, "shuffle")).shuffle(kinds)
    return [generate_universe(_seed(master, campaign_id, "universe", str(i)), kind) for i, kind in enumerate(kinds)]


def expressibility(world: Any) -> str:
    if world.law is None:
        return "NO_LAW"
    if validate(world.law) - {x.name for x in world.inputs}:
        return "OUTSIDE_GRAMMAR"
    card = world.public_card()
    try:
        basis = analyse([InputDimension(x["name"], x["unit"], x["range"][0], x["range"][1]) for x in card["inputs"]],
                        card["output"]["unit"], card["base_dimensions"])
    except DimensionRefused:
        return "OUTSIDE_GRAMMAR"
    rng = random.Random(f"expressibility:{world.universe_id}")
    rows = []
    for _ in range(PROBE_POINTS):
        pt = {x.name: math.exp(rng.uniform(math.log(x.low), math.log(x.high))) for x in world.inputs}
        y = evaluate(world.law, pt)
        if not (math.isfinite(y) and y > 0):
            return "OUTSIDE_GRAMMAR"
        rows.append({**pt, world.output: y})
    L, z = design_matrix(basis, rows, world.output)
    for s in enumerate_structures(len(basis.groups))[0]:
        f = fit(s, L, z)
        if f.ok and float(np.max(np.abs(log_f(s, np.asarray(f.theta), L) - z))) < EXACT:
            return "EXPRESSIBLE_BY_FIT"
    return "NOT_FOUND_BY_FIT"


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _diff(a: Mapping[str, float], b: Mapping[str, float], ids: list[str]) -> dict[str, Any]:
    pairs = [(a[u], b[u]) for u in ids if u in a and u in b]
    d = [x - y for x, y in pairs]
    return {"n": len(d), "a_ahead": sum(x > 0 for x in d), "b_ahead": sum(x < 0 for x in d), "mean_difference": _mean(d)}


def report(records: list[dict[str, Any]], root: bytes) -> dict[str, Any]:
    valid = [r for r in records if r.get("status") == "VALID"]
    credit: dict[str, dict[str, float]] = collections.defaultdict(dict)
    answer: dict[str, dict[str, str]] = collections.defaultdict(dict)
    kind, in_family, world_sets = {}, {}, {}
    for r in valid:
        for u in r["universes"]:
            credit[r["arm"]][u["universe_id"]] = float(u["credit"])
            answer[r["arm"]][u["universe_id"]] = u["answer"]
            kind[u["universe_id"]] = u["kind"]
            in_family[u["universe_id"]] = bool(u["truth_in_searched_family"])
        t = r["task"]
        world_sets[(t["seed"], t["campaign"], t["presentation"])] = None
    expr: dict[str, str] = {}
    for seed, campaign, presentation in sorted(world_sets):
        cid = f"gl-v03-dev-{seed}-{campaign}-{presentation}"
        for w in worlds(master_seed(root, campaign, presentation, seed), cid):
            if w.universe_id in kind:
                if w.kind.value != kind[w.universe_id]:
                    raise ValueError(f"re-derived world {w.universe_id} is {w.kind.value}, the run says {kind[w.universe_id]}")
                expr[w.universe_id] = expressibility(w)
    if set(expr) != set(kind):
        raise ValueError(f"{len(set(kind) - set(expr))} run universes were not re-derived from this root: wrong root "
                         "or records from another run")
    disc = sorted(u for u, k in kind.items() if k == "discoverable")
    by_expr = collections.Counter((kind[u], e) for u, e in expr.items())
    out: dict[str, Any] = {
        "label": "DEVELOPMENT_DESCRIPTIVE: counts and means only; no interval, test, rate, lift or ranking claim",
        "grammar": "five declared shapes (EXC-4 H2 owner decision 2026-10-30), not the operator/limit closure",
        "expressibility_by_kind": {f"{k}|{e}": n for (k, e), n in sorted(by_expr.items())},
        "contrast_i_grammar_minus_monomial_discoverable": {
            "all": _diff(credit[GRAMMAR], credit[MONOMIAL], disc),
            "in_monomial_family": _diff(credit[GRAMMAR], credit[MONOMIAL], [u for u in disc if in_family[u]]),
            "out_of_monomial_family": _diff(credit[GRAMMAR], credit[MONOMIAL], [u for u in disc if not in_family[u]]),
            "out_of_family_and_grammar_expressible": _diff(
                credit[GRAMMAR], credit[MONOMIAL], [u for u in disc if not in_family[u] and expr.get(u) == "EXPRESSIBLE_BY_FIT"]),
            "out_of_family_not_found_in_grammar": _diff(
                credit[GRAMMAR], credit[MONOMIAL], [u for u in disc if not in_family[u] and expr.get(u) == "NOT_FOUND_BY_FIT"]),
        },
        "contrast_ii_grammar_minus_pysr": {
            "all_kinds": _diff(credit[GRAMMAR], credit[PYSR], sorted(kind)),
            "discoverable": _diff(credit[GRAMMAR], credit[PYSR], disc),
        } if PYSR in credit else "PYSR_NOT_RUN",
        "contrast_iii_false_law_counts_on_controls": {},
        "mean_credit_by_kind": {arm: {k: _mean([c for u, c in credit[arm].items() if kind[u] == k]) for k in KINDS}
                                for arm in sorted(credit)},
    }
    for k in CONTROL_KINDS:
        ids = [u for u, kk in kind.items() if kk == k]
        out["contrast_iii_false_law_counts_on_controls"][k] = {
            arm: {"n": sum(u in answer[arm] for u in ids),
                  "false_law": sum(answer[arm].get(u) in ("law", "indistinguishable") for u in ids)}
            for arm in (GRAMMAR, CAREFUL)}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EXC-4 expressibility and contrasts (after the pilot, revealed root)")
    parser.add_argument("--runs", required=True)
    parser.add_argument("--root-file", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    records = [json.loads(line) for line in pathlib.Path(args.runs).read_text().splitlines() if line.strip()]
    root = bytes.fromhex(pathlib.Path(args.root_file).read_text().strip())
    result = report(records, root)
    pathlib.Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps({k: result[k] for k in ("expressibility_by_kind",)}, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
