"""Pack loading, the disposition vocabulary and content digests shared by every arm."""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

PACK_DIR = pathlib.Path(__file__).resolve().parent / "pack"
PROBLEM_SCHEMA = "forge.battery_rediscovery.problem/1"
OUTPUT_SCHEMA = "forge.battery_rediscovery.arm_output/1"

SUPPORTED = "SUPPORTED"
NOT_SUPPORTED = "NOT_SUPPORTED"
REVIEW = "REVIEW"
NOT_ASSESSABLE = "NOT_ASSESSABLE"
REFUSED = "REFUSED"
DISPOSITIONS = (SUPPORTED, NOT_SUPPORTED, REVIEW, NOT_ASSESSABLE, REFUSED)
NON_COMMITTAL = (REVIEW, NOT_ASSESSABLE, REFUSED)

AXES = ("MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY")


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


@dataclass(frozen=True)
class Trajectory:
    traj_id: str
    cell: str
    kind: str
    t: np.ndarray
    current: np.ndarray
    voltage: np.ndarray
    temperature: np.ndarray
    z0: float
    capacity_Ah: float

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Trajectory":
        return cls(d["id"], d["cell"], d["kind"], np.asarray(d["t_s"], float), np.asarray(d["current_A"], float),
                   np.asarray(d["voltage_V"], float), np.asarray(d["temperature_C"], float), float(d["z0"]),
                   float(d["capacity_Ah"]))


@dataclass(frozen=True)
class Problem:
    raw: Mapping[str, Any]

    @property
    def problem_id(self) -> str:
        return self.raw["problem_id"]

    @property
    def model(self) -> Mapping[str, Any]:
        return self.raw["declared_model"]

    @property
    def rest_band(self) -> float:
        return float(self.raw["conventions"]["rest_band_A"])

    def calibration(self) -> list[Trajectory]:
        return [Trajectory.from_dict(d) for d in self.raw["sets"]["calibration"]["trajectories"]]

    def heldout(self, set_name: str) -> dict[str, list[Trajectory]] | None:
        s = self.raw["sets"].get(set_name)
        if s is None:
            return None
        return {name: [Trajectory.from_dict(d) for d in trajs] for name, trajs in sorted(s["subsets"].items())}

    def acceptance(self, set_name: str, subset: str) -> Mapping[str, float]:
        return self.raw["acceptance"][f"{set_name}/{subset}"]

    def voltage_sigma(self) -> float | None:
        v = self.raw["measurement_uncertainty"]["voltage_V"]
        return float(v["standard_uncertainty"]) if v.get("status") == "DECLARED_TYPE_B" else None

    @property
    def ocv_knots(self) -> np.ndarray | None:
        ocv = self.model["ocv"]
        return np.asarray(ocv["knots_z_V"], float) if ocv["status"] == "MEASURED_FIXED" else None


def load_pack(pack_dir: pathlib.Path = PACK_DIR) -> dict[str, Problem]:
    manifest = json.loads((pack_dir / "MANIFEST.json").read_bytes())
    problems = {}
    for pid, entry in sorted(manifest["problems"].items()):
        raw = (pack_dir / entry["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"pack file {entry['file']} does not match its manifest digest")
        payload = json.loads(raw)
        if payload.get("schema") != PROBLEM_SCHEMA or payload.get("problem_id") != pid:
            raise RuntimeError(f"pack file {entry['file']} is not problem {pid}")
        problems[pid] = Problem(payload)
    return problems


def combine(dispositions: list[str]) -> str:
    """A set of sub-answers: a decisive failure wins, then a refusal, then not-assessable, then review; else support."""
    for d in (NOT_SUPPORTED, REFUSED, NOT_ASSESSABLE, REVIEW):
        if d in dispositions:
            return d
    return SUPPORTED if dispositions else NOT_ASSESSABLE


__all__ = ["AXES", "DISPOSITIONS", "NON_COMMITTAL", "NOT_ASSESSABLE", "NOT_SUPPORTED", "OUTPUT_SCHEMA", "PACK_DIR",
           "Problem", "REFUSED", "REVIEW", "SUPPORTED", "Trajectory", "canonical_bytes", "combine", "digest", "load_pack",
           "write_json"]
