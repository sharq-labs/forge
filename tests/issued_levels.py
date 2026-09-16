"""A genuinely ISSUED validation check, for tests whose subject is a level-bearing check.

R-04 (core re-audit 2026-09-16) closed the last hole in the issuer rule: ANALYTICALLY_VERIFIED needed
no issuer at all, so ``ValidationCheck(PASS, establishes=ANALYTICALLY_VERIFIED, evidence=("trust me",))``
was constructed, attained and carried a SUPPORTED verdict. Now all four of the levels an external
issuer grants are held to that issuer's record.

Dozens of tests across this suite use a level-bearing PASS check as a FIXTURE: their subject is a
verdict, a serialized record, a report's derived state or a repair message, and the level is only how
they get a report past "no check both passed and established a level". Those tests must keep testing
exactly what they tested, so they build the check here instead of by hand.

This is a support module beside ``zero_provider.py`` and ``mutation_guards.py`` rather than a test: it
constructs records and holds no assertions.

The two functions differ in what they are FOR:

* :func:`issued_analytic_check` is the real thing -- the same two evidence records the production
  producers write, over a reference this repository pins. A test that needs an ANALYTICALLY_VERIFIED
  check that the core accepts wants this one.
* :func:`unissued_level_check` names a level that needs no issuer, for a test whose subject is
  "some level was attained" and nothing more. DIMENSIONALLY_VALID and NUMERICALLY_CONVERGED still
  need none, which the batch-9 protocol records as an open residual under R-04; when that closes,
  this function is where the change lands, once, rather than in each caller.
"""

from __future__ import annotations

from engcore.domains import (
    SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS,
    SCIENTIFIC_THRESHOLD_DECLARATIONS,
)
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
)

#: The reference used when a caller does not name one. The lumped series recurrence: it is the one the
#: production MCP report rests on, so a test using it exercises the same issuer path production does.
DEFAULT_REFERENCE = "thermal_models.lumped.series_recurrence"


def analytic_issuer_evidence(reference_id: str = DEFAULT_REFERENCE) -> tuple[str, ...]:
    """The evidence lines a genuine issuer of ``reference_id`` writes.

    Resolved from the two registries rather than written out, so a test using this cannot drift from
    what the rule requires: the reference named as ``"<id>: <expression>"``, and the declared
    threshold record of the gate the registry says awards it.
    """
    declared = SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS[reference_id]
    gate = SCIENTIFIC_THRESHOLD_DECLARATIONS[declared["thresholds_gate"]]
    module, _, name = str(gate["declared_by"]).rpartition(".")
    thresholds = getattr(__import__(module, fromlist=[name]), name)
    return (f"{reference_id}: {declared['expression']}", *thresholds.evidence())


def issued_analytic_check(
    name: str = "analytic_reference_agreement",
    *,
    outcome: ValidationOutcome = ValidationOutcome.PASS,
    residual: float | None = 1.0e-9,
    tolerance: float | None = 1.0e-6,
    detail: str = "agrees with the pinned closed form",
    reference_id: str = DEFAULT_REFERENCE,
    extra_evidence: tuple[str, ...] = (),
) -> ValidationCheck:
    """A PASS check that genuinely establishes ANALYTICALLY_VERIFIED."""
    return ValidationCheck(
        name=name,
        outcome=outcome,
        detail=detail,
        establishes=ValidationLevel.ANALYTICALLY_VERIFIED,
        residual=residual,
        tolerance=tolerance,
        evidence=analytic_issuer_evidence(reference_id) + tuple(extra_evidence),
    )


def unissued_level_check(
    name: str = "dimensional_check",
    *,
    outcome: ValidationOutcome = ValidationOutcome.PASS,
    residual: float | None = 0.0,
    tolerance: float | None = 1.0e-9,
    detail: str = "every reported quantity carries the declared dimension",
    evidence: tuple[str, ...] = ("fixture: the model record's declared units",),
) -> ValidationCheck:
    """A PASS check establishing a level that needs no issuer, for a test that needs only *a* level."""
    return ValidationCheck(
        name=name,
        outcome=outcome,
        detail=detail,
        establishes=ValidationLevel.DIMENSIONALLY_VALID,
        residual=residual,
        tolerance=tolerance,
        evidence=tuple(evidence),
    )
