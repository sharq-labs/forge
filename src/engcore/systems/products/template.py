"""Generic product templates: one composition contract for every engineered product.

A :class:`ProductTemplate` composes ONLY generic records:

* an :class:`~engcore.systems.assembly.AssemblyTopology` (product structure);
* :class:`PhysicsParticipant` requirements -- which physics family must be
  computed for which instances, by which candidate providers (registry ids),
  from which required inputs;
* :class:`RequiredInput` declarations -- every quantity the template needs and
  does not know.  An undeclared input stays UNKNOWN; nothing is defaulted;
* declared couplings between participants, with an explicit statement of
  whether the coupling semantics are executable yet.

:func:`capability_report` turns a template plus a provider registry into an
honest capability matrix: for each participant whether it is executable here
(a provider is AVAILABLE and every input is declared), blocked by a provider,
blocked by inputs, or has no adapter at all.  Available is not qualified; a
READY participant is one that CAN run, not one whose result would be trusted.

Product names live only in the modules that build specific templates
(``drone``, ``vehicle``, ``motor``, ``hvac``); this module knows none of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from ...providers.catalog import ProviderRegistry
from ...providers.health import ProviderHealth, assess_health
from ...scenarios.timeline import canonical_digest
from ...scientific.errors import InvalidScientificProblem
from ...scientific.twins import TwinReference
from ...scientific.units.quantity import Quantity, dimensionality
from ...spatial.geometry import Transform
from ..assembly import AssemblyTopology, ConnectionPoint, InstanceLevel, InterfaceDeclaration, JointDeclaration, Placement
from ..topology import ComponentDefinition, ComponentInstance, SystemDefinition

PRODUCT_TEMPLATE_SCHEMA = "engcore.systems.product_template/1"
UNBOUND_TWIN_VERSION = "unbound"


class TemplateRefusal(InvalidScientificProblem):
    """A product template that would claim an input, provider or coupling it does not have."""


@dataclass(frozen=True)
class RequiredInput:
    """A quantity the product needs.  ``value`` is None (UNKNOWN) until declared WITH a source reference."""

    input_id: str
    owner: str
    unit: str
    description: str
    value: Quantity | None = None
    source_ref: str = ""

    def __post_init__(self) -> None:
        if self.value is not None:
            if not isinstance(self.value, Quantity) or self.value.dimensionality != dimensionality(self.unit):
                raise TemplateRefusal(f"input {self.input_id!r} must be a Quantity in a unit of {self.unit}")
            if not str(self.source_ref).strip():
                raise TemplateRefusal(f"input {self.input_id!r} is declared without a source reference; an unsourced value is refused")
        elif self.source_ref:
            raise TemplateRefusal(f"input {self.input_id!r} names a source but no value")

    @property
    def known(self) -> bool:
        return self.value is not None

    def declare(self, value: Quantity, source_ref: str) -> "RequiredInput":
        return RequiredInput(self.input_id, self.owner, self.unit, self.description, value, source_ref)

    def to_dict(self) -> dict[str, Any]:
        return {"input_id": self.input_id, "owner": self.owner, "unit": self.unit, "status": "known" if self.known else "UNKNOWN",
                "value": None if self.value is None else self.value.to_dict(), "source_ref": self.source_ref}


@dataclass(frozen=True)
class PhysicsParticipant:
    """A physics family that must be computed for some instances, by one of the named candidate providers."""

    participant_id: str
    physics: str
    owners: tuple[str, ...]
    providers: tuple[str, ...]
    inputs: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.owners:
            raise TemplateRefusal(f"participant {self.participant_id!r} owns no instance")
        object.__setattr__(self, "providers", tuple(self.providers))
        object.__setattr__(self, "inputs", tuple(sorted(set(self.inputs))))

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "physics": self.physics, "owners": list(self.owners), "providers": list(self.providers),
                "inputs": list(self.inputs), "notes": self.notes}


class CouplingStatus(str, Enum):
    DECLARED_NOT_EXECUTABLE = "declared_not_executable"   # the semantics are named; no runtime executes them yet
    ONE_WAY_EXECUTABLE = "one_way_executable"             # a sequential hand-off exists in the runtime
    ITERATIVE_EXECUTABLE = "iterative_executable"         # part of a two-way fixed point the multiphysics runtime iterates to a declared tolerance


@dataclass(frozen=True)
class CouplingDeclaration:
    source: str
    target: str
    quantity: str
    status: CouplingStatus = CouplingStatus.DECLARED_NOT_EXECUTABLE

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "quantity": self.quantity, "status": CouplingStatus(self.status).value}


@dataclass(frozen=True)
class ProductTemplate:
    template_id: str
    version: str
    assembly: AssemblyTopology
    participants: tuple[PhysicsParticipant, ...]
    inputs: tuple[RequiredInput, ...]
    couplings: tuple[CouplingDeclaration, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = [p.participant_id for p in self.participants]
        if len(set(ids)) != len(ids):
            raise TemplateRefusal("participant ids must be unique")
        imap = {i.input_id: i for i in self.inputs}
        if len(imap) != len(self.inputs):
            raise TemplateRefusal("input ids must be unique")
        instances = {i.instance_id for i in self.assembly.system.instances}
        for i in self.inputs:
            if i.owner not in instances:
                raise TemplateRefusal(f"input {i.input_id!r} is owned by unknown instance {i.owner!r}")
        for p in self.participants:
            if set(p.owners) - instances:
                raise TemplateRefusal(f"participant {p.participant_id!r} owns unknown instances {sorted(set(p.owners) - instances)}")
            if set(p.inputs) - set(imap):
                raise TemplateRefusal(f"participant {p.participant_id!r} needs undeclared inputs {sorted(set(p.inputs) - set(imap))}")
        for c in self.couplings:
            if c.source not in ids or c.target not in ids:
                raise TemplateRefusal(f"coupling {c.source}->{c.target} names unknown participants")

    def input(self, input_id: str) -> RequiredInput:
        for i in self.inputs:
            if i.input_id == input_id:
                return i
        raise TemplateRefusal(f"template has no input {input_id!r}")

    def unknown_inputs(self) -> tuple[str, ...]:
        return tuple(i.input_id for i in self.inputs if not i.known)

    def with_inputs(self, declared: Mapping[str, tuple[Quantity, str]]) -> "ProductTemplate":
        """A copy with some inputs declared as ``{input_id: (value, source_ref)}``.  Unknown ids are refused."""
        unknown = sorted(set(declared) - {i.input_id for i in self.inputs})
        if unknown:
            raise TemplateRefusal(f"undeclared inputs {unknown}")
        new = tuple(i.declare(*declared[i.input_id]) if i.input_id in declared else i for i in self.inputs)
        return ProductTemplate(self.template_id, self.version, self.assembly, self.participants, new, self.couplings, self.notes)

    def values(self, *ids: str) -> dict[str, Quantity]:
        """Declared values, or a refusal naming every UNKNOWN one (never a default)."""
        missing = [i for i in ids if not self.input(i).known]
        if missing:
            raise TemplateRefusal(f"inputs {missing} are UNKNOWN; they are never defaulted")
        return {i: self.input(i).value for i in ids}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PRODUCT_TEMPLATE_SCHEMA, "template_id": self.template_id, "version": self.version,
                "assembly_digest": self.assembly.digest, "participants": [p.to_dict() for p in self.participants],
                "inputs": [i.to_dict() for i in self.inputs], "couplings": [c.to_dict() for c in self.couplings], "notes": list(self.notes)}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


class ParticipantReadiness(str, Enum):
    READY = "ready"                        # an AVAILABLE provider and every input declared (runnable, NOT qualified)
    BLOCKED_BY_INPUTS = "blocked_by_inputs"
    BLOCKED_BY_PROVIDER = "blocked_by_provider"
    NO_ADAPTER = "no_adapter"              # no provider adapter exists for this physics yet


@dataclass(frozen=True)
class ParticipantCapability:
    participant_id: str
    physics: str
    readiness: ParticipantReadiness
    provider_health: Mapping[str, str]
    missing_inputs: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "physics": self.physics, "readiness": self.readiness.value,
                "provider_health": dict(self.provider_health), "missing_inputs": list(self.missing_inputs), "reason": self.reason}


def capability_report(template: ProductTemplate, registry: ProviderRegistry, *,
                      in_repository: Mapping[str, Callable[[], tuple[bool, str]]] | None = None) -> tuple[ParticipantCapability, ...]:
    """Honest per-participant capability.

    ``in_repository`` maps provider ids implemented inside Forge to an
    availability probe ``() -> (ok, detail)``; such a path counts as runnable
    only when its probe succeeds here (still unqualified).  A registry entry
    with the same id always takes precedence over the in-repository probe.
    """
    internal = dict(in_repository or {})
    registered = {s.capability.provider_id for s in registry.discover()}
    out = []
    for p in template.participants:
        missing = tuple(i for i in p.inputs if not template.input(i).known)
        health: dict[str, str] = {}
        for pid in p.providers:
            if pid not in registered and pid in internal:
                try:
                    ok, detail = internal[pid]()
                except Exception as exc:  # noqa: BLE001 - a probe that raises is broken, not available
                    ok, detail = False, f"probe raised {type(exc).__name__}"
                health[pid] = "in_repository_available" if ok else f"in_repository_unavailable ({detail})"
                continue
            try:
                health[pid] = assess_health(registry.status(pid)).health.value
            except Exception as exc:  # noqa: BLE001 - an unregistered provider is reported, not raised
                health[pid] = f"not_registered ({type(exc).__name__})"
        runnable = [pid for pid, h in health.items() if h in (ProviderHealth.AVAILABLE.value, "in_repository_available")]
        if not p.providers:
            readiness, why = ParticipantReadiness.NO_ADAPTER, "no provider adapter exists for this physics in Forge yet"
        elif not runnable:
            readiness, why = ParticipantReadiness.BLOCKED_BY_PROVIDER, "no candidate provider is available here"
        elif missing:
            readiness, why = ParticipantReadiness.BLOCKED_BY_INPUTS, f"{len(missing)} required input(s) are UNKNOWN"
        else:
            readiness, why = ParticipantReadiness.READY, f"runnable via {runnable}; available is not qualified"
        out.append(ParticipantCapability(p.participant_id, p.physics, readiness, health, missing, why))
    return tuple(out)


# ---------------------------------------------------------------------------
# Small builder for template assemblies
# ---------------------------------------------------------------------------


@dataclass
class AssemblyBuilder:
    """Accumulates instances/levels/points/joints/interfaces; every instance gets an UNBOUND twin reference."""

    template_id: str
    instances: list = field(default_factory=list)
    levels: list = field(default_factory=list)
    placements: list = field(default_factory=list)
    points: list = field(default_factory=list)
    joints: list = field(default_factory=list)
    interfaces: list = field(default_factory=list)
    definitions: dict = field(default_factory=dict)

    def add(self, instance_id: str, definition: str, level: str, parent: str = "", placement: Transform | None = None) -> "AssemblyBuilder":
        self.definitions.setdefault(definition, ComponentDefinition(definition, "1"))
        self.instances.append(ComponentInstance(instance_id, definition, "1", TwinReference(f"{self.template_id}.{instance_id}",
                                                                                           UNBOUND_TWIN_VERSION), parent_id=parent))
        self.levels.append(InstanceLevel(instance_id, level))
        if placement is not None:
            self.placements.append(Placement(instance_id, placement))
        return self

    def point(self, point_id: str, instance_id: str, local: Transform | None = None) -> "AssemblyBuilder":
        self.points.append(ConnectionPoint(point_id, instance_id, local or Transform()))
        return self

    def joint(self, joint: JointDeclaration) -> "AssemblyBuilder":
        self.joints.append(joint)
        return self

    def interface(self, itf: InterfaceDeclaration) -> "AssemblyBuilder":
        self.interfaces.append(itf)
        return self

    def build(self, version: str = "1") -> AssemblyTopology:
        system = SystemDefinition(self.template_id, version, tuple(self.definitions.values()), tuple(self.instances))
        return AssemblyTopology(system, tuple(self.levels), tuple(self.placements), tuple(self.points), tuple(self.joints), tuple(self.interfaces))


def inputs(owner_specs: Iterable[tuple[str, str, str, str]]) -> tuple[RequiredInput, ...]:
    """``(input_id, owner, unit, description)`` rows -> UNKNOWN RequiredInputs."""
    return tuple(RequiredInput(i, o, u, d) for i, o, u, d in owner_specs)
