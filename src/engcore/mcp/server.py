"""The MCP transport: this runtime, exposed to an agent, over stdio.

The domain run tools remain **transport and nothing else**: they compute no
physics here, evaluate no condition here and re-decide no credibility verdict.
Every scientific fact they return was produced below this module.

The public surface also exposes structured claim orchestration and a product
gateway. The product tools do not compute physics or invent scientific
judgement: they ground an outer LLM proposal, compile it against the production
capability registry and execute only when the deterministic compiler says the
claim is READY. The LLM remains a proposer, never the authority that chooses
model applicability, evidence, uncertainty or a verdict.

**The unflattering verdict is transmitted.** The nominal electro-thermal case
reports ``INSUFFICIENT_EVIDENCE``, because the payload has no field for a
resistor's rated dissipation or a source's current limit and
``electrical.dc.kcl`` declares no conditions at all — so those models are
honestly UNKNOWN (``NEEDS.md`` A2.4, A2.5). This server does not soften that,
filter it or re-rank it. A transport that improved a verdict on the way past
would be the exact substitution the layer beneath it exists to refuse.

**What this module adds, and it is one thing.** :func:`_fired_rules` turns a
verdict into the list of *rules that fired*, each naming the specific
condition, check or gap behind it, so an agent receiving ``NOT_SUPPORTED``
knows which bound was violated and one receiving ``INSUFFICIENT_EVIDENCE``
knows what is missing — without a second call. Every rule reads a property the
report already exposes; none re-derives a status, and the enumeration is
checked against the report's own verdict rather than trusted
(:func:`_verdict_block`).
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import mcp.types as mcp_types
from mcp.server.mcpserver import MCPServer

from ..scientific.models.definition import ValidityStatus
from ..product import (
    ProductRequestError,
    describe_product as _describe_product,
    prepare_simulation as _prepare_simulation,
    run_proposed_simulation as _run_proposed_simulation,
    run_simulation as _run_simulation,
)
from ..systems.electrothermal import coupled as cp
from .errors import (
    MalformedPayloadError,
    MissingFieldError,
    MissingUnitError,
    ProblemPayloadError,
    UnknownFieldError,
    WrongDimensionError,
)
from ..scientific.solvers.protocol import ConvergenceState
from .evidence import EVIDENCE_BASIS_ORDER, CredibilityVerdict
from .battery import run_battery_case
from .claim_assessment import (
    ClaimAssessmentError,
    assess_claim_request,
    refused_claim_assessment,
)
from .canonical import plan_canonical_engineering_intent
from .intent import compile_engineering_intent
from .planning import plan_engineering_intent
from .answer import summarize_engineering_run
from .scenario_uq import scenario_envelope
from .context import evaluate_context
from .probabilistic_uq import build_deterministic_samples, predictive_intervals
from .problem import (
    CaseDescription,
    build_electrothermal_system,
    describe_electrothermal_case,
    run_electrothermal_case,
)
from .systems import SYSTEMS, system

__all__ = [
    "BATTERY_RESPONSE_SCHEMA",
    "CAPABILITIES_SCHEMA",
    "RESPONSE_SCHEMA",
    "SERVER_NAME",
    "SERVER_VERSION",
    "SYSTEM_NAME",
    "assess_claim",
    "assess_scientific_claim",
    "build_server",
    "answer_engineering_problem",
    "answer_engineering_scenarios",
    "evaluate_engineering_context",
    "answer_engineering_uncertainty",
    "compile_engineering_problem",
    "plan_canonical_engineering_intent",
    "plan_engineering_problem",
    "describe_capabilities",
    "describe_empirical_uq",
    "describe_product",
    "main",
    "prepare_simulation",
    "run_battery",
    "run_proposed_simulation",
    "run_simulation",
    "run_electrothermal",
    "run_engineering_problem",
]

SERVER_NAME = "crafty-engcore"
SERVER_VERSION = "0.11.0"
CAPABILITIES_SCHEMA = "mcp_capabilities/1"
RESPONSE_SCHEMA = "mcp_electrothermal_response/1"
BATTERY_RESPONSE_SCHEMA = "mcp_battery_response/1"

#: The electro-thermal system's name. Kept as a module constant because the
#: response carries it and because this module was written around it; the
#: authority for what systems exist is :data:`engcore.mcp.systems.SYSTEMS`.
SYSTEM_NAME = "electrothermal"


# =====================================================================
# What a verdict means — and what it does not
# =====================================================================

#: Prose for each verdict. Deliberately **not** derived, because no registry
#: states it: the source of truth is ``CredibilityVerdict``'s own docstring in
#: ``evidence.py`` and this is a restatement of it for a reader who has only
#: the wire format. The guard below is what stops it drifting into a lie by
#: omission — a member added to the enum fails at import rather than arriving
#: at an agent with no explanation attached.
_VERDICT_GUIDANCE: Mapping[CredibilityVerdict, Mapping[str, str]] = {
    CredibilityVerdict.SUPPORTED: {
        "means": "Nothing in this report argues against relying on the result, "
                 "and at least one check both passed and established an "
                 "evidentiary level.",
        "does_not_mean": "It does not mean the result is right, that the model "
                         "is accurate, or that anything has been certified, "
                         "and it does not discharge the engineer of record's "
                         "judgement. Read the checks, the levels they "
                         "established and the conditions each model was judged "
                         "against, and decide. A SUPPORTED report may carry "
                         "WARNING checks.",
        "action": "Read the evidence and decide.",
    },
    CredibilityVerdict.INSUFFICIENT_EVIDENCE: {
        "means": "Something needed to answer the question was never produced — "
                 "a condition nobody could evaluate, a check that did not run, "
                 "a model nobody assessed, or a coupled run that never reached "
                 "its own criterion.",
        "does_not_mean": "It is not a failure and says nothing against the "
                         "design. It is the absence of an answer, not a "
                         "negative one.",
        "action": "Produce the missing evidence: declare the inputs named in "
                  "verdict_reasons, or raise the coupling budget. Re-running "
                  "the same case unchanged returns the same verdict.",
    },
    CredibilityVerdict.NOT_SUPPORTED: {
        "means": "Something that was produced argues against the result: a "
                 "bound known to be violated, or a check that ran and failed.",
        "does_not_mean": "It does not mean the numbers are arithmetically wrong "
                         "— it means the model was applied outside where anyone "
                         "has said it holds, so the numbers evidence nothing. "
                         "More evidence cannot rescue it.",
        "action": "Change the design or the model. NOT_SUPPORTED outranks "
                  "INSUFFICIENT_EVIDENCE, so gaps may also be present; they "
                  "are reported under other_findings.",
    },
}

#: What a caller does about each refusal class. One entry per subclass of
#: ``ProblemPayloadError`` — the taxonomy that exists precisely because each
#: maps to a *different repair*.
_REPAIR: Mapping[type, str] = {
    MalformedPayloadError: "Fix the shape, or the admissible value, at this path.",
    MissingFieldError: "Supply this field. It is required and has no default.",
    MissingUnitError: "Send a string carrying a magnitude and a unit, e.g. "
                      "'10 ohm'. This boundary will not choose a unit on your "
                      "behalf.",
    UnknownFieldError: "Remove or correct this key — see expected.accepted_keys "
                       "for the names this section takes. A misspelling is "
                       "refused rather than ignored, because dropping it would "
                       "present as a declaration you never made.",
    WrongDimensionError: "Send any unit of the dimension in expected.dimension. "
                         "The value parsed; its dimension is not the one this "
                         "field needs.",
}


#: The same three questions, answered for each (verdict, evidence basis) pair (R-04, core re-audit
#: 2026-09-16). ``_VERDICT_GUIDANCE`` above is the VALIDATED reading and is what
#: ``describe_capabilities`` has always listed per verdict; it is left byte-identical. What the audit
#: found is that an agent reading ``means`` on a SUPPORTED report could be told
#: more than its attained evidence basis justified. Some capabilities now carry benchmark
#: or independently implemented solver evidence and others remain verification-only, so the
#: response must render the basis actually attained on this run rather than make a server-wide
#: assumption. The word stays SUPPORTED; the sentence beside it says which kind of evidence
#: this particular report rests on.
_BASIS_GUIDANCE: Mapping[tuple[CredibilityVerdict, str], Mapping[str, str]] = {
    (CredibilityVerdict.SUPPORTED, "VALIDATED"): {
        "means": _VERDICT_GUIDANCE[CredibilityVerdict.SUPPORTED]["means"]
                 + " At least one of those levels compares the model with something outside "
                   "itself: a benchmark, an experiment, or an independently implemented solver.",
        "does_not_mean": _VERDICT_GUIDANCE[CredibilityVerdict.SUPPORTED]["does_not_mean"],
        "action": _VERDICT_GUIDANCE[CredibilityVerdict.SUPPORTED]["action"],
    },
    (CredibilityVerdict.SUPPORTED, "VERIFICATION_ONLY"): {
        "means": "Nothing in this report argues against relying on the result, and at least one "
                 "check both passed and established an evidentiary level -- but every level "
                 "attained is a VERIFICATION level: it says the declared model was solved "
                 "correctly. This report contains no comparison of the model with the world.",
        "does_not_mean": "It does not mean the model describes the part, that the equations are the "
                         "right equations, or that any measurement agrees with the answer. Nothing "
                         "here was compared with a benchmark, an experiment, or an independently "
                         "implemented solver. A correct solution of the wrong model is exactly what "
                         "this verdict cannot distinguish. Read the attained levels, the conditions "
                         "each model was judged against, and decide.",
        "action": "Read the evidence and decide, and decide separately whether the model applies: "
                  "this report does not answer that. To demand more, set required_evidence_basis "
                  "to VALIDATED and the verdict becomes INSUFFICIENT_EVIDENCE until something "
                  "outside the model agrees with it.",
    },
    (CredibilityVerdict.SUPPORTED, "NONE"): {
        "means": "Reserved: SUPPORTED requires at least one attained level, so this pair cannot "
                 "arise. It is described because an undescribed pair must not reach an agent.",
        "does_not_mean": "It is not a verdict this platform can produce.",
        "action": "Report this response as a defect in engcore.mcp.",
    },
}
for _verdict in (CredibilityVerdict.INSUFFICIENT_EVIDENCE, CredibilityVerdict.NOT_SUPPORTED):
    for _basis in ("VALIDATED", "VERIFICATION_ONLY", "NONE"):
        # A gap and a finding mean what they mean whatever was attained beside them: the rules that
        # produced them are in `verdict_reasons`, and the basis is reported as a field. Only
        # SUPPORTED's sentence depended on the reader assuming the levels meant more than they did.
        _BASIS_GUIDANCE[(_verdict, _basis)] = _VERDICT_GUIDANCE[_verdict]

#: What each evidence basis IS, in one sentence, for the block and for describe_capabilities.
_BASIS_MEANS: Mapping[str, str] = {
    "VALIDATED": "At least one attained level compares the model with something outside itself.",
    # R-39 (I-12 part A): agreement between two solvers is named here explicitly, because it is the level
    # most likely to be read as validation -- it used to be counted as one -- and because it is the only
    # level in this group that involves a second program rather than a second look at the same one.
    "VERIFICATION_ONLY": "Every attained level says the declared model was solved correctly. That includes "
                         "agreement between two solvers of the same declared model, which compares two "
                         "implementations and not the model with the world. Nothing here compares it with "
                         "the world.",
    "NONE": "No check both passed and established an evidentiary level.",
}


def _audit_tables() -> None:
    """Refuse to import while anything an agent could receive is undescribed.

    The discipline ``derive_verdict`` applies to an enum member it was not
    written for: a verdict or refusal class with no entry here would reach an
    agent with no explanation and no repair, which is worse than a crash.
    """
    for defined, described, what in (
        ({v.value for v in CredibilityVerdict},
         {v.value for v in _VERDICT_GUIDANCE}, "verdict"),
        # R-04: every (verdict, basis) pair, for the reason every verdict is described --
        # a pair with no entry would reach an agent with no explanation attached.
        ({f"{v.value}/{b}" for v in CredibilityVerdict for b in EVIDENCE_BASIS_ORDER},
         {f"{v.value}/{b}" for v, b in _BASIS_GUIDANCE}, "verdict and evidence basis pair"),
        ({str(b) for b in EVIDENCE_BASIS_ORDER}, set(_BASIS_MEANS), "evidence basis"),
        ({c.__name__ for c in ProblemPayloadError.__subclasses__()},
         {c.__name__ for c in _REPAIR}, "payload error class"),
    ):
        if defined != described:
            raise RuntimeError(
                f"engcore.mcp.server describes {sorted(described)} but the "
                f"platform defines {sorted(defined)}; an undescribed {what} "
                f"must not reach an agent unexplained"
            )


_audit_tables()


# =====================================================================
# describe_capabilities
# =====================================================================

def _describe_system(boundary) -> dict[str, Any]:
    """One system, entirely off its own description.

    Nothing about a field is restated here. ``required``, ``dimension``,
    ``unit_exemplar``, the prose and the unlocked conditions all come from
    the model records through the boundary's own describe function, and the
    example is the one that boundary publishes.
    """
    description = boundary.description()
    payload = description.to_dict()
    return {
        "name": boundary.name,
        "tool": boundary.tool,
        "summary": boundary.summary,
        "models": payload["models"],
        "fields": payload["fields"],
        "required_fields": [f.path for f in description.required],
        "optional_fields": [f.path for f in description.optional],
        "example_case": payload["example"],
        # Not fields with a rule attached -- fields that do not exist. Each is
        # solved for by the run, and a payload asserting one would fix the
        # answer it is supposed to find. Empty for a system that solves for
        # nothing the caller might otherwise declare, which is a fact about
        # that system rather than a gap in this description.
        "fields_you_may_not_supply": [
            {"model_input": name, "why": why}
            for name, why in sorted(payload["coupling_supplied_inputs"].items())
        ],
    }


def describe_capabilities() -> dict[str, Any]:
    """Everything an agent needs to write a case, read off the registries.

    **Every system, from one loop.** The list used to be one hand-written
    entry: a summary beside a call to one builder, which is a description of
    the electro-thermal system wearing the shape of a description of the
    runtime. Systems are now a registry (:mod:`engcore.mcp.systems`) and each
    describes itself; adding a third is an entry there, not an edit here.

    Required flags, dimensions, unit exemplars, prose, unlocked conditions and
    the runnable example all come from the model records at call time, so this
    description cannot drift from what the run tools will accept.
    """
    return {
        "schema": CAPABILITIES_SCHEMA,
        "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "systems": [_describe_system(boundary) for boundary in SYSTEMS],
        "verdicts": [
            {
                "value": verdict.value,
                **_VERDICT_GUIDANCE[verdict],
                # R-04: what the same verdict means on each kind of evidence, so an agent
                # knows before it calls that a SUPPORTED verdict may rest on verification
                # alone -- which, on this server, every SUPPORTED verdict does.
                "by_evidence_basis": [
                    {"evidence_basis": basis, "evidence_basis_means": _BASIS_MEANS[basis],
                     **_BASIS_GUIDANCE[(verdict, basis)]}
                    for basis in sorted(EVIDENCE_BASIS_ORDER, key=EVIDENCE_BASIS_ORDER.get, reverse=True)
                ],
            }
            for verdict in CredibilityVerdict
        ],
        "how_to_read_a_field": {
            "required": "Omitting it is a refusal; the case cannot be posed.",
            "dimension": "Any unit of this dimension is accepted. "
                         "unit_exemplar is one such unit, not the required one.",
            "unlocks_conditions": "Validity conditions that become decidable "
                                  "when this optional field is supplied, and "
                                  "report UNKNOWN without it. Omitting a field "
                                  "is never an error and never yields IN_DOMAIN.",
            "alternative_to": "Other keys that can do this field's job. Supply "
                              "this one or those; group_unlocks_conditions is "
                              "what the group unlocks.",
        },
        "notice": "A credibility evidence report is advisory input to an "
                  "engineer of record. It is not a decision, not a "
                  "certification, and not a claim of conformance with ASME "
                  "V&V 10/20/40 or NASA-STD-7009, whose vocabulary it borrows.",
    }


# =====================================================================
# The reasons behind a verdict
# =====================================================================

def _unknown_models(report: Any) -> list[dict[str, Any]]:
    """Every model assessed UNKNOWN, with the conditions that left it there.

    The condition list can be **empty**, and that is not a bug: a model whose
    validity domain declares no conditions is UNKNOWN by the core's own rule —
    absence of declared limits is not evidence of unlimited validity — and
    ``electrical.dc.kcl`` is exactly that model. Reporting condition names
    alone would drop it, leaving an agent a verdict with nothing behind it.
    """
    return [
        {
            "model_id": record.model_id,
            "unknown_conditions": list(record.assessment.unknown),
            "note": (
                ""
                if record.assessment.unknown
                else "declares no validity conditions, so nothing was evaluated"
            ),
        }
        for record in report.validity
        if ValidityStatus(record.assessment.status) is ValidityStatus.UNKNOWN
    ]


def _finished(report: Any) -> bool:
    """Whether the solver behind this report said it was done (R-10).

    ``None`` is the absence of a state -- a report around values that came from no solver -- and is
    not a rule firing. Read through the enum, like everything else a rule reads.
    """
    state = getattr(report, "convergence", None)
    return state is None or ConvergenceState(state) in (
        ConvergenceState.CONVERGED,
        ConvergenceState.NOT_APPLICABLE,
    )


def _fired_rules(report: Any) -> list[dict[str, Any]]:
    """Each rule of ``derive_verdict`` that this report's contents trigger.

    Read off the report's own derived properties, in the order
    :func:`~engcore.mcp.evidence.derive_verdict` applies them. Nothing here
    decides a verdict; :func:`_verdict_block` checks the enumeration against
    the verdict the report itself produces, so a rule that stopped matching is
    a loud failure rather than a silent omission.
    """
    verdicts = CredibilityVerdict
    coupling = report.coupling
    candidates = (
        ("model_validity_violated", verdicts.NOT_SUPPORTED,
         report.violated_conditions,
         lambda v: {"violated_conditions":
                    [{"model_id": m, "condition": c} for m, c in v]}),
        ("validation_check_failed", verdicts.NOT_SUPPORTED,
         report.failed_checks, lambda v: {"failed_checks": list(v)}),
        ("model_validity_unknown", verdicts.INSUFFICIENT_EVIDENCE,
         _unknown_models(report), lambda v: {"models": v}),
        ("validation_check_not_run", verdicts.INSUFFICIENT_EVIDENCE,
         report.not_run_checks, lambda v: {"not_run_checks": list(v)}),
        ("model_never_assessed", verdicts.INSUFFICIENT_EVIDENCE,
         report.unassessed_models,
         lambda v: {"models": [{"model_id": m, "version": r} for m, r in v]}),
        ("assessment_unattributed", verdicts.INSUFFICIENT_EVIDENCE,
         report.unattributed_assessments,
         lambda v: {"models": [{"model_id": m, "version": r} for m, r in v]}),
        ("no_validity_records", verdicts.INSUFFICIENT_EVIDENCE,
         () if report.validity else ("empty",),
         lambda v: {"note": "nobody asked whether any model applied"}),
        ("coupling_criterion_not_met", verdicts.INSUFFICIENT_EVIDENCE,
         () if coupling is None or coupling.is_met else (coupling,),
         lambda v: {
             "outcome": v[0].outcome,
             "iterations_run": v[0].iterations_run,
             "iteration_limit": v[0].iteration_limit,
             "largest_iterate_change": str(v[0].largest_iterate_change),
             "tolerance": str(v[0].tolerance),
         }),
        ("no_attained_level", verdicts.INSUFFICIENT_EVIDENCE,
         () if report.attained_levels else ("empty",),
         lambda v: {"note": "no check both passed and established a level"}),
        ("required_level_not_attained", verdicts.INSUFFICIENT_EVIDENCE,
         report.missing_required_levels,
         lambda v: {"missing_levels": [level.value for level in v]}),
        # R-10, named here: the batch-7 rule makes this INSUFFICIENT_EVIDENCE, and the
        # NOT_RUN check it also writes already showed up under validation_check_not_run.
        # A reader seeing "a check did not run" would look for a check; what happened is
        # that the solver stopped.
        ("solver_did_not_converge", verdicts.INSUFFICIENT_EVIDENCE,
         () if _finished(report) else (report.convergence,),
         lambda v: {"convergence": ConvergenceState(v[0]).value,
                    "note": "the solver reported that it had not finished; these values are an "
                            "iterate and not a solution"}),
        ("required_evidence_basis_not_attained", verdicts.INSUFFICIENT_EVIDENCE,
         () if report.missing_evidence_basis is None else (report.missing_evidence_basis,),
         lambda v: {"required_evidence_basis": v[0],
                    "evidence_basis": report.evidence_basis}),
        # Never decides anything. Carried because SUPPORTED absorbs it, which
        # makes it the finding a reader is most likely to miss.
        ("check_warned", None, report.warning_checks,
         lambda v: {"warning_checks": list(v)}),
        # R-04: never decides anything either, and for the same reason it is carried:
        # SUPPORTED absorbs it, and it is the thing a reader most needs told. Every
        # SUPPORTED verdict either MCP tool can return today fires this rule.
        ("verification_only", None,
         () if report.evidence_basis == "VALIDATED" else (report.evidence_basis,),
         lambda v: {"evidence_basis": v[0],
                    "means": _BASIS_MEANS[v[0]],
                    "attained_levels": sorted(level.value for level in report.attained_levels),
                    "levels_withheld": [list(entry) for entry in report.levels_withheld]}),
    )
    return [
        {"rule": rule,
         "produces": verdict.value if verdict else None,
         "detail": detail(value)}
        for rule, verdict, value, detail in candidates
        if value
    ]


def _verdict_block(report: Any) -> dict[str, Any]:
    """The verdict, what it means, and the rules that produced it."""
    verdict = report.verdict
    fired = _fired_rules(report)
    reasons = [rule for rule in fired if rule["produces"] == verdict.value]
    # A verdict other than SUPPORTED is produced by a rule, so an empty
    # `reasons` means this enumeration has fallen out of step with
    # `derive_verdict` — and would hand an agent a refusal it cannot act on.
    # Fail loudly rather than transmit one.
    if verdict is not CredibilityVerdict.SUPPORTED and not reasons:
        raise RuntimeError(
            f"report {report.run_id!r} reports {verdict.value!r} and this "
            f"transport can name no rule that produced it; the reason "
            f"enumeration in engcore.mcp.server is out of step with "
            f"derive_verdict"
        )
    basis = report.evidence_basis
    return {
        "value": verdict.value,
        # R-04: the sentence beside the word, keyed by (verdict, basis). SUPPORTED on
        # verification alone no longer reads as though something outside the model agreed.
        **_BASIS_GUIDANCE[(verdict, basis)],
        "evidence_basis": basis,
        "evidence_basis_means": _BASIS_MEANS[basis],
        "attained_levels": sorted(level.value for level in report.attained_levels),
        "levels_withheld": [list(entry) for entry in report.levels_withheld],
        "warning_checks": list(report.warning_checks),
        "verdict_reasons": reasons,
        # Rules that fired without deciding this verdict: gaps outranked by a
        # finding, and warnings, which never decide anything.
        "other_findings": [
            rule for rule in fired if rule["produces"] != verdict.value
        ],
    }


# =====================================================================
# run_electrothermal
# =====================================================================

def _response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The whole run, as JSON. Every value transported, none computed."""
    case = run_electrothermal_case(payload)
    system = build_electrothermal_system(payload)
    stages = system.stages
    if case.run.refusal is not None:
        # A refused run carries ONE report, about the problem that was refused,
        # and the stage it belongs to is not necessarily the first. Zipping the
        # payload's stages with the reports in order published R2's refusal
        # under R1 (audit CAP-06). The stage is found by the problem id instead.
        refused_id = case.run.refusal.result.problem_id
        stages = tuple(
            stage
            for stage, prop_problem, thermal_problem in cp.stage_problems(system)
            if refused_id in (prop_problem.problem_id, thermal_problem.problem_id)
        ) or stages[:1]
    coupling = case.reports[0].coupling
    return {
        "schema": RESPONSE_SCHEMA,
        "system": SYSTEM_NAME,
        # The coupling's own statement, as its own field. It is a property of
        # the iteration *between* results rather than any participant's
        # numerical convergence. Also carried inside each report.
        "coupling": coupling.to_dict() if coupling else None,
        "stages": [
            {
                "component_id": stage.component_id,
                "verdict": _verdict_block(report),
                # Verbatim: values with units, per-model validity with its
                # satisfied/violated/unknown condition names, every validation
                # check including NOT_RUN, provenance, and the caller's own
                # asserted context under its `caller_asserted` marking.
                "report": report.to_dict(),
                # What would have to change for each violated condition to
                # enter the validated domain: one line per declared input the
                # domain can invert exactly, and every input it could not,
                # named with the reason. Alternatives, never a plan -- nothing
                # here ranks them or recommends one, and no entry can name a
                # bound. See `engcore.domains.repair`.
                "repairs": [repair.to_dict() for repair in repairs],
            }
            for stage, report, repairs in zip(
                stages, case.reports, case.repairs
            )
        ],
    }


