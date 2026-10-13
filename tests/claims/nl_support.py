"""Source prose for natural-language adapter tests: every value stated once, with the span it is quoted from."""

from __future__ import annotations

import re
from typing import Any, Mapping


class Prose:
    """Builds text sentence by sentence and records the span each cited value occupies.

    ``policy`` holds what the deploying application binds when the prose cannot
    state it (a waiver of uncertainty quantification is never read from prose).
    """

    def __init__(self) -> None:
        self.text = ""
        self.spans: dict[str, tuple[int, int]] = {}
        self.policy: dict[str, Any] = {}

    def say(self, *parts: Any) -> "Prose":
        """Append one sentence. Each part is plain text or ``(span_key, text)`` to cite."""
        for part in parts:
            if isinstance(part, tuple):
                key, words = part
                start = len(self.text)
                self.text += words
                self.spans[key] = (start, len(self.text))
            else:
                self.text += part
        self.text += " "
        return self

    def cite(self, key: str, words: str) -> "Prose":
        """Point ``key`` at the first occurrence of ``words`` in the text."""
        start = self.text.index(words)
        self.spans[key] = (start, start + len(words))
        return self


def quantity_words(raw: Mapping[str, Any]) -> str:
    magnitude = repr(raw["magnitude"])
    if re.fullmatch(r"[+-]?[1-9]\d{0,2}\.\d{3}", magnitude):
        magnitude += "0"  # 1.616 could be a grouped 1616; 1.6160 cannot (the adapter refuses the former)
    return f"{magnitude} {raw['units']}"


def state_inputs(prose: Prose, payload: Mapping[str, Any]) -> Prose:
    for section in ("operating_context", "known_inputs"):
        for path, value in sorted(payload[section].items()):
            words = quantity_words(value) if isinstance(value, Mapping) else str(value)
            prose.say(f"{path} is ", (path, words), ".")
    return prose


_OPERATOR_WORDS = {"<": "below", "<=": "at most", ">": "above", ">=": "at least"}


def comparison_sentence(payload: Mapping[str, Any]) -> str:
    qoi = payload["qoi"]["name"].replace("_", " ")
    target = quantity_words(payload["target"]["value"])
    if payload["tolerance"] is not None:
        return f"The {qoi} must stay within {quantity_words(payload['tolerance'])} of {target}."
    return f"The {qoi} must stay {_OPERATOR_WORDS[payload['operator']]} {target}."


def state_claim(payload: Mapping[str, Any], prose: Prose | None = None) -> Prose:
    """Prose that states every criterion of ``payload`` and every input, citing each."""
    prose = state_inputs(prose or Prose(), payload)
    prose.say(("claim.comparison", comparison_sentence(payload)))
    levels = " and ".join(level.replace("_", " ") for level in payload["evidence"]["required_levels"])
    prose.say(("claim.evidence", f"The decision requires {levels} evidence."))
    channels = payload["uncertainty"]["required_channels"]
    if channels:
        words = " and ".join(c.replace("_", " ") for c in channels)
        k = payload["uncertainty"]["coverage_factor"]
        prose.say(("claim.uncertainty", f"Quantify {words} uncertainty" + (f" with coverage factor {k!r}" if k else "") + "."))
    else:
        prose.policy["uncertainty"] = payload["uncertainty"]
    prose.say("It is for this decision: ", ("claim.decision", payload["decision"]["statement"]))
    return prose
