"""Scientific Twin revisions: an immutable, executable representation of one concrete candidate system.

The frozen Core :class:`~engcore.scientific.twins.ScientificTwin` declares a
system instance (kind, models, typed declarations, evidence references).  A
:class:`TwinRevision` binds that declaration to everything else that makes the
candidate concrete, BY DIGEST, without copying any of those authorities:

* system definition and assembly topology (product structure);
* geometry models / variants and material identities;
* scenario / environment, state and provider-plan digests;
* evidence references, applicability records and uncertainty references.

What a Twin is not: a solver, a result, a dashboard, a validation status or a
scientific authority.  Specifically:

* Evidence references are CONTEXT-BOUND.  Each carries the context digest it
  was produced for; a reference produced for another context is refused, and
  :meth:`TwinRevision.derive` drops every reference whose context changed
  (listing what it dropped).  Changing geometry never keeps old evidence.
* Applicability is context-bound the same way: a derived revision with a new
  context restarts at NOT_ASSESSED.
* Uncertainty is never implied: a quantity with no reference is UNKNOWN.
  A QUANTIFIED uncertainty and a decided applicability are context-bound like
  evidence.
* The twin's kind is carried, never upgraded: a CANDIDATE stays a candidate
  through any number of revisions, cannot carry calibration, validation or
  measurement evidence, and :func:`verify_lineage` refuses a kind change
  across a parent link.
* Evidence references are POINTERS.  Their context and role are the caller's
  statement until :meth:`TwinRevision.verify_evidence` checks each one against
  the record it names; consumers that act on evidence must call it.
* Twin-level ``evidence_refs`` / ``calibration_evidence_refs`` on the Core
  record must each be matched by a context-bound EvidenceReference (calibration
  refs by a CALIBRATION one); otherwise the revision is refused, so a
  derive() that drops evidence cannot leave them behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.twins import ScientificTwin, TwinKind

TWIN_REVISION_SCHEMA = "engcore.systems.twin_revision/1"


class TwinRevisionRefusal(InvalidScientificProblem):
    """A twin revision that would claim more than its references support."""


class EvidenceRole(str, Enum):
    VERIFICATION = "verification"        # numerics/code: solves the equations right
    VALIDATION = "validation"            # model vs physical observation
    CALIBRATION = "calibration"          # parameters fitted to observation (not validation)
    PROVIDER_RUN = "provider_run"        # a provider computation (not evidence of physical truth)
    MEASUREMENT = "measurement"          # an admitted observation record


@dataclass(frozen=True, order=True)
class EvidenceReference:
    """A reference to an evidence record held elsewhere, bound to the exact context it was produced for."""

    ref: str
    role: EvidenceRole
    context_digest: str

    def __post_init__(self) -> None:
        if not str(self.ref).strip():
            raise TwinRevisionRefusal("evidence reference must name a record")
        object.__setattr__(self, "role", EvidenceRole(self.role))
        if len(str(self.context_digest)) != 64:
            raise TwinRevisionRefusal(f"evidence {self.ref!r} must state the 64-hex context digest it was produced for")

    def to_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "role": self.role.value, "context_digest": self.context_digest}


class ApplicabilityState(str, Enum):
    NOT_ASSESSED = "not_assessed"
    UNKNOWN = "unknown"            # assessed, but the inputs needed to decide are missing
    IN_DOMAIN = "in_domain"
    PARTIAL = "partial"
    OUT_OF_DOMAIN = "out_of_domain"


@dataclass(frozen=True, order=True)
class ApplicabilityRecord:
    model_id: str
    model_version: str
    state: ApplicabilityState
    assessment_ref: str = ""
    context_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", ApplicabilityState(self.state))
        if self.decided:
            if not str(self.assessment_ref).strip():
                raise TwinRevisionRefusal(f"applicability {self.state.value} for {self.model_id} names no assessment record; "
                                          "a decided applicability is never asserted bare")
            if len(str(self.context_digest)) != 64:
                raise TwinRevisionRefusal(f"applicability {self.state.value} for {self.model_id} states no context it was assessed for")

    @property
    def decided(self) -> bool:
        return self.state in (ApplicabilityState.IN_DOMAIN, ApplicabilityState.PARTIAL, ApplicabilityState.OUT_OF_DOMAIN)

    def to_dict(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "model_version": self.model_version, "state": self.state.value, "assessment_ref": self.assessment_ref,
                "context_digest": self.context_digest}


class UncertaintyStatus(str, Enum):
    QUANTIFIED = "quantified"
    UNKNOWN = "unknown"


@dataclass(frozen=True, order=True)
class UncertaintyReference:
    quantity: str
    status: UncertaintyStatus
    ref: str = ""
    context_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", UncertaintyStatus(self.status))
        if self.status is UncertaintyStatus.QUANTIFIED:
            if not str(self.ref).strip():
                raise TwinRevisionRefusal(f"uncertainty of {self.quantity!r} is declared quantified without a reference")
            if len(str(self.context_digest)) != 64:
                raise TwinRevisionRefusal(f"quantified uncertainty of {self.quantity!r} states no context it was quantified for")

    def to_dict(self) -> dict[str, Any]:
        return {"quantity": self.quantity, "status": self.status.value, "ref": self.ref, "context_digest": self.context_digest}


def twin_digest(twin: ScientificTwin) -> str:
    """Digest of the twin's SCIENTIFIC content: identity, kind, models, typed declarations, assumptions.

    Name, description and metadata are descriptive (Core: metadata is not a
    scientific input side channel), so editing them is not a new context and
    cannot be used to shed evidence.
    """
    return canonical_digest({"twin": list(twin.reference.key), "kind": twin.kind.value, "models": [m.to_dict() for m in twin.models],
                             "declarations": [d.to_dict() for d in twin.declarations], "assumptions": list(twin.assumptions)})


def _digests(values: Iterable[str], label: str) -> tuple[str, ...]:
    out = tuple(sorted({str(v) for v in values}))
    if any(len(v) != 64 for v in out):
        raise TwinRevisionRefusal(f"{label} must be 64-hex content digests")
    return out


def _context(twin, system, assembly, geometry, variants, materials, scenario, state, plan) -> dict[str, Any]:
    return {"twin_digest": twin_digest(twin), "twin": list(twin.reference.key), "twin_kind": twin.kind.value,
            "system_digest": system, "assembly_digest": assembly, "geometry_digests": list(geometry), "geometry_variant_ids": list(variants),
            "material_digests": list(materials), "scenario_digest": scenario, "state_digest": state, "provider_plan_digest": plan}


@dataclass(frozen=True)
class TwinRevision:
    """One immutable revision of a concrete candidate system.  ``revision_id`` is content-derived."""

    twin: ScientificTwin
    system_digest: str = ""
    assembly_digest: str = ""
    geometry_digests: tuple[str, ...] = ()
    geometry_variant_ids: tuple[str, ...] = ()
    material_digests: tuple[str, ...] = ()
    scenario_digest: str = ""
    state_digest: str = ""
    provider_plan_digest: str = ""
    evidence: tuple[EvidenceReference, ...] = ()
    applicability: tuple[ApplicabilityRecord, ...] = ()
    uncertainty: tuple[UncertaintyReference, ...] = ()
    parent: str = ""
    change_note: str = ""
    dropped_evidence: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.twin, ScientificTwin):
            raise TwinRevisionRefusal("a twin revision binds a ScientificTwin")
        for label in ("system_digest", "assembly_digest", "scenario_digest", "state_digest", "provider_plan_digest"):
            v = str(getattr(self, label) or "")
            if v and len(v) != 64:
                raise TwinRevisionRefusal(f"{label} must be a 64-hex content digest or empty (not bound)")
        object.__setattr__(self, "geometry_digests", _digests(self.geometry_digests, "geometry digests"))
        object.__setattr__(self, "geometry_variant_ids", _digests(self.geometry_variant_ids, "geometry variant ids"))
        object.__setattr__(self, "material_digests", _digests(self.material_digests, "material digests"))
        ev = tuple(sorted(self.evidence))
        if any(not isinstance(e, EvidenceReference) for e in ev) or len({e.ref for e in ev}) != len(ev):
            raise TwinRevisionRefusal("evidence must be unique EvidenceReference records")
        ctx = self.context_digest
        foreign = [e.ref for e in ev if e.context_digest != ctx]
        if foreign:
            raise TwinRevisionRefusal(f"evidence {foreign} was produced for another context; evidence does not transfer between contexts")
        bound = {e.ref: e.role for e in ev}
        loose = [r for r in self.twin.evidence_refs if r not in bound] + \
                [r for r in self.twin.calibration_evidence_refs if bound.get(r) is not EvidenceRole.CALIBRATION]
        if loose:
            raise TwinRevisionRefusal(f"twin-level evidence references {loose} have no context-bound EvidenceReference on this revision; "
                                      "a reference with no context is never carried")
        if self.twin.kind is TwinKind.CANDIDATE:
            forbidden = sorted({e.role.value for e in ev} & {EvidenceRole.CALIBRATION.value, EvidenceRole.VALIDATION.value,
                                                              EvidenceRole.MEASUREMENT.value})
            if forbidden:
                raise TwinRevisionRefusal(f"a CANDIDATE twin carries {forbidden} evidence; a candidate has no physical article to measure, "
                                          "validate or calibrate against")
        if self.twin.kind is TwinKind.CALIBRATED and not any(e.role is EvidenceRole.CALIBRATION for e in ev):
            raise TwinRevisionRefusal("a CALIBRATED revision needs calibration evidence bound to its own context")
        app = tuple(sorted(self.applicability))
        if any(not isinstance(a, ApplicabilityRecord) for a in app) or len({(a.model_id, a.model_version) for a in app}) != len(app):
            raise TwinRevisionRefusal("applicability must be one ApplicabilityRecord per model")
        models = {m.key for m in self.twin.models}
        stray = [(a.model_id, a.model_version) for a in app if (a.model_id, a.model_version) not in models]
        if stray:
            raise TwinRevisionRefusal(f"applicability names models {stray} the twin does not declare")
        if any(a.decided and a.context_digest != ctx for a in app):
            raise TwinRevisionRefusal("an applicability assessment was made for another context; it does not transfer")
        unc = tuple(sorted(self.uncertainty))
        if any(not isinstance(u, UncertaintyReference) for u in unc) or len({u.quantity for u in unc}) != len(unc):
            raise TwinRevisionRefusal("uncertainty references must be unique per quantity")
        if any(u.status is UncertaintyStatus.QUANTIFIED and u.context_digest != ctx for u in unc):
            raise TwinRevisionRefusal("an uncertainty quantification was made for another context; it does not transfer")
        if self.parent and len(self.parent) != 64:
            raise TwinRevisionRefusal("parent must be a revision id")
        object.__setattr__(self, "evidence", ev)
        object.__setattr__(self, "applicability", app)
        object.__setattr__(self, "uncertainty", unc)
        object.__setattr__(self, "dropped_evidence", tuple(sorted(self.dropped_evidence)))

    # ---- identity -------------------------------------------------------------
    def context(self) -> dict[str, Any]:
        """Everything that defines WHAT the candidate is.  Evidence and assessments are bound to this digest."""
        return _context(self.twin, self.system_digest, self.assembly_digest, self.geometry_digests, self.geometry_variant_ids,
                        self.material_digests, self.scenario_digest, self.state_digest, self.provider_plan_digest)

    @staticmethod
    def context_digest_for(twin: ScientificTwin, **bindings: Any) -> str:
        """The context digest a revision with these bindings WILL have -- so evidence can be bound before it is attached."""
        return canonical_digest(_context(twin, bindings.get("system_digest", ""), bindings.get("assembly_digest", ""),
                                         tuple(sorted(bindings.get("geometry_digests", ()))), tuple(sorted(bindings.get("geometry_variant_ids", ()))),
                                         tuple(sorted(bindings.get("material_digests", ()))), bindings.get("scenario_digest", ""),
                                         bindings.get("state_digest", ""), bindings.get("provider_plan_digest", "")))

    @property
    def context_digest(self) -> str:
        return canonical_digest(self.context())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TWIN_REVISION_SCHEMA, "classification": "candidate_representation_not_evidence",
                "context": self.context(), "context_digest": self.context_digest, "twin": self.twin.to_dict(),
                "evidence": [e.to_dict() for e in self.evidence], "applicability": [a.to_dict() for a in self.applicability],
                "uncertainty": [u.to_dict() for u in self.uncertainty], "parent": self.parent, "change_note": self.change_note,
                "dropped_evidence": list(self.dropped_evidence)}

    @property
    def revision_id(self) -> str:
        return canonical_digest({k: v for k, v in self.to_dict().items() if k not in ("change_note", "dropped_evidence")})

    def serialize(self) -> dict[str, Any]:
        """The stored form: ``to_dict`` plus the revision id, which :meth:`from_dict` requires and checks."""
        return dict(self.to_dict(), revision_id=self.revision_id)

    def verify_evidence(self, records: Mapping[str, Mapping[str, Any]]) -> "TwinRevision":
        """Check every evidence pointer against the record it names: it must exist, state this context and this role."""
        for e in self.evidence:
            rec = records.get(e.ref)
            if rec is None:
                raise TwinRevisionRefusal(f"evidence {e.ref!r} names no available record")
            if rec.get("context_digest") != e.context_digest or rec.get("role") != e.role.value:
                raise TwinRevisionRefusal(f"evidence {e.ref!r}: the record states another context or role than the pointer")
        return self

    @property
    def is_candidate(self) -> bool:
        return self.twin.kind is TwinKind.CANDIDATE

    # ---- reads ------------------------------------------------------------------
    def uncertainty_of(self, quantity: str) -> UncertaintyReference:
        """The declared uncertainty status; an undeclared quantity is UNKNOWN (never zero)."""
        for u in self.uncertainty:
            if u.quantity == quantity:
                return u
        return UncertaintyReference(quantity, UncertaintyStatus.UNKNOWN)

    def applicability_of(self, model_id: str, version: str) -> ApplicabilityRecord:
        for a in self.applicability:
            if (a.model_id, a.model_version) == (model_id, version):
                return a
        if (model_id, version) not in {m.key for m in self.twin.models}:
            raise TwinRevisionRefusal(f"the twin does not declare model {model_id} {version}")
        return ApplicabilityRecord(model_id, version, ApplicabilityState.NOT_ASSESSED)

    def evidence_with_role(self, role: EvidenceRole) -> tuple[EvidenceReference, ...]:
        return tuple(e for e in self.evidence if e.role is EvidenceRole(role))

    # ---- revisions --------------------------------------------------------------
    def with_evidence(self, *refs: EvidenceReference) -> "TwinRevision":
        """A new revision carrying additional references (each must be bound to this context)."""
        return replace(self, evidence=self.evidence + tuple(refs), parent=self.revision_id, dropped_evidence=())

    def with_assessments(self, *, applicability: Iterable[ApplicabilityRecord] = (),
                         uncertainty: Iterable[UncertaintyReference] = ()) -> "TwinRevision":
        """A new revision with applicability/uncertainty records added (each bound to this context)."""
        app = {(a.model_id, a.model_version): a for a in self.applicability}
        app.update({(a.model_id, a.model_version): a for a in applicability})
        unc = {u.quantity: u for u in self.uncertainty}
        unc.update({u.quantity: u for u in uncertainty})
        return replace(self, applicability=tuple(app.values()), uncertainty=tuple(unc.values()), parent=self.revision_id, dropped_evidence=())

    def derive(self, *, change_note: str, **changes: Any) -> "TwinRevision":
        """A child revision.  Context changes drop evidence and reset applicability; nothing transfers silently."""
        if not str(change_note).strip():
            raise TwinRevisionRefusal("a derived revision states what changed")
        allowed = {"twin", "system_digest", "assembly_digest", "geometry_digests", "geometry_variant_ids", "material_digests",
                   "scenario_digest", "state_digest", "provider_plan_digest"}
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise TwinRevisionRefusal(f"derive() cannot change {unknown}; evidence and applicability are re-established, not carried")
        new_twin = changes.get("twin", self.twin)
        if isinstance(new_twin, ScientificTwin) and new_twin.kind is not self.twin.kind:
            raise TwinRevisionRefusal(f"derive() cannot change the twin kind ({self.twin.kind.value} -> {new_twin.kind.value}); "
                                      "a kind change is a separate, evidenced declaration")
        probe = replace(self, **changes, evidence=(), applicability=(), uncertainty=(), parent=self.revision_id, change_note=change_note,
                        dropped_evidence=())
        if probe.context_digest == self.context_digest:
            return replace(probe, evidence=self.evidence, applicability=self.applicability, uncertainty=self.uncertainty)
        # applicability and uncertainty describe the old context too: they restart at NOT_ASSESSED / UNKNOWN
        return replace(probe, dropped_evidence=tuple(e.ref for e in self.evidence))

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "TwinRevision":
        if p.get("schema") != TWIN_REVISION_SCHEMA:
            raise TwinRevisionRefusal("unsupported twin revision schema")
        c = p["context"]
        out = cls(
            ScientificTwin.from_dict(p["twin"]), c["system_digest"], c["assembly_digest"], tuple(c["geometry_digests"]),
            tuple(c["geometry_variant_ids"]), tuple(c["material_digests"]), c["scenario_digest"], c["state_digest"], c["provider_plan_digest"],
            tuple(EvidenceReference(e["ref"], e["role"], e["context_digest"]) for e in p["evidence"]),
            tuple(ApplicabilityRecord(a["model_id"], a["model_version"], a["state"], a["assessment_ref"], a.get("context_digest", ""))
                  for a in p["applicability"]),
            tuple(UncertaintyReference(u["quantity"], u["status"], u["ref"], u.get("context_digest", "")) for u in p["uncertainty"]),
            p.get("parent", ""), p.get("change_note", ""), tuple(p.get("dropped_evidence", ())))
        if out.context_digest != p["context_digest"]:
            raise TwinRevisionRefusal("serialized revision context does not match its digest")
        if p.get("revision_id") != out.revision_id:
            raise TwinRevisionRefusal("serialized revision has no revision id or one that does not match its content")
        return out


def verify_lineage(revision: TwinRevision, store: Mapping[str, TwinRevision]) -> tuple[str, ...]:
    """The chain of revision ids from the root to ``revision``; refuses a missing or tampered ancestor."""
    chain = [revision.revision_id]
    cur = revision
    seen = {cur.revision_id}
    while cur.parent:
        parent = store.get(cur.parent)
        if parent is None or parent.revision_id != cur.parent:
            raise TwinRevisionRefusal(f"ancestor {cur.parent[:12]} is missing or does not match its id")
        if parent.revision_id in seen:
            raise TwinRevisionRefusal("revision lineage contains a cycle")
        if parent.twin.kind is not cur.twin.kind:
            raise TwinRevisionRefusal(f"lineage changes the twin kind ({parent.twin.kind.value} -> {cur.twin.kind.value}); "
                                      "a kind change is a separate, evidenced declaration, not a revision")
        seen.add(parent.revision_id)
        chain.append(parent.revision_id)
        cur = parent
    return tuple(reversed(chain))
