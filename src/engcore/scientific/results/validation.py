"""Validation reporting.

Three deliberate design decisions:

1. **Checks coexist; the level is derived, never asserted.** A single scalar
   "validation level" is misleading, because dimensional validity, numerical
   convergence and experimental agreement are independent claims. A report
   therefore holds a list of checks, and any attained level must be *backed
   by a passing check that declares it*.

2. **NOT_RUN is distinct from PASS.** A check that never executed can never
   contribute evidence. This is the mechanism that prevents a result from
   claiming validation that was not actually performed.

3. **A check may not claim more than its own numbers support.** Decisions 1
   and 2 between them established that a level is backed by a *passing* check
   that *compared something*. Neither of them asked whether the comparison
   succeeded, and so neither of them stopped a check from reporting PASS with
   ``residual=10.0`` beside ``tolerance=1e-6`` -- seven orders outside its own
   bound -- and carrying ``ANALYTICALLY_VERIFIED`` all the way to a SUPPORTED
   verdict. The level was derived, exactly as decision 1 promises. The *pass*
   was asserted. See :func:`comparison_met_its_bound` and
   :func:`outcome_is_earned`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..sequences import duplicates
from ..errors import ScientificValidationError
from ..serialization import require_schema, schema_string

CHECK_SCHEMA = schema_string("validation_check")
REPORT_SCHEMA = schema_string("validation_report")


def compared_something(
    residual: float | None,
    tolerance: float | None,
    evidence: tuple[str, ...],
) -> bool:
    """Is there evidence that a comparison was performed?

    Two admissible forms, and the second is why the rule is not written as
    "must have a residual".

    **A measured quantity against a stated bound** -- ``residual`` *and*
    ``tolerance``. Both, not either: a residual with no tolerance is a number
    nobody bounded, and a tolerance with no residual is a bound with nothing
    measured against it. Neither on its own is a comparison.

    **A named reference** -- a non-empty ``evidence``. Some levels are
    established by comparing against something that yields no number at all.
    ``DIMENSIONALLY_VALID`` is the standing example: what is compared is the
    dimension of each produced metric against the ``unit_exemplar`` its
    ``ModelOutputSpec`` declares, and the outcome is a yes or a no, not a
    residual that could be small. Writing the rule as "must have a residual"
    would be narrower than the truth and would push an honest check into
    claiming a number it does not have.
    """
    if residual is not None and tolerance is not None:
        return True
    return bool(evidence)


def comparison_met_its_bound(
    residual: float | None,
    tolerance: float | None,
) -> bool | None:
    """Did the measured quantity actually meet the bound it was judged against?

    Three answers, and the third is the one that keeps this rule from
    swallowing the evidence-only form :func:`compared_something` exists to
    protect.

    ``None`` -- **there is no comparison of this shape to judge.** Either
    number absent. ``DIMENSIONALLY_VALID`` is the standing example: what it
    compares is a dimension against a ``unit_exemplar``, and the outcome is a
    yes or a no, not a number that could be small. A check in that form has
    nothing here to contradict, and this function says so rather than
    inventing a verdict about it.

    ``False`` -- the residual missed the bound, *or* either number is not
    finite. A NaN is refused for the reason :class:`RouteComparison` already
    refuses one: ``nan <= tolerance`` is ``False`` and ``nan > tolerance`` is
    also ``False``, so a rule written only as "not greater than" would read a
    NaN as compliant and let the identical defect back in wearing a different
    hat. A quantity that cannot be ordered against its bound was not compared
    to it.

    ``True`` -- both numbers are finite and ``residual <= tolerance``.
    """
    if residual is None or tolerance is None:
        return None
    residual = float(residual)
    tolerance = float(tolerance)
    if not (math.isfinite(residual) and math.isfinite(tolerance)):
        return False
    return residual <= tolerance


def outcome_is_earned(
    outcome: "ValidationOutcome",
    establishes: "ValidationLevel | None",
    residual: float | None,
    tolerance: float | None,
) -> bool:
    """GUARD 21's rule, over plain fields rather than over an object.

    Fields rather than a check, for the reason :func:`level_is_earned` gives
    and for the same reason: a rule an object could answer for itself is the
    shape of the defect being closed.

    **The rule.** A check that *claims success* while carrying both a residual
    and a tolerance must have met that tolerance. ``compared_something``
    establishes that a comparison happened; this establishes that it
    succeeded. Nothing else in this module asked, which is how a PASS carrying
    ``residual=10.0`` against ``tolerance=1e-6`` reached a SUPPORTED verdict
    with its own numbers standing seven orders away, in the same record,
    disagreeing with it.

    **What counts as claiming success**, and why this is not scoped to
    ``outcome`` alone. Two claims live on a check and they are separable:

    * ``outcome is PASS`` claims *this check succeeded*. There is no reading
      of PASS under which "the number missed its bound" is consistent, so a
      PASS is held to the comparison unconditionally -- level or no level.
    * ``establishes=X`` claims *X is now backed by this check*. That claim is
      made by a WARNING too, and a WARNING is a pass with a caveat when it
      makes it, so a level-declaring WARNING is held to the same standard.

    **A WARNING that declares no level claims neither, and is left alone.**
    That is not an exemption carved for a site; it is the rule reaching only
    as far as the claims. A level-free WARNING is inert as evidence:
    ``attained_levels`` reads ``c.passed``, which is ``outcome is PASS``, so
    such a check contributes nothing for a residual to contradict. And the
    form is load-bearing rather than incidental -- ``RouteConsensus.to_check``
    builds exactly one, deliberately, for routes that share their machinery
    and disagree: the disagreement is a real finding about the implementation,
    reported with the two numbers that are the *reason* for the WARNING, while
    the level is already withheld because ``earned`` requires agreement.
    Refusing that construction would delete the platform's only way to say
    "these routes disagreed and I am not calling it a scientific failure" and
    would replace a correct scientific report with an exception.

    **FAIL and NOT_RUN claim nothing** and are not held to anything here. A
    FAIL is free to sit inside its tolerance, and one in this repository does:
    a refinement gate FAILs on a residual that is *within* bound when the
    sequence behind it never contracted, because agreement with no convergent
    sequence behind it is not verification. That construction is also why this
    is a refusal and not a derivation -- see
    :meth:`ValidationCheck.__post_init__`.
    """
    met = comparison_met_its_bound(residual, tolerance)
    if met is None or met:
        return True
    if outcome is ValidationOutcome.PASS:
        return False
    if outcome is ValidationOutcome.WARNING and establishes is not None:
        return False
    return True


def level_is_earned(
    establishes: "ValidationLevel | None",
    outcome: "ValidationOutcome",
    residual: float | None,
    tolerance: float | None,
    evidence: tuple[str, ...],
) -> bool:
    """GUARD 2's rule, over plain fields rather than over an object.

    It takes fields rather than a check for one reason: the rule has to be
    applicable to something that *claims* to be a check. A method can be
    overridden and a property can be shadowed, so a rule that could only be
    asked of an object would be a rule the object got to answer for itself --
    which is the shape of the defect this function exists to close, one level
    down. Read the fields, apply the rule, decide here.

    **The rule.** A check that PASSes and declares a level must have compared
    something. A PASS with a level and no residual, no tolerance and no
    reference is a *claimed* level: a sentence asserting that the thing it
    names is true, occupying the field a reader consults to find out whether
    anybody checked.

    **Scoped to PASS and WARNING, deliberately.** A FAIL or NOT_RUN check
    contributes no level to ``attained_levels`` whatever it declares, so
    requiring evidence from one would be demanding proof of a claim nobody is
    making. A WARNING is a pass with a caveat and is held to the same standard.
    A check that declares no level asserts nothing and needs to show nothing.
    """
    if establishes is None:
        return True
    if outcome not in (ValidationOutcome.PASS, ValidationOutcome.WARNING):
        return True
    return compared_something(residual, tolerance, evidence)


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
        # GUARD 21, enforced. Last, because it reads the two numbers and wants
        # them coerced to float first.
        #
        # REFUSED, NOT DERIVED, and the choice is decided by a construction in
        # this repository rather than by taste. Deriving `outcome` from the two
        # numbers is the stronger-looking move and matches the platform's own
        # principle that a derivable fact should be derived -- but that
        # principle applies only where the fact really is derivable from what
        # is at hand, and `outcome` is not. `residual <= tolerance` is
        # NECESSARY for a PASS and it is not SUFFICIENT: the outcome is a
        # conjunction over evidence the check does not carry.
        #
        # A refinement-gate check in this repository proves it, and the FAST
        # suite exercises the branch. It FAILs while the residual it reports
        # sits INSIDE its own tolerance, because the outcome is a conjunction:
        # the sequence must also have contracted. A single refinement can land
        # close by luck while the sequence never contracts, and agreement with
        # no convergent sequence behind it is not verification, it is a
        # coincidence. A derivation would read those two numbers, see
        # agreement, and promote that FAIL to a PASS carrying a level. It
        # would not close this defect; it would open its mirror image, and the
        # mirror image is the worse one, because it manufactures a level
        # nobody claimed.
        #
        # So the implication is kept in the one direction the numbers support:
        # PASS implies the bound was met, never the converse. What deriving
        # would have cost, beyond that FAIL: the two WARNING forms below, and
        # a change to the meaning of `outcome` at every one of the sixty-odd
        # construction sites across five domains that pass it in today.
        if not self.outcome_is_earned:
            raise ScientificValidationError(
                f"validation check {self.name!r} reports "
                f"{self.outcome.value.upper()}"
                + (
                    f" and declares establishes={self.establishes.value}"
                    if self.establishes is not None
                    else ""
                )
                + f", but its own numbers say the comparison did not succeed: "
                f"residual={self.residual!r} against tolerance="
                f"{self.tolerance!r}. A check that reports success while the "
                f"quantity it measured stands outside the bound it was judged "
                f"against contradicts itself in the same record, and the "
                f"contradiction is invisible to every reader who consults the "
                f"outcome. Report the outcome the comparison actually had, or "
                f"-- if the outcome turns on something these two numbers do "
                f"not decide -- do not report it as a success"
            )

    @property
    def passed(self) -> bool:
        return self.outcome is ValidationOutcome.PASS

    @property
    def compared_something(self) -> bool:
        """Does this check carry evidence that a comparison was performed?

        The rule itself is :func:`compared_something`; this is the way to ask
        it about this check.
        """
        return compared_something(self.residual, self.tolerance, self.evidence)

    @property
    def earns_its_level(self) -> bool:
        """Is this check's declared level backed by an actual comparison?

        The rule itself is :func:`level_is_earned`, which reads fields rather
        than objects. This is the way to ask it about this check, and it is
        deliberately not the only way: ``ValidationReport`` asks the same
        function about whatever it has been handed, because a report that
        asked the object would be letting the object answer for itself.

        **Enforced in ``__post_init__``.** The constructor refuses anything
        that fails it, so a claimed level is a value that cannot be built
        rather than one a sweep looks for. It was a checked invariant until the
        thermal re-freeze: exactly one construction failed the rule and lived
        inside a byte-pinned file, and exempting it would have been a guard
        with a hole in it.
        """
        return level_is_earned(
            self.establishes,
            self.outcome,
            self.residual,
            self.tolerance,
            self.evidence,
        )

    @property
    def comparison_met_its_bound(self) -> bool | None:
        """Did this check's residual meet its tolerance? ``None`` if no such pair.

        The rule itself is :func:`comparison_met_its_bound`; this is the way to
        ask it about this check.
        """
        return comparison_met_its_bound(self.residual, self.tolerance)

    @property
    def outcome_is_earned(self) -> bool:
        """Is this check's claim of success consistent with its own numbers?

        The rule itself is :func:`outcome_is_earned`, which reads fields rather
        than objects. This is the way to ask it about this check, and -- as
        with :attr:`earns_its_level` -- it is deliberately not the only way:
        ``ValidationReport`` asks the same function about whatever it has been
        handed, because a report that asked the object would be letting the
        object answer for itself.

        **Enforced in ``__post_init__``.** A PASS whose residual exceeds its
        tolerance is a value that cannot be built, not one a sweep looks for.
        """
        return outcome_is_earned(
            self.outcome,
            self.establishes,
            self.residual,
            self.tolerance,
        )

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
    """The set of checks performed on one result, and what they establish.

    THE SECOND AXIS OF GUARD 2
    ---------------------------
    ``ValidationCheck.__post_init__`` closed the *construction* axis: a check
    claiming a level it did not check for cannot be built. It said nothing
    about the *containment* axis, and this record read whatever it was handed.
    An object that was not a ``ValidationCheck`` at all -- anything with a
    ``passed`` and an ``establishes`` -- placed straight into ``checks``
    reached :attr:`attained_levels`, satisfied :meth:`claims` and passed
    :meth:`require_level`. The constructor rule was never consulted, because
    the constructor was never called.

    That is the third time this shape has appeared here: a guard complete on
    one axis, read as complete. So this record now applies the rule itself, to
    whatever it is given, at both the moment it is given it and every time a
    level is read off it -- and it applies it through :func:`level_is_earned`,
    over fields, so an object that overrides ``earns_its_level`` cannot answer
    the question about itself.
    """

    checks: tuple[ValidationCheck, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        for index, check in enumerate(self.checks):
            if not isinstance(check, ValidationCheck):
                raise ScientificValidationError(
                    f"validation report entry {index} is a "
                    f"{type(check).__name__}, not a ValidationCheck. A record "
                    f"that reads `passed` and `establishes` off whatever it "
                    f"was handed is a record in which the constructor rule was "
                    f"never consulted, because the constructor was never called"
                )
        self._require_every_level_earned()
        self._require_no_check_contradicts_its_numbers()
        names = [c.name for c in self.checks]
        duplicated = duplicates(names)
        if duplicated:
            raise ScientificValidationError(
                f"duplicate validation check names: {duplicated}"
            )

    def _require_every_level_earned(self) -> None:
        """Apply GUARD 2's rule to the fields of every check held here.

        Redundant with ``ValidationCheck.__post_init__`` for a check that was
        constructed and never touched again, and deliberately so. A frozen
        dataclass refuses ``check.evidence = ()``; it does not refuse
        ``object.__setattr__(check, "evidence", ())``, which is available for
        every frozen record in this repository and cannot be closed on the
        record itself. What *can* be closed is the place where a level stops
        being a field and becomes a claim, and that place is here.
        """
        for check in self.checks:
            if not level_is_earned(
                check.establishes,
                check.outcome,
                check.residual,
                check.tolerance,
                check.evidence,
            ):
                raise ScientificValidationError(
                    f"validation check {check.name!r} in this report reports "
                    f"{ValidationOutcome(check.outcome).value.upper()} and "
                    f"declares establishes="
                    f"{ValidationLevel(check.establishes).value}, but carries "
                    f"no evidence that anything was compared. The constructor "
                    f"refuses this, so a check that reaches a report in this "
                    f"state was altered after it was built or never went "
                    f"through the constructor at all -- either way the level "
                    f"is a claim and not a finding"
                )

    def _require_no_check_contradicts_its_numbers(self) -> None:
        """Apply GUARD 21's rule to the fields of every check held here.

        Redundant with ``ValidationCheck.__post_init__`` for a check that was
        constructed and never touched again, and deliberately so -- the
        argument is :meth:`_require_every_level_earned`'s, verbatim and for the
        same reason. A frozen dataclass refuses ``check.residual = 10.0``; it
        does not refuse ``object.__setattr__(check, "residual", 10.0)``, which
        is available for every frozen record in this repository and cannot be
        closed on the record itself. What *can* be closed is the place where an
        outcome stops being a field and becomes a claim a reader acts on, and
        that place is here.
        """
        for check in self.checks:
            if not outcome_is_earned(
                check.outcome,
                check.establishes,
                check.residual,
                check.tolerance,
            ):
                raise ScientificValidationError(
                    f"validation check {check.name!r} in this report reports "
                    f"{ValidationOutcome(check.outcome).value.upper()} while "
                    f"its own residual {check.residual!r} stands outside its "
                    f"own tolerance {check.tolerance!r}. The constructor "
                    f"refuses this, so a check that reaches a report in this "
                    f"state was altered after it was built or never went "
                    f"through the constructor at all -- either way the success "
                    f"is a claim and not a finding"
                )

    # ---- derived state --------------------------------------------------
    @property
    def status(self) -> ValidationOutcome:
        """Aggregate outcome. FAIL dominates; an empty report is NOT_RUN.

        The comparison rule is re-applied here for the reason it is re-applied
        on :attr:`attained_levels`, one field over. GUARD 2 is about levels, so
        it is re-read where a level becomes a claim; GUARD 21 is about
        *outcomes*, and this is where an outcome becomes one.
        """
        self._require_no_check_contradicts_its_numbers()
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
        # Re-applied on the read, not only on construction. A check can be
        # altered after the report holding it was built, and the level only
        # matters at the moment it is read as a claim -- so the rule is applied
        # at that moment, over fields, whatever the object says about itself.
        self._require_every_level_earned()
        self._require_no_check_contradicts_its_numbers()
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
