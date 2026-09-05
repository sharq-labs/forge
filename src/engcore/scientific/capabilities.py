"""Scientific capability identity — *what science is required or provided*.

This is deliberately **not**
:class:`~engcore.scientific.solvers.capability.SolverCapability`, and the
distinction is load-bearing rather than cosmetic:

``ScientificCapability``
    "Which physical/scientific operation is needed?"  It is a statement about
    nature and about what a computational realization claims to represent.

``SolverCapability``
    "Which computational operation can this backend execute?"  It is a
    statement about software: a linear solve, an ODE integration, a
    nonlinear root find.

One scientific capability may be reachable through several solver
capabilities, and one solver capability serves many scientific capabilities.
Collapsing the two would make that many-to-many relationship inexpressible
and would silently equate "we can integrate an ODE" with "we can model this
physics" — which is exactly the confusion this platform exists to prevent.

Deliberate omissions
--------------------
* **No description field.** A capability is pure identity; two records naming
  the same capability must be equal and hash alike regardless of how anyone
  chose to describe it. Prose belongs on the realization that declares it.
  ``SolverCapability`` reaches the same conclusion from the other direction:
  it keeps its description for humans but excludes it from equality and
  hashing, and exposes a bare ``SolverCapabilityId`` for records that only
  need to reference a capability.
* **No registry, global or otherwise.** Capability identifiers are open: a
  future domain package declares its own without editing the core, exactly as
  it already does for :class:`SolverCapability`.
* **No capability is defined here.** The core understands the *grammar* of a
  namespaced identifier and nothing about any particular science.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .errors import InvalidScientificCapability
from .serialization import require_schema, schema_string

SCIENTIFIC_CAPABILITY_SCHEMA = schema_string("scientific_capability")

#: One segment of an identifier: lowercase, starts with a letter, may carry
#: dotted sub-structure (``solid.linear_elasticity``). Strict by intent — a
#: canonical form means ``Mechanics:X`` cannot masquerade as a second,
#: distinct capability alongside ``mechanics:x``. Non-conforming text is
#: rejected rather than coerced: silently rewriting an identifier would be
#: inferring what the author meant.
_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")

SEPARATOR = ":"


@dataclass(frozen=True)
class ScientificCapability:
    """A namespaced scientific capability identifier, ``namespace:name``.

    Immutable, hashable and deterministic. Construct it from its two parts,
    or from a full identifier with :meth:`parse`.
    """

    namespace: str
    name: str

    def __post_init__(self) -> None:
        for label in ("namespace", "name"):
            raw = str(getattr(self, label)).strip()
            if not raw:
                raise InvalidScientificCapability(
                    f"scientific capability requires a non-empty {label}"
                )
            if not _SEGMENT.match(raw):
                raise InvalidScientificCapability(
                    f"scientific capability {label} {raw!r} is not a valid "
                    f"identifier segment; expected lowercase "
                    f"[a-z][a-z0-9_]* with optional dotted sub-segments"
                )
            object.__setattr__(self, label, raw)

    @property
    def identifier(self) -> str:
        """The canonical ``namespace:name`` form."""
        return f"{self.namespace}{SEPARATOR}{self.name}"

    @classmethod
    def parse(cls, identifier: str) -> "ScientificCapability":
        """Build a capability from ``"namespace:name"``.

        Exactly one separator is required. An unnamespaced identifier is
        refused rather than defaulted into some ``core:`` namespace: guessing
        which science a bare name belongs to is precisely the kind of
        inference this layer must not perform.
        """
        text = str(identifier).strip()
        parts = text.split(SEPARATOR)
        if len(parts) != 2:
            raise InvalidScientificCapability(
                f"scientific capability {text!r} must have exactly one "
                f"{SEPARATOR!r} separating namespace from name"
            )
        return cls(namespace=parts[0], name=parts[1])

    @classmethod
    def coerce(cls, value: "ScientificCapability | str") -> "ScientificCapability":
        """Accept an instance unchanged, or parse an identifier string."""
        if isinstance(value, ScientificCapability):
            return value
        if isinstance(value, str):
            return cls.parse(value)
        raise InvalidScientificCapability(
            f"cannot read a scientific capability from "
            f"{type(value).__name__}"
        )

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.identifier

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCIENTIFIC_CAPABILITY_SCHEMA,
            "namespace": self.namespace,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificCapability":
        require_schema(payload, SCIENTIFIC_CAPABILITY_SCHEMA)
        return cls(namespace=payload["namespace"], name=payload["name"])


def scientific_capabilities(
    values: Iterable["ScientificCapability | str"],
) -> frozenset[ScientificCapability]:
    """Normalize a mixed iterable of capabilities/identifiers to a frozen set."""
    return frozenset(ScientificCapability.coerce(v) for v in values)


def capability_identifiers(
    capabilities: Iterable[ScientificCapability],
) -> tuple[str, ...]:
    """Sorted canonical identifiers — the deterministic serialized form."""
    return tuple(sorted(c.identifier for c in capabilities))
