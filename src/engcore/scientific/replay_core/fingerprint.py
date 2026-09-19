from __future__ import annotations

import hashlib

from ..serialization import to_json
from .bundle import ReplayBundle


def replay_bundle_fingerprint(bundle: ReplayBundle) -> str:
    if not isinstance(bundle, ReplayBundle):
        raise TypeError("replay_bundle_fingerprint requires ReplayBundle")
    return hashlib.sha256(to_json(bundle).encode("utf-8")).hexdigest()
