"""Provenance of a language-model claim proposal: which fields may decide a verdict.

A claim's verdict is decided against its criteria -- the quantity, the
comparison, the bound, the tolerance, the evidence bar, the uncertainty demand
and the inputs. A language model may *propose* all of them. It may establish
none of them. This module decides, field by field, whether a proposed value has
an authority other than the model:

``SOURCE_GROUNDED``         the user's text states it, at a span the proposal
                            cites, and the value is read back from that span
                            (a number with its unit, an operator phrase, every
                            requirement the text names and none it does not).
``POLICY_BOUND``            the deploying application fixed it. A policy is an
                            argument of the adapter, never part of a proposal.
``COMPUTED_FROM_GROUNDED``  derived deterministically from grounded values
                            (the claim shape from its operator, a bound named
                            by reference to a grounded input).
``LEAST_AUTHORITY``         the value can only make a verdict harder to reach:
                            no assumptions, an UNKNOWN discrepancy, no extra
                            capability constraint.
``AI_PROPOSED``             none of the above. Advisory: shown, never used.

The rule is not a list of dangerous field names. **Every** field that takes part
in a claim's scientific identity (:data:`~engcore.claims.contract.SCIENTIFIC_FIELDS`)
must have an admissible provenance. A field with no grounding rule here -- one
added to the contract later, for instance -- is AI_PROPOSED by construction and
blocks compilation. Grounding is fail-closed in the same way: a span that does
not parse, a number used to ground two different fields, a requirement the text
names that the proposal dropped, all leave the field ungrounded.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, Mapping, Sequence

from ...scientific.errors import ScientificCoreError
from ...scientific.ir.constraints import ConstraintOperator
from ...scientific.results.validation import ValidationLevel
from ...scientific.units.quantity import Quantity
from ...sria.uncertainty import UncertaintyChannel

#: Spans for claim criteria are keyed ``claim.<field>``; spans for inputs keep
#: their input path, as they always have.
CRITERION_SPAN_PREFIX = "claim."


class CriterionProvenance(str, Enum):
    SOURCE_GROUNDED = "source_grounded"
    POLICY_BOUND = "policy_bound"
    COMPUTED_FROM_GROUNDED = "computed_from_grounded"
    LEAST_AUTHORITY = "least_authority"
    AI_PROPOSED = "ai_proposed"


#: The provenances that may establish a decision criterion. AI_PROPOSED is absent.
ADMISSIBLE_PROVENANCE = frozenset(
    {
        CriterionProvenance.SOURCE_GROUNDED,
        CriterionProvenance.POLICY_BOUND,
        CriterionProvenance.COMPUTED_FROM_GROUNDED,
        CriterionProvenance.LEAST_AUTHORITY,
    }
)


@dataclass(frozen=True)
class FieldProvenance:
    """Why one field of a compiled claim holds the value it holds."""

    field: str
    provenance: CriterionProvenance
    basis: str

    @property
    def admissible(self) -> bool:
        return self.provenance in ADMISSIBLE_PROVENANCE

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "provenance": self.provenance.value, "basis": self.basis}


class Ungrounded(Exception):
    """A proposed value with no admissible provenance. Carries the reason."""


# ---------------------------------------------------------------------------
# Reading the source text
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?")
_UNIT_STOP = ",;:)]}"


def normalized(text: str) -> str:
    """Lower case, ``_`` and ``-`` read as spaces, whitespace collapsed."""
    return " ".join(re.sub(r"[_\-]+", " ", str(text).lower()).split())


def _phrase_in(phrase: str, text: str) -> bool:
    words = normalized(phrase)
    if not words:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(words)}(?![a-z0-9])", normalized(text)) is not None


def _unit_candidates(rest: str) -> Iterator[str]:
    """Unit spellings that may follow a number, longest first."""
    words: list[str] = []
    for raw in rest.split()[:10]:
        stop = next((i for i, c in enumerate(raw) if c in _UNIT_STOP), None)
        word = raw if stop is None else raw[:stop]
        word = word.rstrip(".")
        if word:
            words.append(word)
        if stop is not None or raw.endswith("."):
            break
    for n in range(len(words), 0, -1):
        yield " ".join(words[:n])


@dataclass
class TokenLedger:
    """Which number in the text grounded which field: one number, one field."""

    used: dict[tuple[int, int], str] = field(default_factory=dict)

    def claim(self, token: tuple[int, int], path: str) -> None:
        self.used[token] = path


@dataclass(frozen=True)
class StatedNumber:
    start: int
    end: int
    magnitude: float
    unit: str | None  # None: no unit follows the number

    @property
    def token(self) -> tuple[int, int]:
        return (self.start, self.end)


def stated_numbers(text: str, start: int, end: int) -> list[StatedNumber]:
    """Every number written inside ``text[start:end]``, with the unit that follows it, if any."""
    found: list[StatedNumber] = []
    window = text[start:end]
    for match in _NUMBER.finditer(window):
        try:
            magnitude = float(match.group().replace(",", "."))
        except ValueError:
            continue
        rest = window[match.end():]
        unit: str | None = None
        for candidate in _unit_candidates(rest):
            try:
                # The Core's own reader, with its refusal of arithmetic in the unit half.
                parsed = Quantity.parse(f"{magnitude!r} {candidate}")
            except Exception:  # any refusal means: this spelling is not a unit
                continue
            if math.isclose(parsed.magnitude, magnitude, rel_tol=0.0, abs_tol=0.0):
                unit = parsed.units
                break
        found.append(StatedNumber(start + match.start(), start + match.end(), magnitude, unit))
    return found


def _same_value(stated: StatedNumber, value: Quantity, *, spread: bool) -> bool:
    if stated.unit is None:
        if value.dimensionality != dimensionless_dimension():
            return False
        written = Quantity(stated.magnitude, "dimensionless")
    else:
        written = Quantity(stated.magnitude, stated.unit)
    if not written.is_compatible_with(value):
        return False
    try:
        mine = written.magnitude_as_spread_in(value.units) if spread else written.magnitude_in(value.units)
    except ScientificCoreError:
        return False
    return math.isclose(mine, value.magnitude, rel_tol=1e-9, abs_tol=1e-12)


_DIMENSIONLESS: list[str] = []


def dimensionless_dimension() -> str:
    if not _DIMENSIONLESS:
        _DIMENSIONLESS.append(Quantity(1.0, "dimensionless").dimensionality)
    return _DIMENSIONLESS[0]


def span_text(text: str, spans: Mapping[str, Sequence[int]], key: str) -> tuple[int, int] | None:
    raw = spans.get(key)
    if raw is None or isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence) or len(raw) != 2:
        return None
    if any(isinstance(v, bool) or not isinstance(v, int) for v in raw):
        return None
    start, end = int(raw[0]), int(raw[1])
    if not (0 <= start < end <= len(text)):
        return None
    return start, end


def ground_quantity(
    text: str,
    where: tuple[int, int],
    value: Quantity,
    ledger: TokenLedger,
    path: str,
    *,
    spread: bool = False,
    allowed_reuse: tuple[int, int] | None = None,
) -> StatedNumber:
    """The number in the span that states ``value`` (unit included) and grounds nothing else."""
    candidates = [n for n in stated_numbers(text, *where) if _same_value(n, value, spread=spread)]
    if not candidates:
        raise Ungrounded(f"the cited text does not state {value.magnitude!r} {value.units}")
    for number in candidates:
        holder = ledger.used.get(number.token)
        if holder is None or holder == path or number.token == allowed_reuse:
            ledger.claim(number.token, path)
            return number
    holders = sorted({ledger.used[n.token] for n in candidates})
    raise Ungrounded(f"the number that states this value already grounds {holders}; one statement grounds one field")


def ground_count(text: str, where: tuple[int, int], value: float, ledger: TokenLedger, path: str) -> StatedNumber:
    for number in stated_numbers(text, *where):
        if number.unit is None and math.isclose(number.magnitude, float(value), rel_tol=1e-12, abs_tol=0.0):
            holder = ledger.used.get(number.token)
            if holder is None or holder == path:
                ledger.claim(number.token, path)
                return number
    raise Ungrounded(f"the cited text does not state {value!r}")


# ---------------------------------------------------------------------------
# Vocabularies the text can name
# ---------------------------------------------------------------------------

#: Phrases that state each comparison. Matched longest first, without overlap,
#: so "not exceed" is never also read as "exceed".
OPERATOR_PHRASES: Mapping[ConstraintOperator, tuple[str, ...]] = {
    ConstraintOperator.LESS_EQUAL: (
        "<=", "≤", "at most", "no more than", "not more than", "does not exceed", "do not exceed",
        "must not exceed", "not exceed", "not exceeding", "no greater than", "not greater than",
        "not above", "no higher than", "up to",
    ),
    ConstraintOperator.LESS_THAN: ("<", "less than", "below", "under", "lower than", "smaller than", "beneath"),
    ConstraintOperator.GREATER_EQUAL: (
        ">=", "≥", "at least", "no less than", "not less than", "not below", "no lower than", "no fewer than",
    ),
    ConstraintOperator.GREATER_THAN: (">", "greater than", "more than", "above", "exceeds", "exceed", "higher than", "over"),
    ConstraintOperator.EQUAL: ("±", "+/-", "+-", "within", "equals", "equal to", "approximately", "=="),
}


def operators_stated(span: str) -> set[ConstraintOperator]:
    """Every comparison the span states, by longest non-overlapping phrase."""
    low = " " + str(span).lower() + " "
    phrases = sorted(
        ((phrase, op) for op, items in OPERATOR_PHRASES.items() for phrase in items),
        key=lambda item: -len(item[0]),
    )
    taken = [False] * len(low)
    found: set[ConstraintOperator] = set()
    for phrase, op in phrases:
        word_like = phrase[0].isalpha()
        pattern = rf"(?<![a-z]){re.escape(phrase)}(?![a-z])" if word_like else re.escape(phrase)
        for match in re.finditer(pattern, low):
            if any(taken[match.start():match.end()]):
                continue
            for i in range(match.start(), match.end()):
                taken[i] = True
            found.add(op)
    return found


def _vocabulary_named(members: Sequence[Enum], text: str) -> set[str]:
    return {member.value for member in members if _phrase_in(member.value, text)}


LEVEL_VOCABULARY = tuple(level for level in ValidationLevel if level is not ValidationLevel.UNVERIFIED)
CHANNEL_VOCABULARY = tuple(UncertaintyChannel)

#: A waiver of uncertainty quantification has to be written down; it is never inferred.
UNCERTAINTY_WAIVER_PHRASES = (
    "no uncertainty quantification",
    "without uncertainty quantification",
    "uncertainty quantification is not required",
    "uncertainty is not required",
    "point comparison",
    "point estimate is sufficient",
)


# ---------------------------------------------------------------------------
# Per-field grounding rules
# ---------------------------------------------------------------------------


@dataclass
class GroundingContext:
    text: str
    spans: Mapping[str, Sequence[int]]
    ledger: TokenLedger
    proposal: Mapping[str, Any]
    #: input path -> the stated number that grounded it (quantity inputs only)
    grounded_inputs: dict[str, StatedNumber | None]

    def span(self, name: str) -> tuple[int, int]:
        where = span_text(self.text, self.spans, CRITERION_SPAN_PREFIX + name)
        if where is None:
            raise Ungrounded(f"no valid source span cited for {CRITERION_SPAN_PREFIX + name}")
        return where

    def cited(self, name: str) -> str:
        start, end = self.span(name)
        return self.text[start:end]


def _quote(text: str, where: tuple[int, int]) -> str:
    return f"span [{where[0]}, {where[1]}) {text[where[0]:where[1]]!r}"


Rule = Callable[[GroundingContext, Any], FieldProvenance]


def _source(name: str, ctx: GroundingContext, where: tuple[int, int], note: str = "") -> FieldProvenance:
    return FieldProvenance(name, CriterionProvenance.SOURCE_GROUNDED, _quote(ctx.text, where) + (f"; {note}" if note else ""))


def _rule_qoi(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    where = ctx.span("qoi")
    cited = ctx.text[where[0]:where[1]]
    name = str(raw.get("name", ""))
    missing = [token for token in name.split("_") if token and not _phrase_in(token, cited)]
    if missing:
        raise Ungrounded(f"the cited text does not name the quantity {name!r} (missing {missing})")
    for key, value in dict(raw.get("qualifiers") or {}).items():
        if not _phrase_in(str(value), cited):
            raise Ungrounded(f"the cited text does not name qualifier {key}={value!r}")
    return _source("qoi", ctx, where, "its unit's dimension is checked against the grounded bound by the contract")


def _rule_operator(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    where = ctx.span("operator")
    try:
        proposed = ConstraintOperator(raw)
    except ValueError as exc:
        raise Ungrounded(f"operator {raw!r} is not a comparison") from exc
    stated = operators_stated(ctx.text[where[0]:where[1]])
    if stated != {proposed}:
        raise Ungrounded(
            f"the cited text states the comparison(s) {sorted(op.value for op in stated)}, "
            f"not exactly {proposed.value!r}"
        )
    return _source("operator", ctx, where)


def _rule_kind(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    try:
        operator = ConstraintOperator(ctx.proposal.get("operator"))
    except ValueError as exc:
        raise Ungrounded("the claim shape follows from the operator, which is not a comparison") from exc
    derived = "tolerance_band" if operator is ConstraintOperator.EQUAL else "threshold"
    if raw != derived:
        raise Ungrounded(f"kind {raw!r} contradicts the operator {operator.value!r}, which makes it {derived!r}")
    return FieldProvenance("kind", CriterionProvenance.COMPUTED_FROM_GROUNDED, f"derived from operator {operator.value!r}")


def _rule_target(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    where = ctx.span("target")
    ref = raw.get("input_ref")
    if ref is not None:
        stated = ctx.grounded_inputs.get(ref)
        value = _input_value(ctx.proposal, ref)
        if stated is None or not isinstance(value, Quantity):
            raise Ungrounded(f"the bound names input {ref!r}, which is not a quantity the text states")
        ground_quantity(ctx.text, where, value, ctx.ledger, "claim.target", allowed_reuse=stated.token)
        return FieldProvenance(
            "target", CriterionProvenance.COMPUTED_FROM_GROUNDED,
            f"the bound is grounded input {ref!r}; " + _quote(ctx.text, where),
        )
    value = Quantity.from_dict(raw["value"])
    ground_quantity(ctx.text, where, value, ctx.ledger, "claim.target")
    return _source("target", ctx, where)


def _rule_tolerance(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    if raw is None:
        return FieldProvenance(
            "tolerance", CriterionProvenance.COMPUTED_FROM_GROUNDED,
            "no tolerance: a threshold claim carries none (enforced by the contract)",
        )
    where = ctx.span("tolerance")
    ground_quantity(ctx.text, where, Quantity.from_dict(raw), ctx.ledger, "claim.tolerance", spread=True)
    return _source("tolerance", ctx, where)


def _rule_required_capabilities(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    items = list(raw or [])
    if not items:
        return FieldProvenance("required_capabilities", CriterionProvenance.LEAST_AUTHORITY, "no capability is required")
    where = ctx.span("required_capabilities")
    cited = ctx.text[where[0]:where[1]]
    missing = [item for item in items if not _phrase_in(str(item).split(".")[-1], cited)]
    if missing:
        raise Ungrounded(f"the cited text does not name the required capabilities {missing}")
    return _source("required_capabilities", ctx, where)


def _rule_assumptions(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    items = list(raw or [])
    if not items:
        return FieldProvenance("assumptions", CriterionProvenance.LEAST_AUTHORITY, "no caller assumption is carried")
    where = ctx.span("assumptions")
    cited = normalized(ctx.text[where[0]:where[1]])
    for item in items:
        if normalized(item.get("statement", "")) not in cited:
            raise Ungrounded(f"the cited text does not state the assumption {item.get('assumption_id')!r}")
    return _source("assumptions", ctx, where)


def _rule_decision(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    where = ctx.span("decision")
    statement = normalized(raw.get("statement", ""))
    if not statement or statement not in normalized(ctx.text[where[0]:where[1]]):
        raise Ungrounded("the cited text does not state the decision this claim serves")
    return _source("decision", ctx, where, "the decision id labels the stated decision")


def _rule_evidence(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    where = ctx.span("evidence")
    proposed = {str(v) for v in raw.get("required_levels", [])}
    in_span = _vocabulary_named(LEVEL_VOCABULARY, ctx.text[where[0]:where[1]])
    in_text = _vocabulary_named(LEVEL_VOCABULARY, ctx.text)
    if in_span != proposed:
        raise Ungrounded(f"the cited text requires {sorted(in_span)}, the proposal {sorted(proposed)}")
    if not in_text <= proposed:
        raise Ungrounded(f"the text also requires {sorted(in_text - proposed)}, which the proposal dropped")
    return _source("evidence", ctx, where)


def _rule_uncertainty(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    proposed = {str(v) for v in raw.get("required_channels", [])}
    whole = ctx.text
    named_anywhere = _vocabulary_named(CHANNEL_VOCABULARY, whole)
    if not named_anywhere <= proposed:
        raise Ungrounded(f"the text requires uncertainty channel(s) {sorted(named_anywhere - proposed)}, which the proposal dropped")
    discrepancy_named = _phrase_in("discrepancy", whole)
    k = raw.get("coverage_factor")
    coverage_named = _phrase_in("coverage factor", whole)
    if not proposed:
        where = ctx.span("uncertainty")
        cited = ctx.text[where[0]:where[1]]
        if not any(_phrase_in(p, cited) for p in UNCERTAINTY_WAIVER_PHRASES):
            raise Ungrounded("demanding no uncertainty is a declaration; the cited text does not make it")
        if discrepancy_named or coverage_named or raw.get("require_supported_discrepancy"):
            raise Ungrounded("the text names uncertainty requirements that a waiver would discard")
        return _source("uncertainty", ctx, where, "an explicit waiver of uncertainty quantification")
    where = ctx.span("uncertainty")
    in_span = _vocabulary_named(CHANNEL_VOCABULARY, ctx.text[where[0]:where[1]])
    if in_span != proposed:
        raise Ungrounded(f"the cited text demands {sorted(in_span)}, the proposal {sorted(proposed)}")
    if k is None:
        if coverage_named:
            raise Ungrounded("the text states a coverage factor the proposal dropped")
    else:
        ground_count(ctx.text, where, float(k), ctx.ledger, "claim.uncertainty.coverage_factor")
    if bool(raw.get("require_supported_discrepancy")) != discrepancy_named:
        raise Ungrounded("whether model-form discrepancy must be supported is not what the text states")
    return _source("uncertainty", ctx, where)


def _rule_discrepancy(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    if raw.get("kind") == "unknown":
        return FieldProvenance("discrepancy", CriterionProvenance.LEAST_AUTHORITY, "model-form discrepancy is UNKNOWN")
    raise Ungrounded("a model-form discrepancy declaration other than UNKNOWN must be policy-bound")


def _rule_input_uncertainty(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    if raw is None:
        return FieldProvenance("input_uncertainty", CriterionProvenance.LEAST_AUTHORITY, "no input distribution is declared")
    where = ctx.span("input_uncertainty")
    for path, leaf in _leaves(raw):
        if isinstance(leaf, Quantity):
            try:
                ground_quantity(ctx.text, where, leaf, ctx.ledger, f"claim.input_uncertainty{path}", spread=True)
            except Ungrounded:
                ground_quantity(ctx.text, where, leaf, ctx.ledger, f"claim.input_uncertainty{path}")
        elif isinstance(leaf, (int, float)) and not isinstance(leaf, bool):
            ground_count(ctx.text, where, float(leaf), ctx.ledger, f"claim.input_uncertainty{path}")
        elif isinstance(leaf, str) and not path.endswith("/path"):
            if not _phrase_in(leaf, ctx.text[where[0]:where[1]]):
                raise Ungrounded(f"the cited text does not state input_uncertainty{path} = {leaf!r}")
    return _source("input_uncertainty", ctx, where)


def _rule_decision_context(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    if raw is None:
        return FieldProvenance(
            "decision_context", CriterionProvenance.LEAST_AUTHORITY,
            "no decision context: no policy floor is added; the claim's own grounded bar applies",
        )
    raise Ungrounded("a decision context assigns consequence and influence; only a deploying policy may bind it")


def _leaves(node: Any, where: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(node, Mapping):
        if "magnitude" in node and "units" in node:
            yield where, Quantity.from_dict(node)
            return
        for key, child in node.items():
            if key == "schema":
                continue
            yield from _leaves(child, f"{where}/{key}")
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _leaves(child, f"{where}/{index}")
    elif node is not None:
        yield where, node


def _input_value(proposal: Mapping[str, Any], path: str) -> Any:
    for section in ("known_inputs", "operating_context"):
        raw = dict(proposal.get(section) or {}).get(path)
        if raw is not None:
            return Quantity.from_dict(raw) if isinstance(raw, Mapping) else raw
    return None


#: One rule per criterion field. Inputs and ``missing_inputs`` are grounded by
#: the adapter itself (an input the text does not state is moved to missing).
FIELD_RULES: Mapping[str, Rule] = {
    "kind": _rule_kind,
    "qoi": _rule_qoi,
    "operator": _rule_operator,
    "target": _rule_target,
    "tolerance": _rule_tolerance,
    "required_capabilities": _rule_required_capabilities,
    "assumptions": _rule_assumptions,
    "decision": _rule_decision,
    "evidence": _rule_evidence,
    "uncertainty": _rule_uncertainty,
    "discrepancy": _rule_discrepancy,
    "input_uncertainty": _rule_input_uncertainty,
    "decision_context": _rule_decision_context,
}

#: Fields the adapter grounds itself rather than through :data:`FIELD_RULES`.
ADAPTER_GROUNDED_FIELDS = frozenset({"known_inputs", "operating_context", "missing_inputs"})


def ground_input(text: str, spans: Mapping[str, Sequence[int]], ledger: TokenLedger, path: str, raw: Any) -> StatedNumber | None:
    """Ground one stated input. Returns the number that stated a quantity, ``None`` for text/flags."""
    where = span_text(text, spans, path)
    if where is None:
        raise Ungrounded("no valid source span cited")
    if isinstance(raw, Mapping):
        try:
            value = Quantity.from_dict(raw)
        except (ScientificCoreError, KeyError, TypeError, ValueError) as exc:
            raise Ungrounded(f"not a readable quantity: {exc}") from exc
        return ground_quantity(text, where, value, ledger, path)
    cited = text[where[0]:where[1]]
    if isinstance(raw, bool):
        if str(raw).lower() not in cited.lower():
            raise Ungrounded("the cited text does not state this flag")
        return None
    if isinstance(raw, int):
        ground_count(text, where, float(raw), ledger, path)
        return None
    if isinstance(raw, str):
        if raw not in cited:
            raise Ungrounded("the cited text does not state this value")
        return None
    raise Ungrounded(f"a {type(raw).__name__} cannot be grounded")


__all__ = [
    "ADAPTER_GROUNDED_FIELDS",
    "ADMISSIBLE_PROVENANCE",
    "CRITERION_SPAN_PREFIX",
    "CriterionProvenance",
    "FIELD_RULES",
    "FieldProvenance",
    "GroundingContext",
    "OPERATOR_PHRASES",
    "TokenLedger",
    "Ungrounded",
    "ground_input",
    "operators_stated",
    "stated_numbers",
]
