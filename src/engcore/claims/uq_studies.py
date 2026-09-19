"""Phase 2 -- executing the uncertainty studies a plan names, and reading them back.

A plan's ``uncertainty:<channel>`` step carries the exact study it will run
(:func:`study_spec`), so the plan digest -- and through the charter every piece
of evidence -- binds what was run. This module runs it:

* **refinement** (NUMERICAL): the capability's own executor at every level of
  the declared ladder; level 0 must reproduce the reported value, or the study
  is not about the reported run and the channel stays UNKNOWN;
* **propagation** (EPISTEMIC_PARAMETER): the executor at every seeded draw of
  the claim's declared input distributions.

Every variant run is bound exactly as the main run is (``binding_problems``
under the variant's run id) and is *usable* only if every model stayed in its
validated domain, the solver finished, a coupled loop met its criterion, and no
check failed -- except, for a refinement level, the accuracy checks the study
declares, which judge a coarse level at its own resolution and are expected to
fail there. An unusable run is never dropped: it makes the estimate UNKNOWN.

What cannot be read back
------------------------
A study record carries each run's report digest and value, not the report.
:func:`verify_study_record` re-derives the estimate from those values and
refuses any edit, but it cannot re-derive the values themselves without
executing again; that is what a replay does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..scientific.errors import ScientificCoreError
from ..scientific.models.definition import ValidityStatus
from ..scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ..scientific.units.quantity import Quantity
from ..scientific.results.validation import ValidationOutcome
from ..scientific.solvers.protocol import ConvergenceState
from ..sria.uncertainty import UncertaintyChannel
from ._records import canonical_json, tagged_digest
from .aleatoric_uq import ReplicateObservation, estimate_aleatoric_replicates
from .analysis.model_discrepancy import (
    DiscrepancyProtocol,
    PairedObservation,
    estimate_model_form_discrepancy,
)
from .measurement_dataset import DatasetObservation
from .model_form_uq import evaluate_discrepancy_for_model_form
from .model_form_uncertainty import ModelFormAuthorityError, promote_model_form_interval
from ..uq.model_form import ModelFormPolicy, ModelFormScope
from ..uq.model_form.qualification import ProducerQualification
from .capabilities import CapabilityDeclaration, CapabilityRegistry, build_case, declared_path
from .contract import ScientificClaim
from .errors import CapabilityExecutionRefused, CapabilityInputError, ClaimLayerError
from .numerical_uq import RefinementLevel, estimate_from_dict, estimate_numerical_uncertainty
from .parameter_uq import (
    TOLERANCE_CONFIDENCE,
    TOLERANCE_CONTENT,
    InputUncertainty,
    PropagatedRun,
    draw_samples,
    estimate_parameter_uncertainty,
    parameter_estimate_from_dict,
)

_REPORT_TAG = "crafty.claims.variant_report/1"
_EMPIRICAL_CONTEXT_TAG = "crafty.claims.empirical_context/1"
_MODEL_SCOPE_TAG = "crafty.claims.model_scope/1"
_MODEL_DATASET_TAG = "crafty.claims.model_form_dataset/1"


class UncertaintyStudyError(ClaimLayerError):
    """A study record does not re-derive from what it carries."""


def run_inputs_for(claim: ScientificClaim, declaration: CapabilityDeclaration) -> dict[str, Any]:
    """The stated inputs a run is built from: everything supplied, except a target named only by reference."""
    supplied = dict(claim.supplied_inputs)
    return {p: v for p, v in supplied.items() if p != claim.target.input_ref or declaration.input(p) is not None}


def study_spec(declaration: CapabilityDeclaration, claim: ScientificClaim, channel: UncertaintyChannel) -> tuple[dict[str, Any] | None, str | None]:
    """The exact study that would quantify ``channel`` for this claim, or why none can."""
    qoi = claim.qoi.name
    if channel not in declaration.uncertainty.channels_for(qoi):
        return None, f"{declaration.capability_id} declares no way to quantify {channel.value} for {qoi}"
    if channel is UncertaintyChannel.NUMERICAL:
        study = declaration.refinement
        if study is None or qoi not in study.quantities:  # pragma: no cover - the declaration refuses this
            return None, "no refinement study is declared for this quantity"
        supplied = run_inputs_for(claim, declaration)
        baseline = {}
        for path, default in study.refined_inputs.items():
            stated = supplied.get(path)
            if stated is not None and (isinstance(stated, bool) or not isinstance(stated, int)):
                return None, f"{path} is stated as {stated!r}, not a count"
            baseline[path] = default if stated is None else stated
        ladder = study.ladder(baseline)
        if isinstance(ladder, str):
            return None, ladder
        return {
            "kind": "refinement",
            "ratio": study.ratio,
            "formal_order": study.formal_order,
            "order_tolerance": study.order_tolerance,
            "accuracy_checks": sorted(study.accuracy_checks),
            "ladder": [dict(level) for level in ladder],
        }, None
    if channel is UncertaintyChannel.EPISTEMIC_PARAMETER:
        spec = claim.input_uncertainty
        if spec is None:
            return None, "the claim declares no input distributions to propagate"
        allowed = {p.path for p in declaration.perturbable}
        outside = sorted(d.path for d in spec.distributions if declared_path(d.path) not in allowed)
        if outside:
            return None, f"{declaration.capability_id} does not accept perturbed values at {outside}"
        return {
            "kind": "propagation",
            "input_uncertainty": spec.to_dict(),
            "content": TOLERANCE_CONTENT,
            "confidence": TOLERANCE_CONFIDENCE,
        }, None
    if channel is UncertaintyChannel.ALEATORIC:
        return {
            "kind": "aleatoric_replicates",
            "content": TOLERANCE_CONTENT,
            "confidence": TOLERANCE_CONFIDENCE,
            "admission": (
                "independent same-population, exact-context physical replicates "
                "with calibrated MEASUREMENT intervals"
            ),
        }, None
    if channel is UncertaintyChannel.MODEL_FORM:
        policy = ModelFormPolicy()
        return {
            "kind": "model_form_empirical",
            "discrepancy_protocol": {
                "protocol_id": "claim_model_form_empirical_v1",
                "minimum_calibration_groups": policy.minimum_calibration_groups,
                "minimum_validation_groups": policy.minimum_validation_groups,
                "require_all_holdout_compatible": True,
            },
            "promotion_policy": {
                "minimum_calibration_groups": policy.minimum_calibration_groups,
                "minimum_validation_groups": policy.minimum_validation_groups,
                "minimum_calibration_observations": policy.minimum_calibration_observations,
                "minimum_validation_observations": policy.minimum_validation_observations,
                "minimum_holdout_coverage": policy.minimum_holdout_coverage,
                "coverage_factor": policy.coverage_factor,
                "estimator": policy.estimator.value,
                "empirical_quantile": policy.empirical_quantile,
            },
            "admission": (
                "curated DatasetObservation records with explicit calibration/"
                "validation split plus an independently reviewed producer qualification"
            ),
        }, None
    return None, f"no study in this runtime quantifies {channel.value}"  # pragma: no cover - declaration-gated


# ---------------------------------------------------------------------------
# Running one variant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VariantRun:
    run_id: str
    report: Any
    value: float | None
    usable: bool
    problem: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "report_digest": None if self.report is None else tagged_digest(_REPORT_TAG, self.report.to_dict()),
            "verdict": None if self.report is None else self.report.verdict.value,
            "value": self.value,
            "usable": self.usable,
            "problem": self.problem,
        }


_FINISHED = {ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE}


def _usability(report: Any, tolerated_failures: frozenset[str]) -> str | None:
    for record in report.validity:
        status = ValidityStatus(record.assessment.status)
        if status is not ValidityStatus.IN_DOMAIN:
            return f"model {record.model_id} is {status.value}"
    if report.convergence is not None and ConvergenceState(report.convergence) not in _FINISHED:
        return f"the solver did not finish ({ConvergenceState(report.convergence).value})"
    if report.coupling is not None and report.coupling.criterion.value != "met":
        return "the coupled loop did not meet its criterion"
    failed = sorted(c.name for c in report.validation if ValidationOutcome(c.outcome) is ValidationOutcome.FAIL and c.name not in tolerated_failures)
    if failed:
        return f"check(s) {failed} failed"
    return None


def run_variant(plan: Any, registry: CapabilityRegistry, inputs: Mapping[str, Any], run_id: str, *, tolerated_failures: frozenset[str] = frozenset()) -> VariantRun:
    """Execute the plan's capability on ``inputs`` under ``run_id``; bind and judge the report."""
    from .execution import binding_problems

    declaration = registry.get(plan.capability_id)
    try:
        case = build_case(declaration, dict(inputs))
        run = declaration.executor(case, run_id=run_id)
    except (CapabilityExecutionRefused, CapabilityInputError, ScientificCoreError, ValueError) as exc:
        return VariantRun(run_id, None, None, False, f"refused: {type(exc).__name__}: {exc}")
    chosen = [item for item in run.reports if item.instance == plan.instance]
    if not chosen and len(run.reports) == 1 and run.reports[0].instance is None:
        chosen = list(run.reports)
    if len(chosen) != 1:
        return VariantRun(run_id, None, None, False, f"no single report for instance {plan.instance!r}")
    report = chosen[0].report
    problems = binding_problems(plan, registry, report, {k: v for k, v in inputs.items()}, run_id=run_id)
    qoi = plan.content["qoi"]
    quantity = report.values.get(qoi["name"])
    value = None if quantity is None else float(quantity.to(qoi["units"]).magnitude)
    if value is not None and not math.isfinite(value):
        return VariantRun(run_id, report, None, False, f"the run reported a non-finite {qoi['name']}")
    if problems:
        return VariantRun(run_id, report, value, False, "unbound: " + "; ".join(problems))
    why = _usability(report, tolerated_failures)
    if value is None:
        return VariantRun(run_id, report, None, False, f"the run reported no {qoi['name']}")
    return VariantRun(run_id, report, value, why is None, why)


