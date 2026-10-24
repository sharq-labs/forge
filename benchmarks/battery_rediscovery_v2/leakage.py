"""Leakage firewall v2 for battery_rediscovery_v2 (evaluator side; the candidate never imports this module).

The numeric and text scanning engines are v1's, imported unchanged from ``benchmarks.battery_rediscovery_v1.leakage``
(scanner v1: complete numeric tokens compared by value, sign-blind, SI-prefix aware, a long transcription matched at its
own precision; text tokens as case-sensitive substrings).  What v2 changes is the POLICY around them:

* CANDIDATE MATERIAL is everything the candidate run can read: the v2 candidate package and pack, the frozen v1 candidate
  modules it imports, the repsem ablation modules it imports, and the engcore Mind packages.  Benchmark code and the pack
  are scanned numerically; the v2 and v1 candidate files also textually; the repsem ablation modules and the engcore
  Mind packages textually for identity tokens only (their vocabulary legitimately names identifiability states, e.g. the
  synthetic fixtures' labels).
* PACK MEASUREMENT ARRAYS are protected by PROVENANCE: the pack must rebuild byte-identically from the pinned raw/split
  inputs (``build_pack.build_all``).  Every other pack field is scanned.
* CANDIDATE OUTPUTS are not numerically scanned.  They are a deterministic function of the scanned inputs and code
  (replay checks that), and on data shared with history a computed statistic can equal a historical number by chance
  (v0 was invalidated by exactly such a coincidence, a 760.006 s timestamp).  A leak can reach an output only through the
  scanned material or through a runtime read, and both are audited.
* RUNTIME AUDIT: every path the sandboxed run opened or listed must lie under the declared roots or be one of the
  declared files; no evaluator-side or historical module may be loaded; and during a RUN every output path must be
  opened for writing only (so no arm can read another arm's answers).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
from typing import Any, Iterable, Sequence

from benchmarks.battery_rediscovery_v1 import leakage as v1lk
from benchmarks.battery_rediscovery_v1.leakage import Protected, numeric_hits, protected, round_sig, tokens  # noqa: F401

SCANNER_ID = "forge.battery_rediscovery_v2.leakage_firewall"
SCANNER_VERSION = "2.0.0"
NUMERIC_ENGINE = f"{v1lk.SCANNER_ID}@{v1lk.SCANNER_VERSION}"

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATE = HERE / "candidate"
PACK = CANDIDATE / "pack"
V1_CANDIDATE_FILES = tuple(ROOT / "benchmarks" / "battery_rediscovery_v1" / "candidate" / f
                           for f in ("__init__.py", "common.py", "model.py", "baselines.py", "mind_arm.py"))
REPSEM_BENCH_FILES = tuple(ROOT / "benchmarks" / "mind_repsem_v1" / f for f in ("__init__.py", "arms.py", "fixtures.py"))
MIND_DIRS = (ROOT / "src" / "engcore" / "mind" / "minimal", ROOT / "src" / "engcore" / "mind" / "repsem")

STATIC_IDENTITY = sorted(set(v1lk.STATIC_IDENTITY) | {
    "B0038", "B0039", "B0040", "BatteryAgingARC_25-44", "25-44", "battery_thermal_flagship",
    "battery_rediscovery_v0/results", "battery_rediscovery_v1/results", "battery_rediscovery_v1/evaluator",
    "EVALUATION.md", "MIND__P1", "MIND__P2", "CAREFUL_BASELINE__P", "ABLATION.json", "nasa_pcoe",
    "lg_hg2", "kirkaldy",
    "41d4a6977e3f", "0ea0a44622b6", "1d7eb3dbf82b"})
VERDICT = sorted(set(v1lk.VERDICT) | {"REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY", "READY_FOR_BATTERY_V2",
                                      "REPRESENTATION_MISSING", "SEMANTIC_ROLE_ERROR", "MULTIPLE_CAUSES"})
PLATFORM_EXEMPT = set(v1lk.PLATFORM_EXEMPT)
MEASUREMENT_KEYS = ("t_s", "current_A", "level_A", "voltage_V", "temperature_C", "ocv_knots", "knots_z_V")


def identity_tokens() -> list[str]:
    toks = set(STATIC_IDENTITY)
    ev = HERE / "evaluator"
    for entries in json.loads((ev / "IDENTITY_MAP.json").read_bytes()).values():
        for e in entries.values():
            for k in ("source_file", "cell"):
                if k in e:
                    toks.add(pathlib.PurePosixPath(str(e[k])).name)
    for entry in json.loads((ev / "PACK_PROVENANCE.json").read_bytes()).values():
        for k in ("raw_sha256", "split_sha256"):
            toks |= {d[:12] for d in entry.get(k, {}).values()}
    return sorted(toks)


def text_hits(text: str, *, platform: bool = False) -> list[str]:
    idt = [t for t in identity_tokens() if not (platform and t in PLATFORM_EXEMPT)]
    return sorted({t for t in idt if t in text} | ({t for t in VERDICT if t in text} if not platform else set()))


def candidate_files() -> list[pathlib.Path]:
    files = [p for p in CANDIDATE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return sorted(files + list(V1_CANDIDATE_FILES))


def benchmark_files() -> list[pathlib.Path]:
    return sorted(candidate_files() + list(REPSEM_BENCH_FILES))


def platform_files() -> list[pathlib.Path]:
    return sorted([p for d in MIND_DIRS for p in d.glob("*.py")] + list(REPSEM_BENCH_FILES))


def _name(p: pathlib.Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT)).replace(os.sep, "/")
    except ValueError:
        return str(p)


def scannable_text(p: pathlib.Path) -> str:
    raw = p.read_bytes().decode("utf-8", errors="replace")
    if p.suffix != ".json":
        return raw

    def strip(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: ("<measurement array: provenance-checked>" if k in MEASUREMENT_KEYS and isinstance(v, list)
                        else strip(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o

    try:
        return json.dumps(strip(json.loads(raw)), sort_keys=True, indent=1, ensure_ascii=False)
    except ValueError:
        return raw


def numeric_findings(files: Iterable[pathlib.Path], values: Sequence[Protected]) -> list[dict[str, Any]]:
    out = []
    for p in files:
        hits = numeric_hits(scannable_text(p), values)
        if hits:
            out.append({"file": _name(p), "hits": hits})
    return out


def text_findings(files: Iterable[pathlib.Path], *, platform: bool = False) -> list[dict[str, Any]]:
    out = []
    for p in files:
        hits = text_hits(p.read_bytes().decode("utf-8", errors="replace"), platform=platform)
        if hits:
            out.append({"file": _name(p), "tokens": hits})
    return out


def provenance_findings(pack_dir: pathlib.Path = PACK) -> list[dict[str, Any]]:
    """Every pack file must equal, byte for byte, what the builder makes from the pinned inputs."""
    from . import build_pack  # noqa: PLC0415  (evaluator side)

    out = []
    for pid, (spec, _, _) in build_pack.build_all().items():
        expected = (json.dumps(spec, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()
        path = pack_dir / f"{pid}.json"
        if not path.exists() or path.read_bytes() != expected:
            out.append({"file": path.name, "finding": "differs from the rebuild from the pinned inputs"})
    manifest = json.loads((pack_dir / "MANIFEST.json").read_bytes())
    for pid, entry in manifest["problems"].items():
        if hashlib.sha256((pack_dir / entry["file"]).read_bytes()).hexdigest() != entry["sha256"]:
            out.append({"file": entry["file"], "finding": "differs from MANIFEST.json"})
    extra = sorted(p.name for p in pack_dir.iterdir() if p.name not in {"MANIFEST.json", *(e["file"] for e in
                                                                            manifest["problems"].values())})
    if extra:
        out.append({"file": extra, "finding": "files in the pack that the manifest does not bind"})
    return out


PACK_KEYS = {
    # specification
    "schema", "problem_id", "description", "clock", "observable", "variables", "declared_family", "requested_parameters",
    "measurement_noise", "adequacy_bar", "acceptance", "applicability", "conventions", "questions", "sets",
    # variables
    "name", "role", "unit", "source", "basis", "driven_by", "derived_from",
    # family
    "family_id", "rival", "equations", "parameter_bounds", "constants", "ocv", "status", "representation", "knots_soc",
    "bounds_V", "interpolation", "knots_z_V", "ocv_knots", "ocv_knots_soc", "R0", "R1", "C1",
    *(f"ocv_k{k}" for k in range(16)),
    # noise, bars, applicability, conventions
    "sigma", "independent", "half_width", "distribution", "rmse_max", "p95_abs_max", "widen", "soc_support",
    "level_A", "soc", "temperature_C", "current_sign", "hold", "rest_band_A", "initial_state", "initial_polarization",
    "capacity_basis", "scored_samples",
    # questions
    "MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY",
    "vocabulary", "set_rule",
    # sets and trajectories
    "calibration", "within_unit_heldout", "cross_unit_heldout", "later_cycles", "other_cell", "pulses_alternate_soc",
    "within_unit_heldout/later_cycles", "cross_unit_heldout/other_cell", "within_unit_heldout/pulses_alternate_soc",
    "id", "unit_id", "kind", "columns", "conditions", "capacity_As", "t_s", "current_A", "voltage_V",
    # manifest
    "problems", "file", "sha256", "Q1", "Q2",
}


def schema_findings(pack_dir: pathlib.Path = PACK) -> list[dict[str, Any]]:
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


V2 = "benchmarks.battery_rediscovery_v2"
FORBIDDEN_MODULE_PREFIXES = (f"{V2}.evaluator", f"{V2}.leakage", f"{V2}.mutation", f"{V2}.freeze", f"{V2}.seal",
                             f"{V2}.launch", f"{V2}.build_pack", f"{V2}.tests",
                             "benchmarks.battery_rediscovery_v1.evaluator", "benchmarks.battery_rediscovery_v1.leakage",
                             "benchmarks.battery_rediscovery_v1.mutation", "benchmarks.battery_rediscovery_v1.freeze",
                             "benchmarks.battery_rediscovery_v1.seal", "benchmarks.battery_rediscovery_v1.launch",
                             "benchmarks.battery_rediscovery_v1.v0_history", "benchmarks.battery_rediscovery_v1.build_pack",
                             "benchmarks.battery_rediscovery_v1.sandbox_run", "benchmarks.battery_rediscovery_v0",
                             "benchmarks.mind_repsem_v1.gap_map", "benchmarks.mind_repsem_v1.run_ablation",
                             "benchmarks.mind_repsem_v1.tests", "benchmarks.battery_1rc", "benchmarks.battery_thermal",
                             "tools.nasa_battery")
ALLOWED_FILES = tuple(str(p.relative_to(ROOT)).replace(os.sep, "/") for p in (
    ROOT / "benchmarks" / "__init__.py", ROOT / "benchmarks" / "battery_rediscovery_v1" / "__init__.py",
    ROOT / "benchmarks" / "battery_rediscovery_v2" / "__init__.py", HERE / "sandbox_run.py",
    *V1_CANDIDATE_FILES, *REPSEM_BENCH_FILES))


def _forms(r: pathlib.Path) -> set[str]:
    """A root as written, absolute, and resolved (Windows 8.3 short names and long names both match)."""
    return {os.path.normcase(os.path.abspath(str(r))), os.path.normcase(str(pathlib.Path(r).resolve()))}


def _under(path: str, roots: Iterable[pathlib.Path]) -> bool:
    p = os.path.normcase(os.path.abspath(path))
    q = os.path.normcase(str(pathlib.Path(path).resolve()))
    return any(x == f or x.startswith(f + os.sep) for r in roots for f in _forms(r) for x in (p, q))


def _cached(norm: str) -> str | None:
    """The source file a ``__pycache__/<stem>.<tag>.pyc`` was compiled from (an allowed source's bytecode is allowed)."""
    p = pathlib.PurePath(norm)
    if p.parent.name != "__pycache__" or p.suffix != ".pyc":
        return None
    return os.path.normcase(str(pathlib.Path(p.parent.parent) / (p.name.split(".")[0] + ".py")))


def runtime_findings(log: dict[str, Any], out_dirs: Sequence[pathlib.Path], *, readable: Sequence[pathlib.Path] = ()
                     ) -> dict[str, Any]:
    """``out_dirs`` may only be written; ``readable`` (the sealed outputs, for a replay) may only be read."""
    roots = [CANDIDATE, ROOT / "src" / "engcore", pathlib.Path(sys.prefix).resolve(),
             pathlib.Path(sys.base_prefix).resolve(), *out_dirs, *readable]
    allowed_files = {os.path.normcase(str(ROOT / f)) for f in ALLOWED_FILES}
    listable = {os.path.normcase(str(p)) for p in (ROOT, ROOT / "src", ROOT / "benchmarks", HERE,
                                                   ROOT / "benchmarks" / "battery_rediscovery_v1",
                                                   ROOT / "benchmarks" / "battery_rediscovery_v1" / "candidate",
                                                   ROOT / "benchmarks" / "mind_repsem_v1")}
    bad, engcore, read_outputs = [], [], []
    for path, mode in log["opened"]:
        norm = os.path.normcase(os.path.abspath(path))
        if norm in allowed_files or (mode == "list" and norm in listable) or _cached(norm) in allowed_files:
            continue
        if not _under(path, roots):
            bad.append([path, mode])
            continue
        if _under(path, out_dirs) and mode != "list" and not any(c in mode for c in "wax"):
            read_outputs.append([path, mode])
        if _under(path, [ROOT / "src" / "engcore"]) and path.endswith(".py"):
            engcore.append(path)
    platform_identity = []
    for path in sorted(set(engcore)):
        hits = text_hits(pathlib.Path(path).read_bytes().decode("utf-8", errors="replace"), platform=True)
        if hits:
            platform_identity.append({"file": path, "tokens": hits})
    return {"paths_outside_roots": bad, "outputs_read_during_run": read_outputs,
            "forbidden_modules": sorted(m for m in log["modules"] if m.startswith(FORBIDDEN_MODULE_PREFIXES)),
            "platform_identity_tokens": platform_identity, "engcore_files_opened": len(set(engcore)),
            "paths_opened": len(log["opened"]), "exit": log.get("exit")}


def audit(values: Sequence[Protected], *, access_logs: Sequence[tuple[pathlib.Path, Sequence[pathlib.Path],
          Sequence[pathlib.Path]]] = (), phase: str) -> dict[str, Any]:
    """``access_logs``: (log, write-only output dirs, read-only dirs) per sandboxed process."""
    bench = benchmark_files()
    numeric = numeric_findings(bench, values)
    text = text_findings(candidate_files()) + text_findings(platform_files(), platform=True)
    schema = schema_findings()
    provenance = provenance_findings()
    runtime = {}
    for log, outs, reads in access_logs:
        runtime[_name(log)] = runtime_findings(json.loads(log.read_bytes()), outs, readable=reads)
    bad_runtime = any(r["paths_outside_roots"] or r["forbidden_modules"] or r["platform_identity_tokens"]
                      or r["outputs_read_during_run"] or r["exit"] != 0 for r in runtime.values())
    failed = bool(numeric or text or schema or provenance or bad_runtime)
    return {"schema": "forge.battery_rediscovery_v2.leakage_audit/1", "scanner": f"{SCANNER_ID}@{SCANNER_VERSION}",
            "numeric_engine": NUMERIC_ENGINE, "phase": phase, "status": "LEAKAGE_INVALIDATED" if failed else "PASS",
            "numeric": numeric, "text": text, "pack_schema": schema, "provenance": provenance, "runtime": runtime,
            "benchmark_files_scanned": len(bench), "platform_files_scanned": len(platform_files()),
            "protected_values": [{"name": v.name, "value": str(v.value), "unit": v.unit} for v in values]}


__all__ = ["MEASUREMENT_KEYS", "NUMERIC_ENGINE", "SCANNER_ID", "SCANNER_VERSION", "VERDICT", "audit", "benchmark_files",
           "candidate_files",
           "identity_tokens", "numeric_findings", "platform_files", "provenance_findings", "runtime_findings",
           "schema_findings", "text_findings", "text_hits"]
