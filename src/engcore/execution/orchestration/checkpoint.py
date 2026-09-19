from __future__ import annotations
from dataclasses import dataclass
import re

_SHA256=re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class CheckpointReference:
    checkpoint_id:str
    state_digest:str

    def __post_init__(self)->None:
        cid=str(self.checkpoint_id).strip()
        digest=str(self.state_digest).strip().lower()
        if not cid or not _SHA256.fullmatch(digest):
            raise ValueError("checkpoint requires id and lowercase SHA-256 state_digest")
        object.__setattr__(self,"checkpoint_id",cid)
        object.__setattr__(self,"state_digest",digest)
