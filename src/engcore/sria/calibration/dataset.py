"""Leakage-resistant dataset handling.

A random row split on this corpus would be close to meaningless. Ten instances
of BBOB f12 at the same dimension and budget are near-identical computational
problems; putting five in train and five in test measures memorisation, not
generalisation, and would report an impressively small held-out error for a
model that has learned nothing transferable.

So splits are **grouped by problem identity** and the grouping is enforced
rather than assumed: :func:`grouped_split` refuses to return a split whose
train and test groups intersect, and :func:`assert_no_group_leakage` is called
by the evaluation path.

The group key is also the one field a model may never see. It lives on the
record for splitting only, and :func:`assert_group_key_not_a_feature` proves
no covariate carries it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from .learning_record import ComputationalLearningRecord, LearningRecordError


class LeakageError(Exception):
    """A split or feature set that would leak problem identity."""


@dataclass(frozen=True)
class GroupedSplit:
    """A train/test split with its grouping made explicit."""

    train: tuple[ComputationalLearningRecord, ...]
    test: tuple[ComputationalLearningRecord, ...]
    train_groups: tuple[str, ...]
    test_groups: tuple[str, ...]
    strategy: str

    @property
    def summary(self) -> str:
        return (
            f"{self.strategy}: {len(self.train)} train rows / "
            f"{len(self.train_groups)} groups, {len(self.test)} test rows / "
            f"{len(self.test_groups)} groups"
        )


def assert_no_group_leakage(split: GroupedSplit) -> None:
    overlap = set(split.train_groups) & set(split.test_groups)
    if overlap:
        raise LeakageError(
            f"train and test share problem groups {sorted(overlap)[:5]}; "
            f"held-out error would measure memorisation, not generalisation"
        )


def assert_group_key_not_a_feature(
    records: Iterable[ComputationalLearningRecord],
) -> None:
    """The split key must never appear among the covariates."""
    for record in records:
        if not record.group_key:
            continue
        for name, _ in record.covariates.items():
            if record.group_key.lower() in name.lower():
                raise LeakageError(
                    f"record {record.record_id!r} exposes its group key in "
                    f"covariate {name!r}; problem identity is a split key, "
                    f"never a feature"
                )


def group_counts(
    records: Iterable[ComputationalLearningRecord],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.group_key] += 1
    return dict(counts)


def grouped_split(
    records: Sequence[ComputationalLearningRecord],
    *,
    holdout_groups: int | None = None,
    holdout_fraction: float = 0.25,
    strategy: str = "grouped-by-problem-identity",
) -> GroupedSplit:
    """Hold out whole problem groups, chosen deterministically.

    Deterministic by sorted group name rather than randomly: this campaign has
    to be reproducible, and a seeded shuffle would still invite quietly
    re-rolling the seed until the numbers improve.
    """
    records = list(records)
    if not records:
        raise LearningRecordError("cannot split an empty dataset")

    missing = [r.record_id for r in records if not r.group_key]
    if missing:
        raise LeakageError(
            f"{len(missing)} records carry no group_key; a split cannot be "
            f"made leakage-resistant without problem identity "
            f"(first: {missing[:3]})"
        )

    groups = sorted({r.group_key for r in records})
    if len(groups) < 2:
        raise LeakageError(
            f"only {len(groups)} problem group(s) present; a grouped holdout "
            f"is not possible and any reported held-out score would be fiction"
        )

    if holdout_groups is None:
        holdout_groups = max(1, int(round(len(groups) * holdout_fraction)))
    holdout_groups = min(holdout_groups, len(groups) - 1)

    # Every k-th group, so the holdout spans the range rather than one end.
    step = len(groups) / holdout_groups
    picked = {groups[min(len(groups) - 1, int(i * step))] for i in range(holdout_groups)}

    train = tuple(r for r in records if r.group_key not in picked)
    test = tuple(r for r in records if r.group_key in picked)

    split = GroupedSplit(
        train=train,
        test=test,
        train_groups=tuple(sorted({r.group_key for r in train})),
        test_groups=tuple(sorted({r.group_key for r in test})),
        strategy=strategy,
    )
    assert_no_group_leakage(split)
    assert_group_key_not_a_feature(records)
    return split


def grouped_folds(
    records: Sequence[ComputationalLearningRecord],
    *,
    folds: int = 4,
) -> tuple[GroupedSplit, ...]:
    """Deterministic grouped k-fold, for a stabler held-out estimate."""
    records = list(records)
    groups = sorted({r.group_key for r in records})
    if len(groups) < folds:
        raise LeakageError(
            f"{len(groups)} groups cannot support {folds} grouped folds"
        )

    assignments: dict[str, int] = {g: i % folds for i, g in enumerate(groups)}
    out: list[GroupedSplit] = []
    for fold in range(folds):
        test_groups = {g for g, f in assignments.items() if f == fold}
        train = tuple(r for r in records if r.group_key not in test_groups)
        test = tuple(r for r in records if r.group_key in test_groups)
        split = GroupedSplit(
            train=train,
            test=test,
            train_groups=tuple(sorted({r.group_key for r in train})),
            test_groups=tuple(sorted(test_groups)),
            strategy=f"grouped-{folds}fold-by-problem-identity[fold={fold}]",
        )
        assert_no_group_leakage(split)
        out.append(split)
    return tuple(out)