def _walk(payload: Any, path: str) -> Any:
    """The value at a dotted, indexed path — ``stages[0].body.duration``.

    Used only to echo back **what the caller actually sent** at the field a
    refusal names, so an agent need not trust a value re-parsed out of prose.
    ``None`` for an absent path, which is also what an absent field looks
    like; the message beside it says which of the two it was.
    """
    node = payload
    for segment in path.split("."):
        name, _, index = segment.partition("[")
        if not isinstance(node, Mapping):
            return None
        node = node.get(name)
        if index:
            position = index.rstrip("]")
            if not (isinstance(node, list)
                    and position.isdigit()
                    and int(position) < len(node)):
                return None
            node = node[int(position)]
    return node


def _generic(path: str) -> str:
    """``stages[0].body.duration`` as the description writes it, with ``[]``."""
    return ".".join(
        segment.split("[")[0] + "[]" if "[" in segment else segment
        for segment in path.split(".")
    )


def _accepted_in(description: Any, section: str) -> list[str]:
    """Every key one section takes: its own fields, and its sub-objects.

    The sub-objects — ``stages``, ``coupling``, ``conductor``, ``limits``,
    ``body``, ``applicability`` — are containers that no model declares, so the
    description has no field record for any (``NEEDS.md`` STEP 8 §1.3). They
    are recovered from the *section paths* of the fields inside them, which is
    still the derived description talking rather than a list written down here
    and left to rot.
    """
    prefix = f"{section}." if section else ""
    keys = {f.key for f in description.fields if f.section == section}
    keys |= {
        f.section[len(prefix):].split(".")[0].removesuffix("[]")
        for f in description.fields
        if f.section.startswith(prefix) and f.section != section
    }
    return sorted(keys)


