"""The credibility evidence report: what a run produced, and what it evidences.

A ``ScientificResult`` already carries values, provenance and a validation
report. What it does not carry is the answer to the question an engineer of
record actually asks — *may I rely on this?* — because that answer depends on
three independent facts the platform deliberately keeps apart:

===========================  ==================================================
was the model applicable     ``ValidityAssessment`` — carried, never recomputed
did the checks pass          ``ValidationReport`` — including what did NOT run
what produced it             ``ProvenanceRecord`` — carried unaltered
===========================  ==================================================

A :class:`CredibilityEvidenceReport` puts those three in one record, adds the
caller's own asserted context in a field that cannot be mistaken for any of
them, and derives a single advisory verdict from the lot.

What "credibility" means here, and what this project does not claim
-------------------------------------------------------------------
The word is used in the sense the verification and validation (V&V) literature
gives it — ASME V&V 10 and V&V 20 (verification and validation in
computational solid mechanics, and in computational fluid dynamics and heat
transfer), ASME V&V 40 (assessing credibility of computational modelling
through verification and validation), and NASA-STD-7009 (models and
simulations). In all of them credibility is a property of the *evidence
supporting a result in a stated context of use*, not a property of the model
and not a measure of accuracy. That is what this record reports.

* **The attained levels are an evidentiary scale, not a quality score.**
  ``ValidationLevel`` says what a passing check *established*: dimensional
  validity, numerical convergence, agreement with an analytic solution, with a
  benchmark, with another solver, with experiment. Loosely, the first few sit
  on the verification side of the V&V 10/20 distinction — did we solve the
  equations right — and the last two on the validation side — did we solve the
  right equations against the world. The correspondence is loose and is stated
  loosely on purpose: this is not a mapping the standards define, and the
  levels are attained independently rather than climbed in order, so they do
  not form a single ordinal grade the way a credibility assessment scale's
  factors are scored.

* **``INSUFFICIENT_EVIDENCE`` is the same idea as NASA-STD-7009's level 0** —
  the bottom of its credibility assessment scale, "insufficient evidence".
  Both mean the same thing: nothing here answers the question, and the fix is
  to go and produce the evidence. It is not a formal score against that
  standard's scale, which assesses eight factors separately; it is the same
  distinction applied to one report.

* **``required_levels`` is where a study states its own bar**, which is the
  move V&V 40 makes when it sets the required rigour from the model risk in
  the context of use. This layer does not compute model risk and does not know
  the context of use. It only records the bar the caller declared and reports
  whether it was met.

**No conformance is claimed.** This project is not certified, is not assessed
against any of these standards, and no standards body endorses it. The
standards are frameworks for structured human judgement; what this module does
is execute a small, explicit part of that judgement as code, so that the part
which *can* be mechanical is not left to a reader's memory. Everything the
standards ask of a person — deciding the context of use, weighing the risk,
accepting the result — is still asked of a person.

**The report is advisory input to an engineer of record, not a decision.** A
``SUPPORTED`` verdict says nothing in this record argues against relying on the
result. It does not say the result is right, and it does not discharge anyone's
professional judgement or responsibility.

**Asserted context is caller-asserted context, not evidence.** What a caller
declares about its own situation is carried verbatim, marked as the caller's
claim, and excluded from the verdict by construction — it is not a parameter
of :func:`derive_verdict`. It is in the record because a reader needs to know
what was claimed; it is fenced because a claim is not a finding.

Why validity lives here and not on the result
---------------------------------------------
``ScientificResult`` has no ``validity`` field, so today a validity assessment
travels *beside* a result and is easy to drop on the floor. Adding the field to
the core would be the better long-term fix and is written up in ``NEEDS.md``;
this layer is the consumer-side answer that needs no core change. The
consequence is stated rather than hidden: **this layer carries validity
because the result cannot**, and a report assembled without the assessments is
UNKNOWN rather than silently clean.

Why the verdict cannot be stored
--------------------------------
:attr:`CredibilityEvidenceReport.verdict` is a read-only property over
:func:`derive_verdict`. It is not a constructor parameter, so
``CredibilityEvidenceReport(verdict=...)`` is a ``TypeError`` from Python itself rather
than a rule this module has to police, and no code path anywhere can put a
verdict into a report that its contents do not produce. ``to_dict`` emits the
derived value for readers; ``from_dict`` recomputes it and refuses a payload
whose stored verdict disagrees. That is exactly the mechanism
``ValidationReport.from_dict`` already uses for ``attained_levels`` — "derived
fields in the payload are advisory; recompute and verify so a hand-edited
record cannot smuggle in an unearned validation claim" — applied one level up.

**What that guarantee is, stated exactly.** It is not tamper-proofing, and
claiming otherwise would be the kind of overstatement this layer exists to
refuse. Anyone willing to call ``object.__setattr__`` can rewrite a frozen
record anywhere in this repository — a ``ValidationCheck``'s outcome or a
``ProvenanceRecord``'s run id just as easily as anything here — and no
defence in one consumer module changes that. The guarantee is narrower and
more useful:

* **The verdict always describes the contents.** Because it is derived on
  access rather than stored, there is no stale copy to drift out of step. Tamper
  with a carried assessment and the verdict moves *with* it: the report is
  never internally inconsistent, which is the failure mode a stored field
  would have introduced.
* **A forged verdict cannot cross a serialization boundary.** A subclass can
  override the property and lie in-process, but the payload it writes is
  refused by :meth:`CredibilityEvidenceReport.from_dict` on the way back in — so the lie
  cannot be persisted, sent, or handed to a second reader.
* **No supported API expresses the lie.** Constructor, ``dataclasses.replace``
  and attribute assignment all raise; ``pickle`` and ``copy.deepcopy``
  round-trip the honest verdict.

What this module does not do
----------------------------
It computes no physics, evaluates no condition and re-runs no check. Every
scientific judgement in a report was made upstream by a model's validity
domain or a solver's validation, and is *transported* here. The only thing this
module decides is how to combine judgements already made, and it says so in one
pure function that a reader can check in full.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from ..scientific.models.definition import (
    VALIDITY_ASSESSMENT_SCHEMA,
    ValidityAssessment,
    ValidityStatus,
)
from ..scientific.results.provenance import PROVENANCE_SCHEMA, ProvenanceRecord
from ..scientific.results.result import ScientificResult
from ..scientific.results.validation import (
    CHECK_SCHEMA,
    REPORT_SCHEMA,
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity
from .errors import CredibilityEvidenceError

__all__ = [
    "ASSERTED_CONTEXT_SCHEMA",
    "EVIDENCE_PACKAGE_SCHEMA",
    "MODEL_VALIDITY_SCHEMA",
    "AssertedContext",
    "CredibilityEvidenceReport",
    "CredibilityVerdict",
    "EvidencePackage",  # deprecated alias
    "ModelValidityRecord",
    "derive_verdict",
]

MODEL_VALIDITY_SCHEMA = schema_string("mcp_model_validity_record")
ASSERTED_CONTEXT_SCHEMA = schema_string("mcp_asserted_context")
# The schema string is a **wire identifier**, not vocabulary, and it is
# deliberately not renamed with the class. A payload written before this
# rename carries ``mcp_evidence_package/1``, and ``require_schema`` compares it
# by exact equality; changing the string would reject every existing record
# while claiming to be a rename. Renaming the wire form is a version bump plus
# a reader that accepts both, which is a larger change than this one and has
# not been argued for.
EVIDENCE_PACKAGE_SCHEMA = schema_string("mcp_evidence_package")

#: Schemas a caller's asserted context may not embed. These are the record
#: types a reader — human or tool — scans for when it wants evidence, so
#: carrying one inside a declaration would put an evidence-shaped object
#: underneath the markings that say the declaration is not evidence.
#: A ``Quantity`` is deliberately absent: a declaration is mostly quantities,
#: and none of them looks like a result.
_FORBIDDEN_EMBEDDED_SCHEMAS = frozenset(
    {CHECK_SCHEMA, REPORT_SCHEMA, VALIDITY_ASSESSMENT_SCHEMA, PROVENANCE_SCHEMA}
)


def _embedded_core_schemas(value: Any) -> set[str]:
    """Core record schemas appearing anywhere in a nested payload.

    Walks the whole structure rather than checking the top level: a check
    buried three keys deep is exactly as misleading to a document scanner as
    one at the root, and rather more misleading to a human.
    """
    found: set[str] = set()
    if isinstance(value, Mapping):
        schema = value.get("schema")
        if isinstance(schema, str) and schema in _FORBIDDEN_EMBEDDED_SCHEMAS:
            found.add(schema)
        for nested in value.values():
            found |= _embedded_core_schemas(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found |= _embedded_core_schemas(nested)
    return found


class CredibilityVerdict(str, Enum):
    """What the report's own contents support. **Advisory, not a decision.**

    Three values and no more. The temptation is a richer scale — "supported
    with caveats", "probably fine" — and it is refused for the same reason the
    platform refuses a single scalar validation level: a gradient invites the
    reader to skip the evidence and act on the grade. These three each map to a
    different *action*, which is the only thing a verdict is good for:

    ``SUPPORTED``
        Nothing in this report argues against relying on the result. It does
        not say the result is right, and it does not discharge the engineer of
        record's judgement — the checks that ran, what they establish and the
        conditions that were satisfied are all carried here to be read.

    ``INSUFFICIENT_EVIDENCE``
        Something needed to answer the question was never produced. The fix is
        to go and produce it: declare the missing input, run the missing check.

    ``NOT_SUPPORTED``
        Something that *was* produced argues against the result — a bound
        known to be violated, or a check that ran and failed. The fix is to
        change the design or the model, not to gather more evidence.
    """

    SUPPORTED = "supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_SUPPORTED = "not_supported"


def derive_verdict(
    *,
    validity: Sequence["ModelValidityRecord"],
    validation: Sequence[ValidationCheck],
    unassessed_models: Sequence[tuple[str, str]] = (),
    required_levels: Sequence[ValidationLevel] = (),
) -> CredibilityVerdict:
    """The one place a verdict is decided. Pure, total, and order-independent.

    A function of two sequences rather than of a report, so it can be read,
    tested and argued with on its own, and so no attribute of a report other
    than these two can ever influence the answer. In particular the caller's
    ``declarations`` are not a parameter: they cannot move a verdict because
    they are not in scope of the function that decides one.

    **The rules.**

    ``NOT_SUPPORTED``
        any model validity is ``OUTSIDE_VALIDATED_DOMAIN``, or any check's
        outcome is ``FAIL``.

    ``INSUFFICIENT_EVIDENCE``
        any model validity is ``UNKNOWN``; or any check's outcome is
        ``NOT_RUN``; or a model that took part in the run was never assessed
        (``unassessed_models``); or **no check both passed and established an
        evidentiary level**; or a level the caller declared it needs
        (``required_levels``) was not attained; or there are no validity
        records at all.

    ``SUPPORTED``
        everything else.

    **Precedence: NOT_SUPPORTED wins over INSUFFICIENT_EVIDENCE**, and the
    order matters because both frequently apply at once — a body outside its
    Biot bound is also, very often, one whose emissivity nobody declared.

    The justification is that the two verdicts recommend opposite actions. A
    design known to violate a bound is not merely under-evidenced: gathering
    the missing declaration cannot rescue it, because the evidence already in
    hand says the model does not apply. Reporting INSUFFICIENT_EVIDENCE there
    would send a reader off to collect inputs for a question that has already
    been answered against them — and would let a caller *bury* a violated bound
    by omitting an unrelated input, which is precisely the substitution this
    report exists to prevent. A violation is a finding; an omission is a gap;
    a finding outranks a gap.

    **Empty is not clean.** No checks means nothing was verified, and no
    validity records means nobody asked whether the model applied. Both are
    ``INSUFFICIENT_EVIDENCE``, because the alternative is that an empty report
    reports ``SUPPORTED`` — the exact failure the ``NOT_RUN`` outcome exists to
    prevent, reintroduced one level up.

    **WARNING is not a failure and does not change the verdict.** A check that
    ran and returned ``WARNING`` produced its evidence; the platform's own
    ``ValidationReport.status`` ranks it below ``FAIL`` for that reason. It
    stays fully visible in :attr:`CredibilityEvidenceReport.validation`, and in
    :attr:`CredibilityEvidenceReport.warning_checks`, for the reader who must weigh it.
    Folding it into the verdict would either overstate it (as
    ``NOT_SUPPORTED``) or invent a fourth value.

    **SUPPORTED requires at least one attained level, and this mirrors
    NOT_RUN.** The platform already refuses to read a check that did not run as
    a check that passed: ``NOT_RUN`` is a distinct outcome precisely because
    *absence of a result is not a result*. The same thing is true one level up.
    A passing check that establishes nothing has produced no evidence for
    anything — it has only failed to object — and a report assembled entirely
    from such checks says nothing at all about the result. Reporting that as
    ``SUPPORTED`` would reintroduce, at the level of the report, exactly the
    substitution ``NOT_RUN`` exists to prevent: absence of an objection read as
    the presence of support.

    So the guard is evidential rather than numeric. It is not "are there any
    checks" but "did any check both pass and establish a level", which reuses
    the core's own definition — :attr:`ValidationReport.attained_levels` — of
    what counts. An empty check list and a check list that attains nothing are
    the same answer to the same question, and get the same verdict.

    **This is a real narrowing, and it is meant to be.** When the rule landed,
    two solvers in this repository produced a fully successful report whose
    ``attained_levels`` was empty — the lumped thermal solver, which declined a
    level for its residual check on the grounds that self-consistency is not
    verification, and the resistance property solver, whose only check is an
    admissibility bound. Reports built on either became
    ``INSUFFICIENT_EVIDENCE``. That was the honest reading: those solvers were
    right that they had earned nothing, and the verdict should say so rather
    than round it up.

    The lumped solver has since earned one, and how it did is the intended
    response to this rule rather than an escape from it. It did not relabel the
    residual check; it acquired a second check with an independent reference
    behind it (``domains/thermal_models/lumped_reference.py``), and the residual
    check still establishes nothing. The rule is satisfied by new evidence
    existing, which is the only way it is meant to be satisfiable. The
    resistance property solver still attains nothing, and what it would need is
    recorded in ``NEEDS.md`` as a visible gap.

    ``required_levels`` is unchanged and remains the way a caller demands a
    *particular* level rather than merely some level.

    **Fails closed on anything it does not recognise.** The three rules are
    total over today's enum members, but totality here is achieved by a final
    ``SUPPORTED`` return, and a member added to ``ValidityStatus`` or
    ``ValidationOutcome`` tomorrow would land on it silently — an upgrade to
    the most favourable verdict, earned by the enum growing. So the function
    checks explicitly that everything reaching the last branch is something it
    was written to understand, and raises if not.
    """
    # Normalised through the enum rather than compared raw. ValidityAssessment
    # has no __post_init__ and so may hold a bare string; that happens to
    # compare and hash equal to its enum member today, but leaning on a
    # str-enum implementation detail to decide a verdict is not a dependency
    # worth having. ModelValidityRecord already refuses anything
    # ValidityStatus() cannot accept — but this function is exported and
    # documented as usable on its own, so it must not rely on a sibling type's
    # constructor having run.
    try:
        statuses = {
            ValidityStatus(record.assessment.status) for record in validity
        }
        outcomes = {ValidationOutcome(check.outcome) for check in validation}
    except (ValueError, AttributeError) as exc:
        raise CredibilityEvidenceError(
            f"cannot derive a verdict from these contents ({exc}); a status or "
            f"outcome this function does not understand must not be read as "
            f"'nothing argues against this result'"
        ) from exc

    # Order of these two branches IS the precedence rule. Do not reorder.
    if ValidityStatus.OUTSIDE_VALIDATED_DOMAIN in statuses:
        return CredibilityVerdict.NOT_SUPPORTED
    if ValidationOutcome.FAIL in outcomes:
        return CredibilityVerdict.NOT_SUPPORTED

    if ValidityStatus.UNKNOWN in statuses:
        return CredibilityVerdict.INSUFFICIENT_EVIDENCE
    if ValidationOutcome.NOT_RUN in outcomes:
        return CredibilityVerdict.INSUFFICIENT_EVIDENCE
    if unassessed_models:
        return CredibilityVerdict.INSUFFICIENT_EVIDENCE
    if not validity:
        return CredibilityVerdict.INSUFFICIENT_EVIDENCE

    # The evidential guard, and the core's own definition of what counts:
    # exactly `ValidationReport.attained_levels`. It subsumes "there are no
    # checks at all" -- an empty check list attains nothing, and so does a
    # full one that establishes nothing.
    attained = {
        check.establishes
        for check in validation
        if check.passed and check.establishes is not None
    }
    if not attained:
        return CredibilityVerdict.INSUFFICIENT_EVIDENCE
    if required_levels and not set(required_levels) <= attained:
        return CredibilityVerdict.INSUFFICIENT_EVIDENCE

    # Everything below is SUPPORTED, so everything reaching here must be a
    # member this function was written to handle. A future enum addition is a
    # loud failure at the one site that has to be updated, not a silent upgrade.
    unhandled_statuses = statuses - {ValidityStatus.IN_DOMAIN}
    unhandled_outcomes = outcomes - {
        ValidationOutcome.PASS,
        ValidationOutcome.WARNING,
    }
    if unhandled_statuses or unhandled_outcomes:
        raise CredibilityEvidenceError(
            f"derive_verdict does not handle "
            f"{sorted(s.value for s in unhandled_statuses)} / "
            f"{sorted(o.value for o in unhandled_outcomes)}; a case this "
            f"function was not written for must not fall through to SUPPORTED"
        )

    return CredibilityVerdict.SUPPORTED


@dataclass(frozen=True)
class ModelValidityRecord:
    """One model's validity verdict, transported from its ``ValidityAssessment``.

    The assessment is carried whole rather than flattened into a status: the
    satisfied, violated and unknown condition *names* are the part a reader
    acts on. "OUTSIDE_VALIDATED_DOMAIN" tells an engineer to stop;
    "OUTSIDE_VALIDATED_DOMAIN, violated: biot_number" tells them what to change.

    Nothing here recomputes an assessment. The model that owns the validity
    domain produced this; this record only says which model it belonged to, so
    a report covering several models does not collapse them into one verdict
    with no attribution.
    """

    model_id: str
    version: str
    assessment: ValidityAssessment

    def __post_init__(self) -> None:
        for label in ("model_id", "version"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise CredibilityEvidenceError(
                    f"model validity record requires a non-empty {label}"
                )
            object.__setattr__(self, label, text)
        if not isinstance(self.assessment, ValidityAssessment):
            raise CredibilityEvidenceError(
                f"model validity record requires a ValidityAssessment, got "
                f"{type(self.assessment).__name__} — a bare status string "
                f"would drop the condition names a reader acts on"
            )
        # ValidityAssessment is the one record in the core with no
        # __post_init__: it coerces nothing and cross-checks nothing. Two
        # consequences have to be handled here, because nothing upstream does.
        #
        # 1. `ValidityAssessment(status="in_domain")` stores a raw str, and
        #    `ValidityAssessment(status="typo")` stores a string that is no
        #    status at all. Normalise the first — probing without writing back
        #    leaves `.status` a str, which then crashes the core's own
        #    `to_dict` on `self.status.value` — and refuse the second, because
        #    an unrecognised status matches no branch of derive_verdict.
        try:
            status = ValidityStatus(self.assessment.status)
        except ValueError as exc:
            raise CredibilityEvidenceError(
                f"model validity record for {self.model_id!r} carries "
                f"{self.assessment.status!r}, which is not a ValidityStatus; "
                f"an unrecognised status would be read as 'nothing argues "
                f"against this result'"
            ) from exc
        # Rebuilt rather than mutated in place: the caller's assessment is
        # theirs, and a record that edited it would be a worse neighbour than
        # one that copied it.
        assessment = ValidityAssessment(
            status=status,
            satisfied=tuple(self.assessment.satisfied),
            violated=tuple(self.assessment.violated),
            unknown=tuple(self.assessment.unknown),
        )
        object.__setattr__(self, "assessment", assessment)

        # 2. Nothing forces the status to agree with the assessment's own
        #    condition lists, so `status=IN_DOMAIN, violated=("biot_number",)`
        #    constructs happily — and would report SUPPORTED on the same record
        #    that names the bound it violated. Cross-check against exactly the
        #    classification `ValidityDomain.assess` performs, so every
        #    assessment the core actually produced passes untouched and only a
        #    hand-built or hand-edited one is refused. Recompute-and-verify, the
        #    same discipline `ValidationReport.from_dict` applies to
        #    `attained_levels`.
        if assessment.violated:
            implied = ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        elif assessment.unknown:
            implied = ValidityStatus.UNKNOWN
        else:
            implied = ValidityStatus.IN_DOMAIN
        if status is not implied:
            raise CredibilityEvidenceError(
                f"model validity record for {self.model_id!r} declares status "
                f"{status.value!r} while its own conditions imply "
                f"{implied.value!r} (violated={list(assessment.violated)}, "
                f"unknown={list(assessment.unknown)}); a record may report a "
                f"status but may not contradict the conditions it carries"
            )

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.version)

    @property
    def status(self) -> ValidityStatus:
        return self.assessment.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_VALIDITY_SCHEMA,
            "model_id": self.model_id,
            "version": self.version,
            "assessment": self.assessment.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelValidityRecord":
        require_schema(payload, MODEL_VALIDITY_SCHEMA)
        return cls(
            model_id=payload["model_id"],
            version=payload["version"],
            assessment=ValidityAssessment.from_dict(payload["assessment"]),
        )


def _merged_validity(
    result: ScientificResult,
    supplied: tuple["ModelValidityRecord", ...],
) -> tuple["ModelValidityRecord", ...]:
    """The result's own assessments and the caller's, merged and never ranked.

    The result carries a mapping keyed by model id; the version comes from the
    result's own ``models``, which is where the core requires every assessed
    id to appear. A model both sources name must carry the same assessment —
    one verdict per model, decided once — and a disagreement raises here rather
    than being resolved by which argument happened to be looked at first.
    """
    versions = {model_id: version for model_id, version in result.models}
    carried = tuple(
        ModelValidityRecord(
            model_id=model_id,
            version=versions[model_id],
            assessment=assessment,
        )
        for model_id, assessment in sorted(result.validity.items())
    )
    by_key: dict[str, ModelValidityRecord] = {}
    merged: list[ModelValidityRecord] = []
    for record in (*carried, *supplied):
        existing = by_key.get(record.model_id)
        if existing is None:
            by_key[record.model_id] = record
            merged.append(record)
            continue
        if existing == record:
            continue
        raise CredibilityEvidenceError(
            f"two different validity verdicts for model "
            f"{record.model_id!r}: the result carries {existing.assessment} "
            f"and the caller supplied {record.assessment}. One model has one "
            f"verdict; choosing between them by precedence would let either "
            f"replace the other with nothing in the record to say so"
        )
    return tuple(merged)


@dataclass(frozen=True)
class AssertedContext:
    """Something the caller *said*, carried verbatim and marked as not evidence.

    The motivating case is the lumped model's convection regime. A caller may
    declare ``convection_regime='forced'`` to explain why they chose a wide
    constant-``hA`` span. No condition reads it, the problem record cannot
    carry it — ``ProvenanceRecord`` admits only ``Quantity`` inputs — and so it
    reaches a reader through no other channel. It is real context and it is
    worth having; it is not evidence, and a report that filed it beside the
    validation checks would be inviting exactly the confusion this platform
    exists to prevent.

    So it lives in its own field, under its own schema, and the marking
    **survives serialization**: ``to_dict`` emits ``caller_asserted: true`` and
    ``consumed_by_verdict: false`` as literal keys. A reader parsing the JSON
    without ever seeing this docstring still cannot mistake it for a check.

    **Why the marking is not "no check consumed this".** That was the first
    wording and it is false. Wrap a whole ``LumpedApplicabilityDeclaration``
    here — the motivating case — and the payload contains
    ``body_conductivity``, ``surface_area``, ``melting_temperature`` and the
    rest, every one of which *is* read by a condition: they are the inputs the
    Biot number, the Fourier number and the excursion budgets are computed
    from. Only the convection regime is genuinely inert. Asserting a blanket
    "no check consumed this" over that payload would put a false statement in
    the record, which is the precise failure this field exists to prevent.

    ``consumed_by_verdict: false`` is asserted instead, and it is true by
    construction rather than by inspection: ``declarations`` is not a parameter
    of :func:`derive_verdict`, so nothing in this field can move a verdict. A
    reader who wants to know whether a particular declared value was consumed
    by a *condition* has the answer in the same report — the condition names
    are in the validity records beside it.

    ``payload`` is whatever the declaration's own ``to_dict`` produced. It is
    stored verbatim — not summarised, not filtered — because the point is that
    the reader sees what was claimed, and a report that edited the claim on
    the way through would be a worse record than one that omitted it. The one
    thing refused is a payload that embeds a *core record*: a caller's asserted
    context has no business carrying something shaped like a validation check,
    because a tool scanning the document for ``schema`` keys would find it
    below the markings that say it is not evidence.
    """

    source: str
    payload: Mapping[str, Any]
    description: str = ""

    def __post_init__(self) -> None:
        source = str(self.source).strip()
        if not source:
            raise CredibilityEvidenceError(
                "asserted context requires a source naming what declared it; "
                "an unattributed claim is not context, it is noise"
            )
        object.__setattr__(self, "source", source)

        if not isinstance(self.payload, Mapping):
            raise CredibilityEvidenceError(
                f"asserted context payload must be a mapping, got "
                f"{type(self.payload).__name__}"
            )
        payload = dict(self.payload)
        # Verbatim has to mean *round-trippable*. A payload holding a live
        # object would serialize to something a reader could not compare
        # against the declaration it came from, which defeats the purpose.
        try:
            json.dumps(payload, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise CredibilityEvidenceError(
                f"asserted context {source!r} payload is not JSON-serializable "
                f"({exc}); pass the declaration's own to_dict() output so the "
                f"claim survives the record it is stored in"
            ) from exc
        embedded = _embedded_core_schemas(payload)
        if embedded:
            raise CredibilityEvidenceError(
                f"asserted context {source!r} embeds core evidence records "
                f"({sorted(embedded)}); a caller's claim may not carry "
                f"something shaped like a check or an assessment, because a "
                f"reader scanning for those shapes would find it underneath "
                f"the markings that say this is not evidence"
            )
        object.__setattr__(self, "payload", payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASSERTED_CONTEXT_SCHEMA,
            "source": self.source,
            "description": self.description,
            # Not decoration. These two keys are the only thing standing
            # between a JSON reader and treating a caller's claim as a result.
            "caller_asserted": True,
            # True by construction, not by inspection: `declarations` is not a
            # parameter of derive_verdict. Deliberately NOT the stronger
            # "consumed_by_any_check", which would be false for any payload
            # carrying an applicability declaration — see the class docstring.
            "consumed_by_verdict": False,
            "payload": dict(sorted(self.payload.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssertedContext":
        require_schema(payload, ASSERTED_CONTEXT_SCHEMA)
        return cls(
            source=payload["source"],
            payload=dict(payload.get("payload", {})),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class CredibilityEvidenceReport:
    """One run's values, validity, validation, provenance and asserted context.

    Assembled by a consumer, never by the core. Every scientific judgement in
    it was made upstream; this record transports them together so that the
    three questions the platform keeps separate can be *asked* together without
    being *merged*.

    :attr:`verdict` is a property, not a field. See the module docstring.
    """

    run_id: str
    values: Mapping[str, Quantity]
    provenance: ProvenanceRecord
    validity: tuple[ModelValidityRecord, ...] = ()
    validation: tuple[ValidationCheck, ...] = ()
    declarations: tuple[AssertedContext, ...] = ()
    #: Levels the assembling study declares it needs before it will rely on
    #: this result. Empty means "no level is demanded", which is the rule as
    #: specified and is why a report can be SUPPORTED with nothing attained.
    #: A caller who needs more says so here rather than re-reading the verdict.
    required_levels: tuple[ValidationLevel, ...] = ()
    #: The solver's own commentary on its validation, carried unaltered.
    #: Separate from ``notes`` because that is the *assembler's* commentary,
    #: and letting an assembler's sentence come back out of
    #: :meth:`validation_report` in the field where the validation machinery's
    #: own words belong would be a small forgery.
    validation_notes: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        if not run_id:
            raise CredibilityEvidenceError(
                "credibility evidence report requires a non-empty run_id; evidence that "
                "cannot be attributed to a run is not evidence"
            )
        object.__setattr__(self, "run_id", run_id)

        values = dict(self.values)
        for name, value in values.items():
            if not isinstance(value, Quantity):
                raise CredibilityEvidenceError(
                    f"report value {name!r} must be a Quantity — a bare "
                    f"number is not a scientific result"
                )
        object.__setattr__(self, "values", values)

        validity = tuple(self.validity)
        for record in validity:
            if not isinstance(record, ModelValidityRecord):
                raise CredibilityEvidenceError(
                    f"validity entries must be ModelValidityRecord, got "
                    f"{type(record).__name__}"
                )
        keys = [record.key for record in validity]
        duplicates = {k for k in keys if keys.count(k) > 1}
        if duplicates:
            raise CredibilityEvidenceError(
                f"duplicate model validity records for {sorted(duplicates)}; "
                f"one model at one version has one verdict, and two entries "
                f"would let a reader pick the flattering one"
            )
        # Sorted, because the order a caller happened to assess models in is
        # not information about the models. Two reports stating the same
        # per-model verdicts are the same report and must serialize
        # byte-identically — the same reason ProvenanceRecord sorts its
        # bindings. The validation checks below are deliberately NOT sorted:
        # there, order is the order the checks ran in, which *is* information.
        object.__setattr__(self, "validity", tuple(sorted(validity, key=lambda r: r.key)))

        validation = tuple(self.validation)
        for check in validation:
            if not isinstance(check, ValidationCheck):
                raise CredibilityEvidenceError(
                    f"validation entries must be ValidationCheck, got "
                    f"{type(check).__name__}"
                )
        names = [check.name for check in validation]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise CredibilityEvidenceError(
                f"duplicate validation check names: {sorted(duplicates)}; the "
                f"core's own ValidationReport refuses these for the same "
                f"reason, so a report may not launder them"
            )
        object.__setattr__(self, "validation", validation)

        # Required, matching ScientificResult's own rule that "an
        # unattributable number is not a scientific result". A report is a
        # stronger claim than a result, so it cannot have a weaker rule: an
        # optional-and-inert provenance would let an unattributed report
        # report SUPPORTED.
        if not isinstance(self.provenance, ProvenanceRecord):
            raise CredibilityEvidenceError(
                f"credibility evidence report requires a ProvenanceRecord, got "
                f"{type(self.provenance).__name__}; evidence that cannot be "
                f"attributed to what produced it is not evidence"
            )

        # Validity records must name models that actually took part. Without
        # this a caller could attach an honest IN_DOMAIN assessment of an
        # unrelated model and turn an unassessed report into a SUPPORTED one.
        declared_models = set(self.provenance.models)
        if declared_models:
            stray = {r.key for r in validity} - declared_models
            if stray:
                raise CredibilityEvidenceError(
                    f"validity records name models the provenance does not: "
                    f"{sorted(stray)}. An assessment of a model that did not "
                    f"produce these values is not evidence about these values"
                )

        object.__setattr__(
            self, "required_levels", tuple(
                ValidationLevel(level) for level in self.required_levels
            )
        )

        declarations = tuple(self.declarations)
        for declaration in declarations:
            if not isinstance(declaration, AssertedContext):
                raise CredibilityEvidenceError(
                    f"declarations must be AssertedContext, got "
                    f"{type(declaration).__name__} — the type is what marks "
                    f"a caller's claim as something no check consumed"
                )
        object.__setattr__(self, "declarations", declarations)

    # ---- derived state --------------------------------------------------
    @property
    def verdict(self) -> CredibilityVerdict:
        """What this report's own contents support. **Advisory.**

        Read this as the beginning of a conversation with the evidence, not as
        a decision taken on the reader's behalf. The report is assembled for
        an engineer of record; it is that engineer, not this property, who
        decides whether a design proceeds. ``SUPPORTED`` means *nothing here
        argues against it* — the checks that ran are listed, what each
        establishes is listed, and the conditions a model was judged against
        are named, precisely so that the judgement stays with the person
        qualified to make it.

        Derived on every access from :func:`derive_verdict`. There is no
        stored copy to drift, and no constructor parameter to disagree with.
        """
        return derive_verdict(
            validity=self.validity,
            validation=self.validation,
            unassessed_models=self.unassessed_models,
            required_levels=self.required_levels,
        )

    @property
    def is_supported(self) -> bool:
        return self.verdict is CredibilityVerdict.SUPPORTED

    @property
    def unassessed_models(self) -> tuple[tuple[str, str], ...]:
        """Models the provenance says ran, that nobody assessed for validity.

        The per-model form of "nobody asked whether the model applied", and
        strictly stronger than the report-level "there are no validity records
        at all": a run over two models with one assessment is a gap that a
        count of records cannot see.
        """
        assessed = {record.key for record in self.validity}
        return tuple(sorted(set(self.provenance.models) - assessed))

    @property
    def attained_levels(self) -> frozenset[ValidationLevel]:
        """Levels backed by a passing check, as the core computes them.

        Exposed beside the verdict because ``SUPPORTED`` does not require this
        to be non-empty, and a reader is entitled to notice when it is.
        """
        return self.validation_report().attained_levels

    @property
    def missing_required_levels(self) -> tuple[ValidationLevel, ...]:
        """Declared-as-needed levels that no passing check established."""
        return tuple(
            sorted(
                set(self.required_levels) - self.attained_levels,
                key=lambda level: level.value,
            )
        )

    @property
    def violated_conditions(self) -> tuple[tuple[str, str], ...]:
        """``(model_id, condition_name)`` for every violated condition.

        The actionable half of a ``NOT_SUPPORTED`` verdict: not *that* the
        design failed, but which bound it failed against.
        """
        return tuple(
            (record.model_id, name)
            for record in self.validity
            for name in record.assessment.violated
        )

    @property
    def unknown_conditions(self) -> tuple[tuple[str, str], ...]:
        """``(model_id, condition_name)`` for every condition left UNKNOWN.

        The actionable half of an ``INSUFFICIENT_EVIDENCE`` verdict: the list
        of declarations somebody still has to make.
        """
        return tuple(
            (record.model_id, name)
            for record in self.validity
            for name in record.assessment.unknown
        )

    @property
    def not_run_checks(self) -> tuple[str, ...]:
        """Names of checks that were declared and never executed."""
        return tuple(
            check.name
            for check in self.validation
            if check.outcome is ValidationOutcome.NOT_RUN
        )

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(
            check.name
            for check in self.validation
            if check.outcome is ValidationOutcome.FAIL
        )

    @property
    def warning_checks(self) -> tuple[str, ...]:
        """Checks that ran, did not fail, and flagged something anyway.

        WARNING is the one outcome the verdict deliberately absorbs into
        SUPPORTED, which makes it the one a reader is most likely to miss.
        Findable here rather than only by filtering :attr:`validation` by hand.
        """
        return tuple(
            check.name
            for check in self.validation
            if check.outcome is ValidationOutcome.WARNING
        )

    # ---- assembly -------------------------------------------------------
    @classmethod
    def from_result(
        cls,
        result: ScientificResult,
        *,
        validity: Iterable[ModelValidityRecord] = (),
        declarations: Iterable[AssertedContext] = (),
        required_levels: Iterable[ValidationLevel] = (),
        notes: str = "",
        run_id: str | None = None,
    ) -> "CredibilityEvidenceReport":
        """Assemble a report around one executed :class:`ScientificResult`.

        Values, validation checks and provenance are taken from the result
        unaltered — including ``NOT_RUN`` checks, which is the whole point of
        carrying the report's checks rather than its aggregate status.

        ``validity`` is read **from the result first**, and from the caller
        second. ``ScientificResult.validity`` is a mapping of assessments the
        producer of the result made; each becomes a
        :class:`ModelValidityRecord` here, which stays the transport — this
        report's own field is what ``derive_verdict`` reads, and nothing about
        the verdict rules changed.

        The caller's argument is still accepted, because a result whose
        producer did not hold the operating point carries nothing and somebody
        else has to make the assessment. **The two sources are merged, not
        ranked.** A model named by both must carry the identical assessment;
        two different verdicts for one model are refused rather than resolved
        by precedence, because silently preferring either would let one verdict
        replace another with no reader able to tell.

        A report assembled with no validity records at all — or with fewer than
        the models the provenance says ran — still reports
        ``INSUFFICIENT_EVIDENCE``, which is the honest reading of "nobody asked
        whether the model applied". An empty ``ScientificResult.validity``
        contributes nothing here, exactly as it means nothing there.

        ``run_id`` defaults to the result's own id. It may be overridden for
        the legitimate case of a report covering a coupled run assembled
        around one of its sub-results, where the run's identity is not any one
        result's. Both identities stay visible: the override lands in
        ``run_id`` and the result's own is still in ``provenance.run_id``.
        """
        if not isinstance(result, ScientificResult):
            raise CredibilityEvidenceError(
                f"from_result expects a ScientificResult, got "
                f"{type(result).__name__}"
            )
        return cls(
            run_id=run_id or result.result_id,
            values=dict(result.values),
            provenance=result.provenance,
            validity=_merged_validity(result, tuple(validity)),
            validation=tuple(result.validation.checks),
            declarations=tuple(declarations),
            required_levels=tuple(required_levels),
            validation_notes=result.validation.notes,
            notes=notes,
        )

    def validation_report(self) -> ValidationReport:
        """The carried checks, back in the core's own record type.

        Round-trips through the core rather than reimplementing its derived
        state: a caller who wants ``attained_levels`` should get the core's
        answer, computed by the core, not a second opinion from here.

        Carries ``validation_notes`` — the solver's own commentary — and not
        this report's ``notes``, which belong to whoever assembled it. Putting
        an assembler's sentence into a ``validation_report/1`` record would
        make it indistinguishable, in the serialized form, from something the
        validation machinery said.
        """
        return ValidationReport(
            checks=self.validation, notes=self.validation_notes
        )

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_PACKAGE_SCHEMA,
            "run_id": self.run_id,
            "values": {
                name: self.values[name].to_dict()
                for name in sorted(self.values)
            },
            "provenance": self.provenance.to_dict(),
            "validity": [record.to_dict() for record in self.validity],
            "validation": [check.to_dict() for check in self.validation],
            "declarations": [d.to_dict() for d in self.declarations],
            "required_levels": [level.value for level in self.required_levels],
            "validation_notes": self.validation_notes,
            "notes": self.notes,
            # Derived, emitted for readers, and re-derived on the way back in.
            "verdict": self.verdict.value,
            # Also derived. Emitted because a reader of the JSON who never
            # opens the check list should still see that a SUPPORTED verdict
            # carries warnings, or rests on no attained level at all.
            "verdict_qualifiers": {
                "warning_checks": list(self.warning_checks),
                "attained_levels": sorted(
                    level.value for level in self.attained_levels
                ),
                "unassessed_models": [list(m) for m in self.unassessed_models],
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CredibilityEvidenceReport":
        require_schema(payload, EVIDENCE_PACKAGE_SCHEMA)
        report = cls(
            run_id=payload["run_id"],
            values={
                name: Quantity.from_dict(value)
                for name, value in (payload.get("values") or {}).items()
            },
            validity=tuple(
                ModelValidityRecord.from_dict(r)
                for r in (payload.get("validity") or ())
            ),
            validation=tuple(
                ValidationCheck.from_dict(c)
                for c in (payload.get("validation") or ())
            ),
            provenance=ProvenanceRecord.from_dict(payload["provenance"]),
            declarations=tuple(
                AssertedContext.from_dict(d)
                for d in (payload.get("declarations") or ())
            ),
            required_levels=tuple(
                ValidationLevel(level)
                for level in (payload.get("required_levels") or ())
            ),
            validation_notes=payload.get("validation_notes", ""),
            notes=payload.get("notes", ""),
        )
        # The verdict in a payload is advisory; recompute and verify so a
        # hand-edited record cannot smuggle in a verdict its contents do not
        # support. Exactly what ValidationReport.from_dict does for
        # attained_levels, one level up.
        declared = payload.get("verdict")
        if declared is not None and declared != report.verdict.value:
            raise CredibilityEvidenceError(
                f"serialized verdict {declared!r} does not match the verdict "
                f"its contents produce ({report.verdict.value!r}); a report "
                f"may report a verdict but may not assert one"
            )
        return report


#: Deprecated alias, kept for one release.
#:
#: The record was called ``EvidencePackage`` before the layer adopted the
#: vocabulary of ASME V&V 10/20/40 and NASA-STD-7009, in which the thing being
#: reported is *credibility*. The name is retained so existing importers keep
#: working across one release and no more; new code should use
#: :class:`CredibilityEvidenceReport`. It is the same class, not a subclass, so
#: ``isinstance`` and ``from_dict`` behave identically either way.
EvidencePackage = CredibilityEvidenceReport
