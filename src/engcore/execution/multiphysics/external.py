"""Adapter boundary for native processes and external scientific solvers.

The multiphysics core never imports OpenFOAM, FEniCS, SPICE, PyBaMM or another
provider-specific type. A provider session implements this protocol and the
adapter turns it into the same ExecutableParticipant lifecycle every domain
uses.

Phase 2 BR12:

* **Mocks are labelled.**  ``ExternalProviderIdentity.mock`` marks a session
  that is not a real provider (a test double, a replay of canned values).  The
  label is part of the identity a checkpoint is sealed to, and
  ``system_runtime.MultiphysicsAuthority`` refuses a run with a mock external
  participant unless its caller explicitly allows mocks.  A mock is never
  evidence that a real provider executes.
* **Failures are classified.**  A session that raises anything other than a
  scientific refusal (a crashed process, a missing file, a library error) is
  reported as :class:`ExternalProviderFailure`, naming the provider build and
  the lifecycle phase.  It is a refusal of the window, never retried as a
  numerical non-convergence; numerical non-convergence is the session's
  ``internal_converged=False``, which the runtime may retry.
"""

from __future__ import annotations

import json
import secrets
import weakref
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from ...scientific.errors import InvalidScientificProblem, ScientificCoreError
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
    #: True for a session that is not a real provider (labelled, never evidence of real execution)
    mock: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mock, bool):
            raise InvalidScientificProblem("external provider identity mock flag must be boolean")
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
        return checkpoint_scope(self.to_dict())

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            # absent for real providers: their state scope and checkpoints keep their identity
            **({"mock": True} if self.mock else {}),
        }


@dataclass(frozen=True)
class ExternalSnapshot:
    """A provider session's state at a checkpoint.

    Forge cannot recompute ``state_digest`` from the opaque ``token``, so the
    session must not change ``token`` after issuing it (hand out an immutable
    token, or copy it on restore): a token edited in place would restore under
    the digest recorded for the original.
    """

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


