from __future__ import annotations

from dataclasses import dataclass
import hashlib, json, re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .environment import RuntimeEnvironment
from .identity import ArtifactIdentity
from .profile import RunManifestProfile

RUN_MANIFEST_SCHEMA=schema_string("scientific_run_manifest")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ScientificRunManifest:
    run_id:str
    profile:RunManifestProfile
    contract_artifacts:tuple[ArtifactIdentity,...]
    environment:RuntimeEnvironment
    random_seed:int|None=None
    parent_run_id:str|None=None
    parent_manifest_digest:str|None=None
    replay_of_manifest_digest:str|None=None

    def __post_init__(self)->None:
        run_id=str(self.run_id).strip()
        artifacts=tuple(sorted(tuple(self.contract_artifacts),key=lambda a:(a.kind,a.identifier,a.digest)))
        if not run_id or not isinstance(self.profile,RunManifestProfile):
            raise InvalidScientificProblem("scientific run manifest requires run_id and RunManifestProfile")
        if any(not isinstance(a,ArtifactIdentity) for a in artifacts):
            raise InvalidScientificProblem("run manifest contract artifacts must be ArtifactIdentity records")
        keys=[(a.kind,a.identifier) for a in artifacts]
        if len(keys)!=len(set(keys)):
            raise InvalidScientificProblem("run manifest contains duplicate artifact kind/identifier bindings")
        if not isinstance(self.environment,RuntimeEnvironment):
            raise InvalidScientificProblem("run manifest requires RuntimeEnvironment")
        if self.random_seed is not None and (isinstance(self.random_seed,bool) or not isinstance(self.random_seed,int)):
            raise InvalidScientificProblem("run manifest random_seed must be int or None")
        parent_run=None if self.parent_run_id is None else str(self.parent_run_id).strip()
        parent_digest=None if self.parent_manifest_digest is None else str(self.parent_manifest_digest).strip().lower()
        if (parent_run is None)!=(parent_digest is None):
            raise InvalidScientificProblem("run manifest parent_run_id and parent_manifest_digest must be declared together")
        if parent_run==run_id:
            raise InvalidScientificProblem("run manifest cannot name itself as parent")
        for label,value in (("parent_manifest_digest",parent_digest),
                            ("replay_of_manifest_digest",self.replay_of_manifest_digest)):
            if value is not None:
                digest=str(value).strip().lower()
                if not _SHA256.fullmatch(digest):
                    raise InvalidScientificProblem(f"{label} must be lowercase SHA-256")
                object.__setattr__(self,label,digest)
        self.profile.validate(artifacts)
        object.__setattr__(self,"run_id",run_id)
        object.__setattr__(self,"contract_artifacts",artifacts)
        object.__setattr__(self,"parent_run_id",parent_run)
        object.__setattr__(self,"parent_manifest_digest",parent_digest)

    def content_dict(self)->dict[str,Any]:
        return {"schema":RUN_MANIFEST_SCHEMA,"run_id":self.run_id,
                "profile":self.profile.to_dict(),
                "contract_artifacts":[a.to_dict() for a in self.contract_artifacts],
                "environment":self.environment.to_dict(),"random_seed":self.random_seed,
                "parent_run_id":self.parent_run_id,
                "parent_manifest_digest":self.parent_manifest_digest,
                "replay_of_manifest_digest":self.replay_of_manifest_digest}

    @property
    def digest(self)->str:
        return hashlib.sha256(json.dumps(self.content_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def to_dict(self)->dict[str,Any]:
        return {**self.content_dict(),"manifest_digest":self.digest}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"ScientificRunManifest":
        require_schema(payload,RUN_MANIFEST_SCHEMA)
        value=cls(payload["run_id"],RunManifestProfile.from_dict(payload["profile"]),
                  tuple(ArtifactIdentity.from_dict(a) for a in payload.get("contract_artifacts",())),
                  RuntimeEnvironment.from_dict(payload["environment"]),payload.get("random_seed"),
                  payload.get("parent_run_id"),payload.get("parent_manifest_digest"),
                  payload.get("replay_of_manifest_digest"))
        if "manifest_digest" in payload and payload["manifest_digest"]!=value.digest:
            raise InvalidScientificProblem("serialized scientific run manifest digest is forged or stale")
        return value