# ---------------------------------------------------------------------------
# The studies
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StudyOutcome:
    """What the plan's studies produced: one record per studied channel, and the channel records."""

    records: tuple[dict[str, Any], ...]
    channel_records: Mapping[UncertaintyChannel, Uncertainty]

    def to_list(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.records]


def planned_studies(plan: Any) -> list[tuple[UncertaintyChannel, dict[str, Any]]]:
    out = []
    for step in sorted(plan.steps, key=lambda s: s.step_id):
        if step.kind.value == "uncertainty" and step.availability.value == "planned" and step.detail.get("study") is not None:
            out.append((UncertaintyChannel(step.detail["channel"]), dict(step.detail["study"])))
    return out


def _refinement(plan, registry, claim, report, spec) -> tuple[dict[str, Any], Uncertainty]:
    declaration = registry.get(plan.capability_id)
    base = run_inputs_for(claim, declaration)
    qoi = plan.content["qoi"]
    reported = float(report.values[qoi["name"]].to(qoi["units"]).magnitude)
    tolerated = frozenset(spec["accuracy_checks"])
    runs = [run_variant(plan, registry, {**base, **level}, f"{plan.run_id}~numerical~{k}", tolerated_failures=tolerated) for k, level in enumerate(spec["ladder"])]
    levels = tuple(RefinementLevel(k, r.value, dict(spec["ladder"][k]), r.run_id) for k, r in enumerate(runs))
    unusable = [(k, r) for k, r in enumerate(runs) if not r.usable]
    estimate = estimate_numerical_uncertainty(
        levels, quantity=qoi["name"], units=qoi["units"], refinement_ratio=spec["ratio"],
        formal_order=spec["formal_order"], order_tolerance=spec["order_tolerance"],
    )
    problem = None
    if unusable:
        k, r = unusable[0]
        problem = f"refinement level {k} is not usable: {r.problem}"
    elif not math.isclose(runs[0].value, reported, rel_tol=1e-12, abs_tol=0.0):
        problem = f"level 0 ({runs[0].value!r}) does not reproduce the reported value ({reported!r}); the study is not about the reported run"
    record = {
        "channel": UncertaintyChannel.NUMERICAL.value,
        "kind": "refinement",
        "spec": spec,
        "runs": [r.to_dict() for r in runs],
        "estimate": estimate.to_dict(),
        "problem": problem,
    }
    uncertainty = estimate.to_uncertainty() if problem is None else Uncertainty.unknown(f"numerical uncertainty not quantified: {problem}")
    record["uncertainty"] = uncertainty.to_dict()
    return record, uncertainty


