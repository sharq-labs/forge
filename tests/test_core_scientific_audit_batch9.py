"""Batch 9 of the 2026-09-16 core re-audit: ANALYTICALLY_VERIFIED needs an issuer (I-09, part B of two).

Closes the issuer half of R-04. An issuer record was required for only three of the six levels a check can
claim: CROSS_SOLVER_VALIDATED, BENCHMARK_VALIDATED and EXPERIMENTALLY_VALIDATED. DIMENSIONALLY_VALID,
NUMERICALLY_CONVERGED and ANALYTICALLY_VERIFIED needed only GUARD 2's "something was compared", and a
non-empty evidence string is something. ``ValidationCheck(PASS, establishes=ANALYTICALLY_VERIFIED,
evidence=("trust me",))`` was constructed, attained, survived ``from_dict`` and carried a SUPPORTED verdict --
and the one SUPPORTED report either MCP tool can return rests on exactly that level.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH9_THRESHOLD_PROTOCOL.json`. Every test here was
committed as `xfail(strict=True)` first and run with `--runxfail` at b71d878 to watch it fail; the markers
came off in the implementation commit, and the xfail commit is d66a7fe. What each failed on there, recorded so the evidence is not overstated:
2 on an assertion (the production lumped check's evidence, and `DID NOT RAISE` for the hand-written check,
which is an assertion about a refusal that is absent), and 12 on an `ImportError` for the registry or the
threshold set the improvement adds. The tests were then rewritten once, after the implementation found that
`src/engcore/domains/thermal/` is SHA-256 pinned by three frozen experiments and could not gain an evidence
line -- see the protocol's amendment log; the rule they assert is the same rule, over the records the
producers already kept. The registry is imported LAZILY inside each test for that reason: a
module-level import would have made every test a collection error, which is not a failing assertion and
proves nothing about the guard.

``test_r04_a_fail_or_not_run_is_held_to_nothing`` already held at b71d878 and carries no xfail: it is the
guard that the rule stays scoped to a CLAIM, so a FAIL or NOT_RUN check is held to nothing.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.thresholds import VerificationThresholds
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)

ANALYTIC = ValidationLevel.ANALYTICALLY_VERIFIED

#: The three analytic references in src/, named here rather than read from the registry so this module
#: COLLECTS at the preregistration commit: a module-level import of a table the improvement has yet to add
#: would make every test below a collection error, which is not a failing assertion and proves nothing.
REFERENCES = (
    "kinetics.cstr.adiabatic_reaction_free_invariant",
    "thermal.conduction1d.single_mode_analytic",
    "thermal_models.lumped.series_recurrence",
)


def _registries():
    from engcore.domains import (
        SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS,
        SCIENTIFIC_THRESHOLD_DECLARATIONS,
    )

    return SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS, SCIENTIFIC_THRESHOLD_DECLARATIONS


def _thresholds_of(reference_id: str):
    """The declared VerificationThresholds of the gate the registry says awards ``reference_id``."""
    references, gates = _registries()
    gate = gates[references[reference_id]["thresholds_gate"]]
    module, _, name = str(gate["declared_by"]).rpartition(".")
    return getattr(__import__(module, fromlist=[name]), name)


def _issued(reference_id: str, **overrides) -> dict:
    """The evidence a genuine issuer writes for ``reference_id``.

    Two lines, and both are lines the producers in src/ already wrote before this batch: the reference
    named as ``"<id>: <expression>"``, and the awarding gate's declared threshold record. What the
    batch adds is the rule that CHECKS them.
    """
    references, _gates = _registries()
    declared = references[reference_id]
    lines = {
        "reference": f"{reference_id}: {declared['expression']}",
        "thresholds": _thresholds_of(reference_id).evidence()[0],
    }
    lines.update(overrides)
    return lines


def _check(evidence, *, level=ANALYTIC, outcome=ValidationOutcome.PASS) -> ValidationCheck:
    return ValidationCheck(name="analytic_reference_agreement", outcome=outcome, establishes=level,
                           residual=1e-9, tolerance=1e-6, evidence=tuple(evidence))


# =====================================================================
# the refusals
# =====================================================================
def test_r04_a_hand_written_analytically_verified_check_is_refused():
    """The audited reproduction, verbatim."""
    with pytest.raises(ScientificValidationError, match="(?i)analytic"):
        _check(("trust me",))


def test_r04_an_unregistered_reference_is_refused():
    """A reference id is a public string and was never proof of anything."""
    lines = _issued("thermal_models.lumped.series_recurrence")
    lines["reference"] = "my.own.closed_form: T(t) = whatever I like"
    with pytest.raises(ScientificValidationError, match="(?i)no single analytic reference"):
        _check(lines.values())


def test_r04_a_closed_form_that_is_not_the_registered_one_is_refused():
    """A copied reference line with the statement quietly changed: the level says a solve agreed
    with a SPECIFIC closed form, and this is a different statement."""
    reference_id = "thermal_models.lumped.series_recurrence"
    lines = _issued(reference_id)
    lines["reference"] = f"{reference_id}: T(t) = T0 for all t"
    with pytest.raises(ScientificValidationError, match="(?i)not the registered one"):
        _check(lines.values())


def test_r04_naming_two_registered_references_is_refused():
    """One check, one closed form. Two would leave a reader unable to say which was compared."""
    lines = _issued("thermal_models.lumped.series_recurrence")
    references, _ = _registries()
    other = "kinetics.cstr.adiabatic_reaction_free_invariant"
    lines["second"] = f"{other}: {references[other]['expression']}"
    with pytest.raises(ScientificValidationError, match="(?i)no single analytic reference"):
        _check(lines.values())


def test_r04_a_caller_built_threshold_set_is_refused():
    """The consensus rule's second half: a set that is not the domain's own awards nothing."""
    lines = _issued("thermal_models.lumped.series_recurrence")
    invented = VerificationThresholds(gate_id="thermal_models.lumped.analytic_reference",
                                      version="0.1.0", values={"rounding_ulps": 1.0e9})
    lines["thresholds"] = invented.evidence()[0]
    assert not invented.is_declared, "the same gate id and version, other numbers"
    with pytest.raises(ScientificValidationError, match="(?i)threshold specification"):
        _check(lines.values())


def test_r04_a_check_with_no_threshold_record_is_refused():
    """A valid reference and no record of which numbers it was judged against.

    Its own test because the hand-written case above is refused a step earlier, for naming no
    registered reference -- which the batch-9 mutation run showed: removing this guard left that
    test green, so it was proving nothing about this one.
    """
    lines = _issued("thermal_models.lumped.series_recurrence")
    del lines["thresholds"]
    with pytest.raises(ScientificValidationError, match="(?i)no single verification threshold record"):
        _check(lines.values())


def test_r04_two_threshold_records_are_refused():
    """One check, one set of numbers. Two would leave a reader unable to say which judged it."""
    lines = _issued("thermal_models.lumped.series_recurrence")
    lines["second"] = _thresholds_of("kinetics.cstr.adiabatic_reaction_free_invariant").evidence()[0]
    with pytest.raises(ScientificValidationError, match="(?i)no single verification threshold record"):
        _check(lines.values())


def test_r04_a_reference_whose_gate_is_another_domains_is_refused():
    """The registry says which gate awards which reference; another domain's declared set is not it."""
    from engcore.domains.electrical.dc.validation import DC_CONVERGENCE_THRESHOLDS

    lines = _issued("thermal_models.lumped.series_recurrence")
    assert DC_CONVERGENCE_THRESHOLDS.is_declared
    lines["thresholds"] = DC_CONVERGENCE_THRESHOLDS.evidence()[0]
    with pytest.raises(ScientificValidationError, match="(?i)threshold specification"):
        _check(lines.values())


