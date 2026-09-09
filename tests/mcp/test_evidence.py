"""What a credibility evidence report may and may not claim.

The package's whole job is to let three separate judgements — was the model
applicable, did the checks pass, what produced this — be read together without
being merged, and to derive one advisory verdict from them that a caller cannot
overrule. These tests are mostly about the second half of that sentence.

The last section builds packages from **real electrothermal runs** rather than
fixtures, because a verdict derived only from hand-made inputs proves the
function and not the plumbing.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import json
import pickle

import pytest

from src.engcore.domains.electrical import material as mat
from src.engcore.domains.thermal_models import context as ctx
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.mcp import (
    EVIDENCE_PACKAGE_SCHEMA,
    AssertedContext,
    CouplingCriterion,
    CouplingEvidence,
    CredibilityEvidenceReport,
    CredibilityEvidenceError,
    CredibilityVerdict,
    ModelValidityRecord,
    classify_assessment,
    combine_assessments,
    derive_verdict,
)
from src.engcore.scientific.models.definition import (
    RangeCondition,
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityDomain,
    ValidityStatus,
)
from src.engcore.scientific.errors import (
    ModelValidityError,
    ScientificValidationError,
)
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.result import ScientificResult
from src.engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
    unverified_report,
)
from src.engcore.scientific.units.quantity import Quantity
from src.engcore.systems.electrothermal import coupled as cp

K = "kelvin"


# =====================================================================
# Fixtures — small, explicit, no hidden state
# =====================================================================

def validity(status, *, model_id="thermal.lumped", version="0.1.0", **names):
    """A record whose condition lists agree with its status.

    The package cross-checks the two — a status of IN_DOMAIN over a non-empty
    `violated` is refused — so a helper that built inconsistent records would
    only be able to test the refusal.
    """
    if not names:
        names = {
            ValidityStatus.IN_DOMAIN: {"satisfied": ("biot_number",)},
            ValidityStatus.OUTSIDE_VALIDATED_DOMAIN: {"violated": ("biot_number",)},
            ValidityStatus.UNKNOWN: {
                "unknown": ("biot_number",),
                "unknown_reasons": (
                    UnknownCondition(
                        name="biot_number", reason=UnknownReason.NOT_SUPPLIED
                    ),
                ),
            },
        }[ValidityStatus(status)]
    return ModelValidityRecord(
        model_id=model_id,
        version=version,
        assessment=ValidityAssessment(status=status, **names),
    )


IN_DOMAIN = validity(ValidityStatus.IN_DOMAIN, satisfied=("biot_number",))
OUTSIDE = validity(
    ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("biot_number",)
)
UNKNOWN = validity(
    ValidityStatus.UNKNOWN,
    unknown=("biot_number",),
    unknown_reasons=(
        UnknownCondition(name="biot_number", reason=UnknownReason.NOT_SUPPLIED),
    ),
)

PASSED = ValidationCheck(
    name="lumped_balance_residual",
    outcome=ValidationOutcome.PASS,
    establishes=ValidationLevel.DIMENSIONALLY_VALID,
    residual=1.2e-13,
    tolerance=1e-9,
)
FAILED = ValidationCheck(
    name="lumped_balance_residual",
    outcome=ValidationOutcome.FAIL,
    residual=4.0,
    tolerance=1e-9,
)
NOT_RUN = ValidationCheck(
    name="cross_solver_agreement",
    outcome=ValidationOutcome.NOT_RUN,
    detail="no second solver was available",
)
WARNED = ValidationCheck(
    name="tolerance_margin", outcome=ValidationOutcome.WARNING
)

#: Both models are listed because the package requires every validity record
#: to name a model the provenance says took part.
PROVENANCE = ProvenanceRecord(
    run_id="evidence-test",
    software_version="engcore.mcp/0.1.0",
    models=(("thermal.lumped", "0.1.0"), ("electrical.material", "0.1.0")),
    inputs={"heat_capacity": Quantity(2.5, "joule/kelvin")},
    assumptions=("lumped body: one uniform temperature",),
)

#: A single-model provenance, for the cases that assess exactly one model.
ONE_MODEL_PROVENANCE = dataclasses.replace(
    PROVENANCE, models=(("thermal.lumped", "0.1.0"),)
)

VALUES = {"final_temperature": Quantity(338.577018, K)}

DECLARATION = AssertedContext(
    source="LumpedApplicabilityDeclaration",
    payload={"convection_regime": "forced", "melting_temperature": None},
    description="why the caller believes a 60 K constant-hA span is credible",
)


def package(
    *,
    validity_records=(IN_DOMAIN,),
    checks=(PASSED,),
    declarations=(),
    provenance=None,
    **kw,
):
    """A package whose provenance lists exactly the models being assessed.

    Built that way so a test that means to exercise a verdict rule is not
    tripped by the unassessed-model rule, which has its own tests below.
    """
    records = tuple(validity_records)
    if provenance is None:
        provenance = dataclasses.replace(
            PROVENANCE, models=tuple(r.key for r in records)
        )
    return CredibilityEvidenceReport(
        run_id="evidence-test",
        values=VALUES,
        provenance=provenance,
        validity=records,
        validation=tuple(checks),
        declarations=tuple(declarations),
        **kw,
    )


# =====================================================================
# The verdict rules
# =====================================================================

def test_everything_in_domain_and_checked_is_supported():
    assert package().verdict is CredibilityVerdict.SUPPORTED
    assert package().is_supported


def test_unknown_validity_is_insufficient_evidence():
    """A condition nobody supplied the input for is a gap, not a pass."""
    pkg = package(validity_records=(UNKNOWN,))
    assert pkg.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert pkg.unknown_conditions == (("thermal.lumped", "biot_number"),)


def test_unknown_validity_can_never_produce_supported():
    """Exhaustive over every outcome combination, not one example.

    UNKNOWN validity must dominate every arrangement of checks that does not
    itself force NOT_SUPPORTED. If any combination let it reach SUPPORTED, a
    caller could bury a missing declaration under a pile of passing checks.
    """
    outcomes = [PASSED, FAILED, NOT_RUN, WARNED]
    for size in range(len(outcomes) + 1):
        for combo in itertools.combinations(outcomes, size):
            # PASSED and FAILED share a name; the package refuses duplicates,
            # so rename as we go rather than skipping the case.
            checks = tuple(
                dataclasses.replace(c, name=f"{c.name}_{i}")
                for i, c in enumerate(combo)
            )
            verdict = package(validity_records=(UNKNOWN,), checks=checks).verdict
            assert verdict is not CredibilityVerdict.SUPPORTED, combo


def test_outside_validated_domain_is_not_supported_and_names_the_condition():
    pkg = package(validity_records=(OUTSIDE,))
    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert pkg.violated_conditions == (("thermal.lumped", "biot_number"),)
    # the condition name survives serialization, which is where a reader meets it
    assert "biot_number" in json.dumps(pkg.to_dict())


def test_a_failed_check_is_not_supported_even_when_all_validity_is_in_domain():
    """An applicable model whose check failed is still a failure."""
    pkg = package(checks=(FAILED,))
    assert all(r.status is ValidityStatus.IN_DOMAIN for r in pkg.validity)
    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert pkg.failed_checks == ("lumped_balance_residual",)


def test_a_not_run_check_is_insufficient_evidence_even_when_nothing_failed():
    """The NOT_RUN mechanism, carried one level up.

    Everything that ran, passed. The verdict is still not SUPPORTED, because a
    check that never executed cannot contribute evidence — which is the rule
    the core states and the reason NOT_RUN exists as an outcome at all.
    """
    pkg = package(checks=(PASSED, NOT_RUN))
    assert pkg.failed_checks == ()
    assert pkg.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert pkg.not_run_checks == ("cross_solver_agreement",)


def test_not_supported_takes_precedence_over_insufficient_evidence():
    """A violated bound plus a missing declaration is NOT_SUPPORTED.

    The precedence exists because the two verdicts recommend opposite actions.
    Gathering the missing input cannot rescue a model already known not to
    apply, and reporting the gap first would let a caller bury a violated bound
    behind an unrelated omission.
    """
    pkg = package(validity_records=(UNKNOWN, dataclasses.replace(
        OUTSIDE, model_id="electrical.material"
    )))
    assert {r.status for r in pkg.validity} == {
        ValidityStatus.UNKNOWN,
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
    }
    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED


def test_a_failed_check_outranks_an_unknown_validity_too():
    """The other half of the precedence rule."""
    assert (
        package(validity_records=(UNKNOWN,), checks=(FAILED,)).verdict
        is CredibilityVerdict.NOT_SUPPORTED
    )


def test_a_warning_does_not_change_the_verdict_and_stays_visible():
    """WARNING ran and produced evidence; it is not a failure and not a gap.

    Deliberate: folding it into the verdict would either overstate it as
    NOT_SUPPORTED or need a fourth value. It stays in the carried checks for
    the reader who has to weigh it.
    """
    pkg = package(checks=(PASSED, WARNED))
    assert pkg.verdict is CredibilityVerdict.SUPPORTED
    assert "tolerance_margin" in {c.name for c in pkg.validation}
    assert pkg.validation_report().warnings != ()


def test_an_empty_package_is_insufficient_evidence_not_supported():
    """No checks and no validity records means nothing was established.

    The alternative — vacuous SUPPORTED — is the NOT_RUN failure mode
    reintroduced at the package level.
    """
    assert package(checks=()).verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert package(validity_records=()).verdict is (
        CredibilityVerdict.INSUFFICIENT_EVIDENCE
    )
    assert package(validity_records=(), checks=()).verdict is (
        CredibilityVerdict.INSUFFICIENT_EVIDENCE
    )


def test_the_verdict_rules_are_total_and_deterministic():
    """Every combination of statuses and outcomes yields exactly one verdict.

    Checked against an independently written oracle rather than against the
    implementation restated — 8 status subsets x 16 outcome subsets.
    """
    statuses = [
        ValidityStatus.IN_DOMAIN,
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
        ValidityStatus.UNKNOWN,
    ]
    outcomes = [
        ValidationOutcome.PASS,
        ValidationOutcome.FAIL,
        ValidationOutcome.WARNING,
        ValidationOutcome.NOT_RUN,
    ]

    def oracle(status_set, outcome_set):
        if ValidityStatus.OUTSIDE_VALIDATED_DOMAIN in status_set:
            return CredibilityVerdict.NOT_SUPPORTED
        if ValidationOutcome.FAIL in outcome_set:
            return CredibilityVerdict.NOT_SUPPORTED
        if ValidityStatus.UNKNOWN in status_set:
            return CredibilityVerdict.INSUFFICIENT_EVIDENCE
        if ValidationOutcome.NOT_RUN in outcome_set:
            return CredibilityVerdict.INSUFFICIENT_EVIDENCE
        if not status_set:
            return CredibilityVerdict.INSUFFICIENT_EVIDENCE
        # SUPPORTED needs a level, and only a PASS can carry one. An empty
        # outcome set attains nothing, so it falls out of this branch rather
        # than needing its own.
        if ValidationOutcome.PASS not in outcome_set:
            return CredibilityVerdict.INSUFFICIENT_EVIDENCE
        return CredibilityVerdict.SUPPORTED

    seen = set()
    for s_size in range(len(statuses) + 1):
        for s_combo in itertools.combinations(statuses, s_size):
            for o_size in range(len(outcomes) + 1):
                for o_combo in itertools.combinations(outcomes, o_size):
                    records = tuple(
                        validity(s, model_id=f"m{i}") for i, s in enumerate(s_combo)
                    )
                    # A PASS carries a level; nothing else can. That is the
                    # rule under test, so the fixture has to express it.
                    checks = tuple(
                        ValidationCheck(
                            name=f"c{i}",
                            outcome=o,
                            establishes=(
                                ValidationLevel.DIMENSIONALLY_VALID
                                if o is ValidationOutcome.PASS
                                else None
                            ),
                            evidence=("fixture:metric=dimensionless declared by the model record",),
                        )
                        for i, o in enumerate(o_combo)
                    )
                    got = derive_verdict(validity=records, validation=checks)
                    assert got is oracle(set(s_combo), set(o_combo)), (
                        s_combo,
                        o_combo,
                    )
                    seen.add(got)
    # all three verdicts are reachable; none is dead code
    assert seen == set(CredibilityVerdict)


def test_the_verdict_does_not_depend_on_the_order_of_its_inputs():
    other = dataclasses.replace(UNKNOWN, model_id="electrical.material")
    forward = package(
        validity_records=(IN_DOMAIN, other), provenance=PROVENANCE
    )
    reverse = package(
        validity_records=(other, IN_DOMAIN), provenance=PROVENANCE
    )
    assert forward.verdict is reverse.verdict
    # and equal content serializes identically, so order is not readable as data
    assert forward.to_dict() == reverse.to_dict()


# =====================================================================
# The declaration is context, not evidence
# =====================================================================

def test_the_declaration_changes_no_verdict():
    """Two packages differing only in declarations produce identical verdicts.

    The structural reason, not just the observed one: `declarations` is not a
    parameter of derive_verdict, so it is not in scope of the function that
    decides a verdict.
    """
    for records, checks in (
        ((IN_DOMAIN,), (PASSED,)),
        ((UNKNOWN,), (PASSED,)),
        ((OUTSIDE,), (PASSED,)),
        ((IN_DOMAIN,), (FAILED,)),
        ((IN_DOMAIN,), (NOT_RUN,)),
    ):
        bare = package(validity_records=records, checks=checks)
        declared = package(
            validity_records=records, checks=checks, declarations=(DECLARATION,)
        )
        assert bare.verdict is declared.verdict
    assert "declarations" not in derive_verdict.__code__.co_varnames


def test_the_declaration_is_marked_as_caller_asserted_in_the_serialized_form():
    """The marking must survive to_dict, or a JSON reader never sees it."""
    entry = package(declarations=(DECLARATION,)).to_dict()["declarations"][0]
    assert entry["caller_asserted"] is True
    assert entry["consumed_by_verdict"] is False
    assert entry["source"] == "LumpedApplicabilityDeclaration"
    # carried verbatim, not summarised
    assert entry["payload"]["convection_regime"] == "forced"


def test_a_declaration_payload_must_survive_the_record_it_is_stored_in():
    with pytest.raises(CredibilityEvidenceError):
        AssertedContext(source="x", payload={"q": Quantity(1.0, K)})
    with pytest.raises(CredibilityEvidenceError):
        AssertedContext(source="  ", payload={})


# =====================================================================
# A verdict cannot be asserted — structurally
# =====================================================================

def test_the_verdict_is_not_a_field_and_cannot_be_constructed():
    """Not policed by a check — absent from the constructor entirely."""
    assert "verdict" not in CredibilityEvidenceReport.__dataclass_fields__
    assert isinstance(
        type(package()).__dict__["verdict"], property
    )
    with pytest.raises(TypeError):
        CredibilityEvidenceReport(
            run_id="r",
            values={},
            verdict=CredibilityVerdict.SUPPORTED,
        )


def test_the_verdict_cannot_be_replaced_or_written_onto_an_instance():
    pkg = package(validity_records=(OUTSIDE,))
    with pytest.raises(TypeError):
        dataclasses.replace(pkg, verdict=CredibilityVerdict.SUPPORTED)
    with pytest.raises(AttributeError):
        object.__setattr__(pkg, "verdict", CredibilityVerdict.SUPPORTED)
    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED


def test_a_serialized_verdict_inconsistent_with_the_contents_is_rejected():
    """The from_dict half: a hand-edited record cannot smuggle a verdict in.

    Mirrors ValidationReport.from_dict's treatment of attained_levels — the
    derived field in a payload is advisory, recomputed and verified.
    """
    payload = package(validity_records=(OUTSIDE,)).to_dict()
    assert payload["verdict"] == CredibilityVerdict.NOT_SUPPORTED.value
    payload["verdict"] = CredibilityVerdict.SUPPORTED.value
    with pytest.raises(CredibilityEvidenceError) as caught:
        CredibilityEvidenceReport.from_dict(payload)
    assert "does not match" in str(caught.value)


def test_a_payload_with_no_verdict_key_is_accepted_and_derives_its_own():
    payload = package().to_dict()
    del payload["verdict"]
    assert CredibilityEvidenceReport.from_dict(payload).verdict is CredibilityVerdict.SUPPORTED


def test_poisoning_the_instance_dict_does_not_shadow_the_property():
    """A property is a data descriptor; the instance dict loses to it."""
    pkg = package(validity_records=(OUTSIDE,))
    pkg.__dict__["verdict"] = CredibilityVerdict.SUPPORTED
    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert pkg.to_dict()["verdict"] == CredibilityVerdict.NOT_SUPPORTED.value


def test_pickling_and_copying_carry_the_honest_verdict():
    pkg = package(validity_records=(OUTSIDE,))
    assert pickle.loads(pickle.dumps(pkg)).verdict is CredibilityVerdict.NOT_SUPPORTED
    assert copy.deepcopy(pkg).verdict is CredibilityVerdict.NOT_SUPPORTED


def test_a_subclass_can_lie_in_process_but_not_across_a_serialization_boundary():
    """The honest limit of the guarantee, pinned so it is not overstated.

    Nothing stops a subclass overriding the property — Python has no mechanism
    for that and pretending otherwise would be theatre. What matters is that
    the lie cannot be persisted, sent, or handed to a second reader: the real
    ``from_dict`` recomputes the verdict from the contents and refuses.
    """
    class Liar(CredibilityEvidenceReport):
        @property
        def verdict(self):
            return CredibilityVerdict.SUPPORTED

    liar = Liar(
        run_id="r",
        values=VALUES,
        validity=(OUTSIDE,),
        validation=(PASSED,),
        provenance=PROVENANCE,
    )
    assert liar.verdict is CredibilityVerdict.SUPPORTED          # in-process, yes
    with pytest.raises(CredibilityEvidenceError):                  # across a boundary, no
        CredibilityEvidenceReport.from_dict(liar.to_dict())


def test_the_verdict_tracks_the_contents_rather_than_being_stored():
    """Derived-on-access means there is no stale copy to drift.

    Rewriting a carried assessment through ``object.__setattr__`` — the escape
    hatch that defeats every frozen record in this repository, not just these —
    moves the verdict *with* the contents. That is the property worth having: a
    package is never internally inconsistent. A stored verdict field would have
    kept reporting NOT_SUPPORTED over contents that no longer said so.
    """
    pkg = package(validity_records=(OUTSIDE,))
    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED
    object.__setattr__(
        pkg.validity[0].assessment, "status", ValidityStatus.IN_DOMAIN
    )
    object.__setattr__(pkg.validity[0].assessment, "violated", ())
    # The condition moves from violated to satisfied rather than vanishing: an
    # assessment naming no condition at all evaluated nothing, and since F09
    # that is UNKNOWN on both sides of this boundary rather than IN_DOMAIN.
    object.__setattr__(
        pkg.validity[0].assessment, "satisfied", ("biot_number",)
    )
    assert pkg.verdict is CredibilityVerdict.SUPPORTED
    # and the serialized form agrees with the contents, not with history
    assert pkg.to_dict()["verdict"] == CredibilityVerdict.SUPPORTED.value
    assert CredibilityEvidenceReport.from_dict(pkg.to_dict()).verdict is (
        CredibilityVerdict.SUPPORTED
    )


def test_the_package_copies_the_mappings_it_is_given():
    """A caller's later mutation must not reach inside a constructed package."""
    values = {"T": Quantity(300.0, K)}
    pkg = CredibilityEvidenceReport(run_id="r", values=values, provenance=PROVENANCE)
    values["INJECTED"] = Quantity(1.0, K)
    assert "INJECTED" not in pkg.values

    payload = {"convection_regime": "forced"}
    context = AssertedContext(source="s", payload=payload)
    payload["convection_regime"] = "tampered"
    assert context.payload["convection_regime"] == "forced"


