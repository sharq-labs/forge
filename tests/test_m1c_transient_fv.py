"""Synthetic mathematical verification designs only. All tests written, NOT RUN."""
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
from engcore.numerical.core import NumericalMethod, NumericalRefusal, NumericalDiagnostics, failed
from engcore.numerical.mesh_adaptation import Grid1D
from engcore.numerical.vertex_state import VertexDualAdapter1D, StateAdapterAdmission, StatePlacement, normalized_input_bytes
from engcore.scenarios.timeline import TimeBasis, TimeBasisKind, TimePoint, TimeWindow
from engcore.scientific.knowledge.claim import KnowledgeClaim, KnowledgeKind
from engcore.scientific.knowledge.snapshot import KnowledgeSnapshot
from engcore.scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.solvers.protocol import SolverSettings, ConvergenceState, SolverIdentity
from engcore.scientific.units.quantity import Quantity
from engcore.scientific.errors import UnitCompatibilityError
from engcore.domains.thermal_models.conduction1d_nonuniform import ConductionBoundary, BoundaryKind, STEADY_CONDUCTION_MODEL
from engcore.domains.thermal_models.conduction1d_transient_fv import (
    ThermalRegion, ContactResistance, ConductionAdmission, TransientConduction1D, SparseFVProvider,
    TEMPERATURE, MODEL, REALIZATION, problem_context, forcing_bytes,
)

U=Uncertainty.unknown("synthetic mathematical fixture; not measured")
BASIS=TimeBasis("fixture:clock",TimeBasisKind.ELAPSED,"synthetic manufactured clock origin")
ADMISSION=ConductionAdmission.SYNTHETIC_FIXTURE


def origin(raw):
    return KnowledgeSource("fixture:input","synthetic mathematics, not experimental reference",
        hashlib.sha256(raw).hexdigest(),"1","fixture://synthetic-not-measured",KnowledgeSourceClass.OTHER)


def region(left=0,right=1,*,area=1,k=1,c=1,missing=False):
    material=MaterialIdentity("fixture_solid",specification="SYNTHETIC-MATH")
    rows=[("k",Quantity(k,"W/m/K")),("c",Quantity(c,"J/m**3/K"))]
    if missing:rows.pop()
    raw=json.dumps([[p,q.to_dict()] for p,q in rows],sort_keys=True).encode()
    src=origin(raw); claims=[];data=[]
    for pid,q in rows:
        app=PropertyApplicability(material.digest,pid,(),"fixture_linear_solid")
        claim=KnowledgeClaim("fixture:"+pid,KnowledgeKind.MATERIAL_PROPERTY,material.subject_key,pid,q,"",None,
            src.source_id,src.document_digest,app.digest)
        claims.append(claim);data.append(PropertyDatum(claim,app,DatumOrigin.ASSUMED))
    props=MaterialPropertySet("fixture:properties",material,KnowledgeSnapshot("fixture:snapshot",(src,),tuple(claims)),tuple(data))
    return ThermalRegion(Quantity(left,"m"),Quantity(right,"m"),Quantity(area,"m**2"),props,
                         MaterialState(material,phase="fixture_linear_solid"),"k","c",(raw,))


