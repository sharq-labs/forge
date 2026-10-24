"""Leakage firewall v3 for battery_rediscovery_v3 (evaluator side; the candidate never imports this module).

The numeric and text engines are scanner v1's (``benchmarks.battery_rediscovery_v1.leakage``), imported unchanged:
complete numeric tokens compared by value (sign-blind, SI-prefix aware, a long transcription matched at its own
precision) and text tokens as case-sensitive substrings.  The POLICY is v2's architecture with a fresh v3 identity:

* CANDIDATE MATERIAL = everything the sandboxed run may read: the CandidateBundle (pack), the GEN1 code (the v2
  candidate package, the frozen v1 candidate modules, the repsem ablation modules it imports, the engcore Mind packages)
  and the two v3 harness files the sandbox loads.  The pack and benchmark code are scanned numerically; benchmark code and
  the pack textually; the engcore Mind packages and the repsem ablation modules textually for identity tokens only.
* PACK MEASUREMENT ARRAYS are protected by PROVENANCE: the bundle must rebuild byte-identically from the pinned raw inputs
  (``build_pack.build_all`` and the v2 bridge bytes), and the manifest must bind every file.
* CANDIDATE OUTPUTS are not numerically scanned (they are a deterministic function of the scanned inputs; replay checks
  that), as in v2.
* RUNTIME AUDIT: every path the sandboxed process opened or listed must lie under the declared roots or be a declared
  file; no evaluator-side, vault, truth or historical module may be loaded; the EvaluatorVault, the TruthBundle, the v2
  pack directory and every v0/v1/v2 results directory are FORBIDDEN even if they lie under a root; during a RUN every
  output path is write-only.

There is no amendment mechanism: a post-seal defect in this module invalidates v3 and requires a v4.
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
from benchmarks.battery_rediscovery_v2 import leakage as v2lk

SCANNER_ID = "forge.battery_rediscovery_v3.leakage_firewall"
SCANNER_VERSION = "3.0.0"
NUMERIC_ENGINE = f"{v1lk.SCANNER_ID}@{v1lk.SCANNER_VERSION}"

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACK = HERE / "CandidateBundle"
VAULT = HERE / "EvaluatorVault"
TRUTH = HERE / "TruthBundle"
GEN1_CANDIDATE = ROOT / "benchmarks" / "battery_rediscovery_v2" / "candidate"
GEN1_CANDIDATE_FILES = tuple(GEN1_CANDIDATE / f for f in ("__init__.py", "arms.py", "common.py", "families.py", "run.py",
                                                         "views.py"))
V1_CANDIDATE_FILES = v2lk.V1_CANDIDATE_FILES
REPSEM_BENCH_FILES = v2lk.REPSEM_BENCH_FILES
MIND_DIRS = v2lk.MIND_DIRS
HARNESS_FILES = (HERE / "__init__.py", HERE / "sandbox_run.py")

STATIC_IDENTITY = sorted(set(v2lk.STATIC_IDENTITY) | {
    "B0029", "B0030", "B0031", "B0032", "B0051", "BatteryAgingARC", "49_50_51_52", "PCoE", "NASA",
    "Kirkaldy", "Expt 4", "Expt 5", "Drive Cycle Aging", "Standard Cycle Aging", "10637534", "M50T", "LG M50",
    "LGM50", "LG_M50", "chen2020", "Chen2020", "4032561", "Maccor", "BioLogic", "Biologic", "Zenodo", "zenodo",
    "forge-data", "v3_rpt", "battery_1rc_crosscell", "kirkaldy_fade", "model_measurement_validation",
    "battery_rediscovery_v2/results", "EvaluatorVault", "TruthBundle", "IDENTITY_MAP", "CENSUS.json",
    "TRUTH.json", "EVALUATION.json", "reference_b"})
VERDICT = sorted(set(v2lk.VERDICT) | {"REAL_DATA_IMPROVEMENT_CONFIRMED", "PARTIAL_REAL_DATA_IMPROVEMENT",
                                      "NO_REAL_DATA_IMPROVEMENT", "REPRESENTATION_STILL_LIMITING",
                                      "SEMANTIC_ROLES_STILL_LIMITING", "GEN1_REAL_DATA_ADVANTAGE_CONFIRMED",
                                      "GEN1_REAL_DATA_ADVANTAGE_PARTIAL", "NO_GEN1_REAL_DATA_ADVANTAGE",
                                      "BENCHMARK_UNDERPOWERED", "TRUTH_INSUFFICIENT", "REFERENCE_DISAGREEMENT"})
#: engcore platform modules name the ``model_measurement_validation`` benchmark directory in their text (claims-layer
#: evidence registries).  A path name in platform code is not data; any read of that directory is still refused by the
#: runtime roots.  Exempt for PLATFORM text only, never for candidate material.
PLATFORM_EXEMPT = set(v2lk.PLATFORM_EXEMPT) | {"model_measurement_validation"}
MEASUREMENT_KEYS = v2lk.MEASUREMENT_KEYS


def identity_tokens() -> list[str]:
    toks = set(STATIC_IDENTITY)
    ident = json.loads((VAULT / "IDENTITY_MAP.json").read_bytes())
    for entry in ident.values():
        d = entry.get("design", {})
        for k in ("cell",):
            if k in d:
                toks.add(str(d[k]))
        for t in entry.get("trajectories", {}).values():
            if "source_file" in t:
                toks.add(pathlib.PurePosixPath(str(t["source_file"])).name)
    for entry in json.loads((VAULT / "PACK_PROVENANCE.json").read_bytes()).values():
        toks |= {d[:12] for d in entry.get("raw_sha256", {}).values()}
    for m in json.loads((VAULT / "EXTRACT_MANIFEST.json").read_bytes())["members"].values():
        toks.add(m["sha256"][:12])
    # single cell letters ("A", "F", ...) are design metadata, not identities: never tokens
    return sorted(t for t in toks if len(t) >= 4)


def text_hits(text: str, *, platform: bool = False) -> list[str]:
    idt = [t for t in identity_tokens() if not (platform and t in PLATFORM_EXEMPT)]
    return sorted({t for t in idt if t in text} | ({t for t in VERDICT if t in text} if not platform else set()))


def pack_files(pack_dir: pathlib.Path = PACK) -> list[pathlib.Path]:
    return sorted(p for p in pack_dir.iterdir() if p.is_file())


def candidate_code_files() -> list[pathlib.Path]:
    return sorted(list(GEN1_CANDIDATE_FILES) + list(V1_CANDIDATE_FILES) + list(HARNESS_FILES))


def benchmark_files(pack_dir: pathlib.Path = PACK) -> list[pathlib.Path]:
    return sorted(candidate_code_files() + list(REPSEM_BENCH_FILES) + pack_files(pack_dir))


def platform_files() -> list[pathlib.Path]:
    return sorted([p for d in MIND_DIRS for p in d.glob("*.py")] + list(REPSEM_BENCH_FILES))


def _name(p: pathlib.Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT)).replace(os.sep, "/")
    except ValueError:
        return str(p)


def numeric_findings(files: Iterable[pathlib.Path], values: Sequence[Protected]) -> list[dict[str, Any]]:
    out = []
    for p in files:
        hits = numeric_hits(v2lk.scannable_text(p), values)
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


_EXPECTED: dict[str, bytes] | None = None


def provenance_findings(pack_dir: pathlib.Path = PACK) -> list[dict[str, Any]]:
    """Every bundle file equals, byte for byte, the rebuild from the pinned inputs; the manifest binds every file."""
    from . import build_pack  # noqa: PLC0415  (evaluator side)

    global _EXPECTED
    out = []
    if _EXPECTED is None:  # the rebuild is deterministic; one per process
        built, _refused = build_pack.build_all()
        _EXPECTED = {pid: build_pack.spec_bytes(spec) for pid, (spec, _i, _p, _e) in built.items()}
        _EXPECTED.update(build_pack.bridge())
    expected = _EXPECTED
    for pid, raw in expected.items():
        path = pack_dir / f"{pid}.json"
        if not path.exists() or path.read_bytes() != raw:
            out.append({"file": path.name, "finding": "differs from the rebuild from the pinned inputs"})
    manifest = json.loads((pack_dir / "MANIFEST.json").read_bytes())
    if set(manifest["problems"]) != set(expected):
        out.append({"file": "MANIFEST.json", "finding": "binds a different problem set than the rebuild"})
    for pid, entry in manifest["problems"].items():
        f = pack_dir / entry["file"]
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != entry["sha256"]:
            out.append({"file": entry["file"], "finding": "differs from MANIFEST.json"})
    extra = sorted(p.name for p in pack_dir.iterdir() if p.name not in {"MANIFEST.json", *(e["file"] for e in
                                                                            manifest["problems"].values())})
    if extra:
        out.append({"file": extra, "finding": "files in the bundle that the manifest does not bind"})
    return out


PACK_KEYS = set(v2lk.PACK_KEYS) | {
    "partner_cell_pulses", "intermediate_rates", "partner_cell_intermediate_rates",
    "cross_unit_heldout/partner_cell_pulses", "within_unit_heldout/intermediate_rates",
    "cross_unit_heldout/partner_cell_intermediate_rates", *(f"P{k:02d}" for k in range(1, 33))}


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


V3 = "benchmarks.battery_rediscovery_v3"
FORBIDDEN_MODULE_PREFIXES = tuple(v2lk.FORBIDDEN_MODULE_PREFIXES) + (
    f"{V3}.evaluator", f"{V3}.leakage", f"{V3}.mutation", f"{V3}.freeze", f"{V3}.seal", f"{V3}.launch",
    f"{V3}.build_pack", f"{V3}.census", f"{V3}.extract", f"{V3}.gen1_reference", f"{V3}.tests",
    "benchmarks.battery_rediscovery_v2.sandbox_run", "benchmarks.battery_rediscovery_v2.evaluator")
ALLOWED_FILES = tuple(str(p.relative_to(ROOT)).replace(os.sep, "/") for p in (
    ROOT / "benchmarks" / "__init__.py", ROOT / "benchmarks" / "battery_rediscovery_v1" / "__init__.py",
    ROOT / "benchmarks" / "battery_rediscovery_v2" / "__init__.py", *GEN1_CANDIDATE_FILES, *HARNESS_FILES,
    *V1_CANDIDATE_FILES, *REPSEM_BENCH_FILES))
FORBIDDEN_ROOTS = (VAULT, TRUTH, GEN1_CANDIDATE / "pack",
                   ROOT / "benchmarks" / "battery_rediscovery_v0" / "results",
                   ROOT / "benchmarks" / "battery_rediscovery_v1" / "results",
                   ROOT / "benchmarks" / "battery_rediscovery_v2" / "results",
                   ROOT / "benchmarks" / "battery_rediscovery_v2" / "evaluator",
                   ROOT / "benchmarks" / "battery_rediscovery_v3" / "evaluator")
_under, _cached = v2lk._under, v2lk._cached


def runtime_findings(log: dict[str, Any], out_dirs: Sequence[pathlib.Path], *, readable: Sequence[pathlib.Path] = (),
                     pack_dir: pathlib.Path = PACK) -> dict[str, Any]:
    """``out_dirs`` may only be written; ``readable`` (the sealed outputs, for a replay) may only be read."""
    roots = [pack_dir, ROOT / "src" / "engcore", pathlib.Path(sys.prefix).resolve(),
             pathlib.Path(sys.base_prefix).resolve(), *out_dirs, *readable]
    allowed_files = {os.path.normcase(str(ROOT / f)) for f in ALLOWED_FILES}
    listable = {os.path.normcase(str(p)) for p in (ROOT, ROOT / "src", ROOT / "benchmarks", HERE, GEN1_CANDIDATE,
                                                   ROOT / "benchmarks" / "battery_rediscovery_v1",
                                                   ROOT / "benchmarks" / "battery_rediscovery_v1" / "candidate",
                                                   ROOT / "benchmarks" / "battery_rediscovery_v2",
                                                   ROOT / "benchmarks" / "mind_repsem_v1")}
    bad, forbidden, engcore, read_outputs = [], [], [], []
    for path, mode in log["opened"]:
        norm = os.path.normcase(os.path.abspath(path))
        if _under(path, FORBIDDEN_ROOTS):
            forbidden.append([path, mode])
            continue
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
    return {"paths_outside_roots": bad, "forbidden_paths": forbidden, "outputs_read_during_run": read_outputs,
            "forbidden_modules": sorted(m for m in log["modules"] if m.startswith(FORBIDDEN_MODULE_PREFIXES)),
            "platform_identity_tokens": platform_identity, "engcore_files_opened": len(set(engcore)),
            "paths_opened": len(log["opened"]), "exit": log.get("exit")}


def runtime_failed(r: dict[str, Any]) -> bool:
    return bool(r["paths_outside_roots"] or r["forbidden_paths"] or r["forbidden_modules"]
                or r["platform_identity_tokens"] or r["outputs_read_during_run"] or r["exit"] != 0)


def audit(values: Sequence[Protected], *, access_logs: Sequence[tuple[pathlib.Path, Sequence[pathlib.Path],
          Sequence[pathlib.Path]]] = (), phase: str, pack_dir: pathlib.Path = PACK,
          provenance: bool = True) -> dict[str, Any]:
    """``access_logs``: (log, write-only output dirs, read-only dirs) per sandboxed process."""
    bench = benchmark_files(pack_dir)
    numeric = numeric_findings(bench, values)
    text = (text_findings(candidate_code_files() + pack_files(pack_dir))
            + text_findings(platform_files(), platform=True))
    schema = schema_findings(pack_dir)
    prov = provenance_findings(pack_dir) if provenance else []
    runtime = {}
    for log, outs, reads in access_logs:
        runtime[_name(log)] = runtime_findings(json.loads(log.read_bytes()), outs, readable=reads, pack_dir=pack_dir)
    failed = bool(numeric or text or schema or prov or any(runtime_failed(r) for r in runtime.values()))
    return {"schema": "forge.battery_rediscovery_v3.leakage_audit/1", "scanner": f"{SCANNER_ID}@{SCANNER_VERSION}",
            "numeric_engine": NUMERIC_ENGINE, "phase": phase, "status": "LEAKAGE_INVALIDATED" if failed else "PASS",
            "numeric": numeric, "text": text, "pack_schema": schema, "provenance": prov,
            "provenance_checked": provenance, "runtime": runtime, "benchmark_files_scanned": len(bench),
            "platform_files_scanned": len(platform_files()),
            "protected_values": [{"name": v.name, "value": str(v.value), "unit": v.unit} for v in values]}


__all__ = ["FORBIDDEN_ROOTS", "MEASUREMENT_KEYS", "NUMERIC_ENGINE", "SCANNER_ID", "SCANNER_VERSION", "VERDICT", "audit",
           "benchmark_files", "candidate_code_files", "identity_tokens", "numeric_findings", "pack_files",
           "platform_files", "provenance_findings", "runtime_failed", "runtime_findings", "schema_findings",
           "text_findings", "text_hits"]
