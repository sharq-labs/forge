"""Scientific core audit 2026-09-16, batch 5: near-duplicate readings and unit-raw comparisons.

Findings CORE-017 and CORE-018 (docs/audits/CORE_SCIENTIFIC_AUDIT_2026-09-16.md), under
benchmarks/core_v4_false_confidence/BATCH5_THRESHOLD_PROTOCOL.json. Recorded as strict xfails in commit e299af9 before the fix.
"""

from __future__ import annotations

import pytest

from engcore.inference import GaussianObservation, ObservationSet
from engcore.inference.split import DataLeakageError, ObservationSplit
from engcore.scientific import Quantity, TwinReference
from engcore.scientific.errors import ModelValidityError
from engcore.scientific.models.definition import CrossLimitCondition

TWIN = TwinReference("rig", "1")


def _obs(cid, value, sigma):
    return GaussianObservation(cid, "y", Quantity(value, "kelvin"), Quantity(sigma, "kelvin"), f"lab:{cid}")


@pytest.mark.parametrize("value,sigma", [(4.0, 0.5000005), (4.0000001, 0.5)], ids=["sigma_1ppm", "value_0.2ppm_of_sigma"])
def test_core017_a_copied_reading_nudged_below_measurement_resolution_is_leakage(value, sigma):
    calibration = ObservationSet((_obs("c1", 2.0, 0.5), _obs("c2", 4.0, 0.5)), dataset_id="cal")
    held = ObservationSet((_obs("h9", value, sigma),), dataset_id="held")
    with pytest.raises(DataLeakageError):
        ObservationSplit(calibration=calibration, held_out=held, twin=TWIN, source_dataset_id="src")


def test_core017_a_distinct_nearby_reading_is_not_leakage():
    calibration = ObservationSet((_obs("c1", 2.0, 0.5), _obs("c2", 4.0, 0.5)), dataset_id="cal")
    held = ObservationSet((_obs("h9", 4.001, 0.5),), dataset_id="held")
    ObservationSplit(calibration=calibration, held_out=held, twin=TWIN, source_dataset_id="src")


def test_core018_cross_limit_bounds_are_ordered_in_one_unit():
    with pytest.raises(ModelValidityError):
        CrossLimitCondition("ratio", numerator="a", denominator="b",
                            minimum=Quantity(0.9, "dimensionless"), maximum=Quantity(50, "percent"))
    CrossLimitCondition("ratio2", numerator="a", denominator="b",
                        minimum=Quantity(50, "percent"), maximum=Quantity(0.9, "dimensionless"))