def _payload_error(
    exc: ProblemPayloadError, payload: Any, *, system_name: str = SYSTEM_NAME
) -> mcp_types.CallToolResult:
    """A refusal an agent can repair from, without a second call.

    ``field`` is the path the boundary named — every message in ``problem.py``
    begins with it. ``received`` is read back out of the caller's **own
    payload** at that path, and ``expected`` out of the **registry-derived**
    description, so neither is reconstructed from the message prose. The
    message itself is carried verbatim beside them.
    """
    message = str(exc)
    field = message.split(" ", 1)[0].rstrip(":,")
    description = system(system_name).description()
    try:
        expected: dict[str, Any] = description.field(_generic(field)).to_dict()
    except KeyError:
        # No such field: either an unknown key, or a structural path such as
        # `stages` that names a container rather than a value. Say which keys
        # its section does take — the registry knows, so this is not a guess.
        generic = _generic(field)
        section = generic.rsplit(".", 1)[0] if "." in generic else ""
        expected = {"accepted_keys": _accepted_in(description, section)}
    structured = json.loads(json.dumps({
        "error": type(exc).__name__,
        "field": field,
        "received": _walk(payload, field),
        "expected": expected,
        "repair": _REPAIR[type(exc)],
        # Verbatim. The boundary already says what was wrong, in its own
        # words; nothing about it is restated or summarised here.
        "message": message,
    }, default=str))
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text", text=json.dumps(structured, indent=2)
        )],
        structuredContent=structured,
        isError=True,
    )


