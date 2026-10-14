"""Provenance of a language-model claim proposal: which fields may decide a verdict.

A claim's verdict is decided against its criteria -- the quantity, the
comparison, the bound, the tolerance, the evidence bar, the uncertainty demand
and the inputs. A language model may *propose* all of them. It may establish
none of them. This module decides, field by field, whether a proposed value has
an authority other than the model:

``SOURCE_GROUNDED``         the user's text states it in a CONTROLLED SENTENCE
                            that this module parses completely; the model only
                            says which sentence.
``POLICY_BOUND``            the deploying application fixed it. A policy is an
                            argument of the adapter, never part of a proposal.
``COMPUTED_FROM_GROUNDED``  derived deterministically from grounded values
                            (the claim shape from its operator, a bound named
                            by reference to a grounded input).
``LEAST_AUTHORITY``         the value can only make a verdict harder to reach:
                            no assumptions, an UNKNOWN discrepancy, no extra
                            capability constraint.
``AI_PROPOSED``             none of the above. Advisory: shown, never used.

Every field that takes part in a claim's scientific identity
(:data:`~engcore.claims.contract.SCIENTIFIC_FIELDS`) must have an admissible
provenance; a field with no grounding rule here is AI_PROPOSED by construction.

Why a controlled language (hostile review F1, two re-reviews)
-------------------------------------------------------------
Two attempts to read decision criteria out of free English with phrase lists
were each defeated by ordinary sentences: a preposition read as a comparison
("under full load reaches 400 K"), a failure condition read as the requirement
("fails if ... exceeds 400 K"), a line break or an abbreviation that cut a
negation off the clause, a coverage factor taken from an unrelated "k = 0.04",
a requirement worded outside the lexicon silently dropped. A deterministic
reader cannot interpret free prose safely, and an LLM may not interpret it for
the Core. So a criterion is SOURCE_GROUNDED only when its sentence is, in its
ENTIRETY, one of these forms (case-insensitive, whitespace-normalized, one
final period optional)::

    [The] <quantity> [of <element>] must be|stay|remain <comparison> <n> <unit>
    [The] <quantity> [of <element>] must be|stay|remain within <t> <unit> of <v> <unit>
    [The] <quantity> [of <element>] must be|stay|remain <v> <unit> ± <t> <unit>
    The decision requires <level> [, <level>] [and <level>] evidence
    Quantify <channel> [, <channel>] [and <channel>] uncertainty [with coverage factor <k>]
              [, and model form discrepancy must be supported]
    [The] <input name | input path> is <value>

and the text speaks about that quantity, that input, or that kind of
requirement in no other sentence -- so a second statement, a condition or a
retraction elsewhere blocks grounding instead of being ignored. Sentences end
only at ``.``, ``!`` or ``?`` followed by whitespace (never after a known
abbreviation) or at a blank line; a line break inside a sentence is whitespace.
Anything else is UNGROUNDED: the user restates it in the controlled form, or
the deploying application binds it by policy. A waiver of uncertainty, a
capability constraint, a model-form declaration, input distributions and a
decision context are never read from prose.

The reading is CLOSED-WORLD (third review): every sentence of the text must be
accounted for -- read by a rule, stated about a declared input, or stating
exactly what a policy binds. One sentence nothing accounts for ("That limit is
waived during burn-in", "Apply a safety margin of 20 K") makes the claim
UNGROUNDED, because a deterministic reader cannot know it changes nothing. A
policy may bind a comparison, an evidence bar or an uncertainty demand; it may
not replace a different or stricter one the user wrote. A value is written
unambiguously: no number that could be a grouped integer (``1.200``) and no
unit spelling with more than one standard definition (``gallon``, ``ton``).
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

#: Spans for claim criteria are keyed ``claim.<name>``; spans for inputs keep their input path.
CRITERION_SPAN_PREFIX = "claim."

#: The criterion span keys a proposal may cite. The comparison is ONE sentence.
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
# Sentences
# ---------------------------------------------------------------------------

_ABBREVIATIONS = frozenset({"e.g", "i.e", "etc", "vs", "approx", "no", "nos", "fig", "eq", "al", "cf", "ca", "resp",
                            "incl", "excl", "max", "min", "dr", "mr", "mrs", "ms", "st", "vol", "pp", "ref", "sec"})
_END = re.compile(r"[.!?](?=\s|$)|\n\s*\n")
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int          # exclusive; excludes the terminal punctuation
    text: str         # whitespace-normalized, terminal punctuation removed

    def contains(self, where: tuple[int, int]) -> bool:
        return self.start <= where[0] and where[1] <= self.end + 1


def sentences(text: str) -> list[Sentence]:
    """The text's sentences. A period ends one only before whitespace and not after a known abbreviation."""
    out: list[Sentence] = []
    start = 0
    for match in _END.finditer(text):
        if match.group().startswith("."):
            before = re.search(r"([A-Za-z.]+)$", text[start:match.start()])
            word = before.group(1).lower().strip(".") if before else ""
            if word in _ABBREVIATIONS:
                continue
        end = match.start()
        body = " ".join(text[start:end].split())
        if body:
            out.append(Sentence(start, end, body))
        start = match.end()
    body = " ".join(text[start:].split())
    if body:
        out.append(Sentence(start, len(text), body))
    return out


def sentence_at(text: str, where: tuple[int, int]) -> Sentence:
    """The one sentence a cited span lies in; a span across a sentence boundary is refused."""
    for sentence in sentences(text):
        if sentence.contains(where):
            return sentence
    raise Ungrounded("the cited span is not inside one sentence; one statement is read from one sentence")


