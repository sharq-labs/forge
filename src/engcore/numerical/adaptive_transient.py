"""M1D physics-neutral serial coordination. Declared decisions are not error evidence."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import hashlib
import math

from ..scenarios.timeline import TimeWindow, canonical_digest
from ..scientific.knowledge.source import KnowledgeSource
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from .core import NumericalRefusal
from .mesh_adaptation import Bisection1D, _AuditOnlyRecord, _IssuedRecords


class AdaptiveAdmission(str, Enum):
    OD6_ISSUED_ADAPTIVE_WINDOWS_V1 = "od6_issued_adaptive_windows/1"


class MeshOperation(str, Enum):
    REFINE = "refine"
    COARSEN = "coarsen"


@dataclass(frozen=True)
class DeclaredCriterion(_AuditOnlyRecord):
    criterion_id: str
    version: str
    definition: bytes
    source: KnowledgeSource

    def require(self):
        if (not isinstance(self.criterion_id,str) or not self.criterion_id.strip()
                or not isinstance(self.version,str) or not self.version.strip()
                or type(self.definition) is not bytes or not self.definition
                or not isinstance(self.source,KnowledgeSource)
                or hashlib.sha256(self.definition).hexdigest()!=self.source.document_digest):
            raise NumericalRefusal("explicit versioned criterion definition and matching source bytes required")

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema":"declared_adaptation_criterion/1","id":self.criterion_id,"version":self.version,
                "definition_digest":hashlib.sha256(self.definition).hexdigest(),"source":self.source.to_dict(),
                "classification":"declared_selection_rule_not_verified_error_estimator"}


@dataclass(frozen=True)
class AdaptationDecision(_AuditOnlyRecord):
    criterion: DeclaredCriterion
    operation: MeshOperation
    mesh_version: str
    state_id: str
    instant: dict
    basis_step_id: str
    cells: tuple[str,...]
    bisections: tuple[Bisection1D,...]
    minimum_cell: Quantity | None
    max_ratio: float

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema":"issued_adaptation_decision/1","criterion":self.criterion.to_dict(),
                "operation":self.operation.value,"mesh_version":self.mesh_version,"state":self.state_id,
                "instant":self.instant,"basis_step":self.basis_step_id,"cells":list(self.cells),
                "bisections":[b.to_dict() for b in self.bisections],
                "minimum_cell":None if self.minimum_cell is None else self.minimum_cell.to_dict(),
                "max_ratio":self.max_ratio}


@dataclass(frozen=True)
class AdaptiveHistory(_AuditOnlyRecord):
    sequence: int
    parent: str
    status: str
    before: dict
    after: dict
    details: dict

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema":"adaptive_transient_history/1","sequence":self.sequence,"parent":self.parent,
                "status":self.status,"before":self.before,"after":self.after,"details":self.details,
                "uncertainty":Uncertainty.unknown("adaptive spatial/temporal error and discrepancy unquantified").to_dict(),
                "classification":"execution_history_not_physical_validation"}


class AdaptiveBackend1D(ABC):
    """Domain boundary: a backend computes/rebuilds and owns qualified recovery."""
    @abstractmethod
    def guard(self): ...
    @abstractmethod
    def identity_material(self): ...
    @abstractmethod
    def checkpoint(self): ...
    @abstractmethod
    def restore(self,checkpoint): ...
    @abstractmethod
    def advance(self,**forcing): ...
    @abstractmethod
    def prepare_rebuild(self): ...
    @abstractmethod
    def rebuild(self,permit,transition,transferred,receipt,target): ...
    @abstractmethod
    def poison(self): ...


class AdaptiveTransient1D:
    def __init__(self,backend:AdaptiveBackend1D,*,criteria:tuple[DeclaredCriterion,...],admission:AdaptiveAdmission):
        if not isinstance(backend,AdaptiveBackend1D) or admission is not AdaptiveAdmission.OD6_ISSUED_ADAPTIVE_WINDOWS_V1:
            raise NumericalRefusal("explicit qualified adaptive backend and versioned admission required")
        self.backend=backend
        self._owner_backend=backend
        self._issued=_IssuedRecords()
        self._criteria={}
        for criterion in criteria:
            if not isinstance(criterion,DeclaredCriterion):
                raise NumericalRefusal("typed declared criteria required")
            criterion.require()
            key=(criterion.criterion_id,criterion.version)
            if key in self._criteria:
                raise NumericalRefusal("conflicting duplicate criterion identity")
            self._criteria[key]=self._issued.issue(criterion)
        self._history=[]
        self._criterion_roster=tuple(sorted((key,c.record_id) for key,c in self._criteria.items()))
        self._root=canonical_digest(backend.identity_material())
        self._expected_backend=backend.identity_material()
        self._head=self._root
        self._last_step=None
        self._poisoned=False

    def _guard(self):
        if self._poisoned:
            raise NumericalRefusal("adaptive execution poisoned; complete safe restoration unavailable")
        if self.backend is not self._owner_backend:
            raise NumericalRefusal("adaptive backend instance substituted")
        self.backend.guard()
        if self.backend.identity_material()!=self._expected_backend:
            raise NumericalRefusal("uncommitted backend state/time drift")
        self._issued.verify()
        parent=self._root
        for index,event in enumerate(self._history):
            self._issued.require(event)
            if event.sequence!=index or event.parent!=parent:
                raise NumericalRefusal("missing or inconsistent adaptive history")
            parent=event.record_id
        if parent!=self._head:
            raise NumericalRefusal("adaptive history head mismatch")
        for criterion in self._criteria.values():
            self._issued.require(criterion)
            criterion.require()
        if tuple(sorted((key,c.record_id) for key,c in self._criteria.items()))!=self._criterion_roster:
            raise NumericalRefusal("declared criterion roster changed")
        if self._last_step is not None:
            self._issued.require(self._last_step)

    @property
    def history(self):
        self._guard()
        return tuple(self._history)

    @property
    def audit_history(self):
        """Retain refusal/poison audit access; never admits execution or a usable result."""
        parent=self._root
        for index,event in enumerate(self._history):
            self._issued.require(event)
            if event.sequence!=index or event.parent!=parent:
                raise NumericalRefusal("inconsistent adaptive audit history")
            parent=event.record_id
        if parent!=self._head:
            raise NumericalRefusal("adaptive audit head mismatch")
        return tuple(self._history)

    def _record(self,status,before,details):
        after={"classification":"poisoned_indeterminate_state"} if self._poisoned else self.backend.identity_material()
        event=self._issued.issue(AdaptiveHistory(len(self._history),self._head,status,before,after,details))
        self._history.append(event);self._head=event.record_id
        return event

    def _failed(self,checkpoint,before,error):
        try:
            self.backend.restore(checkpoint)
            self.backend.guard()
            if self.backend.identity_material()!=before:
                raise NumericalRefusal("restored backend differs from complete window start")
        except Exception as restoration:
            self._poisoned=True
            self.backend.poison()
            self._record("poisoned",before,{"failure_type":type(error).__name__,"restore_failure_type":type(restoration).__name__})
            raise NumericalRefusal("adaptive failure: complete restoration refused; execution poisoned") from error
        self._record("rolled_back_refused_attempt",before,{"failure_type":type(error).__name__,
                     "notice":"no window accepted and no automatic retry"})

    def advance(self,**forcing):
        self._guard()
        window=forcing.get("window")
        if not isinstance(window,TimeWindow) or window.start.to_dict()!=self.backend.identity_material()["instant"]:
            raise NumericalRefusal("adaptive window must start at exact current clock")
        before=self.backend.identity_material()
        checkpoint=self.backend.checkpoint()
        try:
            result=self.backend.advance(**forcing)
            self.backend.guard()
            if result.window!=window or self.backend.identity_material()["instant"]!=window.end.to_dict():
                raise NumericalRefusal("backend accepted wrong time window")
            self._issued.issue(result)
            event=self._record("accepted_window",before,{"result":result.to_dict()})
            self._expected_backend=self.backend.identity_material()
            self._last_step=result
            return result,event
        except Exception as exc:
            self._failed(checkpoint,before,exc)
            raise

    def declare_decision(self,criterion:DeclaredCriterion,operation:MeshOperation,*,cells=(),bisections=(),
                         minimum_cell:Quantity|None=None,max_ratio:float):
        self._guard()
        self._issued.require(criterion);criterion.require()
        if self._criteria.get((criterion.criterion_id,criterion.version)) is not criterion or self._last_step is None:
            raise NumericalRefusal("registered criterion and accepted numerical basis required")
        if not isinstance(operation,MeshOperation):
            raise NumericalRefusal("explicit supported mesh operation required")
        if isinstance(max_ratio,bool) or not math.isfinite(max_ratio) or max_ratio<1:
            raise NumericalRefusal("explicit finite neighbour ratio >=1 required")
        if (operation is MeshOperation.REFINE and (not cells or bisections or minimum_cell is None)
                or operation is MeshOperation.COARSEN and (cells or not bisections or minimum_cell is not None)):
            raise NumericalRefusal("refinement selection/minimum or recorded coarsening siblings required")
        material=self.backend.identity_material()
        return self._issued.issue(AdaptationDecision(criterion,operation,material["mesh_version"],material["state"],
            material["instant"],self._last_step.record_id,tuple(cells),tuple(bisections),minimum_cell,max_ratio))

    def adapt(self,decision:AdaptationDecision,*,target):
        self._guard();self._issued.require(decision)
        self._issued.require(decision.criterion);decision.criterion.require()
        before=self.backend.identity_material()
        if (decision.mesh_version!=before["mesh_version"] or decision.state_id!=before["state"]
                or decision.instant!=before["instant"] or self._last_step is None
                or decision.basis_step_id!=self._last_step.record_id):
            raise NumericalRefusal("stale adaptation decision/basis/state/time")
        checkpoint=self.backend.checkpoint()
        try:
            permit=self.backend.prepare_rebuild()
            adapter=self.backend.adapter
            conserved=self.backend.conserved_state
            if decision.operation is MeshOperation.REFINE:
                transition=adapter.refine(decision.cells,minimum_cell=decision.minimum_cell,max_ratio=decision.max_ratio)
            else:
                transition=adapter.coarsen(decision.bisections,max_ratio=decision.max_ratio)
            transferred,receipt=adapter.transfer_state(conserved,transition)
            rebuilt=self.backend.rebuild(permit,transition,transferred,receipt,target)
            self.backend.guard()
            event=self._record("accepted_adaptation",before,{"decision":decision.to_dict(),
                "transition":transition.to_dict(),"transfer":receipt.to_dict(),"rebuild":rebuilt})
            self._expected_backend=self.backend.identity_material()
            return transition,receipt,event
        except Exception as exc:
            self._failed(checkpoint,before,exc)
            raise
