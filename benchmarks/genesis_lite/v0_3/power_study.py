"""Genesis-lite v0.3: the owner-authorised power and null-calibration study (ODC-O1b; D2, 2026-10-20).

NON-FORMAL. Synthetic records only: no hidden world, pilot record or formal root is read, and nothing here is a
measurement of any arm. Its output is evidence for the owner about the v0.3 statistical rule, never a lift result.

Part A (null calibration of the D2 statistic): one-sided paired sign-flip p with the Monte-Carlo stream keyed by a fresh
random "revealed root" per replicate (``analysis.sign_flip_stream``), at the formal sizes (600 world sets per presentation,
2,400 pooled). Under an exchangeable null the rejection rate must not exceed alpha beyond Monte-Carlo error, and Holm over
the five-member family must hold the family-wise rate. An asymmetric mean-zero null (outside the preregistered scope) is
reported for information.

Part B (power of the whole v0.3 decision): synthetic per-universe credits (+1 / -1, Bernoulli) for ``careful`` (the
strongest baseline), ``monomial_enumeration`` (the representation arm) and a candidate, on the formal grid, scored by
``analysis.lift_decision`` itself. The candidate's outcome on a universe is coupled to careful's through a shared
uniform with probability ``rho`` (rho = 1: the candidate succeeds wherever careful does when its rate is at least
careful's). The statistical claim is ``lift_claimed`` without the identity / binding problems a synthetic run must have
(DRAFT identity, no committed root, no harness binding): baseline named, Holm pooled, pooled lower bound > 0, every
presentation and every kind non-inferior.

Speed: v0.2's pure-Python ``bootstrap_mean_ci`` costs ~14 s per decision at the formal size. The study replaces it with a
vectorised bootstrap with the same estimator (B = 2,000 resamples of world sets, the floor 2.5 % order statistic, a fixed
seed). Since D3b-1 the decision's own bootstrap is ``analysis.capped_bootstrap_ci`` (numpy, used unchanged), so the
substitute reaches only v0.2's ``representation_limited``; ``bootstrap_crosscheck`` re-runs some cells with the original.
Its threshold-flip count uses -0.1 for the kind bound, a study constant from before D3b-2 (the rule's margin is 0.15).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import pathlib
import time
from contextlib import contextmanager
from typing import Any, Iterator

import numpy as np

from .. import analysis as v02
from . import analysis as v03a

STUDY_SCHEMA = "forge.genesis_lite.v0_3/power_study/1"
ALPHAS = (0.01, 0.05, 0.10)
CANDIDATE = "candidate"


def fast_bootstrap_mean_ci(values: Any, resamples: int | None = None) -> tuple[float, float, float]:
    """v0.2's ``bootstrap_mean_ci`` estimator, vectorised (same B, same order statistic, fixed seed)."""
    resamples = v02.BOOTSTRAP if resamples is None else resamples
    if len(values) == 0:
        return float("nan"), float("nan"), 1.0
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(0)
    means = np.sort(arr[rng.integers(0, len(arr), size=(resamples, len(arr)))].mean(axis=1))
    return float(math.fsum(arr) / len(arr)), float(means[max(int(0.025 * resamples) - 1, 0)]), \
        float((means <= 0).mean())


@contextmanager
def _study_scoring(root: bytes, fast: bool) -> Iterator[None]:
    """Score with the keyed stream of ``root`` (as if it were the committed one) and, if ``fast``, the vectorised
    bootstrap. Restores everything on exit; never touches the committed preregistration."""
    saved = (v03a._formal_root_commitment, v03a.bootstrap_mean_ci, v02.bootstrap_mean_ci)
    v03a._formal_root_commitment = lambda: hashlib.sha256(root).hexdigest()
    if fast:
        v03a.bootstrap_mean_ci = v02.bootstrap_mean_ci = fast_bootstrap_mean_ci
    try:
        yield
    finally:
        v03a._formal_root_commitment, v03a.bootstrap_mean_ci, v02.bootstrap_mean_ci = saved


def _prereg_sha() -> str:
    from .preregistration import PREREG_PATH  # noqa: PLC0415

    return PREREG_PATH.with_suffix(".sha256").read_bytes().split()[0].decode()


