"""Projecting a world from its owners, and verifying that a world is still that projection.

:func:`project_world` is the one way a world holding owner facts is made: it reads the declaration in force and every
record the declaration points at, through the execution side's :class:`~.authority.Authorities`, and binds each
projected fact to its record.  It never fills a gap: a value source, model, provider or budget record the owner does
not hold refuses the projection.

:func:`verify_world` answers whether a world may support a decision NOW.  The world's content must be the content its
identity names (an object edited after it was built is a MISMATCH), every binding is checked against its owner
(VERIFIED / STALE / MISSING / MISMATCH / ...), every projected fact must carry a binding, and the world must be
EXACTLY the projection of the declaration in force under the owners as they are, revision included (a copy edited
without an owner change, or one carrying a history no owner made, is a MISMATCH, never a new legitimate world).  A
projection is a root world: its owners are its provenance, and it carries no history they cannot verify.  Replay
integrity is a different question: a historical world rebuilds byte for byte (``ScientificWorld.from_dict``) whatever
its owners say today.
"""

from __future__ import annotations

from engcore.scientific import ScientificModelDefinition, Uncertainty
from engcore.scientific.ir.values import decode_value

from .authority import Authorities, AuthorityReport, BindingCheck, BindingStatus, OwnerKind, OwnerUnavailable
from .base import WorldRefused
from .declaration import ProtocolDeclaration
from .owners import UNIT_RECORD, record_key
from .variables import VALUE_FIELDS
from .world import ApplicabilityBinding, BudgetStatement, Lineage, ProviderSnapshot, ScientificWorld, WorldBudget

K = OwnerKind


def project_world(declaration: ProtocolDeclaration, authorities: Authorities, *, bound_at: str = "") -> ScientificWorld:
    """The world ``declaration`` projects under ``authorities``: every fact read from its owner, every fact bound.

    The world is built from the declaration AS THE OWNER READER HOLDS IT (rebuilt from the record's payload), never
    from the caller's objects, so the world and the declaration in force share no object."""
    import dataclasses

    if type(declaration) is not ProtocolDeclaration:
        raise WorldRefused("a world is projected from exactly a ProtocolDeclaration")
    if type(authorities) is not Authorities:
        raise WorldRefused("a world is projected through the execution side's Authorities")
    authorities = authorities.memoized()                     # one consistent read of every owner record
    reader, held = authorities.require(K.DECLARATION, declaration.declaration_id)
    if held.record_digest != declaration.digest:
        raise WorldRefused(f"declaration {declaration.declaration_id!r} revision {declaration.revision} is not the one "
                           f"in force (revision {held.revision})")
    decl_binding = held.binding(("declaration",), reader.project(held, ("declaration",)), bound_at)
    declaration = ProtocolDeclaration.from_dict(held.payload["declaration"])      # the owner's copy, detached
    if declaration.digest != held.record_digest:
        raise WorldRefused("the declaration in force does not rebuild from its own record")
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
        statements.append(BudgetStatement(b.dimension, b.kind, projected, record.binding(fields_, projected, bound_at),
                                          b.unit))

    return ScientificWorld(
        declaration.world_id, tuple(variables), declaration.entities, declaration.constraints, declaration.actions,
        declaration.channels, tuple(applicability), tuple(providers),
        WorldBudget(unbounded=tuple(unbounded), statements=tuple(statements), projected=True),
        declaration.references, declaration.declared_by, declaration.basis,
        Lineage(), declaration.description, decl_binding, units_binding)


def verify_world(world: ScientificWorld, authorities: Authorities) -> AuthorityReport:
    """Every projected fact of ``world`` checked against its owner now, and the world checked to be exactly the
    projection of the declaration in force.  ``ok`` only if all of it holds; nothing is repaired or re-bound."""
    return verified_projection(world, authorities)[0]


