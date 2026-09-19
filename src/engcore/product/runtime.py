"""Product-facing simulation gateway over the scientific claim runtime.

This package is deliberately above the Scientific Core and below transports
such as MCP, HTTP or a web UI. It does not contain physics, choose credibility
levels or trust language-model output.

A language model may propose a structured claim from user prose. The existing
natural-language adapter verifies that every proposed physical value is
grounded in a cited span of the user's text and refuses authority fields. The
deterministic compiler then decides whether the proposal is executable.

No OpenAI or Anthropic SDK belongs here. A transport or application may call
any provider it wants, then submit the provider's proposal to this boundary.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..claims.adapters.nl import compile_natural_language
from ..claims.assessment import assess_claim
from ..claims.capabilities import CapabilityRegistry
from ..claims.external_evidence import read_external_record
from ..claims.measurement_dataset import DatasetObservation
from ..claims.errors import ClaimLayerError
from ..scientific.serialization import schema_string
from ..uq.model_form.qualification import ProducerQualification

PRODUCT_CAPABILITIES_SCHEMA = schema_string("product_capabilities")
PRODUCT_PREPARATION_SCHEMA = schema_string("product_simulation_preparation")
PRODUCT_RUN_SCHEMA = schema_string("product_simulation_run")


class ProductRequestError(ValueError):
    """A product request is malformed before it reaches scientific compilation."""


def _wire_spans(spans: Mapping[str, Sequence[int]]) -> dict[str, tuple[int, int]]:
    """Read JSON-friendly path-to-[start,end] spans without coercion."""
    if not isinstance(spans, Mapping):
        raise ProductRequestError("spans must be an object mapping input paths to [start, end]")
    out: dict[str, tuple[int, int]] = {}
    for path, raw in spans.items():
        if not isinstance(path, str) or not path:
            raise ProductRequestError("every span key must be a non-empty input path")
        if (
            isinstance(raw, (str, bytes))
            or not isinstance(raw, Sequence)
            or len(raw) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in raw)
        ):
            raise ProductRequestError(f"span {path!r} must be [start, end] integer offsets")
        start, end = int(raw[0]), int(raw[1])
        if start < 0 or end <= start:
            raise ProductRequestError(f"span {path!r} must satisfy 0 <= start < end")
        out[path] = (start, end)
    return out


def _capability_view(registry: CapabilityRegistry) -> list[dict[str, Any]]:
    """Stable product discovery view, derived only from capability declarations."""
    return [
        {
            "capability_id": declaration.capability_id,
            "version": declaration.version,
            "domain": declaration.domain,
            "summary": declaration.summary,
            "produces": [
                {
                    "name": quantity.name,
                    "unit_exemplar": quantity.unit_exemplar,
                    "dimension": quantity.dimension,
                    "instance_key": quantity.instance_key,
                    "description": quantity.description,
                    "attainable_levels": sorted(
                        level.value for level in declaration.attainable(quantity.name)
                    ),
                    "quantified_uncertainty": sorted(
                        channel.value
                        for channel in declaration.uncertainty.channels_for(quantity.name)
                    ),
                }
                for quantity in declaration.produces
            ],
            "provides": sorted(
                capability.identifier for capability in declaration.provided_capabilities
            ),
            "claim_shapes": sorted(shape.value for shape in declaration.claim_shapes),
            "inputs": [item.to_dict() for item in declaration.inputs],
            "routes": [route.to_dict() for route in declaration.routes],
        }
        for declaration in registry
    ]


def describe_product(registry: CapabilityRegistry) -> dict[str, Any]:
    """Describe what the first product surface can actually simulate and judge."""
    return {
        "schema": PRODUCT_CAPABILITIES_SCHEMA,
        "product": {
            "name": "Forge",
            "surface": "scientific_simulation_runtime",
            "workflow": [
                "propose",
                "compile",
                "plan",
                "execute",
                "verify",
                "assess",
                "explain",
            ],
        },
        "registry_digest": registry.digest,
        "capabilities": _capability_view(registry),
        "llm_boundary": {
            "role": "proposal_only",
            "may": [
                "interpret user prose",
                "propose a structured scientific claim",
                "cite exact source spans for physical values",
                "explain the returned scientific record",
            ],
            "may_not": [
                "assert a verdict",
                "select an applicable model as authority",
                "invent missing physical values",
                "declare uncertainty zero",
                "award validation or credibility",
            ],
            "rule": (
                "The deterministic compiler and assessment runtime decide every "
                "scientific status. The LLM is never the scientific authority."
            ),
        },
        "notice": (
            "This is a simulation and scientific-assessment product boundary. "
            "It is not a safety certification or an automatic real-world decision."
        ),
    }


def _compile_proposal(
    text: str,
    proposal: Mapping[str, Any],
    spans: Mapping[str, Sequence[int]],
    registry: CapabilityRegistry,
):
    """Compile one provider proposal once, translating contract refusals to product input errors."""
    try:
        return compile_natural_language(
            text,
            proposal,
            _wire_spans(spans),
            registry,
        )
    except ClaimLayerError as exc:
        raise ProductRequestError(str(exc)) from exc


def _preparation_view(compilation: Any) -> dict[str, Any]:
    return {
        "schema": PRODUCT_PREPARATION_SCHEMA,
        "status": compilation.status,
        "ready": compilation.status == "ready",
        "findings": list(compilation.findings),
        "moved_to_missing": list(compilation.moved_to_missing),
        "compilation": (
            None
            if compilation.compiled is None
            else compilation.compiled.to_dict()
        ),
        "authority": (
            "The language model proposed the claim; grounding and deterministic "
            "compilation decided whether it is executable."
        ),
    }


def prepare_simulation(
    text: str,
    proposal: Mapping[str, Any],
    spans: Mapping[str, Sequence[int]],
    registry: CapabilityRegistry,
) -> dict[str, Any]:
    """Ground an LLM proposal in the user's prose and compile it without executing."""
    return _preparation_view(_compile_proposal(text, proposal, spans, registry))