def _outcome(kind: str, value: float) -> str:
    from engcore.blindfold.roles import DEFAULT_CREDIT  # noqa: PLC0415

    return next(o for o, c in sorted(DEFAULT_CREDIT[kind].items()) if c == value)


def _records(arm: str, success: np.ndarray, grid: list, sha: str, in_family: np.ndarray) -> list[dict]:
    out = []
    for i, (p, c, s) in enumerate(grid):
        universes = []
        for j, k in enumerate(v03a.KINDS):
            value = 1.0 if success[i, j] else -1.0
            universes.append({"kind": k, "credit": value, "outcome": _outcome(k, value), "independent_agrees": True,
                              "truth_in_searched_family": bool(in_family[i, j]),
                              "universe_id": f"{arm}-{p}-{s}-{c}-{k}"})
        out.append({"arm": arm, "status": "VALID", "presentation": p, "campaign_id": c, "seed": s,
                    "isolation": "proposer_process", "reasons": [], "prereg_sha256": sha, "universes": universes})
    return out


def scenario_records(cell: dict[str, Any], rng: np.random.Generator, grid: list | None = None) -> list[dict]:
    """careful, monomial_enumeration and the candidate on ``grid`` (default: the formal grid)."""
    grid = sorted(v03a.FORMAL_GRID) if grid is None else sorted(grid)
    shape = (len(grid), len(v03a.KINDS))
    rates = lambda d: np.array([d.get(k, d["default"]) for k in v03a.KINDS])   # noqa: E731
    base_rate, cand_rate, rep_rate = rates(cell["careful"]), rates(cell["candidate"]), rates(cell["representation"])
    u_base, u_own = rng.random(shape), rng.random(shape)
    u_cand = np.where(rng.random(shape) < cell["rho"], u_base, u_own)
    in_family = rng.random(shape) >= cell.get("off_family", 0.0)
    sha = _prereg_sha()
    return (_records("careful", u_base < base_rate, grid, sha, in_family)
            + _records(v03a.REPRESENTATION_ARM, rng.random(shape) < rep_rate, grid, sha, in_family)
            + _records(CANDIDATE, u_cand < cand_rate, grid, sha, in_family))


def statistical_claim(out: dict[str, Any]) -> dict[str, Any]:
    """``lift_claimed`` without the identity / binding problems; and which condition failed."""
    parts = {"baseline": out["strongest_baseline"] is not None, "holm_pooled": bool(out["holm_significant"]["pooled"]),
             "pooled_lower95": out["primary"]["pooled"]["lower95"] > 0,
             "presentations": all(out["presentation_noninferiority"].values()),
             "kinds": all(v["ok"] for v in out["kind_noninferiority"].values())}
    return {"claim": all(parts.values()), **parts}


def run_cell(cell: dict[str, Any], reps: int, seed: int, fast: bool = True) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    tally: dict[str, int] = {}
    pooled_mean, problems = [], set()
    kind_stats: dict[str, dict[str, list[float]]] = {k: {"mean": [], "margin": [], "fail": []} for k in v03a.KINDS}
    for _ in range(reps):
        rows = scenario_records(cell, rng)
        root = rng.bytes(32)
        with _study_scoring(root, fast):
            out = v03a.lift_decision(rows, CANDIDATE, revealed_root=root, verification=[])
        for name, ok in statistical_claim(out).items():
            tally[name] = tally.get(name, 0) + int(ok)
        pooled_mean.append(out["primary"]["pooled"]["mean_difference"])
        problems.update(p.split(":")[0][:90] for p in out["coverage_problems"])
        for k, v in out["kind_noninferiority"].items():
            kind_stats[k]["mean"].append(v["mean_difference"])
            kind_stats[k]["margin"].append(v["mean_difference"] - v["lower95"])
            kind_stats[k]["fail"].append(0.0 if v["ok"] else 1.0)
    claims = tally["claim"]
    return {"cell": cell, "reps": reps, "seed": seed, "claim_rate": claims / reps,
            "claim_rate_95ci": clopper_pearson(claims, reps), "condition_pass_rates": {k: v / reps for k, v in tally.items()},
            "mean_pooled_difference": float(np.mean(pooled_mean)), "coverage_problems_seen": sorted(problems),
            "kind_noninferiority_stats": {k: {"sd_mean_difference": float(np.std(s["mean"])),
                                              "mean_of_mean_minus_lower95": float(np.mean(s["margin"])),
                                              "fail_rate": float(np.mean(s["fail"]))} for k, s in kind_stats.items()}}


