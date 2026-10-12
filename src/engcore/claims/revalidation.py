"""What a stored assessment's evidence still proves offline (Trust Repair Pass 1, Review 3 R3-01).

:func:`~engcore.claims.assessment.verify_assessment` re-derives a record from
the claim, plan and credibility report the record carries. That proves the
record is **consistent with itself**. It does not prove the run happened, and
it cannot: the bundle digest is an unkeyed hash, so whoever edits a record can
recompute it. Review 3 rewrote a NAFEMS T3 record consistently to 305 K, a
value the benchmark puts about 95 tolerances away, and it verified as
SUPPORTED with BENCHMARK_VALIDATED.

This module answers the stronger question for each level the verdict rests on:
*does the stored evidence still earn that level, without re-running the
solver?*

- **Oracle-issued levels** (BENCHMARK_VALIDATED, EXPERIMENTALLY_VALIDATED).
  The pinned evidence is reached only through the plan capability's own
  declared benchmark and experimental routes, never through anything the
  record names. Its comparison is run again on the record's stored values at
  the operating point the record's own provenance states. The stored check's
  outcome, residual and compared metrics must be what that comparison
  produces now. If they differ, the record is **refuted**: a level its own
  evidence no longer earns is a forged or corrupted record. If they agree,
  the level is SCIENTIFICALLY_REVALIDATED.
- **Every other level** (DIMENSIONALLY_VALID, NUMERICALLY_CONVERGED,
  ANALYTICALLY_VERIFIED, CROSS_SOLVER_VALIDATED). These are earned inside the
  run: a refinement study, a closed form evaluated on the run's own inputs, an
  independent solve. A stored record of one is only as good as the run, so it
  stands REPLAY_REQUIRED and is re-earned only by
  :func:`~engcore.claims.replay.bundle.replay_bundle`.
- **A demanded uncertainty channel** quantified from the run's own numbers
  (a study's runs, a solver's own estimate) is REPLAY_REQUIRED for the same
  reason. A narrower forged interval would turn a band comparison
  "satisfied".
- **The verdict itself.** A re-earned oracle level pins the stored value only
  to the oracle's band (expected ± tolerance), and the claim is compared on
  that value. The verdict is fixed by pinned evidence only when two things
  hold: it rests on admissible evidence, and the claim's QOI is compared by a
  re-earned oracle with the same comparison outcome for every value in that
  band. Otherwise a value moved inside the band, with its check re-issued
  consistently, could flip it, so it stands REPLAY_REQUIRED. An insufficient
  verdict is decided by the run's own diagnostics, so it is REPLAY_REQUIRED
  too.

Nothing here grants a level, upgrades a verdict, or claims that the original
computation ran.

- SCIENTIFICALLY_REVALIDATED means "the stored values re-earn the required
  levels and the claim's comparison against repository-pinned evidence".
- REPLAY_REQUIRED means "only a re-execution can say more".

Neither is authentication, and neither is publishable support. A consistent
record can carry a genuine report from ANOTHER run, for example the default
grid in place of the planned numerics. Admissibility rests on that run's own
diagnostics. Only a replay re-earns both (Trust Repair Pass 1, review round 2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from .capabilities import CapabilityRegistry, RouteKind
from .planning import ExperimentPlan, StepAvailability, StepKind

#: The levels whose issuer is an external, repository-pinned oracle comparison
#: that can be re-run from the stored values alone.
ORACLE_LEVELS = frozenset({ValidationLevel.BENCHMARK_VALIDATED, ValidationLevel.EXPERIMENTALLY_VALIDATED})


class RevalidationStanding(str, Enum):
    """What offline verification can say about the evidence a verdict rests on."""

    #: Every level the verdict rests on was re-earned from the stored values
    #: against repository-pinned evidence, no demanded uncertainty channel rests
    #: on run-produced numbers, and the claim's comparison has one outcome over
    #: every value that evidence admits. Two things are NOT re-earned:
    #: - that the stored report is the planned run (numerics, grid, identity);
    #: - the run's own admissibility diagnostics.
    #: So this is not publishable support. Only a replay that re-executes is.
    SCIENTIFICALLY_REVALIDATED = "scientifically_revalidated"
    #: Something the verdict rests on is earned only inside a run. The record
    #: is consistent, and only a replay can re-earn it.
    REPLAY_REQUIRED = "replay_required"


@dataclass(frozen=True)
class LevelStanding:
    level: ValidationLevel
    check_name: str | None
    standing: RevalidationStanding
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "check_name": self.check_name,
            "standing": self.standing.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class EvidenceRevalidation:
    """The offline standing of a stored assessment's evidence. A non-empty ``refuted`` means the record is forged."""

    levels: tuple[LevelStanding, ...]
    channels: tuple[tuple[str, str], ...]
    refuted: tuple[str, ...]
    #: Why the verdict ITSELF is not fixed by pinned evidence, independent of the levels. Empty only
    #: when the verdict rests on admissible evidence and the claim's comparison has the same outcome
    #: for every value the pinned evidence admits.
    verdict: tuple[str, ...] = ()

    @property
    def standing(self) -> RevalidationStanding:
        if self.channels or self.verdict or any(
            item.standing is RevalidationStanding.REPLAY_REQUIRED for item in self.levels
        ):
            return RevalidationStanding.REPLAY_REQUIRED
        return RevalidationStanding.SCIENTIFICALLY_REVALIDATED

    @property
    def reasons(self) -> tuple[str, ...]:
        """Why the standing is not SCIENTIFICALLY_REVALIDATED."""
        out = [
            f"{item.level.value}: {item.detail}"
            for item in self.levels
            if item.standing is RevalidationStanding.REPLAY_REQUIRED
        ]
        out += [f"uncertainty channel {channel}: {detail}" for channel, detail in self.channels]
        out += [f"verdict: {detail}" for detail in self.verdict]
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "standing": self.standing.value,
            "levels": [item.to_dict() for item in self.levels],
            "channels": [{"channel": c, "detail": d} for c, d in self.channels],
            "verdict": list(self.verdict),
            "refuted": list(self.refuted),
        }


