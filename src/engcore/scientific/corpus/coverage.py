"""Where the evidence is, and where it is not.

A pass fraction says how much of what was tried worked. It says nothing about
what was tried, and a model validated at ten points clustered in one corner of
its operating space can report 100% while having no evidence at all over the
regime a decision is about to be made in.

So coverage is multidimensional. A :class:`ValidationRegion` is a set of named,
unit-bearing axes cut into bins; every scored case falls in one cell; and each
cell reports what the evidence there actually is:

``SUPPORTED``
    enough passing cases, no failures.
``SPARSE``
    some passing evidence, below the declared minimum. Not the same as
    supported, and refusing to say so is the point.
``FAILED``
    at least one failure here. One failure does not average away against
    neighbouring passes.
``UNTESTED``
    no scored case landed here at all.

NEITHER A REFUSAL NOR AN UNSCREENED CASE CHANGES A CELL'S STATUS
------------------------------------------------------------------
``_cell_status`` takes passes and failures and nothing else. A cell where the
model declined every case, or where every case had undeclared applicability, is
``UNTESTED`` -- not ``SUPPORTED``. In the first the model produced no answer; in
the second nobody established that the answers were about a region the model
claims. Both are counted, separately and visibly, and neither is evidence.

A REFUSAL NEVER CHANGES A CELL'S STATUS
----------------------------------------
Refusals are tallied per cell and are deliberately excluded from
:func:`_cell_status`. A cell where the model declined every case is
``UNTESTED``, not ``SUPPORTED``: the model produced no answer there, so there
is nothing to have been right about. Correct and unexpected refusals are
counted separately rather than merged, because one is a guardrail working and
the other is a defect, and a single ``refused`` number would hide the
difference.

AND COVERAGE IS ABOUT ONE METRIC
---------------------------------
A cell used to tally every comparison that landed in it, whatever quantity was
being compared. So a model whose temperature agrees everywhere and whose
voltage fails everywhere produced cells that were half right about both, and a
query about voltage could be answered ``SUPPORTED`` by evidence about
temperature. Two quantities validated over the same operating region are two
pieces of evidence, not one.

Every :class:`ValidationCoverage` therefore names its ``metric`` and indexes
only that metric's comparisons. :func:`build_coverage_by_metric` produces the
set when a campaign scored several.

Core never learns what an axis or a metric means. ``temperature``,
``state_of_charge`` and ``load`` are strings with units, and the binning is
arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import bisect
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, normalize_unit
from .campaign import CaseVerdict, ValidationCampaignReport, ValidationComparison
from .dataset import DatasetSplit, ReferenceCase, ReferenceDataset
from .source import CorpusError, text

COVERAGE_DIMENSION_SCHEMA = schema_string("corpus_coverage_dimension")
VALIDATION_REGION_SCHEMA = schema_string("corpus_validation_region")
COVERAGE_CELL_SCHEMA = schema_string("corpus_coverage_cell")
VALIDATION_COVERAGE_SCHEMA = schema_string("corpus_validation_coverage")
FAILURE_CLUSTER_SCHEMA = schema_string("corpus_failure_cluster")


class CoverageStatus(str, Enum):
    SUPPORTED = "supported"
    SPARSE = "sparse"
    FAILED = "failed"
    UNTESTED = "untested"


@dataclass(frozen=True, order=True)
class CoverageDimension:
    """One named axis of the operating space, cut at declared edges.

    ``edges`` are strictly increasing interior cut points in ``unit``, so ``n``
    edges make ``n + 1`` bins. The outermost bins are unbounded, which is
    deliberate: a case beyond the declared range is still evidence somewhere,
    and the envelope -- not the coverage grid -- is what calls it
    extrapolation.
    """

    name: str
    unit: str
    edges: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", text(self.name, label="dimension name"))
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        edges = tuple(float(item) for item in self.edges)
        if any(not math.isfinite(item) for item in edges):
            raise CorpusError(f"dimension {self.name!r} edges must be finite")
        if list(edges) != sorted(set(edges)):
            raise CorpusError(
                f"dimension {self.name!r} edges must be strictly increasing"
            )
        object.__setattr__(self, "edges", edges)

    @property
    def bin_count(self) -> int:
        return len(self.edges) + 1

    def bin_of(self, value: Quantity) -> int:
        """Which bin a unit-bearing coordinate falls in."""
        magnitude = value.magnitude_in(self.unit)
        return bisect.bisect_right(self.edges, magnitude)

    def bin_label(self, index: int) -> str:
        lower = "-inf" if index == 0 else f"{self.edges[index - 1]:g}"
        upper = "+inf" if index == len(self.edges) else f"{self.edges[index]:g}"
        return f"[{lower}, {upper}) {self.unit}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COVERAGE_DIMENSION_SCHEMA,
            "name": self.name,
            "unit": self.unit,
            "edges": list(self.edges),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoverageDimension":
        require_schema(payload, COVERAGE_DIMENSION_SCHEMA)
        return cls(payload["name"], payload["unit"], tuple(payload.get("edges", ())))


@dataclass(frozen=True)
class ValidationRegion:
    """The operating space a campaign's evidence is indexed over."""

    region_id: str
    dimensions: tuple[CoverageDimension, ...]
    minimum_supporting_cases: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "region_id", text(self.region_id, label="region_id"))
        dimensions = tuple(sorted(self.dimensions))
        if not dimensions or any(
            not isinstance(item, CoverageDimension) for item in dimensions
        ):
            raise CorpusError("a validation region requires CoverageDimension records")
        names = [item.name for item in dimensions]
        if len(names) != len(set(names)):
            raise CorpusError("a validation region repeats a dimension name")
        object.__setattr__(self, "dimensions", dimensions)
        minimum = self.minimum_supporting_cases
        if isinstance(minimum, bool) or int(minimum) != minimum or int(minimum) < 1:
            raise CorpusError("minimum_supporting_cases must be a positive integer")
        object.__setattr__(self, "minimum_supporting_cases", int(minimum))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.dimensions)

    def locate(self, coordinates: Mapping[str, Quantity]) -> tuple[int, ...] | None:
        """The cell a point falls in, or ``None`` if it is not fully located.

        A point missing one of the region's axes is not placed at a default. It
        is simply not located, and the caller has to say so rather than pretend
        it sat at zero.
        """
        located: list[int] = []
        for dimension in self.dimensions:
            value = coordinates.get(dimension.name)
            if value is None:
                return None
            try:
                located.append(dimension.bin_of(value))
            except Exception as exc:  # noqa: BLE001
                raise CorpusError(
                    f"coordinate {dimension.name!r} cannot be read in "
                    f"{dimension.unit!r}: {exc}"
                ) from exc
        return tuple(located)

    def label(self, cell: Sequence[int]) -> str:
        return "; ".join(
            f"{dimension.name}={dimension.bin_label(index)}"
            for dimension, index in zip(self.dimensions, cell)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VALIDATION_REGION_SCHEMA,
            "region_id": self.region_id,
            "dimensions": [item.to_dict() for item in self.dimensions],
            "minimum_supporting_cases": self.minimum_supporting_cases,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationRegion":
        require_schema(payload, VALIDATION_REGION_SCHEMA)
        return cls(
            payload["region_id"],
            tuple(CoverageDimension.from_dict(i) for i in payload["dimensions"]),
            payload.get("minimum_supporting_cases", 2),
        )


@dataclass(frozen=True, order=True)
class CoverageCell:
    """What the evidence is in one cell of the region."""

    cell: tuple[int, ...]
    label: str
    passed: int
    failed: int
    unscored: int
    correct_refusals: int
    unexpected_refusals: int
    #: Cases here whose applicability was never established. Counted so the
    #: cell can say "there were results, and none of them were evidence about a
    #: claimed region" -- which is different from no results at all.
    undeclared: int
    status: CoverageStatus

    def __post_init__(self) -> None:
        for label in (
            "passed",
            "failed",
            "unscored",
            "correct_refusals",
            "unexpected_refusals",
            "undeclared",
        ):
            value = getattr(self, label)
            if isinstance(value, bool) or int(value) != value or int(value) < 0:
                raise CorpusError(f"coverage cell {label} must be a non-negative integer")
            object.__setattr__(self, label, int(value))
        object.__setattr__(self, "cell", tuple(int(i) for i in self.cell))
        object.__setattr__(self, "status", CoverageStatus(self.status))

    @property
    def scored(self) -> int:
        return self.passed + self.failed

    @property
    def refused(self) -> int:
        """Every refusal here, of either kind. Never part of :attr:`scored`."""
        return self.correct_refusals + self.unexpected_refusals

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COVERAGE_CELL_SCHEMA,
            "cell": list(self.cell),
            "label": self.label,
            "passed": self.passed,
            "failed": self.failed,
            "unscored": self.unscored,
            "correct_refusals": self.correct_refusals,
            "unexpected_refusals": self.unexpected_refusals,
            "undeclared": self.undeclared,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoverageCell":
        require_schema(payload, COVERAGE_CELL_SCHEMA)
        return cls(
            tuple(payload["cell"]),
            payload["label"],
            payload["passed"],
            payload["failed"],
            payload["unscored"],
            payload["correct_refusals"],
            payload["unexpected_refusals"],
            payload["undeclared"],
            CoverageStatus(payload["status"]),
        )


@dataclass(frozen=True, order=True)
class FailureCluster:
    """Failures that share a coordinate. A pattern, not a cause.

    This says "the failures here are concentrated at this coordinate". It does
    not say why, and it never names missing physics: identifying the mechanism
    is a scientific judgement that needs evidence this record does not hold.
    """

    dimension: str
    bin_label: str
    failed: int
    scored: int
    case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", text(self.dimension, label="dimension"))
        object.__setattr__(self, "case_ids", tuple(sorted(self.case_ids)))

    @property
    def failure_fraction(self) -> float | None:
        return None if self.scored == 0 else self.failed / self.scored

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FAILURE_CLUSTER_SCHEMA,
            "dimension": self.dimension,
            "bin_label": self.bin_label,
            "failed": self.failed,
            "scored": self.scored,
            "case_ids": list(self.case_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FailureCluster":
        require_schema(payload, FAILURE_CLUSTER_SCHEMA)
        return cls(
            payload["dimension"],
            payload["bin_label"],
            payload["failed"],
            payload["scored"],
            tuple(payload.get("case_ids", ())),
        )


@dataclass(frozen=True)
class ValidationCoverage:
    """The evidence map for one campaign, one metric, over one region."""

    region: ValidationRegion
    cells: tuple[CoverageCell, ...]
    #: WHICH QUANTITY this map is about. Evidence for one metric is not
    #: evidence for another, however well they share an operating region.
    metric: str = ""
    unlocated_cases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.region, ValidationRegion):
            raise CorpusError("coverage requires a ValidationRegion")
        object.__setattr__(self, "metric", text(self.metric, label="coverage metric"))
        cells = tuple(sorted(self.cells))
        if any(not isinstance(item, CoverageCell) for item in cells):
            raise CorpusError("coverage requires CoverageCell records")
        # A status is a derived scientific conclusion, not caller-owned data.
        # CoverageCell cannot derive it alone because the minimum belongs to
        # the region, so this is the authoritative boundary that recomputes it.
        for item in cells:
            derived = _cell_status(
                item.passed, item.failed, self.region.minimum_supporting_cases
            )
            if item.status is not derived:
                raise CorpusError(
                    f"coverage cell {item.cell} declares status "
                    f"{item.status.value!r}, but its counts derive "
                    f"{derived.value!r} under region minimum "
                    f"{self.region.minimum_supporting_cases}"
                )
        object.__setattr__(self, "cells", cells)
        object.__setattr__(self, "unlocated_cases", tuple(sorted(self.unlocated_cases)))

    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in CoverageStatus}
        for cell in self.cells:
            counts[cell.status.value] += 1
        return counts

    def guardrail_counts(self) -> dict[str, int]:
        """Refusals across the region, on their own axis.

        Reported beside the coverage map and never folded into it: this is how
        often the model declined and whether it was right to, which is a
        different question from where it has been shown to be correct.
        """
        return {
            "correct_refusals": sum(item.correct_refusals for item in self.cells),
            "unexpected_refusals": sum(item.unexpected_refusals for item in self.cells),
        }

    @property
    def refusal_accuracy(self) -> float | None:
        counts = self.guardrail_counts()
        total = counts["correct_refusals"] + counts["unexpected_refusals"]
        return None if total == 0 else counts["correct_refusals"] / total

    def cell_at(self, coordinates: Mapping[str, Quantity]) -> CoverageCell | None:
        located = self.region.locate(coordinates)
        if located is None:
            return None
        for cell in self.cells:
            if cell.cell == located:
                return cell
        return None

    def cells_with(self, status: CoverageStatus) -> tuple[CoverageCell, ...]:
        wanted = CoverageStatus(status)
        return tuple(item for item in self.cells if item.status is wanted)

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VALIDATION_COVERAGE_SCHEMA,
            "region": self.region.to_dict(),
            "metric": self.metric,
            "cells": [item.to_dict() for item in self.cells],
            "unlocated_cases": list(self.unlocated_cases),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationCoverage":
        require_schema(payload, VALIDATION_COVERAGE_SCHEMA)
        return cls(
            ValidationRegion.from_dict(payload["region"]),
            tuple(CoverageCell.from_dict(i) for i in payload["cells"]),
            payload["metric"],
            tuple(payload.get("unlocated_cases", ())),
        )