def _propagation(plan, registry, claim, report, spec) -> tuple[dict[str, Any], Uncertainty]:
    declaration = registry.get(plan.capability_id)
    base = run_inputs_for(claim, declaration)
    qoi = plan.content["qoi"]
    reported = float(report.values[qoi["name"]].to(qoi["units"]).magnitude)
    input_spec = InputUncertainty.from_dict(spec["input_uncertainty"])
    draws = draw_samples(input_spec, plan.content["core_digest"])
    runs = []
    for i, draw in enumerate(draws):
        variant = run_variant(plan, registry, {**base, **draw}, f"{plan.run_id}~parameter~{i}")
        runs.append((variant, PropagatedRun(i, variant.run_id, draw, variant.value, variant.usable, variant.problem)))
    estimate = estimate_parameter_uncertainty([p for _, p in runs], quantity=qoi["name"], units=qoi["units"], nominal=reported, content=spec["content"], required_confidence=spec["confidence"])
    uncertainty = estimate.to_uncertainty()
    record = {
        "channel": UncertaintyChannel.EPISTEMIC_PARAMETER.value,
        "kind": "propagation",
        "spec": spec,
        "runs": [v.to_dict() for v, _ in runs],
        "estimate": estimate.to_dict(),
        "problem": None,
        "uncertainty": uncertainty.to_dict(),
    }
    return record, uncertainty



