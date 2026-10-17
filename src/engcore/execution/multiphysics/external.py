"""Adapter boundary for native processes and external scientific solvers.

The multiphysics core never imports OpenFOAM, FEniCS, SPICE, PyBaMM or another
provider-specific type. A provider session implements this protocol and the
adapter turns it into the same ExecutableParticipant lifecycle every domain
uses.
"""

from __future__ import annotations

import json
import secrets
import weakref
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import CheckpointRecord, ParticipantSpec
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity
from .participant import (
    AdvanceRequest,
    AdvanceResult,
    CouplingValue,
    ExecutableParticipant,
    InitializationResult,
    RuntimeCheckpoint,
    validate_inputs,
    validate_outputs,
)


@dataclass(frozen=True)
class ExternalProviderIdentity:
    provider_id: str
    provider_version: str
    adapter_id: str
    adapter_version: str

    def __post_init__(self) -> None:
        for label in (
            "provider_id",
            "provider_version",
            "adapter_id",
            "adapter_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"external provider identity requires {label}"
                )
            object.__setattr__(self, label, value)

    @property
    def state_scope(self) -> str:
        """The provider build whose state a snapshot holds (bound into checkpoint records).

        Canonical JSON of the four identity fields: unambiguous whatever
        characters the fields contain.
        """
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
        }