def _battery_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The whole marched run, as JSON. Every value transported, none computed.

    ``march`` is its own field and is **not** a coupling record. The march is
    one-way: the cell heats itself and the body carries the temperature into
    the next step, and nothing iterates to convergence. ``CouplingEvidence``
    describes a fixed point -- iterations against a budget, an iterate change
    against a tolerance -- and every one of those numbers would have to be
    invented here. So the report carries no coupling record and the march's
    own outcome travels beside it, verbatim.
    """
    case = run_battery_case(payload)
    run = case.run
    return {
        "schema": BATTERY_RESPONSE_SCHEMA,
        "system": "battery",
        "march": {
            "coupling": run.coupling.value,
            "outcome": run.outcome.value,
            "steps_run": len(run.steps),
            "elapsed": str(run.final.elapsed),
            # Where a model first left its domain, if one did. UNKNOWN is not
            # a violation and is deliberately not reported here as one.
            "first_step_outside": {
                model_id: (
                    None
                    if run.first_step_outside(model_id) is None
                    else run.first_step_outside(model_id).index
                )
                # The MARCH's models, not the report's. The report also
                # carries the lumped model, which the march does not assess
                # per step -- asking it for a step verdict is a loud failure
                # by design, and rightly so.
                for model_id in sorted(run.steps[0].validity)
            },
        },
        "verdict": _verdict_block(case.report),
        # Verbatim: values with units, per-model validity with its
        # satisfied/violated/unknown condition names, every validation check
        # including NOT_RUN, provenance, and the caller's own declarations
        # under their `caller_asserted` marking.
        "report": case.report.to_dict(),
    }


def run_battery(case: dict[str, Any]) -> dict[str, Any]:
    """Run one battery case and return its credibility evidence report.

    The same contract as :func:`run_electrothermal`: the success payload is
    what the annotation describes, and a refused payload comes back as a
    ``CallToolResult`` carrying ``is_error`` and structured content.
    """
    try:
        return _battery_response(case)
    except ProblemPayloadError as exc:
        return _payload_error(exc, case, system_name="battery")


def run_electrothermal(case: dict[str, Any]) -> dict[str, Any]:
    """Run one case and return its credibility evidence report.

    The annotation describes the **success** payload, which is what the SDK
    turns into the tool's output schema. A refused payload returns a
    ``CallToolResult`` instead — the protocol-level record that carries
    ``is_error`` *and* structured content, which a raised ``ToolError`` cannot.
    Widening the annotation to a union is not the fix: the SDK rejects
    ``CallToolResult`` inside one at registration, precisely so the output
    schema keeps describing the success case.
    """
    try:
        return _response(case)
    except ProblemPayloadError as exc:
        return _payload_error(exc, case)


def compile_engineering_problem(
    description: str,
    declarations: dict[str, Any] | None = None,
    system_name: str | None = None,
) -> dict[str, Any]:
    """Route and compile controlled engineering prose into a reviewed case."""
    plan = plan_engineering_intent(description)
    selected = system_name or plan["selected_system"]
    if selected is None:
        return {
            "schema": "engineering_compilation/1",
            "status": "needs_system",
            "plan": plan,
            "intent": None,
        }
    intent = compile_engineering_intent(
        description, declarations, system_name=selected
    )
    intent["selection"] = {
        "source": "explicit" if system_name else "deterministic_router",
        "plan": plan,
    }
    return intent


def plan_engineering_problem(description: str) -> dict[str, Any]:
    """Route prose to a supported system without making a scientific claim."""
    return plan_engineering_intent(description)


def run_engineering_problem(
    description: str,
    declarations: dict[str, Any] | None = None,
    system_name: str | None = None,
) -> dict[str, Any]:
    """Compile prose and run only when every required declaration exists."""
    intent = compile_engineering_problem(description, declarations, system_name)
    if intent["status"] == "needs_system":
        return {
            "schema": "engineering_run/1",
            "status": "needs_system",
            "intent": intent,
            "result": None,
        }
    if intent["status"] != "ready":
        return {
            "schema": "engineering_run/1",
            "status": intent["status"],
            "intent": intent,
            "result": None,
        }
    return {
        "schema": "engineering_run/1",
        "status": "completed",
        "intent": intent,
        "result": (
            _response(intent["case"])
            if intent["system"] == "electrothermal"
            else _battery_response(intent["case"])
        ),
    }


def answer_engineering_problem(
    description: str,
    declarations: dict[str, Any] | None = None,
    system_name: str | None = None,
) -> dict[str, Any]:
    """Return an engineering-facing view while retaining the raw evidence."""
    return summarize_engineering_run(
        run_engineering_problem(description, declarations, system_name)
    )


def answer_engineering_scenarios(
    description: str,
    scenarios: list[dict[str, Any]],
    declarations: dict[str, Any] | None = None,
    system_name: str | None = None,
) -> dict[str, Any]:
    """Run caller-declared scenarios and return a non-probabilistic envelope."""
    if not isinstance(scenarios, list) or not 2 <= len(scenarios) <= 100:
        raise ValueError("scenarios must contain between 2 and 100 entries")
    base = dict(declarations or {})
    ids = []
    answers = []
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, Mapping):
            raise TypeError(f"scenarios[{index}] must be an object")
        scenario_id = str(scenario.get("scenario_id", "")).strip()
        overrides = scenario.get("declarations")
        if not scenario_id:
            raise ValueError(f"scenarios[{index}].scenario_id must be non-empty")
        if not isinstance(overrides, Mapping):
            raise TypeError(f"scenarios[{index}].declarations must be an object")
        merged = {**base, **dict(overrides)}
        ids.append(scenario_id)
        answers.append(answer_engineering_problem(
            description, merged, system_name
        ))
    return {
        "schema": "engineering_scenario_answer/1",
        "status": "completed" if all(
            answer["status"] == "completed" for answer in answers
        ) else "incomplete",
        "uncertainty": scenario_envelope(answers, scenario_ids=ids),
        "scenarios": [
            {"scenario_id": scenario_id, "answer": answer}
            for scenario_id, answer in zip(ids, answers)
        ],
    }


def evaluate_engineering_context(
    description: str,
    criteria: list[dict[str, Any]],
    declarations: dict[str, Any] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    system_name: str | None = None,
) -> dict[str, Any]:
    """Evaluate caller-declared decision criteria against point or scenario results."""
    if scenarios:
        scenario_answer = answer_engineering_scenarios(
            description, scenarios, declarations, system_name
        )
        first = scenario_answer["scenarios"][0]["answer"]
        evaluation = evaluate_context(
            first, criteria, uncertainty=scenario_answer["uncertainty"]
        )
        return {**evaluation, "engineering": scenario_answer}
    answer = answer_engineering_problem(description, declarations, system_name)
    return {**evaluate_context(answer, criteria), "engineering": answer}


def answer_engineering_uncertainty(
    description: str,
    uncertain_inputs: list[dict[str, Any]],
    dependence: str,
    declarations: dict[str, Any] | None = None,
    system_name: str | None = None,
    sample_count: int = 32,
    credible_mass: float = 0.95,
) -> dict[str, Any]:
    """Propagate caller-declared independent distributions, fail closed."""
    samples = build_deterministic_samples(
        uncertain_inputs, sample_count=sample_count, dependence=dependence
    )
    base = dict(declarations or {})
    answers = [
        answer_engineering_problem(
            description, {**base, **sample}, system_name
        )
        for sample in samples
    ]
    incomplete = [
        index for index, answer in enumerate(answers)
        if answer["status"] != "completed"
    ]
    uq = (
        {
            "schema": "engineering_probabilistic_uq/1",
            "status": "incomplete",
            "sample_count": len(samples),
            "incomplete_sample_indices": incomplete,
            "intervals": [],
        }
        if incomplete else predictive_intervals(answers, credible_mass=credible_mass)
    )
    return {
        "schema": "engineering_uncertainty_answer/1",
        "status": uq["status"],
        "dependence": dependence,
        "declared_inputs": uncertain_inputs,
        "uncertainty": uq,
        "samples": [
            {
                "sample_index": index,
                "declarations": sample,
                "answer": answer,
            }
            for index, (sample, answer) in enumerate(zip(samples, answers))
        ],
    }


# =====================================================================
# The server
# =====================================================================

_DESCRIBE_DESCRIPTION = """\
What this runtime can be asked, and what it will refuse. Call this first.

