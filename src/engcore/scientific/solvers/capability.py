"""Solver capabilities and solver-capability identity.

Capabilities are *extensible identifiers*, not a closed enum: a future domain
package must be able to declare ``CIRCUIT_TRANSIENT`` without editing the
core. Well-known names are provided as constants for convenience, but the
core never depends on any particular physical capability existing.

A capability answers exactly one question: which solver can support this
ScientificProblem?

Two types, one identity
-----------------------
:class:`SolverCapabilityId`
    The canonical identity alone. This is what a record *references* when it
    says "computing me needs this capability". It carries nothing but the
    name, so it round-trips losslessly through serialization.

:class:`SolverCapability`
    The declaration: the same identity plus human-readable prose. This is
    what a solver *publishes*.

**Identity is the canonical name and nothing else.** ``description`` is
excluded from equality and hashing: two records naming ``core:ode`` denote
the same capability however each chose to describe it. Letting prose into
identity would mean a set could hold ``core:ode`` twice, a dictionary keyed
by capability could miss a lookup because a caller reworded a docstring, and
a realization requiring ``core:ode`` would fail to match a solver providing
it. Description is documentation about a capability, never part of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..errors import ScientificCoreError
from ..serialization import require_schema, schema_string

CAPABILITY_SCHEMA = schema_string("solver_capability")


def _canonical_capability_name(value: Any) -> str:
    """Validate and canonicalize a solver capability name.

    The rules are exactly those this module has always enforced — non-empty
    after stripping, no interior whitespace — and deliberately no stricter.
    Requiring a ``namespace:name`` grammar here would retroactively invalidate
    any historical record whose capability name was unnamespaced, and
    migrating frozen records is not in scope. Namespacing remains the
    documented convention, enforced by review rather than by the type.
    """
    name = str(value).strip()
    if not name:
        raise ScientificCoreError("capability name must be non-empty")
    if any(ch.isspace() for ch in name):
        raise ScientificCoreError(
            f"capability name {name!r} must not contain whitespace"
        )
    return name


@dataclass(frozen=True)
class SolverCapabilityId:
    """Canonical identity of a solver capability, e.g. ``core:ode``.

    A *reference*, not a declaration: it names a capability without claiming
    to describe or provide one. Records that merely require a capability hold
    this, so that what they store is exactly what they can serialize and
    reload unchanged — a reference carrying borrowed prose would come back
    from ``from_dict`` with that prose silently emptied.

    It serializes as a bare string rather than a schema envelope, because it
    is a field of some owning record and not a record in its own right.
    """

    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _canonical_capability_name(self.name))

    @classmethod
    def coerce(
        cls, value: "SolverCapabilityId | SolverCapability | str"
    ) -> "SolverCapabilityId":
        """Accept an id unchanged, or take the identity of a name/declaration."""
        if isinstance(value, SolverCapabilityId):
            return value
        if isinstance(value, SolverCapability):
            return cls(value.name)
        if isinstance(value, str):
            return cls(value)
        raise ScientificCoreError(
            f"cannot read a solver capability identity from "
            f"{type(value).__name__}"
        )

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name


@dataclass(frozen=True)
class SolverCapability:
    """A declared capability: a namespaced identifier plus prose.

    ``description`` is documentation and is excluded from equality and
    hashing — see the module docstring. The serialized form still carries it,
    so no stored record changes shape.
    """

    name: str
    description: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _canonical_capability_name(self.name))

    @property
    def id(self) -> SolverCapabilityId:
        """This capability's identity, stripped of its description."""
        return SolverCapabilityId(self.name)

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CAPABILITY_SCHEMA,
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SolverCapability":
        require_schema(payload, CAPABILITY_SCHEMA)
        return cls(
            name=payload["name"], description=payload.get("description", "")
        )


def capability_names(
    capabilities: Iterable[SolverCapability | SolverCapabilityId | str],
) -> frozenset[str]:
    """Normalize a mixed iterable of capabilities/ids/names to a name set."""
    return frozenset(
        c.name
        if isinstance(c, (SolverCapability, SolverCapabilityId))
        else str(c)
        for c in capabilities
    )


def solver_capability_ids(
    capabilities: Iterable[SolverCapability | SolverCapabilityId | str],
) -> frozenset[SolverCapabilityId]:
    """Normalize a mixed iterable to validated capability identities."""
    return frozenset(SolverCapabilityId.coerce(c) for c in capabilities)


def solver_capability_identifiers(
    capabilities: Iterable[SolverCapabilityId],
) -> tuple[str, ...]:
    """Sorted canonical names — the deterministic serialized form."""
    return tuple(sorted(c.name for c in capabilities))


class CoreCapabilities:
    """Solver-shape capabilities the core itself can reason about.

    These describe the *mathematical form* of a problem, not a physical
    domain. Domain packages add their own names (``electrical:dc``,
    ``thermal:steady``) without touching this class.
    """

    ALGEBRAIC = SolverCapability("core:algebraic", "Closed-form algebraic evaluation")
    LINEAR_SYSTEM = SolverCapability("core:linear_system", "Linear system solve")
    NONLINEAR_SYSTEM = SolverCapability(
        "core:nonlinear_system", "Nonlinear root finding"
    )
    ODE = SolverCapability("core:ode", "Ordinary differential equations")
    DAE = SolverCapability("core:dae", "Differential algebraic equations")
    PDE = SolverCapability("core:pde", "Partial differential equations")
    OPTIMIZATION = SolverCapability("core:optimization", "Numerical optimization")
    STOCHASTIC = SolverCapability("core:stochastic", "Stochastic/Monte Carlo methods")

    @classmethod
    def all(cls) -> tuple[SolverCapability, ...]:
        return tuple(
            value
            for key, value in sorted(vars(cls).items())
            if isinstance(value, SolverCapability)
        )
