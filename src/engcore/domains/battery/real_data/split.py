"""Calibration / holdout split over whole physical groups, bound to a receipt.

The unit of the split is declared, never implied, and it is never a row:
adjacent samples of one time series come from one experiment, so a row-level
split puts the same experiment on both sides of the boundary.

``SplitUnit.CELL``
    Groups are assigned by physical cell. Calibration and holdout share no
    cell. This is the only unit that can support a statement about cells
    the calibration did not see.
``SplitUnit.TEST_SEQUENCE``
    Groups are assigned by test sequence. Calibration and holdout share no
    test sequence and no raw file, but they MAY share a cell. When they do,
    the split records the shared cells and says, in its own record, that the
    holdout supports a within-cell statement only.

The hard guard is the one Review 3 found missing in the S-OCV catalog
(``BATT_001`` / ``BATT_002`` on both sides): calibration and holdout must be
disjoint at the declared unit, over group ids and over raw-file digests. Overlap raises
:class:`~engcore.scientific.corpus.CorpusLeakageError`; it is never
reported as a smaller holdout.

The split's roles are the Core's :class:`~engcore.scientific.corpus.DatasetSplit`.
The holdout is VALIDATION or LOCKED_HOLDOUT, never CALIBRATION, and the only
way a fitting path reaches series is :func:`calibration_series`, which
returns calibration groups and refuses a split bound to another receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence

from ....scientific.corpus import CorpusError, CorpusLeakageError, DatasetSplit
from ....scientific.serialization import schema_string
from .ingest import BatteryDataset, BatteryTimeSeries, RealDataError

SPLIT_SCHEMA = schema_string("battery_calibration_holdout_split")
SPLIT_VERSION = "engcore.domains.battery.real_data.split/1"
_SPLIT_TAG = "engcore.domains.battery.real_data.split/1"


class SplitUnit(str, Enum):
    CELL = "cell"
    TEST_SEQUENCE = "test_sequence"


def _text(value: object, *, label: str) -> str:
    result = str(value).strip()
    if not result:
        raise RealDataError(f"{label} must be a non-empty string")
    return result


@dataclass(frozen=True)
class SplitPolicy:
    """The declared assignment, made before any model sees the data.

    ``calibration`` and ``holdout`` list unit keys -- cell ids for
    ``SplitUnit.CELL``, test-sequence ids for ``SplitUnit.TEST_SEQUENCE``.
    Every group of the dataset must fall under exactly one of them.
    """

    policy_id: str
    unit: SplitUnit
    calibration: tuple[str, ...]
    holdout: tuple[str, ...]
    rationale: str
    holdout_role: DatasetSplit = DatasetSplit.VALIDATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, label="policy_id"))
        object.__setattr__(self, "unit", SplitUnit(self.unit))
        calibration = tuple(_text(k, label="calibration key") for k in self.calibration)
        holdout = tuple(_text(k, label="holdout key") for k in self.holdout)
        if len(set(calibration)) != len(calibration) or len(set(holdout)) != len(holdout):
            raise RealDataError("a split policy lists a key twice")
        leaked = sorted(set(calibration) & set(holdout))
        if leaked:
            raise CorpusLeakageError(
                f"split policy {self.policy_id!r} puts {self.unit.value} keys {leaked} in calibration AND holdout; "
                "the same evidence cannot be both the fit and its own independent test"
            )
        if not calibration:
            raise CorpusError(f"split policy {self.policy_id!r} has no calibration {self.unit.value}")
        if not holdout:
            raise CorpusError(
                f"split policy {self.policy_id!r} has no holdout {self.unit.value}; an independent holdout is "
                "impossible, and none is reported"
            )
        object.__setattr__(self, "calibration", tuple(sorted(calibration)))
        object.__setattr__(self, "holdout", tuple(sorted(holdout)))
        role = DatasetSplit(self.holdout_role)
        if role is DatasetSplit.CALIBRATION:
            raise RealDataError("the holdout role cannot be CALIBRATION")
        object.__setattr__(self, "holdout_role", role)
        object.__setattr__(self, "rationale", _text(self.rationale, label="rationale"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": SPLIT_VERSION,
            "unit": self.unit.value,
            "calibration": list(self.calibration),
            "holdout": list(self.holdout),
            "holdout_role": self.holdout_role.value,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class CalibrationHoldoutSplit:
    receipt_digest: str
    dataset_id: str
    policy: SplitPolicy
    calibration_groups: tuple[str, ...]
    holdout_groups: tuple[str, ...]
    calibration_raw_sha256: tuple[str, ...]
    holdout_raw_sha256: tuple[str, ...]
    shared_cells: tuple[str, ...]
    independence_scope: str

    def __post_init__(self) -> None:
        # Re-checked at construction so a split assembled by hand meets the same guard.
        for left, right, what in (
            (self.calibration_groups, self.holdout_groups, "group ids"),
            (self.calibration_raw_sha256, self.holdout_raw_sha256, "raw-file digests"),
        ):
            leaked = sorted(set(left) & set(right))
            if leaked:
                raise CorpusLeakageError(f"calibration and holdout share {what} {leaked}")
        if not self.calibration_groups or not self.holdout_groups:
            raise CorpusError("a split needs at least one calibration group and one holdout group")
        if self.policy.unit is SplitUnit.CELL and self.shared_cells:
            raise CorpusLeakageError(
                f"a cell-level split cannot share cells across the boundary: {list(self.shared_cells)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SPLIT_SCHEMA,
            "receipt_digest": self.receipt_digest,
            "dataset_id": self.dataset_id,
            "policy": self.policy.to_dict(),
            "calibration_groups": list(self.calibration_groups),
            "holdout_groups": list(self.holdout_groups),
            "calibration_raw_sha256": list(self.calibration_raw_sha256),
            "holdout_raw_sha256": list(self.holdout_raw_sha256),
            "overlap": {"groups": 0, "raw_files": 0, "unit_keys": 0},
            "shared_cells": list(self.shared_cells),
            "independence_scope": self.independence_scope,
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(_SPLIT_TAG.encode("utf-8") + b"\x00" + payload.encode("utf-8")).hexdigest()


def _unit_key(series: BatteryTimeSeries, unit: SplitUnit) -> str:
    return series.cell_id if unit is SplitUnit.CELL else series.test_sequence_id


def build_split(dataset: BatteryDataset, policy: SplitPolicy) -> CalibrationHoldoutSplit:
    """Assign every group by its unit key; refuse any overlap, gap or unknown key."""

    if not isinstance(dataset, BatteryDataset):
        raise RealDataError("build_split needs an ingested BatteryDataset")
    if not isinstance(policy, SplitPolicy):
        raise RealDataError("build_split needs a SplitPolicy")
    keys = {item.group_id: _unit_key(item, policy.unit) for item in dataset.series}
    known = set(keys.values())
    unknown = sorted((set(policy.calibration) | set(policy.holdout)) - known)
    if unknown:
        raise RealDataError(f"split policy names {policy.unit.value} keys {unknown} that the dataset does not hold")
    unassigned = sorted(g for g, k in keys.items() if k not in policy.calibration and k not in policy.holdout)
    if unassigned:
        raise RealDataError(
            f"groups {unassigned} are assigned to neither side; an unassigned group is a silent exclusion"
        )
    calibration = tuple(sorted(g for g, k in keys.items() if k in policy.calibration))
    holdout = tuple(sorted(g for g, k in keys.items() if k in policy.holdout))
    cal_series = [dataset.group(g) for g in calibration]
    hold_series = [dataset.group(g) for g in holdout]
    shared = tuple(sorted({s.cell_id for s in cal_series} & {s.cell_id for s in hold_series}))
    if policy.unit is SplitUnit.CELL:
        scope = (
            "cell-level: calibration and holdout share no physical cell; the holdout can test generalization "
            "to the held-out cells only"
        )
    elif shared:
        scope = (
            f"within-cell only: calibration and holdout are different test sequences of the SAME cell(s) "
            f"{list(shared)}. The holdout can test a calibration on a sequence it did not see; it cannot "
            "support any statement about another cell"
        )
    else:
        scope = "test-sequence level with disjoint cells"
    return CalibrationHoldoutSplit(
        receipt_digest=dataset.receipt.digest,
        dataset_id=dataset.receipt.dataset_id,
        policy=policy,
        calibration_groups=calibration,
        holdout_groups=holdout,
        calibration_raw_sha256=tuple(sorted(s.raw_sha256 for s in cal_series)),
        holdout_raw_sha256=tuple(sorted(s.raw_sha256 for s in hold_series)),
        shared_cells=shared,
        independence_scope=scope,
    )


def calibration_series(dataset: BatteryDataset, split: CalibrationHoldoutSplit) -> tuple[BatteryTimeSeries, ...]:
    """The only series a fitting or identifiability path may read."""

    if not isinstance(split, CalibrationHoldoutSplit):
        raise RealDataError("calibration_series needs a CalibrationHoldoutSplit")
    if split.receipt_digest != dataset.receipt.digest:
        raise RealDataError(
            "the split is bound to another dataset receipt; evidence must stay bound to the data it was split from"
        )
    derived = build_split(dataset, split.policy)
    if derived.to_dict() != split.to_dict():
        raise RealDataError(
            "the split is not the one its own policy derives from this dataset (groups, digests, shared cells or "
            "scope differ); a hand-assembled split cannot route a held-out group into a fit"
        )
    series = tuple(dataset.group(g) for g in split.calibration_groups)
    if sorted(s.raw_sha256 for s in series) != list(split.calibration_raw_sha256):
        raise RealDataError("calibration series do not carry the raw digests the split recorded")
    return series


__all__ = [
    "SPLIT_SCHEMA",
    "SPLIT_VERSION",
    "CalibrationHoldoutSplit",
    "SplitPolicy",
    "SplitUnit",
    "build_split",
    "calibration_series",
]