Returns one entry per system -- currently electrothermal and battery, each \
naming the tool that runs it. For each: every field a case may contain, \
whether it is required, the physical dimension it must carry and an example \
unit; for each optional field, the validity conditions it unlocks (omitting it \
is never an error, but the conditions it would have decided then report \
UNKNOWN); the model inputs you may NOT supply, because the coupling solves for \
them; a complete runnable example case; and what each of the three verdicts \
means and does not mean.

Every field fact is read from the model registries at call time, so this \
description cannot drift from what the run tools will accept, and a system \
added to this runtime appears here without this text being edited.

Two rules worth knowing before you write a case. Every physical value is a \
string carrying a unit -- "10 ohm", never 10 -- because this boundary will not \
choose a unit on your behalf. And an unrecognised key is refused, not ignored: \
a misspelling would otherwise present as a declaration you never made, and \
would silently turn a condition you meant to satisfy into an UNKNOWN one.

Takes no arguments."""

_RUN_DESCRIPTION = """\
Run one electro-thermal case and return its credibility evidence report.

Solves a DC series circuit of temperature-dependent resistors coupled to \
first-order lumped thermal bodies, iterating to a quasi-static end-of-interval \
fixed point, and returns one report per stage. Quasi-static means each body is \
integrated over its declared duration with the dissipation at R(T_final), the \
resistance of its end-of-interval temperature, held constant across the whole \
interval: the real resistance moves from R(T_0) to R(T_final) and that \
transient is approximated, not resolved. Declaring \
stages[].conductor.element.resistance_variation_budget lets the element record \
check how far R moved against what you accept. A stage that omits this element \
evidence now carries a NOT_RUN validation check and cannot be SUPPORTED. The \
body also accepts capacity_evidence (bulk_density, bulk_specific_heat and an \
explicit extra_heat_capacity) and verifies heat_capacity = rho*c_p*V + C_extra; \
omitting the basis likewise fails closed as INSUFFICIENT_EVIDENCE. Each report carries: the values with units, each model's validity (status plus \
the satisfied, violated and UNKNOWN condition names), every validation check \
with its outcome and what it established -- including checks that did NOT run \
-- the coupling outcome as its own field, full provenance, and anything you \
asserted, marked caller_asserted. Your applicability declaration is what the \
thermal validity conditions are computed from, so its values decide the \
verdict, and the record says so: consumed_by_verdict is true.

Each stage carries a verdict of SUPPORTED, INSUFFICIENT_EVIDENCE or \
NOT_SUPPORTED, with verdict_reasons naming the specific condition, check or \
gap that produced it. NOT_SUPPORTED means a bound was violated or a check \
failed: change the design, because more evidence will not help. \
INSUFFICIENT_EVIDENCE means something was never produced, and verdict_reasons \
says what to declare. NOT_SUPPORTED outranks INSUFFICIENT_EVIDENCE, so a \
NOT_SUPPORTED report may carry gaps too, under other_findings.