def test_an_unrecognised_validity_status_is_refused_rather_than_read_as_clean():
    """An unrecognised status must never reach a verdict.

    It would match neither the NOT_SUPPORTED nor the INSUFFICIENT_EVIDENCE
    branch and fall through to SUPPORTED — the most favourable verdict
    available, earned by malformation.

    **The refusal moved into the core** and this test moved with it. It used to
    be this package's job because ``ValidityAssessment`` coerced nothing, so a
    bogus status could be constructed and had to be caught on arrival here. The
    core now refuses it at construction, which is strictly earlier and strictly
    wider: an assessment reaches plenty of readers that never cross this
    boundary, and every one of them used to be exposed.
    """
    with pytest.raises(ModelValidityError):
        ValidityAssessment(status="probably_fine")

    # And therefore no such record can be built to hand to this boundary at
    # all. Asserted rather than assumed: "the input cannot be constructed" is
    # the whole reason the boundary check below is no longer reachable.
    with pytest.raises(ModelValidityError):
        ModelValidityRecord(
            model_id="m",
            version="1",
            assessment=ValidityAssessment(status="probably_fine"),
        )
    # a correct status supplied as a bare string is still accepted
    assert ModelValidityRecord(
        model_id="m", version="1",
        assessment=ValidityAssessment(
            status="in_domain", satisfied=("biot_number",)
        ),
    ).status == ValidityStatus.IN_DOMAIN


