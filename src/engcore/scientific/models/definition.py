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
        reference = self.minimum if self.minimum is not None else self.maximum
        if not value.is_compatible_with(reference):
            raise ModelValidityError(
                f"validity condition {self.name!r}: value {value} is not "
                f"dimensionally compatible with {reference}"
            )
        if self.minimum is not None:
            magnitude = value.to(self.minimum.units).magnitude
            outside = (
                magnitude < self.minimum.magnitude
                if self.minimum_inclusive
                else magnitude <= self.minimum.magnitude
            )
            if outside:
                return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.maximum is not None:
            magnitude = value.to(self.maximum.units).magnitude
            outside = (
                magnitude > self.maximum.magnitude
                if self.maximum_inclusive
                else magnitude >= self.maximum.magnitude
            )
            if outside:
                return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        return ValidityStatus.IN_DOMAIN

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


ValidityCondition = RangeCondition | CategoryCondition | FlagCondition

_CONDITION_DECODERS = {
    RANGE_CONDITION_SCHEMA: RangeCondition,
    CATEGORY_CONDITION_SCHEMA: CategoryCondition,
    FLAG_CONDITION_SCHEMA: FlagCondition,
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
    """The conditions under which a model's results are considered validated."""

    conditions: tuple[ValidityCondition, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "conditions", tuple(self.conditions))
        names = [c.name for c in self.conditions]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ModelValidityError(
                f"duplicate validity condition names: {sorted(duplicates)}"
            )

    def assess(self, context: Mapping[str, Any]) -> ValidityAssessment:
        """Classify a context as in-domain, outside-domain, or unknown.

        A domain with no conditions is UNKNOWN, not valid: absence of declared
        limits is not evidence of unlimited validity.
        """
        if not self.conditions:
            return ValidityAssessment(status=ValidityStatus.UNKNOWN)

        satisfied: list[str] = []
        violated: list[str] = []
        unknown: list[str] = []
        for condition in self.conditions:
            outcome = condition.evaluate(context.get(condition.name))
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VALIDITY_DOMAIN_SCHEMA,
            "conditions": [c.to_dict() for c in self.conditions],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidityDomain":
        require_schema(payload, VALIDITY_DOMAIN_SCHEMA)
        return cls(
            conditions=tuple(
                _decode_condition(c) for c in payload.get("conditions", ())
            ),
            description=payload.get("description", ""),
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

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.version)

    def assess_validity(self, context: Mapping[str, Any]) -> ValidityAssessment:
        return self.validity.assess(context)

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
