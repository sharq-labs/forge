"""PyBOP as the fitting provider. Forge does not own an optimiser.

PyBOP parameterises PyBaMM models against measured data, with both frequentist
and Bayesian machinery. Forge has no optimisation stack to expand and does not
build one here: no line search, no population method, no sampler. What Forge
owns is the part that decides whether a fit may be believed --

* **which data the fit was allowed to see** (:class:`FitDataset`);
* which parameters were free, inside what bounds, under what priors;
* which optimiser and which objective, by identity;
* what came back, and what did not come back.

THE RULE THIS MODULE EXISTS TO ENFORCE
---------------------------------------
*Calibration data only. Never validation. Never holdout.*

It is enforced by a type, not by a comment. A :class:`FitDataset` carries a
:class:`DatasetRole`, the role is required, and :meth:`PyBOPProvider.execute`
refuses every role except ``CALIBRATION`` before PyBOP is imported. There is no
flag that relaxes it and no keyword that overrides it, because the failure this
prevents is not a mistake somebody makes once: fitting on validation data
produces a model that scores beautifully and has been told the answers, and the
score looks exactly like a good model.

``UNSPECIFIED`` is a role, and it is refused too. A dataset that does not say
what it is has not been screened, and "not screened" is not "calibration".

What a fit is, and is not
-------------------------
A fit is **evidence about parameters**, not a scientific answer, so it comes
back as :attr:`ProviderResult.evidence` and never as a ``ScientificResult``.
Nothing downstream can mistake it for a prediction, and a fitted parameter set
becomes usable only by being promoted into a
:class:`~engcore.providers.pybamm_provider.ParameterAuthority` -- which mints a
new digest, which changes the provider identity of every run that uses it.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .contract import (
    ExecutionOutcome,
    ProviderCapability,
    ProviderExecutionReceipt,
    ProviderIdentity,
    ProviderRequest,
    ProviderResult,
    digest_of,
    unavailable_result,
)
from .environment import EnvironmentIdentity

PROVIDER_NAME = "pybop"
ADAPTER_VERSION = "engcore.providers.pybop_provider/0.1.0"


class DatasetRole(str, Enum):
    """What a dataset is for. Required, and only one of these may be fitted on."""

    CALIBRATION = "calibration"
    VALIDATION = "validation"
    HOLDOUT = "holdout"
    #: Read once and therefore no longer independent. Kept distinct from
    #: HOLDOUT so a corpus cannot quietly recover independence it has spent.
    OBSERVED_HOLDOUT = "observed_holdout"
    #: Nobody said. Refused, because unscreened is not calibration.
    UNSPECIFIED = "unspecified"

    @property
    def may_be_fitted(self) -> bool:
        return self is DatasetRole.CALIBRATION


@dataclass(frozen=True)
class FitDataset:
    """Measured channels offered to a fit, with the role that governs them.

    ``digest`` is computed over the channels themselves, so two fits that claim
    the same dataset can be shown to have used the same numbers. Declaring a
    role a dataset does not have changes the digest as well, which makes a
    relabelled dataset visible rather than merely wrong.
    """

    dataset_id: str
    role: DatasetRole
    time_s: tuple[float, ...]
    current_a: tuple[float, ...]
    terminal_voltage_v: tuple[float, ...]
    provenance: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.role, DatasetRole):
            raise ValueError("a fit dataset requires a DatasetRole")
        if not str(self.dataset_id).strip():
            raise ValueError("a fit dataset requires a dataset_id")
        lengths = {
            len(self.time_s),
            len(self.current_a),
            len(self.terminal_voltage_v),
        }
        if len(lengths) != 1 or lengths == {0}:
            raise ValueError(
                "a fit dataset needs time, current and voltage channels of "
                "equal, non-zero length"
            )
        for label in ("time_s", "current_a", "terminal_voltage_v"):
            values = tuple(float(v) for v in getattr(self, label))
            if not all(math.isfinite(v) for v in values):
                raise ValueError(f"{label} carries a non-finite sample")
            object.__setattr__(self, label, values)

    @property
    def sample_count(self) -> int:
        return len(self.time_s)

    def digest(self) -> str:
        return digest_of(
            {
                "dataset_id": self.dataset_id,
                "role": self.role.value,
                "time_s": list(self.time_s),
                "current_a": list(self.current_a),
                "terminal_voltage_v": list(self.terminal_voltage_v),
            }
        )


@dataclass(frozen=True)
class FitParameter:
    """One free parameter: its name in the provider's vocabulary, and its prior.

    ``prior`` is optional and, when absent, absent. A fit run without a prior
    has not implicitly been given a uniform one over the bounds; it has been
    run without a prior, and the record says so rather than filling in a
    convention the caller did not choose.
    """

    name: str
    lower: float
    upper: float
    initial: float
    prior: str | None = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("a fit parameter requires a name")
        low, high, start = float(self.lower), float(self.upper), float(self.initial)
        if not (math.isfinite(low) and math.isfinite(high)) or low >= high:
            raise ValueError(f"{self.name}: bounds must be finite and increasing")
        if not (low <= start <= high):
            raise ValueError(f"{self.name}: initial value is outside its own bounds")
        object.__setattr__(self, "lower", low)
        object.__setattr__(self, "upper", high)
        object.__setattr__(self, "initial", start)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lower": self.lower,
            "upper": self.upper,
            "initial": self.initial,
            "prior": self.prior,
        }


#: Optimisers this adapter will construct, by Forge-facing name. An allowlist
#: for the reason the model catalogue is one: an optimiser chosen by string
#: from caller input is a caller choosing code to run.
OPTIMISERS = {
    "scipy_minimize": "SciPyMinimize",
    "scipy_differential_evolution": "SciPyDifferentialEvolution",
    "cmaes": "CMAES",
    "xnes": "XNES",
}

#: Objectives, same rule.
OBJECTIVES = {
    "rmse": "RootMeanSquaredError",
    "sse": "SumSquaredError",
    "mae": "MeanAbsoluteError",
}


@dataclass(frozen=True)
class FitEvidence:
    """What a fit produced. Evidence about parameters, never a prediction."""

    dataset_id: str
    dataset_digest: str
    dataset_role: str
    parameters: tuple[dict[str, Any], ...]
    optimiser: str
    objective: str
    best_values: Mapping[str, float]
    final_cost: float | None
    #: Parameter uncertainty, when the chosen machinery produces one. ``None``
    #: means none was produced -- never zero, and never a default interval.
    parameter_uncertainty: Mapping[str, Any] | None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_digest": self.dataset_digest,
            "dataset_role": self.dataset_role,
            "parameters": [dict(p) for p in self.parameters],
            "optimiser": self.optimiser,
            "objective": self.objective,
            "best_values": dict(self.best_values),
            "final_cost": self.final_cost,
            "parameter_uncertainty": (
                None
                if self.parameter_uncertainty is None
                else dict(self.parameter_uncertainty)
            ),
            "diagnostics": dict(self.diagnostics),
            "is_validation_evidence": False,
        }


class PyBOPProvider:
    """Fits declared parameters of a PyBaMM model to declared calibration data.

    ``model_factory`` and ``parameter_values_factory`` are supplied by the
    caller, because *which* model and *whose* parameters are Forge decisions
    that a fitting library must not make.
    """

    def __init__(
        self,
        *,
        dataset: FitDataset,
        parameters: Sequence[FitParameter],
        model_factory,
        parameter_values_factory,
        optimiser: str = "scipy_minimize",
        objective: str = "rmse",
        max_iterations: int | None = None,
    ) -> None:
        if not parameters:
            raise ValueError("a fit with no free parameters is not a fit")
        self._dataset = dataset
        self._parameters = tuple(parameters)
        self._model_factory = model_factory
        self._values_factory = parameter_values_factory
        self._optimiser = str(optimiser)
        self._objective = str(objective)
        self._max_iterations = max_iterations
        self._environment = EnvironmentIdentity.capture()

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    def available(self) -> bool:
        try:
            import pybop  # noqa: F401
        except Exception:
            return False
        return True

    def capabilities(self) -> frozenset[ProviderCapability]:
        return frozenset({ProviderCapability.PARAMETER_INFERENCE})

    def execute(self, request: ProviderRequest) -> ProviderResult:
        digest = request.digest()
        if request.capability not in self.capabilities():
            return self._refused(
                digest,
                f"this provider offers parameter inference and was asked for "
                f"{request.capability.value}",
            )

        # The rule, before anything else and before PyBOP is imported.
        if not self._dataset.role.may_be_fitted:
            return self._refused(
                digest,
                f"dataset {self._dataset.dataset_id!r} carries the role "
                f"{self._dataset.role.value!r}. Fitting is permitted on "
                f"calibration data only: a parameter fitted against validation "
                f"or holdout samples has been told the answer, and the score it "
                f"then earns on those samples is not evidence",
            )
        if self._optimiser not in OPTIMISERS:
            return self._refused(
                digest, f"optimiser {self._optimiser!r} is not on the allowlist"
            )
        if self._objective not in OBJECTIVES:
            return self._refused(
                digest, f"objective {self._objective!r} is not on the allowlist"
            )
        if not self.available():
            return unavailable_result(
                request,
                "pybop is not importable in this interpreter; install the "
                "forge[battery-fit] extra",
            )
        return self._fit(request, digest)

    def _refused(self, digest: str, detail: str) -> ProviderResult:
        return ProviderResult(
            receipt=ProviderExecutionReceipt(
                identity=None,
                request_digest=digest,
                outcome=ExecutionOutcome.FORGE_REFUSED,
                detail=detail,
            )
        )

    def _identity(self) -> ProviderIdentity:
        import pybop

        return ProviderIdentity(
            provider_name=PROVIDER_NAME,
            provider_version=pybop.__version__,
            model_identity=f"fit:{self._dataset.dataset_id}",
            solver_identity=OPTIMISERS[self._optimiser],
            configuration_digest=digest_of(
                {
                    "optimiser": self._optimiser,
                    "objective": self._objective,
                    "max_iterations": self._max_iterations,
                    "parameters": [p.to_dict() for p in self._parameters],
                    "dataset_digest": self._dataset.digest(),
                }
            ),
            environment_identity=self._environment.digest(),
            adapter_version=ADAPTER_VERSION,
        )

    def _fit(self, request: ProviderRequest, digest: str) -> ProviderResult:
        import numpy as np
        import pybop

        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        clock = time.perf_counter()
        identity = self._identity()
        try:
            dataset = pybop.Dataset(
                {
                    "Time [s]": np.asarray(self._dataset.time_s, dtype=float),
                    "Current [A]": np.asarray(self._dataset.current_a, dtype=float),
                    "Voltage [V]": np.asarray(
                        self._dataset.terminal_voltage_v, dtype=float
                    ),
                }
            )
            values = self._values_factory()
            values.update(
                {
                    p.name: pybop.Parameter(
                        bounds=(p.lower, p.upper), initial_value=p.initial
                    )
                    for p in self._parameters
                },
                check_already_exists=False,
            )
            simulator = pybop.pybamm.Simulator(
                self._model_factory(),
                parameter_values=values,
                protocol=dataset,
                output_variables=["Voltage [V]"],
            )
            cost = getattr(pybop, OBJECTIVES[self._objective])(
                dataset, target=["Voltage [V]"]
            )
            optimiser = getattr(pybop, OPTIMISERS[self._optimiser])(
                pybop.Problem(simulator, cost)
            )
            outcome = optimiser.run()
            names = list(simulator.input_parameter_names)
            best = {
                str(name): float(value)
                for name, value in zip(names, np.atleast_1d(outcome.x))
            }
        except Exception as exc:
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=identity,
                    request_digest=digest,
                    outcome=ExecutionOutcome.PROVIDER_ERROR,
                    detail=f"{type(exc).__name__}: {exc}",
                    wall_seconds=time.perf_counter() - clock,
                    started_at=started,
                )
            )
        elapsed = time.perf_counter() - clock

        if not best or any(not math.isfinite(v) for v in best.values()):
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=identity,
                    request_digest=digest,
                    outcome=ExecutionOutcome.NUMERICAL_FAILURE,
                    detail=f"the optimiser returned non-finite or empty values: {best}",
                    wall_seconds=elapsed,
                    started_at=started,
                )
            )

        at_bound = sorted(
            p.name
            for p in self._parameters
            if p.name in best
            and (
                abs(best[p.name] - p.lower) <= 1e-9 * max(abs(p.lower), 1.0)
                or abs(best[p.name] - p.upper) <= 1e-9 * max(abs(p.upper), 1.0)
            )
        )
        evidence = FitEvidence(
            dataset_id=self._dataset.dataset_id,
            dataset_digest=self._dataset.digest(),
            dataset_role=self._dataset.role.value,
            parameters=tuple(p.to_dict() for p in self._parameters),
            optimiser=OPTIMISERS[self._optimiser],
            objective=OBJECTIVES[self._objective],
            best_values=best,
            final_cost=_final_cost(outcome),
            # PyBOP produces a parameter covariance only from the Bayesian
            # samplers, which this sprint does not run. None, not zero: an
            # unquantified uncertainty that became a number would be the
            # exact inversion the Core forbids.
            parameter_uncertainty=None,
            diagnostics={
                "sample_count": self._dataset.sample_count,
                "iterations": getattr(outcome, "n_iterations", None),
                "evaluations": getattr(outcome, "n_evaluations", None),
                "message": str(getattr(outcome, "message", "")),
                "wall_seconds": elapsed,
                # A parameter resting on its own bound is a fit that wanted to
                # go further. Reported, never silently accepted.
                "parameters_at_bound": at_bound,
            },
        )
        return ProviderResult(
            receipt=ProviderExecutionReceipt(
                identity=identity,
                request_digest=digest,
                outcome=ExecutionOutcome.OK,
                detail=f"fitted {len(best)} parameters on {self._dataset.sample_count} samples",
                wall_seconds=elapsed,
                started_at=started,
            ),
            evidence=evidence.to_dict(),
        )


def _final_cost(outcome: Any) -> float | None:
    for attribute in ("final_cost", "fun", "cost"):
        value = getattr(outcome, attribute, None)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return None


def build_fit_request(
    *, dataset: FitDataset, parameters: Sequence[FitParameter], qoi: str
) -> ProviderRequest:
    return ProviderRequest(
        capability=ProviderCapability.PARAMETER_INFERENCE,
        model_key="pybop.fit",
        parameter_authority=dataset.digest(),
        qois=(qoi,),
        inputs={
            "dataset_id": dataset.dataset_id,
            "dataset_role": dataset.role.value,
            "sample_count": dataset.sample_count,
            "parameters": [p.to_dict() for p in parameters],
        },
    )


__all__ = [
    "ADAPTER_VERSION",
    "OBJECTIVES",
    "OPTIMISERS",
    "PROVIDER_NAME",
    "DatasetRole",
    "FitDataset",
    "FitEvidence",
    "FitParameter",
    "PyBOPProvider",
    "build_fit_request",
]
