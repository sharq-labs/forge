"""DCCircuit — the typed topology of a linear resistive DC circuit.

This is the *domain* representation. It is deliberately not a
``ScientificProblem``: topology is domain-specific and has no place in the
universal IR. The mapping between the two lives in ``problem.py``, and the
solver receives topology through the prepared-solve payload.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ....scientific.errors import InvalidScientificProblem
from ....scientific.serialization import require_schema, schema_string
from .components import (
    DCCurrentSource,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)

CIRCUIT_SCHEMA = schema_string("electrical_dc_circuit")
CANONICAL_SCHEMA = schema_string("electrical_dc_circuit_canonical")

#: Marks a ScientificProblem as describing a DC circuit, so a fingerprint
#: found in problem metadata can be interpreted unambiguously.
DOMAIN_ARTIFACT_TYPE = "electrical_dc_circuit"


@dataclass(frozen=True)
class DCCircuit:
    """A validated linear resistive DC circuit.

    Invariants enforced at construction:

    * node ids unique;
    * component ids unique **across all component types** (a resistor and a
      source may not share an id — results are keyed by component id);
    * exactly one node marked ``is_reference``;
    * every component terminal names a declared node.
    """

    circuit_id: str
    nodes: tuple[ElectricalNode, ...]
    resistors: tuple[Resistor, ...] = ()
    voltage_sources: tuple[DCVoltageSource, ...] = ()
    current_sources: tuple[DCCurrentSource, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        circuit_id = str(self.circuit_id).strip()
        if not circuit_id:
            raise InvalidScientificProblem("circuit requires a non-empty id")
        object.__setattr__(self, "circuit_id", circuit_id)
        for label in ("nodes", "resistors", "voltage_sources", "current_sources"):
            object.__setattr__(self, label, tuple(getattr(self, label)))

        if not self.nodes:
            raise InvalidScientificProblem(
                f"circuit {circuit_id!r} declares no nodes"
            )

        node_ids = [n.node_id for n in self.nodes]
        duplicates = {n for n in node_ids if node_ids.count(n) > 1}
        if duplicates:
            raise InvalidScientificProblem(
                f"circuit {circuit_id!r} has duplicate node ids: "
                f"{sorted(duplicates)}"
            )

        component_ids = [c.component_id for c in self.components]
        duplicates = {c for c in component_ids if component_ids.count(c) > 1}
        if duplicates:
            raise InvalidScientificProblem(
                f"circuit {circuit_id!r} has duplicate component ids: "
                f"{sorted(duplicates)}"
            )

        references = [n.node_id for n in self.nodes if n.is_reference]
        if len(references) != 1:
            raise InvalidScientificProblem(
                f"circuit {circuit_id!r} requires exactly one reference node, "
                f"found {len(references)} ({sorted(references)}); the datum "
                f"must be declared explicitly"
            )

        known = set(node_ids)
        for component in self.components:
            for terminal in component.nodes:
                if terminal not in known:
                    raise InvalidScientificProblem(
                        f"component {component.component_id!r} references "
                        f"unknown node {terminal!r}"
                    )

    # ---- accessors ------------------------------------------------------
    @property
    def components(self) -> tuple:
        return (*self.resistors, *self.voltage_sources, *self.current_sources)

    @property
    def reference_node(self) -> str:
        return next(n.node_id for n in self.nodes if n.is_reference)

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(n.node_id for n in self.nodes)

    @property
    def non_reference_node_ids(self) -> tuple[str, ...]:
        """Deterministically ordered unknown-voltage nodes.

        Sorted by id so that an identical circuit always produces an
        identical matrix ordering, regardless of insertion order.
        """
        reference = self.reference_node
        return tuple(sorted(n for n in self.node_ids if n != reference))

    @property
    def ordered_voltage_sources(self) -> tuple[DCVoltageSource, ...]:
        """Voltage sources in deterministic id order (one unknown each)."""
        return tuple(sorted(self.voltage_sources, key=lambda s: s.component_id))

    def node(self, node_id: str) -> ElectricalNode:
        for candidate in self.nodes:
            if candidate.node_id == node_id:
                return candidate
        raise InvalidScientificProblem(f"unknown node {node_id!r}")

    def resistors_at(self, node_id: str) -> tuple[Resistor, ...]:
        return tuple(r for r in self.resistors if node_id in r.nodes)

    # ---- canonical scientific identity ----------------------------------
    def canonical_dict(self) -> dict[str, Any]:
        """A deterministic, unit-normalised description of the *physical*
        system, used to compute :meth:`fingerprint`.

        Three deliberate differences from :meth:`to_dict`:

        * **Values are normalised to domain base units** (ohm, volt, ampere),
          so ``1 kohm`` and ``1000 ohm`` describe the same physical circuit
          and therefore share an identity. A cosmetic unit choice must not
          create a different scientific system. ``to_dict`` keeps the units
          the caller wrote, for display and round-tripping.
        * ``circuit_id`` and ``description`` are **excluded**: they are
          labels. Renaming a circuit does not change the physics.
        * Terminal order within a component is **preserved, never sorted**.
          Swapping a resistor's terminals or a source's polarity flips the
          sign of the reported metrics, so it is a different measurement
          convention and must produce a different identity.

        Components and nodes are sorted by id, so insertion order cannot
        affect the result.
        """
        return {
            "schema": CANONICAL_SCHEMA,
            "reference_node": self.reference_node,
            "nodes": sorted(self.node_ids),
            "resistors": [
                {
                    "component_id": r.component_id,
                    "node_a": r.node_a,
                    "node_b": r.node_b,
                    "resistance_ohm": r.resistance.magnitude_in("ohm"),
                }
                for r in sorted(self.resistors, key=lambda c: c.component_id)
            ],
            "voltage_sources": [
                {
                    "component_id": s.component_id,
                    "positive_node": s.positive_node,
                    "negative_node": s.negative_node,
                    "voltage_volt": s.voltage.magnitude_in("volt"),
                }
                for s in sorted(self.voltage_sources, key=lambda c: c.component_id)
            ],
            "current_sources": [
                {
                    "component_id": s.component_id,
                    "from_node": s.from_node,
                    "to_node": s.to_node,
                    "current_ampere": s.current.magnitude_in("ampere"),
                }
                for s in sorted(self.current_sources, key=lambda c: c.component_id)
            ],
        }

    def fingerprint(self) -> str:
        """SHA-256 of the canonical description — a stable scientific identity.

        Deterministic across runs and processes: it uses a cryptographic hash
        over sorted, compact JSON, never Python's ``hash()``, object identity,
        a random UUID or a timestamp.
        """
        payload = json.dumps(
            self.canonical_dict(), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CIRCUIT_SCHEMA,
            "circuit_id": self.circuit_id,
            "description": self.description,
            "nodes": [n.to_dict() for n in sorted(self.nodes, key=lambda n: n.node_id)],
            "resistors": [
                r.to_dict()
                for r in sorted(self.resistors, key=lambda c: c.component_id)
            ],
            "voltage_sources": [
                s.to_dict()
                for s in sorted(self.voltage_sources, key=lambda c: c.component_id)
            ],
            "current_sources": [
                s.to_dict()
                for s in sorted(self.current_sources, key=lambda c: c.component_id)
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DCCircuit":
        require_schema(payload, CIRCUIT_SCHEMA)
        return cls(
            circuit_id=payload["circuit_id"],
            description=payload.get("description", ""),
            nodes=tuple(
                ElectricalNode.from_dict(n) for n in payload.get("nodes", ())
            ),
            resistors=tuple(
                Resistor.from_dict(r) for r in payload.get("resistors", ())
            ),
            voltage_sources=tuple(
                DCVoltageSource.from_dict(s)
                for s in payload.get("voltage_sources", ())
            ),
            current_sources=tuple(
                DCCurrentSource.from_dict(s)
                for s in payload.get("current_sources", ())
            ),
        )
