"""A normalized, engineer-readable summary of one system run.

Built ONLY from records that already exist: the BIG 12 :class:`SystemRunResult`, the constraint
assessments, the verification ladder, reference comparisons, and the scientific status the existing
credibility authority derives (``trust_handoff`` -> ``CredibilityVerdict``).  It introduces no trust
vocabulary and no number of its own.  Model discrepancy must be stated by the caller (there is no
default), and an output whose uncertainty is UNKNOWN is printed as UNKNOWN, never as an error bar.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..credibility.evidence import CredibilityVerdict
from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import UncertaintyKind
from ..scientific.units.quantity import Quantity
from ..system_runtime import (
    Availability, ConstraintAssessment, ConservationAssessment, RunStatus, SystemRunRequest, SystemRunResult, trace_result, trust_handoff,
)
from .ladder import VerificationLadder
from .reference import ReferenceComparison, ReferenceRecord

SUMMARY_SCHEMA = "engcore.engineering.summary/1"


@dataclass(frozen=True)
class KeyOutput:
    label: str
    observable_id: str
    availability: str
    value: Quantity | None
    #: "UNKNOWN (why)" or the stated uncertainty kind; never a number invented here
    uncertainty: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "observable_id": self.observable_id, "availability": self.availability,
                "value": None if self.value is None else self.value.to_dict(), "uncertainty": self.uncertainty, "reason": self.reason}


@dataclass(frozen=True)
class ConstraintLine:
    binding_id: str
    constraint_id: str
    status: str
    margin: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"binding_id": self.binding_id, "constraint_id": self.constraint_id, "status": self.status, "margin": self.margin, "note": self.note}


@dataclass(frozen=True)
class UncertaintyStatement:
    #: every statement below is required: an absent one would read as "no uncertainty"
    known_input_uncertainty: tuple[str, ...]
    unknown_input_uncertainty: tuple[str, ...]
    model_discrepancy: str
    material_provenance: tuple[str, ...]
    model_applicability: str
    benchmark_applicability: str

    def __post_init__(self) -> None:
        if not str(self.model_discrepancy).strip() or not str(self.model_applicability).strip() or not str(self.benchmark_applicability).strip():
            raise InvalidScientificProblem("model discrepancy, model applicability and benchmark applicability must each be stated")
        if not any(tok in self.model_discrepancy.upper() for tok in ("NOT QUANTIFIED", "UNKNOWN")):
            raise InvalidScientificProblem("model discrepancy must be stated as UNKNOWN / NOT QUANTIFIED: this layer holds no quantified discrepancy record, and a number or 'none' here would read as zero")

    def to_dict(self) -> dict[str, Any]:
        return {"known_input_uncertainty": list(self.known_input_uncertainty), "unknown_input_uncertainty": list(self.unknown_input_uncertainty),
                "model_discrepancy": self.model_discrepancy, "material_provenance": list(self.material_provenance),
                "model_applicability": self.model_applicability, "benchmark_applicability": self.benchmark_applicability}


def _uncertainty_text(output) -> str:
    u = output.uncertainty
    if u.kind is UncertaintyKind.UNKNOWN:
        return f"UNKNOWN ({u.source or 'not quantified'})"
    return f"{u.kind.value} ({u.source or 'source not stated'})"


@dataclass(frozen=True)
class EngineeringSummary:
    system: str
    execution: str
    key_outputs: tuple[KeyOutput, ...]
    constraints: tuple[ConstraintLine, ...]
    conservation: tuple[str, ...]
    ladder: VerificationLadder
    comparisons: tuple[ReferenceComparison, ...]
    uncertainty: UncertaintyStatement
    #: the EXISTING credibility verdict value; never an invented one
    scientific_status: str
    scientific_status_basis: str
    identities: tuple[tuple[str, str], ...]
    providers: tuple[str, ...]
    trace_complete: bool
    trace_gaps: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def _core_dict(self) -> dict[str, Any]:
        return {"schema": SUMMARY_SCHEMA, "system": self.system, "execution": self.execution,
                "key_outputs": [k.to_dict() for k in self.key_outputs], "constraints": [c.to_dict() for c in self.constraints],
                "conservation": list(self.conservation), "verification": self.ladder.to_dict(),
                "reference_comparisons": [c.to_dict() for c in self.comparisons], "uncertainty": self.uncertainty.to_dict(),
                "scientific_status": self.scientific_status, "scientific_status_basis": self.scientific_status_basis,
                "identities": [list(i) for i in self.identities], "providers": list(self.providers),
                "trace": {"complete": self.trace_complete, "gaps": list(self.trace_gaps)}, "notes": list(self.notes)}

    def to_dict(self) -> dict[str, Any]:
        core = self._core_dict()
        #: the sha256 of ``summary.txt``, which is rendered from ``core`` alone: the text a bundle ships cannot be edited apart from this record
        core["text_sha256"] = hashlib.sha256(render_summary_text(core).encode("utf-8")).hexdigest()
        return core

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def render_text(self) -> str:
        return render_summary_text(self._core_dict())


def render_summary_text(payload: Mapping[str, Any]) -> str:
    """The engineer-readable text of a summary, rendered from its dict form (the same function renders it when a bundle is verified)."""
    out = [f"SYSTEM\n  {payload['system']}", f"EXECUTION\n  {str(payload['execution']).upper()}", "KEY OUTPUTS"]
    for k in payload["key_outputs"]:
        v = k["value"]
        shown = f"{v['magnitude']:.6g} {v['units']}" if v is not None else f"{str(k['availability']).upper()}: {k['reason']}"
        out.append(f"  {k['label']}: {shown}   [uncertainty {k['uncertainty']}]")
    out.append("CONSTRAINTS")
    out += [f"  {c['binding_id']} ({c['constraint_id']}): {str(c['status']).upper()}{'  (' + c['margin'] + ')' if c['margin'] else ''}" for c in payload["constraints"]] or ["  none declared"]
    if payload["conservation"]:
        out.append("CONSERVATION")
        out += [f"  {line}" for line in payload["conservation"]]
    out.append("VERIFICATION")
    for e in payload["verification"]["levels"]:
        out.append(f"  L{e['level']} {str(e['status']).replace('_', ' ')}: {e['note']}")
    out.append("REFERENCE COMPARISONS")
    out += [f"  {c['classification']}: {c['criterion']['criterion_id']} {str(c['outcome']).upper()} ({c['value']['magnitude']:.4g} {c['value']['units']}; tolerance "
            f"{c['criterion']['tolerance']['magnitude']:.4g} {c['criterion']['tolerance']['units']})" for c in payload["reference_comparisons"]] or ["  NOT AVAILABLE"]
    u = payload["uncertainty"]
    out += ["UNCERTAINTY", f"  known input uncertainty: {', '.join(u['known_input_uncertainty']) or 'none stated'}",
            f"  UNKNOWN input uncertainty: {', '.join(u['unknown_input_uncertainty']) or 'none'}", f"  model discrepancy: {u['model_discrepancy']}",
            f"  model applicability: {u['model_applicability']}", f"  benchmark applicability: {u['benchmark_applicability']}",
            f"SCIENTIFIC STATUS\n  {payload['scientific_status']} - {payload['scientific_status_basis']}",
            f"TRACE\n  {'complete' if payload['trace']['complete'] else 'GAPS: ' + '; '.join(payload['trace']['gaps'])}"]
    return "\n".join(out) + "\n"


def build_summary(title: str, request: SystemRunRequest, result: SystemRunResult, *, outputs: Sequence[tuple[str, str]],
                  constraints: Sequence[ConstraintAssessment] = (), conservation: Sequence[ConservationAssessment] = (),
                  ladder: VerificationLadder, comparisons: Sequence[ReferenceComparison] = (), references: Sequence[ReferenceRecord] = (),
                  uncertainty: UncertaintyStatement, trace_observable: str, notes: Sequence[str] = ()) -> EngineeringSummary:
    """Assemble the summary of ``result``.  ``outputs`` are (label, observable id) pairs the flagship declares as headline.

    Every reference comparison must name a reference that is supplied (so a bundle can ship it), and every ladder link that claims to be a
    reference comparison must carry exactly one of the supplied comparisons."""
    if result.request_digest != request.digest:
        raise InvalidScientificProblem("the request is not the one this result was produced for")
    supplied_refs = {r.digest for r in references}
    for c in comparisons:
        if c.reference_digest not in supplied_refs:
            raise InvalidScientificProblem(f"comparison {c.criterion.criterion_id!r} names a reference that is not supplied with the summary (it cannot be bundled)")
    supplied_cmps = {canonical_digest(c.to_dict()) for c in comparisons}
    cited: set[str] = set()
    for entry in ladder.entries:
        for link in entry.evidence:
            if link.kind == "reference_comparison":
                if link.record_digest not in supplied_cmps:
                    raise InvalidScientificProblem(f"level {entry.level} cites a reference comparison that is not among the summary's comparisons")
                cited.add(link.record_digest)
    if supplied_cmps - cited:
        raise InvalidScientificProblem("a reference comparison is reported but no ladder level cites it (a not-met comparison must not be omitted from the ladder)")
    if result.trust_inputs.unknown_uncertainty_outputs and not uncertainty.unknown_input_uncertainty:
        raise InvalidScientificProblem("outputs with UNKNOWN uncertainty exist, so the statement must name the UNKNOWN input uncertainty (an empty list would read as none)")
    key: list[KeyOutput] = []
    for label, obs_id in outputs:
        o = result.observable(obs_id)
        if o.availability is Availability.AVAILABLE:
            key.append(KeyOutput(label, obs_id, "available", o.value.value, _uncertainty_text(o.value)))
        else:
            key.append(KeyOutput(label, obs_id, o.availability.value, None, "not available", o.reason))
    lines = tuple(ConstraintLine(c.binding_id, c.constraint_id, c.status,
                                 "" if c.check is None else f"margin {c.check.margin.magnitude:.4g} {c.check.margin.units}", c.reason) for c in constraints)
    cons = tuple(f"{c.balance_id}: {c.status}" + (f" residual {c.residual.magnitude:.3e} {c.residual.units} (tolerance {c.tolerance.magnitude:.3e})"
                                                  if c.residual is not None else f" (missing: {', '.join(c.missing_terms)})") for c in conservation)
    report = trust_handoff(result, request, allow_partial=result.status is not RunStatus.SUCCEEDED)
    verdict: CredibilityVerdict = report.verdict
    trace = trace_result(result, trace_observable)
    providers = tuple(sorted({f"{p.provider_id} {p.provider_version}" for p in result.provider_records}))
    basis = ("derived by the existing credibility authority; the runtime supplies no validity record and no validation check, "
             "and this summary adds none")
    return EngineeringSummary(
        title, result.status.value, tuple(key), lines, cons, ladder, tuple(comparisons), uncertainty, verdict.value, basis,
        (("request", result.request_digest), ("plan", result.plan_digest), ("result", result.digest)), providers, trace.complete,
        tuple(trace.gaps), tuple(notes))
