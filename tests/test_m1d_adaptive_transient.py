"""Synthetic adaptive execution/verification designs. Authored, NOT RUN; not measured evidence."""
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import math

import numpy as np
import pytest

from engcore.data import InMemoryBulkStore
from engcore.materials.identity import MaterialIdentity, MaterialState
from engcore.materials.properties import MaterialPropertySet, PropertyApplicability, PropertyDatum, DatumOrigin
from engcore.numerical.adaptive_transient import AdaptiveTransient1D, AdaptiveAdmission, DeclaredCriterion, MeshOperation
from engcore.numerical.core import NumericalMethod, NumericalRefusal
from engcore.numerical.interval_transfer import MeshResourceKind
from engcore.numerical.mesh_adaptation import Grid1D
from engcore.numerical.vertex_state import VertexDualAdapter1D, StateAdapterAdmission, StatePlacement, normalized_input_bytes
from engcore.numerical import vertex_state as vertex_implementation
from engcore.scenarios.timeline import TimeBasis, TimeBasisKind, TimePoint, TimeWindow
from engcore.scientific.knowledge.claim import KnowledgeClaim, KnowledgeKind
from engcore.scientific.knowledge.snapshot import KnowledgeSnapshot
from engcore.scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.solvers.protocol import SolverSettings
from engcore.scientific.units.quantity import Quantity
from engcore.scientific.errors import InvalidScientificProblem
from engcore.domains.thermal_models.conduction1d_nonuniform import BoundaryKind, ConductionBoundary
from engcore.domains.thermal_models.conduction1d_transient_fv import (
    ThermalRegion, TransientConduction1D, ConductionAdmission, SparseFVProvider, TEMPERATURE,
    problem_context, forcing_bytes,
)
from engcore.domains.thermal_models import conduction1d_transient_fv as thermal_implementation
from engcore.domains.thermal_models.adaptive_conduction1d import ThermalAdaptiveBackend, ThermalRebuildTarget


U=Uncertainty.unknown("synthetic fixture; no measured material or model discrepancy")
BASIS=TimeBasis("fixture:adaptive_clock",TimeBasisKind.ELAPSED,"synthetic initial instant")


def origin(raw):
    return KnowledgeSource("fixture:synthetic_input","synthetic mathematics, never experimental data",
        hashlib.sha256(raw).hexdigest(),"1","fixture://not-measured",KnowledgeSourceClass.OTHER)


def material(left=0,right=1,*,k=1,c=1,area=1,missing=False):
    identity=MaterialIdentity("fixture_solid",specification="SYNTHETIC-MATH")
    rows=[("k",Quantity(k,"W/m/K")),("c",Quantity(c,"J/m**3/K"))]
    if missing:rows.pop()
    raw=json.dumps([[pid,value.to_dict()] for pid,value in rows],sort_keys=True).encode()
    src=origin(raw);data=[];claims=[]
    for pid,value in rows:
        app=PropertyApplicability(identity.digest,pid,(),"fixture_phase")
        claim=KnowledgeClaim("fixture:"+pid,KnowledgeKind.MATERIAL_PROPERTY,identity.subject_key,pid,value,"",None,
            src.source_id,src.document_digest,app.digest)
        claims.append(claim);data.append(PropertyDatum(claim,app,DatumOrigin.ASSUMED))
    props=MaterialPropertySet("fixture:properties",identity,KnowledgeSnapshot("fixture:snapshot",(src,),tuple(claims)),tuple(data))
    return ThermalRegion(Quantity(left,"m"),Quantity(right,"m"),Quantity(area,"m**2"),props,
        MaterialState(identity,phase="fixture_phase"),"k","c",(raw,))


