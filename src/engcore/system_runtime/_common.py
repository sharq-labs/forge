"""Small shared helpers for the system runtime (no authority of their own).

Canonical serialization is strict on purpose: NaN and infinity are refused anywhere in an
interpreted record, keys are checked exactly, and every digest is sha256 over sorted-key JSON.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:@/-]*$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def schema(name: str, version: int = 1) -> str:
    return f"forge.system_runtime.{name}/{version}"


def identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise InvalidScientificProblem(f"{label} must be a non-empty typed identifier, got {value!r}")
    return text


def text(value: object, label: str, *, allow_empty: bool = False) -> str:
    out = str(value).strip() if value is not None else ""
    if not out and not allow_empty:
        raise InvalidScientificProblem(f"{label} must be non-empty text")
    return out


def hex64(value: object, label: str, *, allow_empty: bool = False) -> str:
    out = str(value).strip() if value is not None else ""
    if not out and allow_empty:
        return ""
    if not _HEX64.fullmatch(out):
        raise InvalidScientificProblem(f"{label} must be a sha256 hex digest")
    return out


def reject_non_finite(payload: Any, label: str = "record") -> None:
    """No NaN / Inf may sit inside an interpreted scientific record."""
    if isinstance(payload, float):
        if not math.isfinite(payload):
            raise InvalidScientificProblem(f"{label} contains a non-finite number")
    elif isinstance(payload, Mapping):
        for key, value in payload.items():
            reject_non_finite(value, f"{label}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            reject_non_finite(value, f"{label}[{index}]")


def canonical_json(payload: Any) -> str:
    reject_non_finite(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_of(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def strict_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(payload, Mapping):
        raise InvalidScientificProblem(f"{label} payload must be a mapping")
    found = set(payload)
    if found != expected:
        extra, missing = sorted(found - expected), sorted(expected - found)
        raise InvalidScientificProblem(f"{label} payload keys differ: unknown {extra}, missing {missing}")


def require_schema(payload: Mapping[str, Any], expected: str) -> None:
    if not isinstance(payload, Mapping) or payload.get("schema") != expected:
        found = payload.get("schema") if isinstance(payload, Mapping) else type(payload).__name__
        raise InvalidScientificProblem(f"unsupported schema {found!r}; expected {expected!r}")


def unique(items: tuple, key, label: str) -> None:
    keys = [key(item) for item in items]
    if len(keys) != len(set(keys)):
        raise InvalidScientificProblem(f"{label} contains duplicate identifiers")
