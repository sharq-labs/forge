"""Three questions a benchmark case answers, kept apart.

WHY THIS MODULE EXISTS
----------------------
The old scorer compared one enum per case: did Forge return the expected
verdict. That collapses three different questions into one PASS, and the
collapse is not hypothetical. In the ``adv_unsound:small_overshoot`` family
four dev cases are scored as caught while the condition their own ground truth
names is *satisfied* -- they are refused by something else entirely. The verdict
was right, the mechanism was not, and a headline catch rate could not tell the
difference between finding a defect and tripping over an unrelated one.

So a scored case now carries three answers:

===================  =========================================================
verdict_match        did Forge return the expected final verdict
declared_catcher     did the mechanism the truth names actually decide the case
catch_type           if Forge refused, was that the declared mechanism, an
                     explicitly-permitted alternative, or a coincidence
===================  =========================================================

These never merge. A case can be ``verdict_match=True`` and
``catch_type=COINCIDENTAL`` at the same time, and that combination is the one
this module exists to make visible.

WHAT IS *NOT* HERE, AND WHY
---------------------------
**Reason accuracy.** ``ground_truth.reason`` is prose written for a human --
"Over the ceiling by 0.174 K. Small, and still over." Nothing Forge emits can
be compared to it without a heuristic, and a heuristic that guessed would
manufacture exactly the false precision this round exists to remove. So reason
matching reports ``UNSPECIFIED`` for every case whose truth does not carry a
machine-checkable field, and the scorecard prints that denominator instead of
hiding it. The optional fields a future truth revision can populate --
``acceptable_catchers``, ``expected_unknown_reason`` -- are read here if they
appear and are absent from every case today.

**Inferred alternates.** ``ALTERNATE_VALID`` is only ever returned when the
case explicitly lists the catcher in ``acceptable_catchers``. It is never
inferred from the fact that some other condition happened to fail: that is the
inference which turns a coincidence into a success.

THE DECLARED-CATCHER GRAMMAR
----------------------------
``should_be_caught_by`` is not free text. Over the 2000 cases it takes exactly
five shapes, and each says something different about what the run must show:

=============================  ============================================
``""``                         nothing declared -- not scoreable
``"biot_number"``              that condition must DECIDE the case
``"biot_number -> UNKNOWN"``   that condition must be UNKNOWN
``"biot_number (alt route      that condition must be SATISFIED: the case
remains)"``                    asserts an alternative route must not refuse
``"thermal runaway"``          prose naming a MECHANISM rather than a
                               condition -- the coupling must refuse
=============================  ============================================

What "decide" means depends on the expected verdict, because the same condition
carries a different claim in each: on a NOT_SUPPORTED case it must be violated;
on an INSUFFICIENT_EVIDENCE case it must be violated *or* unknown (the
conservative-screen adjudication moved verdicts and deliberately left
``should_be_caught_by`` alone, so both readings are live); on a SUPPORTED case
it must be satisfied, because such a case exists to assert a near miss that
must not refuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CatcherForm(str, Enum):
    """What shape the declared catcher takes. See the module docstring."""

    NOT_DECLARED = "not_declared"
    DECIDING_CONDITION = "deciding_condition"
    EXPECT_UNKNOWN = "expect_unknown"
    EXPECT_HELD = "expect_held"
    MECHANISM = "mechanism"


class CatcherStatus(str, Enum):
    FIRED = "FIRED"
    HELD = "HELD"
    NOT_FIRED = "NOT_FIRED"
    NOT_DECLARED = "NOT_DECLARED"


class CatchType(str, Enum):
    DECLARED = "DECLARED"
    ALTERNATE_VALID = "ALTERNATE_VALID"
    COINCIDENTAL = "COINCIDENTAL"
    UNDECLARED = "UNDECLARED"
    NONE = "NONE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReasonMatch(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNSPECIFIED = "UNSPECIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


#: The one prose catcher in the corpus, and what it actually asserts: not a
#: condition on any model, but that the coupled solve refuses to transport a
#: quantity it cannot stand behind.
MECHANISM_CATCHERS = {"thermal runaway": "coupling_refusal"}

_UNKNOWN_SUFFIX = " -> UNKNOWN"
_HELD_SUFFIX = " (alt route remains)"


@dataclass(frozen=True)
class DeclaredCatcher:
    form: CatcherForm
    name: str | None
    raw: str

    @property
    def is_scoreable(self) -> bool:
        return self.form is not CatcherForm.NOT_DECLARED


def parse_catcher(raw: str | None) -> DeclaredCatcher:
    """Read ``should_be_caught_by`` without guessing."""
    text = (raw or "").strip()
    if not text:
        return DeclaredCatcher(CatcherForm.NOT_DECLARED, None, text)
    if text in MECHANISM_CATCHERS:
        return DeclaredCatcher(
            CatcherForm.MECHANISM, MECHANISM_CATCHERS[text], text
        )
    if text.endswith(_UNKNOWN_SUFFIX):
        return DeclaredCatcher(
            CatcherForm.EXPECT_UNKNOWN, text[: -len(_UNKNOWN_SUFFIX)].strip(), text
        )
    if text.endswith(_HELD_SUFFIX):
        return DeclaredCatcher(
            CatcherForm.EXPECT_HELD, text[: -len(_HELD_SUFFIX)].strip(), text
        )
    return DeclaredCatcher(CatcherForm.DECIDING_CONDITION, text, text)


@dataclass(frozen=True)
class ReportFacts:
    """What the run showed, reduced to what scoring needs.

    Condition names are pooled across every model in every report of the run.
    A condition is identified by name alone because the benchmark's
    ``should_be_caught_by`` names it that way -- no case anywhere qualifies a
    condition by the model that declares it.
    """

    verdict: str
    violated: frozenset[str] = frozenset()
    unknown: frozenset[str] = frozenset()
    satisfied: frozenset[str] = frozenset()
    coupling_refused: bool = False
    #: ``UnknownReason`` codes observed, as ``condition:reason`` pairs and as
    #: bare reason codes. A benchmark that declares an expected reason is
    #: matched against these rather than against the prose.
    unknown_reasons: frozenset[str] = frozenset()
    #: Populated only when the run produced no report at all.
    error: str = ""


@dataclass(frozen=True)
class ScoredCase:
    case_id: str
    system: str
    defect: str
    label: str
    expected_verdict: str
    actual_verdict: str
    verdict_match: bool
    catcher_raw: str
    catcher_form: str
    catcher_name: str | None
    declared_catcher_status: str
    catch_type: str
    reason_match: str
    false_accept: bool
    false_reject: bool
    #: Conditions that actually decided the case, for the coincidence audit.
    deciding_conditions: tuple[str, ...] = ()
    #: Does the truth DECLARE any acceptable alternate at all? Carried so the
    #: alternate rate has a denominator that is the cases which could have
    #: one, rather than every case in the corpus.
    has_alternates: bool = False
    #: Did an explicitly-declared ALTERNATE catcher fire? Only ever true when
    #: the case lists one, so it can never be inferred from a bare failure.
    alternate_fired: bool = False
    #: The truth's own `needs_review` flag, surfaced so a case whose truth is
    #: known to be suspect is visible in the scorecard rather than only in a
    #: file. `UNDER_REVIEW` cases still score normally -- they are reported,
    #: not excused.
    review_status: str = "SETTLED"
    #: What KIND of thing decided this case's truth. Absent on a case means
    #: the corpus default, GENERATOR_CONSTRUCTION.
    oracle: str = "GENERATOR_CONSTRUCTION"

    def as_row(self) -> dict:
        return {
            "id": self.case_id,
            "system": self.system,
            "defect": self.defect,
            "label": self.label,
            "expected": self.expected_verdict,
            "actual": self.actual_verdict,
            "match": self.verdict_match,
            "catcher": self.catcher_raw,
            "catcher_form": self.catcher_form,
            "catcher_status": self.declared_catcher_status,
            "catch_type": self.catch_type,
            "reason_match": self.reason_match,
            "false_accept": self.false_accept,
            "false_reject": self.false_reject,
            "deciding": list(self.deciding_conditions),
            "has_alternates": self.has_alternates,
            "alternate_fired": self.alternate_fired,
            "review_status": self.review_status,
            "oracle": self.oracle,
        }


def _catcher_status(
    catcher: DeclaredCatcher, expected_verdict: str, facts: ReportFacts
) -> CatcherStatus:
    if catcher.form is CatcherForm.NOT_DECLARED:
        return CatcherStatus.NOT_DECLARED
    if catcher.form is CatcherForm.MECHANISM:
        return (
            CatcherStatus.FIRED
            if facts.coupling_refused
            else CatcherStatus.NOT_FIRED
        )
    name = catcher.name
    if catcher.form is CatcherForm.EXPECT_UNKNOWN:
        return (
            CatcherStatus.FIRED if name in facts.unknown else CatcherStatus.NOT_FIRED
        )
    if catcher.form is CatcherForm.EXPECT_HELD:
        return (
            CatcherStatus.HELD
            if name in facts.satisfied
            else CatcherStatus.NOT_FIRED
        )
    # DECIDING_CONDITION: what "decide" means depends on what the case claims.
    if expected_verdict == "NOT_SUPPORTED":
        return (
            CatcherStatus.FIRED if name in facts.violated else CatcherStatus.NOT_FIRED
        )
    if expected_verdict == "INSUFFICIENT_EVIDENCE":
        decided = name in facts.violated or name in facts.unknown
        return CatcherStatus.FIRED if decided else CatcherStatus.NOT_FIRED
    # SUPPORTED: the case asserts a near miss that must NOT refuse.
    return CatcherStatus.HELD if name in facts.satisfied else CatcherStatus.NOT_FIRED


def _catch_type(
    *,
    is_unsound: bool,
    refused: bool,
    catcher: DeclaredCatcher,
    status: CatcherStatus,
    acceptable: frozenset[str],
    facts: ReportFacts,
) -> CatchType:
    """Was a refusal the declared mechanism, a permitted alternate, or luck?"""
    if not is_unsound:
        return CatchType.NOT_APPLICABLE
    if not refused:
        return CatchType.NONE
    if status is CatcherStatus.FIRED:
        return CatchType.DECLARED
    if catcher.form is CatcherForm.NOT_DECLARED:
        # Truth names no mechanism, so nothing here can classify the refusal.
        # Saying UNDECLARED rather than guessing is the whole point.
        return CatchType.UNDECLARED
    # An alternate counts only when the truth SAYS it counts.
    if acceptable & (facts.violated | facts.unknown):
        return CatchType.ALTERNATE_VALID
    return CatchType.COINCIDENTAL


def score_case(ground_truth: dict, case_id: str, system: str, facts: ReportFacts) -> ScoredCase:
    """One case, scored on all three questions independently."""
    expected = ground_truth["expected_verdict"]
    label = ground_truth["label"]
    catcher = parse_catcher(ground_truth.get("should_be_caught_by"))
    acceptable = frozenset(ground_truth.get("acceptable_catchers") or ())

    is_unsound = label != "valid"
    refused = facts.verdict != "SUPPORTED"
    status = _catcher_status(catcher, expected, facts)
    catch = _catch_type(
        is_unsound=is_unsound,
        refused=refused,
        catcher=catcher,
        status=status,
        acceptable=acceptable,
        facts=facts,
    )

    # Reason matching is reported, never invented. Only a case carrying a
    # machine-checkable expectation is matched, and it is matched against the
    # UnknownReason CODES the run produced -- never against the prose in
    # `reason`, which no scorer can read.
    expected_unknown = ground_truth.get("expected_unknown_reason")
    if expected_unknown is None:
        reason = ReasonMatch.UNSPECIFIED
    else:
        reason = (
            ReasonMatch.MATCH
            if expected_unknown in facts.unknown_reasons
            else ReasonMatch.MISMATCH
        )

    return ScoredCase(
        case_id=case_id,
        system=system,
        defect=ground_truth["defect"],
        label=label,
        expected_verdict=expected,
        actual_verdict=facts.verdict,
        verdict_match=facts.verdict == expected,
        catcher_raw=catcher.raw,
        catcher_form=catcher.form.value,
        catcher_name=catcher.name,
        declared_catcher_status=status.value,
        catch_type=catch.value,
        reason_match=reason.value,
        false_accept=is_unsound and facts.verdict == "SUPPORTED",
        false_reject=(not is_unsound) and facts.verdict != "SUPPORTED",
        deciding_conditions=tuple(sorted(facts.violated | facts.unknown)),
        has_alternates=bool(acceptable),
        alternate_fired=bool(acceptable & (facts.violated | facts.unknown)),
        review_status=(
            "UNDER_REVIEW" if ground_truth.get("needs_review") else "SETTLED"
        ),
        oracle=ground_truth.get("oracle") or "GENERATOR_CONSTRUCTION",
    )


def scorecard(scored: list[ScoredCase]) -> dict:
    """Every metric with its own explicit denominator.

    No metric here is a fraction of "total cases" unless total cases is really
    the population it is about. A rate whose denominator is not stated beside
    it is the failure this whole module is a response to.
    """
    total = len(scored)
    if not total:
        return {"total": 0}

    def rate(n, d, places=1):
        # `places` exists so the figures this scorecard inherits keep the
        # precision they were published with. A false-accept rate that
        # silently went from 0.00% to 0.0% would show up as a moved figure in
        # the record guard and cost a reader the time to find out it was
        # nothing.
        return f"{n}/{d} ({n / d:.{places}%})" if d else "0/0 (n/a)"

    sound = [s for s in scored if s.label == "valid"]
    unsound = [s for s in scored if s.label != "valid"]
    matched = [s for s in scored if s.verdict_match]
    fa = [s for s in scored if s.false_accept]
    fr = [s for s in scored if s.false_reject]
    refused_unsound = [s for s in unsound if s.actual_verdict != "SUPPORTED"]

    scoreable = [s for s in scored if s.catcher_form != CatcherForm.NOT_DECLARED.value]
    fired = [
        s for s in scoreable
        if s.declared_catcher_status in (CatcherStatus.FIRED.value, CatcherStatus.HELD.value)
    ]
    missed = [s for s in scoreable if s.declared_catcher_status == CatcherStatus.NOT_FIRED.value]

    coincidental = [s for s in scored if s.catch_type == CatchType.COINCIDENTAL.value]
    alternate = [s for s in scored if s.catch_type == CatchType.ALTERNATE_VALID.value]
    undeclared_catch = [s for s in scored if s.catch_type == CatchType.UNDECLARED.value]

    reason_specified = [s for s in scored if s.reason_match != ReasonMatch.UNSPECIFIED.value]
    reason_matched = [s for s in reason_specified if s.reason_match == ReasonMatch.MATCH.value]

    # Alternates are counted apart from primaries throughout. `alternate_only`
    # is the population a primary-rate alone would misreport: the declared
    # mechanism missed and a declared ALTERNATE caught it.
    alternate_declared = [s for s in scored if s.has_alternates]
    alternate_hit = [s for s in alternate_declared if s.alternate_fired]
    alternate_only = [
        s for s in scoreable
        if s.alternate_fired
        and s.declared_catcher_status == CatcherStatus.NOT_FIRED.value
    ]

    unknown_expected = [
        s for s in scored if s.expected_verdict == "INSUFFICIENT_EVIDENCE"
    ]
    unknown_reason_specified = [
        s for s in unknown_expected
        if s.reason_match != ReasonMatch.UNSPECIFIED.value
    ]
    under_review = [s for s in scored if s.review_status == "UNDER_REVIEW"]

    return {
        "total": total,
        "sound": len(sound),
        "unsound": len(unsound),
        # --- question 1: the verdict
        "exact_verdict_match": rate(len(matched), total),
        "catch_rate": rate(len(refused_unsound), len(unsound)),
        "false_accept": rate(len(fa), len(unsound), 2),
        "false_reject": rate(len(fr), len(sound)),
        "false_accept_ids": sorted(s.case_id for s in fa)[:60],
        "false_reject_ids": sorted(s.case_id for s in fr)[:60],
        # --- question 2: the declared mechanism
        "declared_catcher_cases": len(scoreable),
        "declared_catcher_not_declared": total - len(scoreable),
        "declared_catcher_rate": rate(len(fired), len(scoreable)),
        "declared_catcher_missed": len(missed),
        "declared_catcher_missed_ids": sorted(s.case_id for s in missed)[:60],
        # --- question 3: what a refusal actually was
        "coincidental_catches": len(coincidental),
        "coincidental_catch_ids": sorted(s.case_id for s in coincidental)[:60],
        "alternate_valid_catches": len(alternate),
        "undeclared_mechanism_catches": len(undeclared_catch),
        # --- alternates, separately from primaries. A case whose PRIMARY
        # missed and whose declared ALTERNATE fired is a success of a
        # different kind, and merging the two would recreate the collapse
        # this module exists to undo.
        "alternate_declared_cases": len(alternate_declared),
        "alternate_catcher_fired": len(alternate_hit),
        "alternate_catcher_rate": rate(len(alternate_hit), len(alternate_declared)),
        "primary_or_alternate_rate": rate(
            len(fired) + len(alternate_only), len(scoreable)
        ),
        # --- reasons, with the denominator that makes it honest
        "reason_specified_cases": len(reason_specified),
        "reason_matches": len(reason_matched),
        "reason_mismatches": len(reason_specified) - len(reason_matched),
        "reason_accuracy": rate(len(reason_matched), len(reason_specified)),
        "reason_note": (
            "ground_truth.reason is human prose and is not machine-comparable; "
            "cases carrying no expected_unknown_reason score UNSPECIFIED and "
            "are excluded from the denominator above rather than counted as "
            "failures"
        ),
        # --- unknown-verdict population, reported on its own
        "unknown_verdict_cases": len(unknown_expected),
        "unknown_verdict_match": rate(
            sum(s.verdict_match for s in unknown_expected), len(unknown_expected)
        ),
        "unknown_reason_specified": len(unknown_reason_specified),
        "unknown_reason_accuracy": rate(
            sum(
                s.reason_match == ReasonMatch.MATCH.value
                for s in unknown_reason_specified
            ),
            len(unknown_reason_specified),
        ),
        # --- truth this benchmark itself does not stand behind
        "under_review_cases": len(under_review),
        "under_review_ids": sorted(s.case_id for s in under_review)[:60],
        "oracle_classes": {
            name: sum(1 for s in scored if s.oracle == name)
            for name in sorted({s.oracle for s in scored})
        },
    }


def per_family(scored: list[ScoredCase]) -> dict:
    """The same three questions, per defect family, sorted for determinism."""
    families: dict[str, list[ScoredCase]] = {}
    for case in scored:
        families.setdefault(case.defect, []).append(case)
    out = {}
    for name in sorted(families):
        rows = families[name]
        scoreable = [
            r for r in rows if r.catcher_form != CatcherForm.NOT_DECLARED.value
        ]
        fired = [
            r for r in scoreable
            if r.declared_catcher_status
            in (CatcherStatus.FIRED.value, CatcherStatus.HELD.value)
        ]
        out[name] = {
            "total": len(rows),
            "verdict_match": sum(r.verdict_match for r in rows),
            "false_accept": sum(r.false_accept for r in rows),
            "false_reject": sum(r.false_reject for r in rows),
            "declared_catcher_cases": len(scoreable),
            "declared_catcher_fired": len(fired),
            "coincidental": sum(
                r.catch_type == CatchType.COINCIDENTAL.value for r in rows
            ),
        }
    return out