def checkpoint_scope(build: Mapping[str, Any]) -> str:
    """Canonical JSON of a provider build: the scope a checkpoint record names.

    Unambiguous whatever characters the fields contain, so two builds never
    share a scope string.
    """
    return json.dumps(build, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class _ScopedSnapshot:
    """A provider snapshot sealed by the participant with the build that wrote it.

    ``nonce`` is the participant's own issue record: a wrapper built anywhere
    else, even with the right scope, names no issued checkpoint and is refused.
    ``snapshot`` is whatever state the participant restores from
    (an :class:`ExternalSnapshot`, an adapter's held state, a provider solution).
    """

    scope: str
    snapshot: Any
    nonce: str


_NOT_ISSUED = object()


class CheckpointSeal:
    """Issues and admits one participant's checkpoints for one provider build.

    Provider state is opaque to Forge and meaningful only to the build that
    wrote it, so the record names that build: ``provider_state_id`` is
    ``<scope>#<slot>``.  ``admit`` returns a token's state only when all hold:

    * the token was sealed here, under this build's scope and the record's slot;
    * this seal issued it: the registry holds the very state object, by
      identity, so a payload re-wrapped under an issued nonce is refused;
    * the record is the one issued with that token (instant, digest, slot and
      restore flag), so a record re-made around an issued token is refused;
    * the participant's digest of the state, recomputed now, still equals the
      issued digest, and so does its optional ``integrity_of`` fingerprint
      (continuation state outside the recorded identity, e.g. a solver's
      clock): state edited in place after issue is refused.

    The registry is per seal (per participant object) and bounded by live
    tokens: an entry is dropped when no checkpoint holds its token any more.
    """

    def __init__(
        self,
        participant_id: str,
        scope: str,
        *,
        integrity_of: Callable[[Any], str] | None = None,
    ) -> None:
        self._participant_id = participant_id
        self._scope = scope
        self._integrity_of = integrity_of or (lambda _state: "")
        # nonce -> (the very state object issued, the record issued with it,
        # the state's integrity fingerprint at issue)
        self._issued: dict[str, tuple[Any, CheckpointRecord, str]] = {}

    @property
    def scope(self) -> str:
        return self._scope

    def seal(
        self,
        instant: Quantity,
        *,
        state_digest: str,
        deterministic_restore: bool,
        slot: str,
        state: Any,
    ) -> RuntimeCheckpoint:
        nonce = secrets.token_hex(16)
        token = _ScopedSnapshot(self._scope, state, nonce)
        record = CheckpointRecord(
            participant_id=self._participant_id,
            instant=instant,
            state_digest=state_digest,
            deterministic_restore=deterministic_restore,
            provider_state_id=f"{self._scope}#{slot}",
        )
        self._issued[nonce] = (state, record, self._integrity_of(state))
        weakref.finalize(token, self._issued.pop, nonce, None)
        return RuntimeCheckpoint(record=record, token=token)

    def admit(
        self,
        checkpoint: RuntimeCheckpoint,
        *,
        slot_of: Callable[[Any], str],
        digest_of: Callable[[Any], str],
        state_type: type | tuple[type, ...] = object,
        label: str = "provider",
    ) -> Any:
        token = checkpoint.token
        if not isinstance(token, _ScopedSnapshot) or not isinstance(
            token.snapshot, state_type
        ):
            raise InvalidScientificProblem(
                f"{label} participant checkpoint token was not sealed by the "
                f"participant's checkpoint seal"
            )
        if (
            token.scope != self._scope
            or checkpoint.record.provider_state_id
            != f"{self._scope}#{slot_of(token.snapshot)}"
        ):
            raise InvalidScientificProblem(
                f"{label} checkpoint holds state of provider build "
                f"{token.scope}; participant {self._participant_id!r} runs "
                f"{self._scope} and never restores another provider's or "
                f"build's state"
            )
        issued_state, issued_record, fingerprint = self._issued.get(
            token.nonce, (_NOT_ISSUED, None, "")
        )
        # identity, not equality: a payload re-wrapped under an issued digest,
        # slot and nonce is not the state that digest was recorded for
        if issued_state is not token.snapshot:
            raise InvalidScientificProblem(
                f"{label} checkpoint was not issued by participant "
                f"{self._participant_id!r}; only its own checkpoints restore"
            )
        if checkpoint.record != issued_record:
            raise InvalidScientificProblem(
                f"{label} checkpoint record and provider snapshot digest disagree"
                if checkpoint.record.state_digest != issued_record.state_digest
                else f"{label} checkpoint record was not issued with its token"
            )
        if (
            digest_of(token.snapshot) != issued_record.state_digest
            or self._integrity_of(token.snapshot) != fingerprint
        ):
            raise InvalidScientificProblem(
                f"{label} checkpoint state changed after it was issued: it no "
                f"longer hashes to what was issued"
            )
        return token.snapshot


class ExternalProviderFailure(InvalidScientificProblem):
    """An external session failed for a non-scientific reason (process, file, library); a refusal, never a retry."""

    def __init__(self, message: str, *, identity: "ExternalProviderIdentity", phase: str) -> None:
        super().__init__(message)
        self.identity = identity
        self.phase = phase


def _classified(participant: "ExternalSolverParticipant", phase: str, call, *args):
    try:
        return call(*args)
    except ScientificCoreError:
        # a scientific refusal, or a numerical failure the runtime classifies and may retry
        # (CouplingWindowNotConverged), keeps its own type
        raise
    except Exception as exc:  # noqa: BLE001 - every other failure is a provider failure, named
        identity = participant.provider_identity
        raise ExternalProviderFailure(
            f"external provider {identity.provider_id}@{identity.provider_version} "
            f"(adapter {identity.adapter_id}@{identity.adapter_version}) failed during {phase} of participant "
            f"{participant.spec.participant_id!r}: {type(exc).__name__}: {exc}",
            identity=identity,
            phase=phase,
        ) from exc


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
        # issues and admits this participant's checkpoints for the admitted build
        self._seal = CheckpointSeal(spec.participant_id, identity.state_scope)

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
        result = _classified(
            self, "initialize", self._session.initialize, instant, external_inputs, external_uncertainty
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
        result = _classified(self, "advance", self._session.advance, request)
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
        self._require_same_build()
        snapshot = _classified(self, "snapshot", self._session.snapshot, instant)
        self._require_same_build()  # never seal a snapshot under a build it was not taken from
        if not isinstance(snapshot, ExternalSnapshot):
            raise InvalidScientificProblem(
                "external solver snapshot must be ExternalSnapshot"
            )
        return self._seal.seal(
            instant,
            state_digest=snapshot.state_digest,
            deterministic_restore=self.spec.deterministic_restore,
            slot=snapshot.provider_state_id,
            state=snapshot,
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
        self._require_same_build()
        snapshot = self._seal.admit(
            checkpoint,
            slot_of=lambda state: state.provider_state_id,
            # the provider's own digest: its state is opaque to Forge
            digest_of=lambda state: state.state_digest,
            state_type=ExternalSnapshot,
            label="external",
        )
        _classified(self, "restore", self._session.restore, snapshot)
        self._require_same_build()

    @property
    def is_mock(self) -> bool:
        return self._identity.mock

    def finalize(self) -> None:
        _classified(self, "finalize", self._session.finalize)
