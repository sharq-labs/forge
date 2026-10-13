"""Provenance of a language-model claim proposal: which fields may decide a verdict.

A claim's verdict is decided against its criteria -- the quantity, the
comparison, the bound, the tolerance, the evidence bar, the uncertainty demand
and the inputs. A language model may *propose* all of them. It may establish
none of them. This module decides, field by field, whether a proposed value has
an authority other than the model:

``SOURCE_GROUNDED``         the user's text states it, and THIS MODULE read it
                            there. The model only says where to look; what the
                            words mean is read deterministically from the text
                            and compared with the proposal.
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
must have an admissible provenance; a field with no grounding rule here -- one
added to the contract later, for instance -- is AI_PROPOSED by construction.

Reading is deliberately narrow and fail-closed (hostile review F1 and its
re-review). The comparison is read from ONE sentence: exactly one comparison
phrase, no negation outside it, the quantity named before it, and every number
of the quantity's dimension consumed as the bound or the tolerance. A number is
read only when it is written plainly: thousands separators, unicode minus signs,
fractions, exponents written with ``^`` or a multiplication sign, and unit
modifiers (``gauge``, ``peak``, ``rise`` ...) make it unreadable, and an
unreadable number where a criterion is read blocks the criterion. An input is
read only after its own name. Requirement vocabulary is read both ways, and a
requirement word the reader cannot place blocks the field. A waiver of
uncertainty, a capability constraint, a model-form declaration, input
distributions and a decision context are never read from prose: only a policy
binds them. Whatever this module cannot read with certainty is UNGROUNDED --
the user can state it more plainly, or the application can bind it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, Mapping, Sequence

from ...scientific.errors import ScientificCoreError
from ...scientific.ir.constraints import ConstraintOperator
from ...scientific.units.quantity import Quantity, dimensionality

#: Spans for claim criteria are keyed ``claim.<name>``; spans for inputs keep
#: their input path, as they always have.
CRITERION_SPAN_PREFIX = "claim."

#: The criterion span keys a proposal may cite. The comparison (quantity,
#: operator, bound, tolerance) is ONE span: its parts are read from one sentence.
CRITERION_SPANS = frozenset({"comparison", "evidence", "uncertainty", "decision", "assumptions"})


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
# Sentences, words and negation
# ---------------------------------------------------------------------------

#: A sentence ends at ; ! ? a newline, or a period followed by whitespace or the end.
_BREAK = re.compile(r"[;!?\n]|\.(?=\s|$)")
_WORD = re.compile(r"[a-z0-9]+")
_NEGATOR = re.compile(r"(?<![a-z])(?:not|never|no|none|nor|neither|cannot|without|nothing)(?![a-z])|n't")
_STOPWORDS = frozenset({"the", "a", "an", "of", "at", "in", "on", "for", "its", "their", "this", "that"})


def normalized(text: str) -> str:
    """Lower case, ``_`` and ``-`` read as spaces, whitespace collapsed."""
    return " ".join(re.sub(r"[_\-]+", " ", str(text).lower()).split())


def _phrase_in(phrase: str, text: str) -> bool:
    words = normalized(phrase)
    if not words:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(words)}(?![a-z0-9])", normalized(text)) is not None


def clause_of(text: str, where: tuple[int, int]) -> tuple[int, int]:
    """The sentence holding the cited span. A span that crosses a sentence boundary is refused.

    Breaks are found over the whole text (a period is a break only when whitespace or the end
    follows it), so a decimal point or a dotted input path never splits a sentence.
    """
    start, end = where
    breaks = [(m.start(), m.end()) for m in _BREAK.finditer(text)]
    if any(start <= s and e < end for s, e in breaks):
        raise Ungrounded("the cited span crosses a sentence boundary; one statement is read from one sentence")
    left = max((e for s, e in breaks if e <= start), default=0)
    right = min((s for s, e in breaks if e >= end), default=len(text))
    return left, right


def _words(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
    """Words of ``text[start:end]`` in lower case, with absolute positions; ``_``/``-`` split words."""
    low = re.sub(r"[_\-]", " ", text[start:end].lower())
    return [(start + m.start(), start + m.end(), m.group()) for m in _WORD.finditer(low)]


def name_position(text: str, clause: tuple[int, int], name: str, before: int | None = None) -> tuple[int, int] | None:
    """Where ``name``'s words appear in order in the clause, separated by nothing but stopwords."""
    wanted = [w for w in _WORD.findall(normalized(name)) if w]
    if not wanted:
        return None
    words = _words(text, *clause)
    for i, (s, _, w) in enumerate(words):
        if w != wanted[0]:
            continue
        j, k = i, 0
        end = None
        while j < len(words) and k < len(wanted):
            if words[j][2] == wanted[k]:
                end = words[j][1]
                k += 1
                j += 1
            elif k > 0 and words[j][2] in _STOPWORDS:
                j += 1
            else:
                break
        if k == len(wanted) and end is not None and (before is None or end <= before):
            return s, end
    return None


