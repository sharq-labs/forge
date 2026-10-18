"""M1A lineage/transfer adversarial probes. NOT RUN; fixtures are not provenance."""
from dataclasses import replace

import pytest

from engcore.data import InMemoryBulkStore
from engcore.data.errors import BulkDataIntegrityError
from engcore.numerical.core import NumericalRefusal
from engcore.numerical.mesh_adaptation import Grid1D, MeshLineage1D, MeshVersion1D, Bisection1D
from engcore.numerical.interval_transfer import AdaptiveMesh1D, MeshResourceKind, IntensiveTransferRule
from engcore.numerical import interval_transfer as implementation
from engcore.numerical.field_mapping import map_cells_1d
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields.semantics import FieldSemantics
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.semantics import ConservedQuantity, QuantitySemantics, QuantityRole
from engcore.scientific.units.quantity import Quantity

CONTEXT = "1"*64  # Deliberately a declared fixture binding, never measured/solver provenance.
U = Uncertainty.unknown("fixture source uncertainty not evaluated")


def semantics(kind="cell_integrated"):
    cq = ConservedQuantity("fixture:species_A", "kg")
    if kind == "cell_integrated":
        q = QuantitySemantics("fixture:species_A", "kg", (QuantityRole.INTEGRATED,), cq)
    elif kind == "cell_average_density":
        q = QuantitySemantics("fixture:species_A.density", "kg/m", (QuantityRole.DENSITY,))
    else:
        return FieldSemantics("intensive", QuantitySemantics("fixture:state", "K", (QuantityRole.INTENSIVE,)))
    return FieldSemantics(kind, q, "m", cq)


def session(grid=None):
    store = InMemoryBulkStore()
    runtime = AdaptiveMesh1D(grid or Grid1D((0,1,4), "m"), root_context="fixture:root",
                             coordinate_frame="fixture:axis", store=store)
    return runtime, store


def state(runtime, values=(2,6), kind="cell_integrated", unit=None):
    sem = semantics(kind)
    return runtime.register_state("q", values, semantics=sem, unit=unit or sem.quantity.unit,
                                  uncertainty=U, context_digest=CONTEXT)


def refine(runtime, ids=None):
    return runtime.refine(ids or tuple(c.cell_id for c in runtime.mesh.cells),
                           minimum_cell=Quantity(.01,"m"), max_ratio=10)


def test_refine_transfer_coarsen_transfer_back_on_unequal_cells():
    runtime, _ = session()
    root = runtime.mesh
    source = state(runtime)
    change = refine(runtime)
    fine, receipt = runtime.transfer_state(source, change)
    assert runtime.mesh.grid.nodes == (0,.5,1,2.5,4)
    assert runtime.read_state(fine) == pytest.approx((1,1,3,3))
    assert receipt.diagnostics.provenance["source_total"] == pytest.approx(8)
    assert receipt.diagnostics.provenance["target_total"] == pytest.approx(8)
    assert receipt.diagnostics.provenance["source_coverage_fraction"] == pytest.approx(1)
    assert receipt.diagnostics.provenance["target_coverage_fraction"] == pytest.approx(1)
    coarse_change = runtime.coarsen(change.change.bisections, max_ratio=10)
    coarse, returned = runtime.transfer_state(fine, coarse_change)
    assert runtime.mesh.grid.digest == root.grid.digest
    assert runtime.mesh.version_id != root.version_id
    assert runtime.read_state(coarse) == pytest.approx((2,6))
    assert returned.uncertainty.kind is UncertaintyKind.UNKNOWN
    assert coarse_change.change.after.parent_version_id == fine.mesh.version_id
    with pytest.raises(NumericalRefusal, match="stale"):
        runtime.read_state(source)  # Same geometry never reactivates an old version.


def test_density_and_amount_kinds_choose_different_transferred_values():
    density, _ = session()
    source = state(density, kind="cell_average_density")
    fine, receipt = density.transfer_state(source, refine(density))
    assert density.read_state(fine) == pytest.approx((2,2,6,6))
    assert receipt.diagnostics.provenance["source_total"] == pytest.approx(20)
    assert receipt.diagnostics.provenance["target_total"] == pytest.approx(20)


def test_coarsening_does_not_recover_unresolved_fine_information():
    runtime, _ = session()
    split = refine(runtime)
    fine = state(runtime, (1,3,9,3))
    coarse, _ = runtime.transfer_state(fine, runtime.coarsen(split.change.bisections, max_ratio=10))
    assert runtime.read_state(coarse) == pytest.approx((4,12))
    returned, receipt = runtime.transfer_state(coarse, refine(runtime))
    assert runtime.read_state(returned) == pytest.approx((2,2,6,6))
    assert runtime.read_state(returned) != pytest.approx((1,3,9,3))
    assert receipt.diagnostics.provenance["target_total"] == pytest.approx(16)


