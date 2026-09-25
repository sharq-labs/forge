"""Authoritative system state at a synchronization boundary.

A :class:`SystemState` is what the runtime *commits* after a node succeeded and (where declared)
its runtime applicability check held.  It is immutable and digest-chained: each committed state
names the digest of the state it replaced.  A failed or refused step never produces one, so the
previous state stays authoritative.

Value records reuse the Core ``InitialStateValue`` (variable, ``Quantity``, ``Uncertainty``); the
runtime never turns a missing uncertainty into zero (``Uncertainty.unknown`` is explicit).  The set
of owners and, per owner, the set of variables is fixed by the initial state: a step may change a
value, never silently add or drop a variable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics.state import InitialStateValue
from ..scientific.units.quantity import Quantity
from ._common import digest_of, hex64, identifier, reject_non_finite, require_schema, schema, strict_keys, unique

OWNER_STATE_SCHEMA = schema("owner_state")
INITIAL_STATE_SPEC_SCHEMA = schema("initial_state_spec")
SYSTEM_STATE_SCHEMA = schema("system_state")
PROVIDER_CHECKPOINT_REF_SCHEMA = schema("provider_checkpoint_ref")

_OWNER_ROLES = ("component", "slow", "scenario")


def _time_seconds(value: Quantity, label: str) -> float:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    seconds = float(value.magnitude_in("second"))  # dimension mismatch raises
    return seconds


@dataclass(frozen=True, order=True)
class OwnerState:
    """The values one owner (a component instance, the slow lifecycle domain, ...) holds."""

    owner_id: str
    role: str
    values: tuple[InitialStateValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", identifier(self.owner_id, "state owner id"))
        if self.role not in _OWNER_ROLES:
            raise InvalidScientificProblem(f"state owner role must be one of {_OWNER_ROLES}, got {self.role!r}")
        values = tuple(self.values)
        if not values or any(not isinstance(item, InitialStateValue) for item in values):
            raise InvalidScientificProblem(f"owner {self.owner_id!r} needs InitialStateValue records (an empty state is not 'no state')")
        unique(values, lambda item: item.variable_id, f"owner {self.owner_id!r} state variables")
        object.__setattr__(self, "values", tuple(sorted(values, key=lambda item: item.variable_id)))

    def variable_ids(self) -> tuple[str, ...]:
        return tuple(item.variable_id for item in self.values)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": OWNER_STATE_SCHEMA, "owner_id": self.owner_id, "role": self.role, "values": [item.to_dict() for item in self.values]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OwnerState":
        require_schema(payload, OWNER_STATE_SCHEMA)
        strict_keys(payload, {"schema", "owner_id", "role", "values"}, "owner state")
        return cls(payload["owner_id"], payload["role"], tuple(InitialStateValue.from_dict(v) for v in payload["values"]))


@dataclass(frozen=True, order=True)
class ProviderCheckpointRef:
    """A provider/participant checkpoint identity and whether it DECLARES its state complete."""

    owner_id: str
    checkpoint_digest: str
    declared_complete: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_id", identifier(self.owner_id, "checkpoint owner id"))
        object.__setattr__(self, "checkpoint_digest", hex64(self.checkpoint_digest, "checkpoint digest"))
        if not isinstance(self.declared_complete, bool):
            raise InvalidScientificProblem("declared_complete must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROVIDER_CHECKPOINT_REF_SCHEMA, "owner_id": self.owner_id, "checkpoint_digest": self.checkpoint_digest,
                "declared_complete": self.declared_complete}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProviderCheckpointRef":
        require_schema(payload, PROVIDER_CHECKPOINT_REF_SCHEMA)
        strict_keys(payload, {"schema", "owner_id", "checkpoint_digest", "declared_complete"}, "provider checkpoint ref")
        return cls(payload["owner_id"], payload["checkpoint_digest"], payload["declared_complete"])


def _owners(owners: tuple[OwnerState, ...]) -> tuple[OwnerState, ...]:
    owners = tuple(owners)
    if not owners or any(not isinstance(item, OwnerState) for item in owners):
        raise InvalidScientificProblem("a system state needs at least one OwnerState")
    unique(owners, lambda item: item.owner_id, "state owners")
    return tuple(sorted(owners, key=lambda item: item.owner_id))


def _pairs(items: tuple[tuple[str, str], ...], label: str) -> tuple[tuple[str, str], ...]:
    out = tuple((identifier(a, f"{label} owner"), hex64(b, f"{label} digest")) for a, b in items)
    unique(out, lambda item: item[0], label)
    return tuple(sorted(out))


@dataclass(frozen=True)
class InitialStateSpec:
    """The initial state a request declares.  Nothing is inferred: every value is stated."""

    time: Quantity
    owners: tuple[OwnerState, ...]
    material_state_digests: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _time_seconds(self.time, "initial state time")
        object.__setattr__(self, "owners", _owners(self.owners))
        object.__setattr__(self, "material_state_digests", _pairs(self.material_state_digests, "material state"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": INITIAL_STATE_SPEC_SCHEMA, "time": self.time.to_dict(), "owners": [o.to_dict() for o in self.owners],
                "material_state_digests": [list(p) for p in self.material_state_digests]}

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InitialStateSpec":
        require_schema(payload, INITIAL_STATE_SPEC_SCHEMA)
        strict_keys(payload, {"schema", "time", "owners", "material_state_digests"}, "initial state spec")
        return cls(Quantity.from_dict(payload["time"]), tuple(OwnerState.from_dict(o) for o in payload["owners"]),
                   tuple((a, b) for a, b in payload["material_state_digests"]))


@dataclass(frozen=True)
class SystemState:
    """The complete authoritative state at one synchronization boundary."""

    request_digest: str
    system_digest: str
    environment_digest: str  # "" only when the request states the environment is absent
    time: Quantity
    sequence: int
    owners: tuple[OwnerState, ...]
    material_state_digests: tuple[tuple[str, str], ...]
    provider_checkpoints: tuple[ProviderCheckpointRef, ...]
    previous_digest: str
    produced_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_digest", hex64(self.request_digest, "state request digest"))
        object.__setattr__(self, "system_digest", hex64(self.system_digest, "state system digest"))
        object.__setattr__(self, "environment_digest", hex64(self.environment_digest, "state environment digest", allow_empty=True))
        _time_seconds(self.time, "state time")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise InvalidScientificProblem("state sequence must be a non-negative integer")
        object.__setattr__(self, "owners", _owners(self.owners))
        object.__setattr__(self, "material_state_digests", _pairs(self.material_state_digests, "material state"))
        checkpoints = tuple(self.provider_checkpoints)
        if any(not isinstance(item, ProviderCheckpointRef) for item in checkpoints):
            raise InvalidScientificProblem("provider checkpoints must be ProviderCheckpointRef records")
        unique(checkpoints, lambda item: item.owner_id, "provider checkpoints")
        object.__setattr__(self, "provider_checkpoints", tuple(sorted(checkpoints)))
        object.__setattr__(self, "previous_digest", hex64(self.previous_digest, "previous state digest", allow_empty=True))
        if (self.sequence == 0) != (self.previous_digest == ""):
            raise InvalidScientificProblem("only the initial state (sequence 0) has no previous digest")
        object.__setattr__(self, "produced_by", identifier(self.produced_by, "state producer"))

    @classmethod
    def initial(cls, spec: InitialStateSpec, *, request_digest: str, system_digest: str, environment_digest: str) -> "SystemState":
        if not isinstance(spec, InitialStateSpec):
            raise InvalidScientificProblem("initial state requires an InitialStateSpec")
        return cls(request_digest, system_digest, environment_digest, spec.time, 0, spec.owners, spec.material_state_digests, (), "", "initial")

    @property
    def seconds(self) -> float:
        return _time_seconds(self.time, "state time")

    def owner(self, owner_id: str) -> OwnerState:
        for item in self.owners:
            if item.owner_id == owner_id:
                return item
        raise KeyError(owner_id)

    def advance(
        self,
        *,
        time: Quantity,
        updates: tuple[OwnerState, ...],
        produced_by: str,
        provider_checkpoints: tuple[ProviderCheckpointRef, ...] | None = None,
        material_state_digests: tuple[tuple[str, str], ...] | None = None,
    ) -> "SystemState":
        """The next committed state.  Refuses anything that would silently change the state's shape.

        Time never runs backwards; every updated owner must already exist and keep exactly its
        variable set and units; an owner not mentioned keeps its values unchanged.
        """
        if _time_seconds(time, "new state time") < self.seconds:
            raise InvalidScientificProblem("a committed state cannot move backwards in time")
        current = {item.owner_id: item for item in self.owners}
        merged = dict(current)
        for update in tuple(updates):
            if not isinstance(update, OwnerState):
                raise InvalidScientificProblem("state updates must be OwnerState records")
            before = current.get(update.owner_id)
            if before is None:
                raise InvalidScientificProblem(f"state update names unknown owner {update.owner_id!r}; owners are fixed by the initial state")
            if before.variable_ids() != update.variable_ids() or before.role != update.role:
                raise InvalidScientificProblem(
                    f"state update for {update.owner_id!r} would change its variable set or role "
                    f"({before.variable_ids()} -> {update.variable_ids()})")
            for old, new in zip(before.values, update.values):
                if old.value.dimensionality != new.value.dimensionality:
                    raise InvalidScientificProblem(f"state variable {update.owner_id}.{new.variable_id} changed dimension")
            merged[update.owner_id] = update
        return SystemState(
            self.request_digest, self.system_digest, self.environment_digest, time, self.sequence + 1, tuple(merged.values()),
            self.material_state_digests if material_state_digests is None else material_state_digests,
            self.provider_checkpoints if provider_checkpoints is None else provider_checkpoints,
            self.digest, produced_by)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SYSTEM_STATE_SCHEMA, "request_digest": self.request_digest, "system_digest": self.system_digest,
                "environment_digest": self.environment_digest, "time": self.time.to_dict(), "sequence": self.sequence,
                "owners": [o.to_dict() for o in self.owners], "material_state_digests": [list(p) for p in self.material_state_digests],
                "provider_checkpoints": [c.to_dict() for c in self.provider_checkpoints], "previous_digest": self.previous_digest,
                "produced_by": self.produced_by}

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SystemState":
        require_schema(payload, SYSTEM_STATE_SCHEMA)
        strict_keys(payload, {"schema", "request_digest", "system_digest", "environment_digest", "time", "sequence", "owners",
                              "material_state_digests", "provider_checkpoints", "previous_digest", "produced_by"}, "system state")
        reject_non_finite(payload, "system state")
        return cls(payload["request_digest"], payload["system_digest"], payload["environment_digest"], Quantity.from_dict(payload["time"]),
                   payload["sequence"], tuple(OwnerState.from_dict(o) for o in payload["owners"]),
                   tuple((a, b) for a, b in payload["material_state_digests"]),
                   tuple(ProviderCheckpointRef.from_dict(c) for c in payload["provider_checkpoints"]),
                   payload["previous_digest"], payload["produced_by"])
