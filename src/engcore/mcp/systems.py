"""The systems this transport exposes, as a registry rather than a list.

Why this module exists
----------------------
``describe_capabilities`` used to hold one system's description inline: a
hand-written summary beside a call to one builder, inside a one-element list.
That is a description of the electro-thermal system wearing the shape of a
description of the runtime, and the difference only shows when a second system
arrives — which is exactly when a reader is most likely to trust it.

So every per-system fact a description needs is a field on
:class:`SystemBoundary`, and :func:`describe_capabilities` iterates. Adding a
third system is one entry here and a module beside the two that exist; it is
not an edit to the transport, and it cannot produce a description that
describes one system and claims to describe all of them.

What is written down here, and what is not
-------------------------------------------
**Written down:** the name, the tool name, and a one-line summary. Those are
naming decisions with no record to read them off — no model states that this
composition is called "electrothermal", and the tool name is a protocol fact.

**Not written down:** every field, its dimension, whether it is required, what
it unlocks, and the runnable example. All of those come from
:meth:`SystemBoundary.describe`, which reads the model registries at call
time. A model input added, removed or re-dimensioned in a domain changes the
description rather than making it quietly false.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from . import battery as bat_boundary
from . import problem as et_boundary

__all__ = ["SYSTEMS", "SystemBoundary", "system"]


@dataclass(frozen=True)
class SystemBoundary:
    """One system a caller may pose a case to.

    ``describe`` and ``run`` are the two halves of a boundary and both are
    required: a system that could be described and not run would let an agent
    write a case nothing accepts, and one that could be run and not described
    would make an agent guess the payload — which is the situation
    ``describe_capabilities`` exists to remove.
    """

    name: str
    tool: str
    summary: str
    describe: Callable[[], et_boundary.CaseDescription]
    run: Callable[..., Any]

    def description(self) -> et_boundary.CaseDescription:
        return self.describe()


ELECTROTHERMAL = SystemBoundary(
    name="electrothermal",
    tool="run_electrothermal",
    summary=(
        "A DC series circuit of temperature-dependent resistors coupled to "
        "first-order lumped thermal bodies, run to a fixed point. One "
        "credibility evidence report per stage."
    ),
    describe=et_boundary.describe_electrothermal_case,
    run=et_boundary.run_electrothermal_case,
)

BATTERY = SystemBoundary(
    name="battery",
    tool="run_battery",
    summary=(
        "One equivalent-circuit cell discharged over a marched interval, "
        "heating itself against a lumped thermal body. Four independent "
        "battery claims plus the thermal one, in a single credibility "
        "evidence report. The coupling is ONE-WAY and never iterates to a "
        "fixed point, so the march reports its own outcome rather than a "
        "convergence."
    ),
    describe=bat_boundary.describe_battery_case,
    run=bat_boundary.run_battery_case,
)

#: Every system, in a fixed order so two calls to ``describe_capabilities``
#: agree.
SYSTEMS: tuple[SystemBoundary, ...] = (ELECTROTHERMAL, BATTERY)


def system(name: str) -> SystemBoundary:
    """One system by name, or a loud failure naming the ones that exist."""
    for candidate in SYSTEMS:
        if candidate.name == name:
            return candidate
    raise KeyError(
        f"no system named {name!r}; this runtime exposes "
        f"{[s.name for s in SYSTEMS]}"
    )
