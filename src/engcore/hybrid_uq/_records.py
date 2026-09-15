"""Canonical bytes, digests and schema checks shared by the V2 records. Private."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Mapping

import numpy as np

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


#: How far below zero the smallest eigenvalue of a covariance's CORRELATION matrix may be computed, in units of
#: machine epsilon per dimension. Roundoff in forming and decomposing a valid covariance stays well inside it;
#: a materially indefinite matrix (``[[1, 2], [2, 1]]`` has correlation eigenvalue -1) is nowhere near it.
COVARIANCE_EIGENVALUE_ROUNDOFF = 16.0


def require_valid_covariance(covariance, p: int, label: str = "covariance") -> np.ndarray:
    """A finite, symmetric, positive-semidefinite p x p covariance with a positive diagonal, or HybridUQError.

    Semidefiniteness is judged on the correlation matrix ``D^-1/2 C D^-1/2``. That makes it independent of the
    parameters' units and scales: a tolerance on the raw eigenvalues, relative to the largest, would pass a
    materially negative direction along a parameter whose own variance is many orders smaller. A matrix within
    roundoff of singular is accepted, because roundoff cannot tell it from a positive definite one. Nothing is
    repaired: no eigenvalue is clipped and no variance is replaced.
    """
    cov = np.asarray(covariance, dtype=np.float64)
    if cov.shape != (p, p) or not np.all(np.isfinite(cov)):
        raise HybridUQError(f"{label} must be a finite {p} x {p} matrix")
    diagonal = np.diag(cov)
    if np.any(diagonal <= 0.0):
        raise HybridUQError(f"{label} must have a positive diagonal")
    scale = 1.0 / np.sqrt(diagonal)
    correlation = cov * np.outer(scale, scale)
    # Symmetry in correlation units too: an off-diagonal entry near zero differs from its mirror by roundoff that
    # is large relative to the entry and negligible relative to the variances it couples.
    if float(np.max(np.abs(correlation - correlation.T))) > 1e-10:
        raise HybridUQError(f"{label} must be symmetric")
    smallest = float(np.min(np.linalg.eigvalsh(0.5 * (correlation + correlation.T))))
    tolerance = COVARIANCE_EIGENVALUE_ROUNDOFF * p * float(np.finfo(float).eps)
    if smallest < -tolerance:
        raise HybridUQError(
            f"{label} is not positive semidefinite: its correlation matrix has eigenvalue {smallest:.3g} "
            f"(roundoff allows {-tolerance:.3g}); a covariance with a negative variance direction is no uncertainty")
    return cov
