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


#: The threshold gate and tolerance key a test pin names unless told otherwise:
#: the DC cross-solver gate, which is what the consensus tests judge against.
#: A route declaration names the gate its comparison belongs to (CONS-01), so a
#: consensus judged under any other declared set earns nothing.
DEFAULT_THRESHOLD_GATE_ID = "electrical.dc.cross_solver"
DEFAULT_TOLERANCE_KEY = "agreement_rel_tol"


def route(
    route_id: str,
    solver: SolverIdentity | None = None,
    *,
    threshold_gate_id: str = DEFAULT_THRESHOLD_GATE_ID,
    tolerance_key: str = DEFAULT_TOLERANCE_KEY,
    **overrides,
) -> SolveRoute:
    """A declared route, pinned, ready to be handed to a consensus."""
    return declare(
        SolveRoute(
            route_id=route_id,
            solver=solver or SolverIdentity(f"solver.{route_id}", "1.0", backend=route_id),
            dependencies=dependencies(route_id, **overrides),
        ),
        threshold_gate_id=threshold_gate_id,
        tolerance_key=tolerance_key,
    )[0]


def declare(
    *routes: SolveRoute,
    threshold_gate_id: str = DEFAULT_THRESHOLD_GATE_ID,
    tolerance_key: str = DEFAULT_TOLERANCE_KEY,
) -> tuple[SolveRoute, ...]:
    """Pin each route's own declaration, as the domain layer would."""
    for item in routes:
        assert item.dependencies is not None, f"{item.route_id} declares nothing to pin"
        PINS[item.route_id] = {
            "solver_id": item.solver.solver_id,
            "backend": item.solver.backend,
            "dependency_digest": item.dependencies.digest,
            # Listed as declared: the core compares a route's identities
            # against this list before it resolves any of them (IND-05).
            "identities": {
                dimension.value: sorted(names)
                for dimension, names in item.dependencies.identities.items()
            },
            "threshold_gate_id": threshold_gate_id,
            "tolerance_key": tolerance_key,
        }
    return routes


def bound_results(routes, values, *, consensus_id="test", unit="dimensionless"):
    """One executed-looking ``ScientificResult`` per route, carrying ``values``.

    Distinct result ids and run ids, each naming its route's solver in its own
    provenance and as its solver identity -- what ``from_results`` requires of
    a result before it binds a route to it (IND-02).
    """
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ScientificResult
    from engcore.scientific.units.quantity import Quantity

    results = {}
    for item in routes:
        results[item.route_id] = ScientificResult(
            result_id=f"{consensus_id}:{item.route_id}",
            values={
                name: Quantity(float(value), unit)
                for name, value in values.get(item.route_id, {}).items()
            },
            provenance=ProvenanceRecord(
                run_id=f"{consensus_id}:{item.route_id}:run",
                solvers=(item.solver.key,),
            ),
            solver=item.solver,
        )
    return results


def earned_consensus(routes, values, *, thresholds, tolerance_key, required, consensus_id="test"):
    """The construction path that can award ``CROSS_SOLVER_VALIDATED``.

    ``from_results`` over :func:`bound_results`: since IND-02 a mapping of
    numbers (``over``) never awards the level, so a test that needs a
    level-bearing consensus binds each route to a result.
    """
    from engcore.scientific.consensus import CrossSolverConsensus

    routes = tuple(routes)
    return CrossSolverConsensus.from_results(
        consensus_id=consensus_id,
        routes=routes,
        results=bound_results(routes, values, consensus_id=consensus_id),
        thresholds=thresholds,
        tolerance_key=tolerance_key,
        required_outputs=tuple(required),
    )


def bound_over(*, consensus_id, routes, values, thresholds, tolerance_key, required_outputs=(), notes=""):
    """``CrossSolverConsensus.over``'s signature, bound to results where it can be.

    A drop-in for the tests written against ``over`` before IND-02, whose
    positive cases need the level: every route's numbers are carried by a
    ``ScientificResult`` (:func:`bound_results`) and compared through
    ``from_results``. Non-finite numbers cannot be carried by a ``Quantity``,
    so those cases -- which establish nothing on any path -- go through
    ``over`` unchanged. Every refusal the tests pin is reached on both paths.
    """
    import math

    from engcore.scientific.consensus import CrossSolverConsensus

    routes = tuple(routes)
    finite = all(
        math.isfinite(float(value))
        for produced in values.values()
        for value in produced.values()
    )
    known = {item.route_id for item in routes}
    if not finite or set(values) != known:
        return CrossSolverConsensus.over(
            consensus_id=consensus_id, routes=routes, values=values,
            thresholds=thresholds, tolerance_key=tolerance_key,
            required_outputs=required_outputs, notes=notes,
        )
    return CrossSolverConsensus.from_results(
        consensus_id=consensus_id,
        routes=routes,
        results=bound_results(routes, values, consensus_id=consensus_id),
        thresholds=thresholds,
        tolerance_key=tolerance_key,
        required_outputs=required_outputs,
        notes=notes,
    )


def pin_artifact_bytes(route_id: str, identity: str, payload: bytes) -> None:
    """Pin, as the domain layer would, which bytes one external dependency of a route is.

    IND-03: bytes presented for an ``ext:`` identity are evidence only when their
    digest is pinned for that identity on that route; a ``py:`` identity is never
    pinned, because Forge reads the source it resolves for itself. A test that
    builds a world of artifacts states that world's truth here, exactly as a
    domain would state its own in ``engcore.domains``.
    """
    from engcore.scientific.consensus import canonical_component_identity
    from engcore.scientific.errors import ScientificValidationError
    from engcore.scientific.independence_evidence import ArtifactFingerprint

    try:
        canonical = canonical_component_identity(identity)
    except ScientificValidationError:
        return
    if canonical.startswith("py:"):
        return
    digest = ArtifactFingerprint.from_bytes("pin", payload).digest
    entry = PINS.setdefault(route_id, {})
    digests = entry.setdefault("artifact_digests", {}).setdefault(canonical, [])
    if digest not in digests:
        digests.append(digest)


def resolved_source(identity: str) -> bytes:
    """The source bytes Forge resolves for a ``py:`` identity: its defining module's file."""
    import importlib
    import pathlib

    from engcore.scientific.consensus import canonical_component_identity

    module_name = canonical_component_identity(identity)[len("py:"):].partition(":")[0]
    return pathlib.Path(importlib.import_module(module_name).__file__).read_bytes()

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