def runner(nodes=(0,.2,.7,1),*,regions=None,temperatures=None):
    adapter=VertexDualAdapter1D(Grid1D(tuple(nodes),"m"),admission=StateAdapterAdmission.OD6_VERTEX_DUAL_STATE_V1,
        root_context="fixture:adaptive",coordinate_frame="fixture:axis",store=InMemoryBulkStore())
    regions=tuple(regions or (material(),))
    time=TimePoint(BASIS.basis_id,0);admission=ConductionAdmission.SYNTHETIC_FIXTURE
    context=problem_context(adapter,regions,(),BASIS,time,admission)
    values=tuple(temperatures if temperatures is not None else (300,)*len(nodes))
    raw=normalized_input_bytes(support=adapter.support,role="initial_state",name="T0",values=values,unit="K",
        context_digest=context,contract={"placement":StatePlacement.VERTEX_INTENSIVE.value,"semantics":TEMPERATURE.to_dict()},uncertainty=U)
    initial=adapter.register_state("T0",values,placement=StatePlacement.VERTEX_INTENSIVE,semantics=TEMPERATURE,unit="K",
        uncertainty=U,context_digest=context,source=origin(raw),source_bytes=raw)
    session=TransientConduction1D(adapter,regions=regions,contacts=(),basis=BASIS,initial_time=time,initial=initial,
        admission=admission,provider=SparseFVProvider(),method=NumericalMethod("sparse_direct",SolverSettings(tolerances={"residual_rtol":1e-12})),
        conservation_atol=Quantity(1e-9,"J"),conservation_rtol=1e-12,temperature_atol=Quantity(1e-9,"K"),local_power_atol=Quantity(1e-8,"W"))
    definition=b"Synthetic caller schedule: explicitly request selected issued bisections after a completed window; no error bound."
    criterion=DeclaredCriterion("fixture:caller_schedule","1",definition,origin(definition))
    runtime=AdaptiveTransient1D(ThermalAdaptiveBackend(session),criteria=(criterion,),admission=AdaptiveAdmission.OD6_ISSUED_ADAPTIVE_WINDOWS_V1)
    return runtime,criterion


def forcing(runtime,dt=.1,*,left=0,right=0,q=None):
    session=runtime.backend.session
    window=TimeWindow(session.time,TimePoint(session.basis.basis_id,session.time.seconds+Fraction(str(dt))))
    a=ConductionBoundary(BoundaryKind.INWARD_HEAT_FLUX,Quantity(left,"W/m**2"))
    b=ConductionBoundary(BoundaryKind.INWARD_HEAT_FLUX,Quantity(right,"W/m**2"))
    sources=tuple(Quantity(v,"W/m**3") for v in (q if q is not None else (0,)*len(session.regions)))
    raw=forcing_bytes(session.context,window,a,b,sources)
    return dict(window=window,dt=Quantity(dt,"s"),left=a,right=b,volumetric_sources=sources,source=origin(raw),source_bytes=raw)


def refine(runtime,criterion,*,target=None,cells=None):
    backend=runtime.backend
    decision=runtime.declare_decision(criterion,MeshOperation.REFINE,
        cells=tuple(c.record_id for c in backend.adapter.mesh.cells) if cells is None else cells,
        minimum_cell=Quantity(.0001,"m"),max_ratio=20)
    return runtime.adapt(decision,target=target or ThermalRebuildTarget(backend.session.regions,()))


def test_constant_solution_changed_mesh_rebuild_and_derived_origin():
    r,c=runner();old=r.backend.session
    step,_=r.advance(**forcing(r))
    transition,receipt,event=refine(r,c)
    new=r.backend.session
    assert new is not old and new.support.mesh.parent_version_id==old.support.mesh.version_id
    assert new.time==step.window.end
    assert new.adapter.read_state(new.current)==pytest.approx((300,)*7,abs=1e-9)
    assert new.initial.source is None and new.initial.parents  # derived, never invented measurement
    assert receipt.source_total==pytest.approx(300,abs=1e-9)
    assert receipt.target_total==pytest.approx(300,abs=1e-9)
    assert event.status=="accepted_adaptation"
    with pytest.raises(NumericalRefusal,match="unusable|stale"):old._guard()
    r.advance(**forcing(r))


def test_closed_domain_energy_refinement_and_recorded_coarsening():
    r,c=runner(temperatures=(300,340,310,290))
    # Independent initial integral for c=A=1 and widths (.1,.35,.4,.15).
    expected=300*.1+340*.35+310*.4+290*.15
    r.advance(**forcing(r))
    first,_,_=refine(r,c)
    r.advance(**forcing(r))
    decision=r.declare_decision(c,MeshOperation.COARSEN,bisections=first.primal.change.bisections,max_ratio=20)
    r.adapt(decision,target=ThermalRebuildTarget(r.backend.session.regions,()))
    step,_=r.advance(**forcing(r))
    assert math.fsum(r.backend.adapter.read_state(step.energy))==pytest.approx(expected,abs=1e-8)
    assert r.backend.adapter.mesh.grid.nodes==(0,.2,.7,1)
    assert r.backend.adapter.mesh.version_id!=first.before.mesh.version_id


def test_nonzero_external_energy_budget_across_adaptation():
    r,c=runner(regions=(material(c=3,area=2),))
    r.advance(**forcing(r,.1,left=4,right=-1,q=(5,)))
    refine(r,c)
    step,_=r.advance(**forcing(r,.2,left=4,right=-1,q=(5,)))
    # Continuous geometry and prescribed flux/source, independent of implementation diagnostics.
    expected=3*2*300+(.1+.2)*(4*2-1*2+5*2*1)
    assert math.fsum(r.backend.adapter.read_state(step.energy))==pytest.approx(expected,abs=1e-8)


