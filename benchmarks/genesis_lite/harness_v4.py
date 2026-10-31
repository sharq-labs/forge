"""Genesis-lite v0.4 DEVELOPMENT campaign path: the v0.3 campaign flow with every universe proposed by its own
OS-isolated process (:mod:`.isolated_host`; owner decisions D3, D11). Nothing in the v0.3 flow is changed: the
operator keeps the escrow, presentation, query cap, adjudication and independent evaluator; only WHERE the arm runs
differs. The record carries the launcher's outside verification of every proposer process; a run whose six
verifications are not all complete and passing is INVALID_BENCHMARK, never a result.

``development_identity_v4`` binds the v0.3 development identity and the v0.4 files. There is no v0.4
preregistration yet; DEVELOPMENT_ONLY.
"""

from __future__ import annotations

import hashlib
import pathlib
import time
from contextlib import nullcontext
from collections.abc import Mapping, Sequence
from typing import Any

from . import harness as h2
from . import harness_v3 as h3
from .isolated_host import ISOLATION_LABEL, per_universe_arm, verified

HERE = pathlib.Path(__file__).resolve().parent
V4_FILES = ("analysis_v4.py", "arms_v4.py", "decide_v4.py", "deadline_v4.py", "expressibility_v3.py", "harness_v4.py", "isolated_host.py",
            "pilot_v4.py", "proposer_host.py", "proposer_profile_v4.py", "telemetry_v4.py", "runtime_assets_v4.py", "reveal_v4.py")
#: substrate the v0.4 files rely on outside the v0.3 closure (outside verification constants and /proc walk)
SUBSTRATE_V4_FILES = ("src/engcore/blindfold/isolation.py",)
KINDS = h2.KINDS


def development_identity_v4() -> tuple[str, list[str]]:
    v3_identity, changed = h3.development_identity()
    files = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in V4_FILES}
    files.update({name: hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest() for name in SUBSTRATE_V4_FILES})
    return h2._digest({"v0_3_development_identity": v3_identity, "v0_4_files": files}), changed


def run_one_v4(arm_name: str, spec: str, *, master_seed: bytes, campaign_id: str, presentation: str, seed: int = 0,
               hidden: Sequence[str], env: Mapping[str, str] | None = None, budget_fraction: float = 1.0,
               timeout: float = 600.0, exposed: Sequence[str] | None = None) -> dict[str, Any]:
    """One campaign of ``arm_name`` (resolved inside the isolated process from ``spec``, ``module:function``)."""
    checks: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    started = time.perf_counter()
    from .runtime_assets_v4 import runtime_identity
    runtime = runtime_identity(env or {})
    arm = per_universe_arm(spec, hidden, checks, env=env, timeout=timeout, exposed=exposed, timings=timings)
    from .telemetry_v4 import operator_phases
    phases = operator_phases({"independent_evaluator": h3.score_v3.evaluate_campaign,
                              "adjudication": h3.adjudicate_v3,
                              "v3_identity": h3.development_identity}) if (env or {}).get("FORGE_PERF_DIAGNOSTICS") == "1" else nullcontext({})
    with phases as parent_phases:
        rec = h3.run_one_v3(arm_name, arm, master_seed=master_seed, campaign_id=campaign_id, presentation=presentation,
                            seed=seed, isolation="in_process", budget_fraction=budget_fraction)
    out = rec.to_dict()
    identity, changed = development_identity_v4()
    out.update({"isolation": ISOLATION_LABEL, "isolation_checks": checks, "development_identity_v4": identity,
                "arm_spec": spec, "operator_timings": timings, "proposer_runtime_identity_sha256": runtime["sha256"],
                "operator_phase_seconds": parent_phases,
                "campaign_total_seconds": time.perf_counter() - started,
                "host_start_seconds": sum(t["launch_to_hello_seconds"] for t in timings)})
    problems = []
    if changed:
        problems.append(f"the shared v0.2 code differs from its preregistration: {changed[:5]}")
    if out["status"] == "VALID":
        uids = sorted(u["universe_id"] for u in out.get("universes", ()))
        seen = sorted({c["universe_id"] for c in checks})
        if len(checks) != len(KINDS) or len(seen) != len(KINDS):
            problems.append(f"{len(checks)} isolated proposer process(es) for {len(KINDS)} universes")
        if not all(verified(c) for c in checks):
            problems.append("a proposer process failed outside verification")
        if len(uids) != len(KINDS):
            problems.append("the record does not carry six universes")
    if problems:
        out["status"] = "INVALID_BENCHMARK"
        out["reasons"] = [*out.get("reasons", []), *problems]
    return out


__all__ = ["SUBSTRATE_V4_FILES", "V4_FILES", "development_identity_v4", "run_one_v4"]
