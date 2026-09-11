"""Prose claim -> runtime behaviour checker.

``enforcement`` asks whether the runtime honours the bound a condition carries
in its *structured* form.  It cannot see the other half of a published record:
the human-readable ``description``, which is what a reader actually believes.
A record whose prose says one thing while its structured bound does another is
a contract defect that no structured-only check can see -- that is the class
the SC5 semantic mutation exposed.

This module closes that class.  It does not compare prose against the
structured bound (regex against record, which would only ever prove the record
self-consistent).  It reads a *claim* out of the prose, turns the claim into
concrete values, and puts those values through the real ``assess_validity``
call.  The two failure directions of Phase CG-7 fall out of that directly:

RECORD_TOO_BROAD
    The prose says a value is inside the model's applicability and the runtime
    refuses it.

RECORD_TOO_NARROW
    The prose says a value is outside and the runtime evaluates it happily.

Extraction is deliberately conservative.  Two rules keep it from inventing
claims that are not there:

1.  Only the *leading clause* of a description is read for a numeric bound.
    Record convention states the condition's own bound first -- ``Bi = h L_c /
    k <= 0.1``, ``In (0, 1]``, ``|I| / (derating * maximum_current) <= 1`` --
    and later sentences discuss other quantities.  Reading only the leading
    clause is what keeps ``convection_property_range_utilization`` (whose later
    prose says "exactly Pr >= 0.6", a statement about the Prandtl number and
    not about the ratio itself) from producing a bogus claim.
2.  Anything the rule table below does not match produces *no* claim at all.
    A description with no extractable claim is reported as unbound and is not
    a failure; over-firing on prose is worse than under-firing, because a guard
    that cries wolf gets deleted.

Both halves of the rule table -- the restrictive patterns that assert a bound
and the permissive patterns that assert the absence of one -- are listed here
as data, so a reviewer can read what the checker believes English means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

from . import enforcement, records

ACCEPTS = "accepts"
REFUSES = "refuses"

RECORD_TOO_BROAD = "RECORD_TOO_BROAD"
RECORD_TOO_NARROW = "RECORD_TOO_NARROW"

_NUMBER = r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?"


def _number(text: str) -> float:
    """Parse a record-style number, including the ``1/3`` fractions records use."""
    text = text.strip()
    if "/" in text:
        head, _, tail = text.partition("/")
        return float(head.strip()) / float(tail.strip())
    return float(text)


def leading_clause(description: str) -> str:
    """The part of a description that speaks about the condition's own bound.

    Splits at the first ``.``, ``:``, ``;`` or ``,`` that sits outside every
    bracket and outside every ``|...|`` absolute-value pair, so that
    ``min(f, 1 - f) <= 0.05`` and ``|T - T_Q,ref| / span <= 1`` survive intact.
    """
    depth = 0
    bars = 0
    for index, character in enumerate(description):
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == "|":
            bars ^= 1
        elif character in ".:;," and depth == 0 and not bars:
            # A separator wedged between two digits is a decimal point, not the
            # end of the clause: splitting "<= 0.1" at the dot silently turns
            # the bound into zero.
            before = description[index - 1] if index else ""
            after = description[index + 1] if index + 1 < len(description) else ""
            if before.isdigit() and after.isdigit():
                continue
            return description[:index]
    return description


@dataclass(frozen=True)
class ProseBound:
    """A bound a record's prose asserts, with the rule and text that produced it."""

    minimum: float | None = None
    minimum_inclusive: bool = True
    maximum: float | None = None
    maximum_inclusive: bool = True
    rule: str = ""
    text: str = ""


@dataclass(frozen=True)
class Claim:
    """One executable consequence of a prose bound: a value and its verdict."""

    ref: records.ConditionRef
    verdict: str
    value: float
    rule: str
    text: str


# --- restrictive rules: prose that asserts a bound ------------------------

_INTERVAL = re.compile(
    r"\bin\s*([\[\(])\s*(" + _NUMBER + r")\s*,\s*(" + _NUMBER + r")\s*([\]\)])",
    re.IGNORECASE,
)
_FACTOR = re.compile(r"\bwithin\s+a\s+factor\s+of\s+(" + _NUMBER + r")", re.IGNORECASE)
_STRICTLY_POSITIVE = re.compile(r"\bstrictly\s+positive\b", re.IGNORECASE)
_NON_NEGATIVE = re.compile(r"\bnon-?negative\b", re.IGNORECASE)
_COMPARISON = re.compile(r"(<=|>=|<|>)\s*(" + _NUMBER + r")")


