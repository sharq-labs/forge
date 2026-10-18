"""A-1/A-2/A-13 design probes and regressions. Build-First: NOT RUN.

Callbacks are unqualified fixtures, never physical validation or domain support.
"""
from dataclasses import replace

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.transfer import TransferEngine
from engcore.scientific.composition.conversion import EnergyConversion, LossPath
from engcore.scientific.conservation import BalanceTerm, ConservationBalance
from engcore.scientific.errors import InvalidScientificProblem, ScientificCoreError, ScientificValidationError
from engcore.scientific.fields.definition import FieldDefinition, FieldLocation
from engcore.scientific.fields.mesh import StructuredMesh
from engcore.scientific.multiphysics.mapping import FieldMappingDefinition
from engcore.scientific.multiphysics import (
    BalanceSide, ConservationTermBinding, CoupledConservation, CouplingEdge, CouplingPlan,
    CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection,
    PortKind, PortRef, TimePolicy, TransferMeasure,
)
from engcore.scientific.multiphysics.conservation import ContributionKind
from engcore.scientific.semantics import (
    ConservedQuantity, QuantityRole, QuantitySemantics, QuantityTransport, TransportKind,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

U = Uncertainty.unknown("design fixture; no quantified uncertainty")


def meaning(name, unit, *roles, conserved=None):
    return QuantitySemantics(name, unit, roles, conserved)


def port(name, direction, sem=None, *, quantity="legacy", unit=None):
    return PortDefinition(name, PortDirection(direction), PortKind.SCALAR, quantity,
                          unit or sem.unit, semantics=sem)


def spec(pid, ports):
    return ParticipantSpec(pid, "fixture-model", "1", "fixture-realization", "1", "fixture", "1", "callback", "1", tuple(ports))


def graph(source, target, transport=None, *, source_name="q", target_name="q", unit=None, balances=(), **edge_kw):
    a = spec("a", [port("out", "output", source, quantity=source_name, unit=unit)])
    b = spec("b", [port("in", "input", target, quantity=target_name, unit=unit)])
    edge = CouplingEdge("e", PortRef("a", "out"), PortRef("b", "in"), transport=transport, **edge_kw)
    return PhysicsGraph("semantic", (a, b), (edge,), conservation=balances)


def transfer(g, value, uncertainty=U):
    store = InMemoryBulkStore()
    engine = TransferEngine(g, resolver=BulkDataResolver(store), store=store)
    return engine.transfer(g.edge("e"), value, uncertainty, instant="0 s")


def test_stiffness_cannot_feed_surface_tension_even_when_raw_labels_and_dimensions_match():
    a = meaning("mechanics:stiffness", "N/m", QuantityRole.EXTENSIVE)
    b = meaning("interfaces:surface_tension", "N/m", QuantityRole.INTENSIVE)
    with pytest.raises(InvalidScientificProblem, match="different quantity meanings/roles"):
        graph(a, b, QuantityTransport("signal"))


def test_legacy_dimension_and_prose_are_not_sufficient_to_relabel_stiffness():
    with pytest.raises(InvalidScientificProblem, match="legacy quantity meanings differ"):
        graph(None, None, source_name="spring_stiffness", target_name="surface_tension", unit="N/m",
              transport_declaration="delivered whole")


def test_force_is_explicit_effort_signal_without_energy_transport_or_prose():
    force = meaning("mechanics:contact_force", "N", QuantityRole.EFFORT)
    g = graph(force, force, QuantityTransport("signal"), source_name="spring_force", target_name="contact_load")
    result = transfer(g, Quantity(12, "N"))
    assert result.value.magnitude_in("N") == 12
    assert not result.losses and g.edge("e").conversion is None and not g.edge("e").transport_declaration


def test_dimensional_match_does_not_override_a_role_mismatch():
    effort = meaning("fixture:x", "N", QuantityRole.EFFORT)
    flow = meaning("fixture:x", "N", QuantityRole.FLOW)
    with pytest.raises(InvalidScientificProblem, match="meanings/roles"):
        graph(effort, flow, QuantityTransport("signal"))


def test_missing_or_mixed_semantics_are_refused():
    sem = meaning("fixture:temperature", "K", QuantityRole.INTENSIVE)
    for source, target, transport in ((sem, None, QuantityTransport("signal")),
                                      (None, sem, None), (sem, sem, None)):
        with pytest.raises(InvalidScientificProblem, match="both port semantics"):
            graph(source, target, transport, unit="K")


def test_prose_or_legacy_conversion_cannot_override_typed_transport():
    sem = meaning("fixture:force", "N", QuantityRole.EFFORT)
    with pytest.raises(InvalidScientificProblem, match="legacy conversion/prose"):
        graph(sem, sem, QuantityTransport("signal"), transport_declaration="trust this")


@pytest.mark.parametrize("identifier,unit", [("physics:energy", "J"), ("physics:mass", "kg"),
    ("physics:charge", "C"), ("physics:momentum.axis_x", "kg*m/s"), ("chemistry:species_A.amount", "mol")])
def test_conservation_uses_declared_meaning_for_each_scalar_measure(identifier, unit):
    conserved = ConservedQuantity(identifier, unit)
    sem = meaning(identifier + ".carried", unit, QuantityRole.EXTENSIVE, conserved=conserved)
    balance = ConservationBalance("b", (BalanceTerm("in", Quantity(10, unit), semantics=sem),),
        (BalanceTerm("out", Quantity(8, unit), semantics=sem), BalanceTerm("loss", Quantity(2, unit), semantics=sem)),
        Quantity(1e-10, unit), conserved_quantity=conserved)
    assert balance.closed and balance.to_validation_check().establishes is None
    assert ConservationBalance.from_dict(balance.to_dict()) == balance


def test_same_dimension_species_are_not_interchangeable_in_a_balance():
    a, b = ConservedQuantity("chemistry:species_A", "mol"), ConservedQuantity("chemistry:species_B", "mol")
    sa = meaning("chemistry:A", "mol", QuantityRole.EXTENSIVE, conserved=a)
    sb = meaning("chemistry:B", "mol", QuantityRole.EXTENSIVE, conserved=b)
    with pytest.raises(ScientificValidationError, match="precise conserved meaning"):
        ConservationBalance("false", (BalanceTerm("a", Quantity(1, "mol"), semantics=sa),),
            (BalanceTerm("b", Quantity(1, "mol"), semantics=sb),), Quantity(0, "mol"), conserved_quantity=a)


def bindings():
    return (ConservationTermBinding("supplied", "e", BalanceSide.LEFT, TransferMeasure.SOURCE,
                                   contribution=ContributionKind.SOURCE),
            ConservationTermBinding("arrived", "e", BalanceSide.RIGHT, TransferMeasure.RECEIVED,
                                   contribution=ContributionKind.OUTFLOW),
            ConservationTermBinding("leak", "e", BalanceSide.RIGHT, TransferMeasure.LOSS,
                                   loss_form="fixture:leak", contribution=ContributionKind.LOSS))


@pytest.mark.parametrize("identifier,unit", [("chemistry:species_A.rate", "mol/s"), ("electrical:charge.rate", "C/s")])
def test_species_or_charge_partition_has_realized_named_losses_and_unknown_uncertainty(identifier, unit):
    cq = ConservedQuantity(identifier, unit)
    sem = meaning(identifier + ".flow", unit, QuantityRole.FLOW, conserved=cq)
    partition = QuantityTransport("conserved", cq, 0.8, (LossPath("fixture:leak", 0.2),))
    balance = CoupledConservation("species-or-charge", bindings(), Quantity(1e-10, unit), conserved_quantity=cq)
    g = graph(sem, sem, partition, balances=(balance,))
    result = transfer(g, Quantity(10, unit))
    assert result.value.magnitude_in(unit) == pytest.approx(8)
    assert result.losses["fixture:leak"].magnitude_in(unit) == pytest.approx(2)
    assert result.uncertainty.kind is UncertaintyKind.UNKNOWN
    assert CoupledConservation.from_dict(balance.to_dict()) == balance
    store = InMemoryBulkStore()
    plan = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                       TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("a", "b"))
    participants = {pid: CallbackParticipant(g.participant(pid),
        initialize=(lambda *args: InitializationResult({"out": Quantity(10, unit)}, {"out": U})) if pid == "a" else
                   (lambda *args: InitializationResult({}, {})),
        advance=(lambda req: AdvanceResult(req.end, {"out": Quantity(10, unit)}, {"out": U}, 1, True)) if pid == "a" else
                (lambda req: AdvanceResult(req.end, {}, {}, 1, True))) for pid in ("a", "b")}
    run = MultiphysicsRuntime(g, plan, participants, resolver=BulkDataResolver(store), store=store).run("fixture", external_inputs={})
    assert run.final_outputs["_conservation_status"]["required"] == "pass"
    # This checks the realized transfer partition, not independent species/charge physics.


