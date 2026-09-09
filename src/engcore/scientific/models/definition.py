"""Scientific model definition and validity domain.

A model is not an equation string. It is a versioned scientific claim with
declared requirements, assumptions, a validity domain, references and a
validation status. Recording *when a model is valid* is as important as
recording what it computes — a model evaluated outside its validated domain
must be reportable as such rather than silently trusted.

No physical laws are implemented here, and none are registered by the core.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from ..errors import (
    InvalidScientificProblem,
    ModelValidityError,
    ScientificCoreError,
)
from ..ir.values import ValueKind
from ..ir.variables import VariableRole
from ..serialization import (
    require_bool,
    require_schema,
    require_schema_any,
    schema_string,
)
from ..units.quantity import Quantity, dimensionality
from ..sequences import duplicates
from ..units.validation import require_same_dimension, require_unit
from ..results.immutable import freeze

#: Bumped to /2 by the `exclusions` field. Additive: a /1 record carries no
#: exclusions and reads back as `None` -- "this record does not say" --
#: which is the truthful reading and is distinguishable from a declared
#: empty list. Both versions load; only /2 is written.
MODEL_SCHEMA = schema_string("scientific_model_definition", 2)
MODEL_SCHEMA_V1 = schema_string("scientific_model_definition")
MODEL_INPUT_SCHEMA = schema_string("model_input_spec")
MODEL_OUTPUT_SCHEMA = schema_string("model_output_spec")
BINDING_ISSUE_SCHEMA = schema_string("model_binding_issue")
BINDING_REPORT_SCHEMA = schema_string("model_binding_report")
RANGE_CONDITION_SCHEMA = schema_string("validity_range_condition")
CROSS_LIMIT_CONDITION_SCHEMA = schema_string("validity_cross_limit_condition")
CATEGORY_CONDITION_SCHEMA = schema_string("validity_category_condition")
FLAG_CONDITION_SCHEMA = schema_string("validity_flag_condition")
VALIDITY_DOMAIN_SCHEMA = schema_string("validity_domain")
#: Retained as the name the rest of the tree imports; it now means /2.
VALIDITY_ASSESSMENT_SCHEMA = schema_string("validity_assessment", 2)


class ModelType(str, Enum):
    """Epistemic character of a model — how much it is derived versus fitted."""

    FUNDAMENTAL_RELATION = "fundamental_relation"
    CONSTITUTIVE_MODEL = "constitutive_model"
    EMPIRICAL_CORRELATION = "empirical_correlation"
    APPROXIMATION = "approximation"
    NUMERICAL_MODEL = "numerical_model"
    DATA_DRIVEN_MODEL = "data_driven_model"


class ModelValidationStatus(str, Enum):
    """What has actually been established about this model."""

    UNVALIDATED = "unvalidated"
    SELF_CONSISTENT = "self_consistent"
    BENCHMARK_VALIDATED = "benchmark_validated"
    EXPERIMENTALLY_VALIDATED = "experimentally_validated"
    DEPRECATED = "deprecated"


class ValidityStatus(str, Enum):
    IN_DOMAIN = "in_domain"
    OUTSIDE_VALIDATED_DOMAIN = "outside_validated_domain"
    UNKNOWN = "unknown"          # required context was not supplied


# ---- validity conditions -------------------------------------------------
# Structured predicates, deliberately generic: the core knows about ranges,
# category membership and flags. It does not know about temperature, Reynolds
# number or phase — domains express those *through* these primitives.


def _within(
    value: Quantity,
    *,
    minimum: Quantity | None,
    maximum: Quantity | None,
    minimum_inclusive: bool,
    maximum_inclusive: bool,
    name: str,
) -> ValidityStatus:
    """Is ``value`` inside the declared bounds? Exact; no tolerance applied.

    Shared by :class:`RangeCondition` and :class:`CrossLimitCondition` so the
    two cannot drift on endpoint handling. A condition type that rounded
    differently from its sibling would make the same bound mean two things
    depending on which record happened to express it.
    """
    reference = minimum if minimum is not None else maximum
    if not value.is_compatible_with(reference):
        raise ModelValidityError(
            f"validity condition {name!r}: value {value} is not "
            f"dimensionally compatible with {reference}"
        )
    if minimum is not None:
        magnitude = value.to(minimum.units).magnitude
        outside = (
            magnitude < minimum.magnitude
            if minimum_inclusive
            else magnitude <= minimum.magnitude
        )
        if outside:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    if maximum is not None:
        magnitude = value.to(maximum.units).magnitude
        outside = (
            magnitude > maximum.magnitude
            if maximum_inclusive
            else magnitude >= maximum.magnitude
        )
        if outside:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    return ValidityStatus.IN_DOMAIN


def _absent_or_unreadable(value: Any) -> "UnknownReason":
    """The reason a single-key condition could not read its own input.

    Two situations and one test between them, so every condition type answers
    the question the same way. ``None`` means nobody supplied it -- actionable,
    and the caller can name it. Anything else means it arrived and this core
    could not read it: a field, a mesh, an array, a bare float where a
    ``Quantity`` was required. That is a gap in the core and the caller can do
    nothing about it, which is precisely why the two must not arrive as the
    same symbol.

    **Absence is tested as ``is None``, not by truthiness.** A declared
    ``0.0`` state of charge, an empty string and ``False`` are all supplied
    values, and reading them as "missing" would report a caller who declared
    something as a caller who declared nothing.
    """
    if value is None:
        return UnknownReason.NOT_SUPPLIED
    return UnknownReason.UNREADABLE_SHAPE


def _strict_bool(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    """A serialized boolean must arrive as a boolean, as ``ModelValidityError``.

    The rule now lives at the serialization boundary, where it is a property of
    reading a wire format rather than of this package. This keeps the model
    package's own error type on the refusal, and keeps the call sites short.
    """
    return require_bool(payload, key, default, error=ModelValidityError)


@dataclass(frozen=True)
class RangeCondition:
    """A bounded validity range, with open or closed endpoints.

    Both bounds default to **inclusive**, so ``minimum <= x <= maximum``. Set
    an inclusivity flag to ``False`` for a strict endpoint — a model valid
    only for ``x > 0`` (a positive resistance, an absolute temperature, a
    non-degenerate length) states that exactly rather than approximating it
    with an epsilon.

    An inclusivity flag has no effect when its bound is ``None``.

    This is exact contract logic: no tolerance and no epsilon is applied to a
    validity range. Numerical tolerance belongs to result validation, not to
    the question of whether a model was applicable in the first place.

    **A conservative screen: a bound whose failure is not evidence against.**
    Set ``conservative_screen`` when a value outside this range is an
    *evidence gap* rather than a finding -- when the bound is the edge of what
    the criterion behind it certifies, so a value past that edge is
    unaddressed by that criterion rather than contradicted by it. Such a
    condition reports ``UNKNOWN`` outside its bounds, with reason
    :attr:`UnknownReason.CONSERVATIVE_SCREEN`, instead of
    ``OUTSIDE_VALIDATED_DOMAIN`` -- so it lands among the gaps rather than
    among the findings, and a consumer can tell it from the other three
    situations UNKNOWN covers.

    That distinction is the declaring record's to make and not this class's to
    infer. Nothing here can tell a bound that certifies against from one that
    merely screens: both are two numbers and a name. So the record says which
    it is, and the default is ``False`` -- an ordinary bound, outside is
    outside -- which is what every record written before this flag existed
    keeps meaning.

    **It weakens one condition, in one direction, and never into a claim.** A
    screen cannot report ``IN_DOMAIN`` for a value it did not admit: the value
    is still outside, still named in the assessment, and still costs the
    domain its clean status. What changes is which of the two non-clean
    readings the condition contributes.

    **A dependent bound: one whose answer means nothing unless another holds.**
    ``requires`` names other conditions **in the same validity domain** that
    must be *satisfied* before this one's value licenses anything. Without it
    every condition is evaluated independently, and a domain has no way to say
    "my number is derived from a state that condition over there is what
    establishes". A bound computed from an unestablished state reports
    ``IN_DOMAIN`` on a number nobody is entitled to, and the assessment then
    reads as evidence.

    The rule is one line: **evaluated only when every named condition came out
    satisfied; otherwise ``UNKNOWN`` with reason**
    :attr:`UnknownReason.PREREQUISITE_NOT_ESTABLISHED`.

    ===========================  ==================================
    a required condition is      this condition becomes
    ===========================  ==================================
    satisfied                    evaluated normally
    violated                     ``UNKNOWN``, prerequisite
    unknown (for any reason)     ``UNKNOWN``, prerequisite
    ===========================  ==================================

    **``UNKNOWN`` and not ``violated``, and that is a choice rather than a
    derivation.** A dependent condition could inherit the violation of what it
    depends on. It must not. This condition was never tested: its bound has no
    evidence for it and none against it, and reporting
    ``OUTSIDE_VALIDATED_DOMAIN`` would be reporting evidence against a bound
    nobody evaluated -- the same overclaim in the opposite direction from the
    one this field exists to prevent. A gap is what the absence of a test is.

    **Dependencies form a general acyclic graph**, of any depth. Order of
    declaration does not matter: :class:`ValidityDomain` evaluates in
    dependency order and reports in declaration order. Self-dependency and
    duplicate names are refused here; unknown names and cycles are refused by
    the domain, which is the only object that can see the siblings.
    """

    name: str
    minimum: Quantity | None = None
    maximum: Quantity | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    #: Outside this range is a gap in the evidence, not a finding against.
    conservative_screen: bool = False
    #: Sibling condition names that must be satisfied before this condition's
    #: value licenses anything. Empty means independent, which is what every
    #: record written before this field existed describes.
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ModelValidityError("range condition requires a name")
        object.__setattr__(self, "name", str(self.name).strip())
        # Normalised here so `requires` is a tuple of clean names by the time
        # ValidityDomain checks it against its siblings. The self-reference and
        # the duplicate are the two dependency errors decidable without seeing
        # the domain, so they are decided here.
        required = tuple(str(r).strip() for r in self.requires if str(r).strip())
        if self.name in required:
            raise ModelValidityError(
                f"condition {self.name!r} requires itself, which can never be "
                f"satisfied before it is evaluated"
            )
        repeated = duplicates(required)
        if repeated:
            raise ModelValidityError(
                f"condition {self.name!r} names {repeated} more than once "
                f"in requires"
            )
        object.__setattr__(self, "requires", required)
        if not isinstance(self.conservative_screen, bool):
            raise ModelValidityError(
                f"condition {self.name!r}: conservative_screen must be a "
                f"boolean, not {type(self.conservative_screen).__name__}"
            )
        if self.minimum is None and self.maximum is None:
            raise ModelValidityError(
                f"range condition {self.name!r} needs a minimum or a maximum"
            )
        for bound in (self.minimum, self.maximum):
            if bound is not None and not isinstance(bound, Quantity):
                raise ModelValidityError(
                    f"range condition {self.name!r} bounds must be Quantities"
                )
        if self.minimum is not None and self.maximum is not None:
            require_same_dimension(
                self.minimum, self.maximum,
                context=f"validity range {self.name!r}",
            )
            if self.maximum.to(self.minimum.units).magnitude < self.minimum.magnitude:
                raise ModelValidityError(
                    f"range condition {self.name!r}: maximum below minimum"
                )

    def _bounds_outcome(self, value: Any) -> ValidityStatus:
        """Where the value sits relative to the bounds, before any screen.

        Split out because :meth:`explain_in` has to tell "outside the bounds
        of a screen" from "could not be read at all", and after the screen
        translation both are ``UNKNOWN``.
        """
        if not isinstance(value, Quantity):
            return ValidityStatus.UNKNOWN
        return _within(
            value,
            minimum=self.minimum,
            maximum=self.maximum,
            minimum_inclusive=self.minimum_inclusive,
            maximum_inclusive=self.maximum_inclusive,
            name=self.name,
        )

    def evaluate(self, value: Any) -> ValidityStatus:
        outcome = self._bounds_outcome(value)
        # Translated here and not inside `_within`, which is shared with the
        # sibling type that carries no such flag and exists so the two cannot
        # drift on endpoint handling. Where a value sits relative to its
        # bounds is the same question for both; what a value outside them
        # licenses anybody to say is this condition's own declaration.
        if (
            outcome is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
            and self.conservative_screen
        ):
            return ValidityStatus.UNKNOWN
        return outcome

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        """This condition reads exactly one key: its own name."""
        return self.evaluate(context.get(self.name))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        """Why this condition could not be assessed. Asked only when UNKNOWN.

        DERIVED from what is actually in the context, not asserted: absent is
        ``NOT_SUPPLIED`` and a caller can fix it; present-but-unreadable is
        ``UNREADABLE_SHAPE`` and a caller cannot. The second is the case a
        field, a mesh or an array lands in, and it is the one that used to be
        indistinguishable from the first.

        A screen that was read and did not clear is neither: the value arrived,
        this core read it, and the bound declined to certify it.
        ``CONSERVATIVE_SCREEN`` is that third answer, and it must be tested
        before the other two -- a readable value outside a screen would
        otherwise be reported as ``UNREADABLE_SHAPE``, which is false about
        both the value and the core.
        """
        value = context.get(self.name)
        if (
            self.conservative_screen
            and self._bounds_outcome(value) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        ):
            return UnknownReason.CONSERVATIVE_SCREEN
        return _absent_or_unreadable(value)

    @property
    def context_keys(self) -> frozenset[str]:
        """The context names this condition reads. See :class:`ValidityDomain`."""
        return frozenset({self.name})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RANGE_CONDITION_SCHEMA,
            "name": self.name,
            "minimum": self.minimum.to_dict() if self.minimum else None,
            "maximum": self.maximum.to_dict() if self.maximum else None,
            "minimum_inclusive": self.minimum_inclusive,
            "maximum_inclusive": self.maximum_inclusive,
            # Written unconditionally, including when False and when empty. A
            # reader has to be able to see that a bound is a screen, or that a
            # condition is gated; a key present only on the records that set it
            # would make "an ordinary independent bound" and "a writer that
            # predates the field" the same payload.
            "conservative_screen": self.conservative_screen,
            "requires": list(self.requires),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RangeCondition":
        require_schema(payload, RANGE_CONDITION_SCHEMA)
        minimum, maximum = payload.get("minimum"), payload.get("maximum")
        requires = payload.get("requires", ())
        if isinstance(requires, (str, bytes)) or not isinstance(requires, Sequence):
            raise ModelValidityError(
                f"'requires' must be a sequence of condition names, not "
                f"{type(requires).__name__} ({requires!r}). A bare string "
                f"would decode as one dependency per character"
            )
        return cls(
            name=payload["name"],
            minimum=Quantity.from_dict(minimum) if minimum else None,
            maximum=Quantity.from_dict(maximum) if maximum else None,
            # Records written before open ranges existed described closed
            # ranges, so a missing flag means inclusive.
            minimum_inclusive=_strict_bool(payload, "minimum_inclusive", True),
            maximum_inclusive=_strict_bool(payload, "maximum_inclusive", True),
            # And a record written before screens existed described an ordinary
            # bound; one written before dependencies existed described an
            # independent condition. Same additive reading, and for the same
            # reason: the absent key had exactly one meaning while it was
            # absent. What is NOT accepted is a present key of the wrong type
            # -- see `_strict_bool`.
            conservative_screen=_strict_bool(payload, "conservative_screen", False),
            requires=tuple(requires),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class CategoryCondition:
    """``context[name] in allowed`` — e.g. material class, phase, regime."""

    name: str
    allowed: frozenset[str] = frozenset()
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ModelValidityError("category condition requires a name")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "allowed", frozenset(self.allowed))
        if not self.allowed:
            raise ModelValidityError(
                f"category condition {self.name!r} needs allowed values"
            )

    def evaluate(self, value: Any) -> ValidityStatus:
        if value is None:
            return ValidityStatus.UNKNOWN
        if not isinstance(value, str):
            return ValidityStatus.UNKNOWN
        return (
            ValidityStatus.IN_DOMAIN
            if value in self.allowed
            else ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        )

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        """This condition reads exactly one key: its own name."""
        return self.evaluate(context.get(self.name))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        """Why this condition could not be assessed. Asked only when UNKNOWN."""
        return _absent_or_unreadable(context.get(self.name))

    @property
    def context_keys(self) -> frozenset[str]:
        """The context names this condition reads. See :class:`ValidityDomain`."""
        return frozenset({self.name})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CATEGORY_CONDITION_SCHEMA,
            "name": self.name,
            "allowed": sorted(self.allowed),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CategoryCondition":
        require_schema(payload, CATEGORY_CONDITION_SCHEMA)
        return cls(
            name=payload["name"],
            allowed=frozenset(payload.get("allowed", ())),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class FlagCondition:
    """``context[name] is expected`` — e.g. steady_state=True, linear=True."""

    name: str
    expected: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ModelValidityError("flag condition requires a name")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "expected", bool(self.expected))

    def evaluate(self, value: Any) -> ValidityStatus:
        if not isinstance(value, bool):
            return ValidityStatus.UNKNOWN
        return (
            ValidityStatus.IN_DOMAIN
            if value is self.expected
            else ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        )

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        """This condition reads exactly one key: its own name."""
        return self.evaluate(context.get(self.name))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        """Why this condition could not be assessed. Asked only when UNKNOWN."""
        return _absent_or_unreadable(context.get(self.name))

    @property
    def context_keys(self) -> frozenset[str]:
        """The context names this condition reads. See :class:`ValidityDomain`."""
        return frozenset({self.name})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FLAG_CONDITION_SCHEMA,
            "name": self.name,
            "expected": self.expected,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FlagCondition":
        require_schema(payload, FLAG_CONDITION_SCHEMA)
        return cls(
            name=payload["name"],
            expected=_strict_bool(payload, "expected", True),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class CrossLimitCondition:
    """``context[numerator] / context[denominator]``, against a bound.

    **What this is for.** :class:`RangeCondition` compares a quantity to a
    bound written into the model record. Nothing here expressed *this declared
    limit must stand in a relation to that declared limit* — a material whose
    reference temperature sits above its own maximum operating temperature has
    contradicted itself, and saying so needs two of the caller's values at
    once, not one of theirs and one of the record's.

    Three properties follow from the shape and each is deliberate.

    **It is decidable before any solve.** Both operands are *declarations*, so
    a contradiction between limits is a fact about the declaration and can be
    reported without an operating point, a solver or a run. That is what makes
    it a different question from every state-facing condition beside it, and
    why it is worth having its own type rather than being one more ratio a
    domain assembles.

    **It is UNKNOWN when either operand is absent**, and never IN_DOMAIN.
    The same rule as everywhere else: absence of a declaration is not evidence
    of consistency, and a caller cannot satisfy a cross-limit condition by
    omitting one of the two limits it compares.

    **It introduces no bound of its own.** The ratio is dimensionless by
    construction — the two operands must carry the same dimension, and a
    condition comparing a temperature with a resistance is refused at
    construction rather than at assessment — so the bound is a pure number
    that a domain supplies, usually the same constant its state-facing sibling
    already uses. Every migrated caller reuses one.

    **What it is not.** It is not a way to refuse a declaration. A record that
    cannot exist at all — an interval whose upper edge is below its lower,
    where the derived position would divide by a negative span — belongs in
    the record's own constructor, raising, because a *report* about it would
    arrive after the arithmetic it was supposed to prevent. Those two
    mechanisms stay separate; see ``NEEDS.md`` for the one that was examined
    and deliberately not migrated.
    """

    name: str
    numerator: str
    denominator: str
    minimum: Quantity | None = None
    maximum: Quantity | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("name", "numerator", "denominator"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ModelValidityError(
                    f"cross-limit condition requires a non-empty {label}"
                )
            object.__setattr__(self, label, value)
        if self.numerator == self.denominator:
            raise ModelValidityError(
                f"cross-limit condition {self.name!r} compares "
                f"{self.numerator!r} with itself, which is always 1 and "
                f"decides nothing"
            )
        if self.minimum is None and self.maximum is None:
            raise ModelValidityError(
                f"cross-limit condition {self.name!r} needs a minimum or a "
                f"maximum"
            )
        for bound in (self.minimum, self.maximum):
            if bound is None:
                continue
            if not isinstance(bound, Quantity):
                raise ModelValidityError(
                    f"cross-limit condition {self.name!r} bounds must be "
                    f"Quantities"
                )
            # The operands share a dimension, so their ratio is dimensionless
            # and so is every admissible bound on it. A bound carrying kelvin
            # would silently make this condition a range condition wearing the
            # wrong type, so it is refused here rather than at assessment.
            if not bound.is_compatible_with("dimensionless"):
                raise ModelValidityError(
                    f"cross-limit condition {self.name!r} bounds a ratio of "
                    f"two same-dimension declarations, so they must be "
                    f"dimensionless; got {bound}"
                )
        if self.minimum is not None and self.maximum is not None:
            if self.maximum.magnitude < self.minimum.magnitude:
                raise ModelValidityError(
                    f"cross-limit condition {self.name!r}: maximum below "
                    f"minimum"
                )

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        """Why this condition could not be assessed. Asked only when UNKNOWN.

        Two keys, so two chances to be unreadable, and the precedence matters:
        if **either** operand arrived in a shape this core cannot read, that is
        the situation, because supplying the other one would not help. Only
        when neither was supplied at all is this a caller's omission.
        """
        operands = (
            context.get(self.numerator),
            context.get(self.denominator),
        )
        if any(
            _absent_or_unreadable(value) is UnknownReason.UNREADABLE_SHAPE
            for value in operands
        ):
            return UnknownReason.UNREADABLE_SHAPE
        return UnknownReason.NOT_SUPPLIED

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        """The ratio of the two named declarations, against the bound.

        UNKNOWN unless **both** are present as Quantities. A zero denominator
        is refused rather than reported: the ratio would be an infinity that
        the bound would then compare, and an infinity nobody computed is worse
        than a loud failure.
        """
        numerator = context.get(self.numerator)
        denominator = context.get(self.denominator)
        if not isinstance(numerator, Quantity):
            return ValidityStatus.UNKNOWN
        if not isinstance(denominator, Quantity):
            return ValidityStatus.UNKNOWN
        if not numerator.is_compatible_with(denominator):
            raise ModelValidityError(
                f"validity condition {self.name!r}: {self.numerator} "
                f"({numerator}) and {self.denominator} ({denominator}) do not "
                f"share a dimension, so their ratio is not a number this "
                f"condition can bound"
            )
        divisor = denominator.to(numerator.units).magnitude
        if divisor == 0.0:
            raise ModelValidityError(
                f"validity condition {self.name!r}: {self.denominator} is "
                f"zero, and the ratio this condition bounds does not exist"
            )
        ratio = Quantity(numerator.magnitude / divisor, "dimensionless")
        return _within(
            ratio,
            minimum=self.minimum,
            maximum=self.maximum,
            minimum_inclusive=self.minimum_inclusive,
            maximum_inclusive=self.maximum_inclusive,
            name=self.name,
        )

    @property
    def context_keys(self) -> frozenset[str]:
        """The two operands. Deliberately **not** this condition's own name.

        A cross-limit condition is labelled by the relation it states and reads
        neither key by that label, so its name is not a context entry and is
        not something a caller could occupy. Classifying it as one would force
        a domain to reserve a name nothing computes and nothing reads.
        """
        return frozenset({self.numerator, self.denominator})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CROSS_LIMIT_CONDITION_SCHEMA,
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "minimum": self.minimum.to_dict() if self.minimum else None,
            "maximum": self.maximum.to_dict() if self.maximum else None,
            "minimum_inclusive": self.minimum_inclusive,
            "maximum_inclusive": self.maximum_inclusive,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CrossLimitCondition":
        require_schema(payload, CROSS_LIMIT_CONDITION_SCHEMA)
        minimum, maximum = payload.get("minimum"), payload.get("maximum")
        return cls(
            name=payload["name"],
            numerator=payload["numerator"],
            denominator=payload["denominator"],
            minimum=Quantity.from_dict(minimum) if minimum else None,
            maximum=Quantity.from_dict(maximum) if maximum else None,
            minimum_inclusive=_strict_bool(payload, "minimum_inclusive", True),
            maximum_inclusive=_strict_bool(payload, "maximum_inclusive", True),
            description=payload.get("description", ""),
        )


ValidityCondition = (
    RangeCondition | CategoryCondition | FlagCondition | CrossLimitCondition
)


def _required_names(condition: ValidityCondition) -> tuple[str, ...]:
    """The siblings this condition depends on, for a type that can declare any.

    Read through ``getattr`` because :data:`ValidityCondition` is a union of
    four concrete records and only :class:`RangeCondition` currently declares
    dependencies. A type that does not carry the field depends on nothing,
    which is the same answer as an empty declaration -- so the gating code
    below stays one path rather than branching on condition type.
    """
    return tuple(getattr(condition, "requires", ()) or ())


def _dependency_order(
    conditions: tuple[ValidityCondition, ...],
) -> tuple[ValidityCondition, ...]:
    """Evaluation order for a set of conditions, or a refusal.

    A GENERAL ACYCLIC GRAPH, of any depth, rather than a depth-one rule. The
    restriction was considered and rejected: Kahn's algorithm is the same
    twenty lines whether it permits one level or many, so a depth limit would
    buy no simplicity and would have to be justified to anyone who later needed
    a chain -- and "the implementation found it easier" is not a scientific
    reason to refuse a well-formed declaration. What must be refused is a graph
    with no valid order at all, and that is a cycle, which this detects
    directly rather than approximating by forbidding depth.

    Refused here: a dependency on a name no sibling declares, and a cycle.
    Self-dependency and duplicates are already refused by the condition itself.
    Both refusals are at construction, so a domain that cannot be evaluated
    coherently never exists to be asked.

    The returned order is stable: ties are broken by declaration order, so the
    same conditions always evaluate in the same sequence regardless of how the
    graph is shaped.
    """
    # Read ONCE, here, and reused by the ordering below. The two used to walk
    # the conditions separately and call `_required_names` on each of them
    # twice over.
    requirements = {c.name: frozenset(_required_names(c)) for c in conditions}

    known = {c.name for c in conditions}
    for condition in conditions:
        missing = sorted(requirements[condition.name] - known)
        if missing:
            raise ModelValidityError(
                f"condition {condition.name!r} requires {missing}, which "
                f"{'is' if len(missing) == 1 else 'are'} not a condition of "
                f"this validity domain. A dependency on a name nothing here "
                f"declares can never be satisfied, so the condition would be "
                f"permanently UNKNOWN"
            )

    # KAHN'S ALGORITHM WITH AN IN-DEGREE COUNT, rather than a rescan per layer.
    #
    # The previous form recomputed `set(_required_names(c))` for every still
    # pending condition on every pass, and rebuilt `pending` each time. For a
    # FLAT or FAN graph that is one pass and costs nothing, which is why this
    # never showed: those resolve everything in a single layer. A CHAIN resolves
    # exactly one condition per pass, so it made n passes over an O(n) list --
    # **O(n^2)**, measured at 85 ms for 1,000 chained conditions and 2.1 s for
    # 5,000, against 0.4 ms and 2.8 ms for the same counts laid out flat.
    #
    # The order produced is unchanged, and that is deliberate rather than
    # incidental: conditions are emitted layer by layer, and in declaration
    # order within each layer, exactly as `[c for c in pending if ...]` did.
    # `assess` reports in declaration order and evaluates in this one, and while
    # the ordering provably cannot change a verdict -- `tests/
    # test_core_invariants_adversarial.py` asserts that over every permutation
    # -- reproducing it exactly keeps this a performance change and nothing else.
    # NOTHING DECLARES A PREREQUISITE -- which is every model shipped today:
    # 0 of 64 validity conditions in this repository use `requires`. With no
    # edges the graph has one layer, declaration order is already a valid
    # topological order, and the index below would be five mappings built to
    # discover that.
    #
    # Without this the index cost 22-33% more than the old rescan on flat and
    # fan graphs -- a real regression, measured, and the price of removing the
    # quadratic. This gives the common case back rather than accepting a trade
    # that was never necessary.
    if not any(requirements.values()):
        return tuple(conditions)

    position = {c.name: index for index, c in enumerate(conditions)}
    by_name = {c.name: c for c in conditions}

    outstanding = {name: len(required) for name, required in requirements.items()}
    dependents: dict[str, list[str]] = {}
    for name, required in requirements.items():
        for prerequisite in required:
            dependents.setdefault(prerequisite, []).append(name)

    order: list[ValidityCondition] = []
    layer = [c for c in conditions if not outstanding[c.name]]
    while layer:
        order.extend(layer)
        freed: list[str] = []
        for condition in layer:
            for dependent in dependents.get(condition.name, ()):
                outstanding[dependent] -= 1
                if outstanding[dependent] == 0:
                    freed.append(dependent)
        # Back into declaration order, so a layer reads the way the domain
        # wrote it rather than the way its prerequisites happened to finish.
        freed.sort(key=position.__getitem__)
        layer = [by_name[name] for name in freed]

    if len(order) != len(conditions):
        # Everything left depends on something else still left, which is
        # the definition of a cycle. Named in sorted order so the message
        # is the same on every run.
        stuck = sorted(name for name, count in outstanding.items() if count)
        raise ModelValidityError(
            f"validity conditions {stuck} form a dependency cycle. There "
            f"is no order in which each is evaluated after the conditions "
            f"it requires, so no assessment of this domain could be "
            f"coherent"
        )
    return tuple(order)

_CONDITION_DECODERS = {
    RANGE_CONDITION_SCHEMA: RangeCondition,
    CATEGORY_CONDITION_SCHEMA: CategoryCondition,
    FLAG_CONDITION_SCHEMA: FlagCondition,
    CROSS_LIMIT_CONDITION_SCHEMA: CrossLimitCondition,
}


def _decode_condition(payload: Mapping[str, Any]) -> ValidityCondition:
    decoder = _CONDITION_DECODERS.get(payload.get("schema"))
    if decoder is None:
        raise ModelValidityError(
            f"unknown validity condition schema {payload.get('schema')!r}"
        )
    return decoder.from_dict(payload)


class UnknownReason(str, Enum):
    """Why one condition could not be assessed. **Closed, and exhaustive.**

    ``ValidityStatus.UNKNOWN`` was one symbol carrying at least four distinct
    situations, and every one of them reached ``derive_verdict`` as
    ``INSUFFICIENT_EVIDENCE``. The external verdict stayed honest -- it
    degraded to "I do not know" rather than lying -- but the *reason* was lost,
    so no consumer could act on it and no audit could tell a core limitation
    from a missing declaration. These are those situations, named:

    ``NOT_SUPPLIED``
        Nobody supplied the input. **Actionable and nameable**: the caller
        declares it and the condition becomes assessable. This is the only one
        of the four a caller can fix by declaring something.

    ``UNREADABLE_SHAPE``
        The input arrived, and in a shape this core cannot read -- a field, a
        mesh, an array, anything that is not the scalar ``Quantity`` (or
        ``str``, or ``bool``) the condition is stated over. **The caller can do
        nothing about this**; it is a gap in the core, and it is the ceiling on
        the universality claim: a domain built on fields can never reach
        SUPPORTED however good its physics, because every one of its
        conditions returns UNKNOWN silently. Naming the situation does not
        close it -- see the module note -- but it makes it visible and
        countable instead of indistinguishable from a caller's omission.

    ``CONSERVATIVE_SCREEN``
        The condition is a deliberately conservative screen and the run did not
        clear it. **Not shown wrong, and may still be fine.** A screen that
        refuses to certify is not a screen that found a defect, and collapsing
        the two overstates what was learned.

    ``PREREQUISITE_NOT_ESTABLISHED``
        The condition cannot be assessed until another one is. **No producer
        exists in this tree**, deliberately: a prerequisite mechanism built
        before there was anywhere to record *why* a condition was skipped
        would have to be rewritten once there was. The name is here so that
        mechanism has somewhere to put its answer, and so this enum is the one
        place the four situations are listed.

    A reason outside this enum is refused rather than defaulted, which is what
    stops the channel from silently re-collapsing into one symbol.
    """

    NOT_SUPPLIED = "not_supplied"
    UNREADABLE_SHAPE = "unreadable_shape"
    CONSERVATIVE_SCREEN = "conservative_screen"
    PREREQUISITE_NOT_ESTABLISHED = "prerequisite_not_established"


UNKNOWN_CONDITION_SCHEMA = schema_string("unknown_condition")


@dataclass(frozen=True)
class UnknownCondition:
    """One condition that could not be assessed, and why.

    ``detail`` is prose for a reader and carries no meaning a consumer should
    branch on; ``reason`` is the machine-readable part and is what
    :mod:`engcore.domains.repair` and every other consumer decides on.
    """

    name: str
    reason: UnknownReason
    detail: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ModelValidityError("unknown-condition record requires a name")
        object.__setattr__(self, "name", str(self.name).strip())
        try:
            object.__setattr__(self, "reason", UnknownReason(self.reason))
        except ValueError as exc:
            raise ModelValidityError(
                f"unknown-condition record {self.name!r} carries reason "
                f"{self.reason!r}, which is not one of the declared "
                f"situations {[r.value for r in UnknownReason]}. A reason that "
                f"cannot be attributed to one of them is refused rather than "
                f"defaulted: defaulting is how UNKNOWN became one symbol "
                f"meaning four things in the first place"
            ) from exc
        object.__setattr__(self, "detail", str(self.detail))

    @property
    def is_actionable(self) -> bool:
        """Can the caller make this condition assessable by declaring something?

        True for ``NOT_SUPPLIED`` alone. A shape this core cannot read is not
        fixed by declaring it again, a conservative screen was assessed and did
        not clear, and a prerequisite is the other condition's problem.
        """
        return self.reason is UnknownReason.NOT_SUPPLIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNKNOWN_CONDITION_SCHEMA,
            "name": self.name,
            "reason": self.reason.value,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UnknownCondition":
        require_schema(payload, UNKNOWN_CONDITION_SCHEMA)
        return cls(
            name=payload["name"],
            reason=UnknownReason(payload["reason"]),
            detail=payload.get("detail", ""),
        )


#: Bumped from /1 because a /1 record carrying unknown conditions has no place
#: to say WHY, and the missing reason cannot be defaulted -- "not recorded" is
#: not one of the four situations. `from_dict` therefore accepts /1 only when
#: its `unknown` list is empty, where there is nothing to explain. The
#: `quantity_transfer/1 -> /2` bump is the same move for the same reason.
VALIDITY_ASSESSMENT_SCHEMA_V1 = schema_string("validity_assessment", 1)
VALIDITY_ASSESSMENT_SCHEMA_V2 = schema_string("validity_assessment", 2)


def classify_conditions(
    *,
    satisfied: Sequence[str],
    violated: Sequence[str],
    unknown: Sequence[str],
) -> ValidityStatus:
    """The status these condition lists imply. **The one statement of the rule.**

    * anything violated -> ``OUTSIDE_VALIDATED_DOMAIN``;
    * else anything unknown -> ``UNKNOWN``;
    * else something satisfied -> ``IN_DOMAIN``;
    * else -- **nothing was evaluated at all** -- ``UNKNOWN``.

    That last clause is not an edge case and not a convenience. *Absence of
    declared limits is not evidence of unlimited validity*: a domain with no
    conditions has established nothing, and ``ValidityDomain.assess`` returns
    exactly this for one. Classifying an all-empty assessment as IN_DOMAIN
    would let a model that checked nothing certify itself, which is the
    strongest claim in the vocabulary awarded for the least work.

    **Why this lives here.** The rule was written out three times -- in
    ``ValidityDomain.assess``, in the credibility boundary's
    ``classify_assessment``, and again in a domain's coupling combiner -- and
    the boundary's copy existed *because* the core did not enforce it. Three
    statements of one rule is three chances for it to drift, and the drift
    would not be visible: each copy looks correct on its own. It is stated
    once, where the record that has to obey it lives, and the other two
    delegate.
    """
    if violated:
        return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    if unknown:
        return ValidityStatus.UNKNOWN
    if satisfied:
        return ValidityStatus.IN_DOMAIN
    return ValidityStatus.UNKNOWN


@dataclass(frozen=True)
class ValidityAssessment:
    """Result of testing a validity domain against a context.

    ``unknown`` names the conditions that could not be assessed;
    ``unknown_reasons`` says why each one could not, and **covering the first
    exactly is an enforced invariant**, not a convention. A name in ``unknown``
    with no reason beside it is the defect this record was changed to close:
    one symbol standing for a missing declaration, a shape the core cannot
    read, a conservative screen, and an unmet prerequisite, with no way for a
    consumer to tell them apart.

    ``unknown`` stays a tuple of plain names, deliberately. Every consumer in
    the tree does ``for name in assessment.unknown`` and set arithmetic against
    ``violated`` and ``satisfied``; making the entries records would break all
    of them, and making them a ``str`` subclass carrying a reason would buy
    compatibility with the same weaker guarantee ``NEEDS.md A2.6`` already
    criticises ``FrozenMapping`` for. Two fields with an enforced correspondence
    says the same thing without the sleight of hand.
    """

    status: ValidityStatus
    satisfied: tuple[str, ...] = ()
    violated: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    unknown_reasons: tuple[UnknownCondition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "satisfied", tuple(self.satisfied))
        object.__setattr__(self, "violated", tuple(self.violated))
        object.__setattr__(self, "unknown", tuple(self.unknown))
        object.__setattr__(self, "unknown_reasons", tuple(self.unknown_reasons))

        # The status is COERCED first and CROSS-CHECKED second, and both were
        # previously the credibility boundary's job -- which is one layer too
        # late and one layer too narrow, because an assessment reaches plenty
        # of readers that never cross that boundary.
        #
        # `ValidityAssessment(status="in_domain")` stored a raw str, which then
        # crashed this record's own `to_dict` on `self.status.value`;
        # `status="typo"` stored a string that is no status at all.
        try:
            object.__setattr__(self, "status", ValidityStatus(self.status))
        except ValueError as exc:
            raise ModelValidityError(
                f"validity assessment carries status {self.status!r}, which is "
                f"not a ValidityStatus. An unrecognised status matches no "
                f"branch of any consumer and is read as 'nothing argues "
                f"against this result'; the declared statuses are "
                f"{[s.value for s in ValidityStatus]}"
            ) from exc
        self._require_status_agrees_with_its_own_conditions()

        for entry in self.unknown_reasons:
            if not isinstance(entry, UnknownCondition):
                raise ModelValidityError(
                    f"unknown_reasons entry {entry!r} is a "
                    f"{type(entry).__name__}, not an UnknownCondition. The "
                    f"reason is the machine-readable half of this record and "
                    f"a bare string is exactly the thing it replaces"
                )
        explained = [entry.name for entry in self.unknown_reasons]
        duplicated = duplicates(explained)
        if duplicated:
            raise ModelValidityError(
                f"conditions {duplicated} each carry more than one reason for "
                f"being unknown; a condition was not assessed for exactly one "
                f"reason"
            )
        # Hashed ONCE and reused. `n not in set(explained)` inside the
        # comprehension below rebuilt this set for every entry, which made the
        # coverage check O(n^2) -- 3.1 s for an assessment carrying 10,000
        # unknown conditions. Same shape as the duplicate scan above it, one
        # line apart, and equally invisible at the sizes a domain declares.
        explained_names = set(explained)
        stray = sorted(explained_names - set(self.unknown))
        if stray:
            raise ModelValidityError(
                f"unknown_reasons explains {stray}, which this assessment does "
                f"not report as unknown"
            )
        unexplained = [n for n in self.unknown if n not in explained_names]
        if unexplained:
            raise ModelValidityError(
                f"conditions {sorted(unexplained)} are reported UNKNOWN with "
                f"no reason. UNKNOWN carries at least four distinct "
                f"situations -- a missing declaration, a shape this core "
                f"cannot read, a conservative screen, an unmet prerequisite -- "
                f"and a name on its own cannot be acted on by any consumer or "
                f"told apart by any audit. Give each one an UnknownCondition; "
                f"the declared reasons are "
                f"{[r.value for r in UnknownReason]}"
            )

    @property
    def implied_status(self) -> ValidityStatus:
        """The status this assessment's own condition lists imply."""
        return classify_conditions(
            satisfied=self.satisfied,
            violated=self.violated,
            unknown=self.unknown,
        )

    def _require_status_agrees_with_its_own_conditions(self) -> None:
        """A record that contradicts itself must not exist.

        ``status=IN_DOMAIN, violated=("biot_number",)`` constructed happily and
        would report the model applicable on the same record that names the
        bound it broke. Three more of the same shape were reachable: OUTSIDE
        with nothing violated, IN_DOMAIN with unknowns outstanding, and
        IN_DOMAIN having evaluated nothing at all -- the last being the
        strongest claim in the vocabulary awarded for the least work.

        Recompute-and-verify rather than derive-and-overwrite. Deriving would
        make a producer that had the classification wrong silently *right*, and
        the thing that was wrong -- a caller assembling an assessment by hand
        instead of through ``assess`` -- would go on being wrong somewhere this
        record cannot see. A refusal names it.

        Every assessment ``ValidityDomain.assess`` produces passes untouched:
        it uses this same classification.
        """
        implied = self.implied_status
        if self.status is implied:
            return
        raise ModelValidityError(
            f"validity assessment declares status {self.status.value!r} while "
            f"its own conditions imply {implied.value!r} "
            f"(satisfied={list(self.satisfied)}, "
            f"violated={list(self.violated)}, unknown={list(self.unknown)}). "
            f"An assessment may report a status but may not contradict the "
            f"conditions it carries: a violated condition is evidence against "
            f"the model, an unknown one is evidence of nothing either way, and "
            f"an assessment that evaluated nothing has established nothing -- "
            f"absence of declared limits is not evidence of unlimited validity"
        )

    def reason_for(self, name: str) -> UnknownReason | None:
        """Why ``name`` was not assessed, or ``None`` if it was."""
        for entry in self.unknown_reasons:
            if entry.name == name:
                return entry.reason
        return None

    def unknown_because(self, reason: UnknownReason) -> tuple[str, ...]:
        """The conditions not assessed for one particular reason."""
        return tuple(
            entry.name
            for entry in self.unknown_reasons
            if entry.reason is UnknownReason(reason)
        )

    @property
    def actionable_unknowns(self) -> tuple[str, ...]:
        """Conditions a caller could make assessable by declaring something.

        ``NOT_SUPPLIED`` only. This is the distinction repair guidance needs
        and could not previously make: "declare this and the condition becomes
        assessable" is a different sentence from "this cannot be assessed at
        all", and before there were reasons both arrived as a bare name.
        """
        return self.unknown_because(UnknownReason.NOT_SUPPLIED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VALIDITY_ASSESSMENT_SCHEMA_V2,
            "status": self.status.value,
            "satisfied": list(self.satisfied),
            "violated": list(self.violated),
            "unknown": list(self.unknown),
            "unknown_reasons": [e.to_dict() for e in self.unknown_reasons],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidityAssessment":
        version = require_schema_any(
            payload,
            (VALIDITY_ASSESSMENT_SCHEMA_V1, VALIDITY_ASSESSMENT_SCHEMA_V2),
        )
        unknown = tuple(payload.get("unknown", ()))
        if version == VALIDITY_ASSESSMENT_SCHEMA_V1 and unknown:
            raise ScientificCoreError(
                f"{VALIDITY_ASSESSMENT_SCHEMA_V1} record reports "
                f"{sorted(unknown)} as unknown and has no field to say why. "
                f"The reason cannot be reconstructed and must not be "
                f"defaulted: 'not recorded' is not one of the four declared "
                f"situations. Re-derive the assessment, or read it with the "
                f"code that wrote it"
            )
        return cls(
            status=ValidityStatus(payload["status"]),
            satisfied=tuple(payload.get("satisfied", ())),
            violated=tuple(payload.get("violated", ())),
            unknown=unknown,
            unknown_reasons=tuple(
                UnknownCondition.from_dict(e)
                for e in payload.get("unknown_reasons", ())
            ),
        )


@dataclass(frozen=True)
class ValidityDomain:
    """The conditions under which a model's results are considered validated.

    **The reserved namespace.** ``derived_quantities`` names the context keys
    that no caller may supply — the dimensionless groups and state coordinates
    a domain's assembler computes, which the conditions below read *by name*.
    It lives here, on the model record, rather than being handed in at each
    call, for three reasons.

    A reserved name exists because a condition reads it and no declaration can
    produce it. That is a fact about *these conditions*, so it belongs beside
    them; two assemblers serving the same model then cannot disagree about
    which names are the assembler's, because there is only one answer and it
    is written down once.

    It is reachable from a registry. A ``ModelRegistry`` iterating its models
    can enumerate every reserved name in the repository, which is what lets
    the forgery test be written once over ``__iter__`` instead of once per
    domain — a new domain is covered the day it registers, without anyone
    remembering to extend a list.

    It survives serialization. ``to_dict``/``from_dict`` carry it, so a model
    that crosses a process or a file boundary keeps its reserved namespace. A
    module-level constant in a domain package does not.

    **What it buys.** :meth:`assess` can then tell the two namespaces apart and
    refuse to read a reserved name that the assembler did not produce; see
    that method. And ``ScientificModelDefinition`` refuses to be constructed at
    all if a condition reads a name that is neither a declared model input nor
    reserved here — so a derived quantity cannot be introduced without being
    declared forgeable-by-nobody, at import, rather than being discovered from
    a verdict later.
    """

    conditions: tuple[ValidityCondition, ...] = ()
    description: str = ""
    derived_quantities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "conditions", tuple(self.conditions))
        names = [c.name for c in self.conditions]
        duplicated = duplicates(names)
        if duplicated:
            raise ModelValidityError(
                f"duplicate validity condition names: {duplicated}"
            )
        object.__setattr__(
            self, "derived_quantities", frozenset(self.derived_quantities)
        )
        # A reserved name nothing reads is not a guard, it is a claim that one
        # exists. Refused so the set stays an accurate statement of what this
        # domain's conditions consume.
        stale = sorted(self.derived_quantities - self.context_keys)
        if stale:
            raise ModelValidityError(
                f"validity domain reserves {stale}, which no condition reads; "
                f"a reserved name that decides nothing is not protecting "
                f"anything. Remove it, or add the condition that reads it"
            )
        # Refused HERE, because this is the only object that can see the
        # sibling names. Same family as the check above: a declaration naming
        # something that does not exist is refused at construction rather than
        # discovered from a verdict. The order is recomputed in `assess`; what
        # this call buys is that an incoherent domain cannot be constructed.
        _dependency_order(self.conditions)

    @property
    def context_keys(self) -> frozenset[str]:
        """Every context name this domain's conditions read."""
        keys: set[str] = set()
        for condition in self.conditions:
            keys |= condition.context_keys
        return frozenset(keys)

    def assess(
        self,
        context: Mapping[str, Any] | None = None,
        *,
        declared: Mapping[str, Any] | None = None,
        assembled: Mapping[str, Any] | None = None,
    ) -> ValidityAssessment:
        """Classify a context as in-domain, outside-domain, or unknown.

        A domain with no conditions is UNKNOWN, not valid: absence of declared
        limits is not evidence of unlimited validity.

        **Two namespaces, not one merged mapping.** A condition reads a value
        by name and cannot see where it came from. If the caller's parameters
        and the assembler's derived quantities arrive already merged, a caller
        parameter that occupies a derived quantity's name *is* that derived
        quantity as far as every condition here is concerned — which is how a
        model with no rating declared at all reports IN_DOMAIN over three
        numbers nobody computed.

        So the two namespaces arrive separately:

        * ``assembled`` is what the domain's assembler actually produced. Every
          key must be reserved in :attr:`derived_quantities`; a domain emitting
          an unreserved name has a derived quantity a caller could impersonate,
          and is told so here rather than by a verdict.
        * ``declared`` is what the caller stated. A reserved name in it is
          **refused**, not overwritten: the request is for a verdict over a
          quantity the caller has asserted, and answering it at all — with
          their number or with the domain's — would be answering a question the
          caller was not entitled to ask.

        The single-mapping form is still accepted, because most models have no
        reserved namespace and a plain context is the honest way to assess one.
        It is read as entirely caller-declared, so if this domain reserves
        anything and the mapping carries it, that is the merged-mapping mistake
        and it raises. There is therefore no path by which a reserved name is
        read from anywhere but ``assembled``.
        """
        merged = self._merge(context, declared=declared, assembled=assembled)
        if not self.conditions:
            return ValidityAssessment(status=ValidityStatus.UNKNOWN)

        # EVALUATED in dependency order, REPORTED in declaration order. The
        # two are separated deliberately: a dependent has to be decided after
        # what it depends on, and a reader has to see the domain's own list
        # order however the graph happens to be shaped. Reordering the
        # `conditions` tuple therefore cannot change any outcome -- it only
        # changes the order the same outcomes are listed in.
        outcomes: dict[str, ValidityStatus] = {}
        reason_by_name: dict[str, UnknownReason] = {}
        for condition in _dependency_order(self.conditions):
            required = _required_names(condition)
            unmet = [
                name
                for name in required
                if outcomes.get(name) is not ValidityStatus.IN_DOMAIN
            ]
            if unmet:
                # NOT EVALUATED AT ALL. The value may well be sitting in the
                # context; it is not read, because reading it would produce a
                # verdict on a number derived from a state nothing here
                # established. And UNKNOWN rather than the prerequisite's
                # `violated`: this bound was never tested, so there is no
                # evidence against it either.
                outcomes[condition.name] = ValidityStatus.UNKNOWN
                reason_by_name[condition.name] = (
                    UnknownReason.PREREQUISITE_NOT_ESTABLISHED
                )
                continue
            # ``evaluate_in`` rather than ``evaluate(context.get(name))``: a
            # cross-limit condition reads two keys and neither is its own
            # name. Every condition type implements it, and the single-key
            # ones implement it as exactly the lookup this line used to do.
            outcome = condition.evaluate_in(merged)
            outcomes[condition.name] = outcome
            if outcome is ValidityStatus.UNKNOWN:
                # DERIVED, at the one place that knows both the condition and
                # the context it failed to read. A reason assembled later from
                # a name alone would be a guess, and a reason supplied by the
                # caller would be the assertion this channel exists to
                # replace.
                reason_by_name[condition.name] = condition.explain_in(merged)

        satisfied: list[str] = []
        violated: list[str] = []
        unknown: list[str] = []
        reasons: list[UnknownCondition] = []
        for condition in self.conditions:
            outcome = outcomes[condition.name]
            if outcome is ValidityStatus.IN_DOMAIN:
                satisfied.append(condition.name)
            elif outcome is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
                violated.append(condition.name)
            else:
                unknown.append(condition.name)
                reasons.append(
                    UnknownCondition(
                        name=condition.name,
                        reason=reason_by_name[condition.name],
                    )
                )

        if violated:
            status = ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        elif unknown:
            status = ValidityStatus.UNKNOWN
        else:
            status = ValidityStatus.IN_DOMAIN

        return ValidityAssessment(
            status=status,
            satisfied=tuple(satisfied),
            violated=tuple(violated),
            unknown=tuple(unknown),
            unknown_reasons=tuple(reasons),
        )

    def _merge(
        self,
        context: Mapping[str, Any] | None,
        *,
        declared: Mapping[str, Any] | None,
        assembled: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        """The one mapping the conditions read, with provenance enforced first."""
        if context is not None and (declared is not None or assembled is not None):
            raise ModelValidityError(
                "assess() takes either a single caller-declared mapping or the "
                "declared=/assembled= pair, not both"
            )
        if context is not None and hasattr(context, "assembled"):
            # A domain's two-namespace context, handed in as one mapping. It
            # would be read as entirely caller-declared and refused a line
            # below with a message about a caller forging a name it did not
            # forge, so say the true thing instead.
            raise ModelValidityError(
                "a domain validity context carries the two namespaces already "
                "and must not be flattened into the single-mapping form; call "
                "context.assess(model), which hands this model the slice of the "
                "assembly it reserves"
            )
        if context is not None:
            declared = context
        declared = {} if declared is None else declared
        assembled = {} if assembled is None else assembled

        unregistered = sorted(set(assembled) - self.derived_quantities)
        if unregistered:
            raise ModelValidityError(
                f"this validity domain was handed assembled quantities "
                f"{unregistered} that it does not reserve; an assembled "
                f"quantity that is not reserved can be supplied by a caller "
                f"parameter of the same name and read as though the domain had "
                f"computed it. Add it to derived_quantities"
            )
        forged = sorted(set(declared) & self.derived_quantities)
        if forged:
            raise ModelValidityError(
                f"caller-declared context carries the reserved name(s) "
                f"{forged}; {sorted(self.derived_quantities)} are derived by "
                f"this domain and a caller cannot supply one. Strip them from "
                f"the declaration, and pass what the domain computed as "
                f"assembled="
            )
        if not assembled:
            return declared
        return {**declared, **assembled}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": VALIDITY_DOMAIN_SCHEMA,
            "conditions": [c.to_dict() for c in self.conditions],
            "description": self.description,
        }
        # Emitted only when there is something to say. A record that reserves
        # nothing serializes exactly as it did before this field existed, which
        # is what keeps a frozen model record byte-identical through a
        # round trip; ``from_dict`` reads a missing key as the empty set, so
        # the absent key and an empty list mean the same thing. A record that
        # *does* reserve names carries them, because a reserved namespace that
        # did not survive serialization would be a guard that stopped at a
        # process boundary.
        if self.derived_quantities:
            payload["derived_quantities"] = sorted(self.derived_quantities)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidityDomain":
        require_schema(payload, VALIDITY_DOMAIN_SCHEMA)
        return cls(
            conditions=tuple(
                _decode_condition(c) for c in payload.get("conditions", ())
            ),
            description=payload.get("description", ""),
            derived_quantities=frozenset(payload.get("derived_quantities", ())),
        )