def _restrictive(clause: str) -> ProseBound | None:
    interval = _INTERVAL.search(clause)
    if interval is not None:
        open_bracket, low, high, close_bracket = interval.groups()
        return ProseBound(
            minimum=_number(low),
            minimum_inclusive=open_bracket == "[",
            maximum=_number(high),
            maximum_inclusive=close_bracket == "]",
            rule="interval",
            text=interval.group(0),
        )

    factor = _FACTOR.search(clause)
    if factor is not None:
        span = _number(factor.group(1))
        return ProseBound(
            minimum=1.0 / span,
            minimum_inclusive=True,
            maximum=span,
            maximum_inclusive=True,
            rule="factor",
            text=factor.group(0),
        )

    if _STRICTLY_POSITIVE.search(clause) is not None:
        return ProseBound(
            minimum=0.0,
            minimum_inclusive=False,
            rule="strictly_positive",
            text=_STRICTLY_POSITIVE.search(clause).group(0),
        )

    if _NON_NEGATIVE.search(clause) is not None:
        return ProseBound(
            minimum=0.0,
            minimum_inclusive=True,
            rule="non_negative",
            text=_NON_NEGATIVE.search(clause).group(0),
        )

    comparisons = _COMPARISON.findall(clause)
    if not comparisons:
        return None
    minimum = maximum = None
    minimum_inclusive = maximum_inclusive = True
    for operator, raw in comparisons:
        value = _number(raw)
        if operator in ("<=", "<"):
            if maximum is not None:
                return None  # two upper bounds in one clause: do not guess.
            maximum, maximum_inclusive = value, operator == "<="
        else:
            if minimum is not None:
                return None  # two lower bounds in one clause: do not guess.
            minimum, minimum_inclusive = value, operator == ">="
    return ProseBound(
        minimum=minimum,
        minimum_inclusive=minimum_inclusive,
        maximum=maximum,
        maximum_inclusive=maximum_inclusive,
        rule="comparison",
        text="; ".join(f"{operator} {raw}" for operator, raw in comparisons),
    )


# --- permissive rules: prose that asserts the absence of a bound ----------
#
# Each entry is (name, pattern, target).  ``target`` says which value the
# phrase claims is supported: an explicit number, or the word "below"/"above"
# meaning "just past whatever edge the structured bound carries".  These are
# the phrasings that turn a faithful record into a lie without touching a
# single digit -- the SC5 shape.

_PERMISSIVE: Sequence[tuple[str, re.Pattern[str], object]] = (
    (
        "zero_supported",
        re.compile(
            r"\b(?:including\s+zero|zero\s+(?:\w+\s+){0,2}?(?:is|are))\b[^.;]{0,60}?"
            r"\b(?:supported|allowed|permitted|accepted|admissible|valid|fine|"
            r"handled|in\s+scope|within\s+scope)\b",
            re.IGNORECASE,
        ),
        0.0,
    ),
    (
        "any_value",
        re.compile(
            r"\bany\s+(?:\w+\s+){0,3}?(?:value|magnitude)?[^.;]{0,60}?"
            r"\b(?:is|are)\s+(?:supported|allowed|permitted|accepted)\b",
            re.IGNORECASE,
        ),
        "both",
    ),
    (
        "no_lower_bound",
        re.compile(
            r"\b(?:no\s+lower\s+(?:bound|limit)|unbounded\s+below|"
            r"not\s+bounded\s+below)\b",
            re.IGNORECASE,
        ),
        "below",
    ),
    (
        "no_upper_bound",
        re.compile(
            r"\b(?:no\s+upper\s+(?:bound|limit)|unbounded\s+above|"
            r"not\s+bounded\s+above)\b",
            re.IGNORECASE,
        ),
        "above",
    ),
    (
        "unrestricted",
        re.compile(
            r"\b(?:without\s+restriction|no\s+restriction\s+on)\b",
            re.IGNORECASE,
        ),
        "both",
    ),
)

# Deliberately absent from the table: a bare "unbounded" or "unrestricted".
# Records use those words about *other* symbols -- kcl's lumped_electrical_length
# says "lambda is unbounded" while bounding the ratio at 0.1 -- so matching them
# alone produces a confident false accusation. Only phrasings that name a bound's
# absence ("no lower bound", "unbounded below") are read as claims.


def _step(value: float) -> float:
    return max(abs(value), 1.0) * 1e-6


