"""Validation reporting.

Two deliberate design decisions:

1. **Checks coexist; the level is derived, never asserted.** A single scalar
   "validation level" is misleading, because dimensional validity, numerical
   convergence and experimental agreement are independent claims. A report
   therefore holds a list of checks, and any attained level must be *backed
   by a passing check that declares it*.

2. **NOT_RUN is distinct from PASS.** A check that never executed can never
   contribute evidence. This is the mechanism that prevents a result from
   claiming validation that was not actually performed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..errors import ScientificValidationError
from ..serialization import require_schema, schema_string

CHECK_SCHEMA = schema_string("validation_check")
REPORT_SCHEMA = schema_string("validation_report")


class ValidationOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_RUN = "not_run"


class ValidationLevel(str, Enum):
    """What has been established, in increasing evidentiary strength.

    These are *claims about evidence*, not a quality score. A result may
    attain several independently (dimensional validity and numerical
    convergence say different things).

    ``UNVERIFIED`` is the odd one out and is **not a level a check may
    establish** — see :attr:`ValidationCheck.establishes`, which refuses it. It
    is the sentinel for the *absence* of verification, kept as a member because
    it names that state for a reader and for :func:`unverified_report`, and
    kept out of every attained-level computation by being unable to reach one.
    """

    UNVERIFIED = "unverified"
    DIMENSIONALLY_VALID = "dimensionally_valid"
    NUMERICALLY_CONVERGED = "numerically_converged"
    ANALYTICALLY_VERIFIED = "analytically_verified"
    BENCHMARK_VALIDATED = "benchmark_validated"
    CROSS_SOLVER_VALIDATED = "cross_solver_validated"
    EXPERIMENTALLY_VALIDATED = "experimentally_validated"


@dataclass(frozen=True)
class ValidationCheck:
    """One executed (or deliberately skipped) verification step."""

    name: str
    outcome: ValidationOutcome
    detail: str = ""
    establishes: ValidationLevel | None = None
    residual: float | None = None
    tolerance: float | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ScientificValidationError("validation check requires a name")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "outcome", ValidationOutcome(self.outcome))
        if self.establishes is not None:
            establishes = ValidationLevel(self.establishes)
            # The sentinel is the absence of verification, so a check that
            # established it would be claiming to have established an absence.
            #
            # Refused **here**, at the one site where the claim is made, rather
            # than filtered at each site that reads it. Those sites are
            # `attained_levels`, `claims`, `require_level` and every consumer's
            # own `required_levels`, and the review found the last of them
            # disagreeing with the first: a passing check declaring UNVERIFIED
            # satisfied a caller's demand for it and produced a SUPPORTED
            # verdict — nothing verified, saying so, read as evidence. A rule
            # enforced at four reading sites is a rule that will be missed at
            # the fifth; a value that cannot exist cannot be read
            # inconsistently.
            #
            # Every outcome, not only PASS. A NOT_RUN check that "established
            # unverified" is the same category error in a humbler voice, and
            # allowing it would leave a payload shape whose meaning depends on
            # a field that is supposed to be inert.
            #
            # The way to say a check earned nothing is unchanged and is the one
            # the platform means: leave `establishes` as None. The lumped
            # residual check and the resistance admissibility bound already do,
            # and `unverified_report` builds a NOT_RUN check with no level at
            # all.
            if establishes is ValidationLevel.UNVERIFIED:
                raise ScientificValidationError(
                    f"validation check {str(self.name).strip()!r} declares "
                    f"establishes=UNVERIFIED. That is the sentinel for the "
                    f"absence of verification, not a level: a check cannot "
                    f"establish that nothing was established. Leave "
                    f"establishes unset to say a check earned no level"
                )
            object.__setattr__(self, "establishes", establishes)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        # GUARD 2, enforced. A PASS or WARNING declaring a level must carry
        # evidence that it compared something -- see `earns_its_level`, which
        # states the rule and is what this refuses on.
        #
        # This was a checked invariant in `tests/test_core_guards.py` rather
        # than a refusal, and the only reason was one construction inside a
        # byte-pinned file that could not be edited. The thermal re-freeze
        # fixed it, so the rule moves here, beside the `establishes=UNVERIFIED`
        # refusal it belongs next to and for the identical reason: a rule
        # enforced at the four sites that read levels is a rule that will be
        # missed at the fifth, and a value that cannot be constructed cannot be
        # read inconsistently.
        #
        # No exception, deliberately. An enforced guard with one exception is
        # an opt-in guard with extra words, and the hole would be the shape of
        # the next domain's mistake.
        if not self.earns_its_level:
            raise ScientificValidationError(
                f"validation check {self.name!r} reports "
                f"{self.outcome.value.upper()} and declares "
                f"establishes={self.establishes.value}, but carries no "
                f"evidence that anything was compared: no residual with a "
                f"tolerance, and no reference in `evidence`. A level with "
                f"nothing behind it is a claim occupying the field a reader "
                f"consults to find out whether anybody checked. Record what "
                f"was compared -- a residual and its bound, or the reference "
                f"the comparison was made against -- or leave establishes "
                f"unset, which is how a check says it earned nothing"
            )
        if self.residual is not None:
            object.__setattr__(self, "residual", float(self.residual))
        if self.tolerance is not None:
            object.__setattr__(self, "tolerance", float(self.tolerance))

    @property
    def passed(self) -> bool:
        return self.outcome is ValidationOutcome.PASS

    @property
    def compared_something(self) -> bool:
        """Does this check carry evidence that a comparison was performed?

        Two admissible forms, and the second is why the rule is not written as
        "must have a residual".

        **A measured quantity against a stated bound** -- ``residual`` *and*
        ``tolerance``. Both, not either: a residual with no tolerance is a
        number nobody bounded, and a tolerance with no residual is a bound with
        nothing measured against it. Neither on its own is a comparison.

        **A named reference** -- a non-empty ``evidence``. Some levels are
        established by comparing against something that yields no number at
        all. ``DIMENSIONALLY_VALID`` is the standing example: what is compared
        is the dimension of each produced metric against the ``unit_exemplar``
        its ``ModelOutputSpec`` declares, and the outcome of that comparison is
        a yes or a no, not a residual that could be small. Writing the rule as
        "must have a residual" would therefore be narrower than the truth and
        would push an honest check into claiming a number it does not have.
        ``evidence`` names what was compared against, which is what lets a
        reader check the claim rather than take it.
        """
        if self.residual is not None and self.tolerance is not None:
            return True
        return bool(self.evidence)

    @property
    def earns_its_level(self) -> bool:
        """Is this check's declared level backed by an actual comparison?

        **The rule.** A check that PASSes and declares ``establishes`` must
        have compared something. A PASS with a level and no residual, no
        tolerance and no reference is a *claimed* level -- a sentence asserting
        that the thing it names is true, occupying the field a reader consults
        to find out whether anybody checked. That is the single thing this
        project exists to refuse, and it is refused here rather than at the
        four sites that read levels.

        **Scoped to PASS, deliberately.** A FAIL or NOT_RUN check contributes
        no level to ``attained_levels`` whatever it declares, so requiring
        evidence from one would be demanding proof of a claim nobody is making.
        A WARNING is a pass with a caveat and is held to the same standard as a
        PASS. A check that declares no level is asserting nothing and needs to
        show nothing -- ``establishes=None`` remains the honest way to say a
        check earned no level.

        **Enforced in ``__post_init__``.** This property states the rule and
        the constructor refuses anything that fails it, so a claimed level is a
        value that cannot be built rather than one a sweep looks for. It was a
        checked invariant until the thermal re-freeze: exactly one construction
        failed the rule and lived inside a byte-pinned file, and exempting it
        would have been a guard with a hole in it.
        """
        if self.establishes is None:
            return True
        if self.outcome not in (
            ValidationOutcome.PASS,
            ValidationOutcome.WARNING,
        ):
            return True
        return self.compared_something

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHECK_SCHEMA,
            "name": self.name,
            "outcome": self.outcome.value,
            "detail": self.detail,
            "establishes": self.establishes.value if self.establishes else None,
            "residual": self.residual,
            "tolerance": self.tolerance,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationCheck":
        require_schema(payload, CHECK_SCHEMA)
        establishes = payload.get("establishes")
        return cls(
            name=payload["name"],
            outcome=ValidationOutcome(payload["outcome"]),
            detail=payload.get("detail", ""),
            establishes=ValidationLevel(establishes) if establishes else None,
            residual=payload.get("residual"),
            tolerance=payload.get("tolerance"),
            evidence=tuple(payload.get("evidence", ())),
        )


@dataclass(frozen=True)
class ValidationReport:
    """The set of checks performed on one result, and what they establish."""

    checks: tuple[ValidationCheck, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        names = [c.name for c in self.checks]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ScientificValidationError(
                f"duplicate validation check names: {sorted(duplicates)}"
            )

    # ---- derived state --------------------------------------------------
    @property
    def status(self) -> ValidationOutcome:
        """Aggregate outcome. FAIL dominates; an empty report is NOT_RUN."""
        outcomes = {c.outcome for c in self.checks}
        if ValidationOutcome.FAIL in outcomes:
            return ValidationOutcome.FAIL
        if ValidationOutcome.WARNING in outcomes:
            return ValidationOutcome.WARNING
        if ValidationOutcome.PASS in outcomes:
            return ValidationOutcome.PASS
        return ValidationOutcome.NOT_RUN

    @property
    def attained_levels(self) -> frozenset[ValidationLevel]:
        """Levels backed by a *passing* check. Never asserted directly.

        ``UNVERIFIED`` can never appear here, and needs no filter to keep it
        out: ``ValidationCheck`` refuses the value, so no check carries it.
        That is why this property, :meth:`claims` and every consumer's
        ``required_levels`` cannot disagree about the sentinel — there is
        nothing for them to disagree about.
        """
        return frozenset(
            c.establishes
            for c in self.checks
            if c.passed and c.establishes is not None
        )

    def claims(self, level: ValidationLevel) -> bool:
        return ValidationLevel(level) in self.attained_levels

    @property
    def failures(self) -> tuple[ValidationCheck, ...]:
        return tuple(c for c in self.checks if c.outcome is ValidationOutcome.FAIL)

    @property
    def warnings(self) -> tuple[ValidationCheck, ...]:
        return tuple(c for c in self.checks if c.outcome is ValidationOutcome.WARNING)

    @property
    def not_run(self) -> tuple[ValidationCheck, ...]:
        return tuple(c for c in self.checks if c.outcome is ValidationOutcome.NOT_RUN)

    def with_check(self, check: ValidationCheck) -> "ValidationReport":
        return ValidationReport(checks=(*self.checks, check), notes=self.notes)

    def require_level(self, level: ValidationLevel) -> None:
        """Raise unless the level was actually established."""
        if not self.claims(level):
            raise ScientificValidationError(
                f"validation level {ValidationLevel(level).value!r} was not "
                f"established by any passing check"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "checks": [c.to_dict() for c in self.checks],
            "status": self.status.value,
            "attained_levels": sorted(l.value for l in self.attained_levels),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationReport":
        require_schema(payload, REPORT_SCHEMA)
        report = cls(
            checks=tuple(
                ValidationCheck.from_dict(c) for c in payload.get("checks", ())
            ),
            notes=payload.get("notes", ""),
        )
        # Derived fields in the payload are advisory; recompute and verify so a
        # hand-edited record cannot smuggle in an unearned validation claim.
        declared = set(payload.get("attained_levels", ()))
        recomputed = {l.value for l in report.attained_levels}
        if declared and declared != recomputed:
            raise ScientificValidationError(
                f"serialized attained_levels {sorted(declared)} do not match "
                f"the levels established by its checks {sorted(recomputed)}"
            )
        return report


def unverified_report(reason: str = "no validation performed") -> ValidationReport:
    """An explicit 'nothing was checked' report — better than an empty one."""
    return ValidationReport(
        checks=(
            ValidationCheck(
                name="validation_performed",
                outcome=ValidationOutcome.NOT_RUN,
                detail=reason,
            ),
        )
    )