def clause_of(text: str, where: tuple[int, int]) -> tuple[int, int]:
    sentence = sentence_at(text, where)
    return sentence.start, sentence.end


def normalized(text: str) -> str:
    """Lower case, ``_`` and ``-`` read as spaces, whitespace collapsed."""
    return " ".join(re.sub(r"[_\-]+", " ", str(text).lower()).split())


def _content_words(text: str) -> list[str]:
    """Words, with articles and possessive marks dropped."""
    words = _WORD.findall(normalized(text).replace("'s ", " ").replace("’s ", " "))
    return [w for w in words if w not in ("the", "a", "an")]


def _phrase_in(phrase: str, text: str) -> bool:
    words = " ".join(_content_words(phrase))
    return bool(words) and re.search(rf"(?<![a-z0-9]){re.escape(words)}(?![a-z0-9])", " ".join(_content_words(text))) is not None


def _named_elsewhere(text: str, phrase: str, here: Sentence) -> list[str]:
    return [s.text for s in sentences(text) if s.start != here.start and _phrase_in(phrase, s.text)]


#: Words that make a sentence conditional, negated, counterfactual or contrastive.
_BLOCKING = re.compile(
    r"(?<![a-z])(?:if|when|whenever|unless|until|were|would|could|should|might|otherwise|not|never|no|none|nor|"
    r"neither|cannot|without|except|instead|rather|unlike|replacing|fail\w*|reject\w*|avoid\w*|prevent\w*|"
    r"prohibit\w*|forbid\w*)(?![a-z])|n't"
)


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

_NUM = r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
_GROUPING_LOOKALIKE = re.compile(r"[+-]?[1-9]\d{0,2}\.\d{3}")
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
        return None if self.unit is None else dimensionality(self.unit)


def _unit_candidates(rest: str) -> Iterator[tuple[str, str | None]]:
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
        following = words[n].lower().strip("()[]") if n < len(words) else None
        yield " ".join(words[:n]), following


def stated_numbers(text: str, start: int, end: int) -> list[StatedNumber]:
    """Every number written inside ``text[start:end]``, with the unit that follows it, if any.

    A number this reader could misread is returned with ``readable=False``:
    grouping commas, any sign other than ASCII, fractions and exponents built
    from ``/``, ``^`` or a multiplication sign, ranges, a malformed literal, and a
    unit followed by a modifier. Identifiers (``R1``, ``R-134a``) are skipped.
    """
    found: list[StatedNumber] = []
    for match in _NUMBER.finditer(text, start, end):
        s, e = match.start(), match.end()
        before = text[s - 1] if s > 0 else " "
        after = text[e] if e < len(text) else " "
        literal = match.group()
        if before.isalpha() or before == "_":
            continue
        readable = not ("," in literal or literal.count(".") > 1 or before in _UNREADABLE_BEFORE or after in _UNREADABLE_AFTER)
        if before in _SIGNS and s >= 1:
            prior = text[s - 2] if s >= 2 else " "
            if prior.isalpha():
                continue
            if not (prior.isspace() or prior in "([{=:"):
                readable = False
            else:
                s -= 1
        try:
            magnitude = float(text[s:e])
        except ValueError:
            found.append(StatedNumber(s, e, float("nan"), None, False))
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


#: Unit spellings with more than one standard definition (short ton / tonne / long ton, US / imperial
#: volumes, thermochemical / IT calorie and BTU, mechanical / metric horsepower, thou / milliradian ...).
#: The parser would pick one silently; a criterion or an input written with one of them is not read.
AMBIGUOUS_UNIT_WORDS = frozenset({
    "ton", "tons", "gallon", "gallons", "gal", "quart", "quarts", "qt", "pint", "pints", "pt", "cup", "cups",
    "ounce", "ounces", "oz", "floz", "fluid", "mil", "mils", "calorie", "calories", "cal", "kcal", "kilocalorie",
    "kilocalories", "btu", "btus", "mmbtu", "hp", "horsepower", "bhp", "barrel", "barrels", "bbl", "cwt",
    "hundredweight", "therm", "therms", "bushel", "bushels",
    # pound: mass or force (lbm / lbf); mile: statute or nautical
    "pound", "pounds", "lb", "lbs", "mile", "miles",
})


def _quantity(number: str, unit: str) -> Quantity:
    """``<number> <unit>`` read with the Core's own parser, or Ungrounded.

    A number that could be a decimal or a grouped integer (``1.200``) and a unit spelling with more
    than one standard definition are refused: a value is written unambiguously or it is not read.
    """
    if _GROUPING_LOOKALIKE.fullmatch(number):
        raise Ungrounded(f"{number!r} could be a decimal or a grouped integer; a value is written unambiguously")
    ambiguous = sorted(set(re.findall(r"[a-z]+", unit.lower())) & AMBIGUOUS_UNIT_WORDS)
    if ambiguous:
        raise Ungrounded(f"the unit {unit.strip()!r} spells {ambiguous}, which has more than one standard definition")
    try:
        return Quantity.parse(f"{number} {unit.strip()}")
    except Exception as exc:
        raise Ungrounded(f"{number} {unit!r} is not a number with a unit ({exc})") from exc


def _equal(written: Quantity, value: Quantity, *, spread: bool) -> bool:
    if not written.is_compatible_with(value):
        return False
    try:
        mine = written.magnitude_as_spread_in(value.units) if spread else written.magnitude_in(value.units)
    except ScientificCoreError:
        return False
    return math.isclose(mine, value.magnitude, rel_tol=1e-9, abs_tol=1e-12)


