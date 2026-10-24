"""Leakage audit of everything the candidate can see (evaluator side; the candidate never imports this module).

Three checks, any finding of which makes the run LEAKAGE_INVALIDATED:

* static: every candidate-visible file (the candidate package and pack, and the Minimal Mind source) is scanned for
  IDENTITY tokens (source datasets, cells, files, digests, historical record and directory names) and historical
  VERDICT tokens.  After the seal, the scan is repeated with the historical parameter and error values
  (``historical_value_tokens``), which are read only then.
* schema: every key of every pack JSON object must be in the declared pack schema (no extra field can carry a label).
* runtime: the access log of the sandboxed run may name no opened path outside the declared roots and no loaded module
  from the evaluator side or a historical battery package.  Every engcore file the run opened is also scanned for
  IDENTITY tokens; a VERDICT token there is reported as platform vocabulary (it is not bound to these problems).
  The bare publisher name "NASA" is left out of the platform scan only (the platform cites NASA-STD-7009), and the
  import machinery's listing of the repository root and src/ (sys.path entries) is not a read.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Any, Iterable

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATE = HERE / "candidate"
MIND_SRC = ROOT / "src" / "engcore" / "mind" / "minimal"

STATIC_IDENTITY = [
    "NASA", "PCoE", "FY08Q4", "BatteryAgingARC", "B0005", "B0006", "B0007", "B0018", "HG2", "McMaster", "Kollmeyer",
    "Mendeley", "cp3473x7xv", "Digatron", "Kirkaldy", "forge-data", "549_", "551_", "battery_1rc_closure",
    "battery_1rc_identifiability", "battery_1rc_crosscell", "thevenin_route", "nasa_battery_aging", "IDENTITY_MAP",
    "PACK_PROVENANCE", "CALIBRATION.json", "VALIDATION.json", "OUTCOME.json", "UNCERTAINTY_REPORT", "SENSITIVITY.json",
    "PREREGISTRATION", "0eae4585baf3", "fa818ab4db5d", "d022afa086ef", "82302a7db4fc", "70ffb357511d", "d9b9dd9b9b84",
    "52eff1a8d273", "408f9dc4b174", "35bb500c2934", "d8acfb269758",
]
VERDICT = ["NOT_IDENTIFIABLE", "WEAKLY_IDENTIFIABLE", "IDENTIFIABILITY_SUPPORTED", "MODEL_REJECTED",
           "MODEL_VALIDATION_SUPPORTED", "PARTIALLY_CLOSED", "INSUFFICIENT_MEASUREMENT_EVIDENCE", "EVIDENCE_BACKED"]

PACK_KEYS = {
    "schema", "problem_id", "description", "declared_model", "family", "equations", "requested_parameters", "bounds",
    "R0_ohm", "R1_ohm", "C1_F", "ocv", "status", "knots_soc", "bounds_V", "knots_z_V", "interpolation", "conventions",
    "current_sign", "rest_band_A", "hold", "initial_polarization_V", "initial_soc", "capacity_basis", "scored_samples",
    "measurement_uncertainty", "voltage_V", "current_A", "temperature_C", "time_s", "half_width", "standard_uncertainty",
    "distribution", "basis", "acceptance", "rmse_mV_max", "p95_abs_mV_max", "applicability", "widen_by", "soc", "min",
    "max", "set_rule", "questions", "MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION",
    "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY", "vocabulary", "sets", "calibration", "trajectories", "subsets", "id",
    "cell", "kind", "t_s", "z0", "capacity_Ah", "problems", "file", "sha256", "P1", "P2",
    "within_cell_heldout", "cross_cell_heldout", "later_cycles", "other_cell", "pulses", "cc",
    "within_cell_heldout/later_cycles", "cross_cell_heldout/other_cell", "within_cell_heldout/pulses",
    "within_cell_heldout/cc",
}
PLATFORM_EXEMPT = {"NASA"}
FORBIDDEN_MODULE_PREFIXES = ("benchmarks.battery_rediscovery_v0.evaluator", "benchmarks.battery_rediscovery_v0.leakage",
                             "benchmarks.battery_rediscovery_v0.build_pack", "benchmarks.battery_rediscovery_v0.seal",
                             "benchmarks.battery_rediscovery_v0.freeze", "benchmarks.battery_1rc", "tools.nasa_battery")


def candidate_files() -> list[pathlib.Path]:
    files = [p for p in CANDIDATE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    files += sorted(MIND_SRC.glob("*.py"))
    return sorted(files)


def identity_tokens() -> list[str]:
    """Static identity tokens plus every source identity the pack builder recorded (evaluator files, never history)."""
    tokens = set(STATIC_IDENTITY)
    ev = HERE / "evaluator"
    ident = json.loads((ev / "IDENTITY_MAP.json").read_bytes())
    for entries in ident.values():
        for e in entries.values():
            tokens.add(pathlib.PurePosixPath(e["source_file"]).name)
            for k in ("cell", "test"):
                if k in e:
                    tokens.add(str(e[k]))
    prov = json.loads((ev / "PACK_PROVENANCE.json").read_bytes())
    for entry in prov.values():
        tokens |= {d[:12] for d in entry["source_data_sha256"].values()}
    # generic split-file names are pack vocabulary too ("calibration.json" never appears in the pack; keep it)
    return sorted(tokens)


def _scan_text(text: str, tokens: Iterable[str]) -> list[str]:
    return sorted({t for t in tokens if t in text})


def static_findings(files: Iterable[pathlib.Path], *, extra: Iterable[str] = ()) -> list[dict[str, Any]]:
    idt, extra = identity_tokens(), list(extra)
    out = []
    for p in files:
        text = p.read_bytes().decode("utf-8", errors="replace")
        hits = _scan_text(text, idt) + _scan_text(text, VERDICT)
        for pat in extra:
            if re.search(pat, text):
                hits.append(f"value:{pat}")
        if hits:
            try:
                name = str(p.resolve().relative_to(ROOT)).replace(os.sep, "/")
            except ValueError:
                name = str(p)
            out.append({"file": name, "tokens": sorted(set(hits))})
    return out


def schema_findings(pack_dir: pathlib.Path = CANDIDATE / "pack") -> list[dict[str, Any]]:
    out = []

    def walk(o: Any, path: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k not in PACK_KEYS:
                    out.append({"file": path, "unexpected_key": k})
                walk(v, path)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (dict, list)):
                    walk(v, path)

    for p in sorted(pack_dir.glob("*.json")):
        walk(json.loads(p.read_bytes()), p.name)
    return out


def _under(path: str, roots: Iterable[pathlib.Path]) -> bool:
    p = os.path.normcase(os.path.abspath(path))
    return any(p == os.path.normcase(str(r)) or p.startswith(os.path.normcase(str(r)) + os.sep) for r in roots)


def allowed_roots(out_dir: pathlib.Path) -> list[pathlib.Path]:
    roots = {CANDIDATE, ROOT / "src" / "engcore", pathlib.Path(sys.prefix).resolve(), pathlib.Path(sys.base_prefix).resolve(),
             out_dir.resolve()}
    return sorted(roots)


ALLOWED_FILES = ("benchmarks/__init__.py", "benchmarks/battery_rediscovery_v0/__init__.py",
                 "benchmarks/battery_rediscovery_v0/sandbox_run.py")


def runtime_findings(log: dict[str, Any], out_dir: pathlib.Path) -> dict[str, Any]:
    roots = allowed_roots(out_dir)
    allowed_files = {os.path.normcase(str(ROOT / f)) for f in ALLOWED_FILES}
    bad_paths, engcore_opened = [], []
    for path, mode in log["opened"]:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in allowed_files or norm in {os.path.normcase(str(ROOT / "benchmarks")),
                                             os.path.normcase(str(HERE))}:
            continue
        if mode == "list" and norm in {os.path.normcase(str(ROOT)), os.path.normcase(str(ROOT / "src"))}:
            continue
        if not _under(path, roots):
            bad_paths.append([path, mode])
        elif _under(path, [ROOT / "src" / "engcore"]) and path.endswith(".py"):
            engcore_opened.append(path)
    bad_modules = sorted(m for m in log["modules"] if m.startswith(FORBIDDEN_MODULE_PREFIXES))
    idt = [t for t in identity_tokens() if t not in PLATFORM_EXEMPT]
    platform_identity, platform_vocab = [], []
    for path in sorted(set(engcore_opened)):
        text = pathlib.Path(path).read_bytes().decode("utf-8", errors="replace")
        hits = _scan_text(text, idt)
        if hits:
            platform_identity.append({"file": path, "tokens": hits})
        vh = _scan_text(text, VERDICT)
        if vh:
            platform_vocab.append({"file": path, "tokens": vh})
    return {"paths_outside_roots": bad_paths, "forbidden_modules": bad_modules,
            "platform_identity_tokens": platform_identity, "platform_verdict_vocabulary": platform_vocab,
            "engcore_files_opened": len(set(engcore_opened)), "paths_opened": len(log["opened"])}


def historical_value_tokens(root: pathlib.Path = ROOT) -> list[str]:
    """Regexes for the historical 1RC estimates and RMSEs (read ONLY after the seal), at 3 and 4 significant digits.

    AMENDMENT-01 (post-seal, disclosed): a match may not be followed by a decimal point either.  The frozen pattern
    excluded only a following digit, so "760" (a historical C1) matched the measured timestamp 760.006 s.
    """
    pats = set()
    for rel in ("benchmarks/battery_1rc_closure/results/CALIBRATION.json",
                "benchmarks/battery_1rc_identifiability/results/CALIBRATION.json"):
        rec = json.loads((root / rel).read_bytes())
        one = rec["models"]["1rc"]
        vals = [*one["parameters"].values(), one["tau_s"], one["rmse_mV"], rec["models"]["rint"]["rmse_mV"]]
        for v in vals:
            if not isinstance(v, (int, float)) or v == 0:
                continue
            for sig in (3, 4):
                s = f"{float(v):.{sig}g}"
                if "e" in s:
                    continue
                pats.add(r"(?<![\d.])" + re.escape(s) + r"(?![\d.])")
    return sorted(pats)


def audit(access_log: pathlib.Path | None, out_dir: pathlib.Path, *, post_seal: bool = False) -> dict[str, Any]:
    extra = historical_value_tokens() if post_seal else []
    static = static_findings(candidate_files(), extra=extra)
    schema = schema_findings()
    runtime = None
    if access_log is not None:
        runtime = runtime_findings(json.loads(access_log.read_bytes()), out_dir)
    failed = bool(static or schema or (runtime and (runtime["paths_outside_roots"] or runtime["forbidden_modules"]
                                                       or runtime["platform_identity_tokens"])))
    return {"schema": "forge.battery_rediscovery.leakage_audit/1", "phase": "post_seal" if post_seal else "pre_seal",
            "status": "LEAKAGE_INVALIDATED" if failed else "PASS", "static": static, "pack_schema": schema,
            "runtime": runtime, "files_scanned": len(candidate_files()), "identity_tokens": len(identity_tokens()),
            "value_patterns": len(extra)}


__all__ = ["VERDICT", "audit", "candidate_files", "historical_value_tokens", "identity_tokens", "runtime_findings",
           "schema_findings", "static_findings"]