# =====================================================================
# Record hygiene
# =====================================================================

def test_an_unassessed_model_that_took_part_is_insufficient_evidence():
    """The per-model form of "nobody asked whether the model applied".

    Two models ran; one was assessed and is IN_DOMAIN. A rule that only counts
    validity records sees a non-empty list and says SUPPORTED. The provenance
    knows better, and it is already in the package.
    """
    pkg = package(validity_records=(IN_DOMAIN,), provenance=PROVENANCE)
    assert pkg.unassessed_models == (("electrical.material", "0.1.0"),)
    assert pkg.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    # assess the second model and the gap closes
    both = package(
        validity_records=(
            IN_DOMAIN,
            dataclasses.replace(IN_DOMAIN, model_id="electrical.material"),
        ),
        provenance=PROVENANCE,
    )
    assert both.unassessed_models == ()
    assert both.verdict is CredibilityVerdict.SUPPORTED


def test_a_validity_record_for_a_model_that_did_not_run_is_refused():
    """An honest assessment of the wrong model is not evidence about these values.

    Without this, a caller holding an unassessed thermal run could attach a
    real IN_DOMAIN assessment of some unrelated model and turn
    INSUFFICIENT_EVIDENCE into SUPPORTED.
    """
    with pytest.raises(CredibilityEvidenceError) as caught:
        package(
            validity_records=(
                dataclasses.replace(IN_DOMAIN, model_id="kinetics.cstr"),
            ),
            provenance=ONE_MODEL_PROVENANCE,
        )
    assert "kinetics.cstr" in str(caught.value)


