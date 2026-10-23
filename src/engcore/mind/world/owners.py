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
asserted by a caller; only live readers back a dispatch.  Liveness is the reader's MODE, not a proof of currency: a
following reader is as current as the callable the execution side hands it (a callable that returns a fixed record
is live by mode), a ``BudgetReader`` built over a mapping holds that mapping's id -> account objects (``following``
re-reads the mapping), and a ``ProviderRegistryReader`` reads the provider owner's cached status unless the execution
side chooses ``refresh=True``.  Which currency the execution side needs is its own policy; nothing here decides it.

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
import threading
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


class _Unreadable(OwnerUnavailable):
    """An account state its owner cannot write down and read back, the same way at every attempt (a property of the
    state handed over, not of the moment it was read): it cannot be ordered against what a following reader observed."""


class _NotRead:
    """Why one handed account was not read back, and whether that refuses it for good (``_Unreadable``)."""

    __slots__ = ("why", "for_good")

    def __init__(self, why: str, for_good: bool) -> None:
        self.why, self.for_good = why, for_good


class _Failed(Exception):
    """One read-back attempt that failed: why, and the text written before it failed (None if none was)."""

    def __init__(self, why: str, text_: str | None, moving: bool, recursion: bool) -> None:
        super().__init__(why)
        self.why, self.text, self.moving, self.recursion = why, text_, moving, recursion


_ATTEMPTS = 3                                         # read-backs of one handed account before it is classified
_MUTATION = ("changed size during iteration", "mutated during iteration", "changed during iteration")