def test_coupled_balance_cannot_substitute_another_conserved_meaning():
    cq = ConservedQuantity("chemistry:A.rate", "mol/s")
    wrong = ConservedQuantity("chemistry:B.rate", "mol/s")
    sem = meaning("chemistry:A.flow", "mol/s", QuantityRole.FLOW, conserved=cq)
    balance = CoupledConservation("wrong", bindings(), Quantity(1e-10, "mol/s"), conserved_quantity=wrong)
    with pytest.raises(InvalidScientificProblem, match="conserved meanings disagree"):
        graph(sem, sem, QuantityTransport("conserved", cq, 0.8, (LossPath("fixture:leak", 0.2),)), balances=(balance,))


def test_unknown_delivery_is_not_lossless_and_unaccounted_loss_is_not_zero():
    cq = ConservedQuantity("physics:mass", "kg")
    with pytest.raises(InvalidScientificProblem, match="UNKNOWN"):
        QuantityTransport("conserved", cq).transfer(Quantity(10, "kg"))
    with pytest.raises(InvalidScientificProblem, match="all input"):
        QuantityTransport("conserved", cq, 0.8)


def test_source_and_loss_kinds_do_not_manufacture_missing_measures():
    with pytest.raises(InvalidScientificProblem, match="realized LOSS"):
        ConservationTermBinding("false-loss", "e", "right", "received", contribution="loss")
    with pytest.raises(InvalidScientificProblem, match="wrong equation side"):
        ConservationTermBinding("false-source", "e", "right", "source", contribution="source")


