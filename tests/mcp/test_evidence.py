"""What an evidence package may and may not claim.

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
    EvidencePackage,
    EvidencePackageError,
    EvidenceVerdict,
    ModelValidityRecord,
    derive_verdict,
)
from src.engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
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
            ValidityStatus.UNKNOWN: {"unknown": ("biot_number",)},
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
UNKNOWN = validity(ValidityStatus.UNKNOWN, unknown=("biot_number",))

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
    return EvidencePackage(
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
    assert package().verdict is EvidenceVerdict.SUPPORTED
    assert package().is_supported


def test_unknown_validity_is_insufficient_evidence():
    """A condition nobody supplied the input for is a gap, not a pass."""
    pkg = package(validity_records=(UNKNOWN,))
    assert pkg.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE
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
            assert verdict is not EvidenceVerdict.SUPPORTED, combo


def test_outside_validated_domain_is_not_supported_and_names_the_condition():
    pkg = package(validity_records=(OUTSIDE,))
    assert pkg.verdict is EvidenceVerdict.NOT_SUPPORTED
    assert pkg.violated_conditions == (("thermal.lumped", "biot_number"),)
    # the condition name survives serialization, which is where a reader meets it
    assert "biot_number" in json.dumps(pkg.to_dict())


def test_a_failed_check_is_not_supported_even_when_all_validity_is_in_domain():
    """An applicable model whose check failed is still a failure."""
    pkg = package(checks=(FAILED,))
    assert all(r.status is ValidityStatus.IN_DOMAIN for r in pkg.validity)
    assert pkg.verdict is EvidenceVerdict.NOT_SUPPORTED
    assert pkg.failed_checks == ("lumped_balance_residual",)


def test_a_not_run_check_is_insufficient_evidence_even_when_nothing_failed():
    """The NOT_RUN mechanism, carried one level up.

    Everything that ran, passed. The verdict is still not SUPPORTED, because a
    check that never executed cannot contribute evidence — which is the rule
    the core states and the reason NOT_RUN exists as an outcome at all.
    """
    pkg = package(checks=(PASSED, NOT_RUN))
    assert pkg.failed_checks == ()
    assert pkg.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE
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
    assert pkg.verdict is EvidenceVerdict.NOT_SUPPORTED


def test_a_failed_check_outranks_an_unknown_validity_too():
    """The other half of the precedence rule."""
    assert (
        package(validity_records=(UNKNOWN,), checks=(FAILED,)).verdict
        is EvidenceVerdict.NOT_SUPPORTED
    )


def test_a_warning_does_not_change_the_verdict_and_stays_visible():
    """WARNING ran and produced evidence; it is not a failure and not a gap.

    Deliberate: folding it into the verdict would either overstate it as
    NOT_SUPPORTED or need a fourth value. It stays in the carried checks for
    the reader who has to weigh it.
    """
    pkg = package(checks=(PASSED, WARNED))
    assert pkg.verdict is EvidenceVerdict.SUPPORTED
    assert "tolerance_margin" in {c.name for c in pkg.validation}
    assert pkg.validation_report().warnings != ()


def test_an_empty_package_is_insufficient_evidence_not_supported():
    """No checks and no validity records means nothing was established.

    The alternative — vacuous SUPPORTED — is the NOT_RUN failure mode
    reintroduced at the package level.
    """
    assert package(checks=()).verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert package(validity_records=()).verdict is (
        EvidenceVerdict.INSUFFICIENT_EVIDENCE
    )
    assert package(validity_records=(), checks=()).verdict is (
        EvidenceVerdict.INSUFFICIENT_EVIDENCE
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
            return EvidenceVerdict.NOT_SUPPORTED
        if ValidationOutcome.FAIL in outcome_set:
            return EvidenceVerdict.NOT_SUPPORTED
        if ValidityStatus.UNKNOWN in status_set:
            return EvidenceVerdict.INSUFFICIENT_EVIDENCE
        if ValidationOutcome.NOT_RUN in outcome_set:
            return EvidenceVerdict.INSUFFICIENT_EVIDENCE
        if not status_set or not outcome_set:
            return EvidenceVerdict.INSUFFICIENT_EVIDENCE
        return EvidenceVerdict.SUPPORTED

    seen = set()
    for s_size in range(len(statuses) + 1):
        for s_combo in itertools.combinations(statuses, s_size):
            for o_size in range(len(outcomes) + 1):
                for o_combo in itertools.combinations(outcomes, o_size):
                    records = tuple(
                        validity(s, model_id=f"m{i}") for i, s in enumerate(s_combo)
                    )
                    checks = tuple(
                        ValidationCheck(name=f"c{i}", outcome=o)
                        for i, o in enumerate(o_combo)
                    )
                    got = derive_verdict(validity=records, validation=checks)
                    assert got is oracle(set(s_combo), set(o_combo)), (
                        s_combo,
                        o_combo,
                    )
                    seen.add(got)
    # all three verdicts are reachable; none is dead code
    assert seen == set(EvidenceVerdict)


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
    with pytest.raises(EvidencePackageError):
        AssertedContext(source="x", payload={"q": Quantity(1.0, K)})
    with pytest.raises(EvidencePackageError):
        AssertedContext(source="  ", payload={})


# =====================================================================
# A verdict cannot be asserted — structurally
# =====================================================================

def test_the_verdict_is_not_a_field_and_cannot_be_constructed():
    """Not policed by a check — absent from the constructor entirely."""
    assert "verdict" not in EvidencePackage.__dataclass_fields__
    assert isinstance(
        type(package()).__dict__["verdict"], property
    )
    with pytest.raises(TypeError):
        EvidencePackage(
            run_id="r",
            values={},
            verdict=EvidenceVerdict.SUPPORTED,
        )


def test_the_verdict_cannot_be_replaced_or_written_onto_an_instance():
    pkg = package(validity_records=(OUTSIDE,))
    with pytest.raises(TypeError):
        dataclasses.replace(pkg, verdict=EvidenceVerdict.SUPPORTED)
    with pytest.raises(AttributeError):
        object.__setattr__(pkg, "verdict", EvidenceVerdict.SUPPORTED)
    assert pkg.verdict is EvidenceVerdict.NOT_SUPPORTED


def test_a_serialized_verdict_inconsistent_with_the_contents_is_rejected():
    """The from_dict half: a hand-edited record cannot smuggle a verdict in.

    Mirrors ValidationReport.from_dict's treatment of attained_levels — the
    derived field in a payload is advisory, recomputed and verified.
    """
    payload = package(validity_records=(OUTSIDE,)).to_dict()
    assert payload["verdict"] == EvidenceVerdict.NOT_SUPPORTED.value
    payload["verdict"] = EvidenceVerdict.SUPPORTED.value
    with pytest.raises(EvidencePackageError) as caught:
        EvidencePackage.from_dict(payload)
    assert "does not match" in str(caught.value)


def test_a_payload_with_no_verdict_key_is_accepted_and_derives_its_own():
    payload = package().to_dict()
    del payload["verdict"]
    assert EvidencePackage.from_dict(payload).verdict is EvidenceVerdict.SUPPORTED


def test_poisoning_the_instance_dict_does_not_shadow_the_property():
    """A property is a data descriptor; the instance dict loses to it."""
    pkg = package(validity_records=(OUTSIDE,))
    pkg.__dict__["verdict"] = EvidenceVerdict.SUPPORTED
    assert pkg.verdict is EvidenceVerdict.NOT_SUPPORTED
    assert pkg.to_dict()["verdict"] == EvidenceVerdict.NOT_SUPPORTED.value


def test_pickling_and_copying_carry_the_honest_verdict():
    pkg = package(validity_records=(OUTSIDE,))
    assert pickle.loads(pickle.dumps(pkg)).verdict is EvidenceVerdict.NOT_SUPPORTED
    assert copy.deepcopy(pkg).verdict is EvidenceVerdict.NOT_SUPPORTED


def test_a_subclass_can_lie_in_process_but_not_across_a_serialization_boundary():
    """The honest limit of the guarantee, pinned so it is not overstated.

    Nothing stops a subclass overriding the property — Python has no mechanism
    for that and pretending otherwise would be theatre. What matters is that
    the lie cannot be persisted, sent, or handed to a second reader: the real
    ``from_dict`` recomputes the verdict from the contents and refuses.
    """
    class Liar(EvidencePackage):
        @property
        def verdict(self):
            return EvidenceVerdict.SUPPORTED

    liar = Liar(
        run_id="r",
        values=VALUES,
        validity=(OUTSIDE,),
        validation=(PASSED,),
        provenance=PROVENANCE,
    )
    assert liar.verdict is EvidenceVerdict.SUPPORTED          # in-process, yes
    with pytest.raises(EvidencePackageError):                  # across a boundary, no
        EvidencePackage.from_dict(liar.to_dict())


def test_the_verdict_tracks_the_contents_rather_than_being_stored():
    """Derived-on-access means there is no stale copy to drift.

    Rewriting a carried assessment through ``object.__setattr__`` — the escape
    hatch that defeats every frozen record in this repository, not just these —
    moves the verdict *with* the contents. That is the property worth having: a
    package is never internally inconsistent. A stored verdict field would have
    kept reporting NOT_SUPPORTED over contents that no longer said so.
    """
    pkg = package(validity_records=(OUTSIDE,))
    assert pkg.verdict is EvidenceVerdict.NOT_SUPPORTED
    object.__setattr__(
        pkg.validity[0].assessment, "status", ValidityStatus.IN_DOMAIN
    )
    object.__setattr__(pkg.validity[0].assessment, "violated", ())
    assert pkg.verdict is EvidenceVerdict.SUPPORTED
    # and the serialized form agrees with the contents, not with history
    assert pkg.to_dict()["verdict"] == EvidenceVerdict.SUPPORTED.value
    assert EvidencePackage.from_dict(pkg.to_dict()).verdict is (
        EvidenceVerdict.SUPPORTED
    )


def test_the_package_copies_the_mappings_it_is_given():
    """A caller's later mutation must not reach inside a constructed package."""
    values = {"T": Quantity(300.0, K)}
    pkg = EvidencePackage(run_id="r", values=values, provenance=PROVENANCE)
    values["INJECTED"] = Quantity(1.0, K)
    assert "INJECTED" not in pkg.values

    payload = {"convection_regime": "forced"}
    context = AssertedContext(source="s", payload=payload)
    payload["convection_regime"] = "tampered"
    assert context.payload["convection_regime"] == "forced"


