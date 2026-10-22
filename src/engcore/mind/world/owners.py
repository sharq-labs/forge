"""Read-only adapters over the canonical owners a world is projected from.

Each reader READS one owner through that owner's own API, states the identity of a record, and projects the allowed
fields.  It never writes, converts, decides applicability, availability or affordability, and never issues a
verdict.  Exact owner types are required: a look-alike or a subclass is not the owner.  Where the owner defines a
digest (``SystemState.digest``, ``BudgetLedger.digest``, the provider health report's status digest, the unit
registry fingerprint) that digest is the identity.  ``ScientificModelDefinition`` and ``ScientificExperiment`` define
none: their identity here is sha256 of the core's own frozen deterministic serialization (``engcore.scientific.
to_json``), a change detector over the owner's whole record, labelled world-derived (no owner digest exists).

LIVENESS.  A reader is ``live`` when every read consults the owner as it is at that moment.  Readers over mutable
owner objects (the model and provider registries, ledgers, experiments, the unit registry) are live.  A run record
and a set of declarations are values: ``RunStateReader(record)`` and ``DeclarationReader(declarations)`` state what the
execution side handed over at one moment (enough to project and to replay) and are NOT live;
``RunStateReader.following(head)`` and ``DeclarationReader.following(in_force)`` ask the execution side again at every
read and are.  Frozen snapshot readers are never live.  Liveness is derived from the reader's type and mode, never
asserted by a caller; only live readers back a dispatch.

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
verification made, and only after each recorded payload re-derives the owner's own identity for the record (the
owner's digest rule applied to the payload, :func:`rederive`): a snapshot record whose payload its digest refutes is
refused.  Replay therefore proves that a record is self-consistent under the owners' rules and what admission decided
on it, never that the owners held it then or still state it now (provenance needs the owner's own anchor).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Iterable, Mapping

from engcore.providers.catalog import (
    Availability, ProviderCapability, ProviderRegistry, ProviderStatus, ProviderUnavailable,
)
from engcore.providers.health import assess_health
from engcore.providers.identity import content_digest
from engcore.scientific import ModelNotFoundError, ScientificCoreError, to_json
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.scientific.models.registry import ModelRegistry
from engcore.scientific.units.quantity import registry_fingerprint, verify_registry_unmutated
from engcore.sria.campaign.budget import BudgetLedger
from engcore.system_runtime.result import SystemCheckpoint, SystemRunResult
from engcore.system_runtime.state import SystemState

from .authority import OwnerKind, OwnerRecord, OwnerUnavailable
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
    live: bool = True                                 # see LIVENESS above; a reader over a mutable owner object

    def pinned(self) -> "_Reader":
        """This reader with the owner's current state held fixed for one verification (one consistent read)."""
        return self

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
    """The head state of the run the execution side says governs (exactly a run result or checkpoint).

    ``RunStateReader(record)`` reads the record as handed over: it cannot know whether the run moved on since, so it
    is not live.  ``RunStateReader.following(head)`` calls the execution side's ``head()`` at every verification and
    reads the record it returns now, which must be the same run (its request digest is the owner instance): live.
    Which record is the head of the run is the execution side's statement; nothing here infers it."""

    kinds = frozenset({K.SYSTEM_STATE})

    def __init__(self, record: Any) -> None:
        self.owner_id, self._head, self._history = self._load(record)
        self._follow: Callable[[], Any] | None = None
        self._record = record                         # the record object loaded (a following reader reuses its load)
        self._highest = (self._head.sequence, self._head.digest)     # following: the furthest head stated so far

    @classmethod
    def following(cls, head: Callable[[], Any]) -> "RunStateReader":
        if not callable(head):
            raise WorldRefused("a followed run head is a callable the execution side answers with its current record")
        reader = cls(head())
        reader._follow = head
        return reader

    @property
    def live(self) -> bool:                          # derived from the mode, never set
        return self._follow is not None

    @staticmethod
    def _load(record: Any) -> tuple[str, Any, frozenset[str]]:
        if type(record) is SystemRunResult:
            head = record.final_state
        elif type(record) is SystemCheckpoint:
            head = record.state
        else:
            raise WorldRefused("the state owner is exactly a SystemRunResult or SystemCheckpoint (its constructors "
                               f"bind the head to the last committed state), not {type(record).__name__}")
        if head is None:
            raise WorldRefused("the run committed no state; there is no head to read")
        return record.request_digest, head, frozenset(s.digest for s in record.state_history) - {head.digest}

    def pinned(self) -> "RunStateReader":
        if self._follow is None:
            return self
        try:
            record = self._follow()
            if record is self._record and type(record) in (SystemRunResult, SystemCheckpoint):
                current = RunStateReader.__new__(RunStateReader)      # the same frozen record: its load is reused
                current.owner_id, current._head, current._history = self.owner_id, self._head, self._history
                current._follow, current._record = None, record
            else:
                current = RunStateReader(record)
        except Exception as exc:  # noqa: BLE001 - an owner that cannot state its head is unavailable, never guessed
            raise OwnerUnavailable(f"the execution side could not state the run's current head: {exc}") from None
        if current.owner_id != self.owner_id:
            raise OwnerUnavailable("the followed head belongs to another run (its request digest changed); which run "
                                   "governs is a new statement, not a move of this one")
        sequence, head = current._head.sequence, current._head.digest
        if sequence < self._highest[0] or (sequence == self._highest[0] and head != self._highest[1]):
            raise OwnerUnavailable(f"the followed head went back (sequence {sequence} after {self._highest[0]}) or "
                                   "restated a sequence with another state: a run's head only moves forward")
        self._highest = (sequence, head)
        self._record, self._head, self._history = current._record, current._head, current._history
        return current

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if self._follow is not None:
            return self.pinned().read(kind, record_id)
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
                           {"value": v.value.to_dict(), "uncertainty": v.uncertainty.to_dict(),
                            "state": self._head.to_dict()})

    def superseded(self, kind: OwnerKind, record_id: str) -> frozenset[str] | None:
        if self._follow is not None:
            return self.pinned().superseded(kind, record_id)
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
    """The provider registry's status of a provider, and the owner's health assessment of that status.

    ``ProviderRegistry.status`` answers from the registry's own cache once a provider was probed (the owner's
    semantics, the same ``system_runtime.preflight`` relies on).  With ``refresh=True`` every read re-probes through the
    owner's ``status(refresh=True)``: the execution side chooses its currency policy; nothing here decides it.  (The
    owner's refresh also clears its process-wide distribution caches: re-probing is a deliberate execution-side cost.)"""

    kinds = frozenset({K.PROVIDER_STATUS})

    def __init__(self, registry: ProviderRegistry, owner_id: str, *, refresh: bool = False) -> None:
        if type(registry) is not ProviderRegistry:
            raise WorldRefused("the provider owner is exactly a ProviderRegistry")
        if type(refresh) is not bool:
            raise WorldRefused("refresh is a bool")
        self._registry = registry
        self._refresh = refresh
        self.owner_id = text(owner_id, "provider registry id")

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if OwnerKind(kind) is not K.PROVIDER_STATUS:
            return None
        try:
            status = self._registry.status(record_id, refresh=self._refresh)
        except ProviderUnavailable:                   # the registry holds no such provider
            return None
        except Exception as exc:  # noqa: BLE001 - a probe that fails is an owner that cannot answer, never a guess
            raise OwnerUnavailable(f"the provider registry could not probe {record_id!r}: {exc}") from None
        report = assess_health(status)
        payload = status.to_dict()
        return OwnerRecord(K.PROVIDER_STATUS, self.owner_id, record_id, status.version or "-",
                           content_digest({k: v for k, v in payload.items() if k != "location"}),
                           {"status": payload, "report": report.to_dict()})


