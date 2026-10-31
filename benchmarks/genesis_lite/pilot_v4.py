"""Genesis-lite v0.4 campaign driver (gaps P-4, P-5, G16; ACTIVE_PLAN "Blindfold Step 1 gap closure").

In-tree, reviewed and committed, so a run is bound to a commit (the EXC-4 pilots used an out-of-tree driver):

* the ROOT comes from a file the operator writes outside the tree BEFORE the run (32 bytes, no group/other access);
  the driver never generates, logs or copies it. Its SHA-256 commitment is written to ``commitment.json`` before the
  first campaign starts, and the root file's directory and the output directory are hidden from every proposer;
* every campaign runs through :func:`harness_v4.run_one_v4`: one OS-isolated, outside-verified proposer process per
  universe;
* ``environment.json`` is the environment manifest (P-5): interpreter, platform and kernel, every installed
  distribution with its version (and their digest), thread limits, isolation support, exposures and hides, the full
  git HEAD and whether the tree was clean. Its SHA-256 is recorded beside it;
* ``tier="formal"`` additionally requires a clean tree and a frozen v0.4 preregistration whose digest file matches
  and whose recorded development identity equals this tree's; without one it refuses. Freezing it is the owner's.

DEVELOPMENT runs make no claim; formal results are analysed only by :mod:`.analysis_v4` under the frozen plan.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.metadata
import json
import os
import pathlib
import platform
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from .arms import ARMS as ARMS_V2
from .arms_grammar_v3 import GRAMMAR_ARMS
from .arms_v3 import ARMS_V3
from .arms_v4 import ARMS_V4
from .harness_v4 import development_identity_v4, run_one_v4
from .isolated_host import THREAD_ENV, exposures, hidden_paths, support

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")
DOMAIN = "forge.genesis_lite.v0_4"
PREREG = HERE / "preregistration" / "genesis_lite_v0_4.json"
PREREG_DIGEST = HERE / "preregistration" / "genesis_lite_v0_4.sha256"
ROOT_BYTES = 32


def _specs() -> dict[str, tuple[str, str]]:
    """name -> (proposer_host spec, role) for the v0.4 Step 1 roster (D14): every registered baseline arm."""
    out = {name: (name, entry[3]) for name, entry in ARMS_V2.items()}
    for module, registry in (("arms_v3", ARMS_V3), ("arms_grammar_v3", GRAMMAR_ARMS), ("arms_v4", ARMS_V4)):
        for name, entry in registry.items():
            out[name] = (f"benchmarks.genesis_lite.{module}:{entry[0].__name__}", entry[3])
    return out


ROSTER = _specs()


def roles() -> dict[str, str]:
    return {name: role for name, (_, role) in ROSTER.items()}


@dataclass(frozen=True)
class Task:
    arm: str
    campaign: int
    presentation: str
    seed: int


def master_seed(root: bytes, campaign: int, presentation: str, seed: int) -> bytes:
    return hmac.new(root, f"{DOMAIN}\n{campaign}\n{presentation}\n{seed}".encode(), hashlib.sha256).digest()


def campaign_id(tier: str, task: Task) -> str:
    return f"gl-v04-{tier}-{task.seed}-{task.campaign}-{task.presentation}"


def plan(arms: Sequence[str], *, campaigns: int, presentations: Iterable[str], seeds: Iterable[int]) -> list[Task]:
    unknown = sorted(set(arms) - set(ROSTER))
    if unknown or len(set(arms)) != len(arms):
        raise ValueError(f"arms must be distinct registered roster names; unknown: {unknown}")
    presentations, seeds = tuple(presentations), tuple(seeds)
    if not set(presentations) <= set(PRESENTATIONS) or campaigns <= 0 or not seeds:
        raise ValueError("bad grid")
    return [Task(a, i, p, s) for s in seeds for i in range(campaigns) for p in presentations for a in arms]


def read_root(path: str | os.PathLike[str]) -> bytes:
    """The sealed root: a regular file outside the code tree, 32 bytes, no group/other permission bits."""
    p = pathlib.Path(path).resolve()
    if p.is_relative_to(ROOT.resolve()):
        raise ValueError("the root file lies inside the code tree")
    st = p.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077:
        raise ValueError("the root file must be a regular file without group or other permissions (0600)")
    data = p.read_bytes()
    if len(data) != ROOT_BYTES:
        raise ValueError(f"the root file must hold exactly {ROOT_BYTES} bytes")
    return data


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", "safe.directory=*", *args], capture_output=True, text=True, check=True,
                          cwd=ROOT).stdout.strip()


def environment_manifest(hidden: Sequence[str], exposed: Sequence[str]) -> dict[str, Any]:
    dists = sorted({f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
                    if d.metadata["Name"]}, key=str.lower)
    try:
        wsl_conf = pathlib.Path("/etc/wsl.conf").read_text()
    except OSError:
        wsl_conf = None
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "kernel": platform.release(), "cpu_count": os.cpu_count(), "thread_env": THREAD_ENV,
            "distributions": dists, "distributions_sha256": hashlib.sha256("\n".join(dists).encode()).hexdigest(),
            "wsl_conf": wsl_conf, "isolation_support": support(), "exposed": list(exposed), "hidden": list(hidden)}


def formal_identity_check(identity: str) -> str:
    """Refusal text, or "" when a frozen v0.4 preregistration matches this tree."""
    if not PREREG.exists() or not PREREG_DIGEST.exists():
        return "no frozen v0.4 preregistration (freezing it is the owner's decision)"
    digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if PREREG_DIGEST.read_text().split()[0] != digest:
        return "the v0.4 preregistration does not match its digest file"
    if json.loads(PREREG.read_text()).get("development_identity_v4") != identity:
        return "the code differs from the identity the v0.4 preregistration froze"
    return ""


def _work(task: Task, seed_hex: str, tier: str, hidden: tuple[str, ...], exposed: tuple[str, ...],
          env: Mapping[str, str]) -> dict[str, Any]:
    spec, _role = ROSTER[task.arm]
    rec = run_one_v4(task.arm, spec, master_seed=bytes.fromhex(seed_hex), campaign_id=campaign_id(tier, task),
                     presentation=task.presentation, seed=task.seed, hidden=hidden, exposed=exposed, env=env)
    rec["task"] = asdict(task)
    return rec


def run(arms: Sequence[str], *, root_file: str, out: str, tier: str = "development", campaigns: int = 1,
        presentations: Iterable[str] = PRESENTATIONS, seeds: Iterable[int] = (0,), workers: int = 4,
        deadline_seconds: float = 2700.0, env: Mapping[str, str] | None = None,
        expose: Sequence[str] = ()) -> dict[str, Any]:
    """``env`` reaches every proposer process (e.g. a read-only Julia depot for PySR); ``expose`` binds extra
    directories under /opt back read-only. Both are recorded in the commitment."""
    if tier not in ("development", "formal"):
        raise ValueError("tier is development or formal")
    ok, why = support()
    if not ok:
        raise RuntimeError(f"isolated runs need an isolation-capable host: {why}")
    root = read_root(root_file)
    out_dir = pathlib.Path(out).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)                  # a fresh directory: runs are never appended to
    if out_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("the output directory lies inside the code tree")
    head, dirty = _git("rev-parse", "HEAD"), bool(_git("status", "--porcelain"))
    identity, changed = development_identity_v4()
    if tier == "formal":
        refusal = ("the tree is not clean" if dirty else "") or formal_identity_check(identity)
        if refusal:
            raise RuntimeError(f"formal tier refused: {refusal}")
    exposed = exposures(expose)
    env = dict(env or {})
    hidden = hidden_paths([pathlib.Path(root_file).resolve().parent, out_dir], exposed=exposed)
    tasks = plan(arms, campaigns=campaigns, presentations=presentations, seeds=seeds)
    commitment = {"root_commitment_sha256": hashlib.sha256(root).hexdigest(), "tier": tier, "git_head": head,
                  "tree_dirty": dirty, "development_identity_v4": identity, "v0_2_pin_changed": changed,
                  "custody": "SELF_ADMINISTERED", "planned_campaigns": len(tasks), "tasks": [asdict(t) for t in tasks],
                  "proposer_env": env, "exposed": list(exposed), "hidden": list(hidden),
                  "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (out_dir / "commitment.json").write_text(json.dumps(commitment, indent=1, sort_keys=True))
    manifest = environment_manifest(hidden, exposed)
    text = json.dumps(manifest, indent=1, sort_keys=True)
    (out_dir / "environment.json").write_text(text)
    (out_dir / "environment.json.sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "  environment.json\n")
    runs = out_dir / "runs.jsonl"
    runs.write_text("")
    done = 0

    def keep(rec: Mapping[str, Any]) -> None:
        nonlocal done
        done += rec.get("status") not in ("NOT_STARTED", "DEADLINE_TERMINATED")
        with runs.open("a") as fh:
            fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")

    def seed_hex(task: Task) -> str:
        return master_seed(root, task.campaign, task.presentation, task.seed).hex()

    from .deadline_v4 import execute
    execution = execute(_work, [(t, seed_hex(t), tier, hidden, exposed, env) for t in tasks],
                        directory=out_dir / "task_results", workers=workers, deadline_seconds=deadline_seconds, keep=keep)
    summary = {**commitment, **execution, "completed": done, "workers": workers,
               "runs_sha256": hashlib.sha256(runs.read_bytes()).hexdigest()}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tier", default="development", choices=("development", "formal"))
    ap.add_argument("--arms", nargs="+", default=sorted(ROSTER))
    ap.add_argument("--campaigns", type=int, default=1)
    ap.add_argument("--presentations", nargs="+", default=list(PRESENTATIONS))
    ap.add_argument("--seeds", nargs="+", type=int, default=[0])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--deadline-seconds", type=float, default=2700.0)
    ap.add_argument("--env", nargs="*", default=[], help="KEY=VALUE pairs passed to every proposer process")
    ap.add_argument("--expose", nargs="*", default=[], help="extra directories under /opt bound back read-only")
    a = ap.parse_args(argv)
    env = dict(kv.split("=", 1) for kv in a.env)
    summary = run(a.arms, root_file=a.root_file, out=a.out, tier=a.tier, campaigns=a.campaigns,
                  presentations=a.presentations, seeds=a.seeds, workers=a.workers, deadline_seconds=a.deadline_seconds,
                  env=env, expose=a.expose)
    print(json.dumps({k: summary[k] for k in ("completed", "not_run_at_deadline", "elapsed_seconds", "runs_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
