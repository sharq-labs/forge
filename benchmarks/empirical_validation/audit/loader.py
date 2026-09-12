"""Fixture loading. Reads JSON off disk and does nothing else to it."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def all_fixture_names() -> list[str]:
    return sorted(p.stem for p in FIXTURES.glob("*.json"))