def test_a_record_whose_status_contradicts_its_own_conditions_is_refused():
    """IN_DOMAIN over a non-empty `violated` would report SUPPORTED.

    **The cross-check moved into the core**, and this test moved with it.
    ``ValidityAssessment`` used to enforce no relation between its status and
    its condition lists, so this package cross-checked on arrival. The core now
    refuses the contradiction at construction, against the same classification
    ``ValidityDomain.assess`` performs, so every assessment the core actually
    produced still passes untouched and a hand-built one cannot be built at
    all — which is what makes this boundary safe rather than merely careful.

    The fourth case is the quiet one: OUTSIDE_VALIDATED_DOMAIN over an empty
    ``violated`` claims a finding nothing recorded.
    """
    for status, names in (
        (ValidityStatus.IN_DOMAIN, {"violated": ("biot_number",)}),
        (
            ValidityStatus.IN_DOMAIN,
            {
                "unknown": ("biot_number",),
                "unknown_reasons": (
                    UnknownCondition(
                        name="biot_number", reason=UnknownReason.NOT_SUPPLIED
                    ),
                ),
            },
        ),
        (ValidityStatus.UNKNOWN, {"violated": ("biot_number",)}),
        (ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, {"satisfied": ("biot_number",)}),
    ):
        with pytest.raises(ModelValidityError) as caught:
            ModelValidityRecord(
                model_id="m",
                version="1",
                assessment=ValidityAssessment(status=status, **names),
            )
        assert "contradict" in str(caught.value)

    # The assessments the core really emits are unaffected, which is the half
    # a refusal this strict has to keep proving.
    assert ValidityAssessment(
        status=ValidityStatus.IN_DOMAIN, satisfied=("biot_number",)
    ).status is ValidityStatus.IN_DOMAIN
    assert ValidityAssessment(
        status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("biot_number",)
    ).status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    # A domain with no conditions: UNKNOWN over three empty lists, and still
    # legitimate. Absence of declared limits is not evidence of unlimited
    # validity, so this must not be swept up by the rule above.
    assert ValidityAssessment(
        status=ValidityStatus.UNKNOWN
    ).status is ValidityStatus.UNKNOWN


def test_a_status_given_as_a_bare_string_is_normalised_not_merely_probed():
    """Probing without writing back leaves `.status` a str, and to_dict crashes.

    `ValidityAssessment.to_dict` does `self.status.value`, so a record that
    merely validated the string would construct fine and then fail to
    serialize with a bare AttributeError.
    """
    record = ModelValidityRecord(
        model_id="thermal.lumped",
        version="0.1.0",
        assessment=ValidityAssessment(status="in_domain", satisfied=("a",)),
    )
    assert record.status is ValidityStatus.IN_DOMAIN
    assert isinstance(record.assessment.status, ValidityStatus)
    assert record.to_dict()["assessment"]["status"] == "in_domain"


def test_derive_verdict_fails_closed_when_called_on_its_own():
    """It is exported and documented as usable standalone, so it must be safe.

    The guard in ModelValidityRecord protects packages; this function is
    reachable without one.
    """
    import types

    junk = types.SimpleNamespace(
        assessment=types.SimpleNamespace(status="probably_fine")
    )
    with pytest.raises(CredibilityEvidenceError):
        derive_verdict(validity=[junk], validation=[])


def test_required_levels_turn_an_unattained_claim_into_a_gap():
    """The caller's own bar, checked against the core's attained_levels.

    SUPPORTED does not by itself require any level to have been attained — see
    the verdict docstring — so a study that needs one says so here.
    """
    pkg = package(checks=(PASSED,), required_levels=(ValidationLevel.DIMENSIONALLY_VALID,))
    assert pkg.attained_levels == frozenset({ValidationLevel.DIMENSIONALLY_VALID})
    assert pkg.missing_required_levels == ()
    assert pkg.verdict is CredibilityVerdict.SUPPORTED

    demanding = package(
        checks=(PASSED,),
        required_levels=(ValidationLevel.EXPERIMENTALLY_VALIDATED,),
    )
    assert demanding.missing_required_levels == (
        ValidationLevel.EXPERIMENTALLY_VALIDATED,
    )
    assert demanding.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_a_clean_package_that_attains_no_level_is_insufficient_evidence():
    """Absence of an objection is not evidence, one level up from NOT_RUN.

    Everything here is clean: validity is IN_DOMAIN, nothing failed, nothing
    was skipped. The single check ran and passed — and established nothing, so
    the package has produced no evidence for anything. It has only failed to
    object, which is exactly what NOT_RUN exists to stop being read as a pass.
    """
    bare = ValidationCheck(name="ran", outcome=ValidationOutcome.PASS)
    pkg = package(checks=(bare,))

    # the package really is clean by every other measure
    assert pkg.validity[0].assessment.status is ValidityStatus.IN_DOMAIN
    assert pkg.failed_checks == ()
    assert pkg.not_run_checks == ()
    assert pkg.violated_conditions == () and pkg.unknown_conditions == ()

    assert pkg.attained_levels == frozenset()
    assert pkg.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert not pkg.is_supported
    assert pkg.to_dict()["verdict_qualifiers"]["attained_levels"] == []


def test_one_attained_level_is_what_separates_supported_from_the_gap():
    """The same package, differing only in whether a level was established."""
    without = package(
        checks=(ValidationCheck(name="ran", outcome=ValidationOutcome.PASS),)
    )
    with_level = package(
        checks=(
            ValidationCheck(
                name="ran",
                outcome=ValidationOutcome.PASS,
                establishes=ValidationLevel.DIMENSIONALLY_VALID,
                evidence=("fixture:metric=dimensionless declared by the model record",),
            ),
        )
    )
    assert without.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert with_level.verdict is CredibilityVerdict.SUPPORTED


def test_a_level_established_by_a_check_that_did_not_pass_does_not_count():
    """`attained` is the core's definition: passing checks only."""
    warned = package(
        checks=(
            ValidationCheck(
                name="ran",
                outcome=ValidationOutcome.WARNING,
                establishes=ValidationLevel.DIMENSIONALLY_VALID,
                evidence=("fixture:metric=dimensionless declared by the model record",),
            ),
        )
    )
    assert warned.attained_levels == frozenset()
    assert warned.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_the_assemblers_notes_never_reach_the_cores_validation_report():
    """`notes` belongs to whoever built the package; the solver has its own."""
    result = ScientificResult(
        result_id="r1",
        values=VALUES,
        provenance=ONE_MODEL_PROVENANCE,
        validation=ValidationReport(
            checks=(PASSED,), notes="residual measured against the balance"
        ),
    )
    pkg = CredibilityEvidenceReport.from_result(
        result, validity=(IN_DOMAIN,), notes="reviewed and accepted by J. Smith"
    )
    assert pkg.notes == "reviewed and accepted by J. Smith"
    assert pkg.validation_notes == "residual measured against the balance"
    assert pkg.validation_report().notes == "residual measured against the balance"


def test_a_declaration_may_not_embed_a_core_evidence_record():
    """A check-shaped object under the not-evidence markings misleads a scanner."""
    with pytest.raises(CredibilityEvidenceError) as caught:
        AssertedContext(
            source="s",
            payload={"cross_solver_agreement": PASSED.to_dict()},
        )
    assert "validation_check" in str(caught.value)
    # nested, not just at the top level
    with pytest.raises(CredibilityEvidenceError):
        AssertedContext(source="s", payload={"a": {"b": [PASSED.to_dict()]}})
    # an ordinary declaration payload is untouched
    AssertedContext(source="s", payload={"q": Quantity(1.0, K).to_dict()})


def test_a_warning_is_reachable_without_filtering_the_check_list_by_hand():
    pkg = package(checks=(PASSED, WARNED))
    assert pkg.warning_checks == ("tolerance_margin",)
    assert pkg.to_dict()["verdict_qualifiers"]["warning_checks"] == [
        "tolerance_margin"
    ]


def test_a_package_refuses_two_verdicts_for_one_model():
    with pytest.raises(CredibilityEvidenceError):
        package(validity_records=(IN_DOMAIN, OUTSIDE))


def test_a_package_refuses_duplicate_check_names():
    with pytest.raises(CredibilityEvidenceError):
        package(checks=(PASSED, dataclasses.replace(FAILED, name=PASSED.name)))


def test_a_package_refuses_a_bare_number_as_a_value():
    with pytest.raises(CredibilityEvidenceError):
        CredibilityEvidenceReport(run_id="r", values={"T": 300.0}, provenance=PROVENANCE)


def test_a_package_refuses_an_unattributable_run():
    with pytest.raises(CredibilityEvidenceError):
        CredibilityEvidenceReport(run_id="   ", values={}, provenance=PROVENANCE)


# =====================================================================
# Round trip
# =====================================================================