A fully declared nominal case can be SUPPORTED: the example_case in \
describe_capabilities is. Expect INSUFFICIENT_EVIDENCE whenever a condition \
cannot be decided, and verdict_reasons names it -- a resistor's ratings \
(stages[].conductor.ratings), the source's current limit (source_ratings), the \
element data (stages[].conductor.element), the body's applicability fields, or \
material limits (stages[].conductor.limits) whose Debye-temperature floor is \
elemental-metal physics and stays UNKNOWN for a film, an alloy or a \
semiconductor. That is the runtime's real answer, it is transmitted unchanged, \
and it is neither an error nor a reason to retry.

The verdict is advisory input to an engineer of record. It is not a decision, \
not a certification, and not a claim of conformance with any standard.

Pass the case as the `case` argument, shaped like the example_case in \
describe_capabilities. A malformed case comes back as an error naming the \
field, what you sent, what was expected and how to repair it -- fix that one \
field and call again."""


_ASSESS_CLAIM_DESCRIPTION = """Assess one structured scientific claim for one declared decision.

The request must explicitly name a registered system, its case payload, the
reported quantity to assess, the terminal decision statement, one or more
required ValidationLevels, and a model-discrepancy declaration.

This tool does not infer a scientific question from prose, select a model,
choose a report when a system returns several, or invent a confidence target.
It executes the existing system boundary and carries its credibility report
through SRIA evidence and assurance.

The result contains BOTH the production credibility verdict and the assurance
verdict. A validation level cannot hide a NOT_SUPPORTED or
INSUFFICIENT_EVIDENCE credibility report: the credibility critic itself is a
required assurance critic.

This is scientific decision support, not safety certification and not an
automatic real-world decision."""

_RUN_BATTERY_DESCRIPTION = """\
Run one battery case and return its credibility evidence report.

Marches one equivalent-circuit cell through a constant-current discharge, \
letting its own I^2 R dissipation heat a lumped thermal body and carrying the \
new temperature into the next step. Returns the values with units, each \
model's validity (status plus the satisfied, violated and UNKNOWN condition \
names), every validation check with its outcome including checks that did NOT \
run, full provenance, and your own declarations marked caller_asserted. The \
cell limits and the load you declare are what the battery validity conditions \
are computed from, so their values decide the verdict, and each record says \
so: consumed_by_verdict is true.

Four battery models are assessed independently and are meant to be able to \
disagree: a cell whose terminal voltage the Rint circuit describes badly may \
still have its charge counted correctly. Their verdicts are taken OVER each \
step, not at the instant it began, so a step that starts inside a temperature \
limit and ends outside it is reported as outside.

THE COUPLING IS ONE-WAY. The march does not iterate to a fixed point, so \
there is no convergence to report and no coupling record; the march reports \
its own outcome -- horizon_reached, cutoff_reached, validity_lost -- in its \
own field, with the step at which each model first left its domain.

`load.duration` is the length of ONE STEP, not the horizon. The discharge \
lasts duration * steps, so raising the step count lengthens the run.

`cell.limits.cell_thermal_conductance` is required for a coupled run even \
though the models mark it optional: it is both the conductance the \
self-heating condition is stated over and the one the body exchanges \
through, and this runtime will not invent a second source for it.

The thermal body's applicability is part of this payload under \
thermal.applicability. A fully declared nominal case can therefore reach \
SUPPORTED when the battery and thermal models are in-domain and the report's \
validation checks earn evidence. Omitting thermal applicability remains \
backward-compatible and yields the honest UNKNOWN/INSUFFICIENT_EVIDENCE path; \
the runtime never fills those scientific declarations with defaults.

The verdict is advisory input to an engineer of record. It is not a decision, \
not a certification, and not a claim of conformance with any standard.

Pass the case as the `case` argument, shaped like the battery system's \
example_case in describe_capabilities. A malformed case comes back as an \
error naming the field, what you sent, what was expected and how to repair \
it -- fix that one field and call again."""


def assess_claim(request: dict[str, Any]) -> dict[str, Any]:
    """Public structured claim-assessment boundary.

    Expected scientific refusals are returned as data. Unexpected programming
    errors still raise: a transport must not turn an implementation defect
    into an innocent-looking INSUFFICIENT_EVIDENCE answer.
    """
    try:
        return assess_claim_request(request)
    except (ClaimAssessmentError, ProblemPayloadError) as exc:
        return refused_claim_assessment(exc)


_ASSESS_SCIENTIFIC_CLAIM_DESCRIPTION = """Assess one structured scientific claim WITHOUT naming a system.

Pass a `scientific_claim/1` record as `claim`. It states the quantity of
interest and its units, a THRESHOLD (<, <=, >, >=) or TOLERANCE_BAND (==
with a tolerance) comparison, the target, the operating context and known
inputs (keyed by the capability's input paths), inputs you know are unknown,
your assumptions, the decision, the required ValidationLevels, the
uncertainty demand, and an explicit model-discrepancy declaration (UNKNOWN is
allowed and is never read as zero). Every field is required; unknown fields
are refused, not ignored.

The runtime routes the claim by declared capabilities -- never by words --
selects a model only if its applicability can be assessed, plans the run,
executes it, and derives the verdict from the credibility report and the
SRIA assurance decision:

  SUPPORTED              admissible evidence satisfies the comparison
  CONTRADICTED           admissible evidence violates it -- the same bar
  INSUFFICIENT_EVIDENCE  anything else: not ready, outside validity, a run
                         that is not credible, a missing level, an UNKNOWN
                         demanded uncertainty, or a band straddling the bound

A model outside its validity domain NEVER makes a claim CONTRADICTED: it
shows only that this execution cannot bear on it. When the claim cannot run,
the answer says why (NEEDS_INPUT, AMBIGUOUS, UNSUPPORTED_CAPABILITY, REFUSED)
and lists repair actions read from the declarations. Every explanation item
points into the record it explains.

The verdict is advisory input to an engineer of record. It is not a decision,
not a certification, and not a claim of conformance with any standard."""


def describe_external_evidence() -> dict[str, Any]:
    """Production-curated measurement/literature records and their trust identity.

    A listed record is curated, not automatically applicable.  The claim
    assessment still checks quantity, dimension, operating conditions and
    uncertainty before the record can bear on a result.
    """
    from ..claims.external_evidence import (
        PRODUCTION_EXTERNAL_RECORDS,
        PRODUCTION_EXTERNAL_REGISTRY,
        MeasurementRecord,
    )

    return {
        "registry_digest": PRODUCTION_EXTERNAL_REGISTRY.digest,
        "records": [
            {
                "source_class": (
                    "measurement" if isinstance(record, MeasurementRecord) else "literature"
                ),
                "record_digest": record.digest,
                "record": record.to_dict(),
            }
            for record in PRODUCTION_EXTERNAL_RECORDS
        ],
        "rule": (
            "curation is not applicability and never awards a validation level; "
            "pass only records that describe the subject/operating point being assessed"
        ),
    }


