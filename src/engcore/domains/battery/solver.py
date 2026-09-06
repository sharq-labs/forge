"""Closed-form evaluator for one interval of constant-current discharge.

Advances one declared cell under one declared load over one interval. The
arithmetic is four expressions and no iteration:

    z_end = z_0 - eta I t / Q_nom            coulomb counting
    V     = OCV(z_end) - I R_int             Rint circuit
    Q_gen = I^2 R_int                        irreversible heat
    t_run = (z_0 - z_stop) Q_nom / (eta I)   runtime to the binding cutoff

One solver discharges four models. That is not a merge of the claims: each
model keeps its own record, its own validity domain and its own realization,
and :meth:`BatteryCellSolver.metrics_for` returns only the metrics the model
being realized actually declares. Sharing an implementation between records is
what ``ImplementationReference`` is for; sharing a *validity domain* between
them is what this domain refuses to do.

What ``validate`` establishes, and what it does not
---------------------------------------------------
Three checks run. One establishes ``DIMENSIONALLY_VALID`` and is the only
level this solver claims. The other two are residuals of each closed form
against the relation it solves; they do real work — a flipped sign, a wrong
efficiency or a mis-ordered cutoff each leave them non-zero — but they compare
an expression against the equation it was derived from, with no independent
reference. That is weaker than what the byte-pinned conduction solver has, and
that solver claims no more than dimensional validity either. So these two
declare **no level**, and say so.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ...scientific.errors import InvalidScientificProblem
from ...scientific.realizations.definition import ModelRealizationDefinition
from ...scientific.ir.problem import ScientificProblem
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.capability import SolverCapability
from ...scientific.solvers.protocol import (
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ...scientific.units.quantity import Quantity
from . import context as ctx
from . import models as mdl
from .cell import CellSpecification, DischargeLoad

SOLVER_ID = "engcore.battery.cell_closed_form"
SOLVER_VERSION = "0.1.0"
BACKEND = "python.float"

#: Relative tolerance on the two closed-form residuals. Both are exact in real
#: arithmetic, so this bounds floating-point round-off in a handful of
#: multiplications and nothing else. It is a numerical tolerance on a
#: verification check, not a scientific bound, and it appears in no validity
#: domain.
RESIDUAL_RELATIVE_TOLERANCE = 1e-12


@dataclass(frozen=True)
class PreparedCellStep:
    """The cell, the load and the realization this step will discharge."""

    cell: CellSpecification
    load: DischargeLoad
    realization: ModelRealizationDefinition


@dataclass(frozen=True)
class CellStepValues:
    """Every number one step produces, before any model claims any of them.

    Held as a record rather than a bare dict so the solver's own arithmetic and
    its validation share one definition of what was computed, and so a reader
    can see which of these are always present (the first four) and which exist
    only when a cutoff was declared.
    """

    final_state_of_charge: float
    open_circuit_voltage: float
    terminal_voltage: float
    heat_generation: float
    runtime_to_cutoff: float | None
    effective_capacity: float | None
    binding_cutoff_state_of_charge: float | None


def evaluate_step(cell: CellSpecification, load: DischargeLoad) -> CellStepValues:
    """The whole of this domain's arithmetic, as a pure function.

    Separate from the solver so it can be tested and reused without a binding
    table, and so the coupling module can march a discharge forward without
    rebinding a solver at every step. Nothing here reads a validity condition:
    computing a number and being entitled to it are different questions, kept
    in different modules.
    """
    capacity_ah = cell.nominal_capacity.magnitude_in(ctx.CAPACITY_UNIT)
    resistance_ohm = cell.internal_resistance.magnitude_in(ctx.RESISTANCE_UNIT)
    efficiency = cell.coulombic_efficiency.magnitude_in(ctx.DIMENSIONLESS)
    low = cell.open_circuit_voltage_at_empty.magnitude_in(ctx.VOLTAGE_UNIT)
    high = cell.open_circuit_voltage_at_full.magnitude_in(ctx.VOLTAGE_UNIT)

    current_a = load.current.magnitude_in(ctx.CURRENT_UNIT)
    initial_soc = load.initial_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
    # Hours, because the capacity is in ampere-hours. The conversion is done
    # through Quantity rather than by a literal 3600, so a load declared in
    # minutes and one declared in seconds reach the same number.
    duration_h = load.duration.magnitude_in("hour")

    charge_removed = efficiency * current_a * duration_h / capacity_ah
    final_soc = initial_soc - charge_removed
    ocv = low + (high - low) * final_soc
    terminal = ocv - current_a * resistance_ohm
    heat = current_a * current_a * resistance_ohm

    binding = _binding_cutoff(cell, load, low, high, resistance_ohm, current_a)
    runtime_s: float | None = None
    if binding is not None:
        # Time to walk from z_0 down to the binding cutoff at this current.
        # Negative when the run already starts below the cutoff, which is a
        # real answer to a badly posed question and is reported rather than
        # clipped: the runtime model's own conditions are where that is judged.
        runtime_s = (
            (initial_soc - binding) * capacity_ah / (efficiency * current_a)
        ) * 3600.0

    effective_capacity = None
    exponent = cell.limits.peukert_exponent
    reference = cell.limits.peukert_reference_current
    if exponent is not None and reference is not None:
        derated = ctx.peukert_effective_capacity(
            nominal_capacity=cell.nominal_capacity,
            current=load.current,
            reference_current=reference,
            exponent=exponent,
        )
        effective_capacity = (
            None if derated is None else derated.magnitude_in(ctx.CAPACITY_UNIT)
        )

    return CellStepValues(
        final_state_of_charge=final_soc,
        open_circuit_voltage=ocv,
        terminal_voltage=terminal,
        heat_generation=heat,
        runtime_to_cutoff=runtime_s,
        effective_capacity=effective_capacity,
        binding_cutoff_state_of_charge=binding,
    )


def _binding_cutoff(
    cell: CellSpecification,
    load: DischargeLoad,
    low: float,
    high: float,
    resistance_ohm: float,
    current_a: float,
) -> float | None:
    """The state of charge at which the run stops, or ``None`` if none was set.

    Whichever declared cutoff is reached first stops the run, and on a falling
    state of charge "first" means "at the higher state of charge". Selected by
    comparison and never by iteration.

    A voltage cutoff is converted to a state of charge through the same chord
    inversion :func:`~engcore.domains.battery.context.
    voltage_cutoff_state_of_charge` uses, so the runtime and the consistency
    condition rest on one definition rather than two that could drift apart.
    """
    candidates: list[float] = []
    if load.cutoff_state_of_charge is not None:
        candidates.append(
            load.cutoff_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        )
    if load.cutoff_voltage is not None:
        candidates.append(
            (
                load.cutoff_voltage.magnitude_in(ctx.VOLTAGE_UNIT)
                + current_a * resistance_ohm
                - low
            )
            / (high - low)
        )
    return max(candidates) if candidates else None


class BatteryCellSolver:
    """Advances one cell over one interval. Satisfies the solver protocol.

    The cell and its load are bound to this instance by problem id, exactly as
    the sibling thermal and electrical domains bind their systems. The binding
    table is instance-local state and never a global registry.
    """

    def __init__(self, settings: SolverSettings | None = None) -> None:
        self._bound: dict[str, tuple[CellSpecification, DischargeLoad]] = {}
        self.settings = settings or SolverSettings()

    # -- identity ---------------------------------------------------------
    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        return mdl.battery_solver_capabilities()

    # -- binding ----------------------------------------------------------
    def bind_cell(
        self, cell: CellSpecification, load: DischargeLoad, problem_id: str
    ) -> None:
        """Associate a cell and its load with a problem id.

        Rebinding is idempotent for the same *physical* cell and refused for a
        different one, keyed on :attr:`CellSpecification.physical_key`. So the
        same cell under a second load, at a second temperature or over a second
        interval rebinds freely — those are operating points — while swapping
        the cell itself is refused, because that would let two results claim
        one identity while describing different systems.
        """
        if not isinstance(cell, CellSpecification):
            raise InvalidScientificProblem("bind_cell expects a CellSpecification")
        if not isinstance(load, DischargeLoad):
            raise InvalidScientificProblem("bind_cell expects a DischargeLoad")
        key = str(problem_id)
        existing = self._bound.get(key)
        if existing is not None and existing[0].physical_key != cell.physical_key:
            raise InvalidScientificProblem(
                f"problem {key!r} is already bound to a different cell; "
                f"silently swapping the cell behind a problem id would let "
                f"two results claim one identity while describing different "
                f"systems"
            )
        self._bound[key] = (cell, load)

    @staticmethod
    def verify_problem_matches_cell(
        problem: ScientificProblem,
        cell: CellSpecification,
        load: DischargeLoad,
    ) -> None:
        """Refuse a problem describing a different cell than the one bound.

        The sibling domains guard exactly this, on the grounds that a result
        whose provenance contradicts the system that produced it is worse than
        no result. Without the guard,
        ``build_battery_problem(cellA, ...)`` followed by
        ``bind_cell(cellB, ...)`` would yield a result attributed to a problem
        describing something else, with provenance mixing the two.

        The optional declarations are checked on the same terms and for the
        same reason one level further out: a problem claiming a rating the
        bound cell does not have would produce a validity verdict attributed
        to a cell that never had the evidence behind it.
        """
        for name, declared in (
            (ctx.NOMINAL_CAPACITY, cell.nominal_capacity),
            (ctx.INTERNAL_RESISTANCE, cell.internal_resistance),
            (ctx.OCV_AT_FULL, cell.open_circuit_voltage_at_full),
            (ctx.OCV_AT_EMPTY, cell.open_circuit_voltage_at_empty),
            (ctx.COULOMBIC_EFFICIENCY, cell.coulombic_efficiency),
            (ctx.DURATION, load.duration),
        ):
            stated = problem.parameter(name).value
            if not isinstance(stated, Quantity) or stated.compare(declared) != 0.0:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} states {name} = {stated} "
                    f"but the bound cell declares {declared}"
                )

        declared_names = {p.name for p in problem.parameters}
        for spec in ctx.LIMIT_SPECS:
            value = getattr(cell.limits, spec.name)
            if value is None:
                continue
            if spec.name not in declared_names:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} omits {spec.name}, which "
                    f"the bound cell declares"
                )
            if problem.parameter(spec.name).value != value:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} states {spec.name} = "
                    f"{problem.parameter(spec.name).value} but the bound cell "
                    f"declares {value}"
                )

        initial = problem.initial_conditions
        if len(initial) != 1 or initial[0].variable != ctx.STATE_OF_CHARGE:
            raise InvalidScientificProblem(
                f"problem {problem.problem_id!r} must carry exactly one "
                f"initial condition, on {ctx.STATE_OF_CHARGE!r}"
            )
        if initial[0].value.compare(load.initial_state_of_charge) != 0.0:
            raise InvalidScientificProblem(
                f"problem {problem.problem_id!r} starts at {initial[0].value} "
                f"but the bound load declares {load.initial_state_of_charge}"
            )

    def supports(self, problem: ScientificProblem) -> bool:
        return mdl.CELL_DISCHARGE_STEP.name in problem.required_capabilities

    # -- lifecycle --------------------------------------------------------
    def prepare(
        self,
        problem: ScientificProblem,
        *,
        realization: ModelRealizationDefinition = mdl.RINT_OCV_REALIZATION,
    ) -> PreparedSolve:
        bound = self._bound.get(problem.problem_id)
        if bound is None:
            raise InvalidScientificProblem(
                f"no cell is bound to problem {problem.problem_id!r}; call "
                f"bind_cell first"
            )
        cell, load = bound
        # Refuse an inconsistent pairing before solving, not after attributing.
        self.verify_problem_matches_cell(problem, cell, load)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.settings,
            payload=PreparedCellStep(cell=cell, load=load, realization=realization),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        step: PreparedCellStep = prepared.payload
        started = time.perf_counter()
        computed = evaluate_step(step.cell, step.load)

        values: dict[str, float] = {
            mdl.FINAL_STATE_OF_CHARGE_METRIC: computed.final_state_of_charge,
            mdl.OPEN_CIRCUIT_VOLTAGE_METRIC: computed.open_circuit_voltage,
            mdl.TERMINAL_VOLTAGE_METRIC: computed.terminal_voltage,
            mdl.HEAT_GENERATION_METRIC: computed.heat_generation,
        }
        # A runtime to no declared cutoff, and a derating with no declared
        # exponent, are not zero and not infinite: they are metrics this run
        # does not produce, and they are absent rather than defaulted.
        if computed.runtime_to_cutoff is not None:
            values[mdl.RUNTIME_METRIC] = computed.runtime_to_cutoff
        if computed.effective_capacity is not None:
            values[mdl.EFFECTIVE_CAPACITY_METRIC] = computed.effective_capacity

        return RawSolverOutput(
            values=values,
            # NOT_APPLICABLE, not CONVERGED. Every expression here is closed
            # form: it neither converges nor fails to, and the core's contract
            # says the two must not be conflated.
            convergence=ConvergenceState.NOT_APPLICABLE,
            iterations=1,
            wall_seconds=time.perf_counter() - started,
            diagnostics={
                "charge_removed_fraction": (
                    step.load.initial_state_of_charge.magnitude_in(
                        ctx.DIMENSIONLESS
                    )
                    - computed.final_state_of_charge
                ),
                "binding_cutoff_state_of_charge": (
                    computed.binding_cutoff_state_of_charge
                ),
                "realization": step.realization.realization_id,
            },
        )

    # -- interpretation ---------------------------------------------------
    _METRIC_UNITS = {
        mdl.FINAL_STATE_OF_CHARGE_METRIC: ctx.DIMENSIONLESS,
        mdl.OPEN_CIRCUIT_VOLTAGE_METRIC: ctx.VOLTAGE_UNIT,
        mdl.TERMINAL_VOLTAGE_METRIC: ctx.VOLTAGE_UNIT,
        mdl.HEAT_GENERATION_METRIC: ctx.POWER_UNIT,
        mdl.RUNTIME_METRIC: ctx.TIME_UNIT,
        mdl.EFFECTIVE_CAPACITY_METRIC: ctx.CAPACITY_UNIT,
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

    def metrics_for(
        self,
        model_id: str,
        prepared: PreparedSolve,
        raw: RawSolverOutput,
    ) -> dict[str, Quantity]:
        """Only the metrics ``model_id`` actually declares as outputs.

        One evaluator produces the union; each model claims its own share. A
        consumer asking what the coulomb-counting model produced must not be
        handed a terminal voltage, because that number rests on the Rint
        model's assumptions and carries the Rint model's validity verdict, not
        this one's.
        """
        declared = {
            model.model_id: model.provided_metrics for model in mdl.BATTERY_MODELS
        }
        if model_id not in declared:
            raise InvalidScientificProblem(
                f"unknown battery model {model_id!r}"
            )
        produced = self.extract_metrics(prepared, raw)
        return {
            metric: value
            for metric, value in produced.items()
            if metric in declared[model_id]
        }

    # -- validation -------------------------------------------------------
    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        """Check each closed form against the relation it claims to solve.

        Three checks, and they establish different things on purpose:

        ``metric_dimensions``
            Every produced metric carries the dimension its model's
            ``ModelOutputSpec`` declares. This is a real, independent check —
            it compares the solver against the model records rather than
            against itself — and it is the one check here that establishes a
            level: ``DIMENSIONALLY_VALID``.

        ``coulomb_balance_residual``
            The state-of-charge update against ``dz/dt = -eta I / Q_nom``.

        ``rint_terminal_residual``
            The terminal voltage against ``V - OCV(z) + I R_int = 0``.

        The last two **establish no level, deliberately.** They do real work: a
        flipped sign, a dropped efficiency or a wrong chord each leave them
        non-zero. But each compares an expression against the equation it was
        derived from, with no independent reference — weaker evidence than the
        byte-pinned conduction solver has, and that solver claims only
        dimensional validity. Awarding a higher level here, from weaker
        evidence, is exactly the unearned claim the result contract exists to
        refuse.
        """
        step: PreparedCellStep = prepared.payload
        if not raw.succeeded:
            return ValidationReport(
                checks=(
                    ValidationCheck(
                        name="cell_step_evaluated",
                        outcome=ValidationOutcome.FAIL,
                        detail="the solve did not succeed; no residual exists",
                    ),
                )
            )

        cell, load = step.cell, step.load
        return ValidationReport(
            checks=(
                self._dimension_check(prepared, raw),
                self._coulomb_check(cell, load, raw),
                self._terminal_check(cell, load, raw),
            )
        )

    def _dimension_check(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationCheck:
        declared: dict[str, str] = {
            spec.metric: spec.unit_exemplar
            for model in mdl.BATTERY_MODELS
            for spec in model.outputs
        }
        produced = self.extract_metrics(prepared, raw)
        mismatched = [
            metric
            for metric, value in produced.items()
            if metric not in declared
            or not value.is_compatible_with(declared[metric])
        ]
        passed = not mismatched
        return ValidationCheck(
            name="metric_dimensions",
            outcome=(
                ValidationOutcome.PASS if passed else ValidationOutcome.FAIL
            ),
            # The one level this solver claims, and it is earned: the check
            # compares what was computed against what the model records
            # declare, which is a reference outside the arithmetic.
            #
            # Conditional on the outcome. `attained_levels` filters on
            # `passed` so this changes no verdict, but a serialized check
            # reading `outcome: fail` beside `establishes: dimensionally_valid`
            # contradicts itself for a reader who does not know that.
            establishes=(
                ValidationLevel.DIMENSIONALLY_VALID if passed else None
            ),
            detail=(
                f"{len(produced)} produced metrics checked against the "
                f"dimensions their model records declare"
                + (f"; mismatched: {sorted(mismatched)}" if mismatched else "")
            ),
        )

    @staticmethod
    def _coulomb_check(
        cell: CellSpecification, load: DischargeLoad, raw: RawSolverOutput
    ) -> ValidationCheck:
        capacity_ah = cell.nominal_capacity.magnitude_in(ctx.CAPACITY_UNIT)
        efficiency = cell.coulombic_efficiency.magnitude_in(ctx.DIMENSIONLESS)
        current_a = load.current.magnitude_in(ctx.CURRENT_UNIT)
        duration_h = load.duration.magnitude_in("hour")
        initial = load.initial_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        final = raw.values[mdl.FINAL_STATE_OF_CHARGE_METRIC]

        # dz/dt of the closed form is constant, so the residual of the balance
        # is exact everywhere on the interval and is evaluated once.
        derivative = (final - initial) / duration_h if duration_h else 0.0
        residual = abs(derivative + efficiency * current_a / capacity_ah)
        scale = max(abs(efficiency * current_a / capacity_ah), 1.0)
        tolerance = RESIDUAL_RELATIVE_TOLERANCE * scale
        return ValidationCheck(
            name="coulomb_balance_residual",
            outcome=(
                ValidationOutcome.PASS
                if residual <= tolerance
                else ValidationOutcome.FAIL
            ),
            establishes=None,
            residual=residual,
            tolerance=tolerance,
            detail=(
                f"|dz/dt + eta I / Q_nom| = {residual:.3e} per hour against a "
                f"scale of {scale:.3e}. Verification of the closed form "
                f"against the balance it solves; no physical validation and "
                f"no coupled-convergence claim."
            ),
        )

    @staticmethod
    def _terminal_check(
        cell: CellSpecification, load: DischargeLoad, raw: RawSolverOutput
    ) -> ValidationCheck:
        resistance_ohm = cell.internal_resistance.magnitude_in(ctx.RESISTANCE_UNIT)
        current_a = load.current.magnitude_in(ctx.CURRENT_UNIT)
        ocv = raw.values[mdl.OPEN_CIRCUIT_VOLTAGE_METRIC]
        terminal = raw.values[mdl.TERMINAL_VOLTAGE_METRIC]

        residual = abs(terminal - ocv + current_a * resistance_ohm)
        scale = max(abs(ocv), 1.0)
        tolerance = RESIDUAL_RELATIVE_TOLERANCE * scale
        return ValidationCheck(
            name="rint_terminal_residual",
            outcome=(
                ValidationOutcome.PASS
                if residual <= tolerance
                else ValidationOutcome.FAIL
            ),
            establishes=None,
            residual=residual,
            tolerance=tolerance,
            detail=(
                f"|V - OCV(z) + I R_int| = {residual:.3e} V against a scale "
                f"of {scale:.3e} V. Verification of the closed form against "
                f"the circuit relation it states; no physical validation."
            ),
        )


def cell_heat_generation(
    cell: CellSpecification, load: DischargeLoad
) -> Quantity:
    """I^2 R_int for this cell and load, as a Quantity.

    A named entry point for the one number the thermal side of a coupled run
    needs, so the coupling module does not have to reach into a raw output map
    to find it. The exclusion of the reversible term is documented on
    :func:`~engcore.domains.battery.context.heat_generation` and applies here
    unchanged.
    """
    heat = ctx.heat_generation(
        current=load.current, internal_resistance=cell.internal_resistance
    )
    if heat is None:  # pragma: no cover - both are required on their records
        raise InvalidScientificProblem(
            "a cell and a load always carry a current and a resistance"
        )
    return heat


def finite(value: float) -> bool:
    """Whether a raw magnitude may cross into interpreted science.

    Raw solver output is the sanctioned home for non-finite numbers and
    :class:`Quantity` is where they stop. Nothing in this domain can produce
    one from finite declarations, so this exists for a caller marching a long
    run to assert that fact rather than assume it.
    """
    return math.isfinite(value)
