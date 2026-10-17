"""Deterministic, applicability-aware solver selection (Phase 2 BR11).

Selection reuses what exists: provider discovery (:class:`~.catalog.ProviderStatus`),
declared capabilities (:class:`~.catalog.ProviderCapability`) and admitted
qualifications (:func:`~.qualification.admitted_qualifications`).  It adds a
RECORD of the decision and three rules:

* **Availability is not qualification.**  An available provider with no
  admitted qualification of its exact build and adapter covering the required
  scope is refused, whatever else it offers.  Nothing is promoted because it is
  the one that happens to be installed.
* **Applicability first.**  Physics, dimension, time mode, output ranks, mesh
  requirement, restart and checkpoint support are matched against the declared
  capability; regimes, equations and boundary-condition kinds a capability
  record does not carry are matched through the qualification SCOPE tokens,
  which is the envelope the provider was actually checked in.
* **Deterministic order** among the eligible: the caller's explicit preference
  list, then provider id.  No speed, popularity or availability ranking.

The result is a :class:`SolverSelection` with every provider's verdict and
reasons, so a fallback decision is traceable to a recorded criterion.  A
selection grants no scientific authority: an eligible provider's result is
still only a result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from .catalog import ProviderStatus
from .health import ProviderQualification
from .qualification import admitted_qualifications


@dataclass(frozen=True)
class SolverRequirement:
    """What the admitted problem needs of a solver.  ``qualification_scope`` is mandatory."""

    physics: tuple[str, ...]
    qualification_scope: tuple[str, ...]
    dimension: int | None = None
    time_mode: str | None = None
    output_ranks: tuple[str, ...] = ()
    mesh_requirement: str | None = None
    restart: bool = False
    checkpoint: bool = False

    def __post_init__(self) -> None:
        physics = tuple(sorted({str(p).strip() for p in self.physics}))
        scope = tuple(sorted({str(s).strip() for s in self.qualification_scope}))
        if not physics or "" in physics:
            raise InvalidScientificProblem("a solver requirement names the physics it needs")
        if not scope or "" in scope:
            raise InvalidScientificProblem(
                "a solver requirement names the qualification scope it needs; without one, any available provider "
                "would be eligible, which is availability standing in for qualification"
            )
        object.__setattr__(self, "physics", physics)
        object.__setattr__(self, "qualification_scope", scope)
        object.__setattr__(self, "output_ranks", tuple(sorted({str(r).strip() for r in self.output_ranks})))

    def to_dict(self) -> dict[str, Any]:
        return {"physics": list(self.physics), "qualification_scope": list(self.qualification_scope),
                "dimension": self.dimension, "time_mode": self.time_mode, "output_ranks": list(self.output_ranks),
                "mesh_requirement": self.mesh_requirement, "restart": self.restart, "checkpoint": self.checkpoint}


@dataclass(frozen=True)
class SelectionEntry:
    provider_id: str
    eligible: bool
    reasons: tuple[str, ...]
    build: tuple[str, str] = ("", "")
    qualification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "eligible": self.eligible, "reasons": list(self.reasons),
                "build": list(self.build), "qualification": self.qualification}


@dataclass(frozen=True)
class SolverSelection:
    requirement: SolverRequirement
    entries: tuple[SelectionEntry, ...]
    order: tuple[str, ...]
    preference: tuple[str, ...]

    @property
    def selected(self) -> str | None:
        return self.order[0] if self.order else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "solver_selection",
            "requirement": self.requirement.to_dict(),
            "entries": [e.to_dict() for e in self.entries],
            "order": list(self.order),
            "preference": list(self.preference),
            "criteria": ("available; declared capability covers the requirement; an admitted qualification of the "
                         "exact build and adapter covers the scope; then explicit preference, then provider id"),
            "notice": "a selection is not evidence and grants no scientific authority",
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _capability_reasons(requirement: SolverRequirement, status: ProviderStatus) -> list[str]:
    cap = status.capability
    reasons = []
    missing = sorted(set(requirement.physics) - set(cap.physics))
    if missing:
        reasons.append(f"physics {missing} not declared")
    if requirement.dimension is not None and requirement.dimension not in cap.dimensions:
        reasons.append(f"dimension {requirement.dimension} not in {list(cap.dimensions)}")
    if requirement.time_mode is not None and requirement.time_mode not in cap.time_modes:
        reasons.append(f"time mode {requirement.time_mode!r} not in {list(cap.time_modes)}")
    ranks = sorted(set(requirement.output_ranks) - set(cap.output_ranks))
    if ranks:
        reasons.append(f"output ranks {ranks} not declared")
    if requirement.mesh_requirement is not None and cap.mesh_requirement != requirement.mesh_requirement:
        reasons.append(f"mesh requirement {cap.mesh_requirement!r}, needed {requirement.mesh_requirement!r}")
    if requirement.restart and not cap.restart:
        reasons.append("restart not supported")
    if requirement.checkpoint and not cap.checkpoint:
        reasons.append("checkpoint not supported")
    return reasons


def select_solvers(
    requirement: SolverRequirement,
    statuses: Iterable[ProviderStatus],
    *,
    qualifications: Iterable[ProviderQualification],
    routes: Iterable[Any],
    ledger: Any,
    adapters: Mapping[str, tuple[str, str]],
    preference: tuple[str, ...] = (),
) -> SolverSelection:
    """Every provider's verdict for ``requirement``, and the deterministic order of the eligible ones."""
    if not isinstance(requirement, SolverRequirement):
        raise InvalidScientificProblem("select_solvers takes a SolverRequirement")
    admitted = admitted_qualifications(tuple(qualifications), tuple(routes), ledger)
    entries = []
    for status in sorted(statuses, key=lambda s: s.capability.provider_id):
        pid = status.capability.provider_id
        reasons: list[str] = []
        build = (status.version, status.digest)
        if not status.available:
            reasons.append(f"unavailable: {status.reason or status.availability.value}")
        reasons += _capability_reasons(requirement, status)
        adapter = adapters.get(pid)
        covering = [
            q for q in admitted
            if q.provider_id == pid and (q.provider_version, q.provider_digest) == build
            and adapter is not None and (q.adapter_id, q.adapter_version) == tuple(adapter)
            and set(requirement.qualification_scope) <= set(q.scope)
        ]
        if adapter is None:
            reasons.append("no adapter is named for this provider; a qualification is of a provider AND its adapter")
        elif not covering:
            reasons.append(f"no admitted qualification of build {build[0]!r} through adapter {tuple(adapter)} "
                           f"covers scope {list(requirement.qualification_scope)}")
        entries.append(SelectionEntry(pid, not reasons, tuple(reasons), build,
                                      covering[0].route if covering else ""))
    unknown = sorted(set(preference) - {e.provider_id for e in entries})
    if unknown:
        raise InvalidScientificProblem(f"preference names providers that were not assessed: {unknown}")
    rank = {pid: k for k, pid in enumerate(preference)}
    order = tuple(sorted((e.provider_id for e in entries if e.eligible),
                         key=lambda pid: (rank.get(pid, len(rank)), pid)))
    return SolverSelection(requirement, tuple(entries), order, tuple(preference))


__all__ = ["SelectionEntry", "SolverRequirement", "SolverSelection", "select_solvers"]
