"""Running a cell against the existing lumped thermal model, honestly.

The cell dissipates ``I^2 R_int`` into a body; the body's temperature rises;
the cell's temperature-dependent conditions see the new operating point and can
flip to OUTSIDE_VALIDATED_DOMAIN. This module marches that forward.

Three claims, kept apart on purpose
------------------------------------
A run here produces three statements that are routinely confused, and this
module holds them in three different places with three different types so that
none can stand in for another:

1. **Numerical convergence** of each sub-solve — the thermal step's
   ``ConvergenceState``. Both participants are closed forms, so it is
   ``NOT_APPLICABLE`` at every step and stays that way. It says nothing about
   the coupling and nothing about whether either model applies.
2. **Coupling structure** — :class:`CouplingDirection`, on the run. It says how
   the two sub-models depend on each other, and it is ``ONE_WAY`` here.
3. **Scientific validity** — a :class:`ValidityAssessment` per step. This is
   the one that *changes* during a run, which is the whole point of marching.

Why the coupling is one-way, and why that is not hidden
--------------------------------------------------------
With a constant ``R_int``, the heat ``I^2 R_int`` does not depend on
temperature. The dependency graph is therefore acyclic: the cell drives the
body and the body does not drive the cell back. There is no fixed point, so
there is nothing to iterate toward and nothing to converge.

The temptation is to run a fixed-point loop anyway and report
``CRITERION_MET`` on the first pass, because that produces a record that
*looks* like the electrothermal pack's. It would be a fabricated convergence
claim about an iteration that was never needed, and it is exactly the kind of
unearned statement the rest of this repository refuses. So this module iterates
nothing and says so in a field named for the structure rather than for a
verdict.

A genuinely two-way coupling needs ``R_int(T)``, which this domain does not
model — an ``R_int`` that rises as the cell cools would feed temperature back
into the heat. That is a real next model, it is out of scope for v0, and it is
recorded in ``NEEDS.md`` rather than approximated here.

What this module does not do
-----------------------------
It does not modify ``systems/electrothermal/``, import from it, or reimplement
it. It consumes the **public API** of ``domains.thermal_models.lumped``:
``ThermalBody``, ``build_lumped_thermal_problem``, ``LumpedThermalSolver`` and
``assess_lumped_validity``. Whether a composition helper of this shape belongs
under ``systems/`` is argued in ``NEEDS.md``; it is not decided here by putting
it there.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from ...scientific.errors import InvalidScientificProblem
from ...scientific.models.definition import ValidityAssessment, ValidityStatus
from ...scientific.results.validation import ValidationReport
from ...scientific.solvers.protocol import ConvergenceState
from ...scientific.units.quantity import Quantity
from ..thermal_models import lumped as lump
from . import cell as bat
from . import context as ctx
from . import models as mdl
from .solver import cell_heat_generation, evaluate_step

#: The largest number of steps a march will take before stopping and saying so.
#: Not a convergence criterion and not a physical bound: a guard against an
#: unbounded loop, whose only effect is which :class:`MarchOutcome` is
#: reported. A caller wanting more steps declares more.
DEFAULT_STEP_LIMIT = 1000

#: The instant a step begins at — the temperature and state of charge the cell
#: model is evaluated at.
STEP_START = "step_start"

#: The instant a step ends at — where the body reached, and where the next step
#: begins.
STEP_END = "step_end"

#: The instants a step's validity is assessed at, in temporal order.
#:
#: **Why these two and no more.** The lumped response over a step is
#: ``T(t) = T_ss + (T_0 - T_ss) exp(-t/tau)``, which is monotonic in ``t``; the
#: heat and the discharge current are constant across the step. The extrema of
#: every temperature-dependent condition over the interval are therefore its
#: endpoints, and assessing both is assessing the whole step rather than
#: sampling it. A model whose state moved non-monotonically within a step would
#: need more instants, and this tuple is where that would be said.
ASSESSED_INSTANTS = (STEP_START, STEP_END)


def _over_the_step(
    per_instant: Sequence[Mapping[str, ValidityAssessment]],
) -> dict[str, ValidityAssessment]:
    """One verdict per model over the whole interval, from the instants in it.

    A condition is **satisfied over the step** only if it was satisfied at every
    instant assessed and questioned at none. Anything violated at any instant is
    violated over the step; anything unknown at any instant, and violated at
    none, is unknown over it.

    That ordering is the same precedence ``ValidityDomain.assess`` applies
    within one instant, applied again across instants — a finding outranks a
    gap, and a gap outranks a claim of satisfaction. The result's condition
    lists are disjoint, so its status is exactly what the shared classification
    implies and the record can cross a reporting boundary unaltered.
    """
    model_ids: list[str] = []
    for instant in per_instant:
        for model_id in instant:
            if model_id not in model_ids:
                model_ids.append(model_id)

    combined: dict[str, ValidityAssessment] = {}
    for model_id in model_ids:
        assessments = [i[model_id] for i in per_instant if model_id in i]
        violated: list[str] = []
        unknown: list[str] = []
        satisfied: list[str] = []
        for assessment in assessments:
            for name in assessment.violated:
                if name not in violated:
                    violated.append(name)
            for name in assessment.unknown:
                if name not in unknown:
                    unknown.append(name)
            for name in assessment.satisfied:
                if name not in satisfied:
                    satisfied.append(name)
        unknown = [n for n in unknown if n not in violated]
        satisfied = [
            n for n in satisfied if n not in violated and n not in unknown
        ]
        if violated:
            status = ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        elif unknown:
            status = ValidityStatus.UNKNOWN
        elif satisfied:
            status = ValidityStatus.IN_DOMAIN
        else:
            status = ValidityStatus.UNKNOWN
        combined[model_id] = ValidityAssessment(
            status=status,
            satisfied=tuple(satisfied),
            violated=tuple(violated),
            unknown=tuple(unknown),
        )
    return combined


class CouplingDirection(str, Enum):
    """How the two sub-models depend on each other. **Structural, not a verdict.**

    Deliberately **not** ``ConvergenceState`` and deliberately not the
    electrothermal pack's ``CouplingOutcome``. Reusing either would make "the
    two models are acyclic" and "an iteration met its criterion" the same
    serialized token, which is the conflation both of those types were written
    to prevent.

    **Only one member exists**, because only one is executed. A ``TWO_WAY``
    member would be a name minted from intuition for a case this domain cannot
    produce: nothing here makes the heat depend on the temperature, so no
    cyclic run exists to label. The sibling pack deleted a ``DIVERGED`` member
    on exactly this reasoning. When ``R_int(T)`` arrives, the member arrives
    with it and with a run that exercises it.
    """

    ONE_WAY = "one_way"


class MarchOutcome(str, Enum):
    """Why the march stopped. Also not a convergence verdict.

    Every member is reachable by this module. ``CUTOFF_REACHED`` and
    ``VALIDITY_LOST`` are both *early* stops and are kept distinct: one means
    the cell ran out of the charge the caller asked for, the other means the
    run walked outside a model's declared domain and continuing would produce
    numbers no model here is entitled to.
    """

    HORIZON_REACHED = "horizon_reached"
    CUTOFF_REACHED = "cutoff_reached"
    VALIDITY_LOST = "validity_lost"
    STEP_LIMIT_REACHED = "step_limit_reached"


@dataclass(frozen=True)
class SelfHeatingStep:
    """One interval of the march: what the cell saw, and what came out.

    ``cell_temperature`` is the temperature at the **start** of the interval —
    the value the cell model was evaluated at.  ``final_temperature`` is where
    the body ended up and is what the next step starts from. Naming them apart
    is the same discipline the domain applies to ``state_of_charge`` and
    ``final_state_of_charge``.

    **A step is an interval, and ``validity`` is a verdict about the interval.**
    It used to be a verdict about the instant the step started at, which is a
    different claim wearing the same name: a step beginning at 298 K and ending
    at 351 K recorded ``discharge_temperature_position`` as *satisfied* against
    a 333 K limit, because the only temperature anybody asked about was the one
    the cell had before it heated up. The excursion was in the record — as
    ``final_temperature`` — and the verdict beside it said the model applied.

    So the assessment is made at every instant in :data:`ASSESSED_INSTANTS`, the
    per-instant verdicts are kept in ``validity_at`` where a reader can see
    *where* in the step a condition flipped, and ``validity`` is the combination
    over the interval — satisfied only where satisfied throughout. Which
    instants were assessed is part of the record rather than part of the prose,
    because "over the whole step" is only true of the instants actually looked
    at.
    """

    index: int
    elapsed: Quantity
    cell_temperature: Quantity
    final_temperature: Quantity
    state_of_charge: Quantity
    final_state_of_charge: Quantity
    terminal_voltage: Quantity
    heat_generation: Quantity
    #: The thermal sub-solve's own report about its own termination. Closed
    #: form, so NOT_APPLICABLE — and it is carried per step rather than once
    #: per run so a reader can check that it never silently became something
    #: else halfway through.
    thermal_convergence: ConvergenceState
    #: The thermal sub-solve's verification report. Separate from
    #: ``thermal_convergence`` because "the solve terminated" and "the answer
    #: was checked" are different claims, and separate again from ``validity``
    #: because "the answer was checked" and "the model applied" are different
    #: claims still.
    thermal_validation: ValidationReport
    #: One verdict per battery model, keyed by model id, **over the whole
    #: interval this step covers**. Satisfied only where satisfied at every
    #: instant assessed. This is the field that changes across a march.
    validity: Mapping[str, ValidityAssessment]
    #: instant -> model id -> the verdict at that instant. The evidence
    #: ``validity`` is combined from, kept because "outside its domain by the
    #: end" and "outside it from the start" are different findings.
    validity_at: Mapping[str, Mapping[str, ValidityAssessment]]

    def __post_init__(self) -> None:
        missing = [i for i in ASSESSED_INSTANTS if i not in self.validity_at]
        if missing:
            raise InvalidScientificProblem(
                f"step {self.index} carries no verdict at {missing}; a "
                f"verdict over an interval may not rest on fewer instants "
                f"than the record says it was assessed at"
            )

    @property
    def assessed_instants(self) -> tuple[str, ...]:
        """The instants ``validity`` was combined from, in temporal order."""
        return tuple(
            instant for instant in ASSESSED_INSTANTS if instant in self.validity_at
        )

    def temperature_at(self, instant: str) -> Quantity:
        """The temperature the cell was assessed at, for one instant."""
        if instant == STEP_START:
            return self.cell_temperature
        if instant == STEP_END:
            return self.final_temperature
        raise InvalidScientificProblem(
            f"step {self.index} assessed no instant named {instant!r}"
        )

    def status_at(self, instant: str, model_id: str) -> ValidityStatus:
        """The verdict for one model at one instant within this step."""
        try:
            verdicts = self.validity_at[instant]
        except KeyError:
            raise InvalidScientificProblem(
                f"step {self.index} assessed no instant named {instant!r}"
            ) from None
        if model_id not in verdicts:
            raise InvalidScientificProblem(
                f"step {self.index} carries no verdict for {model_id!r} at "
                f"{instant!r}"
            )
        return verdicts[model_id].status

    def status(self, model_id: str) -> ValidityStatus:
        """The verdict for one model over this whole step."""
        if model_id not in self.validity:
            raise InvalidScientificProblem(
                f"step {self.index} carries no verdict for {model_id!r}"
            )
        return self.validity[model_id].status


@dataclass(frozen=True)
class SelfHeatingRun:
    """A marched discharge, and why it stopped.

    ``coupling`` is the **only** statement about how the two models are joined
    anywhere in this record. It is not written into any step's
    ``thermal_convergence``, into any ``ValidationReport``, or into any
    validity assessment — and it is never computed from the sub-solves' own
    convergence, which would make a closed-form evaluation look like a
    converged iteration.
    """

    coupling: CouplingDirection
    outcome: MarchOutcome
    steps: tuple[SelfHeatingStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        if not self.steps:
            raise InvalidScientificProblem(
                "a self-heating run must carry at least one step; a run that "
                "executed nothing is not a run"
            )

    @property
    def final(self) -> SelfHeatingStep:
        return self.steps[-1]

    def temperatures(self) -> tuple[Quantity, ...]:
        """The temperature the cell was evaluated at, step by step."""
        return tuple(step.cell_temperature for step in self.steps)

    def first_step_outside(self, model_id: str) -> SelfHeatingStep | None:
        """The first step at which ``model_id`` left its validated domain.

        ``None`` when it never did. Deliberately not "the first step that was
        not IN_DOMAIN": UNKNOWN is not a violation, and collapsing the two
        would report a missing declaration as a physical excursion.
        """
        for step in self.steps:
            if step.status(model_id) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
                return step
        return None


def thermal_body_for(
    cell: bat.CellSpecification,
    *,
    body_id: str | None = None,
    heat_capacity: Quantity,
    ambient_temperature: Quantity,
    initial_temperature: Quantity,
    step_duration: Quantity,
    applicability: Any = None,
) -> lump.ThermalBody:
    """A lumped body whose conductance is the one the cell declared.

    The cell's ``cell_thermal_conductance`` is the same physical ``hA`` the
    thermal body needs, and taking it from one place is what keeps the
    self-heating condition and the thermal solve talking about the same cooling
    path. A cell that declares no conductance cannot be coupled: there is no
    second source for that number and inventing one would make the coupled
    temperature rise a function of a value nobody declared.

    The heat capacity is a *thermal* property the cell record does not carry,
    so it is supplied here. That asymmetry is real rather than an oversight:
    ``hA`` appears in a battery validity condition and ``C`` does not.
    """
    conductance = cell.limits.cell_thermal_conductance
    if conductance is None:
        raise InvalidScientificProblem(
            f"cell {cell.cell_id!r} declares no "
            f"{ctx.CELL_THERMAL_CONDUCTANCE}, so it cannot be coupled to a "
            f"thermal body: the conductance the self-heating condition is "
            f"stated over and the conductance the body would exchange through "
            f"are the same number, and this domain will not invent it"
        )
    return lump.ThermalBody(
        body_id=body_id or f"battery-{cell.cell_id}",
        heat_capacity=heat_capacity,
        ambient_conductance=conductance,
        ambient_temperature=ambient_temperature,
        initial_temperature=initial_temperature,
        duration=step_duration,
        applicability=(
            applicability
            if applicability is not None
            else lump.LumpedApplicabilityDeclaration()
        ),
    )


def _advance_body(
    body: lump.ThermalBody, heat: Quantity
) -> tuple[Quantity, ConvergenceState, ValidationReport]:
    """One thermal step, through the lumped model's own public API.

    Nothing is reimplemented here: the body is bound, the problem is built by
    the thermal domain's builder, and the thermal domain's own solver produces,
    interprets and validates the step. This module reads three things out of it
    and asserts nothing about any of them.
    """
    problem = lump.build_lumped_thermal_problem(body)
    solver = lump.LumpedThermalSolver()
    solver.bind_body(body, problem.problem_id, heat_input=heat)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    return (
        metrics[lump.TEMPERATURE_METRIC],
        raw.convergence,
        solver.validate(prepared, raw),
    )


def run_self_heating_discharge(
    cell: bat.CellSpecification,
    load: bat.DischargeLoad,
    *,
    heat_capacity: Quantity,
    ambient_temperature: Quantity,
    initial_temperature: Quantity | None = None,
    steps: int = 10,
    step_limit: int = DEFAULT_STEP_LIMIT,
    stop_on_validity_loss: bool = False,
) -> SelfHeatingRun:
    """March one cell's discharge, letting its own dissipation heat it.

    Each step:

    1. evaluates the cell at the current temperature and state of charge,
    2. advances the lumped body over the step with that step's heat input,
    3. assesses the cell's validity at the start **and** the end of the step,
       and records the thermal step's convergence and validation **separately**
       from both,
    4. carries the new temperature and state of charge into the next step.

    The temperature rises because ``I^2 R_int`` is fed to a body with finite
    ``hA``; it approaches ``T_amb + Q/hA``, which is the asymptote the
    self-heating condition is stated over. A cell whose declared discharge
    temperature range or resistance span is narrower than that rise will see
    those conditions flip to OUTSIDE_VALIDATED_DOMAIN partway through the run,
    while every step's ``thermal_convergence`` stays ``NOT_APPLICABLE`` and the
    run's ``coupling`` stays ``ONE_WAY``. Those three facts are independent and
    this record keeps them so.

    ``stop_on_validity_loss`` stops the march at the first step where any
    model leaves its validated domain, reporting ``VALIDITY_LOST``. It defaults
    to ``False`` because continuing produces the evidence that a condition
    *did* flip and where — but a caller who wants the numbers to stop when the
    entitlement to them stops can say so. It reads the verdict **over the
    step**, so a step that leaves the domain before it ends stops the march at
    that step rather than one later: the temperature the step ended at is a
    temperature the run reached, and a rule that only looked at where each step
    began could report a run ending 18 K above a declared limit with the
    condition recorded as satisfied.

    ``initial_temperature`` defaults to the load's declared cell temperature,
    which is the only consistent starting point: the load says what the cell is
    at, and starting the body somewhere else would evaluate the first step at a
    temperature the run does not have.
    """
    if steps < 1:
        raise InvalidScientificProblem("a march needs at least one step")
    if steps > step_limit:
        raise InvalidScientificProblem(
            f"requested {steps} steps against a limit of {step_limit}; raise "
            f"the limit explicitly rather than having it silently truncate"
        )

    start_temperature = (
        load.cell_temperature if initial_temperature is None else initial_temperature
    )
    temperature = start_temperature
    state_of_charge = load.initial_state_of_charge
    elapsed_s = 0.0
    step_s = load.duration.magnitude_in(ctx.TIME_UNIT)

    recorded: list[SelfHeatingStep] = []
    outcome = MarchOutcome.HORIZON_REACHED

    for index in range(1, steps + 1):
        step_load = load.at(
            state_of_charge=state_of_charge, cell_temperature=temperature
        )
        computed = evaluate_step(cell, step_load)
        heat = cell_heat_generation(cell, step_load)

        body = thermal_body_for(
            cell,
            heat_capacity=heat_capacity,
            ambient_temperature=ambient_temperature,
            initial_temperature=temperature,
            step_duration=load.duration,
        )
        final_temperature, convergence, thermal_validation = _advance_body(
            body, heat
        )

        problem = bat.build_battery_problem(cell, step_load)
        # Assessed at both ends of the interval, not only at the temperature
        # the step started from. The state of charge and the current are the
        # step's own, which is what the cell model was evaluated with; only
        # the temperature moves within the step, and it moves monotonically,
        # so these two instants are its extrema.
        by_instant = {
            instant: bat.assess_all(
                problem,
                state_of_charge=state_of_charge,
                discharge_current=load.current,
                cell_temperature=instant_temperature,
            )
            for instant, instant_temperature in (
                (STEP_START, temperature),
                (STEP_END, final_temperature),
            )
        }
        verdicts = _over_the_step([by_instant[i] for i in ASSESSED_INSTANTS])

        elapsed_s += step_s
        final_soc = Quantity(computed.final_state_of_charge, ctx.DIMENSIONLESS)
        recorded.append(
            SelfHeatingStep(
                index=index,
                elapsed=Quantity(elapsed_s, ctx.TIME_UNIT),
                cell_temperature=temperature,
                final_temperature=final_temperature,
                state_of_charge=state_of_charge,
                final_state_of_charge=final_soc,
                terminal_voltage=Quantity(
                    computed.terminal_voltage, ctx.VOLTAGE_UNIT
                ),
                heat_generation=heat,
                thermal_convergence=convergence,
                thermal_validation=thermal_validation,
                validity=verdicts,
                validity_at=by_instant,
            )
        )

        if stop_on_validity_loss and any(
            assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
            for assessment in verdicts.values()
        ):
            outcome = MarchOutcome.VALIDITY_LOST
            break

        binding = computed.binding_cutoff_state_of_charge
        if binding is not None and computed.final_state_of_charge <= binding:
            outcome = MarchOutcome.CUTOFF_REACHED
            break

        temperature = final_temperature
        state_of_charge = final_soc
    else:
        outcome = (
            MarchOutcome.STEP_LIMIT_REACHED
            if steps == step_limit
            else MarchOutcome.HORIZON_REACHED
        )

    return SelfHeatingRun(
        coupling=CouplingDirection.ONE_WAY, outcome=outcome, steps=tuple(recorded)
    )


def coupled_model_ids() -> tuple[str, ...]:
    """The battery models a coupled run reports a verdict for, in fixed order."""
    return tuple(model.model_id for model in mdl.BATTERY_MODELS)
