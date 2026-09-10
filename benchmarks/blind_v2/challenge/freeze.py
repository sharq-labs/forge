"""Build the corpus, then seal it.

The freeze manifest digests every artifact the round depends on -- spec,
inventory, bound register, generator source, oracle source, truth source, the
cases, the shadows, the truth and the generation log -- so that "the truth
predates the run" is a checkable claim about bytes and not a statement of
intent. :func:`verify` recomputes every digest independently.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib

from . import audit, build, generator, shadows, truth
from .systems import SYSTEMS

BLIND = pathlib.Path(__file__).resolve().parent.parent
CASES = BLIND / "cases"
TRUTH = BLIND / "truth"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_jsonl(path: pathlib.Path, records: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(payload, encoding="utf-8")
    return sha256_bytes(payload.encode("utf-8"))


def generate() -> dict:
    """Run every system's builder and write the corpus."""
    log = generator.GenerationLog()
    all_cases: list[dict] = []
    all_truth: list[dict] = []
    all_shadows: list[dict] = []
    per_system: dict[str, dict] = {}
    for spec in SYSTEMS:
        cases, truths = build.build_system(spec, log)
        shadow_records = shadows.build_for_system(spec, cases, str(generator.SEED))
        all_cases.extend(cases)
        all_truth.extend(truths)
        all_shadows.extend(shadow_records)
        decided = [t for t in truths if t["outcome"] != "REJECTED_AT_BOUNDARY"]
        per_system[spec.system_id] = {
            "primary_cases": len(cases),
            "shadows": len(shadow_records),
            "scientifically_decided": len(decided),
            "dual_oracle": sum(1 for t in truths if t["oracle"]["dual_oracle"]),
            "families": _count(cases, "family"),
            "outcomes": _count(truths, "outcome"),
            "truth_classes": _count(truths, "truth_class"),
        }
    CASES.mkdir(parents=True, exist_ok=True)
    TRUTH.mkdir(parents=True, exist_ok=True)
    digests = {
        "cases/primary.jsonl": write_jsonl(CASES / "primary.jsonl", all_cases),
        "cases/shadows.jsonl": write_jsonl(CASES / "shadows.jsonl", all_shadows),
        "truth/truth.jsonl": write_jsonl(TRUTH / "truth.jsonl", all_truth),
    }
    rejections = [
        {
            "proposer": r.case_intent,
            "system": r.system,
            "reason": r.reason,
            "detail": r.detail,
        }
        for r in log.rejections
    ]
    generation_log = {
        "schema": "blind_v2_generation_log/1",
        "what_this_is": (
            "Every sample the generator produced and did not keep, with why. A "
            "rejection is a fact about the sampler -- it could not construct a "
            "legal declaration, or the same declaration had already been made "
            "-- and never about what the system under test would have said, "
            "which the generator has no way to ask."
        ),
        "rejection_counts": _count_key(rejections, "reason"),
        "rejections": rejections,
    }
    payload = json.dumps(generation_log, indent=2, sort_keys=True) + "\n"
    (BLIND / "GENERATION_LOG.json").write_text(payload, encoding="utf-8")
    digests["GENERATION_LOG.json"] = sha256_bytes(payload.encode("utf-8"))
    return {
        "cases": all_cases,
        "truth": all_truth,
        "shadows": all_shadows,
        "per_system": per_system,
        "digests": digests,
    }


def _count(records: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for record in records:
        out[record[key]] = out.get(record[key], 0) + 1
    return dict(sorted(out.items()))


def _count_key(records: list[dict], key: str) -> dict:
    return _count(records, key)


FROZEN_SOURCE = (
    "challenge/__init__.py",
    "challenge/units.py",
    "challenge/truth.py",
    "challenge/systems.py",
    "challenge/generator.py",
    "challenge/build.py",
    "challenge/shadows.py",
    "challenge/audit.py",
    "challenge/freeze.py",
    "challenge/oracles/__init__.py",
    "challenge/oracles/numeric.py",
    "challenge/oracles/thermal_lumped.py",
    "challenge/oracles/material_tcr.py",
    "challenge/oracles/battery.py",
    "challenge/oracles/cstr.py",
    "challenge/oracles/conduction1d.py",
    "challenge/oracles/electrical_dc.py",
    "contract_capture/capture_contract.py",
    "contract_capture/build_bound_register.py",
    "contract_capture/write_preregistration.py",
)

FROZEN_DATA = (
    "CHALLENGE_SPEC.json",
    "SYSTEM_INVENTORY.json",
    "PRE_FREEZE_ALLOWED_SOURCE_READS.json",
    "CONTRACT_SURFACE.json",
    "BOUND_REGISTER.json",
    "GENERATION_LOG.json",
    "cases/primary.jsonl",
    "cases/shadows.jsonl",
    "truth/truth.jsonl",
)

FROZEN_TESTS = ("tests/test_blind_v2_challenge.py",)


def build_manifest(result: dict, *, core_tree_sha256: str, core_commit: str) -> dict:
    artifacts = {}
    for relative in FROZEN_SOURCE + FROZEN_DATA + FROZEN_TESTS:
        path = BLIND / relative
        artifacts[relative] = sha256_file(path) if path.exists() else None
    truth_records = result["truth"]
    decided = [t for t in truth_records if t["outcome"] != "REJECTED_AT_BOUNDARY"]
    dual = [t for t in truth_records if t["oracle"]["dual_oracle"]]
    unresolved = [t for t in truth_records if t["truth_class"] == "UNRESOLVED"]
    manifest = {
        "schema": "blind_v2_freeze/1",
        "frozen_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "certified_core_commit": core_commit,
        "certified_core_tree_sha256": core_tree_sha256,
        "generator_seed": generator.SEED,
        "primary_case_count": len(result["cases"]),
        "shadow_count": len(result["shadows"]),
        "scientifically_decided": len(decided),
        "truth_class_counts": _count(truth_records, "truth_class"),
        "outcome_counts": _count(truth_records, "outcome"),
        "family_counts": _count(result["cases"], "family"),
        "dual_oracle_cases": len(dual),
        "dual_oracle_share_of_decided": round(len(dual) / max(1, len(decided)), 4),
        "dual_oracle_independence_levels": _count_optional(dual),
        "unresolved_truth": len(unresolved),
        "precedence_dependent": sum(1 for t in truth_records if t["precedence_dependent"]),
        "channel_ambiguous": sum(1 for t in truth_records if t["channel_ambiguous"]),
        "per_system": result["per_system"],
        "no_peek_audit": audit.run_all(),
        "artifacts": artifacts,
        "verification_recipe": (
            "for each artifact, sha256 over raw file bytes; the manifest's own "
            "bytes are excluded from every value it records"
        ),
    }
    return manifest


def _count_optional(records: list[dict]) -> dict:
    out: dict[str, int] = {}
    for record in records:
        level = record["oracle"]["independence_level"] or "unrecorded"
        out[level] = out.get(level, 0) + 1
    return dict(sorted(out.items()))


def verify(manifest_path: pathlib.Path | None = None) -> dict:
    """Recompute every digest in the manifest. Independent of the writer."""
    path = manifest_path or (BLIND / "FREEZE.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mismatches = []
    missing = []
    for relative, expected in manifest["artifacts"].items():
        target = BLIND / relative
        if not target.exists():
            missing.append(relative)
            continue
        actual = sha256_file(target)
        if actual != expected:
            mismatches.append({"artifact": relative, "expected": expected, "actual": actual})
    return {
        "verified": not mismatches and not missing,
        "mismatches": mismatches,
        "missing": missing,
        "artifact_count": len(manifest["artifacts"]),
    }