def _assessment_view(record: Mapping[str, Any], *, digest: str) -> dict[str, Any]:
    """UI/API projection of an assessment. It derives no new scientific judgement."""
    credibility = record.get("credibility")
    assurance = record.get("assurance")
    return {
        "status": record.get("status"),
        "verdict": record.get("verdict"),
        "result": record.get("result"),
        "plan": record.get("plan"),
        "trust": {
            "credibility": None if credibility is None else credibility.get("verdict"),
            "evidence_basis": None if credibility is None else credibility.get("evidence_basis"),
            "assurance": None if assurance is None else assurance.get("verdict"),
            "validity": record.get("validity"),
            "verification": record.get("verification"),
            "validation": record.get("validation"),
            "uncertainty": record.get("uncertainty"),
        },
        "reasons": record.get("reasons", []),
        "limitations": record.get("limitations", []),
        "missing_evidence": record.get("missing_evidence", []),
        "repair_actions": record.get("repair_actions", []),
        "next_experiments": record.get("next_experiments"),
        "assessment_digest": digest,
    }


def run_simulation(
    claim: Mapping[str, Any],
    registry: CapabilityRegistry,
    *,
    external: Sequence[Mapping[str, Any]] = (),
    empirical_observations: Sequence[Mapping[str, Any]] = (),
    model_form_qualification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one structured product claim through the production scientific runtime."""
    offered = tuple(
        read_external_record(item.get("record", item))
        for item in external
    )
    empirical = tuple(
        DatasetObservation.from_dict(item)
        for item in empirical_observations
    )
    qualification = (
        None
        if model_form_qualification is None
        else ProducerQualification.from_dict(model_form_qualification)
    )
    assessment = assess_claim(
        claim,
        registry,
        external=offered,
        empirical_observations=empirical,
        model_form_qualification=qualification,
    )
    record = assessment.to_dict()
    return {
        "schema": PRODUCT_RUN_SCHEMA,
        "view": _assessment_view(record, digest=assessment.digest),
        "record": record,
        "notice": (
            "The view is a projection of the canonical assessment record; the "
            "record remains the auditable source of every displayed status."
        ),
    }


def run_proposed_simulation(
    text: str,
    proposal: Mapping[str, Any],
    spans: Mapping[str, Sequence[int]],
    registry: CapabilityRegistry,
    *,
    external: Sequence[Mapping[str, Any]] = (),
    empirical_observations: Sequence[Mapping[str, Any]] = (),
    model_form_qualification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """End-to-end product flow from an LLM proposal to an assessed simulation.

    A proposal that is not READY is returned as preparation data and is never
    executed. No missing value is defaulted merely to make the product flow.
    """
    compilation = _compile_proposal(text, proposal, spans, registry)
    preparation = _preparation_view(compilation)
    if not preparation["ready"] or preparation["compilation"] is None:
        return {
            "schema": PRODUCT_RUN_SCHEMA,
            "preparation": preparation,
            "view": None,
            "record": None,
            "notice": "The proposal was not executable; no simulation was run.",
        }

    if compilation.compiled is None or compilation.compiled.claim is None:
        raise ProductRequestError("a READY preparation produced no parsed scientific claim")
    result = run_simulation(
        compilation.compiled.claim.to_dict(),
        registry,
        external=external,
        empirical_observations=empirical_observations,
        model_form_qualification=model_form_qualification,
    )
    return {
        **result,
        "preparation": preparation,
    }


__all__ = [
    "PRODUCT_CAPABILITIES_SCHEMA",
    "PRODUCT_PREPARATION_SCHEMA",
    "PRODUCT_RUN_SCHEMA",
    "ProductRequestError",
    "describe_product",
    "prepare_simulation",
    "run_proposed_simulation",
    "run_simulation",
]