def negated(text: str, clause: tuple[int, int], allowed: Sequence[tuple[int, int]] = ()) -> bool:
    """Whether a negator appears in the clause outside the allowed (already-read) phrases."""
    low = text[clause[0]:clause[1]].lower()
    for match in _NEGATOR.finditer(low):
        s, e = clause[0] + match.start(), clause[0] + match.end()
        if not any(a <= s and e <= b for a, b in allowed):
            return True
    return False


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?")
_SIGNS = "+-"
_UNREADABLE_BEFORE = "/^×*·⋅−–—.,"
_UNREADABLE_AFTER = "/^×*·⋅,"
_UNIT_STOP = ",;:)]}"
#: A word right after a unit that changes what the number means.
UNIT_MODIFIERS = frozenset({
    "gauge", "g", "peak", "pk", "rms", "rise", "drop", "increase", "decrease", "change", "difference", "delta",
    "offset", "ripple", "amplitude", "above", "below", "over", "under", "higher", "lower", "more", "less",
})


@dataclass(frozen=True)
class StatedNumber:
    start: int
    end: int
    magnitude: float
    unit: str | None  # None: no unit follows the number
    readable: bool = True

    @property
    def token(self) -> tuple[int, int]:
        return (self.start, self.end)

    def dimension(self) -> str | None:
        if self.unit is None:
            return None
        return dimensionality(self.unit)


def _unit_candidates(rest: str) -> Iterator[tuple[str, str | None]]:
    """(unit spelling, the word after it) pairs that may follow a number, longest spelling first."""
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
        yield " ".join(words[:n]), (words[n].lower() if n < len(words) else None)


def stated_numbers(text: str, start: int, end: int) -> list[StatedNumber]:
    """Every number written inside ``text[start:end]``, with the unit that follows it, if any.

    A number written in a way this reader could misread is returned with
    ``readable=False``: grouping commas (``1,200``), any sign other than ASCII,
    fractions and exponents built from ``/``, ``^`` or a multiplication sign, a
    number inside an identifier, and a unit followed by a modifier.
    """
    found: list[StatedNumber] = []
    for match in _NUMBER.finditer(text, start, end):
        s, e = match.start(), match.end()
        before = text[s - 1] if s > 0 else " "
        after = text[e] if e < len(text) else " "
        literal = match.group()
        if before.isalpha() or before == "_":
            continue  # part of an identifier ("R1", "stage_2"), not a stated number
        readable = not ("," in literal or before in _UNREADABLE_BEFORE or after in _UNREADABLE_AFTER)
        if before in _SIGNS and s >= 1:
            prior = text[s - 2] if s >= 2 else " "
            if prior.isalpha():
                continue  # a hyphenated identifier ("R-134a")
            if not (prior.isspace() or prior in "([{=:"):
                readable = False  # "10-3": arithmetic or a range, not a signed number
            else:
                s -= 1
        try:
            magnitude = float(text[s:e].replace(",", ""))
        except ValueError:
            continue
        unit: str | None = None
        if readable:
            for candidate, following in _unit_candidates(text[e:end]):
                try:
                    parsed = Quantity.parse(f"{magnitude!r} {candidate}")
                except Exception:  # any refusal means: this spelling is not a unit
                    continue
                if parsed.magnitude != magnitude:
                    continue
                unit = parsed.units
                if following in UNIT_MODIFIERS:
                    readable = False
                break
        found.append(StatedNumber(s, e, magnitude, unit, readable))
    return found