@dataclass
class TokenLedger:
    """Which statement grounded which field: one statement, one field."""

    used: dict[tuple[int, int], str] = field(default_factory=dict)

    def take(self, token: tuple[int, int], path: str, *, allowed_reuse: tuple[int, int] | None = None) -> None:
        holder = self.used.get(token)
        if holder is not None and holder != path and token != allowed_reuse:
            raise Ungrounded(f"the statement that states this value already grounds {holder!r}; one statement grounds one field")
        self.used[token] = path


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
# The comparison sentence
# ---------------------------------------------------------------------------

#: The comparison phrases of the controlled threshold form.
THRESHOLD_PHRASES: Mapping[str, ConstraintOperator] = {
    "below": ConstraintOperator.LESS_THAN, "under": ConstraintOperator.LESS_THAN,
    "less than": ConstraintOperator.LESS_THAN, "lower than": ConstraintOperator.LESS_THAN,
    "at most": ConstraintOperator.LESS_EQUAL, "no more than": ConstraintOperator.LESS_EQUAL,
    "not more than": ConstraintOperator.LESS_EQUAL, "no greater than": ConstraintOperator.LESS_EQUAL,
    "not greater than": ConstraintOperator.LESS_EQUAL, "no higher than": ConstraintOperator.LESS_EQUAL,
    "above": ConstraintOperator.GREATER_THAN, "over": ConstraintOperator.GREATER_THAN,
    "more than": ConstraintOperator.GREATER_THAN, "greater than": ConstraintOperator.GREATER_THAN,
    "higher than": ConstraintOperator.GREATER_THAN,
    "at least": ConstraintOperator.GREATER_EQUAL, "no less than": ConstraintOperator.GREATER_EQUAL,
    "not less than": ConstraintOperator.GREATER_EQUAL, "no lower than": ConstraintOperator.GREATER_EQUAL,
}

#: Kept for callers and tests: every phrase of the controlled comparison forms, by operator.
OPERATOR_PHRASES: Mapping[ConstraintOperator, tuple[str, ...]] = {
    op: tuple(p for p, o in THRESHOLD_PHRASES.items() if o is op) for op in (
        ConstraintOperator.LESS_THAN, ConstraintOperator.LESS_EQUAL,
        ConstraintOperator.GREATER_THAN, ConstraintOperator.GREATER_EQUAL)
} | {ConstraintOperator.EQUAL: ("within", "±", "+/-")}

_OPS = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in sorted(THRESHOLD_PHRASES, key=len, reverse=True))
_SUBJECT = r"(?:the\s+)?(?P<subject>.+?)\s+must\s+(?:be|stay|remain)\s+"
_THRESHOLD = re.compile(rf"{_SUBJECT}(?P<op>{_OPS})\s+(?P<v>{_NUM})\s*(?P<vu>\S.*)", re.IGNORECASE)
_WITHIN = re.compile(rf"{_SUBJECT}within\s+(?P<t>{_NUM})\s*(?P<tu>\S.*?)\s+of\s+(?P<v>{_NUM})\s*(?P<vu>\S.*)", re.IGNORECASE)
_PLUSMINUS = re.compile(rf"{_SUBJECT}(?P<v>{_NUM})\s*(?P<vu>\S.*?)\s*(?:±|\+/-|\+-)\s*(?P<t>{_NUM})\s*(?P<tu>\S.*)",
                        re.IGNORECASE)
#: A threshold whose bound is another stated input, named rather than copied: "... must be below the yield stress".
_THRESHOLD_REF = re.compile(rf"{_SUBJECT}(?P<op>{_OPS})\s+(?:the\s+)?(?P<ref>[A-Za-z][A-Za-z ]*)", re.IGNORECASE)


def operators_stated(span: str) -> set[ConstraintOperator]:
    """The comparisons the controlled phrases in ``span`` name (longest phrase first, never twice)."""
    low = " ".join(str(span).lower().split())
    found: set[ConstraintOperator] = set()
    for phrase in sorted(THRESHOLD_PHRASES, key=len, reverse=True):
        pattern = rf"(?<![a-z]){re.escape(phrase)}(?![a-z])"
        if re.search(pattern, low):
            found.add(THRESHOLD_PHRASES[phrase])
            low = re.sub(pattern, " ", low)
    if re.search(r"(?<![a-z])within(?![a-z])|±|\+/-", low):
        found.add(ConstraintOperator.EQUAL)
    return found


@dataclass(frozen=True)
class StatedComparison:
    sentence: Sentence
    subject: str
    operator: ConstraintOperator
    target: Quantity | None
    tolerance: Quantity | None
    #: the input the bound names, when the sentence names it instead of writing a number
    target_ref: str | None = None

    @property
    def clause(self) -> tuple[int, int]:
        return self.sentence.start, self.sentence.end

    @property
    def token(self) -> tuple[int, int]:
        return self.clause


def read_comparison(text: str, where: tuple[int, int]) -> StatedComparison:
    """Parse the cited sentence as one of the controlled comparison forms, completely, or refuse."""
    sentence = sentence_at(text, where)
    body = sentence.text
    for pattern, kind in ((_WITHIN, "within"), (_PLUSMINUS, "pm"), (_THRESHOLD, "threshold")):
        match = pattern.fullmatch(body)
        if match is None:
            continue
        target = _quantity(match["v"], match["vu"])
        if kind == "threshold":
            operator = THRESHOLD_PHRASES[" ".join(match["op"].lower().split())]
            return StatedComparison(sentence, match["subject"], operator, target, None)
        tolerance = _quantity(match["t"], match["tu"])
        return StatedComparison(sentence, match["subject"], ConstraintOperator.EQUAL, target, tolerance)
    match = _THRESHOLD_REF.fullmatch(body)
    if match is not None:
        operator = THRESHOLD_PHRASES[" ".join(match["op"].lower().split())]
        return StatedComparison(sentence, match["subject"], operator, None, None, " ".join(_content_words(match["ref"])))
    raise Ungrounded(
        f"the cited sentence {body!r} is not a controlled comparison: write "
        "'<quantity> must be <below|at most|above|at least> <value> <unit>', "
        "'<quantity> must be within <tolerance> of <value>' or '<quantity> must be <value> ± <tolerance>'"
    )


