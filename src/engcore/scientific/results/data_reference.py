"""Scientific data identity — *which* bulk data a result means.

A `ScientificResult` is a small interpreted record. A solved field is not:
one CFD state is O(mesh) and a scientific record that carried it inline would
stop being readable, stop being diffable, stop being hashable at sane cost,
and would drag the whole array through every provenance and evidence payload
that ever quotes the result.

The record therefore names its bulk data instead of containing it, and the
name is **content identity, never location**:

    Scientific control plane      ScientificResult          no storage knowledge
            | references
    Scientific data identity      ScientificDataReference   this module
            | resolved by
    Runtime / storage plane       engcore.data              locations live here

Why identity is not location
----------------------------
A scientific result is a claim about nature. Where its bytes happen to sit —
a temp directory, a shared filesystem, object storage, device memory, another
machine — is an execution fact, and an execution fact must not be able to
change what a result *means*. If a path were part of the identity, then moving
a file would silently mint a different scientific record, and a provenance
chain would rot the first time storage was reorganized. That failure mode is
not hypothetical: it is what artifact-URI-in-the-record systems spend migration
tooling on.

So the reference carries a **digest of the content** and nothing that could
locate it. Two references are equal exactly when they name the same bytes under
the same scientific label — regardless of which backend, host, process or
directory holds those bytes.

What the digest proves, and what it does not
--------------------------------------------
The digest is a statement about **bytes**, and only about bytes. It gives:

* **content identity** — this reference names *these* values and no others;
* **integrity** — corruption, truncation or substitution is detected;
* **relocation stability** — moving the bytes cannot change the reference;
* **content addressing** — identical byte images share one stored blob.

It does **not** prove scientific equivalence, and no claim in this package
should be read as saying it does:

* Equal digests imply byte-identical data, which is *stronger* than scientific
  equality — but two computations that are scientifically equivalent to within
  tolerance will in general produce **different** digests. Different hardware,
  compiler, BLAS, thread count, reduction order, vectorization or library
  version routinely change the last bits of a floating-point result while
  changing nothing a scientist would call the answer. A digest mismatch is
  therefore evidence that the *bytes* differ; it is not evidence that the
  science differs.
* Conversely a digest match says the byte images agree; it says nothing about
  whether either computation was correct, converged, or physically meaningful.
  Those questions belong to validation and to uncertainty, which are separate
  fields on the result and stay that way.

Tolerance-level comparison of two scientific datasets is a real and different
operation. This module does not implement it, does not approximate it, and
must not be cited as a substitute for it.

What this record deliberately does NOT carry
--------------------------------------------
* **No path, URI, host, device, provider or store identity.** That is the
  whole point; see above.
* **No mesh, topology, coordinate frame, tensor rank, conformity or field
  support.** DATA-BOUNDARY0 intentionally does not define ``FIELD0``/``TOPO0``
  descriptors; that vocabulary is deferred, not decided. Guessing it here
  would produce a free-form descriptor string — the untyped-semantics escape
  hatch this platform refuses. ``count`` below is a count of values and is
  *not* a shape.
* **No lifetime, retention or garbage-collection policy.** A reference states
  what data is meant; whether that data still exists is a question for a
  resolver, which answers it with a typed failure rather than a guess.
* **No values.** This module never holds bulk data. It computes a digest over
  it and forgets it.

What "same data" means, precisely
---------------------------------
Identity is over the **canonical byte image** defined below, not over IEEE
value equality. Two consequences follow and both are deliberate:

* ``-0.0`` and ``0.0`` are different preimages, as are distinct NaN payload bit
  patterns. Two arrays a mathematician would call equal can therefore carry two
  identities. The alternative — normalizing before hashing — would mean a
  digest no longer attests to the bytes a solver actually produced, which is
  the one thing it exists to do.
* Any future storage backend must be able to reproduce that exact image to
  verify a blob. A compressed or re-typed archive can hold the data, but it
  verifies by decoding to the canonical image, not in place.

Evolution
---------
DATA-BOUNDARY0 defines the minimum identity needed to prove its invariant. It
does not close the record against future work, and nothing here should be read
as a permanent law about what a data reference may become. Future shape,
support, frame and topology semantics remain deferred and undecided — whether
they arrive as fields here, as a sibling record, or as something neither, is a
question for the milestone that has the evidence to answer it.

One factual constraint that such a milestone will have to plan around, recorded
because it is a property of the current code rather than an opinion:
``require_schema`` is an exact string match with no migration path, so any
change to ``scientific_data_reference/1``'s version string makes stored results
containing a reference unloadable by the current reader. That constrains *how*
an evolution is rolled out; it does not forbid one. Widening the closed
``dtype`` or ``digest_algorithm`` sets is a value change, not a shape change,
and does not touch the schema at all.

Scope of the byte-identity guarantee
------------------------------------
``digest`` is unconditional: it is a function of the bytes alone and survives
any dependency change. The *serialized reference* is not quite: ``unit`` is
re-normalized through the units backend on every construction, so a change in
that backend's default unit spelling would change the reference's bytes. That
is an inherited property of the units contract, not something introduced here,
and it cannot affect resolution — the digest excludes the unit.

Relationship to the finiteness policy
-------------------------------------
``Quantity`` refuses NaN and +/-Inf, and that is unchanged: a reference is not
a quantity and carries no magnitudes. The digest is taken over bytes, so a
non-finite value a backend genuinely produced stays reportable and stays
detectable, exactly as ``RawSolverOutput`` already permits one layer down.
"""

