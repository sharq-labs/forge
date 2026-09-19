from __future__ import annotations
from dataclasses import dataclass
import re

_SHA256=re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class CertificationArtifact:
    name:str
    digest:str

    def __post_init__(self)->None:
        name=str(self.name).strip()
        digest=str(self.digest).strip().lower()
        if not name or not _SHA256.fullmatch(digest):
            raise ValueError("certification artifact requires name and lowercase SHA-256 digest")
        object.__setattr__(self,"name",name)
        object.__setattr__(self,"digest",digest)