def _equal(stated: StatedNumber, value: Quantity, *, spread: bool) -> bool:
    if not stated.readable:
        return False
    if stated.unit is None:
        if value.dimensionality != dimensionality("dimensionless"):
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


@dataclass
class TokenLedger:
    """Which number in the text grounded which field: one number, one field."""

    used: dict[tuple[int, int], str] = field(default_factory=dict)

    def take(self, number: StatedNumber, path: str, *, allowed_reuse: tuple[int, int] | None = None) -> None:
        holder = self.used.get(number.token)
        if holder is not None and holder != path and number.token != allowed_reuse:
            raise Ungrounded(f"the number that states this value already grounds {holder!r}; one statement grounds one field")
        self.used[number.token] = path


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


# ---------------------------------------------------------------------------
# Comparison phrases
# ---------------------------------------------------------------------------

#: Phrases that state each comparison, matched longest first and never twice.
#: EQUAL is stated only as a band: "within <tolerance> of <value>" or "<value> ± <tolerance>".
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
    ConstraintOperator.EQUAL: ("±", "+/-", "+-", "within"),
}
_BAND_AFTER_VALUE = frozenset({"±", "+/-", "+-"})


def operator_matches(text: str, start: int, end: int) -> list[tuple[int, int, ConstraintOperator, str]]:
    """Every comparison phrase in ``text[start:end]``: longest first, without overlap."""
    low = text.lower()
    phrases = sorted(((p, op) for op, items in OPERATOR_PHRASES.items() for p in items), key=lambda item: -len(item[0]))
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, int, ConstraintOperator, str]] = []
    for phrase, op in phrases:
        pattern = rf"(?<![a-z']){re.escape(phrase)}(?![a-z])" if phrase[0].isalpha() else re.escape(phrase)
        for match in re.compile(pattern).finditer(low, start, end):
            s, e = match.start(), match.end()
            if any(not (e <= a or b <= s) for a, b in taken):
                continue
            taken.append((s, e))
            found.append((s, e, op, phrase))
    return sorted(found)


def operators_stated(span: str) -> set[ConstraintOperator]:
    return {op for _, _, op, _ in operator_matches(span, 0, len(span))}


@dataclass(frozen=True)
class StatedComparison:
    clause: tuple[int, int]
    operator: ConstraintOperator
    operator_at: tuple[int, int]
    target: StatedNumber
    tolerance: StatedNumber | None