def session(nodes=(0,.2,.7,1),*,regions=None,temperatures=None,contacts=(),provider=None,admission=ADMISSION,
            residual_rtol=1e-12,conservation_rtol=1e-12):
    a=VertexDualAdapter1D(Grid1D(tuple(nodes),"m"),admission=StateAdapterAdmission.OD6_VERTEX_DUAL_STATE_V1,
        root_context="fixture:transient",coordinate_frame="fixture:axis",store=InMemoryBulkStore())
    regions=tuple(regions or (region(),))
    initial_time=TimePoint(BASIS.basis_id,Fraction(0))
    context=problem_context(a,regions,contacts,BASIS,initial_time,admission)
    values=tuple(temperatures if temperatures is not None else (300,)*len(nodes))
    raw=normalized_input_bytes(support=a.support,role="initial_state",name="T0",values=values,unit="K",
        context_digest=context,contract={"placement":StatePlacement.VERTEX_INTENSIVE.value,"semantics":TEMPERATURE.to_dict()},uncertainty=U)
    initial=a.register_state("T0",values,placement=StatePlacement.VERTEX_INTENSIVE,semantics=TEMPERATURE,unit="K",
        uncertainty=U,context_digest=context,source=origin(raw),source_bytes=raw)
    return TransientConduction1D(a,regions=regions,contacts=tuple(contacts),basis=BASIS,initial_time=initial_time,
        initial=initial,admission=admission,provider=provider or SparseFVProvider(),
        method=NumericalMethod("sparse_direct",SolverSettings(tolerances={"residual_rtol":residual_rtol})),
        conservation_atol=Quantity(1e-9,"J"),conservation_rtol=conservation_rtol,
        temperature_atol=Quantity(1e-9,"K"),local_power_atol=Quantity(1e-8,"W"))


def flux(v):return ConductionBoundary(BoundaryKind.INWARD_HEAT_FLUX,Quantity(v,"W/m**2"))
def fixed(v):return ConductionBoundary(BoundaryKind.TEMPERATURE,Quantity(v,"K"))


def test_coordinate_conversion_does_not_revalidate_the_whole_mesh_per_vertex(monkeypatch):
    """Mesh authority checks must not turn coordinate conversion into quadratic work."""
    original = VertexDualAdapter1D.mesh.fget
    reads = []

    def checked_mesh(adapter):
        reads.append(None)
        return original(adapter)

    monkeypatch.setattr(VertexDualAdapter1D, "mesh", property(checked_mesh))
    counts = []
    for cells in (4, 16):
        reads.clear()
        run = session(nodes=tuple(np.linspace(0, 1, cells + 1)))
        assert tuple(run._x) == tuple(np.linspace(0, 1, cells + 1))
        counts.append(len(reads))
    assert counts[0] > 0  # still use the checked public mesh boundary
    assert counts[1] <= counts[0] + 1, counts


def advance(s,dt=.1,*,left=None,right=None,q=None,**overrides):
    window=TimeWindow(s.time,TimePoint(s.basis.basis_id,s.time.seconds+Fraction(str(dt))))
    left=left if left is not None else flux(0)
    right=right if right is not None else flux(0)
    sources=tuple(Quantity(v,"W/m**3") for v in (q if q is not None else (0,)*len(s.regions)))
    raw=forcing_bytes(s.context,window,left,right,sources)
    kw=dict(window=window,dt=Quantity(dt,"s"),left=left,right=right,volumetric_sources=sources,
            source=origin(raw),source_bytes=raw)
    kw.update(overrides)
    return s.step(**kw)


def test_constant_equilibrium_nonuniform_and_dual_sizes():
    s=session()
    result=advance(s,left=fixed(300),right=fixed(300))
    assert s.adapter.read_state(result.temperature)==pytest.approx((300,)*4,abs=1e-9)
    assert s.support.intervals.cell_widths==pytest.approx((.1,.35,.4,.15),abs=1e-14)
    assert result.energy.placement is StatePlacement.DUAL_CELL_INTEGRATED
    assert result.temperature.uncertainty.kind is UncertaintyKind.UNKNOWN
    assert result.execution.diagnostics.error_estimate is None
    assert result.binding["temporal_order"]==1


def test_insulated_nonconstant_both_neumann_transient_conserves_external_total():
    s=session(temperatures=(300,340,310,290))
    # External analytical c=A=1: initial energy = sum(T_i * exact half/midpoint widths).
    before=300*.1+340*.35+310*.4+290*.15
    result=advance(s,.2)
    actual=s.adapter.read_state(result.energy)
    assert math.fsum(actual)==pytest.approx(before,abs=1e-9)
    assert result.inward_boundary_powers==(0,0)
    assert max(s.adapter.read_state(result.temperature))<340


