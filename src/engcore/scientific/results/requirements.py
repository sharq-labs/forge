"""The declarations a problem makes about its own validation, read (I-19, R-72).

``ScientificProblem`` carries two declarations that read, to any engineer holding the record, as
gates: :attr:`~engcore.scientific.ir.problem.ScientificProblem.validation_requirements` names the
checks a result must carry, and
:class:`~engcore.scientific.ir.problem.UncertaintySpecification` demands REPORTED or QUANTIFIED
uncertainty on named metrics, optionally at a named confidence level.

The 2026-09-16 re-audit found that **nothing in this tree read either of them**. A result carrying
one unrelated check and UNKNOWN uncertainty was ``is_usable``, its report status was PASS, and
``TrustedExecutionRuntime`` -- the one place in ``src`` that holds the admitted problem and the
validation report together -- called such a record ``trusted``. This module is the rule those
places now read. It decides nothing by itself: it says what is unmet, and hands back the NOT_RUN
checks that say so in a record.

**NOT_RUN and not FAIL**, for the reason the credibility boundary's own ``solver_convergence`` and
``stored_result_attribution`` checks are NOT_RUN: nothing here found the values false. The check the
problem demanded was not run, or the uncertainty it demanded was not computed. The work to
recommend is to run it; FAIL would recommend discarding a result that may be perfectly correct.

**The registry** exists because a requirement name was never validated, so ``numerically_convergd``
was accepted and -- since nothing read the field -- never noticed. Every module in this tree that
emits a check kind a problem declares registers it beside the emitter, and a requirement naming no
registered kind is UNSATISFIABLE: it is reported as unmet, with the registered kinds named, wherever
a requirement is enforced.

It is read at ENFORCEMENT time and not at construction, deliberately. The scientific core may not
reach down into a domain package, so the registry is populated only when a domain is itself
imported; a refusal at ``ScientificProblem.__post_init__`` or ``from_dict`` would therefore make a
problem record's acceptability depend on which domain modules a process happens to have loaded, and
a guard that switches itself off with the import graph is worse than no guard. At enforcement time
the domain is necessarily loaded -- its result is the thing being judged.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..ir.problem import ScientificProblem, UncertaintyRequirement
from .uncertainty import Uncertainty, UncertaintyKind
from .validation import ValidationCheck, ValidationOutcome, ValidationReport

#: The check a result or report carries when the problem's declared validation requirements are not
#: met. One name, so a reader and a payload diff both find it in one place.
DECLARED_VALIDATION_REQUIREMENTS_CHECK = "declared_validation_requirements"

#: The same, for the problem's uncertainty specification.
DECLARED_UNCERTAINTY_REQUIREMENT_CHECK = "declared_uncertainty_requirement"

#: How close a record's declared confidence level must be to the demanded one. Both sides are
#: DECLARATIONS rather than computed numbers, so exact equality is nearly right; the relative
#: tolerance is here only so a float that has been through JSON compares equal to the one written.
CONFIDENCE_LEVEL_RELATIVE_TOLERANCE = 1.0e-12

_REGISTERED_CHECK_KINDS: set[str] = {
    DECLARED_VALIDATION_REQUIREMENTS_CHECK,
    DECLARED_UNCERTAINTY_REQUIREMENT_CHECK,
}


def register_validation_check_kinds(*names: str) -> None:
    """Declare that this tree emits checks under ``names``.

    Called by the module that EMITS the check, so the registry is a fact about the emitters rather
    than a list somebody maintains. Idempotent: a kind two domains both emit (every domain emits
    ``dimensional_consistency``) is registered twice and means the same thing both times.

    A set of names and not a mapping of name to description, on purpose: two emitters would give
    the same name two different descriptions and neither would be wrong, and the rule that reads
    this registry asks only whether the name is a check kind at all.
    """
    for name in names:
        text = str(name).strip()
        if not text:
            raise ValueError("a validation check kind must have a non-empty name")
        _REGISTERED_CHECK_KINDS.add(text)


def registered_validation_check_kinds() -> frozenset[str]:
    """Every check kind this process's imports have declared."""
    return frozenset(_REGISTERED_CHECK_KINDS)


def unsatisfiable_validation_requirements(problem: ScientificProblem) -> tuple[str, ...]:
    """Declared requirements that name no registered check kind, sorted.

    A typo cannot be satisfied by any result, ever, and saying so is more useful than saying the
    requirement is merely unmet -- which is why the two are reported separately here and together
    below.
    """
    registered = registered_validation_check_kinds()
    return tuple(
        sorted(
            name
            for name in _declared_requirements(problem)
            if name not in registered
        )
    )