def describe_empirical_uq() -> dict[str, Any]:
    """Describe the empirical-UQ admission, available data and trust blockers."""
    from ..claims.aleatoric_uq import estimate_aleatoric_replicates
    from ..claims.empirical_uq_trust import (
        PRODUCTION_EMPIRICAL_OBSERVATIONS,
        PRODUCTION_EMPIRICAL_RECORDS,
    )
    from ..claims.model_form_trust import PRODUCTION_MODEL_FORM_QUALIFICATIONS
    from ..claims.parameter_uq import (
        TOLERANCE_CONFIDENCE,
        TOLERANCE_CONTENT,
        minimum_samples,
    )

    by_context: dict[tuple[str, str], set[str]] = {}
    for item in PRODUCTION_EMPIRICAL_RECORDS:
        context = (
            str(item.conditions.get("load.state_of_charge")),
            str(item.conditions.get("load.cell_temperature")),
        )
        by_context.setdefault(context, set()).add(item.independence_group)
    max_replicates = max((len(groups) for groups in by_context.values()), default=0)
    required_replicates = minimum_samples(
        TOLERANCE_CONTENT, TOLERANCE_CONFIDENCE
    )
    split_counts = {
        "calibration": sum(
            item.split.value == "calibration"
            for item in PRODUCTION_EMPIRICAL_RECORDS
        ),
        "validation": sum(
            item.split.value == "validation"
            for item in PRODUCTION_EMPIRICAL_RECORDS
        ),
    }

    return {
        "empirical_observation_registry_digest":
            PRODUCTION_EMPIRICAL_OBSERVATIONS.digest,
        "empirical_observation_pin_count":
            len(PRODUCTION_EMPIRICAL_OBSERVATIONS.pins),
        "empirical_records": [
            {
                "observation_id": item.observation_id,
                "digest": item.digest,
                "split": item.split.value,
                "independence_group": item.independence_group,
                "quantity": item.quantity,
                "conditions": {
                    name: value.to_dict()
                    for name, value in item.conditions.items()
                },
                "uncertainty": item.uncertainty.to_dict(),
            }
            for item in PRODUCTION_EMPIRICAL_RECORDS
        ],
        "aleatoric": {
            "engine": estimate_aleatoric_replicates.__name__,
            "source_record": "claim DatasetObservation",
            "target_content": TOLERANCE_CONTENT,
            "target_confidence": TOLERANCE_CONFIDENCE,
            "required_independent_replicates_per_exact_context":
                required_replicates,
            "maximum_current_pinned_replicates_per_exact_context":
                max_replicates,
            "production_ready": max_replicates >= required_replicates,
            "blocker": (
                None
                if max_replicates >= required_replicates
                else (
                    f"only {max_replicates} exact-context independent physical "
                    f"replicates are pinned; {required_replicates} are required "
                    "for the declared two-sided 95/95 Wilks interval"
                )
            ),
            "missing_evidence_semantics": "UNKNOWN, never zero",
        },
        "model_form": {
            "source_record": "claim DatasetObservation",
            "split_counts": split_counts,
            "independence_groups": sorted(
                {item.independence_group for item in PRODUCTION_EMPIRICAL_RECORDS}
            ),
            "production_qualification_registry_digest":
                PRODUCTION_MODEL_FORM_QUALIFICATIONS.digest,
            "production_qualification_pin_count":
                len(PRODUCTION_MODEL_FORM_QUALIFICATIONS.pins),
            "production_ready":
                bool(PRODUCTION_MODEL_FORM_QUALIFICATIONS.pins),
            "blocker": (
                None
                if PRODUCTION_MODEL_FORM_QUALIFICATIONS.pins
                else (
                    "curated calibration/validation observations now exist, but "
                    "no independently reviewed model-form producer qualification "
                    "is repository-pinned; discrepancy evidence cannot authorize "
                    "its own promotion"
                )
            ),
            "missing_evidence_semantics": "UNKNOWN, never zero",
        },
        "notice": (
            "Empirical study engines are implemented and replay-verifiable. "
            "Production capability declarations advertise a channel as quantified "
            "only after its evidence/trust prerequisites are actually satisfied."
        ),
    }

