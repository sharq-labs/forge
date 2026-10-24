"""Read-only census of the battery, Mind and historical-truth assets (evaluator-only; names every identity).

    python -m benchmarks.battery_rediscovery_v0.evaluator.census     # writes evaluator/CENSUS.json

Repository assets are identified by (commit, git blob id); external data by sha256 and size.  Nothing is opened for its
scientific content: only identities are recorded.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess

from ..candidate.common import write_json

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
BASE = "12862b0b8821e2564d8c94853f31d44ced55eebf"
MIND = "e2b8037c881847a497c32f7ca56f82b95b493727"
DATA = pathlib.Path("D:/forge-data")

NO, YES = "NO", "YES"
BUILDER = "NO (builder input: pseudonymised into the pack)"


def _blob(commit: str, path: str) -> str | None:
    r = subprocess.run(["git", "rev-parse", f"{commit}:{path}"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _ext(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"present": False}
    if path.is_dir():
        return {"present": True, "directory": True}
    raw = path.read_bytes()
    return {"present": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


REPO = [
    # (path, commit, group, role, candidate_visible, evaluator_only)
    ("benchmarks/battery_1rc_closure/data/calibration.json", BASE, "A", "NASA split: calibration (2 cells, ordinals 2-20)", BUILDER, NO),
    ("benchmarks/battery_1rc_closure/data/within_cell_holdout.json", BASE, "A", "NASA split: within-cell held-out (ordinals 21-30)", BUILDER, NO),
    ("benchmarks/battery_1rc_closure/data/cross_cell_validation.json", BASE, "A", "NASA split: cross-cell held-out (third cell)", BUILDER, NO),
    ("benchmarks/battery_1rc_closure/PREREGISTRATION_v2.json", BASE, "A", "NASA preregistration (declared sections transcribed; outcome-free)", NO, YES),
    ("benchmarks/battery_1rc_identifiability/data/calibration.json", BASE, "A", "LG HG2 split: calibration pulses (3 A / 18 A)", BUILDER, NO),
    ("benchmarks/battery_1rc_identifiability/data/heldout_pulses.json", BASE, "A", "LG HG2 split: held-out pulses (6 A / 12 A)", BUILDER, NO),
    ("benchmarks/battery_1rc_identifiability/data/heldout_cc.json", BASE, "A", "LG HG2 split: held-out 1C constant current", BUILDER, NO),
    ("benchmarks/battery_1rc_identifiability/data/ocv.json", BASE, "A", "LG HG2 measured OCV knots", BUILDER, NO),
    ("benchmarks/battery_1rc_identifiability/PREREGISTRATION.json", BASE, "A", "LG HG2 preregistration (declared sections transcribed)", NO, YES),
    ("benchmarks/battery_1rc_identifiability/MEASUREMENT_UNCERTAINTY_DECISION.json", BASE, "A", "LG HG2 Type B uncertainty decision (components transcribed; its 'limits' field carries an outcome and is NOT copied)", NO, YES),
    ("benchmarks/battery_1rc_crosscell/README.md", BASE, "A", "LG M50T (Kirkaldy 2024) cross-cell work; held-out cells no longer blind: not used", NO, YES),
    ("src/engcore/domains/battery/thevenin_route.py", BASE, "A", "FORGE Thevenin 1RC route (model, solver, replay)", "platform (not imported by any arm)", NO),
    ("src/engcore/domains/battery/thevenin.py", BASE, "A", "1RC parameter types", "platform (not imported)", NO),
    ("src/engcore/domains/battery/solver.py", BASE, "A", "production Rint kernel", "platform (not imported)", NO),
    ("src/engcore/domains/battery/calibration.py", BASE, "A", "battery calibration helpers", "platform (not imported)", NO),
    ("tools/nasa_battery_aging.py", BASE, "A", "NASA .mat importer (canonical records)", NO, YES),
    ("benchmarks/battery_1rc_closure/fit.py", BASE, "A", "historical calibration + identifiability tool", NO, YES),
    ("benchmarks/battery_1rc_closure/evaluate.py", BASE, "A", "historical validation tool", NO, YES),
    ("benchmarks/battery_1rc_closure/uq.py", BASE, "A", "historical parameter-UQ tool", NO, YES),
    ("benchmarks/battery_1rc_closure/sensitivity.py", BASE, "A", "historical hold/v_p0 sensitivity tool", NO, YES),
    ("benchmarks/battery_1rc_identifiability/fit.py", BASE, "A", "historical LG HG2 calibration + identifiability tool", NO, YES),
    ("benchmarks/battery_1rc_identifiability/evaluate.py", BASE, "A", "historical LG HG2 validation tool", NO, YES),
    ("benchmarks/battery_1rc_identifiability/outcome.py", BASE, "A", "historical LG HG2 outcome mapping", NO, YES),
    ("src/engcore/mind/minimal/structures.py", MIND, "B", "Mind: hypothesis representation (log-linear structures, prior)", YES, NO),
    ("src/engcore/mind/minimal/outcome_model.py", MIND, "B", "Mind: prediction path (hyper-g posterior predictive)", YES, NO),
    ("src/engcore/mind/minimal/competition.py", MIND, "B", "Mind: belief update, sealing, evidence admission", YES, NO),
    ("src/engcore/mind/minimal/experiments.py", MIND, "B", "Mind: experiment/data selection (expected discrimination)", YES, NO),
    ("src/engcore/mind/minimal/falsifier.py", MIND, "B", "Mind: falsifier role (sealed decisive tests)", YES, NO),
    ("src/engcore/mind/minimal/stopping.py", MIND, "B", "Mind: stopping / refusal rule", YES, NO),
    ("src/engcore/mind/minimal/runner.py", MIND, "B", "Mind: closed loop, six conclusion kinds, replay", YES, NO),
    ("src/engcore/mind/minimal/trace.py", MIND, "B", "Mind: content-addressed step records, replay comparison", YES, NO),
    ("src/engcore/mind/minimal/problem.py", MIND, "B", "Mind: experimental problem statement", YES, NO),
    ("src/engcore/mind/minimal/__init__.py", MIND, "B", "Mind: package surface", YES, NO),
    ("tests/mind/test_minimal_mind.py", MIND, "B", "Mind: its own functional/adversarial tests (copied; 27 pass at base)", NO, NO),
    ("benchmarks/genesis_lite_mind/MIND_PILOT_PLAN.json", MIND, "B", "BR-MIND-01 pilot plan (historical Mind evidence: NOT copied)", NO, YES),
    ("benchmarks/battery_1rc_closure/results/CALIBRATION.json", BASE, "C", "historical NASA fitted parameters + identifiability decision", NO, YES),
    ("benchmarks/battery_1rc_closure/results/VALIDATION.json", BASE, "C", "historical NASA within/cross-cell acceptance, residuals", NO, YES),
    ("benchmarks/battery_1rc_closure/results/UNCERTAINTY_REPORT.json", BASE, "C", "historical NASA UQ / model-form / applicability", NO, YES),
    ("benchmarks/battery_1rc_closure/results/SENSITIVITY.json", BASE, "C", "historical NASA sensitivity results", NO, YES),
    ("benchmarks/battery_1rc_closure/README.md", BASE, "C", "historical NASA conclusions (prose)", NO, YES),
    ("benchmarks/battery_1rc_identifiability/results/CALIBRATION.json", BASE, "C", "historical LG HG2 fitted parameters + identifiability", NO, YES),
    ("benchmarks/battery_1rc_identifiability/results/VALIDATION.json", BASE, "C", "historical LG HG2 held-out results", NO, YES),
    ("benchmarks/battery_1rc_identifiability/results/OUTCOME.json", BASE, "C", "historical LG HG2 outcome (preregistered mapping)", NO, YES),
    ("benchmarks/battery_1rc_identifiability/README.md", BASE, "C", "historical LG HG2 conclusions (prose)", NO, YES),
    ("benchmarks/battery_1rc_crosscell/results/OUTCOME.json", BASE, "C", "historical LG M50T cross-cell outcome (not used)", NO, YES),
    ("docs/work/PROGRESS.md", BASE, "C", "session log naming every prior battery verdict", NO, YES),
]

EXTERNAL = [
    (DATA / "nasa_pcoe_battery/5_Battery_Data_Set.zip", "A", "NASA PCoE archive (owner-approved download)"),
    (DATA / "nasa_pcoe_battery/extracted/1. BatteryAgingARC-FY08Q4/B0005.mat", "A", "NASA cell B0005 raw"),
    (DATA / "nasa_pcoe_battery/extracted/1. BatteryAgingARC-FY08Q4/B0006.mat", "A", "NASA cell B0006 raw"),
    (DATA / "nasa_pcoe_battery/extracted/1. BatteryAgingARC-FY08Q4/B0007.mat", "A", "NASA cell B0007 raw"),
    (DATA / "lg_hg2/raw/549_HPPC.csv", "A", "LG HG2 HPPC raw"),
    (DATA / "lg_hg2/raw/551_Cap_1C.csv", "A", "LG HG2 1C capacity raw"),
    (DATA / "kirkaldy2024/bol25.sha256", "A", "LG M50T (Kirkaldy 2024) BOL 25 C digest list (250 MB set; not used)"),
    (DATA / "chen2020_lgm50", "A", "LG M50 (Chen 2020) CSVs (not used)"),
]

BRANCHES = [
    ("feat/battery-real-data-identifiability", "A", "Battery Practical Pass 1 (A123; WEAKLY_IDENTIFIABLE); historical, not used"),
    ("feat/br-mind-01-minimal-mind", "B", "BR-MIND-01 branch (head 20069cc2; Mind code frozen at e2b8037c); not merged"),
    ("codex/mind-development-evidence-2026-10-20", "B", "Mind preservation branch (blocked Genesis/Mind work); NOT merged into this branch"),
    ("feat/genesis-lite-v03-clean-n1", "-", "sealed Family-3a stage a6200e5c; untouched by this task"),
]


def census() -> dict:
    rows = []
    for path, commit, group, role, visible, evaluator in REPO:
        rows.append({"path": path, "commit": commit, "blob": _blob(commit, path), "group": group, "role": role,
                     "candidate_visible": visible, "evaluator_only": evaluator})
    for path, group, role in EXTERNAL:
        rows.append({"path": str(path).replace("\\", "/"), "commit": None, "external": _ext(path), "group": group,
                     "role": role, "candidate_visible": BUILDER if path.suffix in (".mat", ".csv") else NO,
                     "evaluator_only": NO})
    for ref, group, role in BRANCHES:
        r = subprocess.run(["git", "rev-parse", ref], cwd=ROOT, capture_output=True, text=True)
        rows.append({"path": f"refs/heads/{ref}", "commit": r.stdout.strip() or None, "group": group, "role": role,
                     "candidate_visible": NO, "evaluator_only": NO})
    return {"schema": "forge.battery_rediscovery.census/1", "base_commit": BASE, "mind_source_commit": MIND, "rows": rows}


def main() -> int:
    write_json(HERE / "CENSUS.json", census())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
