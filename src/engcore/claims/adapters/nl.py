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
  from, and that span must state the value -- magnitude and unit. A value the
  text does not contain is not dropped silently and never defaulted: it is
  moved to ``missing_inputs``, so the compiler answers NEEDS_INPUT and names it.
* **No AI-authored decision criteria.** Every field of the claim's scientific
  identity -- the quantity, the comparison, the bound, the tolerance, the
  evidence bar, the uncertainty demand, the decision, the declarations -- needs
  a provenance other than the model (:mod:`.grounding`): stated in the cited
  text, bound by the deploying application's policy, computed from grounded
  values, or the field's least-authority value. One field without it and the
  answer is UNGROUNDED: no claim is compiled, nothing can run, and the model's
  values are returned as advisory only.
* **No declared-away uncertainty.** A proposal cannot declare an uncertainty
  channel quantified or zero; it can only *demand* channels, exactly as a
  structured caller can. A ``ZERO_DECLARED`` discrepancy from a model is refused.
* **The compiler keeps its answers.** When every field is grounded the result
  is whatever :func:`compile_claim` decides -- READY, NEEDS_INPUT, AMBIGUOUS,
  REFUSED -- with the adapter's own findings and the provenance of each field.

The adapter never calls a model. :class:`ClaimProposer` is the protocol an
outer integration implements; this module only checks what it returns.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .._records import require_mapping, require_text
from ..contract import SCIENTIFIC_FIELDS, ScientificClaim
from ..errors import ClaimContractError
from ...scientific.errors import ScientificCoreError
from .grounding import (
    ADAPTER_GROUNDED_FIELDS,
    CRITERION_SPAN_PREFIX,
    CRITERION_SPANS,
    FIELD_RULES,
    POLICY_TEXT_CHECKS,
    CriterionProvenance,
    FieldProvenance,
    GroundingContext,
    COMPARISON_FIELDS,
    TokenLedger,
    Ungrounded,
    declared_input_sentences,
    ground_input,
    policy_comparison_conflicts,
    policy_consumes,
    unread_sentences,
)

#: Fields no language-model proposal may carry, anywhere in the proposal.
FORBIDDEN_AUTHORITY_FIELDS = frozenset({
    "verdict", "claim_verdict", "credibility", "assurance", "evidence_records",
    "attained_levels", "validation_result", "uncertainty_values", "quantified_uncertainty",
    "selected_model", "selected_capability", "model_applicable", "applicability", "decision_outcome",
    "comparison", "result",
})

#: The status of a proposal whose decision criteria are not all grounded.
UNGROUNDED = "ungrounded"


