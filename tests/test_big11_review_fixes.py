"""BIG 11 review fixes outside the provider boundary: contracts, structural cases, long-history compression."""

from __future__ import annotations

import importlib.util
import pathlib
from dataclasses import replace
from fractions import Fraction

import pytest

from engcore.coupling import ParticipantStateContract, StateCompleteness
from engcore.multiscale import AggregationSpec, OutputSample, OutputSeries, RepresentativeWindow, aggregate, compress_history
from engcore.pde.cases import RegionMaterial
from engcore.scenarios import AggregateForm, TimeWindow
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("multiscale_reference_b11", str(HERE / "multiscale_reference.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
DAY, HOUR = R.DAY, R.HOUR


def test_reset_state_is_declared_and_part_of_contract_identity():
    kw = dict(participant_id="cell", declared_state=("soc",), evolved_state=("soc",), completeness=StateCompleteness.DECLARED_COMPLETE,
              basis="fresh simulation per execution")
    plain = ParticipantStateContract(**kw)
    reset = ParticipantStateContract(**kw, reset_state=("particle_concentration_profiles", "cell_temperature"))
    assert reset.to_dict()["reset_state"] == ["cell_temperature", "particle_concentration_profiles"]
    assert reset.to_dict() != plain.to_dict()
    assert ParticipantStateContract.from_dict(reset.to_dict()) == reset
    assert "reset_state" not in plain.to_dict()  # contracts without reset state keep their earlier digests


def _resolved(pid, q, status="known"):
    from engcore.materials.properties import PropertyDerivation, ResolvedProperty
    from engcore.scenarios import NamedQuantity

    known = status == "known"
    return ResolvedProperty(pid, status, PropertyDerivation.SOURCED if known else PropertyDerivation.NONE,
                            NamedQuantity(pid, q) if known else None, "a" * 64, "b" * 64, "c" * 64, (), (), (), None)


def test_region_material_is_the_big5_records_not_numbers_and_digests():
    E, nu = _resolved("youngs_modulus", Quantity(70e9, "Pa")), _resolved("poisson_ratio", Quantity(0.33, "dimensionless"))
    m = RegionMaterial("plate", E, nu)
    assert m.youngs_modulus == E.value.value and m.provenance == (E.digest, nu.digest)  # value and digest are ONE object
    with pytest.raises(InvalidScientificProblem, match="not a number"):
        RegionMaterial("plate", Quantity(70e9, "Pa"), nu)
    with pytest.raises(InvalidScientificProblem, match="not a number"):
        RegionMaterial("plate", nu, E)  # records swapped
    with pytest.raises(InvalidScientificProblem, match="not a number"):
        RegionMaterial("plate", _resolved("youngs_modulus", None, status="unknown"), nu)


def test_non_extensive_domain_aggregates_are_never_summed_by_compression():
    spec = AggregationSpec("tmax", "heater_temperature", AggregateForm.EXTREMA, statistic="max")
    recs = []
    for d in (0, 1):
        w = TimeWindow(R.p(d * DAY), R.p((d + 1) * DAY))
        rep = RepresentativeWindow(f"r{d}", w, w, Fraction(1), "fully_resolved", (), "p", "x")
        series = OutputSeries("heater_temperature", "K", tuple(
            OutputSample(TimeWindow(R.p(d * DAY + i * HOUR), R.p(d * DAY + (i + 1) * HOUR)), Quantity(300.0 + i, "K")) for i in range(24)),
            "e" * 64)
        recs.append(aggregate(spec, [(rep, series)], w))
    out = compress_history("peak", [replace(r, form_key="domain_defined:peak_index", extensive=False) for r in recs])
    assert out.status == "unknown" and out.value is None  # a max-like domain value summed over windows would be nonsense
    summed = compress_history("dose", [replace(r, form_key="domain_defined:dose", extensive=True) for r in recs])
    assert summed.status == "known" and summed.value.magnitude == pytest.approx(2 * 323.0)


def test_non_extensive_domain_aggregate_over_several_unrepeated_tiles_is_unknown():
    from engcore.multiscale.aggregation import DomainAggregator
    from engcore.scenarios.lifecycle import HistoryFeature

    class Peak(DomainAggregator):
        aggregator_id, version, parameters = "peak", "1", ()
        required_source_features = frozenset({HistoryFeature.MEAN})
        preserves = frozenset({HistoryFeature.MEAN})
        extensive, output_unit = False, "K"

        def compute(self, samples):
            return Quantity(max(v.magnitude_in("K") for _, v in samples), "K")

    spec = AggregationSpec("peak", "heater_temperature", AggregateForm.DOMAIN_DEFINED, aggregator=Peak())
    parts = []
    for d in (0, 1):
        w = TimeWindow(R.p(d * DAY), R.p((d + 1) * DAY))
        rep = RepresentativeWindow(f"r{d}", w, w, Fraction(1), "fully_resolved", (), "p", "x")
        parts.append((rep, OutputSeries("heater_temperature", "K", tuple(
            OutputSample(TimeWindow(R.p(d * DAY + i * HOUR), R.p(d * DAY + (i + 1) * HOUR)), Quantity(300.0 + i, "K")) for i in range(24)),
            "e" * 64)))
    rec = aggregate(spec, parts, TimeWindow(R.p(0), R.p(2 * DAY)))
    assert rec.status == "unknown" and rec.value is None  # never peak1 + peak2
    assert aggregate(spec, parts[:1], TimeWindow(R.p(0), R.p(DAY))).value.magnitude == 323.0