def unmet_validation_requirements(
    problem: ScientificProblem, report: ValidationReport | None
) -> tuple[str, ...]:
    """Declared requirements the report does not satisfy, sorted.

    A requirement is satisfied by a check of that EXACT name whose outcome is PASS. A check that is
    present and WARNING, NOT_RUN or FAIL does not satisfy it: the problem demanded the check, and a
    check that did not pass is not the check passing -- a NOT_RUN check of the right name says the
    opposite of what the declaration promises.
    """
    passed = {
        check.name
        for check in getattr(report, "checks", ()) or ()
        if getattr(check, "outcome", None) is ValidationOutcome.PASS
    }
    return tuple(sorted(set(_declared_requirements(problem)) - passed))


def unmet_uncertainty_requirements(
    problem: ScientificProblem, uncertainty: Mapping[str, Uncertainty] | None
) -> tuple[str, ...]:
    """Metrics the problem's uncertainty specification demands and the records do not supply, sorted.

    * ``NONE`` demands nothing.
    * ``REPORTED`` is met by an Uncertainty RECORD for the metric -- including one that says UNKNOWN,
      because the demand was that a result state its position and UNKNOWN is a position.
    * ``QUANTIFIED`` is not met by UNKNOWN. That is the record's own word for *not evaluated*, and a
      demand for a quantified uncertainty is not met by a record saying nobody quantified it.
    * a declared ``confidence_level`` must be the one the metric's record declares, to
      :data:`CONFIDENCE_LEVEL_RELATIVE_TOLERANCE`. An interval at 68 % does not satisfy a demand for
      95 %, and a record that declares no level at all does not satisfy one either.
    * a metric the problem does not carry as a value it will produce is reported too, under the same
      rule the registry states: a demand about a name the problem does not carry can never be met.
    """
    spec = problem.uncertainty
    requirement = UncertaintyRequirement(spec.requirement)
    if requirement is UncertaintyRequirement.NONE:
        return ()
    records = dict(uncertainty or {})
    produced = _produced_names(problem)
    unmet: list[str] = []
    for metric in spec.metrics:
        name = str(metric).strip()
        if produced and name not in produced:
            unmet.append(name)
            continue
        record = records.get(name)
        if record is None:
            unmet.append(name)
            continue
        if (
            requirement is UncertaintyRequirement.QUANTIFIED
            and UncertaintyKind(record.kind) is UncertaintyKind.UNKNOWN
        ):
            unmet.append(name)
            continue
        if spec.confidence_level is not None and not _same_confidence_level(
            spec.confidence_level, record.confidence_level
        ):
            unmet.append(name)
    return tuple(sorted(set(unmet)))


def requirement_checks(
    problem: ScientificProblem | None,
    *,
    validation: ValidationReport | None = None,
    uncertainty: Mapping[str, Uncertainty] | Iterable[Any] = (),
) -> tuple[ValidationCheck, ...]:
    """The NOT_RUN checks that say what this problem's declarations do not get, or nothing.

    Nothing at all when nothing is unmet, so a result or report that meets its declaration keeps its
    bytes and its digest. At most two checks, named by the two module constants above.

    A check and not a new field: a NOT_RUN check already lowers a credibility verdict to
    INSUFFICIENT_EVIDENCE through machinery that exists and is guarded, it survives serialization,
    and it cannot be deleted from a payload without deleting a check -- which is visible in the
    check list and moves the verdict by itself.
    """
    if problem is None:
        return ()
    checks: list[ValidationCheck] = []
    unmet = unmet_validation_requirements(problem, validation)
    if unmet:
        unsatisfiable = set(unsatisfiable_validation_requirements(problem))
        never = sorted(name for name in unmet if name in unsatisfiable)
        detail = (
            f"problem {problem.problem_id!r} declares validation requirement(s) "
            f"{list(unmet)} and this validation report carries no PASSING check of "
            f"those names. The declaration was read as a gate and nothing enforced it"
        )
        if never:
            detail += (
                f". {never} name no check kind this tree emits, so they cannot be satisfied by any "
                f"result; the registered kinds are {sorted(registered_validation_check_kinds())}"
            )
        checks.append(
            ValidationCheck(
                name=DECLARED_VALIDATION_REQUIREMENTS_CHECK,
                outcome=ValidationOutcome.NOT_RUN,
                detail=detail,
            )
        )
    records = uncertainty if isinstance(uncertainty, Mapping) else {}
    missing = unmet_uncertainty_requirements(problem, records)
    if missing:
        spec = problem.uncertainty
        level = (
            "" if spec.confidence_level is None
            else f" at a confidence level of {spec.confidence_level}"
        )
        checks.append(
            ValidationCheck(
                name=DECLARED_UNCERTAINTY_REQUIREMENT_CHECK,
                outcome=ValidationOutcome.NOT_RUN,
                detail=(
                    f"problem {problem.problem_id!r} demands "
                    f"{UncertaintyRequirement(spec.requirement).value.upper()} uncertainty{level} "
                    f"for {list(missing)}, and these values do not carry it"
                ),
            )
        )
    return tuple(checks)


