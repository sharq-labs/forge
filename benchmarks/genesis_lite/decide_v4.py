"""The v0.4 decision from a sealed run directory (review findings 3, 4 and 10 of 2026-10-30; re-review H1, H2, M1,
L1 and L3).

``analysis_v4.decision`` is the pure rule; it takes roles, grid and representation verdicts as arguments. This entry
point takes NONE of them from the caller:

* roles come from the frozen roster in code (:func:`pilot_v4.roles`), bound by ``development_identity_v4``;
* the grid comes from the task list in ``commitment.json``, written before the first campaign; every planned arm must
  appear and nothing else may;
* ``runs.jsonl`` must match the digest in ``summary.json``; the run must be complete (nothing cancelled at the
  deadline, every planned task exactly once and VALID), and every record must belong to its committed task;
* the representation verdicts that drive the D10 cap are RECOMPUTED here from the revealed root
  (:func:`reveal_v4.represented`), after the root is checked against the commitment; a supplied reveal file can only
  be compared for equality, never trusted;
* the code deciding must be the code that ran: this tree's ``development_identity_v4`` must equal the committed one
  with the v0.2 pin unchanged, and a formal decision also needs the frozen v0.4 preregistration to match this tree. A
  development run is analysed DEVELOPMENT_ONLY and never claims lift;
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
from .harness_v4 import development_identity_v4
from .isolated_host import ISOLATION_LABEL, verified
from .pilot_v4 import Task, campaign_id, formal_identity_check, formal_runtime_check, read_root, roles
from .reveal_v4 import represented

_BOUND = ("root_commitment_sha256", "development_identity_v4", "tier", "tasks", "planned_campaigns", "tree_dirty",
          "v0_2_pin_changed", "proposer_env", "exposed", "hidden", "proposer_runtime_identity_sha256", "environment_manifest_sha256")
#: D9: the superiority test is Holm over the pre-declared family; the caller cannot choose another (review M H-a)
MULTIPLICITY = "holm_family"


def _load(out_dir: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any], bytes, dict[str, Any]]:
    commitment = json.loads((out_dir / "commitment.json").read_text())
    summary = json.loads((out_dir / "summary.json").read_text())
    runs = (out_dir / "runs.jsonl").read_bytes()
    if hashlib.sha256(runs).hexdigest() != summary.get("runs_sha256"):
        raise AnalysisRefused("runs.jsonl does not match the digest recorded in summary.json")
    for key in _BOUND:
        if key not in summary or key not in commitment:
            raise AnalysisRefused(f"summary.json or commitment.json lacks {key}")
        if summary[key] != commitment[key]:
            raise AnalysisRefused(f"summary.json and commitment.json disagree on {key}")
    try:
        raw_manifest = (out_dir / "environment.json").read_bytes()
        manifest = json.loads(raw_manifest)
        runtime = manifest["proposer_runtime_identity"]
        digest = hashlib.sha256(json.dumps(runtime["content"], sort_keys=True).encode()).hexdigest()
        if digest != runtime["sha256"] or digest != commitment["proposer_runtime_identity_sha256"]:
            raise ValueError("runtime content/digest mismatch")
        if hashlib.sha256(raw_manifest).hexdigest() != commitment["environment_manifest_sha256"]:
            raise ValueError("environment manifest digest mismatch")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AnalysisRefused(f"saved runtime/environment manifest refused: {exc}") from exc
    return commitment, summary, runs, manifest


def provenance_problems(rec: Mapping[str, Any], commitment: Mapping[str, Any]) -> list[str]:
    if rec.get("status") != "VALID":
        return []
    out = []
    if rec.get("isolation") != ISOLATION_LABEL:
        out.append(f"isolation {rec.get('isolation')!r}")
    checks = list(rec.get("isolation_checks", ()))
    if len(checks) != 6 or not all(verified(c) for c in checks):
        out.append("not six passing outside verifications")
    elif any(set(c["hidden"]) != set(commitment["hidden"]) for c in checks):
        out.append("an outside verification checked other hides than the committed ones")
    if rec.get("development_identity_v4") != commitment["development_identity_v4"]:
        out.append("another development identity")
    if rec.get("proposer_runtime_identity_sha256") != commitment["proposer_runtime_identity_sha256"]:
        out.append("another proposer runtime identity")
    if not str(rec.get("campaign_id", "")).startswith(f"gl-v04-{commitment['tier']}-"):
        out.append("a campaign id of another tier")
    return out


def _completeness(records: list[dict[str, Any]], tasks: list[Task], summary: Mapping[str, Any], tier: str) -> None:
    """Re-review M1 and L3: the candidate's run rules (a run that missed its cap, or any non-VALID world set, supports
    no decision) and every record bound to exactly one committed task."""
    if summary.get("not_run_at_deadline") != 0:
        raise AnalysisRefused(f"{summary.get('not_run_at_deadline')!r} planned campaign(s) did not run before the "
                              "deadline: an incomplete run supports no decision")
    if summary.get("completed") != len(tasks) or summary.get("planned_campaigns") != len(tasks):
        raise AnalysisRefused(f"the run completed {summary.get('completed')!r} of {len(tasks)} planned campaigns")
    if len(records) != len(tasks):
        raise AnalysisRefused(f"{len(records)} record(s) for {len(tasks)} planned campaigns")
    planned = {(t.arm, campaign_id(tier, t)): t for t in tasks}
    seen: set[tuple[str, str]] = set()
    for r in records:
        try:
            task = Task(**r.get("task", {}))
        except TypeError as exc:
            raise AnalysisRefused(f"a record carries a malformed task: {exc}") from exc
        key = (str(r.get("arm")), campaign_id(tier, task))
        if key not in planned or planned[key] != task or key in seen:
            raise AnalysisRefused(f"record {key} is not one committed task")
        if r.get("arm") != task.arm or r.get("campaign_id") != key[1] or r.get("presentation") != task.presentation \
                or r.get("seed") != task.seed:
            raise AnalysisRefused(f"record {key} names another campaign, presentation or seed than its task")
        if r.get("status") != "VALID":
            raise AnalysisRefused(f"record {key} is {r.get('status')!r}: any non-VALID world set blocks the decision")
        if r.get("completed_within_deadline") is not True:
            raise AnalysisRefused(f"record {key} lacks completion within the operator deadline")
        seen.add(key)


def decide(out_dir: str | pathlib.Path, root_file: str | pathlib.Path, candidate: str, *,
           reveal_path: str | pathlib.Path | None = None) -> dict[str, Any]:
    out_dir = pathlib.Path(out_dir)
    commitment, summary, runs, manifest = _load(out_dir)
    tier = commitment["tier"]
    identity, changed = development_identity_v4()
    if identity != commitment["development_identity_v4"] or changed:
        raise AnalysisRefused("the deciding code is not the code that ran (development identity or v0.2 pin differs)")
    if tier == "formal":
        refusal = ("the run started from a dirty tree" if commitment["tree_dirty"] else "") or \
            ("the run's v0.2 pin had changed" if commitment["v0_2_pin_changed"] else "") or \
            formal_identity_check(identity) or formal_runtime_check(manifest)
        if refusal:
            raise AnalysisRefused(f"formal decision refused: {refusal}")
    elif tier != "development":
        raise AnalysisRefused(f"unknown tier {tier!r}")
    root = read_root(root_file)
    if hashlib.sha256(root).hexdigest() != commitment["root_commitment_sha256"]:
        raise AnalysisRefused("the root does not match the run's commitment")
    tasks = [Task(**t) for t in commitment["tasks"]]
    frozen = roles()
    planned = {t.arm for t in tasks}
    expected = set(frozen) | {candidate}
    if planned != expected:
        raise AnalysisRefused(f"the committed task list does not run exactly the frozen roster plus the candidate: "
                              f"missing {sorted(expected - planned)}, extra {sorted(planned - expected)}")
    records = [json.loads(line) for line in runs.decode().splitlines() if line.strip()]
    _completeness(records, tasks, summary, tier)
    bad = {r.get("campaign_id"): p for r in records if (p := provenance_problems(r, commitment))}
    if bad:
        raise AnalysisRefused(f"{len(bad)} VALID record(s) fail provenance, e.g. {next(iter(bad.items()))}")
    try:
        verdicts = represented(records, root)["represented"]
    except ValueError as exc:
        raise AnalysisRefused(f"the reveal cannot be recomputed from this root and these records: {exc}") from exc
    if reveal_path is not None:
        supplied = json.loads(pathlib.Path(reveal_path).read_text())
        if supplied.get("runs_sha256") != hashlib.sha256(runs).hexdigest() or supplied.get("represented") != verdicts:
            raise AnalysisRefused("the supplied reveal differs from the one recomputed from the root")
    grid = {(t.presentation, campaign_id(tier, t), t.seed) for t in tasks}
    result = a4.decision(records, candidate, frozen, verdicts, grid, multiplicity=MULTIPLICITY)
    if tier == "development":
        result["lift_claimed"] = False
    result["tier_status"] = "FORMAL" if tier == "formal" else "DEVELOPMENT_ONLY"
    result["commitment"] = {k: commitment[k] for k in ("root_commitment_sha256", "development_identity_v4", "tier")}
    return result


__all__ = ["decide", "provenance_problems"]
