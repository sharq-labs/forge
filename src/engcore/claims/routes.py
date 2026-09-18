"""CORE-6 -- execution routes: what each route IS, and what it could establish.

A capability declares its routes (:class:`~engcore.claims.capabilities.RouteDeclaration`):
the primary simulation, further solver routes, an analytic reference, a
benchmark or experimental oracle. This module classifies them for planning,
and the classification is never taken from the declaration's own words.

Solver routes: independence is read from the pins
-------------------------------------------------
Two solver routes are compared through the identities the domain layer pins in
``engcore.domains.SCIENTIFIC_ROUTE_DECLARATIONS``, resolved by the Core's own
:func:`~engcore.scientific.consensus.canonical_component_identity` -- so one
implementation reached through two names is one identity -- and judged by the
same rule :class:`~engcore.scientific.consensus.CrossSolverConsensus` applies:

``ALIAS``                  the same canonical identities in every solver
                           dimension: one implementation under another name.
``SHARED_IMPLEMENTATION``  a shared canonical implementation (a different
                           numerical method inside the same code is still the
                           same code).
``PARTIALLY_INDEPENDENT``  no shared implementation, but a shared backend,
                           preprocessing or numerical method: not enough for
                           ``CROSS_SOLVER_VALIDATED``.
``INDEPENDENT``            nothing shared in any solver-independence dimension
                           (the problem declaration may be shared: that is what
                           makes two answers comparable).
``UNVERIFIED``             a route without a pin, or a pin whose identities do
                           not reproduce its own digest.

Only ``INDEPENDENT`` can establish ``CROSS_SOLVER_VALIDATED``, and that level is
**verification**: two codes agreeing says the equations were solved, never that
the equations describe reality. The classification is a planning-time
prediction; the executed consensus, with its byte-verified independence
evidence, remains the only thing that awards the level.

Evidence routes
---------------
An analytic reference can establish ``ANALYTICALLY_VERIFIED`` (verification).
A benchmark or experimental oracle establishes what its *trusted* identity
establishes (``BENCHMARK_VALIDATED`` or ``EXPERIMENTALLY_VALIDATED``) --
validation, the only kind that speaks to reality.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.consensus import (
    SOLVER_INDEPENDENCE_DIMENSIONS,
    IndependenceDimension,
    RouteDependencies,
)
from ..scientific.errors import ScientificCoreError
from ..scientific.results.validation import VALIDATION_LEVELS, ValidationLevel
from .capabilities import CapabilityDeclaration, RouteDeclaration, RouteKind


class RouteClass(str, Enum):
    PRIMARY = "primary"
    ALIAS = "alias"
    SHARED_IMPLEMENTATION = "shared_implementation"
    PARTIALLY_INDEPENDENT = "partially_independent"
    INDEPENDENT = "independent"
    UNVERIFIED = "unverified"
    ANALYTIC_REFERENCE = "analytic_reference"
    BENCHMARK = "benchmark"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class PinnedDependencies:
    """A pinned route's canonical identities per dimension, or why there are none."""

    route_id: str
    identities: Mapping[IndependenceDimension, frozenset[str]] | None
    problem: str | None = None


def pinned_dependencies(pinned_route: str | None) -> PinnedDependencies:
    """Read a route's pin and prove it reproduces its own digest."""
    from .. import domains

    if pinned_route is None:
        return PinnedDependencies("", None, "the route names no pinned declaration")
    pin = domains.SCIENTIFIC_ROUTE_DECLARATIONS.get(pinned_route)
    if pin is None:
        return PinnedDependencies(pinned_route, None, f"{pinned_route!r} is not a pinned route")
    try:
        dependencies = RouteDependencies(
            identities={key: frozenset(value) for key, value in dict(pin["identities"]).items()}
        )
        canonical = dependencies.canonical()
        digest = dependencies.digest
    except (ScientificCoreError, KeyError, TypeError) as exc:
        return PinnedDependencies(pinned_route, None, f"the pin for {pinned_route!r} cannot be read: {exc}")
    if digest != pin.get("dependency_digest"):
        return PinnedDependencies(
            pinned_route, None, f"the pin for {pinned_route!r} does not reproduce its own dependency digest"
        )
    return PinnedDependencies(pinned_route, canonical)


def classify_dependencies(
    primary: Mapping[IndependenceDimension, frozenset[str]],
    other: Mapping[IndependenceDimension, frozenset[str]],
) -> tuple[RouteClass, tuple[IndependenceDimension, ...]]:
    """The relation of ``other`` to ``primary``, and the solver dimensions they share."""
    shared = tuple(
        dimension for dimension in IndependenceDimension if primary[dimension] & other[dimension]
    )
    solver_shared = tuple(d for d in shared if d in SOLVER_INDEPENDENCE_DIMENSIONS)
    if all(primary[d] == other[d] for d in SOLVER_INDEPENDENCE_DIMENSIONS):
        return RouteClass.ALIAS, solver_shared
    if IndependenceDimension.IMPLEMENTATION in shared:
        return RouteClass.SHARED_IMPLEMENTATION, solver_shared
    if solver_shared:
        return RouteClass.PARTIALLY_INDEPENDENT, solver_shared
    return RouteClass.INDEPENDENT, solver_shared