def test_the_package_round_trips_through_its_serialized_form():
    """Everything, including the NOT_RUN check and the declarations."""
    pkg = package(
        validity_records=(
            IN_DOMAIN,
            dataclasses.replace(UNKNOWN, model_id="electrical.material"),
        ),
        checks=(PASSED, NOT_RUN, WARNED),
        declarations=(DECLARATION,),
    )
    payload = json.loads(json.dumps(pkg.to_dict(), sort_keys=True))
    restored = CredibilityEvidenceReport.from_dict(payload)

    assert restored.to_dict() == pkg.to_dict()
    assert restored.run_id == pkg.run_id
    assert restored.values == pkg.values
    assert restored.validity == pkg.validity
    assert restored.validation == pkg.validation
    assert restored.declarations == pkg.declarations
    assert restored.verdict is pkg.verdict
    # the two things most easily lost in a round trip
    assert restored.not_run_checks == ("cross_solver_agreement",)
    assert restored.declarations[0].payload == DECLARATION.payload
    assert payload["schema"] == EVIDENCE_PACKAGE_SCHEMA


def test_provenance_in_the_package_equals_the_source_record_exactly():
    pkg = package(provenance=ONE_MODEL_PROVENANCE)
    assert pkg.provenance == ONE_MODEL_PROVENANCE
    assert pkg.provenance.to_dict() == ONE_MODEL_PROVENANCE.to_dict()
    restored = CredibilityEvidenceReport.from_dict(pkg.to_dict())
    assert restored.provenance == ONE_MODEL_PROVENANCE


def test_a_package_cannot_exist_without_provenance():
    """Stricter than ScientificResult would need, and for the same reason.

    A package is a stronger claim than a result, so it cannot have a weaker
    attribution rule. An optional-and-inert provenance would let an
    unattributed package report SUPPORTED.
    """
    with pytest.raises(TypeError):
        CredibilityEvidenceReport(run_id="r", values={})
    with pytest.raises(CredibilityEvidenceError):
        CredibilityEvidenceReport(run_id="r", values={}, provenance={"run_id": "r"})


# =====================================================================
# Assembly from a ScientificResult
# =====================================================================

def test_from_result_carries_the_checks_that_never_ran():
    """The aggregate status would have hidden this; the checks do not."""
    result = ScientificResult(
        result_id="r1",
        values=VALUES,
        provenance=PROVENANCE,
        validation=unverified_report("no solver was available"),
    )
    pkg = CredibilityEvidenceReport.from_result(result, validity=(IN_DOMAIN,))
    assert pkg.not_run_checks == ("validation_performed",)
    assert pkg.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert pkg.provenance == result.provenance
    assert pkg.values == result.values


def test_from_result_with_no_validity_is_unknown_rather_than_clean():
    """A result carrying no assessment produces a package that says so.

    The result *can* carry validity now, and an empty mapping there means
    nobody asked — which is what this package reports, rather than reading the
    silence as clean.
    """
    result = ScientificResult(
        result_id="r1",
        values=VALUES,
        provenance=PROVENANCE,
        validation=ValidationReport(checks=(PASSED,)),
    )
    assert result.validity == {}
    pkg = CredibilityEvidenceReport.from_result(result)
    assert pkg.validity == ()
    assert pkg.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


# =====================================================================
# Validity carried on the result itself
# =====================================================================

def result_carrying(assessments, *, checks=(PASSED,)):
    """A result whose own ``validity`` mapping holds the assessments."""
    return ScientificResult(
        result_id="carried",
        values=VALUES,
        provenance=ONE_MODEL_PROVENANCE,
        models=tuple(ONE_MODEL_PROVENANCE.models),
        validation=ValidationReport(checks=tuple(checks)),
        validity=assessments,
        validity_not_assessed={
            model_id: "fixture: this test carries no verdict for this model"
            for model_id, _version in ONE_MODEL_PROVENANCE.models
            if model_id not in assessments
        },
    )


def only_model():
    model_id, _version = ONE_MODEL_PROVENANCE.models[0]
    return model_id


def test_a_package_reads_the_validity_the_result_carries():
    """The gap NEEDS.md §1.1 records, closed at the point it was felt.

    No caller argument at all: the producer of the result made the assessment,
    the result carried it, and the package found it there.
    """
    carried = result_carrying({only_model(): IN_DOMAIN.assessment})
    pkg = CredibilityEvidenceReport.from_result(carried)

    assert [record.model_id for record in pkg.validity] == [only_model()]
    assert pkg.validity[0].assessment == IN_DOMAIN.assessment
    assert pkg.validity[0].version == ONE_MODEL_PROVENANCE.models[0][1]
    assert pkg.unassessed_models == ()
    assert pkg.verdict is CredibilityVerdict.SUPPORTED


def test_the_carried_verdict_reaches_the_verdict_rules_unchanged():
    """A violated bound carried on the result is NOT_SUPPORTED, as ever.

    ``derive_verdict`` did not move: it reads this report's own field, which is
    still the transport. What changed is where that field can be filled from.
    """
    carried = result_carrying(
        {
            only_model(): ValidityAssessment(
                status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
                violated=("biot_number",),
            )
        }
    )
    pkg = CredibilityEvidenceReport.from_result(carried)
    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert pkg.violated_conditions == ((only_model(), "biot_number"),)


def test_the_callers_records_still_work_when_the_result_carries_none():
    """The older path is not deprecated: a producer may not hold the context."""
    result = ScientificResult(
        result_id="r1",
        values=VALUES,
        provenance=ONE_MODEL_PROVENANCE,
        validation=ValidationReport(checks=(PASSED,)),
    )
    assert result.validity == {}
    pkg = CredibilityEvidenceReport.from_result(result, validity=(IN_DOMAIN,))
    assert pkg.validity == (IN_DOMAIN,)
    assert pkg.verdict is CredibilityVerdict.SUPPORTED


def test_the_two_sources_merge_when_they_name_different_models():
    """Neither source is authoritative; together they cover the run."""
    two_models = ScientificResult(
        result_id="two",
        values=VALUES,
        provenance=PROVENANCE,
        models=tuple(PROVENANCE.models),
        validation=ValidationReport(checks=(PASSED,)),
        validity={PROVENANCE.models[0][0]: IN_DOMAIN.assessment},
        validity_not_assessed={
            PROVENANCE.models[1][0]: (
                "fixture: the caller supplies this model's verdict, not the "
                "result"
            )
        },
    )
    other_id, other_version = PROVENANCE.models[1]
    pkg = CredibilityEvidenceReport.from_result(
        two_models,
        validity=(
            ModelValidityRecord(
                model_id=other_id,
                version=other_version,
                assessment=IN_DOMAIN.assessment,
            ),
        ),
    )
    assert {record.model_id for record in pkg.validity} == {
        m for m, _ in PROVENANCE.models
    }
    assert pkg.unassessed_models == ()


def test_the_same_verdict_from_both_sources_is_not_a_duplicate():
    """Saying it twice identically is redundant, not contradictory."""
    carried = result_carrying({only_model(): IN_DOMAIN.assessment})
    pkg = CredibilityEvidenceReport.from_result(
        carried,
        validity=(
            ModelValidityRecord(
                model_id=only_model(),
                version=ONE_MODEL_PROVENANCE.models[0][1],
                assessment=IN_DOMAIN.assessment,
            ),
        ),
    )
    assert len(pkg.validity) == 1


def test_two_different_verdicts_for_one_model_are_refused_not_ranked():
    """Precedence would let either replace the other with nothing to say so.

    The failure mode this prevents is specific: a caller passing a clean
    assessment over a result that carries a violated one, and the package
    reporting the clean answer because the caller's argument won.
    """
    carried = result_carrying({only_model(): IN_DOMAIN.assessment})
    with pytest.raises(CredibilityEvidenceError) as excinfo:
        CredibilityEvidenceReport.from_result(
            carried,
            validity=(
                ModelValidityRecord(
                    model_id=only_model(),
                    version=ONE_MODEL_PROVENANCE.models[0][1],
                    assessment=ValidityAssessment(
                        status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
                        violated=("biot_number",),
                    ),
                ),
            ),
        )
    assert "two different validity verdicts" in str(excinfo.value)


