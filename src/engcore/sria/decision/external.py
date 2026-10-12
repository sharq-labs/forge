"""External suggestions enter the canonical planner as proposals, never as decisions.

The canonical experiment planner is this package: generators label candidates
with an :class:`~.actions.ActionFamily` (EXPLORE, CHARACTERIZE, DISCRIMINATE,
OPTIMIZE, REDUCE_UNCERTAINTY, VALIDATE) and ONE utility engine scores them.
External numerical libraries (Bayesian optimisation, symbolic regression,
UQ toolkits) and language models may *suggest* where to look.  A suggestion:

* becomes an :class:`~.actions.ActionProposal` whose assumptions name the
  suggesting engine and version -- provenance, not authority;
* never carries a score into the utility engine (an acquisition value is
  recorded as the engine's own number, not FORGE's expected utility);
* from a language model may not claim an evidence level, a status or an
  applicability decision -- it is refused if it tries.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from .actions import ActionFamily, ActionProposal
from .hypotheses import ProposerKind

EXTERNAL_SUGGESTION_SCHEMA = "engcore.sria.decision.external_suggestion/1"

#: keys a suggestion may not carry: deciding these is FORGE's authority, never a proposer's
AUTHORITY_KEYS = frozenset({"status", "verdict", "verdicts", "evidence", "evidence_level", "validation", "validation_level",
                            "validated", "applicable", "applicability", "admitted", "admission", "supported", "support",
                            "uncertainty", "uncertainty_quantified", "measurement", "measurements", "novel", "novelty", "qualified"})


def _keys(obj: Any) -> set[str]:
    """Every key at any depth (a nested 'status' is still a status claim)."""
    out: set[str] = set()
    if isinstance(obj, Mapping):
        for k, val in obj.items():
            out.add(str(k).lower())
            out |= _keys(val)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            out |= _keys(item)
    return out


class SuggestionRefused(ValueError):
    """A suggestion that tried to carry authority a proposer does not have."""


@dataclass(frozen=True)
class ExternalSuggestion:
    engine_kind: ProposerKind
    engine_id: str
    engine_version: str
    family: ActionFamily
    target_ref: str
    point: Mapping[str, Any]
    rationale: str
    acquisition_value: float | None = None   # the engine's own number (EI, UCB, ...); NOT a FORGE utility
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "engine_kind", ProposerKind(self.engine_kind))
        object.__setattr__(self, "family", ActionFamily(self.family))
        for label in ("engine_id", "engine_version", "target_ref", "rationale"):
            if not str(getattr(self, label)).strip():
                raise SuggestionRefused(f"an external suggestion names its {label}")
        if self.acquisition_value is not None and not math.isfinite(float(self.acquisition_value)):
            raise SuggestionRefused("an acquisition value is finite or absent")
        claimed = sorted(AUTHORITY_KEYS & (_keys(dict(self.point)) | _keys(dict(self.extra))))
        if claimed:
            raise SuggestionRefused(f"a suggestion from {self.engine_id!r} carries {claimed}: a proposer suggests where to look, "
                                    "it never decides status, evidence, applicability or uncertainty")
        object.__setattr__(self, "point", json.loads(json.dumps(dict(self.point), sort_keys=True)))
        object.__setattr__(self, "extra", json.loads(json.dumps(dict(self.extra), sort_keys=True)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": EXTERNAL_SUGGESTION_SCHEMA, "engine_kind": self.engine_kind.value, "engine_id": self.engine_id,
                "engine_version": self.engine_version, "family": self.family.value, "target_ref": self.target_ref,
                "point": dict(self.point), "rationale": self.rationale, "acquisition_value": self.acquisition_value,
                "extra": dict(self.extra)}

    @property
    def digest(self) -> str:
        """Content address: a replay reuses the stored suggestion, it never asks the engine again."""
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def proposal_from_suggestion(suggestion: ExternalSuggestion, *, expected_observable: str = "",
                             required_fidelity: str = "") -> ActionProposal:
    """The planner-side proposal for a suggestion.  Scoring stays with the utility engine."""
    if not isinstance(suggestion, ExternalSuggestion):
        raise SuggestionRefused("only an ExternalSuggestion becomes a proposal")
    return ActionProposal(
        family=suggestion.family, target_ref=suggestion.target_ref,
        rationale=f"{suggestion.engine_kind.value} {suggestion.engine_id} {suggestion.engine_version}: {suggestion.rationale}",
        assumptions=(f"suggested_by={suggestion.engine_kind.value}:{suggestion.engine_id}@{suggestion.engine_version}",
                     f"suggestion_digest={suggestion.digest}",
                     "the engine's acquisition value is its own number and is not FORGE expected utility"),
        required_fidelity=required_fidelity, expected_observable=expected_observable)


__all__ = ["AUTHORITY_KEYS", "EXTERNAL_SUGGESTION_SCHEMA", "ExternalSuggestion", "SuggestionRefused", "proposal_from_suggestion"]
