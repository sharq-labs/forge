"""System composition semantics — how separately posed problems fit together.

Layer C of the architecture map, and deliberately the *smallest* part of it
that a real two-way consumer forced into existence.

What is here
------------
:class:`~engcore.scientific.composition.dependency.QuantityDependency` — one
directed statement that a named quantity of one problem supplies a named
quantity of another, plus two readers over a set of problems.

What is **not** here, and why
-----------------------------
No ``ComponentDefinition``, ``ComponentInstance``, ``SystemDefinition``,
``SystemInstance``, port type, physical connector, hierarchy or assembly.
Every one of them was tested against the question *what exact information
becomes impossible, duplicated, ambiguous or domain-specific without it?* and
every one gave a weak answer for the consumer at hand.

Instance identity in particular is **not** invented here:
:class:`~engcore.scientific.twins.definition.ScientificTwin` is already the
versioned authority for one scientific system instance, carrying typed
declarations with ``PARAMETER``/``STATE``/``OPERATING_CONDITION``/``CONTROL``
roles. A second authority would be a duplicate, not a layer.

Nothing here executes, schedules, transfers, interpolates, relaxes or converges
anything. Composition is stated; running it is a later milestone's contract.
"""

from .dependency import (
    QUANTITY_DEPENDENCY_SCHEMA,
    QuantityDependency,
    externally_imposed,
    unresolved_inputs,
)

__all__ = [
    "QUANTITY_DEPENDENCY_SCHEMA",
    "QuantityDependency",
    "externally_imposed",
    "unresolved_inputs",
]
