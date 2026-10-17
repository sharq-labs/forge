"""A fan-in reduction must not depend on the unit its target port is declared in.

Reproduced defects:

* two 300 K sources SUM-reduced into a port declared in degC delivered
  53.7 degC == 326.85 K; the same graph declared in K delivered 600 K.  A sum
  of absolute values on a scale with a conventional zero is unit-dependent, so
  it is refused when the graph is built.  MEAN/MIN/MAX are affine-invariant and
  stay admitted; SUM on a ratio scale or of a difference unit stays admitted.
* INTERVAL fan-in reported each source's own confidence level for the combined
  bounds (20 sources at 0.95 -> "0.95"); only the union bound 1 - sum(1 - c_i)
  is guaranteed without an independence assumption.
* STANDARD-uncertainty MEAN fan-in into a degC port aborted, because the
  combined width was stated as a degC point.
"""

from __future__ import annotations

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.relaxation import relax_uncertainty
from engcore.execution.multiphysics.transfer import combine_fan_in_uncertainty
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.multiphysics.graph import ReductionOperator
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True)


def _graph(sink_unit, op, source_unit="K", sources="ab"):
    srcs = [_spec(p, [PortDefinition("t", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", source_unit)]) for p in sources]
    sink = _spec("sink", [PortDefinition("t_in", PortDirection.INPUT, PortKind.SCALAR, "temperature", sink_unit),
                          PortDefinition("o", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")])
    edges = tuple(CouplingEdge(f"e{p}", PortRef(p, "t"), PortRef("sink", "t_in"), reduction=op) for p in sources)
    return PhysicsGraph("fan-in-units", (*srcs, sink), edges)


def _delivered(sink_unit, op, values=(Quantity(300, "K"), Quantity(400, "K")), source_unit="K", uncertainty=UNKNOWN):
    graph = _graph(sink_unit, op, source_unit)
    seen = []

    def source(spec, value):
        return CallbackParticipant(spec, initialize=lambda *_: InitializationResult({"t": value}, {"t": uncertainty}),
                                   advance=lambda r: AdvanceResult(r.end, {"t": value}, {"t": uncertainty}, 1, True))

    def advance(request):
        seen.append((request.inputs["t_in"], request.input_uncertainty["t_in"]))
        return AdvanceResult(request.end, {"o": Quantity(0, "K")}, {"o": UNKNOWN}, 1, True)

    sink = CallbackParticipant(graph.participant("sink"),
                               initialize=lambda *_: InitializationResult({"o": Quantity(0, "K")}, {"o": UNKNOWN}),
                               advance=advance)
    plan = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    participants = {"a": source(graph.participant("a"), values[0]), "b": source(graph.participant("b"), values[1]),
                    "sink": sink}
    MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store).run(
        "r", external_inputs={}, external_uncertainty={})
    return seen[-1]


@pytest.mark.parametrize("unit", ["degC", "degF"])
def test_sum_fan_in_into_an_offset_scale_is_refused(unit):
    with pytest.raises(InvalidScientificProblem, match="conventional zero"):
        _graph(unit, ReductionOperator.SUM)


def test_sum_fan_in_from_offset_sources_into_a_ratio_scale_is_admitted_and_unit_invariant():
    assert _delivered("K", ReductionOperator.SUM)[0].magnitude_in("K") == pytest.approx(700.0)
    in_c = _delivered("K", ReductionOperator.SUM, (Quantity(26.85, "degC"), Quantity(126.85, "degC")), "degC")[0]
    assert in_c.magnitude_in("K") == pytest.approx(700.0)


def test_sum_fan_in_of_differences_is_admitted():
    got = _delivered("delta_degC", ReductionOperator.SUM, (Quantity(2, "delta_degC"), Quantity(3, "delta_degC")), "delta_degC")
    assert got[0].magnitude_in("delta_degC") == pytest.approx(5.0)


@pytest.mark.parametrize("op, expected", [(ReductionOperator.MEAN, 350.0), (ReductionOperator.MIN, 300.0),
                                          (ReductionOperator.MAX, 400.0)])
def test_affine_invariant_reductions_deliver_the_same_physical_value_in_either_unit(op, expected):
    assert _delivered("K", op)[0].magnitude_in("K") == pytest.approx(expected)
    assert _delivered("degC", op)[0].magnitude_in("K") == pytest.approx(expected)


def test_graph_payload_with_offset_sum_fan_in_does_not_round_trip_into_a_runnable_graph():
    good = _graph("K", ReductionOperator.SUM).to_dict()
    for participant in good["participants"]:
        for port in participant["ports"]:
            if port["port_id"] == "t_in":
                port["unit"] = "degC"
    with pytest.raises(InvalidScientificProblem, match="conventional zero"):
        PhysicsGraph.from_dict(good)


# ---- fan-in uncertainty ---------------------------------------------------------------


def _interval(level, lo=299.0, hi=301.0):
    return Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(lo, "K"), upper=Quantity(hi, "K"),
                       confidence_level=level, source="declared", method="declared interval")


def _combine(levels, op=ReductionOperator.MAX):
    sources = tuple(f"s{i}" for i in range(len(levels)))
    graph = _graph("K", op, sources=sources)
    edges = graph.edges
    return combine_fan_in_uncertainty(graph, edges, {e.edge_id: _interval(c) for e, c in zip(edges, levels)})


@pytest.mark.parametrize("op", [ReductionOperator.SUM, ReductionOperator.MEAN, ReductionOperator.MIN, ReductionOperator.MAX])
def test_interval_fan_in_states_only_the_union_bound_on_coverage(op):
    assert _combine([0.95, 0.95], op).confidence_level == pytest.approx(0.90)
    assert _combine([0.99, 0.95], op).confidence_level == pytest.approx(0.94)


def test_interval_fan_in_of_many_sources_claims_no_coverage_rather_than_a_source_level():
    assert _combine([0.95] * 20).confidence_level is None


def test_interval_fan_in_with_an_undeclared_level_claims_no_coverage():
    assert _combine([0.95, None]).confidence_level is None


def test_standard_mean_fan_in_into_an_offset_scale_states_its_width_as_a_spread():
    sigma = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.5, "K"), source="declared",
                        method="declared sigma")
    value, uq = _delivered("degC", ReductionOperator.MEAN, uncertainty=sigma)
    assert value.magnitude_in("K") == pytest.approx(350.0)
    assert uq.kind is UncertaintyKind.STANDARD
    assert uq.standard_uncertainty.magnitude_as_spread_in("K") == pytest.approx(0.5)
    assert str(uq.standard_uncertainty.units) == "kelvin"  # a spread, never a degC point


# ---- relaxation of iterates (same rules: union-bound coverage, widths as spreads) -----------


def test_relaxed_interval_states_the_union_bound_of_the_contributing_iterates():
    old, raw = _interval(0.95), _interval(0.95, 300.0, 302.0)
    mixed = relax_uncertainty(old, raw, factor=0.5, unit="K", edge_id="e")
    assert mixed.confidence_level == pytest.approx(0.90)
    assert relax_uncertainty(old, _interval(None), factor=0.5, unit="K", edge_id="e").confidence_level is None
    # w = 1 takes the raw iterate alone: its own level carries through
    assert relax_uncertainty(_interval(0.5), raw, factor=1.0, unit="K", edge_id="e").confidence_level == pytest.approx(0.95)


def test_relaxed_standard_width_on_an_offset_scale_is_a_spread():
    sigma = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.5, "K"), source="declared",
                        method="declared sigma")
    mixed = relax_uncertainty(sigma, sigma, factor=0.5, unit="degC", edge_id="e")
    assert str(mixed.standard_uncertainty.units) == "kelvin"
    assert mixed.standard_uncertainty.magnitude_as_spread_in("K") == pytest.approx(0.5)


def test_relaxed_interval_on_an_offset_scale_is_affine_invariant_under_over_relaxation():
    def interval(lo, hi, unit):
        return Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(lo, unit), upper=Quantity(hi, unit),
                           confidence_level=0.95, source="declared", method="declared interval")

    in_k = relax_uncertainty(interval(299, 301, "K"), interval(300, 302, "K"), factor=1.5, unit="K", edge_id="e")
    in_c = relax_uncertainty(interval(299, 301, "K"), interval(300, 302, "K"), factor=1.5, unit="degC", edge_id="e")
    assert in_c.lower.magnitude_in("K") == pytest.approx(in_k.lower.magnitude_in("K"))
    assert in_c.upper.magnitude_in("K") == pytest.approx(in_k.upper.magnitude_in("K"))
    assert in_c.confidence_level == pytest.approx(0.90)


def test_interval_mean_fan_in_on_an_offset_scale_matches_the_ratio_scale_result():
    def combine(unit):
        graph = _graph(unit, ReductionOperator.MEAN)
        return combine_fan_in_uncertainty(graph, graph.edges, {e.edge_id: _interval(0.95, 299.0 + i, 301.0 + i)
                                                                for i, e in enumerate(graph.edges)})

    in_k, in_c = combine("K"), combine("degC")
    assert in_c.lower.magnitude_in("K") == pytest.approx(in_k.lower.magnitude_in("K")) == pytest.approx(299.5)
    assert in_c.upper.magnitude_in("K") == pytest.approx(in_k.upper.magnitude_in("K")) == pytest.approx(301.5)