# ---- the budget owners ---------------------------------------------------------------------------------------------------------
class BudgetReader(_Reader):
    """Budget ledgers (``BudgetLedger``) and observation accounts (``ScientificExperiment``) by id.

    ``BudgetReader(ledgers, experiments)`` reads the account OBJECTS handed over: live for their in-place changes
    (settled charges, recorded evaluations), not for an execution side that replaces an account object (as
    ``sria.campaign`` does on restore).  ``BudgetReader.following(accounts)`` asks the execution side's ``accounts()``
    for the current ``(ledgers, experiments)`` at every verification."""

    kinds = frozenset({K.BUDGET_LEDGER, K.EXPERIMENT})

    @classmethod
    def following(cls, accounts: Callable[[], tuple[Mapping[str, Any], Mapping[str, Any]]],
                  owner_id: str = "budget") -> "BudgetReader":
        if not callable(accounts):
            raise WorldRefused("followed accounts are a callable the execution side answers with (ledgers, experiments)")
        reader = cls(*accounts(), owner_id=owner_id)
        reader._follow = accounts
        return reader

    def pinned(self) -> "BudgetReader":
        if self._follow is None:
            return self
        try:
            return BudgetReader(*self._follow(), owner_id=self.owner_id)
        except Exception as exc:  # noqa: BLE001 - an owner that cannot state its accounts is unavailable
            raise OwnerUnavailable(f"the execution side could not state its budget accounts: {exc}") from None

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if self._follow is not None:
            return self.pinned().read(kind, record_id)
        return self._read(kind, record_id)

    def __init__(self, ledgers: Mapping[str, BudgetLedger] | None = None,
                 experiments: Mapping[str, ScientificExperiment] | None = None, owner_id: str = "budget") -> None:
        self._follow: Callable[[], Any] | None = None
        self._ledgers = dict(ledgers or {})
        self._experiments = dict(experiments or {})
        if any(type(x) is not BudgetLedger for x in self._ledgers.values()):
            raise WorldRefused("a budget ledger is exactly a BudgetLedger")
        if any(type(x) is not ScientificExperiment for x in self._experiments.values()):
            raise WorldRefused("an observation account is exactly a ScientificExperiment")
        accounts = [*self._ledgers.values(), *self._experiments.values()]
        if len({id(x) for x in accounts}) != len(accounts):
            raise WorldRefused("one budget account object is registered under one id (an account registered twice "
                               "could state two dimensions from one pool)")
        self.owner_id = text(owner_id, "budget owner id")

    def _read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
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
                               {"budget": payload["budget"], "accounting": payload["accounting"], "experiment": payload})
        return None


