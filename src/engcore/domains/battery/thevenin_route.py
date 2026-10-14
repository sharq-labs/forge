"""The one-RC Thevenin cell as a scientific execution route (battery.thevenin_1rc, Rock A).

:mod:`.thevenin` is the exact kernel for ONE constant-current interval. This module turns it into a route that
FORGE can execute, attribute and replay:

* a formal model record, :data:`THEVENIN_1RC_MODEL` (``battery.cell.thevenin_1rc``), its realization
  :data:`THEVENIN_1RC_REALIZATION`, and a solver, :class:`Thevenin1RCSolver`, that satisfies the solver protocol;
* typed inputs: a :class:`Thevenin1RCParameterSet` (R0, OCV, capacity and efficiency through the existing
  :class:`~engcore.domains.battery.cell.CellSpecification`, R1 and C1 through
  :class:`~engcore.domains.battery.thevenin.Thevenin1RCParameters`, plus the temperature range and the maximum
  discharge current the set is declared for), an explicit :class:`Thevenin1RCInitialState` (SOC **and**
  polarization voltage, with the stated basis for both) and a chronological :class:`DischargeRestProfile`;
* :func:`run_thevenin_1rc`, which marches the profile, assesses the model's validity domain over the whole march
  and returns a :class:`~engcore.scientific.results.result.ScientificResult` whose provenance is built from the
  execution itself;
* :func:`replay_thevenin_1rc`, which re-executes a :class:`Thevenin1RCReplayRecord` and refuses a stale,
  altered or non-reproducing record.

Sign convention: **positive current is discharge**, stated on every profile and refused otherwise. Zero current
is rest. Negative current (charge) and hysteresis are outside the model and refused, never mapped. A step that
would leave SOC in [0, 1] is refused, never clipped.

What this module does NOT establish: that any parameter set describes a real cell, that the model is adequate
for any measured trajectory, or any measurement, parameter or model-form uncertainty. Every output carries
UNKNOWN uncertainty. ``validation_status`` is SELF_CONSISTENT: the closed form is checked against independent
analytic references (tests/domains/battery/test_thevenin_route.py), not against measurements. The route is
deliberately NOT registered in the production capability registry, the MCP boundary or the battery domain pack.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ...scientific.capabilities import ScientificCapability
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.conditions import InitialCondition
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.ir.variables import ScientificParameter, ScientificVariable, VariableRole
from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
)
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
    RealizationReference,
)
from ...scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.capability import CoreCapabilities, SolverCapability, SolverCapabilityId
from ...scientific.solvers.protocol import (
    ConvergenceState,
    DeclaredSupport,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ...scientific.units.quantity import Quantity
from . import context as ctx
from .cell import CellSpecification
from .thevenin import (
    POLARIZATION_CAPACITANCE,
    POLARIZATION_RESISTANCE,
    POLARIZATION_VOLTAGE,
    Thevenin1RCParameters,
    TheveninState,
    evaluate_thevenin_step,
)

MODEL_ID = "battery.cell.thevenin_1rc"
MODEL_VERSION = "0.1.0"
REALIZATION_ID = f"{MODEL_ID}.exact_piecewise_constant"
REALIZATION_VERSION = "0.1.0"
SOLVER_ID = "engcore.battery.thevenin_1rc_march"
SOLVER_VERSION = "0.1.0"
BACKEND = "python.float"
REPLAY_SCHEMA = "forge.battery.thevenin_1rc_replay/1"
PARAMETER_SET_SCHEMA = "forge.battery.thevenin_1rc_parameter_set/1"
POSITIVE_DISCHARGE = "positive_discharge"

#: Relative tolerance of the residual checks. They compare float arithmetic against an independent closed form,
#: so the bound is a few hundred ulps of the largest term, not a modelling tolerance.
RESIDUAL_RELATIVE_TOLERANCE = 1e-9

TERMINAL_VOLTAGE_METRIC = "terminal_voltage"
FINAL_STATE_OF_CHARGE_METRIC = "final_state_of_charge"
FINAL_POLARIZATION_METRIC = "final_polarization_voltage"
MINIMUM_TERMINAL_VOLTAGE_METRIC = "minimum_terminal_voltage"

#: derived quantities the route's assembler computes over the WHOLE march (worst case), never caller input
TEMPERATURE_POSITION_LOW = "thevenin_temperature_position_low"
TEMPERATURE_POSITION_HIGH = "thevenin_temperature_position_high"
CURRENT_UTILIZATION = "thevenin_current_utilization"
MINIMUM_STATE_OF_CHARGE = "thevenin_minimum_state_of_charge"

#: validation check names (module constants: the evidentiary-level audit reads them)
CHECK_METRIC_DIMENSIONS = "thevenin_metric_dimensions"
CHECK_COULOMB_BALANCE = "thevenin_coulomb_balance_residual"
CHECK_POLARIZATION_SUPERPOSITION = "thevenin_polarization_superposition_residual"
CHECK_TERMINAL_RELATION = "thevenin_terminal_relation_residual"

TERMINAL_STATE = ScientificCapability.parse("battery:cell_terminal_state")
THEVENIN_MARCH = SolverCapability(
    "battery:thevenin_1rc_march",
    "A chronological piecewise-constant discharge/rest profile through a one-RC equivalent-circuit cell",
)

_ONE = Quantity(1.0, ctx.DIMENSIONLESS)
_ZERO = Quantity(0.0, ctx.DIMENSIONLESS)

_EXCLUSIONS = (
    "charging and any negative (charge-direction) current; refused, never mapped",
    "OCV hysteresis between charge and discharge branches",
    "more than one polarization time constant (diffusion is represented by one RC branch only)",
    "temperature dependence of R0, R1, C1 and OCV inside the declared temperature range: one parameter set "
    "stands for the whole range it is declared for",
    "ageing, capacity fade, resistance growth and self-discharge",
    "measurement noise, sensor bias and any uncertainty of the declared parameters",
    "cell-to-cell variation; one cell or one lumped string",
)

THEVENIN_1RC_MODEL = ScientificModelDefinition(
    model_id=MODEL_ID,
    version=MODEL_VERSION,
    name="One-RC Thevenin equivalent-circuit cell under a piecewise-constant discharge/rest profile",
    domain="battery",
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "Terminal voltage V = OCV(z) - I R0 - v_p, with dz/dt = -I/(eta Q) and dv_p/dt = (I R1 - v_p)/(R1 C1), "
        "advanced exactly over every constant-current interval. Positive current is discharge; zero is rest."
    ),
    inputs=(
        ModelInputSpec(name=ctx.NOMINAL_CAPACITY, source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar=ctx.CAPACITY_UNIT,
                       description="Charge basis of the state of charge for THIS parameter set; strictly positive."),
        ModelInputSpec(name=ctx.INTERNAL_RESISTANCE, source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar=ctx.RESISTANCE_UNIT, description="Series (ohmic) resistance R0; strictly positive."),
        ModelInputSpec(name=POLARIZATION_RESISTANCE, source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar=ctx.RESISTANCE_UNIT, description="Polarization branch resistance R1; strictly positive."),
        ModelInputSpec(name=POLARIZATION_CAPACITANCE, source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar="farad", description="Polarization branch capacitance C1; strictly positive."),
        ModelInputSpec(name=ctx.COULOMBIC_EFFICIENCY, source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar=ctx.DIMENSIONLESS, description="Charge debited per charge drawn, in (0, 1]."),
        ModelInputSpec(name=ctx.OCV_AT_FULL, source_kind=InputSourceKind.PARAMETER, unit_exemplar=ctx.VOLTAGE_UNIT,
                       description="OCV at z = 1 (or the end of the declared OCV curve)."),
        ModelInputSpec(name=ctx.OCV_AT_EMPTY, source_kind=InputSourceKind.PARAMETER, unit_exemplar=ctx.VOLTAGE_UNIT,
                       description="OCV at z = 0 (or the start of the declared OCV curve)."),
        ModelInputSpec(name=ctx.STATE_OF_CHARGE, source_kind=InputSourceKind.VARIABLE, unit_exemplar=ctx.DIMENSIONLESS,
                       role=VariableRole.STATE, description="State of charge; evolves; initial value declared."),
        ModelInputSpec(name=POLARIZATION_VOLTAGE, source_kind=InputSourceKind.VARIABLE, unit_exemplar=ctx.VOLTAGE_UNIT,
                       role=VariableRole.STATE, description="Polarization voltage v_p; evolves; initial value declared."),
        ModelInputSpec(name=ctx.DISCHARGE_CURRENT, source_kind=InputSourceKind.VARIABLE,
                       unit_exemplar=ctx.CURRENT_UNIT, role=VariableRole.CONTROL,
                       description="Imposed current, positive out (discharge), zero at rest; never negative here."),
        ModelInputSpec(name=ctx.CELL_TEMPERATURE, source_kind=InputSourceKind.VARIABLE,
                       unit_exemplar=ctx.TEMPERATURE_UNIT, role=VariableRole.STATE,
                       description="Cell temperature per interval, supplied from outside and never inferred."),
    ),
    outputs=(
        ModelOutputSpec(metric=TERMINAL_VOLTAGE_METRIC, unit_exemplar=ctx.VOLTAGE_UNIT,
                        description="Terminal voltage at the end of the profile."),
        ModelOutputSpec(metric=FINAL_STATE_OF_CHARGE_METRIC, unit_exemplar=ctx.DIMENSIONLESS,
                        description="State of charge at the end of the profile."),
        ModelOutputSpec(metric=FINAL_POLARIZATION_METRIC, unit_exemplar=ctx.VOLTAGE_UNIT,
                        description="Polarization voltage at the end of the profile."),
        ModelOutputSpec(metric=MINIMUM_TERMINAL_VOLTAGE_METRIC, unit_exemplar=ctx.VOLTAGE_UNIT,
                        description="Lowest terminal voltage at any interval end of the profile."),
    ),
    assumptions=(
        "the current is constant over each declared interval; the update is exact for that input",
        "one polarization branch with constant R1 and C1 over the declared temperature range",
        "the OCV is the declared chord or curve of the parameter set, evaluated at the end-of-interval SOC",
        "the initial state of charge and polarization voltage are declared with a stated basis, never defaulted",
    ),
    exclusions=_EXCLUSIONS,
    validity=ValidityDomain(
        derived_quantities=frozenset({TEMPERATURE_POSITION_LOW, TEMPERATURE_POSITION_HIGH, CURRENT_UTILIZATION,
                                      MINIMUM_STATE_OF_CHARGE}),
        conditions=(
            RangeCondition(
                name=TEMPERATURE_POSITION_LOW, minimum=_ZERO,
                description="The coldest interval lies inside the parameter set's declared temperature range "
                            "(position 0 = its lower end). Outside it the parameters are extrapolated.",
            ),
            RangeCondition(
                name=TEMPERATURE_POSITION_HIGH, maximum=_ONE,
                description="The warmest interval lies inside the declared temperature range (position 1 = upper end).",
            ),
            RangeCondition(
                name=CURRENT_UTILIZATION, minimum=_ZERO, maximum=_ONE,
                description="The largest interval current over the maximum discharge current the parameter set is "
                            "declared for. 1 is that declared maximum, by definition.",
            ),
            RangeCondition(
                name=MINIMUM_STATE_OF_CHARGE, minimum=_ZERO, maximum=_ONE,
                description="The lowest state of charge reached; the march itself refuses to leave [0, 1].",
            ),
        ),
        description="Worst case over every interval of the march.",
    ),
    references=(
        "Plett, G. L., Battery Management Systems, Volume I: Battery Modeling, Artech House (2015), Ch. 2 "
        "(equivalent-circuit models; the R-RC cell and its exact discrete-time update for piecewise-constant input)",
        "Hu, X., Li, S. & Peng, H., A comparative study of equivalent circuit models for Li-ion batteries, "
        "J. Power Sources 198 (2012) 359-367",
    ),
    required_capabilities=frozenset({THEVENIN_MARCH.name}),
    # SELF_CONSISTENT: checked against independent analytic references and limiting cases. Nothing measured.
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)

THEVENIN_1RC_REALIZATION = ModelRealizationDefinition(
    realization_id=REALIZATION_ID,
    version=REALIZATION_VERSION,
    model=ModelReference(MODEL_ID, MODEL_VERSION),
    formulation=ModelFormulation.ODE,
    name="Exact zero-order-hold update of the one-RC cell",
    description=(
        "Each constant-current interval is advanced with the exact solution of the linear ODE: "
        "v_p <- v_p exp(-dt/tau) + I R1 (1 - exp(-dt/tau)); z <- z - I dt/(eta Q). No discretization error "
        "exists for piecewise-constant input."
    ),
    provided_capabilities=frozenset({TERMINAL_STATE}),
    required_capabilities=frozenset(),
    required_solver_capabilities=frozenset({
        SolverCapabilityId.coerce(THEVENIN_MARCH),
        SolverCapabilityId.coerce(CoreCapabilities.ALGEBRAIC),
    }),
    assumptions=("exact for piecewise-constant current; numerical uncertainty is float rounding only",),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.battery.thevenin_route",
        version=REALIZATION_VERSION,
        reference="Thevenin1RCSolver over engcore.domains.battery.thevenin.evaluate_thevenin_step",
    ),
)


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _quantity(value: Any, unit: str, label: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(f"{label} must be a Quantity carrying {unit!r}")
    value.require_compatible(Quantity(1.0, unit), context=label)
    out = value.to(unit)
    if not math.isfinite(out.magnitude):
        raise InvalidScientificProblem(f"{label} must be finite")
    return out


# =====================================================================
# Typed inputs
# =====================================================================

@dataclass(frozen=True)
class Thevenin1RCParameterSet:
    """One named 1RC parameter set and the operating range it is declared for.

    ``basis`` states where the numbers come from ("declared fixture", "identified on cells X by calibration
    record Y"). It is recorded, never interpreted: a caller's statement is not evidence.
    """

    parameter_set_id: str
    cell: CellSpecification
    branch: Thevenin1RCParameters
    minimum_temperature: Quantity
    maximum_temperature: Quantity
    maximum_discharge_current: Quantity
    basis: str

    def __post_init__(self) -> None:
        if not str(self.parameter_set_id).strip():
            raise InvalidScientificProblem("a parameter set needs a non-empty parameter_set_id")
        if not isinstance(self.cell, CellSpecification):
            raise InvalidScientificProblem("a parameter set needs a CellSpecification for R0, OCV, Q and eta")
        if not isinstance(self.branch, Thevenin1RCParameters):
            raise InvalidScientificProblem("a parameter set needs Thevenin1RCParameters for R1 and C1")
        low = _quantity(self.minimum_temperature, ctx.TEMPERATURE_UNIT, "minimum_temperature")
        high = _quantity(self.maximum_temperature, ctx.TEMPERATURE_UNIT, "maximum_temperature")
        if not high.magnitude > low.magnitude:
            raise InvalidScientificProblem("the declared temperature range must have maximum > minimum")
        imax = _quantity(self.maximum_discharge_current, ctx.CURRENT_UNIT, "maximum_discharge_current")
        if not imax.magnitude > 0.0:
            raise InvalidScientificProblem("maximum_discharge_current must be strictly positive")
        if not str(self.basis).strip():
            raise InvalidScientificProblem("a parameter set must state its basis (where its numbers come from)")
        object.__setattr__(self, "minimum_temperature", low)
        object.__setattr__(self, "maximum_temperature", high)
        object.__setattr__(self, "maximum_discharge_current", imax)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_SET_SCHEMA,
            "parameter_set_id": self.parameter_set_id,
            "cell": self.cell.to_dict(),
            POLARIZATION_RESISTANCE: self.branch.polarization_resistance.to_dict(),
            POLARIZATION_CAPACITANCE: self.branch.polarization_capacitance.to_dict(),
            "minimum_temperature": self.minimum_temperature.to_dict(),
            "maximum_temperature": self.maximum_temperature.to_dict(),
            "maximum_discharge_current": self.maximum_discharge_current.to_dict(),
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Thevenin1RCParameterSet":
        if payload.get("schema") != PARAMETER_SET_SCHEMA:
            raise InvalidScientificProblem(f"not a {PARAMETER_SET_SCHEMA} record: {payload.get('schema')!r}")
        return cls(
            parameter_set_id=payload["parameter_set_id"],
            cell=CellSpecification.from_dict(payload["cell"]),
            branch=Thevenin1RCParameters(Quantity.from_dict(payload[POLARIZATION_RESISTANCE]),
                                         Quantity.from_dict(payload[POLARIZATION_CAPACITANCE])),
            minimum_temperature=Quantity.from_dict(payload["minimum_temperature"]),
            maximum_temperature=Quantity.from_dict(payload["maximum_temperature"]),
            maximum_discharge_current=Quantity.from_dict(payload["maximum_discharge_current"]),
            basis=payload["basis"],
        )

    @property
    def digest(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True)
class Thevenin1RCInitialState:
    """The declared initial state. Both coordinates are required; ``basis`` states why they hold (for example,
    "rested 3600 s, more than 5 tau, before t0, so v_p is taken as 0"). There is no default polarization."""

    state_of_charge: Quantity
    polarization_voltage: Quantity
    basis: str

    def __post_init__(self) -> None:
        if self.state_of_charge is None or self.polarization_voltage is None:
            raise InvalidScientificProblem("the initial state needs both the state of charge and the polarization "
                                           "voltage; neither is defaulted")
        TheveninState(self.state_of_charge, self.polarization_voltage)   # SOC in [0, 1]; units checked
        if not str(self.basis).strip():
            raise InvalidScientificProblem("the initial state must state its basis; an undeclared initial "
                                           "polarization is not zero by default")

    def kernel_state(self) -> TheveninState:
        return TheveninState(self.state_of_charge, self.polarization_voltage)

    def to_dict(self) -> dict[str, Any]:
        return {"state_of_charge": self.state_of_charge.to_dict(),
                "polarization_voltage": self.polarization_voltage.to_dict(), "basis": self.basis}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Thevenin1RCInitialState":
        return cls(Quantity.from_dict(payload["state_of_charge"]), Quantity.from_dict(payload["polarization_voltage"]),
                   payload["basis"])


@dataclass(frozen=True)
class ProfileSegment:
    """One interval of constant current (positive = discharge, zero = rest) at one cell temperature."""

    duration: Quantity
    current: Quantity
    cell_temperature: Quantity

    def __post_init__(self) -> None:
        duration = _quantity(self.duration, ctx.TIME_UNIT, "segment duration")
        if not duration.magnitude > 0.0:
            raise InvalidScientificProblem("a segment duration must be strictly positive")
        current = _quantity(self.current, ctx.CURRENT_UNIT, "segment current")
        if current.magnitude < 0.0:
            raise InvalidScientificProblem(
                "a negative segment current is a charge under the positive-discharge convention; the 1RC route "
                "has no charge or hysteresis evidence and refuses it rather than mapping it"
            )
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "current", current)
        object.__setattr__(self, "cell_temperature",
                           _quantity(self.cell_temperature, ctx.TEMPERATURE_UNIT, "segment cell_temperature"))

    def to_dict(self) -> dict[str, Any]:
        return {"duration": self.duration.to_dict(), "current": self.current.to_dict(),
                "cell_temperature": self.cell_temperature.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProfileSegment":
        return cls(Quantity.from_dict(payload["duration"]), Quantity.from_dict(payload["current"]),
                   Quantity.from_dict(payload["cell_temperature"]))


@dataclass(frozen=True)
class DischargeRestProfile:
    """A chronological sequence of constant-current intervals. ``sign_convention`` must be stated and must be
    ``positive_discharge``: a profile recorded under another convention is refused, not silently negated."""

    profile_id: str
    segments: tuple[ProfileSegment, ...]
    sign_convention: str

    def __post_init__(self) -> None:
        if not str(self.profile_id).strip():
            raise InvalidScientificProblem("a profile needs a non-empty profile_id")
        if self.sign_convention != POSITIVE_DISCHARGE:
            raise InvalidScientificProblem(
                f"the 1RC route takes current with the {POSITIVE_DISCHARGE!r} convention only; got "
                f"{self.sign_convention!r}. Convert the record explicitly and state it, do not rely on a mapping"
            )
        segments = tuple(self.segments)
        if not segments or not all(isinstance(s, ProfileSegment) for s in segments):
            raise InvalidScientificProblem("a profile needs at least one ProfileSegment")
        object.__setattr__(self, "segments", segments)

    def to_dict(self) -> dict[str, Any]:
        return {"profile_id": self.profile_id, "sign_convention": self.sign_convention,
                "segments": [s.to_dict() for s in self.segments]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DischargeRestProfile":
        return cls(payload["profile_id"], tuple(ProfileSegment.from_dict(s) for s in payload["segments"]),
                   payload["sign_convention"])

    @property
    def digest(self) -> str:
        return _sha256(self.to_dict())


# =====================================================================
# Problem, march and solver
# =====================================================================

def build_thevenin_problem(parameter_set: Thevenin1RCParameterSet, initial: Thevenin1RCInitialState,
                           profile: DischargeRestProfile) -> ScientificProblem:
    cell = parameter_set.cell
    return ScientificProblem(
        problem_id=f"battery-thevenin1rc-{parameter_set.parameter_set_id}-{profile.profile_id}",
        name=f"1RC cell {parameter_set.parameter_set_id} under profile {profile.profile_id}",
        description="Terminal voltage, state of charge and polarization of a one-RC cell over a chronological "
                    "piecewise-constant discharge/rest profile.",
        variables=(
            ScientificVariable(name=ctx.STATE_OF_CHARGE, unit=ctx.DIMENSIONLESS, role=VariableRole.STATE,
                               description="State of charge."),
            ScientificVariable(name=POLARIZATION_VOLTAGE, unit=ctx.VOLTAGE_UNIT, role=VariableRole.STATE,
                               description="Polarization voltage of the RC branch."),
            ScientificVariable(name=ctx.DISCHARGE_CURRENT, unit=ctx.CURRENT_UNIT, role=VariableRole.CONTROL,
                               description="Imposed current, positive = discharge."),
            ScientificVariable(name=ctx.CELL_TEMPERATURE, unit=ctx.TEMPERATURE_UNIT, role=VariableRole.STATE,
                               description="Cell temperature, supplied per interval."),
        ),
        parameters=(
            ScientificParameter(name=ctx.NOMINAL_CAPACITY, value=cell.nominal_capacity, description="Q"),
            ScientificParameter(name=ctx.INTERNAL_RESISTANCE, value=cell.internal_resistance, description="R0"),
            ScientificParameter(name=POLARIZATION_RESISTANCE, value=parameter_set.branch.polarization_resistance,
                                description="R1"),
            ScientificParameter(name=POLARIZATION_CAPACITANCE, value=parameter_set.branch.polarization_capacitance,
                                description="C1"),
            ScientificParameter(name=ctx.COULOMBIC_EFFICIENCY, value=cell.coulombic_efficiency, description="eta"),
            ScientificParameter(name=ctx.OCV_AT_FULL, value=cell.open_circuit_voltage_at_full, description="OCV(1)"),
            ScientificParameter(name=ctx.OCV_AT_EMPTY, value=cell.open_circuit_voltage_at_empty, description="OCV(0)"),
        ),
        initial_conditions=(
            InitialCondition(variable=ctx.STATE_OF_CHARGE, value=initial.state_of_charge,
                             description=f"declared: {initial.basis}"),
            InitialCondition(variable=POLARIZATION_VOLTAGE, value=initial.polarization_voltage,
                             description=f"declared: {initial.basis}"),
        ),
        models=(ModelReference(MODEL_ID, MODEL_VERSION),),
        required_capabilities=frozenset({THEVENIN_MARCH.name}),
        metadata={"parameter_set_sha256": parameter_set.digest, "profile_sha256": profile.digest},
    )


@dataclass(frozen=True)
class TrajectoryPoint:
    """The state at the END of one interval (times in seconds from the profile start)."""

    time_s: float
    current_a: float
    cell_temperature_k: float
    state_of_charge: float
    polarization_voltage_v: float
    open_circuit_voltage_v: float
    terminal_voltage_v: float

    def as_list(self) -> list[float]:
        return [self.time_s, self.current_a, self.cell_temperature_k, self.state_of_charge,
                self.polarization_voltage_v, self.open_circuit_voltage_v, self.terminal_voltage_v]


def march(parameter_set: Thevenin1RCParameterSet, initial: Thevenin1RCInitialState,
          profile: DischargeRestProfile) -> tuple[TrajectoryPoint, ...]:
    """Advance every interval exactly. Refuses (never clips) a step that leaves SOC in [0, 1] or the OCV curve."""
    state = initial.kernel_state()
    elapsed = 0.0
    points = []
    for index, segment in enumerate(profile.segments):
        try:
            step = evaluate_thevenin_step(parameter_set.cell, parameter_set.branch, state,
                                          current=segment.current, duration=segment.duration)
        except InvalidScientificProblem as exc:
            raise InvalidScientificProblem(f"interval {index} of profile {profile.profile_id!r}: {exc}") from exc
        elapsed += segment.duration.magnitude_in("second")
        state = step.final_state
        points.append(TrajectoryPoint(
            time_s=elapsed,
            current_a=segment.current.magnitude_in(ctx.CURRENT_UNIT),
            cell_temperature_k=segment.cell_temperature.magnitude_in(ctx.TEMPERATURE_UNIT),
            state_of_charge=state.state_of_charge.magnitude_in(ctx.DIMENSIONLESS),
            polarization_voltage_v=state.polarization_voltage.magnitude_in(ctx.VOLTAGE_UNIT),
            open_circuit_voltage_v=step.open_circuit_voltage.magnitude_in(ctx.VOLTAGE_UNIT),
            terminal_voltage_v=step.terminal_voltage.magnitude_in(ctx.VOLTAGE_UNIT),
        ))
    return tuple(points)


@dataclass(frozen=True)
class _PreparedMarch:
    parameter_set: Thevenin1RCParameterSet
    initial: Thevenin1RCInitialState
    profile: DischargeRestProfile
    realization: ModelRealizationDefinition


class Thevenin1RCSolver(DeclaredSupport):
    """Marches one bound (parameter set, initial state, profile) through the exact 1RC update."""

    serves_capabilities = frozenset({THEVENIN_MARCH.name})
    served_models = (THEVENIN_1RC_MODEL,)
    _METRIC_UNITS = {
        TERMINAL_VOLTAGE_METRIC: ctx.VOLTAGE_UNIT,
        FINAL_STATE_OF_CHARGE_METRIC: ctx.DIMENSIONLESS,
        FINAL_POLARIZATION_METRIC: ctx.VOLTAGE_UNIT,
        MINIMUM_TERMINAL_VOLTAGE_METRIC: ctx.VOLTAGE_UNIT,
    }

    def __init__(self, settings: SolverSettings | None = None) -> None:
        self._bound: dict[str, tuple[Thevenin1RCParameterSet, Thevenin1RCInitialState, DischargeRestProfile]] = {}
        self.settings = settings or SolverSettings()
        self._trajectories: dict[int, tuple[TrajectoryPoint, ...]] = {}

    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        return frozenset({THEVENIN_MARCH, CoreCapabilities.ALGEBRAIC})

    def bind(self, parameter_set: Thevenin1RCParameterSet, initial: Thevenin1RCInitialState,
             profile: DischargeRestProfile, problem_id: str) -> None:
        existing = self._bound.get(problem_id)
        if existing is not None and existing[0].digest != parameter_set.digest:
            raise InvalidScientificProblem(f"problem {problem_id!r} is already bound to another parameter set")
        self._bound[problem_id] = (parameter_set, initial, profile)

    def prepare(self, problem: ScientificProblem, *,
                realization: ModelRealizationDefinition = THEVENIN_1RC_REALIZATION) -> PreparedSolve:
        bound = self._bound.get(problem.problem_id)
        if bound is None:
            raise InvalidScientificProblem(f"nothing is bound to problem {problem.problem_id!r}")
        parameter_set, initial, profile = bound
        if (problem.metadata.get("parameter_set_sha256") != parameter_set.digest
                or problem.metadata.get("profile_sha256") != profile.digest):
            raise InvalidScientificProblem(f"problem {problem.problem_id!r} states another parameter set or profile "
                                           "than the one bound to it")
        for name, value in ((POLARIZATION_RESISTANCE, parameter_set.branch.polarization_resistance),
                            (POLARIZATION_CAPACITANCE, parameter_set.branch.polarization_capacitance),
                            (ctx.INTERNAL_RESISTANCE, parameter_set.cell.internal_resistance)):
            if problem.parameter(name).value.compare(value) != 0.0:
                raise InvalidScientificProblem(f"problem {problem.problem_id!r} states {name} other than the bound set")
        if realization.realization_id != REALIZATION_ID:
            raise InvalidScientificProblem(f"this solver realizes {REALIZATION_ID}, not {realization.realization_id}")
        return PreparedSolve(problem=problem, solver=self.identity, settings=self.settings,
                             payload=_PreparedMarch(parameter_set, initial, profile, realization))

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        payload: _PreparedMarch = prepared.payload
        started = time.perf_counter()
        points = march(payload.parameter_set, payload.initial, payload.profile)
        self._trajectories[id(prepared)] = points
        last = points[-1]
        return RawSolverOutput(
            values={TERMINAL_VOLTAGE_METRIC: last.terminal_voltage_v,
                    FINAL_STATE_OF_CHARGE_METRIC: last.state_of_charge,
                    FINAL_POLARIZATION_METRIC: last.polarization_voltage_v,
                    MINIMUM_TERMINAL_VOLTAGE_METRIC: min(p.terminal_voltage_v for p in points)},
            convergence=ConvergenceState.NOT_APPLICABLE,
            iterations=len(points),
            wall_seconds=time.perf_counter() - started,
            diagnostics={"intervals": len(points), "realization": payload.realization.realization_id},
        )

    def trajectory(self, prepared: PreparedSolve) -> tuple[TrajectoryPoint, ...]:
        return self._trajectories[id(prepared)]

    def extract_metrics(self, prepared: PreparedSolve, raw: RawSolverOutput) -> dict[str, Quantity]:
        if not raw.succeeded:
            return {}
        return {metric: Quantity(value, self._METRIC_UNITS[metric]) for metric, value in raw.values.items()}

    def validate(self, prepared: PreparedSolve, raw: RawSolverOutput) -> ValidationReport:
        """Four checks. Only the dimension check establishes a level (DIMENSIONALLY_VALID); the three residuals
        compare the march with independent closed forms (a direct charge sum, the superposition integral of the
        RC branch, the circuit relation) and establish nothing beyond verification of the arithmetic."""
        if not raw.succeeded:
            return ValidationReport(checks=(ValidationCheck(name=CHECK_METRIC_DIMENSIONS, outcome=ValidationOutcome.FAIL,
                                                            detail="the march did not succeed"),))
        payload: _PreparedMarch = prepared.payload
        points = self.trajectory(prepared)
        return ValidationReport(checks=(
            self._dimension_check(prepared, raw),
            self._coulomb_check(payload, points),
            self._superposition_check(payload, points),
            self._terminal_check(payload, points),
        ))

    def _dimension_check(self, prepared: PreparedSolve, raw: RawSolverOutput) -> ValidationCheck:
        declared = {spec.metric: spec.unit_exemplar for spec in THEVENIN_1RC_MODEL.outputs}
        produced = self.extract_metrics(prepared, raw)
        bad = sorted(m for m, v in produced.items() if m not in declared or not v.is_compatible_with(declared[m]))
        ok = not bad and set(produced) == set(declared)
        return ValidationCheck(
            name=CHECK_METRIC_DIMENSIONS,
            outcome=ValidationOutcome.PASS if ok else ValidationOutcome.FAIL,
            establishes=ValidationLevel.DIMENSIONALLY_VALID if ok else None,
            evidence=tuple(f"{m}={u}" for m, u in sorted(declared.items())),
            detail=f"{len(produced)} metrics against the model record's declared dimensions" + (f"; bad: {bad}" if bad else ""),
        )

    @staticmethod
    def _coulomb_check(payload: _PreparedMarch, points: Sequence[TrajectoryPoint]) -> ValidationCheck:
        cell = payload.parameter_set.cell
        q_as = cell.nominal_capacity.magnitude_in(ctx.CAPACITY_UNIT) * 3600.0
        eta = cell.coulombic_efficiency.magnitude_in(ctx.DIMENSIONLESS)
        charge = sum(s.current.magnitude_in(ctx.CURRENT_UNIT) * s.duration.magnitude_in("second")
                     for s in payload.profile.segments)
        expected = payload.initial.state_of_charge.magnitude_in(ctx.DIMENSIONLESS) - charge / (eta * q_as)
        residual = abs(points[-1].state_of_charge - expected)
        tolerance = RESIDUAL_RELATIVE_TOLERANCE * max(1.0, abs(expected))
        return ValidationCheck(
            name=CHECK_COULOMB_BALANCE,
            outcome=ValidationOutcome.PASS if residual <= tolerance else ValidationOutcome.FAIL,
            establishes=None, residual=residual, tolerance=tolerance,
            detail="final SOC against z0 - (sum I dt)/(eta Q) computed in one sum; verification of the arithmetic only",
        )

    @staticmethod
    def _superposition_check(payload: _PreparedMarch, points: Sequence[TrajectoryPoint]) -> ValidationCheck:
        r1 = payload.parameter_set.branch.polarization_resistance.magnitude_in(ctx.RESISTANCE_UNIT)
        tau = payload.parameter_set.branch.time_constant.magnitude_in("second")
        total = points[-1].time_s
        vp = payload.initial.polarization_voltage.magnitude_in(ctx.VOLTAGE_UNIT) * math.exp(-total / tau)
        start = 0.0
        for segment in payload.profile.segments:
            end = start + segment.duration.magnitude_in("second")
            vp += segment.current.magnitude_in(ctx.CURRENT_UNIT) * r1 * (
                math.exp(-(total - end) / tau) - math.exp(-(total - start) / tau))
            start = end
        residual = abs(points[-1].polarization_voltage_v - vp)
        scale = max(abs(vp), max(abs(s.current.magnitude_in(ctx.CURRENT_UNIT)) for s in payload.profile.segments) * r1,
                    abs(payload.initial.polarization_voltage.magnitude_in(ctx.VOLTAGE_UNIT)), 1e-12)
        tolerance = RESIDUAL_RELATIVE_TOLERANCE * scale
        return ValidationCheck(
            name=CHECK_POLARIZATION_SUPERPOSITION,
            outcome=ValidationOutcome.PASS if residual <= tolerance else ValidationOutcome.FAIL,
            establishes=None, residual=residual, tolerance=tolerance,
            detail="final v_p against the superposition (convolution) integral of the RC branch over all intervals, "
                   "computed without the recursive update; verification only",
        )

    @staticmethod
    def _terminal_check(payload: _PreparedMarch, points: Sequence[TrajectoryPoint]) -> ValidationCheck:
        r0 = payload.parameter_set.cell.internal_resistance.magnitude_in(ctx.RESISTANCE_UNIT)
        worst = 0.0
        for p in points:
            ocv = payload.parameter_set.cell.open_circuit_voltage(Quantity(p.state_of_charge, ctx.DIMENSIONLESS))
            expected = ocv.magnitude_in(ctx.VOLTAGE_UNIT) - p.current_a * r0 - p.polarization_voltage_v
            worst = max(worst, abs(p.terminal_voltage_v - expected))
        tolerance = RESIDUAL_RELATIVE_TOLERANCE * max(abs(p.terminal_voltage_v) for p in points)
        return ValidationCheck(
            name=CHECK_TERMINAL_RELATION,
            outcome=ValidationOutcome.PASS if worst <= tolerance else ValidationOutcome.FAIL,
            establishes=None, residual=worst, tolerance=tolerance,
            detail="every interval end against V = OCV(z) - I R0 - v_p; verification only",
        )


# =====================================================================
# Validity over the whole march
# =====================================================================

def assess_thevenin_validity(parameter_set: Thevenin1RCParameterSet, profile: DischargeRestProfile,
                             points: Sequence[TrajectoryPoint]):
    low = parameter_set.minimum_temperature.magnitude_in(ctx.TEMPERATURE_UNIT)
    high = parameter_set.maximum_temperature.magnitude_in(ctx.TEMPERATURE_UNIT)
    temps = [s.cell_temperature.magnitude_in(ctx.TEMPERATURE_UNIT) for s in profile.segments]
    imax = parameter_set.maximum_discharge_current.magnitude_in(ctx.CURRENT_UNIT)
    assembled = {
        TEMPERATURE_POSITION_LOW: Quantity((min(temps) - low) / (high - low), ctx.DIMENSIONLESS),
        TEMPERATURE_POSITION_HIGH: Quantity((max(temps) - low) / (high - low), ctx.DIMENSIONLESS),
        CURRENT_UTILIZATION: Quantity(max(s.current.magnitude_in(ctx.CURRENT_UNIT) for s in profile.segments) / imax,
                                      ctx.DIMENSIONLESS),
        MINIMUM_STATE_OF_CHARGE: Quantity(min(p.state_of_charge for p in points), ctx.DIMENSIONLESS),
    }
    return THEVENIN_1RC_MODEL.assess_validity(assembled=assembled, record_values=True)


# =====================================================================
# The route and its replay
# =====================================================================

@dataclass(frozen=True)
class Thevenin1RCReplayRecord:
    """Everything needed to re-execute one run and the exact numbers it produced."""

    payload: Mapping[str, Any]

    @property
    def digest(self) -> str:
        return _sha256(dict(self.payload))

    def to_dict(self) -> dict[str, Any]:
        return {**dict(self.payload), "record_sha256": self.digest}


@dataclass(frozen=True)
class Thevenin1RCRun:
    result: ScientificResult
    trajectory: tuple[TrajectoryPoint, ...]
    replay: Thevenin1RCReplayRecord


def _replay_payload(parameter_set, initial, profile, points) -> dict[str, Any]:
    trajectory = [p.as_list() for p in points]
    return {
        "schema": REPLAY_SCHEMA,
        "model": {"model_id": MODEL_ID, "version": MODEL_VERSION},
        "realization": {"realization_id": REALIZATION_ID, "version": REALIZATION_VERSION},
        "solver": {"solver_id": SOLVER_ID, "version": SOLVER_VERSION, "backend": BACKEND},
        "parameter_set": parameter_set.to_dict(),
        "parameter_set_sha256": parameter_set.digest,
        "initial_state": initial.to_dict(),
        "profile": profile.to_dict(),
        "profile_sha256": profile.digest,
        "trajectory_columns": ["time_s", "current_a", "cell_temperature_k", "state_of_charge",
                               "polarization_voltage_v", "open_circuit_voltage_v", "terminal_voltage_v"],
        "trajectory": trajectory,
        "trajectory_sha256": _sha256(trajectory),
    }


def run_thevenin_1rc(parameter_set: Thevenin1RCParameterSet, initial: Thevenin1RCInitialState,
                     profile: DischargeRestProfile, *, run_id: str | None = None) -> Thevenin1RCRun:
    """Execute the 1RC route end to end: problem, prepare, solve, validate, validity, provenance, result, replay."""
    for name, value in (("parameter_set", parameter_set), ("initial", initial), ("profile", profile)):
        if not isinstance(value, (Thevenin1RCParameterSet, Thevenin1RCInitialState, DischargeRestProfile)):
            raise InvalidScientificProblem(f"{name} has the wrong type: {type(value).__name__}")
    problem = build_thevenin_problem(parameter_set, initial, profile)
    solver = Thevenin1RCSolver()
    solver.bind(parameter_set, initial, profile, problem.problem_id)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    report = solver.validate(prepared, raw)
    points = solver.trajectory(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    assessment = assess_thevenin_validity(parameter_set, profile, points)
    replay = Thevenin1RCReplayRecord(_replay_payload(parameter_set, initial, profile, points))
    identifier = run_id or f"battery-thevenin1rc-{replay.digest[:16]}"
    binding = ExecutionBinding.from_execution(prepared, raw, model=ModelReference(MODEL_ID, MODEL_VERSION),
                                              realization=RealizationReference(REALIZATION_ID, REALIZATION_VERSION))
    cell = parameter_set.cell
    provenance = ProvenanceRecord(
        run_id=identifier,
        bindings=(binding,),
        inputs={
            ctx.NOMINAL_CAPACITY: cell.nominal_capacity,
            ctx.INTERNAL_RESISTANCE: cell.internal_resistance,
            POLARIZATION_RESISTANCE: parameter_set.branch.polarization_resistance,
            POLARIZATION_CAPACITANCE: parameter_set.branch.polarization_capacitance,
            ctx.COULOMBIC_EFFICIENCY: cell.coulombic_efficiency,
            ctx.OCV_AT_FULL: cell.open_circuit_voltage_at_full,
            ctx.OCV_AT_EMPTY: cell.open_circuit_voltage_at_empty,
            ctx.STATE_OF_CHARGE: initial.state_of_charge,
            POLARIZATION_VOLTAGE: initial.polarization_voltage,
        },
        assumptions=THEVENIN_1RC_MODEL.assumptions,
        metadata={
            "system": "battery.thevenin_1rc",
            "parameter_set_id": parameter_set.parameter_set_id,
            "parameter_set_sha256": parameter_set.digest,
            "parameter_set_basis": parameter_set.basis,
            "profile_id": profile.profile_id,
            "profile_sha256": profile.digest,
            "initial_state_basis": initial.basis,
            "sign_convention": POSITIVE_DISCHARGE,
            "replay_record_sha256": replay.digest,
        },
    )
    result = ScientificResult(
        result_id=identifier,
        problem_id=problem.problem_id,
        values=metrics,
        provenance=provenance,
        models=((MODEL_ID, MODEL_VERSION),),
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        validity={MODEL_ID: assessment},
        uncertainty={name: Uncertainty.unknown(
            "battery.thevenin_1rc has no measurement, parameter or model-form uncertainty established; UNKNOWN is "
            "explicit and must not be read as zero") for name in metrics},
        assumptions=THEVENIN_1RC_MODEL.assumptions,
        metadata={"replay_record_sha256": replay.digest, "trajectory_sha256": replay.payload["trajectory_sha256"]},
    )
    return Thevenin1RCRun(result=result, trajectory=points, replay=replay)


class ReplayRefused(InvalidScientificProblem):
    """A replay record that is stale, altered, or does not reproduce."""


def replay_thevenin_1rc(record: Mapping[str, Any]) -> Thevenin1RCRun:
    """Re-execute a replay record and require bit-identical reproduction.

    Refused: a record digest that does not match its content; another schema; a model, realization or solver
    identity other than this code's (a stale record is never re-run under new code); a parameter-set or profile
    digest that does not match the embedded content; a trajectory that does not reproduce exactly."""
    record = dict(record)
    stated = record.pop("record_sha256", None)
    if stated is None or _sha256(record) != stated:
        raise ReplayRefused("the replay record's content does not match its digest (altered or truncated)")
    if record.get("schema") != REPLAY_SCHEMA:
        raise ReplayRefused(f"not a {REPLAY_SCHEMA} record: {record.get('schema')!r}")
    current = {"model": {"model_id": MODEL_ID, "version": MODEL_VERSION},
               "realization": {"realization_id": REALIZATION_ID, "version": REALIZATION_VERSION},
               "solver": {"solver_id": SOLVER_ID, "version": SOLVER_VERSION, "backend": BACKEND}}
    for key, value in current.items():
        if record.get(key) != value:
            raise ReplayRefused(f"stale replay record: it was produced by {key} {record.get(key)!r}, this code is "
                                f"{value!r}; re-running it would attribute old numbers to new code")
    parameter_set = Thevenin1RCParameterSet.from_dict(record["parameter_set"])
    profile = DischargeRestProfile.from_dict(record["profile"])
    if parameter_set.digest != record["parameter_set_sha256"] or profile.digest != record["profile_sha256"]:
        raise ReplayRefused("the embedded parameter set or profile does not match its recorded digest")
    run = run_thevenin_1rc(parameter_set, Thevenin1RCInitialState.from_dict(record["initial_state"]), profile)
    if run.replay.payload["trajectory"] != record["trajectory"]:
        raise ReplayRefused("the replay did not reproduce the recorded trajectory bit for bit")
    return run


__all__ = [
    "CHECK_COULOMB_BALANCE", "CHECK_METRIC_DIMENSIONS", "CHECK_POLARIZATION_SUPERPOSITION", "CHECK_TERMINAL_RELATION",
    "DischargeRestProfile", "MODEL_ID", "MODEL_VERSION", "POSITIVE_DISCHARGE", "ProfileSegment", "REALIZATION_ID",
    "ReplayRefused", "SOLVER_ID", "THEVENIN_1RC_MODEL", "THEVENIN_1RC_REALIZATION", "Thevenin1RCInitialState",
    "Thevenin1RCParameterSet", "Thevenin1RCReplayRecord", "Thevenin1RCRun", "Thevenin1RCSolver", "TrajectoryPoint",
    "assess_thevenin_validity", "build_thevenin_problem", "march", "replay_thevenin_1rc", "run_thevenin_1rc",
]
