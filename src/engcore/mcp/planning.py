"""Deterministic capability routing before any scientific case is built."""

from __future__ import annotations

import re
from typing import Any

from .systems import SYSTEMS

__all__ = ["PLAN_SCHEMA", "plan_engineering_intent"]

PLAN_SCHEMA = "engineering_plan/1"

_TERMS = {
    "electrothermal": (
        "electrothermal", "electro-thermal", "resistor", "resistance",
        "conductor", "source voltage", "حراري كهربائي", "حرارية كهربائية",
        "كهربائية حرارية", "مقاومة", "مقاوم",
        "موصل", "جهد المصدر",
    ),
    "battery": (
        "battery", "cell", "discharge", "state of charge", "soc",
        "بطارية", "بطاريه", "خلية", "تفريغ", "حالة الشحن",
    ),
}


def _contains_term(text: str, term: str) -> bool:
    """Phrase match without treating ``cell`` in ``excellent`` as evidence."""
    if term.isascii():
        return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None
    return term in text


def plan_engineering_intent(description: str) -> dict[str, Any]:
    """Select a supported boundary only when the user's own words distinguish it."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description must be a non-empty string")
    lowered = description.lower()
    candidates = []
    for boundary in SYSTEMS:
        matched = sorted({
            term for term in _TERMS.get(boundary.name, ())
            if _contains_term(lowered, term)
        })
        candidates.append({
            "system": boundary.name,
            "tool": boundary.tool,
            "score": len(matched),
            "matched_terms": matched,
            "summary": boundary.summary,
        })
    ranked = sorted(candidates, key=lambda item: (-item["score"], item["system"]))
    selected = None
    if ranked and ranked[0]["score"] > 0:
        if len(ranked) == 1 or ranked[0]["score"] > ranked[1]["score"]:
            selected = ranked[0]["system"]
    return {
        "schema": PLAN_SCHEMA,
        "status": "selected" if selected else "needs_system",
        "selected_system": selected,
        "candidates": ranked,
        "question": None if selected else (
            "أي نظام تقصد: electrothermal أم battery؟ صف المكوّن أو عملية التشغيل بوضوح."
        ),
        "selection_authority": "deterministic_keyword_router",
        "does_not_establish": [
            "model applicability", "model adequacy", "solver compatibility",
            "scientific validity",
        ],
    }