def test_existing_exact_name_thermal_transfer_and_legacy_bytes_are_retained():
    g = graph(None, None, source_name="temperature", target_name="temperature", unit="K")
    result = transfer(g, Quantity(300, "K"))
    assert result.value.magnitude_in("K") == 300
    p = g.participant("a").port("out")
    payload = p.to_dict()
    assert payload["schema"] == "multiphysics_port/1" and "semantics" not in payload
    assert PortDefinition.from_dict(payload) == p
    assert PhysicsGraph.from_dict(g.to_dict()).fingerprint() == g.fingerprint()


def test_legacy_aliases_require_migration_and_matched_conversion_forms_remain_explicit():
    conversion = EnergyConversion("declared", "electrical", "thermal", "W", 1.0)
    with pytest.raises(InvalidScientificProblem, match="semantic migration"):
        graph(None, None, unit="W", source_name="power", target_name="heat", conversion=conversion)
    g = graph(None, None, unit="W", source_name="electrical", target_name="thermal", conversion=conversion)
    assert transfer(g, Quantity(3, "W")).value.magnitude_in("W") == 3


def test_typed_records_roundtrip_and_cannot_downgrade_or_omit_semantics():
    sem = meaning("fixture:force", "N", QuantityRole.EFFORT)
    g = graph(sem, sem, QuantityTransport("signal"))
    assert PhysicsGraph.from_dict(g.to_dict()).fingerprint() == g.fingerprint()
    cq = ConservedQuantity("fixture:mass", "kg")
    mass = meaning("fixture:mass", "kg", QuantityRole.EXTENSIVE, conserved=cq)
    term = BalanceTerm("amount", Quantity(1, "kg"), semantics=mass)
    balance = ConservationBalance("mass", (term,), (replace(term, name="amount-out"),), Quantity(1e-10, "kg"), conserved_quantity=cq)
    coupled = CoupledConservation("mass", bindings(), Quantity(1e-10, "kg"), conserved_quantity=cq)
    for record, cls, key in ((g.participant("a").port("out"), PortDefinition, "semantics"),
                              (g.edge("e"), CouplingEdge, "transport"),
                              (term, BalanceTerm, "semantics"),
                              (balance, ConservationBalance, "conserved_quantity"),
                              (bindings()[0], ConservationTermBinding, "contribution"),
                              (coupled, CoupledConservation, "conserved_quantity")):
        payload = record.to_dict()
        assert cls.from_dict(payload) == record
        assert payload["schema"].endswith("/2")
        downgraded = {**payload, "schema": payload["schema"].rsplit("/", 1)[0] + "/1"}
        with pytest.raises(InvalidScientificProblem, match="explicit /2"):
            cls.from_dict(downgraded)
        incomplete = dict(payload)
        incomplete.pop(key)
        with pytest.raises(InvalidScientificProblem, match="requires"):
            cls.from_dict(incomplete)
        with pytest.raises(ScientificCoreError, match="unsupported schema"):
            cls.from_dict({**payload, "schema": "future/99"})