def test_discontinuous_material_reresolution_preserves_integral_not_pointwise_claim():
    regions=(material(0,.4,c=2,k=1),material(.4,1,c=5,k=10))
    r,c=runner(nodes=(0,.3,.8,1),regions=regions)
    initial=300*(.4*2+.6*5)
    r.advance(**forcing(r,q=(0,0)))
    old=r.backend.session
    refine(r,c,target=ThermalRebuildTarget(regions,()))
    new=r.backend.session
    assert new.storage.data.count!=old.storage.data.count
    assert len(new.material_resolutions)==2
    assert math.fsum(new.adapter.read_state(new.energy))==pytest.approx(initial,abs=1e-8)
    assert new.energy.uncertainty.kind is UncertaintyKind.UNKNOWN
    # Old dual averages can straddle material jumps: integral closure is not constant-T/local accuracy evidence.


def test_mesh_change_invalidates_old_fields_resources_and_sessions():
    r,c=runner();a=r.backend.adapter
    cache={"matrix_version":"old"};history=[{"iteration":1}]
    bindings=(a.bind_resource("provider",MeshResourceKind.SOLVER_CACHE,cache),
              a.bind_resource("coupling",MeshResourceKind.COUPLING_HISTORY,history))
    step,_=r.advance(**forcing(r));refine(r,c)
    assert cache=={} and history==[]
    with pytest.raises(NumericalRefusal,match="stale"):a.read_state(step.temperature)
    for b in bindings:
        with pytest.raises(NumericalRefusal,match="stale"):a.require_resource(b)


def test_provider_failure_rolls_back_complete_same_session_and_does_not_advance(monkeypatch):
    r,c=runner();s=r.backend.session
    cache={"assembly":[1,2,3]};s.adapter.bind_resource("cache",MeshResourceKind.SOLVER_CACHE,cache)
    before=r.backend.identity_material();registry=set(s.adapter._issued._records)
    original=thermal_implementation.spla.splu
    def fail(*args,**kwargs):
        cache["assembly"].append(99)
        raise RuntimeError("synthetic SuperLU failure")
    monkeypatch.setattr(thermal_implementation.spla,"splu",fail)
    with pytest.raises(NumericalRefusal,match="provider failure"):r.advance(**forcing(r))
    assert r.backend.identity_material()==before and r.backend.session is s
    assert set(s.adapter._issued._records)==registry and cache=={"assembly":[1,2,3]}
    assert r.audit_history[-1].status=="rolled_back_refused_attempt"
    monkeypatch.setattr(thermal_implementation.spla,"splu",original)
    step,_=r.advance(**forcing(r))  # explicit caller retry, no implicit advance
    assert step.window.start==s.initial_time


def test_partial_publication_registry_rollback_discards_speculative_fields(monkeypatch):
    r,c=runner();s=r.backend.session
    registry=dict(s.adapter._issued._records);fields=dict(s.adapter._fields)
    original=s.adapter.convert_storage
    def fail(*args,**kwargs):raise NumericalRefusal("synthetic post-temperature publication failure")
    monkeypatch.setattr(s.adapter,"convert_storage",fail)
    with pytest.raises(NumericalRefusal,match="publication failure"):r.advance(**forcing(r))
    assert s.adapter._issued._records==registry and s.adapter._fields==fields
    assert s.time==s.initial_time and not s._unusable
    monkeypatch.setattr(s.adapter,"convert_storage",original)
    r.advance(**forcing(r))


def test_failed_restore_due_to_saved_source_corruption_poisons(monkeypatch):
    r,c=runner();s=r.backend.session
    def fail(*args,**kwargs):
        s.adapter._runtime._store.corrupt(s.initial.data,b"x"*s.initial.data.byte_length)
        raise RuntimeError("synthetic failure plus source corruption")
    monkeypatch.setattr(thermal_implementation.spla,"splu",fail)
    with pytest.raises(NumericalRefusal,match="poisoned"):r.advance(**forcing(r))
    assert r.audit_history[-1].status=="poisoned"
    with pytest.raises(NumericalRefusal,match="poisoned"):r.advance(**forcing(r))


def test_checkpoint_is_same_backend_same_object_and_not_durable():
    r,c=runner();other,_=runner()
    cp=r.backend.checkpoint()
    with pytest.raises(InvalidScientificProblem):other.backend.restore(cp)
    forged=replace(cp,record=replace(cp.record))
    with pytest.raises(InvalidScientificProblem):r.backend.restore(forged)
    r.backend.restore(cp)


