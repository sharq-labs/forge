"""Binding between artifact Domain Packs and SRIA semantic authority.

Forge historically had two concepts called DomainPack:
- domainpacks.DomainPackProvider owns executable scientific artifacts;
- sria.domain_pack.DomainPack owns semantics, scope, assumptions and critics.

They are no longer independent authorities. A provider may expose an optional
semantic_domain_pack attribute or zero-argument callable. When present,
registration validates it and binds it to the exact artifact-pack identity and
model set. When absent, the registration explicitly has artifact authority
only; no semantic authority is inferred.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..sria.domain_pack import validate_domain_pack as validate_semantic_domain_pack
from .errors import InvalidDomainPackProvider
from .manifest import DomainPackManifest


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _jsonable(to_dict())
    raise InvalidDomainPackProvider(
        "semantic authority contains a value that cannot be serialized "
        f"deterministically: {type(value).__name__}"
    )


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class SemanticAuthoritySnapshot:
    pack_id: str
    pack_version: str
    model_references: tuple[str, ...]
    parameter_semantics: tuple[tuple[str, str], ...]
    qois: tuple[str, ...]
    scope: Any
    assumptions: tuple[str, ...]
    fidelity_ladder: tuple[Any, ...]
    semantic_terms: tuple[str, ...]
    critic_ids: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "model_references": list(self.model_references),
            "parameter_semantics": [
                [key, value] for key, value in self.parameter_semantics
            ],
            "qois": list(self.qois),
            "scope": _jsonable(self.scope),
            "assumptions": list(self.assumptions),
            "fidelity_ladder": [
                _jsonable(item) for item in self.fidelity_ladder
            ],
            "semantic_terms": list(self.semantic_terms),
            "critic_ids": list(self.critic_ids),
            "digest": self.digest,
        }


def _semantic_pack(provider: Any) -> Any | None:
    candidate = getattr(provider, "semantic_domain_pack", None)
    if candidate is None:
        return None
    return candidate() if callable(candidate) else candidate


def bind_semantic_authority(
    provider: Any,
    manifest: DomainPackManifest,
) -> SemanticAuthoritySnapshot | None:
    pack = _semantic_pack(provider)
    if pack is None:
        return None

    try:
        validate_semantic_domain_pack(pack)
    except Exception as exc:
        raise InvalidDomainPackProvider(
            "semantic_domain_pack violates the SRIA semantic-pack contract"
        ) from exc

    key = (
        str(getattr(pack, "pack_id", "")).strip(),
        str(getattr(pack, "pack_version", "")).strip(),
    )
    if key != manifest.key:
        raise InvalidDomainPackProvider(
            "semantic authority must share the exact id/version of the "
            f"artifact Domain Pack; semantic={key}, artifact={manifest.key}"
        )

    model_references = tuple(
        sorted(str(item).strip() for item in pack.model_references())
    )
    expected_models = tuple(
        sorted(
            f"{item.artifact_id}@{item.version}"
            for item in manifest.models
        )
    )
    if model_references != expected_models:
        raise InvalidDomainPackProvider(
            "semantic authority model_references disagree with the artifact "
            f"manifest; semantic={model_references}, artifact={expected_models}"
        )

    semantics = tuple(
        sorted(
            (str(key), str(value))
            for key, value in pack.parameter_semantics().items()
        )
    )
    critics = tuple(pack.domain_critics())
    critic_ids = tuple(
        sorted(str(getattr(item, "critic_id", "")).strip() for item in critics)
    )
    if any(not value for value in critic_ids):
        raise InvalidDomainPackProvider(
            "semantic authority critics must expose non-empty critic_id"
        )

    qois = tuple(sorted(str(item) for item in pack.qois()))
    scope = pack.scope()
    assumptions = tuple(sorted(str(item) for item in pack.assumptions()))
    fidelity = tuple(pack.fidelity_ladder())
    semantic_terms = tuple(sorted(str(item) for item in pack.semantic_terms()))
    payload = {
        "pack_id": key[0],
        "pack_version": key[1],
        "model_references": list(model_references),
        "parameter_semantics": [list(item) for item in semantics],
        "qois": list(qois),
        "scope": _jsonable(scope),
        "assumptions": list(assumptions),
        "fidelity_ladder": [_jsonable(item) for item in fidelity],
        "semantic_terms": list(semantic_terms),
        "critic_ids": list(critic_ids),
    }
    digest = _digest(payload)
    return SemanticAuthoritySnapshot(
        pack_id=key[0],
        pack_version=key[1],
        model_references=model_references,
        parameter_semantics=semantics,
        qois=qois,
        scope=scope,
        assumptions=assumptions,
        fidelity_ladder=fidelity,
        semantic_terms=semantic_terms,
        critic_ids=critic_ids,
        digest=digest,
    )


__all__ = [
    "SemanticAuthoritySnapshot",
    "bind_semantic_authority",
]
