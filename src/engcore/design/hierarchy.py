"""Recursive (hierarchical) discovery: component-owned design spaces, sub-candidate replacement, recomposition.

A product design is not one flat dictionary of variables.  A part's choices
belong to that part; the part belongs to a unit; the unit belongs to the
product.  This module keeps that ownership:

* :class:`ComponentDesignSpace` -- a :class:`~.space.DesignSpace` owned by one
  component path (``("product", "unit_1", "part")``);
* :class:`HierarchicalDesignSpace` -- the set of owned spaces; owner paths
  must form a tree, and a variable is addressed as ``(owner, name)``;
* :class:`HierarchicalCandidate` -- one exact sub-candidate per owner (each a
  D0 :class:`~.candidate.DesignCandidate` bound to its own Twin) plus the
  parent's recomposed identity;
* :meth:`HierarchicalCandidate.replace_component` -- swap one owner's
  sub-candidate; the parent obtains a new identity and records the lineage
  ``component revision -> parent revision``.

Recomposition binds identities.  It does not claim that the recomposed
product works: the parent must still be evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from .candidate import DesignCandidate
from .space import DesignSpace

HIERARCHICAL_CANDIDATE_SCHEMA = "engcore.design.hierarchical_candidate/1"

OwnerPath = tuple[str, ...]


def _path(value: Iterable[str]) -> OwnerPath:
    p = tuple(str(v).strip() for v in value)
    if not p or any(not v or "/" in v for v in p):
        raise InvalidScientificProblem(f"owner path {value!r} must be non-empty identifiers without '/'")
    return p


@dataclass(frozen=True)
class ComponentDesignSpace:
    owner: OwnerPath
    space: DesignSpace

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner", _path(self.owner))
        if not isinstance(self.space, DesignSpace):
            raise InvalidScientificProblem("a component design space wraps a DesignSpace")

    @property
    def owner_id(self) -> str:
        return "/".join(self.owner)


@dataclass(frozen=True)
class HierarchicalDesignSpace:
    root: str
    components: tuple[ComponentDesignSpace, ...]

    def __post_init__(self) -> None:
        comps = tuple(sorted(self.components, key=lambda c: c.owner))
        if not comps:
            raise InvalidScientificProblem("a hierarchical space owns at least one component space")
        owners = [c.owner for c in comps]
        if len(set(owners)) != len(owners):
            raise InvalidScientificProblem("each owner path owns exactly one design space")
        for o in owners:
            if o[0] != self.root:
                raise InvalidScientificProblem(f"owner {o} is not under root {self.root!r}")
        object.__setattr__(self, "components", comps)

    def owners(self) -> tuple[OwnerPath, ...]:
        return tuple(c.owner for c in self.components)

    def space_of(self, owner: Iterable[str]) -> DesignSpace:
        o = _path(owner)
        for c in self.components:
            if c.owner == o:
                return c.space
        raise InvalidScientificProblem(f"no design space is owned by {'/'.join(o)!r}")

    def owner_of(self, variable: str) -> tuple[OwnerPath, ...]:
        """Every owner declaring a variable of this name (names are local; there is no global flattening)."""
        return tuple(c.owner for c in self.components if variable in c.space.variable_map)

    def children(self, owner: Iterable[str]) -> tuple[OwnerPath, ...]:
        o = _path(owner)
        return tuple(c.owner for c in self.components if len(c.owner) > len(o) and c.owner[:len(o)] == o)

    def to_dict(self) -> dict[str, Any]:
        return {"root": self.root, "components": [{"owner": list(c.owner), "space": list(c.space.reference.key)} for c in self.components]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class ComponentLineage:
    owner: OwnerPath
    previous_candidate: str
    new_candidate: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {"owner": list(self.owner), "previous_candidate": self.previous_candidate, "new_candidate": self.new_candidate, "note": self.note}


@dataclass(frozen=True)
class HierarchicalCandidate:
    """One sub-candidate per owner, plus lineage.  ``candidate_id`` is the recomposed parent identity."""

    space: HierarchicalDesignSpace
    components: Mapping[OwnerPath, DesignCandidate]
    parent_candidate: str = ""
    lineage: tuple[ComponentLineage, ...] = ()
    assembly_digest: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        comps = {_path(k): v for k, v in dict(self.components).items()}
        if set(comps) != set(self.space.owners()):
            raise InvalidScientificProblem(f"a hierarchical candidate needs exactly one sub-candidate per owner; "
                                           f"missing {sorted(set(self.space.owners()) - set(comps))}, "
                                           f"undeclared {sorted(set(comps) - set(self.space.owners()))}")
        for owner, cand in comps.items():
            if not isinstance(cand, DesignCandidate):
                raise InvalidScientificProblem(f"{'/'.join(owner)} sub-candidate must be a DesignCandidate")
            cand.validate_against(self.space.space_of(owner))
        twins = [c.twin.key for c in comps.values()]
        if len(set(twins)) != len(twins):
            raise InvalidScientificProblem("two components share one Twin; each owner's candidate is its own Twin")
        if self.assembly_digest and len(self.assembly_digest) != 64:
            raise InvalidScientificProblem("assembly_digest must be a 64-hex digest or empty")
        object.__setattr__(self, "components", dict(sorted(comps.items())))

    @property
    def candidate_id(self) -> str:
        return canonical_digest({"schema": HIERARCHICAL_CANDIDATE_SCHEMA, "space": self.space.digest,
                                 "components": {"/".join(o): [c.candidate_id, list(c.twin.key)] for o, c in self.components.items()},
                                 "assembly_digest": self.assembly_digest})

    def component(self, owner: Iterable[str]) -> DesignCandidate:
        return self.components[_path(owner)]

    def replace_component(self, owner: Iterable[str], candidate: DesignCandidate, *, note: str,
                          assembly_digest: str | None = None) -> "HierarchicalCandidate":
        """Swap one owner's sub-candidate; returns a recomposed parent with lineage.  The original is unchanged.

        The new sub-candidate must name its predecessor as a parent (D0
        lineage), so a replacement can always be traced to what it replaced.
        """
        o = _path(owner)
        old = self.components.get(o)
        if old is None:
            raise InvalidScientificProblem(f"no sub-candidate owned by {'/'.join(o)!r}")
        if old.candidate_id not in {p.candidate_id for p in candidate.parents}:
            raise InvalidScientificProblem("the replacement sub-candidate must declare the replaced one as a parent")
        if not str(note).strip():
            raise InvalidScientificProblem("a replacement states why")
        comps = dict(self.components)
        comps[o] = candidate
        return HierarchicalCandidate(self.space, comps, self.candidate_id,
                                     self.lineage + (ComponentLineage(o, old.candidate_id, candidate.candidate_id, note),),
                                     self.assembly_digest if assembly_digest is None else assembly_digest, self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HIERARCHICAL_CANDIDATE_SCHEMA, "candidate_id": self.candidate_id, "space": self.space.to_dict(),
                "components": {"/".join(o): c.to_dict() for o, c in self.components.items()}, "parent_candidate": self.parent_candidate,
                "lineage": [x.to_dict() for x in self.lineage], "assembly_digest": self.assembly_digest}


def verify_component_lineage(candidate: HierarchicalCandidate, ancestors: Mapping[str, HierarchicalCandidate]) -> tuple[str, ...]:
    """Parent identities from the root to ``candidate``; each step must replace exactly the recorded component."""
    chain = [candidate.candidate_id]
    cur = candidate
    while cur.parent_candidate:
        prev = ancestors.get(cur.parent_candidate)
        if prev is None or prev.candidate_id != cur.parent_candidate:
            raise InvalidScientificProblem("an ancestor candidate is missing or does not match its id")
        step = cur.lineage[-1] if cur.lineage else None
        if step is None or prev.components[step.owner].candidate_id != step.previous_candidate:
            raise InvalidScientificProblem("recorded lineage does not match the ancestor's component")
        changed = {o for o in cur.components if cur.components[o].candidate_id != prev.components[o].candidate_id}
        if changed != {step.owner}:
            raise InvalidScientificProblem(f"recomposition changed {sorted('/'.join(o) for o in changed)}, not only the recorded owner")
        chain.append(prev.candidate_id)
        cur = prev
    return tuple(reversed(chain))