def _evidence_line(check: ValidationCheck, prefix: str) -> str | None:
    lines = [line[len(prefix):] for line in check.evidence if isinstance(line, str) and line.startswith(prefix)]
    return lines[0] if len(lines) == 1 else None


def _oracle_identity(check: ValidationCheck) -> tuple[str, str, str] | None:
    """``(oracle_id, version, digest)`` the check names, or ``None`` when it is not an oracle comparison."""
    named = _evidence_line(check, "oracle:")
    digest = _evidence_line(check, "sha256:")
    if named is None or digest is None or "@" not in named:
        return None
    oracle_id, _, version = named.rpartition("@")
    return oracle_id, version, digest


def _routed_evidence(plan: ExperimentPlan, registry: CapabilityRegistry, identity: tuple[str, str, str]) -> Any | None:
    """The pinned evidence set the plan's own capability routes to, matching ``identity`` exactly."""
    oracle_id, version, digest = identity
    declaration = registry.get(plan.capability_id)
    for route in declaration.routes:
        if route.kind not in (RouteKind.BENCHMARK, RouteKind.EXPERIMENTAL) or route.oracle_provider is None:
            continue
        evidence = route.oracle_provider()
        found = evidence.identity
        if (found.oracle_id, found.version, found.evidence_digest) == (oracle_id, version, digest):
            return evidence if evidence.is_trusted else None
    return None


def _same(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)


#: The exact lines a genuine level-awarding oracle comparison writes (``OracleEvidenceSet.compare``).
_AUTHORITY_PINNED = "oracle-authority:repository-pinned"
_BINDING_NAMED = "oracle-binding:the prediction names the record it came from"