def test_a_carried_unknown_is_a_gap_and_a_missing_key_is_a_different_gap():
    """Both are INSUFFICIENT_EVIDENCE and they are not the same finding.

    The carried UNKNOWN names the condition nobody declared. The absent key
    produces an unassessed model. A reader repairs them differently, and the
    package keeps them apart because the result did.
    """
    unknown = CredibilityEvidenceReport.from_result(
        result_carrying(
            {
                only_model(): ValidityAssessment(
                    status=ValidityStatus.UNKNOWN,
                    unknown=("emissivity",),
                    unknown_reasons=(
                        UnknownCondition(
                            name="emissivity",
                            reason=UnknownReason.NOT_SUPPLIED,
                        ),
                    ),
                )
            }
        )
    )
    absent = CredibilityEvidenceReport.from_result(result_carrying({}))

    assert unknown.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert absent.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert unknown.unknown_conditions == ((only_model(), "emissivity"),)
    assert unknown.unassessed_models == ()
    assert absent.unknown_conditions == ()
    assert absent.unassessed_models == tuple(ONE_MODEL_PROVENANCE.models)


def test_the_carried_checks_go_back_into_the_cores_own_report_type():
    pkg = package(checks=(PASSED, NOT_RUN))
    report = pkg.validation_report()
    assert isinstance(report, ValidationReport)
    assert report.attained_levels == frozenset(
        {ValidationLevel.DIMENSIONALLY_VALID}
    )
    assert report.not_run != ()


# =====================================================================
# Real electrothermal runs — not fixtures
# =====================================================================

def conductor():
    return mat.TemperatureDependentConductor(
        component_id="R1",
        reference_resistance=Quantity(10.0, "ohm"),
        temperature_coefficient=Quantity(0.00393, "1/kelvin"),
        reference_temperature=Quantity(293.15, K),
    )


def thermal_body(declaration):
    return lump.ThermalBody(
        body_id="R1",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(300.0, K),
        duration=Quantity(120.0, "second"),
        applicability=declaration,
    )


#: Every lumped condition decidable and satisfied at the coupled operating
#: point (the body settles towards 342.43 K, a 42.43 K rise over ambient).
APPLICABLE = ctx.LumpedApplicabilityDeclaration(
    characteristic_length=Quantity(0.002, "meter"),
    surface_area=Quantity(0.01, "meter**2"),
    body_conductivity=Quantity(200.0, "watt/meter/kelvin"),
    surface_emissivity=Quantity(0.05, "dimensionless"),
    convection_regime=ctx.FORCED_CONVECTION,
    conductance_excursion_bound=Quantity(60.0, K),
    capacity_excursion_bound=Quantity(100.0, K),
    melting_temperature=Quantity(900.0, K),
    fluid_conductivity=Quantity(0.0261, "watt/meter/kelvin"),
    fluid_kinematic_viscosity=Quantity(1.589e-5, "meter**2/second"),
    fluid_prandtl_number=Quantity(0.707, "dimensionless"),
    fluid_velocity=Quantity(1.0, "meter/second"),
    convection_length=Quantity(0.6, "meter"),
)

#: 50 mm of a 0.2 W/(m K) insulator: Bi = 5 * 0.05 / 0.2 = 1.25, twelve times
#: the limit. Fo = 2.4 / 1.25 = 1.92, still above its own floor, so exactly one
#: condition is violated.
BIOT_VIOLATING = dataclasses.replace(
    APPLICABLE,
    characteristic_length=Quantity(0.05, "meter"),
    body_conductivity=Quantity(0.2, "watt/meter/kelvin"),
)

#: No conductivity declared, so no Biot number can be formed.
MISSING_INPUT = dataclasses.replace(APPLICABLE, body_conductivity=None)


def run_coupled(declaration, run_id):
    system = cp.CoupledElectroThermalSystem(
        stages=(cp.CoupledStage(conductor(), thermal_body(declaration)),),
        source_voltage=Quantity(5.0, "volt"),
    )
    problems = cp.coupled_problems(
        system,
        {s.component_id: s.conductor.reference_resistance for s in system.stages},
    )
    plan = cp.nominal_plan(
        system,
        cp.coupled_dependencies(system, problems),
        seed=Quantity(300.0, K),
        tolerance=Quantity(1e-6, K),
        max_iterations=50,
    )
    return cp.run_fixed_point_coupling(system, plan, run_id=run_id), problems


def package_from_run(declaration, run_id):
    """Assemble a credibility evidence report from a real coupled run.

    The thermal sub-result supplies values, validation and provenance; the
    lumped model's validity assessment is made separately, because the result
    cannot carry it. The caller's declaration goes in as asserted context.
    """
    run, problems = run_coupled(declaration, run_id)
    electrical, _, thermal_id = (p.problem_id for p in problems)
    power = run.final.result_for(electrical).value("resistor_power:R1")
    assessment = lump.assess_lumped_validity(
        problems[2],
        initial_temperature=Quantity(300.0, K),
        ambient_temperature=Quantity(300.0, K),
        heat_input=power,
    )
    thermal_result = run.final.result_for(thermal_id)
    return run, thermal_result, CredibilityEvidenceReport.from_result(
        thermal_result,
        validity=(
            ModelValidityRecord(
                model_id=lump.LUMPED_CAPACITY_MODEL.model_id,
                version=lump.LUMPED_CAPACITY_MODEL.version,
                assessment=assessment,
            ),
        ),
        declarations=(
            AssertedContext(
                source="LumpedApplicabilityDeclaration",
                payload=declaration.to_dict(),
                description="caller-declared applicability context",
            ),
        ),
    )


def test_a_real_run_of_an_applicable_body_is_supported():
    """In domain, converged, nothing failed — and now something established.

    This package has been SUPPORTED, then INSUFFICIENT_EVIDENCE, and is
    SUPPORTED again, and the three states are not the same claim. It was
    SUPPORTED originally because nothing objected; the evidential guard took
    that away, correctly, because a report assembled entirely from checks that
    establish nothing says nothing. It is SUPPORTED now because the lumped
    solver acquired a check that establishes something: agreement with an
    independent reconstruction of the solution from the governing equation's
    own coefficients, in ``thermal_models/lumped_reference.py``.

    What separates the first state from the third is that a level is attained,
    and the level is attained by a passing check that names it. The guard is
    untouched — it is being satisfied rather than circumvented.
    """
    run, thermal, pkg = package_from_run(APPLICABLE, "evidence-applicable")

    # the run itself converged — a separate fact, asserted separately
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert pkg.violated_conditions == () and pkg.unknown_conditions == ()
    assert pkg.not_run_checks == ()
    assert pkg.failed_checks == ()
    # something argues for it, and it is nameable
    assert pkg.attained_levels == frozenset(
        {ValidationLevel.ANALYTICALLY_VERIFIED}
    )
    assert [c.name for c in pkg.validation if c.establishes is not None] == [
        "analytic_reference_agreement"
    ]
    assert pkg.verdict is CredibilityVerdict.SUPPORTED
    # and it is a real result, not an empty one
    assert pkg.values["final_temperature"].magnitude_in(K) == pytest.approx(
        338.577018, abs=1e-6
    )
    # provenance came from the thermal sub-result unaltered
    assert pkg.provenance == thermal.provenance
    assert pkg.validation == tuple(thermal.validation.checks)


def test_the_residual_check_still_establishes_nothing_on_the_real_run():
    """The new level came from the new check, not from relabelling the old one.

    ``lumped_balance_residual`` compares the closed form against the equation
    it was derived from. That was not evidence before this round and it is not
    evidence now; if the level had been attached to it instead, the verdict
    would have improved without any new evidence existing.
    """
    _, _, pkg = package_from_run(APPLICABLE, "evidence-residual")
    residual = next(c for c in pkg.validation if c.name == "lumped_balance_residual")
    assert residual.outcome is ValidationOutcome.PASS
    assert residual.establishes is None


