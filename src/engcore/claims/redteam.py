"""Scientific Red Team: try to break a claim, and say exactly how far the attack got.

::

    Claim -> AttackSpace -> AttackPlan -> CounterexampleCandidate -> Replay -> IndependentCheck -> TrustEnvelope

* An :class:`AttackDimension` has an admissible range (or admissible choices), a SOURCE for that range and a
  plausibility classification (PLAUSIBLE / EDGE / IMPLAUSIBLE).  Route dimensions (model form, solver/provider,
  discretization, numerical setting) choose among the subject's declared :class:`Route` records.
* The :class:`AttackPlan` is deterministic (corners, centre, seeded interior points) with an explicit evaluation budget.
* A violation is only a CANDIDATE.  It is replayed; then checked by INDEPENDENT routes at the same point -- a different
  model family, or a higher-fidelity realization (highest fidelity first).  The VOTERS are the candidate's route plus
  every converged independent route; the highest-fidelity tier of voters decides.  Classes:

  =======================  ======================================================================
  PHYSICAL                 replayed, converged, at least one independent route confirms it, and
                           every voter of the highest fidelity tier agrees
  NUMERICAL_ARTIFACT       not reproducible or not converged on replay (unexplained), or a refined
                           route of the SAME family removes it (explained)
  MODEL_FORM_DEPENDENT     the highest-fidelity voters disagree about the violation
  OUTSIDE_PLAUSIBILITY     the point needs an IMPLAUSIBLE dimension value: never a physical
                           counterexample
  UNCONFIRMED              no independent route could be evaluated to confirm it
  =======================  ======================================================================

* A route value that is not finite is a NON-CONVERGED evaluation, never "the claim holds there".

* The :class:`TrustEnvelope` is FALSIFIED(counterexample), SURVIVED(region, budget, method) or UNKNOWN(reason).
  There is no SAFE: not finding a counterexample within a budget and a region says only that.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class RedTeamRefused(ValueError):
    pass


class AttackKind(str, Enum):
    INPUT_PARAMETER = "input_parameter"
    ENVIRONMENT = "environment"
    OPERATING_POINT = "operating_point"
    BOUNDARY_CONDITION = "boundary_condition"
    MATERIAL_ASSUMPTION = "material_assumption"
    MODEL_FORM = "model_form"
    SOLVER_PROVIDER = "solver_provider"
    DISCRETIZATION = "discretization"
    NUMERICAL_SETTING = "numerical_setting"


ROUTE_KINDS = frozenset({AttackKind.MODEL_FORM, AttackKind.SOLVER_PROVIDER, AttackKind.DISCRETIZATION, AttackKind.BOUNDARY_CONDITION,
                         AttackKind.MATERIAL_ASSUMPTION})


class Plausibility(str, Enum):
    PLAUSIBLE = "plausible"
    EDGE = "edge"
    IMPLAUSIBLE = "implausible"


@dataclass(frozen=True)
class AttackDimension:
    """A continuous dimension has ``low``/``high`` and optional EDGE extension ``edge_low``/``edge_high``; a route
    dimension has ``choices`` (route ids).  Either way the range has a SOURCE."""

    name: str
    kind: AttackKind
    source: str
    low: float | None = None
    high: float | None = None
    edge_low: float | None = None
    edge_high: float | None = None
    implausible_beyond: bool = False       # whether the plan may also probe beyond the edge (labelled IMPLAUSIBLE)
    choices: tuple[str, ...] = ()
    unit: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", AttackKind(self.kind))
        if not str(self.name).strip() or not str(self.source).strip():
            raise RedTeamRefused("an attack dimension names itself and the SOURCE of its admissible range")
        if self.choices:
            if self.kind not in ROUTE_KINDS:
                raise RedTeamRefused(f"{self.name}: discrete choices are route alternatives (model/solver/discretization/BC/material)")
            object.__setattr__(self, "choices", tuple(self.choices))
        else:
            if self.low is None or self.high is None or not (math.isfinite(self.low) and math.isfinite(self.high) and self.low <= self.high):
                raise RedTeamRefused(f"{self.name}: a continuous dimension has a finite admissible range")
            if not str(self.unit).strip():
                raise RedTeamRefused(f"{self.name}: a continuous dimension names its unit")
            lo_e = self.low if self.edge_low is None else self.edge_low
            hi_e = self.high if self.edge_high is None else self.edge_high
            if not (lo_e <= self.low and hi_e >= self.high):
                raise RedTeamRefused(f"{self.name}: the EDGE band lies outside the plausible range")

    def plausibility(self, value: Any) -> Plausibility:
        if self.choices:
            return Plausibility.PLAUSIBLE if value in self.choices else Plausibility.IMPLAUSIBLE
        v = float(value)
        if self.low <= v <= self.high:
            return Plausibility.PLAUSIBLE
        lo_e = self.low if self.edge_low is None else self.edge_low
        hi_e = self.high if self.edge_high is None else self.edge_high
        return Plausibility.EDGE if lo_e <= v <= hi_e else Plausibility.IMPLAUSIBLE

    def to_dict(self) -> dict[str, Any]:
        return {k: (val.value if isinstance(val, Enum) else list(val) if isinstance(val, tuple) else val) for k, val in self.__dict__.items()}


@dataclass(frozen=True)
class AttackSpace:
    claim_ref: str
    dimensions: tuple[AttackDimension, ...]

    def __post_init__(self) -> None:
        names = [d.name for d in self.dimensions]
        if not str(self.claim_ref).strip() or not names or len(set(names)) != len(names):
            raise RedTeamRefused("an attack space names its claim and has unique dimensions")
        if sum(1 for d in self.dimensions if d.choices) > 1:
            raise RedTeamRefused("one route dimension per attack space (a route is one model/solver/discretization choice)")

    @property
    def digest(self) -> str:
        return _digest({"claim_ref": self.claim_ref, "dimensions": [d.to_dict() for d in self.dimensions]})

    def classify(self, point: Mapping[str, Any]) -> Plausibility:
        worst = Plausibility.PLAUSIBLE
        for d in self.dimensions:
            p = d.plausibility(point[d.name])
            if p is Plausibility.IMPLAUSIBLE:
                return p
            if p is Plausibility.EDGE:
                worst = p
        return worst


# ---------------------------------------------------------------------------- the subject under attack


@dataclass(frozen=True)
class RouteResult:
    value: float
    converged: bool = True


@dataclass(frozen=True)
class Route:
    route_id: str
    family: str                            # model family: routes of one family are not independent of each other
    fidelity: int                          # higher = higher fidelity within the comparison
    evaluate: Callable[[Mapping[str, float]], RouteResult] = field(compare=False, hash=False)


class Sense(str, Enum):
    AT_MOST = "at_most"
    AT_LEAST = "at_least"


@dataclass(frozen=True)
class ClaimSubject:
    """The claim: ``observable`` <sense> ``threshold`` everywhere in the attack space.  ``claim_route`` is the route the
    claim was made with (the default when the space has no route dimension)."""

    claim_id: str
    observable: str
    unit: str
    sense: Sense
    threshold: float
    routes: tuple[Route, ...]
    claim_route: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "sense", Sense(self.sense))
        ids = [r.route_id for r in self.routes]
        if len(set(ids)) != len(ids) or self.claim_route not in ids:
            raise RedTeamRefused("routes are unique and include the claim's own route")

    def route(self, route_id: str) -> Route:
        for r in self.routes:
            if r.route_id == route_id:
                return r
        raise RedTeamRefused(f"no route {route_id!r}")

    def margin(self, value: float) -> float:
        """Positive = violation by that much; non-positive = the claim holds at this value."""
        return value - self.threshold if self.sense is Sense.AT_MOST else self.threshold - value


# ---------------------------------------------------------------------------- plan and execution


@dataclass(frozen=True)
class AttackPlan:
    space_digest: str
    budget: int                            # evaluations of the subject, all routes counted
    seed: str
    interior_points: int = 16
    probe_edges: bool = True
    probe_implausible: bool = False        # only to label what lies beyond; never counted as physical
    method: str = "corners+centre+seeded-interior/1"

    def __post_init__(self) -> None:
        if self.budget < 1 or self.interior_points < 0 or not str(self.seed).strip():
            raise RedTeamRefused("an attack plan has a positive budget and a seed")


def _points(space: AttackSpace, plan: AttackPlan) -> list[dict[str, Any]]:
    cont = [d for d in space.dimensions if not d.choices]
    routes = [d for d in space.dimensions if d.choices]
    grids = []
    for d in cont:
        vals = [d.low, d.high]
        if plan.probe_edges:
            vals += [x for x in (d.edge_low, d.edge_high) if x is not None]
        if plan.probe_implausible:
            span = max(d.high - d.low, 1e-12)
            vals += [(d.edge_low if d.edge_low is not None else d.low) - 0.5 * span,
                     (d.edge_high if d.edge_high is not None else d.high) + 0.5 * span]
        grids.append(sorted(set(vals)))
    pts = [dict(zip([d.name for d in cont], combo)) for combo in itertools.product(*grids)] if cont else [{}]
    pts.append({d.name: (d.low + d.high) / 2 for d in cont})
    rng = random.Random(f"redteam\n{plan.seed}\n{space.digest}")
    for _ in range(plan.interior_points):
        pts.append({d.name: rng.uniform(d.low, d.high) for d in cont})
    if routes:
        r = routes[0]
        pts = [{**p, r.name: choice} for p in pts for choice in r.choices]
    # deterministic order: plausible first, then edge, then implausible; within each, as generated
    order = {Plausibility.PLAUSIBLE: 0, Plausibility.EDGE: 1, Plausibility.IMPLAUSIBLE: 2}
    return sorted(pts, key=lambda p: order[space.classify(p)])


class CounterexampleClass(str, Enum):
    PHYSICAL = "physical"
    NUMERICAL_ARTIFACT = "numerical_artifact"
    MODEL_FORM_DEPENDENT = "model_form_dependent"
    OUTSIDE_PLAUSIBILITY = "outside_plausibility"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True)
class CounterexampleCandidate:
    point: Mapping[str, Any] = field(hash=False)
    route_id: str = ""
    family: str = ""
    value: float = 0.0
    margin: float = 0.0
    plausibility: Plausibility = Plausibility.PLAUSIBLE
    classification: CounterexampleClass = CounterexampleClass.UNCONFIRMED
    replay_value: float | None = None
    confirmations: tuple[tuple[str, str, int, float, bool], ...] = ()   # (route_id, family, fidelity, margin, converged)
    explained: bool = False             # NUMERICAL_ARTIFACT removed by a refined route of the same family
    reason: str = ""

    @property
    def cross_family_confirmed(self) -> bool:
        return any(fam != self.family and conv and m > 0 for _r, fam, _f, m, conv in self.confirmations)

    def to_dict(self) -> dict[str, Any]:
        return {"point": dict(self.point), "route_id": self.route_id, "family": self.family, "value": self.value, "margin": self.margin,
                "plausibility": self.plausibility.value, "classification": self.classification.value, "replay_value": self.replay_value,
                "confirmations": [list(c) for c in self.confirmations], "explained": self.explained, "reason": self.reason}


class EnvelopeOutcome(str, Enum):
    FALSIFIED = "falsified"
    SURVIVED = "survived"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrustEnvelope:
    claim_id: str
    outcome: EnvelopeOutcome
    space_digest: str
    method: str
    budget: int
    evaluations: int
    region: Mapping[str, Any] = field(hash=False, default_factory=dict)
    counterexample: CounterexampleCandidate | None = None
    candidates: tuple[CounterexampleCandidate, ...] = ()
    reason: str = ""
    evaluations_to_first_candidate: int | None = None
    points_planned: int = 0
    points_covered: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"claim_id": self.claim_id, "outcome": self.outcome.value, "space_digest": self.space_digest, "method": self.method,
                "budget": self.budget, "evaluations": self.evaluations, "region": dict(self.region),
                "counterexample": None if self.counterexample is None else self.counterexample.to_dict(),
                "candidates": [c.to_dict() for c in self.candidates], "reason": self.reason,
                "evaluations_to_first_candidate": self.evaluations_to_first_candidate, "points_planned": self.points_planned,
                "points_covered": self.points_covered, "statement": self.statement()}

    def statement(self) -> str:
        if self.outcome is EnvelopeOutcome.FALSIFIED:
            c = self.counterexample
            return (f"FALSIFIED: physical counterexample at {dict(c.point)} ({c.plausibility.value} region; {c.reason})")
        if self.outcome is EnvelopeOutcome.SURVIVED:
            return (f"SURVIVED {self.evaluations} evaluations ({self.method}) over the declared plausible/edge region "
                    f"{dict(self.region)}; this is not a statement that the claim is safe outside that region, budget or method")
        return f"UNKNOWN: {self.reason}"


def _classify(subject: ClaimSubject, space: AttackSpace, point: Mapping[str, Any], route: Route, first: RouteResult,
              spend: Callable[[Route, Mapping[str, Any]], RouteResult | None], replay_tol: float) -> CounterexampleCandidate:
    plaus = space.classify(point)
    margin = subject.margin(first.value)
    base = dict(point=dict(point), route_id=route.route_id, family=route.family, value=first.value, margin=margin, plausibility=plaus)
    if plaus is Plausibility.IMPLAUSIBLE:
        return CounterexampleCandidate(**base, classification=CounterexampleClass.OUTSIDE_PLAUSIBILITY,
                                       reason="the point needs an implausible dimension value")
    again = spend(route, point)
    if again is None:
        return CounterexampleCandidate(**base, classification=CounterexampleClass.UNCONFIRMED, reason="budget exhausted before replay")
    if not again.converged or abs(again.value - first.value) > replay_tol * max(1.0, abs(first.value)):
        return CounterexampleCandidate(**base, replay_value=again.value, classification=CounterexampleClass.NUMERICAL_ARTIFACT,
                                       reason="not reproducible or not converged on replay")
    confirms = []
    independent = sorted((o for o in subject.routes if o.route_id != route.route_id
                          and (o.family != route.family or o.fidelity > route.fidelity)), key=lambda o: (-o.fidelity, o.route_id))
    for other in independent:
        res = spend(other, point)
        if res is None:
            break
        confirms.append((other.route_id, other.family, other.fidelity, subject.margin(res.value), res.converged))
    base.update(replay_value=again.value, confirmations=tuple(confirms))
    usable = [c for c in confirms if c[4]]
    refined_same = [c for c in usable if c[1] == route.family and c[2] > route.fidelity]
    if refined_same and all(c[3] <= 0 for c in refined_same):
        return CounterexampleCandidate(**base, classification=CounterexampleClass.NUMERICAL_ARTIFACT, explained=True,
                                       reason="a refined route of the same family removes the violation")
    if not usable:
        return CounterexampleCandidate(**base, classification=CounterexampleClass.UNCONFIRMED,
                                       reason="no independent family or higher-fidelity route could confirm it")
    voters = [(route.fidelity, True)] + [(c[2], c[3] > 0) for c in usable]
    top = max(f for f, _ in voters)
    top_votes = [agree for f, agree in voters if f == top]
    confirmed_by = sorted(c[0] for c in usable if c[3] > 0)
    if confirmed_by and all(top_votes):
        return CounterexampleCandidate(**base, classification=CounterexampleClass.PHYSICAL,
                                       reason=f"replayed and confirmed by {confirmed_by}; the highest-fidelity routes agree")
    return CounterexampleCandidate(**base, classification=CounterexampleClass.MODEL_FORM_DEPENDENT,
                                   reason="the highest-fidelity independent routes do not all reproduce the violation")


def run_red_team(subject: ClaimSubject, space: AttackSpace, plan: AttackPlan, *, replay_tol: float = 1e-9) -> TrustEnvelope:
    if plan.space_digest != space.digest:
        raise RedTeamRefused("the plan was made for another attack space")
    if space.claim_ref != subject.claim_id:
        raise RedTeamRefused("the attack space targets another claim")
    route_dim = next((d for d in space.dimensions if d.choices), None)
    if route_dim is not None and set(route_dim.choices) - {r.route_id for r in subject.routes}:
        raise RedTeamRefused("a route choice names a route the subject does not declare")
    used = [0]

    def spend(route: Route, point: Mapping[str, Any]) -> RouteResult | None:
        if used[0] >= plan.budget:
            return None
        used[0] += 1
        res = route.evaluate({k: v for k, v in point.items() if route_dim is None or k != route_dim.name})
        if not isinstance(res, RouteResult):
            raise RedTeamRefused(f"route {route.route_id} returned no RouteResult")
        if not math.isfinite(res.value):                     # never "the claim holds there"
            return RouteResult(float("nan"), converged=False)
        return res

    points = _points(space, plan)
    candidates: list[CounterexampleCandidate] = []
    first_at = None
    nonconverged = 0
    covered = 0
    common = dict(space_digest=space.digest, method=plan.method, budget=plan.budget, points_planned=len(points))
    for point in points:
        route = subject.route(point[route_dim.name]) if route_dim else subject.route(subject.claim_route)
        res = spend(route, point)
        if res is None:
            break
        covered += 1
        if not res.converged:
            nonconverged += 1                                # a non-converged value decides nothing either way
            continue
        if subject.margin(res.value) > 0:
            if first_at is None:
                first_at = used[0]
            cand = _classify(subject, space, point, route, res, spend, replay_tol)
            candidates.append(cand)
            if cand.classification is CounterexampleClass.PHYSICAL:
                return TrustEnvelope(subject.claim_id, EnvelopeOutcome.FALSIFIED, evaluations=used[0], counterexample=cand,
                                     candidates=tuple(candidates), evaluations_to_first_candidate=first_at,
                                     points_covered=covered, **common)
    region = {d.name: (list(d.choices) if d.choices else [d.edge_low if (plan.probe_edges and d.edge_low is not None) else d.low,
                                                         d.edge_high if (plan.probe_edges and d.edge_high is not None) else d.high])
              for d in space.dimensions}
    done = dict(evaluations=used[0], region=region, candidates=tuple(candidates), evaluations_to_first_candidate=first_at,
                points_covered=covered, **common)
    blocking = [c for c in candidates if c.classification in (CounterexampleClass.MODEL_FORM_DEPENDENT, CounterexampleClass.UNCONFIRMED)
                or (c.classification is CounterexampleClass.NUMERICAL_ARTIFACT and not c.explained)]
    if blocking:
        kinds = sorted({c.classification.value for c in blocking})
        return TrustEnvelope(subject.claim_id, EnvelopeOutcome.UNKNOWN, **done,
                             reason=f"violations found but not confirmed as physical ({', '.join(kinds)})")
    if nonconverged:
        return TrustEnvelope(subject.claim_id, EnvelopeOutcome.UNKNOWN, **done, reason=f"{nonconverged} evaluations did not converge")
    if covered < len(points):
        return TrustEnvelope(subject.claim_id, EnvelopeOutcome.UNKNOWN, **done,
                             reason=f"the budget ran out after {covered} of {len(points)} planned points")
    return TrustEnvelope(subject.claim_id, EnvelopeOutcome.SURVIVED, **done,
                         reason="no violation inside the plausible/edge region within the budget" if not candidates
                         else "only explained numerical artifacts or violations beyond plausibility were found")


__all__ = ["AttackDimension", "AttackKind", "AttackPlan", "AttackSpace", "ClaimSubject", "CounterexampleCandidate",
           "CounterexampleClass", "EnvelopeOutcome", "Plausibility", "RedTeamRefused", "Route", "RouteResult", "Sense", "TrustEnvelope",
           "run_red_team"]
