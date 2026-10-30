"""The v0.4 decision from a sealed run directory (review findings 3, 4 and 10 of 2026-10-30).

``analysis_v4.decision`` is the pure rule; it takes roles, grid and representation verdicts as arguments. This entry
point takes NONE of them from the caller:

* roles come from the frozen roster in code (:func:`pilot_v4.roles`), bound by ``development_identity_v4``;
* the grid comes from the task list in ``commitment.json``, written before the first campaign; every planned arm must
  appear and nothing else may;
* ``runs.jsonl`` must match the digest in ``summary.json``, and the reveal must name the same runs and the same root
  commitment;
* every VALID record must be OS-isolated per universe with six passing outside verifications, carry the committed
  development identity, and have a campaign id of the committed tier.

Removing an arm, a seed or a record therefore blocks or refuses; it never strengthens a result.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Mapping
from typing import Any

from . import analysis_v4 as a4
from .analysis import AnalysisRefused
from .isolated_host import ISOLATION_LABEL, verified
from .pilot_v4 import Task, campaign_id, roles


def _load(out_dir: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    commitment = json.loads((out_dir / "commitment.json").read_text())
    summary = json.loads((out_dir / "summary.json").read_text())
    runs = (out_dir / "runs.jsonl").read_bytes()
    if hashlib.sha256(runs).hexdigest() != summary.get("runs_sha256"):
        raise AnalysisRefused("runs.jsonl does not match the digest recorded in summary.json")
    for key in ("root_commitment_sha256", "development_identity_v4", "tier", "tasks"):
        if summary.get(key, commitment.get(key)) != commitment.get(key):
            raise AnalysisRefused(f"summary.json and commitment.json disagree on {key}")
    return commitment, summary, runs


def provenance_problems(rec: Mapping[str, Any], commitment: Mapping[str, Any]) -> list[str]:
    if rec.get("status") != "VALID":
        return []
    out = []
    if rec.get("isolation") != ISOLATION_LABEL:
        out.append(f"isolation {rec.get('isolation')!r}")
    checks = list(rec.get("isolation_checks", ()))
    if len(checks) != 6 or not all(verified(c) for c in checks):
        out.append("not six passing outside verifications")
    if rec.get("development_identity_v4") != commitment["development_identity_v4"]:
        out.append("another development identity")
    if not str(rec.get("campaign_id", "")).startswith(f"gl-v04-{commitment['tier']}-"):
        out.append("a campaign id of another tier")
    return out


def decide(out_dir: str | pathlib.Path, reveal_path: str | pathlib.Path, candidate: str, *,
           multiplicity: str = "holm_family") -> dict[str, Any]:
    out_dir = pathlib.Path(out_dir)
    commitment, _summary, runs = _load(out_dir)
    reveal = json.loads(pathlib.Path(reveal_path).read_text())
    if reveal.get("runs_sha256") != hashlib.sha256(runs).hexdigest():
        raise AnalysisRefused("the reveal was computed on other runs")
    if reveal.get("root_commitment_sha256") != commitment["root_commitment_sha256"]:
        raise AnalysisRefused("the reveal's root does not match the run's commitment")
    tasks = [Task(**t) for t in commitment["tasks"]]
    frozen = roles()
    planned = {t.arm for t in tasks}
    expected = {a for a, r in frozen.items()} | {candidate}
    if planned != expected:
        raise AnalysisRefused(f"the committed task list does not run exactly the frozen roster plus the candidate: "
                              f"missing {sorted(expected - planned)}, extra {sorted(planned - expected)}")
    grid = {(t.presentation, campaign_id(commitment["tier"], t), t.seed) for t in tasks}
    records = [json.loads(line) for line in runs.decode().splitlines() if line.strip()]
    bad = {r.get("campaign_id"): p for r in records if (p := provenance_problems(r, commitment))}
    if bad:
        raise AnalysisRefused(f"{len(bad)} VALID record(s) fail provenance, e.g. {next(iter(bad.items()))}")
    result = a4.decision(records, candidate, frozen, reveal["represented"], grid, multiplicity=multiplicity)
    result["commitment"] = {k: commitment[k] for k in ("root_commitment_sha256", "development_identity_v4", "tier")}
    return result


__all__ = ["decide", "provenance_problems"]
