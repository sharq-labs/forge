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

:class:`~engcore.scientific.composition.transfer.QuantityTransfer` — one
declared dependency, *realized*: the value that crossed, the record it was read
from, and the instant it was read at. It is the smallest record that makes an
existing crossing declared and checkable, and it was forced into existence by a
crossing that had none: one problem's declared quantity reaching another
problem's applicability assessment by matching component identifiers in a dict
comprehension.

:class:`~engcore.scientific.composition.conversion.EnergyConversion` — the
declaration a crossing needs when what crosses is *energy*: which form enters,
which form arrives, what fraction of it survives and where the rest goes. A
dependency carrying an energy or a power cannot be declared without one, which
is the point: the repository's one existing conversion was an ordinary
dependency plus a sentence in a twin's assumptions, and "all of it arrives" was
what you got by writing nothing.

Nothing here executes, schedules, interpolates, relaxes or converges anything.
A ``QuantityTransfer`` records that a value moved; it does not move it, does not
decide when to, and does not reconcile two that disagree — it refuses them.
Composition is stated; running it is a later milestone's contract, and
``NEEDS.md`` C4 says what that contract would have to add.
"""

from .conversion import (
    ENERGY_CONVERSION_SCHEMA,
    ConversionOutcome,
    EnergyConversion,
    LossPath,
)
from .dependency import (
    QUANTITY_DEPENDENCY_SCHEMA,
    QuantityDependency,
    externally_imposed,
    unresolved_inputs,
)
from .transfer import (
    QUANTITY_TRANSFER_SCHEMA,
    QuantityTransfer,
    require_agreeing_transfers,
)

__all__ = [
    "ENERGY_CONVERSION_SCHEMA",
    "ConversionOutcome",
    "EnergyConversion",
    "LossPath",
    "QUANTITY_DEPENDENCY_SCHEMA",
    "QuantityDependency",
    "QUANTITY_TRANSFER_SCHEMA",
    "QuantityTransfer",
    "externally_imposed",
    "require_agreeing_transfers",
    "unresolved_inputs",
]
