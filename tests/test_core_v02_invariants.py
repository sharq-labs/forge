"""Core V0.2 — invariants a mutation probe found nothing was protecting.

Every test here exists because a specific dangerous edit to the Scientific
Core survived the entire 876-test suite. They are not additional coverage for
its own sake; each one names the mutation it kills.

The probe applied comparison-boundary flips, and/or swaps and ``frozen=True``
removal to load-bearing modules and asked whether any test noticed. What it
found, in the results package:

    result.py:118-120   ScientificResult.is_usable -- the whole predicate.
                        `and`->`or`, `in`->`not in` and `is not`->`is` all
                        survived. Three tests touch it and all three assert
                        only `not result.is_usable`, so nothing pinned the
                        True side or the boundary between them.
    uncertainty.py:54   confidence_level bounds. Zero test references it.
    uncertainty.py:65   standard_uncertainty >= 0. The zero case, which the
                        module's own docstring calls a distinct scientific
                        statement, was never constructed.
    uncertainty.py:75   INTERVAL requires BOTH bounds. A test does cover it,
                        but passes on a downstream dimensionality error rather
                        than the guard, so removing the guard changes nothing.
    uncertainty.py:82   upper >= lower, including the degenerate equal case.
    frozen=True         on ValidationCheck, ValidationReport, Uncertainty and
                        ScientificResult. 39 frozen dataclasses in the
                        scientific core and no test asserted immutability of
                        any of them.

Why immutability is load-bearing rather than hygiene: ``attained_levels`` is
derived from the checks and is deliberately never settable, so a result can
only claim validation some check established. That guarantee is enforced on
the deserialization path by ``from_dict``. In memory it rests entirely on
``frozen=True`` -- lose it, and a passing level can be manufactured on an
existing report by assignment.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.engcore.scientific.errors import ScientificCoreError
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.result import ScientificResult
from src.engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from src.engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from src.engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from src.engcore.scientific.units.quantity import Quantity


def _provenance() -> ProvenanceRecord:
    return ProvenanceRecord(
        run_id="core-v02-0001",
        software_version="scientific-core-v0",
        git_commit="0" * 40,
        models=(("synthetic.linear_response", "1.0.0"),),
        solvers=(("algebraic", "1.0.0"),),
        inputs={"drive_level": Quantity(5.0, "volt")},
        assumptions=("synthetic",),
        tolerances={"rtol": 1e-9},
        environment={"python": "3.x"},
        timestamp="2026-01-01T00:00:00+00:00",
    )


def _report(outcome: ValidationOutcome) -> ValidationReport:
    """A one-check report with the requested aggregate status."""
    if outcome is ValidationOutcome.NOT_RUN:
        return ValidationReport(
            checks=(ValidationCheck("c", ValidationOutcome.NOT_RUN),)
        )
    return ValidationReport(checks=(ValidationCheck("c", outcome),))


def _result(**overrides) -> ScientificResult:
    payload = dict(
        result_id="core-v02-0001",
        problem_id="synthetic_algebraic_v0",
        values={"load": Quantity(2.5, "watt")},
        models=(("synthetic.linear_response", "1.0.0"),),
        solver=SolverIdentity("algebraic", "1.0.0"),
        convergence=ConvergenceState.NOT_APPLICABLE,
        validation=ValidationReport(),
        provenance=_provenance(),
    )
    payload.update(overrides)
    return ScientificResult(**payload)


# =====================================================================
# ScientificResult.is_usable — the full truth table
# =====================================================================

#: Convergence states that permit use. NOT_APPLICABLE is here because a
#: closed-form evaluation neither converges nor fails to; the contract is
#: explicit that it must not be conflated with CONVERGED, and it must equally
#: not be treated as a failure.
USABLE_CONVERGENCE = (
    ConvergenceState.CONVERGED,
    ConvergenceState.NOT_APPLICABLE,
)
UNUSABLE_CONVERGENCE = (
    ConvergenceState.NOT_CONVERGED,
    ConvergenceState.MAX_ITERATIONS,
    ConvergenceState.DIVERGED,
    ConvergenceState.FAILED,
)
#: FAIL is the only validation status that blocks use. NOT_RUN deliberately
#: does not: "nothing was checked" is not "a check failed", and collapsing
#: them would make an unvalidated result indistinguishable from a refuted one.
NON_BLOCKING_VALIDATION = (
    ValidationOutcome.PASS,
    ValidationOutcome.WARNING,
    ValidationOutcome.NOT_RUN,
)


@pytest.mark.parametrize("convergence", USABLE_CONVERGENCE + UNUSABLE_CONVERGENCE)
@pytest.mark.parametrize(
    "validation", NON_BLOCKING_VALIDATION + (ValidationOutcome.FAIL,)
)
def test_is_usable_is_exactly_converged_and_not_failed(
    convergence: ConvergenceState, validation: ValidationOutcome
) -> None:
    """The full 6x4 truth table of the usability gate.

    Kills three mutations at once: `and`->`or` (which would make either
    condition sufficient), `in`->`not in` (which would invert the convergence
    set) and `is not`->`is` (which would invert the validation test).
    """
    result = _result(convergence=convergence, validation=_report(validation))
    expected = (
        convergence in USABLE_CONVERGENCE
        and validation is not ValidationOutcome.FAIL
    )
    assert result.is_usable is expected


def test_is_usable_needs_both_conditions_not_either() -> None:
    """Pinned separately from the table so an `and`->`or` regression names
    itself: each condition alone must not be enough."""
    converged_but_failed = _result(
        convergence=ConvergenceState.CONVERGED,
        validation=_report(ValidationOutcome.FAIL),
    )
    diverged_but_passing = _result(
        convergence=ConvergenceState.DIVERGED,
        validation=_report(ValidationOutcome.PASS),
    )
    assert not converged_but_failed.is_usable
    assert not diverged_but_passing.is_usable


def test_is_usable_does_not_mean_validated() -> None:
    """It reports the absence of known problems, not the presence of proof.

    A result with nothing checked at all is usable and claims no levels. If
    these ever diverge, the docstring's careful distinction has been lost.
    """
    result = _result(validation=ValidationReport())
    assert result.is_usable
    assert result.attained_levels == frozenset()
    assert result.validation_status is ValidationOutcome.NOT_RUN


# =====================================================================
# Uncertainty — boundaries, not just happy paths
# =====================================================================

@pytest.mark.parametrize("level", [0.0, 1.0, -0.1, 1.1, 2.0])
def test_confidence_level_must_be_strictly_inside_zero_and_one(level: float) -> None:
    """0.0 and 1.0 are the mutation-sensitive ends: `<` -> `<=` admits them.

    Neither is meaningful. A 0% credible interval states nothing and a 100%
    one claims certainty no finite computation established.
    """
    with pytest.raises(ScientificCoreError, match="strictly between"):
        Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(1.0, "kelvin"),
            method="probe",
            confidence_level=level,
        )


def test_a_legitimate_confidence_level_is_accepted() -> None:
    record = Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(1.0, "kelvin"),
        method="probe",
        confidence_level=0.95,
    )
    assert record.confidence_level == 0.95


def test_zero_standard_uncertainty_is_a_claim_not_an_error() -> None:
    """A computed-but-zero uncertainty differs from UNKNOWN, and the contract
    says so. `< 0.0` -> `<= 0.0` would reject the zero case and silently
    collapse that distinction."""
    exact = Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(0.0, "kelvin"),
        method="exact_arithmetic",
    )
    assert exact.is_quantified
    assert exact.kind is not UncertaintyKind.UNKNOWN
    assert not Uncertainty.unknown().is_quantified


def test_negative_standard_uncertainty_is_refused() -> None:
    with pytest.raises(ScientificCoreError, match="non-negative"):
        Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(-1e-30, "kelvin"),
            method="probe",
        )


@pytest.mark.parametrize(
    "bounds",
    [
        {"lower": Quantity(1.0, "kelvin")},
        {"upper": Quantity(2.0, "kelvin")},
        {},
    ],
)
def test_interval_requires_both_bounds_by_its_own_guard(bounds: dict) -> None:
    """Matches the guard's message, not merely "something raised".

    The pre-existing test asserted only that a ScientificCoreError appeared,
    which a downstream dimensionality failure also satisfies -- so deleting
    the guard left that test green. Matching the message pins the guard.
    """
    with pytest.raises(ScientificCoreError, match="requires both lower and upper"):
        Uncertainty(kind=UncertaintyKind.INTERVAL, method="probe", **bounds)


def test_a_degenerate_interval_is_legal() -> None:
    """upper == lower is a zero-width interval: an exactly known value. The
    boundary that separates it from an inverted interval is one `<`."""
    record = Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(1.0, "kelvin"),
        upper=Quantity(1.0, "kelvin"),
        method="exact_arithmetic",
    )
    assert record.is_quantified


def test_an_inverted_interval_is_refused() -> None:
    with pytest.raises(ScientificCoreError, match="below lower bound"):
        Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(2.0, "kelvin"),
            upper=Quantity(1.0, "kelvin"),
            method="probe",
        )


# =====================================================================
# Immutability — the in-memory half of the anti-forgery guarantee
# =====================================================================

def test_a_validation_verdict_cannot_be_flipped_after_construction() -> None:
    """The concrete forgery `frozen=True` is preventing.

    ``attained_levels`` reads the checks, so if a check's outcome could be
    reassigned, a NOT_RUN check could be promoted to PASS on a live report and
    the level would follow. ``from_dict`` blocks this on load; only frozenness
    blocks it here.
    """
    check = ValidationCheck(
        name="analytic_agreement",
        outcome=ValidationOutcome.NOT_RUN,
        establishes=ValidationLevel.ANALYTICALLY_VERIFIED,
    )
    report = ValidationReport(checks=(check,))
    assert report.attained_levels == frozenset()

    with pytest.raises(dataclasses.FrozenInstanceError):
        check.outcome = ValidationOutcome.PASS  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.checks = ()  # type: ignore[misc]

    assert report.attained_levels == frozenset()
    assert not report.claims(ValidationLevel.ANALYTICALLY_VERIFIED)


def test_a_result_cannot_be_reattributed_after_construction() -> None:
    """Provenance that can be swapped out is not provenance."""
    result = _result()
    for field_name, value in (
        ("result_id", "someone-elses-run"),
        ("provenance", _provenance()),
        ("values", {}),
        ("convergence", ConvergenceState.CONVERGED),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(result, field_name, value)


def test_an_uncertainty_record_cannot_be_upgraded_in_place() -> None:
    unknown = Uncertainty.unknown("not evaluated")
    with pytest.raises(dataclasses.FrozenInstanceError):
        unknown.kind = UncertaintyKind.STANDARD  # type: ignore[misc]
    assert not unknown.is_quantified


#: The results package is where scientific claims are recorded, so everything
#: in it is expected to be immutable. Asserted as a set rather than one type
#: at a time: a new mutable record added here later should have to justify
#: itself by failing this test.
RESULT_RECORD_TYPES = (
    ScientificResult,
    ValidationCheck,
    ValidationReport,
    Uncertainty,
    ProvenanceRecord,
    SolverIdentity,
)


@pytest.mark.parametrize("record_type", RESULT_RECORD_TYPES)
def test_every_scientific_record_type_is_frozen(record_type: type) -> None:
    assert dataclasses.is_dataclass(record_type)
    assert record_type.__dataclass_params__.frozen, (
        f"{record_type.__name__} is mutable; scientific records must not be "
        f"editable after construction"
    )
