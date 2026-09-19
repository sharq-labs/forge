"""An OUTER adapter contract for natural-language claims. No language model lives in the Scientific Core.

A language model may *propose* a structured claim from prose. It has no
authority beyond that proposal, and this module is the boundary that enforces
it deterministically before the proposal reaches :func:`~engcore.claims.compile_claim`:

* **No authority fields.** A proposal carrying a verdict, evidence, attained
  levels, uncertainty values, a selected or "applicable" model, or a decision
  is REFUSED outright -- those are outputs of the Core, never inputs from a
  model.
* **No invented physical values.** Every stated input (known input or
  operating context) must cite the exact span of the source text it came
  from, and that span must contain the value's magnitude as written. A value
  the text does not contain is not dropped silently and never defaulted: it is
  moved to ``missing_inputs``, so the compiler answers NEEDS_INPUT and names it.
* **No declared-away uncertainty.** A proposal cannot declare an uncertainty
  channel quantified or zero; it can only *demand* channels, exactly as a
  structured caller can. A ``ZERO_DECLARED`` discrepancy from a model is refused.
* **The compiler keeps its answers.** The result is whatever
  :func:`compile_claim` decides -- READY, NEEDS_INPUT, AMBIGUOUS, REFUSED --
  with the adapter's own findings attached.

The adapter never calls a model. :class:`ClaimProposer` is the protocol an
outer integration implements; this module only checks what it returns.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .._records import require_mapping, require_text

#: Fields no language-model proposal may carry, anywhere in the proposal.
FORBIDDEN_AUTHORITY_FIELDS = frozenset({
    "verdict", "claim_verdict", "credibility", "assurance", "evidence_records",
    "attained_levels", "validation_result", "uncertainty_values", "quantified_uncertainty",
    "selected_model", "selected_capability", "model_applicable", "applicability", "decision_outcome",
    "comparison", "result",
})


class ClaimProposer(Protocol):
    """Implemented OUTSIDE the Core by an integration that calls a language model."""

    def propose(self, text: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class NaturalLanguageCompilation:
    status: str  # "refused" or the compiler's status
    findings: tuple[str, ...]
    moved_to_missing: tuple[str, ...]
    compiled: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": list(self.findings),
            "moved_to_missing": list(self.moved_to_missing),
            "compiled": None if self.compiled is None else self.compiled.to_dict(),
            "authority": "language-model proposal; the deterministic compiler decided every status",
        }


def _forbidden(node: Any, where: str = "") -> list[str]:
    found = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            path = f"{where}/{key}"
            if str(key) in FORBIDDEN_AUTHORITY_FIELDS:
                found.append(path)
            found.extend(_forbidden(value, path))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_forbidden(value, f"{where}/{i}"))
    return found


def _magnitude_in(span: str, raw: Any) -> bool:
    """Whether the span literally states the value (magnitude for a quantity, the value for a count/text)."""
    if isinstance(raw, Mapping) and "magnitude" in raw:
        number = float(raw["magnitude"])
    elif isinstance(raw, bool):
        return str(raw).lower() in span.lower()
    elif isinstance(raw, int):
        number = float(raw)
    elif isinstance(raw, str):
        return raw in span
    else:
        return False
    for token in re.findall(r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", span):
        try:
            if float(token.replace(",", ".")) == number:
                return True
        except ValueError:
            continue
    return False


def compile_natural_language(text: str, proposal: Mapping[str, Any], spans: Mapping[str, tuple[int, int]], registry: Any) -> NaturalLanguageCompilation:
    """Check a model's proposal against its source text, then let the deterministic compiler decide."""
    from ..compiler import compile_claim

    require_text(text, field="text")  # non-empty; spans index the text exactly as given, so it is not stripped
    proposal = copy.deepcopy(dict(require_mapping(proposal, field="proposal")))
    forbidden = _forbidden(proposal)
    if forbidden:
        return NaturalLanguageCompilation("refused", tuple(f"a proposal may not carry {p}: that is the Core's output" for p in forbidden), ())
    discrepancy = proposal.get("discrepancy") or {}
    if isinstance(discrepancy, Mapping) and discrepancy.get("kind") == "zero_declared":
        return NaturalLanguageCompilation("refused", ("a language-model proposal may not declare model-form discrepancy zero",), ())
    findings: list[str] = []
    moved: list[str] = []
    missing = list(proposal.get("missing_inputs") or [])
    for section in ("known_inputs", "operating_context"):
        inputs = dict(proposal.get(section) or {})
        for path in sorted(inputs):
            span = spans.get(path)
            ok = False
            if span is not None:
                start, end = span
                if 0 <= start < end <= len(text):
                    ok = _magnitude_in(text[start:end], inputs[path])
            if not ok:
                findings.append(f"{section}.{path}: the source text does not state this value at a cited span; moved to missing_inputs")
                moved.append(path)
                del inputs[path]
                if path not in missing:
                    missing.append(path)
        proposal[section] = inputs
    proposal["missing_inputs"] = sorted(missing)
    compiled = compile_claim(proposal, registry)
    return NaturalLanguageCompilation(compiled.status.value, tuple(findings), tuple(moved), compiled)


__all__ = ["FORBIDDEN_AUTHORITY_FIELDS", "ClaimProposer", "NaturalLanguageCompilation", "compile_natural_language"]
