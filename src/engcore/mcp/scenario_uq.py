"""Declared-scenario uncertainty envelopes over completed engineering answers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..scientific.units.quantity import Quantity

__all__ = ["SCENARIO_UQ_SCHEMA", "scenario_envelope"]

SCENARIO_UQ_SCHEMA = "engineering_scenario_uq/1"


def scenario_envelope(
    answers: Sequence[Mapping[str, Any]], *, scenario_ids: Sequence[str]
) -> dict[str, Any]:
    """Envelope like-named outputs; attach no probability the inputs lack."""
    if len(answers) < 2:
        raise ValueError("scenario uncertainty requires at least two scenarios")
    if len(answers) != len(scenario_ids):
        raise ValueError("scenario_ids length must match answers")
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("scenario ids must be unique")

    incomplete = [
        scenario_ids[index] for index, answer in enumerate(answers)
        if answer.get("status") != "completed"
    ]
    if incomplete:
        return {
            "schema": SCENARIO_UQ_SCHEMA,
            "status": "incomplete",
            "scenario_count": len(answers),
            "incomplete_scenarios": incomplete,
            "intervals": [],
            "probability_model": None,
        }

    systems = {answer["system"] for answer in answers}
    if len(systems) != 1:
        raise ValueError("all scenarios must run the same system")

    samples: dict[tuple[str, str], list[tuple[str, Quantity]]] = defaultdict(list)
    scenario_verdicts = []
    for scenario_id, answer in zip(scenario_ids, answers):
        scenario_verdicts.append({
            "scenario_id": scenario_id,
            "verdict": answer["verdict"],
        })
        for result in answer["results"]:
            for name, payload in result["values"].items():
                samples[(result["subject"], name)].append((
                    scenario_id,
                    Quantity(payload["magnitude"], payload["units"]),
                ))

    intervals = []
    for (subject, name), values in sorted(samples.items()):
        if len(values) != len(answers):
            # A quantity absent from one scenario has no common envelope. Its
            # omission is explicit rather than silently reducing sample count.
            continue
        unit = values[0][1].units
        converted = [
            (scenario_id, value.magnitude_in(unit))
            for scenario_id, value in values
        ]
        low_id, low = min(converted, key=lambda item: item[1])
        high_id, high = max(converted, key=lambda item: item[1])
        intervals.append({
            "subject": subject,
            "quantity": name,
            "lower": Quantity(low, unit).to_dict(),
            "upper": Quantity(high, unit).to_dict(),
            "lower_scenario_id": low_id,
            "upper_scenario_id": high_id,
            "sample_count": len(converted),
            "method": "declared_scenario_envelope",
            "confidence_level": None,
        })

    return {
        "schema": SCENARIO_UQ_SCHEMA,
        "status": "completed",
        "system": next(iter(systems)),
        "scenario_count": len(answers),
        "scenario_verdicts": scenario_verdicts,
        "all_scenarios_supported": all(
            item["verdict"] == "supported" for item in scenario_verdicts
        ),
        "intervals": intervals,
        "probability_model": None,
        "interpretation": (
            "Bounds span only the scenarios explicitly supplied by the caller; "
            "they are not a confidence or credible interval."
        ),
        "does_not_include": [
            "probability between or beyond declared scenarios",
            "observation or measurement noise",
            "model-form uncertainty",
            "numerical error beyond each scenario's recorded validation",
        ],
    }