def _moving(exc: BaseException) -> bool:
    """The interpreter's own signal that a container was mutated while it was iterated (exactly ``RuntimeError``)."""
    return type(exc) is RuntimeError and any(m in str(exc) for m in _MUTATION)


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
        self._lock = threading.Lock()                 # one desk serves concurrent admissions: check-and-advance is atomic

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
        with self._lock:
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
    ``sria.campaign`` does on restore); its constructor refuses an account set that is not exactly typed, names an
    account by anything but a str, or registers one object under two ids.  ``BudgetReader.following(accounts)`` asks
    the execution side's ``accounts()`` for the current ``(ledgers, experiments)`` at every verification, and every
    account only moves forward: its history (a ledger's settled charges, an experiment's recorded evaluations, in the
    form the owner reads them back, so a restore of an unchanged account is the same history) must extend the longest
    history this reader observed for it.  An account BEHIND that history (it went back, or this verification's
    snapshot is older than one already observed) is refused for as long as it is behind; an account that REWROTE its
    history (neither extends nor is a prefix of it) is refused by this reader from then on; adopting a new timeline is
    the execution side's statement, made with a new reader.  A change to an account's declaration with its history
    unchanged (a budget top-up) is a move of the owner.  Every account handed over is observed at construction and at
    every verification (``Authorities.memoized`` pins every reader when a verification starts, whichever world is
    verified: a proposer's world never chooses what is observed); an account is refused only to a verification that
    reads it, so an account no world reads refuses nothing.

    What a verification is handed is read entry by entry (one malformed entry never hides the others): an account is
    named by its str id (a str subclass is read as the plain str it spells; an entry under any other key is no account
    a world can bind, and is not read); an account that is not exactly its owner's type is refused for good; one
    object handed under two ids is observed under both and refused to that verification.  Each account is read back by
    its owner from the text its owner writes it down as: a ledger by ``BudgetLedger.from_dict`` from its digest rule's
    JSON (``canonical_digest``: sorted keys, ``default=str``), an experiment whole by ``ScientificExperiment.from_dict``
    from ``to_json`` (once per account and content), so the record served, its digest and its history are detached
    data a checkpoint restore of the same account reproduces; the record served is parsed from that text at every
    read.  A read-back is tried up to three times and its failure classified by what happens, not by the exception's
    type: any success is observed; three failures alike (the same failure on the same text) are the state itself, which
    its owner cannot write down and read back, and refuse the account from then on (that state cannot be ordered
    against what was observed, and it may hold a spend); failures that differ, or the interpreter's own "changed during
    iteration" error, are an account moving while it was serialized, refused to that verification only.

    Each verification is in flight from its start, through ``accounts()`` and the read-back (both with no lock held:
    no execution-side code runs under the reader's lock), to its comparison, which holds the lock.  Every observation
    that extends the history is recorded, and a verification decides on an account only once every other verification
    in flight when it compared has compared too, whichever started first: it waits for them (at most ``WAIT_S``,
    holding no lock; a compared verification never waits for another compared one), then decides on what is observed
    by then (an account another verification moved past is behind; one refused for good is refused).  A verification
    it waited for that was handed accounts and left without comparing (interrupted), or one still in flight after
    ``WAIT_S``, makes it decide on no account (refused to that verification only).  So a state handed to, and read back
    by, a verification is compared before any verification that was waiting on it decides, and a return to an earlier
    state never re-authorizes what such a state had moved past.  The cost: a verification whose ``accounts()`` or
    read-back does not complete within ``WAIT_S`` makes every verification that compares meanwhile wait ``WAIT_S`` and
    be refused, until it completes.  What is never observed: a state no verification was handed and read back (a spend
    and its rollback both between two verifications look like no change), a state that kept moving through three
    read-backs, an entry under a key that is not a str, the state of a verification whose ``accounts()`` raises or
    hands no pair of mappings, and one interrupted (``BaseException``) between being handed accounts and comparing
    them; at-most-once execution is the execution owner's.  An ``accounts()`` or read-back that reads through the
    reader it feeds on the same thread is refused at once (from inside the read-back, that refusal repeats, so the
    account is refused for good).  A pinned snapshot serves the records it observed and is never live."""

    kinds = frozenset({K.BUDGET_LEDGER, K.EXPERIMENT})
    WAIT_S = 1.0                                     # the most a compared verification waits for the others in flight

    @classmethod
    def following(cls, accounts: Callable[[], tuple[Mapping[str, Any], Mapping[str, Any]]],
                  owner_id: str = "budget") -> "BudgetReader":
        if not callable(accounts):
            raise WorldRefused("followed accounts are a callable the execution side answers with (ledgers, experiments)")
        reader = cls(*accounts(), owner_id=owner_id)
        reader._follow = accounts
        ticket = reader._ticket()
        try:
            reader._observe_all(reader, ticket)          # what is handed over at construction: the first baseline
        finally:
            reader._leave(ticket, False)
        return reader

    @property
    def live(self) -> bool:                          # derived from the mode: a pinned snapshot is never live (R7-D1)
        return self._observed is None

    @staticmethod
    def _history(items: Iterable[Any]) -> tuple[str, ...]:
        return tuple(hashlib.sha256(json.dumps(x.to_dict(), sort_keys=True, default=str).encode("utf-8")).hexdigest()
                     for x in items)

    def _read_once(self, key: tuple[str, str]) -> tuple[OwnerRecord, tuple[str, ...]]:
        """One read-back of one handed account: its record and history, both from ONE text its owner wrote, or
        ``_Failed`` with the text written before the failure (if any)."""
        kind, record_id = key
        text_: str | None = None
        try:
            if kind == "ledger":
                ledger = self._ledgers[record_id]
                # The owner's read-back (``from_dict``, which normalizes what it reads), written down by the owner's own
                # digest rule and read back again from that text.
                text_ = json.dumps(BudgetLedger.from_dict(ledger.to_dict()).to_dict(), sort_keys=True,
                                   separators=(",", ":"), default=str)
                back = BudgetLedger.from_dict(json.loads(text_))
                return (OwnerRecord(K.BUDGET_LEDGER, self.owner_id, record_id, str(back.revision), back.digest,
                                    {"ledger": back.to_dict()}), self._history(back.charges))
            exp = self._experiments[record_id]
            text_ = to_json(exp)
            content = hashlib.sha256(text_.encode("utf-8")).hexdigest()
            cached = self._readback.get(key)
            if cached is None or cached[0] != content:
                written = json.loads(text_)
                rebuilt = ScientificExperiment.from_dict(json.loads(text_))
                back_text = to_json(rebuilt)
                back = json.loads(back_text)
                if type(written) is not dict or back.get("accounting") != written.get("accounting") \
                        or back.get("budget") != written.get("budget"):
                    raise ValueError("its accounting is not its evaluations' (an account serialized while it moved, "
                                     "or one whose accounting its owner does not derive)")
                cached = (content, back_text, hashlib.sha256(back_text.encode("utf-8")).hexdigest(),
                          self._history(rebuilt.evaluations))
                self._readback[key] = cached
            _, back_text, digest_, history = cached
            back = json.loads(back_text)             # parsed from the owner's text at every read: never shared
            return (OwnerRecord(K.EXPERIMENT, self.owner_id, record_id, str(len(back["evaluations"])), digest_,
                                {"budget": back["budget"], "accounting": back["accounting"], "experiment": back}),
                    history)
        except Exception as exc:  # noqa: BLE001 - classified by the caller over several attempts
            raise _Failed(f"{type(exc).__name__}: {exc}", text_, _moving(exc), isinstance(exc, RecursionError)) \
                from None

    def _account(self, key: tuple[str, str]) -> tuple[OwnerRecord | None, tuple[str, ...]]:
        """One handed account read back by its owner: its record and history (any attempt that succeeds), or, after
        ``_ATTEMPTS`` failures, ``_Unreadable`` when they fail alike (the state itself) or ``OwnerUnavailable`` when
        they differ or the interpreter says the account was mutated while it was iterated (it moved)."""
        kind, record_id = key
        if record_id not in (self._ledgers if kind == "ledger" else self._experiments):
            return None, ()
        what = f"budget {kind} {record_id!r}"
        failures: list[_Failed] = []
        for _ in range(_ATTEMPTS):
            try:
                return self._read_once(key)
            except _Failed as failed:
                failures.append(failed)
        if all(f.recursion for f in failures):       # the state's depth, or this verification's caller's?
            try:
                return self._at_baseline_depth(key)
            except _Failed as failed:
                if failed.moving:
                    raise OwnerUnavailable(f"{what} moved while it was serialized: {failed.why}") from None
                raise _Unreadable(f"{what} is not one its owner writes down and reads back (it exceeds the "
                                  f"interpreter's recursion limit on a fresh thread too): {failed.why}") from None
        if any(f.moving for f in failures) or len({(f.why, f.text) for f in failures}) > 1:
            raise OwnerUnavailable(f"{what} moved while it was serialized ({_ATTEMPTS} read-backs failed "
                                   f"differently): {failures[-1].why}")
        raise _Unreadable(f"{what} is not one its owner writes down and reads back ({_ATTEMPTS} read-backs failed "
                          f"alike): {failures[-1].why}")

    def _at_baseline_depth(self, key: tuple[str, str]) -> tuple[OwnerRecord, tuple[str, ...]]:
        """The read-back once more on a fresh thread (a shallow stack), under the same-thread read-through flag:
        whether the state is too deep for its owner's rules, or only this verification's caller's stack was."""
        box: dict[str, Any] = {}

        def run() -> None:
            self._in_follow.active = True
            try:
                box["read"] = self._read_once(key)
            except _Failed as failed:
                box["failed"] = failed
            finally:
                self._in_follow.active = False

        thread = threading.Thread(target=run, name="budget-read-back", daemon=True)
        thread.start()
        thread.join()
        if "read" in box:
            return box["read"]
        raise box.get("failed") or _Failed("the read-back on a fresh thread did not complete", None, False, False)

    def _read_back(self) -> dict[tuple[str, str], tuple[OwnerRecord | None, tuple[str, ...]] | _NotRead]:
        """Every account handed over, read back now (no lock held): its record and history, or why it was not read.
        Total: no failure of one account's read-back leaves this method or hides another account."""
        out: dict[tuple[str, str], tuple[OwnerRecord | None, tuple[str, ...]] | _NotRead] = dict(self._entry_refusals)
        for key in [*(("ledger", i) for i in self._ledgers), *(("experiment", i) for i in self._experiments)]:
            if key in self._skip:                    # refused for good already: not read again
                out[key] = _NotRead("", True)
                continue
            try:
                out[key] = self._account(key)
            except _Unreadable as exc:
                out[key] = _NotRead(str(exc), True)
            except OwnerUnavailable as exc:
                out[key] = _NotRead(str(exc), False)
        return out

    def _observe_all(self, snapshot: "BudgetReader", ticket: int) -> dict[tuple[str, str], OwnerRecord | str | None]:
        """The following reader's forward-only rule over EVERY account handed over in ``snapshot``.  The read-back runs
        with no lock held (it runs the account objects' own serialization, into the snapshot's private cache); only
        the comparison holds the lock, and it runs no code of the accounts.  Every observation that extends the history
        is recorded; a handed account its owner cannot write down and read back refuses its account from then on.  A
        verification decides on an account only once every verification in flight when it compared has compared too,
        whichever started first: it waits for them (at most ``WAIT_S``, holding no lock; a compared verification never
        waits for another compared one, so no two wait for each other), then decides on what is observed by then (an
        account another verification moved past is behind; one refused for good is refused).  If one of them was still
        in flight after the wait, or was handed accounts and left without comparing, it decides on no account (refused
        for that verification only)."""
        read = snapshot._read_back()
        observed: dict[tuple[str, str], OwnerRecord | str | None] = {}
        accepted: dict[tuple[str, str], tuple[str, ...]] = {}
        with self._changed:
            self._in_flight.discard(ticket)
            self._changed.notify_all()
            pending = set(self._in_flight)
            self._readback = {k: v for k, v in snapshot._readback.items() if k in read}   # the accounts handed now
            for key, got in read.items():
                if key in self._diverged:
                    observed[key] = self._diverged[key]
                    continue
                if type(got) is _NotRead:
                    if got.for_good:
                        self._diverged[key] = (f"{got.why}; the account was handed over in that state, which cannot "
                                               "be ordered against the history this reader observed (it may hold a "
                                               "spend): refused by this reader from then on (a new timeline is stated "
                                               "with a new reader)")
                        observed[key] = self._diverged[key]
                    else:
                        observed[key] = got.why
                    continue
                record, history = got
                if record is None:
                    observed[key] = None
                    continue
                seen = self._seen.get(key, ())
                if history[:len(seen)] != seen and seen[:len(history)] != history:
                    self._diverged[key] = (f"budget {key[0]} {key[1]!r} rewrote its history (it neither extends nor is "
                                           "a prefix of the history this reader observed): refused by this reader from "
                                           "then on (a new timeline is stated with a new reader)")
                    observed[key] = self._diverged[key]
                elif len(history) < len(seen):
                    observed[key] = self._behind(key)
                else:
                    self._seen[key] = history
                    if key in snapshot._aliased:
                        observed[key] = (f"budget {key[0]} {key[1]!r} was handed over as one account object under "
                                         "two ids (one account stating two accounts): observed, but refused for this "
                                         "verification")
                    else:
                        observed[key] = record
                        accepted[key] = history
            if pending and accepted:
                waiter = [pending, False]            # [the tickets waited for, one of them left without comparing]
                self._waiters[ticket] = waiter
                try:
                    done = self._changed.wait_for(lambda: waiter[1] or not pending & self._in_flight,
                                                  timeout=self.WAIT_S)
                finally:
                    del self._waiters[ticket]
                if not done or waiter[1]:
                    why = ("was handed accounts and left without comparing them" if waiter[1] else
                           f"was still in flight {self.WAIT_S} s after this one compared")
                    waiting = (f"another verification of this budget reader {why} (it may hold a later state of the "
                               "accounts, whichever verification started first): this verification decides on no "
                               "account; refused for this verification only")
                    return {k: (waiting if k in accepted else v) for k, v in observed.items()}
                for key, history in accepted.items():   # decided on what is observed once those have compared
                    if key in self._diverged:
                        observed[key] = self._diverged[key]
                    elif len(self._seen.get(key, ())) > len(history):
                        observed[key] = self._behind(key)
        return observed

    @staticmethod
    def _behind(key: tuple[str, str]) -> str:
        return (f"budget {key[0]} {key[1]!r} is behind the history this reader observed (it went back a revision, or "
                "this verification's snapshot is older than one already observed): refused while it is behind")

    def _leave(self, ticket: int, handed: bool) -> None:
        """``ticket`` is no longer in flight.  One that was handed accounts and never compared them makes every
        verification waiting for it decide on no account."""
        with self._changed:
            if handed and ticket in self._in_flight:
                for waiter in self._waiters.values():
                    if ticket in waiter[0]:
                        waiter[1] = True
            self._in_flight.discard(ticket)
            self._changed.notify_all()

    def _ticket(self) -> int:
        with self._lock:
            self._tickets += 1
            self._in_flight.add(self._tickets)
            return self._tickets

    @classmethod
    def _handed(cls, handed: Any, owner_id: str, skip: frozenset[tuple[str, str]]) -> "BudgetReader":
        """What one ``accounts()`` call handed over, entry by entry: an entry that is not an account never hides one
        that is (see the class docstring)."""
        ledgers, experiments = handed
        snapshot = cls(owner_id=owner_id)
        objects: dict[int, list[tuple[str, str]]] = {}
        for kind, mapping, owner_type, store in (("ledger", ledgers, BudgetLedger, snapshot._ledgers),
                                                 ("experiment", experiments, ScientificExperiment,
                                                  snapshot._experiments)):
            for raw_id, account in dict(mapping or {}).items():
                if not issubclass(type(raw_id), str):
                    continue                         # no world binds an account by a key that is not a str
                key = (kind, str.__str__(raw_id))    # the plain str it spells (no code of the id runs)
                if type(account) is not owner_type:
                    snapshot._entry_refusals[key] = _NotRead(f"budget {kind} {key[1]!r} is not exactly a "
                                                             f"{owner_type.__name__}", True)
                    continue
                store[key[1]] = account
                objects.setdefault(id(account), []).append(key)
        snapshot._aliased = frozenset(k for keys in objects.values() if len(keys) > 1 for k in keys)
        snapshot._skip = skip
        return snapshot

    def pinned(self) -> "BudgetReader":
        """One verification's snapshot: the accounts the execution side hands over now (asked with no lock held), read
        back and compared with what this reader observed under its lock, and served only as observed (records taken at
        the pin; the next verification observes any later move).  Never live."""
        if self._follow is None:
            return self
        if getattr(self._in_follow, "active", False):
            raise OwnerUnavailable("the execution side read through the budget reader it feeds while the reader was "
                                   "asking for, or reading back, the accounts it would read (on this thread)")
        ticket, handed = 0, False
        try:
            self._in_follow.active = True
            with self._lock:                         # the ticket is named before it is in flight: a finally that
                self._tickets += 1                   # runs at any point discards exactly what was taken
                ticket = self._tickets
                self._in_flight.add(ticket)
                skip = frozenset(self._diverged)
            try:
                mapping = self._follow()
            except Exception as exc:  # noqa: BLE001 - an owner that cannot state its accounts is unavailable
                raise OwnerUnavailable(f"the execution side could not state its budget accounts: {exc}") from None
            handed = True
            try:
                current = BudgetReader._handed(mapping, self.owner_id, skip)
            except Exception as exc:  # noqa: BLE001 - what was handed is not a pair of account mappings
                raise OwnerUnavailable(f"the execution side handed over no pair of account mappings: {exc}") from None
            current._readback = dict(self._readback)     # a private copy: no other verification writes into it
            current._in_follow = self._in_follow         # its read-back runs under this reader's read-through flag
            current._observed = self._observe_all(current, ticket)
            return current
        finally:
            self._in_follow.active = False
            try:
                self._leave(ticket, handed)
            finally:
                self._in_flight.discard(ticket)      # (atomic): never left in flight if the lock wait is interrupted

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        if self._follow is not None:
            return self.pinned().read(kind, record_id)
        return self._read(kind, record_id)

    def __init__(self, ledgers: Mapping[str, BudgetLedger] | None = None,
                 experiments: Mapping[str, ScientificExperiment] | None = None, owner_id: str = "budget") -> None:
        self._follow: Callable[[], Any] | None = None
        self._observed: dict[tuple[str, str], OwnerRecord | str | None] | None = None   # a pinned snapshot's records
        self._seen: dict[tuple[str, str], tuple[str, ...]] = {}
        self._diverged: dict[tuple[str, str], str] = {}   # account -> why it is refused by this reader for good
        self._readback: dict[tuple[str, str], tuple[Any, ...]] = {}   # account -> (content digest, read-back text,
        # its digest, its history): one entry per account, so the cache never outgrows the accounts' current state
        self._entry_refusals: dict[tuple[str, str], _NotRead] = {}   # a snapshot's handed entries that are no account
        self._aliased: frozenset[tuple[str, str]] = frozenset()     # a snapshot's ids handed for one object
        self._skip: frozenset[tuple[str, str]] = frozenset()        # accounts refused for good when the pin started
        self._in_follow = threading.local()          # set while this reader's accounts() or read-back runs on a thread
        self._tickets = 0                            # verifications of this reader, numbered when they start
        self._in_flight: set[int] = set()
        self._waiters: dict[int, list[Any]] = {}     # a waiting ticket -> [the tickets it waits for, one left uncompared]
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)   # a verification left the in-flight set
        raw = [dict(ledgers or {}), dict(experiments or {})]
        if any(not issubclass(type(i), str) for m in raw for i in m):
            raise WorldRefused("a budget account id is a str")
        self._ledgers = {str.__str__(i): x for i, x in raw[0].items()}
        self._experiments = {str.__str__(i): x for i, x in raw[1].items()}
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
        if kind not in self.kinds:
            return None
        key = ("ledger" if kind is K.BUDGET_LEDGER else "experiment", record_id)
        if self._observed is None:
            return self._account(key)[0]
        observed = self._observed.get(key)
        if isinstance(observed, str):
            raise OwnerUnavailable(observed)
        return observed


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
        self._lock = threading.Lock()

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
        held = [(k, current._held[k[0]]) for k in current._seen]
        with self._lock:                             # check everything, then advance: atomic per verification
            for key, d in held:
                if self._seen.get(key, d.digest) != d.digest:
                    raise OwnerUnavailable(f"declaration {key[0]!r} revision {key[1]} is restated with other content "
                                           "(a revision names one content; a change is a new revision)")
                if d.revision < self._latest.get(key[0], d.revision):
                    raise OwnerUnavailable(f"declaration {key[0]!r} went back from revision {self._latest[key[0]]} "
                                           f"to {d.revision} (revisions only move forward)")
            for key, d in held:
                self._seen.setdefault(key, d.digest)
                self._latest[key[0]] = max(self._latest.get(key[0], d.revision), d.revision)
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
            return str(len(payload["ledger"]["charges"])), canonical_digest(rebuilt.to_dict())   # the owner's rule
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
