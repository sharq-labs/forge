"""Deterministic serialization helpers for Scientific Core records.

Rules enforced here:

* every serialized record carries an explicit ``schema`` string
  ``"<name>/<version>"`` so readers can refuse unknown formats;
* enums serialize to their ``value`` (stable, human readable);
* mappings serialize with sorted keys so byte-identical inputs produce
  byte-identical JSON;
* pickle is never a scientific record format.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Mapping

from .errors import ScientificCoreError


def schema_string(name: str, version: int = 1) -> str:
    return f"{name}/{version}"


def require_schema(payload: Mapping[str, Any], expected: str) -> None:
    """Reject a payload whose schema is missing or unknown."""
    found = payload.get("schema")
    if found != expected:
        raise ScientificCoreError(
            f"unsupported schema {found!r}; expected {expected!r}"
        )


def require_schema_any(
    payload: Mapping[str, Any], accepted: tuple[str, ...]
) -> str:
    """Reject a payload unless its schema is one this reader understands.

    The reader half of an additive version bump: the writer emits the newest
    string, and the reader keeps loading the older versions it still knows how
    to interpret. Returns the version found, so a caller can branch on it.

    Deliberately a tuple of **exact strings**, not a version range, a
    comparison or a migration framework. A version is admitted only because
    somebody checked that this reader handles it; a range would admit versions
    that do not exist yet, which is the failure mode ``require_schema``
    existed to prevent in the first place.
    """
    found = payload.get("schema")
    if found not in accepted:
        raise ScientificCoreError(
            f"unsupported schema {found!r}; expected one of {list(accepted)}"
        )
    return str(found)


def require_bool(
    payload: Mapping[str, Any],
    key: str,
    default: bool,
    *,
    error: type[Exception] = ScientificCoreError,
    context: str = "",
) -> bool:
    """A serialized boolean must arrive as a boolean.

    ``bool("false")`` is ``True``. A wire format that coerces lets a malformed
    record **invert** a scientific declaration rather than be refused -- a flag
    written as ``"false"`` coming back as True, a violated constraint coming
    back satisfied. Neither is a rounding error; both are the opposite of what
    was recorded, arriving silently.

    The absent key is still the additive default, because that is a record
    written before the field existed and the absence had exactly one meaning
    while it lasted. What is refused is a key that is **present and is not a
    boolean**.

    ``0`` and ``1`` are refused with the strings, and this is the decision
    rather than an accident. They are what a writer produces by losing the
    type, and accepting them would make "this writer lost the type"
    indistinguishable from "this writer meant False" -- so a record written by
    a broken producer would be read as a confident scientific statement.

    Stated here, at the serialization boundary, because it is a property of
    reading a wire format and not of any one record. It was previously a
    private helper in the model package applied to exactly one of the five
    boolean wire fields in this core.
    """
    if key not in payload:
        return default
    value = payload[key]
    if not isinstance(value, bool):
        where = f"{context}: " if context else ""
        raise error(
            f"{where}{key!r} must be a boolean, not {type(value).__name__} "
            f"({value!r}). A serialized scientific declaration is refused "
            f"rather than coerced: bool('false') is True, so coercing here "
            f"would silently invert the declaration instead of rejecting the "
            f"record"
        )
    return value


def encode(value: Any) -> Any:
    """Recursively convert a value into JSON-compatible primitives.

    Objects exposing ``to_dict()`` are delegated to; enums become their value;
    mappings are emitted with sorted keys.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): encode(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [encode(v) for v in value]
        if isinstance(value, (set, frozenset)):
            items.sort(key=lambda v: json.dumps(v, sort_keys=True))
        return items
    raise ScientificCoreError(
        f"cannot serialize value of type {type(value).__name__}"
    )


#: Types a scientific record may hold in a free-form field. Not a style
#: preference: this is the set that survives being written down and read back
#: as the same value.
_WRITABLE_LEAVES = (bool, int, float, str)


def unwritable(value: Any, *, path: str = "") -> tuple[str, str] | None:
    """Where a value stops being recordable, and what stopped it.

    Returns ``(path, type name)`` for the first thing inside ``value`` that no
    scientific record can carry, or ``None`` if the whole structure can be
    written down. The path is a subscript expression -- ``['numerics']['a']``
    -- so an error can point at the offending leaf rather than at the field
    containing it.

    THE BOUNDARY, and why it is not simply "whatever ``json.dumps`` accepts".
    Two narrowings, both deliberate and both in the direction of a record that
    reads back as what was stored:

    * **non-finite floats are refused**, though ``json.dumps`` emits them
      happily as the bare tokens ``NaN`` and ``Infinity``, which no conforming
      JSON reader accepts. A record that serializes to something unreadable is
      a record whose provenance does not exist, which is the same failure as
      one that cannot serialize at all -- only later and quieter. ``Quantity``
      already refuses non-finite magnitudes for this reason; this is that rule
      reaching the free-form fields.
    * **non-string mapping keys are refused**, though ``json.dumps`` silently
      coerces ``1`` and ``"1"`` to the same key -- so a record holding both
      loses one on the way out, and a record holding either reads back with a
      key of a different type than it was given.

    Everything else follows JSON: mappings, sequences, strings, numbers,
    booleans and null. A ``tuple`` is admitted and comes back as a list, which
    is JSON's nature rather than this function's opinion.
    """
    if value is None or isinstance(value, _WRITABLE_LEAVES):
        if isinstance(value, float) and value != value:
            return (path, "float('nan')")
        if isinstance(value, float) and value in (float("inf"), float("-inf")):
            return (path, "float('inf')")
        return None
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                return (f"{path}[{key!r}]", f"{type(key).__name__} key")
            found = unwritable(value[key], path=f"{path}[{key!r}]")
            if found is not None:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = unwritable(item, path=f"{path}[{index}]")
            if found is not None:
                return found
        return None
    return (path, type(value).__name__)


def to_json(record: Any, *, indent: int | None = None) -> str:
    """Deterministic JSON for any record exposing ``to_dict()``.

    ``allow_nan=False``, which is the whole of the fix and needs saying. Python's
    ``json`` emits non-finite floats as the bare tokens ``NaN``, ``Infinity``
    and ``-Infinity``, which **no conforming JSON reader accepts** -- they are
    not in the grammar. So a record carrying one serialized without complaint
    and produced a document that Python could read back and nothing else could.

    That is worse than failing to serialize, not better: a record whose
    provenance cannot be read by the consumer it was written for has no
    provenance, and the failure surfaces at the consumer rather than at the
    producer, long after the run that could have explained it.

    ``unwritable`` already refuses non-finite floats in the free-form fields,
    and ``Quantity`` refuses non-finite magnitudes. This closes the same rule
    over every OTHER branch of a payload -- a residual, a tolerance, a
    threshold -- in one place, on the way out, where no future record can miss
    it by forgetting to call a validator.

    A ``ValueError`` from here names the record that could not be written down.
    """
    payload = record.to_dict() if hasattr(record, "to_dict") else encode(record)
    try:
        return json.dumps(payload, sort_keys=True, indent=indent, allow_nan=False)
    except ValueError as exc:
        raise ScientificCoreError(
            f"{type(record).__name__} cannot be serialized: {exc}. A non-finite "
            f"float has no JSON representation -- Python emits the bare tokens "
            f"NaN and Infinity, which no conforming reader accepts -- so a "
            f"record carrying one would serialize here and be unreadable at "
            f"the consumer it was written for"
        ) from exc


def decode_mapping(
    payload: Mapping[str, Any] | None,
    factory,
) -> dict:
    """Rebuild ``{name: object}`` maps produced by :func:`encode`."""
    if not payload:
        return {}
    return {str(k): factory(v) for k, v in payload.items()}


def as_tuple(values) -> tuple:
    return tuple(values) if values is not None else ()
