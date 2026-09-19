"""Adapter boundary for native processes and external scientific solvers.

The multiphysics core never imports OpenFOAM, FEniCS, SPICE, PyBaMM or another
provider-specific type. A provider session implements this protocol and the
adapter turns it into the same ExecutableParticipant lifecycle every domain
uses.
"""

from __future__ import annotations

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

    @property
    def spec(self) -> ParticipantSpec:
        return self._spec

    @property
    def provider_identity(self) -> ExternalProviderIdentity:
        return self._session.identity

    def initialize(
        self,
        instant: Quantity,
        external_inputs: Mapping[str, CouplingValue],
        external_uncertainty: Mapping[str, Uncertainty],
    ) -> InitializationResult:
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
        validate_inputs(
            self.spec,
            request.inputs,
            request.input_uncertainty,
        )
        result = self._session.advance(request)
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
        snapshot = self._session.snapshot(instant)
        if not isinstance(snapshot, ExternalSnapshot):
            raise InvalidScientificProblem(
                "external solver snapshot must be ExternalSnapshot"
            )
        return RuntimeCheckpoint(
            record=CheckpointRecord(
                participant_id=self.spec.participant_id,
                instant=instant,
                state_digest=snapshot.state_digest,
                deterministic_restore=self.spec.deterministic_restore,
                provider_state_id=snapshot.provider_state_id,
            ),
            token=snapshot,
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
        if not isinstance(checkpoint.token, ExternalSnapshot):
            raise InvalidScientificProblem(
                "external participant checkpoint token is not ExternalSnapshot"
            )
        if (
            checkpoint.token.state_digest
            != checkpoint.record.state_digest
        ):
            raise InvalidScientificProblem(
                "external checkpoint record and provider snapshot digest disagree"
            )
        self._session.restore(checkpoint.token)

    def finalize(self) -> None:
        self._session.finalize()
