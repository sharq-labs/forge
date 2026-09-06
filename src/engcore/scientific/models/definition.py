"""Scientific model definition and validity domain.

A model is not an equation string. It is a versioned scientific claim with
declared requirements, assumptions, a validity domain, references and a
validation status. Recording *when a model is valid* is as important as
recording what it computes — a model evaluated outside its validated domain
must be reportable as such rather than silently trusted.

No physical laws are implemented here, and none are registered by the core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, ModelValidityError
from ..ir.values import ValueKind
from ..ir.variables import VariableRole
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from ..units.validation import require_same_dimension, require_unit

MODEL_SCHEMA = schema_string("scientific_model_definition")
MODEL_INPUT_SCHEMA = schema_string("model_input_spec")
MODEL_OUTPUT_SCHEMA = schema_string("model_output_spec")
BINDING_ISSUE_SCHEMA = schema_string("model_binding_issue")
BINDING_REPORT_SCHEMA = schema_string("model_binding_report")
RANGE_CONDITION_SCHEMA = schema_string("validity_range_condition")
CROSS_LIMIT_CONDITION_SCHEMA = schema_string("validity_cross_limit_condition")
CATEGORY_CONDITION_SCHEMA = schema_string("validity_category_condition")
FLAG_CONDITION_SCHEMA = schema_string("validity_flag_condition")
VALIDITY_DOMAIN_SCHEMA = schema_string("validity_domain")
VALIDITY_ASSESSMENT_SCHEMA = schema_string("validity_assessment")


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
    """

    name: str
    minimum: Quantity | None = None
    maximum: Quantity | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ModelValidityError("range condition requires a name")
        object.__setattr__(self, "name", str(self.name).strip())
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

    def evaluate(self, value: Any) -> ValidityStatus:
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

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        """This condition reads exactly one key: its own name."""
        return self.evaluate(context.get(self.name))

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
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RangeCondition":
        require_schema(payload, RANGE_CONDITION_SCHEMA)
        minimum, maximum = payload.get("minimum"), payload.get("maximum")
        return cls(
            name=payload["name"],
            minimum=Quantity.from_dict(minimum) if minimum else None,
            maximum=Quantity.from_dict(maximum) if maximum else None,
            # Records written before open ranges existed described closed
            # ranges, so a missing flag means inclusive.
            minimum_inclusive=bool(payload.get("minimum_inclusive", True)),
            maximum_inclusive=bool(payload.get("maximum_inclusive", True)),
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
            expected=bool(payload.get("expected", True)),
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
            minimum_inclusive=bool(payload.get("minimum_inclusive", True)),
            maximum_inclusive=bool(payload.get("maximum_inclusive", True)),
            description=payload.get("description", ""),
        )


ValidityCondition = (
    RangeCondition | CategoryCondition | FlagCondition | CrossLimitCondition
)

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


@dataclass(frozen=True)
class ValidityAssessment:
    """Result of testing a validity domain against a context."""

    status: ValidityStatus
    satisfied: tuple[str, ...] = ()
    violated: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VALIDITY_ASSESSMENT_SCHEMA,
            "status": self.status.value,
            "satisfied": list(self.satisfied),
            "violated": list(self.violated),
            "unknown": list(self.unknown),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidityAssessment":
        require_schema(payload, VALIDITY_ASSESSMENT_SCHEMA)
        return cls(
            status=ValidityStatus(payload["status"]),
            satisfied=tuple(payload.get("satisfied", ())),
            violated=tuple(payload.get("violated", ())),
            unknown=tuple(payload.get("unknown", ())),
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
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ModelValidityError(
                f"duplicate validity condition names: {sorted(duplicates)}"
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

        satisfied: list[str] = []
        violated: list[str] = []
        unknown: list[str] = []
        for condition in self.conditions:
            # ``evaluate_in`` rather than ``evaluate(context.get(name))``: a
            # cross-limit condition reads two keys and neither is its own
            # name. Every condition type implements it, and the single-key
            # ones implement it as exactly the lookup this line used to do.
            outcome = condition.evaluate_in(merged)
            if outcome is ValidityStatus.IN_DOMAIN:
                satisfied.append(condition.name)
            elif outcome is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
                violated.append(condition.name)
            else:
                unknown.append(condition.name)

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
    """

    name: str
    source_kind: InputSourceKind
    unit_exemplar: str | None = None
    value_kind: ValueKind | None = None
    role: VariableRole | None = None
    required: bool = True
    description: str = ""

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
            required=bool(payload.get("required", True)),
            description=payload.get("description", ""),
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


@dataclass(frozen=True)
class ScientificModelDefinition:
    """A versioned scientific model contract."""

    model_id: str
    version: str
    name: str = ""
    domain: str = ""
    model_type: ModelType = ModelType.APPROXIMATION
    description: str = ""
    inputs: tuple[ModelInputSpec, ...] = ()
    outputs: tuple[ModelOutputSpec, ...] = ()
    assumptions: tuple[str, ...] = ()
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
        input_names = [spec.name for spec in self.inputs]
        duplicates = {n for n in input_names if input_names.count(n) > 1}
        if duplicates:
            raise InvalidScientificProblem(
                f"model {self.model_id!r} has duplicate input names: "
                f"{sorted(duplicates)}"
            )
        output_names = [spec.metric for spec in self.outputs]
        duplicates = {n for n in output_names if output_names.count(n) > 1}
        if duplicates:
            raise InvalidScientificProblem(
                f"model {self.model_id!r} has duplicate output metrics: "
                f"{sorted(duplicates)}"
            )
        object.__setattr__(
            self, "required_capabilities", frozenset(self.required_capabilities)
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

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
            "validity": self.validity.to_dict(),
            "references": list(self.references),
            "required_capabilities": sorted(self.required_capabilities),
            "validation_status": self.validation_status.value,
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificModelDefinition":
        require_schema(payload, MODEL_SCHEMA)
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
