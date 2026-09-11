"""Run every case and write the round's machine-readable artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import adjudication, falsification, integrity, residuals, validation
from .evidence import ROOT


def _write(name, payload):
    (ROOT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def core_digest() -> str:
    """The previous rounds' certified digest, recomputed by their own recipe."""
    root = Path(__file__).resolve().parents[3] / "src" / "engcore" / "scientific"
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def evidence_hashes() -> dict:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "evidence").iterdir())
        if path.is_file()
    }


def build() -> dict:
    results = validation.run_all()
    shapes = residuals.run_all(results)
    checks = integrity.run_all(results)
    plants = falsification.run_all()
    found = adjudication.findings(results, shapes)

    rows = [row for bundle in results.values() for row in bundle["rows"]]
    counts = {"CALIBRATION": 0, "VALIDATION": 0, "HELD_OUT": 0}
    for row in rows:
        counts[row["split"]] += 1

    _write("VALIDATION_RESULTS.json", {
        "schema": "validation_results/1",
        "what_this_is": (
            "Every comparison this round ran, at the tolerances METRIC_PLAN.json "
            "fixed before any of them ran. Rows carry the measurement, its "
            "uncertainty, the Core's prediction, the residual, the split and "
            "the applicability status."
        ),
        "row_counts": counts,
        "rows_failing_their_preregistered_tolerance": sum(
            1 for r in rows if r.get("within_tolerance") is False
        ),
        "cases": {
            key: {k: v for k, v in bundle.items() if k != "rows"}
            | {"rows": bundle["rows"]}
            for key, bundle in results.items()
        },
        "integrity": checks,
    })

    _write("RESIDUAL_ANALYSIS.json", {
        "schema": "residual_analysis/1",
        "why_this_exists": (
            "A low summary error with a systematic trend inside it is a "
            "different situation from a low summary error without one. Every "
            "case with more than two points is examined for bias, slope, "
            "curvature, sign changes and low-to-high drift."
        ),
        "analyses": shapes,
    })

    _write("FALSIFICATION.json", {
        "schema": "falsification/1",
        "what_this_is": (
            "Eight controlled failures planted in what the Core returns or in "
            "the result set's own bookkeeping. Five are numerical; three are "
            "structural and leave every residual looking healthy, which is why "
            "the integrity checks exist."
        ),
        **plants,
    })

    _write("FINDINGS.json", {
        "schema": "findings/1",
        "adjudication_classes": adjudication.CLASSES,
        "findings": found,
        "counts_by_class": {
            cls: sum(1 for f in found if f["class"] == cls)
            for cls in adjudication.CLASSES
            if any(f["class"] == cls for f in found)
        },
        "production_changes_made": 0,
    })

    _write("MODEL_ACCOUNTING.json", {
        "schema": "model_accounting/1",
        "rule": "Every shipped model appears exactly once. None disappears because data was unavailable.",
        "model_count": len(adjudication.ACCOUNTING),
        "counts": {
            verdict: sum(1 for v in adjudication.ACCOUNTING.values() if v["verdict"] == verdict)
            for verdict in sorted({v["verdict"] for v in adjudication.ACCOUNTING.values()})
        },
        "models": adjudication.ACCOUNTING,
    })

    return {
        "results": results,
        "shapes": shapes,
        "checks": checks,
        "plants": plants,
        "findings": found,
        "counts": counts,
        "core_digest": core_digest(),
        "evidence_hashes": evidence_hashes(),
    }
