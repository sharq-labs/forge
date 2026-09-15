"""Canonical bytes, digests and schema checks shared by the V2 records. Private."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from .vocabulary import HybridUQError

_NON_FINITE = {"inf": math.inf, "-inf": -math.inf, "nan": math.nan}


def encode_float(value: float) -> float | str:
    """A float JSON can carry exactly: non-finite values become the names ``inf``, ``-inf``, ``nan``."""
    value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return value


def decode_float(value: Any) -> float:
    if isinstance(value, str):
        if value not in _NON_FINITE:
            raise HybridUQError(f"not a float encoding: {value!r}")
        return _NON_FINITE[value]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HybridUQError(f"not a number: {value!r}")
    return float(value)


def encode_vector(values: Iterable[float]) -> list:
    return [encode_float(v) for v in values]


def decode_vector(values: Iterable[Any]) -> tuple[float, ...]:
    return tuple(decode_float(v) for v in values)


def encode_matrix(rows) -> list | None:
    return None if rows is None else [encode_vector(row) for row in rows]


def decode_matrix(rows) -> tuple[tuple[float, ...], ...] | None:
    return None if rows is None else tuple(decode_vector(row) for row in rows)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest_of(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def require_schema(payload: Mapping[str, Any], expected: str) -> None:
    if not isinstance(payload, Mapping):
        raise HybridUQError(f"a {expected} payload must be a mapping")
    found = payload.get("schema")
    if found != expected:
        raise HybridUQError(f"unsupported schema {found!r}; this reader accepts exactly {expected!r}")


def material(payload: Mapping[str, Any], non_material: Iterable[str]) -> dict[str, Any]:
    excluded = set(non_material)
    return {k: v for k, v in payload.items() if k not in excluded}