from __future__ import annotations

import hashlib
import sys
from array import array
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..errors import ScientificCoreError
from ..serialization import require_schema, schema_string
from ..units.quantity import normalize_unit

DATA_REFERENCE_SCHEMA = schema_string("scientific_data_reference")

#: The one element encoding this milestone supports. A closed set, not a free
#: string: a caller cannot invent an encoding the resolver does not understand,
#: and a stored record cannot claim one.
FLOAT64 = "float64"
SUPPORTED_DTYPES = frozenset({FLOAT64})

#: Likewise closed. Widening it later is a deliberate contract change.
SHA256 = "sha256"
SUPPORTED_DIGEST_ALGORITHMS = frozenset({SHA256})

_BYTES_PER_ELEMENT = {FLOAT64: 8}

#: Domain-separation tag mixed into every digest preimage. It binds a digest to
#: *this* encoding, so a future dtype cannot produce a colliding digest for
#: different data, and so a Crafty digest is not confusable with a bare
#: SHA-256 of the same bytes taken elsewhere.
_DIGEST_TAG = b"crafty.scientific.bulk/1\x00"


def encode_float64(values: Iterable[float] | Sequence[float]) -> bytes:
    """Canonical little-endian IEEE-754 float64 bytes for a 1-D sequence.

    Canonical means byte-identical for *equal values* on every platform, which
    is what makes a content digest a portable identity rather than a local one.
    A big-endian host byteswaps; it does not get its own digest space. This is
    a property of the encoding only: it does not imply that two machines
    computing the same physics produce equal values in the first place.

    Buffer-exposing sequences (``array('d')``, a C-contiguous NumPy float64
    array) are read through ``memoryview`` without a Python-level loop. This
    module still imports no array library: it asks the object for a buffer and
    checks the format, which any conforming producer answers.

    An object that *does* expose a buffer but not a 1-D contiguous ``float64``
    one is **refused**, not quietly converted. Falling back to a per-element
    ``float()`` loop there would upcast a float32 or complex device array in
    silence, and the resulting digest would attest to data the solver never
    computed. Plain Python sequences expose no buffer at all and are converted,
    which is unambiguous.
    """
    raw: bytes | None = None
    try:
        view = memoryview(values)  # type: ignore[arg-type]
    except TypeError:
        view = None
    if view is not None:
        try:
            if view.ndim == 1 and view.format == "d" and view.c_contiguous:
                raw = view.tobytes()
            else:
                raise ScientificCoreError(
                    f"cannot encode a buffer of format {view.format!r}, "
                    f"{view.ndim} dimension(s), contiguous="
                    f"{view.c_contiguous}: bulk scientific data is 1-D "
                    f"contiguous float64. Converting it here would make the "
                    f"digest attest to data the producer did not compute"
                )
        finally:
            view.release()
    if raw is None:
        raw = array("d", (float(v) for v in values)).tobytes()

    if sys.byteorder != "little":  # pragma: no cover - little-endian CI
        buffer = array("d")
        buffer.frombytes(raw)
        buffer.byteswap()
        raw = buffer.tobytes()
    return raw


def decode_float64(payload: bytes) -> tuple[float, ...]:
    """Inverse of :func:`encode_float64`."""
    if len(payload) % 8:
        raise ScientificCoreError(
            f"float64 payload of {len(payload)} bytes is not a whole number "
            f"of elements"
        )
    buffer = array("d")
    buffer.frombytes(payload)
    if sys.byteorder != "little":  # pragma: no cover - little-endian CI
        buffer.byteswap()
    return tuple(buffer)


def content_digest(payload: bytes, *, dtype: str = FLOAT64) -> str:
    """SHA-256 over the canonical bytes, domain-separated by dtype.

    Deliberately a function of the **values alone** — not of the logical name,
    not of the unit, and certainly not of any location. Two results whose
    encoded arrays are byte-identical share one digest and can therefore share
    one stored blob, which is the behaviour wanted when several results
    reference the same artifact. The scientific labels live on the reference,
    where they belong.

    This is byte identity, not scientific equivalence; see the module
    docstring. Two runs that agree to within tolerance normally hash
    differently, and that is not a defect.
    """
    if dtype not in SUPPORTED_DTYPES:
        raise ScientificCoreError(
            f"unsupported bulk dtype {dtype!r}; supported: "
            f"{sorted(SUPPORTED_DTYPES)}"
        )
    digest = hashlib.sha256()
    digest.update(_DIGEST_TAG)
    digest.update(dtype.encode("ascii"))
    digest.update(b"\x00")
    digest.update(payload)
    return digest.hexdigest()


