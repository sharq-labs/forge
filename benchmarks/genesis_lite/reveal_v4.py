"""Post-run reveal for Genesis-lite v0.4: the per-universe REPRESENTATION verdicts ``analysis_v4`` needs (D10, G15).

Run only after every campaign is sealed. From the root file and the run records it re-derives every hidden world the
records name (same derivation as the escrow), refuses a root that does not reproduce them, and writes, per law-kind
universe, whether some BASELINE family represents its truth: the monomial family (the record's
``truth_in_searched_family``) or the frozen five-shape grammar (``expressibility_v3.expressibility`` by exact fit;
NOT_FOUND is an upper bound, so "not represented" can be conservative toward the candidate, never in its favour:
a capped cell can only cost the candidate credit).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from collections.abc import Iterable, Mapping
from typing import Any

from .analysis_v4 import LAW_KINDS
from .evaluator import score_v3
from .expressibility_v3 import expressibility, worlds
from .pilot_v4 import Task, campaign_id, master_seed, read_root


def represented(records: Iterable[Mapping[str, Any]], root: bytes) -> dict[str, Any]:
    valid = [r for r in records if r.get("status") == "VALID"]
    kinds: dict[str, str] = {}
    in_family: dict[str, bool] = {}
    world_sets: dict[str, tuple[str, Task]] = {}
    for r in valid:
        t = r["task"]
        task = Task(r["arm"], int(t["campaign"]), str(t["presentation"]), int(t["seed"]))
        cid = r["campaign_id"]
        world_sets[cid] = (cid, task)
        for u in r["universes"]:
            uid = u["universe_id"]
            if kinds.setdefault(uid, u["kind"]) != u["kind"]:
                raise ValueError(f"records disagree on the kind of universe {uid}")
            if u["kind"] in LAW_KINDS:
                flag = bool(u["truth_in_searched_family"])
                if in_family.setdefault(uid, flag) != flag:
                    raise ValueError(f"records disagree whether universe {uid}'s truth is in the monomial family")
    expr: dict[str, str] = {}
    for cid, task in world_sets.values():
        for w in worlds(master_seed(root, task.campaign, task.presentation, task.seed), cid):
            if w.universe_id in kinds:
                if w.kind.value != kinds[w.universe_id]:
                    raise ValueError(f"re-derived world {w.universe_id} is {w.kind.value}; the run says {kinds[w.universe_id]}")
                if w.kind.value in LAW_KINDS:
                    # recomputed from the re-derived world, never trusted from a record (review finding 8)
                    if w.law is None or score_v3.v2.in_monomial_family(w.law) != in_family[w.universe_id]:
                        raise ValueError(f"universe {w.universe_id}: the record's monomial-family flag is not the world's")
                    expr[w.universe_id] = expressibility(w)
    missing = sorted(set(in_family) - set(expr))
    if missing:
        raise ValueError(f"{len(missing)} law-kind universes were not re-derived from this root: wrong root or records")
    verdicts = {u: in_family[u] or expr[u] == "EXPRESSIBLE_BY_FIT" for u in sorted(in_family)}
    return {"schema": "forge.genesis_lite.reveal/4", "root_commitment_sha256": hashlib.sha256(root).hexdigest(),
            "represented": verdicts, "expressibility": dict(sorted(expr.items())),
            "monomial_family": dict(sorted(in_family.items())),
            "rule": "represented = monomial family OR five-shape grammar EXPRESSIBLE_BY_FIT"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="v0.4 post-run representation reveal")
    ap.add_argument("--runs", required=True)
    ap.add_argument("--root-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--commitment", required=True, help="the run's commitment.json, written before the run")
    a = ap.parse_args(argv)
    root = read_root(a.root_file)
    committed = json.loads(pathlib.Path(a.commitment).read_text())["root_commitment_sha256"]
    if hashlib.sha256(root).hexdigest() != committed:
        raise SystemExit("the root file does not match the run's commitment")
    runs = pathlib.Path(a.runs).read_text().splitlines()
    out = represented([json.loads(line) for line in runs if line.strip()], root)
    out["runs_sha256"] = hashlib.sha256(pathlib.Path(a.runs).read_bytes()).hexdigest()
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True))
    print(json.dumps({"law_universes": len(out["represented"]),
                      "represented": sum(out["represented"].values())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
