"""Explicit aggregation of fast-physics output histories, with information loss stated.

There is no generic "average everything" rule.  Each aggregate is declared
(:class:`AggregationSpec`), produces a DERIVED :class:`AggregationRecord`
(never a measurement) that states which history features it PRESERVES and
which it LOSES, and the consuming degradation model declares which forms and
features it accepts (:class:`~engcore.scenarios.lifecycle.AggregateRequirement`).

Representative repetition (weight > 1) scales extensive quantities by the
exact weight and is recorded as an assumption; it never preserves ORDER or
EXTREMA of the represented history (other periods were not resolved).  A
gap in the resolved samples makes the aggregate UNKNOWN -- a missing interval
is not zero exposure.  Uncertainty of every aggregate is UNKNOWN: aggregation
does not create or improve uncertainty information.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Sequence

from ..scenarios.contracts import NamedQuantity
from ..scenarios.lifecycle import AggregateForm, HistoryFeature
from ..scenarios.timeline import TimeWindow, canonical_digest
from ..scientific.errors import InvalidScientificProblem, ScientificCoreError
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity, is_ratio_scale
from ._common import fraction_text, identifier, window_seconds
from .windows import RepresentativeWindow

CLASSIFICATION = "derived_aggregate_not_measurement"
ALL_FEATURES = frozenset(HistoryFeature)
#: Features a representative REPETITION can never vouch for.
REPETITION_LOSES = frozenset({HistoryFeature.ORDER, HistoryFeature.EXTREMA})

_FORM_PRESERVES = {
    AggregateForm.INTEGRAL_DOSE: frozenset({HistoryFeature.INTEGRAL}),
    AggregateForm.TIME_WEIGHTED_MEAN: frozenset({HistoryFeature.MEAN}),
    AggregateForm.EXTREMA: frozenset({HistoryFeature.EXTREMA}),
    AggregateForm.CYCLE_COUNT: frozenset({HistoryFeature.CYCLES}),
    AggregateForm.HISTOGRAM: frozenset({HistoryFeature.DISTRIBUTION, HistoryFeature.DWELL}),
    AggregateForm.DWELL_ABOVE: frozenset({HistoryFeature.DWELL}),
}


@dataclass(frozen=True)
class OutputSample:
    """One fast-physics output, held over one resolved (coupling) window."""

    window: TimeWindow
    value: Quantity

    def to_dict(self) -> dict[str, Any]:
        return {"window": self.window.to_dict(), "value": self.value.to_dict()}


@dataclass(frozen=True)
class OutputSeries:
    """A resolved history of one output quantity from one fast execution.

    ``preserved_features`` states what the series itself can vouch for; a
    raw piecewise-constant series from coupled windows preserves every
    feature AT ITS RESOLUTION (``resolution``), a series that is itself an
    aggregate preserves only what that aggregate kept.
    """

    quantity_id: str
    unit: str
    samples: tuple[OutputSample, ...]
    source_digest: str
    resolution: str = "piecewise constant over each coupling window"
    preserved_features: frozenset[HistoryFeature] = ALL_FEATURES

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity_id", identifier(self.quantity_id, "series quantity_id"))
        samples = tuple(sorted(self.samples, key=lambda s: s.window.start.seconds))
        if not samples:
            raise InvalidScientificProblem("an output series needs at least one sample")
        for s in samples:
            s.value.require_compatible(self.unit, context=f"series {self.quantity_id!r}")
        for a, b in zip(samples, samples[1:]):
            if b.window.start.seconds < a.window.end.seconds:
                raise InvalidScientificProblem(f"series {self.quantity_id!r} samples overlap")
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "preserved_features", frozenset(HistoryFeature(f) for f in self.preserved_features))

    def gaps_within(self, window: TimeWindow) -> list[tuple[Fraction, Fraction]]:
        gaps, cursor = [], window.start.seconds
        for s in self.samples:
            if s.window.end.seconds <= window.start.seconds or s.window.start.seconds >= window.end.seconds:
                continue
            if s.window.start.seconds > cursor:
                gaps.append((cursor, s.window.start.seconds))
            cursor = max(cursor, s.window.end.seconds)
        if cursor < window.end.seconds:
            gaps.append((cursor, window.end.seconds))
        return gaps

    def within(self, window: TimeWindow) -> list[tuple[Fraction, Quantity]]:
        out = []
        for s in self.samples:
            lo, hi = max(s.window.start.seconds, window.start.seconds), min(s.window.end.seconds, window.end.seconds)
            if hi > lo:
                out.append((hi - lo, s.value.to(self.unit)))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"quantity_id": self.quantity_id, "unit": self.unit, "samples": [s.to_dict() for s in self.samples],
                "source_digest": self.source_digest, "resolution": self.resolution,
                "preserved_features": sorted(f.value for f in self.preserved_features)}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


class DomainAggregator(ABC):
    """A domain-defined aggregate (e.g. a kinetics-weighted dose).

    The domain declares the source features it needs, the features its result
    preserves, and whether the result is extensive (scales with represented
    duration under repetition).
    """

    aggregator_id: str
    version: str
    parameters: tuple[NamedQuantity, ...]
    required_source_features: frozenset[HistoryFeature]
    preserves: frozenset[HistoryFeature]
    extensive: bool
    output_unit: str

    @abstractmethod
    def compute(self, samples: Sequence[tuple[Fraction, Quantity]]) -> Quantity:
        """Aggregate ``(duration_seconds, value)`` samples of ONE resolved window."""

    def identity(self) -> dict[str, Any]:
        return {"aggregator_id": self.aggregator_id, "version": self.version, "parameters": [p.to_dict() for p in self.parameters],
                "required_source_features": sorted(f.value for f in self.required_source_features),
                "preserves": sorted(f.value for f in self.preserves), "extensive": self.extensive, "output_unit": self.output_unit}


@dataclass(frozen=True)
class AggregationSpec:
    aggregate_id: str
    quantity_id: str
    form: AggregateForm
    #: level (DWELL_ABOVE, CYCLE_COUNT), statistic ("max"/"min" for EXTREMA),
    #: bin edges (HISTOGRAM), all in the series unit.  Conventions: DWELL_ABOVE
    #: counts time with value STRICTLY above ``level``; a cycle is a rise from
    #: at-or-below to strictly above ``level``; histogram bins are [lo, hi).
    level: Quantity | None = None
    statistic: str = ""
    bin_edges: tuple[Quantity, ...] = ()
    aggregator: DomainAggregator | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "aggregate_id", identifier(self.aggregate_id, "aggregate_id"))
        form = AggregateForm(self.form)
        object.__setattr__(self, "form", form)
        if (form is AggregateForm.DOMAIN_DEFINED) != (self.aggregator is not None):
            raise InvalidScientificProblem("a domain aggregator is required for, and only for, the DOMAIN_DEFINED form")
        if form in (AggregateForm.DWELL_ABOVE, AggregateForm.CYCLE_COUNT) and self.level is None:
            raise InvalidScientificProblem(f"{form.value} needs an explicit level")
        if form is AggregateForm.EXTREMA and self.statistic not in ("max", "min"):
            raise InvalidScientificProblem("an EXTREMA aggregate declares statistic 'max' or 'min'")
        if form is AggregateForm.HISTOGRAM and len(self.bin_edges) < 2:
            raise InvalidScientificProblem("a histogram needs at least two explicit bin edges")

    @property
    def form_key(self) -> str:
        return f"domain_defined:{self.aggregator.aggregator_id}" if self.aggregator else self.form.value

    def to_dict(self) -> dict[str, Any]:
        return {"aggregate_id": self.aggregate_id, "quantity_id": self.quantity_id, "form": self.form_key,
                "level": None if self.level is None else self.level.to_dict(), "statistic": self.statistic,
                "bin_edges": [b.to_dict() for b in self.bin_edges], "aggregator": None if self.aggregator is None else self.aggregator.identity()}


@dataclass(frozen=True)
class AggregationRecord:
    aggregate_id: str
    quantity_id: str
    form_key: str
    unit: str
    value: Quantity | None
    status: str
    reason: str
    statistics: tuple[tuple[str, str], ...]
    histogram: tuple[tuple[str, str, str], ...]
    represented: TimeWindow
    resolved: tuple[TimeWindow, ...]
    weights: tuple[Fraction, ...]
    source_digests: tuple[str, ...]
    preserved: frozenset[HistoryFeature]
    lost: tuple[str, ...]
    discarded: tuple[str, ...]
    assumption_dependent: bool
    spec_digest: str
    statistic: str = ""
    uncertainty: Uncertainty = field(default_factory=lambda: Uncertainty.unknown(
        "aggregate of fast-physics outputs whose uncertainty is not quantified; aggregation adds no uncertainty information"))

    @property
    def classification(self) -> str:
        return CLASSIFICATION

    @property
    def preserved_features(self) -> frozenset[str]:
        return frozenset(f.value for f in self.preserved)

    @property
    def represented_seconds(self) -> Fraction:
        return window_seconds(self.represented)

    @property
    def resolved_seconds(self) -> Fraction:
        return sum((window_seconds(w) for w in self.resolved), Fraction(0))

    def named_value(self, input_id: str) -> NamedQuantity | None:
        if self.status != "known" or self.value is None:
            return None
        return NamedQuantity(input_id, self.value, self.uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {"classification": CLASSIFICATION, "aggregate_id": self.aggregate_id, "quantity_id": self.quantity_id,
                "form": self.form_key, "unit": self.unit, "value": None if self.value is None else self.value.to_dict(),
                "status": self.status, "reason": self.reason, "statistics": [list(x) for x in self.statistics],
                "histogram": [list(x) for x in self.histogram], "represented": self.represented.to_dict(),
                "resolved": [w.to_dict() for w in self.resolved], "weights": [fraction_text(w) for w in self.weights],
                "represented_seconds": fraction_text(self.represented_seconds), "resolved_seconds": fraction_text(self.resolved_seconds),
                "source_digests": list(self.source_digests), "preserved": sorted(self.preserved_features), "lost": list(self.lost),
                "discarded": list(self.discarded), "assumption_dependent": self.assumption_dependent,
                "spec_digest": self.spec_digest, "statistic": self.statistic, "uncertainty": self.uncertainty.to_dict()}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def _affine(unit: str) -> bool:
    return not is_ratio_scale(unit)


def aggregate(spec: AggregationSpec, parts: Sequence[tuple[RepresentativeWindow, OutputSeries]], represented: TimeWindow) -> AggregationRecord:
    """Aggregate ``spec.quantity_id`` over ``represented`` from representative executions.

    ``parts`` pair each representative window with the series its fast
    execution produced; together the representative windows must tile
    ``represented`` exactly.
    """
    parts = tuple(parts)
    if not parts:
        raise InvalidScientificProblem("aggregation needs at least one representative execution")
    tiles = sorted((rep.represented for rep, _ in parts), key=lambda w: w.start.seconds)
    if tiles[0].start.seconds != represented.start.seconds or tiles[-1].end.seconds != represented.end.seconds or any(
            a.end.seconds != b.start.seconds for a, b in zip(tiles, tiles[1:])):
        raise InvalidScientificProblem("representative windows do not tile the represented interval exactly")
    series_unit = parts[0][1].unit
    weights = tuple(rep.weight for rep, _ in parts)
    repeated = any(w != 1 for w in weights)
    base = dict(aggregate_id=spec.aggregate_id, quantity_id=spec.quantity_id, form_key=spec.form_key, represented=represented,
                resolved=tuple(rep.resolved for rep, _ in parts), weights=weights,
                source_digests=tuple(s.source_digest for _, s in parts), spec_digest=canonical_digest(spec.to_dict()),
                assumption_dependent=repeated, statistic=spec.statistic)
    discarded = ["within-sample variation below the series resolution"]
    if repeated:
        discarded += ["variation between the resolved period and the other represented periods (repetition assumed)",
                      "order and extrema of unresolved periods"]

    def unknown(reason: str, unit: str) -> AggregationRecord:
        return AggregationRecord(**base, unit=unit, value=None, status="unknown", reason=reason, statistics=(), histogram=(),
                                 preserved=frozenset(), lost=tuple(sorted(f.value for f in ALL_FEATURES)), discarded=tuple(discarded))

    for rep, series in parts:
        if series.quantity_id != spec.quantity_id:
            raise InvalidScientificProblem(f"aggregate {spec.aggregate_id!r} expects {spec.quantity_id!r}, got {series.quantity_id!r}")
        gaps = series.gaps_within(rep.resolved)
        if gaps:
            return unknown(f"resolved window {rep.window_id!r} has unresolved gaps {[(float(a), float(b)) for a, b in gaps]}; "
                           "missing history is not zero", series_unit)
    source_features = frozenset.intersection(*(s.preserved_features for _, s in parts))
    form = spec.form
    statistics: list[tuple[str, str]] = []
    histogram: list[tuple[str, str, str]] = []
    value: Quantity | None

    if form is AggregateForm.DOMAIN_DEFINED:
        agg = spec.aggregator
        missing = sorted(f.value for f in agg.required_source_features - source_features)
        if missing:
            return unknown(f"domain aggregator {agg.aggregator_id!r} needs source history features {missing} "
                           "that the bound series does not preserve", agg.output_unit)
        total = None
        for rep, series in parts:
            try:
                v = agg.compute(series.within(rep.resolved)).to(agg.output_unit)
            except (ArithmeticError, ValueError, ScientificCoreError) as exc:
                return unknown(f"domain aggregator {agg.aggregator_id!r} refused the resolved history: {exc}", agg.output_unit)
            if agg.extensive:
                v = Quantity(v.magnitude * float(rep.weight), agg.output_unit)
            elif repeated:
                return unknown(f"non-extensive domain aggregate {agg.aggregator_id!r} has no declared repetition rule", agg.output_unit)
            total = v if total is None else Quantity(total.magnitude + v.magnitude, agg.output_unit)
        value, unit, preserved = total, agg.output_unit, frozenset(agg.preserves) & source_features
    else:
        needs = _FORM_PRESERVES[form]
        if not needs <= source_features:
            return unknown(f"{form.value} needs source features {sorted(f.value for f in needs - source_features)}", series_unit)
        samples = [(rep, series.within(rep.resolved)) for rep, series in parts]
        if form is AggregateForm.INTEGRAL_DOSE:
            if _affine(series_unit):
                return unknown(f"the time integral of an affine unit ({series_unit}) has no meaning", series_unit)
            unit = str((Quantity(1, series_unit) * Quantity(1, "s")).units)
            total = sum(float(rep.weight) * float(dt) * v.magnitude for rep, ss in samples for dt, v in ss)
            value = Quantity(total, unit)
        elif form is AggregateForm.TIME_WEIGHTED_MEAN:
            unit = series_unit
            num = sum(float(rep.weight) * float(dt) * v.magnitude for rep, ss in samples for dt, v in ss)
            den = sum(float(rep.weight) * float(dt) for rep, ss in samples for dt, _ in ss)
            value = Quantity(num / den, unit)
        elif form is AggregateForm.EXTREMA:
            unit = series_unit
            if repeated:
                return unknown("the extremum of the represented window is not known: only one period of the repeated "
                               "tiles was resolved", unit)
            values = [v.magnitude for _, ss in samples for _, v in ss]
            value = Quantity(max(values) if spec.statistic == "max" else min(values), unit)
            statistics = [("max", repr(max(values))), ("min", repr(min(values)))]
        elif form is AggregateForm.DWELL_ABOVE:
            unit = "second"
            level = spec.level.magnitude_in(series_unit)
            value = Quantity(sum(float(rep.weight) * float(dt) for rep, ss in samples for dt, v in ss if v.magnitude > level), unit)
        elif form is AggregateForm.CYCLE_COUNT:
            unit = "dimensionless"
            level = spec.level.magnitude_in(series_unit)
            total = Fraction(0)
            previous_above = None
            for rep, ss in sorted(samples, key=lambda x: x[0].represented.start.seconds):
                above = [v.magnitude > level for _, v in ss]
                if previous_above is None and above[0]:
                    return unknown("the history starts above the cycle level; whether a cycle began before the window "
                                   "is not known (a missing rise is not zero cycles)", unit)
                rises = sum(1 for a, b in zip(above, above[1:]) if b and not a)
                if previous_above is not None and above[0] and not previous_above:
                    rises += 1  # rise across the boundary between tiles
                if rep.weight != 1:
                    if above[0] != above[-1]:
                        return unknown(f"representative period {rep.window_id!r} does not close (starts "
                                       f"{'above' if above[0] else 'below'}, ends {'above' if above[-1] else 'below'} the level); "
                                       "cycles across repetitions are not declared", unit)
                    # closure (first == last) means no rise can cross a repetition boundary
                    total += rep.weight * rises
                else:
                    total += rises
                previous_above = above[-1]
            if total.denominator != 1:
                return unknown("representative weight times the resolved cycle count is not an integer; "
                               "fractional cycles are not declared", unit)
            value = Quantity(int(total), unit)
        else:  # HISTOGRAM
            unit = "second"
            edges = [b.magnitude_in(series_unit) for b in spec.bin_edges]
            if edges != sorted(edges):
                raise InvalidScientificProblem("histogram bin edges must be increasing")
            counts = [0.0] * (len(edges) - 1)
            outside = 0.0
            for rep, ss in samples:
                for dt, v in ss:
                    x = v.magnitude
                    idx = next((i for i in range(len(edges) - 1) if edges[i] <= x < edges[i + 1]), None)
                    if idx is None:
                        outside += float(rep.weight) * float(dt)
                    else:
                        counts[idx] += float(rep.weight) * float(dt)
            if outside:
                return unknown(f"{outside:g} s of the history lies outside the declared bins; it is not dropped silently", unit)
            histogram = [(repr(edges[i]), repr(edges[i + 1]), repr(counts[i])) for i in range(len(counts))]
            value = None
        preserved = _FORM_PRESERVES[form]
    if repeated:
        preserved = preserved - REPETITION_LOSES
        if form is not AggregateForm.DOMAIN_DEFINED and not (_FORM_PRESERVES[form] <= preserved):
            return unknown(f"representative repetition removes the {form.value} information itself", unit)
    lost = tuple(sorted(f.value for f in ALL_FEATURES - preserved))
    status = "known" if value is not None or histogram else "unknown"
    return AggregationRecord(**base, unit=unit, value=value, status=status, reason="" if status == "known" else "no scalar value",
                             statistics=tuple(statistics), histogram=tuple(histogram), preserved=frozenset(preserved), lost=lost,
                             discarded=tuple(discarded))


@dataclass(frozen=True)
class CompressedHistory:
    """Long-history compression of consecutive aggregation records (DERIVED data).

    Compression never increases assurance: its preserved features are the
    intersection of its sources', any UNKNOWN source makes it UNKNOWN, and its
    uncertainty is UNKNOWN.
    """

    history_id: str
    quantity_id: str
    form_key: str
    interval: TimeWindow
    source_digests: tuple[str, ...]
    represented_seconds: Fraction
    resolved_seconds: Fraction
    value: Quantity | None
    status: str
    retained: tuple[tuple[str, str], ...]
    preserved: tuple[str, ...]
    discarded: tuple[str, ...]
    uncertainty: Uncertainty = field(default_factory=lambda: Uncertainty.unknown("compressed derived history; uncertainty not quantified"))

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "compressed_derived_history_not_measurement", "history_id": self.history_id,
                "quantity_id": self.quantity_id, "form": self.form_key, "interval": self.interval.to_dict(),
                "source_digests": list(self.source_digests), "represented_seconds": fraction_text(self.represented_seconds),
                "resolved_seconds": fraction_text(self.resolved_seconds), "value": None if self.value is None else self.value.to_dict(),
                "status": self.status, "retained": [list(x) for x in self.retained], "preserved": list(self.preserved),
                "discarded": list(self.discarded), "uncertainty": self.uncertainty.to_dict()}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def compress_history(history_id: str, records: Sequence[AggregationRecord]) -> CompressedHistory:
    records = tuple(sorted(records, key=lambda r: r.represented.start.seconds))
    if not records:
        raise InvalidScientificProblem("nothing to compress")
    first = records[0]
    if any((r.spec_digest, r.unit) != (first.spec_digest, first.unit) for r in records):
        raise InvalidScientificProblem("compression merges records of ONE aggregation spec (same form, level, statistic, "
                                       "aggregator parameters) and unit only")
    if any(a.represented.end.seconds != b.represented.start.seconds for a, b in zip(records, records[1:])):
        raise InvalidScientificProblem("compressed records must be contiguous; a gap is not zero history")
    interval = TimeWindow(first.represented.start, records[-1].represented.end)
    preserved = frozenset.intersection(*(r.preserved_features for r in records))
    discarded = sorted({d for r in records for d in r.discarded} | {"per-window values inside the compressed interval"})
    represented = sum((r.represented_seconds for r in records), Fraction(0))
    resolved = sum((r.resolved_seconds for r in records), Fraction(0))
    base = dict(history_id=identifier(history_id, "history_id"), quantity_id=first.quantity_id, form_key=first.form_key, interval=interval,
                source_digests=tuple(r.digest for r in records), represented_seconds=represented, resolved_seconds=resolved)
    if any(r.status != "known" or r.value is None for r in records):
        return CompressedHistory(**base, value=None, status="unknown", retained=(), preserved=(), discarded=tuple(discarded))
    mags = [r.value.magnitude_in(first.unit) for r in records]
    if first.form_key in (AggregateForm.INTEGRAL_DOSE.value, AggregateForm.DWELL_ABOVE.value, AggregateForm.CYCLE_COUNT.value) or \
            first.form_key.startswith("domain_defined:"):
        value = Quantity(sum(mags), first.unit)
        retained = (("sum", repr(sum(mags))), ("windows", str(len(records))))
    elif first.form_key == AggregateForm.TIME_WEIGHTED_MEAN.value:
        w = [float(r.represented_seconds) for r in records]
        value = Quantity(sum(m * x for m, x in zip(mags, w)) / sum(w), first.unit)
        retained = (("mean", repr(value.magnitude)), ("windows", str(len(records))))
    elif first.form_key == AggregateForm.EXTREMA.value:
        pick = max if first.statistic == "max" else min
        value = Quantity(pick(mags), first.unit)
        retained = ((f"{first.statistic}_of_window_{first.statistic}", repr(pick(mags))), ("windows", str(len(records))))
    else:
        return CompressedHistory(**base, value=None, status="unknown", retained=(), preserved=(), discarded=tuple(discarded))
    return CompressedHistory(**base, value=value, status="known", retained=retained,
                             preserved=tuple(sorted(f for f in preserved)), discarded=tuple(discarded))