def _permissive(ref: records.ConditionRef, description: str) -> list[Claim]:
    """Values the *whole* description claims are supported.

    Permissive phrasing is read over the entire description, not just the
    leading clause: a record that adds "any capacity, including zero, is
    supported" three sentences down is making the claim just as loudly.
    """
    claims: list[Claim] = []
    for name, pattern, target in _PERMISSIVE:
        match = pattern.search(description)
        if match is None:
            continue
        values: list[float] = []
        if isinstance(target, (int, float)):
            values.append(float(target))
        if target in ("below", "both") and ref.minimum is not None:
            values.append(ref.minimum - _step(ref.minimum))
        if target in ("above", "both") and ref.maximum is not None:
            values.append(ref.maximum + _step(ref.maximum))
        for value in values:
            claims.append(
                Claim(
                    ref=ref,
                    verdict=ACCEPTS,
                    value=value,
                    rule=f"permissive:{name}",
                    text=match.group(0),
                )
            )
    return claims


def prose_bound(ref: records.ConditionRef) -> ProseBound | None:
    """The bound this record's prose asserts, or None if it asserts none."""
    description = (ref.description or "").strip()
    if not description:
        return None
    return _restrictive(leading_clause(description))


def _bound_claims(ref: records.ConditionRef, bound: ProseBound) -> Iterator[Claim]:
    """Turn an asserted bound into values with expected verdicts.

    Each edge yields the value on the edge and the value just past it.  A probe
    is dropped when it lands outside the *other* asserted edge, since such a
    value is refused for a reason the edge under test does not own.
    """

    def in_other_half(value: float, edge: str) -> bool:
        if edge == "minimum" and bound.maximum is not None:
            if value > bound.maximum or (
                value == bound.maximum and not bound.maximum_inclusive
            ):
                return False
        if edge == "maximum" and bound.minimum is not None:
            if value < bound.minimum or (
                value == bound.minimum and not bound.minimum_inclusive
            ):
                return False
        return True

    if bound.minimum is not None:
        edge = bound.minimum
        step = _step(edge)
        on_edge = ACCEPTS if bound.minimum_inclusive else REFUSES
        for value, verdict in ((edge, on_edge), (edge - step, REFUSES), (edge + step, ACCEPTS)):
            if in_other_half(value, "minimum"):
                yield Claim(ref, verdict, value, f"bound:{bound.rule}:minimum", bound.text)

    if bound.maximum is not None:
        edge = bound.maximum
        step = _step(edge)
        on_edge = ACCEPTS if bound.maximum_inclusive else REFUSES
        for value, verdict in ((edge, on_edge), (edge + step, REFUSES), (edge - step, ACCEPTS)):
            if in_other_half(value, "maximum"):
                yield Claim(ref, verdict, value, f"bound:{bound.rule}:maximum", bound.text)


def claims_for(ref: records.ConditionRef) -> list[Claim]:
    """Every executable claim this record's prose makes about its own values."""
    description = (ref.description or "").strip()
    if not description:
        return []
    claims: list[Claim] = []
    bound = _restrictive(leading_clause(description))
    if bound is not None:
        claims.extend(_bound_claims(ref, bound))
    claims.extend(_permissive(ref, description))
    return claims


def unbound(refs: Iterable[records.ConditionRef] | None = None) -> list[str]:
    """Conditions whose prose asserts nothing this checker can execute.

    Reported for coverage honesty, never as a failure: a description that
    explains *why* a bound exists without restating the number is a legitimate
    record, and a rule that demanded otherwise would be a style checker rather
    than a contract guard.
    """
    return [
        ref.ref
        for ref in (records.conditions() if refs is None else refs)
        if not claims_for(ref)
    ]


def check(refs: Iterable[records.ConditionRef] | None = None) -> dict:
    """Run every prose claim through the runtime and report the disagreements."""
    findings: list[dict] = []
    checked = 0
    conditions = list(records.conditions() if refs is None else refs)
    for ref in conditions:
        model = records.model_by_id(ref.model_id)
        for claim in claims_for(ref):
            checked += 1
            observed = enforcement._classify(model, ref, claim.value)
            satisfied = observed == enforcement.SATISFIED
            if claim.verdict == ACCEPTS and not satisfied:
                direction = RECORD_TOO_BROAD
            elif claim.verdict == REFUSES and satisfied:
                direction = RECORD_TOO_NARROW
            else:
                continue
            findings.append(
                {
                    "condition": ref.ref,
                    "direction": direction,
                    "rule": claim.rule,
                    "prose": claim.text,
                    "value": claim.value,
                    "prose_says": claim.verdict,
                    "runtime_says": observed,
                }
            )
    return {
        "conditions": len(conditions),
        "claims_checked": checked,
        "conditions_without_executable_claim": unbound(conditions),
        "findings": findings,
    }