def _cell_status(
    passed: int, failed: int, minimum: int
) -> CoverageStatus:
    """Support is decided by answers only.

    Refusals are not arguments to this function, and that is the point: a cell
    cannot become SUPPORTED because the model declined there.
    """
    if failed:
        return CoverageStatus.FAILED
    if passed == 0:
        return CoverageStatus.UNTESTED
    return CoverageStatus.SUPPORTED if passed >= minimum else CoverageStatus.SPARSE


_EMPTY_CELL = {
    "passed": 0,
    "failed": 0,
    "unscored": 0,
    "correct_refusals": 0,
    "unexpected_refusals": 0,
    "undeclared": 0,
}


def build_coverage(
    report: ValidationCampaignReport,
    dataset: ReferenceDataset,
    region: ValidationRegion,
    *,
    metric: str,
) -> ValidationCoverage:
    """Index one metric's comparisons over a declared operating region.

    Every cell of the region appears, including the empty ones. A coverage map
    that only lists the cells that happened to be tested cannot answer the
    question it exists for -- where is there *no* evidence.

    ``metric`` is required rather than defaulted. A default would have to be
    "all of them", which is the mixing this argument exists to prevent.
    """
    metric = text(metric, label="coverage metric")
    if report.normalized_dataset_sha256 != dataset.normalized_digest:
        raise CorpusError(
            "coverage was asked to index a campaign report against a different "
            "dataset than the one it was run on"
        )
    cases = {case.case_id: case for case in dataset.cases}
    tallies: dict[tuple[int, ...], dict[str, int]] = {}
    unlocated: set[str] = set()

    for comparison in report.comparisons:
        if comparison.metric != metric:
            continue
        case = cases.get(comparison.case_id)
        if case is None:
            raise CorpusError(
                f"comparison names case {comparison.case_id!r}, absent from the dataset"
            )
        if comparison.split is not case.split:
            raise CorpusError(
                f"comparison {comparison.case_id!r}/{comparison.metric!r} says it "
                f"belongs to {comparison.split.value!r}, but the dataset places "
                f"that case in {case.split.value!r}; split identity is evidence, "
                f"not a label a report may rewrite"
            )
        # Calibration evidence is allowed to fit a model. It is not independent
        # evidence that the fitted model validates, so it never enters a
        # ValidationCoverage map.
        if case.split is DatasetSplit.CALIBRATION:
            continue
        located = region.locate(case.coordinates)
        if located is None:
            unlocated.add(case.case_id)
            continue
        bucket = tallies.setdefault(located, dict(_EMPTY_CELL))
        verdict = comparison.verdict
        if verdict is CaseVerdict.PASS:
            bucket["passed"] += 1
        elif verdict is CaseVerdict.FAIL:
            bucket["failed"] += 1
        elif verdict is CaseVerdict.CORRECT_REFUSAL:
            bucket["correct_refusals"] += 1
        elif verdict is CaseVerdict.UNEXPECTED_REFUSAL:
            bucket["unexpected_refusals"] += 1
        elif verdict is CaseVerdict.APPLICABILITY_UNDECLARED:
            # Not passed, not failed, not a judged refusal. It cannot make this
            # cell supported and it cannot make it failed.
            bucket["undeclared"] += 1
        else:
            bucket["unscored"] += 1

    cells: list[CoverageCell] = []
    for coordinate in _all_cells(region):
        bucket = tallies.get(coordinate, _EMPTY_CELL)
        cells.append(
            CoverageCell(
                cell=coordinate,
                label=region.label(coordinate),
                passed=bucket["passed"],
                failed=bucket["failed"],
                unscored=bucket["unscored"],
                correct_refusals=bucket["correct_refusals"],
                unexpected_refusals=bucket["unexpected_refusals"],
                undeclared=bucket["undeclared"],
                # Refusals are not passed in. A declined cell stays untested.
                status=_cell_status(
                    bucket["passed"], bucket["failed"], region.minimum_supporting_cases
                ),
            )
        )
    return ValidationCoverage(region, tuple(cells), metric, tuple(sorted(unlocated)))