def test_a_real_run_of_a_thick_low_conductivity_body_is_not_supported():
    """Bi = 1.25. The numbers are identical to the applicable case."""
    _, _, baseline = package_from_run(APPLICABLE, "evidence-baseline")
    run, _thermal, pkg = package_from_run(BIOT_VIOLATING, "evidence-biot")

    assert pkg.verdict is CredibilityVerdict.NOT_SUPPORTED
    assert pkg.violated_conditions == (
        (lump.LUMPED_CAPACITY_MODEL.model_id, ctx.BIOT_NUMBER),
    )
    # the three things stay separate: the coupling still converged, every
    # sub-check still passed, and only the validity verdict moved
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert pkg.failed_checks == ()
    assert pkg.values == baseline.values
    assert baseline.verdict is CredibilityVerdict.SUPPORTED
    # and the violated bound outranks the level the same run attained: the
    # reference comparison passed here too, and NOT_SUPPORTED still wins.
    assert ValidationLevel.ANALYTICALLY_VERIFIED in pkg.attained_levels


def test_a_real_run_with_an_undeclared_conductivity_is_insufficient_evidence():
    """No k, so no Biot number, so nothing is known about applicability."""
    run, _thermal, pkg = package_from_run(MISSING_INPUT, "evidence-missing")

    assert pkg.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert ctx.BIOT_NUMBER in [name for _, name in pkg.unknown_conditions]
    assert pkg.violated_conditions == ()
    assert pkg.failed_checks == ()
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET


def test_the_three_real_packages_round_trip_and_keep_their_verdicts():
    for declaration, expected in (
        (APPLICABLE, CredibilityVerdict.SUPPORTED),
        (BIOT_VIOLATING, CredibilityVerdict.NOT_SUPPORTED),
        (MISSING_INPUT, CredibilityVerdict.INSUFFICIENT_EVIDENCE),
    ):
        _, _, pkg = package_from_run(declaration, "evidence-roundtrip")
        restored = CredibilityEvidenceReport.from_dict(
            json.loads(json.dumps(pkg.to_dict(), sort_keys=True))
        )
        assert restored.verdict is expected
        assert restored.to_dict() == pkg.to_dict()
        assert restored.provenance == pkg.provenance


def test_the_real_declaration_is_carried_verbatim_and_buys_the_caller_nothing():
    """The forced-convection claim is visible, and changes no verdict.

    This is the gap from REVIEW.md closed at the package level: the regime
    reaches no condition and no provenance record, so without this field a
    reader could not see it was claimed at all.
    """
    _, _, pkg = package_from_run(BIOT_VIOLATING, "evidence-declaration")
    (declaration,) = pkg.declarations
    assert declaration.payload["convection_regime"] == ctx.FORCED_CONVECTION
    assert declaration.payload == BIOT_VIOLATING.to_dict()

    stripped = dataclasses.replace(pkg, declarations=())
    assert stripped.verdict is pkg.verdict is CredibilityVerdict.NOT_SUPPORTED


# =====================================================================
# F09 — one classification, shared between the core and this boundary
# =====================================================================

def test_f09_the_empty_domain_assessment_the_core_emits_crosses_the_boundary():
    """``ValidityDomain().assess({})`` is UNKNOWN, and must stay UNKNOWN here.

    A model that declares no conditions has had nothing asked of it, and the
    core says so: absence of declared limits is not evidence of unlimited
    validity. The wrapper used to re-derive the status from the condition lists
    alone — empty violated and empty unknown read as IN_DOMAIN — and so refused
    the very assessment the core produced. ``electrical.dc.kcl`` is a real
    model in this repository with exactly that domain.
    """
    empty = ValidityDomain().assess({})
    assert empty.status is ValidityStatus.UNKNOWN

    record = ModelValidityRecord(
        model_id="electrical.dc.kcl", version="0.1.0", assessment=empty
    )
    assert record.status is ValidityStatus.UNKNOWN


def test_f09_the_wrapper_agrees_with_the_core_on_every_assessment_it_emits():
    """The classification is shared, and this is what shared is checked to mean.

    Every assessment reachable from ``ValidityDomain.assess`` over this family
    of domains and contexts must cross the boundary with its status intact. A
    wrapper holding a second, subtly different rule would fail here rather than
    only on the empty domain that happened to be noticed.
    """
    bounded = RangeCondition(
        name="x", minimum=Quantity(0.0, "kelvin"), maximum=Quantity(10.0, "kelvin")
    )
    other = RangeCondition(
        name="y", minimum=Quantity(0.0, "kelvin"), maximum=Quantity(10.0, "kelvin")
    )
    domains = [
        ValidityDomain(),
        ValidityDomain(conditions=(bounded,)),
        ValidityDomain(conditions=(bounded, other)),
    ]
    contexts = [
        {},
        {"x": Quantity(5.0, K)},
        {"x": Quantity(50.0, K)},
        {"x": Quantity(5.0, K), "y": Quantity(5.0, K)},
        {"x": Quantity(50.0, K), "y": Quantity(5.0, K)},
        {"x": Quantity(5.0, K), "y": Quantity(50.0, K)},
    ]
    for domain, context in itertools.product(domains, contexts):
        assessment = domain.assess(context)
        record = ModelValidityRecord(
            model_id="probe", version="0.1.0", assessment=assessment
        )
        assert record.status is assessment.status, (domain, context)


def test_f09_a_status_that_contradicts_its_own_conditions_is_still_refused():
    """The fix widens the classification; it does not remove the cross-check.

    Raised by the core now rather than by this boundary -- the check moved to
    where the record lives, so it fires for every reader and not only for the
    ones that cross into credibility evidence.
    """
    with pytest.raises(ModelValidityError, match="may not contradict"):
        ModelValidityRecord(
            model_id="probe",
            version="0.1.0",
            assessment=ValidityAssessment(
                status=ValidityStatus.IN_DOMAIN, violated=("biot_number",)
            ),
        )
    with pytest.raises(ModelValidityError, match="may not contradict"):
        ModelValidityRecord(
            model_id="probe",
            version="0.1.0",
            assessment=ValidityAssessment(
                status=ValidityStatus.IN_DOMAIN,
                unknown=("biot_number",),
                unknown_reasons=(
                    UnknownCondition(
                        name="biot_number", reason=UnknownReason.NOT_SUPPLIED
                    ),
                ),
            ),
        )
    # and an assessment that named nothing may not claim IN_DOMAIN either:
    # nothing was evaluated, so nothing was found to hold.
    with pytest.raises(ModelValidityError, match="may not contradict"):
        ModelValidityRecord(
            model_id="probe",
            version="0.1.0",
            assessment=ValidityAssessment(status=ValidityStatus.IN_DOMAIN),
        )


# =====================================================================
# F05 / TASK 1 — attribution, the closure, and the coupling statement
# =====================================================================

NO_MODEL_PROVENANCE = dataclasses.replace(PROVENANCE, models=())


def test_f05_an_empty_model_inventory_cannot_attribute_an_assessment():
    """The finding: an empty inventory switched the attribution guard off.

    The guard exists so a caller cannot attach an honest IN_DOMAIN assessment
    of an unrelated model and turn an unassessed report into a SUPPORTED one.
    It was skipped entirely when the provenance named no models — which is the
    case where *nothing* backs the assessment, and so the case the guard is
    most needed in. A complete empty inventory was being read as an inventory
    that happened to be complete.

    Absent attribution is insufficient evidence, and not a raise: the report is
    perfectly well-formed, it simply does not say what produced the values its
    assessment is about.
    """
    report = CredibilityEvidenceReport(
        run_id="f05",
        values=VALUES,
        provenance=NO_MODEL_PROVENANCE,
        validity=(IN_DOMAIN,),
        validation=(PASSED,),
    )
    assert report.unattributed_assessments == (IN_DOMAIN.key,)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_f05_naming_the_model_as_a_contributor_attributes_it():
    """The fix is a statement a caller can make, not a wall.

    An assembler that knows the closure says so, and the same report is then
    attributed. What it may not do is stay silent and be believed.
    """
    report = CredibilityEvidenceReport(
        run_id="f05-named",
        values=VALUES,
        provenance=NO_MODEL_PROVENANCE,
        contributing_models=(IN_DOMAIN.key,),
        validity=(IN_DOMAIN,),
        validation=(PASSED,),
    )
    assert report.unattributed_assessments == ()
    assert report.verdict is CredibilityVerdict.SUPPORTED


