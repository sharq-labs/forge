"""Phase 8 -- scientific challenge mode: try declared routes that could falsify the claim.

The default path looks for evidence that bears on a claim. Challenge mode
looks for evidence *against* it, using only what is declared and executable:

``ALTERNATIVE_MODEL``        every other registered capability that produces the
                             QOI, each assessed alone; an admissible CONTRADICTED
                             from any of them weakens the claim.
``INDEPENDENT_SOLVER``       a declared independent route not active in the run;
                             attempted only when the claim can request it.
``PARAMETER_BOUNDARY``       the claim's *own* declared input distributions,
                             one input at a time at the edge of its support
                             (uniform bounds; normal +/-3 sigma); a usable run
                             there that violates the comparison weakens the claim.
``EXTERNAL_ORACLE``          admissible external evidence (trusted benchmark,
                             pinned measurement or literature): an inconsistent
                             comparison, or an external value that itself
                             violates the claim, weakens it.
``UNCERTAINTY_GUARD_BAND``   a claim that demanded no channel, re-assessed with
                             every channel its capability can quantify; a band
                             that no longer decides the claim weakens it.
``VALIDITY_BOUNDARY_STRESS`` the robustness envelope within the declared input
                             ranges: support ending (failure or domain end)
                             inside them weakens the claim.

A challenge is not evidence. What it records are the executions and evidence
records it produced, and ``weakened`` is set only by an *admissible* record:
an unusable run, an unknown uncertainty or an undeclared route make a
challenge INCONCLUSIVE or NOT_ATTEMPTED, never a weakening.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from ...scientific.units.quantity import Quantity
from ...sria.uncertainty import UncertaintyChannel
from .._records import tagged_digest
from ..capabilities import CapabilityRegistry
from ..contract import UncertaintyDemand
from ..parameter_uq import DistributionKind
from .sensitivity import BoundaryKind, SensitivityError, robustness_envelope
from ..uq_studies import run_inputs_for, run_variant

_TAG = "crafty.claims.challenge/1"


class ChallengeKind(str, Enum):
    ALTERNATIVE_MODEL = "alternative_model"
    INDEPENDENT_SOLVER = "independent_solver"
    PARAMETER_BOUNDARY = "parameter_boundary"
    EXTERNAL_ORACLE = "external_oracle"
    UNCERTAINTY_GUARD_BAND = "uncertainty_guard_band"
    VALIDITY_BOUNDARY_STRESS = "validity_boundary_stress"


class ChallengeResult(str, Enum):
    SURVIVED = "survived"
    WEAKENED = "weakened"
    INCONCLUSIVE = "inconclusive"
    NOT_ATTEMPTED = "not_attempted"


@dataclass(frozen=True)
class Challenge:
    kind: ChallengeKind
    target: str
    attempted: bool
    result: ChallengeResult
    weakened: bool
    evidence_refs: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value, "target": self.target, "attempted": self.attempted, "result": self.result.value,
            "weakened": self.weakened, "evidence_refs": list(self.evidence_refs), "detail": self.detail,
        }


@dataclass(frozen=True)
class ChallengeReport:
    claim_identity: str
    nominal_verdict: str
    challenges: tuple[Challenge, ...]

    @property
    def status(self) -> str:
        """A lossy one-word headline; :meth:`outcome_summary` is the unambiguous reading.

        ``survived_attempted_challenges`` means *at least one* attempted challenge
        survived and none weakened -- not that every attempted challenge
        survived: others may be INCONCLUSIVE or NOT_ATTEMPTED. ``not_challenged``
        means none survived or weakened, although some may have been attempted
        and stayed INCONCLUSIVE. The vocabulary is serialized and kept as is.
        """
        if any(c.weakened for c in self.challenges):
            return "weakened"
        if any(c.result is ChallengeResult.SURVIVED for c in self.challenges):
            return "survived_attempted_challenges"
        return "not_challenged"

    def outcome_counts(self) -> dict[str, int]:
        """How many challenges ended in each result, plus how many were attempted."""
        counts = {result.value: 0 for result in ChallengeResult}
        for challenge in self.challenges:
            counts[challenge.result.value] += 1
        counts["attempted"] = sum(1 for c in self.challenges if c.attempted)
        return counts

    @property
    def unresolved(self) -> tuple[Challenge, ...]:
        """Challenges that neither survived nor weakened: INCONCLUSIVE or NOT_ATTEMPTED.

        A survived challenge says nothing about these; the claim was not shown
        to hold against them, and not shown to fail.
        """
        return tuple(c for c in self.challenges
                     if c.result in (ChallengeResult.INCONCLUSIVE, ChallengeResult.NOT_ATTEMPTED))

    def outcome_summary(self) -> dict[str, Any]:
        """Counts per result and whether unresolved challenges remain.

        Not part of :meth:`to_dict`, so the record and its digest are unchanged;
        everything here is derived from the per-challenge results it serializes.
        """
        counts = self.outcome_counts()
        unresolved = self.unresolved
        return {
            "status": self.status,
            "attempted": counts["attempted"],
            "survived": counts[ChallengeResult.SURVIVED.value],
            "weakened": counts[ChallengeResult.WEAKENED.value],
            "inconclusive": counts[ChallengeResult.INCONCLUSIVE.value],
            "not_attempted": counts[ChallengeResult.NOT_ATTEMPTED.value],
            "unresolved_remain": bool(unresolved),
            "unresolved": [f"{c.kind.value}:{c.target}:{c.result.value}" for c in unresolved],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_identity": self.claim_identity, "nominal_verdict": self.nominal_verdict, "status": self.status,
            "challenges": [c.to_dict() for c in self.challenges],
            "notice": "a challenge is not evidence; only the executions and records it lists are, and it never changes the verdict",
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


def _alternative_models(assessment, registry) -> list[Challenge]:
    from ..assessment import assess_claim

    out = []
    chosen = assessment.plan.capability_id if assessment.plan is not None else None
    for declaration in registry.producing(assessment.claim.qoi.name):
        if declaration.capability_id == chosen:
            continue
        alone = CapabilityRegistry((declaration,))
        other = assess_claim(assessment.claim, alone)
        record = other.to_dict()
        verdict = record["verdict"]
        refs = tuple(filter(None, [record["evidence"] and record["evidence"]["record_hash"], record["plan"] and record["plan"]["content"]["run_id"]]))
        if verdict == "contradicted":
            result, weakened = ChallengeResult.WEAKENED, True
            detail = f"{declaration.capability_id} contradicts the claim with admissible evidence"
        elif verdict == "supported":
            result, weakened = ChallengeResult.SURVIVED, False
            detail = f"{declaration.capability_id} independently supports the claim"
        else:
            result, weakened = ChallengeResult.INCONCLUSIVE, False
            detail = f"{declaration.capability_id} cannot decide the claim ({record['compilation']['status']}): " + "; ".join(r["reason"] for r in record["reasons"][:2])
        out.append(Challenge(ChallengeKind.ALTERNATIVE_MODEL, declaration.capability_id, True, result, weakened, refs, detail))
    if not out:
        out.append(Challenge(ChallengeKind.ALTERNATIVE_MODEL, "registry", False, ChallengeResult.NOT_ATTEMPTED, False, (),
                             f"no other registered capability produces {assessment.claim.qoi.name}"))
    return out


def _independent_solver(assessment, registry) -> list[Challenge]:
    if assessment.plan is None:
        return []
    declaration = registry.get(assessment.plan.capability_id)
    out = []
    for route in assessment.plan.content["routes"]:
        if route["route_class"] != "independent":
            continue
        decl = declaration.route(route["route_id"])
        if route["active"]:
            continue
        out.append(Challenge(ChallengeKind.INDEPENDENT_SOLVER, route["route_id"], False, ChallengeResult.NOT_ATTEMPTED, False, (),
                             f"requires the claim to state {list(decl.activation) if decl else []} (an external program); "
                             f"not requested, so not run: {route['reason']}"))
    return out


def _parameter_boundary(assessment, registry) -> list[Challenge]:
    spec = assessment.claim.input_uncertainty
    if spec is None or assessment.plan is None or not assessment.execution or not assessment.execution.bound:
        return [Challenge(ChallengeKind.PARAMETER_BOUNDARY, "input_uncertainty", False, ChallengeResult.NOT_ATTEMPTED, False, (),
                          "the claim declares no input distributions, so it names no range to challenge it over")]
    from .sensitivity import _holds

    declaration = registry.get(assessment.plan.capability_id)
    base = run_inputs_for(assessment.claim, declaration)
    out = []
    for dist in spec.distributions:
        if dist.kind is DistributionKind.UNIFORM:
            edges = (dist.first.magnitude, dist.second.magnitude)
        else:
            sigma = dist.second.magnitude_as_spread_in(dist.first.units)
            edges = (dist.first.magnitude - 3.0 * sigma, dist.first.magnitude + 3.0 * sigma)
        runs = [run_variant(assessment.plan, registry, {**base, dist.path: Quantity(x, dist.first.units)},
                            f"{assessment.plan.run_id}~challenge~{dist.path}~{i}") for i, x in enumerate(edges)]
        refs = tuple(r.run_id for r in runs)
        failing = [r for r in runs if r.usable and not _holds(assessment, r.value)]
        if failing:
            out.append(Challenge(ChallengeKind.PARAMETER_BOUNDARY, dist.path, True, ChallengeResult.WEAKENED, True, refs,
                                 f"at the edge of the declared {dist.kind.value} input range the claim's comparison fails "
                                 f"(value {failing[0].value!r})"))
        elif all(r.usable for r in runs):
            out.append(Challenge(ChallengeKind.PARAMETER_BOUNDARY, dist.path, True, ChallengeResult.SURVIVED, False, refs,
                                 f"the claim holds at both edges {edges} of the declared range"))
        else:
            bad = next(r for r in runs if not r.usable)
            out.append(Challenge(ChallengeKind.PARAMETER_BOUNDARY, dist.path, True, ChallengeResult.INCONCLUSIVE, False, refs,
                                 f"an edge run is not usable ({bad.problem}); the claim is not established there, and not refuted"))
    return out


def _external_oracle(assessment) -> list[Challenge]:
    external = assessment.to_dict().get("external_evidence_assessments") or []
    out = []
    constraint = assessment.claim.constraint(assessment.compiled.target) if assessment.compiled.target is not None else None
    for i, item in enumerate(external):
        target = f"{item['source_class']}:{item['record_digest'][:16]}"
        if item["standing"] != "admissible":
            out.append(Challenge(ChallengeKind.EXTERNAL_ORACLE, target, False, ChallengeResult.NOT_ATTEMPTED, False, (),
                                 f"standing {item['standing']}: only admissible external evidence can challenge a claim"))
            continue
        refs = (item["evidence_record_hash"],)
        comparison = item.get("comparison") or {}
        value = item["record"].get("expected") or item["record"].get("value")
        violates = False
        if constraint is not None and value is not None:
            violates = not constraint.check(Quantity.from_dict(value)).satisfied
        if comparison.get("outcome") == "inconsistent" or violates:
            why = "inconsistent with the simulated value" if comparison.get("outcome") == "inconsistent" else "its own value violates the claim"
            out.append(Challenge(ChallengeKind.EXTERNAL_ORACLE, target, True, ChallengeResult.WEAKENED, True, refs, f"admissible external evidence is {why}"))
        elif comparison.get("outcome") == "consistent":
            out.append(Challenge(ChallengeKind.EXTERNAL_ORACLE, target, True, ChallengeResult.SURVIVED, False, refs,
                                 "admissible external evidence is consistent with the simulated value and satisfies the claim"))
        else:
            out.append(Challenge(ChallengeKind.EXTERNAL_ORACLE, target, True, ChallengeResult.INCONCLUSIVE, False, refs,
                                 f"comparison {comparison.get('outcome', 'absent')}: {comparison.get('detail', '')}"))
    return out


def _guard_band(assessment, registry) -> list[Challenge]:
    from ..assessment import assess_claim
    from ..uq_studies import study_spec

    claim = assessment.claim
    if claim.uncertainty.demands_quantification or assessment.plan is None:
        return []
    declaration = registry.get(assessment.plan.capability_id)
    available = [c for c in UncertaintyChannel if study_spec(declaration, claim, c)[0] is not None]
    if not available:
        return [Challenge(ChallengeKind.UNCERTAINTY_GUARD_BAND, "channels", False, ChallengeResult.NOT_ATTEMPTED, False, (),
                          "the capability can quantify no uncertainty channel for this claim")]
    banded = replace(claim, uncertainty=UncertaintyDemand(frozenset(available), None, False))
    record = assess_claim(banded, registry).to_dict()
    refs = tuple(r["run_id"] for s in record.get("uncertainty_studies", []) for r in s["runs"])
    outcome = (record.get("comparison") or {}).get("outcome")
    if assessment.verdict.value == "supported" and record["verdict"] != "supported":
        return [Challenge(ChallengeKind.UNCERTAINTY_GUARD_BAND, ",".join(c.value for c in available), True, ChallengeResult.WEAKENED, True, refs,
                          f"with the quantifiable channels applied the comparison is {outcome}: the point comparison overstated the claim")]
    # Survival means a decided verdict held under the band. An undecided nominal verdict that stays
    # undecided was not tested by the band at all: that is INCONCLUSIVE, never SURVIVED.
    decided = assessment.verdict.value in ("supported", "contradicted")
    result = ChallengeResult.SURVIVED if decided and record["verdict"] == assessment.verdict.value else ChallengeResult.INCONCLUSIVE
    return [Challenge(ChallengeKind.UNCERTAINTY_GUARD_BAND, ",".join(c.value for c in available), True, result, False, refs,
                      f"with the quantifiable channels applied the claim is {record['verdict']} (comparison {outcome})")]


#: Relative slack for comparing an envelope input with a range edge: the probe at the
#: edge is ``x0 * (1 +/- limit)``, which reproduces the edge only to rounding.
_EDGE_RTOL = 1e-12


def _side_against_range(direction: str, side: Mapping[str, Any], x0: float, lo: float, hi: float) -> tuple[str, str] | None:
    """Judge one envelope side against the declared range ``[lo, hi]`` (stated unit).

    ``("inside", why)`` when support ends (failure or domain end) within the range,
    an edge included; ``("unreached", why)`` when the last holding probe stops short
    of the edge -- a capped search or a boundary bracket straddling the edge leaves
    the rest of the range unexamined, which is not "holds across"; ``None`` when the
    claim held at the edge. The envelope's ``decrease`` side scales the stated value
    down, which moves toward ``hi`` when the stated value is negative.
    """
    toward_lower = (direction == "decrease") == (x0 > 0)
    edge = lo if toward_lower else hi

    def at_edge(value: float) -> bool:
        return math.isclose(value, edge, rel_tol=_EDGE_RTOL, abs_tol=0.0)

    beyond = side["first_not_holding"]
    if side["kind"] != BoundaryKind.SEARCH_LIMIT.value and beyond is not None:
        if (beyond >= edge if toward_lower else beyond <= edge) or at_edge(beyond):
            return "inside", f"{direction}: {side['kind']} at {beyond:g}"
    last = side["last_holding"]
    if (last <= edge if toward_lower else last >= edge) or at_edge(last):
        return None
    return "unreached", f"{direction}: shown to hold only to {last:g}, short of {edge:g}"


def _validity_stress(assessment, registry) -> list[Challenge]:
    spec = assessment.claim.input_uncertainty
    if spec is None or assessment.verdict.value != "supported":
        return [Challenge(ChallengeKind.VALIDITY_BOUNDARY_STRESS, "inputs", False, ChallengeResult.NOT_ATTEMPTED, False, (),
                          "stress needs a supported claim and declared input ranges to stress within")]
    out = []
    stated = run_inputs_for(assessment.claim, registry.get(assessment.plan.capability_id))
    for dist in spec.distributions:
        if dist.kind is DistributionKind.UNIFORM:
            lo_q, hi_q = dist.first, dist.second
        else:
            sigma = dist.second.magnitude_as_spread_in(dist.first.units)
            lo_q = Quantity(dist.first.magnitude - 3.0 * sigma, dist.first.units)
            hi_q = Quantity(dist.first.magnitude + 3.0 * sigma, dist.first.units)
        # The envelope searches around the stated value, in the stated unit; the
        # range edges are compared there, never as raw magnitudes of another unit.
        x0_q = stated.get(dist.path)
        if not isinstance(x0_q, Quantity):
            out.append(Challenge(ChallengeKind.VALIDITY_BOUNDARY_STRESS, dist.path, False, ChallengeResult.NOT_ATTEMPTED, False, (),
                                 "the claim states no quantity at this path to stress around"))
            continue
        x0 = x0_q.magnitude
        lo, hi = lo_q.to(x0_q.units).magnitude, hi_q.to(x0_q.units).magnitude
        limit = min(0.95, max(abs(hi - x0), abs(x0 - lo)) / abs(x0)) if x0 else 0.0
        if limit <= 0.0:
            out.append(Challenge(ChallengeKind.VALIDITY_BOUNDARY_STRESS, dist.path, False, ChallengeResult.NOT_ATTEMPTED, False, (),
                                 "a zero nominal has no relative range to stress"))
            continue
        try:
            envelope = robustness_envelope(assessment, registry, search_limit=limit, parameters=(dist.path,))
        except SensitivityError as exc:
            out.append(Challenge(ChallengeKind.VALIDITY_BOUNDARY_STRESS, dist.path, False, ChallengeResult.NOT_ATTEMPTED, False, (),
                                 f"the declared range was not stressed: {exc}"))
            continue
        entry = envelope.parameters[dist.path]
        refs = tuple(e["run_id"] for d in ("decrease", "increase") for e in entry[d]["evaluations"])
        inside, unreached = [], []
        for direction in ("decrease", "increase"):
            found = _side_against_range(direction, entry[direction], x0, lo, hi)
            if found is not None:
                (inside if found[0] == "inside" else unreached).append(found[1])
        if inside:
            out.append(Challenge(ChallengeKind.VALIDITY_BOUNDARY_STRESS, dist.path, True, ChallengeResult.WEAKENED, True, refs,
                                 f"support ends inside the declared range [{lo:g}, {hi:g}]: {inside}"))
        elif unreached:
            out.append(Challenge(ChallengeKind.VALIDITY_BOUNDARY_STRESS, dist.path, True, ChallengeResult.INCONCLUSIVE, False, refs,
                                 f"the declared range [{lo:g}, {hi:g}] was not stressed to its edges: {unreached}"))
        else:
            out.append(Challenge(ChallengeKind.VALIDITY_BOUNDARY_STRESS, dist.path, True, ChallengeResult.SURVIVED, False, refs,
                                 f"support holds across the declared range [{lo:g}, {hi:g}]"))
    return out


def challenge_claim(assessment: Any, registry: CapabilityRegistry) -> ChallengeReport:
    """Run every applicable challenge against an assessed claim. Never changes the assessment's verdict."""
    if assessment.claim is None:
        return ChallengeReport("", assessment.verdict.value, ())
    challenges = (
        _alternative_models(assessment, registry)
        + _independent_solver(assessment, registry)
        + _parameter_boundary(assessment, registry)
        + _external_oracle(assessment)
        + _guard_band(assessment, registry)
        + _validity_stress(assessment, registry)
    )
    return ChallengeReport(assessment.claim.identity_digest, assessment.verdict.value, tuple(challenges))


__all__ = ["Challenge", "ChallengeKind", "ChallengeReport", "ChallengeResult", "challenge_claim"]
