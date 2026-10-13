"""Source prose for natural-language adapter tests: every value stated once, with the span it is quoted from."""

from __future__ import annotations

from typing import Any, Mapping


class Prose:
    """Builds text sentence by sentence and records the span each cited value occupies."""

    def __init__(self) -> None:
        self.text = ""
        self.spans: dict[str, tuple[int, int]] = {}

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


def quantity_words(raw: Mapping[str, Any]) -> str:
    magnitude = raw["magnitude"]
    return f"{magnitude!r} {raw['units']}"


def state_inputs(prose: Prose, payload: Mapping[str, Any]) -> Prose:
    for section in ("operating_context", "known_inputs"):
        for path, value in sorted(payload[section].items()):
            words = quantity_words(value) if isinstance(value, Mapping) else str(value)
            prose.say(f"{path} is ", (path, words), ".")
    return prose


_OPERATOR_WORDS = {"<": "below", "<=": "at most", ">": "above", ">=": "at least", "==": "within"}


def state_claim(payload: Mapping[str, Any], prose: Prose | None = None) -> Prose:
    """Prose that states every criterion of ``payload`` and every input, citing each."""
    prose = state_inputs(prose or Prose(), payload)
    qoi = payload["qoi"]["name"].replace("_", " ")
    target = payload["target"]
    operator = payload["operator"]
    if payload["tolerance"] is not None:
        prose.say(
            "The ", ("claim.qoi", qoi), " must stay ", ("claim.operator", _OPERATOR_WORDS[operator]), " ",
            ("claim.tolerance", quantity_words(payload["tolerance"])), " of ",
            ("claim.target", quantity_words(target["value"])), ".",
        )
    else:
        prose.say(
            "The ", ("claim.qoi", qoi), " must stay ", ("claim.operator", _OPERATOR_WORDS[operator]), " ",
            ("claim.target", quantity_words(target["value"])), ".",
        )
    levels = " and ".join(level.replace("_", " ") for level in payload["evidence"]["required_levels"])
    prose.say(("claim.evidence", f"The decision requires {levels} evidence"), ".")
    channels = payload["uncertainty"]["required_channels"]
    if channels:
        words = " and ".join(c.replace("_", " ") for c in channels)
        k = payload["uncertainty"]["coverage_factor"]
        prose.say(("claim.uncertainty", f"Quantify {words} uncertainty" + (f" with coverage factor {k!r}" if k else "")), ".")
    else:
        prose.say(("claim.uncertainty", "A point comparison is acceptable"), ".")
    prose.say("It is for this decision: ", ("claim.decision", payload["decision"]["statement"]))
    return prose
