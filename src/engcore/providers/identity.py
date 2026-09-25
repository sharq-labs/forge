"""Provider execution identity derived from CONTENT, never from caller-chosen labels.

Everything that can change a provider's result enters the digest: provider id,
version and package/executable digest, adapter identity, the Forge problem, the
generated provider configuration (e.g. an ``.inp`` deck, an OpenFOAM
dictionary, a PyBaMM parameter-set dump), every input artifact's bytes, the
output request, the BIG 2 time window, the environment and state digests.  A
random workspace path is never part of identity; the bytes written into it are.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..scenarios.timeline import TimeWindow
from ..scientific.errors import InvalidScientificProblem
from .catalog import ProviderStatus

IDENTITY_SCHEMA = "engcore.providers.execution_identity/1"


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def content_digest(payload: Any) -> str:
    """sha256 of bytes, of text, or of canonical JSON (NaN/Inf refused)."""
    if isinstance(payload, bytes):
        data = payload
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        try:
            data = canonical_json(payload).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise InvalidScientificProblem(f"provider identity content is not canonical data: {exc}") from exc
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ProviderExecutionIdentity:
    provider_id: str
    provider_version: str
    provider_digest: str
    adapter_id: str
    adapter_version: str
    problem_digest: str
    configuration_digest: str
    input_digests: tuple[tuple[str, str], ...]
    output_request: tuple[str, ...]
    window: TimeWindow | None
    environment_digest: str
    state_digest: str
    #: result-changing dependencies of the provider (name, version, sha256) from discovery
    provider_dependencies: tuple[tuple[str, str, str], ...] = ()

    @classmethod
    def from_content(cls, status: ProviderStatus, *, adapter_id: str, adapter_version: str, problem: Any, configuration: Any,
                     inputs: Mapping[str, Any] = {}, output_request: tuple[str, ...] = (), window: TimeWindow | None = None,
                     environment: Any = None, state: Any = None) -> "ProviderExecutionIdentity":
        if not status.available or not status.version or not status.digest:
            raise InvalidScientificProblem("execution identity needs an AVAILABLE provider with version and digest")
        if not output_request:
            raise InvalidScientificProblem("an execution must state which outputs it requests")
        return cls(status.capability.provider_id, status.version, status.digest, adapter_id, adapter_version,
                   content_digest(problem), content_digest(configuration),
                   tuple(sorted((name, content_digest(value)) for name, value in inputs.items())),
                   tuple(sorted(output_request)), window,
                   "" if environment is None else content_digest(environment), "" if state is None else content_digest(state),
                   tuple(status.dependencies))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": IDENTITY_SCHEMA, "provider_id": self.provider_id, "provider_version": self.provider_version,
                "provider_digest": self.provider_digest, "adapter_id": self.adapter_id, "adapter_version": self.adapter_version,
                "problem_digest": self.problem_digest, "configuration_digest": self.configuration_digest,
                "input_digests": [list(x) for x in self.input_digests], "output_request": list(self.output_request),
                "window": None if self.window is None else self.window.to_dict(),
                "environment_digest": self.environment_digest, "state_digest": self.state_digest,
                "provider_dependencies": [list(d) for d in self.provider_dependencies]}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())