def _recordable(value: Any) -> Any:
    if isinstance(value, Quantity):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): _recordable(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_recordable(v) for v in value]
    return value


def _context_digest(inputs: Mapping[str, Any]) -> str:
    return tagged_digest(
        _EMPIRICAL_CONTEXT_TAG,
        {str(k): _recordable(v) for k, v in sorted(inputs.items())},
    )


def _aleatoric(
    plan,
    report,
    spec,
    observations: Sequence[DatasetObservation],
) -> tuple[dict[str, Any], Uncertainty]:
    qoi = plan.content["qoi"]
    nominal = report.values[qoi["name"]].to(qoi["units"])
    replicates: list[ReplicateObservation] = []
    source_observations: list[DatasetObservation] = []
    for item in observations:
        if item.quantity != qoi["name"] or not item.ready_for_measurement_evidence:
            continue
        if (
            item.uncertainty.kind is not UncertaintyKind.INTERVAL
            or UncertaintySource(item.uncertainty.source_kind)
            is not UncertaintySource.MEASUREMENT
        ):
            continue
        source_observations.append(item)
        replicates.append(
            ReplicateObservation(
                observation_id=item.observation_id,
                population_ref=f"{item.manifest_digest}:{item.dataset_version}",
                context_digest=_context_digest(item.conditions),
                independence_group=item.independence_group,
                quantity=item.quantity,
                value=item.value,
                measurement_uncertainty=item.uncertainty,
            )
        )

    if not replicates:
        problem = (
            "no eligible same-context physical replicate observations were supplied"
        )
        uncertainty = Uncertainty.unknown(
            f"aleatoric uncertainty not quantified: {problem}"
        )
        estimate = None
    else:
        estimate = estimate_aleatoric_replicates(
            replicates,
            nominal=nominal,
            content=float(spec["content"]),
            required_confidence=float(spec["confidence"]),
        )
        uncertainty = estimate.to_uncertainty()
        problem = estimate.failure_reason

    record = {
        "channel": UncertaintyChannel.ALEATORIC.value,
        "kind": "aleatoric_replicates",
        "spec": spec,
        "source_observations": [item.to_dict() for item in source_observations],
        "replicates": [item.to_dict() for item in replicates],
        "estimate": None if estimate is None else estimate.to_dict(),
        "problem": problem,
        "uncertainty": uncertainty.to_dict(),
    }
    return record, uncertainty


