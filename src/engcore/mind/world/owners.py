"""Read-only adapters over the canonical owners a world is projected from.

Each reader READS one owner through that owner's own API, states the owner's identity for a record (the owner's own
digest rule, never one this package invents), and projects the allowed fields.  It never writes, converts, decides
applicability, availability or affordability, and never issues a verdict.  Exact owner types are required: a
look-alike or a subclass is not the owner.

=================  ======================================================================================================
owner kind         owner, identity and current read
=================  ======================================================================================================
SYSTEM_STATE       ``system_runtime``: the execution side's run record (``SystemRunResult`` or ``SystemCheckpoint``).
                   Owner instance: the run's request digest.  Record: one ``(state owner, variable)`` of the HEAD
                   state (``final_state`` / the checkpoint's ``state``, which the owner's constructors bind to the last
                   committed state of a digest chain).  Revision: the state sequence.  Digest: ``SystemState.digest``.
                   History: every earlier committed state of the run (so a ghost digest is MISSING, an earlier one
                   STALE).  Which run governs is the execution side's statement; across runs nothing is inferred.
MODEL_RECORD       ``scientific.ModelRegistry.get(model_id, version)``; exact ``ScientificModelDefinition`` only.
                   Digest: sha256 of ``engcore.scientific.to_json`` (the frozen deterministic serialization).
PROVIDER_STATUS    ``providers.ProviderRegistry.status(provider_id)`` and ``providers.health.assess_health``.  Digest:
                   the health report's own ``status_digest`` rule (``content_digest`` of the status without its
                   location).  Revision: the status version.
BUDGET_LEDGER      ``sria.campaign.BudgetLedger``: ``digest`` and ``revision`` (the ledger's own read-only identity).
EXPERIMENT         ``scientific.experiments.ScientificExperiment``: sha256 of ``to_json``; revision = evaluations.
DECLARATION        the problem/protocol declaration the execution side holds in force (``ProtocolDeclaration``).
UNIT_REGISTRY      ``scientific.units``: ``registry_fingerprint()`` after ``verify_registry_unmutated()``.
=================  ======================================================================================================

A reader built from a snapshot (:func:`frozen_readers`) answers exactly the reads a historical projection and its
verification made: replay proves what a world contained, never that its owners still state it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from engcore.providers.catalog import ProviderRegistry
from engcore.providers.health import assess_health
from engcore.providers.identity import content_digest
from engcore.scientific import ModelNotFoundError, ScientificCoreError, to_json
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.scientific.models.registry import ModelRegistry
from engcore.scientific.units.quantity import registry_fingerprint, verify_registry_unmutated
from engcore.sria.campaign.budget import BudgetLedger
from engcore.system_runtime.result import SystemCheckpoint, SystemRunResult

from .authority import OwnerKind, OwnerRecord
from .base import WorldRefused, text

K = OwnerKind


def record_key(*parts: str) -> str:
    """An unambiguous record identity from owner-side identifiers (which may contain any separator)."""
    return json.dumps([text(p, "record identity part") for p in parts], ensure_ascii=True, separators=(",", ":"))


def record_parts(record_id: str, n: int) -> tuple[str, ...] | None:
    try:
        parts = json.loads(record_id)
    except (TypeError, ValueError):
        return None
    if not isinstance(parts, list) or len(parts) != n or any(type(p) is not str for p in parts):
        return None
    return tuple(parts)


def _sha_json(record: Any) -> str:
    return hashlib.sha256(to_json(record).encode("utf-8")).hexdigest()


class _Reader:
    kinds: frozenset[OwnerKind] = frozenset()
    owner_id: str = ""

    def superseded(self, kind: OwnerKind, record_id: str) -> frozenset[str] | None:
        return None                                   # most owners replace in place and keep no history

    def project(self, record: OwnerRecord, fields: tuple[str, ...]) -> dict[str, Any]:
        payload = record.payload
        missing = [f for f in fields if f not in payload]
        if missing:
            raise WorldRefused(f"the {record.owner_kind.value} record {record.record_id!r} has no field {missing}")
        return {f: payload[f] for f in fields}


# ---- the state owner -------------------------------------------------------------------------------------------------------
class RunStateReader(_Reader):
    """The head state of the run record the execution side says governs (exactly a run result or checkpoint)."""

    kinds = frozenset({K.SYSTEM_STATE})

    def __init__(self, record: Any) -> None:
        if type(record) is SystemRunResult:
            head, self.final = record.final_state, True
        elif type(record) is SystemCheckpoint:
            head, self.final = record.state, False
        else:
            raise WorldRefused("the state owner is exactly a SystemRunResult or SystemCheckpoint (its constructors "
                               f"bind the head to the last committed state), not {type(record).__name__}")
        if head is None:
            raise WorldRefused("the run committed no state; there is no head to read")
        self.owner_id = record.request_digest
        self._head = head
        self._history = frozenset(s.digest for s in record.state_history) - {head.digest}

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        parts = record_parts(record_id, 2)
        if OwnerKind(kind) is not K.SYSTEM_STATE or parts is None:
            return None
        owner, variable = parts
        try:
            values = self._head.owner(owner).values
        except KeyError:
            return None
        found = [v for v in values if v.variable_id == variable]
        if len(found) != 1:
            return None
        v = found[0]
        return OwnerRecord(K.SYSTEM_STATE, self.owner_id, record_id, str(self._head.sequence), self._head.digest,
                           {"value": v.value.to_dict(), "uncertainty": v.uncertainty.to_dict()})

    def superseded(self, kind: OwnerKind, record_id: str) -> frozenset[str] | None:
        return self._history


# ---- the model registry -----------------------------------------------------------------------------------------------------
class ModelRegistryReader(_Reader):
    kinds = frozenset({K.MODEL_RECORD})

    def __init__(self, registry: ModelRegistry, owner_id: str) -> None:
        if type(registry) is not ModelRegistry:
            raise WorldRefused("the model owner is exactly a ModelRegistry")
        self._registry = registry
        self.owner_id = text(owner_id, "model registry id")

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        parts = record_parts(record_id, 2)
        if OwnerKind(kind) is not K.MODEL_RECORD or parts is None:
            return None
        try:
            model = self._registry.get(*parts)
        except ModelNotFoundError:
            return None
        if type(model) is not ScientificModelDefinition:
            raise WorldRefused(f"the registered record for {parts} is a {type(model).__name__}, not exactly a "
                               "ScientificModelDefinition (a subclass could assess differently)")
        return OwnerRecord(K.MODEL_RECORD, self.owner_id, record_id, model.version, _sha_json(model),
                           {"model": model.to_dict()})


# ---- the provider authority --------------------------------------------------------------------------------------------------
class ProviderRegistryReader(_Reader):
    kinds = frozenset({K.PROVIDER_STATUS})

    def __init__(self, registry: ProviderRegistry, owner_id: str) -> None:
        if type(registry) is not ProviderRegistry:
            raise WorldRefused("the provider owner is exactly a ProviderRegistry")
        self._registry = registry
        self.owner_id = text(owner_id, "provider registry id")

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if OwnerKind(kind) is not K.PROVIDER_STATUS:
            return None
        try:
            status = self._registry.status(record_id)
        except Exception:  # noqa: BLE001 - an unregistered or unprobeable provider is absent, never guessed
            return None
        report = assess_health(status)
        payload = status.to_dict()
        return OwnerRecord(K.PROVIDER_STATUS, self.owner_id, record_id, status.version or "-",
                           content_digest({k: v for k, v in payload.items() if k != "location"}),
                           {"status": payload, "report": report.to_dict()})


# ---- the budget owners ---------------------------------------------------------------------------------------------------------
class BudgetReader(_Reader):
    """Budget ledgers (``BudgetLedger``) and observation accounts (``ScientificExperiment``) by id."""

    kinds = frozenset({K.BUDGET_LEDGER, K.EXPERIMENT})

    def __init__(self, ledgers: Mapping[str, BudgetLedger] | None = None,
                 experiments: Mapping[str, ScientificExperiment] | None = None, owner_id: str = "budget") -> None:
        self._ledgers = dict(ledgers or {})
        self._experiments = dict(experiments or {})
        if any(type(x) is not BudgetLedger for x in self._ledgers.values()):
            raise WorldRefused("a budget ledger is exactly a BudgetLedger")
        if any(type(x) is not ScientificExperiment for x in self._experiments.values()):
            raise WorldRefused("an observation account is exactly a ScientificExperiment")
        self.owner_id = text(owner_id, "budget owner id")

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        kind = OwnerKind(kind)
        if kind is K.BUDGET_LEDGER:
            ledger = self._ledgers.get(record_id)
            if ledger is None:
                return None
            return OwnerRecord(kind, self.owner_id, record_id, str(ledger.revision), ledger.digest,
                               {"ledger": ledger.to_dict()})
        if kind is K.EXPERIMENT:
            exp = self._experiments.get(record_id)
            if exp is None:
                return None
            payload = exp.to_dict()
            return OwnerRecord(kind, self.owner_id, record_id, str(len(exp.evaluations)), _sha_json(exp),
                               {"budget": payload["budget"], "accounting": payload["accounting"]})
        return None


# ---- the declaration in force ----------------------------------------------------------------------------------------------------
class DeclarationReader(_Reader):
    """The problem / protocol declarations the execution side holds in force, by declaration id."""

    kinds = frozenset({K.DECLARATION})

    def __init__(self, in_force: Iterable[Any], owner_id: str = "declarations") -> None:
        from .declaration import ProtocolDeclaration

        held: dict[str, Any] = {}
        for d in in_force:
            if type(d) is not ProtocolDeclaration:
                raise WorldRefused("a declaration in force is exactly a ProtocolDeclaration")
            if d.declaration_id in held:
                raise WorldRefused(f"two declarations in force for {d.declaration_id!r}")
            held[d.declaration_id] = d
        self._held = held
        self.owner_id = text(owner_id, "declaration owner id")

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        d = self._held.get(record_id) if OwnerKind(kind) is K.DECLARATION else None
        if d is None:
            return None
        return OwnerRecord(K.DECLARATION, self.owner_id, record_id, str(d.revision), d.digest,
                           {"declaration": d.to_dict()})


# ---- the unit registry -----------------------------------------------------------------------------------------------------------
UNIT_RECORD = "sealed_registry"


class UnitRegistryReader(_Reader):
    kinds = frozenset({K.UNIT_REGISTRY})
    owner_id = "engcore.scientific.units"

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if OwnerKind(kind) is not K.UNIT_REGISTRY or record_id != UNIT_RECORD:
            return None
        try:
            verify_registry_unmutated()
        except ScientificCoreError as exc:
            raise WorldRefused(f"the unit registry was mutated behind its seal: {exc}") from None
        fingerprint = registry_fingerprint()
        return OwnerRecord(K.UNIT_REGISTRY, self.owner_id, UNIT_RECORD, fingerprint[:16], fingerprint,
                           {"fingerprint": fingerprint})


# ---- frozen readers (replay) -----------------------------------------------------------------------------------------------------
class FrozenReader(_Reader):
    """Answers exactly the reads recorded in a snapshot: what the owners stated then, not what they state now."""

    def __init__(self, kind: OwnerKind, owner_id: str, records: Mapping[str, tuple[OwnerRecord, frozenset[str] | None]]
                 ) -> None:
        self.kinds = frozenset({OwnerKind(kind)})
        self.owner_id = owner_id
        self._records = dict(records)

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        found = self._records.get(record_id)
        return None if found is None or OwnerKind(kind) not in self.kinds else found[0]

    def superseded(self, kind: OwnerKind, record_id: str) -> frozenset[str] | None:
        found = self._records.get(record_id)
        return None if found is None else found[1]


def frozen_readers(snapshot: Mapping[str, Any]) -> tuple[FrozenReader, ...]:
    by_kind: dict[OwnerKind, dict[str, tuple[OwnerRecord, frozenset[str] | None]]] = {}
    owners = {OwnerKind(k): o for k, o in snapshot["owners"]}
    for item in snapshot["records"]:
        r = item["record"]
        record = OwnerRecord(OwnerKind(r["owner_kind"]), r["owner_id"], r["record_id"], r["revision"],
                             r["record_digest"], r["payload"])
        history = None if item["superseded"] is None else frozenset(item["superseded"])
        by_kind.setdefault(record.owner_kind, {})[record.record_id] = (record, history)
    return tuple(FrozenReader(kind, owner_id, by_kind.get(kind, {})) for kind, owner_id in sorted(
        owners.items(), key=lambda kv: kv[0].value))


__all__ = [
    "BudgetReader", "DeclarationReader", "FrozenReader", "ModelRegistryReader", "ProviderRegistryReader",
    "RunStateReader", "UNIT_RECORD", "UnitRegistryReader", "frozen_readers", "record_key", "record_parts",
]