# ---------------------------------------------------------------------------
# Requirement sentences
# ---------------------------------------------------------------------------

_LIST_SPLIT = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+", re.IGNORECASE)
_EVIDENCE = re.compile(r"the\s+decision\s+requires\s+(?P<levels>.+?)\s+evidence", re.IGNORECASE)
_UNCERTAINTY = re.compile(
    rf"quantify\s+(?P<ch>.+?)\s+uncertainty(?:\s+with\s+coverage\s+factor\s+(?P<k>{_NUM}))?"
    r"(?P<disc>,?\s+and\s+(?:the\s+)?model[\s-]+form\s+discrepancy\s+must\s+be\s+supported)?",
    re.IGNORECASE,
)

#: Canonical names in the controlled requirement forms: the vocabulary's own values, read with spaces.
LEVEL_NAMES = ("dimensionally_valid", "numerically_converged", "analytically_verified", "benchmark_validated",
               "cross_solver_validated", "experimentally_validated")
CHANNEL_NAMES = ("aleatoric", "epistemic_parameter", "model_form", "numerical")

#: Words that speak about an evidence requirement. Outside the one controlled sentence they block it.
LEVEL_STEMS = re.compile(
    r"(?<![a-z])(?:validat|verif|converg|benchmark|experiment|empiric|measur|labs?\b|laborator|calibrat|correlat|"
    r"agree|match|tests?\b|tested|testing|cross ?solver|analytic|dimensional)"
)
#: Words that speak about an uncertainty demand. Outside the one controlled sentence they block it.
CHANNEL_STEMS = re.compile(
    r"(?<![a-z])(?:aleator|epistem|parametr|parameters?\b|model[\s-]+form|numerical\b|discreti[sz]|coverage|"
    r"discrepanc|uncertain|variab|scatter|noise|errors?\b)|(?<![a-z])k\s*="
)


def _names_in(listed: str, vocabulary: Sequence[str]) -> set[str] | None:
    """The vocabulary members a controlled list names, or None when any item is not a member."""
    canonical = {normalized(member): member for member in vocabulary}
    found: set[str] = set()
    for item in _LIST_SPLIT.split(listed.strip()):
        member = canonical.get(normalized(item))
        if member is None:
            return None
        found.add(member)
    return found


def read_evidence(body: str) -> set[str] | None:
    match = _EVIDENCE.fullmatch(body)
    return None if match is None else _names_in(match["levels"], LEVEL_NAMES)


def read_uncertainty(body: str) -> tuple[set[str], float | None, bool] | None:
    match = _UNCERTAINTY.fullmatch(body)
    if match is None:
        return None
    channels = _names_in(match["ch"], CHANNEL_NAMES)
    if channels is None:
        return None
    k = None
    if match["k"] is not None:
        if _GROUPING_LOOKALIKE.fullmatch(match["k"]):
            return None
        k = float(match["k"])
    return channels, k, match["disc"] is not None


def _other_mentions(text: str, stems: re.Pattern, here: Sentence | None) -> list[str]:
    return [s.text for s in sentences(text) if (here is None or s.start != here.start) and stems.search(normalized(s.text))]


# ---------------------------------------------------------------------------
# Per-field grounding rules
# ---------------------------------------------------------------------------


@dataclass
class GroundingContext:
    text: str
    spans: Mapping[str, Sequence[int]]
    ledger: TokenLedger
    proposal: Mapping[str, Any]
    #: input path -> the sentence that grounded it (quantity inputs only)
    grounded_inputs: dict[str, Sentence | None]
    #: start offsets of the sentences a rule read; every sentence of the text must end up here (closed world)
    consumed: set[int] = field(default_factory=set)
    _comparison: StatedComparison | Ungrounded | None = None

    def span(self, name: str) -> tuple[int, int]:
        where = span_text(self.text, self.spans, CRITERION_SPAN_PREFIX + name)
        if where is None:
            raise Ungrounded(f"no valid source span cited for {CRITERION_SPAN_PREFIX + name}")
        return where

    def comparison(self) -> StatedComparison:
        if self._comparison is None:
            try:
                self._comparison = read_comparison(self.text, self.span("comparison"))
            except Ungrounded as exc:
                self._comparison = exc
        if isinstance(self._comparison, Ungrounded):
            raise Ungrounded(str(self._comparison))
        return self._comparison


def _quote(sentence: Sentence) -> str:
    return f"[{sentence.start}, {sentence.end}) {sentence.text!r}"


Rule = Callable[[GroundingContext, Any], FieldProvenance]


def _source(name: str, sentence: Sentence, note: str = "") -> FieldProvenance:
    return FieldProvenance(name, CriterionProvenance.SOURCE_GROUNDED, "read from " + _quote(sentence) + (f"; {note}" if note else ""))


def _read(ctx: GroundingContext, name: str, sentence: Sentence, note: str = "") -> FieldProvenance:
    """``name`` was read from ``sentence``; the sentence is consumed."""
    ctx.consumed.add(sentence.start)
    return _source(name, sentence, note)