class InputSourceKind(str, Enum):
    """Where a model input must come from in the problem IR."""

    VARIABLE = "variable"
    PARAMETER = "parameter"


class BindingIssueKind(str, Enum):
    """Why a model input could not be bound to the problem."""

    MISSING = "missing"
    WRONG_SOURCE_KIND = "wrong_source_kind"
    WRONG_DIMENSION = "wrong_dimension"
    WRONG_VALUE_TYPE = "wrong_value_type"
    WRONG_ROLE = "wrong_role"


@dataclass(frozen=True)
class ModelInputSpec:
    """A typed requirement, not a bare name.

    ``unit_exemplar`` states the *dimension* the input must have by naming
    any unit of that dimension; binding compares dimensionality, so a model
    declaring ``"kelvin"`` accepts a problem in ``"degC"``.

    ``varies_with`` widens the input from a constant to a **declared curve**.
    Its value is the name of the independent variable the model will accept a
    curve against, and it is a property of the *model's* contract rather than
    of any curve handed to it: the model states which axis it is prepared to
    read, and :meth:`accept_curve` refuses a curve declared against any other.
    That is what stops a caller handing over a table and letting the model
    guess which axis it is. ``None`` -- the default, and what every existing
    input has -- means this input is a constant and a curve is refused
    outright.
    """

    name: str
    source_kind: InputSourceKind
    unit_exemplar: str | None = None
    value_kind: ValueKind | None = None
    role: VariableRole | None = None
    required: bool = True
    description: str = ""
    varies_with: str | None = None

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise InvalidScientificProblem("model input requires a name")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source_kind", InputSourceKind(self.source_kind))
        if self.value_kind is not None:
            object.__setattr__(self, "value_kind", ValueKind(self.value_kind))
        if self.role is not None:
            object.__setattr__(self, "role", VariableRole(self.role))

        if self.unit_exemplar is not None:
            object.__setattr__(
                self,
                "unit_exemplar",
                require_unit(
                    self.unit_exemplar, context=f"model input {name!r}"
                ),
            )
            if self.value_kind is None:
                object.__setattr__(self, "value_kind", ValueKind.QUANTITY)
            elif self.value_kind is not ValueKind.QUANTITY:
                raise InvalidScientificProblem(
                    f"model input {name!r}: unit_exemplar is only meaningful "
                    f"for quantity-valued inputs, not {self.value_kind.value!r}"
                )
        elif self.value_kind is ValueKind.QUANTITY:
            raise InvalidScientificProblem(
                f"model input {name!r}: a quantity-valued input must declare "
                f"a unit_exemplar so its dimension can be checked"
            )

        if self.role is not None and self.source_kind is not InputSourceKind.VARIABLE:
            raise InvalidScientificProblem(
                f"model input {name!r}: role applies to variables only"
            )

        if self.varies_with is not None:
            varies_with = str(self.varies_with).strip()
            if not varies_with:
                raise InvalidScientificProblem(
                    f"model input {name!r}: varies_with must name the "
                    f"independent variable, or be omitted entirely. An empty "
                    f"name declares that the input varies and does not say "
                    f"with what, which is the guess this field exists to stop"
                )
            if varies_with == name:
                raise InvalidScientificProblem(
                    f"model input {name!r}: varies_with names the input "
                    f"itself, which is not a function of anything"
                )
            if self.unit_exemplar is None:
                raise InvalidScientificProblem(
                    f"model input {name!r}: varies_with applies to "
                    f"quantity-valued inputs only, and this one declares no "
                    f"unit_exemplar"
                )
            object.__setattr__(self, "varies_with", varies_with)

    def accept_curve(self, curve: Any) -> None:
        """Refuse a declared curve this input's contract does not cover.

        **The fail-closed gate.** Four ways a curve is refused, and the first
        is the one that matters for a model that never adopted this mechanism:
        an input that declares no ``varies_with`` is a constant, and handing
        it a curve raises rather than being read as a constant, being
        evaluated at some default, or being stored and quietly ignored.

        Returns ``None`` on acceptance; raises
        :class:`~engcore.scientific.errors.InvalidScientificProblem` otherwise.
        """
        from .curves import DeclaredCurve

        if not isinstance(curve, DeclaredCurve):
            raise InvalidScientificProblem(
                f"model input {self.name!r}: a curve must be a DeclaredCurve, "
                f"got {type(curve).__name__}. A bare table, mapping or "
                f"callable states neither which variable it is against nor "
                f"over what interval it is evidence"
            )
        if self.varies_with is None:
            raise InvalidScientificProblem(
                f"model input {self.name!r} is declared as a constant and was "
                f"handed a curve of {self.name!r} against "
                f"{curve.against!r}. A model that reads this input as one "
                f"number cannot be handed a function of state without saying "
                f"so: declare varies_with={curve.against!r} on this input if "
                f"the model evaluates it, and do not if it does not"
            )
        if curve.against != self.varies_with:
            raise InvalidScientificProblem(
                f"model input {self.name!r} accepts a curve against "
                f"{self.varies_with!r}, but this curve is declared against "
                f"{curve.against!r}. The independent variable is part of the "
                f"declaration on both sides and neither side infers it"
            )
        if curve.quantity != self.name:
            raise InvalidScientificProblem(
                f"model input {self.name!r} was handed a curve of "
                f"{curve.quantity!r}; a curve states which quantity it gives "
                f"and this one gives another"
            )
        if dimensionality(curve.unit) != dimensionality(self.unit_exemplar):
            raise InvalidScientificProblem(
                f"model input {self.name!r} expects the dimension of "
                f"{self.unit_exemplar!r} "
                f"[{dimensionality(self.unit_exemplar)}], but its curve gives "
                f"{curve.unit!r} [{dimensionality(curve.unit)}]"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_INPUT_SCHEMA,
            "name": self.name,
            "source_kind": self.source_kind.value,
            "unit_exemplar": self.unit_exemplar,
            "value_kind": self.value_kind.value if self.value_kind else None,
            "role": self.role.value if self.role else None,
            "required": self.required,
            "description": self.description,
            "varies_with": self.varies_with,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelInputSpec":
        require_schema(payload, MODEL_INPUT_SCHEMA)
        value_kind_raw = payload.get("value_kind")
        role_raw = payload.get("role")
        return cls(
            name=payload["name"],
            source_kind=InputSourceKind(payload["source_kind"]),
            unit_exemplar=payload.get("unit_exemplar"),
            value_kind=ValueKind(value_kind_raw) if value_kind_raw else None,
            role=VariableRole(role_raw) if role_raw else None,
            required=_strict_bool(payload, "required", True),
            description=payload.get("description", ""),
            varies_with=payload.get("varies_with"),
        )


@dataclass(frozen=True)
class ModelOutputSpec:
    """A metric the model produces, with the dimension it will carry."""

    metric: str
    unit_exemplar: str
    description: str = ""

    def __post_init__(self) -> None:
        metric = str(self.metric).strip()
        if not metric:
            raise InvalidScientificProblem("model output requires a metric name")
        object.__setattr__(self, "metric", metric)
        object.__setattr__(
            self,
            "unit_exemplar",
            require_unit(self.unit_exemplar, context=f"model output {metric!r}"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_OUTPUT_SCHEMA,
            "metric": self.metric,
            "unit_exemplar": self.unit_exemplar,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelOutputSpec":
        require_schema(payload, MODEL_OUTPUT_SCHEMA)
        return cls(
            metric=payload["metric"],
            unit_exemplar=payload["unit_exemplar"],
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class BindingIssue:
    """One reason a model does not fit a problem."""

    name: str
    kind: BindingIssueKind
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", BindingIssueKind(self.kind))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BINDING_ISSUE_SCHEMA,
            "name": self.name,
            "kind": self.kind.value,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BindingIssue":
        require_schema(payload, BINDING_ISSUE_SCHEMA)
        return cls(
            name=payload["name"],
            kind=BindingIssueKind(payload["kind"]),
            detail=payload.get("detail", ""),
        )


@dataclass(frozen=True)
class ModelBindingReport:
    """Structured outcome of checking a model against a problem.

    A model is compatible only when there are no issues; there is no
    "mostly satisfied" state, because a wrong-dimension binding is not a
    partial success.
    """

    model_id: str
    version: str
    problem_id: str
    valid_bindings: tuple[str, ...] = ()
    issues: tuple[BindingIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "valid_bindings", tuple(self.valid_bindings))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def is_satisfied(self) -> bool:
        return not self.issues

    def of_kind(self, kind: BindingIssueKind) -> tuple[BindingIssue, ...]:
        return tuple(i for i in self.issues if i.kind is BindingIssueKind(kind))

    @property
    def missing(self) -> tuple[BindingIssue, ...]:
        return self.of_kind(BindingIssueKind.MISSING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BINDING_REPORT_SCHEMA,
            "model_id": self.model_id,
            "version": self.version,
            "problem_id": self.problem_id,
            "is_satisfied": self.is_satisfied,
            "valid_bindings": list(self.valid_bindings),
            "issues": [i.to_dict() for i in self.issues],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelBindingReport":
        require_schema(payload, BINDING_REPORT_SCHEMA)
        return cls(
            model_id=payload["model_id"],
            version=payload["version"],
            problem_id=payload["problem_id"],
            valid_bindings=tuple(payload.get("valid_bindings", ())),
            issues=tuple(
                BindingIssue.from_dict(i) for i in payload.get("issues", ())
            ),
        )


#: The value of ``exclusions`` on a record that never declared them.
#:
#: A distinct object, not ``None`` and not ``()``. Both of those read like
#: declarations -- ``None`` like "nothing to say", ``()`` like "excludes
#: nothing" -- and the whole point of the field is that neither of those is
#: what an omission means. This one renders as ``NOT DECLARED`` and is refused
#: at construction, so no model reaches it by writing nothing.
class _NotDeclared:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - display only
        return "NOT_DECLARED"

    def __bool__(self) -> bool:
        return False


NOT_DECLARED = _NotDeclared()

#: The attribute a package defines to state, for a module it contains, that a
#: model built there cannot declare its exclusions.
#:
#: The same mechanism :data:`~engcore.scientific.results.result.
#: UNASSESSED_DECLARATIONS_ATTRIBUTE` uses, for the same reason and with the
#: same shape: a module whose source is byte-pinned by a frozen experiment
#: cannot be edited to pass a new argument, and the position is therefore
#: stated one package above the freeze, in the declaring package's own words.
#:
#: This module knows the *name* and nothing else. Which model is exempt, and
#: why, is the domain layer's business -- the universal core names no domain,
#: which is the layering rule ``test_x2`` enforces over this subtree, and it
#: refused the first version of this field for exactly that.
#:
#: It is not an opt-out. A guard reads the frozen experiment configs and
#: refuses any entry whose module is not actually pinned by one, so the
#: exemption is read off the pins rather than remembered, and it expires the
#: day the freeze does.
UNDECLARED_EXCLUSIONS_ATTRIBUTE = "SCIENTIFIC_UNDECLARED_EXCLUSIONS"


def _exclusions_exempted(module: str) -> str | None:
    """A reason some package states for ``module`` leaving exclusions undeclared.

    Walked only on the failure path, from the nearest package outwards, so the
    closest declaration wins and a distant package cannot quietly override one
    made beside the module.
    """
    parts = module.split(".")
    for depth in range(len(parts) - 1, 0, -1):
        package = sys.modules.get(".".join(parts[:depth]))
        stated = getattr(package, UNDECLARED_EXCLUSIONS_ATTRIBUTE, None)
        if isinstance(stated, Mapping) and module in stated:
            reason = str(stated[module]).strip()
            if reason:
                return reason
    return None


def _constructing_module() -> str:
    """The module building this record. See the sibling in ``results.result``."""
    frame = sys._getframe(1)
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name != __name__ and not name.startswith("dataclasses"):
            return name
        frame = frame.f_back
    return ""  # pragma: no cover - a record built with no caller frame


@dataclass(frozen=True)
class ScientificModelDefinition:
    """A versioned scientific model contract.

    ``exclusions`` states what the model **does not represent**, as distinct
    from ``assumptions``, which states the conditions under which it holds.
    The two are close enough to have been written into one tuple across this
    repository and different enough that a reader needs them apart: "the Biot
    number is small enough" is something a run can be checked against, and
    "no phase change" is not -- it is a phenomenon nobody will be warned about
    because no condition can detect it.

    **Mandatory, and there is no usable default.** Omitting it raises. An
    optional field records whether somebody thought about the question, not
    what the model excludes, and its default reads exactly like a declaration
    -- which is the failure the field was added to end, reproduced one level
    up. The only value reachable by writing nothing is :data:`NOT_DECLARED`,
    which is not a declaration, renders as ``NOT DECLARED``, and is refused.

    **An empty list justifies itself.** ``exclusions=()`` is the claim that
    the model excludes nothing, which is almost never true, so it must be
    accompanied by ``excludes_nothing_because``. A claim that strong is
    allowed and is not free.

    **A model shipped in this repository must declare exclusions, and the rule
    is not enforced here.** It was, briefly, and the constructor is the wrong
    place: this same constructor reads archived records through
    :meth:`from_dict`, and a record written before the field existed genuinely
    does not declare exclusions. Refusing to load it would destroy information
    rather than prevent a claim, and the round-trip test for a legacy record is
    what said so. The rule is about *authoring* a model, and it is enforced
    over the authored population -- every definition reachable in this package
    -- by a repository-wide guard, which owns its own single named exemption:
    one model, in a frozen tree the round that added this field could not
    edit. That name lives with the guard rather than here, for the same reason
    nothing else domain-shaped lives in this package -- the core does not know
    which model it is. What is refused here is a malformed exclusion: a blank
    one, which says nothing while looking like it does.
    """

    model_id: str
    version: str
    name: str = ""
    domain: str = ""
    model_type: ModelType = ModelType.APPROXIMATION
    description: str = ""
    inputs: tuple[ModelInputSpec, ...] = ()
    outputs: tuple[ModelOutputSpec, ...] = ()
    assumptions: tuple[str, ...] = ()
    #: Mandatory. See the class docstring; the default is a sentinel that is
    #: refused, not a value.
    exclusions: tuple[str, ...] = NOT_DECLARED  # type: ignore[assignment]
    #: Required exactly when ``exclusions`` is empty, and refused otherwise.
    excludes_nothing_because: str = ""
    validity: ValidityDomain = field(default_factory=ValidityDomain)
    references: tuple[str, ...] = ()
    required_capabilities: frozenset[str] = frozenset()
    validation_status: ModelValidationStatus = ModelValidationStatus.UNVALIDATED
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("model_id", "version"):
            if not str(getattr(self, label)).strip():
                raise InvalidScientificProblem(f"model requires a non-empty {label}")
            object.__setattr__(self, label, str(getattr(self, label)).strip())
        object.__setattr__(self, "model_type", ModelType(self.model_type))
        object.__setattr__(
            self, "validation_status", ModelValidationStatus(self.validation_status)
        )
        for label in ("inputs", "outputs", "assumptions", "references"):
            object.__setattr__(self, label, tuple(getattr(self, label)))

        # Mandatory. See the class docstring for why an omission may not be
        # read as an empty list, and why the sentinel is not None.
        if self.exclusions is NOT_DECLARED:
            if _exclusions_exempted(_constructing_module()) is None:
                raise InvalidScientificProblem(
                    f"model {self.model_id!r} declares no exclusions. A model "
                    f"is a claim about a physical system, and a claim that "
                    f"does not say what it leaves out -- no phase change, no "
                    f"ageing, no reversible heat, no saturation, whichever it "
                    f"omits -- is a claim a reader cannot assess. A reader of "
                    f"a credibility report cannot read this source. Pass "
                    f"exclusions=(...) with what this model does not "
                    f"represent, or exclusions=() with "
                    f"excludes_nothing_because=... if it truly represents "
                    f"everything in its scope"
                )
        else:
            exclusions = tuple(str(e).strip() for e in self.exclusions)
            if any(not e for e in exclusions):
                raise InvalidScientificProblem(
                    f"model {self.model_id!r} declares an empty exclusion; an "
                    f"exclusion is a sentence about what the model does not "
                    f"represent, and a blank one says nothing while looking "
                    f"like it does"
                )
            object.__setattr__(self, "exclusions", exclusions)

            # An empty list justifies itself. It is the strongest claim this
            # field can carry and the one least often true, so it costs a
            # sentence; every other list is its own justification.
            because = str(self.excludes_nothing_because).strip()
            if not exclusions and not because:
                raise InvalidScientificProblem(
                    f"model {self.model_id!r} declares that it excludes "
                    f"nothing and does not say why. That is a claim to "
                    f"represent every phenomenon in its scope, which is "
                    f"almost never true; if it is true here, say what makes "
                    f"it true in excludes_nothing_because"
                )
            if exclusions and because:
                raise InvalidScientificProblem(
                    f"model {self.model_id!r} declares {len(exclusions)} "
                    f"exclusion(s) and also excludes_nothing_because; the "
                    f"second contradicts the first"
                )
            object.__setattr__(self, "excludes_nothing_because", because)
        input_names = [spec.name for spec in self.inputs]
        duplicated = duplicates(input_names)
        if duplicated:
            raise InvalidScientificProblem(
                f"model {self.model_id!r} has duplicate input names: "
                f"{duplicated}"
            )
        output_names = [spec.metric for spec in self.outputs]
        duplicated = duplicates(output_names)
        if duplicated:
            raise InvalidScientificProblem(
                f"model {self.model_id!r} has duplicate output metrics: "
                f"{duplicated}"
            )
        object.__setattr__(
            self, "required_capabilities", frozenset(self.required_capabilities)
        )
        object.__setattr__(self, "metadata", freeze(dict(self.metadata)))

        # Every context name this model's conditions read must be accounted
        # for: either a declared input, which the caller is *supposed* to
        # supply, or a reserved derived quantity, which no caller may. A third
        # category — a name a condition reads that nothing declares — is the
        # forgery hole, and it is closed here, at import, rather than at the
        # verdict that would otherwise be the first sign of it. A domain adding
        # a dimensionless group to a condition cannot ship it unreserved.
        unclassified = sorted(
            self.validity.context_keys
            - set(input_names)
            - self.validity.derived_quantities
        )
        if unclassified:
            raise InvalidScientificProblem(
                f"model {self.model_id!r} has validity condition(s) reading "
                f"{unclassified}, which is neither a declared model input nor "
                f"a reserved derived quantity. A name in neither category is "
                f"supplied by whatever happens to occupy it in the assessed "
                f"context, including a caller parameter. Declare it as a "
                f"ModelInputSpec if a caller supplies it, or list it in "
                f"validity.derived_quantities if this domain computes it"
            )

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.version)

    @property
    def derived_quantities(self) -> frozenset[str]:
        """The names no caller may supply. See :class:`ValidityDomain`."""
        return self.validity.derived_quantities

    def assess_validity(
        self,
        context: Mapping[str, Any] | None = None,
        *,
        declared: Mapping[str, Any] | None = None,
        assembled: Mapping[str, Any] | None = None,
    ) -> ValidityAssessment:
        return self.validity.assess(
            context, declared=declared, assembled=assembled
        )

    @property
    def provided_metrics(self) -> tuple[str, ...]:
        return tuple(spec.metric for spec in self.outputs)

    def check_against(self, problem) -> ModelBindingReport:
        """Bind this model's typed inputs and outputs to a problem.

        Name matching alone is not binding: a model needing ``temperature``
        is *not* satisfied by a variable called ``temperature`` measured in
        volts, nor by a parameter when it declared it needs a variable.
        Every such mismatch is reported as a typed issue.
        """
        variables = {v.name: v for v in problem.variables}
        parameters = {p.name: p for p in problem.parameters}
        issues: list[BindingIssue] = []
        bound: list[str] = []

        for spec in self.inputs:
            source = (
                variables.get(spec.name)
                if spec.source_kind is InputSourceKind.VARIABLE
                else parameters.get(spec.name)
            )
            if source is None:
                other = (
                    parameters.get(spec.name)
                    if spec.source_kind is InputSourceKind.VARIABLE
                    else variables.get(spec.name)
                )
                if other is not None:
                    issues.append(
                        BindingIssue(
                            spec.name,
                            BindingIssueKind.WRONG_SOURCE_KIND,
                            f"required as {spec.source_kind.value}, but the "
                            f"problem declares it as the other kind",
                        )
                    )
                elif spec.required:
                    issues.append(
                        BindingIssue(
                            spec.name,
                            BindingIssueKind.MISSING,
                            f"problem declares no {spec.source_kind.value} "
                            f"named {spec.name!r}",
                        )
                    )
                continue

            issue = (
                self._check_variable(spec, source)
                if spec.source_kind is InputSourceKind.VARIABLE
                else self._check_parameter(spec, source)
            )
            if issue is None:
                bound.append(spec.name)
            else:
                issues.append(issue)

        issues.extend(self._check_outputs(problem))

        return ModelBindingReport(
            model_id=self.model_id,
            version=self.version,
            problem_id=getattr(problem, "problem_id", ""),
            valid_bindings=tuple(bound),
            issues=tuple(issues),
        )

    def _check_variable(self, spec: ModelInputSpec, variable) -> BindingIssue | None:
        if spec.role is not None and variable.role is not spec.role:
            return BindingIssue(
                spec.name,
                BindingIssueKind.WRONG_ROLE,
                f"expected role {spec.role.value!r}, found "
                f"{variable.role.value!r}",
            )
        if spec.unit_exemplar is not None:
            if dimensionality(variable.unit) != dimensionality(spec.unit_exemplar):
                return BindingIssue(
                    spec.name,
                    BindingIssueKind.WRONG_DIMENSION,
                    f"expected dimension of {spec.unit_exemplar!r} "
                    f"[{dimensionality(spec.unit_exemplar)}], found "
                    f"{variable.unit!r} [{dimensionality(variable.unit)}]",
                )
        return None

    def _check_parameter(self, spec: ModelInputSpec, parameter) -> BindingIssue | None:
        if spec.value_kind is not None and parameter.kind is not spec.value_kind:
            return BindingIssue(
                spec.name,
                BindingIssueKind.WRONG_VALUE_TYPE,
                f"expected {spec.value_kind.value!r} value, found "
                f"{parameter.kind.value!r}",
            )
        if spec.unit_exemplar is not None:
            if parameter.kind is not ValueKind.QUANTITY:
                return BindingIssue(
                    spec.name,
                    BindingIssueKind.WRONG_VALUE_TYPE,
                    f"expected a quantity with the dimension of "
                    f"{spec.unit_exemplar!r}, found "
                    f"{parameter.kind.value!r}",
                )
            found = parameter.value.units
            if dimensionality(found) != dimensionality(spec.unit_exemplar):
                return BindingIssue(
                    spec.name,
                    BindingIssueKind.WRONG_DIMENSION,
                    f"expected dimension of {spec.unit_exemplar!r} "
                    f"[{dimensionality(spec.unit_exemplar)}], found "
                    f"{found!r} [{dimensionality(found)}]",
                )
        return None

    def _check_outputs(self, problem) -> list[BindingIssue]:
        """Outputs must agree dimensionally with metrics the problem declares.

        A metric the problem never references is not an error: a model may
        legitimately produce more than the study asks for.
        """
        declared = getattr(problem, "metric_units", lambda: {})()
        issues: list[BindingIssue] = []
        for spec in self.outputs:
            expected = declared.get(spec.metric)
            if expected is None:
                continue
            if dimensionality(expected) != dimensionality(spec.unit_exemplar):
                issues.append(
                    BindingIssue(
                        spec.metric,
                        BindingIssueKind.WRONG_DIMENSION,
                        f"model produces {spec.metric!r} in "
                        f"{spec.unit_exemplar!r} "
                        f"[{dimensionality(spec.unit_exemplar)}] but the "
                        f"problem declares it as {expected!r} "
                        f"[{dimensionality(expected)}]",
                    )
                )
        return issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_SCHEMA,
            "model_id": self.model_id,
            "version": self.version,
            "name": self.name,
            "domain": self.domain,
            "model_type": self.model_type.value,
            "description": self.description,
            "inputs": [spec.to_dict() for spec in self.inputs],
            "outputs": [spec.to_dict() for spec in self.outputs],
            "assumptions": list(self.assumptions),
            "exclusions": (
                None
                if self.exclusions is NOT_DECLARED
                else list(self.exclusions)
            ),
            "excludes_nothing_because": self.excludes_nothing_because,
            "validity": self.validity.to_dict(),
            "references": list(self.references),
            "required_capabilities": sorted(self.required_capabilities),
            "validation_status": self.validation_status.value,
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificModelDefinition":
        require_schema_any(payload, (MODEL_SCHEMA_V1, MODEL_SCHEMA))
        return cls(
            model_id=payload["model_id"],
            version=payload["version"],
            name=payload.get("name", ""),
            domain=payload.get("domain", ""),
            model_type=ModelType(payload.get("model_type", "approximation")),
            description=payload.get("description", ""),
            inputs=tuple(
                ModelInputSpec.from_dict(s) for s in payload.get("inputs", ())
            ),
            outputs=tuple(
                ModelOutputSpec.from_dict(s) for s in payload.get("outputs", ())
            ),
            assumptions=tuple(payload.get("assumptions", ())),
            # A missing or null key means the record does not say, which is
            # NOT_DECLARED and is refused by the constructor -- so a payload
            # written before this field existed fails loudly rather than
            # reading back as a stronger claim than it carried. `.get` would
            # have read it as "excludes nothing".
            exclusions=(
                NOT_DECLARED
                if payload.get("exclusions") is None
                else tuple(payload["exclusions"])
            ),
            excludes_nothing_because=payload.get("excludes_nothing_because", ""),
            validity=ValidityDomain.from_dict(payload["validity"])
            if payload.get("validity")
            else ValidityDomain(),
            references=tuple(payload.get("references", ())),
            required_capabilities=frozenset(payload.get("required_capabilities", ())),
            validation_status=ModelValidationStatus(
                payload.get("validation_status", "unvalidated")
            ),
            metadata=dict(payload.get("metadata", {})),
        )
