"""The flagship: calibrating a conductor's linear TCR law from resistance data.

    R(T) = R_ref * (1 + alpha * (T - T_ref))

Every forward evaluation goes through the PRODUCTION solver
(``ResistancePropertySolver``) and is admitted through the analytic route --
never by constructing numbers here and asserting they were admitted. The
solver reports ``ConvergenceState.NOT_APPLICABLE`` and attains
``DIMENSIONALLY_VALID``, which is what the analytic admission boundary asks
for and the whole of what this model can honestly claim.

Synthetic truth
---------------
:class:`TcrTruth` holds parameters the calibration algorithm never sees. It is
passed to :func:`synthesize_tcr_observations`, which produces observations
through the same production forward model the calibration will call, and then
adds declared Gaussian noise. The truth is available to the test that grades
the recovery and to nothing else -- in particular
:func:`tcr_forward_evaluator` closes over the *fixed* reference temperature
and the conductor id, never over the truth.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..domains.electrical import material as mat
from ..inference.admissibility import AdmissibleAnalyticPrediction
from ..inference.grid import GaussianObservation, ObservationSet
from ..inference.parameters import (
    CalibrationParameterSet,
    ParameterBounds,
    ParameterIdentity,
)
from ..scientific.ir.problem import ModelReference
from ..scientific.results.provenance import ProvenanceRecord
from ..scientific.results.result import ScientificResult
from ..scientific.units.quantity import Quantity

TCR_MODEL_REF = ModelReference(
    model_id=mat.LINEAR_TCR_MODEL.model_id, version=mat.LINEAR_TCR_MODEL.version
)

RESISTANCE = mat.RESISTANCE_METRIC
OHM = mat.RESISTANCE_UNIT
KELVIN = mat.TEMPERATURE_UNIT
PER_KELVIN = mat.TCR_UNIT

#: The closed form this adapter admits predictions on the strength of. Recorded
#: in every admitted prediction so a reader of the audit trail sees the claim
#: rather than having to find the solver.
ANALYTIC_BASIS = "R(T) = R_ref * (1 + alpha_TCR * (T - T_ref)); closed form, no discretization"


@dataclass(frozen=True)
class TcrTruth:
    """Known parameters for a synthetic study. NEVER given to a calibration.

    Held in its own type rather than as loose floats so that handing it
    somewhere it does not belong is visible in a signature.
    """

    reference_resistance: Quantity
    temperature_coefficient: Quantity
    reference_temperature: Quantity

    def __post_init__(self) -> None:
        for label, unit in (
            ("reference_resistance", OHM),
            ("temperature_coefficient", PER_KELVIN),
            ("reference_temperature", KELVIN),
        ):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise TypeError(f"{label} must be a Quantity")
            value.require_compatible(Quantity(0.0, unit), context=f"truth {label}")

    @property
    def vector(self) -> tuple[float, float]:
        """(R_ref in ohm, alpha in 1/kelvin), in the declared column order."""
        return (
            self.reference_resistance.magnitude_in(OHM),
            self.temperature_coefficient.magnitude_in(PER_KELVIN),
        )

    def conductor(self, component_id: str = "R1") -> mat.TemperatureDependentConductor:
        return mat.TemperatureDependentConductor(
            component_id=component_id,
            reference_resistance=self.reference_resistance,
            temperature_coefficient=self.temperature_coefficient,
            reference_temperature=self.reference_temperature,
        )


def build_tcr_parameter_set(
    *,
    resistance_bounds: tuple[float, float] = (0.0, 10.0),
    alpha_bounds: tuple[float, float] = (-0.02, 0.02),
) -> CalibrationParameterSet:
    """The two estimated parameters, in the column order everything downstream uses.

    Bounds are physical rather than a prior: a resistance is non-negative, and
    a temperature coefficient of a metallic conductor lies well inside
    +/-0.02 /K. Widening them to make a fit converge would be changing what the
    quantity is allowed to be, which is why the range lives on the identity and
    is checked when an estimate is recorded.
    """
    return CalibrationParameterSet((
        ParameterIdentity(
            name=mat.REFERENCE_RESISTANCE,
            unit=OHM,
            model=TCR_MODEL_REF,
            bounds=ParameterBounds(
                Quantity(resistance_bounds[0], OHM), Quantity(resistance_bounds[1], OHM)
            ),
        ),
        ParameterIdentity(
            name=mat.TEMPERATURE_COEFFICIENT,
            unit=PER_KELVIN,
            model=TCR_MODEL_REF,
            bounds=ParameterBounds(
                Quantity(alpha_bounds[0], PER_KELVIN), Quantity(alpha_bounds[1], PER_KELVIN)
            ),
        ),
    ))


def tcr_prediction(
    *,
    reference_resistance: Quantity,
    temperature_coefficient: Quantity,
    reference_temperature: Quantity,
    temperature: Quantity,
    condition_id: str,
    component_id: str = "R1",
) -> AdmissibleAnalyticPrediction:
    """One forward evaluation, through the production solver, admitted analytically.

    The whole path is here on purpose: prepare, solve, extract, validate, and a
    real :class:`ScientificResult` carrying provenance. Nothing shortcuts to a
    number. If the solver's validation ever stopped attaining
    ``DIMENSIONALLY_VALID``, the admission would fail rather than this function
    quietly producing an unbacked value.
    """
    conductor = mat.TemperatureDependentConductor(
        component_id=component_id,
        reference_resistance=reference_resistance,
        temperature_coefficient=temperature_coefficient,
        reference_temperature=reference_temperature,
    )
    problem = mat.build_resistance_problem(conductor)
    solver = mat.ResistancePropertySolver()
    solver.bind_conductor(conductor, problem.problem_id, temperature=temperature)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    report = solver.validate(prepared, raw)

    run_id = (
        "tcr-"
        + hashlib.sha256(
            f"{component_id}|{reference_resistance.magnitude_in(OHM)!r}|"
            f"{temperature_coefficient.magnitude_in(PER_KELVIN)!r}|"
            f"{reference_temperature.magnitude_in(KELVIN)!r}|"
            f"{temperature.magnitude_in(KELVIN)!r}".encode("utf-8")
        ).hexdigest()[:16]
    )
    provenance = ProvenanceRecord(
        run_id=run_id,
        models=((TCR_MODEL_REF.model_id, TCR_MODEL_REF.version),),
        solvers=((mat.SOLVER_ID, mat.SOLVER_VERSION),),
        inputs={
            mat.REFERENCE_RESISTANCE: reference_resistance,
            mat.TEMPERATURE_COEFFICIENT: temperature_coefficient,
            mat.REFERENCE_TEMPERATURE: reference_temperature,
            mat.TEMPERATURE: temperature,
        },
        metadata={"condition_id": condition_id, "analytic_basis": ANALYTIC_BASIS},
    )
    result = ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        provenance=provenance,
        models=((TCR_MODEL_REF.model_id, TCR_MODEL_REF.version),),
        solver=solver.identity,
        convergence=raw.convergence,
        validation=report,
        validity_not_assessed={
            TCR_MODEL_REF.model_id: (
                "not assessed by this forward evaluation: the calibration "
                "sweeps parameter candidates, and a validity verdict about a "
                "candidate conductor is a statement about a declaration the "
                "study is still choosing. Applicability is assessed once, "
                "against the calibrated result, where it means something"
            )
        },
    )
    return AdmissibleAnalyticPrediction(
        prediction_id=run_id,
        domain="electrical.material",
        adapter_id="studies.tcr",
        binding_ref=f"{TCR_MODEL_REF.model_id}@{TCR_MODEL_REF.version}",
        source_result=result,
        observable_names=(RESISTANCE,),
        validation=report,
        analytic_basis=ANALYTIC_BASIS,
        verification_ref=f"solver:{mat.SOLVER_ID}@{mat.SOLVER_VERSION}",
        metadata={"condition_id": condition_id},
    )


def synthesize_tcr_observations(
    truth: TcrTruth,
    temperatures_k: Sequence[float],
    *,
    sigma: Quantity,
    dataset_id: str,
    seed: int,
    curvature_per_k2: float = 0.0,
) -> ObservationSet:
    """Observations from the production forward model, plus declared noise.

    ``curvature_per_k2`` is the misspecification handle and defaults to zero,
    which is the well-specified case. When non-zero the truth carries a
    quadratic term the fitted linear law cannot represent::

        R(T) = R_ref (1 + alpha dT + curvature dT^2)

    That is this model's OWN declared limitation -- it ships
    ``LINEARIZATION_BAND`` and ``LINEARIZATION_EXCURSION_RATIO`` and knows it is
    a truncation -- rather than an invented strawman.

    Seeded explicitly. The same seed and inputs give the same observations;
    a different seed gives a different draw from the same distribution.
    """
    if not isinstance(sigma, Quantity):
        raise TypeError("sigma must be a Quantity")
    sigma.require_compatible(Quantity(0.0, OHM), context="observation sigma")
    if sigma.magnitude_in(OHM) <= 0.0:
        raise ValueError("observation sigma must be strictly positive")

    rng = np.random.default_rng(seed)
    t_ref = truth.reference_temperature.magnitude_in(KELVIN)
    r_ref = truth.reference_resistance.magnitude_in(OHM)

    observations: list[GaussianObservation] = []
    for index, temperature_k in enumerate(temperatures_k):
        prediction = tcr_prediction(
            reference_resistance=truth.reference_resistance,
            temperature_coefficient=truth.temperature_coefficient,
            reference_temperature=truth.reference_temperature,
            temperature=Quantity(float(temperature_k), KELVIN),
            condition_id=f"T{index}",
        )
        clean = prediction.value(RESISTANCE).magnitude_in(OHM)
        if curvature_per_k2:
            delta = float(temperature_k) - t_ref
            clean += r_ref * curvature_per_k2 * delta * delta
        noisy = clean + float(rng.normal(0.0, sigma.magnitude_in(OHM)))
        observations.append(
            GaussianObservation(
                condition_id=f"T{index}",
                observable_name=RESISTANCE,
                value=Quantity(noisy, OHM),
                sigma=sigma,
                source_ref=f"synthetic:{dataset_id}:seed={seed}",
            )
        )
    return ObservationSet(observations=tuple(observations), dataset_id=dataset_id)


def tcr_forward_table(
    observations: ObservationSet,
    grid_points: Sequence[Sequence[float]],
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    counter: dict[str, int] | None = None,
):
    """An :class:`AdmittedForwardTable` over a parameter grid, row by admitted row.

    Each row is built by :class:`AdmittedForwardRow`'s constructor from real
    admitted predictions, so every value in the table crossed the admission
    boundary. The table is what the posterior, and therefore the parameter
    uncertainty and the identifiability assessment, are computed from.
    """
    from ..inference.grid import AdmittedForwardRow, AdmittedForwardTable

    rows = []
    for point in grid_points:
        if counter is not None:
            counter["n"] = counter.get("n", 0) + 1
        r_ref, alpha = float(point[0]), float(point[1])
        predictions = {}
        for observation in observations.observations:
            predictions[observation.condition_id] = tcr_prediction(
                reference_resistance=Quantity(r_ref, OHM),
                temperature_coefficient=Quantity(alpha, PER_KELVIN),
                reference_temperature=reference_temperature,
                temperature=temperatures_by_condition[observation.condition_id],
                condition_id=observation.condition_id,
            )
        rows.append(AdmittedForwardRow((r_ref, alpha), observations, predictions))
    return AdmittedForwardTable.from_rows(
        parameter_names=(mat.REFERENCE_RESISTANCE, mat.TEMPERATURE_COEFFICIENT),
        observations=observations,
        rows=rows,
    )


def ols_reference_estimate(
    observations: ObservationSet,
    temperatures_by_condition: Mapping[str, Quantity],
    reference_temperature: Quantity,
) -> dict[str, float]:
    """Closed-form OLS for (R_ref, alpha), derived independently of the optimizer.

    The model is linear in ``(a, b) = (R_ref, R_ref*alpha)`` against
    ``dT = T - T_ref``::

        R = a + b*dT

    so the estimate and its standard errors are textbook and computed here from
    the raw observation values with no reference to the calibration engine.
    This is the Phase 26 oracle: it can disagree with the optimizer, which is
    the only reason it is worth computing.

    Standard errors use the DECLARED sigma rather than the residual scatter, so
    the tolerance a recovery test is graded against comes from the noise that
    was injected rather than from the fit's own success.
    """
    t_ref = reference_temperature.magnitude_in(KELVIN)
    delta = np.asarray(
        [
            temperatures_by_condition[o.condition_id].magnitude_in(KELVIN) - t_ref
            for o in observations.observations
        ],
        dtype=np.float64,
    )
    y = np.asarray(
        [o.value.magnitude_in(OHM) for o in observations.observations],
        dtype=np.float64,
    )
    sigma = float(observations.observations[0].sigma.magnitude_in(OHM))
    n = delta.size
    mean_d = float(delta.mean())
    sxx = float(((delta - mean_d) ** 2).sum())
    if sxx <= 0.0:
        raise ValueError(
            "every observation is at the same temperature, so the slope is not "
            "estimable and there is no closed-form reference"
        )
    b = float(((delta - mean_d) * (y - y.mean())).sum() / sxx)
    a = float(y.mean() - b * mean_d)
    se_a = sigma * math_sqrt(1.0 / n + mean_d * mean_d / sxx)
    se_b = sigma / math_sqrt(sxx)
    # alpha = b/a. Delta method, including the a-b covariance term
    # cov(a,b) = -sigma^2 * mean_d / sxx, which is NOT negligible when the
    # temperature span does not straddle T_ref.
    cov_ab = -(sigma * sigma) * mean_d / sxx
    alpha = b / a
    var_alpha = (
        (1.0 / a) ** 2 * se_b**2
        + (b / (a * a)) ** 2 * se_a**2
        - 2.0 * (b / (a**3)) * cov_ab
    )
    return {
        "reference_resistance": a,
        "temperature_coefficient": alpha,
        "se_reference_resistance": se_a,
        "se_temperature_coefficient": math_sqrt(max(var_alpha, 0.0)),
        "slope_b": b,
        "se_slope_b": se_b,
    }


def math_sqrt(value: float) -> float:
    import math

    return math.sqrt(value)


def tcr_forward_evaluator(
    observations: ObservationSet,
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    counter: dict[str, int] | None = None,
):
    """A forward evaluator for :func:`engcore.inference.calibration.calibrate`.

    Closes over the FIXED reference temperature and the measurement conditions,
    never over the truth: what it is handed each call is the candidate
    ``(R_ref, alpha)`` vector and nothing else.
    """

    def evaluate(vector: Sequence[float]):
        if counter is not None:
            counter["n"] = counter.get("n", 0) + 1
        r_ref, alpha = float(vector[0]), float(vector[1])
        out: list[Quantity] = []
        for observation in observations.observations:
            temperature = temperatures_by_condition[observation.condition_id]
            prediction = tcr_prediction(
                reference_resistance=Quantity(r_ref, OHM),
                temperature_coefficient=Quantity(alpha, PER_KELVIN),
                reference_temperature=reference_temperature,
                temperature=temperature,
                condition_id=observation.condition_id,
            )
            out.append(prediction.value(RESISTANCE))
        return out

    return evaluate
