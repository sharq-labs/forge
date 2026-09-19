from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema,schema_string
from .independence import IndependenceEvidence,IndependenceLevel

DEPENDENCY_COMPONENT_SCHEMA=schema_string("verification_dependency_component")
DEPENDENCY_MANIFEST_SCHEMA=schema_string("verification_dependency_manifest")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


class DependencyRole(str,Enum):
    MODEL="model"
    SOLVER="solver"
    NUMERICS="numerics"
    DATA="data"
    LIBRARY="library"
    RUNTIME="runtime"


@dataclass(frozen=True)
class DependencyComponent:
    family_id:str
    implementation_digest:str
    role:DependencyRole

    def __post_init__(self)->None:
        family=str(self.family_id).strip();digest=str(self.implementation_digest).strip().lower()
        if not family or not _SHA256.fullmatch(digest):
            raise InvalidScientificProblem("dependency component requires family id and SHA-256 implementation digest")
        object.__setattr__(self,"family_id",family);object.__setattr__(self,"implementation_digest",digest)
        object.__setattr__(self,"role",DependencyRole(self.role))

    def to_dict(self)->dict[str,Any]:
        return {"schema":DEPENDENCY_COMPONENT_SCHEMA,"family_id":self.family_id,
                "implementation_digest":self.implementation_digest,"role":self.role.value}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"DependencyComponent":
        require_schema(payload,DEPENDENCY_COMPONENT_SCHEMA)
        return cls(payload["family_id"],payload["implementation_digest"],DependencyRole(payload["role"]))


@dataclass(frozen=True)
class RouteDependencyManifest:
    route_id:str
    components:tuple[DependencyComponent,...]
    authority_id:str
    externally_operated:bool=False

    def __post_init__(self)->None:
        route=str(self.route_id).strip();authority=str(self.authority_id).strip()
        components=tuple(self.components)
        if not route or not authority or not components:
            raise InvalidScientificProblem("verification dependency manifest requires route, authority and components")
        if any(not isinstance(c,DependencyComponent) for c in components):
            raise InvalidScientificProblem("manifest components must be DependencyComponent records")
        keys=[(c.role,c.family_id) for c in components]
        if len(keys)!=len(set(keys)): raise InvalidScientificProblem("dependency manifest duplicates a role/family component")
        if not isinstance(self.externally_operated,bool): raise InvalidScientificProblem("externally_operated must be bool")
        object.__setattr__(self,"route_id",route);object.__setattr__(self,"authority_id",authority)
        object.__setattr__(self,"components",components)

    def to_dict(self)->dict[str,Any]:
        return {"schema":DEPENDENCY_MANIFEST_SCHEMA,"route_id":self.route_id,
                "components":[c.to_dict() for c in self.components],"authority_id":self.authority_id,
                "externally_operated":self.externally_operated}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"RouteDependencyManifest":
        require_schema(payload,DEPENDENCY_MANIFEST_SCHEMA)
        return cls(payload["route_id"],tuple(DependencyComponent.from_dict(c) for c in payload["components"]),
                   payload["authority_id"],payload.get("externally_operated",False))


def derive_independence(primary:RouteDependencyManifest,candidate:RouteDependencyManifest)->IndependenceEvidence:
    if primary.route_id==candidate.route_id:
        raise InvalidScientificProblem("independence requires distinct route ids")
    p={(c.role.value,c.family_id):c for c in primary.components}
    q={(c.role.value,c.family_id):c for c in candidate.components}
    shared_families=tuple(sorted(f"{role}:{family}" for role,family in set(p)&set(q)))
    p_exact={(c.role.value,c.family_id,c.implementation_digest) for c in primary.components}
    q_exact={(c.role.value,c.family_id,c.implementation_digest) for c in candidate.components}
    if p_exact==q_exact:
        level=IndependenceLevel.NONE
        rationale="routes have the same dependency implementation set"
        shared=shared_families
    elif shared_families:
        level=IndependenceLevel.PARTIAL
        rationale="routes share one or more dependency families"
        shared=shared_families
    elif candidate.externally_operated and candidate.authority_id!=primary.authority_id:
        level=IndependenceLevel.EXTERNAL
        rationale="dependency families are disjoint and verification is operated by a distinct external authority"
        shared=()
    else:
        level=IndependenceLevel.STRONG
        rationale="declared dependency families are disjoint"
        shared=()
    return IndependenceEvidence(primary.route_id,candidate.route_id,level,shared,rationale)
