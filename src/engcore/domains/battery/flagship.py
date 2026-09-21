"""The flagship electrothermal cell: model record, realization and solver.

This module turns the kernel in :mod:`engcore.domains.battery.electrothermal`
into artifacts the planner, the pack registries and the multiphysics runtime
can carry: one :class:`ScientificModelDefinition`, one realization, and one
solver satisfying the core protocol.

It does not restate the physics. Every number comes from
:func:`~engcore.domains.battery.electrothermal.advance_electrothermal_step`.

Relation to ``battery.cell.rint_ocv``
--------------------------------------
Separate records, deliberately. The Rint model is an algebraic cell with one
constant resistance and no dynamic state; this one carries a polarization state,
two temperature-dependent resistances and a declared open-circuit voltage curve.
They answer differently at the same operating point, so they are two claims with
two validity domains, and ``battery.cell@1`` is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any

from ...scientific.capabilities import ScientificCapability
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import (
    InitialCondition,
    ModelReference,
    ScientificParameter,
    ScientificProblem,
    ScientificVariable,
)
from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
    VariableRole,
)
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.capability import (
    CoreCapabilities,
    SolverCapability,
    SolverCapabilityId,
)
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
from . import electrothermal as et
from .flagship_ocv import CHARGE_STATE_BASIS_AH, FLAGSHIP_OCV_CURVE

MODEL_ID = "battery.cell.electrothermal_1rc"
MODEL_VERSION = "0.1.0"
REALIZATION_VERSION = "0.1.0"
SOLVER_ID = "engcore.battery.electrothermal_1rc_closed_form"
SOLVER_VERSION = "0.1.0"
BACKEND = "python.float"

#: What this model produces. The capability is its own: a consumer asking for a
#: Rint terminal state must not be handed a 1-RC one, because the two carry
#: different validity domains.
ELECTROTHERMAL_CELL_STATE = ScientificCapability.parse(
    "battery:electrothermal_cell_state"
)

#: What it needs from somewhere else. The cell temperature is an input, and the
#: thermal participant provides it.
REQUIRED_BODY_TEMPERATURE = ScientificCapability.parse("thermal:body_temperature")

ELECTROTHERMAL_CELL_STEP = SolverCapability(
    "battery:electrothermal_cell_step",
    "Advance one interval of a 1-RC cell at one held cell temperature.",
)

# -- metric names -----------------------------------------------------------
TERMINAL_VOLTAGE_METRIC = "terminal_voltage"
OPEN_CIRCUIT_VOLTAGE_METRIC = "open_circuit_voltage"
STATE_OF_CHARGE_METRIC = "state_of_charge"
POLARIZATION_VOLTAGE_METRIC = "polarization_voltage"
OHMIC_DROP_METRIC = "ohmic_drop"
HEAT_GENERATION_METRIC = "heat_generation"
ELECTRICAL_LOSS_METRIC = "electrical_loss"

# -- input names ------------------------------------------------------------
OHMIC_RESISTANCE_REFERENCE = "ohmic_resistance_reference"
OHMIC_ACTIVATION_ENERGY = "ohmic_activation_energy"
POLARIZATION_RESISTANCE_REFERENCE = "polarization_resistance_reference"
POLARIZATION_ACTIVATION_ENERGY = "polarization_activation_energy"
POLARIZATION_CAPACITANCE = "polarization_capacitance"
REFERENCE_TEMPERATURE = "reference_temperature"
CHARGE_STATE_BASIS = "charge_state_basis"
INITIAL_STATE_OF_CHARGE = "initial_state_of_charge"
INITIAL_POLARIZATION_VOLTAGE = "initial_polarization_voltage"
LOAD_CURRENT = "load_current"

_ASSUMPTIONS = (
    "one lumped cell at one temperature, which the thermal participant owns",
    "the load current is constant across each advanced interval",
    "one RC branch stands for the whole diffusion overpotential",
    "the ohmic and polarization resistances follow an Arrhenius law in the "
    "cell temperature, with the fitted activation energies",
    "the open-circuit voltage is the declared curve, over its declared "
    "charge-state interval and nowhere else",
    "the charge state is the declared basis minus the integrated current; "
    "the basis is a constant, not a fitted capacity",
)

_EXCLUSIONS = (
    "reversible entropic heat I T dU/dT, which is of the same order as the "
    "irreversible term at low rate and changes sign with current direction; "
    "no entropy coefficient is measured for this cell and none is assumed",
    "ageing: capacity fade, resistance growth and any dependence on cycle "
    "count. The model has no state that ages",
    "hysteresis between charge and discharge. The declared open-circuit "
    "voltage curve carries the hysteresis of the branches it was averaged "
    "from and cannot separate it",
    "any second, slower diffusion time constant. One RC branch cannot "
    "represent a relaxation tail with two scales, and the measured tails have "
    "one this model fits and one it does not",
    "any dependence of the open-circuit voltage on temperature. The declared "
    "curve has no temperature axis",
    "any dependence of the usable capacity on temperature or rate. The charge "
    "state basis is a constant",
    "charge acceptance. Negative current is admitted arithmetically but no "
    "charge-direction evidence supports the parameters, and the composition "
    "that executes this model declares discharge and rest only",
    "internal temperature gradients. The cell is one lumped temperature and "
    "no Biot-number screen is stated for it",
)

_PARAMETERS = (
    ModelInputSpec(
        name=OHMIC_RESISTANCE_REFERENCE,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=ctx.RESISTANCE_UNIT,
        description=(
            "Series resistance at the reference temperature; strictly positive."
        ),
    ),
    ModelInputSpec(
        name=OHMIC_ACTIVATION_ENERGY,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=et.ACTIVATION_ENERGY_UNIT,
        description=(
            "Activation energy of the series resistance. Zero is a result, not "
            "a default: it says the evidence showed no temperature dependence."
        ),
    ),
    ModelInputSpec(
        name=POLARIZATION_RESISTANCE_REFERENCE,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=ctx.RESISTANCE_UNIT,
        description="RC-branch resistance at the reference temperature.",
    ),
    ModelInputSpec(
        name=POLARIZATION_ACTIVATION_ENERGY,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=et.ACTIVATION_ENERGY_UNIT,
        description="Activation energy of the RC-branch resistance.",
    ),
    ModelInputSpec(
        name=POLARIZATION_CAPACITANCE,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=et.CAPACITANCE_UNIT,
        description="RC-branch capacitance; sets the relaxation time constant.",
    ),
    ModelInputSpec(
        name=REFERENCE_TEMPERATURE,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=ctx.TEMPERATURE_UNIT,
        description="Temperature the two reference resistances are defined at.",
    ),
    ModelInputSpec(
        name=CHARGE_STATE_BASIS,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=ctx.CAPACITY_UNIT,
        description=(
            "Charge the charge-state axis is normalized by. A declared "
            "constant; the model does not fit a capacity."
        ),
    ),
    ModelInputSpec(
        name=ctx.COULOMBIC_EFFICIENCY,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=ctx.DIMENSIONLESS,
        description="Charge returned per charge delivered, in (0, 1].",
    ),
)

_STATE = (
    ModelInputSpec(
        name=ctx.STATE_OF_CHARGE,
        source_kind=InputSourceKind.VARIABLE,
        unit_exemplar=ctx.DIMENSIONLESS,
        role=VariableRole.STATE,
        description="Charge state on the declared basis, in [0, 1].",
    ),
    ModelInputSpec(
        name=et.POLARIZATION_VOLTAGE,
        source_kind=InputSourceKind.VARIABLE,
        unit_exemplar=ctx.VOLTAGE_UNIT,
        role=VariableRole.STATE,
        description="Voltage across the RC branch; the model's dynamic state.",
    ),
    ModelInputSpec(
        name=LOAD_CURRENT,
        source_kind=InputSourceKind.VARIABLE,
        unit_exemplar=ctx.CURRENT_UNIT,
        role=VariableRole.CONTROL,
        description="Current drawn from the cell, positive out. Imposed externally.",
    ),
    ModelInputSpec(
        name=ctx.CELL_TEMPERATURE,
        source_kind=InputSourceKind.VARIABLE,
        unit_exemplar=ctx.TEMPERATURE_UNIT,
        role=VariableRole.STATE,
        description=(
            "Cell temperature over the interval. Owned by the thermal "
            "participant; this model reads it and never sets it."
        ),
    ),
    ModelInputSpec(
        name=ctx.DURATION,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=ctx.TIME_UNIT,
        description="Length of the advanced interval; strictly positive.",
    ),
)

ELECTROTHERMAL_1RC_MODEL = ScientificModelDefinition(
    model_id=MODEL_ID,
    version=MODEL_VERSION,
    name="One-RC Thevenin cell with Arrhenius resistances and declared OCV",
    domain="battery",
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "Terminal voltage, charge state and irreversible heat of a cell "
        "represented as a declared OCV(z) source in series with an Arrhenius "
        "ohmic resistance and one Arrhenius RC branch: "
        "V = OCV(z) - I R0(T) - v_p, "
        "dv_p/dt = (I R1(T) - v_p) / (R1(T) C1), "
        "dz/dt = -I / (eta Q_basis), "
        "Qdot = I^2 R0(T) + I <v_p>."
    ),
    inputs=_PARAMETERS + _STATE,
    outputs=(
        ModelOutputSpec(
            metric=TERMINAL_VOLTAGE_METRIC,
            unit_exemplar=ctx.VOLTAGE_UNIT,
            description="Terminal voltage at the end of the interval.",
        ),
        ModelOutputSpec(
            metric=OPEN_CIRCUIT_VOLTAGE_METRIC,
            unit_exemplar=ctx.VOLTAGE_UNIT,
            description=(
                "The declared curve's value at the reached charge state; "
                "absent, not extrapolated, outside its interval."
            ),
        ),
        ModelOutputSpec(
            metric=STATE_OF_CHARGE_METRIC,
            unit_exemplar=ctx.DIMENSIONLESS,
            description="Charge state at the end of the interval.",
        ),
        ModelOutputSpec(
            metric=POLARIZATION_VOLTAGE_METRIC,
            unit_exemplar=ctx.VOLTAGE_UNIT,
            description="RC-branch voltage at the end of the interval.",
        ),
        ModelOutputSpec(
            metric=OHMIC_DROP_METRIC,
            unit_exemplar=ctx.VOLTAGE_UNIT,
            description="I R0(T) over the interval.",
        ),
        ModelOutputSpec(
            metric=HEAT_GENERATION_METRIC,
            unit_exemplar=ctx.POWER_UNIT,
            description=(
                "Mean irreversible dissipation over the interval, "
                "I^2 R0(T) + I <v_p>. The reversible entropic term is excluded "
                "and is not small at low rate."
            ),
        ),
        ModelOutputSpec(
            metric=ELECTRICAL_LOSS_METRIC,
            unit_exemplar=et.ENERGY_UNIT,
            description="Energy dissipated over the interval.",
        ),
    ),
    assumptions=_ASSUMPTIONS,
    exclusions=_EXCLUSIONS,
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=OHMIC_RESISTANCE_REFERENCE,
                minimum=Quantity(0.0, ctx.RESISTANCE_UNIT),
                minimum_inclusive=False,
                description=(
                    "Strictly positive; a cell with no series resistance has no "
                    "ohmic loss and no self-heating from one."
                ),
            ),
            RangeCondition(
                name=POLARIZATION_RESISTANCE_REFERENCE,
                minimum=Quantity(0.0, ctx.RESISTANCE_UNIT),
                minimum_inclusive=False,
                description=(
                    "Strictly positive; a zero RC resistance has no time "
                    "constant and the relaxation the branch represents vanishes."
                ),
            ),
            RangeCondition(
                name=POLARIZATION_CAPACITANCE,
                minimum=Quantity(0.0, et.CAPACITANCE_UNIT),
                minimum_inclusive=False,
                description="Strictly positive; otherwise the time constant is zero.",
            ),
            RangeCondition(
                name=CHARGE_STATE_BASIS,
                minimum=Quantity(0.0, ctx.CAPACITY_UNIT),
                minimum_inclusive=False,
                description="Strictly positive; the charge-state axis divides by it.",
            ),
            RangeCondition(
                name=ctx.STATE_OF_CHARGE,
                minimum=Quantity(0.0, ctx.DIMENSIONLESS),
                maximum=Quantity(1.0, ctx.DIMENSIONLESS),
                description=(
                    "The charge state is a fraction of the declared basis. A "
                    "step leaving it is refused rather than clipped."
                ),
            ),
        )
    ),
)

ELECTROTHERMAL_1RC_REALIZATION = ModelRealizationDefinition(
    realization_id=f"{MODEL_ID}.exact_constant_current",
    version=REALIZATION_VERSION,
    model=ModelReference(MODEL_ID, MODEL_VERSION),
    # ODE: the model poses two coupled first-order equations in z and v_p. This
    # realization integrates both exactly over an interval of constant current
    # at a held temperature, which is what the formulation/realization split is
    # for -- the claim is an ODE, the discharge of it uses no integrator.
    formulation=ModelFormulation.ODE,
    name="Exact integration of the 1-RC cell over one constant-current interval",
    description=(
        "Closed-form update of the charge state and the RC-branch voltage, with "
        "the exact time-average of the RC voltage used for the dissipation, so "
        "the heat reported over an interval is the energy the branch dissipated "
        "in it rather than its endpoint power."
    ),
    provided_capabilities=frozenset({ELECTROTHERMAL_CELL_STATE}),
    required_capabilities=frozenset({REQUIRED_BODY_TEMPERATURE}),
    required_solver_capabilities=frozenset(
        {
            SolverCapabilityId.coerce(ELECTROTHERMAL_CELL_STEP),
            SolverCapabilityId.coerce(CoreCapabilities.ALGEBRAIC),
        }
    ),
    assumptions=(
        "the current is constant over the integrated interval",
        "the cell temperature is held over the integrated interval; the "
        "coupling window is what makes that an approximation, and the "
        "composition's refinement evidence is what bounds it",
        "exact for the declared equations; no time-discretization error",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.battery.electrothermal",
        version=REALIZATION_VERSION,
        reference="advance_electrothermal_step; see the module docstring",
    ),
)


def flagship_cell(
    *,
    cell_id: str,
    ohmic_resistance_reference: Quantity,
    ohmic_activation_energy: Quantity,
    polarization_resistance_reference: Quantity,
    polarization_activation_energy: Quantity,
    polarization_capacitance: Quantity,
    reference_temperature: Quantity,
    charge_state_basis: Quantity | None = None,
    coulombic_efficiency: Quantity | None = None,
) -> et.ElectrothermalCell:
    """Build the flagship cell around the frozen open-circuit voltage authority.

    The curve is not an argument. Replacing it replaces the model, and this
    function exists so that every consumer of ``battery.cell.electrothermal_1rc``
    gets the one curve that model record's evidence is about.
    """
    return et.ElectrothermalCell(
        cell_id=cell_id,
        nominal_capacity=(
            Quantity(CHARGE_STATE_BASIS_AH, ctx.CAPACITY_UNIT)
            if charge_state_basis is None
            else charge_state_basis
        ),
        coulombic_efficiency=(
            Quantity(1.0, ctx.DIMENSIONLESS)
            if coulombic_efficiency is None
            else coulombic_efficiency
        ),
        ohmic_resistance=et.ArrheniusResistance(
            ohmic_resistance_reference,
            ohmic_activation_energy,
            reference_temperature,
        ),
        polarization_resistance=et.ArrheniusResistance(
            polarization_resistance_reference,
            polarization_activation_energy,
            reference_temperature,
        ),
        polarization_capacitance=polarization_capacitance,
        open_circuit_voltage_curve=FLAGSHIP_OCV_CURVE,
    )


def build_electrothermal_problem(
    cell: et.ElectrothermalCell,
    state: et.ElectricalState,
    *,
    duration: Quantity,
    problem_id: str | None = None,
) -> ScientificProblem:
    """The universal problem statement for one advanced interval of this cell.

    ``load_current`` and ``cell_temperature`` are variables with role CONTROL,
    not parameters: both are imposed from outside the problem -- the first by
    whatever draws the current, the second by the thermal participant -- and a
    problem that recorded them as configuration would misstate which part of
    the system owns them.
    """
    return ScientificProblem(
        problem_id=problem_id or f"battery-electrothermal-{cell.cell_id}",
        name=f"Electrothermal 1-RC cell {cell.cell_id}",
        description=(
            "Terminal voltage, charge state, polarization voltage and "
            "irreversible heat of one 1-RC cell over a single interval of "
            "imposed current at an imposed cell temperature."
        ),
        variables=(
            ScientificVariable(
                name=ctx.STATE_OF_CHARGE,
                unit=ctx.DIMENSIONLESS,
                role=VariableRole.STATE,
                description="Charge state on the declared basis; evolves over the interval.",
            ),
            ScientificVariable(
                name=et.POLARIZATION_VOLTAGE,
                unit=ctx.VOLTAGE_UNIT,
                role=VariableRole.STATE,
                description="RC-branch voltage; the model's dynamic state.",
            ),
            ScientificVariable(
                name=LOAD_CURRENT,
                unit=ctx.CURRENT_UNIT,
                role=VariableRole.CONTROL,
                description="Externally imposed current, positive out.",
            ),
            ScientificVariable(
                name=ctx.CELL_TEMPERATURE,
                unit=ctx.TEMPERATURE_UNIT,
                role=VariableRole.CONTROL,
                description=(
                    "Externally imposed cell temperature, owned by the thermal "
                    "participant."
                ),
            ),
        ),
        parameters=(
            ScientificParameter(
                name=OHMIC_RESISTANCE_REFERENCE,
                value=cell.ohmic_resistance.reference_value,
                description="Series resistance at the reference temperature.",
            ),
            ScientificParameter(
                name=OHMIC_ACTIVATION_ENERGY,
                value=cell.ohmic_resistance.activation_energy,
                description="Activation energy of the series resistance.",
            ),
            ScientificParameter(
                name=POLARIZATION_RESISTANCE_REFERENCE,
                value=cell.polarization_resistance.reference_value,
                description="RC-branch resistance at the reference temperature.",
            ),
            ScientificParameter(
                name=POLARIZATION_ACTIVATION_ENERGY,
                value=cell.polarization_resistance.activation_energy,
                description="Activation energy of the RC-branch resistance.",
            ),
            ScientificParameter(
                name=POLARIZATION_CAPACITANCE,
                value=cell.polarization_capacitance,
                description="RC-branch capacitance.",
            ),
            ScientificParameter(
                name=REFERENCE_TEMPERATURE,
                value=cell.ohmic_resistance.reference_temperature,
                description="Temperature the reference resistances are defined at.",
            ),
            ScientificParameter(
                name=CHARGE_STATE_BASIS,
                value=cell.nominal_capacity,
                description="Declared charge the charge-state axis is normalized by.",
            ),
            ScientificParameter(
                name=ctx.COULOMBIC_EFFICIENCY,
                value=cell.coulombic_efficiency,
                description="Charge returned per charge delivered.",
            ),
            ScientificParameter(
                name=ctx.DURATION,
                value=duration,
                description="Length of the interval to advance.",
            ),
        ),
        initial_conditions=(
            InitialCondition(
                variable=ctx.STATE_OF_CHARGE,
                value=state.state_of_charge,
                description="Charge state at the start of the interval.",
            ),
            InitialCondition(
                variable=et.POLARIZATION_VOLTAGE,
                value=state.polarization_voltage,
                description="RC-branch voltage at the start of the interval.",
            ),
        ),
        models=(ModelReference(MODEL_ID, MODEL_VERSION),),
        required_capabilities=frozenset({ELECTROTHERMAL_CELL_STEP.name}),
    )


@dataclass(frozen=True)
class PreparedElectrothermalStep:
    cell: et.ElectrothermalCell
    state: et.ElectricalState
    current: Quantity
    duration: Quantity
    temperature: Quantity
    realization: ModelRealizationDefinition


#: Relative tolerance on the closed-form residuals. Both are exact in real
#: arithmetic; this bounds round-off in a handful of multiplications. It is a
#: numerical tolerance on a verification check and appears in no validity domain.
RESIDUAL_RELATIVE_TOLERANCE = 1e-11


class ElectrothermalCellSolver(DeclaredSupport):
    """Advances one flagship cell over one interval. Satisfies the protocol."""

    def __init__(self, settings: SolverSettings | None = None) -> None:
        self._bound: dict[str, PreparedElectrothermalStep] = {}
        self.settings = settings or SolverSettings()

    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        return frozenset({ELECTROTHERMAL_CELL_STEP, CoreCapabilities.ALGEBRAIC})

    serves_capabilities = frozenset({ELECTROTHERMAL_CELL_STEP.name})
    served_models = (ELECTROTHERMAL_1RC_MODEL,)
    #: The realization this solver binds and prepares. A class attribute rather
    #: than a hardcoded default so a subclass serving a different model version
    #: can name its own realization without reimplementing the kernel. Holds
    #: exactly what the two call sites below used to name.
    realization = ELECTROTHERMAL_1RC_REALIZATION

    def bind_step(
        self,
        cell: et.ElectrothermalCell,
        state: et.ElectricalState,
        problem_id: str,
        *,
        current: Quantity,
        duration: Quantity,
        temperature: Quantity,
    ) -> None:
        """Associate one cell, state and operating point with a problem id.

        Rebinding the same physical cell at a new operating point is free; that
        is what marching a trajectory is. Rebinding a *different* cell behind
        one problem id is refused, because two results would then claim one
        identity while describing different systems.
        """
        if not isinstance(cell, et.ElectrothermalCell):
            raise InvalidScientificProblem("bind_step expects an ElectrothermalCell")
        if not isinstance(state, et.ElectricalState):
            raise InvalidScientificProblem("bind_step expects an ElectricalState")
        key = str(problem_id)
        existing = self._bound.get(key)
        if existing is not None and _physical_key(existing.cell) != _physical_key(cell):
            raise InvalidScientificProblem(
                f"problem {key!r} is already bound to a different cell; swapping "
                f"the cell behind a problem id would let two results claim one "
                f"identity while describing different systems"
            )
        self._bound[key] = PreparedElectrothermalStep(
            cell=cell,
            state=state,
            current=current,
            duration=duration,
            temperature=temperature,
            realization=self.realization,
        )

    def prepare(
        self,
        problem: ScientificProblem,
        *,
        realization: ModelRealizationDefinition | None = None,
    ) -> PreparedSolve:
        realization = realization or self.realization
        bound = self._bound.get(problem.problem_id)
        if bound is None:
            raise InvalidScientificProblem(
                f"no cell is bound to problem {problem.problem_id!r}; call "
                f"bind_step first"
            )
        self.verify_problem_matches_step(problem, bound)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.settings,
            payload=PreparedElectrothermalStep(
                cell=bound.cell,
                state=bound.state,
                current=bound.current,
                duration=bound.duration,
                temperature=bound.temperature,
                realization=realization,
            ),
        )

    @staticmethod
    def verify_problem_matches_step(
        problem: ScientificProblem, bound: PreparedElectrothermalStep
    ) -> None:
        """Refuse a problem describing a different cell than the one bound."""
        for name, declared in (
            (CHARGE_STATE_BASIS, bound.cell.nominal_capacity),
            (ctx.COULOMBIC_EFFICIENCY, bound.cell.coulombic_efficiency),
            (
                OHMIC_RESISTANCE_REFERENCE,
                bound.cell.ohmic_resistance.reference_value,
            ),
            (
                POLARIZATION_RESISTANCE_REFERENCE,
                bound.cell.polarization_resistance.reference_value,
            ),
            (POLARIZATION_CAPACITANCE, bound.cell.polarization_capacitance),
            (ctx.DURATION, bound.duration),
        ):
            stated = problem.parameter(name).value
            if not isinstance(stated, Quantity) or stated.compare(declared) != 0.0:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} states {name} = {stated} but "
                    f"the bound cell declares {declared}"
                )
        initial = {item.variable: item.value for item in problem.initial_conditions}
        expected = {
            ctx.STATE_OF_CHARGE: bound.state.state_of_charge,
            et.POLARIZATION_VOLTAGE: bound.state.polarization_voltage,
        }
        if set(initial) != set(expected):
            raise InvalidScientificProblem(
                f"problem {problem.problem_id!r} must carry initial conditions on "
                f"exactly {sorted(expected)}, got {sorted(initial)}"
            )
        for variable, value in expected.items():
            if initial[variable].compare(value) != 0.0:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} starts at {variable} = "
                    f"{initial[variable]} but the bound state declares {value}"
                )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        step: PreparedElectrothermalStep = prepared.payload
        started = time.perf_counter()
        result = et.advance_electrothermal_step(
            step.cell,
            step.state,
            current=step.current,
            duration=step.duration,
            temperature=step.temperature,
        )
        return RawSolverOutput(
            values={
                TERMINAL_VOLTAGE_METRIC: result.terminal_voltage.magnitude,
                OPEN_CIRCUIT_VOLTAGE_METRIC: result.open_circuit_voltage.magnitude,
                STATE_OF_CHARGE_METRIC: result.final_state.state_of_charge.magnitude,
                POLARIZATION_VOLTAGE_METRIC: (
                    result.final_state.polarization_voltage.magnitude
                ),
                OHMIC_DROP_METRIC: result.ohmic_drop.magnitude,
                HEAT_GENERATION_METRIC: result.heat_generation.magnitude,
                ELECTRICAL_LOSS_METRIC: result.electrical_loss.magnitude,
            },
            # NOT_APPLICABLE, not CONVERGED. Both updates are closed form: they
            # neither converge nor fail to, and the core's contract says the two
            # must not be conflated.
            convergence=ConvergenceState.NOT_APPLICABLE,
            iterations=1,
            wall_seconds=time.perf_counter() - started,
            diagnostics={
                "step": result.to_dict(),
                "realization": step.realization.realization_id,
                "ocv_authority_digest": step.cell.ocv_digest,
            },
        )

    _METRIC_UNITS = {
        TERMINAL_VOLTAGE_METRIC: ctx.VOLTAGE_UNIT,
        OPEN_CIRCUIT_VOLTAGE_METRIC: ctx.VOLTAGE_UNIT,
        STATE_OF_CHARGE_METRIC: ctx.DIMENSIONLESS,
        POLARIZATION_VOLTAGE_METRIC: ctx.VOLTAGE_UNIT,
        OHMIC_DROP_METRIC: ctx.VOLTAGE_UNIT,
        HEAT_GENERATION_METRIC: ctx.POWER_UNIT,
        ELECTRICAL_LOSS_METRIC: et.ENERGY_UNIT,
    }

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        if not raw.succeeded:
            return {}
        return {
            metric: Quantity(value, self._METRIC_UNITS[metric])
            for metric, value in raw.values.items()
        }

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        """Three checks, establishing three different things on purpose.

        ``metric_dimensions``
            Every produced metric carries the dimension the model record
            declares. It compares the solver against a reference outside its own
            arithmetic, and it is the one check here that establishes a level.

        ``electrothermal_terminal_residual``
            ``V - OCV(z) + I R0 + v_p``, which must vanish.

        ``electrothermal_energy_residual``
            The reported dissipation against ``I (OCV - V)`` recomputed from the
            interval's mean polarization voltage.

        The last two compare an expression against the equation it was derived
        from, with no independent reference. That is weaker evidence than the
        sibling solvers have for their own levels, so they **establish nothing**
        and say so.
        """
        step: PreparedElectrothermalStep = prepared.payload
        if not raw.succeeded:
            return ValidationReport(
                checks=(
                    ValidationCheck(
                        name="electrothermal_step_evaluated",
                        outcome=ValidationOutcome.FAIL,
                        detail="the solve did not succeed; no residual exists",
                    ),
                )
            )
        payload = raw.diagnostics["step"]
        return ValidationReport(
            checks=(
                self._dimension_check(prepared, raw),
                self._terminal_check(raw, payload),
                self._energy_check(step, raw, payload),
            )
        )

    def _dimension_check(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationCheck:
        declared = {
            spec.metric: spec.unit_exemplar
            for spec in ELECTROTHERMAL_1RC_MODEL.outputs
        }
        produced = self.extract_metrics(prepared, raw)
        mismatched = sorted(
            metric
            for metric, value in produced.items()
            if metric not in declared or not value.is_compatible_with(declared[metric])
        )
        passed = not mismatched
        return ValidationCheck(
            name="metric_dimensions",
            outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
            # Conditional on the outcome: a serialized check reading
            # ``outcome: fail`` beside a level contradicts itself for a reader
            # who does not know that ``attained_levels`` filters on the outcome.
            establishes=ValidationLevel.DIMENSIONALLY_VALID if passed else None,
            # A dimension match leaves no residual that could be small, so the
            # reference it was made against is the only evidence a comparison
            # happened -- and a level with no evidence behind it reads exactly
            # like one nobody checked.
            evidence=tuple(
                f"{metric}={unit}" for metric, unit in sorted(declared.items())
            ),
            detail=(
                f"{len(produced)} produced metrics checked against the "
                f"dimensions their model record declares"
                if passed
                else f"metrics disagree with the model record: {mismatched}"
            ),
        )

    def _terminal_check(self, raw: RawSolverOutput, payload: Any) -> ValidationCheck:
        ocv = raw.values[OPEN_CIRCUIT_VOLTAGE_METRIC]
        terminal = raw.values[TERMINAL_VOLTAGE_METRIC]
        ohmic = raw.values[OHMIC_DROP_METRIC]
        polarization = raw.values[POLARIZATION_VOLTAGE_METRIC]
        residual = abs(terminal - (ocv - ohmic - polarization))
        scale = max(abs(ocv), 1e-12)
        passed = residual <= RESIDUAL_RELATIVE_TOLERANCE * scale
        return ValidationCheck(
            name="electrothermal_terminal_residual",
            outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
            detail=(
                f"V - (OCV - I R0 - v_p) = {residual:.3e} V against "
                f"{RESIDUAL_RELATIVE_TOLERANCE:.0e} relative"
            ),
        )

    def _energy_check(
        self,
        step: PreparedElectrothermalStep,
        raw: RawSolverOutput,
        payload: Any,
    ) -> ValidationCheck:
        current = step.current.magnitude_in(ctx.CURRENT_UNIT)
        duration = step.duration.magnitude_in(ctx.TIME_UNIT)
        r0 = Quantity.from_dict(payload[et.OHMIC_RESISTANCE]).magnitude_in(
            ctx.RESISTANCE_UNIT
        )
        mean_vp = Quantity.from_dict(
            payload["mean_polarization_voltage"]
        ).magnitude_in(ctx.VOLTAGE_UNIT)
        expected = current * current * r0 + current * mean_vp
        reported = raw.values[HEAT_GENERATION_METRIC]
        energy = raw.values[ELECTRICAL_LOSS_METRIC]
        residual = max(
            abs(reported - expected),
            abs(energy - reported * duration) / max(duration, 1e-12),
        )
        scale = max(abs(expected), 1e-12)
        passed = (
            residual <= RESIDUAL_RELATIVE_TOLERANCE * scale
            and math.isfinite(reported)
        )
        return ValidationCheck(
            name="electrothermal_energy_residual",
            outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
            detail=(
                f"reported dissipation against I^2 R0 + I <v_p>, and the energy "
                f"against its own power-time product: {residual:.3e} W"
            ),
        )


def _physical_key(cell: et.ElectrothermalCell) -> tuple:
    return (
        cell.cell_id,
        cell.nominal_capacity.magnitude,
        cell.coulombic_efficiency.magnitude,
        cell.ohmic_resistance.reference_value.magnitude,
        cell.ohmic_resistance.activation_energy.magnitude,
        cell.polarization_resistance.reference_value.magnitude,
        cell.polarization_resistance.activation_energy.magnitude,
        cell.polarization_capacitance.magnitude,
        cell.ocv_digest,
    )


ELECTROTHERMAL_MODELS = (ELECTROTHERMAL_1RC_MODEL,)
ELECTROTHERMAL_REALIZATIONS = (ELECTROTHERMAL_1RC_REALIZATION,)


def electrothermal_solver_capabilities() -> frozenset[SolverCapability]:
    return frozenset({ELECTROTHERMAL_CELL_STEP, CoreCapabilities.ALGEBRAIC})


__all__ = [
    "BACKEND",
    "build_electrothermal_problem",
    "CHARGE_STATE_BASIS",
    "ELECTRICAL_LOSS_METRIC",
    "ELECTROTHERMAL_1RC_MODEL",
    "ELECTROTHERMAL_1RC_REALIZATION",
    "ELECTROTHERMAL_CELL_STATE",
    "ELECTROTHERMAL_CELL_STEP",
    "ELECTROTHERMAL_MODELS",
    "ELECTROTHERMAL_REALIZATIONS",
    "ElectrothermalCellSolver",
    "HEAT_GENERATION_METRIC",
    "INITIAL_POLARIZATION_VOLTAGE",
    "INITIAL_STATE_OF_CHARGE",
    "LOAD_CURRENT",
    "MODEL_ID",
    "MODEL_VERSION",
    "OHMIC_ACTIVATION_ENERGY",
    "OHMIC_DROP_METRIC",
    "OHMIC_RESISTANCE_REFERENCE",
    "OPEN_CIRCUIT_VOLTAGE_METRIC",
    "POLARIZATION_ACTIVATION_ENERGY",
    "POLARIZATION_CAPACITANCE",
    "POLARIZATION_RESISTANCE_REFERENCE",
    "POLARIZATION_VOLTAGE_METRIC",
    "PreparedElectrothermalStep",
    "REFERENCE_TEMPERATURE",
    "REQUIRED_BODY_TEMPERATURE",
    "SOLVER_ID",
    "SOLVER_VERSION",
    "STATE_OF_CHARGE_METRIC",
    "TERMINAL_VOLTAGE_METRIC",
    "electrothermal_solver_capabilities",
    "flagship_cell",
]