@dataclass(frozen=True)
class ExternalSnapshot:
    state_digest: str
    provider_state_id: str
    token: Any

    def __post_init__(self) -> None:
        digest = str(self.state_digest).strip().lower()
        provider_state_id = str(self.provider_state_id).strip()
        if (
            len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise InvalidScientificProblem(
                "external snapshot state_digest must be sha256 hex"
            )
        if not provider_state_id:
            raise InvalidScientificProblem(
                "external snapshot requires provider_state_id"
            )
        object.__setattr__(self, "state_digest", digest)
        object.__setattr__(self, "provider_state_id", provider_state_id)


@dataclass(frozen=True)
class _ScopedSnapshot:
    """A provider snapshot sealed by the participant with the build that wrote it.

    ``nonce`` is the participant's own issue record: a wrapper built anywhere
    else, even with the right scope, names no issued checkpoint and is refused.
    """

    scope: str
    snapshot: ExternalSnapshot
    nonce: str


@runtime_checkable
class ExternalSolverSession(Protocol):
    @property
    def identity(self) -> ExternalProviderIdentity: ...

    def initialize(
        self,
        instant: Quantity,
        inputs: Mapping[str, CouplingValue],
        input_uncertainty: Mapping[str, Uncertainty],
    ) -> InitializationResult: ...

    def advance(self, request: AdvanceRequest) -> AdvanceResult: ...

    def snapshot(self, instant: Quantity) -> ExternalSnapshot: ...

    def restore(self, snapshot: ExternalSnapshot) -> None: ...

    def finalize(self) -> None: ...


class ExternalSolverParticipant(ExecutableParticipant):
    """Provider-neutral adapter with identity and checkpoint enforcement."""

    def __init__(
        self,
        spec: ParticipantSpec,
        session: ExternalSolverSession,
    ) -> None:
        self._spec = spec
        self._session = session
        identity = session.identity
        if identity.provider_id != spec.solver_id:
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} declares solver "
                f"{spec.solver_id!r}, external provider is "
                f"{identity.provider_id!r}"
            )
        if identity.provider_version != spec.solver_version:
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} declares solver version "
                f"{spec.solver_version!r}, external provider is "
                f"{identity.provider_version!r}"
            )
        if identity.adapter_id != spec.adapter_id:
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} declares adapter "
                f"{spec.adapter_id!r}, session exposes "
                f"{identity.adapter_id!r}"
            )
        if identity.adapter_version != spec.adapter_version:
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} declares adapter version "
                f"{spec.adapter_version!r}, session exposes "
                f"{identity.adapter_version!r}"
            )
        # the identity verified against the spec; a session whose identity
        # later changes is refused rather than re-read
        self._identity = identity
        # nonce -> the very snapshot object issued here (weak: an entry lives as
        # long as some checkpoint still holds it, so the registry stays bounded)
        self._issued: weakref.WeakValueDictionary[str, ExternalSnapshot] = (
            weakref.WeakValueDictionary()
        )

    @property
    def spec(self) -> ParticipantSpec:
        return self._spec

    @property
    def provider_identity(self) -> ExternalProviderIdentity:
        return self._identity

    def _require_same_build(self) -> str:
        if self._session.identity != self._identity:
            raise InvalidScientificProblem(
                f"external session of participant {self.spec.participant_id!r} "
                f"changed provider identity after admission"
            )
        return self._identity.state_scope

    def initialize(
        self,
        instant: Quantity,
        external_inputs: Mapping[str, CouplingValue],
        external_uncertainty: Mapping[str, Uncertainty],
    ) -> InitializationResult:
        self._require_same_build()
        validate_inputs(
            self.spec,
            external_inputs,
            external_uncertainty,
        )
        result = self._session.initialize(
            instant,
            external_inputs,
            external_uncertainty,
        )
        self._require_same_build()  # a build switched inside the call is refused too
        if not isinstance(result, InitializationResult):
            raise InvalidScientificProblem(
                f"external provider {self.provider_identity.provider_id!r} "
                f"initialize returned {type(result).__name__}"
            )
        validate_outputs(
            self.spec,
            result.outputs,
            result.uncertainty,
        )
        return result

    def advance(self, request: AdvanceRequest) -> AdvanceResult:
        # outputs are attributed to the admitted build: a session now running
        # another build is refused, not recorded under the admitted identity
        self._require_same_build()
        validate_inputs(
            self.spec,
            request.inputs,
            request.input_uncertainty,
        )
        result = self._session.advance(request)
        self._require_same_build()  # a build switched inside the call is refused too
        if not isinstance(result, AdvanceResult):
            raise InvalidScientificProblem(
                f"external provider {self.provider_identity.provider_id!r} "
                f"advance returned {type(result).__name__}"
            )
        validate_outputs(
            self.spec,
            result.outputs,
            result.uncertainty,
        )
        return result

    def checkpoint(self, instant: Quantity) -> RuntimeCheckpoint:
        if not self.spec.checkpointable:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} is not checkpointable"
            )
        scope = self._require_same_build()
        snapshot = self._session.snapshot(instant)
        self._require_same_build()  # never seal a snapshot under a build it was not taken from
        if not isinstance(snapshot, ExternalSnapshot):
            raise InvalidScientificProblem(
                "external solver snapshot must be ExternalSnapshot"
            )
        nonce = secrets.token_hex(16)
        self._issued[nonce] = snapshot
        return RuntimeCheckpoint(
            record=CheckpointRecord(
                participant_id=self.spec.participant_id,
                instant=instant,
                state_digest=snapshot.state_digest,
                deterministic_restore=self.spec.deterministic_restore,
                # provider state is opaque to Forge and meaningful only to the
                # provider build that wrote it: the record names that build
                provider_state_id=f"{scope}#{snapshot.provider_state_id}",
            ),
            token=_ScopedSnapshot(scope, snapshot, nonce),
        )

    def restore(self, checkpoint: RuntimeCheckpoint) -> None:
        if not self.spec.checkpointable:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} is not checkpointable"
            )
        if checkpoint.record.participant_id != self.spec.participant_id:
            raise InvalidScientificProblem(
                "external participant cannot restore another participant checkpoint"
            )
        scope = self._require_same_build()
        token = checkpoint.token
        if not isinstance(token, _ScopedSnapshot) or not isinstance(
            token.snapshot, ExternalSnapshot
        ):
            raise InvalidScientificProblem(
                "external participant checkpoint token was not sealed by an "
                "external participant"
            )
        if (
            token.scope != scope
            or checkpoint.record.provider_state_id
            != f"{scope}#{token.snapshot.provider_state_id}"
        ):
            raise InvalidScientificProblem(
                f"external checkpoint holds state of provider build "
                f"{token.scope}; participant {self.spec.participant_id!r} runs "
                f"{scope} and never restores another provider's or build's state"
            )
        if token.snapshot.state_digest != checkpoint.record.state_digest:
            raise InvalidScientificProblem(
                "external checkpoint record and provider snapshot digest disagree"
            )
        # identity, not equality: a payload re-wrapped under an issued digest,
        # slot and nonce is not the state that digest was recorded for
        if self._issued.get(token.nonce) is not token.snapshot:
            raise InvalidScientificProblem(
                f"external checkpoint was not issued by participant "
                f"{self.spec.participant_id!r}; only its own checkpoints restore"
            )
        self._session.restore(token.snapshot)
        self._require_same_build()

    def finalize(self) -> None:
        self._session.finalize()