def test_prescribed_boundary_flux_and_sources_independent_energy_balance():
    s=session(regions=(region(area=2,c=3),))
    before=2*3*300*1  # independent continuous geometry/storage formula
    result=advance(s,.25,left=flux(4),right=flux(-1),q=(5,))
    expected_external=.25*(4*2-1*2+5*2*1)
    assert math.fsum(s.adapter.read_state(result.energy))-before==pytest.approx(expected_external,abs=1e-8)
    assert result.inward_boundary_powers==pytest.approx((8,-2),abs=1e-12)
    assert result.source_energy_j==pytest.approx(2.5,abs=1e-12)
    assert result.balance_residual_j==pytest.approx(0,abs=1e-8)


def test_shared_interior_face_has_opposite_local_contributions():
    s=session(temperatures=(300,320,310,300))
    r=advance(s)
    t=s.adapter.read_state(r.temperature)
    # Independently use homogeneous Fourier law; no implementation residual helper.
    expected=[(a-b)/(x1-x0) for a,b,x0,x1 in zip(t[:-1],t[1:],(0,.2,.7),(.2,.7,1))]
    assert r.interior_powers==pytest.approx(expected,abs=1e-9)
    assert math.fsum([-expected[0],expected[0]-expected[1],expected[1]-expected[2],expected[2]])==pytest.approx(0,abs=1e-12)


def test_dirichlet_reaction_accounts_for_endpoint_half_storage():
    s=session()
    advance(s,left=fixed(300),right=fixed(300))
    result=advance(s,left=fixed(310),right=flux(0))
    # Left half volume C=.1; storage increase1J plus outward face power over dt.
    t=s.adapter.read_state(result.temperature)
    expected_left=10+((t[0]-t[1])/.2)
    assert result.inward_boundary_powers[0]==pytest.approx(expected_left,abs=1e-8)
    assert t[0]==pytest.approx(310,abs=1e-9)


def test_material_discontinuity_uses_series_not_arithmetic_conductivity():
    regions=(region(0,.4,k=1,c=2,area=2),region(.4,1,k=10,c=3,area=2))
    s=session(nodes=(0,.8,1),regions=regions)
    r=advance(s,left=fixed(300),right=flux(2))
    t=s.adapter.read_state(r.temperature)
    expected_g=1/(.4/(1*2)+.4/(10*2))
    assert r.interior_powers[0]==pytest.approx(expected_g*(t[0]-t[1]),abs=1e-9)
    assert s._capacity==pytest.approx((1.6,3,0.6),abs=1e-12)


