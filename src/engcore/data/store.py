"""Bulk data stores — labelled bytes in, labelled bytes out.

A store is deliberately stupid. It does not verify content, does not interpret
units, does not know what a field is, and does not know which
`ScientificResult` (if any) refers to what it holds. It maps a **content
digest** to bytes.

Why keyed by digest rather than by logical name
-----------------------------------------------
Content addressing here is not an aspiration toward a storage platform; it is
the smallest mechanism that makes the milestone's invariant checkable. Two
consequences follow directly and are both wanted:

* moving a blob between stores cannot change its key, so relocation cannot
  change the reference — which is the whole claim under test;
* several results that computed identical data share one stored blob without
  any de-duplication machinery, and a store cannot silently return one
  result's array for another's request.

No lifetime, retention, replication, locking or garbage collection is
implemented. Those are real problems and they are out of scope; see the
DATA-BOUNDARY0 preregistration's non-goals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, Sequence

from ..scientific.results.data_reference import (
    ScientificDataReference,
    encode_float64,
)
from .errors import BulkDataUnavailable


class BulkDataStore(Protocol):
    """What every storage backend must provide.

    Four operations and no more. Anything richer belongs to a backend, not to
    the contract every backend has to satisfy.
    """

    @property
    def name(self) -> str:
        """A human label for diagnostics.

        **Runtime identity only.** It appears in error messages so an operator
        knows which places were consulted; it never reaches a scientific
        record, and a reference does not carry it.
        """
        ...

    def put(self, reference: ScientificDataReference, payload: bytes) -> None: ...

    def has(self, reference: ScientificDataReference) -> bool: ...

    def read(self, reference: ScientificDataReference) -> bytes:
        """Raw stored bytes.

        Raises :class:`BulkDataUnavailable` when absent. Verification is
        deliberately **not** done here — it belongs to the resolver, so there is
        exactly one place where integrity is decided and a new backend cannot
        forget to check.
        """
        ...

    def delete(self, reference: ScientificDataReference) -> None: ...


class InMemoryBulkStore:
    """Process-local bytes. Backend A.

    The natural home for data produced by a solve whose consumer is in the
    same process — which is what every current Crafty consumer is.
    """

    def __init__(self, name: str = "memory") -> None:
        self._name = str(name)
        self._blobs: dict[str, bytes] = {}

    @property
    def name(self) -> str:
        return self._name

    def put(self, reference: ScientificDataReference, payload: bytes) -> None:
        self._blobs[reference.digest] = bytes(payload)

    def has(self, reference: ScientificDataReference) -> bool:
        return reference.digest in self._blobs

    def read(self, reference: ScientificDataReference) -> bytes:
        try:
            return self._blobs[reference.digest]
        except KeyError:
            raise BulkDataUnavailable(
                f"{reference.name!r} ({reference.digest[:12]}…) is not held by "
                f"store {self._name!r}"
            ) from None

    def delete(self, reference: ScientificDataReference) -> None:
        self._blobs.pop(reference.digest, None)

    # ---- test/inspection affordances ------------------------------------
    def __len__(self) -> int:
        """Number of distinct blobs held. Content-keyed, so this is the
        de-duplicated count: two results with identical data show one."""
        return len(self._blobs)

    def corrupt(self, reference: ScientificDataReference, payload: bytes) -> None:
        """Overwrite a blob's bytes without changing its key.

        Present so that substitution can be exercised deliberately. ``put``
        cannot express it: ``put`` keys by the digest of what the caller
        claims, so writing wrong bytes under a right key has to be an explicit
        act, which is exactly what an attacker or a failing disk performs.
        """
        self._blobs[reference.digest] = bytes(payload)


class FilesystemBulkStore:
    """One file per blob under a root directory. Backend B.

    The root is a location. It lives here and only here: it is passed to the
    constructor, it is never recorded in a reference, and it never travels in a
    scientific record. Two stores rooted at different directories holding the
    same blob are indistinguishable to the scientific layer, which is the
    point.
    """

    SUFFIX = ".bulk"

    def __init__(self, root: str | Path, name: str = "filesystem") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._name = str(name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def root(self) -> Path:
        """The directory in use. A runtime fact; deliberately not identity."""
        return self._root

    def _path(self, reference: ScientificDataReference) -> Path:
        return self._root / f"{reference.digest}{self.SUFFIX}"

    def put(self, reference: ScientificDataReference, payload: bytes) -> None:
        self._path(reference).write_bytes(payload)

    def has(self, reference: ScientificDataReference) -> bool:
        return self._path(reference).is_file()

    def read(self, reference: ScientificDataReference) -> bytes:
        path = self._path(reference)
        if not path.is_file():
            raise BulkDataUnavailable(
                f"{reference.name!r} ({reference.digest[:12]}…) is not held by "
                f"store {self._name!r}"
            )
        return path.read_bytes()

    def delete(self, reference: ScientificDataReference) -> None:
        self._path(reference).unlink(missing_ok=True)


def store_values(
    store: BulkDataStore,
    name: str,
    values: Iterable[float] | Sequence[float],
    *,
    unit: str,
) -> ScientificDataReference:
    """Encode ``values``, hand the bytes to ``store``, return their identity.

    The single sanctioned way bulk data enters the data plane. The returned
    reference is a function of the values and their scientific labels alone —
    swap ``store`` for a different backend and the reference is identical.
    """
    reference, payload = ScientificDataReference.for_values(
        name, values, unit=unit
    )
    store.put(reference, payload)
    return reference
