from __future__ import annotations

from dataclasses import dataclass
from .dependencies import RouteDependencyManifest,derive_independence
from .independence import IndependenceEvidence,IndependenceLevel
from .ladder import VerificationLevel,level_for_route
from .route import VerificationRoute


_INDEPENDENCE_RANK={IndependenceLevel.NONE:0,IndependenceLevel.PARTIAL:1,
                    IndependenceLevel.STRONG:2,IndependenceLevel.EXTERNAL:3}


@dataclass(frozen=True)
class VerificationPolicy:
    minimum_level:VerificationLevel=VerificationLevel.V2
    minimum_independence:IndependenceLevel=IndependenceLevel.STRONG
    minimum_routes:int=1
    require_external:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"minimum_level",VerificationLevel(self.minimum_level))
        object.__setattr__(self,"minimum_independence",IndependenceLevel(self.minimum_independence))
        if isinstance(self.minimum_routes,bool) or int(self.minimum_routes)<1: raise ValueError("minimum_routes must be >=1")
        object.__setattr__(self,"minimum_routes",int(self.minimum_routes))
        if not isinstance(self.require_external,bool): raise ValueError("require_external must be bool")


@dataclass(frozen=True)
class VerificationCandidate:
    route:VerificationRoute
    dependencies:RouteDependencyManifest
    def __post_init__(self)->None:
        if self.route.route_id!=self.dependencies.route_id: raise ValueError("verification route and dependency manifest ids differ")


@dataclass(frozen=True)
class PlannedVerificationRoute:
    candidate:VerificationCandidate
    independence:IndependenceEvidence


@dataclass(frozen=True)
class VerificationPlan:
    primary_route:VerificationRoute
    primary_dependencies:RouteDependencyManifest
    selected:tuple[PlannedVerificationRoute,...]
    rejected:tuple[tuple[str,str],...]
    policy:VerificationPolicy

    @property
    def complete(self)->bool:
        if len(self.selected)<self.policy.minimum_routes: return False
        if self.policy.require_external and not any(x.independence.level is IndependenceLevel.EXTERNAL for x in self.selected): return False
        return True


def plan_verification(primary_route:VerificationRoute,primary_dependencies:RouteDependencyManifest,
                      candidates:tuple[VerificationCandidate,...],policy:VerificationPolicy=VerificationPolicy())->VerificationPlan:
    if primary_route.route_id!=primary_dependencies.route_id: raise ValueError("primary route and dependency manifest ids differ")
    selected=[];rejected=[]
    for candidate in candidates:
        if candidate.route.route_id==primary_route.route_id:
            rejected.append((candidate.route.route_id,"same route as primary"));continue
        level=level_for_route(candidate.route.kind)
        independence=derive_independence(primary_dependencies,candidate.dependencies)
        if level<policy.minimum_level:
            rejected.append((candidate.route.route_id,f"verification level V{int(level)} below required V{int(policy.minimum_level)}"));continue
        if _INDEPENDENCE_RANK[independence.level]<_INDEPENDENCE_RANK[policy.minimum_independence]:
            rejected.append((candidate.route.route_id,f"independence {independence.level.value} below required {policy.minimum_independence.value}"));continue
        selected.append(PlannedVerificationRoute(candidate,independence))
    selected.sort(key=lambda x:(-int(level_for_route(x.candidate.route.kind)),
                                -_INDEPENDENCE_RANK[x.independence.level],x.candidate.route.route_id))
    return VerificationPlan(primary_route,primary_dependencies,tuple(selected),tuple(rejected),policy)