def test_out_of_band_restore_cannot_rewind_committed_adaptive_history():
    r,c=runner();checkpoint=r.backend.checkpoint()
    r.advance(**forcing(r))
    r.backend.restore(checkpoint)
    with pytest.raises(NumericalRefusal,match="uncommitted backend state/time drift"):
        r.advance(**forcing(r))


def test_checkpoint_equal_content_nested_record_substitution_cannot_mint_issuance():
    r,c=runner();checkpoint=r.backend.checkpoint()
    snap=checkpoint.token.snapshot
    original=snap.record_id
    registries=[];replaced=False
    for tag,owner,entries in snap.registries:
        if entries and not replaced:
            key,record,digest=entries[0]
            entries=((key,replace(record),digest),*entries[1:])
            replaced=True
        registries.append((tag,owner,entries))
    object.__setattr__(snap,"registries",tuple(registries))
    assert snap.record_id==original  # Same material hash does not establish same local issuance.
    with pytest.raises(NumericalRefusal,match="reference authority changed"):
        r.backend.restore(checkpoint)


def test_missing_target_properties_after_mesh_mutation_poisons_without_acceptance():
    r,c=runner();r.advance(**forcing(r))
    with pytest.raises(NumericalRefusal,match="poisoned"):
        refine(r,c,target=ThermalRebuildTarget((material(missing=True),),()))
    assert r.audit_history[-1].status=="poisoned"
    assert not any(e.status=="accepted_adaptation" for e in r.audit_history)


def test_partial_coverage_transfer_refuses_and_poisons(monkeypatch):
    r,c=runner();r.advance(**forcing(r))
    original=vertex_implementation.map_cells_1d
    def partial(values,source,target,**kwargs):
        cropped=Grid1D((*target.nodes[:-1],.95),target.unit)
        kwargs["target_fingerprint"]=cropped.digest
        return original(values,source,cropped,**kwargs)
    monkeypatch.setattr(vertex_implementation,"map_cells_1d",partial)
    with pytest.raises(NumericalRefusal,match="poisoned"):refine(r,c)
    assert r.audit_history[-1].status=="poisoned"


def test_unissued_sibling_record_refusal_rolls_back_without_fabricated_ancestry():
    r,c=runner();r.advance(**forcing(r));change,_,_=refine(r,c)
    r.advance(**forcing(r))
    forged=replace(change.primal.change.bisections[0])
    decision=r.declare_decision(c,MeshOperation.COARSEN,bisections=(forged,),max_ratio=20)
    before=r.backend.identity_material()
    with pytest.raises(NumericalRefusal,match="unissued"):r.adapt(decision,target=ThermalRebuildTarget(r.backend.session.regions,()))
    assert r.backend.identity_material()==before
    assert r.audit_history[-1].status=="rolled_back_refused_attempt"


def test_undeclared_criterion_no_accepted_basis_and_tampered_definition_refuse():
    r,c=runner()
    with pytest.raises(NumericalRefusal,match="accepted numerical basis"):
        r.declare_decision(c,MeshOperation.REFINE,cells=("fake",),minimum_cell=Quantity(.01,"m"),max_ratio=20)
    r.advance(**forcing(r))
    with pytest.raises(NumericalRefusal,match="unissued"):
        r.declare_decision(replace(c),MeshOperation.REFINE,cells=("fake",),minimum_cell=Quantity(.01,"m"),max_ratio=20)
    object.__setattr__(c,"definition",b"changed unsupported rule")
    with pytest.raises(NumericalRefusal):r.advance(**forcing(r))


def test_exact_window_order_and_stale_decision_refuse():
    r,c=runner();r.advance(**forcing(r))
    dec=r.declare_decision(c,MeshOperation.REFINE,cells=tuple(x.record_id for x in r.backend.adapter.mesh.cells),minimum_cell=Quantity(.01,"m"),max_ratio=20)
    old=forcing(r);r.advance(**old)
    with pytest.raises(NumericalRefusal,match="exact current clock"):r.advance(**old)
    with pytest.raises(NumericalRefusal,match="stale adaptation"):r.adapt(dec,target=ThermalRebuildTarget(r.backend.session.regions,()))


def test_opaque_provider_resource_refuses_checkpoint_before_execution():
    r,c=runner();r.backend.adapter.bind_resource("opaque",MeshResourceKind.SOLVER_CACHE,{"factorization":object()})
    with pytest.raises(NumericalRefusal,match="opaque"):r.advance(**forcing(r))
    assert r.backend.session.time==r.backend.session.initial_time


