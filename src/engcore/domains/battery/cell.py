"""The cell and load declarations, the problem builders, and the assessments.

A :class:`CellSpecification` is what a cell *is*: five numbers plus whatever
optional limits the caller can state about where its own models stop. A
:class:`DischargeLoad` is what is being asked of it: a current, a starting
state of charge, a temperature and an interval.

The split is deliberate and is the same one the sibling thermal domain makes
between a body and its operating point. The same cell under two loads is one
cell; that is what :attr:`CellSpecification.physical_key` says, and it is why
neither the load nor the optional limits appear in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.conditions import InitialCondition
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.ir.variables import (
    ScientificParameter,
    ScientificVariable,
    VariableRole,
)
from ...scientific.models.definition import ValidityAssessment
from ...scientific.serialization import require_schema, schema_string
from ...scientific.units.quantity import Quantity
from ..derived_context import assembled_validity_context, caller_declared
from . import context as ctx
from . import models as mdl

CELL_SPECIFICATION_SCHEMA = schema_string("battery_cell_specification")
DISCHARGE_LOAD_SCHEMA = schema_string("battery_discharge_load")


def _required(value: Any, unit: str, label: str, *, positive: bool = False) -> Quantity:
    """A required declaration, checked. ``None`` is refused, not tolerated.

    The mirror of :func:`context._checked`: that one exists so an *absent*
    optional declaration becomes UNKNOWN, this one exists so an absent
    *required* declaration is a construction error. Collapsing the two would
    let a cell with no capacity be built and then report UNKNOWN about it.
    """
    checked = ctx._checked(value, unit, label, positive=positive)
    if checked is None:
        raise InvalidScientificProblem(
            f"{label} is required and was not declared"
        )
    return checked


@dataclass(frozen=True)
class CellSpecification:
    """One declared cell, or one series string treated as a single cell.

    The five required fields are the cell's constitutive declaration: what
    charge it holds, what it drops under load, and what its terminals sit at
    when they are open. ``limits`` is optional and defaults to an empty
    :class:`~engcore.domains.battery.context.CellLimits`, which is the honest
    starting point — a cell about which nothing beyond those five was said
    supports no applicability verdict except UNKNOWN.

    ``chemistry`` is **inert**, exactly as ``limits.cooling_mode`` is. It is
    validated against :data:`~engcore.domains.battery.context.
    CHEMISTRY_VOCABULARY`, serialized with this record, and read by no
    derivation and no condition. It records why a caller believes their
    declared ratings and spans are credible; it never substitutes for them. A
    verdict that could be moved by asserting a chemistry would be a verdict
    resting on an unverifiable claim by the party being assessed.
    """

    cell_id: str
    nominal_capacity: Quantity
    internal_resistance: Quantity
    open_circuit_voltage_at_full: Quantity
    open_circuit_voltage_at_empty: Quantity
    coulombic_efficiency: Quantity = field(
        default_factory=lambda: Quantity(1.0, ctx.DIMENSIONLESS)
    )
    limits: ctx.CellLimits = field(default_factory=ctx.CellLimits)
    chemistry: str | None = None

    def __post_init__(self) -> None:
        cell_id = str(self.cell_id).strip()
        if not cell_id:
            raise InvalidScientificProblem("a cell requires a cell_id")
        object.__setattr__(self, "cell_id", cell_id)
        if not isinstance(self.limits, ctx.CellLimits):
            raise InvalidScientificProblem(
                f"limits must be a CellLimits, got {type(self.limits).__name__}"
            )

        object.__setattr__(
            self,
            "nominal_capacity",
            _required(
                self.nominal_capacity,
                ctx.CAPACITY_UNIT,
                ctx.NOMINAL_CAPACITY,
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "internal_resistance",
            _required(
                self.internal_resistance,
                ctx.RESISTANCE_UNIT,
                ctx.INTERNAL_RESISTANCE,
                positive=True,
            ),
        )
        for label in (ctx.OCV_AT_FULL, ctx.OCV_AT_EMPTY):
            object.__setattr__(
                self,
                label,
                _required(getattr(self, label), ctx.VOLTAGE_UNIT, label),
            )
        object.__setattr__(
            self,
            "coulombic_efficiency",
            _required(
                self.coulombic_efficiency,
                ctx.DIMENSIONLESS,
                ctx.COULOMBIC_EFFICIENCY,
                positive=True,
            ),
        )

        # A coulombic efficiency above 1 credits the cell with more charge
        # than crossed its terminals. That is not an optimistic number, it is
        # a violation of the charge balance the counter states.
        efficiency = self.coulombic_efficiency.magnitude_in(ctx.DIMENSIONLESS)
        if efficiency > 1.0:
            raise InvalidScientificProblem(
                f"{ctx.COULOMBIC_EFFICIENCY} must lie in (0, 1], got "
                f"{efficiency!r}"
            )

        # The OCV chord must rise with state of charge. A flat or falling
        # chord makes the voltage-to-charge relation non-invertible, so a
        # cutoff voltage would name no state of charge and the runtime model
        # would silently produce a number from a division by zero.
        low = self.open_circuit_voltage_at_empty.magnitude_in(ctx.VOLTAGE_UNIT)
        high = self.open_circuit_voltage_at_full.magnitude_in(ctx.VOLTAGE_UNIT)
        if high <= low:
            raise InvalidScientificProblem(
                f"{ctx.OCV_AT_FULL} must exceed {ctx.OCV_AT_EMPTY}, got "
                f"{high!r} and {low!r}: a cell whose open-circuit voltage does "
                f"not rise with charge has no invertible relation between the "
                f"two, and every cutoff and runtime here rests on one"
            )

        if self.chemistry is not None:
            chemistry = str(self.chemistry).strip()
            if chemistry not in ctx.CHEMISTRY_VOCABULARY:
                raise InvalidScientificProblem(
                    f"chemistry must be one of "
                    f"{list(ctx.CHEMISTRY_VOCABULARY)}, got {chemistry!r}"
                )
            object.__setattr__(self, "chemistry", chemistry)

    @property
    def physical_key(self) -> tuple[str, float, float, float, float, float]:
        """What makes this *this cell*: its id and its five declared numbers.

        The limits and the chemistry are excluded deliberately. A cell declared
        with a Peukert exponent and one declared without are the same cell
        known to different depth, exactly as the sibling thermal domain's body
        is the same body with and without its conductivity. Including them
        would make supplying evidence about a cell into a change of physical
        identity — and would let a caller change what a solver considers the
        same system by asserting a string.
        """
        return (
            self.cell_id,
            self.nominal_capacity.magnitude_in(ctx.CAPACITY_UNIT),
            self.internal_resistance.magnitude_in(ctx.RESISTANCE_UNIT),
            self.open_circuit_voltage_at_full.magnitude_in(ctx.VOLTAGE_UNIT),
            self.open_circuit_voltage_at_empty.magnitude_in(ctx.VOLTAGE_UNIT),
            self.coulombic_efficiency.magnitude_in(ctx.DIMENSIONLESS),
        )

    def open_circuit_voltage(self, state_of_charge: Quantity) -> Quantity | None:
        """OCV on this cell's declared chord. A convenience over ``context``."""
        return ctx.open_circuit_voltage(
            state_of_charge=state_of_charge,
            ocv_at_empty=self.open_circuit_voltage_at_empty,
            ocv_at_full=self.open_circuit_voltage_at_full,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CELL_SPECIFICATION_SCHEMA,
            "cell_id": self.cell_id,
            ctx.NOMINAL_CAPACITY: self.nominal_capacity.to_dict(),
            ctx.INTERNAL_RESISTANCE: self.internal_resistance.to_dict(),
            ctx.OCV_AT_FULL: self.open_circuit_voltage_at_full.to_dict(),
            ctx.OCV_AT_EMPTY: self.open_circuit_voltage_at_empty.to_dict(),
            ctx.COULOMBIC_EFFICIENCY: self.coulombic_efficiency.to_dict(),
            "limits": self.limits.to_dict(),
            "chemistry": self.chemistry,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CellSpecification":
        require_schema(payload, CELL_SPECIFICATION_SCHEMA)
        return cls(
            cell_id=payload["cell_id"],
            nominal_capacity=Quantity.from_dict(payload[ctx.NOMINAL_CAPACITY]),
            internal_resistance=Quantity.from_dict(
                payload[ctx.INTERNAL_RESISTANCE]
            ),
            open_circuit_voltage_at_full=Quantity.from_dict(
                payload[ctx.OCV_AT_FULL]
            ),
            open_circuit_voltage_at_empty=Quantity.from_dict(
                payload[ctx.OCV_AT_EMPTY]
            ),
            coulombic_efficiency=Quantity.from_dict(
                payload[ctx.COULOMBIC_EFFICIENCY]
            ),
            limits=ctx.CellLimits.from_dict(payload["limits"]),
            chemistry=payload.get("chemistry"),
        )


@dataclass(frozen=True)
class DischargeLoad:
    """What is being asked of the cell over one interval.

    Four required fields state the operating point. The four optional ones
    state a duty and a stopping rule; each is ``None`` when not declared, and
    each omission leaves the conditions that need it UNKNOWN rather than
    satisfied.

    ``duty_type`` is **inert**, on the same footing as
    :attr:`CellSpecification.chemistry`: validated, serialized, read by
    nothing. A caller declaring ``"pulsed"`` does not thereby satisfy the pulse
    conditions — a declared pulse current and a declared pulse duration do, and
    a string never does.
    """

    load_id: str
    current: Quantity
    initial_state_of_charge: Quantity
    cell_temperature: Quantity
    duration: Quantity
    pulse_current: Quantity | None = None
    pulse_duration: Quantity | None = None
    cutoff_voltage: Quantity | None = None
    cutoff_state_of_charge: Quantity | None = None
    duty_type: str | None = None

    def __post_init__(self) -> None:
        load_id = str(self.load_id).strip()
        if not load_id:
            raise InvalidScientificProblem("a load requires a load_id")
        object.__setattr__(self, "load_id", load_id)

        object.__setattr__(
            self,
            "current",
            _required(
                self.current, ctx.CURRENT_UNIT, ctx.DISCHARGE_CURRENT,
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "initial_state_of_charge",
            _required(
                self.initial_state_of_charge,
                ctx.DIMENSIONLESS,
                ctx.STATE_OF_CHARGE,
            ),
        )
        object.__setattr__(
            self,
            "cell_temperature",
            _required(
                self.cell_temperature,
                ctx.TEMPERATURE_UNIT,
                ctx.CELL_TEMPERATURE,
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "duration",
            _required(self.duration, ctx.TIME_UNIT, ctx.DURATION, positive=True),
        )

        for label, unit, positive in (
            (ctx.PULSE_CURRENT, ctx.CURRENT_UNIT, True),
            (ctx.PULSE_DURATION, ctx.TIME_UNIT, True),
            (ctx.CUTOFF_VOLTAGE, ctx.VOLTAGE_UNIT, False),
            (ctx.CUTOFF_STATE_OF_CHARGE, ctx.DIMENSIONLESS, False),
        ):
            object.__setattr__(
                self,
                label,
                ctx._checked(getattr(self, label), unit, label, positive=positive),
            )

        for label in (ctx.STATE_OF_CHARGE, ctx.CUTOFF_STATE_OF_CHARGE):
            value = (
                self.initial_state_of_charge
                if label == ctx.STATE_OF_CHARGE
                else self.cutoff_state_of_charge
            )
            if value is None:
                continue
            fraction = value.magnitude_in(ctx.DIMENSIONLESS)
            if not 0.0 <= fraction <= 1.0:
                raise InvalidScientificProblem(
                    f"{label} must lie in [0, 1], got {fraction!r}"
                )

        if self.duty_type is not None:
            duty = str(self.duty_type).strip()
            if duty not in ctx.DUTY_TYPE_VOCABULARY:
                raise InvalidScientificProblem(
                    f"duty_type must be one of "
                    f"{list(ctx.DUTY_TYPE_VOCABULARY)}, got {duty!r}"
                )
            object.__setattr__(self, "duty_type", duty)

    def to_dict(self) -> dict[str, Any]:
        def encode(value: Quantity | None) -> dict[str, Any] | None:
            return value.to_dict() if value is not None else None

        return {
            "schema": DISCHARGE_LOAD_SCHEMA,
            "load_id": self.load_id,
            "current": self.current.to_dict(),
            "initial_state_of_charge": self.initial_state_of_charge.to_dict(),
            ctx.CELL_TEMPERATURE: self.cell_temperature.to_dict(),
            ctx.DURATION: self.duration.to_dict(),
            ctx.PULSE_CURRENT: encode(self.pulse_current),
            ctx.PULSE_DURATION: encode(self.pulse_duration),
            ctx.CUTOFF_VOLTAGE: encode(self.cutoff_voltage),
            ctx.CUTOFF_STATE_OF_CHARGE: encode(self.cutoff_state_of_charge),
            "duty_type": self.duty_type,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DischargeLoad":
        require_schema(payload, DISCHARGE_LOAD_SCHEMA)

        def decode(key: str) -> Quantity | None:
            raw = payload.get(key)
            return Quantity.from_dict(raw) if raw else None

        return cls(
            load_id=payload["load_id"],
            current=Quantity.from_dict(payload["current"]),
            initial_state_of_charge=Quantity.from_dict(
                payload["initial_state_of_charge"]
            ),
            cell_temperature=Quantity.from_dict(payload[ctx.CELL_TEMPERATURE]),
            duration=Quantity.from_dict(payload[ctx.DURATION]),
            pulse_current=decode(ctx.PULSE_CURRENT),
            pulse_duration=decode(ctx.PULSE_DURATION),
            cutoff_voltage=decode(ctx.CUTOFF_VOLTAGE),
            cutoff_state_of_charge=decode(ctx.CUTOFF_STATE_OF_CHARGE),
            duty_type=payload.get("duty_type"),
        )

    def at(
        self,
        *,
        state_of_charge: Quantity | None = None,
        cell_temperature: Quantity | None = None,
        duration: Quantity | None = None,
    ) -> "DischargeLoad":
        """The same duty at a different operating point.

        Used by the coupling module to march the same declared load forward
        through a sequence of states without rebuilding the duty declaration
        each time. Every other field, including the inert ``duty_type``, is
        carried across unchanged.
        """
        return DischargeLoad(
            load_id=self.load_id,
            current=self.current,
            initial_state_of_charge=(
                self.initial_state_of_charge
                if state_of_charge is None
                else state_of_charge
            ),
            cell_temperature=(
                self.cell_temperature
                if cell_temperature is None
                else cell_temperature
            ),
            duration=self.duration if duration is None else duration,
            pulse_current=self.pulse_current,
            pulse_duration=self.pulse_duration,
            cutoff_voltage=self.cutoff_voltage,
            cutoff_state_of_charge=self.cutoff_state_of_charge,
            duty_type=self.duty_type,
        )


# =====================================================================
# Problem construction
# =====================================================================

def _limit_parameters(limits: ctx.CellLimits) -> tuple[ScientificParameter, ...]:
    """The declared limits as problem parameters, in the table's fixed order.

    A limit left as ``None`` produces **no parameter**. That is the mechanism
    by which "not declared" survives all the way to ``ValidityDomain.assess``
    as UNKNOWN: there is no placeholder value anywhere on this path, so no
    condition can be satisfied by an omission.

    ``cooling_mode`` produces no parameter either, and for a different reason
    that is worth stating separately: it is a category, and a category is not
    something a verdict here may rest on. It stays on the declaration record
    where a reader can see it and no derivation can.
    """
    return tuple(
        ScientificParameter(
            name=spec.name,
            value=getattr(limits, spec.name),
            description=spec.description,
        )
        for spec in ctx.LIMIT_SPECS
        if getattr(limits, spec.name) is not None
    )


def _load_parameters(load: DischargeLoad) -> tuple[ScientificParameter, ...]:
    """The duty and the stopping rule as problem parameters, in fixed order.

    Same discipline as :func:`_limit_parameters`: an undeclared pulse or an
    undeclared cutoff produces no parameter, and ``duty_type`` produces none
    at all.
    """
    declared: tuple[tuple[str, Quantity | None, str], ...] = (
        (ctx.DURATION, load.duration, "Length of the interval to advance."),
        (
            ctx.PULSE_CURRENT,
            load.pulse_current,
            "Peak current the declared duty reaches.",
        ),
        (
            ctx.PULSE_DURATION,
            load.pulse_duration,
            "Length of that pulse.",
        ),
        (
            ctx.CUTOFF_VOLTAGE,
            load.cutoff_voltage,
            "Terminal voltage at which the run is declared to stop.",
        ),
        (
            ctx.CUTOFF_STATE_OF_CHARGE,
            load.cutoff_state_of_charge,
            "State of charge at which the run is declared to stop.",
        ),
    )
    return tuple(
        ScientificParameter(name=name, value=value, description=description)
        for name, value, description in declared
        if value is not None
    )


def build_battery_problem(
    cell: CellSpecification,
    load: DischargeLoad,
    *,
    problem_id: str | None = None,
) -> ScientificProblem:
    """The universal problem statement for one cell under one load.

    ``discharge_current`` and ``cell_temperature`` are declared as **variables
    with role CONTROL and STATE** rather than as parameters, and carry no
    value in the problem. A parameter is a configured value of the problem;
    these are imposed on it from outside. ``state_of_charge`` is a STATE
    variable *and* carries an initial condition, because it is the one
    quantity this domain actually evolves — the distinction between a state
    this domain integrates and a state it is handed is a typed fact here, not
    a naming habit.

    Whatever the cell's ``limits`` and the load's duty carry is emitted as
    extra parameters, and whatever they leave out is emitted as nothing at all.
    The problem therefore transports exactly the evidence it was given: one
    serialized, sent elsewhere and rebuilt supports the same verdict, and one
    built from a bare cell supports only UNKNOWN.

    Every model in the domain is referenced, because a problem carrying a cell
    and a load states enough for each of the four to be *asked about* — and
    answering UNKNOWN is an answer. Which of them a caller then believes is
    the caller's decision, which is why they are four records.
    """
    return ScientificProblem(
        problem_id=problem_id or f"battery-cell-{cell.cell_id}-{load.load_id}",
        name=f"Cell {cell.cell_id} under load {load.load_id}",
        description=(
            "Terminal voltage, state of charge, heat and runtime of one "
            "equivalent-circuit cell over a single interval of constant "
            "discharge current."
        ),
        variables=(
            ScientificVariable(
                name=ctx.STATE_OF_CHARGE,
                unit=ctx.DIMENSIONLESS,
                role=VariableRole.STATE,
                description="Cell state of charge; evolves over the interval.",
            ),
            ScientificVariable(
                name=ctx.DISCHARGE_CURRENT,
                unit=ctx.CURRENT_UNIT,
                role=VariableRole.CONTROL,
                description="Externally imposed current drawn from the cell.",
            ),
            ScientificVariable(
                name=ctx.CELL_TEMPERATURE,
                unit=ctx.TEMPERATURE_UNIT,
                role=VariableRole.STATE,
                description=(
                    "Cell temperature; supplied from outside this problem and "
                    "never inferred within it."
                ),
            ),
        ),
        parameters=(
            ScientificParameter(
                name=ctx.NOMINAL_CAPACITY,
                value=cell.nominal_capacity,
                description="Charge the cell is rated to deliver.",
            ),
            ScientificParameter(
                name=ctx.INTERNAL_RESISTANCE,
                value=cell.internal_resistance,
                description="Series resistance of the Rint circuit.",
            ),
            ScientificParameter(
                name=ctx.OCV_AT_FULL,
                value=cell.open_circuit_voltage_at_full,
                description="Open-circuit voltage at a state of charge of 1.",
            ),
            ScientificParameter(
                name=ctx.OCV_AT_EMPTY,
                value=cell.open_circuit_voltage_at_empty,
                description="Open-circuit voltage at a state of charge of 0.",
            ),
            ScientificParameter(
                name=ctx.COULOMBIC_EFFICIENCY,
                value=cell.coulombic_efficiency,
                description="Charge debited per charge drawn, in (0, 1].",
            ),
        )
        + _load_parameters(load)
        + _limit_parameters(cell.limits),
        initial_conditions=(
            InitialCondition(
                variable=ctx.STATE_OF_CHARGE,
                value=load.initial_state_of_charge,
                description="State of charge at the start of the interval.",
            ),
        ),
        models=tuple(
            ModelReference(model.model_id, model.version)
            for model in mdl.BATTERY_MODELS
        ),
        required_capabilities=frozenset({mdl.CELL_DISCHARGE_STEP.name}),
    )


# =====================================================================
# Validity
# =====================================================================

def battery_validity_context(
    problem: ScientificProblem,
    *,
    state_of_charge: Quantity | None = None,
    discharge_current: Quantity | None = None,
    cell_temperature: Quantity | None = None,
) -> dict[str, Any]:
    """The full context every ``assess_*`` below consumes.

    The problem's own parameters, plus every quantity
    :func:`~engcore.domains.battery.context.derived_cell_quantities` could form
    from them and from the supplied state. The three keyword arguments are
    variables, and :meth:`ScientificProblem.validity_context` is built from
    *parameters*, so they cannot arrive any other way. That limitation belongs
    to the sibling domains too, is recorded in ``NEEDS.md`` as a finding, and
    is not worked around here either.

    Every one of the three is a ``Quantity``, so everything this function feeds
    into a verdict is something ``ProvenanceRecord`` can record. No categorical
    declaration reaches a condition through this path or any other.

    Omitting an argument omits every quantity that needed it. It never
    substitutes one — and since F03 that is structural rather than intended.
    The state coordinates and every derived group are a **reserved namespace**,
    stripped from the caller's context before anything is assembled, so a
    caller parameter called ``cell_temperature`` or ``peukert_capacity_ratio``
    cannot occupy the key an absent argument or a failed derivation left empty.
    Assembly used to start from the caller's parameters and overwrite only what
    it managed to compute, which meant precisely the opposite.
    """
    declared = caller_declared(
        problem.validity_context(), ctx.ASSEMBLED_QUANTITIES
    )
    state = {
        name: value
        for name, value in (
            (ctx.STATE_OF_CHARGE, state_of_charge),
            (ctx.DISCHARGE_CURRENT, discharge_current),
            (ctx.CELL_TEMPERATURE, cell_temperature),
        )
        if value is not None
    }
    return assembled_validity_context(
        declared=declared,
        assembled={
            **state,
            **ctx.derived_cell_quantities(
                {**declared, **state},
                state_of_charge=state_of_charge,
                discharge_current=discharge_current,
                cell_temperature=cell_temperature,
            ),
        },
        reserved=ctx.ASSEMBLED_QUANTITIES,
    )


def _assess(
    model,
    problem: ScientificProblem,
    state_of_charge: Quantity | None,
    discharge_current: Quantity | None,
    cell_temperature: Quantity | None,
) -> ValidityAssessment:
    return model.assess_validity(
        battery_validity_context(
            problem,
            state_of_charge=state_of_charge,
            discharge_current=discharge_current,
            cell_temperature=cell_temperature,
        )
    )


def assess_rint_validity(
    problem: ScientificProblem,
    *,
    state_of_charge: Quantity | None = None,
    discharge_current: Quantity | None = None,
    cell_temperature: Quantity | None = None,
) -> ValidityAssessment:
    """Is the Rint circuit applicable to this cell at this operating point?

    **Validity, not validation** — the same separation the sibling domains
    keep, and for the same reason: *was this model applicable* and *was this
    result checked* are different questions with different answers, and the
    platform holds them on different fields so neither can quietly stand in for
    the other. A cell model evaluated to machine precision outside its rated
    current is still evaluated to machine precision, and this function is what
    makes the second half of that sentence sayable.

    Every argument is a measured or declared ``Quantity``. There is no
    parameter here through which a caller can assert their way to IN_DOMAIN.
    """
    return _assess(
        mdl.RINT_OCV_MODEL,
        problem,
        state_of_charge,
        discharge_current,
        cell_temperature,
    )


def assess_coulomb_counting_validity(
    problem: ScientificProblem,
    *,
    state_of_charge: Quantity | None = None,
    discharge_current: Quantity | None = None,
    cell_temperature: Quantity | None = None,
) -> ValidityAssessment:
    """Is the charge balance applicable to this step?

    Independent of :func:`assess_rint_validity` by construction: a cell whose
    terminal voltage the Rint circuit describes badly may still have its charge
    counted correctly, and the two verdicts are meant to be able to disagree.
    """
    return _assess(
        mdl.COULOMB_COUNTING_MODEL,
        problem,
        state_of_charge,
        discharge_current,
        cell_temperature,
    )


def assess_runtime_validity(
    problem: ScientificProblem,
    *,
    state_of_charge: Quantity | None = None,
    discharge_current: Quantity | None = None,
    cell_temperature: Quantity | None = None,
) -> ValidityAssessment:
    """Is a runtime to the declared cutoffs a claim this domain can make?

    The condition that only this assessment carries is the consistency of the
    two cutoffs at this load, which neither of the other two models can see.
    """
    return _assess(
        mdl.CONSTANT_CURRENT_RUNTIME_MODEL,
        problem,
        state_of_charge,
        discharge_current,
        cell_temperature,
    )


def assess_peukert_validity(
    problem: ScientificProblem,
    *,
    state_of_charge: Quantity | None = None,
    discharge_current: Quantity | None = None,
    cell_temperature: Quantity | None = None,
) -> ValidityAssessment:
    """Is the fitted rate-capacity law applicable at this current?

    Deliberately its own assessment over its own record. A caller may accept
    every other claim in this domain and reject this one, which is exactly what
    a fitted correlation with a contested exponent deserves.
    """
    return _assess(
        mdl.PEUKERT_DERATING_MODEL,
        problem,
        state_of_charge,
        discharge_current,
        cell_temperature,
    )


def assess_all(
    problem: ScientificProblem,
    *,
    state_of_charge: Quantity | None = None,
    discharge_current: Quantity | None = None,
    cell_temperature: Quantity | None = None,
) -> dict[str, ValidityAssessment]:
    """Every model's verdict, keyed by model id, from one context build.

    A convenience, and deliberately a ``dict`` of separate assessments rather
    than a combined verdict. There is no meaningful way to reduce four
    independent claims to one status: a run may be inside the charge balance's
    domain and outside the Rint circuit's, and a consumer needs to know which.
    """
    context = battery_validity_context(
        problem,
        state_of_charge=state_of_charge,
        discharge_current=discharge_current,
        cell_temperature=cell_temperature,
    )
    return {
        model.model_id: model.assess_validity(context)
        for model in mdl.BATTERY_MODELS
    }