def _recompare(check: ValidationCheck, evidence: Any, report: Any) -> tuple[str | None, tuple[Any, ...]]:
    """``(why the stored check is not what its pinned evidence gives at the stored values, compared observations)``."""
    values = dict(report.values)
    inputs = dict(getattr(report.provenance, "inputs", {}) or {})
    predicted = {o.metric: values[o.metric] for o in evidence.observations if o.metric in values}
    declared = {key for o in evidence.observations for key in o.conditions}
    stated = {key: inputs[key] for key in declared if key in inputs}
    again = evidence.compare(predicted, name=check.name, conditions=stated)
    if again.outcome is not check.outcome:
        return (
            f"check {check.name!r} is stored as {check.outcome.value}, and the pinned "
            f"{evidence.identity.oracle_id}@{evidence.identity.version} comparison of the stored values gives "
            f"{again.outcome.value} ({again.detail})"
        ), ()
    if not _same(check.residual, again.residual) or not _same(check.tolerance, again.tolerance):
        return (
            f"check {check.name!r} stores residual {check.residual} / tolerance {check.tolerance}; the pinned "
            f"comparison of the stored values gives {again.residual} / {again.tolerance}"
        ), ()
    if _evidence_line(check, "metrics:") != _evidence_line(again, "metrics:"):
        return (
            f"check {check.name!r} names compared metrics {_evidence_line(check, 'metrics:')!r}; the pinned "
            f"comparison of the stored values compares {_evidence_line(again, 'metrics:')!r}"
        ), ()
    compared_names = set((_evidence_line(again, "metrics:") or "").split(",")) - {""}
    compared = tuple(o for o in evidence.observations if o.metric in compared_names)
    if check.establishes is not None:
        # The recomparison runs without the producing record, so it can never award a level itself. A
        # stored level is therefore checked against everything the genuine award required: the pinned
        # level, a repository-pinned authority, a prediction bound to its record, and observations that
        # declare where they were taken (Review: F2).
        if check.establishes is not evidence.identity.establishes:
            return f"check {check.name!r} claims {check.establishes.value}; its pinned evidence awards {evidence.identity.establishes.value}", ()
        if _AUTHORITY_PINNED not in check.evidence or _BINDING_NAMED not in check.evidence:
            return (
                f"check {check.name!r} claims {check.establishes.value} without the pinned-authority and "
                "bound-prediction lines that every awarded comparison carries"
            ), ()
        if not compared or any(not o.conditions for o in compared):
            return (
                f"check {check.name!r} claims {check.establishes.value} from observations that declare no "
                "operating point, which never awards a level"
            ), ()
    return None, compared


def _boundaries(claim: Any, bound: Any, units: str) -> list[float]:
    """Where the claim's decision rule changes its outcome, in ``units``."""
    from .contract import ClaimKind

    centre = bound.to(units).magnitude
    if claim.kind is ClaimKind.TOLERANCE_BAND:
        spread = claim.tolerance.magnitude_as_spread_in(units)
        return [centre - spread, centre + spread]
    return [centre]


def _verdict_problems(claim: Any, bound: Any, report: Any, pinned: Mapping[str, tuple[Any, ...]], admissible: bool) -> list[str]:
    """Why the verdict is not fixed by the pinned evidence alone (Review: F1), or nothing.

    A re-earned oracle level pins the stored value only to the oracle's band, which is
    expected +/- tolerance. The claim's comparison is decided on that stored value. So a
    forger who moves the value inside the band, and re-issues a consistent check, can flip
    any claim whose decision boundary falls inside it. The verdict is fixed by pinned
    evidence only when the comparison has the same outcome for EVERY value the pinned
    evidence admits.
    """
    from ..scientific.units.quantity import Quantity

    if not admissible:
        return ["the verdict does not rest on admissible evidence; an insufficient verdict is decided by the run's "
                "own diagnostics, which only a replay re-earns"]
    qoi = claim.qoi.name
    observations = pinned.get(qoi, ())
    if not observations:
        return [f"the claim's quantity {qoi!r} is not compared by any re-earned pinned evidence, so the compared "
                "value is the run's own number"]
    if bound is None:
        return ["the claim has no resolved bound to compare against"]
    units = str(claim.qoi.units)
    problems: list[str] = []
    try:
        constraint = claim.constraint(bound)
        boundaries = _boundaries(claim, bound, units)
        for observation in observations:
            half = observation.absolute_tolerance.magnitude_as_spread_in(str(observation.expected.units))
            lo = Quantity(observation.expected.magnitude - half, observation.expected.units).to(units).magnitude
            hi = Quantity(observation.expected.magnitude + half, observation.expected.units).to(units).magnitude
            lo, hi = min(lo, hi), max(lo, hi)
            inside = [b for b in boundaries if lo <= b <= hi]
            ends = {constraint.check(Quantity(x, units)).satisfied for x in (lo, hi)}
            if inside or len(ends) != 1:
                problems.append(
                    f"the pinned evidence admits {qoi} anywhere in [{lo:.12g}, {hi:.12g}] {units}, and the claim's "
                    f"decision boundary {[round(b, 12) for b in inside] or 'between the ends'} lies within it, so the "
                    "verdict depends on the run's own number inside that band"
                )
    except Exception as exc:  # any failure to establish invariance is a failure to establish it
        problems.append(f"the comparison's invariance over the pinned band could not be established: {type(exc).__name__}: {exc}")
    return problems


