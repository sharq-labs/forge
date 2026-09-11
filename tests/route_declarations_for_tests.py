"""Routes a test can declare, pinned for the length of one test.

``CrossSolverConsensus`` reads independence only from declarations the domain
layer pins (``engcore.domains.SCIENTIFIC_ROUTE_DECLARATIONS``) and verifies. A
test about completeness, tolerance, serialization or the independence
dimensions themselves needs routes that pass that check without being
production routes, so this module builds them and pins them **beside** the real
declarations, never instead of them: the chain map below is searched first and
falls through to whatever the domain layer declares.

Not a way around the rule. A test that wants an unverifiable route simply does
not declare it, which is what every false-independence case in
``test_route_independence_authority.py`` does.
"""

from __future__ import annotations

from collections import ChainMap

import pytest

import engcore.domains as domain_layer
from engcore.scientific.consensus import (
    ROUTE_DECLARATIONS_ATTRIBUTE,
    IndependenceDimension,
    RouteDependencies,
    SolveRoute,
)
from engcore.scientific.solvers.protocol import SolverIdentity

#: Pins added by :func:`declare`, cleared between tests by the fixture.
PINS: dict[str, dict[str, str]] = {}


def dependencies(route_id: str, **overrides) -> RouteDependencies:
    """A distinct identity per dimension, and one problem declaration shared.

    The shared problem declaration is the production shape: two routes asked
    one question. Pass ``problem_declaration=...`` to break even that, or any
    dimension by name to make routes share it.
    """
    identities: dict[IndependenceDimension, set[str]] = {
        dimension: {f"ext:test:{route_id}:{dimension.value}"}
        for dimension in IndependenceDimension
    }
    identities[IndependenceDimension.PROBLEM_DECLARATION] = {"ext:test:one-problem"}
    for name, value in overrides.items():
        identities[IndependenceDimension(name)] = (
            {value} if isinstance(value, str) else set(value)
        )
    return RouteDependencies(identities)


def route(route_id: str, solver: SolverIdentity | None = None, **overrides) -> SolveRoute:
    """A declared route, pinned, ready to be handed to a consensus."""
    return declare(
        SolveRoute(
            route_id=route_id,
            solver=solver or SolverIdentity(f"solver.{route_id}", "1.0", backend=route_id),
            dependencies=dependencies(route_id, **overrides),
        )
    )[0]


def declare(*routes: SolveRoute) -> tuple[SolveRoute, ...]:
    """Pin each route's own declaration, as the domain layer would."""
    for item in routes:
        assert item.dependencies is not None, f"{item.route_id} declares nothing to pin"
        PINS[item.route_id] = {
            "solver_id": item.solver.solver_id,
            "backend": item.solver.backend,
            "dependency_digest": item.dependencies.digest,
        }
    return routes


@pytest.fixture(autouse=True)
def route_declarations_for_tests(monkeypatch):
    """Install the test pins beside the real ones for one test."""
    PINS.clear()
    original = getattr(domain_layer, ROUTE_DECLARATIONS_ATTRIBUTE)
    monkeypatch.setattr(
        domain_layer, ROUTE_DECLARATIONS_ATTRIBUTE, ChainMap(PINS, dict(original))
    )
    yield PINS
    PINS.clear()
