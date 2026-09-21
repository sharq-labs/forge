"""Measured cell trajectories, normalized into the validation corpus.

What this module is
-------------------
The boundary between a laboratory file and Forge's evidence vocabulary. It
takes trajectories that a reader has already turned into numbers with declared
units, and produces :class:`~engcore.scientific.corpus.dataset.ReferenceCase`
and :class:`~engcore.scientific.corpus.dataset.ReferenceObservation` records.

What this module is deliberately not
-------------------------------------
* **Not a file reader.** No path, no archive, no column name, no vendor format
  appears below. Acquisition is I/O and lives with the acquisition record.
* **Not a source of scientific choices.** The split a trajectory belongs to,
  the independence group it sits in, whether it is inside the model's declared
  applicability, and what disagreement Forge will accept are all *arguments*.
  An adapter that decided any of them would be deciding the science of every
  campaign built on it.
* **Not a source of state of charge.** A coulomb-counted coordinate is derived
  here from measured current alone and is labelled for what it is --
  :data:`DEPTH_OF_DISCHARGE`, charge removed over rated capacity. It is a
  coordinate for locating evidence, never an observation, because comparing a
  model's coulomb counter against a coulomb counter is not a test of anything.

Sign convention
---------------
This domain's convention is positive current = discharge. A source recording
the opposite must say so with :class:`CurrentSign`; the conversion is recorded
on every trajectory so a reader can see which way the source pointed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Iterable, Mapping, Sequence

from ...scientific.corpus.dataset import (
    Applicability,
    DatasetSplit,
    ReferenceCase,
    ReferenceCondition,
    ReferenceDataset,
    ReferenceObservation,
)
from ...scientific.corpus.source import (
    CorpusError,
    ReferenceSource,
    SourceSnapshot,
    ToleranceSpec,
)
from ...scientific.units.quantity import Quantity
from . import context as ctx

#: Metric ids. These are the names a campaign scores and a coverage grid is
#: built per. They are metric identities, not quantity paths.
TERMINAL_VOLTAGE_METRIC = "terminal_voltage"
CELL_TEMPERATURE_METRIC = "cell_temperature"

#: Condition (coverage coordinate) names.
AMBIENT_TEMPERATURE = "ambient_temperature"
MEASURED_CELL_TEMPERATURE = "measured_cell_temperature"
LOAD_CURRENT_MAGNITUDE = "load_current_magnitude"
C_RATE = "c_rate"
DEPTH_OF_DISCHARGE = "depth_of_discharge"
ELAPSED_TIME = "elapsed_time"
CYCLE_INDEX = "cycle_index"

#: Input (what the model is given) names.
INITIAL_CELL_TEMPERATURE = "initial_cell_temperature"
INITIAL_STATE_OF_CHARGE = "initial_state_of_charge"


class CurrentSign(str, Enum):
    """Which sign the source uses for discharge."""

    POSITIVE_DISCHARGE = "positive_discharge"
    NEGATIVE_DISCHARGE = "negative_discharge"

    def to_domain(self, value: float) -> float:
        return value if self is CurrentSign.POSITIVE_DISCHARGE else -value


def _finite(value: Any, *, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise CorpusError(f"{label} must be finite, got {value!r}")
    return number


@dataclass(frozen=True)
class TrajectorySample:
    """One instant of one measured trajectory, in this domain's convention.

    ``cell_temperature`` is optional and its absence is load-bearing: a source
    with no temperature channel produces no temperature observation, and the
    campaign then says thermal validation is absent rather than scoring a
    number nobody measured.
    """

    elapsed: Quantity
    current: Quantity
    terminal_voltage: Quantity
    cell_temperature: Quantity | None = None

    def __post_init__(self) -> None:
        for label, unit in (
            ("elapsed", ctx.TIME_UNIT),
            ("current", ctx.CURRENT_UNIT),
            ("terminal_voltage", ctx.VOLTAGE_UNIT),
        ):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise CorpusError(f"trajectory sample {label} must be a Quantity in {unit}")
            value.require_compatible(Quantity(1.0, unit), context=f"sample {label}")
            object.__setattr__(self, label, value.to(unit))
            _finite(getattr(self, label).magnitude, label=f"sample {label}")
        if self.cell_temperature is not None:
            if not isinstance(self.cell_temperature, Quantity):
                raise CorpusError("trajectory sample cell_temperature must be a Quantity")
            self.cell_temperature.require_compatible(
                Quantity(1.0, ctx.TEMPERATURE_UNIT), context="sample cell_temperature"
            )
            converted = self.cell_temperature.to(ctx.TEMPERATURE_UNIT)
            if converted.magnitude <= 0.0:
                raise CorpusError("measured cell temperature must be above absolute zero")
            object.__setattr__(self, "cell_temperature", converted)
        if self.elapsed.magnitude < 0.0:
            raise CorpusError("trajectory sample elapsed time must be non-negative")


@dataclass(frozen=True)
class FileProvenance:
    """The exact file a trajectory was read out of, inside the snapshot."""

    member_path: str
    member_sha256: str
    byte_length: int

    def __post_init__(self) -> None:
        path = str(self.member_path).strip()
        if not path:
            raise CorpusError("file provenance requires a member_path")
        digest = str(self.member_sha256).strip().lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise CorpusError("file provenance member_sha256 must be a SHA-256 hex digest")
        if isinstance(self.byte_length, bool) or int(self.byte_length) <= 0:
            raise CorpusError("file provenance byte_length must be a positive integer")
        object.__setattr__(self, "member_path", path)
        object.__setattr__(self, "member_sha256", digest)
        object.__setattr__(self, "byte_length", int(self.byte_length))

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_path": self.member_path,
            "member_sha256": self.member_sha256,
            "byte_length": self.byte_length,
        }


@dataclass(frozen=True)
class MeasuredTrajectory:
    """One experiment on one cell: its identity, conditions and samples.

    ``rated_capacity`` is the manufacturer's rating, used only to express a
    C-rate and a depth of discharge. It is never the model's fitted capacity
    and never enters a prediction.
    """

    trajectory_id: str
    cell_id: str
    cycle_index: int
    ambient_temperature: Quantity
    rated_capacity: Quantity
    samples: tuple[TrajectorySample, ...]
    provenance: FileProvenance
    source_sign: CurrentSign = CurrentSign.POSITIVE_DISCHARGE
    initial_state_of_charge: Quantity | None = None
    conditions_note: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("trajectory_id", "cell_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise CorpusError(f"a measured trajectory requires {label}")
            object.__setattr__(self, label, value)
        if isinstance(self.cycle_index, bool) or int(self.cycle_index) < 0:
            raise CorpusError("cycle_index must be a non-negative integer")
        object.__setattr__(self, "cycle_index", int(self.cycle_index))
        for label, unit in (
            ("ambient_temperature", ctx.TEMPERATURE_UNIT),
            ("rated_capacity", ctx.CAPACITY_UNIT),
        ):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise CorpusError(f"trajectory {label} must be a Quantity in {unit}")
            value.require_compatible(Quantity(1.0, unit), context=f"trajectory {label}")
            converted = value.to(unit)
            if converted.magnitude <= 0.0:
                raise CorpusError(f"trajectory {label} must be strictly positive")
            object.__setattr__(self, label, converted)
        if not isinstance(self.provenance, FileProvenance):
            raise CorpusError("a measured trajectory requires FileProvenance")
        object.__setattr__(self, "source_sign", CurrentSign(self.source_sign))

        samples = tuple(self.samples)
        if len(samples) < 2 or any(not isinstance(item, TrajectorySample) for item in samples):
            raise CorpusError(
                f"trajectory {self.trajectory_id!r} needs at least two TrajectorySample records"
            )
        previous = None
        for sample in samples:
            seconds = sample.elapsed.magnitude
            if previous is not None and seconds <= previous:
                raise CorpusError(
                    f"trajectory {self.trajectory_id!r} sample instants must ascend "
                    f"strictly; {seconds!r} does not follow {previous!r}"
                )
            previous = seconds
        object.__setattr__(self, "samples", samples)

        # A trajectory is either fully instrumented for temperature or not at
        # all. A channel that drops out partway is a data-quality question the
        # acquisition side must answer, not something to paper over per sample.
        measured = [item.cell_temperature is not None for item in samples]
        if any(measured) and not all(measured):
            raise CorpusError(
                f"trajectory {self.trajectory_id!r} has a cell temperature on some "
                f"samples and not others; a channel that appears and disappears is a "
                f"data-quality finding, not a partially observed trajectory"
            )

        if self.initial_state_of_charge is not None:
            value = self.initial_state_of_charge
            if not isinstance(value, Quantity):
                raise CorpusError("initial_state_of_charge must be a Quantity")
            value.require_compatible(
                Quantity(1.0, ctx.DIMENSIONLESS), context="initial_state_of_charge"
            )
            converted = value.to(ctx.DIMENSIONLESS)
            if not 0.0 <= converted.magnitude <= 1.0:
                raise CorpusError("initial_state_of_charge must lie in [0, 1]")
            object.__setattr__(self, "initial_state_of_charge", converted)
        object.__setattr__(self, "conditions_note", str(self.conditions_note).strip())
        object.__setattr__(
            self, "tags", tuple(sorted({str(item).strip() for item in self.tags if str(item).strip()}))
        )

    @property
    def has_temperature(self) -> bool:
        return self.samples[0].cell_temperature is not None

    def domain_current(self, index: int) -> Quantity:
        """The sample's current in this domain's positive-is-discharge convention."""
        raw = self.samples[index].current.magnitude
        return Quantity(self.source_sign.to_domain(raw), ctx.CURRENT_UNIT)

    def charge_removed(self) -> tuple[Quantity, ...]:
        """Cumulative charge removed at each sample, by trapezoid on measured current.

        Measured current only. Nothing the model produced enters this, which is
        what makes it usable as a coordinate for locating the model's evidence.
        """
        removed = [0.0]
        total = 0.0
        for index in range(1, len(self.samples)):
            dt_hours = (
                self.samples[index].elapsed.magnitude - self.samples[index - 1].elapsed.magnitude
            ) / 3600.0
            mean_current = 0.5 * (
                self.domain_current(index).magnitude + self.domain_current(index - 1).magnitude
            )
            total += mean_current * dt_hours
            removed.append(total)
        return tuple(Quantity(value, ctx.CAPACITY_UNIT) for value in removed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "cell_id": self.cell_id,
            "cycle_index": self.cycle_index,
            AMBIENT_TEMPERATURE: self.ambient_temperature.to_dict(),
            "rated_capacity": self.rated_capacity.to_dict(),
            "samples": len(self.samples),
            "duration": self.samples[-1].elapsed.to_dict(),
            "provenance": self.provenance.to_dict(),
            "source_current_sign": self.source_sign.value,
            "has_measured_cell_temperature": self.has_temperature,
            "conditions_note": self.conditions_note,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class MetricPolicy:
    """What Forge will accept as agreement for one metric, and why.

    Both fields are required together. ``acceptance`` carries
    ``REVIEWED_ACCEPTANCE`` by the corpus's own rule; ``source_uncertainty``
    carries ``SOURCE_REPORTED``. Supplying only the second would leave every
    observation UNSCORED, which is the corpus's correct behaviour and would
    make a campaign silently prove nothing.
    """

    metric: str
    acceptance: ToleranceSpec
    source_uncertainty: ToleranceSpec | None = None

    def __post_init__(self) -> None:
        metric = str(self.metric).strip()
        if not metric:
            raise CorpusError("a metric policy requires a metric name")
        object.__setattr__(self, "metric", metric)
        if not isinstance(self.acceptance, ToleranceSpec):
            raise CorpusError(f"metric {metric!r} requires a reviewed acceptance ToleranceSpec")


@dataclass(frozen=True)
class TrajectoryPlacement:
    """Where one trajectory sits in the split structure, decided elsewhere.

    ``independence_group`` is what makes the split structural rather than
    cosmetic: the corpus refuses a group that straddles the calibration
    boundary, so grouping by physical cell means no cell can be both the fit
    and the test of the fit.
    """

    trajectory_id: str
    split: DatasetSplit
    independence_group: str
    applicability: Applicability = Applicability.UNDECLARED
    note: str = ""

    def __post_init__(self) -> None:
        for label in ("trajectory_id", "independence_group"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise CorpusError(f"a trajectory placement requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "split", DatasetSplit(self.split))
        object.__setattr__(self, "applicability", Applicability(self.applicability))
        object.__setattr__(self, "note", str(self.note).strip())


def case_id_for(trajectory_id: str, sample_index: int) -> str:
    return f"{trajectory_id}#{sample_index:05d}"


def _sampled_indices(count: int, stride: int, *, skip_initial: bool) -> tuple[int, ...]:
    """Which sample indices become cases. Deterministic, declared, no randomness.

    The first sample is optionally skipped because it is the initial condition
    the model is *given*; scoring the model against an input it was handed
    would be counting a tautology as evidence.
    """
    if stride < 1:
        raise CorpusError("sampling stride must be at least 1")
    start = 1 if skip_initial else 0
    return tuple(range(start, count, stride))


def trajectory_cases(
    trajectory: MeasuredTrajectory,
    placement: TrajectoryPlacement,
    *,
    stride: int = 1,
    skip_initial: bool = True,
    metrics: Sequence[MetricPolicy] = (),
) -> tuple[tuple[ReferenceCase, ...], tuple[ReferenceObservation, ...]]:
    """Normalize one trajectory into cases and observations.

    One case per retained sample instant, one observation per declared metric
    the trajectory actually measured. A metric policy for a channel the
    trajectory does not carry produces no observation and no silent zero.
    """

    if not isinstance(trajectory, MeasuredTrajectory):
        raise CorpusError("trajectory_cases expects a MeasuredTrajectory")
    if not isinstance(placement, TrajectoryPlacement):
        raise CorpusError("trajectory_cases expects a TrajectoryPlacement")
    if placement.trajectory_id != trajectory.trajectory_id:
        raise CorpusError(
            f"placement names trajectory {placement.trajectory_id!r}, but the "
            f"trajectory is {trajectory.trajectory_id!r}"
        )
    policies = {item.metric: item for item in metrics}
    if not policies:
        raise CorpusError(
            "normalizing with no metric policy would produce cases nothing can "
            "score; declare what agreement means before building the corpus"
        )
    unknown = sorted(set(policies) - {TERMINAL_VOLTAGE_METRIC, CELL_TEMPERATURE_METRIC})
    if unknown:
        raise CorpusError(
            f"this adapter normalizes {TERMINAL_VOLTAGE_METRIC!r} and "
            f"{CELL_TEMPERATURE_METRIC!r}; it was handed policies for {unknown}"
        )

    removed = trajectory.charge_removed()
    rated = trajectory.rated_capacity.magnitude
    indices = _sampled_indices(len(trajectory.samples), stride, skip_initial=skip_initial)
    if not indices:
        raise CorpusError(
            f"trajectory {trajectory.trajectory_id!r} produced no cases at stride {stride}"
        )

    initial = trajectory.samples[0]
    inputs = [
        ReferenceCondition(
            INITIAL_CELL_TEMPERATURE,
            initial.cell_temperature
            if initial.cell_temperature is not None
            else trajectory.ambient_temperature,
        ),
        ReferenceCondition(AMBIENT_TEMPERATURE, trajectory.ambient_temperature),
    ]
    if trajectory.initial_state_of_charge is not None:
        inputs.append(
            ReferenceCondition(INITIAL_STATE_OF_CHARGE, trajectory.initial_state_of_charge)
        )

    cases: list[ReferenceCase] = []
    observations: list[ReferenceObservation] = []
    for index in indices:
        sample = trajectory.samples[index]
        current = trajectory.domain_current(index)
        conditions = [
            ReferenceCondition(AMBIENT_TEMPERATURE, trajectory.ambient_temperature),
            ReferenceCondition(
                LOAD_CURRENT_MAGNITUDE, Quantity(abs(current.magnitude), ctx.CURRENT_UNIT)
            ),
            ReferenceCondition(
                C_RATE, Quantity(abs(current.magnitude) / rated, ctx.C_RATE_UNIT)
            ),
            ReferenceCondition(
                DEPTH_OF_DISCHARGE,
                Quantity(removed[index].magnitude / rated, ctx.DIMENSIONLESS),
            ),
            ReferenceCondition(ELAPSED_TIME, sample.elapsed),
            ReferenceCondition(
                CYCLE_INDEX, Quantity(float(trajectory.cycle_index), ctx.DIMENSIONLESS)
            ),
        ]
        if sample.cell_temperature is not None:
            conditions.append(
                ReferenceCondition(MEASURED_CELL_TEMPERATURE, sample.cell_temperature)
            )
        case_id = case_id_for(trajectory.trajectory_id, index)
        cases.append(
            ReferenceCase(
                case_id=case_id,
                split=placement.split,
                independence_group=placement.independence_group,
                conditions=tuple(conditions),
                inputs=tuple(inputs),
                applicability=placement.applicability,
                tags=tuple(sorted(set(trajectory.tags) | {f"cell:{trajectory.cell_id}"})),
                note=(
                    f"{trajectory.provenance.member_path}"
                    f"#{trajectory.provenance.member_sha256[:12]}"
                    f" cycle {trajectory.cycle_index} sample {index}"
                    + (f"; {placement.note}" if placement.note else "")
                ),
            )
        )
        if TERMINAL_VOLTAGE_METRIC in policies:
            policy = policies[TERMINAL_VOLTAGE_METRIC]
            observations.append(
                ReferenceObservation(
                    case_id=case_id,
                    metric=TERMINAL_VOLTAGE_METRIC,
                    expected=sample.terminal_voltage,
                    source_uncertainty=policy.source_uncertainty,
                    acceptance_tolerance=policy.acceptance,
                )
            )
        if CELL_TEMPERATURE_METRIC in policies and sample.cell_temperature is not None:
            policy = policies[CELL_TEMPERATURE_METRIC]
            observations.append(
                ReferenceObservation(
                    case_id=case_id,
                    metric=CELL_TEMPERATURE_METRIC,
                    expected=sample.cell_temperature,
                    source_uncertainty=policy.source_uncertainty,
                    acceptance_tolerance=policy.acceptance,
                )
            )
    return tuple(cases), tuple(observations)


def build_reference_dataset(
    *,
    dataset_id: str,
    version: str,
    source: ReferenceSource,
    snapshot: SourceSnapshot,
    trajectories: Iterable[MeasuredTrajectory],
    placements: Mapping[str, TrajectoryPlacement],
    metrics: Sequence[MetricPolicy],
    stride: int = 1,
    skip_initial: bool = True,
    metadata: Mapping[str, Any] | None = None,
) -> ReferenceDataset:
    """Normalize a set of trajectories into one immutable reference dataset.

    Every trajectory must have a placement. A trajectory with no declared split
    is refused rather than defaulted into one: defaulting would decide, in a
    normalizer, which evidence is allowed to influence a fit.
    """

    items = tuple(trajectories)
    if not items:
        raise CorpusError("a reference dataset needs at least one measured trajectory")
    missing = sorted({item.trajectory_id for item in items} - set(placements))
    if missing:
        raise CorpusError(
            f"trajectories have no declared split placement: {missing}. A split is "
            f"a scientific decision and is never defaulted here"
        )
    stray = sorted(set(placements) - {item.trajectory_id for item in items})
    if stray:
        raise CorpusError(f"placements name trajectories not supplied: {stray}")

    cases: list[ReferenceCase] = []
    observations: list[ReferenceObservation] = []
    provenance: list[dict[str, Any]] = []
    for trajectory in sorted(items, key=lambda item: item.trajectory_id):
        case_block, observation_block = trajectory_cases(
            trajectory,
            placements[trajectory.trajectory_id],
            stride=stride,
            skip_initial=skip_initial,
            metrics=metrics,
        )
        cases.extend(case_block)
        observations.extend(observation_block)
        provenance.append(
            {
                **trajectory.to_dict(),
                "split": placements[trajectory.trajectory_id].split.value,
                "independence_group": placements[trajectory.trajectory_id].independence_group,
                "cases": len(case_block),
            }
        )

    combined: dict[str, Any] = {
        "normalization": {
            "adapter": "engcore.domains.battery.measurement",
            "stride": int(stride),
            "skip_initial_sample": bool(skip_initial),
            "current_convention": "positive current is discharge",
            "case_granularity": "one case per retained measured instant",
            "state_of_charge": (
                "not an observation: no independent state-of-charge reference "
                "exists in this source, and comparing a coulomb counter against "
                "a coulomb counter would test nothing"
            ),
        },
        "trajectories": provenance,
    }
    if metadata:
        combined.update(dict(metadata))

    return ReferenceDataset(
        dataset_id=dataset_id,
        version=version,
        source=source,
        snapshot=snapshot,
        cases=tuple(cases),
        observations=tuple(observations),
        metadata=combined,
    )


__all__ = [
    "AMBIENT_TEMPERATURE",
    "CELL_TEMPERATURE_METRIC",
    "CYCLE_INDEX",
    "C_RATE",
    "DEPTH_OF_DISCHARGE",
    "ELAPSED_TIME",
    "INITIAL_CELL_TEMPERATURE",
    "INITIAL_STATE_OF_CHARGE",
    "LOAD_CURRENT_MAGNITUDE",
    "MEASURED_CELL_TEMPERATURE",
    "TERMINAL_VOLTAGE_METRIC",
    "CurrentSign",
    "FileProvenance",
    "MeasuredTrajectory",
    "MetricPolicy",
    "TrajectoryPlacement",
    "TrajectorySample",
    "build_reference_dataset",
    "case_id_for",
    "trajectory_cases",
]