def build_coverage_by_metric(
    report: ValidationCampaignReport,
    dataset: ReferenceDataset,
    region: ValidationRegion,
) -> dict[str, ValidationCoverage]:
    """One coverage map per metric the campaign scored. Never one map for all."""
    metrics = sorted({
        item.metric
        for item in report.comparisons
        if item.split is not DatasetSplit.CALIBRATION
    })
    return {
        metric: build_coverage(report, dataset, region, metric=metric)
        for metric in metrics
    }


def _all_cells(region: ValidationRegion) -> list[tuple[int, ...]]:
    cells: list[tuple[int, ...]] = [()]
    for dimension in region.dimensions:
        cells = [
            (*prefix, index)
            for prefix in cells
            for index in range(dimension.bin_count)
        ]
    return cells


def cluster_failures(
    report: ValidationCampaignReport,
    dataset: ReferenceDataset,
    region: ValidationRegion,
    *,
    metric: str | None = None,
    minimum_failures: int = 2,
) -> tuple[FailureCluster, ...]:
    """Group failures by one coordinate at a time, along each declared axis.

    Marginal rather than joint on purpose: a joint cell with two failures in it
    is usually two failures, while "every failure sits in the top bin of one
    axis" is a pattern worth a person's attention. Reported only when at least
    ``minimum_failures`` land together, so a single failure is not dressed up
    as a trend.
    """
    cases = {case.case_id: case for case in dataset.cases}
    clusters: list[FailureCluster] = []
    for dimension in region.dimensions:
        failed: dict[int, list[str]] = {}
        scored: dict[int, int] = {}
        for comparison in report.comparisons:
            if metric is not None and comparison.metric != metric:
                continue
            # Failure clusters describe independent validation evidence, never
            # fit residuals from the calibration split.
            if comparison.split is DatasetSplit.CALIBRATION:
                continue
            if not comparison.verdict.is_scored:
                continue
            case = cases.get(comparison.case_id)
            if case is None:
                continue
            value = case.condition(dimension.name)
            if value is None:
                continue
            index = dimension.bin_of(value)
            scored[index] = scored.get(index, 0) + 1
            if comparison.verdict is CaseVerdict.FAIL:
                failed.setdefault(index, []).append(case.case_id)
        for index, case_ids in sorted(failed.items()):
            if len(case_ids) < minimum_failures:
                continue
            clusters.append(
                FailureCluster(
                    dimension=dimension.name,
                    bin_label=dimension.bin_label(index),
                    failed=len(case_ids),
                    scored=scored.get(index, 0),
                    case_ids=tuple(case_ids),
                )
            )
    return tuple(sorted(clusters))


__all__ = [
    "COVERAGE_CELL_SCHEMA",
    "COVERAGE_DIMENSION_SCHEMA",
    "FAILURE_CLUSTER_SCHEMA",
    "VALIDATION_COVERAGE_SCHEMA",
    "VALIDATION_REGION_SCHEMA",
    "CoverageCell",
    "CoverageDimension",
    "CoverageStatus",
    "FailureCluster",
    "ValidationCoverage",
    "ValidationRegion",
    "build_coverage",
    "build_coverage_by_metric",
    "cluster_failures",
]
