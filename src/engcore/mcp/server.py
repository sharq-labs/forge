"""The MCP transport: this runtime, exposed to an agent, over stdio.

A **transport and nothing else**. It computes no physics, evaluates no
condition and decides no verdict. Every fact it returns was produced by
:mod:`engcore.mcp.problem` and :mod:`engcore.mcp.evidence` and is carried here
unaltered; every field it describes is read off the model registries by
:func:`~engcore.mcp.problem.describe_electrothermal_case`, so a model input
added or re-dimensioned in a domain changes the description rather than making
it quietly false.

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
from .errors import (
    MalformedPayloadError,
    MissingFieldError,
    MissingUnitError,
    ProblemPayloadError,
    UnknownFieldError,
    WrongDimensionError,
)
from .evidence import CredibilityVerdict
from .problem import (
    build_electrothermal_system,
    describe_electrothermal_case,
    run_electrothermal_case,
)

__all__ = [
    "CAPABILITIES_SCHEMA",
    "RESPONSE_SCHEMA",
    "SERVER_NAME",
    "SERVER_VERSION",
    "SYSTEM_NAME",
    "build_server",
    "describe_capabilities",
    "main",
    "run_electrothermal",
]

SERVER_NAME = "crafty-engcore"
SERVER_VERSION = "0.4.0"
CAPABILITIES_SCHEMA = "mcp_capabilities/1"
RESPONSE_SCHEMA = "mcp_electrothermal_response/1"

#: The one system this transport exposes. Named so a second system is an
#: addition rather than a rewrite of everything below.
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


def _audit_tables() -> None:
    """Refuse to import while anything an agent could receive is undescribed.

    The discipline ``derive_verdict`` applies to an enum member it was not
    written for: a verdict or refusal class with no entry here would reach an
    agent with no explanation and no repair, which is worse than a crash.
    """
    for defined, described, what in (
        ({v.value for v in CredibilityVerdict},
         {v.value for v in _VERDICT_GUIDANCE}, "verdict"),
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

def describe_capabilities() -> dict[str, Any]:
    """Everything an agent needs to write a case, read off the registries.

    Required flags, dimensions, unit exemplars, prose and unlocked conditions
    all come from :func:`~engcore.mcp.problem.describe_electrothermal_case`,
    which reads the model records. Nothing about a field is restated here.
    """
    description = describe_electrothermal_case()
    payload = description.to_dict()
    return {
        "schema": CAPABILITIES_SCHEMA,
        "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "systems": [
            {
                "name": SYSTEM_NAME,
                "tool": "run_electrothermal",
                "summary": "A DC series circuit of temperature-dependent "
                           "resistors coupled to first-order lumped thermal "
                           "bodies, run to a fixed point. One credibility "
                           "evidence report per stage.",
                "models": payload["models"],
                "fields": payload["fields"],
                "required_fields": [f.path for f in description.required],
                "optional_fields": [f.path for f in description.optional],
                "example_case": payload["example"],
            }
        ],
        # Not fields with a rule attached — fields that do not exist. Each is
        # solved for by the coupling, and a payload asserting one would fix the
        # fixed point the run is supposed to find.
        "fields_you_may_not_supply": [
            {"model_input": name, "why": why}
            for name, why in sorted(payload["coupling_supplied_inputs"].items())
        ],
        "verdicts": [
            {"value": verdict.value, **_VERDICT_GUIDANCE[verdict]}
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
        # Never decides anything. Carried because SUPPORTED absorbs it, which
        # makes it the finding a reader is most likely to miss.
        ("check_warned", None, report.warning_checks,
         lambda v: {"warning_checks": list(v)}),
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
    return {
        "value": verdict.value,
        **_VERDICT_GUIDANCE[verdict],
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
    stages = build_electrothermal_system(payload).stages
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
            }
            for stage, report in zip(stages, case.reports)
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
    exc: ProblemPayloadError, payload: Any
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
    description = describe_electrothermal_case()
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


# =====================================================================
# The server
# =====================================================================

_DESCRIBE_DESCRIPTION = """\
What this runtime can be asked, and what it will refuse. Call this first.

Returns, for the electro-thermal system: every field a case may contain, \
whether it is required, the physical dimension it must carry and an example \
unit; for each optional field, the validity conditions it unlocks (omitting it \
is never an error, but the conditions it would have decided then report \
UNKNOWN); the model inputs you may NOT supply, because the coupling solves for \
them; a complete runnable example case; and what each of the three verdicts \
means and does not mean.

Every field fact is read from the model registries at call time, so this \
description cannot drift from what run_electrothermal will accept.

Two rules worth knowing before you write a case. Every physical value is a \
string carrying a unit -- "10 ohm", never 10 -- because this boundary will not \
choose a unit on your behalf. And an unrecognised key is refused, not ignored: \
a misspelling would otherwise present as a declaration you never made, and \
would silently turn a condition you meant to satisfy into an UNKNOWN one.

Takes no arguments."""

_RUN_DESCRIPTION = """\
Run one electro-thermal case and return its credibility evidence report.

Solves a DC series circuit of temperature-dependent resistors coupled to \
first-order lumped thermal bodies, iterating to a fixed point, and returns one \
report per stage: the values with units, each model's validity (status plus \
the satisfied, violated and UNKNOWN condition names), every validation check \
with its outcome and what it established -- including checks that did NOT run \
-- the coupling outcome as its own field, full provenance, and anything you \
asserted, marked caller_asserted and consumed by no verdict.

Each stage carries a verdict of SUPPORTED, INSUFFICIENT_EVIDENCE or \
NOT_SUPPORTED, with verdict_reasons naming the specific condition, check or \
gap that produced it. NOT_SUPPORTED means a bound was violated or a check \
failed: change the design, because more evidence will not help. \
INSUFFICIENT_EVIDENCE means something was never produced, and verdict_reasons \
says what to declare. NOT_SUPPORTED outranks INSUFFICIENT_EVIDENCE, so a \
NOT_SUPPORTED report may carry gaps too, under other_findings.

Expect INSUFFICIENT_EVIDENCE on a well-formed nominal case. The payload has no \
field for a resistor's rated dissipation or a source's current limit, and \
electrical.dc.kcl declares no validity conditions, so those models are \
honestly UNKNOWN. That is the runtime's real answer, it is transmitted \
unchanged, and it is neither an error nor a reason to retry.

The verdict is advisory input to an engineer of record. It is not a decision, \
not a certification, and not a claim of conformance with any standard.

Pass the case as the `case` argument, shaped like the example_case in \
describe_capabilities. A malformed case comes back as an error naming the \
field, what you sent, what was expected and how to repair it -- fix that one \
field and call again."""


def build_server() -> MCPServer:
    """The server, with both tools registered. Used by the tests and by main."""
    server = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions=(
            "A scientific simulation runtime that reports the credibility of "
            "its own results. Call describe_capabilities before writing a "
            "case. Verdicts are advisory input to an engineer of record, and "
            "an unflattering verdict is this runtime's real answer rather than "
            "a failure to retry."
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
    return server


def main() -> None:
    """stdio entry point. No network, no authentication, no persistence."""
    build_server().run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
