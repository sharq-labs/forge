"""The BR1 synthetic contract worlds restated for BR1.1 uncertainty semantics (reasoning fixtures, never admissible).

BR1's fixtures state every interval with no coverage (``confidence_level=None``) and declare no uncertainty demand,
so under BR1.1 a precondition or state-domain decision on those values is MISSING_INFORMATION: a coverage below 1
(or an unstated one) is never an enclosure.  To keep exercising the rest of the BR1 contract (roles, levels, guards,
fixed conditions, providers, budgets, replay), this module restates each root world with its intervals at a stated
95 % coverage and the core's ``UncertaintySpecification`` demanding exactly that coverage of those variables.  The
worlds still cite synthetic fixture references, so no owner can verify them and admission refuses them.

Everything else is the BR1 fixture vocabulary, unchanged (``benchmarks/mind_gen2_world_v1/fixtures.py`` is frozen
with the BR1 benchmark and is not edited).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from benchmarks.mind_gen2_world_v1 import fixtures as _br1
from benchmarks.mind_gen2_world_v1.fixtures import *  # noqa: F401,F403 - the BR1 fixture vocabulary
from benchmarks.mind_gen2_world_v1.fixtures import Uncertainty, q, same
from engcore.mind.world import ScientificWorld
from engcore.scientific import UncertaintyRequirement, UncertaintySpecification
from engcore.scientific.results.uncertainty import UncertaintyKind

COVERAGE = 0.95


def interval(value: float, half: float, unit: str) -> Uncertainty:
    """A synthetic interval at a stated 95 % coverage (probabilistic; never an enclosure)."""
    return Uncertainty(kind="interval", lower=q(value - half, unit), upper=q(value + half, unit),
                       confidence_level=COVERAGE, method="synthetic declared interval at 95 % coverage")


def covered(world: ScientificWorld) -> ScientificWorld:
    """A root BR1 world with every unstated-coverage interval restated at 95 % and that coverage demanded."""
    if world.lineage.revision != 0:
        raise ValueError("only a root world is restated")
    variables, demanded = [], []
    for v in world.variables:
        u = v.uncertainty
        if u.kind is UncertaintyKind.INTERVAL:
            demanded.append(v.name)
            if u.confidence_level is None:
                v = dataclasses.replace(v, uncertainty=dataclasses.replace(
                    u, confidence_level=COVERAGE, method=u.method + " (restated at 95 % coverage)"))
        variables.append(v)
    if not demanded:
        return world
    spec = UncertaintySpecification(UncertaintyRequirement.QUANTIFIED, tuple(sorted(demanded)), COVERAGE,
                                    "synthetic protocol takes state decisions at the stated 95 % coverage")
    return dataclasses.replace(world, variables=tuple(variables), uncertainty=spec)


def battery_world(n: Callable[[str], str] = same) -> ScientificWorld:
    return covered(_br1.battery_world(n))


def hvac_world(task: str = "chamber", n: Callable[[str], str] = same) -> ScientificWorld:
    return covered(_br1.hvac_world(task, n))


def drone_world(n: Callable[[str], str] = same) -> ScientificWorld:
    return covered(_br1.drone_world(n))


def motor_world(n: Callable[[str], str] = same) -> ScientificWorld:
    return covered(_br1.motor_world(n))


def gen1_pool_world(n: Callable[[str], str] = same) -> ScientificWorld:
    return covered(_br1.gen1_pool_world(n))


WORLDS: dict[str, Callable[..., Any]] = {
    "battery": battery_world,
    "hvac_chamber": lambda n=same: hvac_world("chamber", n),
    "hvac_field": lambda n=same: hvac_world("field", n),
    "drone": drone_world,
    "motor": motor_world,
}