def test_r04_a_refused_payload_cannot_be_read_back_either():
    """The read rule is the write rule: a report cannot carry what the constructor refuses."""
    honest = _check(_issued("thermal_models.lumped.series_recurrence").values())
    payload = json.loads(json.dumps(honest.to_dict()))
    payload["evidence"] = ["trust me"]
    with pytest.raises(ScientificValidationError, match="(?i)analytic"):
        ValidationCheck.from_dict(payload)


# =====================================================================
# what still stands
# =====================================================================
@pytest.mark.parametrize("reference_id", REFERENCES)
def test_r04_every_registered_reference_can_issue_its_level(reference_id):
    check = _check(_issued(reference_id).values())
    assert check.establishes is ANALYTIC
    assert ValidationReport(checks=(check,)).attained_levels == frozenset({ANALYTIC})


def test_r04_a_fail_or_not_run_is_held_to_nothing():
    """The rule is scoped to a CLAIM. A FAIL contributes no level whatever it declares."""
    for outcome in (ValidationOutcome.FAIL, ValidationOutcome.NOT_RUN):
        check = ValidationCheck(name="analytic_reference_agreement", outcome=outcome, establishes=None,
                                residual=1.0, tolerance=1e-6, evidence=("no reference was available",))
        assert ValidationReport(checks=(check,)).attained_levels == frozenset()


