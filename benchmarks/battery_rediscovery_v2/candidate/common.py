"""Pack loading, the answer vocabulary, content digests and the frozen declarations shared by every v2 arm."""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

PACK_DIR = pathlib.Path(__file__).resolve().parent / "pack"
SPEC_SCHEMA = "forge.mind.repsem.problem/1"
MANIFEST_SCHEMA = "forge.battery_rediscovery_v2.pack_manifest/1"
OUTPUT_SCHEMA = "forge.battery_rediscovery_v2.arm_output/1"

SUPPORTED, NOT_SUPPORTED, REVIEW, NOT_ASSESSABLE, REFUSED = "SUPPORTED", "NOT_SUPPORTED", "REVIEW", "NOT_ASSESSABLE", "REFUSED"
DISPOSITIONS = (SUPPORTED, NOT_SUPPORTED, REVIEW, NOT_ASSESSABLE, REFUSED)
NON_COMMITTAL = (REVIEW, NOT_ASSESSABLE, REFUSED)
AXES = ("MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY")

#: The fitted-OCV representation the candidate may reason about (knot positions; values are latent parameters).
FITTED_OCV_KNOTS_SOC = (0.0, 0.05, 0.15, 0.3, 0.5, 0.75, 1.0)
FITTED_OCV_BOUNDS_V = (2.0, 4.5)

#: Mind-based arms run these seeds; the primary seed's answers are scored, the others are a stability record.
#: Deterministic arms are seed-independent and run once (their answers are the same for every seed).
SEEDS = (0, 1, 2)
PRIMARY_SEED = 0


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def write_json(path: pathlib.Path, payload: Any) -> str:
    """Write LF-only, sorted, indented JSON as bytes; return the sha256 of the bytes written."""
    raw = (json.dumps(payload, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def load_pack(pack_dir: pathlib.Path = PACK_DIR) -> dict[str, dict[str, Any]]:
    """Every problem specification of the pack, each checked against the manifest digest."""
    manifest = json.loads((pack_dir / "MANIFEST.json").read_bytes())
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise RuntimeError("not a battery_rediscovery_v2 pack manifest")
    out = {}
    for pid, entry in sorted(manifest["problems"].items()):
        raw = (pack_dir / entry["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"pack file {entry['file']} does not match its manifest digest")
        spec = json.loads(raw)
        if spec.get("schema") != SPEC_SCHEMA or spec.get("problem_id") != pid:
            raise RuntimeError(f"pack file {entry['file']} is not problem {pid}")
        out[pid] = spec
    return out


def combine(dispositions: list[str]) -> str:
    """A set of sub-answers: a decisive failure wins, then a refusal, then not-assessable, then review; else support."""
    for d in (NOT_SUPPORTED, REFUSED, NOT_ASSESSABLE, REVIEW):
        if d in dispositions:
            return d
    return SUPPORTED if dispositions else NOT_ASSESSABLE


__all__ = ["AXES", "DISPOSITIONS", "FITTED_OCV_BOUNDS_V", "FITTED_OCV_KNOTS_SOC", "NON_COMMITTAL", "NOT_ASSESSABLE",
           "NOT_SUPPORTED", "OUTPUT_SCHEMA", "PACK_DIR", "PRIMARY_SEED", "REFUSED", "REVIEW", "SEEDS", "SPEC_SCHEMA",
           "SUPPORTED", "canonical_bytes", "combine", "digest", "load_pack", "write_json"]