def merged_requirement_checks(
    problems: Iterable[ScientificProblem],
    *,
    validation: ValidationReport | None = None,
    uncertainty: Mapping[str, Uncertainty] | Iterable[Any] = (),
) -> tuple[ValidationCheck, ...]:
    """The same two checks, over a report that answers SEVERAL problems at once.

    A credibility report may cover more than one sub-solve -- the battery report carries the cell's
    checks and the thermal body's -- and each sub-problem makes its own declaration. Two separate
    calls would produce two checks with the same name, which ``CredibilityEvidenceReport`` refuses
    outright and rightly: one name, one finding. So the details are MERGED, one check per kind,
    naming each problem's unmet items in problem order.
    """
    by_name: dict[str, list[str]] = {}
    for problem in problems:
        for check in requirement_checks(
            problem, validation=validation, uncertainty=uncertainty
        ):
            by_name.setdefault(check.name, []).append(check.detail)
    return tuple(
        ValidationCheck(
            name=name,
            outcome=ValidationOutcome.NOT_RUN,
            detail=" | ".join(details),
        )
        for name, details in by_name.items()
    )


def report_with_requirement_checks(
    problem: ScientificProblem | None,
    report: ValidationReport,
    *,
    uncertainty: Mapping[str, Uncertainty] | Iterable[Any] = (),
) -> ValidationReport:
    """``report`` with the requirement checks appended, or ``report`` itself when nothing is unmet.

    Returned unchanged in the met case rather than rebuilt, so a producer that wires this in cannot
    change a compliant result's bytes by wiring it in.
    """
    checks = requirement_checks(problem, validation=report, uncertainty=uncertainty)
    if not checks:
        return report
    return ValidationReport(checks=(*report.checks, *checks), notes=report.notes)


def _declared_requirements(problem: ScientificProblem) -> tuple[str, ...]:
    return tuple(
        sorted(
            text
            for text in (str(name).strip() for name in problem.validation_requirements)
            if text
        )
    )


def _produced_names(problem: ScientificProblem) -> frozenset[str]:
    """The names this problem says a result for it will carry: its variables and its objectives.

    Empty when the problem declares neither, and the caller then does not use it: a problem that
    names nothing it produces makes no claim this rule can check, and inventing one would refuse a
    specification for being written against a problem that is merely terse.
    """
    names = {str(variable.name).strip() for variable in problem.variables}
    for objective in problem.objectives:
        # Both, because an objective declares a name AND the metric it is an objective over, and a
        # result's values are keyed by the metric while a specification may reasonably name either.
        names.add(str(objective.name).strip())
        names.add(str(objective.metric).strip())
    return frozenset(name for name in names if name)


def _same_confidence_level(demanded: float, declared: float | None) -> bool:
    if declared is None:
        return False
    a, b = float(demanded), float(declared)
    return a == b or abs(a - b) <= CONFIDENCE_LEVEL_RELATIVE_TOLERANCE * max(abs(a), abs(b))


__all__ = [
    "CONFIDENCE_LEVEL_RELATIVE_TOLERANCE",
    "DECLARED_UNCERTAINTY_REQUIREMENT_CHECK",
    "DECLARED_VALIDATION_REQUIREMENTS_CHECK",
    "merged_requirement_checks",
    "register_validation_check_kinds",
    "registered_validation_check_kinds",
    "report_with_requirement_checks",
    "requirement_checks",
    "unmet_uncertainty_requirements",
    "unmet_validation_requirements",
    "unsatisfiable_validation_requirements",
]
