"""Fixture loading. Reads JSON off disk and does nothing else to it."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


#: Where the round's published artifacts -- the top-level ``*.json`` records --
#: are read and written. ``None`` means the committed round directory, which is
#: what a deliberate rebuild of the published record uses. A test points it at a
#: copy so a rebuild never rewrites committed evidence in the working tree, where
#: another test reading the tree would see it change underneath it. Inputs in the
#: round's subdirectories and ``ROUND_REPORT.md`` (never written) stay on ROOT.
ARTIFACT_DIR: Path | None = None


def artifacts() -> Path:
    return ROOT if ARTIFACT_DIR is None else ARTIFACT_DIR


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def all_fixture_names() -> list[str]:
    return sorted(p.stem for p in FIXTURES.glob("*.json"))