def test_an_unrecognised_validity_status_is_refused_rather_than_read_as_clean():
    """ValidityAssessment coerces nothing, so a bogus status can reach here.

    It must not: an unrecognised status matches neither the NOT_SUPPORTED nor
    the INSUFFICIENT_EVIDENCE branch, so it would fall through to SUPPORTED —
    the most favourable verdict available, earned by malformation.
    """
    with pytest.raises(EvidencePackageError):
        ModelValidityRecord(
            model_id="m",
            version="1",
            assessment=ValidityAssessment(status="probably_fine"),
        )
    # a correct status supplied as a bare string is still accepted
    assert ModelValidityRecord(
        model_id="m", version="1",
        assessment=ValidityAssessment(status="in_domain"),
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
    assert pkg.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE
    # assess the second model and the gap closes
    both = package(
        validity_records=(
            IN_DOMAIN,
            dataclasses.replace(IN_DOMAIN, model_id="electrical.material"),
        ),
        provenance=PROVENANCE,
    )
    assert both.unassessed_models == ()
    assert both.verdict is EvidenceVerdict.SUPPORTED


def test_a_validity_record_for_a_model_that_did_not_run_is_refused():
    """An honest assessment of the wrong model is not evidence about these values.

    Without this, a caller holding an unassessed thermal run could attach a
    real IN_DOMAIN assessment of some unrelated model and turn
    INSUFFICIENT_EVIDENCE into SUPPORTED.
    """
    with pytest.raises(EvidencePackageError) as caught:
        package(
            validity_records=(
                dataclasses.replace(IN_DOMAIN, model_id="kinetics.cstr"),
            ),
            provenance=ONE_MODEL_PROVENANCE,
        )
    assert "kinetics.cstr" in str(caught.value)


def test_a_record_whose_status_contradicts_its_own_conditions_is_refused():
    """IN_DOMAIN over a non-empty `violated` would report SUPPORTED.

    ValidityAssessment enforces no relation between its status and its
    condition lists, so the package cross-checks against exactly the
    classification `ValidityDomain.assess` performs: every assessment the core
    actually produced passes untouched, and only a hand-built one is refused.
    """
    for status, names in (
        (ValidityStatus.IN_DOMAIN, {"violated": ("biot_number",)}),
        (ValidityStatus.IN_DOMAIN, {"unknown": ("biot_number",)}),
        (ValidityStatus.UNKNOWN, {"violated": ("biot_number",)}),
        (ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, {"satisfied": ("biot_number",)}),
    ):
        with pytest.raises(EvidencePackageError) as caught:
            ModelValidityRecord(
                model_id="m",
                version="1",
                assessment=ValidityAssessment(status=status, **names),
            )
        assert "contradict" in str(caught.value)


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
    with pytest.raises(EvidencePackageError):
        derive_verdict(validity=[junk], validation=[])


def test_required_levels_turn_an_unattained_claim_into_a_gap():
    """The caller's own bar, checked against the core's attained_levels.

    SUPPORTED does not by itself require any level to have been attained — see
    the verdict docstring — so a study that needs one says so here.
    """
    pkg = package(checks=(PASSED,), required_levels=(ValidationLevel.DIMENSIONALLY_VALID,))
    assert pkg.attained_levels == frozenset({ValidationLevel.DIMENSIONALLY_VALID})
    assert pkg.missing_required_levels == ()
    assert pkg.verdict is EvidenceVerdict.SUPPORTED

    demanding = package(
        checks=(PASSED,),
        required_levels=(ValidationLevel.EXPERIMENTALLY_VALIDATED,),
    )
    assert demanding.missing_required_levels == (
        ValidationLevel.EXPERIMENTALLY_VALIDATED,
    )
    assert demanding.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE


def test_a_passing_check_that_establishes_nothing_still_reports_supported():
    """The rule as specified, pinned so the limit is deliberate not accidental.

    A check with `establishes=None` attains no level, so this package is
    SUPPORTED with an empty attained_levels — which the lumped thermal solver
    produces in real runs, deliberately. The qualifier is emitted beside the
    verdict so a reader of the JSON sees it without opening the check list.
    """
    bare = ValidationCheck(name="ran", outcome=ValidationOutcome.PASS)
    pkg = package(checks=(bare,))
    assert pkg.verdict is EvidenceVerdict.SUPPORTED
    assert pkg.attained_levels == frozenset()
    assert pkg.to_dict()["verdict_qualifiers"]["attained_levels"] == []


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
    pkg = EvidencePackage.from_result(
        result, validity=(IN_DOMAIN,), notes="reviewed and accepted by J. Smith"
    )
    assert pkg.notes == "reviewed and accepted by J. Smith"
    assert pkg.validation_notes == "residual measured against the balance"
    assert pkg.validation_report().notes == "residual measured against the balance"


def test_a_declaration_may_not_embed_a_core_evidence_record():
    """A check-shaped object under the not-evidence markings misleads a scanner."""
    with pytest.raises(EvidencePackageError) as caught:
        AssertedContext(
            source="s",
            payload={"cross_solver_agreement": PASSED.to_dict()},
        )
    assert "validation_check" in str(caught.value)
    # nested, not just at the top level
    with pytest.raises(EvidencePackageError):
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
    with pytest.raises(EvidencePackageError):
        package(validity_records=(IN_DOMAIN, OUTSIDE))


def test_a_package_refuses_duplicate_check_names():
    with pytest.raises(EvidencePackageError):
        package(checks=(PASSED, dataclasses.replace(FAILED, name=PASSED.name)))


def test_a_package_refuses_a_bare_number_as_a_value():
    with pytest.raises(EvidencePackageError):
        EvidencePackage(run_id="r", values={"T": 300.0}, provenance=PROVENANCE)


def test_a_package_refuses_an_unattributable_run():
    with pytest.raises(EvidencePackageError):
        EvidencePackage(run_id="   ", values={}, provenance=PROVENANCE)


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
    restored = EvidencePackage.from_dict(payload)

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
    restored = EvidencePackage.from_dict(pkg.to_dict())
    assert restored.provenance == ONE_MODEL_PROVENANCE


def test_a_package_cannot_exist_without_provenance():
    """Stricter than ScientificResult would need, and for the same reason.

    A package is a stronger claim than a result, so it cannot have a weaker
    attribution rule. An optional-and-inert provenance would let an
    unattributed package report SUPPORTED.
    """
    with pytest.raises(TypeError):
        EvidencePackage(run_id="r", values={})
    with pytest.raises(EvidencePackageError):
        EvidencePackage(run_id="r", values={}, provenance={"run_id": "r"})


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
    pkg = EvidencePackage.from_result(result, validity=(IN_DOMAIN,))
    assert pkg.not_run_checks == ("validation_performed",)
    assert pkg.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert pkg.provenance == result.provenance
    assert pkg.values == result.values


def test_from_result_with_no_validity_is_unknown_rather_than_clean():
    """The result cannot carry validity, so a package built without it says so."""
    result = ScientificResult(
        result_id="r1",
        values=VALUES,
        provenance=PROVENANCE,
        validation=ValidationReport(checks=(PASSED,)),
    )
    pkg = EvidencePackage.from_result(result)
    assert pkg.validity == ()
    assert pkg.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE


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
    """Assemble an evidence package from a real coupled run.

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
    return run, thermal_result, EvidencePackage.from_result(
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
    run, thermal, pkg = package_from_run(APPLICABLE, "evidence-applicable")

    # the run itself converged — a separate fact, asserted separately
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert pkg.verdict is EvidenceVerdict.SUPPORTED
    assert pkg.violated_conditions == () and pkg.unknown_conditions == ()
    assert pkg.not_run_checks == ()
    # and it is a real result, not an empty one
    assert pkg.values["final_temperature"].magnitude_in(K) == pytest.approx(
        338.577018, abs=1e-6
    )
    # provenance came from the thermal sub-result unaltered
    assert pkg.provenance == thermal.provenance
    assert pkg.validation == tuple(thermal.validation.checks)


def test_a_real_run_of_a_thick_low_conductivity_body_is_not_supported():
    """Bi = 1.25. The numbers are identical to the applicable case."""
    _, _, baseline = package_from_run(APPLICABLE, "evidence-baseline")
    run, _thermal, pkg = package_from_run(BIOT_VIOLATING, "evidence-biot")

    assert pkg.verdict is EvidenceVerdict.NOT_SUPPORTED
    assert pkg.violated_conditions == (
        (lump.LUMPED_CAPACITY_MODEL.model_id, ctx.BIOT_NUMBER),
    )
    # the three things stay separate: the coupling still converged, every
    # sub-check still passed, and only the validity verdict moved
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert pkg.failed_checks == ()
    assert pkg.values == baseline.values
    assert baseline.verdict is EvidenceVerdict.SUPPORTED


def test_a_real_run_with_an_undeclared_conductivity_is_insufficient_evidence():
    """No k, so no Biot number, so nothing is known about applicability."""
    run, _thermal, pkg = package_from_run(MISSING_INPUT, "evidence-missing")

    assert pkg.verdict is EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert ctx.BIOT_NUMBER in [name for _, name in pkg.unknown_conditions]
    assert pkg.violated_conditions == ()
    assert pkg.failed_checks == ()
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET


def test_the_three_real_packages_round_trip_and_keep_their_verdicts():
    for declaration, expected in (
        (APPLICABLE, EvidenceVerdict.SUPPORTED),
        (BIOT_VIOLATING, EvidenceVerdict.NOT_SUPPORTED),
        (MISSING_INPUT, EvidenceVerdict.INSUFFICIENT_EVIDENCE),
    ):
        _, _, pkg = package_from_run(declaration, "evidence-roundtrip")
        restored = EvidencePackage.from_dict(
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
    assert stripped.verdict is pkg.verdict is EvidenceVerdict.NOT_SUPPORTED
