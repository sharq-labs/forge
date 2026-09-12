"""ScientificProblem — the top-level domain-neutral problem contract.

Electrical, thermal, mechanics and chemistry must all be expressible through
*this* type. Nothing in it names a physical domain: domains are carried by
model references, capability requirements and units, never by special fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ..errors import InvalidScientificProblem
from ..sequences import duplicates
from ..serialization import require_schema, schema_string, unwritable
from ..units.quantity import Quantity, dimensionality
from ..units.validation import require_same_dimension
from .conditions import BoundaryCondition, BoundaryKind, InitialCondition
from .constraints import ConstraintDefinition
from .objectives import ObjectiveDefinition
from .values import ScientificValue
from .variables import ScientificParameter, ScientificVariable, VariableRole

PROBLEM_SCHEMA = schema_string("scientific_problem")
MODEL_REFERENCE_SCHEMA = schema_string("model_reference")
UNCERTAINTY_SPEC_SCHEMA = schema_string("uncertainty_specification")


@dataclass(frozen=True)
class ModelReference:
    """Points at a registered model without importing it."""

    model_id: str
    version: str

    def __post_init__(self) -> None:
        for label, text in (("model_id", self.model_id), ("version", self.version)):
            if not str(text).strip():
                raise InvalidScientificProblem(
                    f"model reference requires a non-empty {label}"
                )
        object.__setattr__(self, "model_id", str(self.model_id).strip())
        object.__setattr__(self, "version", str(self.version).strip())

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_REFERENCE_SCHEMA,
            "model_id": self.model_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelReference":
        require_schema(payload, MODEL_REFERENCE_SCHEMA)
        return cls(model_id=payload["model_id"], version=payload["version"])


class UncertaintyRequirement(str, Enum):
    """How much uncertainty treatment the study demands of a result."""

    NONE = "none"                # no uncertainty required
    REPORTED = "reported"        # a result must carry an Uncertainty record
    QUANTIFIED = "quantified"    # the record must be an actual estimate


@dataclass(frozen=True)
class UncertaintySpecification:
    """What the problem asks for regarding uncertainty. Requesting it does not
    conjure it: a result still declares UNKNOWN when nothing was computed."""

    requirement: UncertaintyRequirement = UncertaintyRequirement.NONE
    metrics: tuple[str, ...] = ()
    confidence_level: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement", UncertaintyRequirement(self.requirement))
        object.__setattr__(self, "metrics", tuple(self.metrics))
        if self.confidence_level is not None:
            level = float(self.confidence_level)
            if not 0.0 < level < 1.0:
                raise InvalidScientificProblem(
                    "confidence_level must lie strictly between 0 and 1"
                )
            object.__setattr__(self, "confidence_level", level)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_SPEC_SCHEMA,
            "requirement": self.requirement.value,
            "metrics": list(self.metrics),
            "confidence_level": self.confidence_level,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintySpecification":
        require_schema(payload, UNCERTAINTY_SPEC_SCHEMA)
        return cls(
            requirement=UncertaintyRequirement(payload.get("requirement", "none")),
            metrics=tuple(payload.get("metrics", ())),
            confidence_level=payload.get("confidence_level"),
            notes=payload.get("notes", ""),
        )


@dataclass(frozen=True)
class ScientificProblem:
    """A complete, domain-neutral statement of what is to be computed."""

    problem_id: str
    name: str = ""
    description: str = ""
    variables: tuple[ScientificVariable, ...] = ()
    parameters: tuple[ScientificParameter, ...] = ()
    objectives: tuple[ObjectiveDefinition, ...] = ()
    constraints: tuple[ConstraintDefinition, ...] = ()
    initial_conditions: tuple[InitialCondition, ...] = ()
    boundary_conditions: tuple[BoundaryCondition, ...] = ()
    models: tuple[ModelReference, ...] = ()
    required_capabilities: frozenset[str] = frozenset()
    uncertainty: UncertaintySpecification = field(
        default_factory=UncertaintySpecification
    )
    validation_requirements: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        problem_id = str(self.problem_id).strip()
        if not problem_id:
            raise InvalidScientificProblem("problem_id must be non-empty")
        object.__setattr__(self, "problem_id", problem_id)

        for label in (
            "variables", "parameters", "objectives", "constraints",
            "initial_conditions", "boundary_conditions", "models",
        ):
            object.__setattr__(self, label, tuple(getattr(self, label)))
        object.__setattr__(
            self, "required_capabilities", frozenset(self.required_capabilities)
        )
        object.__setattr__(
            self, "validation_requirements", frozenset(self.validation_requirements)
        )
        # `freeze`, not `dict`. The two capability sets above are already
        # `frozenset`s and were safe; this was the one container on the record
        # that a caller could still edit after construction, and a problem is
        # what a solve, a provenance record and every downstream verdict are
        # anchored to.
        #
        # Imported here rather than at module scope: `results` imports
        # `ir.problem` for `ModelReference`, so a top-level import closes a
        # cycle. The same deferral `mcp/evidence.py` already uses for
        # `NOT_DECLARED`, and it costs a `sys.modules` lookup against the
        # validation this method already does.
        from ..results.immutable import freeze

        # The refusal `ScientificResult.metadata`, `ProvenanceRecord.metadata`
        # and `SolverSettings.options` already make. `to_dict` records this
        # mapping with the problem, and it accepted an object, a NaN or an
        # integer key that the record then could not write down, or wrote
        # down as a different value.
        unrecordable = unwritable(self.metadata, path="metadata")
        if unrecordable is not None:
            where, kind = unrecordable
            raise InvalidScientificProblem(
                f"problem {problem_id!r} cannot be recorded: {where} is a "
                f"{kind}, which no scientific record can carry"
            )
        object.__setattr__(self, "metadata", freeze(dict(self.metadata)))

        self._require_unique_names()
        self._require_condition_targets()
        self._require_condition_dimensions()
        self._require_objective_metrics()
        self._require_metric_coherence()

    # ---- invariants ----------------------------------------------------
    def _require_unique_names(self) -> None:
        seen: dict[str, str] = {}
        for kind, items in (
            ("variable", self.variables),
            ("parameter", self.parameters),
        ):
            for item in items:
                if item.name in seen:
                    raise InvalidScientificProblem(
                        f"duplicate name {item.name!r}: declared as "
                        f"{seen[item.name]} and {kind}"
                    )
                seen[item.name] = kind

        for kind, items in (
            ("objective", self.objectives),
            ("constraint", self.constraints),
            ("boundary condition", self.boundary_conditions),
        ):
            names = [item.name for item in items]
            duplicated = duplicates(names)
            if duplicated:
                raise InvalidScientificProblem(
                    f"duplicate {kind} names: {duplicated}"
                )

    def _require_condition_targets(self) -> None:
        known = {v.name for v in self.variables}
        for condition in self.initial_conditions:
            if condition.variable not in known:
                raise InvalidScientificProblem(
                    f"initial condition references unknown variable "
                    f"{condition.variable!r}"
                )
        for condition in self.boundary_conditions:
            if condition.variable not in known:
                raise InvalidScientificProblem(
                    f"boundary condition {condition.name!r} references unknown "
                    f"variable {condition.variable!r}"
                )

    def _require_condition_dimensions(self) -> None:
        """Enforce only the dimension relationships that are true *by
        definition*, and leave the rest to domain/solver adapters.

        * An initial condition **is** the variable's own value at t0, so it
          must share the variable's dimension. Universal.
        * A Dirichlet boundary condition **is** a prescribed value of the
          field, so it must too. Universal.
        * A Neumann condition is a normal derivative or flux — commonly
          ``[variable]/[length]`` or an energy flux entirely unlike the
          variable. Requiring it to match the field would reject correct
          physics, so the core does not check it.
        * Robin mixes coefficients of several different dimensions; periodic
          carries no value. Both are domain-specific.
        """
        units = {v.name: v.unit for v in self.variables}

        for condition in self.initial_conditions:
            require_same_dimension(
                condition.value,
                units[condition.variable],
                context=(
                    f"initial condition on variable "
                    f"{condition.variable!r}"
                ),
            )

        for condition in self.boundary_conditions:
            if condition.kind is not BoundaryKind.DIRICHLET:
                continue  # see docstring: not universally constrained
            if condition.value is None:
                continue
            require_same_dimension(
                condition.value,
                units[condition.variable],
                context=(
                    f"Dirichlet boundary condition {condition.name!r} on "
                    f"variable {condition.variable!r}"
                ),
            )

    def _require_metric_coherence(self) -> None:
        """Reject contradictory unit declarations for one metric.

        An objective measuring ``temperature`` in kelvin alongside a
        constraint bounding ``temperature`` in volts is a specification
        error. Units need not be identical (K and degC, m and cm are fine) —
        only dimensionally compatible.
        """
        declared: dict[str, tuple[str, str]] = {}  # metric -> (unit, source)
        entries = [
            (o.metric, o.unit, f"objective {o.name!r}") for o in self.objectives
        ]
        entries += [
            (c.metric, c.unit, f"constraint {c.name!r}") for c in self.constraints
        ]
        for metric, unit, source in entries:
            if metric not in declared:
                declared[metric] = (unit, source)
                continue
            first_unit, first_source = declared[metric]
            if dimensionality(unit) != dimensionality(first_unit):
                raise InvalidScientificProblem(
                    f"metric {metric!r} is declared with incompatible units: "
                    f"{first_source} uses {first_unit!r} "
                    f"[{dimensionality(first_unit)}] but {source} uses "
                    f"{unit!r} [{dimensionality(unit)}]"
                )

    def _require_objective_metrics(self) -> None:
        if not self.objectives:
            return
        names = [o.metric for o in self.objectives]
        if len(set(names)) != len(names):
            # Two objectives on the same metric is almost always a mistake and
            # is ambiguous for any future scalarization.
            raise InvalidScientificProblem(
                "objectives must reference distinct metrics"
            )

    # ---- accessors -----------------------------------------------------
    @property
    def design_variables(self) -> tuple[ScientificVariable, ...]:
        return tuple(v for v in self.variables if v.role is VariableRole.DESIGN)

    def variable(self, name: str) -> ScientificVariable:
        for candidate in self.variables:
            if candidate.name == name:
                return candidate
        raise InvalidScientificProblem(f"unknown variable {name!r}")

    def parameter(self, name: str) -> ScientificParameter:
        for candidate in self.parameters:
            if candidate.name == name:
                return candidate
        raise InvalidScientificProblem(f"unknown parameter {name!r}")

    def parameter_values(self) -> dict[str, ScientificValue]:
        """Every parameter, at the type it was declared with.

        The union is the honest return type. A parameter holds any member of
        :data:`ScientificValue` — a dimensional Quantity, or an integer count,
        a flag, a category — and this accessor hands them all back unchanged.

        **It is not the right input for provenance.** ``ProvenanceRecord``
        admits Quantity-valued inputs only, so passing this dict wholesale
        works exactly until a problem declares a category, and then fails
        inside whatever runner happens to be building the record rather than
        where the wrong type was introduced. This method was annotated
        ``dict[str, Quantity]`` for precisely that reason and the annotation
        was a lie: no caller was checked against it and none could be, because
        the type it promised is not the type it returns. Use
        :meth:`quantity_parameters` when a Quantity is what the consumer
        requires.
        """
        return {p.name: p.value for p in self.parameters}

    def quantity_parameters(self) -> dict[str, Quantity]:
        """The dimensional parameters alone, for consumers that need Quantities.

        Non-quantity parameters are **left out, not converted**. A category has
        no magnitude and no unit, and there is no defensible Quantity to stand
        in for it; a record that invented one would be recording something the
        problem never declared.

        So a caller reading this gets a truthful subset, and reading
        :meth:`parameter_values` is how to see the rest. That distinction
        matters for provenance in particular: ``inputs`` is a Quantity-only
        contract, and a categorical parameter is not an input it silently
        dropped — it is one that contract was never able to carry.
        """
        return {p.name: p.value for p in self.parameters if p.is_quantity}

    def metric_units(self) -> dict[str, str]:
        """Declared units per referenced metric, for result validation.

        Safe to use as a single source of truth: construction already proved
        that every declaration of a given metric is dimensionally compatible,
        so no contradiction can hide behind this collapse.
        """
        units: dict[str, str] = {}
        for objective in self.objectives:
            units[objective.metric] = objective.unit
        for constraint in self.constraints:
            units.setdefault(constraint.metric, constraint.unit)
        return units

    def validity_context(self, *, reserved: Iterable[str]) -> dict[str, Any]:
        """The **caller-declared** half of a model's validity context.

        Derived from typed parameters — Quantities stay Quantities for range
        predicates, categories and flags unwrap to str/bool. Deliberately not
        sourced from ``metadata``: validity context is a scientific input, not
        a side channel.

        ``reserved`` is the model's :attr:`~engcore.scientific.models.definition.ValidityDomain.derived_quantities`, and it is **required**. There
        is no default and no way to ask for "just the parameters": a caller of
        this method is building the mapping a validity condition will be
        assessed against, and that is precisely the place where the question
        *which of these names is the caller entitled to fill?* has to be
        answered. A signature that let it be omitted would let it be forgotten,
        and every domain that forgot would reopen the same hole independently
        — which is what happened.

        A parameter carrying a reserved name is **refused**. It is not dropped
        and not overwritten, because the two quiet options both answer a
        question the caller was not entitled to ask: a problem asserting its
        own Damkohler number is not a problem whose Damkohler number should be
        silently replaced, it is a problem whose author believes they are
        supplying one. Told, rather than corrected behind their back.

        This does refuse a problem that carries such a parameter for its own
        unrelated purposes. That is the cost, and it is the smaller one: the
        name collides with a quantity this model's conditions read, so there is
        no reading of that problem under which the collision is harmless.

        ``extra`` is gone. What a domain computes is no longer merged in here
        — it goes to ``assess(declared=..., assembled=...)`` as a separate
        namespace, so the two are still distinguishable at the point the
        conditions read them. A single mapping cannot carry that distinction,
        which is why merging was the defect and not the fix.
        """
        reserved = frozenset(reserved)
        context: dict[str, Any] = {
            parameter.name: parameter.context_value()
            for parameter in self.parameters
        }
        forged = sorted(reserved & set(context))
        if forged:
            raise InvalidScientificProblem(
                f"problem {self.problem_id!r} declares parameter(s) {forged}, "
                f"which name quantities the assessing domain derives. A "
                f"declared value cannot occupy a derived quantity's name: the "
                f"condition that reads it cannot tell the two apart, so the "
                f"declaration would be read as evidence the domain computed. "
                f"Rename the parameter"
            )
        return context

    @property
    def is_time_dependent(self) -> bool:
        return bool(self.initial_conditions)

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROBLEM_SCHEMA,
            "problem_id": self.problem_id,
            "name": self.name,
            "description": self.description,
            "variables": [v.to_dict() for v in self.variables],
            "parameters": [p.to_dict() for p in self.parameters],
            "objectives": [o.to_dict() for o in self.objectives],
            "constraints": [c.to_dict() for c in self.constraints],
            "initial_conditions": [c.to_dict() for c in self.initial_conditions],
            "boundary_conditions": [c.to_dict() for c in self.boundary_conditions],
            "models": [m.to_dict() for m in self.models],
            "required_capabilities": sorted(self.required_capabilities),
            "uncertainty": self.uncertainty.to_dict(),
            "validation_requirements": sorted(self.validation_requirements),
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificProblem":
        require_schema(payload, PROBLEM_SCHEMA)
        return cls(
            problem_id=payload["problem_id"],
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            variables=tuple(
                ScientificVariable.from_dict(v)
                for v in payload.get("variables", ())
            ),
            parameters=tuple(
                ScientificParameter.from_dict(p)
                for p in payload.get("parameters", ())
            ),
            objectives=tuple(
                ObjectiveDefinition.from_dict(o)
                for o in payload.get("objectives", ())
            ),
            constraints=tuple(
                ConstraintDefinition.from_dict(c)
                for c in payload.get("constraints", ())
            ),
            initial_conditions=tuple(
                InitialCondition.from_dict(c)
                for c in payload.get("initial_conditions", ())
            ),
            boundary_conditions=tuple(
                BoundaryCondition.from_dict(c)
                for c in payload.get("boundary_conditions", ())
            ),
            models=tuple(
                ModelReference.from_dict(m) for m in payload.get("models", ())
            ),
            required_capabilities=frozenset(payload.get("required_capabilities", ())),
            uncertainty=UncertaintySpecification.from_dict(
                payload["uncertainty"]
            )
            if payload.get("uncertainty")
            else UncertaintySpecification(),
            validation_requirements=frozenset(
                payload.get("validation_requirements", ())
            ),
            metadata=dict(payload.get("metadata", {})),
        )
