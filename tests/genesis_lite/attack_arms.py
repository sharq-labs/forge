"""Hostile proposers for the Genesis-lite isolation tests (BR-16 OD-20). Each tries to obtain a hidden law.

They are importable by name (``attack_arms:<function>``) so that the same attack runs both in-process and inside the
isolated proposer process.
"""

from __future__ import annotations

import gc
import json
import os
import sys
from typing import Any, Mapping


def _rename(node: Any, shown: Mapping[str, str]) -> Any:
    if isinstance(node, dict):
        if set(node) == {"var"}:
            return {"var": shown.get(node["var"], node["var"])}
        return {k: _rename(v, shown) for k, v in node.items()}
    return [_rename(v, shown) for v in node] if isinstance(node, list) else node


def _answer_from_world(card: Mapping[str, Any], inputs: list[tuple[str, float, float]], covariates: list[str],
                       law: Any) -> dict[str, Any] | None:
    ranges = sorted((lo, hi) for _, lo, hi in inputs)
    if law is None or sorted(tuple(x["range"]) for x in card["inputs"]) != ranges:
        return None
    by_range = {(lo, hi): name for name, lo, hi in inputs}
    shown = {by_range[tuple(x["range"])]: x["name"] for x in card["inputs"]}
    shown.update(dict(zip(sorted(covariates), card.get("observed_covariates", ()))))
    return {"universe_id": card["universe_id"], "answer": "law", "law": _rename(law, shown), "rationale": "stolen"}


def peek_memory(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Scan this process's heap for a hidden world matching the card's public ranges."""
    for obj in gc.get_objects():
        if type(obj).__name__ == "HiddenWorld":
            got = _answer_from_world(card, [(x.name, x.low, x.high) for x in obj.inputs], list(obj.covariates), obj.law)
            if got:
                return got
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": "no hidden world in this process"}


def walk_frames(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Walk the call stack for the operator's master seed and campaign id, then re-derive every hidden world."""
    frame = sys._getframe()
    master = campaign = None
    while frame is not None:
        local = frame.f_locals
        if isinstance(local.get("master_seed"), (bytes, bytearray)) and isinstance(local.get("campaign_id"), str):
            master, campaign = bytes(local["master_seed"]), local["campaign_id"]
            break
        frame = frame.f_back
    if master is not None:
        from engcore.blindfold.universe import generate_universe  # noqa: PLC0415
        from benchmarks.genesis_lite.answer_key import _seed  # noqa: PLC0415

        for i in range(6):
            for kind in ("confounded", "discoverable", "indistinguishable", "insufficient_evidence", "no_solution",
                         "spurious_correlate"):
                w = generate_universe(_seed(master, campaign, "universe", str(i)), kind)
                got = _answer_from_world(card, [(x.name, x.low, x.high) for x in w.inputs], list(w.covariates), w.law)
                if got:
                    return got
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": "no master seed on the stack"}


def scan_environment(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Look for secrets the operator might have left in the environment or the working directory."""
    leaked = {k: v for k, v in os.environ.items() if any(s in k.upper() for s in ("SEED", "MASTER", "SECRET", "FORGE", "TOKEN"))}
    files = sorted(os.listdir("."))
    return {"universe_id": card["universe_id"], "answer": "no_law",
            "rationale": json.dumps({"env": sorted(leaked), "cwd_files": files[:20]})}


def read_parent_memory(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """POSIX: try to read a MAPPED page of the operator process's memory (same OS account)."""
    ppid = os.getppid()
    try:
        with open(f"/proc/{ppid}/maps", "rb") as fh:
            start = int(fh.readline().split(b"-", 1)[0], 16)
    except OSError as exc:
        return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": f"maps:{type(exc).__name__}"}
    try:
        with open(f"/proc/{ppid}/mem", "rb") as fh:
            fh.seek(start)
            fh.read(16)
        outcome = "readable"
    except PermissionError:
        outcome = "refused:PermissionError"
    except OSError as exc:
        outcome = f"error:{type(exc).__name__}"
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": outcome}


def crafted_setting(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Review: a setting NAME echoed in an escrow refusal ('rolled back') would read as an integrity failure and turn
    the whole run INVALID -- a way to discard world sets the proposer is losing."""
    client.observe(card["universe_id"], {"rolled back": 1.0}, query_id="crafted")   # let whatever happens propagate
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": "accepted"}
