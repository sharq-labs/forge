from __future__ import annotations

from dataclasses import dataclass
import hashlib, json
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .identity import ArtifactIdentity

RUN_MANIFEST_PROFILE_SCHEMA=schema_string("scientific_run_manifest_profile")


@dataclass(frozen=True)
class RunManifestProfile:
    profile_id:str
    required_artifact_kinds:tuple[str,...]
    singleton_artifact_kinds:tuple[str,...]=()
    allow_extra_artifact_kinds:bool=True
    replay_exact_artifact_kinds:tuple[str,...]|None=None

    def __post_init__(self)->None:
        profile_id=str(self.profile_id).strip()
        required=tuple(sorted(set(str(x).strip() for x in self.required_artifact_kinds)))
        singleton=tuple(sorted(set(str(x).strip() for x in self.singleton_artifact_kinds)))
        if not profile_id or any(not x for x in required+singleton):
            raise InvalidScientificProblem("run manifest profile requires non-empty ids and artifact kinds")
        if not set(singleton)<=set(required):
            raise InvalidScientificProblem("singleton artifact kinds must also be required")
        if not isinstance(self.allow_extra_artifact_kinds,bool):
            raise InvalidScientificProblem("allow_extra_artifact_kinds must be bool")
        exact = required if self.replay_exact_artifact_kinds is None else tuple(
            sorted(set(str(x).strip() for x in self.replay_exact_artifact_kinds))
        )
        if any(not x for x in exact) or not set(exact)<=set(required):
            raise InvalidScientificProblem(
                "replay-exact artifact kinds must be a subset of required artifact kinds"
            )
        object.__setattr__(self,"profile_id",profile_id)
        object.__setattr__(self,"required_artifact_kinds",required)
        object.__setattr__(self,"singleton_artifact_kinds",singleton)
        object.__setattr__(self,"replay_exact_artifact_kinds",exact)

    def validate(self,artifacts:tuple[ArtifactIdentity,...])->None:
        kinds=[a.kind for a in artifacts]
        missing=sorted(set(self.required_artifact_kinds)-set(kinds))
        if missing:
            raise InvalidScientificProblem(f"run manifest is missing required artifact kinds {missing}")
        repeated=sorted(kind for kind in self.singleton_artifact_kinds if kinds.count(kind)!=1)
        if repeated:
            raise InvalidScientificProblem(f"run manifest singleton artifact kinds do not occur exactly once {repeated}")
        if not self.allow_extra_artifact_kinds:
            extra=sorted(set(kinds)-set(self.required_artifact_kinds))
            if extra:
                raise InvalidScientificProblem(f"run manifest contains undeclared extra artifact kinds {extra}")

    def to_dict(self)->dict[str,Any]:
        return {"schema":RUN_MANIFEST_PROFILE_SCHEMA,"profile_id":self.profile_id,
                "required_artifact_kinds":list(self.required_artifact_kinds),
                "singleton_artifact_kinds":list(self.singleton_artifact_kinds),
                "allow_extra_artifact_kinds":self.allow_extra_artifact_kinds,
                "replay_exact_artifact_kinds":list(self.replay_exact_artifact_kinds)}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"RunManifestProfile":
        require_schema(payload,RUN_MANIFEST_PROFILE_SCHEMA)
        return cls(payload["profile_id"],tuple(payload.get("required_artifact_kinds",())),
                   tuple(payload.get("singleton_artifact_kinds",())),
                   payload.get("allow_extra_artifact_kinds",True),
                   tuple(payload.get("replay_exact_artifact_kinds",()))
                   if "replay_exact_artifact_kinds" in payload else None)

    @property
    def digest(self)->str:
        return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