def assess_scientific_claim(
    claim: dict[str, Any],
    external: list[dict[str, Any]] | None = None,
    empirical_observations: list[dict[str, Any]] | None = None,
    model_form_qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generic claim assessment: route, plan, execute, add offered curated evidence and assure.

    ``external`` accepts measurement/literature records such as those returned
    by :func:`describe_external_evidence`.  They are never trusted by being
    passed: the production trust registry and the ordinary applicability/
    uncertainty gates decide their standing.

    ``empirical_observations`` accepts serialized DatasetObservation records
    for ALEATORIC and MODEL_FORM studies. ``model_form_qualification`` may
    carry a ProducerQualification, but it can authorize promotion only when its
    content digest is pinned by the repository-owned production qualification
    registry. Missing empirical evidence stays UNKNOWN.

    Every expected outcome -- a malformed claim, a missing input, an
    unsupported capability, an insufficient verdict -- is returned as a
    record. An unexpected exception is a defect and is not caught.
    """
    from ..claims.assessment import assess_claim as assess
    from ..claims.external_evidence import (
        PRODUCTION_EXTERNAL_REGISTRY,
        read_external_record,
    )
    from ..claims.measurement_dataset import DatasetObservation
    from ..uq.model_form.qualification import ProducerQualification
    from .capabilities import production_registry

    offered = []
    for item in external or ():
        raw = item.get("record", item) if isinstance(item, dict) else item
        offered.append(read_external_record(raw))

    empirical = tuple(
        DatasetObservation.from_dict(item)
        for item in (empirical_observations or ())
    )
    qualification = (
        None
        if model_form_qualification is None
        else ProducerQualification.from_dict(model_form_qualification)
    )

    return assess(
        claim,
        production_registry(),
        external=tuple(offered),
        empirical_observations=empirical,
        model_form_qualification=qualification,
        trust=PRODUCTION_EXTERNAL_REGISTRY,
    ).to_dict()


def describe_product() -> dict[str, Any]:
    """Product discovery surface derived from the production capability registry."""
    from .capabilities import production_registry

    return _describe_product(production_registry())


def prepare_simulation(
    text: str,
    proposal: dict[str, Any],
    spans: dict[str, list[int]],
) -> dict[str, Any]:
    """Ground and compile an LLM-proposed simulation without executing physics."""
    from .capabilities import production_registry

    try:
        return _prepare_simulation(text, proposal, spans, production_registry())
    except ProductRequestError as exc:
        return {
            "error": type(exc).__name__,
            "message": str(exc),
            "status": "refused",
        }


def run_simulation(
    claim: dict[str, Any],
    external: list[dict[str, Any]] | None = None,
    empirical_observations: list[dict[str, Any]] | None = None,
    model_form_qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a structured product claim through the production scientific runtime."""
    from .capabilities import production_registry

    return _run_simulation(
        claim,
        production_registry(),
        external=external or (),
        empirical_observations=empirical_observations or (),
        model_form_qualification=model_form_qualification,
    )


def run_proposed_simulation(
    text: str,
    proposal: dict[str, Any],
    spans: dict[str, list[int]],
    external: list[dict[str, Any]] | None = None,
    empirical_observations: list[dict[str, Any]] | None = None,
    model_form_qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ground an LLM proposal and execute it only when the compiler says READY."""
    from .capabilities import production_registry

    try:
        return _run_proposed_simulation(
            text,
            proposal,
            spans,
            production_registry(),
            external=external or (),
            empirical_observations=empirical_observations or (),
            model_form_qualification=model_form_qualification,
        )
    except ProductRequestError as exc:
        return {
            "error": type(exc).__name__,
            "message": str(exc),
            "status": "refused",
        }


_PRODUCT_DESCRIBE_DESCRIPTION = """Discover Forge's product-facing scientific capabilities.

Returns the executable production capabilities, quantities, inputs, evidence
routes, uncertainty channels and the explicit LLM authority boundary. The
result is derived from the same capability registry used for execution."""


_PRODUCT_PREPARE_DESCRIPTION = """Prepare a simulation proposed by an LLM without running physics.

Pass the user's exact text, the provider's structured scientific-claim
proposal, and source spans for every physical value. Values not grounded in the
user text are moved to missing inputs. Authority fields are refused. The
deterministic compiler returns READY, NEEDS_INPUT, AMBIGUOUS,
UNSUPPORTED_CAPABILITY or REFUSED."""


_PRODUCT_RUN_DESCRIPTION = """Run one structured scientific claim through the Forge product gateway.

The production registry routes, plans, executes and assesses the claim. The
response contains a compact UI/API view and the complete canonical assessment
record. The language model does not choose the verdict."""


_PRODUCT_RUN_PROPOSED_DESCRIPTION = """Run the end-to-end product flow from an LLM proposal.

Forge first grounds the proposal in the user's text and compiles it. Physics is
executed only when the deterministic compiler returns READY. A non-ready
proposal returns its missing inputs, ambiguity or refusal and never runs."""


_COMPILE_INTENT_DESCRIPTION = """\
Route and compile a controlled Arabic or English engineering description.

Returns values extracted from the user's words with their text spans, every \
missing required declaration as a concrete question with its dimension and \
example unit, and a runnable case only when the description is complete. No \
physical value is guessed or copied from an example. Use `declarations` to \
answer questions by exact dotted path. Pass `system_name` to make the system \
explicit; otherwise deterministic routing must find one unambiguous match."""


_PLAN_INTENT_DESCRIPTION = """\
Route an Arabic or English engineering description to a supported system.

Selection is deterministic and reports the exact matched terms and all
candidates. Ambiguous or generic prose returns `needs_system` instead of
guessing. Selection establishes no model applicability, adequacy, solver
compatibility or scientific validity."""


_RUN_INTENT_DESCRIPTION = """\
Route, compile and run a controlled Arabic or English engineering description.

If declarations are missing, returns `needs_input` and explicit questions; no \
simulation runs. If complete, the case passes through the ordinary \
deterministic boundary and returns the unchanged validity, validation, \
uncertainty, provenance and advisory evidence verdict."""


_ANSWER_DESCRIPTION = """\
Route, compile, run and present an engineering problem.

Returns one engineer-facing result per component with values, the unchanged
advisory verdict, per-model applicability boundaries and exclusions, explicit
uncertainty status, validation evidence and provenance. If predictive
uncertainty was not quantified, it says `not_quantified`; absence is never
reported as zero uncertainty. The complete execution response remains attached
verbatim for audit. Incomplete intent returns questions and runs nothing."""


_SCENARIO_DESCRIPTION = """\
Run between 2 and 100 caller-declared input scenarios and report output bounds.

Each scenario supplies an id and declaration overrides on a common base. Every
scenario passes through the normal planning, unit, validity, validation and
evidence path. Output bounds are a declared-scenario envelope with no
probability model and no confidence level; Forge does not invent distributions.
The response states what the envelope excludes and retains every scenario's
complete engineering answer and verdict."""


_CONTEXT_DESCRIPTION = """\
Evaluate explicit engineering decision criteria against a point result or a
declared scenario envelope. Each criterion names a subject, output quantity,
operator (`<=` or `>=`) and unit-bearing threshold. Numerical satisfaction is
kept separate from evidence status: a value may meet its threshold while the
decision remains `indeterminate_evidence` because validity or evidence is
insufficient. Scenario bounds that straddle a threshold produce
`indeterminate_uncertainty`. The result is advisory, never certification."""


_PROBABILISTIC_UQ_DESCRIPTION = """\
Propagate caller-declared uniform or normal input distributions through an
engineering system using deterministic stratified Latin-hypercube samples.

The caller must explicitly declare `dependence="independent"`; this version
refuses correlated inputs rather than silently ignoring correlation. Every
equal-mass sample passes through normal validity, validation and evidence. If
any sample is not SUPPORTED, the tool returns
`predictive_support_not_admitted` with no intervals, refusing silent
conditioning. Successful output includes empirical central intervals, mean and
standard uncertainty, and explicitly excludes model-form uncertainty."""


def build_server() -> MCPServer:
    """The server with product, system and canonical planning tools registered."""
    server = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions=(
            "A scientific simulation runtime that reports the credibility of "
            "its own results. Product clients should call describe_product, "
            "then prepare_simulation or run_proposed_simulation. Engineering "
            "planning accepts only canonical EngineeringIntent records through "
            "plan_canonical_engineering_intent; natural-language interpretation "
            "belongs outside MCP. Language models may propose structured records "
            "but never supply model, solver, graph, evidence or verdict authority. "
            "Lower-level callers can still use describe_capabilities, direct "
            "system tools and assess_claim. Verdicts remain decision support, "
            "not certification."
        ),
    )
    server.add_tool(
        describe_capabilities,
        name="describe_capabilities",
        title="Describe what this runtime accepts",
        description=_DESCRIBE_DESCRIPTION,
    )
    server.add_tool(
        run_electrothermal,
        name="run_electrothermal",
        title="Run an electro-thermal case",
        description=_RUN_DESCRIPTION,
    )
    server.add_tool(
        run_battery,
        name="run_battery",
        title="Run a battery discharge case",
        description=_RUN_BATTERY_DESCRIPTION,
    )
    server.add_tool(
        assess_claim,
        name="assess_claim",
        title="Assess a structured scientific claim",
        description=_ASSESS_CLAIM_DESCRIPTION,
    )
    server.add_tool(
        describe_external_evidence,
        name="describe_external_evidence",
        title="Describe curated production evidence",
        description=(
            "List repository-curated measurement and literature records, their "
            "content digests and the production trust-registry identity. A listed "
            "record is still checked for applicability when used."
        ),
    )
    server.add_tool(
        describe_empirical_uq,
        name="describe_empirical_uq",
        title="Describe empirical uncertainty requirements",
        description=(
            "Describe the fail-closed admission rules for ALEATORIC and "
            "MODEL_FORM uncertainty, including the production model-form "
            "qualification trust-registry identity and current pin count."
        ),
    )
    server.add_tool(
        assess_scientific_claim,
        name="assess_scientific_claim",
        title="Route, run and assess a structured scientific claim",
        description=_ASSESS_SCIENTIFIC_CLAIM_DESCRIPTION + (
            "\n\nOptional external records may be supplied from "
            "describe_external_evidence; empirical DatasetObservation records "
            "may be supplied for ALEATORIC/MODEL_FORM studies. Call "
            "describe_empirical_uq for admission and trust requirements. Passing "
            "a record never bypasses trust, applicability or uncertainty checks."
        ),
    )
    server.add_tool(
        describe_product,
        name="describe_product",
        title="Discover Forge product capabilities",
        description=_PRODUCT_DESCRIBE_DESCRIPTION,
    )
    server.add_tool(
        prepare_simulation,
        name="prepare_simulation",
        title="Prepare an LLM-proposed simulation",
        description=_PRODUCT_PREPARE_DESCRIPTION,
    )
    server.add_tool(
        run_simulation,
        name="run_simulation",
        title="Run a structured product simulation",
        description=_PRODUCT_RUN_DESCRIPTION,
    )
    server.add_tool(
        run_proposed_simulation,
        name="run_proposed_simulation",
        title="Run an LLM-proposed simulation when ready",
        description=_PRODUCT_RUN_PROPOSED_DESCRIPTION,
    )
    server.add_tool(
        plan_canonical_engineering_intent,
        name="plan_canonical_engineering_intent",
        title="Plan a canonical engineering intent",
        description=(
            "Plan a versioned typed EngineeringIntent JSON record. This tool "
            "does not accept or interpret natural language. Optional "
            "display_metadata may preserve user-language text, but it is "
            "non-authoritative and never affects scientific identity or planning."
        ),
    )
    _audit_tools(server)
    return server


def _audit_tools(server: MCPServer) -> None:
    """Every registered system has a tool, and every tool a system.

    The registry says what this runtime exposes and ``build_server`` says what
    an agent can call. A system described but not callable would have an agent
    write a case against a tool that does not exist; a tool callable but not
    described would have them guess its payload. Checked here rather than
    trusted, because adding the third system is exactly when one of the two
    gets forgotten.
    """
    registered = {tool.name for tool in server._tool_manager.list_tools()}
    expected = {boundary.tool for boundary in SYSTEMS}
    missing = sorted(expected - registered)
    if missing:
        raise RuntimeError(
            f"engcore.mcp.systems registers {missing} but this server does "
            f"not expose a tool for it; a described system an agent cannot "
            f"call is worse than one that is not described"
        )


def main() -> None:
    """stdio entry point. No network, no authentication, no persistence."""
    build_server().run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