def test_lineage_and_coarsening_receipts_are_deterministic_but_not_cross_issued():
    a, _ = session()
    b, _ = session()
    sa, sb = state(a), state(b)
    ca, cb = refine(a), refine(b)
    assert ca.to_dict() == cb.to_dict()
    fa, ra = a.transfer_state(sa, ca)
    fb, rb = b.transfer_state(sb, cb)
    assert ra.to_dict() == rb.to_dict()
    aa, bb = a.coarsen(ca.change.bisections, max_ratio=10), b.coarsen(cb.change.bisections, max_ratio=10)
    assert aa.to_dict() == bb.to_dict()
    with pytest.raises(NumericalRefusal, match="unissued"):
        a.transfer_state(fb, aa)
    assert fa.record_id == fb.record_id  # Equal material does not establish local issuance.


def test_cache_and_coupling_history_are_actually_cleared_and_bindings_refuse():
    runtime, _ = session()
    original = state(runtime)
    cache, history = {"matrix":"fixture"}, ["old_secant"]
    matrix = runtime.bind_resource("linear", MeshResourceKind.SOLVER_CACHE, cache)
    iqn = runtime.bind_resource("iqn", MeshResourceKind.COUPLING_HISTORY, history)
    change = refine(runtime)
    assert cache == {} and history == []
    assert set(change.resources) == {matrix.record_id, iqn.record_id}
    assert change.fields == (original.record_id,)
    for binding in (matrix, iqn):
        with pytest.raises(NumericalRefusal, match="stale"):
            runtime.require_resource(binding)
    with pytest.raises(NumericalRefusal, match="stale"):
        runtime.read_state(original)


def test_missing_forged_or_conflicting_coarsening_records_refuse():
    runtime, _ = session()
    split = refine(runtime)
    record = split.change.bisections[0]
    for records in ((), (None,), (replace(record),), (record,record)):
        with pytest.raises(NumericalRefusal, match="issued|conflicting"):
            runtime.coarsen(records, max_ratio=10)
    foreign, _ = session()
    other_split = refine(foreign)
    with pytest.raises(NumericalRefusal, match="unissued"):
        runtime.coarsen(other_split.change.bisections, max_ratio=10)


def test_arbitrary_adjacent_cells_are_not_recorded_siblings():
    runtime, _ = session()
    split = refine(runtime)
    left = split.change.bisections[0].children[1]
    right = split.change.bisections[1].children[0]
    with pytest.raises(NumericalRefusal, match="geometry or ancestry"):
        Bisection1D(split.change.bisections[0].parent, (left,right))
    # An ancestor cannot coarsen while one of its children is itself split.
    refine(runtime, (runtime.mesh.cells[0].cell_id,))
    with pytest.raises(NumericalRefusal, match="active adjacent siblings"):
        runtime.coarsen((split.change.bisections[0],), max_ratio=10)


def test_invalid_parent_child_geometry_and_missing_ancestry_refuse():
    runtime, _ = session()
    split = refine(runtime)
    record = split.change.bisections[0]
    bad = replace(record.children[0], right=record.children[0].right+.1)
    with pytest.raises(NumericalRefusal, match="geometry or ancestry"):
        replace(record, children=(bad, record.children[1]))
    with pytest.raises(NumericalRefusal, match="issuance"):
        MeshVersion1D.from_dict(split.change.after.to_dict())
    with pytest.raises(NumericalRefusal, match="issuance"):
        MeshVersion1D.from_dict({"nodes":[0,1,4]})


def test_nested_record_tampering_poisoned_lineage_is_fail_closed():
    runtime, _ = session()
    original = state(runtime)
    split = refine(runtime)
    object.__setattr__(split.change.bisections[0].children[0], "parent_id", "forged")
    with pytest.raises(NumericalRefusal, match="tampered|unissued"):
        runtime.transfer_state(original, split)
    with pytest.raises(NumericalRefusal, match="tampered|unissued"):
        runtime.coarsen(split.change.bisections, max_ratio=10)


def test_unrelated_mesh_or_fake_change_never_authorizes_transfer():
    runtime, _ = session()
    source = state(runtime)
    split = refine(runtime)
    other, _ = session(Grid1D((0,2,4), "m"))
    with pytest.raises(NumericalRefusal, match="unissued"):
        runtime.transfer_state(source, replace(split, change=replace(split.change, after=other.mesh)))
    with pytest.raises(NumericalRefusal, match="unissued"):
        runtime.transfer_state(source, replace(split))