def read_comparison(text: str, where: tuple[int, int], qoi_dimension: str) -> StatedComparison:
    """Read ``<quantity> <comparison> <bound> [tolerance]`` from the one sentence the span lies in."""
    clause = clause_of(text, where)
    ops = operator_matches(text, *clause)
    if len(ops) != 1:
        raise Ungrounded(
            f"the sentence states {len(ops)} comparison phrase(s) "
            f"({[p for *_, p in ops]}); exactly one is read"
        )
    o_start, o_end, operator, phrase = ops[0]
    if negated(text, clause, [(o_start, o_end)]):
        raise Ungrounded("the sentence is negated outside its comparison phrase; its meaning is not read")
    numbers = stated_numbers(text, *clause)
    if any(not n.readable for n in numbers):
        raise Ungrounded("the sentence writes a number this reader could misread (grouping, sign, fraction, exponent or modifier)")
    relevant = [
        n for n in numbers
        if (n.dimension() == qoi_dimension) or (n.unit is None and qoi_dimension == dimensionality("dimensionless"))
    ]
    if operator is ConstraintOperator.EQUAL:
        if len(relevant) != 2:
            raise Ungrounded(f"a band states a value and a tolerance of the quantity's dimension; the sentence states {len(relevant)}")
        first, second = relevant
        if phrase in _BAND_AFTER_VALUE:
            if not (first.end <= o_start and o_end <= second.start):
                raise Ungrounded(f"'{phrase}' is read as <value> {phrase} <tolerance>")
            return StatedComparison(clause, operator, (o_start, o_end), first, second)
        if not (o_end <= first.start and re.search(r"(?<![a-z])of(?![a-z])", text[first.end:second.start].lower())):
            raise Ungrounded("'within' is read as within <tolerance> of <value>")
        return StatedComparison(clause, operator, (o_start, o_end), second, first)
    if len(relevant) != 1:
        raise Ungrounded(
            f"a threshold states one bound of the quantity's dimension; the sentence states {len(relevant)}, "
            "and an unused one could be the user's real bound"
        )
    if relevant[0].start < o_end:
        raise Ungrounded("the bound is read after its comparison phrase")
    return StatedComparison(clause, operator, (o_start, o_end), relevant[0], None)


# ---------------------------------------------------------------------------
# Requirement vocabularies
# ---------------------------------------------------------------------------

#: How a sentence names each evidence level. Matched longest first, without overlap.
LEVEL_PHRASES: Mapping[str, tuple[str, ...]] = {
    "dimensionally_valid": ("dimensionally valid", "dimensional validity", "dimensionally consistent", "dimensional consistency"),
    "numerically_converged": ("numerically converged", "numerical convergence", "mesh converged", "mesh convergence",
                              "grid converged", "grid convergence"),
    "analytically_verified": ("analytically verified", "analytical verification", "analytic verification",
                              "verified against an analytical solution", "verified against an analytic solution"),
    "benchmark_validated": ("benchmark validated", "benchmark validation", "benchmark verified", "benchmark verification",
                            "benchmark agreement", "agreement with the benchmark"),
    "cross_solver_validated": ("cross solver validated", "cross solver validation", "cross solver verification",
                               "cross solver agreement", "independent solver agreement"),
    "experimentally_validated": ("experimentally validated", "experimental validation", "validated experimentally",
                                 "validated against measurements", "validated against measurement",
                                 "validated against test data", "validated against experiments"),
}
#: Any of these left after the phrases are read is a requirement this reader cannot place.
LEVEL_STEMS = re.compile(r"(?<![a-z])(?:validat|verif|converg|benchmark|experiment|cross ?solver|analytic|dimensional)[a-z]*")

CHANNEL_PHRASES: Mapping[str, tuple[str, ...]] = {
    "aleatoric": ("aleatoric", "aleatory"),
    "epistemic_parameter": ("epistemic parameter", "parameter uncertainty", "parametric uncertainty", "parameter uncertainties"),
    "model_form": ("model form",),
    "numerical": ("numerical", "discretization error", "discretisation error"),
}
DISCREPANCY_PHRASES = (
    "supported model form discrepancy", "model form discrepancy must be supported",
    "model discrepancy must be supported", "discrepancy must be supported", "supported discrepancy",
)
CHANNEL_STEMS = re.compile(
    r"(?<![a-z])(?:aleator[a-z]*|epistem[a-z]*|parametr[a-z]*|parameters?|model form|numerical|discreti[sz][a-z]*"
    r"|coverage|discrepanc[a-z]*)(?![a-z])"
)
_COVERAGE = re.compile(r"coverage factor(?: of| k)?\s*(?:=\s*)?(\d+(?:\.\d+)?)|(?<![a-z])k\s*=\s*(\d+(?:\.\d+)?)")


