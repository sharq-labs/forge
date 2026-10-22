"""The v2 truth table, computed only after the seal is verified.

There is no historical verdict for fresh data, so truth is the frozen reference protocol (``reference.py``) applied to
the pack: an independent implementation of the declared forward model, a denser oracle fit, and preregistered rules with
a 1.10 margin, where a marginal or rule-dependent instance is UNSCORED (None), never guessed.  ``extract`` refuses unless
results/SEAL.json is committed, PASS and binds unchanged files.  The reference reads the pack only, never an output.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from typing import Any

from ..candidate.common import load_pack
from . import reference

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parents[1]


class SealNotVerified(RuntimeError):
    pass


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def verify_seal(results: pathlib.Path) -> dict[str, Any]:
    """The seal exists, is PASS, is committed in HEAD's history with these bytes, and every bound file matches."""
    seal_path = results / "SEAL.json"
    if not seal_path.exists():
        raise SealNotVerified("no SEAL.json: the candidate outputs are not sealed")
    raw = seal_path.read_bytes()
    rel = str(seal_path.resolve().relative_to(ROOT)).replace("\\", "/")
    commits = _git("log", "--format=%H", "--", rel).split()
    if not commits:
        raise SealNotVerified("SEAL.json is not committed")
    committed = subprocess.run(["git", "show", f"{commits[-1]}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout
    if committed != raw:
        raise SealNotVerified("SEAL.json differs from the bytes first committed")
    seal = json.loads(raw)
    if seal["status"] != "PASS":
        raise SealNotVerified(f"the seal status is {seal['status']}")
    bound = dict(seal["outputs"]); bound.update(seal["access_log"]); bound.update(seal["leakage_pre_seal"])
    for path, sha in bound.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sha:
            raise SealNotVerified(f"{path} changed after the seal")
    return {"seal_sha256": hashlib.sha256(raw).hexdigest(), "seal_commit": commits[-1], "files_bound": len(bound)}


def extract(results: pathlib.Path) -> dict[str, Any]:
    seal = verify_seal(results)
    problems = load_pack()
    table = {pid: reference.truth_table(spec) for pid, spec in problems.items()}
    return {"schema": "forge.battery_rediscovery_v2.truth/1", "seal": seal,
            "reference_sha256": hashlib.sha256((HERE / "evaluator" / "reference.py").read_bytes()).hexdigest(),
            "table": table}


__all__ = ["SealNotVerified", "extract", "verify_seal"]
