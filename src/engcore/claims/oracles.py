"""CORE-12 -- discovering trusted external evidence for a QOI in a context.

    What trusted external evidence is available for this model / QOI / context?

The trusted-oracle pin (``engcore.scientific.oracles``) can only be looked up by
``(oracle_id, version)``: it carries no QOI and no conditions, and it has no
registration API on purpose -- the party asking for a level must not be the
party that grants itself authority. This module answers the question above
without weakening either property:

* oracles are reached **only** through the benchmark and experimental routes
  capability declarations name, each with the domain's own provider; nothing
  here registers or constructs an oracle;
* an oracle is reported only when its content reproduces the repository pin
  (``OracleEvidenceSet.is_trusted``); an untrusted set is reported as refused;
* the QOI and conditions come from the oracle's own observations, and the level
  it can establish from its trusted identity (``OracleIdentity.establishes``).

Applicability is judged against the claim's stated operating context:
``EXACT`` when every condition is stated and equal, ``MISMATCH`` when a stated
value differs (the oracle then speaks about another operating point and cannot
validate this claim), ``UNKNOWN`` when a condition is not stated. Only EXACT
evidence can bear on a claim; the rest is listed so a reader sees what exists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.units.quantity import Quantity, dimensionality
from .capabilities import CapabilityRegistry, RouteKind


class OracleApplicability(str, Enum):
    EXACT = "exact"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OracleMatch:
    oracle_id: str
    version: str
    kind: str
    establishes: str
    trusted: bool
    trusted_digest: str
    reference: str
    capability_id: str
    route_id: str
    metric: str
    expected: Quantity
    tolerance: Quantity
    conditions: Mapping[str, Quantity]
    applicability: OracleApplicability
    mismatched: tuple[str, ...] = ()
    unstated: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle_id": self.oracle_id,
            "version": self.version,
            "kind": self.kind,
            "establishes": self.establishes,
            "trusted": self.trusted,
            "trusted_digest": self.trusted_digest,
            "reference": self.reference,
            "capability_id": self.capability_id,
            "route_id": self.route_id,
            "metric": self.metric,
            "expected": self.expected.to_dict(),
            "tolerance": self.tolerance.to_dict(),
            "conditions": {k: v.to_dict() for k, v in sorted(self.conditions.items())},
            "applicability": self.applicability.value,
            "mismatched": list(self.mismatched),
            "unstated": list(self.unstated),
        }


def _equal(stated: Any, fixed: Quantity) -> bool:
    if not isinstance(stated, Quantity) or dimensionality(stated.units) != dimensionality(fixed.units):
        return False
    return math.isclose(stated.to(fixed.units).magnitude, fixed.magnitude, rel_tol=1e-12, abs_tol=0.0)


def applicability(conditions: Mapping[str, Quantity], context: Mapping[str, Any]) -> tuple[OracleApplicability, tuple[str, ...], tuple[str, ...]]:
    mismatched = tuple(sorted(n for n, v in conditions.items() if n in context and not _equal(context[n], v)))
    unstated = tuple(sorted(n for n in conditions if n not in context))
    if mismatched:
        return OracleApplicability.MISMATCH, mismatched, unstated
    if unstated:
        return OracleApplicability.UNKNOWN, mismatched, unstated
    return OracleApplicability.EXACT, (), ()


def discover_oracles(
    registry: CapabilityRegistry,
    *,
    qoi: str | None = None,
    context: Mapping[str, Any] | None = None,
    kinds: Iterable[str] = (),
) -> tuple[OracleMatch, ...]:
    """Every trusted-or-refused oracle observation reachable through declared routes.

    Filtered by QOI (the observation's metric) and by oracle kind when given;
    applicability is judged against ``context`` (the claim's stated inputs).
    """
    wanted_kinds = frozenset(kinds)
    context = dict(context or {})
    out: list[OracleMatch] = []
    for declaration in registry:
        for route in declaration.routes:
            if route.kind not in (RouteKind.BENCHMARK, RouteKind.EXPERIMENTAL) or route.oracle_provider is None:
                continue
            evidence = route.oracle_provider()
            identity = evidence.identity
            if wanted_kinds and identity.kind.value not in wanted_kinds:
                continue
            for observation in evidence.observations:
                if qoi is not None and observation.metric != qoi:
                    continue
                state, mismatched, unstated = applicability(observation.conditions, context)
                out.append(
                    OracleMatch(
                        oracle_id=identity.oracle_id,
                        version=identity.version,
                        kind=identity.kind.value,
                        establishes=identity.establishes.value,
                        trusted=evidence.is_trusted,
                        trusted_digest=identity.evidence_digest,
                        reference=identity.reference,
                        capability_id=declaration.capability_id,
                        route_id=route.route_id,
                        metric=observation.metric,
                        expected=observation.expected,
                        tolerance=observation.absolute_tolerance,
                        conditions=dict(observation.conditions),
                        applicability=state,
                        mismatched=mismatched,
                        unstated=unstated,
                    )
                )
    return tuple(sorted(out, key=lambda m: (m.oracle_id, m.version, m.metric, m.capability_id)))


__all__ = ["OracleApplicability", "OracleMatch", "applicability", "discover_oracles"]