def _model_policy(spec: Mapping[str, Any]) -> ModelFormPolicy:
    raw = dict(spec["promotion_policy"])
    return ModelFormPolicy(
        minimum_calibration_groups=raw["minimum_calibration_groups"],
        minimum_validation_groups=raw["minimum_validation_groups"],
        minimum_calibration_observations=raw["minimum_calibration_observations"],
        minimum_validation_observations=raw["minimum_validation_observations"],
        minimum_holdout_coverage=raw["minimum_holdout_coverage"],
        coverage_factor=raw["coverage_factor"],
        estimator=raw["estimator"],
        empirical_quantile=raw["empirical_quantile"],
    )


def _discrepancy_protocol(spec: Mapping[str, Any]) -> DiscrepancyProtocol:
    raw = dict(spec["discrepancy_protocol"])
    return DiscrepancyProtocol(
        protocol_id=raw["protocol_id"],
        minimum_calibration_groups=raw["minimum_calibration_groups"],
        minimum_validation_groups=raw["minimum_validation_groups"],
        require_all_holdout_compatible=raw["require_all_holdout_compatible"],
    )


def _model_form(
    plan,
    registry,
    claim,
    report,
    spec,
    observations: Sequence[DatasetObservation],
    qualification: ProducerQualification | None,
) -> tuple[dict[str, Any], Uncertainty]:
    declaration = registry.get(plan.capability_id)
    qoi = plan.content["qoi"]
    produced = declaration.produced(qoi["name"])
    base = run_inputs_for(claim, declaration)
    eligible = tuple(
        item
        for item in observations
        if item.quantity == qoi["name"] and item.ready_for_measurement_evidence
    )
    pairs: list[PairedObservation] = []
    runs: list[VariantRun] = []
    problems: list[str] = []

    for index, item in enumerate(eligible):
        inputs = {**base, **dict(item.conditions)}
        variant = run_variant(
            plan,
            registry,
            inputs,
            f"{plan.run_id}~model_form~{index}",
        )
        runs.append(variant)
        if not variant.usable or variant.report is None or variant.value is None:
            problems.append(
                f"{item.observation_id}: prediction run is unusable ({variant.problem})"
            )
            continue
        predicted = Quantity(variant.value, qoi["units"])
        prediction_u: list[Uncertainty] = []
        carried = variant.report.uncertainty.get(qoi["name"])
        if (
            carried is not None
            and carried.is_quantified
            and carried.kind is UncertaintyKind.INTERVAL
            and UncertaintySource(carried.source_kind)
            in (UncertaintySource.NUMERICAL, UncertaintySource.PARAMETER)
        ):
            prediction_u.append(carried)
        measurement = item.to_measurement_record()
        pairs.append(
            PairedObservation(
                observation_id=item.observation_id,
                independence_group=item.independence_group,
                split=item.split,
                quantity=item.quantity,
                observed=item.value,
                predicted=predicted,
                measurement_uncertainty=item.uncertainty,
                prediction_uncertainties=tuple(prediction_u),
                context_digest=_context_digest(inputs),
                measurement_digest=measurement.digest,
            )
        )

    scope = None
    discrepancy = None
    attempt = None
    problem: str | None = None
    uncertainty: Uncertainty
    if not eligible:
        problem = "no eligible curated model/data observations were supplied"
    elif problems:
        problem = "; ".join(problems)
    elif not pairs:
        problem = "no usable paired model/data observations were produced"
    else:
        model_id = (
            produced.model_id
            if produced is not None and produced.model_id is not None
            else declaration.models[0].model_id
        )
        model_use = declaration.model(model_id)
        if model_use is None:
            problem = f"no declared model record for produced quantity {qoi['name']!r}"
        else:
            model_fingerprint = tagged_digest(_MODEL_SCOPE_TAG, model_use.to_dict())
            operating_digest = tagged_digest(
                _EMPIRICAL_CONTEXT_TAG,
                sorted(pair.context_digest for pair in pairs),
            )
            dataset_digest = tagged_digest(
                _MODEL_DATASET_TAG,
                [item.to_dict() for item in sorted(eligible, key=lambda o: o.observation_id)],
            )
            scope = ModelFormScope(
                model_id=model_id,
                model_fingerprint=model_fingerprint,
                operating_context_digest=operating_digest,
                evidence_dataset_digest=dataset_digest,
                quantity=qoi["name"],
                units=qoi["units"],
            )
            discrepancy = estimate_model_form_discrepancy(
                pairs, _discrepancy_protocol(spec)
            )
            attempt = evaluate_discrepancy_for_model_form(
                discrepancy,
                scope=scope,
                policy=_model_policy(spec),
            )
            if qualification is None:
                problem = (
                    "no independently reviewed model-form producer qualification "
                    "was supplied; held-out discrepancy evidence is not authority "
                    "to promote itself"
                )
            else:
                try:
                    uncertainty = promote_model_form_interval(
                        attempt.estimate,
                        qualification,
                        report.values[qoi["name"]].to(qoi["units"]),
                        target_scope=scope,
                        policy=_model_policy(spec),
                    )
                except ModelFormAuthorityError as exc:
                    problem = f"model-form promotion refused: {exc}"

    if problem is not None:
        uncertainty = Uncertainty.unknown(
            f"model-form uncertainty not quantified: {problem}"
        )

    record = {
        "channel": UncertaintyChannel.MODEL_FORM.value,
        "kind": "model_form_empirical",
        "spec": spec,
        "source_observations": [item.to_dict() for item in eligible],
        "runs": [item.to_dict() for item in runs],
        "pairs": [item.to_dict() for item in pairs],
        "scope": None if scope is None else scope.to_dict(),
        "qualification": (
            None if qualification is None else qualification.to_dict()
        ),
        "discrepancy": None if discrepancy is None else discrepancy.to_dict(),
        "model_form_estimate": (
            None
            if attempt is None
            else {
                "status": attempt.estimate.status.value,
                "half_width": attempt.estimate.half_width,
                "empirical_holdout_coverage":
                    attempt.estimate.empirical_holdout_coverage,
                "reason": attempt.estimate.reason,
                "promotion_allowed": attempt.promotion.decision.value == "promotable",
                "promotion_reasons": list(attempt.promotion.reasons),
            }
        ),
        "problem": problem,
        "uncertainty": uncertainty.to_dict(),
    }
    return record, uncertainty


