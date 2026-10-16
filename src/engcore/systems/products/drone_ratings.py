"""Manufacturer rating packets for multirotor missions.

Product-system adapter over the generic ``engcore.scientific.knowledge.operating_rating`` assessment. It reads one
packet format (published field names such as ``cooling_note``, ``test_note``, ``heat_dissipation``; limits whose key
or value carries a duration) and one mission field (``minimum_hover_duration_s``). That knowledge is specific to this
product family and therefore does not live in the Scientific Core (CLAUDE.md layer direction).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.knowledge.operating_rating import (
    ManufacturerOperatingRating,
    MissionRatingAssessment,
    RequestedOperatingCondition,
    assess_operating_ratings,
)
from ...scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from ...scientific.units.quantity import Quantity

_VALUE_WITH_DURATION = re.compile(
    r"^(\d+(?:\.\d+)?)\s*([AWaV])\s*\((\d+(?:\.\d+)?)\s*s\)$"
)
_PLAIN_VALUE = re.compile(r"^(\d+(?:\.\d+)?)\s*([AWaV])$")
_KEY_DURATION = re.compile(
    r"(?:^|_)(\d+(?:\.\d+)?)_(s|min)(?:_|$)|(?:^|_)(\d+(?:\.\d+)?)(s|min)(?:_|$)"
)


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _duration_token(key: str) -> tuple[float, str] | None:
    match = _KEY_DURATION.search(key)
    if match is None:
        return None
    number = match.group(1) or match.group(3)
    unit = match.group(2) or match.group(4)
    magnitude = float(number)
    if magnitude <= 0:
        raise InvalidScientificProblem(f"rating field {key} states a non-positive duration")
    seconds = magnitude * 60.0 if unit == "min" else magnitude
    return seconds, f"{int(seconds) if seconds.is_integer() else seconds}s"


def _unit_letter(letter: str) -> tuple[str, str]:
    return {"A": ("current", "ampere"), "W": ("power", "watt"), "V": ("voltage", "volt")}[letter]


def _limit_from_field(key: str, value: object) -> dict[str, Any] | None:
    if value is None or isinstance(value, bool):
        return None
    if key in {"cooling_note", "test_note", "heat_dissipation", "example_measured_row"}:
        return None
    key_duration = _duration_token(key)
    is_maximum = "maximum" in key or key.startswith("max_") or "_max_" in key or key.startswith("continuous_")
    if isinstance(value, str):
        text = " ".join(value.split())
        timed = _VALUE_WITH_DURATION.fullmatch(text)
        if timed:
            kind, unit = _unit_letter(timed.group(2))
            seconds = float(timed.group(3))
            if key_duration is not None and key_duration[0] != seconds:
                raise InvalidScientificProblem(f"rating field {key} states two different durations")
            return {
                "seconds": seconds,
                "kind": kind,
                "quantity": Quantity(float(timed.group(1)), unit),
                "is_maximum": is_maximum,
                "field": key,
            }
        plain = _PLAIN_VALUE.fullmatch(text)
        if plain and key_duration is not None:
            kind, unit = _unit_letter(plain.group(2))
            return {
                "seconds": key_duration[0],
                "kind": kind,
                "quantity": Quantity(float(plain.group(1)), unit),
                "is_maximum": is_maximum,
                "field": key,
            }
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and key_duration is not None:
        if key.endswith("_w") and "per_" not in key:
            kind, unit = "power", "watt"
        elif key.endswith("_a"):
            kind, unit = "current", "ampere"
        elif key.endswith("_v"):
            kind, unit = "voltage", "volt"
        else:
            raise InvalidScientificProblem(f"rating field {key} has a number and no unit suffix")
        return {
            "seconds": key_duration[0],
            "kind": kind,
            "quantity": Quantity(float(value), unit),
            "is_maximum": is_maximum,
            "field": key,
        }
    return None


def _undated_magnitude(key: str, value: object) -> bool:
    """A current, power or voltage with no explicit duration. Not a duration guess."""
    if _limit_from_field(key, value) is not None or value is None or isinstance(value, bool):
        return False
    if key in {"cooling_note", "test_note", "heat_dissipation", "example_measured_row"}:
        return False
    if isinstance(value, str):
        text = " ".join(value.split())
        return _PLAIN_VALUE.fullmatch(text) is not None and _duration_token(key) is None
    if isinstance(value, (int, float)) and (
        key.endswith(("_a", "_v")) or (key.endswith("_w") and "per_" not in key)
    ):
        return _duration_token(key) is None
    return False


def _agreed_limit(items: list[dict[str, Any]], kind: str) -> tuple[Quantity | None, bool, bool]:
    chosen = [item for item in items if item["kind"] == kind]
    if not chosen:
        return None, False, False
    magnitudes = {float(item["quantity"].magnitude_in(chosen[0]["quantity"].units)) for item in chosen}
    if len(magnitudes) != 1:
        return None, False, True
    return chosen[0]["quantity"], any(item["is_maximum"] for item in chosen), False


def ratings_from_packet_record(record: Mapping[str, Any]) -> tuple[ManufacturerOperatingRating, ...]:
    """Build ratings from one frozen packet record.

    Duration is taken only from an explicit time token in a rating field.
    Notes are qualifiers. A null duration field creates no rating. One
    measured row is preserved nowhere as an established mission operating point.
    """

    fields = record["stated_fields"]
    if not isinstance(fields, Mapping):
        raise InvalidScientificProblem("a packet record requires stated_fields")
    parsed = []
    for key in sorted(fields):
        item = _limit_from_field(str(key), fields[key])
        if item is not None:
            parsed.append(item)
    grouped: dict[float, list[dict[str, Any]]] = {}
    for item in parsed:
        grouped.setdefault(item["seconds"], []).append(item)
    undated = [
        key for key in fields
        if _undated_magnitude(str(key), fields[key])
    ]
    digest = _canonical_digest(dict(record))
    source = KnowledgeSource(
        str(record["record_id"]),
        str(record["manufacturer"]),
        digest,
        "frozen-packet-record",
        str(record["source_page"]),
        KnowledgeSourceClass.MANUFACTURER_DATASHEET,
    )
    cooling = fields.get("cooling_note")
    cooling_text = cooling.strip() if isinstance(cooling, str) and cooling.strip() else None
    temperature = fields.get("test_note")
    temperature_text = temperature.strip() if isinstance(temperature, str) and temperature.strip() else None
    environment = fields.get("heat_dissipation")
    environment_text = (
        f"heat dissipation: {environment.strip()}"
        if isinstance(environment, str) and environment.strip()
        else None
    )
    ratings = []
    for seconds in sorted(grouped):
        items = grouped[seconds]
        current, current_is_maximum, current_conflict = _agreed_limit(items, "current")
        power, power_is_maximum, power_conflict = _agreed_limit(items, "power")
        voltage, _voltage_maximum, voltage_conflict = _agreed_limit(items, "voltage")
        label = "+".join(item["field"] for item in items)
        token = int(seconds) if float(seconds).is_integer() else seconds
        ratings.append(ManufacturerOperatingRating(
            source=source,
            source_digest_scope="frozen_packet_record",
            component_id=str(record["record_id"]),
            manufacturer=str(record["manufacturer"]),
            rating_type=label,
            rating_id=f"{record['record_id']}:{token}s",
            duration=Quantity(float(seconds), "second"),
            current=current,
            power=power,
            voltage=voltage,
            current_is_maximum=current_is_maximum,
            power_is_maximum=power_is_maximum,
            limit_conflict=current_conflict or power_conflict or voltage_conflict,
            undated_magnitude=bool(undated),
            cooling_requirement=cooling_text,
            temperature_qualifier=temperature_text,
            environment_qualifier=environment_text,
            stated_duty=label,
        ))
    return tuple(ratings)


def assess_manufacturer_rating_packet(
    packet: Mapping[str, Any],
    *,
    run_id: str,
    source_revision: str,
) -> MissionRatingAssessment:
    """Assess a frozen packet. The packet is read and not modified.

    The generic assessment takes a duration quantity. This adapter reads the
    frozen packet key ``minimum_hover_duration_s`` and does not read any other
    endurance field. A boolean in that field is refused. A packet flag cannot
    establish an operating point; that requires an admission id and a quantity,
    which this frozen packet does not carry. Mass, disk loading and catalog
    search are outside this check.
    """

    mission = packet["mission"]
    raw_duration = mission["minimum_hover_duration_s"]
    if isinstance(raw_duration, bool) or not isinstance(raw_duration, (int, float)):
        raise InvalidScientificProblem("minimum_hover_duration_s must be a finite number")
    admission = mission.get("operating_point_admission_id")
    if admission is not None and not isinstance(admission, str):
        raise InvalidScientificProblem("operating_point_admission_id must be text or absent")
    request = RequestedOperatingCondition(
        requirement_id=str(packet["packet_id"]),
        duration=Quantity(raw_duration, "second"),
        cooling_condition=mission.get("cooling_condition"),
        operating_point_admission_id=admission,
    )
    ratings: list[ManufacturerOperatingRating] = []
    for record in packet["records"]:
        ratings.extend(ratings_from_packet_record(record))
    return assess_operating_ratings(
        tuple(ratings), request, run_id=run_id, source_revision=source_revision
    )