def _read_vocabulary(text: str, phrases: Mapping[str, Sequence[str]], start: int = 0, end: int | None = None
                     ) -> tuple[set[str], str]:
    """Members named in ``normalized(text[start:end])`` and what is left once their phrases are removed."""
    window = normalized(text[start:len(text) if end is None else end])
    ordered = sorted(((p, m) for m, ps in phrases.items() for p in ps), key=lambda item: -len(item[0]))
    found: set[str] = set()
    for phrase, member in ordered:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(normalized(phrase))}(?![a-z0-9])")
        if pattern.search(window):
            found.add(member)
            window = pattern.sub(" ", window)
    return found, window


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
    _comparison: StatedComparison | Ungrounded | None = None

    def span(self, name: str) -> tuple[int, int]:
        where = span_text(self.text, self.spans, CRITERION_SPAN_PREFIX + name)
        if where is None:
            raise Ungrounded(f"no valid source span cited for {CRITERION_SPAN_PREFIX + name}")
        return where

    def comparison(self) -> StatedComparison:
        if self._comparison is None:
            try:
                units = str(dict(self.proposal.get("qoi") or {}).get("units"))
                self._comparison = read_comparison(self.text, self.span("comparison"), dimensionality(units))
            except Ungrounded as exc:
                self._comparison = exc
            except (ScientificCoreError, ValueError, TypeError) as exc:
                self._comparison = Ungrounded(f"the quantity's unit is not readable ({exc})")
        if isinstance(self._comparison, Ungrounded):
            raise Ungrounded(str(self._comparison))
        return self._comparison


def _quote(text: str, where: tuple[int, int]) -> str:
    return f"[{where[0]}, {where[1]}) {text[where[0]:where[1]]!r}"


Rule = Callable[[GroundingContext, Any], FieldProvenance]


def _source(name: str, ctx: GroundingContext, where: tuple[int, int], note: str = "") -> FieldProvenance:
    return FieldProvenance(name, CriterionProvenance.SOURCE_GROUNDED, "read from " + _quote(ctx.text, where) + (f"; {note}" if note else ""))