def verified_projection(world: ScientificWorld, authorities: Authorities
                        ) -> tuple[AuthorityReport, ScientificWorld | None]:
    """:func:`verify_world`'s report, and, when it is ok, the owners' own fresh projection that ``world`` was found
    to be (same revision; it carries the owners' text, never the caller's non-material fields)."""
    if type(world) is not ScientificWorld:
        raise WorldRefused("only a ScientificWorld is verified")
    if type(authorities) is not Authorities:
        raise WorldRefused("a world is verified against the execution side's Authorities")
    authorities = authorities.memoized()                     # one consistent read of every owner record
    checks: list[BindingCheck] = []
    fresh: ScientificWorld | None = None
    if not world.intact():
        return AuthorityReport(world.revision_id, (BindingCheck(
            BindingStatus.MISMATCH, K.DECLARATION, "-", "identity", "0" * 64,
            {"why": "the world's content is not the content its identity names (edited after it was built)"}),)), None
    named, unread = _named_records(world, authorities)
    for subject, binding, held in world.projected_facts():
        if binding is None:
            if subject in ("declaration", "unit_registry") or held is not None or subject.startswith("budget:"):
                checks.append(BindingCheck(BindingStatus.UNVERIFIABLE, _kind_of(subject), "-", subject, "0" * 64,
                                           {"why": "this fact carries no authority binding (a copy no owner can "
                                                   "verify, such as a synthetic fixture reference)"}))
            continue
        if binding.owner_kind in named and binding.record_id not in named[binding.owner_kind]:
            checks.append(BindingCheck(unread[0], binding.owner_kind, binding.record_id, subject, binding.digest,
                                       {"why": f"{unread[1]}; it is not read (a world never chooses which accounts or "
                                               "providers the execution side reads)"}))
            continue
        checks.append(authorities.check(binding, subject, held))
    if all(c.ok for c in checks) and world.declaration is not None:
        held = authorities.read(K.DECLARATION, world.declaration.record_id)
        try:
            fresh = project_world(ProtocolDeclaration.from_dict(held.payload["declaration"]), authorities)
        except (WorldRefused, KeyError, AttributeError) as exc:
            fresh = None
            checks.append(BindingCheck(BindingStatus.MISMATCH, K.DECLARATION, world.declaration.record_id,
                                       "projection", world.declaration.digest, {"why": f"no projection: {exc}"}))
        else:
            if fresh.revision_id != world.revision_id:
                checks.append(BindingCheck(
                    BindingStatus.MISMATCH, K.DECLARATION, world.declaration.record_id, "projection",
                    world.declaration.digest,
                    {"why": "the world is not exactly the projection of its declaration under its owners (a field "
                            "edited without an owner change, or a history no owner made)",
                     "changed": list(world.changed_from(fresh)), "lineage": world.lineage.revision != 0}))
            else:
                checks.append(BindingCheck(BindingStatus.VERIFIED, K.DECLARATION, world.declaration.record_id,
                                           "projection", world.declaration.digest))
    report = AuthorityReport(world.revision_id, tuple(checks))
    return report, (fresh if report.ok else None)


def _named_records(world: ScientificWorld, authorities: Authorities
                   ) -> tuple[dict[OwnerKind, set[str]], tuple[BindingStatus, str]]:
    """The budget accounts and providers the declaration in force names, exactly as :func:`project_world` binds them
    (its ``budget`` references and its ``providers``), from the declaration alone (no other owner is read): the owner
    kinds whose reads have a per-record effect (a following budget reader's history, a provider re-probe).  When the
    world names no declaration, or the one it names cannot be read, it names none: no budget account or provider is
    read for that world (round 6, K6-F2; round 7, R7-C-F3 / R7-C-F4).  Also returns the status and reason an unnamed
    binding is reported with (OWNER_UNAVAILABLE when the declaration owner is unavailable, else MISMATCH)."""
    none: dict[OwnerKind, set[str]] = {K.BUDGET_LEDGER: set(), K.EXPERIMENT: set(), K.PROVIDER_STATUS: set()}
    if world.declaration is None:
        return none, (BindingStatus.MISMATCH, "the world names no declaration in force")
    try:
        in_force = authorities.read(K.DECLARATION, world.declaration.record_id)
        if in_force is None:
            return none, (BindingStatus.MISMATCH, "the declaration owner holds no declaration the world names")
        declaration = ProtocolDeclaration.from_dict(in_force.payload["declaration"])
    except OwnerUnavailable as exc:
        return none, (BindingStatus.OWNER_UNAVAILABLE, f"the declaration in force cannot be read now ({exc})")
    except (WorldRefused, KeyError, AttributeError) as exc:
        return none, (BindingStatus.MISMATCH, f"the declaration in force does not read back ({exc})")
    return ({K.BUDGET_LEDGER: {b.ref for b in declaration.budget if b.kind == "ledger"},
             K.EXPERIMENT: {b.ref for b in declaration.budget if b.kind == "experiment"},
             K.PROVIDER_STATUS: set(declaration.providers)},
            (BindingStatus.MISMATCH, "the declaration in force names no such account or provider"))


def _kind_of(subject: str) -> OwnerKind:
    head = subject.split(":", 1)[0]
    return {"declaration": K.DECLARATION, "unit_registry": K.UNIT_REGISTRY, "variable": K.SYSTEM_STATE,
            "model": K.MODEL_RECORD, "provider": K.PROVIDER_STATUS, "budget": K.BUDGET_LEDGER}[head]


__all__ = ["project_world", "verified_projection", "verify_world"]