def run_uncertainty_studies(
    plan: Any,
    registry: CapabilityRegistry,
    claim: ScientificClaim,
    report: Any,
    *,
    empirical_observations: Sequence[DatasetObservation] = (),
    model_form_qualification: ProducerQualification | None = None,
) -> StudyOutcome:
    """Run every planned UQ study; missing empirical evidence stays explicit UNKNOWN."""
    records = []
    channels: dict[UncertaintyChannel, Uncertainty] = {}
    empirical_observations = tuple(empirical_observations)
    if any(not isinstance(item, DatasetObservation) for item in empirical_observations):
        raise UncertaintyStudyError(
            "empirical_observations must contain DatasetObservation records"
        )
    if (
        model_form_qualification is not None
        and not isinstance(model_form_qualification, ProducerQualification)
    ):
        raise UncertaintyStudyError(
            "model_form_qualification must be ProducerQualification"
        )
    for channel, spec in planned_studies(plan):
        kind = spec["kind"]
        if kind == "refinement":
            record, uncertainty = _refinement(plan, registry, claim, report, spec)
        elif kind == "propagation":
            record, uncertainty = _propagation(plan, registry, claim, report, spec)
        elif kind == "aleatoric_replicates":
            record, uncertainty = _aleatoric(
                plan, report, spec, empirical_observations
            )
        elif kind == "model_form_empirical":
            record, uncertainty = _model_form(
                plan,
                registry,
                claim,
                report,
                spec,
                empirical_observations,
                model_form_qualification,
            )
        else:  # pragma: no cover - study_spec is the closed producer
            raise UncertaintyStudyError(f"unsupported planned study kind {kind!r}")
        records.append(record)
        if uncertainty.is_quantified:
            channels[channel] = uncertainty
    return StudyOutcome(tuple(records), channels)