def _rule_qoi(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    stated = ctx.comparison()
    name = str(raw.get("name", "")).replace("_", " ")
    subject = _content_words(stated.subject)
    wanted = _content_words(name)
    qualifiers = dict(raw.get("qualifiers") or {})
    if len(qualifiers) > 1:
        raise Ungrounded("a quantity with more than one qualifier is not read from prose")
    if qualifiers:
        (key, value), = qualifiers.items()
        wanted = wanted + ["of"] + _content_words(str(value))
    if subject != wanted:
        raise Ungrounded(f"the comparison's subject is {stated.subject!r}, not the quantity {' '.join(wanted)!r}")
    elsewhere = _named_elsewhere(ctx.text, name, stated.sentence)
    if elsewhere:
        raise Ungrounded(f"the text speaks about {name!r} in another sentence too ({elsewhere[0]!r}); one statement is read")
    return _read(ctx, "qoi", stated.sentence)


def _rule_operator(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    stated = ctx.comparison()
    try:
        proposed = ConstraintOperator(raw)
    except ValueError as exc:
        raise Ungrounded(f"operator {raw!r} is not a comparison") from exc
    if proposed is not stated.operator:
        raise Ungrounded(f"the sentence states {stated.operator.value!r}, the proposal {proposed.value!r}")
    return _read(ctx, "operator", stated.sentence)


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
        source = ctx.grounded_inputs.get(ref)
        if source is None or not isinstance(_input_value(ctx.proposal, ref), Quantity):
            raise Ungrounded(f"the bound names input {ref!r}, which the text does not state as a quantity")
        if stated.target_ref != " ".join(_content_words(_input_name(ref))):
            raise Ungrounded(f"the comparison names {stated.target_ref!r} as its bound, not the input {ref!r}")
        ctx.ledger.take(stated.token, "claim.target")
        ctx.consumed.add(stated.sentence.start)
        return FieldProvenance("target", CriterionProvenance.COMPUTED_FROM_GROUNDED,
                               f"the bound is grounded input {ref!r}, named by " + _quote(stated.sentence))
    if stated.target is None:
        raise Ungrounded(f"the comparison names {stated.target_ref!r} as its bound, not a value")
    value = Quantity.from_dict(raw["value"])
    if not _equal(stated.target, value, spread=False):
        raise Ungrounded(f"the sentence's bound is {stated.target.magnitude!r} {stated.target.units}, "
                         f"not {value.magnitude!r} {value.units}")
    ctx.ledger.take(stated.token, "claim.target")
    return _read(ctx, "target", stated.sentence)


def _rule_tolerance(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    stated = ctx.comparison()
    if raw is None:
        if stated.tolerance is not None:
            raise Ungrounded("the sentence states a tolerance the proposal dropped")
        return FieldProvenance("tolerance", CriterionProvenance.COMPUTED_FROM_GROUNDED, "no tolerance: the sentence states a threshold")
    value = Quantity.from_dict(raw)
    if stated.tolerance is None or not _equal(stated.tolerance, value, spread=True):
        raise Ungrounded(f"the sentence does not state the tolerance {value.magnitude!r} {value.units}")
    return _read(ctx, "tolerance", stated.sentence)


def _policy_only(name: str, empty_basis: str) -> Rule:
    def rule(ctx: GroundingContext, raw: Any) -> FieldProvenance:
        if raw in (None, [], {}, ()):
            return FieldProvenance(name, CriterionProvenance.LEAST_AUTHORITY, empty_basis)
        raise Ungrounded(f"{name} is never read from prose; only the deploying application's policy may bind it")
    return rule


_DECISION_PREFIXES = ("it is for this decision:", "decision:", "the decision is:", "for the decision:")
_ASSUMPTION_PREFIXES = ("assume", "assumption:", "we assume")


def _statement_sentence(ctx: GroundingContext, where: tuple[int, int], statement: str, prefixes: Sequence[str],
                        what: str) -> Sentence:
    sentence = sentence_at(ctx.text, where)
    wanted = normalized(str(statement).strip().rstrip(".!?;:"))
    if len(wanted.split()) < 3:
        raise Ungrounded(f"{what} is too short to be recognised as a statement ({statement!r})")
    body = normalized(sentence.text)
    options = {wanted} | {f"{normalized(p)} {wanted}" for p in prefixes}
    if body not in options:
        raise Ungrounded(f"the cited sentence is not exactly {what} ({sentence.text!r})")
    return sentence


def _rule_assumptions(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    items = list(raw or [])
    if not items:
        return FieldProvenance("assumptions", CriterionProvenance.LEAST_AUTHORITY, "no caller assumption is carried")
    if len(items) > 1:
        raise Ungrounded("more than one assumption is not read from one cited sentence; a policy may bind them")
    sentence = _statement_sentence(ctx, ctx.span("assumptions"), str(items[0].get("statement", "")), _ASSUMPTION_PREFIXES,
                                   f"the assumption {items[0].get('assumption_id')!r}")
    return _read(ctx, "assumptions", sentence)


def _rule_decision(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    sentence = _statement_sentence(ctx, ctx.span("decision"), str(raw.get("statement", "")), _DECISION_PREFIXES,
                                   "the decision this claim serves")
    return _read(ctx, "decision", sentence, "the decision id labels the stated decision")


def _rule_evidence(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    sentence = sentence_at(ctx.text, ctx.span("evidence"))
    stated = read_evidence(sentence.text)
    if stated is None:
        raise Ungrounded(f"the cited sentence {sentence.text!r} is not 'The decision requires <level> [and <level>] evidence' "
                         f"with levels named as {list(LEVEL_NAMES)}")
    proposed = {str(v) for v in raw.get("required_levels", [])}
    if stated != proposed:
        raise Ungrounded(f"the evidence sentence requires {sorted(stated)}, the proposal {sorted(proposed)}")
    elsewhere = _other_mentions(ctx.text, LEVEL_STEMS, sentence)
    if elsewhere:
        raise Ungrounded(f"the text speaks about evidence in another sentence too ({elsewhere[0]!r}); one statement is read")
    return _read(ctx, "evidence", sentence)


def _rule_uncertainty(ctx: GroundingContext, raw: Any) -> FieldProvenance:
    proposed = {str(v) for v in raw.get("required_channels", [])}
    if not proposed:
        raise Ungrounded("demanding no uncertainty quantification is a waiver; only the deploying policy may grant it")
    sentence = sentence_at(ctx.text, ctx.span("uncertainty"))
    stated = read_uncertainty(sentence.text)
    if stated is None:
        raise Ungrounded(f"the cited sentence {sentence.text!r} is not 'Quantify <channel> [and <channel>] uncertainty "
                         f"[with coverage factor <k>]' with channels named as {list(CHANNEL_NAMES)}")
    channels, k, discrepancy = stated
    if channels != proposed:
        raise Ungrounded(f"the uncertainty sentence demands {sorted(channels)}, the proposal {sorted(proposed)}")
    proposed_k = raw.get("coverage_factor")
    if (k is None) != (proposed_k is None) or (k is not None and not math.isclose(k, float(proposed_k), rel_tol=0.0, abs_tol=1e-12)):
        raise Ungrounded(f"the sentence states coverage factor {k!r}, the proposal {proposed_k!r}")
    if bool(raw.get("require_supported_discrepancy")) != discrepancy:
        raise Ungrounded("whether model-form discrepancy must be supported is not what the sentence states")
    elsewhere = _other_mentions(ctx.text, CHANNEL_STEMS, sentence)
    if elsewhere:
        raise Ungrounded(f"the text speaks about uncertainty in another sentence too ({elsewhere[0]!r}); one statement is read")
    return _read(ctx, "uncertainty", sentence)


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


# ---------------------------------------------------------------------------
# Policy-bound requirements may not silently drop a stricter stated one
# ---------------------------------------------------------------------------


def _text_beyond_evidence(text: str, bound: Mapping[str, Any]) -> list[str]:
    allowed = {str(v) for v in bound.get("required_levels", [])}
    beyond: list[str] = []
    for sentence in sentences(text):
        if not LEVEL_STEMS.search(normalized(sentence.text)):
            continue
        stated = read_evidence(sentence.text)
        if stated is None:
            beyond.append(f"an evidence statement this reader cannot read: {sentence.text!r}")
        else:
            beyond.extend(sorted(stated - allowed))
    return beyond


def _text_beyond_uncertainty(text: str, bound: Mapping[str, Any]) -> list[str]:
    allowed = {str(v) for v in bound.get("required_channels", [])}
    policy_k = bound.get("coverage_factor")
    beyond: list[str] = []
    for sentence in sentences(text):
        if not CHANNEL_STEMS.search(normalized(sentence.text)):
            continue
        stated = read_uncertainty(sentence.text)
        if stated is None:
            beyond.append(f"an uncertainty statement this reader cannot read: {sentence.text!r}")
            continue
        channels, k, discrepancy = stated
        beyond.extend(sorted(channels - allowed))
        if k is not None and (policy_k is None or float(policy_k) < k):
            beyond.append(f"coverage factor {k!r} (the policy binds {policy_k!r})")
        if discrepancy and not bound.get("require_supported_discrepancy"):
            beyond.append("supported model-form discrepancy")
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


#: One rule per criterion field. Inputs and ``missing_inputs`` are grounded by the adapter itself.
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


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

_INPUT = re.compile(r"(?P<subject>.+?)\s+(?:is|=|equals)\s+(?P<value>.+)", re.IGNORECASE)
#: A text input's value: one token, never a clause.
_TEXT_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+\-/]*")
#: An input identifier written as one token: a dotted path or a snake_case name, never prose.
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:(?:_|\.|\[\d+\]\.?)[A-Za-z0-9]+)+")


def _input_name(path: str) -> str:
    return re.sub(r"\[\d+\]", "", path).split(".")[-1].replace("_", " ")


def _input_subjects(path: str) -> tuple[list[str], list[str]]:
    """The two exact ways a sentence may name an input: its own name, or its whole path."""
    return _content_words(_input_name(path)), _content_words(path)


def _input_named_elsewhere(text: str, path: str, subject: list[str], here: Sentence) -> list[str]:
    """Other sentences that speak about this input (hostile review, third pass A1).

    Any sentence that names the input blocks it -- a second value, a qualifier, a change over time --
    except (a) another input's own statement whose subject is a DIFFERENT input identifier written as one
    token (``stages[1].body.initial_temperature``, ``ratings.rated_power_temperature``) -- when that
    identifier ends with this input's name, only if this sentence names its input by whole path too --
    and (b) a controlled comparison that names the input as its bound.
    """
    name, _ = _input_subjects(path)
    phrase = " ".join(name)
    blocking: list[str] = []
    for other in sentences(text):
        if other.start == here.start or not _phrase_in(phrase, other.text):
            continue
        match = _INPUT.fullmatch(other.text)
        if match is not None and _IDENTIFIER.fullmatch(re.sub(r"(?i)^the\s+", "", match["subject"].strip())):
            words = _content_words(match["subject"])
            if words != subject and (words[-len(name):] != name or len(subject) > len(name)):
                continue
        try:
            stated = read_comparison(text, (other.start, other.end))
        except Ungrounded:
            stated = None
        if stated is not None and stated.target_ref == phrase and phrase not in " ".join(_content_words(stated.subject)):
            continue
        blocking.append(other.text)
    return blocking


def ground_input(text: str, spans: Mapping[str, Sequence[int]], ledger: TokenLedger, path: str, raw: Any,
                 consumed: set[int] | None = None) -> Sentence | None:
    """Ground one input from a sentence that is exactly ``[the] <input name | input path> is <value>``.

    The subject is the input's name or its whole path, nothing more ("the minimum ambient temperature"
    is not "ambient temperature"), and no other sentence may speak about the input. Returns the
    sentence that stated a quantity, ``None`` for text, flags and counts; on success the sentence's
    start is added to ``consumed``.
    """
    where = span_text(text, spans, path)
    if where is None:
        raise Ungrounded("no valid source span cited")
    sentence = sentence_at(text, where)
    match = _INPUT.fullmatch(sentence.text)
    name = _input_name(path)
    if match is None:
        raise Ungrounded(f"the cited sentence is not '<{name}> is <value>' ({sentence.text!r})")
    if _BLOCKING.search(normalized(sentence.text)):
        raise Ungrounded("the cited sentence is conditional, negated or contrastive; its value is not read")
    subject = _content_words(match["subject"])
    if not subject or subject not in _input_subjects(path):
        raise Ungrounded(f"the cited sentence states {match['subject']!r}, not {name!r}")
    elsewhere = _input_named_elsewhere(text, path, subject, sentence)
    if elsewhere:
        raise Ungrounded(f"the text speaks about {name!r} in another sentence too ({elsewhere[0]!r}); one statement is read")
    value_text = match["value"].strip()
    ledger.take((sentence.start, sentence.end), path)
    stated = _input_value_matches(value_text, raw, sentence)
    if consumed is not None:
        consumed.add(sentence.start)
    return stated


def _input_value_matches(value_text: str, raw: Any, sentence: Sentence) -> Sentence | None:
    if isinstance(raw, Mapping):
        try:
            value = Quantity.from_dict(raw)
        except (ScientificCoreError, KeyError, TypeError, ValueError) as exc:
            raise Ungrounded(f"not a readable quantity: {exc}") from exc
        number = re.fullmatch(rf"(?P<n>{_NUM})\s*(?P<u>\S.*)", value_text)
        if number is None:
            raise Ungrounded(f"{value_text!r} is not a number with a unit")
        written = _quantity(number["n"], number["u"])
        if not _equal(written, value, spread=False):
            raise Ungrounded(f"the sentence states {value_text!r}, not {value.magnitude!r} {value.units}")
        return sentence
    if isinstance(raw, bool):
        if value_text.lower() != str(raw).lower():
            raise Ungrounded(f"the sentence states {value_text!r}, not {raw!r}")
        return None
    if isinstance(raw, int):
        if not re.fullmatch(r"[+-]?\d+", value_text) or int(value_text) != raw:
            raise Ungrounded(f"the sentence states {value_text!r}, not the count {raw!r}")
        return None
    if isinstance(raw, str):
        # Sixth review: a text value is ONE token (an identifier or a category word). "A123 and that limit is
        # waived during burn-in" copied faithfully into an identifier would otherwise read the whole clause.
        if not _TEXT_VALUE.fullmatch(value_text):
            raise Ungrounded(f"{value_text!r} is not a single identifier or category word; a text input is one token")
        if normalized(value_text) != normalized(raw):
            raise Ungrounded(f"the sentence states {value_text!r}, not {raw!r}")
        return None
    raise Ungrounded(f"a {type(raw).__name__} cannot be grounded")


# ---------------------------------------------------------------------------
# Closed world: a policy-bound field consumes only the sentences that agree with it,
# and every sentence of the text must be consumed by something (third review A2, A5)
# ---------------------------------------------------------------------------

#: The comparison fields a policy may bind. A controlled comparison the user wrote must agree with each.
COMPARISON_FIELDS = ("qoi", "operator", "target", "tolerance")


def _comparison_disagrees(stated: StatedComparison, bound: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    try:
        if "qoi" in bound:
            qoi = dict(bound["qoi"])
            wanted = _content_words(str(qoi.get("name", "")).replace("_", " "))
            for value in dict(qoi.get("qualifiers") or {}).values():
                wanted = wanted + ["of"] + _content_words(str(value))
            if _content_words(stated.subject) != wanted:
                problems.append(f"the text compares {stated.subject!r}, the policy {' '.join(wanted)!r}")
        if "operator" in bound and ConstraintOperator(bound["operator"]) is not stated.operator:
            problems.append(f"the text states {stated.operator.value!r}, the policy {bound['operator']!r}")
        if "target" in bound:
            target = dict(bound["target"] or {})
            if target.get("input_ref") is not None:
                if stated.target_ref != " ".join(_content_words(_input_name(str(target["input_ref"])))):
                    problems.append("the text's bound is not the input the policy names")
            elif stated.target is None or not _equal(stated.target, Quantity.from_dict(target["value"]), spread=False):
                problems.append("the text states a different bound than the policy")
        if "tolerance" in bound:
            tolerance = bound["tolerance"]
            if (tolerance is None) != (stated.tolerance is None) or (
                    tolerance is not None and not _equal(stated.tolerance, Quantity.from_dict(tolerance), spread=True)):
                problems.append("the text states a different tolerance than the policy")
    except (KeyError, TypeError, ValueError, AttributeError, ScientificCoreError) as exc:
        problems.append(f"the policy's comparison is not readable ({exc})")
    return problems


def policy_comparison_conflicts(text: str, policy: Mapping[str, Any]) -> tuple[list[str], set[int]]:
    """Controlled comparisons in the text that a policy-bound comparison field would silently override.

    Returns the conflicts and the sentences that agree with the policy (consumed by it). A policy may
    bind a comparison; it may not replace a different one the user wrote -- stricter or looser.
    """
    bound = {name: policy[name] for name in COMPARISON_FIELDS if name in policy}
    if not bound:
        return [], set()
    conflicts: list[str] = []
    agreeing: set[int] = set()
    stated_comparisons: list[str] = []
    for sentence in sentences(text):
        try:
            stated = read_comparison(text, (sentence.start, sentence.end))
        except Ungrounded:
            continue
        stated_comparisons.append(sentence.text)
        problems = _comparison_disagrees(stated, bound)
        if problems:
            conflicts.append(f"{sentence.text!r}: {'; '.join(problems)}")
        else:
            agreeing.add(sentence.start)
    if len(stated_comparisons) > 1:
        # Sixth review BLOCKER: a policy accounts for at most ONE comparison the user wrote. Two controlled
        # comparisons ("below 353.15 kelvin" and "below 400 kelvin") both agreeing with a policy-bound qoi would
        # otherwise both be read, and the model's choice of which one to cite would silently drop the other.
        conflicts.append(f"the text states {len(stated_comparisons)} comparisons ({stated_comparisons[0]!r}, "
                         f"{stated_comparisons[1]!r}); a policy-bound claim reads exactly one")
    return conflicts, agreeing


def _statement_options(statement: str, prefixes: Sequence[str]) -> set[str]:
    wanted = normalized(str(statement).strip().rstrip(".!?;:"))
    return {wanted} | {f"{normalized(p)} {wanted}" for p in prefixes}


def policy_consumes(text: str, name: str, bound: Any) -> set[int]:
    """The sentences a policy-bound field accounts for: those that state exactly what the policy binds.

    Evidence and uncertainty sentences are consumed only after :data:`POLICY_TEXT_CHECKS` found them
    no stricter than the policy; the decision and assumptions only when a sentence states them verbatim.
    """
    consumed: set[int] = set()
    for sentence in sentences(text):
        body = normalized(sentence.text)
        if name == "evidence" and read_evidence(sentence.text) is not None:
            consumed.add(sentence.start)
        elif name == "uncertainty" and read_uncertainty(sentence.text) is not None:
            consumed.add(sentence.start)
        elif name == "decision" and isinstance(bound, Mapping) and \
                body in _statement_options(str(bound.get("statement", "")), _DECISION_PREFIXES):
            consumed.add(sentence.start)
        elif name == "assumptions" and any(
                isinstance(item, Mapping) and body in _statement_options(str(item.get("statement", "")), _ASSUMPTION_PREFIXES)
                for item in (bound or [])):
            consumed.add(sentence.start)
    return consumed


def declared_input_sentences(text: str, paths: Sequence[str]) -> dict[int, set[str]]:
    """Unconditional ``<input> is <value>`` sentences about a proposed input path, grounded or not, by start.

    Each sentence comes with the input paths that account for it. It is only PROVISIONALLY read: a
    misread or uncited input is then missing, which withholds an answer -- but only for an input the
    selected capability takes. A path the model merely listed ("missing_inputs: [that_limit]") must not
    hide a sentence, so :func:`~engcore.claims.adapters.nl.compile_natural_language` re-checks every
    input-read sentence against the selected capability's declared inputs (fourth review BLOCKER).
    """
    found: dict[int, set[str]] = {}
    for sentence in sentences(text):
        match = _INPUT.fullmatch(sentence.text)
        if match is None or _BLOCKING.search(normalized(sentence.text)):
            continue
        subject = _content_words(match["subject"])
        for path in paths:
            if subject in _input_subjects(path):
                found.setdefault(sentence.start, set()).add(path)
    return found


def unread_sentences(text: str, consumed: set[int]) -> list[str]:
    """Sentences no grounding rule, input or policy accounted for. Any one of them makes the claim UNGROUNDED.

    A deterministic reader cannot know what an unread sentence changes -- a retraction ("That limit is
    waived during burn-in"), a margin, a confidence level, a condition cut off by an abbreviation -- so
    it does not guess that it changes nothing.
    """
    return [sentence.text for sentence in sentences(text) if sentence.start not in consumed]


__all__ = [
    "ADAPTER_GROUNDED_FIELDS",
    "ADMISSIBLE_PROVENANCE",
    "AMBIGUOUS_UNIT_WORDS",
    "COMPARISON_FIELDS",
    "declared_input_sentences",
    "CHANNEL_NAMES",
    "CRITERION_SPANS",
    "CRITERION_SPAN_PREFIX",
    "CriterionProvenance",
    "FIELD_RULES",
    "FieldProvenance",
    "GroundingContext",
    "LEVEL_NAMES",
    "OPERATOR_PHRASES",
    "POLICY_TEXT_CHECKS",
    "Sentence",
    "StatedComparison",
    "TokenLedger",
    "Ungrounded",
    "clause_of",
    "ground_input",
    "operators_stated",
    "policy_comparison_conflicts",
    "policy_consumes",
    "read_comparison",
    "read_evidence",
    "read_uncertainty",
    "sentence_at",
    "sentences",
    "stated_numbers",
    "unread_sentences",
]
