"""Projecting a world from its owners, and verifying that a world is still that projection.

:func:`project_world` is the one way a world holding owner facts is made: it reads the declaration in force and every
record the declaration points at, through the execution side's :class:`~.authority.Authorities`, and binds each
projected fact to its record.  It never fills a gap: a value source, model, provider or budget record the owner does
not hold refuses the projection.

:func:`verify_world` answers whether a world may support a decision NOW.  Every binding is checked against its owner
(VERIFIED / STALE / MISSING / MISMATCH / ...), every projected fact must carry a binding, and the world must be
exactly the projection of the declaration in force under the owners as they are (a copy edited without an owner
change is a MISMATCH, never a new legitimate world).  Replay integrity is a different question: a historical world
rebuilds byte for byte (``ScientificWorld.from_dict``) whatever its owners say today.
"""

from __future__ import annotations

from typing import Any

from engcore.scientific import ScientificModelDefinition, Uncertainty
from engcore.scientific.ir.values import decode_value

from .authority import Authorities, AuthorityReport, BindingCheck, BindingStatus, OwnerKind
from .base import WorldRefused
from .declaration import ProtocolDeclaration
from .owners import UNIT_RECORD, record_key
from .variables import VALUE_FIELDS
from .world import ApplicabilityBinding, BudgetStatement, Lineage, ProviderSnapshot, ScientificWorld, WorldBudget

K = OwnerKind


def project_world(declaration: ProtocolDeclaration, authorities: Authorities, *, bound_at: str = "",
                  lineage: Lineage | None = None) -> ScientificWorld:
    """The world ``declaration`` projects under ``authorities``: every fact read from its owner, every fact bound."""
    import dataclasses

    if type(declaration) is not ProtocolDeclaration:
        raise WorldRefused("a world is projected from exactly a ProtocolDeclaration")
    if type(authorities) is not Authorities:
        raise WorldRefused("a world is projected through the execution side's Authorities")
    reader, held = authorities.require(K.DECLARATION, declaration.declaration_id)
    if held.record_digest != declaration.digest:
        raise WorldRefused(f"declaration {declaration.declaration_id!r} revision {declaration.revision} is not the one "
                           f"in force (revision {held.revision})")
    decl_binding = held.binding(("declaration",), reader.project(held, ("declaration",)), bound_at)
    reader, units = authorities.require(K.UNIT_REGISTRY, UNIT_RECORD)
    units_binding = units.binding(("fingerprint",), reader.project(units, ("fingerprint",)), bound_at)

    sources = {s.variable: s for s in declaration.values}
    variables = []
    for v in declaration.variables:
        s = sources.get(v.name)
        if s is None:
            variables.append(v)
            continue
        reader, record = authorities.require(K.SYSTEM_STATE, s.record_id)
        projected = reader.project(record, VALUE_FIELDS)
        value = decode_value(projected["value"])
        variables.append(dataclasses.replace(v, value=value, origin=s.origin, source=record.binding(
            VALUE_FIELDS, projected, bound_at), uncertainty=Uncertainty.from_dict(projected["uncertainty"])))

    applicability = []
    for model_id, version in declaration.models:
        reader, record = authorities.require(K.MODEL_RECORD, record_key(model_id, version))
        projected = reader.project(record, ("model",))
        applicability.append(ApplicabilityBinding(ScientificModelDefinition.from_dict(projected["model"]),
                                                  record.binding(("model",), projected, bound_at)))

    providers = []
    for pid in declaration.providers:
        reader, record = authorities.require(K.PROVIDER_STATUS, pid)
        projected = reader.project(record, ("report", "status"))
        providers.append(ProviderSnapshot(projected["status"], projected["report"],
                                          record.binding(("report", "status"), projected, bound_at)))

    statements, unbounded = [], []
    for b in declaration.budget:
        if b.kind == "unbounded":
            unbounded.append((b.dimension, b.ref))
            continue
        kind, fields_ = (K.BUDGET_LEDGER, ("ledger",)) if b.kind == "ledger" else (K.EXPERIMENT, ("accounting", "budget"))
        reader, record = authorities.require(kind, b.ref)
        projected = reader.project(record, fields_)
        statements.append(BudgetStatement(b.dimension, b.kind, projected, record.binding(fields_, projected, bound_at)))

    return ScientificWorld(
        declaration.world_id, tuple(variables), declaration.entities, declaration.constraints, declaration.actions,
        declaration.channels, tuple(applicability), tuple(providers),
        WorldBudget(unbounded=tuple(unbounded), statements=tuple(statements), projected=True),
        declaration.references, declaration.declared_by, declaration.basis,
        Lineage() if lineage is None else lineage, declaration.description, decl_binding, units_binding,
        declaration.uncertainty)


def verify_world(world: ScientificWorld, authorities: Authorities) -> AuthorityReport:
    """Every projected fact of ``world`` checked against its owner now, and the world checked to be exactly the
    projection of the declaration in force.  ``ok`` only if all of it holds; nothing is repaired or re-bound."""
    if type(world) is not ScientificWorld:
        raise WorldRefused("only a ScientificWorld is verified")
    if type(authorities) is not Authorities:
        raise WorldRefused("a world is verified against the execution side's Authorities")
    authorities = authorities.memoized()                     # one consistent read of every owner record
    checks: list[BindingCheck] = []
    for subject, binding, held in world.projected_facts():
        if binding is None:
            if subject in ("declaration", "unit_registry") or held is not None or subject.startswith("budget:"):
                checks.append(BindingCheck(BindingStatus.UNVERIFIABLE, _kind_of(subject), "-", subject, "0" * 64,
                                           {"why": "this fact carries no authority binding (a copy no owner can "
                                                   "verify, such as a synthetic fixture reference)"}))
            continue
        checks.append(authorities.check(binding, subject, held))
    if all(c.ok for c in checks) and world.declaration is not None:
        held = authorities.read(K.DECLARATION, world.declaration.record_id)
        try:
            fresh = project_world(ProtocolDeclaration.from_dict(held.payload["declaration"]), authorities)
        except (WorldRefused, KeyError, AttributeError) as exc:
            checks.append(BindingCheck(BindingStatus.MISMATCH, K.DECLARATION, world.declaration.record_id,
                                       "projection", world.declaration.digest, {"why": f"no projection: {exc}"}))
        else:
            if fresh.content_digest != world.content_digest:
                checks.append(BindingCheck(
                    BindingStatus.MISMATCH, K.DECLARATION, world.declaration.record_id, "projection",
                    world.declaration.digest,
                    {"why": "the world is not the projection of its declaration under its owners (a field was "
                            "edited without an owner change)", "changed": list(world.changed_from(fresh))}))
            else:
                checks.append(BindingCheck(BindingStatus.VERIFIED, K.DECLARATION, world.declaration.record_id,
                                           "projection", world.declaration.digest))
    return AuthorityReport(world.revision_id, tuple(checks))


def _kind_of(subject: str) -> OwnerKind:
    head = subject.split(":", 1)[0]
    return {"declaration": K.DECLARATION, "unit_registry": K.UNIT_REGISTRY, "variable": K.SYSTEM_STATE,
            "model": K.MODEL_RECORD, "provider": K.PROVIDER_STATUS, "budget": K.BUDGET_LEDGER}[head]


__all__ = ["project_world", "verify_world"]