def test_contact_inside_edge_adds_integrated_resistance_and_requires_source():
    p,res=Quantity(.4,"m"),Quantity(.3,"K/W")
    raw=json.dumps({"position":p.to_dict(),"resistance":res.to_dict()},sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    contact=ContactResistance(p,res,origin(raw),raw)
    s=session(nodes=(0,.8,1),contacts=(contact,))
    r=advance(s,right=flux(2))
    t=s.adapter.read_state(r.temperature)
    assert r.interior_powers[0]==pytest.approx((t[0]-t[1])/(.8+.3),abs=1e-9)
    with pytest.raises(NumericalRefusal,match="strictly inside"):
        session(nodes=(0,.4,1),contacts=(contact,))


def test_manufactured_uniform_transient_backward_euler_first_order():
    # T=300+exp(-t), c=k=A=1, q=-exp(-t), insulated. No spatial truncation.
    errors=[]
    for dt in (.1,.05,.025):
        s=session(temperatures=(301,)*4)
        for _ in range(round(1/dt)):
            end=float(s.time.seconds)+dt
            r=advance(s,dt,q=(-math.exp(-end),))
        errors.append(max(abs(v-(300+math.exp(-1))) for v in s.adapter.read_state(r.temperature)))
    assert errors[0]>errors[1]>errors[2]>0
    assert 1.8<errors[0]/errors[1]<2.2
    assert 1.8<errors[1]/errors[2]<2.2


def test_manufactured_sine_source_and_nonuniform_spatial_refinement():
    # Exact steady-in-time T=300+sin(pi*x), q=pi² sin(pi*x), c=k=A=1.
    # Each source is the ANALYTICAL dual-cell average, not nodal q or solver-derived flux.
    errors=[]
    for n in (9,17,33):
        nodes=tuple((i/(n-1))**1.1 for i in range(n))
        edges=(nodes[0],*(.5*a+.5*b for a,b in zip(nodes[:-1],nodes[1:])),nodes[-1])
        regions=tuple(region(a,b) for a,b in zip(edges[:-1],edges[1:]))
        q=tuple(math.pi*(math.cos(math.pi*a)-math.cos(math.pi*b))/(b-a) for a,b in zip(edges[:-1],edges[1:]))
        exact=tuple(300+math.sin(math.pi*x) for x in nodes)
        s=session(nodes=nodes,regions=regions,temperatures=exact)
        for _ in range(20):r=advance(s,.005,left=fixed(300),right=fixed(300),q=q)
        errors.append(max(abs(a-b) for a,b in zip(s.adapter.read_state(r.temperature),exact)))
    assert errors[0]>errors[1]>errors[2]
    assert errors[0]/errors[1]>2.7
    assert errors[1]/errors[2]>2.7


@pytest.mark.parametrize("k,c",[(0,1),(-1,1),(1,0),(1,-1)])
def test_nonpositive_material_coefficients_refuse(k,c):
    with pytest.raises(NumericalRefusal,match="positive"):
        session(regions=(region(k=k,c=c),))


def test_nonfinite_properties_refuse_at_existing_quantity_boundary():
    for v in (math.nan,math.inf):
        with pytest.raises(UnitCompatibilityError):region(k=v)
        with pytest.raises(UnitCompatibilityError):region(c=v)


def test_missing_material_properties_or_payload_and_assumed_physical_input_refuse():
    for bad in (region(missing=True),replace(region(),source_payloads=())):
        with pytest.raises(NumericalRefusal):session(regions=(bad,))
    with pytest.raises(NumericalRefusal,match="assumed physical"):
        session(admission=ConductionAdmission.PHYSICAL_INPUTS)


def test_material_gap_and_undeclared_area_refuse():
    with pytest.raises(NumericalRefusal,match="partition"):
        session(regions=(region(0,.4),region(.5,1)))
    with pytest.raises(NumericalRefusal,match="Quantity"):
        session(regions=(replace(region(),area=None),))


def test_missing_and_inconsistent_initial_conditions_refuse():
    s=session()
    with pytest.raises(NumericalRefusal,match="initial.*Dirichlet"):
        advance(s,left=fixed(301))
    with pytest.raises(NumericalRefusal,match="unusable"):
        advance(s)
    # Constructor boundary itself must reject a missing initial state.
    with pytest.raises(NumericalRefusal,match="initial state"):
        TransientConduction1D(s.adapter,regions=s.regions,contacts=(),basis=BASIS,initial_time=s.initial_time,
            initial=None,admission=ADMISSION,provider=SparseFVProvider(),method=s.method,
            conservation_atol=Quantity(1e-9,"J"),conservation_rtol=1e-12,
            temperature_atol=Quantity(1e-9,"K"),local_power_atol=Quantity(1e-8,"W"))


def test_missing_boundary_source_and_forcing_provenance_refuse():
    for kw in (dict(volumetric_sources=()),dict(source=None),dict(source_bytes=b"wrong")):
        with pytest.raises(NumericalRefusal):advance(session(),**kw)
    s=session()
    with pytest.raises(NumericalRefusal,match="boundary"):
        s.step(window=TimeWindow(s.time,TimePoint(BASIS.basis_id,Fraction(1,10))),dt=Quantity(.1,"s"),
            left=None,right=flux(0),volumetric_sources=(Quantity(0,"W/m**3"),),source=origin(b""),source_bytes=b"")


def test_exact_window_dt_basis_and_clock_identity_refuse():
    wrong=TimeWindow(TimePoint("fixture:other",Fraction(0)),TimePoint("fixture:other",Fraction(1,10)))
    with pytest.raises(NumericalRefusal,match="time-window"):
        advance(session(),window=wrong)
    with pytest.raises(NumericalRefusal,match="time-window"):
        advance(session(),dt=.1,**{"window":TimeWindow(TimePoint(BASIS.basis_id,Fraction(0)),TimePoint(BASIS.basis_id,Fraction(1,5)))})
    s=session();s.time=TimePoint(BASIS.basis_id,Fraction(1,10))
    with pytest.raises(NumericalRefusal,match="clock"):
        advance(s)


def test_stale_mesh_and_current_state_and_build_identity_refuse():
    s=session()
    s.adapter.refine([s.adapter.mesh.cells[0].record_id],minimum_cell=Quantity(.01,"m"),max_ratio=10)
    with pytest.raises(NumericalRefusal,match="stale"):
        advance(s)
    s=session();s.current=replace(s.current)
    with pytest.raises(NumericalRefusal,match="unissued"):
        advance(s)
    class ChangedBuild(SparseFVProvider):
        @property
        def identity(self):return SolverIdentity("changed","2","other")
    s=session();s.provider=ChangedBuild()
    with pytest.raises(NumericalRefusal,match="drift"):
        advance(s)


@pytest.mark.parametrize("state",[ConvergenceState.FAILED,ConvergenceState.NOT_CONVERGED])
def test_failed_or_nonconverged_provider_poisons_without_success(state):
    class Failing(SparseFVProvider):
        def _execute(self,problem,method):
            return failed(problem,self.identity,method,state,NumericalDiagnostics(),"synthetic failure")
    s=session(provider=Failing())
    with pytest.raises(NumericalRefusal,match="provider failure"):
        advance(s)
    assert s.time==s.initial_time
    with pytest.raises(NumericalRefusal,match="unusable"):
        advance(s)


def test_false_provider_residual_is_independently_rejected():
    class Lying(SparseFVProvider):
        def _execute(self,problem,method):
            record=super()._execute(problem,method)
            wrong=dict(record.outputs)
            wrong["temperature"]=tuple(Quantity(2*q.magnitude,"K") for q in wrong["temperature"])
            return replace(record,outputs=wrong,diagnostics=NumericalDiagnostics(residual_norm=0))
    with pytest.raises(NumericalRefusal,match="residual"):
        advance(session(provider=Lying()))


def test_wrong_dirichlet_cannot_hide_behind_large_storage_norm():
    class EndpointLie(SparseFVProvider):
        def _execute(self,problem,method):
            record=super()._execute(problem,method)
            values=list(record.outputs["temperature"])
            values[0]=Quantity(values[0].magnitude+1,"K")
            return replace(record,outputs={"temperature":tuple(values)},diagnostics=NumericalDiagnostics(residual_norm=0))
    with pytest.raises(NumericalRefusal,match="residual|Dirichlet"):
        advance(session(regions=(region(c=1e20),),provider=EndpointLie()),left=fixed(300))


def test_sparse_provider_does_not_convert_to_dense(monkeypatch):
    import scipy.sparse as sparse
    def forbidden(*args,**kwargs):raise AssertionError("dense conversion forbidden")
    monkeypatch.setattr(sparse.csr_matrix,"toarray",forbidden)
    monkeypatch.setattr(sparse.csc_matrix,"toarray",forbidden)
    r=advance(session())
    assert r.execution.succeeded
    assert r.execution.diagnostics.condition.condition_number is None


def test_unsupported_state_dependent_multiphase_and_anisotropic_material_refuse():
    from engcore.materials.identity import ApplicabilityRange
    r=region();d=r.properties.data[0]
    app=replace(d.applicability,ranges=(ApplicabilityRange("temperature",Quantity(1,"K"),Quantity(1000,"K")),))
    claim=replace(d.claim,applicability_context_digest=app.digest)
    changed=PropertyDatum(claim,app,d.origin)
    snap=replace(r.properties.snapshot,claims=tuple(claim if x.claim_id==claim.claim_id else x for x in r.properties.snapshot.claims))
    props=replace(r.properties,snapshot=snap,data=tuple(changed if x.claim.claim_id==claim.claim_id else x for x in r.properties.data))
    with pytest.raises(NumericalRefusal):session(regions=(replace(r,properties=props),))
    with pytest.raises(NumericalRefusal,match="multiphase"):
        session(regions=(region(0,.5),replace(region(.5,1),state=replace(r.state,phase="other_phase"))))
    # Existing Quantity is scalar; tensor/function coefficients cannot enter a material datum.
    with pytest.raises((TypeError,UnitCompatibilityError)):region(k=lambda temperature:temperature)
    with pytest.raises((TypeError,UnitCompatibilityError)):region(k=np.eye(2))


def test_transient_identity_distinct_from_steady_no_validation_promotion():
    assert MODEL.model_id!=STEADY_CONDUCTION_MODEL.model_id
    assert REALIZATION.model.model_id==MODEL.model_id
    assert MODEL.validation_status.value=="unvalidated"
    assert not MODEL.validity.conditions


def test_replacement_storage_or_initial_clock_cannot_change_energy_and_boundary_policy():
    s=session()
    raw=normalized_input_bytes(support=s.support,role="integrated_storage",name="wrong_storage",values=2*s._capacity,
        unit="J/K",context_digest=s.context,contract={"intensive":TEMPERATURE.to_dict(),
        "integrated":s.storage.integrated.to_dict(),"law":"A_i=C_i*u_i/1","density":None},uncertainty=U)
    other=s.adapter.register_storage("wrong_storage",2*s._capacity,intensive=TEMPERATURE,integrated=s.storage.integrated,
        unit="J/K",uncertainty=U,context_digest=s.context,source=origin(raw),source_bytes=raw)
    s.storage=other
    with pytest.raises(NumericalRefusal,match="drift"):
        advance(s)
    s=session();s.initial_time=TimePoint(BASIS.basis_id,Fraction(1,10))
    with pytest.raises(NumericalRefusal,match="drift"):
        advance(s,left=fixed(301))


def test_provider_exception_and_partial_output_publication_poison(monkeypatch):
    class Throws(SparseFVProvider):
        def _execute(self,problem,method):raise RuntimeError("synthetic provider exception")
    s=session(provider=Throws())
    with pytest.raises(RuntimeError,match="provider exception"):advance(s)
    with pytest.raises(NumericalRefusal,match="unusable"):advance(s)
    s=session();initial=s.current
    def no_energy(*args,**kwargs):raise NumericalRefusal("synthetic energy publication failure")
    monkeypatch.setattr(s.adapter,"convert_storage",no_energy)
    with pytest.raises(NumericalRefusal,match="publication failure"):advance(s)
    assert s.current is initial and s.time==s.initial_time
    with pytest.raises(NumericalRefusal,match="unusable"):advance(s)


def test_provider_problem_substitution_and_mutation_refuse():
    class Substitute(SparseFVProvider):
        def _execute(self,problem,method):
            record=super()._execute(problem,method)
            return replace(record,problem_digest="0"*64)
    with pytest.raises(NumericalRefusal,match="identity mismatch"):advance(session(provider=Substitute()))
    class Mutate(SparseFVProvider):
        def _execute(self,problem,method):
            record=super()._execute(problem,method)
            problem.operands["rhs"][0]+=1
            return record
    with pytest.raises(NumericalRefusal,match="identity mismatch"):advance(session(provider=Mutate()))


def test_material_and_state_mutation_during_provider_call_refuse():
    class Mutate(SparseFVProvider):
        callback=None
        def _execute(self,problem,method):
            record=super()._execute(problem,method)
            self.callback()
            return record
    provider=Mutate();s=session(provider=provider)
    provider.callback=lambda:object.__setattr__(s.regions[0],"area",Quantity(2,"m**2"))
    with pytest.raises(NumericalRefusal,match="drift"):advance(s)
    s=session();object.__setattr__(s.regions[0],"source_payloads",(b"changed",))
    with pytest.raises(NumericalRefusal,match="drift"):advance(s)


def test_initial_context_and_contact_origin_and_affine_boundary_refuse():
    s=session()
    other=replace(s.initial,context_digest="0"*64)
    with pytest.raises(NumericalRefusal,match="initial provenance/context"):
        TransientConduction1D(s.adapter,regions=s.regions,contacts=(),basis=BASIS,initial_time=s.initial_time,
            initial=other,admission=ADMISSION,provider=SparseFVProvider(),method=s.method,
            conservation_atol=Quantity(1e-9,"J"),conservation_rtol=1e-12,
            temperature_atol=Quantity(1e-9,"K"),local_power_atol=Quantity(1e-8,"W"))
    contact=ContactResistance(Quantity(.4,"m"),Quantity(.1,"K/W"),origin(b"wrong"),b"wrong")
    with pytest.raises(NumericalRefusal,match="provenance"):session(contacts=(contact,))
    with pytest.raises(NumericalRefusal,match="affine"):
        advance(session(),left=ConductionBoundary(BoundaryKind.TEMPERATURE,Quantity(26.85,"degC")))


# ---- 2026-10-18 remediation D1: independent references and a datum-free conservation tolerance ----------------------

HETEROGENEOUS=lambda:(region(0,.4,k=1,c=2,area=2),region(.4,1,k=10,c=3,area=1))  # noqa: E731


def test_heterogeneous_capacity_with_an_area_jump_matches_hand_integration_and_stays_in_equilibrium():
    # Duals of nodes (0,.4,1): [0,.2], [.2,.7], [.7,1].  C = sum over regions of overlap * c * A:
    # (.2*2*2, .2*2*2 + .3*3*1, .3*3*1) = (.8, 1.7, .9) J/K.  Uniform 300 K, insulated: nothing may move.
    s=session(nodes=(0,.4,1),regions=HETEROGENEOUS())
    assert s._capacity==pytest.approx((.8,1.7,.9),abs=1e-12)
    r=advance(s,.5)
    assert s.adapter.read_state(r.temperature)==pytest.approx((300,300,300),abs=1e-9)
    assert s.adapter.read_state(r.energy)==pytest.approx((240,510,270),abs=1e-9)
    assert r.interior_powers==pytest.approx((0,0),abs=1e-9)


def test_two_material_steady_state_is_the_exact_series_resistance_solution():
    # Steady 1D conduction, no source: the heat rate is uniform and T is piecewise linear, so a vertex scheme with a
    # node at the interface and series edge resistance is EXACT.  R1 = .4/(1*2) = .2 K/W, R2 = .6/(10*1) = .06 K/W.
    # Right end: inward flux 5 W/m^2 on A = 1 m^2 -> 5 W in; left end held at 300 K takes it out.
    # T = (300, 301, 301.3) K.  Backward Euler with dt = 1e6 s damps the slowest mode (lambda = 50/27 1/s) by
    # 1/(1 + dt*lambda) ~ 5.4e-7 per step, so four steps reach the steady state to roundoff.
    s=session(nodes=(0,.4,1),regions=HETEROGENEOUS())
    for _ in range(4):
        r=advance(s,1e6,left=fixed(300),right=flux(5))
    assert s.adapter.read_state(r.temperature)==pytest.approx((300,301,301.3),abs=1e-9)
    assert r.interior_powers==pytest.approx((-5,-5),abs=1e-9)  # face power is T_left - T_right times g
    assert r.inward_boundary_powers==pytest.approx((-5,5),abs=1e-6)


def test_the_conservation_scale_does_not_depend_on_the_temperature_datum():
    # The heat equation is invariant under T -> T + const (with the boundary values shifted alike), so the energy a
    # step exchanges -- and the tolerance the declared rtol buys on it -- must be identical at 300 K and 3000 K.
    # Only the labelled machine-precision floor may grow with |T|.
    results=[]
    for datum in (0,2700):
        s=session(temperatures=tuple(t+datum for t in (300,340,310,290)))
        results.append(advance(s,.2).binding)
    low,high=results
    assert high["conservation_exchange_scale_J"]==pytest.approx(low["conservation_exchange_scale_J"],rel=1e-9)
    policy=[b["conservation_allowance_J"]-b["conservation_arithmetic_floor_J"] for b in results]
    assert policy[1]==pytest.approx(policy[0],rel=1e-9)
    assert high["conservation_arithmetic_floor_J"]<1e-9  # a roundoff floor, far below any declared tolerance here


def test_a_uniform_energy_leak_the_absolute_energy_scale_would_admit_is_refused():
    """Insulated equilibrium at 300 K; a provider adds 1e-7 K to every node (1e-7 J into a closed slab, sum C = 1).

    With residual_rtol 1e-8 the leak passes the solver checks (global ~3.3e-10; rows 1e-7..4e-7 W, smallest row
    allowance ~2.9e-5 W). The old allowance 1e-9 + 1e-6 * sum|C*T| = 3e-4 J admitted it; on the exchanged energy
    (~1e-7 J) the allowance is ~1e-9 J.
    """
    class Leaking(SparseFVProvider):
        def _execute(self,problem,method):
            record=super()._execute(problem,method)
            shifted=tuple(Quantity(q.magnitude+1e-7,"K") for q in record.outputs["temperature"])
            return replace(record,outputs={"temperature":shifted})
    s=session(provider=Leaking(),residual_rtol=1e-8,conservation_rtol=1e-6)
    with pytest.raises(NumericalRefusal,match="energy conservation"):
        advance(s)
    with pytest.raises(NumericalRefusal,match="unusable"):
        advance(s)


@pytest.mark.parametrize("rtol",[1.0,2.0,math.inf,0.0])
def test_a_conservation_rtol_outside_zero_one_is_refused(rtol):
    # at rtol >= 1 an imbalance can be admitted however large (it enters the exchanged energy it is judged against)
    with pytest.raises(NumericalRefusal,match="conservation_rtol"):
        session(conservation_rtol=rtol)


# ---- 2026-10-18 remediation F2: provider build identity, computed once; private SciPy import guarded --------------


def test_provider_identity_is_the_digest_of_the_loaded_bytes_and_reads_no_file_per_access(monkeypatch):
    from pathlib import Path
    import scipy
    import scipy.sparse.linalg._dsolve._superlu as superlu
    from engcore.domains.thermal_models import conduction1d_transient_fv as module
    from engcore.scenarios.timeline import canonical_digest

    # independently recomputed from the same two files: the value the per-access implementation produced
    expected = canonical_digest({"implementation": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
        "superlu_binary": hashlib.sha256(Path(superlu.__file__).read_bytes()).hexdigest(),
        "scipy": scipy.__version__, "numpy": np.__version__, "policy": "sparse-only/1"})
    def no_reads(*_args, **_kwargs):
        raise AssertionError("the provider identity re-read a file")
    monkeypatch.setattr(Path, "read_bytes", no_reads)
    identity = SparseFVProvider().identity
    assert identity.backend == "SuperLU:" + expected
    assert SparseFVProvider().identity == identity
    assert SparseFVProvider().available()


def test_a_missing_private_superlu_makes_the_provider_unavailable_not_the_model_unimportable():
    import os
    from pathlib import Path
    import subprocess
    import sys
    import engcore

    script = (
        "import sys, json\n"
        "import scipy.sparse.linalg\n"  # the public API still works; only the private module is gone
        "sys.modules['scipy.sparse.linalg._dsolve._superlu'] = None\n"
        "from engcore.domains.thermal_models import conduction1d_transient_fv as m\n"
        "p = m.SparseFVProvider()\n"
        "print(json.dumps([m.MODEL.model_id, p.available(), p.identity.backend, p.unavailable_reason]))\n"
    )
    source_root = str(Path(engcore.__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (source_root, os.environ.get("PYTHONPATH", "")) if p))
    out = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, env=env, check=True,
                         timeout=300)  # a wedged scientific import must fail this test, not hang the run
    model_id, available, backend, reason = json.loads(out.stdout.strip().splitlines()[-1])
    assert model_id == MODEL.model_id
    assert available is False and backend == "SuperLU:unavailable"
    assert "superlu" in reason.lower()