def test_semantic_unit_must_match_port_and_conserved_measure():
    force = meaning("fixture:force", "N", QuantityRole.EFFORT)
    with pytest.raises(InvalidScientificProblem, match="dimension"):
        port("bad", "input", force, unit="K")
    with pytest.raises(InvalidScientificProblem, match="dimensions differ"):
        meaning("fixture:mass", "kg", QuantityRole.EXTENSIVE,
                conserved=ConservedQuantity("fixture:energy", "J"))


def test_typed_fields_refuse_until_declared_field_kind_mapping_is_reviewed():
    mesh = StructuredMesh("mesh", Quantity(1, "m"), Quantity(1, "m"), 3, 3)
    field = FieldDefinition("temperature", "K", "mesh", FieldLocation.CELL)
    sem = meaning("fixture:temperature", "K", QuantityRole.INTENSIVE)
    a = spec("a", [PortDefinition("out", "output", "field", "temperature", "K", field, semantics=sem)])
    b = spec("b", [PortDefinition("in", "input", "field", "temperature", "K", field, semantics=sem)])
    edge = CouplingEdge("e", PortRef("a", "out"), PortRef("b", "in"),
                        mapping=FieldMappingDefinition("identity", "identity"), transport=QuantityTransport("signal"))
    with pytest.raises(InvalidScientificProblem, match="A-3"):
        PhysicsGraph("typed-field", (a, b), (edge,), supports=(mesh,))


@pytest.mark.parametrize("source_uncertainty", [
    Uncertainty(UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.1, "kg"),
                method="declared fixture uncertainty; no coefficient UQ"),
    Uncertainty(UncertaintyKind.INTERVAL, lower=Quantity(9, "kg"), upper=Quantity(11, "kg"),
                method="declared fixture uncertainty; no coefficient UQ"),
])
def test_quantified_input_does_not_quantify_unknown_partition_coefficients(source_uncertainty):
    cq = ConservedQuantity("fixture:mass", "kg")
    sem = meaning("fixture:mass", "kg", QuantityRole.EXTENSIVE, conserved=cq)
    g = graph(sem, sem, QuantityTransport("conserved", cq, 0.8, (LossPath("fixture:leak", 0.2),)))
    result = transfer(g, Quantity(10, "kg"), source_uncertainty)
    assert result.uncertainty.kind is UncertaintyKind.UNKNOWN


