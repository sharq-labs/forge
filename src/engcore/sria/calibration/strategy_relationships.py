"""Algorithm / strategy cost relationships.

**This module is not about fidelity.** CMA-ES, NGOpt, stacked and
adaptive_stacked are *search strategies* competing on the same problem at the
same fidelity. A ratio between them says which algorithm is cheaper — it says
nothing about a coarse model approximating a fine one.

M2's original framing filed these under "fidelity", which was wrong and would
have propagated into every downstream consumer: a multi-fidelity planner
reading "cmaes -> stacked = 5585x cheaper" as a fidelity rung would conclude it
can substitute a cheap *approximation*, when in fact both computed the same
objective exactly and only the search strategy differed.

Genuine model-fidelity relationships live in :mod:`fidelity`, which in M2 is a
contract with no real data behind it.

What is measured here is real and useful: paired realized-cost ratios between
strategies on identical problem instances, in one environment.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from ...scientific.serialization import schema_string
from .learning_record import ComputationalLearningRecord

STRATEGY_RELATIONSHIP_SCHEMA = schema_string("sria_strategy_cost_relationship")


class RelationshipKind(str, Enum):
    """Whether a learned relationship may transfer across domains."""

    #: Depends only on computational structure/environment. Transferable.
    STRUCTURE_TRANSFERABLE = "structure_transferable"
    #: Depends on the physics being modelled. Domain Pack territory.
    DOMAIN_OWNED = "domain_owned"


@dataclass(frozen=True)
class StrategyCostRelationship:
    """Observed cost ratio between two *algorithms* on identical problems.

    Named for what it is. There is deliberately no ``fidelity`` field and no
    accuracy statistic: this object cannot be mistaken for a claim that one
    strategy approximates another.
    """

    from_strategy: str
    to_strategy: str
    kind: RelationshipKind
    metric: str
    median_ratio: float
    geometric_mean_ratio: float
    p10_ratio: float
    p90_ratio: float
    paired_observations: int
    structure_digest: str
    environment_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", RelationshipKind(self.kind))
        if self.kind is RelationshipKind.DOMAIN_OWNED:
            raise ValueError(
                "M2 does not compute domain-owned relationships; accuracy and "
                "sufficiency claims belong to Domain Packs and their Critics"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STRATEGY_RELATIONSHIP_SCHEMA,
            "from_strategy": self.from_strategy,
            "to_strategy": self.to_strategy,
            "kind": self.kind.value,
            "metric": self.metric,
            "median_ratio": self.median_ratio,
            "geometric_mean_ratio": self.geometric_mean_ratio,
            "p10_ratio": self.p10_ratio,
            "p90_ratio": self.p90_ratio,
            "paired_observations": self.paired_observations,
            "structure_digest": self.structure_digest,
            "environment_digest": self.environment_digest,
        }


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def learn_strategy_cost_ratios(
    records: Sequence[ComputationalLearningRecord],
    *,
    min_pairs: int = 5,
) -> tuple[StrategyCostRelationship, ...]:
    """Paired cost ratios between algorithms on identical problem instances.

    Pairs are formed within (problem instance, structure, environment), so the
    two strategies compared ran the identical problem in the same place.
    """
    by_problem: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
    for record in records:
        if not record.cost_is_observed:
            continue
        key = (record.pair_id, record.structure.digest, record.environment.digest)
        by_problem[key].setdefault(record.solver_identity[0], record.realized_cost)

    ratios: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for (_, structure, environment), costs in by_problem.items():
        strategies = sorted(costs)
        for i, left in enumerate(strategies):
            for right in strategies[i + 1 :]:
                if costs[left] <= 0 or costs[right] <= 0:
                    continue
                ratios[(left, right, structure, environment)].append(
                    costs[right] / costs[left]
                )

    out: list[StrategyCostRelationship] = []
    for (left, right, structure, environment), values in sorted(ratios.items()):
        if len(values) < min_pairs:
            continue
        logs = [math.log(v) for v in values if v > 0]
        out.append(
            StrategyCostRelationship(
                from_strategy=left,
                to_strategy=right,
                kind=RelationshipKind.STRUCTURE_TRANSFERABLE,
                metric="realized_cost_ratio",
                median_ratio=statistics.median(values),
                geometric_mean_ratio=(
                    math.exp(statistics.mean(logs)) if logs else float("nan")
                ),
                p10_ratio=_percentile(values, 0.10),
                p90_ratio=_percentile(values, 0.90),
                paired_observations=len(values),
                structure_digest=structure[:12],
                environment_digest=environment[:12],
            )
        )
    return tuple(out)


def strategy_success_rates(
    records: Sequence[ComputationalLearningRecord],
) -> Mapping[str, float]:
    """Observed computational success rate per strategy. Descriptive only."""
    by_strategy: dict[str, list[bool]] = defaultdict(list)
    for record in records:
        if record.eligible_for_computational_failure_learning:
            by_strategy[record.solver_identity[0]].append(
                record.computational_success
            )
    return {
        strategy: statistics.mean(1.0 if v else 0.0 for v in values)
        for strategy, values in sorted(by_strategy.items())
        if values
    }