@dataclass(frozen=True)
class ScientificDataReference:
    """Storage-independent identity of one bulk scientific array.

    Immutable, hashable, serializable, and O(1) in the size of the data it
    names. Equality is over every field below — and every field below is a
    scientific or content fact, so equality is a scientific question and never
    a storage one.
    """

    #: Logical role within the producing result, namespaced like a metric
    #: (``"u:field"``). This is what a consumer asks for.
    #:
    #: Deliberately **unconstrained in shape**. Scientific names carry
    #: punctuation for scientific reasons — ``phase/alpha``, ``velocity/x``,
    #: ``species:H2O`` — and rejecting them on the suspicion that they resemble
    #: a path would make a storage concern dictate scientific vocabulary. There
    #: is no storage field on this record for a name to be confused with, so
    #: there is nothing for a shape heuristic to protect.
    name: str
    #: Unit carried by every element. ``"dimensionless"`` must be stated
    #: explicitly, exactly as ``Quantity`` requires — a bare array of numbers
    #: is not a scientific object.
    unit: str
    #: Number of values. **Not a shape, mesh, topology or field support.**
    #: May be zero: DATA-BOUNDARY0 has no evidence that an empty scientific
    #: dataset is invalid, and no storage invariant here requires otherwise.
    #: Note the consequence — every empty payload of a given dtype has the same
    #: digest, so one empty blob satisfies every empty reference. A consumer
    #: for which an empty dataset is a domain error should say so itself.
    count: int
    #: Element encoding. Closed set; see :data:`SUPPORTED_DTYPES`.
    dtype: str = FLOAT64
    #: Hex digest over the canonical bytes. See :func:`content_digest`.
    digest: str = ""
    digest_algorithm: str = SHA256

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ScientificCoreError(
                "scientific data reference requires a non-empty name"
            )
        object.__setattr__(self, "name", name)

        # Normalizing through the units contract means `m` and `meter` cannot
        # produce two references that claim to be different scientific things.
        object.__setattr__(self, "unit", normalize_unit(self.unit))

        count = int(self.count)
        if count < 0:
            raise ScientificCoreError(
                f"scientific data reference count must be >= 0, got {count}"
            )
        object.__setattr__(self, "count", count)

        dtype = str(self.dtype).strip()
        if dtype not in SUPPORTED_DTYPES:
            raise ScientificCoreError(
                f"unsupported bulk dtype {dtype!r}; supported: "
                f"{sorted(SUPPORTED_DTYPES)}"
            )
        object.__setattr__(self, "dtype", dtype)

        algorithm = str(self.digest_algorithm).strip()
        if algorithm not in SUPPORTED_DIGEST_ALGORITHMS:
            raise ScientificCoreError(
                f"unsupported digest algorithm {algorithm!r}; supported: "
                f"{sorted(SUPPORTED_DIGEST_ALGORITHMS)}"
            )
        object.__setattr__(self, "digest_algorithm", algorithm)

        digest = str(self.digest).strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ScientificCoreError(
                f"scientific data reference requires a 64-character hex "
                f"{algorithm} digest; got {self.digest!r}. Bulk data without "
                f"content identity cannot be checked for substitution"
            )
        object.__setattr__(self, "digest", digest)

    @property
    def byte_length(self) -> int:
        """Exact size the referenced payload must have. Cheap tamper check."""
        return self.count * _BYTES_PER_ELEMENT[self.dtype]

    @classmethod
    def for_values(
        cls,
        name: str,
        values: Iterable[float] | Sequence[float],
        *,
        unit: str,
    ) -> tuple["ScientificDataReference", bytes]:
        """Build a reference for ``values`` and return it with its bytes.

        Returns the payload alongside the reference rather than storing it:
        this module is the identity layer and owns no storage. The caller hands
        the bytes to whichever backend it likes, and the reference is unchanged
        by that choice.
        """
        payload = encode_float64(values)
        reference = cls(
            name=name,
            unit=unit,
            count=len(payload) // _BYTES_PER_ELEMENT[FLOAT64],
            dtype=FLOAT64,
            digest=content_digest(payload, dtype=FLOAT64),
        )
        return reference, payload

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.name}[{self.count} {self.dtype} {self.unit}]@{self.digest[:12]}"

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DATA_REFERENCE_SCHEMA,
            "name": self.name,
            "unit": self.unit,
            "count": self.count,
            "dtype": self.dtype,
            "digest": self.digest,
            "digest_algorithm": self.digest_algorithm,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificDataReference":
        require_schema(payload, DATA_REFERENCE_SCHEMA)
        return cls(
            name=payload["name"],
            unit=payload["unit"],
            count=int(payload["count"]),
            dtype=payload.get("dtype", FLOAT64),
            digest=payload["digest"],
            digest_algorithm=payload.get("digest_algorithm", SHA256),
        )
