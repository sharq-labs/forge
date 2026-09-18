"""Phase 0 stabilization: N4 (derive_verdict on NOT_APPLICABLE) and N5 (problem.py's missing import).

N4. ``ValidationOutcome.NOT_APPLICABLE`` is a record the core itself builds ("this circuit has no voltage
source"), and ``ValidationReport.status`` already excludes it from precedence (R-45). ``derive_verdict``
did not: a NOT_APPLICABLE check reached its fail-closed guard and the exported function raised. The fix
gives it the core's own meaning -- neutral -- and these tests pin the direction that matters: it can never
become a PASS, never attain a level, and never raise a verdict.

N5. ``ElectroThermalCaseRun.__post_init__`` raised ``ProblemPayloadError`` without importing it, so the
refusal it meant to issue surfaced as a ``NameError``.
"""

from __future__ import annotations

import pytest

from engcore.mcp.errors import ProblemPayloadError
from engcore.mcp.evidence import CredibilityEvidenceError, CredibilityVerdict, derive_verdict
from engcore.scientific.results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from test_verdict_monotonicity import (
    STRENGTH,
    SUPPORTING_CHECK,
    SUPPORTING_VALIDITY,
    _check,
)


def _na(name: str = "voltage_source_relation") -> ValidationCheck:
    return ValidationCheck(name=name, outcome=ValidationOutcome.NOT_APPLICABLE, detail="nothing to check")


def test_n4_not_applicable_beside_support_does_not_crash_and_changes_nothing():
    assert derive_verdict(validity=SUPPORTING_VALIDITY, validation=(SUPPORTING_CHECK,)) is CredibilityVerdict.SUPPORTED
    assert derive_verdict(validity=SUPPORTING_VALIDITY, validation=(SUPPORTING_CHECK, _na())) is CredibilityVerdict.SUPPORTED


def test_n4_not_applicable_alone_is_never_support():
    """The empty report's answer: nothing was established."""
    assert derive_verdict(validity=SUPPORTING_VALIDITY, validation=(_na(),)) is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert derive_verdict(validity=SUPPORTING_VALIDITY, validation=(_na("a"), _na("b"))) is CredibilityVerdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("outcome", [ValidationOutcome.FAIL, ValidationOutcome.NOT_RUN])
def test_n4_not_applicable_cannot_mask_adverse_evidence(outcome):
    bad = _check("other", outcome)
    without = derive_verdict(validity=SUPPORTING_VALIDITY, validation=(SUPPORTING_CHECK, bad))
    with_na = derive_verdict(validity=SUPPORTING_VALIDITY, validation=(SUPPORTING_CHECK, bad, _na()))
    assert with_na is without
    assert without is not CredibilityVerdict.SUPPORTED


def test_n4_adding_not_applicable_never_strengthens_any_verdict():
    for validation in [(), (SUPPORTING_CHECK,), (_check("x", ValidationOutcome.NOT_RUN),),
                       (_check("x", ValidationOutcome.FAIL),)]:
        base = derive_verdict(validity=SUPPORTING_VALIDITY, validation=validation)
        more = derive_verdict(validity=SUPPORTING_VALIDITY, validation=validation + (_na(),))
        assert STRENGTH[more] <= STRENGTH[base]


def test_n4_not_applicable_cannot_satisfy_a_required_level():
    verdict = derive_verdict(
        validity=SUPPORTING_VALIDITY,
        validation=(SUPPORTING_CHECK, _na()),
        required_levels=(ValidationLevel.EXPERIMENTALLY_VALIDATED,),
    )
    assert verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_n4_a_duck_typed_not_applicable_claiming_a_level_is_refused():
    """The core's constructor refuses this; the exported function must not read past a duck-typed copy."""
    from types import SimpleNamespace

    forged = SimpleNamespace(
        name="forged", outcome="not_applicable", establishes=ValidationLevel.ANALYTICALLY_VERIFIED,
        residual=0.0, tolerance=1e-9, evidence=(),
    )
    with pytest.raises(CredibilityEvidenceError, match="NOT_APPLICABLE"):
        derive_verdict(validity=SUPPORTING_VALIDITY, validation=(SUPPORTING_CHECK, forged))


def test_n4_an_unknown_outcome_still_fails_closed():
    from types import SimpleNamespace

    alien = SimpleNamespace(name="alien", outcome="probably_fine", establishes=None)
    with pytest.raises(CredibilityEvidenceError):
        derive_verdict(validity=SUPPORTING_VALIDITY, validation=(SUPPORTING_CHECK, alien))


def test_n5_mismatched_repairs_raise_the_declared_refusal_not_a_name_error():
    from engcore.mcp.problem import ElectroThermalCaseRun

    with pytest.raises(ProblemPayloadError, match="repair groups"):
        ElectroThermalCaseRun(run=None, reports=(), repairs=((),))


def test_n5_problem_module_names_every_error_it_raises():
    """Static guard: every ``raise X(`` in problem.py resolves to a name the module defines or imports."""
    import ast
    import pathlib

    import engcore.mcp.problem as problem

    tree = ast.parse(pathlib.Path(problem.__file__).read_bytes().decode("utf-8"))
    raised = {
        node.exc.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name)
    }
    import builtins

    missing = sorted(n for n in raised if not hasattr(problem, n) and not hasattr(builtins, n))
    assert missing == [], f"problem.py raises names it never binds: {missing}"
