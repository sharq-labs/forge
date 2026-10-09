"""Deterministic successor-generation for scientific design search.

This module deliberately sits beside D2 generation instead of changing the
generation-zero contract.  It turns already decision-grade parent candidates
into a typed, reproducible successor population with explicit lineage.

It does not evaluate science.  Parents must come from the caller's
decision-grade memory/archive; the generated children must still be simulated,
validated and assessed before they can become parents themselves.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.values import (
    BooleanValue,
    CategoricalValue,
    IntegerValue,
    ScientificValue,
    encode_value,
    require_scientific_value,
)
from ..scientific.ir.variables import VariableKind
from ..scientific.twins.definition import ScientificTwin, TwinKind
from ..scientific.units.quantity import Quantity
from .candidate import DesignCandidate, DesignCandidateReference
from .generation import ProposalDecision, assignment_digest
from .population import DesignPopulation
from .sampling import MixedVariableSampler
from .space import DesignSpace, DesignSpaceReference

SUCCESSOR_STRATEGY = "adaptive_successor_v1"
SUCCESSOR_BINDING_METADATA_KEY = "engcore.design.successor_binding"


@dataclass(frozen=True)
class SuccessorGenerationPlan:
    population_id: str
    design_space: DesignSpaceReference
    generation: int
    parent_ids: tuple[str, ...]
    count: int
    sequence_start: int = 1
    attempt_budget: int | None = None
    candidate_prefix: str = ""

    def __post_init__(self) -> None:
        population_id = str(self.population_id).strip()
        if not population_id:
            raise InvalidScientificProblem("successor plan requires population_id")
        if not isinstance(self.design_space, DesignSpaceReference):
            raise InvalidScientificProblem("successor plan requires DesignSpaceReference")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise InvalidScientificProblem("successor generation must be an integer >= 1")
        parents = tuple(str(item).strip() for item in self.parent_ids)
        if not parents or any(not item for item in parents):
            raise InvalidScientificProblem("successor plan requires parent candidate ids")
        if len(parents) != len(set(parents)):
            raise InvalidScientificProblem("successor parent ids must be unique")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 1:
            raise InvalidScientificProblem("successor count must be a positive integer")
        if isinstance(self.sequence_start, bool) or not isinstance(self.sequence_start, int) or self.sequence_start < 1:
            raise InvalidScientificProblem("successor sequence_start must be >= 1")
        budget = self.attempt_budget if self.attempt_budget is not None else self.count * 20
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < self.count:
            raise InvalidScientificProblem("successor attempt_budget must be >= count")
        prefix = str(self.candidate_prefix).strip() or population_id
        object.__setattr__(self, "population_id", population_id)
        object.__setattr__(self, "parent_ids", parents)
        object.__setattr__(self, "attempt_budget", budget)
        object.__setattr__(self, "candidate_prefix", prefix)

    @property
    def contraction(self) -> float:
        """Local-search radius. Never collapses to zero, preserving exploration."""
        return max(0.05, 0.5 ** self.generation)

    def candidate_id_for(self, sequence_index: int) -> str:
        return f"{self.candidate_prefix}:g{self.generation}:s{sequence_index}"


@dataclass(frozen=True)
class SuccessorProposal:
    candidate_id: str
    design_space: DesignSpaceReference
    generation: int
    parents: tuple[DesignCandidateReference, ...]
    sequence_index: int
    assignments: Mapping[str, ScientificValue]
    strategy: str = SUCCESSOR_STRATEGY
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        cid = str(self.candidate_id).strip()
        if not cid:
            raise InvalidScientificProblem("successor proposal requires candidate_id")
        if not isinstance(self.design_space, DesignSpaceReference):
            raise InvalidScientificProblem("successor proposal requires DesignSpaceReference")
        if self.generation < 1:
            raise InvalidScientificProblem("successor proposal generation must be >= 1")
        parents = tuple(self.parents)
        if not parents or any(not isinstance(p, DesignCandidateReference) for p in parents):
            raise InvalidScientificProblem("successor proposal requires parent references")
        if len({p.candidate_id for p in parents}) != len(parents):
            raise InvalidScientificProblem("successor proposal parent references must be unique")
        if isinstance(self.sequence_index, bool) or not isinstance(self.sequence_index, int) or self.sequence_index < 1:
            raise InvalidScientificProblem("successor sequence_index must be >= 1")
        assignments = dict(self.assignments)
        if not assignments:
            raise InvalidScientificProblem("successor proposal requires assignments")
        for name, value in assignments.items():
            require_scientific_value(value, context=f"successor assignment {name!r}")
        object.__setattr__(self, "candidate_id", cid)
        object.__setattr__(self, "parents", parents)
        object.__setattr__(self, "assignments", MappingProxyType(assignments))
        object.__setattr__(self, "digest", assignment_digest(assignments))


@runtime_checkable
class SuccessorGate(Protocol):
    def decide(self, proposal: SuccessorProposal) -> ProposalDecision:
        ...


@runtime_checkable
class SuccessorTwinMaterializer(Protocol):
    def materialize(self, proposal: SuccessorProposal) -> ScientificTwin:
        ...


@dataclass(frozen=True)
class SuccessorRejection:
    candidate_id: str
    sequence_index: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SuccessorGenerationBatch:
    plan: SuccessorGenerationPlan
    population: DesignPopulation
    proposals: tuple[SuccessorProposal, ...]
    candidates: tuple[DesignCandidate, ...]
    twins: tuple[ScientificTwin, ...]
    rejected: tuple[SuccessorRejection, ...] = ()


def _blend_continuous(parent: Quantity, global_value: Quantity, fraction: float) -> Quantity:
    target = global_value.to(parent.units)
    return Quantity(
        parent.magnitude + fraction * (target.magnitude - parent.magnitude),
        parent.units,
    )


def _successor_assignments(
    *,
    space: DesignSpace,
    parent_a: DesignCandidate,
    parent_b: DesignCandidate,
    global_values: Mapping[str, ScientificValue],
    contraction: float,
    sequence_index: int,
    generation: int,
) -> dict[str, ScientificValue]:
    """Recombine two parents, then apply a deterministic shrinking mutation."""
    values: dict[str, ScientificValue] = {}
    for position, variable in enumerate(space.variables):
        left = parent_a.assignments[variable.name]
        right = parent_b.assignments[variable.name]
        global_value = global_values[variable.name]
        token = sequence_index + generation + position

        if variable.kind is VariableKind.CONTINUOUS:
            if not all(isinstance(v, Quantity) for v in (left, right, global_value)):
                raise InvalidScientificProblem("continuous successor values must be Quantity")
            right_u = right.to(left.units)
            center = Quantity((left.magnitude + right_u.magnitude) / 2.0, left.units)
            values[variable.name] = _blend_continuous(center, global_value, contraction)
            continue

        if variable.kind is VariableKind.INTEGER:
            if not all(isinstance(v, IntegerValue) for v in (left, right, global_value)):
                raise InvalidScientificProblem("integer successor values must be IntegerValue")
            center = round((left.value + right.value) / 2)
            mutated = round(center + contraction * (global_value.value - center))
            low = int(variable.lower.magnitude)
            high = int(variable.upper.magnitude)
            values[variable.name] = IntegerValue(max(low, min(high, mutated)))
            continue

        if variable.kind is VariableKind.CATEGORICAL:
            if not all(isinstance(v, CategoricalValue) for v in (left, right, global_value)):
                raise InvalidScientificProblem("categorical successor values must be CategoricalValue")
            picked = global_value if token % max(2, generation + 1) == 0 else (left if token % 2 else right)
            values[variable.name] = CategoricalValue(picked.value, vocabulary=variable.categories)
            continue

        if variable.kind is VariableKind.BOOLEAN:
            if not all(isinstance(v, BooleanValue) for v in (left, right, global_value)):
                raise InvalidScientificProblem("boolean successor values must be BooleanValue")
            picked = global_value if token % max(2, generation + 1) == 0 else (left if token % 2 else right)
            values[variable.name] = BooleanValue(picked.value)
            continue

        raise InvalidScientificProblem(f"unsupported successor variable kind {variable.kind!r}")

    return space.validate_assignments(values)


def _binding(proposal: SuccessorProposal) -> str:
    payload = {
        "candidate_id": proposal.candidate_id,
        "design_space": proposal.design_space.to_dict(),
        "generation": proposal.generation,
        "parents": [p.to_dict() for p in proposal.parents],
        "sequence_index": proposal.sequence_index,
        "strategy": proposal.strategy,
        "assignment_digest": proposal.digest,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _bind_twin(twin: ScientificTwin, proposal: SuccessorProposal) -> ScientificTwin:
    if not isinstance(twin, ScientificTwin) or twin.kind is not TwinKind.CANDIDATE:
        raise InvalidScientificProblem("successor materializer must return CANDIDATE ScientificTwin")
    metadata = dict(twin.metadata)
    binding = _binding(proposal)
    existing = metadata.get(SUCCESSOR_BINDING_METADATA_KEY)
    if existing is not None and existing != binding:
        raise InvalidScientificProblem("successor Twin carries a conflicting lineage binding")
    metadata[SUCCESSOR_BINDING_METADATA_KEY] = binding
    return replace(twin, metadata=metadata)


def generate_successors(
    *,
    space: DesignSpace,
    plan: SuccessorGenerationPlan,
    parents: Sequence[DesignCandidate],
    gate: SuccessorGate,
    materializer: SuccessorTwinMaterializer,
) -> SuccessorGenerationBatch:
    """Generate one deterministic derived population from explicit parents."""
    if space.reference.key != plan.design_space.key:
        raise InvalidScientificProblem("successor plan design-space mismatch")
    sampler = MixedVariableSampler(space)
    parent_by_id = {p.candidate_id: p for p in parents}
    if set(parent_by_id) != set(plan.parent_ids):
        raise InvalidScientificProblem("concrete successor parents do not match plan.parent_ids")
    ordered = tuple(parent_by_id[parent_id] for parent_id in plan.parent_ids)
    for parent in ordered:
        parent.validate_against(space)
        if parent.generation >= plan.generation:
            raise InvalidScientificProblem(
                "successor generation must be greater than every parent's generation"
            )

    proposals: list[SuccessorProposal] = []
    candidates: list[DesignCandidate] = []
    twins: list[ScientificTwin] = []
    rejected: list[SuccessorRejection] = []
    seen: set[str] = set()

    attempts = 0
    sequence_index = plan.sequence_start
    while len(candidates) < plan.count and attempts < plan.attempt_budget:
        attempts += 1
        a = ordered[(sequence_index - plan.sequence_start) % len(ordered)]
        b = ordered[(sequence_index - plan.sequence_start + 1) % len(ordered)]
        global_values = sampler.assignments_at(sequence_index)
        assignments = _successor_assignments(
            space=space,
            parent_a=a,
            parent_b=b,
            global_values=global_values,
            contraction=plan.contraction,
            sequence_index=sequence_index,
            generation=plan.generation,
        )
        digest = assignment_digest(assignments)
        cid = plan.candidate_id_for(sequence_index)
        proposal = SuccessorProposal(
            candidate_id=cid,
            design_space=space.reference,
            generation=plan.generation,
            parents=tuple(dict.fromkeys((a.reference, b.reference))),
            sequence_index=sequence_index,
            assignments=assignments,
        )
        sequence_index += 1
        if digest in seen:
            rejected.append(
                SuccessorRejection(cid, proposal.sequence_index, ("duplicate assignment in this successor batch",))
            )
            continue
        seen.add(digest)
        decision = gate.decide(proposal)
        if not isinstance(decision, ProposalDecision):
            raise InvalidScientificProblem("successor gate must return ProposalDecision")
        if not decision.accepted:
            rejected.append(SuccessorRejection(cid, proposal.sequence_index, decision.reasons))
            continue

        twin = _bind_twin(materializer.materialize(proposal), proposal)
        candidate = DesignCandidate(
            candidate_id=cid,
            design_space=space.reference,
            twin=twin.reference,
            assignments=assignments,
            generation=plan.generation,
            parents=proposal.parents,
            operator=SUCCESSOR_STRATEGY,
            metadata={
                "sequence_index": proposal.sequence_index,
                "assignment_digest": proposal.digest,
                "search_contraction": plan.contraction,
            },
        )
        proposals.append(proposal)
        candidates.append(candidate)
        twins.append(twin)

    if len(candidates) != plan.count:
        raise InvalidScientificProblem(
            f"successor search produced {len(candidates)}/{plan.count} accepted candidates "
            f"within attempt budget {plan.attempt_budget}"
        )

    population = DesignPopulation(
        population_id=plan.population_id,
        design_space=space.reference,
        generation=plan.generation,
        members=tuple(candidate.reference for candidate in candidates),
    )
    population.validate_candidates(candidates)
    return SuccessorGenerationBatch(
        plan=plan,
        population=population,
        proposals=tuple(proposals),
        candidates=tuple(candidates),
        twins=tuple(twins),
        rejected=tuple(rejected),
    )


__all__ = [
    "SUCCESSOR_BINDING_METADATA_KEY",
    "SUCCESSOR_STRATEGY",
    "SuccessorGate",
    "SuccessorGenerationBatch",
    "SuccessorGenerationPlan",
    "SuccessorProposal",
    "SuccessorRejection",
    "SuccessorTwinMaterializer",
    "generate_successors",
]
