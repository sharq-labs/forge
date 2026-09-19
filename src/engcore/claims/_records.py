"""Strict record mechanics shared by the claim layer. Private.

Every record in :mod:`engcore.claims` follows the discipline the Scientific
Core's own records follow:

* a ``schema`` string checked exactly on read;
* **unknown keys refused**, not ignored -- a key a reader drops is a
  declaration the writer made and nobody honoured;
* **missing keys refused**, not defaulted -- a default filled in on read is a
  value nobody wrote;
* identity by a *tagged* SHA-256 digest over canonical JSON, so two record
  types with coincidentally equal payloads never share a digest.

Nothing here knows any science.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from ..scientific.errors import ScientificCoreError
from ..scientific.units.quantity import Quantity
from .errors import ClaimContractError

#: Lowercase identifier, as the Core's capability grammar spells one segment.
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")

#: A dotted input path, optionally indexed: ``cell.nominal_capacity``,
#: ``stages[0].body.duration``. Declarations use ``[]`` for "every element";
#: a claim uses a concrete index. Nothing else is a path.
_SEGMENT = r"[a-z][a-z0-9_]*(?:\[(?:\d+)?\])?"
PATH = re.compile(rf"^{_SEGMENT}(?:\.{_SEGMENT})*$")


def require_text(value: Any, *, field: str, error: type[Exception] = ClaimContractError) -> str:
    """A non-empty string, refused rather than coerced when it is anything else."""
    if not isinstance(value, str):
        raise error(f"{field} must be a string, got {type(value).__name__}")
    text = value.strip()
    if not text:
        raise error(f"{field} must be non-empty")
    return text


def require_identifier(value: Any, *, field: str, error: type[Exception] = ClaimContractError) -> str:
    text = require_text(value, field=field, error=error)
    if not IDENTIFIER.match(text):
        raise error(
            f"{field} {text!r} is not an identifier: expected lowercase "
            f"[a-z][a-z0-9_]*. It is matched exactly against declared names, "
            f"so a spelling that would need normalizing is refused rather than "
            f"guessed"
        )
    return text


def require_path(value: Any, *, field: str, error: type[Exception] = ClaimContractError) -> str:
    text = require_text(value, field=field, error=error)
    if not PATH.match(text):
        raise error(
            f"{field} {text!r} is not an input path: expected dotted lowercase "
            f"segments, optionally indexed, e.g. 'cell.nominal_capacity' or "
            f"'stages[0].body.duration'"
        )
    return text


def require_bool(value: Any, *, field: str, error: type[Exception] = ClaimContractError) -> bool:
    if not isinstance(value, bool):
        raise error(
            f"{field} must be a JSON boolean, got {value!r}; a truthy value is "
            f"not a declaration"
        )
    return value


def require_mapping(value: Any, *, field: str, error: type[Exception] = ClaimContractError) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise error(f"{field} must be an object, got {type(value).__name__}")
    return value


def require_list(value: Any, *, field: str, error: type[Exception] = ClaimContractError) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise error(f"{field} must be an array, got {type(value).__name__}")
    return list(value)


def require_keys(
    payload: Mapping[str, Any],
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
    record: str,
    error: type[Exception] = ClaimContractError,
) -> None:
    """Refuse unknown keys and missing required keys, naming each one."""
    required = frozenset(required)
    allowed = required | frozenset(optional)
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise error(
            f"{record} carries unknown field(s) {unknown}; accepted: "
            f"{sorted(allowed)}. Unknown fields are refused rather than "
            f"ignored: a dropped field is a declaration nobody honoured"
        )
    missing = sorted(key for key in required if key not in payload)
    if missing:
        raise error(
            f"{record} is missing required field(s) {missing}; a reader that "
            f"filled them in would be writing values the author never wrote"
        )


def require_schema_exact(
    payload: Mapping[str, Any], expected: str, *, record: str, error: type[Exception] = ClaimContractError
) -> None:
    """``payload["schema"]`` must equal ``expected`` exactly."""
    found = payload.get("schema")
    if found != expected:
        raise error(f"{record}: expected schema {expected!r}, found {found!r}")


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact, no NaN, no silent ASCII escaping."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False
    )


def tagged_digest(tag: str, value: Any) -> str:
    """SHA-256 over ``tag``, a NUL separator and the canonical JSON of ``value``."""
    payload = tag.encode("utf-8") + b"\x00" + canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


ASSESSMENT_DIGEST_TAG = "crafty.claims.assessment/1"


def assessment_record_digest(record: Mapping[str, Any]) -> str:
    """The public ClaimAssessment identity over its canonical record."""
    return tagged_digest(ASSESSMENT_DIGEST_TAG, record)


# ---------------------------------------------------------------------------
# Input values
# ---------------------------------------------------------------------------
#
# A claim states inputs as a Quantity (magnitude AND unit), an identifier or
# category (text), a count (int) or a flag (bool). A bare float is refused: it
# is a number with no unit, and choosing one on the caller's behalf is exactly
# the silent default this layer exists to refuse. A dimensionless value is
# still a Quantity -- ``Quantity(0.5, "dimensionless")`` -- so the decision
# that it has no unit is written down by whoever made it.

INPUT_VALUE_TYPES = (Quantity, str, int, bool)


def check_input_value(value: Any, *, field: str) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, Quantity):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return require_text(value, field=field)
    if isinstance(value, float):
        raise ClaimContractError(
            f"{field} is a bare number ({value!r}). A physical input must carry "
            f"its unit as a Quantity; a dimensionless one is "
            f"Quantity(x, 'dimensionless'), which records that someone decided "
            f"it has no unit"
        )
    raise ClaimContractError(
        f"{field} must be a Quantity, text, integer or boolean, got "
        f"{type(value).__name__}"
    )


def encode_input_value(value: Any) -> Any:
    if isinstance(value, Quantity):
        return value.to_dict()
    return value


def decode_input_value(raw: Any, *, field: str) -> Any:
    if isinstance(raw, Mapping):
        try:
            return Quantity.from_dict(raw)
        except (ScientificCoreError, KeyError, TypeError, ValueError) as exc:
            raise ClaimContractError(f"{field} is not a readable quantity record: {exc}") from exc
    if isinstance(raw, float):
        # JSON has one number type; an integral float written by a JSON encoder
        # for a count is still refused, because the writer produced a float.
        raise ClaimContractError(
            f"{field} is a bare number ({raw!r}); quantities are written as "
            f"quantity records carrying their unit"
        )
    return check_input_value(raw, field=field)


def encode_inputs(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: encode_input_value(values[key]) for key in sorted(values)}


def decode_inputs(raw: Any, *, field: str) -> dict[str, Any]:
    mapping = require_mapping(raw, field=field)
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        path = require_path(key, field=f"{field} key")
        out[path] = decode_input_value(value, field=f"{field}.{path}")
    return out


def quantity_text(quantity: Quantity) -> str:
    """The text form the MCP payload readers accept, proven to round-trip.

    ``repr`` of the magnitude is the shortest string that parses back to the
    same float, and the unit is the registry's normalized spelling. The
    round trip is re-checked here rather than assumed: a unit whose normalized
    spelling the parser does not accept would otherwise reach a payload as a
    different quantity, or as a refusal blamed on the caller.
    """
    if not math.isfinite(quantity.magnitude):  # pragma: no cover - Quantity refuses it
        raise ClaimContractError(f"non-finite magnitude {quantity.magnitude!r}")
    text = f"{quantity.magnitude!r} {quantity.units}"
    try:
        back = Quantity.parse(text)
    except ScientificCoreError as exc:
        raise ClaimContractError(
            f"quantity {quantity} has no text form the payload parser reads back "
            f"({exc}); it cannot be carried into a case without changing it"
        ) from exc
    if back != quantity:
        raise ClaimContractError(
            f"quantity {quantity} reads back from {text!r} as {back}; it cannot "
            f"be carried into a case without changing it"
        )
    return text


__all__: list[str] = []