def _rule_qoi(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    stated = ctx.comparison()
    name = str(raw.get("name", ""))
    if name_position(ctx.text, stated.clause, name, before=stated.operator_at[0]) is None:
        raise Ungrounded(f"the comparison sentence does not name the quantity {name!r} before its comparison phrase")
    clause_text = ctx.text[stated.clause[0]:stated.clause[1]]
    for key, value in dict(raw.get("qualifiers") or {}).items():
        if not _phrase_in(str(value), clause_text):
            raise Ungrounded(f"the comparison sentence does not name qualifier {key}={value!r}")
    return _source("qoi", ctx, stated.clause, "its unit's dimension decides which numbers in the sentence are bounds")


def _rule_operator(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    stated = ctx.comparison()
    try:
        proposed = ConstraintOperator(raw)
    except ValueError as exc:
        raise Ungrounded(f"operator {raw!r} is not a comparison") from exc
    if proposed is not stated.operator:
        raise Ungrounded(f"the sentence states {stated.operator.value!r}, the proposal {proposed.value!r}")
    return _source("operator", ctx, stated.operator_at)


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
    stated = ctx.comparison()
    ref = raw.get("input_ref")
    if ref is not None:
        number = ctx.grounded_inputs.get(ref)
        value = _input_value(ctx.proposal, ref)
        if number is None or not isinstance(value, Quantity) or not _equal(stated.target, value, spread=False):
            raise Ungrounded(f"the bound names input {ref!r}, which is not the grounded value the sentence states as the bound")
        ctx.ledger.take(stated.target, "claim.target", allowed_reuse=number.token)
        return FieldProvenance("target", CriterionProvenance.COMPUTED_FROM_GROUNDED,
                               f"the bound is grounded input {ref!r}, stated at {_quote(ctx.text, stated.target.token)}")
    value = Quantity.from_dict(raw["value"])
    if not _equal(stated.target, value, spread=False):
        raise Ungrounded(f"the sentence's bound is {ctx.text[stated.target.start:stated.target.end]!r} "
                         f"{stated.target.unit}, not {value.magnitude!r} {value.units}")
    ctx.ledger.take(stated.target, "claim.target")
    return _source("target", ctx, stated.target.token)


def _rule_tolerance(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    stated = ctx.comparison()
    if raw is None:
        if stated.tolerance is not None:
            raise Ungrounded("the sentence states a tolerance the proposal dropped")
        return FieldProvenance("tolerance", CriterionProvenance.COMPUTED_FROM_GROUNDED,
                               "no tolerance: the sentence states a threshold")
    value = Quantity.from_dict(raw)
    if stated.tolerance is None or not _equal(stated.tolerance, value, spread=True):
        raise Ungrounded(f"the sentence does not state the tolerance {value.magnitude!r} {value.units}")
    ctx.ledger.take(stated.tolerance, "claim.tolerance")
    return _source("tolerance", ctx, stated.tolerance.token)


def _policy_only(name: str, empty_basis: str) -> Rule:
    def rule(ctx: GroundingContext, raw: Any) -> FieldProvenance:
        if raw in (None, [], {}, ()):
            return FieldProvenance(name, CriterionProvenance.LEAST_AUTHORITY, empty_basis)
        raise Ungrounded(f"{name} is never read from prose; only the deploying application's policy may bind it")
    return rule


def _statement_in_clause(ctx: GroundingContext, where: tuple[int, int], statement: str, what: str) -> tuple[int, int]:
    clause = clause_of(ctx.text, where)
    statement = str(statement).strip().rstrip(".!?;:")
    words = normalized(statement).split()
    if len(words) < 3:
        raise Ungrounded(f"{what} is too short to be recognised as a statement ({statement!r})")
    if not _phrase_in(statement, ctx.text[clause[0]:clause[1]]):
        raise Ungrounded(f"the cited sentence does not state {what}")
    return clause


def _rule_assumptions(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    items = list(raw or [])
    if not items:
        return FieldProvenance("assumptions", CriterionProvenance.LEAST_AUTHORITY, "no caller assumption is carried")
    where = ctx.span("assumptions")
    for item in items:
        _statement_in_clause(ctx, where, str(item.get("statement", "")), f"the assumption {item.get('assumption_id')!r}")
    return _source("assumptions", ctx, clause_of(ctx.text, where))


def _rule_decision(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    clause = _statement_in_clause(ctx, ctx.span("decision"), str(raw.get("statement", "")), "the decision this claim serves")
    return _source("decision", ctx, clause, "the decision id labels the stated decision")


def _rule_evidence(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    clause = clause_of(ctx.text, ctx.span("evidence"))
    if negated(ctx.text, clause):
        raise Ungrounded("the evidence sentence is negated; its requirement is not read")
    proposed = {str(v) for v in raw.get("required_levels", [])}
    in_clause, _ = _read_vocabulary(ctx.text, LEVEL_PHRASES, *clause)
    in_text, left = _read_vocabulary(ctx.text, LEVEL_PHRASES)
    if in_clause != proposed:
        raise Ungrounded(f"the evidence sentence requires {sorted(in_clause)}, the proposal {sorted(proposed)}")
    if not in_text <= proposed:
        raise Ungrounded(f"the text also requires {sorted(in_text - proposed)}, which the proposal dropped")
    stray = sorted(set(LEVEL_STEMS.findall(left)))
    if stray:
        raise Ungrounded(f"the text names evidence ({stray}) this reader cannot place; the requirement is not read")
    return _source("evidence", ctx, clause)


def _rule_uncertainty(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    proposed = {str(v) for v in raw.get("required_channels", [])}
    if not proposed:
        raise Ungrounded("demanding no uncertainty quantification is a waiver; only the deploying policy may grant it")
    clause = clause_of(ctx.text, ctx.span("uncertainty"))
    if negated(ctx.text, clause):
        raise Ungrounded("the uncertainty sentence is negated; its demand is not read")
    with_discrepancy = {**CHANNEL_PHRASES, "__discrepancy__": DISCREPANCY_PHRASES}
    in_clause, _ = _read_vocabulary(ctx.text, with_discrepancy, *clause)
    in_text, left = _read_vocabulary(ctx.text, with_discrepancy)
    discrepancy = "__discrepancy__" in in_text
    in_clause.discard("__discrepancy__")
    in_text.discard("__discrepancy__")
    if in_clause != proposed:
        raise Ungrounded(f"the uncertainty sentence demands {sorted(in_clause)}, the proposal {sorted(proposed)}")
    if not in_text <= proposed:
        raise Ungrounded(f"the text also demands {sorted(in_text - proposed)}, which the proposal dropped")
    if bool(raw.get("require_supported_discrepancy")) != discrepancy:
        raise Ungrounded("whether model-form discrepancy must be supported is not what the text states")
    coverage = [(m.start(), m.group(1) or m.group(2)) for m in _COVERAGE.finditer(normalized(ctx.text))]
    left = _COVERAGE.sub(" ", left)
    stray = sorted(set(CHANNEL_STEMS.findall(left)))
    if stray:
        raise Ungrounded(f"the text names uncertainty terms ({stray}) this reader cannot place; the demand is not read")
    k = raw.get("coverage_factor")
    if len(coverage) > 1:
        raise Ungrounded("the text states more than one coverage factor")
    if k is None:
        if coverage:
            raise Ungrounded("the text states a coverage factor the proposal dropped")
    elif not coverage or not math.isclose(float(coverage[0][1]), float(k), rel_tol=0.0, abs_tol=1e-12):
        raise Ungrounded(f"the coverage factor the text states is not {k!r}")
    return _source("uncertainty", ctx, clause)


def _rule_discrepancy(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    if raw.get("kind") == "unknown":
        return FieldProvenance("discrepancy", CriterionProvenance.LEAST_AUTHORITY, "model-form discrepancy is UNKNOWN")
    raise Ungrounded("a model-form discrepancy declaration other than UNKNOWN must be policy-bound")


def _rule_decision_context(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    if raw is None:
        return FieldProvenance(
            "decision_context", CriterionProvenance.LEAST_AUTHORITY,
            "no decision context: NO POLICY FLOOR is applied; only the claim's own grounded bar. A deployment "
            "that needs a risk floor must bind decision_context in its policy",
        )
    raise Ungrounded("a decision context assigns consequence and influence; only a deploying policy may bind it")


def _text_beyond_evidence(text: str, bound: Mapping[str, Any]) -> list[str]:
    named, _ = _read_vocabulary(text, LEVEL_PHRASES)
    return sorted(named - {str(v) for v in bound.get("required_levels", [])})


def _text_beyond_uncertainty(text: str, bound: Mapping[str, Any]) -> list[str]:
    named, _ = _read_vocabulary(text, {**CHANNEL_PHRASES, "supported discrepancy": DISCREPANCY_PHRASES})
    allowed = {str(v) for v in bound.get("required_channels", [])}
    if bound.get("require_supported_discrepancy"):
        allowed.add("supported discrepancy")
    beyond = sorted(named - allowed)
    if _COVERAGE.search(normalized(text)) and bound.get("coverage_factor") is None:
        beyond.append("coverage factor")
    return beyond


#: A policy may bind a requirement; it may not silently discard a stricter one the user wrote.
POLICY_TEXT_CHECKS: Mapping[str, Callable[[str, Mapping[str, Any]], list[str]]] = {
    "evidence": _text_beyond_evidence,
    "uncertainty": _text_beyond_uncertainty,
}


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
    # A capability constraint steers model selection: never from prose.
    "required_capabilities": _policy_only("required_capabilities", "no capability is required"),
    "assumptions": _rule_assumptions,
    "decision": _rule_decision,
    "evidence": _rule_evidence,
    "uncertainty": _rule_uncertainty,
    "discrepancy": _rule_discrepancy,
    # Input distributions are parameter-uncertainty declarations: never from prose.
    "input_uncertainty": _policy_only("input_uncertainty", "no input distribution is declared"),
    "decision_context": _rule_decision_context,
}

#: Fields the adapter grounds itself rather than through :data:`FIELD_RULES`.
ADAPTER_GROUNDED_FIELDS = frozenset({"known_inputs", "operating_context", "missing_inputs"})


def _input_name(path: str) -> str:
    return re.sub(r"\[\d+\]", "", path).split(".")[-1]


def ground_input(text: str, spans: Mapping[str, Sequence[int]], ledger: TokenLedger, path: str, raw: Any) -> StatedNumber | None:
    """Ground one stated input: its own name, then its value, in the sentence its span lies in.

    Returns the number that stated a quantity, ``None`` for text, flags and counts.
    """
    where = span_text(text, spans, path)
    if where is None:
        raise Ungrounded("no valid source span cited")
    clause = clause_of(text, where)
    name = _input_name(path)
    named = name_position(text, clause, name)
    if named is None:
        raise Ungrounded(f"the cited sentence does not name {name.replace('_', ' ')!r}")
    if negated(text, clause):
        raise Ungrounded("the cited sentence is negated; its value is not read")
    if isinstance(raw, Mapping):
        try:
            value = Quantity.from_dict(raw)
        except (ScientificCoreError, KeyError, TypeError, ValueError) as exc:
            raise Ungrounded(f"not a readable quantity: {exc}") from exc
        dimension = value.dimensionality
        after = [n for n in stated_numbers(text, named[1], clause[1])
                 if not n.readable or n.dimension() == dimension
                 or (n.unit is None and dimension == dimensionality("dimensionless"))]
        if not after or not after[0].readable:
            raise Ungrounded(f"no plainly written value of [{dimension}] follows {name!r} in the cited sentence")
        number = after[0]
        if not (where[0] <= number.start and number.end <= where[1]):
            raise Ungrounded("the value read after the input's name is not inside the cited span")
        if not _equal(number, value, spread=False):
            raise Ungrounded(f"the sentence states {text[number.start:number.end]} {number.unit}, not {value.magnitude!r} {value.units}")
        ledger.take(number, path)
        return number
    cited = text[where[0]:where[1]]
    if isinstance(raw, bool):
        if not _phrase_in(str(raw).lower(), cited):
            raise Ungrounded("the cited text does not state this flag")
        return None
    if isinstance(raw, int):
        numbers = [n for n in stated_numbers(text, named[1], clause[1]) if n.unit is None or not n.readable]
        if not numbers or not numbers[0].readable or numbers[0].magnitude != float(raw):
            raise Ungrounded(f"the sentence does not state the count {raw!r} after {name!r}")
        ledger.take(numbers[0], path)
        return None
    if isinstance(raw, str):
        if not _phrase_in(raw, cited):
            raise Ungrounded("the cited text does not state this value as a phrase")
        return None
    raise Ungrounded(f"a {type(raw).__name__} cannot be grounded")


__all__ = [
    "ADAPTER_GROUNDED_FIELDS",
    "ADMISSIBLE_PROVENANCE",
    "CRITERION_SPANS",
    "CRITERION_SPAN_PREFIX",
    "CriterionProvenance",
    "FIELD_RULES",
    "FieldProvenance",
    "GroundingContext",
    "OPERATOR_PHRASES",
    "POLICY_TEXT_CHECKS",
    "StatedComparison",
    "TokenLedger",
    "Ungrounded",
    "clause_of",
    "ground_input",
    "operators_stated",
    "read_comparison",
    "stated_numbers",
]