def verify_study_records(records: Any, plan: Any, report: Any) -> StudyOutcome:
    """Re-derive every recorded estimate and channel record; refuse any record that does not re-derive."""
    expected = planned_studies(plan)
    if not isinstance(records, list) or len(records) != len(expected):
        raise UncertaintyStudyError("the recorded studies are not the studies the plan names")
    qoi = plan.content["qoi"]
    reported = float(report.values[qoi["name"]].to(qoi["units"]).magnitude)
    out, channels = [], {}
    for record, (channel, spec) in zip(records, expected):
        if record.get("channel") != channel.value or canonical_json(record.get("spec")) != canonical_json(spec):
            raise UncertaintyStudyError(f"the {channel.value} study record is not the planned study")
        try:
            if spec["kind"] == "refinement":
                estimate = estimate_from_dict(record["estimate"])
                values = [lv.value for lv in estimate.levels]
                names = [f"{plan.run_id}~numerical~{k}" for k in range(len(spec["ladder"]))]
            else:
                estimate = parameter_estimate_from_dict(record["estimate"])
                if not math.isclose(estimate.nominal, reported, rel_tol=0.0, abs_tol=0.0):
                    raise UncertaintyStudyError("the propagation's nominal is not the reported value")
                values = [r.value for r in estimate.runs]
                names = [f"{plan.run_id}~parameter~{i}" for i in range(len(estimate.runs))]
                draws = draw_samples(InputUncertainty.from_dict(spec["input_uncertainty"]), plan.content["core_digest"])
                if [canonical_json({k: v.to_dict() for k, v in sorted(d.items())}) for d in draws] != [
                    canonical_json({k: v.to_dict() for k, v in sorted(r.inputs.items())}) for r in estimate.runs
                ]:
                    raise UncertaintyStudyError("the propagated inputs are not the plan's seeded draws")
        except (KeyError, TypeError) as exc:
            raise UncertaintyStudyError(f"the {channel.value} study record is not readable: {exc}") from exc
        except ClaimLayerError as exc:
            raise UncertaintyStudyError(str(exc)) from exc
        runs = record.get("runs", [])
        if [r.get("run_id") for r in runs] != names:
            raise UncertaintyStudyError(f"the {channel.value} study's runs are not the planned variant runs")
        for r, v in zip(runs, values):
            if r.get("value") != v:
                raise UncertaintyStudyError(f"run {r.get('run_id')} records a value its estimate does not carry")
        if spec["kind"] == "refinement":
            problem = None
            unusable = [(k, r) for k, r in enumerate(runs) if not r.get("usable")]
            if unusable:
                problem = f"refinement level {unusable[0][0]} is not usable: {unusable[0][1].get('problem')}"
            elif not math.isclose(runs[0]["value"], reported, rel_tol=1e-12, abs_tol=0.0):
                problem = f"level 0 ({runs[0]['value']!r}) does not reproduce the reported value ({reported!r}); the study is not about the reported run"
            uncertainty = estimate.to_uncertainty() if problem is None else Uncertainty.unknown(f"numerical uncertainty not quantified: {problem}")
        else:
            problem = None
            if [bool(r.get("usable")) for r in runs] != [p.usable for p in estimate.runs]:
                raise UncertaintyStudyError("a propagated run's usability does not match its estimate")
            uncertainty = estimate.to_uncertainty()
        if record.get("problem") != problem or canonical_json(record.get("uncertainty")) != canonical_json(uncertainty.to_dict()):
            raise UncertaintyStudyError(f"the {channel.value} study's result does not re-derive from its runs")
        out.append(dict(record))
        if uncertainty.is_quantified:
            channels[channel] = uncertainty
    return StudyOutcome(tuple(out), channels)


__all__ = [
    "StudyOutcome",
    "UncertaintyStudyError",
    "VariantRun",
    "planned_studies",
    "run_inputs_for",
    "run_uncertainty_studies",
    "run_variant",
    "study_spec",
    "verify_study_records",
]