def test_source_material_bytes_reresolved_not_transferred_as_storage():
    r,c=runner();r.advance(**forcing(r));old=r.backend.session.storage
    refine(r,c,target=ThermalRebuildTarget((material(),),()))
    s=r.backend.session
    assert s.storage is not old and s.storage.context_digest!=old.context_digest
    assert s.storage.data.count==7 and old.data.count==4
    assert math.fsum(s.adapter.read_state(s.energy))==pytest.approx(300,abs=1e-8)
    other,criterion=runner();other.advance(**forcing(other))
    with pytest.raises(NumericalRefusal,match="poisoned"):
        refine(other,criterion,target=ThermalRebuildTarget((material(c=2),),()))
    assert other.audit_history[-1].status=="poisoned"  # physical change is not mesh adaptation
    corrupt,criterion=runner();corrupt.advance(**forcing(corrupt))
    bad=replace(material(),source_payloads=(b"corrupted physical source artifact",))
    with pytest.raises(NumericalRefusal,match="poisoned"):
        refine(corrupt,criterion,target=ThermalRebuildTarget((bad,),()))
    assert corrupt.audit_history[-1].status=="poisoned"


def test_temporal_study_and_uniform_adaptive_comparison_definitions():
    # Uniform-in-space exact T=300+exp(-t), q=-exp(-t), insulated c=A=1.
    errors=[]
    for dt in (.1,.05,.025):
        adaptive,c=runner(temperatures=(301,)*4);uniform,_=runner(temperatures=(301,)*4)
        for index in range(round(1/dt)):
            end=float(adaptive.backend.session.time.seconds)+dt
            adaptive.advance(**forcing(adaptive,dt,q=(-math.exp(-end),)))
            uniform.advance(**forcing(uniform,dt,q=(-math.exp(-end),)))
            if index+1==round(.5/dt):refine(adaptive,c)
        a=adaptive.backend.session;u=uniform.backend.session
        av=a.adapter.read_state(a.current);uv=u.adapter.read_state(u.current)
        assert max(av)-min(av)<1e-9 and max(uv)-min(uv)<1e-9
        assert av[0]==pytest.approx(uv[0],abs=1e-9)
        errors.append(abs(av[0]-(300+math.exp(-1))))
    assert errors[0]>errors[1]>errors[2]
    assert 1.8<errors[0]/errors[1]<2.2 and 1.8<errors[1]/errors[2]<2.2


def test_spatial_adaptive_study_uses_compatible_manufactured_cosine_and_exact_sources():
    # Stationary T=300+cos(pi*x), q=pi² cos(pi*x), insulated: no continuum temporal truncation.
    # Source is its analytical dual average. Material remains homogeneous despite source partitioning.
    errors=[]
    def data(nodes):
        edges=(nodes[0],*(.5*a+.5*b for a,b in zip(nodes[:-1],nodes[1:])),nodes[-1])
        regs=tuple(material(a,b) for a,b in zip(edges[:-1],edges[1:]))
        q=tuple(math.pi*(math.sin(math.pi*b)-math.sin(math.pi*a))/(b-a) for a,b in zip(edges[:-1],edges[1:]))
        return regs,q
    for n in (5,9,17):
        nodes=tuple(i/(n-1) for i in range(n));regions,q=data(nodes)
        r,c=runner(nodes=nodes,regions=regions,temperatures=tuple(300+math.cos(math.pi*x) for x in nodes))
        r.advance(**forcing(r,.05,q=q))
        fine=tuple(v for i,x in enumerate(nodes[:-1]) for v in (x,.5*x+.5*nodes[i+1]))+(nodes[-1],)
        target,target_q=data(fine)
        refine(r,c,target=ThermalRebuildTarget(target,()))
        r.advance(**forcing(r,.05,q=target_q))
        session=r.backend.session
        exact=[300+math.cos(math.pi*x) for x in session.adapter.mesh.grid.nodes]
        errors.append(max(abs(a-b) for a,b in zip(session.adapter.read_state(session.current),exact)))
    assert errors[0]>errors[1]>errors[2]
    # No universal spatial order, error bound or validation follows from this authored study.


def test_history_uncertainty_and_provenance_never_become_validation():
    r,c=runner();r.advance(**forcing(r));refine(r,c)
    events=r.audit_history
    assert [e.status for e in events]==["accepted_window","accepted_adaptation"]
    assert events[1].parent==events[0].record_id
    assert all(e.to_dict()["uncertainty"]["kind"]=="unknown" for e in events)
    assert "not_physical_validation" in events[-1].to_dict()["classification"]