def bootstrap_crosscheck(cell: dict[str, Any], reps: int, seed: int) -> dict[str, Any]:
    """The SAME records and root scored twice, with the vectorised and with v0.2's original bootstrap: every lower
    bound (pooled, presentations, kinds) and the claim are compared replicate by replicate."""
    rng = np.random.default_rng(seed)
    worst, claims_agree, flips, rows_out = 0.0, 0, 0, []
    for _ in range(reps):
        rows = scenario_records(cell, rng)
        root = rng.bytes(32)
        outs = []
        for fast in (True, False):
            with _study_scoring(root, fast):
                outs.append(v03a.lift_decision(rows, CANDIDATE, revealed_root=root, verification=[]))
        bounds = [{**{f"primary/{p}": o["primary"][p]["lower95"] for p in o["primary"]},
                   **{f"kind/{k}": v["lower95"] for k, v in o["kind_noninferiority"].items()}} for o in outs]
        gap = max(abs(bounds[0][k] - bounds[1][k]) for k in bounds[0])
        worst = max(worst, gap)
        same = statistical_claim(outs[0]) == statistical_claim(outs[1])
        claims_agree += same
        flips += any((bounds[0][k] > (0 if k.startswith("primary/pooled") else -0.1)) !=
                     (bounds[1][k] > (0 if k.startswith("primary/pooled") else -0.1)) for k in bounds[0]
                     if k.startswith(("primary/pooled", "kind/")))
        rows_out.append({"max_abs_lower95_gap": gap, "claims_agree": same})
    return {"cell": cell, "reps": reps, "seed": seed, "max_abs_lower95_gap": worst,
            "claim_agreement": f"{claims_agree}/{reps}", "replicates_with_a_threshold_flip": flips,
            "replicates": rows_out}


def clopper_pearson(k: int, n: int, level: float = 0.95) -> list[float]:
    from scipy.stats import beta  # noqa: PLC0415

    a = (1 - level) / 2
    return [0.0 if k == 0 else float(beta.ppf(a, k, n - k + 1)), 1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k))]


# ---- part A ----------------------------------------------------------------------------------------------------------
def _null_diffs(rng: np.random.Generator, n: int, symmetric: bool) -> list[float]:
    if symmetric:          # exchangeable: two iid per-world-set credit sums over six kinds, rate 0.5
        a = (rng.random((n, 6)) < 0.5).sum(axis=1) * 2 - 6
        b = (rng.random((n, 6)) < 0.5).sum(axis=1) * 2 - 6
        return [float(x) for x in a - b]
    # mean zero, skewed: -1 with probability 2/3, +2 with probability 1/3 (outside the preregistered null scope)
    return [2.0 if u < 1 / 3 else -1.0 for u in rng.random(n)]


def null_calibration(reps: int, seed: int, symmetric: bool = True) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    per = len(v03a.FORMAL_GRID) // 4
    rejections = {f"{part}@{a}": 0 for part in ("pooled", "presentation") for a in ALPHAS}
    holm_any = 0
    sha = _prereg_sha()
    for _ in range(reps):
        stream = v03a.sign_flip_stream(rng.bytes(32), sha)
        diffs = _null_diffs(rng, 4 * per, symmetric)
        ps = {"pooled": v03a.sign_flip_p(diffs, stream=stream)["p"]}
        for i, part in enumerate(v03a.PRIMARY_FAMILY[1:]):
            ps[part] = v03a.sign_flip_p(diffs[i * per:(i + 1) * per], stream=stream)["p"]
        for a in ALPHAS:
            rejections[f"pooled@{a}"] += ps["pooled"] <= a
            rejections[f"presentation@{a}"] += ps["anonymous"] <= a
        holm_any += any(v03a.holm(ps).values())
    return {"symmetric_null": symmetric, "reps": reps, "seed": seed, "world_sets": {"pooled": 4 * per, "presentation": per},
            "rejection_rates": {k: v / reps for k, v in rejections.items()},
            "rejection_95ci": {k: clopper_pearson(v, reps) for k, v in rejections.items()},
            "holm_familywise_rate": holm_any / reps, "holm_familywise_95ci": clopper_pearson(holm_any, reps)}


