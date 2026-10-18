"""Thermal M1D backend. Same-object window rollback only; mesh recovery fails closed."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import weakref
from pathlib import Path

import numpy as np

from ...execution.multiphysics.external import CheckpointSeal
from ...numerical.adaptive_transient import AdaptiveBackend1D
from ...numerical.core import NumericalRefusal
from ...numerical.mesh_adaptation import _AuditOnlyRecord, _IssuedRecords
from ...scenarios.timeline import canonical_digest
from .conduction1d_transient_fv import TransientConduction1D, SparseFVProvider


def _resource_bytes(value):
    def require(v):
        if type(v) is dict:
            if any(type(k) is not str for k in v):
                raise NumericalRefusal("recoverable resource dict requires string keys")
            for item in v.values():require(item)
        elif type(v) is list:
            for item in v:require(item)
        elif type(v) not in (str,int,float,bool,type(None)) or type(v) is float and not math.isfinite(v):
            raise NumericalRefusal("opaque/nonfinite provider/cache resource cannot be checkpointed")
    require(value)
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class ThermalRebuildTarget:
    regions: tuple
    contacts: tuple


@dataclass(frozen=True)
class _WindowSnapshot(_AuditOnlyRecord):
    session: object
    mesh: object
    support: object
    configuration: str
    current: object
    energy: object
    temperatures: tuple[float,...]
    instant: object
    clock: str
    current_ids: tuple[str,str]
    registries: tuple
    fields: tuple
    coefficients: tuple
    consumed: frozenset
    base_fields: tuple
    base_transferred: frozenset
    lineage_changes: tuple
    resources: tuple

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema":"same_session_thermal_window_snapshot/1","configuration":self.configuration,
                "mesh":self.mesh.version_id,"support":self.support.record_id,"current":self.current.to_dict(),
                "energy":self.energy.to_dict(),"temperatures":[float(t).hex() for t in self.temperatures],
                "instant":self.instant.to_dict(),"clock":self.clock,"current_ids":self.current_ids,
                "registries":[[tag,[[key,record.to_dict(),digest] for key,record,digest in entries]]
                              for tag,owner,entries in self.registries],
                "fields":list(self.fields),"coefficients":list(self.coefficients),
                "consumed":sorted(self.consumed),"base_fields":list(self.base_fields),
                "base_transferred":sorted(self.base_transferred),
                "lineage_changes":[[key,change.to_dict()] for key,change in self.lineage_changes],
                "resources":[[kind.value,name,binding.to_dict(),hashlib.sha256(payload).hexdigest()]
                             for kind,name,binding,container,payload in self.resources]}


class ThermalAdaptiveBackend(AdaptiveBackend1D):
    """Only the exact stateless M1C sparse provider qualifies for in-place window recovery."""
    def __init__(self,session:TransientConduction1D):
        if not isinstance(session,TransientConduction1D):
            raise NumericalRefusal("M1C session required")
        session._guard()
        self.session=session
        self._current_session=session
        self._poisoned=False
        self._checkpoint_anchors={}
        self._seal=self._new_seal()

    @property
    def adapter(self):return self.session.adapter
    @property
    def conserved_state(self):return self.session.energy

    def _scope(self):
        return canonical_digest({"schema":"adaptive_thermal_checkpoint_scope/1",
            "implementation":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "session_configuration":self.session._config_digest,
            "provider":self.session.provider.identity.to_dict()})

    def _new_seal(self):
        return CheckpointSeal("m1d.thermal.same_session",self._scope(),integrity_of=lambda state:state.record_id)

    def guard(self):
        if self._poisoned or self.session is not self._current_session:
            raise NumericalRefusal("thermal adaptive backend poisoned or substituted session")
        self.session._guard()
        if self._scope()!=self._seal.scope:
            raise NumericalRefusal("checkpoint implementation/provider scope drift")

    def identity_material(self):
        s=self.session
        return {"mesh_version":self.adapter._support.mesh.version_id,"support":self.adapter._support.record_id,
                "state":s.energy.record_id,"temperature":s.current.record_id,"instant":s.time.to_dict(),
                "session_configuration":s._config_digest,"provider":s.provider.identity.to_dict()}

    def _registries(self):
        a=self.adapter
        return (("session",self.session._issued),("dual",a._issued),
                ("primal_manager",a._runtime._issued),("lineage",a._runtime._lineage._issued))

    @staticmethod
    def _references(snap):
        refs=[snap.session,snap.mesh,snap.support,snap.current,snap.energy]
        for tag,owner,entries in snap.registries:
            refs.append(owner)
            refs.extend(record for key,record,digest in entries)
        refs.extend(change for key,change in snap.lineage_changes)
        for kind,name,binding,container,payload in snap.resources:
            refs.extend((binding,container))
        return tuple(refs)

    def checkpoint(self):
        self.guard()
        s,a=self.session,self.adapter
        if type(s.provider) is not SparseFVProvider or vars(s.provider):
            raise NumericalRefusal("checkpoint requires exact stateless qualified sparse provider; external state unsupported")
        resources=tuple((kind,name,binding,container,_resource_bytes(container))
            for (kind,name),(binding,container) in a._runtime._active_resources.items())
        registries=tuple((tag,owner,tuple((key,record,digest) for key,(record,digest) in owner._records.items()))
                         for tag,owner in self._registries())
        for tag,owner,entries in registries:
            for key,record,digest in entries:
                if hasattr(record,"data"):
                    a._runtime._resolver.resolve(record.data)
        snap=_WindowSnapshot(s,a.mesh,a.support,s._config_digest,s.current,s.energy,tuple(map(float,s._temperatures)),
            s.time,s._clock,s._current_ids,registries,tuple(a._fields.items()),tuple(a._coefficients.items()),
            frozenset(a._consumed),tuple(a._runtime._active_fields.items()),frozenset(a._runtime._transferred),
            tuple(a._runtime._lineage._changes_for_versions.items()),resources)
        checkpoint=self._seal.seal(s.time.quantity,state_digest=snap.record_id,deterministic_restore=True,
                                   slot="window",state=snap)
        # Local object authority, separately captured from the snapshot's mutable Python graph.
        self._checkpoint_anchors[id(snap)]=(snap,self._references(snap))
        weakref.finalize(checkpoint.token,self._checkpoint_anchors.pop,id(snap),None)
        return checkpoint

    def restore(self,checkpoint):
        if self._poisoned or self.session is not self._current_session or self._scope()!=self._seal.scope:
            raise NumericalRefusal("checkpoint issuer/session/provider drift; restoration refused")
        snap=self._seal.admit(checkpoint,slot_of=lambda s:"window",digest_of=lambda s:s.record_id,
                              state_type=_WindowSnapshot,label="M1D thermal window")
        anchor=self._checkpoint_anchors.get(id(snap))
        refs=self._references(snap)
        if (anchor is None or anchor[0] is not snap or len(refs)!=len(anchor[1])
                or any(a is not b for a,b in zip(refs,anchor[1]))):
            raise NumericalRefusal("checkpoint nested reference authority changed")
        s,a=self.session,self.adapter
        if (s is not snap.session or a._support is not snap.support or a._runtime._lineage.current is not snap.mesh
                or a._runtime._version is not snap.mesh or canonical_digest(s._configuration())!=snap.configuration
                or type(s.provider) is not SparseFVProvider or vars(s.provider)):
            raise NumericalRefusal("complete same-mesh restoration cannot be established")
        registry_owners=dict(self._registries())
        for tag,owner,entries in snap.registries:
            if registry_owners.get(tag) is not owner:
                raise NumericalRefusal("substituted registry owner")
            for key,record,digest in entries:
                if record.record_id!=key or _IssuedRecords.snapshot(record)!=digest:
                    raise NumericalRefusal("saved issuance material changed")
                if hasattr(record,"data"):
                    a._runtime._resolver.resolve(record.data)
        live=a._runtime._active_resources
        if set(live)!={(kind,name) for kind,name,*_ in snap.resources}:
            raise NumericalRefusal("managed resource roster changed; complete restore unavailable")
        for kind,name,binding,container,payload in snap.resources:
            if live[(kind,name)][0] is not binding or live[(kind,name)][1] is not container:
                raise NumericalRefusal("managed resource instance substituted")
        # Only now mutate known state. Any exception below must poison the outer execution.
        for tag,owner,entries in snap.registries:
            owner._records={key:(record,digest) for key,record,digest in entries}
        a._fields=dict(snap.fields);a._coefficients=dict(snap.coefficients);a._consumed=set(snap.consumed)
        a._runtime._active_fields=dict(snap.base_fields)
        a._runtime._transferred=set(snap.base_transferred)
        a._runtime._lineage._changes_for_versions=dict(snap.lineage_changes)
        for kind,name,binding,container,payload in snap.resources:
            value=json.loads(payload)
            container.clear()
            if type(container) is dict:container.update(value)
            else:container.extend(value)
            if _resource_bytes(container)!=payload:
                raise NumericalRefusal("restored resource content differs")
        s.current,s.energy,s._temperatures=snap.current,snap.energy,np.asarray(snap.temperatures,dtype=float)
        s.time,s._clock,s._current_ids,s._unusable=snap.instant,snap.clock,snap.current_ids,False
        a._unusable=False
        self.guard()  # Includes actual source/state/coefficient byte resolution, not stored digests alone.

    def advance(self,**forcing):
        self.guard()
        return self.session.step(**forcing)

    def prepare_rebuild(self):
        self.guard()
        return self.session.continuation_permit()

    def rebuild(self,permit,transition,transferred,receipt,target):
        if not isinstance(target,ThermalRebuildTarget):
            raise NumericalRefusal("explicit target material regions and contacts required")
        old=self.session
        fresh=TransientConduction1D.from_transfer(permit,transition,transferred,receipt,
                                                regions=tuple(target.regions),contacts=tuple(target.contacts))
        self.session=self._current_session=fresh
        self._seal=self._new_seal()
        self.guard()
        return {"schema":"thermal_session_rebuild/1","continuation":permit.to_dict(),
            "transfer":receipt.to_dict(),"transition":transition.record_id,
            "old_configuration":old._config_digest,"new_configuration":fresh._config_digest,
            "target_material_resolutions":fresh.material_resolutions,"storage":fresh.storage.to_dict(),
            "temperature":fresh.initial.to_dict(),"energy":fresh.energy.to_dict(),
            "notice":"fresh fixed-mesh session from derived conserved state, not a new measurement"}

    def poison(self):
        self._poisoned=True
        self.session._unusable=True