def test_f05_a_stray_assessment_is_still_refused_when_the_inventory_is_not_empty():
    """The widened guard did not weaken the refusal it already made."""
    with pytest.raises(CredibilityEvidenceError, match="does not"):
        CredibilityEvidenceReport(
            run_id="stray",
            values=VALUES,
            provenance=ONE_MODEL_PROVENANCE,
            validity=(validity(ValidityStatus.IN_DOMAIN, model_id="not.in.the.run"),),
        )


def test_a_contributing_model_nobody_assessed_blocks_supported():
    """``unassessed_models`` must be able to be non-empty on a real report.

    It was derived from ``provenance.models`` alone, so a model that took part
    in producing a value but was never *bound* — and every model a coupled run
    knows about through the problems rather than through an execution binding
    is one of those — could not appear in it. The field could report a gap it
    structurally could not see.
    """
    contributor = ("electrical.dc.kcl", "0.1.0")
    report = CredibilityEvidenceReport(
        run_id="unassessed",
        values=VALUES,
        provenance=ONE_MODEL_PROVENANCE,
        contributing_models=(contributor,),
        validity=(IN_DOMAIN,),
        validation=(PASSED,),
    )
    assert report.unassessed_models == (contributor,)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE

    # and assessing it clears the gap rather than the gap being ignorable
    assessed = dataclasses.replace(
        report,
        validity=(
            IN_DOMAIN,
            validity(
                ValidityStatus.IN_DOMAIN,
                model_id=contributor[0],
                version=contributor[1],
                satisfied=("lumped_regime",),
            ),
        ),
    )
    assert assessed.unassessed_models == ()
    assert assessed.verdict is CredibilityVerdict.SUPPORTED


def test_a_coupling_that_missed_its_criterion_can_never_be_supported():
    """Everything else clean, and the fixed point was never reached."""
    missed = CouplingEvidence(
        outcome="iteration_limit_reached",
        iterations_run=50,
        iteration_limit=50,
        largest_iterate_change=Quantity(0.7, K),
        tolerance=Quantity(1e-6, K),
    )
    assert missed.criterion is CouplingCriterion.NOT_MET
    report = package(coupling=missed)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    # the same report without the coupling statement is SUPPORTED, which is
    # exactly the substitution the field exists to prevent
    assert package().verdict is CredibilityVerdict.SUPPORTED


def test_the_coupling_criterion_is_derived_and_cannot_be_asserted():
    """A record may report a criterion; it may not claim one.

    The same discipline as the verdict itself: derived on access from the
    numbers it carries, so there is no stored copy to disagree with them.
    """
    met = CouplingEvidence(
        outcome="criterion_met",
        iterations_run=7,
        iteration_limit=50,
        largest_iterate_change=Quantity(1e-9, K),
        tolerance=Quantity(1e-6, K),
    )
    assert met.criterion is CouplingCriterion.MET
    assert package(coupling=met).verdict is CredibilityVerdict.SUPPORTED
    assert "criterion" not in {f.name for f in dataclasses.fields(CouplingEvidence)}

    # and it compares in the tolerance's own unit rather than by magnitude
    in_millikelvin = CouplingEvidence(
        outcome="criterion_met",
        iterations_run=7,
        iteration_limit=50,
        largest_iterate_change=Quantity(0.5, "millikelvin"),
        tolerance=Quantity(1e-3, K),
    )
    assert in_millikelvin.criterion is CouplingCriterion.MET


def test_the_coupling_statement_round_trips_and_is_not_a_check():
    report = package(coupling=CouplingEvidence(
        outcome="iteration_limit_reached",
        iterations_run=50,
        iteration_limit=50,
        largest_iterate_change=Quantity(0.7, K),
        tolerance=Quantity(1e-6, K),
    ))
    restored = CredibilityEvidenceReport.from_dict(
        json.loads(json.dumps(report.to_dict(), sort_keys=True))
    )
    assert restored.coupling == report.coupling
    assert restored.verdict is report.verdict
    # it is not in the validation report, and not a level anybody attained
    assert restored.validation_report().checks == report.validation
    assert ValidationLevel.NUMERICALLY_CONVERGED not in restored.attained_levels


def test_combining_assessments_keeps_a_finding_above_a_gap():
    """One model applied to several elements has one verdict, not the best one."""
    parts = (
        ValidityAssessment(
            status=ValidityStatus.IN_DOMAIN,
            satisfied=("resistance", "dissipated_power_utilization"),
        ),
        ValidityAssessment(
            status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
            satisfied=("resistance",),
            violated=("dissipated_power_utilization",),
        ),
        ValidityAssessment(
            status=ValidityStatus.UNKNOWN,
            satisfied=("resistance",),
            unknown=("working_voltage_utilization",),
            unknown_reasons=(
                UnknownCondition(
                    name="working_voltage_utilization",
                    reason=UnknownReason.NOT_SUPPLIED,
                ),
            ),
        ),
    )
    combined = combine_assessments(parts)
    assert combined.violated == ("dissipated_power_utilization",)
    assert combined.unknown == ("working_voltage_utilization",)
    assert combined.satisfied == ("resistance",)
    assert combined.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    # and the combination is classified by the one shared rule, so it crosses
    assert classify_assessment(combined) is combined.status
    # nothing to combine is nothing known, not everything fine
    assert combine_assessments(()).status is ValidityStatus.UNKNOWN


# =====================================================================
# F04 — UNVERIFIED cannot buy a verdict
# =====================================================================

def test_f04_a_report_whose_only_level_is_unverified_is_insufficient():
    """The reproduction, and where it is now stopped.

    A passing check declaring ``UNVERIFIED`` satisfied the attained-level guard
    and produced SUPPORTED: nothing was verified, said so, and was read as
    evidence. The check can no longer be built at all, so the report can only
    be assembled with the sentinel absent — and a report whose checks establish
    nothing is INSUFFICIENT_EVIDENCE, which is the rule that was already there
    and was being evaded.
    """
    with pytest.raises(ScientificValidationError):
        ValidationCheck(
            name="nothing_was_verified",
            outcome=ValidationOutcome.PASS,
            establishes=ValidationLevel.UNVERIFIED,
        )

    nothing = ValidationCheck(
        name="nothing_was_verified", outcome=ValidationOutcome.PASS
    )
    report = package(checks=(nothing,))
    assert report.attained_levels == frozenset()
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_f04_the_sentinel_cannot_be_demanded_either():
    """``required_levels`` and ``attained_levels`` must not disagree.

    With the sentinel unattainable by construction, a caller who demanded it
    would have declared a requirement nothing could ever satisfy and would get
    INSUFFICIENT_EVIDENCE forever with no explanation. Refused at the field
    instead, in the same voice and for the same reason as the check itself.
    """
    with pytest.raises(CredibilityEvidenceError, match="UNVERIFIED"):
        package(required_levels=(ValidationLevel.UNVERIFIED,))

    # a real level is still demandable, and still has to be met
    demanded = package(required_levels=(ValidationLevel.BENCHMARK_VALIDATED,))
    assert demanded.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert demanded.missing_required_levels == (
        ValidationLevel.BENCHMARK_VALIDATED,
    )


def test_f04_a_serialized_report_cannot_reintroduce_the_sentinel():
    """Neither through a check nor through a required level."""
    report = package()
    payload = report.to_dict()
    payload["required_levels"] = [ValidationLevel.UNVERIFIED.value]
    with pytest.raises(CredibilityEvidenceError, match="UNVERIFIED"):
        CredibilityEvidenceReport.from_dict(payload)

    payload = report.to_dict()
    payload["validation"][0]["establishes"] = ValidationLevel.UNVERIFIED.value
    with pytest.raises(ScientificValidationError):
        CredibilityEvidenceReport.from_dict(payload)