def test_r04_the_registry_and_the_constants_it_names_cannot_drift():
    """Each entry's digest is recomputed from the constant it names, here as well as at import."""
    references, gates = _registries()
    assert set(references) == set(REFERENCES)
    for reference_id, entry in references.items():
        module, _, name = str(entry["declared_by"]).rpartition(".")
        expression = getattr(__import__(module, fromlist=[name]), name)
        assert expression == entry["expression"], reference_id
        assert hashlib.sha256(expression.encode("utf-8")).hexdigest() == entry["expression_digest"], reference_id
        assert entry["thresholds_gate"] in gates, reference_id


# =====================================================================
# the three production producers
# =====================================================================
def test_r04_the_production_lumped_check_carries_its_issuer_record():
    """The one SUPPORTED report either MCP tool can return rests on this check.

    It already named its reference; what it had no trace of was a declared threshold set, so the
    tolerance it was judged against belonged to nobody.
    """
    from engcore.mcp.problem import example_electrothermal_payload, run_electrothermal_case

    references, _ = _registries()
    report = run_electrothermal_case(example_electrothermal_payload(), run_id="batch9").reports[0]
    (analytic,) = [c for c in report.validation if c.establishes is ANALYTIC]
    lines = set(analytic.evidence)
    reference_id = "thermal_models.lumped.series_recurrence"
    assert f"{reference_id}: {references[reference_id]['expression']}" in lines
    assert any(line.startswith("thresholds:thermal_models.lumped.analytic_reference@") for line in lines)
    assert report.attained_levels == frozenset({ANALYTIC}), "the level is still earned, by its issuer"


@pytest.mark.expensive
def test_r04_the_conduction1d_and_cstr_gates_carry_their_issuer_records():
    """Both already wrote a DECLARED threshold record; what they lacked was a pinned reference."""
    from engcore.domains.thermal.conduction1d import (
        ConductionSlab,
        SlabDiscretization,
        run_verification_gate,
    )
    from engcore.scientific.units.quantity import Quantity

    slab = ConductionSlab(slab_id="batch9", length=Quantity(0.1, "meter"),
                          diffusivity=Quantity(1.2e-5, "meter**2/second"),
                          end_time=Quantity(60.0, "second"),
                          discretization=SlabDiscretization(64, 80))
    references, _ = _registries()
    (check,) = [c for c in run_verification_gate(slab).to_report().checks
                if c.name == "analytic_reference_agreement"]
    lines = set(check.evidence)
    reference_id = "thermal.conduction1d.single_mode_analytic"
    assert f"{reference_id}: {references[reference_id]['expression']}" in lines
    assert any(line.startswith("thresholds:thermal.conduction1d.refinement@") for line in lines)
    assert check.establishes is ANALYTIC, "the level is still earned, by its issuer"
    # Nothing under src/engcore/domains/thermal/ was edited to make that true: the tree is SHA-256
    # pinned by the frozen thermal_t1/t2/t3 experiments, and the rule is written to the records this
    # gate already kept.


def test_r04_a_caller_override_still_withholds_the_level_and_keeps_the_report():
    """The threshold rule's own promise, unchanged: the comparison, the residual and the detail all
    survive an override; only the claim is withheld. Now the issuer rule cannot be what refuses it."""
    from engcore.domains.thermal_models.lumped import LUMPED_ANALYTIC_REFERENCE_THRESHOLDS

    overridden = LUMPED_ANALYTIC_REFERENCE_THRESHOLDS.derive(
        rounding_ulps=float(LUMPED_ANALYTIC_REFERENCE_THRESHOLDS["rounding_ulps"]) * 10.0)
    assert not overridden.is_declared
    lines = _issued("thermal_models.lumped.series_recurrence")
    lines["thresholds"] = overridden.evidence()[0]
    withheld = _check(lines.values(), level=None)  # what `award` returns for an override
    assert withheld.establishes is None
    assert withheld.residual == 1e-9 and withheld.tolerance == 1e-6
