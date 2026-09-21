"""SALib for sensitivity analysis. Sensitivity is evidence; it is not validation.

Morris, Sobol and FAST are implemented by SALib and are not reimplemented here.
The division of labour is exact:

===========================  ==================================================
SALib                        the design (sampling) and the estimator (analysis)
Forge                        which parameters, over what ranges, against which
                             QoI, evaluated by which model, and what the answer
                             is allowed to be used for
===========================  ==================================================

The evaluator is supplied by the caller and is *not* SALib's concern: SALib
produces a sample matrix, Forge evaluates it with whatever model the study is
about -- native or external -- and hands the outputs back for analysis. That is
why this module can rank the sensitivity of a PyBaMM QoI without importing
PyBaMM, and why a sensitivity study of a native Forge model uses exactly the
same path.

WHAT A SENSITIVITY RESULT MAY NEVER BECOME
-------------------------------------------
Validation evidence. :attr:`SensitivityEvidence.is_validation_evidence` is a
property that returns ``False`` and takes no argument, so there is no value a
caller can pass to make it true.

The reason is not conservatism, it is what the two things mean. A sensitivity
index says *the output moves when this input moves*. Validation says *the
output agrees with a measurement of the world*. A model can be exquisitely
sensitive to a parameter and wrong about everything; ``CLAUDE.md`` states the
general form of this -- "sensitivity is not causality" -- and this module is
the battery-shaped instance of it.

What sensitivity is legitimately for, and what this sprint uses it for, is
deciding **which parameters are worth fitting**. Fitting six parameters where
two carry the response is how a fit acquires free parameters that absorb
residuals, which is exactly what the Sprint 3 recovery rejected a second RC
branch for.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

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

PROVIDER_NAME = "salib"
ADAPTER_VERSION = "engcore.providers.salib_provider/0.1.0"

#: Methods this adapter offers, and the SALib sampler/analyzer pair each uses.
#: An allowlist, so a method name arriving from caller input cannot select an
#: arbitrary SALib entry point.
METHODS = {
    "morris": ("SALib.sample.morris", "SALib.analyze.morris"),
    "sobol": ("SALib.sample.sobol", "SALib.analyze.sobol"),
    "fast": ("SALib.sample.fast_sampler", "SALib.analyze.fast"),
}

#: The index each method's ranking is read from, and what it means.
PRIMARY_INDEX = {
    "morris": ("mu_star", "mean absolute elementary effect"),
    "sobol": ("S1", "first-order variance contribution"),
    "fast": ("S1", "first-order variance contribution"),
}


@dataclass(frozen=True)
class SensitivityParameter:
    """One parameter and the range it is varied over. The range is a decision."""

    name: str
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("a sensitivity parameter requires a name")
        low, high = float(self.lower), float(self.upper)
        if not (math.isfinite(low) and math.isfinite(high)) or low >= high:
            raise ValueError(f"{self.name}: range must be finite and increasing")
        object.__setattr__(self, "lower", low)
        object.__setattr__(self, "upper", high)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "lower": self.lower, "upper": self.upper}


@dataclass(frozen=True)
class SensitivityEvidence:
    """A ranking of parameters against one QoI, by one method, on one scenario.

    Every field a reviewer needs to ask "sensitive to what, measured how, over
    what range, and on which cell" is present, because a sensitivity index
    without its scenario is not interpretable: the same parameter can dominate
    at 4 degC and vanish at 25 degC.
    """

    method: str
    qoi: str
    scenario_id: str
    provider_version: str
    parameters: tuple[dict[str, Any], ...]
    indices: Mapping[str, Mapping[str, float]]
    ranking: tuple[str, ...]
    primary_index: str
    sample_count: int
    failed_evaluations: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_validation_evidence(self) -> bool:
        """Permanently ``False``. See this module's docstring.

        A property with no parameter and a constant return, rather than a
        field, so that no constructor argument, payload key or subclass can
        set it. A sensitivity index is not a comparison against the world.
        """
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "qoi": self.qoi,
            "scenario_id": self.scenario_id,
            "provider": PROVIDER_NAME,
            "provider_version": self.provider_version,
            "parameters": [dict(p) for p in self.parameters],
            "indices": {k: dict(v) for k, v in self.indices.items()},
            "ranking": list(self.ranking),
            "primary_index": self.primary_index,
            "primary_index_meaning": PRIMARY_INDEX[self.method][1],
            "sample_count": self.sample_count,
            "failed_evaluations": self.failed_evaluations,
            "diagnostics": dict(self.diagnostics),
            "is_validation_evidence": False,
            "what_this_is_not": (
                "a sensitivity index states that the output moves when the "
                "input moves. It states nothing about agreement with a "
                "measurement, and it can never contribute to a validation level"
            ),
        }


class SALibProvider:
    """Designs a sensitivity experiment, has Forge evaluate it, analyses it.

    ``evaluator`` maps one parameter vector to one scalar QoI value, or to
    ``None`` when that point could not be evaluated. ``None`` matters: a
    refused or failed evaluation is not a zero. Sobol and FAST estimators
    cannot accept a hole, so a run with any failed evaluation is reported as
    ``MISSING_EVIDENCE`` rather than being repaired with a substitute value.
    """

    def __init__(
        self,
        *,
        method: str,
        parameters: Sequence[SensitivityParameter],
        qoi: str,
        scenario_id: str,
        evaluator: Callable[[Mapping[str, float]], float | None],
        samples: int = 64,
        seed: int = 20260921,
    ) -> None:
        if not parameters:
            raise ValueError("a sensitivity study needs at least one parameter")
        self._method = str(method)
        self._parameters = tuple(parameters)
        self._qoi = str(qoi)
        self._scenario_id = str(scenario_id)
        self._evaluator = evaluator
        self._samples = int(samples)
        self._seed = int(seed)
        self._environment = EnvironmentIdentity.capture()

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    def available(self) -> bool:
        try:
            # Both, deliberately. The top package importing proves nothing
            # about whether a sampler is reachable, and a study that failed
            # at `sample()` would have passed an availability probe.
            import SALib  # noqa: F401
            from SALib.sample import morris  # noqa: F401
        except Exception:
            return False
        return True

    def capabilities(self) -> frozenset[ProviderCapability]:
        return frozenset({ProviderCapability.SENSITIVITY_ANALYSIS})

    def execute(self, request: ProviderRequest) -> ProviderResult:
        digest = request.digest()
        if request.capability not in self.capabilities():
            return self._refused(
                digest,
                f"this provider offers sensitivity analysis and was asked for "
                f"{request.capability.value}",
            )
        if self._method not in METHODS:
            return self._refused(
                digest,
                f"method {self._method!r} is not one of {sorted(METHODS)}",
            )
        if not self.available():
            return unavailable_result(
                request,
                "SALib is not importable in this interpreter; install the "
                "forge[sensitivity] extra",
            )
        return self._analyse(request, digest)

    def _refused(self, digest: str, detail: str) -> ProviderResult:
        return ProviderResult(
            receipt=ProviderExecutionReceipt(
                identity=None,
                request_digest=digest,
                outcome=ExecutionOutcome.FORGE_REFUSED,
                detail=detail,
            )
        )

    def _identity(self, version: str) -> ProviderIdentity:
        return ProviderIdentity(
            provider_name=PROVIDER_NAME,
            provider_version=version,
            model_identity=f"{self._method}:{self._qoi}",
            solver_identity=METHODS[self._method][1],
            configuration_digest=digest_of(
                {
                    "method": self._method,
                    "qoi": self._qoi,
                    "scenario_id": self._scenario_id,
                    "samples": self._samples,
                    "seed": self._seed,
                    "parameters": [p.to_dict() for p in self._parameters],
                }
            ),
            environment_identity=self._environment.digest(),
            adapter_version=ADAPTER_VERSION,
        )

    def _problem(self) -> dict[str, Any]:
        return {
            "num_vars": len(self._parameters),
            "names": [p.name for p in self._parameters],
            "bounds": [[p.lower, p.upper] for p in self._parameters],
        }

    def _analyse(self, request: ProviderRequest, digest: str) -> ProviderResult:
        import importlib
        import importlib.metadata as md

        import numpy as np

        version = md.version("salib")
        identity = self._identity(version)
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        clock = time.perf_counter()
        problem = self._problem()
        sampler_name, analyzer_name = METHODS[self._method]
        try:
            sampler = importlib.import_module(sampler_name)
            analyzer = importlib.import_module(analyzer_name)
            design = sampler.sample(problem, self._samples, seed=self._seed)
        except Exception as exc:
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=identity,
                    request_digest=digest,
                    outcome=ExecutionOutcome.PROVIDER_ERROR,
                    detail=f"sampling failed: {type(exc).__name__}: {exc}",
                    wall_seconds=time.perf_counter() - clock,
                    started_at=started,
                )
            )

        names = problem["names"]
        outputs: list[float] = []
        failed = 0
        for row in np.atleast_2d(design):
            point = {name: float(value) for name, value in zip(names, row)}
            try:
                value = self._evaluator(point)
            except Exception:
                value = None
            if value is None or not math.isfinite(float(value)):
                failed += 1
                outputs.append(math.nan)
            else:
                outputs.append(float(value))

        if failed:
            # Not repaired. A hole filled with a mean or a bound would make the
            # estimator report a variance decomposition of a fabricated sample.
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=identity,
                    request_digest=digest,
                    outcome=ExecutionOutcome.MISSING_EVIDENCE,
                    detail=(
                        f"{failed} of {len(outputs)} design points could not be "
                        f"evaluated. The estimator needs every point; a "
                        f"substituted value would decompose a variance that "
                        f"was never measured"
                    ),
                    wall_seconds=time.perf_counter() - clock,
                    started_at=started,
                )
            )

        try:
            array = np.asarray(outputs, dtype=float)
            if self._method == "morris":
                analysis = analyzer.analyze(
                    problem, design, array, seed=self._seed, print_to_console=False
                )
            else:
                analysis = analyzer.analyze(
                    problem, array, seed=self._seed, print_to_console=False
                )
        except Exception as exc:
            return ProviderResult(
                receipt=ProviderExecutionReceipt(
                    identity=identity,
                    request_digest=digest,
                    outcome=ExecutionOutcome.PROVIDER_ERROR,
                    detail=f"analysis failed: {type(exc).__name__}: {exc}",
                    wall_seconds=time.perf_counter() - clock,
                    started_at=started,
                )
            )
        elapsed = time.perf_counter() - clock

        primary = PRIMARY_INDEX[self._method][0]
        indices: dict[str, dict[str, float]] = {name: {} for name in names}
        for key, values in dict(analysis).items():
            if key == "names":
                continue
            values = np.atleast_1d(np.asarray(values, dtype=float))
            if values.shape[0] != len(names):
                continue
            for name, value in zip(names, values):
                indices[name][str(key)] = float(value)
        ranking = tuple(
            sorted(
                names,
                key=lambda n: -abs(indices[n].get(primary, float("nan")))
                if math.isfinite(indices[n].get(primary, float("nan")))
                else float("inf"),
            )
        )
        evidence = SensitivityEvidence(
            method=self._method,
            qoi=self._qoi,
            scenario_id=self._scenario_id,
            provider_version=version,
            parameters=tuple(p.to_dict() for p in self._parameters),
            indices=indices,
            ranking=ranking,
            primary_index=primary,
            sample_count=int(np.atleast_2d(design).shape[0]),
            failed_evaluations=0,
            diagnostics={"seed": self._seed, "wall_seconds": elapsed},
        )
        return ProviderResult(
            receipt=ProviderExecutionReceipt(
                identity=identity,
                request_digest=digest,
                outcome=ExecutionOutcome.OK,
                detail=f"{evidence.sample_count} design points, {self._method}",
                wall_seconds=elapsed,
                started_at=started,
            ),
            evidence=evidence.to_dict(),
        )


def build_sensitivity_request(
    *,
    method: str,
    parameters: Sequence[SensitivityParameter],
    qoi: str,
    scenario_id: str,
    samples: int,
) -> ProviderRequest:
    return ProviderRequest(
        capability=ProviderCapability.SENSITIVITY_ANALYSIS,
        model_key=f"salib.{method}",
        parameter_authority=digest_of(
            {"scenario": scenario_id, "parameters": [p.to_dict() for p in parameters]}
        ),
        qois=(qoi,),
        inputs={
            "scenario_id": scenario_id,
            "parameters": [p.to_dict() for p in parameters],
            "samples": samples,
        },
    )


__all__ = [
    "ADAPTER_VERSION",
    "METHODS",
    "PRIMARY_INDEX",
    "PROVIDER_NAME",
    "SALibProvider",
    "SensitivityEvidence",
    "SensitivityParameter",
    "build_sensitivity_request",
]
