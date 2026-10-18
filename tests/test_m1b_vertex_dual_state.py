"""M1B synthetic architecture/adversarial fixtures. Written, NOT RUN; no physical evidence."""
from dataclasses import replace
import hashlib

import pytest

from engcore.data import InMemoryBulkStore
from engcore.data.errors import BulkDataIntegrityError, BulkDataUnavailable
from engcore.numerical.core import NumericalRefusal
from engcore.numerical.interval_transfer import MeshResourceKind
from engcore.numerical.mesh_adaptation import Grid1D, require_supported_adaptation
from engcore.numerical.field_mapping import map_cells_1d, CellMapping1DResult
from engcore.numerical import vertex_state as implementation
from engcore.numerical.vertex_state import (
    VertexDualAdapter1D, StateAdapterAdmission, StatePlacement, DualSupport1D,
    normalized_input_bytes,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields.semantics import FieldSemantics
from engcore.scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.semantics import ConservedQuantity, QuantitySemantics, QuantityRole
from engcore.scientific.units.quantity import Quantity


CONTEXT = "2"*64
U = Uncertainty.unknown("synthetic fixture, not measured data")
CQ = ConservedQuantity("fixture:species_A", "kg")
AMOUNT = FieldSemantics("cell_integrated", QuantitySemantics("fixture:species_A", "kg",
                        (QuantityRole.INTEGRATED,), CQ), "m", CQ)
DENSITY = FieldSemantics("cell_average_density", QuantitySemantics("fixture:species_A.line_density", "kg/m",
                         (QuantityRole.DENSITY,)), "m", CQ)
PRIMARY = FieldSemantics("intensive", QuantitySemantics("fixture:primary", "K", (QuantityRole.INTENSIVE,)))
P = StatePlacement


def manager(grid=None):
    return VertexDualAdapter1D(grid or Grid1D((0,1,4), "m"),
        admission=StateAdapterAdmission.OD6_VERTEX_DUAL_STATE_V1,
        root_context="fixture:root", coordinate_frame="fixture:axis", store=InMemoryBulkStore())


def origin(payload):
    return KnowledgeSource("fixture:normalized_input", "synthetic test author", hashlib.sha256(payload).hexdigest(),
        "fixture-v1", "fixture://not-measured/not-material-evidence", KnowledgeSourceClass.OTHER)


def register(m, values, *, name="q", placement=P.DUAL_CELL_INTEGRATED, semantics=AMOUNT, unit=None):
    unit = unit or semantics.quantity.unit
    payload = normalized_input_bytes(support=m.support, role="initial_state", name=name, values=values,
        unit=unit, context_digest=CONTEXT, contract={"placement": placement.value, "semantics": semantics.to_dict()}, uncertainty=U)
    return m.register_state(name, values, placement=placement, semantics=semantics, unit=unit,
        uncertainty=U, context_digest=CONTEXT, source=origin(payload), source_bytes=payload)


def storage(m, coefficients, *, name="C", intensive=PRIMARY, integrated=AMOUNT, unit="kg/K", density=None):
    contract = {"intensive": intensive.to_dict(), "integrated": integrated.to_dict(), "law": "A_i=C_i*u_i/1",
                "density": None if density is None else density.to_dict()}
    payload = normalized_input_bytes(support=m.support, role="integrated_storage", name=name, values=coefficients,
        unit=unit, context_digest=CONTEXT, contract=contract, uncertainty=U)
    return m.register_storage(name, coefficients, intensive=intensive, integrated=integrated, unit=unit,
        uncertainty=U, context_digest=CONTEXT, source=origin(payload), source_bytes=payload, density=density)


def refine(m):
    return m.refine([c.record_id for c in m.mesh.cells], minimum_cell=Quantity(.01,"m"), max_ratio=10)


def test_nonuniform_duals_half_boundaries_and_counts():
    m = manager()
    assert m.support.intervals.nodes == (0,.5,2.5,4)
    assert m.support.intervals.cell_widths == pytest.approx((.5,2,1.5), abs=1e-14)
    assert len(m.mesh.cells) == 2
    assert len(m.mesh.grid.nodes) == len(m.support.intervals.cell_widths) == 3
    assert m.support.mesh is m.mesh
    assert manager().support.record_id == m.support.record_id


def test_equal_width_primal_cells_have_boundary_half_control_volumes():
    m = manager(Grid1D((0,1,2,3),"m"))
    assert m.support.intervals.cell_widths == pytest.approx((.5,1,1,.5), abs=1e-14)


def test_grid_units_and_version_change_support_identity():
    m = manager(Grid1D((0,100,400),"cm"))
    assert m.support.intervals.unit == m.mesh.grid.unit
    assert m.support.intervals.nodes == (0,50,250,400)
    old = m.support
    transition = refine(m)
    m.coarsen(transition.primal.change.bisections, max_ratio=10)
    assert m.mesh.grid == old.mesh.grid
    assert m.support.record_id != old.record_id


def test_amount_refine_coarsen_roundtrip_conserves_not_arbitrary_pointwise_information():
    m = manager()
    s = register(m, (1,4,3))  # uniform line density2 on unequal dual lengths
    first = refine(m)
    fine, receipt = m.transfer_state(s, first)
    assert m.read_state(fine) == pytest.approx((.5,1,2,3,1.5), abs=1e-13)
    assert receipt.source_total == pytest.approx(8, abs=1e-13)
    assert receipt.target_total == pytest.approx(8, abs=1e-13)
    assert receipt.source_coverage == pytest.approx((1,1,1), abs=1e-13)
    assert receipt.target_coverage == pytest.approx((1,1,1,1,1), abs=1e-13)
    back_transition = m.coarsen(first.primal.change.bisections, max_ratio=10)
    back, back_receipt = m.transfer_state(fine, back_transition)
    assert m.read_state(back) == pytest.approx((1,4,3), abs=1e-13)
    assert back_receipt.absolute_residual <= 1e-12
    assert back_receipt.relative_residual <= 1e-12
    assert back.uncertainty.kind is UncertaintyKind.UNKNOWN
    with pytest.raises(NumericalRefusal, match="stale"):
        m.read_state(s)


def test_unequal_dual_amounts_are_not_density_values():
    m = manager()
    s = register(m, (2,6,9))
    t, receipt = m.transfer_state(s, refine(m))
    assert m.read_state(t) == pytest.approx((1,1.75,3,6.75,4.5), abs=1e-13)
    assert receipt.target_total == pytest.approx(17, abs=1e-12)


def test_constant_density_preserves_values_and_integral():
    m = manager()
    s = register(m, (2,2,2), placement=P.DUAL_CELL_DENSITY, semantics=DENSITY)
    t, receipt = m.transfer_state(s, refine(m))
    assert m.read_state(t) == pytest.approx((2,)*5, abs=1e-13)
    assert receipt.target_total == pytest.approx(8, abs=1e-13)


def test_constant_intensive_via_explicit_target_storage_not_vertex_interpolation():
    m = manager()
    u = register(m, (3,3,3), name="u", placement=P.VERTEX_INTENSIVE, semantics=PRIMARY)
    law = storage(m, 5*m.support.intervals.cell_widths)
    amount = m.convert_storage(u, law, name="amount")
    transition = refine(m)
    with pytest.raises(NumericalRefusal, match="interpolation"):
        m.transfer_state(u, transition)
    fine, receipt = m.transfer_state(amount, transition)
    target_law = storage(m, 5*m.support.intervals.cell_widths)
    reconstructed = m.convert_storage(fine, target_law, name="u")
    assert m.read_state(reconstructed) == pytest.approx((3,)*5, abs=1e-13)
    assert receipt.target_total == pytest.approx(60, abs=1e-12)
    assert reconstructed.source is None
    assert reconstructed.parents == (fine.record_id, target_law.record_id)


def test_discontinuous_integrated_coefficients_are_explicit_not_averaged():
    m = manager()
    u = register(m, (2,2,2), placement=P.VERTEX_INTENSIVE, semantics=PRIMARY)
    law = storage(m, (1,10,3))
    amounts = m.convert_storage(u, law, name="A")
    assert m.read_state(amounts) == pytest.approx((2,20,6), abs=1e-13)
    recovered = m.convert_storage(amounts, law, name="recovered")
    assert m.read_state(recovered) == pytest.approx((2,2,2), abs=1e-13)
    change = refine(m)
    fine, _ = m.transfer_state(amounts, change)
    with pytest.raises(NumericalRefusal, match="stale"):
        m.convert_storage(fine, law, name="unsupported")
    with pytest.raises(NumericalRefusal, match="explicit current storage"):
        m.convert_storage(fine, None, name="unsupported")


def test_density_to_primary_uses_actual_dual_lengths_and_explicit_storage():
    m = manager()
    density = register(m, (4,4,4), placement=P.DUAL_CELL_DENSITY, semantics=DENSITY)
    law = storage(m, (1,4,3), density=DENSITY)
    u = m.convert_storage(density, law, name="u")
    assert m.read_state(u) == pytest.approx((2,2,2), abs=1e-13)


def test_storage_requires_exact_declared_density_meaning_not_only_same_amount():
    m = manager()
    density = register(m, (4,4,4), placement=P.DUAL_CELL_DENSITY, semantics=DENSITY)
    alias = FieldSemantics("cell_average_density", QuantitySemantics("fixture:other_density", "kg/m",
                          (QuantityRole.DENSITY,)), "m", CQ)
    for law in (storage(m, (1,4,3), name="missing"), storage(m, (1,4,3), name="other", density=alias)):
        with pytest.raises(NumericalRefusal, match="meaning differs"):
            m.convert_storage(density, law, name="u")


@pytest.mark.parametrize("values", [(2,6), (1,2,3,4)])
def test_primal_or_wrong_counts_refuse_even_with_explicit_dual_label(values):
    with pytest.raises(NumericalRefusal, match="per exact vertex"):
        register(manager(), values)


def test_wrong_placement_refuses_dimensional_alias():
    with pytest.raises(NumericalRefusal, match="placement and field kind"):
        register(manager(), (1,2,3), placement=P.VERTEX_INTENSIVE, semantics=AMOUNT)


def test_affine_primary_and_missing_or_zero_storage_refuse():
    m = manager()
    with pytest.raises(NumericalRefusal, match="affine"):
        register(m, (20,20,20), placement=P.VERTEX_INTENSIVE, semantics=PRIMARY, unit="degC")
    with pytest.raises(NumericalRefusal, match="underdetermined"):
        storage(m, (1,0,3))
    with pytest.raises(NumericalRefusal, match="per exact vertex"):
        storage(m, (1,3))


def test_missing_initial_and_coefficient_provenance_refuse():
    m = manager()
    with pytest.raises(NumericalRefusal, match="provenance"):
        m.register_state("q", (1,2,3), placement=P.DUAL_CELL_INTEGRATED, semantics=AMOUNT,
            unit="kg", uncertainty=U, context_digest=CONTEXT, source=None, source_bytes=b"")
    with pytest.raises(NumericalRefusal, match="provenance"):
        m.register_storage("C", (1,2,3), intensive=PRIMARY, integrated=AMOUNT, unit="kg/K",
            uncertainty=U, context_digest=CONTEXT, source=None, source_bytes=b"")


def test_source_bytes_value_support_and_label_substitution_refuse():
    m = manager()
    raw = normalized_input_bytes(support=m.support, role="initial_state", name="q", values=(1,2,3),
        unit="kg", context_digest=CONTEXT, contract={"placement": P.DUAL_CELL_INTEGRATED.value,
        "semantics": AMOUNT.to_dict()}, uncertainty=U)
    for values, payload in [((1,2,4),raw), ((1,2,3),raw+b" ")]:
        with pytest.raises(NumericalRefusal, match="provenance"):
            m.register_state("q", values, placement=P.DUAL_CELL_INTEGRATED, semantics=AMOUNT,
                unit="kg", uncertainty=U, context_digest=CONTEXT, source=origin(raw), source_bytes=payload)
    refine(m)
    with pytest.raises(NumericalRefusal, match="provenance"):
        m.register_state("q", (1,2,3,4,5), placement=P.DUAL_CELL_INTEGRATED, semantics=AMOUNT,
            unit="kg", uncertainty=U, context_digest=CONTEXT, source=origin(raw), source_bytes=raw)


def test_same_dimension_other_intensive_meaning_cannot_use_storage():
    m = manager()
    other = FieldSemantics("intensive", QuantitySemantics("fixture:other_primary", "K", (QuantityRole.INTENSIVE,)))
    s = register(m, (1,2,3), placement=P.VERTEX_INTENSIVE, semantics=other)
    with pytest.raises(NumericalRefusal, match="meaning differs"):
        m.convert_storage(s, storage(m,(1,2,3)), name="A")


def test_stale_records_caches_history_and_unrelated_clone_refuse():
    m = manager()
    s = register(m, (1,4,3))
    cache, history = {"matrix":1}, ["iteration"]
    bindings = [m.bind_resource("matrix", MeshResourceKind.SOLVER_CACHE, cache),
                m.bind_resource("iteration", MeshResourceKind.COUPLING_HISTORY, history)]
    transition = refine(m)
    assert cache == {} and history == []
    for binding in bindings:
        with pytest.raises(NumericalRefusal, match="stale"):
            m.require_resource(binding)
    with pytest.raises(NumericalRefusal, match="stale"):
        m.read_state(s)
    with pytest.raises(NumericalRefusal, match="unissued"):
        m.transfer_state(replace(s), transition)
    with pytest.raises(NumericalRefusal, match="unissued"):
        manager().transfer_state(s, transition)
    target, _ = m.transfer_state(s, transition)
    with pytest.raises(NumericalRefusal, match="consumed|populated"):
        m.transfer_state(s, transition)
    assert sum(m.read_state(target)) == pytest.approx(8, abs=1e-13)


def test_partial_dual_coverage_and_unissued_support_refuse():
    m = manager()
    s = register(m, (1,4,3))
    partial = Grid1D((0,.5,2.5,3.9),"m")
    with pytest.raises(InvalidScientificProblem, match="partial coverage"):
        map_cells_1d((1,4,3), m.support.intervals, partial, source_semantics=AMOUNT,
            target_semantics=AMOUNT, source_unit="kg", target_unit="kg",
            source_fingerprint=m.support.intervals.digest, target_fingerprint=partial.digest, coordinate_frame="fixture:axis")
    transition = refine(m)
    fake = replace(s, support=DualSupport1D(s.support.mesh, partial))
    with pytest.raises(NumericalRefusal, match="unissued"):
        m.transfer_state(fake, transition)


def test_mapper_false_zero_residual_cannot_admit_doubled_amounts(monkeypatch):
    m = manager()
    s = register(m,(1,4,3))
    transition = refine(m)
    original = implementation.map_cells_1d
    def bad(*args, **kwargs):
        result = original(*args, **kwargs)
        return CellMapping1DResult(tuple(2*v for v in result.values), result.diagnostics, result.uncertainty)
    monkeypatch.setattr(implementation, "map_cells_1d", bad)
    with pytest.raises(NumericalRefusal, match="actual dual amounts"):
        m.transfer_state(s, transition)
    assert m._fields == {}


def test_mesh_change_dual_derivation_failure_poisons_session_and_clears_cache(monkeypatch):
    m = manager()
    cache = {"matrix":1}
    m.bind_resource("cache", MeshResourceKind.SOLVER_CACHE, cache)
    def fail(mesh):
        raise NumericalRefusal("deliberate dual derivation failure")
    # Inject failure at post-primal-change issuance instead of defeating pre-change guard.
    original_refine = m._runtime.refine
    def change_then_fail(*args, **kwargs):
        receipt = original_refine(*args, **kwargs)
        monkeypatch.setattr(implementation, "_dual_grid", fail)
        return receipt
    monkeypatch.setattr(m._runtime, "refine", change_then_fail)
    with pytest.raises(NumericalRefusal, match="derivation failure"):
        refine(m)
    assert cache == {}
    with pytest.raises(NumericalRefusal, match="unusable"):
        m.support


def test_versioned_admission_does_not_relax_legacy_transient_guard():
    with pytest.raises(NumericalRefusal, match="transient"):
        require_supported_adaptation(spatial_dimension=1, transient=True)
    with pytest.raises(NumericalRefusal, match="versioned"):
        VertexDualAdapter1D(Grid1D((0,1,4),"m"), admission="od6_vertex_dual_state/1",
            root_context="fixture:root", coordinate_frame="fixture:axis", store=InMemoryBulkStore())
    assert manager().support.mesh is not None


def test_export_cannot_authorize_issuance():
    m = manager()
    with pytest.raises(NumericalRefusal, match="serialized"):
        DualSupport1D.from_dict(m.support.to_dict())


def test_coarsening_does_not_recover_unresolved_fine_intensive_information():
    m = manager()
    transition = refine(m)
    fine = register(m, (1,3,8,2,2))
    coarse_transition = m.coarsen(transition.primal.change.bisections, max_ratio=10)
    coarse, _ = m.transfer_state(fine, coarse_transition)
    again, receipt = m.transfer_state(coarse, refine(m))
    assert sum(m.read_state(again)) == pytest.approx(16, abs=1e-12)
    assert tuple(m.read_state(again)) != (1,3,8,2,2)
    assert receipt.relative_residual <= 1e-12


def test_source_class_label_never_upgrades_unknown_uncertainty():
    m = manager()
    raw = normalized_input_bytes(support=m.support, role="initial_state", name="q", values=(1,4,3),
        unit="kg", context_digest=CONTEXT, contract={"placement": P.DUAL_CELL_INTEGRATED.value,
        "semantics": AMOUNT.to_dict()}, uncertainty=U)
    declared = replace(origin(raw), source_class=KnowledgeSourceClass.EXPERIMENTAL_DATASET)
    s = m.register_state("q", (1,4,3), placement=P.DUAL_CELL_INTEGRATED, semantics=AMOUNT, unit="kg",
        uncertainty=U, context_digest=CONTEXT, source=declared, source_bytes=raw)
    t, receipt = m.transfer_state(s, refine(m))
    assert t.uncertainty.kind is receipt.uncertainty.kind is UncertaintyKind.UNKNOWN


@pytest.mark.parametrize("missing", ["state", "storage", "support", "dual_transition", "primal_invalidation", "mesh_change"])
def test_missing_ancestor_authority_refuses_current_derived_state(missing):
    m = manager()
    u = register(m, (2,2,2), name="u", placement=P.VERTEX_INTENSIVE, semantics=PRIMARY)
    law = storage(m, (1,4,3))
    amounts = m.convert_storage(u, law, name="A")
    transition = refine(m)
    fine, _ = m.transfer_state(amounts, transition)
    registry, record = {
        "state": (m._issued, u), "storage": (m._issued, law), "support": (m._issued, u.support),
        "dual_transition": (m._issued, transition),
        "primal_invalidation": (m._runtime._issued, transition.primal),
        "mesh_change": (m._runtime._lineage._issued, transition.primal.change),
    }[missing]
    registry._records.pop(record.record_id)
    with pytest.raises(NumericalRefusal):
        m.read_state(fine)


def test_primal_bound_state_cannot_be_read_as_vertex_state():
    from engcore.numerical.interval_transfer import AdaptiveMesh1D
    grid = Grid1D((0,1,4), "m")
    primal = AdaptiveMesh1D(grid, root_context="fixture:root", coordinate_frame="fixture:axis", store=InMemoryBulkStore())
    s = primal.register_state("A", (2,6), semantics=AMOUNT, unit="kg", uncertainty=U, context_digest=CONTEXT)
    with pytest.raises(NumericalRefusal, match="primal-cell"):
        manager().read_state(s)


def test_storage_unit_conversion_and_state_amount_conversion():
    m = manager()
    u = register(m, (2,2,2), placement=P.VERTEX_INTENSIVE, semantics=PRIMARY)
    law = storage(m, (1000,4000,3000), unit="g/K")
    amounts = m.convert_storage(u, law, name="A")
    assert m.read_state(amounts) == pytest.approx((2,8,6), abs=1e-12)
    recovered = m.convert_storage(amounts, law, name="u")
    assert m.read_state(recovered) == pytest.approx((2,2,2), abs=1e-12)
    fine, receipt = m.transfer_state(amounts, refine(m), target_unit="g")
    assert sum(m.read_state(fine)) == pytest.approx(16000, abs=1e-9)
    assert receipt.source_total == pytest.approx(16, abs=1e-12)
    assert receipt.target_total == pytest.approx(16, abs=1e-12)


def test_other_species_amount_cannot_use_storage_law():
    m = manager()
    cq = ConservedQuantity("fixture:species_B", "kg")
    other = FieldSemantics("cell_integrated", QuantitySemantics("fixture:species_B", "kg",
                          (QuantityRole.INTEGRATED,), cq), "m", cq)
    s = register(m, (1,2,3), semantics=other)
    with pytest.raises(NumericalRefusal, match="meaning differs"):
        m.convert_storage(s, storage(m,(1,2,3)), name="u")


def test_coefficient_state_context_mismatch_and_populated_target_refuse():
    m = manager()
    s = register(m, (1,2,3))
    law = storage(m, (1,2,3))
    m.convert_storage(s, law, name="u")
    with pytest.raises(NumericalRefusal, match="overwrite"):
        m.convert_storage(s, law, name="u")
    # Construct a legitimately sourced law for a different declared context, not a mutated law.
    payload = normalized_input_bytes(support=m.support, role="integrated_storage", name="otherC", values=(1,2,3),
        unit="kg/K", context_digest="3"*64, contract={"intensive": PRIMARY.to_dict(),
        "integrated": AMOUNT.to_dict(), "law": "A_i=C_i*u_i/1", "density": None}, uncertainty=U)
    other = m.register_storage("otherC", (1,2,3), intensive=PRIMARY, integrated=AMOUNT, unit="kg/K",
        uncertainty=U, context_digest="3"*64, source=origin(payload), source_bytes=payload)
    with pytest.raises(NumericalRefusal, match="contexts differ"):
        m.convert_storage(s, other, name="unsupported")


@pytest.mark.parametrize("record_type", ["state", "storage"])
@pytest.mark.parametrize("damage", ["corrupt", "missing"])
def test_corrupt_or_missing_input_bytes_refuse(record_type, damage):
    m = manager()
    s = register(m, (1,2,3))
    law = storage(m, (2,4,6))
    record = s if record_type == "state" else law
    if damage == "corrupt":
        m._runtime._store.corrupt(record.data, b"x"*record.data.byte_length)
        expected = BulkDataIntegrityError
    else:
        m._runtime._store.delete(record.data)
        expected = BulkDataUnavailable
    with pytest.raises(expected):
        m.convert_storage(s, law, name="u")


def test_nested_support_tamper_refuses_and_source_object_is_not_authority():
    m = manager()
    s = register(m, (1,2,3))
    object.__setattr__(s.support.intervals, "nodes", (0,.5,2.5,4.1))
    with pytest.raises(NumericalRefusal, match="tampered|conflicting"):
        m.read_state(s)