def test_stale_change_and_superseded_source_cannot_execute():
    runtime, _ = session()
    old = state(runtime)
    newer = state(runtime, (3,7))
    split = refine(runtime)
    with pytest.raises(NumericalRefusal, match="exact issued source"):
        runtime.transfer_state(old, split)
    fine, _ = runtime.transfer_state(newer, split)
    refine(runtime)
    with pytest.raises(NumericalRefusal, match="immediate mesh change"):
        runtime.transfer_state(newer, split)
    with pytest.raises(NumericalRefusal, match="stale"):
        runtime.read_state(fine)


def test_partial_coverage_cannot_be_imported_as_a_lineage_transition():
    runtime, _ = session()
    source = state(runtime)
    split = refine(runtime)
    foreign, _ = session(Grid1D((0,1,3), "m"))
    with pytest.raises(NumericalRefusal, match="unissued"):
        runtime.transfer_state(source, replace(split, change=replace(split.change, after=foreign.mesh)))
    with pytest.raises(InvalidScientificProblem, match="partial coverage"):
        map_cells_1d((2,6), Grid1D((0,1,4),"m"), Grid1D((0,1,3),"m"),
            source_semantics=semantics(), target_semantics=semantics(), source_unit="kg", target_unit="kg",
            source_fingerprint=Grid1D((0,1,4),"m").digest, target_fingerprint=Grid1D((0,1,3),"m").digest,
            coordinate_frame="fixture:axis")


def test_affine_units_and_ambiguous_intensive_transfer_refuse():
    runtime, _ = session()
    with pytest.raises(NumericalRefusal, match="affine units refused"):
        state(runtime, (0,100), kind="intensive", unit="degC")
    source = state(runtime, (300,400), kind="intensive")
    change = refine(runtime)
    with pytest.raises(NumericalRefusal, match="explicit qualified"):
        runtime.transfer_state(source, change)
    target, receipt = runtime.transfer_state(source, change, intensive_rule=IntensiveTransferRule.PIECEWISE_CONSTANT_OVERLAP)
    assert runtime.read_state(target) == pytest.approx((300,300,400,400))
    assert receipt.diagnostics.conservation_relative_error is None
    assert "source_total" not in receipt.diagnostics.provenance
    assert target.uncertainty.kind is UncertaintyKind.UNKNOWN


def test_byte_corruption_and_token_substitution_refuse():
    runtime, store = session()
    source = state(runtime)
    with pytest.raises(NumericalRefusal, match="unissued"):
        runtime.read_state(replace(source))
    store.corrupt(source.data, b"x"*source.data.byte_length)
    with pytest.raises(BulkDataIntegrityError):
        runtime.read_state(source)
    split = refine(runtime)
    with pytest.raises(BulkDataIntegrityError):
        runtime.transfer_state(source, split)


def test_incorrect_conservation_claim_cannot_override_actual_values(monkeypatch):
    runtime, _ = session()
    source = state(runtime)
    split = refine(runtime)
    actual_mapper = implementation.map_cells_1d
    def wrong(*args, **kwargs):
        result = actual_mapper(*args, **kwargs)
        return replace(result, values=tuple(x*2 for x in result.values))  # Reported zero residual unchanged.
    monkeypatch.setattr(implementation, "map_cells_1d", wrong)
    with pytest.raises(NumericalRefusal, match="actual transferred amounts"):
        runtime.transfer_state(source, split)
    with pytest.raises(NumericalRefusal, match="stale"):
        runtime.read_state(source)


def test_explicit_refinement_policy_and_unchanged_legacy_grid_identity():
    grid = Grid1D((0,1,4),"m")
    original = grid.to_dict(), grid.digest
    lineage = MeshLineage1D(grid, root_context="fixture:root", coordinate_frame="fixture:axis")
    with pytest.raises(NumericalRefusal, match="minimum cell"):
        lineage.refine((lineage.current.cells[0].cell_id,), minimum_cell=Quantity(1,"m"), max_ratio=10)
    with pytest.raises(NumericalRefusal, match="neighbour ratio"):
        lineage.refine((lineage.current.cells[0].cell_id,), minimum_cell=Quantity(.01,"m"), max_ratio=2)
    assert (grid.to_dict(),grid.digest) == original
    assert lineage.current.operation == "root"