def test_meaning_role_conserved_identity_and_partition_are_material():
    cq = ConservedQuantity("fixture:mass", "kg")
    a = meaning("fixture:amount", "kg", QuantityRole.EXTENSIVE, conserved=cq)
    t = QuantityTransport("conserved", cq, 0.8, (LossPath("fixture:leak", 0.2),))
    original = graph(a, a, t).fingerprint()
    for changed in (replace(a, meaning_id="fixture:other_amount"), replace(a, roles=(QuantityRole.INTEGRATED,))):
        assert graph(changed, changed, t).fingerprint() != original
    other_cq = ConservedQuantity("fixture:other_mass", "kg")
    changed = replace(a, conserved_quantity=other_cq)
    assert graph(changed, changed, replace(t, conserved_quantity=other_cq)).fingerprint() != original
    assert graph(a, a, replace(t, delivered_fraction=0.9, losses=(LossPath("fixture:leak", 0.1),))).fingerprint() != original


def test_power_is_computed_by_a_domain_owned_participant_not_inferred_from_dimensions():
    force = meaning("mechanics:force.axis_x", "N", QuantityRole.EFFORT)
    velocity = meaning("mechanics:velocity.axis_x", "m/s", QuantityRole.INTENSIVE)
    conserved = ConservedQuantity("physics:energy.rate", "W")
    power = meaning("mechanics:power", "W", QuantityRole.FLOW, conserved=conserved)
    specs = {
        "force": spec("force", [port("f", "output", force)]),
        "motion": spec("motion", [port("v", "output", velocity)]),
        "law": spec("law", [port("f", "input", force), port("v", "input", velocity), port("p", "output", power)]),
        "load": spec("load", [port("p", "input", power), port("seen", "output", power)]),
    }
    edges = (CouplingEdge("f", PortRef("force", "f"), PortRef("law", "f"), transport=QuantityTransport("signal")),
             CouplingEdge("v", PortRef("motion", "v"), PortRef("law", "v"), transport=QuantityTransport("signal")),
             CouplingEdge("p", PortRef("law", "p"), PortRef("load", "p"), transport=QuantityTransport("conserved", conserved, 1.0)))
    g = PhysicsGraph("power-fixture", tuple(specs.values()), edges)
    def initial(values):
        return lambda *args: InitializationResult(values, {key: U for key in values})
    def advanced(values_of):
        return lambda req: AdvanceResult(req.end, values_of(req), {key: U for key in values_of(req)}, 1, True)
    # This fixture law stands in for a Domain Pack model/realization. It is not
    # a qualified model and cannot supply evidence for a mechanical capability.
    participants = {
        "force": CallbackParticipant(specs["force"], initialize=initial({"f": Quantity(2, "N")}),
            advance=advanced(lambda req: {"f": Quantity(2, "N")})),
        "motion": CallbackParticipant(specs["motion"], initialize=initial({"v": Quantity(3, "m/s")}),
            advance=advanced(lambda req: {"v": Quantity(3, "m/s")})),
        "law": CallbackParticipant(specs["law"], initialize=initial({"p": Quantity(0, "W")}),
            advance=advanced(lambda req: {"p": req.inputs["f"] * req.inputs["v"]})),
        "load": CallbackParticipant(specs["load"], initialize=initial({"seen": Quantity(0, "W")}),
            advance=advanced(lambda req: {"seen": req.inputs["p"]})),
    }
    plan = CouplingPlan("power-fixture", "explicit", "serial",
        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("force", "motion", "law", "load"))
    store = InMemoryBulkStore()
    result = MultiphysicsRuntime(g, plan, participants, resolver=BulkDataResolver(store), store=store).run("power", external_inputs={})
    assert result.final_outputs["load.seen"]["magnitude"] == pytest.approx(6)