# ---- the study grid --------------------------------------------------------------------------------------------------
def cells() -> list[dict[str, Any]]:
    """Two baseline regimes x candidate lift on discoverable x coupling; plus an off-family and a representation cell."""
    out = []
    for regime, control in (("controls_solved", 0.8), ("controls_unsolved", 0.4)):
        careful = {"default": control, "discoverable": 0.2}
        for delta in (0.0, 0.05, 0.10, 0.20):
            for rho in (0.0, 0.5, 0.9, 1.0):
                out.append({"name": f"{regime}/delta={delta}/rho={rho}", "careful": careful,
                            "candidate": dict(careful, discoverable=0.2 + delta), "representation": {"default": 0.1},
                            "rho": rho})
    careful = {"default": 0.4, "discoverable": 0.2}
    out.append({"name": "controls_unsolved/delta=0.2/rho=1.0/off_family=0.3", "careful": careful,
                "candidate": dict(careful, discoverable=0.4), "representation": {"default": 0.1}, "rho": 1.0,
                "off_family": 0.3})
    out.append({"name": "controls_unsolved/delta=0.2/rho=1.0/representation_solves", "careful": careful,
                "candidate": dict(careful, discoverable=0.4), "representation": {"default": 0.1, "discoverable": 0.8},
                "rho": 1.0})
    return out


def _cell_job(args: tuple) -> dict[str, Any]:
    return run_cell(*args)


def _cross_job(args: tuple) -> dict[str, Any]:
    return bootstrap_crosscheck(*args)


def provenance() -> dict[str, Any]:
    """HEAD, tree cleanliness, code digests and the environment of this run."""
    import platform  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    here = pathlib.Path(__file__).resolve().parent

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=here, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "UNKNOWN"

    code = {name: hashlib.sha256((here / name).read_bytes()).hexdigest()
            for name in ("power_study.py", "analysis.py", "preregistration.py")}
    code["../analysis.py"] = hashlib.sha256((here.parent / "analysis.py").read_bytes()).hexdigest()
    return {"head": git("rev-parse", "HEAD"), "tree_clean": git("status", "--porcelain") == "",
            "code_sha256": code, "python": sys.version.split()[0], "numpy": np.__version__,
            "platform": platform.platform()}


def _null_job(args: tuple) -> dict[str, Any]:
    return null_calibration(*args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 power and null-calibration study (non-formal)")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--reps", type=int, default=100)
    parser.add_argument("--null-reps", type=int, default=2000)
    parser.add_argument("--crosscheck-reps", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261020)
    args = parser.parse_args(argv)
    started = time.time()
    source = provenance()
    grid = cells()
    with concurrent.futures.ProcessPoolExecutor(args.workers) as pool:
        nulls = list(pool.map(_null_job, [(args.null_reps, args.seed + 1, True), (args.null_reps // 2, args.seed + 2, False)]))
        power = list(pool.map(_cell_job, [(c, args.reps, args.seed + 100 + i) for i, c in enumerate(grid)]))
        picks = [c for c in grid if c["name"] in ("controls_solved/delta=0.1/rho=0.9", "controls_unsolved/delta=0.05/rho=0.5")]
        cross = list(pool.map(_cross_job, [(c, args.crosscheck_reps, args.seed + 900 + i) for i, c in enumerate(picks)]))
    doc = {"schema": STUDY_SCHEMA, "status": "NON_FORMAL_SYNTHETIC_STUDY", "prereg_sha256": _prereg_sha(),
           "provenance": source,
           "credit_model": "per-universe credits +1 / -1 only (the maximum-variance case); DEFAULT_CREDIT also has 0, "
                           "+0.5 and -0.5 outcomes, so the power figures and the cap penalty hold for this model only",
           "authorisation": "owner D2 (ODC-O1b), 2026-10-20; runs after D3 (decided 2026-10-20)",
           "args": {k: str(v) for k, v in vars(args).items()}, "null_calibration": nulls, "power": power,
           "bootstrap_crosscheck": cross,
           "wall_seconds": round(time.time() - started, 1)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(doc, indent=1, sort_keys=True) + "\n").encode())
    print(args.out, doc["wall_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
