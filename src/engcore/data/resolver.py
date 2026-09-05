"""Resolution — turning a scientific data identity back into values.

The resolver is the one place where integrity is decided. Stores hand back
bytes without an opinion; the resolver decides whether those bytes are the data
that was asked for, and refuses to return anything else.

Three outcomes, and no fourth:

* the bytes match the reference  → the values,
* no consulted store has them    → :class:`BulkDataUnavailable`,
* a store has bytes that are not them → :class:`BulkDataIntegrityError`.

There is deliberately no "best effort" path. Fabricating an empty array, a
zero-filled array or a nearest-match would let a scientific pipeline continue
past the point where it stopped knowing what it was computing. Data that was
genuinely stored empty and verifies is a real answer and is returned as one.
"""

from __future__ import annotations

from ..scientific.results.data_reference import (
    FLOAT64,
    ScientificDataReference,
    content_digest,
    decode_float64,
)
from .errors import BulkDataIntegrityError, BulkDataUnavailable
from .store import BulkDataStore


class BulkDataResolver:
    """Resolves references against an ordered list of stores.

    The order is a runtime policy — try the fast local store, then the shared
    one — and it is deliberately invisible to the scientific layer: whichever
    store *verifies*, the values and the reference are the same, so a result
    never depends on which one did.

    One deliberate exception to that invisibility: the **first** store holding
    a reference is the one that must satisfy it. If a near cache has rotted,
    resolution fails rather than quietly reading past it to an intact archive.
    Routing around corruption would keep a failing store invisible for as long
    as a good copy existed somewhere, which is how silent data loss becomes
    permanent. A caller that wants the archive asks the archive.
    """

    def __init__(self, *stores: BulkDataStore) -> None:
        if not stores:
            raise ValueError("a resolver needs at least one store")
        self._stores: tuple[BulkDataStore, ...] = tuple(stores)

    def locate(self, reference: ScientificDataReference) -> BulkDataStore | None:
        """First store holding the reference, or ``None``."""
        for store in self._stores:
            if store.has(reference):
                return store
        return None

    def read_bytes(self, reference: ScientificDataReference) -> bytes:
        """Verified bytes for ``reference``.

        Verification is length-then-digest. The length check is not redundant
        with the digest: it distinguishes a truncated write from a substituted
        one in the error message, and it costs nothing.
        """
        store = self.locate(reference)
        if store is None:
            raise BulkDataUnavailable(
                f"no store holds {reference.name!r} "
                f"({reference.digest[:12]}…); consulted "
                f"{[s.name for s in self._stores]}. The scalar values of "
                f"any result "
                f"referencing it remain valid and unaffected"
            )
        payload = store.read(reference)
        if len(payload) != reference.byte_length:
            raise BulkDataIntegrityError(
                f"{reference.name!r} in store {store.name!r} has "
                f"{len(payload)} bytes; the reference declares "
                f"{reference.byte_length} ({reference.count} "
                f"{reference.dtype} values). The stored artifact is truncated "
                f"or is different data"
            )
        found = content_digest(payload, dtype=reference.dtype)
        if found != reference.digest:
            raise BulkDataIntegrityError(
                f"{reference.name!r} in store {store.name!r} hashes to "
                f"{found[:12]}… but the reference declares "
                f"{reference.digest[:12]}…; the stored artifact has been "
                f"modified or substituted"
            )
        return payload

    def resolve(self, reference: ScientificDataReference) -> tuple[float, ...]:
        """Verified values for ``reference``.

        The dtype check is not ceremony: ``dtype`` is a closed set today and
        will widen, and a decoder chosen by assumption rather than by the
        reference would misread the first non-float64 artifact silently.
        """
        if reference.dtype != FLOAT64:
            raise BulkDataIntegrityError(
                f"{reference.name!r} declares dtype {reference.dtype!r}; this "
                f"resolver decodes {FLOAT64!r} only"
            )
        return decode_float64(self.read_bytes(reference))


def relocate(
    reference: ScientificDataReference,
    source: BulkDataStore,
    destination: BulkDataStore,
    *,
    remove_source: bool = False,
) -> ScientificDataReference:
    """Copy (or move) referenced data from one store to another.

    Returns the reference — **unchanged**, and that is the assertion this
    function exists to make legible. Nothing about the scientific identity of
    bulk data is a function of where it sits, so re-homing it is a data-plane
    operation with no scientific consequence and no record to update.

    The copy is verified on read through a resolver over ``source``, so a
    relocation cannot launder corrupt bytes into a new home — and, when
    ``remove_source`` is set, it is verified again *at the destination* before
    the source copy is dropped. This is the only operation in the data plane
    that can leave zero copies, so it is the one that must not take the write
    on trust.

    **Ownership warning.** Blobs are keyed by content, so two results that
    computed identical data share one. ``remove_source=True`` therefore removes
    that data for *every* reference to it, not only this one. There is no
    retention or ownership subsystem here and none is implied; a caller that
    does not know it holds the last reference should copy rather than move.
    """
    payload = BulkDataResolver(source).read_bytes(reference)
    destination.put(reference, payload)
    if remove_source:
        # Read back through a resolver: a failed or partial write must not be
        # discovered after the only other copy is gone.
        BulkDataResolver(destination).read_bytes(reference)
        source.delete(reference)
    return reference
