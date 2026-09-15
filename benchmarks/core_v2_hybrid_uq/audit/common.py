"""Shared plumbing for the Core V2 hybrid-UQ round. Nothing scientific lives here."""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "core_v2_hybrid_uq"
sys.path.insert(0, str(ROOT))


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def b3_harness():
    """Battery B3's own harness, registered under its file name so process-pool workers can import it."""
    audit = ROOT / "benchmarks" / "battery_flagship_b3" / "audit"
    if str(audit) not in sys.path:
        sys.path.insert(0, str(audit))
    return load("run_b3", audit / "run_b3.py")


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return v if math.isfinite(v) else ("inf" if v > 0 else "-inf" if v < 0 else "nan")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if hasattr(value, "value") and hasattr(value, "name"):
        return value.value
    return value


def dump(name: str, payload: dict) -> None:
    ROUND.mkdir(parents=True, exist_ok=True)
    (ROUND / name).write_bytes((json.dumps(jsonable(payload), indent=1, sort_keys=False, allow_nan=False) + "\n").encode("utf-8"))
    print("wrote", ROUND / name, flush=True)