def test_coordinate_frame_is_bound_to_root_mesh_and_state_identity():
    a, _ = session()
    b = AdaptiveMesh1D(a.mesh.grid, root_context="fixture:root", coordinate_frame="fixture:other_axis",
                       store=InMemoryBulkStore())
    sa, sb = state(a), state(b)
    assert a.mesh.grid.digest == b.mesh.grid.digest
    assert a.mesh.root_id != b.mesh.root_id
    assert a.mesh.version_id != b.mesh.version_id
    assert sa.record_id != sb.record_id


def test_quantified_source_uncertainty_does_not_quantify_transfer_error():
    runtime, _ = session()
    known = Uncertainty(UncertaintyKind.STANDARD, standard_uncertainty=Quantity(.1,"kg"), method="fixture only")
    source = runtime.register_state("q", (2,6), semantics=semantics(), unit="kg", uncertainty=known,
                                    context_digest=CONTEXT)
    target, receipt = runtime.transfer_state(source, refine(runtime))
    assert target.uncertainty.kind is UncertaintyKind.UNKNOWN
    assert receipt.uncertainty.kind is UncertaintyKind.UNKNOWN


def test_old_transfer_cannot_overwrite_newer_current_state_or_be_replayed():
    runtime, _ = session()
    source = state(runtime)
    change = refine(runtime)
    fine, _ = runtime.transfer_state(source, change)
    newer = state(runtime, (10,20,30,40))
    with pytest.raises(NumericalRefusal, match="already populated|consumed"):
        runtime.transfer_state(source, change)
    assert runtime.read_state(newer) == pytest.approx((10,20,30,40))
    with pytest.raises(NumericalRefusal, match="superseded"):
        runtime.read_state(fine)


@pytest.mark.parametrize("uncertainty", [
    Uncertainty(UncertaintyKind.STANDARD, standard_uncertainty=Quantity(.1,"s"), method="fixture only"),
    Uncertainty(UncertaintyKind.INTERVAL, lower=Quantity(1,"s"), upper=Quantity(3,"s"), method="fixture only"),
])
def test_known_uncertainty_must_match_state_dimension(uncertainty):
    runtime, _ = session()
    with pytest.raises(NumericalRefusal, match="uncertainty dimensions"):
        runtime.register_state("q", (2,6), semantics=semantics(), unit="kg", uncertainty=uncertainty,
                                context_digest=CONTEXT)


def test_target_units_and_independent_totals_remain_bound():
    runtime, _ = session()
    source = state(runtime)
    target, receipt = runtime.transfer_state(source, refine(runtime), target_unit="g")
    assert runtime.read_state(target) == pytest.approx((1000,1000,3000,3000))
    assert receipt.diagnostics.provenance["source_total"] == pytest.approx(8)
    assert receipt.diagnostics.provenance["target_total"] == pytest.approx(8)


def test_intensive_mapping_cannot_claim_a_conserved_measure(monkeypatch):
    runtime, _ = session()
    source = state(runtime, (300,400), kind="intensive")
    change = refine(runtime)
    mapper = implementation.map_cells_1d
    def false_claim(*args, **kwargs):
        result = mapper(*args, **kwargs)
        return replace(result, diagnostics=replace(result.diagnostics, conservation_relative_error=0))
    monkeypatch.setattr(implementation, "map_cells_1d", false_claim)
    with pytest.raises(NumericalRefusal, match="cannot claim conservation"):
        runtime.transfer_state(source, change, intensive_rule=IntensiveTransferRule.PIECEWISE_CONSTANT_OVERLAP)


def test_vertex_values_are_not_silently_reinterpreted_as_interval_cells():
    runtime, _ = session()
    with pytest.raises(NumericalRefusal, match="scalar cells"):
        state(runtime, (300,350,400), kind="intensive")


@pytest.mark.parametrize("missing", ["parent", "bisection", "change"])
def test_missing_authoritative_ancestry_poisoned_session_refuses(missing):
    runtime, _ = session()
    source = state(runtime)
    split = refine(runtime)
    issuer = runtime._lineage  # Adversarial loss in the private authority registry.
    key = {"parent": split.change.before.record_id, "bisection": split.change.bisections[0].record_id,
           "change": split.change.record_id}[missing]
    issuer._issued._records.pop(key)
    with pytest.raises(NumericalRefusal, match="missing|unissued"):
        runtime.transfer_state(source, split)


def test_wrong_key_alias_cannot_hide_a_missing_bisection():
    runtime, _ = session()
    source = state(runtime)
    split = refine(runtime)
    first, second = split.change.bisections
    records = runtime._lineage._issued._records
    records[first.record_id] = records[second.record_id]
    with pytest.raises(NumericalRefusal, match="conflicting.*registry key"):
        runtime.transfer_state(source, split)
