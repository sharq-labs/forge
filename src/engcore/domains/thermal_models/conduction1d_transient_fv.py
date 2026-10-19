"""Bounded phase-constant quasi-1D Fourier FV/BE. Numerical execution, not validation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import scipy
import scipy.sparse as sp
import scipy.sparse.linalg as spla

try:  # SciPy-private: a release that moves it makes the provider unavailable, never the model unimportable
    import scipy.sparse.linalg._dsolve._superlu as _superlu
except ImportError as _superlu_error:  # pragma: no cover - depends on the installed SciPy layout
    _superlu = None
    _SUPERLU_UNAVAILABLE = f"{type(_superlu_error).__name__}: {_superlu_error}"
else:
    _SUPERLU_UNAVAILABLE = ""

from ...materials.identity import MaterialState
from ...materials.properties import MaterialPropertySet, PropertyDerivation
from ...numerical.core import (NumericalRefusal, NumericalProvider, NumericalProblem, NumericalMethod,
    NumericalExecutionRecord, NumericalDiagnostics, ProblemKind, OperatorIdentity, UnitBoundary,
    VariableSpec, array_digest, failed)
from ...numerical.mesh_adaptation import _AuditOnlyRecord, _IssuedRecords
from ...numerical.vertex_state import (VertexDualAdapter1D, VertexState1D, StatePlacement,
                                        normalized_input_bytes)
from ...scenarios.timeline import TimeBasis, TimePoint, TimeWindow, canonical_digest, exact_seconds
from ...scientific.fields.semantics import FieldSemantics
from ...scientific.ir.problem import ModelReference
from ...scientific.knowledge.source import KnowledgeSource, KnowledgeSourceClass
from ...scientific.models.definition import (ScientificModelDefinition, ModelType, ValidityDomain,
                                             ModelInputSpec, ModelOutputSpec, InputSourceKind)
from ...scientific.numerics.conditioning import classify_condition_number
from ...scientific.realizations.definition import ModelRealizationDefinition, ModelFormulation, ImplementationReference
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.semantics import QuantitySemantics, QuantityRole, ConservedQuantity
from ...scientific.solvers.protocol import SolverIdentity, ConvergenceState
from ...scientific.units.quantity import Quantity, is_ratio_scale
from .conduction1d_nonuniform import BoundaryKind, ConductionBoundary
from .conduction1d_schemes import CONDUCTION_1D_TRANSIENT


MODEL = ScientificModelDefinition(
    model_id="thermal.conduction1d.transient_piecewise_linear", version="0.1.0",
    name="Piecewise phase-constant quasi-1D transient Fourier conduction", domain="thermal",
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description="c*A*dT/dt = d/dx(k*A*dT/dx) + q*A; explicit initial and end conditions",
    inputs=tuple(ModelInputSpec(name=name,source_kind=InputSourceKind.PARAMETER,unit_exemplar=unit)
                 for name,unit in (("conductivity","W/m/K"),("volumetric_storage","J/m**3/K"),
                 ("cross_section","m**2"),("initial_temperature","K"),("volumetric_source","W/m**3"))),
    outputs=(ModelOutputSpec("temperature","K"),ModelOutputSpec("integrated_energy","J")),
    assumptions=("scalar linear phase-constant coefficients", "explicit piecewise-constant cross-section",
                 "quasi-1D series transport without lateral/spreading loss", "zero-reference energy C*T"),
    exclusions=("multiphase", "nonlinear or temperature-dependent coefficients", "anisotropy", "moving mesh"),
    validity=ValidityDomain(description="No sourced model applicability limits declared; UNKNOWN, not unlimited."))
REALIZATION = ModelRealizationDefinition(
    realization_id=MODEL.model_id+".vertex_fv_be", version="0.2.0",
    model=ModelReference(MODEL.model_id, MODEL.version), formulation=ModelFormulation.PDE,
    name="Nonuniform vertex FV / Backward Euler", description="Midpoint duals, series edge resistance, BE order1",
    provided_capabilities=frozenset({CONDUCTION_1D_TRANSIENT}),
    assumptions=("declared first-order temporal accuracy, not an executed order result",),
    implementation=ImplementationReference(__name__, "0.2.0", "M1C sparse vertex FV; no M1D adaptation; "
                                           "energy admission on exchanged energy (2026-10-18)"))

#: Legacy machine-epsilon multiplier for the LOCAL balance diagnostic only.
#: It is not a global conservation allowance or a bound on solver/physical error.
#: The independent global gate evaluates its represented inputs exactly.
_BALANCE_ROUNDOFF_FACTOR = 64

ENERGY = ConservedQuantity("thermal:internal_energy_zero_reference", "J")
TEMPERATURE = FieldSemantics("intensive", QuantitySemantics("thermal:absolute_temperature", "K", (QuantityRole.INTENSIVE,)))
INTEGRATED_ENERGY = FieldSemantics("cell_integrated", QuantitySemantics(ENERGY.meaning_id, "J",
                                  (QuantityRole.INTEGRATED,), ENERGY), "m", ENERGY)


class ConductionAdmission(str, Enum):
    SYNTHETIC_FIXTURE = "synthetic_mathematical_fixture/1"
    PHYSICAL_INPUTS = "declared_physical_inputs_not_model_validation/1"


def _q(value, unit, *, positive=False):
    if not isinstance(value, Quantity) or not is_ratio_scale(value.units):
        raise NumericalRefusal("explicit ratio-scale Quantity required; affine or missing input refused")
    number = value.magnitude_in(unit)
    if not math.isfinite(number) or (positive and number <= 0):
        raise NumericalRefusal("coefficient/geometry/time must be finite and strictly positive")
    return number


@dataclass(frozen=True)
class ThermalRegion:
    left: Quantity
    right: Quantity
    area: Quantity
    properties: MaterialPropertySet
    state: MaterialState
    conductivity_id: str
    storage_id: str
    source_payloads: tuple[bytes, ...]

    def __post_init__(self):
        if _q(self.right,"m")<=_q(self.left,"m"):
            raise NumericalRefusal("material interval must be increasing")
        _q(self.area,"m**2",positive=True)
        if not isinstance(self.properties,MaterialPropertySet) or not isinstance(self.state,MaterialState):
            raise NumericalRefusal("typed material property set/state required")
        if (not isinstance(self.conductivity_id,str) or not self.conductivity_id.strip()
                or not isinstance(self.storage_id,str) or not self.storage_id.strip()
                or self.conductivity_id==self.storage_id):
            raise NumericalRefusal("distinct explicit conductivity and storage property IDs required")
        if any(type(b) is not bytes for b in self.source_payloads):
            raise NumericalRefusal("immutable source payload bytes required")
        object.__setattr__(self,"source_payloads",tuple(self.source_payloads))

    def to_dict(self):
        return {"left": self.left.to_dict(), "right": self.right.to_dict(), "area": self.area.to_dict(),
                "properties": self.properties.to_dict(), "state": self.state.to_dict(),
                "conductivity_id": self.conductivity_id, "storage_id": self.storage_id,
                "source_payload_digests": [hashlib.sha256(b).hexdigest() for b in self.source_payloads]}

    def coefficients(self, admission):
        if (not isinstance(self.properties, MaterialPropertySet) or not isinstance(self.state, MaterialState)
                or self.properties.material != self.state.material or not self.state.phase):
            raise NumericalRefusal("exact material property set and declared phase/state required")
        payloads = {hashlib.sha256(b).hexdigest() for b in self.source_payloads if type(b) is bytes}
        if not self.properties.snapshot.sources or any(s.document_digest not in payloads for s in self.properties.snapshot.sources):
            raise NumericalRefusal("material source bytes missing or inconsistent with snapshot")
        resolutions, values = [], []
        for pid, unit in ((self.conductivity_id,"W/m/K"),(self.storage_id,"J/m**3/K")):
            result = self.properties.resolve(pid, self.state)
            allowed = (PropertyDerivation.SOURCED, PropertyDerivation.ASSUMED) if admission is ConductionAdmission.SYNTHETIC_FIXTURE else (PropertyDerivation.SOURCED,)
            if result.status != "known" or result.derivation not in allowed or not result.sources:
                raise NumericalRefusal("missing, ambiguous, assumed physical or interpolated material property")
            used = [d for d in self.properties.data if d.claim.digest in result.claim_digests]
            if len(used) != 1 or used[0].applicability.ranges or not used[0].applicability.phase:
                raise NumericalRefusal("only explicit phase-constant properties supported; state/temperature dependence refused")
            values.append(_q(result.value.value, unit, positive=True))
            resolutions.append(result.to_dict())
        return (*values, tuple(resolutions))


@dataclass(frozen=True)
class ContactResistance:
    position: Quantity
    resistance: Quantity  # integrated K/W, never area-specific resistance
    source: KnowledgeSource
    source_bytes: bytes

    def __post_init__(self):
        _q(self.position,"m")
        _q(self.resistance,"K/W",positive=True)
        if not isinstance(self.source,KnowledgeSource) or type(self.source_bytes) is not bytes:
            raise NumericalRefusal("explicit sourced contact resistance required")

    def to_dict(self):
        return {"position": self.position.to_dict(), "resistance": self.resistance.to_dict(),
                "source":self.source.to_dict(),"source_digest":hashlib.sha256(self.source_bytes).hexdigest()}


def problem_context(adapter, regions, contacts, basis, initial_time, admission):
    """Exact initial context, including explicit geometry/material/clock/formulation declarations."""
    return canonical_digest({"schema": "transient_fv_context/1", "support": adapter.support.record_id,
        "regions": [r.to_dict() for r in regions], "contacts": [r.to_dict() for r in contacts],
        "basis": basis.to_dict(), "initial_time": initial_time.to_dict(), "admission": admission.value,
        "model": MODEL.to_dict(), "realization": REALIZATION.to_dict()})


def forcing_bytes(context, window, left, right, volumetric_sources):
    return json.dumps({"schema": "transient_fv_forcing/1", "context": context, "window": window.to_dict(),
        "left": left.to_dict(), "right": right.to_dict(), "volumetric_sources": [q.to_dict() for q in volumetric_sources]},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _normalization_source(payload, locator):
    return KnowledgeSource("forge:transient_fv_normalization", "FORGE deterministic normalization, not measurement",
        hashlib.sha256(payload).hexdigest(), "1", locator, KnowledgeSourceClass.OTHER)


def _build_digest():
    """The provider build identity: this module's source and the SuperLU binary, as loaded by this process.

    Computed ONCE, at import (F2-1). It used to re-read and re-hash both files on every ``identity`` access --
    about four times per step. The bytes hashed are the same, so an unchanged checkout gives the same digest as
    before. What changes is an edit made on disk after import: the identity keeps the bytes as they were when
    this process imported the module, instead of hashing a file the process never loaded. It is the source file
    at import time, not the bytecode (a stale ``.pyc`` with an unchanged mtime and size is not detected, as
    before), and the binary file as it was at import, which is what the loaded image came from even if the file
    is replaced later. Any failure to read either file makes the provider unavailable, never the module.
    """
    if _superlu is None:
        return None, _SUPERLU_UNAVAILABLE
    try:
        return canonical_digest({"implementation":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "superlu_binary":hashlib.sha256(Path(_superlu.__file__).read_bytes()).hexdigest(),
            "scipy":scipy.__version__,"numpy":np.__version__,"policy":"sparse-only/1"}), ""
    except (OSError, AttributeError, TypeError) as exc:  # pragma: no cover - frozen/zipped installs
        return None, f"provider build identity unavailable: {type(exc).__name__}: {exc}"


_BUILD_DIGEST, _BUILD_UNAVAILABLE = _build_digest()


class SparseFVProvider(NumericalProvider):
    """Existing provider protocol; strictly sparse SuperLU, no dense condition diagnostics."""
    @property
    def identity(self):
        backend = "SuperLU:"+_BUILD_DIGEST if _BUILD_DIGEST is not None else "SuperLU:unavailable"
        return SolverIdentity("forge.thermal_sparse_fv", "0.1.0", backend=backend)
    kinds = frozenset({ProblemKind.LINEAR})
    methods = frozenset({"sparse_direct"})
    unavailable_reason = _BUILD_UNAVAILABLE or "backend is not installed"

    def available(self):
        return _BUILD_DIGEST is not None

    def _execute(self, problem, method):
        tolerance = method.settings.tolerances.get("residual_rtol")
        if tolerance is None or not math.isfinite(tolerance) or tolerance <= 0:
            raise NumericalRefusal("explicit positive residual_rtol required")
        a, b = problem.operands["matrix"], np.asarray(problem.operands["rhs"],dtype=float)
        if not sp.issparse(a):
            raise NumericalRefusal("M1C provider requires sparse operands")
        condition = classify_condition_number(None, method="not estimated: explicit sparse-only M1C policy")
        try:
            x = spla.splu(a.tocsc()).solve(b)
            residual = float(np.linalg.norm(a@x-b)/max(float(np.linalg.norm(b)),1e-300))
        except Exception as exc:
            return failed(problem, self.identity, method, ConvergenceState.FAILED,
                NumericalDiagnostics(condition=condition, termination_message=str(exc)), "sparse linear solve failed")
        diagnostics = NumericalDiagnostics(residual_norm=residual if math.isfinite(residual) else None,
            condition=condition, termination_message="SuperLU sparse solve; residual is not an error bound")
        if not np.all(np.isfinite(x)) or not math.isfinite(residual) or residual > tolerance:
            return failed(problem, self.identity, method, ConvergenceState.FAILED, diagnostics,"residual admission failed")
        return NumericalExecutionRecord(problem.digest, problem.identity(), self.identity, method,
            ConvergenceState.NOT_APPLICABLE, problem.unknowns.from_array(x), diagnostics)


@dataclass(frozen=True)
class ThermalStep(_AuditOnlyRecord):
    window: TimeWindow
    temperature: VertexState1D
    energy: VertexState1D
    execution: NumericalExecutionRecord
    binding: dict
    interior_powers: tuple[float, ...]
    inward_boundary_powers: tuple[float, float]
    source_powers: tuple[float, ...]
    local_residual_w: tuple[float, ...]
    energy_change_j: float
    boundary_energy_j: float
    source_energy_j: float
    balance_residual_j: float

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema": "transient_fv_step/1", "window": self.window.to_dict(),
                "temperature": self.temperature.to_dict(), "energy": self.energy.to_dict(),
                "execution": self.execution.to_dict(), "binding": self.binding,
                "interior_powers_W": list(self.interior_powers), "inward_boundary_powers_W": list(self.inward_boundary_powers),
                "source_powers_W": list(self.source_powers), "local_residual_W": list(self.local_residual_w),
                "energy_change_J": self.energy_change_j, "boundary_energy_J": self.boundary_energy_j,
                "source_energy_J": self.source_energy_j, "balance_residual_J": self.balance_residual_j,
                "uncertainty": Uncertainty.unknown("numerical error and model discrepancy unquantified").to_dict(),
                "classification": "numerical_balance_not_certified_error_or_physical_validation"}


class TransientConduction1D:
    """One fixed issued mesh, serial BE steps. Any failed step attempt poisons continuation."""
    def __init__(self, adapter: VertexDualAdapter1D, *, regions: tuple[ThermalRegion,...],
                 contacts: tuple[ContactResistance,...], basis: TimeBasis, initial_time: TimePoint,
                 initial: VertexState1D, admission: ConductionAdmission, provider: NumericalProvider,
                 method: NumericalMethod, conservation_atol: Quantity, conservation_rtol: float,
                 temperature_atol: Quantity, local_power_atol: Quantity):
        if (not isinstance(adapter,VertexDualAdapter1D) or not isinstance(admission,ConductionAdmission)
                or not isinstance(basis,TimeBasis) or not isinstance(initial_time,TimePoint)
                or initial_time.basis_id != basis.basis_id or not isinstance(provider,SparseFVProvider)):
            raise NumericalRefusal("explicit M1C adapter/admission/clock/provider required")
        if (not isinstance(method,NumericalMethod) or method.method != "sparse_direct"
                or not math.isfinite(method.settings.tolerances.get("residual_rtol",0))
                or method.settings.tolerances.get("residual_rtol",0) <= 0):
            raise NumericalRefusal("qualified sparse_direct method and explicit positive tolerance required")
        self.adapter, self.regions, self.contacts = adapter, tuple(regions), tuple(contacts)
        self.basis, self.initial_time, self.time = basis, initial_time, initial_time
        self.admission, self.provider, self.method = admission, provider, method
        self.atol = _q(conservation_atol,"J",positive=True)
        self.temperature_atol=_q(temperature_atol,"K",positive=True)
        self.local_power_atol=_q(local_power_atol,"W",positive=True)
        if not math.isfinite(conservation_rtol) or conservation_rtol <= 0 or conservation_rtol >= 1:
            # a fraction of the step's exchanged energy; an imbalance itself enters sum|C*dT|, so what is admitted
            # is up to rtol/(1 - rtol) of the rest of the exchange -- unbounded at rtol >= 1, and already of the
            # order of the whole exchange near 1. Declare rtol << 1.
            raise NumericalRefusal("explicit finite conservation_rtol in (0, 1) required")
        self.rtol = conservation_rtol
        self.support = adapter.support
        self.context = problem_context(adapter,self.regions,self.contacts,basis,initial_time,admission)
        self._issued, self._unusable = _IssuedRecords(), False
        if not isinstance(initial,VertexState1D) or initial.placement is not StatePlacement.VERTEX_INTENSIVE or initial.semantics != TEMPERATURE:
            raise NumericalRefusal("exact sourced M1B vertex temperature initial state required")
        if initial.context_digest != self.context or initial.source is None:
            raise NumericalRefusal("initial provenance/context does not bind this material/geometry/clock problem")
        t = np.asarray(adapter.read_state(initial),dtype=float)*Quantity(1,initial.unit).magnitude_in("K")
        if np.any(t <= 0):
            raise NumericalRefusal("initial absolute temperature must be positive")
        self.initial, self.current, self._temperatures = initial, initial, t
        # The checked accessor validates the complete mesh lineage. Read it once
        # for this coordinate conversion, rather than once per vertex. Later
        # operations still run their existing live state and lineage guards.
        grid = adapter.mesh.grid
        self._x = np.asarray([_q(Quantity(v,grid.unit),"m") for v in grid.nodes])
        boundaries = np.asarray([_q(Quantity(v,self.support.intervals.unit),"m") for v in self.support.intervals.nodes])
        self._bounds, self._overlap, self._areas, self._conductivity, cv, resolutions = self._geometry()
        dual_overlap = np.maximum(0,np.minimum(boundaries[1:,None],self._bounds[None,1:])-np.maximum(boundaries[:-1,None],self._bounds[None,:-1]))
        self._volumes = dual_overlap*self._areas[None,:]
        self._capacity = self._volumes@cv
        edge_overlap = np.maximum(0,np.minimum(self._x[1:,None],self._bounds[None,1:])-np.maximum(self._x[:-1,None],self._bounds[None,:-1]))
        resistance = np.sum(edge_overlap/(self._conductivity*self._areas)[None,:],axis=1)
        used = set()
        for contact in self.contacts:
            expected=json.dumps({"position":contact.position.to_dict(),"resistance":contact.resistance.to_dict()},
                                sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
            adapter._source(contact.source,contact.source_bytes,expected)
            p, r = _q(contact.position,"m"), _q(contact.resistance,"K/W",positive=True)
            index = np.flatnonzero((self._x[:-1]<p)&(p<self._x[1:]))
            if len(index)!=1 or p in used:
                raise NumericalRefusal("contact resistance requires unique position strictly inside a primal edge")
            resistance[index[0]] += r
            used.add(p)
        self._conductance = 1/resistance
        if (not np.all(np.isfinite(self._capacity)) or np.any(self._capacity<=0)
                or not np.all(np.isfinite(self._conductance)) or np.any(self._conductance<=0)):
            raise NumericalRefusal("nonfinite or nonpositive integrated capacity/conductance")
        self.material_resolutions = resolutions
        payload = normalized_input_bytes(support=self.support,role="integrated_storage",name="m1c_storage",
            values=self._capacity,unit="J/K",context_digest=self.context,
            contract={"intensive":TEMPERATURE.to_dict(),"integrated":INTEGRATED_ENERGY.to_dict(),
                      "law":"A_i=C_i*u_i/1","density":None},uncertainty=Uncertainty.unknown())
        self.storage = adapter.register_storage("m1c_storage",self._capacity,intensive=TEMPERATURE,integrated=INTEGRATED_ENERGY,
            unit="J/K",uncertainty=Uncertainty.unknown(),context_digest=self.context,
            source=_normalization_source(payload,"forge:material-resolution:"+self.context),source_bytes=payload)
        self.energy = adapter.convert_storage(initial,self.storage,name="m1c_energy_initial")
        self._config_digest = canonical_digest(self._configuration())
        self._clock = canonical_digest(self.time.to_dict())
        self._current_ids = (self.current.record_id,self.energy.record_id)

    def _geometry(self):
        if not self.regions or any(not isinstance(r,ThermalRegion) for r in self.regions):
            raise NumericalRefusal("explicit complete piecewise material/geometry partition required")
        if len({r.state.phase for r in self.regions})!=1:
            raise NumericalRefusal("multiphase conduction is unsupported")
        edges=[_q(self.regions[0].left,"m")]
        areas, k, c, resolutions=[],[],[],[]
        for region in self.regions:
            left,right=_q(region.left,"m"),_q(region.right,"m")
            if left != edges[-1] or right <= left:
                raise NumericalRefusal("material partition has gap/overlap/reversed interval")
            edges.append(right)
            areas.append(_q(region.area,"m**2",positive=True))
            kr,cr,rr=region.coefficients(self.admission)
            k.append(kr);c.append(cr);resolutions.append(rr)
        if edges[0] != self._x[0] or edges[-1] != self._x[-1]:
            raise NumericalRefusal("material partition must exactly cover declared grid")
        return np.asarray(edges),None,np.asarray(areas),np.asarray(k),np.asarray(c),tuple(resolutions)

    def _configuration(self):
        return {"context":self.context,"support":self.support.record_id,"initial":self.initial.record_id,
                "regions":[r.to_dict() for r in self.regions],"contacts":[c.to_dict() for c in self.contacts],
                "basis":self.basis.to_dict(),"initial_time":self.initial_time.to_dict(),
                "storage_id":self.storage.record_id,"provider":self.provider.identity.to_dict(),"method":self.method.to_dict(),
                "model":MODEL.to_dict(),"realization":REALIZATION.to_dict(),"admission":self.admission.value,
                "conservation_atol_J":self.atol,"conservation_rtol":self.rtol,
                "temperature_atol_K":self.temperature_atol,"local_power_atol_W":self.local_power_atol,
                "capacity":self._capacity.tolist(),"conductance":self._conductance.tolist(),
                "volumes":self._volumes.tolist(),"x":self._x.tolist(),"bounds":self._bounds.tolist(),
                "areas":self._areas.tolist(),"material_resolutions":self.material_resolutions}

    def _guard(self):
        if self._unusable:
            raise NumericalRefusal("transient session unusable after failed step attempt")
        self._issued.verify()
        if self.adapter.support is not self.support or canonical_digest(self._configuration()) != self._config_digest:
            raise NumericalRefusal("stale mesh/support or material/provider/build/configuration drift")
        if (canonical_digest(self.time.to_dict()) != self._clock
                or (self.current.record_id,self.energy.record_id) != self._current_ids):
            raise NumericalRefusal("clock/current state binding drift")
        self.adapter.read_state(self.initial)
        actual=np.asarray(self.adapter.read_state(self.current),dtype=float)*Quantity(1,self.current.unit).magnitude_in("K")
        if not np.array_equal(actual,self._temperatures):
            raise NumericalRefusal("current temperature/state identity mismatch")
        self.adapter.read_state(self.energy)
        self.adapter._current(self.storage,self.adapter._coefficients)
        coefficients=np.asarray(self.adapter._runtime._resolver.resolve(self.storage.data),dtype=float)*Quantity(1,self.storage.unit).magnitude_in("J/K")
        if not np.array_equal(coefficients,self._capacity):
            raise NumericalRefusal("live storage differs from assembled integrated capacity")

    def step(self, *, window: TimeWindow, dt: Quantity, left: ConductionBoundary, right: ConductionBoundary,
             volumetric_sources: tuple[Quantity,...], source: KnowledgeSource, source_bytes: bytes):
        try:
            self._guard()
            return self._step(window,dt,left,right,tuple(volumetric_sources),source,source_bytes)
        except Exception:
            self._unusable=True
            raise

    def _step(self,window,dt,left,right,sources,source,source_bytes):
        if (not isinstance(window,TimeWindow) or window.start != self.time or window.basis_id != self.basis.basis_id
                or exact_seconds(dt,"step dt") != window.end.seconds-window.start.seconds):
            raise NumericalRefusal("step time-window/start/basis/dt identity mismatch")
        seconds=_q(dt,"s",positive=True)
        if not isinstance(left,ConductionBoundary) or not isinstance(right,ConductionBoundary):
            raise NumericalRefusal("both explicit typed end boundary conditions required")
        for bc in (left,right):
            _q(bc.value,"K" if bc.kind is BoundaryKind.TEMPERATURE else "W/m**2",positive=bc.kind is BoundaryKind.TEMPERATURE)
        if len(sources)!=len(self.regions):
            raise NumericalRefusal("explicit volumetric source per material region required, including zero")
        expected=forcing_bytes(self.context,window,left,right,sources)
        self.adapter._source(source,source_bytes,expected)
        powers=self._volumes@np.asarray([_q(q,"W/m**3") for q in sources])
        old=self._temperatures.copy()
        if self.time == self.initial_time:
            for bc,index in ((left,0),(right,-1)):
                if bc.kind is BoundaryKind.TEMPERATURE and abs(old[index]-bc.si_value())>self.temperature_atol:
                    raise NumericalRefusal("initial temperature conflicts with initial Dirichlet boundary")
        n=len(old); g=self._conductance
        diag=self._capacity/seconds+np.r_[g,0]+np.r_[0,g]
        lower,upper=-g.copy(),-g.copy()
        rhs=self._capacity/seconds*old+powers
        boundary=[0.0,0.0]
        for end,(bc,index,area) in enumerate(((left,0,self._areas[0]),(right,n-1,self._areas[-1]))):
            if bc.kind is BoundaryKind.INWARD_HEAT_FLUX:
                boundary[end]=bc.si_value()*area
                rhs[index]+=boundary[end]
            else:
                # Keep all equation rows in power units; never mix K and W in residual scaling.
                rhs[index]=diag[index]*bc.si_value()
                if index==0:upper[0]=0
                else:lower[-1]=0
        matrix=sp.diags((lower,diag,upper),(-1,0,1),shape=(n,n),format="csr")
        binding={"context":self.context,"initial":self.initial.record_id,"previous":self.current.record_id,
                 "previous_energy":self.energy.record_id,"storage":self.storage.record_id,"support":self.support.record_id,
                 "mesh_version":self.support.mesh.version_id,"dt":dt.to_dict(),"window":window.to_dict(),
                 "forcing_source":source.to_dict(),"forcing_digest":hashlib.sha256(source_bytes).hexdigest(),
                 "left":left.to_dict(),"right":right.to_dict(),"sources":[q.to_dict() for q in sources],
                 "configuration":self._config_digest,"temporal_order":1,"model":MODEL.to_dict(),"realization":REALIZATION.to_dict()}
        problem=NumericalProblem("thermal.transient_fv."+canonical_digest(binding),ProblemKind.LINEAR,
            OperatorIdentity("thermal.vertex_fv_be","0.1.0",array_digest(matrix,rhs),"array_bytes"),
            UnitBoundary((VariableSpec("temperature","K",size=n),)),operands={"matrix":matrix.copy(),"rhs":rhs.copy()},window=window)
        expected_problem=problem.digest
        expected_identity=problem.identity()
        execution=self.provider.execute(problem,self.method)
        if (not isinstance(execution,NumericalExecutionRecord) or not execution.succeeded
                or problem.digest!=expected_problem or execution.problem_digest!=expected_problem or execution.provider!=self.provider.identity
                or execution.method.to_dict()!=self.method.to_dict() or execution.problem_identity!=expected_identity):
            raise NumericalRefusal("provider failure/non-convergence or execution identity mismatch")
        new=problem.unknowns.to_array(execution.outputs)
        residual=float(np.linalg.norm(matrix@new-rhs)/max(float(np.linalg.norm(rhs)),1e-300))
        if not np.all(np.isfinite(new)) or np.any(new<=0) or not math.isfinite(residual) or residual>self.method.settings.tolerances["residual_rtol"]:
            raise NumericalRefusal("independent solver residual or state admission failed")
        row_residual=np.abs(matrix@new-rhs)
        row_allowance=self.local_power_atol+self.method.settings.tolerances["residual_rtol"]*(abs(matrix)@abs(new)+abs(rhs))
        if np.any(row_residual>row_allowance):
            raise NumericalRefusal("independent row-wise power residual admission failed")
        for bc,index in ((left,0),(right,-1)):
            if bc.kind is BoundaryKind.TEMPERATURE and abs(new[index]-bc.si_value())>self.temperature_atol:
                raise NumericalRefusal("post-solve Dirichlet temperature constraint failed")
        faces=g*(new[:-1]-new[1:])
        internal=np.r_[0,faces]-np.r_[faces,0]
        storage_rate=self._capacity*(new-old)/seconds
        for end,(bc,index) in enumerate(((left,0),(right,-1))):
            if bc.kind is BoundaryKind.TEMPERATURE:
                boundary[end]=storage_rate[index]-internal[index]-powers[index]
        local=storage_rate-internal-powers
        local[0]-=boundary[0];local[-1]-=boundary[1]
        delta=math.fsum(float(c)*(float(b)-float(a)) for c,a,b in zip(self._capacity,old,new))
        boundary_energy=seconds*math.fsum(boundary);source_energy=seconds*math.fsum(map(float,powers))
        balance=delta-boundary_energy-source_energy
        # The declared relative tolerance applies to the energy this step actually moves, which is independent of
        # the temperature datum: the larger of the internal redistribution sum|C*dT| and the external energy
        # dt*(|boundary| + |sources|). It was applied to sum|C*T|, energy from 0 K, so the admitted imbalance grew
        # with the absolute temperature level rather than with the heat exchanged. Interior face powers are left
        # out: they cancel in the balance and would make the tolerance grow with the node count. The global gate
        # below evaluates represented inputs exactly. The legacy matrix-based allowance is retained separately
        # for the local diagnostic and cannot relax that global gate.
        exchange=max(math.fsum(abs(float(c)*(float(b)-float(a))) for c,a,b in zip(self._capacity,old,new)),
                     seconds*(abs(boundary[0])+abs(boundary[1])+math.fsum(abs(float(p)) for p in powers)))
        # Preserve the existing local residual diagnostic and its arithmetic allowance.
        # It may not relax the independent global conservation admission below.
        local_arithmetic=_BALANCE_ROUNDOFF_FACTOR*np.finfo(float).eps*seconds*math.fsum(map(float,abs(matrix)@np.abs(new)+np.abs(rhs)))
        local_allowance=self.atol+self.rtol*exchange+local_arithmetic
        if (not all(math.isfinite(v) for v in (delta,boundary_energy,source_energy,balance,
                                               exchange,local_arithmetic,local_allowance))
                or not np.all(np.isfinite(local))):
            raise NumericalRefusal("non-finite energy conservation arithmetic; session cannot continue")
        # Exact arithmetic on the represented inputs: this bounds neither solver
        # error nor physical/model uncertainty. Solver drift above the declared
        # conservation tolerance is refused, even if its row residual is small.
        f=lambda value: Fraction.from_float(float(value))
        changes=tuple(f(c)*(f(b)-f(a)) for c,a,b in zip(self._capacity,old,new))
        exact_dt=f(seconds)
        exact_boundary=exact_dt*sum(map(f,boundary),Fraction(0))
        exact_source=exact_dt*sum(map(f,powers),Fraction(0))
        exact_delta=sum(changes,Fraction(0))
        exact_balance=exact_delta-exact_boundary-exact_source
        exact_exchange=max(sum(map(abs,changes),Fraction(0)),
            exact_dt*(sum((abs(f(b)) for b in boundary),Fraction(0))+
                      sum((abs(f(p)) for p in powers),Fraction(0))))
        exact_allowance=f(self.atol)+f(self.rtol)*exact_exchange
        if (abs(exact_balance)>exact_allowance or np.max(np.abs(local))*seconds>local_allowance):
            raise NumericalRefusal("energy conservation admission failed; session cannot continue")
        try:
            allowance=float(exact_allowance)
            exchange_display=float(exact_exchange)
        except OverflowError as exc:
            raise NumericalRefusal("non-finite energy conservation display; session cannot continue") from exc
        if not all(math.isfinite(v) for v in (allowance,exchange_display)):
            raise NumericalRefusal("non-finite energy conservation display; session cannot continue")
        # Recheck frozen inputs/live parent state after provider execution, before publishing.
        self._guard()
        binding.update(actual_residual=residual,row_residual_W=row_residual.tolist(),conservation_allowance_J=allowance,
                       conservation_exchange_scale_J=exchange_display,conservation_arithmetic_floor_J=0.0,
                       conservation_admission_policy="exact_represented_inputs_global/1",
                       conservation_exact_balance_J=str(exact_balance),conservation_exact_allowance_J=str(exact_allowance),
                       local_conservation_allowance_J=local_allowance,local_conservation_arithmetic_floor_J=local_arithmetic,
                       dirichlet_reaction_notice="reconstructed boundary reaction, not independent measured flux")
        step_id=canonical_digest(binding)
        temperature=self.adapter._publish("m1c_temperature_"+step_id,new,StatePlacement.VERTEX_INTENSIVE,TEMPERATURE,
            "K",Uncertainty.unknown(),self.context,None,(self.current.record_id,self.storage.record_id))
        energy=self.adapter.convert_storage(temperature,self.storage,name="m1c_energy_"+step_id)
        result=self._issued.issue(ThermalStep(window,temperature,energy,execution,binding,tuple(map(float,faces)),
            tuple(map(float,boundary)),tuple(map(float,powers)),tuple(map(float,local)),delta,boundary_energy,source_energy,balance))
        self.current,self.energy,self._temperatures,self.time=temperature,energy,new.copy(),window.end
        self._clock=canonical_digest(self.time.to_dict())
        self._current_ids=(self.current.record_id,self.energy.record_id)
        return result