def revalidate_evidence(
    plan: ExperimentPlan,
    claim: Any,
    report: Any,
    registry: CapabilityRegistry,
    *,
    evidence: Any = None,
    bound: Any = None,
    admissible: bool = False,
) -> EvidenceRevalidation:
    """The offline standing of ``report``'s evidence for ``claim`` under ``plan``.

    Every oracle comparison the report carries is re-run against its pinned
    evidence, so a stale or edited one is refuted wherever it sits. Then each
    level the claim requires and the report attains is given its standing,
    together with each demanded uncertainty channel the evidence quantifies, and
    the verdict itself: it is fixed by pinned evidence only when it rests on
    admissible evidence and the comparison is invariant over the pinned band.
    """
    refuted: list[str] = []
    reearned: dict[str, bool] = {}
    unroutable: set[str] = set()
    pinned_by_metric: dict[str, tuple[Any, ...]] = {}
    for check in report.validation:
        identity = _oracle_identity(check)
        if identity is None:
            continue
        pinned = _routed_evidence(plan, registry, identity)
        if pinned is None:
            # Not reachable through this capability's own routes: nothing offline can re-run it.
            unroutable.add(check.name)
            continue
        problem, compared = _recompare(check, pinned, report)
        if problem is not None:
            refuted.append(problem)
            continue
        earned = check.outcome is ValidationOutcome.PASS and check.establishes in ORACLE_LEVELS
        reearned[check.name] = earned
        if earned:
            for observation in compared:
                pinned_by_metric[observation.metric] = (*pinned_by_metric.get(observation.metric, ()), observation)

    planned = {
        ValidationLevel(step.detail["level"]): str(step.detail["check_name"])
        for step in plan.steps_of(StepKind.VALIDATION_CHECK)
        if step.availability is StepAvailability.PLANNED and step.detail.get("check_name")
    }
    attained = set(report.attained_levels)
    by_name = {check.name: check for check in report.validation}
    levels: list[LevelStanding] = []
    for level in claim.evidence.required_levels:
        if level not in attained:
            continue  # not attained: the verdict cannot rest on it
        name = planned.get(level)
        if level in ORACLE_LEVELS and name in unroutable and getattr(by_name.get(name), "establishes", None) is level:
            # The plan's own check for this level names evidence its capability does not route to: a
            # genuine run writes that route's pin, so this is another oracle's record put in its place (F4).
            refuted.append(
                f"planned check {name!r} awards {level.value} from oracle evidence the plan's capability does not route to"
            )
            continue
        if name is not None and reearned.get(name):
            levels.append(LevelStanding(
                level, name, RevalidationStanding.SCIENTIFICALLY_REVALIDATED,
                "re-earned from the stored values against the repository-pinned evidence the plan's capability routes to",
            ))
        elif level in ORACLE_LEVELS:
            levels.append(LevelStanding(
                level, name, RevalidationStanding.REPLAY_REQUIRED,
                "no planned comparison against pinned evidence the plan's capability routes to re-earns it offline",
            ))
        else:
            levels.append(LevelStanding(
                level, name, RevalidationStanding.REPLAY_REQUIRED,
                "earned inside the run (refinement, closed form or independent solve); only a replay re-earns it",
            ))

    channels: list[tuple[str, str]] = []
    if evidence is not None:
        for channel in claim.uncertainty.ordered_channels():
            if evidence.uncertainty.channel(channel).is_quantified:
                channels.append((
                    channel.value,
                    "quantified from the run's own numbers; a stored interval is re-derived for consistency only, "
                    "and only a replay re-earns it",
                ))
    verdict = _verdict_problems(claim, bound, report, pinned_by_metric, admissible)
    return EvidenceRevalidation(tuple(levels), tuple(channels), tuple(refuted), tuple(verdict))


__all__ = [
    "EvidenceRevalidation",
    "LevelStanding",
    "ORACLE_LEVELS",
    "RevalidationStanding",
    "revalidate_evidence",
]
