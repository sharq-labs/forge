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
    """Deterministic JSON for any record exposing ``to_dict()``."""
    payload = record.to_dict() if hasattr(record, "to_dict") else encode(record)
    return json.dumps(payload, sort_keys=True, indent=indent)


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
