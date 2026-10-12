"""Scientific Red Team: try to break a claim, and say exactly how far the attack got.

::

    Claim -> AttackSpace -> AttackPlan -> CounterexampleCandidate -> Replay -> IndependentCheck -> TrustEnvelope

* An :class:`AttackDimension` has an admissible range (or admissible choices), a SOURCE for that range and a
  plausibility classification (PLAUSIBLE / EDGE / IMPLAUSIBLE).  Route dimensions (model form, solver/provider,
  discretization, boundary condition, material assumption) choose among the subject's declared :class:`Route` records;
  without one, every declared route is swept at every point.
* The :class:`AttackPlan` is deterministic (corners, centre, seeded interior points, edge endpoints AND seeded points
  inside each edge band) with an explicit evaluation budget; its method label is derived from it.
* A violation is only a CANDIDATE.  It is replayed; then checked by INDEPENDENT routes at the same point -- a different
  model family, or a higher-fidelity realization of the same family.  Neither the candidate's route nor the claim's own
  route votes.  Family and fidelity are declared on the :class:`Route` records (residual: they are not yet governed by a
  route registry).  Classes:

  =======================  ======================================================================
  CONFIRMED_ACROSS_ROUTES  replayed, converged, confirmed by a converged route of ANOTHER family,
                           and no converged independent route dissents.  Agreement of declared
                           models -- never a physical measurement
  NUMERICAL_ARTIFACT       not reproducible or not converged on replay (unexplained), or a refined
                           route of the SAME family removes it and no other family reproduces it
                           (explained)
  MODEL_FORM_DEPENDENT     converged independent routes disagree about the violation
  OUTSIDE_PLAUSIBILITY     the point needs an IMPLAUSIBLE dimension value: never a physical
                           counterexample
  UNCONFIRMED              no other-family route confirms it, or an independent route was not
                           evaluated (budget) or did not converge
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
        if self.name == "__route":
            raise RedTeamRefused("'__route' is reserved for the swept route")
        if not str(self.name).strip() or not str(self.source).strip():
            raise RedTeamRefused("an attack dimension names itself and the SOURCE of its admissible range")
        if self.choices:
            if self.kind not in ROUTE_KINDS:
                raise RedTeamRefused(f"{self.name}: discrete choices are route alternatives (model/solver/discretization/BC/material)")
            object.__setattr__(self, "choices", tuple(self.choices))
            if len(set(self.choices)) != len(self.choices):
                raise RedTeamRefused(f"{self.name}: route choices are distinct")
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

    def __post_init__(self) -> None:
        if not str(self.route_id).strip() or not str(self.family).strip():
            raise RedTeamRefused("a route names itself and its model family")
        object.__setattr__(self, "family", str(self.family).strip().lower())     # 'FE' and 'fe' are one family
        if isinstance(self.fidelity, bool) or not isinstance(self.fidelity, int):
            raise RedTeamRefused("a route's fidelity is an integer rank")


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
        if not str(self.claim_id).strip() or not str(self.observable).strip() or not str(self.unit).strip():
            raise RedTeamRefused("a claim names itself, its observable and its unit")
        if isinstance(self.threshold, bool) or not math.isfinite(float(self.threshold)):
            raise RedTeamRefused("a claim's threshold is a finite number (a NaN threshold can never be violated)")
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
    budget: int                            # evaluations of the subject, all routes counted (replays and confirmations too)
    seed: str
    interior_points: int = 16
    edge_interior_points: int = 4          # seeded samples INSIDE each edge band (not only its endpoints)
    probe_edges: bool = True
    probe_implausible: bool = False        # only to label what lies beyond; never a counterexample
    replay_tol: float = 1e-9               # relative replay agreement; part of the plan (and its digest), not a call option

    def __post_init__(self) -> None:
        if isinstance(self.budget, bool) or self.budget < 1 or self.interior_points < 0 or self.edge_interior_points < 0 \
                or not str(self.seed).strip():
            raise RedTeamRefused("an attack plan has a positive budget and a seed")
        if not (math.isfinite(self.replay_tol) and 0 < self.replay_tol < 1):
            raise RedTeamRefused("the replay tolerance is a finite relative tolerance in (0, 1)")

    @property
    def method(self) -> str:
        """Derived from the plan, never caller-asserted."""
        return (f"corners+centre+{self.interior_points} seeded interior"
                + (f"+edge endpoints+{self.edge_interior_points} seeded edge-band" if self.probe_edges else "")
                + ("+implausible probes" if self.probe_implausible else "") + f" (seed {self.seed!r}, redteam/2)")

    def to_dict(self) -> dict[str, Any]:
        return {"space_digest": self.space_digest, "budget": self.budget, "seed": self.seed, "interior_points": self.interior_points,
                "edge_interior_points": self.edge_interior_points, "probe_edges": self.probe_edges,
                "probe_implausible": self.probe_implausible, "replay_tol": self.replay_tol, "method": self.method}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def _points(space: AttackSpace, plan: AttackPlan, route_ids: tuple[str, ...], route_dim: str) -> list[dict[str, Any]]:
    """Deterministic, de-duplicated points, crossed with the attacked routes; plausible first, then edge, then implausible."""
    cont = [d for d in space.dimensions if not d.choices]
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
    if plan.probe_edges:
        for d in cont:
            for lo, hi in ((d.edge_low, d.low), (d.high, d.edge_high)):
                if lo is not None and hi is not None and hi > lo:
                    for _ in range(plan.edge_interior_points):
                        base = {x.name: rng.uniform(x.low, x.high) for x in cont}
                        pts.append({**base, d.name: rng.uniform(lo, hi)})
    seen, unique = set(), []
    for p in pts:
        key = json.dumps(p, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    crossed = [{**p, route_dim: rid} for p in unique for rid in route_ids]
    order = {Plausibility.PLAUSIBLE: 0, Plausibility.EDGE: 1, Plausibility.IMPLAUSIBLE: 2}
    return sorted(crossed, key=lambda p: order[space.classify(p)])


class CounterexampleClass(str, Enum):
    #: replayed, converged, confirmed by at least one converged route of ANOTHER family, with no converged independent
    #: dissent.  Agreement of declared MODEL routes -- not a physical measurement.
    CONFIRMED_ACROSS_ROUTES = "confirmed_across_routes"
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
        def num(x: float | None) -> float | None:
            return None if x is None or not math.isfinite(x) else x
        return {"point": dict(self.point), "route_id": self.route_id, "family": self.family, "value": num(self.value),
                "margin": num(self.margin), "plausibility": self.plausibility.value, "classification": self.classification.value,
                "replay_value": num(self.replay_value),
                "confirmations": [[r, fam, fid, num(m), conv] for r, fam, fid, m, conv in self.confirmations],
                "explained": self.explained, "reason": self.reason}


class EnvelopeOutcome(str, Enum):
    FALSIFIED = "falsified"
    SURVIVED = "survived"
    UNKNOWN = "unknown"


TRUST_ENVELOPE_SCHEMA = "engcore.claims.trust_envelope/2"


@dataclass(frozen=True)
class TrustEnvelope:
    claim_id: str
    outcome: EnvelopeOutcome
    space_digest: str
    plan_digest: str
    subject_digest: str
    method: str
    budget: int
    evaluations: int
    attacked_routes: tuple[str, ...] = ()
    region: Mapping[str, Any] = field(hash=False, default_factory=dict)
    counterexample: CounterexampleCandidate | None = None
    candidates: tuple[CounterexampleCandidate, ...] = ()
    reason: str = ""
    evaluations_to_first_candidate: int | None = None
    points_planned: int = 0
    points_covered: int = 0                # distinct (point, attacked route) pairs evaluated, implausible probes excluded

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TRUST_ENVELOPE_SCHEMA, "claim_id": self.claim_id, "outcome": self.outcome.value,
                "space_digest": self.space_digest, "plan_digest": self.plan_digest, "subject_digest": self.subject_digest,
                "method": self.method, "budget": self.budget, "evaluations": self.evaluations,
                "attacked_routes": list(self.attacked_routes), "region": dict(self.region),
                "counterexample": None if self.counterexample is None else self.counterexample.to_dict(),
                "candidates": [c.to_dict() for c in self.candidates], "reason": self.reason,
                "evaluations_to_first_candidate": self.evaluations_to_first_candidate, "points_planned": self.points_planned,
                "points_covered": self.points_covered, "statement": self.statement()}

    def statement(self) -> str:
        if self.outcome is EnvelopeOutcome.FALSIFIED:
            c = self.counterexample
            routes = sorted({r for r, _f, _fi, m, conv in c.confirmations if conv and m > 0} | {c.route_id})
            return (f"FALSIFIED: counterexample at {dict(c.point)} ({c.plausibility.value} region) confirmed across declared "
                    f"routes {routes} -- agreement of models, not a physical measurement")
        if self.outcome is EnvelopeOutcome.SURVIVED:
            explained = sorted({c.route_id for c in self.candidates if c.explained})
            dismissed = (f"; violations on {explained} were dismissed as numerical artifacts removed by an attacked refined "
                         "route of the same family") if explained else ""
            return (f"SURVIVED {self.points_covered} attacked points ({self.evaluations} evaluations; {self.method}) on routes "
                    f"{list(self.attacked_routes)} over {dict(self.region)}{dismissed}; this is not a statement that the claim is "
                    "safe outside that region, those routes, that budget or that method")
        return f"UNKNOWN: {self.reason}"


def _classify(subject: ClaimSubject, space: AttackSpace, point: Mapping[str, Any], route: Route, first: RouteResult,
              spend: Callable[[Route, Mapping[str, Any]], RouteResult | None], replay_tol: float,
              attacked: tuple[str, ...] = ()) -> CounterexampleCandidate:
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
    # voters: every OTHER route that is independent (another family, or the same family at higher fidelity).  The
    # candidate's own route and the claim's own route never vote: one produced the violation, the other is under attack.
    independent = sorted((o for o in subject.routes if o.route_id not in (route.route_id, subject.claim_route)
                          and (o.family != route.family or o.fidelity > route.fidelity)), key=lambda o: (-o.fidelity, o.route_id))
    confirms = []
    skipped = []
    for other in independent:
        res = spend(other, point)
        if res is None:
            skipped.append(other.route_id)
            continue
        confirms.append((other.route_id, other.family, other.fidelity, subject.margin(res.value), res.converged))
    base.update(replay_value=again.value, confirmations=tuple(confirms))
    if skipped or any(not c[4] for c in confirms):
        return CounterexampleCandidate(**base, classification=CounterexampleClass.UNCONFIRMED,
                                       reason=f"independent routes not evaluated or not converged: "
                                              f"{sorted(skipped + [c[0] for c in confirms if not c[4]])}")
    other_agree = [c for c in confirms if c[1] != route.family and c[3] > 0]
    other_dissent = [c for c in confirms if c[1] != route.family and c[3] <= 0]
    refined_dissent = [c for c in confirms if c[1] == route.family and c[3] <= 0]
    if refined_dissent and not other_agree and not all(c[0] in attacked for c in refined_dissent):
        return CounterexampleCandidate(**base, classification=CounterexampleClass.UNCONFIRMED,
                                       reason=f"only an UNATTACKED refined route {sorted(c[0] for c in refined_dissent)} would explain "
                                              "it away; an explanation must itself have been attacked over the space")
    if refined_dissent and not other_agree:
        return CounterexampleCandidate(**base, classification=CounterexampleClass.NUMERICAL_ARTIFACT, explained=True,
                                       reason="a refined route of the same family removes the violation and no other family "
                                              "reproduces it")
    if other_agree and not other_dissent and not refined_dissent:
        return CounterexampleCandidate(**base, classification=CounterexampleClass.CONFIRMED_ACROSS_ROUTES,
                                       reason=f"replayed and confirmed by other-family routes {sorted(c[0] for c in other_agree)}")
    if not confirms or not (other_agree or other_dissent):
        return CounterexampleCandidate(**base, classification=CounterexampleClass.UNCONFIRMED,
                                       reason="no route of another family could confirm it (same-family agreement only rules "
                                              "out a numerical artifact)")
    return CounterexampleCandidate(**base, classification=CounterexampleClass.MODEL_FORM_DEPENDENT,
                                   reason="independent routes disagree about the violation")


def _subject_digest(subject: ClaimSubject) -> str:
    return _digest({"claim_id": subject.claim_id, "observable": subject.observable, "unit": subject.unit,
                    "sense": subject.sense.value, "threshold": subject.threshold, "claim_route": subject.claim_route,
                    "routes": sorted([r.route_id, r.family, r.fidelity] for r in subject.routes)})


def run_red_team(subject: ClaimSubject, space: AttackSpace, plan: AttackPlan) -> TrustEnvelope:
    """Attack ``subject`` over ``space`` with ``plan``.  Without a route dimension EVERY declared route is swept at every
    point (not only the claim's own route: self-consistency is not surviving an attack)."""
    if plan.space_digest != space.digest:
        raise RedTeamRefused("the plan was made for another attack space")
    if space.claim_ref != subject.claim_id:
        raise RedTeamRefused("the attack space targets another claim")
    route_dim = next((d for d in space.dimensions if d.choices), None)
    if route_dim is not None and set(route_dim.choices) - {r.route_id for r in subject.routes}:
        raise RedTeamRefused("a route choice names a route the subject does not declare")
    if route_dim is not None and subject.claim_route not in route_dim.choices:
        raise RedTeamRefused("the claim's own route is among the attacked route choices")
    attacked = tuple(route_dim.choices) if route_dim is not None else tuple(r.route_id for r in subject.routes)
    dim_name = route_dim.name if route_dim is not None else "__route"
    used = [0]

    def spend(route: Route, point: Mapping[str, Any]) -> RouteResult | None:
        if used[0] >= plan.budget:
            return None
        used[0] += 1
        res = route.evaluate({k: v for k, v in point.items() if k != dim_name})
        if not isinstance(res, RouteResult):
            raise RedTeamRefused(f"route {route.route_id} returned no RouteResult")
        if not math.isfinite(res.value):                     # never "the claim holds there"
            return RouteResult(float("nan"), converged=False)
        return res

    points = _points(space, plan, attacked, dim_name)
    candidates: list[CounterexampleCandidate] = []
    first_at = None
    nonconverged = 0
    covered = 0
    planned_attack = sum(1 for p in points if space.classify(_strip(p, dim_name, route_dim)) is not Plausibility.IMPLAUSIBLE)
    common = dict(space_digest=space.digest, plan_digest=plan.digest, subject_digest=_subject_digest(subject), method=plan.method,
                  budget=plan.budget, attacked_routes=attacked, points_planned=planned_attack)
    exhausted = False
    for point in points:
        route = subject.route(point[dim_name])
        res = spend(route, point)
        if res is None:
            exhausted = True
            break
        visible = _strip(point, dim_name, route_dim)
        if space.classify(visible) is not Plausibility.IMPLAUSIBLE:
            covered += 1
        if not res.converged:
            nonconverged += 1                                # a non-converged value decides nothing either way
            continue
        if subject.margin(res.value) > 0:
            if first_at is None:
                first_at = used[0]
            cand = _classify(subject, space, visible, route, res, spend, plan.replay_tol, attacked)
            candidates.append(cand)
            if cand.classification is CounterexampleClass.CONFIRMED_ACROSS_ROUTES:
                return TrustEnvelope(subject.claim_id, EnvelopeOutcome.FALSIFIED, evaluations=used[0], counterexample=cand,
                                     candidates=tuple(candidates), evaluations_to_first_candidate=first_at,
                                     points_covered=covered, **common)
    region: dict[str, Any] = {}
    for d in space.dimensions:
        if d.choices:
            region[d.name] = list(d.choices)
            continue
        entry: dict[str, Any] = {"plausible": [d.low, d.high]}
        if plan.probe_edges and (d.edge_low is not None or d.edge_high is not None):
            entry["edge_band_sampled" if plan.edge_interior_points else "edge_endpoints_only"] = [d.edge_low if d.edge_low is not None else d.low,
                                          d.edge_high if d.edge_high is not None else d.high]
        region[d.name] = entry
    done = dict(evaluations=used[0], region=region, candidates=tuple(candidates), evaluations_to_first_candidate=first_at,
                points_covered=covered, **common)
    blocking = [c for c in candidates if c.classification in (CounterexampleClass.MODEL_FORM_DEPENDENT, CounterexampleClass.UNCONFIRMED)
                or (c.classification is CounterexampleClass.NUMERICAL_ARTIFACT and not c.explained)]
    if blocking:
        kinds = sorted({c.classification.value for c in blocking})
        return TrustEnvelope(subject.claim_id, EnvelopeOutcome.UNKNOWN, **done,
                             reason=f"violations found but not confirmed across routes ({', '.join(kinds)})")
    if nonconverged:
        return TrustEnvelope(subject.claim_id, EnvelopeOutcome.UNKNOWN, **done, reason=f"{nonconverged} evaluations did not converge")
    if exhausted:
        return TrustEnvelope(subject.claim_id, EnvelopeOutcome.UNKNOWN, **done,
                             reason=f"the budget ran out after {covered} of {planned_attack} planned attack points")
    return TrustEnvelope(subject.claim_id, EnvelopeOutcome.SURVIVED, **done,
                         reason="no violation inside the plausible/edge region within the budget" if not candidates
                         else "only explained numerical artifacts or violations beyond plausibility were found")


def _strip(point: Mapping[str, Any], dim_name: str, route_dim: AttackDimension | None) -> dict[str, Any]:
    return {k: v for k, v in point.items() if k != dim_name or route_dim is not None}


__all__ = ["AttackDimension", "AttackKind", "AttackPlan", "AttackSpace", "ClaimSubject", "CounterexampleCandidate",
           "CounterexampleClass", "EnvelopeOutcome", "Plausibility", "RedTeamRefused", "Route", "RouteResult", "Sense",
           "TRUST_ENVELOPE_SCHEMA", "TrustEnvelope", "run_red_team"]
