"""Battery-owned bridge from the Rint cell's open-circuit voltage to Core inference.

The shared inference layer cannot interpret a battery metric, and should not.
This module owns that meaning: it is the one place that turns a declared cell,
at a declared state of charge, into an :class:`AdmissibleAnalyticPrediction` of
its open-circuit voltage that the frozen calibration, posterior, predictive-UQ
and adequacy machinery can consume.

Every value goes through the production solver
--------------------------------------------------
Prepare, solve, extract, validate, and a real :class:`ScientificResult` carrying
provenance -- exactly the path ``engcore.studies.tcr`` takes for the electrical
material model. Nothing shortcuts to the chord formula. If the battery solver's
validation ever stopped attaining ``DIMENSIONALLY_VALID``, admission would fail
rather than this module quietly producing an unbacked number.

The measured situation, represented rather than approximated
--------------------------------------------------------------
An open-circuit-voltage measurement is taken on a cell that was brought to a
state of charge and then left at rest. This domain's :class:`DischargeLoad`
requires a strictly positive current, so a rest cannot be declared directly,
and this module does not work around that with a vanishing current -- a
provenance record describing a microampere discharge that never happened would
be a false record of the experiment.

What CAN be declared, faithfully, is the conditioning discharge that brought
the cell there: :class:`RestedOcvCondition` states the starting state of charge,
the constant conditioning current and the target, and the load runs for exactly
the duration that brings the coulomb counter to the target. The model's
``open_circuit_voltage`` output at the end of that interval is its claim about
the equilibrium OCV at that state of charge, which is the quantity a rested cell
measures.

That output depends only on the final state of charge, never on the current. So
the conditioning current, which the experiment may not state numerically, is
immaterial to the compared value -- and :func:`ocv_prediction` refuses a result
whose final state of charge is not the declared target, so the claim holds by
check rather than by arithmetic someone trusted.

What this module does NOT do
-----------------------------
* No posterior, likelihood or adequacy arithmetic. That is the frozen Core's.
* No file parsing and no dataset constants. A measured dataset is an input.
* No terminal-voltage observable. At rest the terminal voltage is not a
  quantity this domain can declare, and under load it would need a current the
  caller measured; exposing it here would invite a comparison the experiment
  cannot support. Only ``open_circuit_voltage`` is admitted.
* No change to the model. ``battery.cell.rint_ocv`` is evaluated as shipped.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ...inference.admissibility import (
    AdmissibleAnalyticPrediction,
    InferenceAdmissibilityError,
)
from ...inference.grid import AdmittedForwardRow, AdmittedForwardTable, ObservationSet
from ...inference.parameters import (
    CalibrationParameterSet,
    ParameterBounds,
    ParameterIdentity,
)
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference
from ...scientific.results.provenance import ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.units.quantity import Quantity
from . import context as ctx
from . import models as mdl
from .cell import CellSpecification, DischargeLoad, build_battery_problem
from .solver import SOLVER_ID, SOLVER_VERSION, BatteryCellSolver

ADAPTER_ID = "battery.cell.ocv_inference_forward/0.1.0"
DOMAIN = "battery"

#: The one observable this adapter admits. See the module docstring for why a
#: terminal voltage is not among them.
OCV_OBSERVABLE = mdl.OPEN_CIRCUIT_VOLTAGE_METRIC

RINT_MODEL_REF = ModelReference(
    model_id=mdl.RINT_OCV_MODEL.model_id, version=mdl.RINT_OCV_MODEL.version
)

#: The two parameters a chord calibration estimates, in column order.
CHORD_PARAMETERS = (ctx.OCV_AT_EMPTY, ctx.OCV_AT_FULL)

ANALYTIC_BASIS = (
    "OCV(z_end) = V_empty + (V_full - V_empty) z_end, with z_end = z_0 - I t / "
    "(eta Q_nom); battery.cell.rint_ocv closed form, no discretization"
)

#: How far the coulomb counter may land from the declared target before the
#: prediction is refused. Floating-point round-off in three multiplications and
#: nothing else; not a scientific tolerance and in no validity domain.
TARGET_STATE_OF_CHARGE_TOLERANCE = 1.0e-12


@dataclass(frozen=True)
class FixedCellDeclaration:
    """What a chord calibration holds fixed about the cell.

    The two chord endpoints are deliberately absent: they are what is being
    estimated. Everything here is a declaration the caller takes from the
    cell's own documentation, and none of it is a free parameter.
    """

    cell_id: str
    nominal_capacity: Quantity
    internal_resistance: Quantity
    coulombic_efficiency: Quantity = field(
        default_factory=lambda: Quantity(1.0, ctx.DIMENSIONLESS)
    )
    chemistry: str | None = None

    def __post_init__(self) -> None:
        if not str(self.cell_id).strip():
            raise InvalidScientificProblem("a fixed cell declaration needs a cell_id")

    def cell(self, *, ocv_at_empty: Quantity, ocv_at_full: Quantity) -> CellSpecification:
        """The cell at one candidate chord. Built fresh; never cached across candidates."""
        return CellSpecification(
            cell_id=self.cell_id,
            nominal_capacity=self.nominal_capacity,
            internal_resistance=self.internal_resistance,
            open_circuit_voltage_at_full=ocv_at_full,
            open_circuit_voltage_at_empty=ocv_at_empty,
            coulombic_efficiency=self.coulombic_efficiency,
            chemistry=self.chemistry,
        )


@dataclass(frozen=True)
class RestedOcvCondition:
    """A cell discharged at constant current from one state of charge to another.

    Represents how an open-circuit-voltage measurement's state of charge was
    reached. The measurement itself is taken afterwards at rest; what this
    record declares is the part of the experiment the battery domain can state
    without inventing anything.
    """

    condition_id: str
    target_state_of_charge: Quantity
    conditioning_current: Quantity
    cell_temperature: Quantity
    initial_state_of_charge: Quantity = field(
        default_factory=lambda: Quantity(1.0, ctx.DIMENSIONLESS)
    )

    def __post_init__(self) -> None:
        if not str(self.condition_id).strip():
            raise InvalidScientificProblem("a rested OCV condition needs a condition_id")
        start = self.initial_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        target = self.target_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        if not 0.0 <= target <= 1.0 or not 0.0 <= start <= 1.0:
            raise InvalidScientificProblem(
                f"condition {self.condition_id!r}: states of charge must lie in "
                f"[0, 1], got start {start!r} and target {target!r}"
            )
        if not target < start:
            raise InvalidScientificProblem(
                f"condition {self.condition_id!r}: the target state of charge "
                f"{target!r} is not below the start {start!r}. A discharge "
                f"lowers the state of charge, and this model claims discharge "
                f"only; reaching a state of charge by charging is outside it"
            )
        if self.conditioning_current.magnitude_in(ctx.CURRENT_UNIT) <= 0.0:
            raise InvalidScientificProblem(
                f"condition {self.condition_id!r}: the conditioning current "
                f"must be strictly positive"
            )

    def load(self, fixed: FixedCellDeclaration) -> DischargeLoad:
        """The discharge that lands the coulomb counter exactly on the target."""
        start = self.initial_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        target = self.target_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        capacity_ah = fixed.nominal_capacity.magnitude_in(ctx.CAPACITY_UNIT)
        efficiency = fixed.coulombic_efficiency.magnitude_in(ctx.DIMENSIONLESS)
        current_a = self.conditioning_current.magnitude_in(ctx.CURRENT_UNIT)
        hours = (start - target) * efficiency * capacity_ah / current_a
        return DischargeLoad(
            load_id=f"{self.condition_id}.conditioning",
            current=self.conditioning_current,
            initial_state_of_charge=self.initial_state_of_charge,
            cell_temperature=self.cell_temperature,
            duration=Quantity(hours, "hour"),
        )


def build_ocv_chord_parameter_set(
    *, lower: Quantity, upper: Quantity
) -> CalibrationParameterSet:
    """The two chord endpoints, bounded by the caller's physical limits.

    One pair of bounds for both, taken by the caller from the cell's own
    voltage window. They are bounds on what the quantity may be, not a prior:
    widening them to make a fit converge would change what an open-circuit
    voltage is allowed to be.
    """
    bounds = ParameterBounds(lower, upper)
    return CalibrationParameterSet(
        tuple(
            ParameterIdentity(
                name=name, unit=ctx.VOLTAGE_UNIT, model=RINT_MODEL_REF, bounds=bounds
            )
            for name in CHORD_PARAMETERS
        )
    )


def ocv_prediction(
    fixed: FixedCellDeclaration,
    condition: RestedOcvCondition,
    *,
    ocv_at_empty: Quantity,
    ocv_at_full: Quantity,
) -> AdmissibleAnalyticPrediction:
    """One chord candidate at one condition, through the production solver, admitted."""
    cell = fixed.cell(ocv_at_empty=ocv_at_empty, ocv_at_full=ocv_at_full)
    load = condition.load(fixed)
    problem = build_battery_problem(cell, load)
    solver = BatteryCellSolver()
    solver.bind_cell(cell, load, problem.problem_id)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.metrics_for(RINT_MODEL_REF.model_id, prepared, raw)
    report = solver.validate(prepared, raw)

    target = condition.target_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
    reached = raw.values[mdl.FINAL_STATE_OF_CHARGE_METRIC]
    if abs(reached - target) > TARGET_STATE_OF_CHARGE_TOLERANCE:
        raise InferenceAdmissibilityError(
            f"condition {condition.condition_id!r}: the conditioning discharge "
            f"ended at a state of charge of {reached!r}, not the declared "
            f"target {target!r}. The open-circuit voltage it reports would be "
            f"the voltage at some other state of charge"
        )

    empty_v = ocv_at_empty.magnitude_in(ctx.VOLTAGE_UNIT)
    full_v = ocv_at_full.magnitude_in(ctx.VOLTAGE_UNIT)
    run_id = "battery-ocv-" + hashlib.sha256(
        (
            f"{fixed.cell_id}|{condition.condition_id}|{target!r}|"
            f"{empty_v!r}|{full_v!r}|"
            f"{condition.conditioning_current.magnitude_in(ctx.CURRENT_UNIT)!r}"
        ).encode("utf-8")
    ).hexdigest()[:16]
    provenance = ProvenanceRecord(
        run_id=run_id,
        models=((RINT_MODEL_REF.model_id, RINT_MODEL_REF.version),),
        solvers=((SOLVER_ID, SOLVER_VERSION),),
        inputs={
            ctx.OCV_AT_EMPTY: ocv_at_empty,
            ctx.OCV_AT_FULL: ocv_at_full,
            ctx.NOMINAL_CAPACITY: fixed.nominal_capacity,
            ctx.INTERNAL_RESISTANCE: fixed.internal_resistance,
            ctx.COULOMBIC_EFFICIENCY: fixed.coulombic_efficiency,
            ctx.STATE_OF_CHARGE: condition.initial_state_of_charge,
            ctx.DISCHARGE_CURRENT: condition.conditioning_current,
            ctx.CELL_TEMPERATURE: condition.cell_temperature,
        },
        metadata={
            "condition_id": condition.condition_id,
            "analytic_basis": ANALYTIC_BASIS,
            "represents": (
                "the constant-current conditioning discharge that brought the "
                "cell to its target state of charge; the compared quantity is "
                "the model's open-circuit voltage at the end of it"
            ),
        },
    )
    result = ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        provenance=provenance,
        models=((RINT_MODEL_REF.model_id, RINT_MODEL_REF.version),),
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        validity_not_assessed={
            RINT_MODEL_REF.model_id: (
                "not assessed by this forward evaluation: a calibration sweeps "
                "chord candidates, and an applicability verdict about a "
                "candidate is a statement about a declaration the study is "
                "still choosing. Applicability is assessed once, against the "
                "calibrated cell, where it means something"
            )
        },
    )
    return AdmissibleAnalyticPrediction(
        prediction_id=run_id,
        domain=DOMAIN,
        adapter_id=ADAPTER_ID,
        binding_ref=f"{RINT_MODEL_REF.model_id}@{RINT_MODEL_REF.version}",
        source_result=result,
        observable_names=(OCV_OBSERVABLE,),
        validation=report,
        analytic_basis=ANALYTIC_BASIS,
        verification_ref=f"solver:{SOLVER_ID}@{SOLVER_VERSION}",
        metadata={"condition_id": condition.condition_id},
    )


def candidate_refusal(
    fixed: FixedCellDeclaration, *, ocv_at_empty: Quantity, ocv_at_full: Quantity
) -> str | None:
    """Why this chord candidate is not a cell the domain can declare, or ``None``.

    A search or a grid can propose a candidate the battery domain refuses --
    most commonly ``V_full <= V_empty``, an open-circuit voltage that does not
    rise with charge. That candidate is not a poor fit, it is not a cell, and
    the Core's contract for it is refusal: :func:`engcore.inference.calibrate`
    takes ``None`` from the evaluator, and a forward table records a rejected
    row with no posterior mass. Scoring it with a large residual instead would
    let the optimizer trade a non-cell against a good fit.

    Only the DECLARATION is judged here. A solver or admission failure for a
    valid cell is not translated into a refusal; it still raises, because that
    is a defect rather than a candidate outside the domain.
    """
    try:
        fixed.cell(ocv_at_empty=ocv_at_empty, ocv_at_full=ocv_at_full)
    except InvalidScientificProblem as exc:
        return str(exc)
    return None


def _require_ocv_observations(observations: ObservationSet) -> None:
    strangers = sorted(
        {o.observable_name for o in observations.observations}
        - {OCV_OBSERVABLE}
    )
    if strangers:
        raise InferenceAdmissibilityError(
            f"this adapter admits only {OCV_OBSERVABLE!r}; observations name "
            f"{strangers}"
        )


def _conditions_for(
    observations: ObservationSet, conditions: Mapping[str, RestedOcvCondition]
) -> list[RestedOcvCondition]:
    missing = sorted(
        {o.condition_id for o in observations.observations} - set(conditions)
    )
    if missing:
        raise InferenceAdmissibilityError(
            f"no declared conditioning for observation condition(s) {missing}"
        )
    return [conditions[o.condition_id] for o in observations.observations]


def ocv_forward_table(
    observations: ObservationSet,
    grid_points: Sequence[Sequence[float]],
    *,
    fixed: FixedCellDeclaration,
    conditions: Mapping[str, RestedOcvCondition],
    counter: dict[str, int] | None = None,
) -> AdmittedForwardTable:
    """An admitted forward table over (V_empty, V_full) candidates, in volts."""
    _require_ocv_observations(observations)
    selected = _conditions_for(observations, conditions)
    rows = []
    for point in grid_points:
        empty_v, full_v = float(point[0]), float(point[1])
        refusal = candidate_refusal(
            fixed,
            ocv_at_empty=Quantity(empty_v, ctx.VOLTAGE_UNIT),
            ocv_at_full=Quantity(full_v, ctx.VOLTAGE_UNIT),
        )
        if refusal is not None:
            rows.append(
                AdmittedForwardRow.rejected((empty_v, full_v), observations, refusal)
            )
            continue
        predictions = {}
        for condition in selected:
            if counter is not None:
                counter["n"] = counter.get("n", 0) + 1
            predictions[condition.condition_id] = ocv_prediction(
                fixed,
                condition,
                ocv_at_empty=Quantity(empty_v, ctx.VOLTAGE_UNIT),
                ocv_at_full=Quantity(full_v, ctx.VOLTAGE_UNIT),
            )
        rows.append(AdmittedForwardRow((empty_v, full_v), observations, predictions))
    return AdmittedForwardTable.from_rows(
        parameter_names=CHORD_PARAMETERS, observations=observations, rows=rows
    )


def ocv_forward_evaluator(
    observations: ObservationSet,
    *,
    fixed: FixedCellDeclaration,
    conditions: Mapping[str, RestedOcvCondition],
    counter: dict[str, int] | None = None,
):
    """A forward evaluator for :func:`engcore.inference.calibrate`.

    Closes over the fixed declarations and the conditions, never over any
    measured value: each call is handed a candidate (V_empty, V_full) in volts
    and returns one open-circuit voltage per observation, in observation order.
    """
    _require_ocv_observations(observations)
    selected = _conditions_for(observations, conditions)

    def evaluate(vector: Sequence[float]):
        empty_v, full_v = float(vector[0]), float(vector[1])
        if candidate_refusal(
            fixed,
            ocv_at_empty=Quantity(empty_v, ctx.VOLTAGE_UNIT),
            ocv_at_full=Quantity(full_v, ctx.VOLTAGE_UNIT),
        ) is not None:
            return None
        out: list[Quantity] = []
        for condition in selected:
            if counter is not None:
                counter["n"] = counter.get("n", 0) + 1
            prediction = ocv_prediction(
                fixed,
                condition,
                ocv_at_empty=Quantity(empty_v, ctx.VOLTAGE_UNIT),
                ocv_at_full=Quantity(full_v, ctx.VOLTAGE_UNIT),
            )
            out.append(prediction.value(OCV_OBSERVABLE))
        return out

    return evaluate