# ---- the declaration in force ----------------------------------------------------------------------------------------------------
class DeclarationReader(_Reader):
    """The problem / protocol declarations the execution side holds in force, by declaration id.

    The reader holds DETACHED copies (rebuilt from each declaration's payload), so no world projected from it shares an
    object with what is in force.  ``DeclarationReader(declarations)`` holds the set as handed over (not live; edits to
    the objects handed over do not reach it).  ``DeclarationReader.following(in_force)`` asks the execution side's
    ``in_force()`` at every verification (live) and trusts what it returns NOW: a revised declaration makes every
    admission on the old one stale, a revision restated with other content is refused (a revision names one content),
    and a revision lower than one already seen is refused (revisions only move forward).  The execution side should
    return payload-built copies, not objects it shares with others."""

    kinds = frozenset({K.DECLARATION})

    def __init__(self, in_force: Iterable[Any], owner_id: str = "declarations") -> None:
        self._held = self._load(in_force)
        self.owner_id = text(owner_id, "declaration owner id")
        self._follow: Callable[[], Iterable[Any]] | None = None
        self._seen: dict[tuple[str, int], str] = {(i, d.revision): d.digest for i, d in self._held.items()}
        self._latest: dict[str, int] = {i: d.revision for i, d in self._held.items()}

    @classmethod
    def following(cls, in_force: Callable[[], Iterable[Any]], owner_id: str = "declarations") -> "DeclarationReader":
        if not callable(in_force):
            raise WorldRefused("followed declarations are a callable the execution side answers with those in force")
        reader = cls(in_force(), owner_id)
        reader._follow = in_force
        return reader

    @property
    def live(self) -> bool:                          # derived from the mode, never set
        return self._follow is not None

    @staticmethod
    def _load(in_force: Iterable[Any]) -> dict[str, Any]:
        from .declaration import ProtocolDeclaration

        held: dict[str, Any] = {}
        for d in in_force:
            if type(d) is not ProtocolDeclaration:
                raise WorldRefused("a declaration in force is exactly a ProtocolDeclaration")
            if d.declaration_id in held:
                raise WorldRefused(f"two declarations in force for {d.declaration_id!r}")
            detached = ProtocolDeclaration.from_dict(d.to_dict())
            if detached.digest != d.digest:
                raise WorldRefused(f"declaration {d.declaration_id!r} does not rebuild from its own payload")
            held[d.declaration_id] = detached
        return held

    def pinned(self) -> "DeclarationReader":
        if self._follow is None:
            return self
        try:
            current = DeclarationReader(self._follow(), self.owner_id)
        except Exception as exc:  # noqa: BLE001 - an owner that cannot state what is in force is unavailable
            raise OwnerUnavailable(f"the execution side could not state the declarations in force: {exc}") from None
        for key, d in ((k, current._held[k[0]]) for k in current._seen):
            if self._seen.setdefault(key, d.digest) != d.digest:
                raise OwnerUnavailable(f"declaration {key[0]!r} revision {key[1]} is restated with other content (a "
                                       "revision names one content; a change is a new revision)")
            if d.revision < self._latest.setdefault(key[0], d.revision):
                raise OwnerUnavailable(f"declaration {key[0]!r} went back from revision {self._latest[key[0]]} to "
                                       f"{d.revision} (revisions only move forward)")
            self._latest[key[0]] = max(self._latest[key[0]], d.revision)
        return current

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if self._follow is not None:
            return self.pinned().read(kind, record_id)
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
def rederive(kind: OwnerKind, owner_id: str, record_id: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    """(revision, digest) of a recorded owner payload, by the owner's own identity rule; refused when the payload does
    not carry what the rule needs, is not self-consistent, or is not the record it is filed under (the run, model,
    provider or declaration it names).  Used for snapshot records, never for live reads."""
    from engcore.sria.decision.replay import canonical_digest

    from .declaration import ProtocolDeclaration

    kind = OwnerKind(kind)
    try:
        if kind is K.DECLARATION:
            d = ProtocolDeclaration.from_dict(payload["declaration"])
            if d.declaration_id != record_id:
                raise WorldRefused("the recorded declaration is not the one it is filed under")
            return str(d.revision), d.digest
        if kind is K.UNIT_REGISTRY:
            fingerprint = payload["fingerprint"]
            return fingerprint[:16], fingerprint
        if kind is K.SYSTEM_STATE:
            state = SystemState.from_dict(payload["state"])
            if state.request_digest != owner_id:
                raise WorldRefused("the recorded state is another run's than the owner it is filed under")
            owner, variable = record_parts(record_id, 2) or ("", "")
            found = [v for v in state.owner(owner).values if v.variable_id == variable]
            if len(found) != 1 or found[0].value.to_dict() != payload["value"] or \
                    found[0].uncertainty.to_dict() != payload["uncertainty"]:
                raise WorldRefused("the recorded value is not the recorded state's")
            return str(state.sequence), state.digest
        if kind is K.MODEL_RECORD:
            model = ScientificModelDefinition.from_dict(payload["model"])
            if (model.model_id, model.version) != record_parts(record_id, 2):
                raise WorldRefused("the recorded model is not the (model, version) it is filed under")
            return model.version, _sha_json(model)
        if kind is K.PROVIDER_STATUS:
            status = payload["status"]
            if status["capability"]["provider_id"] != record_id:
                raise WorldRefused("the recorded status is another provider's")
            digest_ = content_digest({k: v for k, v in status.items() if k != "location"})
            if payload["report"].get("status_digest") != digest_:
                raise WorldRefused("the recorded health report is for another status")
            rebuilt = _provider_status(status)       # the owner's constructors over the recorded fields...
            if rebuilt.to_dict() != dict(status):     # ...which must give back exactly the recorded status
                raise WorldRefused("the recorded provider status does not rebuild through the owner's constructors")
            if assess_health(rebuilt).to_dict() != dict(payload["report"]):    # the owner's own rule
                raise WorldRefused("the recorded health report is not what the owner's assessment gives")
            return status.get("version") or "-", digest_
        if kind is K.BUDGET_LEDGER:
            rebuilt = BudgetLedger.from_dict(payload["ledger"])             # a valid ledger record whose derived
            if _as_float(rebuilt.to_dict()) != _as_float(payload["ledger"]):   # totals are the owner's own
                raise WorldRefused("the recorded ledger's derived totals are not what its charges give")
            return str(len(payload["ledger"]["charges"])), canonical_digest(payload["ledger"])   # the owner's rule
        if kind is K.EXPERIMENT:
            exp = ScientificExperiment.from_dict(payload["experiment"])
            full = exp.to_dict()
            if full["budget"] != payload["budget"] or full["accounting"] != payload["accounting"]:
                raise WorldRefused("the recorded accounting is not the recorded experiment's")
            return str(len(exp.evaluations)), _sha_json(exp)
    except (KeyError, TypeError, ValueError, AttributeError, ScientificCoreError) as exc:
        raise WorldRefused(f"a recorded {kind.value} payload cannot re-derive its owner identity: {exc}") from None
    raise WorldRefused(f"no identity rule for {kind.value}")


def _provider_status(status: Mapping[str, Any]) -> ProviderStatus:
    """A recorded ``ProviderStatus.to_dict()`` handed back to the provider owner's own constructors (the owner exposes
    no loader; the caller checks that ``to_dict`` gives the recorded payload back exactly, so no field is reinterpreted)."""
    cap = {k: v for k, v in dict(status["capability"]).items() if k != "classification"}
    for name in ("physics", "dimensions", "time_modes", "output_ranks", "property_forms", "dependencies"):
        cap[name] = tuple(cap.get(name, ()))
    return ProviderStatus(ProviderCapability(**cap), Availability(status["availability"]), status["version"],
                          status["digest"], status["location"], status["reason"],
                          tuple(tuple(d) for d in status["dependencies"]), status["executable_digest"])


def _as_float(node: Any) -> Any:
    """Numbers compared as the owner's from_dict reads them (an int and the equal float are one amount)."""
    if isinstance(node, bool) or node is None or isinstance(node, str):
        return node
    if isinstance(node, (int, float)):
        return float(node)
    if isinstance(node, Mapping):
        return {k: _as_float(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_as_float(v) for v in node]
    return node


class FrozenReader(_Reader):
    """Answers exactly the reads recorded in a snapshot: what the owners stated then, not what they state now.  Each
    record is accepted only if its payload re-derives the recorded revision and digest by the owner's rule."""

    live = False

    def __init__(self, kind: OwnerKind, owner_id: str, records: Mapping[str, tuple[OwnerRecord, frozenset[str] | None]],
                 unavailable: str = "", refused: Mapping[str, tuple[str, str]] | None = None) -> None:
        self.kinds = frozenset({OwnerKind(kind)})
        self.owner_id = owner_id
        self._unavailable = unavailable
        self._refused = dict(refused or {})
        for record_id, (record, _) in records.items():
            if record.owner_kind is not OwnerKind(kind) or record.owner_id != owner_id or record.record_id != record_id:
                raise WorldRefused(f"snapshot record {record_id!r} is not a {OwnerKind(kind).value} record of {owner_id!r}")
            if rederive(record.owner_kind, record.owner_id, record_id, record.payload) != (record.revision,
                                                                                          record.record_digest):
                raise WorldRefused(f"snapshot record {record_id!r}: its payload does not re-derive the recorded "
                                   f"{record.owner_kind.value} revision and digest (the owner's rule refutes it)")
        self._records = dict(records)

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if self._unavailable:
            raise OwnerUnavailable(self._unavailable)
        if record_id in self._refused:                   # a read the owner refused then is refused again
            cls, why = self._refused[record_id]
            raise (OwnerUnavailable if cls == "OwnerUnavailable" else WorldRefused)(why)
        found = self._records.get(record_id)
        return None if found is None or OwnerKind(kind) not in self.kinds else found[0]

    def superseded(self, kind: OwnerKind, record_id: str) -> frozenset[str] | None:
        found = self._records.get(record_id)
        return None if found is None else found[1]


def frozen_readers(snapshot: Mapping[str, Any]) -> tuple[FrozenReader, ...]:
    by_kind: dict[OwnerKind, dict[str, tuple[OwnerRecord, frozenset[str] | None]]] = {}
    owners = {OwnerKind(k): o for k, o in snapshot["owners"]}
    unavailable = {OwnerKind(k): why for k, why in snapshot.get("unavailable", ())}
    refused: dict[OwnerKind, dict[str, tuple[str, str]]] = {}
    for k, record_id, cls, why in snapshot.get("refused", ()):
        refused.setdefault(OwnerKind(k), {})[record_id] = (cls, why)
    for item in snapshot["records"]:
        r = item["record"]
        record = OwnerRecord(OwnerKind(r["owner_kind"]), r["owner_id"], r["record_id"], r["revision"],
                             r["record_digest"], r["payload"])
        history = None if item["superseded"] is None else frozenset(item["superseded"])
        by_kind.setdefault(record.owner_kind, {})[record.record_id] = (record, history)
    return tuple(FrozenReader(kind, owner_id, by_kind.get(kind, {}), unavailable.get(kind, ""), refused.get(kind))
                 for kind, owner_id in sorted(owners.items(), key=lambda kv: kv[0].value))


#: The readers whose liveness is derived from their own type and mode (``Authorities.live``); any other object is not
#: a live owner reader, whatever it says about itself.
LIVE_READER_TYPES = (RunStateReader, ModelRegistryReader, ProviderRegistryReader, BudgetReader, DeclarationReader,
                     UnitRegistryReader)


def is_live(reader: Any) -> bool:
    """Whether ``reader`` reads its owner as it is now (derived; see LIVENESS)."""
    return type(reader) in LIVE_READER_TYPES and reader.live is True


__all__ = [
    "BudgetReader", "DeclarationReader", "FrozenReader", "LIVE_READER_TYPES", "ModelRegistryReader",
    "ProviderRegistryReader", "RunStateReader", "UNIT_RECORD", "UnitRegistryReader", "frozen_readers", "is_live",
    "record_key", "record_parts", "rederive",
]