class ClaimProposer(Protocol):
    """Implemented OUTSIDE the Core by an integration that calls a language model."""

    def propose(self, text: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class NaturalLanguageCompilation:
    status: str  # "refused", "ungrounded" or the compiler's status
    findings: tuple[str, ...]
    moved_to_missing: tuple[str, ...]
    compiled: Any = None
    #: Why each scientific field of the compiled claim holds its value.
    provenance: tuple[FieldProvenance, ...] = ()
    #: Proposed values with no admissible provenance. Shown to the caller; never compiled.
    advisory: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": list(self.findings),
            "moved_to_missing": list(self.moved_to_missing),
            "compiled": None if self.compiled is None else self.compiled.to_dict(),
            "provenance": [item.to_dict() for item in self.provenance],
            "advisory": dict(self.advisory or {}),
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


def _canonical_fields(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """The claim's own serialization of each field, or None when the payload is not a claim."""
    try:
        return ScientificClaim.from_dict(payload).to_dict()
    except ClaimContractError:
        return None


def compile_natural_language(
    text: str,
    proposal: Mapping[str, Any],
    spans: Mapping[str, tuple[int, int]],
    registry: Any,
    *,
    policy: Mapping[str, Any] | None = None,
) -> NaturalLanguageCompilation:
    """Check a model's proposal against its source text, then let the deterministic compiler decide.

    ``policy`` is supplied by the deploying application, never by the model: a
    mapping from claim field (``evidence``, ``uncertainty``, ``decision``,
    ``decision_context``, ...) to the serialized value that application fixes.
    A policy-bound field takes the policy's value; a proposal that states a
    different one is not grounded.
    """
    from ..compiler import compile_claim

    require_text(text, field="text")  # non-empty; spans index the text exactly as given, so it is not stripped
    proposal = copy.deepcopy(dict(require_mapping(proposal, field="proposal")))
    forbidden = _forbidden(proposal)
    if forbidden:
        return NaturalLanguageCompilation("refused", tuple(f"a proposal may not carry {p}: that is the Core's output" for p in forbidden), ())
    discrepancy = proposal.get("discrepancy") or {}
    if isinstance(discrepancy, Mapping) and discrepancy.get("kind") == "zero_declared":
        return NaturalLanguageCompilation("refused", ("a language-model proposal may not declare model-form discrepancy zero",), ())
    policy = dict(require_mapping(policy or {}, field="policy"))
    not_criteria = sorted(set(policy) - set(FIELD_RULES))
    if not_criteria:
        raise ClaimContractError(f"a policy binds decision criteria only; it cannot bind {not_criteria}")
    for path in list(spans):
        if path.startswith(CRITERION_SPAN_PREFIX) and path[len(CRITERION_SPAN_PREFIX):] not in CRITERION_SPANS:
            return NaturalLanguageCompilation(
                "refused",
                (f"span key {path!r} is not one of {sorted(CRITERION_SPAN_PREFIX + s for s in CRITERION_SPANS)}",),
                (),
            )

    findings: list[str] = []
    moved: list[str] = []
    provenance: list[FieldProvenance] = []
    advisory: dict[str, Any] = {}
    ledger = TokenLedger()
    #: start offsets of every sentence some input, rule or policy accounted for (closed world)
    consumed: set[int] = set()

    # Inputs first: an input the text does not state is moved to missing, never defaulted.
    missing = list(proposal.get("missing_inputs") or [])
    grounded_inputs: dict[str, Any] = {}
    for section in ("known_inputs", "operating_context"):
        inputs = dict(proposal.get(section) or {})
        for path in sorted(inputs):
            if path.startswith(CRITERION_SPAN_PREFIX):
                return NaturalLanguageCompilation("refused", (f"input path {path!r} collides with the criterion span namespace",), ())
            try:
                grounded_inputs[path] = ground_input(text, spans, ledger, path, inputs[path], consumed)
            except (Ungrounded, ScientificCoreError, ValueError, TypeError) as why:
                findings.append(f"{section}.{path}: {why}; moved to missing_inputs")
                moved.append(path)
                del inputs[path]
                if path not in missing:
                    missing.append(path)
        proposal[section] = inputs
        provenance.append(FieldProvenance(section, CriterionProvenance.SOURCE_GROUNDED, "every remaining input is stated at its cited span"))
    proposal["missing_inputs"] = sorted(missing)
    consumed.update(declared_input_sentences(text, [*moved, *proposal["missing_inputs"], *(
        path for section in ("known_inputs", "operating_context") for path in proposal[section])]))
    provenance.append(FieldProvenance(
        "missing_inputs", CriterionProvenance.COMPUTED_FROM_GROUNDED,
        "declared unknowns and ungrounded inputs; an unknown input can only withhold an answer",
    ))

    # A policy-bound field takes the policy's value. A proposal disagreeing with it is not grounded.
    policy_view = _canonical_fields({**proposal, **policy})
    comparison_conflicts, agreeing = policy_comparison_conflicts(text, policy)
    for name, bound in sorted(policy.items()):
        if name in proposal:
            # The field alone is compared: every other policy-bound field already holds the policy's value.
            proposed_view = _canonical_fields({**proposal, **policy, name: proposal[name]})
            if proposed_view is None or policy_view is None or proposed_view.get(name) != policy_view.get(name):
                findings.append(f"{name}: the proposal states a value the deploying policy does not; the proposal is not grounded")
                advisory[name] = proposal.get(name)
                provenance.append(FieldProvenance(name, CriterionProvenance.AI_PROPOSED, "contradicts the bound policy"))
                continue
        if name in COMPARISON_FIELDS and comparison_conflicts:
            findings.append(f"{name}: the user's text states a comparison the deploying policy would replace "
                            f"({comparison_conflicts[0]}); a policy may not silently override a stated comparison")
            advisory[name] = proposal.get(name)
            provenance.append(FieldProvenance(name, CriterionProvenance.AI_PROPOSED, "the text states a different comparison"))
            continue
        stricter = POLICY_TEXT_CHECKS.get(name, lambda *_: [])(text, bound if isinstance(bound, Mapping) else {})
        if stricter:
            findings.append(f"{name}: the user's text demands {stricter}, beyond what the deploying policy binds; "
                            "a policy may not silently drop a stricter stated requirement")
            advisory[name] = proposal.get(name)
            provenance.append(FieldProvenance(name, CriterionProvenance.AI_PROPOSED, f"text demands {stricter} beyond the policy"))
            continue
        proposal[name] = copy.deepcopy(bound)
        consumed.update(agreeing if name in COMPARISON_FIELDS else policy_consumes(text, name, bound))
        provenance.append(FieldProvenance(name, CriterionProvenance.POLICY_BOUND, "fixed by the deploying application's policy"))

    # Every other scientific field needs a rule, and the rule has to pass.
    context = GroundingContext(text=text, spans=spans, ledger=ledger, proposal=proposal, grounded_inputs=grounded_inputs,
                               consumed=consumed)
    for name in SCIENTIFIC_FIELDS:
        if name in ADAPTER_GROUNDED_FIELDS or name in policy:
            continue
        raw = proposal.get(name)
        rule = FIELD_RULES.get(name)
        if rule is None:
            why: Exception | str = "no grounding rule exists for this field; a language model cannot establish it"
        else:
            try:
                provenance.append(rule(context, raw))
                continue
            except Ungrounded as exc:
                why = exc
            except (KeyError, TypeError, ValueError, AttributeError, ScientificCoreError) as exc:
                why = f"not a well-formed value ({exc})"
        findings.append(f"{name}: {why}")
        advisory[name] = raw
        provenance.append(FieldProvenance(name, CriterionProvenance.AI_PROPOSED, str(why)))

    # Closed world (third review A2): a sentence nothing accounted for may retract, condition or tighten
    # what was read. It is not assumed to change nothing.
    unread = unread_sentences(text, consumed)
    if unread:
        findings.append(f"the text has sentences no controlled form reads ({unread[0]!r}"
                        + (f" and {len(unread) - 1} more" if len(unread) > 1 else "")
                        + "); restate them in a controlled form, bind them by policy, or remove them")
        advisory["unread_sentences"] = unread

    if advisory:
        return NaturalLanguageCompilation(
            UNGROUNDED, tuple(findings), tuple(moved), None, tuple(provenance), advisory,
        )

    # The record keeps the user's own words, never the model's paraphrase of them.
    proposal["statement"] = text.strip()
    compiled = compile_claim(proposal, registry)
    return NaturalLanguageCompilation(compiled.status.value, tuple(findings), tuple(moved), compiled, tuple(provenance), {})


__all__ = [
    "FORBIDDEN_AUTHORITY_FIELDS",
    "UNGROUNDED",
    "ClaimProposer",
    "NaturalLanguageCompilation",
    "compile_natural_language",
]
