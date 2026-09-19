from __future__ import annotations

import hashlib,json
from typing import Any,Mapping

from .identity import ArtifactIdentity


def artifact_from_payload(kind:str,identifier:str,payload:Mapping[str,Any])->ArtifactIdentity:
    digest=hashlib.sha256(
        json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    ).hexdigest()
    return ArtifactIdentity(kind,identifier,digest)


def provenance_artifact(record)->ArtifactIdentity:
    payload=record.to_dict()
    return artifact_from_payload("provenance_record",record.run_id,payload)