@dataclass(frozen=True)
class RouteAssessment:
    """One declared route, classified for planning."""

    route_id: str
    kind: RouteKind
    route_class: RouteClass
    could_establish: ValidationLevel | None
    attainable_here: bool
    active: bool
    check_name: str | None
    shared_dimensions: tuple[str, ...] = ()
    reason: str = ""

    @property
    def is_validation(self) -> bool:
        return self.could_establish in VALIDATION_LEVELS

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "kind": self.kind.value,
            "route_class": self.route_class.value,
            "could_establish": None if self.could_establish is None else self.could_establish.value,
            "is_validation": self.is_validation,
            "attainable_here": self.attainable_here,
            "active": self.active,
            "check_name": self.check_name,
            "shared_dimensions": list(self.shared_dimensions),
            "reason": self.reason,
        }


def _oracle_level(route: RouteDeclaration) -> ValidationLevel | None:
    if route.oracle_provider is None:
        return None
    evidence = route.oracle_provider()
    return evidence.identity.establishes if evidence.is_trusted else None


def assess_routes(declaration: CapabilityDeclaration, supplied_paths: Iterable[str]) -> tuple[RouteAssessment, ...]:
    """Classify every declared route of ``declaration`` against its primary."""
    from .capabilities import declared_path

    supplied = {declared_path(p) for p in supplied_paths}
    attainable = {a.route_id: a.level for a in declaration.attainable_levels if a.route_id is not None}
    primary = declaration.primary_route
    primary_pin = pinned_dependencies(primary.pinned_route)
    out: list[RouteAssessment] = []
    for route in declaration.routes:
        active = not route.activation or any(path in supplied for path in route.activation)
        common = dict(
            route_id=route.route_id,
            kind=route.kind,
            active=active,
            check_name=route.check_name,
        )
        if route.kind is RouteKind.PRIMARY_SIMULATION:
            out.append(RouteAssessment(route_class=RouteClass.PRIMARY, could_establish=None, attainable_here=False, **common))
            continue
        if route.kind is RouteKind.ANALYTIC_REFERENCE:
            level = ValidationLevel.ANALYTICALLY_VERIFIED
            out.append(
                RouteAssessment(
                    route_class=RouteClass.ANALYTIC_REFERENCE,
                    could_establish=level,
                    attainable_here=attainable.get(route.route_id) is level,
                    reason="a pinned analytic reference: verification of the solve, not validation of the model",
                    **common,
                )
            )
            continue
        if route.kind in (RouteKind.BENCHMARK, RouteKind.EXPERIMENTAL):
            level = _oracle_level(route)
            out.append(
                RouteAssessment(
                    route_class=RouteClass.BENCHMARK if route.kind is RouteKind.BENCHMARK else RouteClass.EXPERIMENTAL,
                    could_establish=level,
                    attainable_here=level is not None and attainable.get(route.route_id) is level,
                    reason=(
                        "a trusted external oracle: validation against reality at its stated conditions only"
                        if level is not None
                        else "the oracle is not trusted: it establishes nothing"
                    ),
                    **common,
                )
            )
            continue
        # A further solver route: independence is computed, never declared.
        other_pin = pinned_dependencies(route.pinned_route)
        if primary_pin.identities is None or other_pin.identities is None:
            out.append(
                RouteAssessment(
                    route_class=RouteClass.UNVERIFIED,
                    could_establish=None,
                    attainable_here=False,
                    reason=primary_pin.problem or other_pin.problem or "unverified",
                    **common,
                )
            )
            continue
        route_class, shared = classify_dependencies(primary_pin.identities, other_pin.identities)
        level = ValidationLevel.CROSS_SOLVER_VALIDATED if route_class is RouteClass.INDEPENDENT else None
        out.append(
            RouteAssessment(
                route_class=route_class,
                could_establish=level,
                attainable_here=level is not None and attainable.get(route.route_id) is level,
                shared_dimensions=tuple(d.value for d in shared),
                reason=(
                    "independent in every solver dimension: may establish CROSS_SOLVER_VALIDATED "
                    "(verification only) when the executed consensus verifies it"
                    if level is not None
                    else f"shares {[d.value for d in shared]} with the primary route: cannot establish "
                    f"CROSS_SOLVER_VALIDATED"
                ),
                **common,
            )
        )
    return tuple(out)


__all__ = [
    "PinnedDependencies",
    "RouteAssessment",
    "RouteClass",
    "assess_routes",
    "classify_dependencies",
    "pinned_dependencies",
]
