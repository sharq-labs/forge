"""Macro-step checkpoint: everything a continuation needs, bound by digest.

A checkpoint is produced only after a macro step is ACCEPTED; a refused step
never replaces the previous valid checkpoint.  Resume from a checkpoint is
refused unless every fast participant DECLARED its checkpoint state complete
(:class:`~engcore.coupling.adapters.ParticipantStateContract`); a resumed run
that matches the uninterrupted one proves reproducibility only.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping

from ..coupling.adapters import ParticipantStateContract
from ..scenarios.timeline import TimePoint, canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics.receipts import StateVariableValue
from ._common import fraction_text, parse_fraction

CHECKPOINT_SCHEMA = "engcore.multiscale.macro_checkpoint/1"

State = Mapping[str, Mapping[str, StateVariableValue]]


def state_to_list(state: State) -> list[dict[str, Any]]:
    return [{"participant_id": pid, "value": state[pid][k].to_dict()} for pid in sorted(state) for k in sorted(state[pid])]


def state_from_list(items: list[Mapping[str, Any]]) -> dict[str, dict[str, StateVariableValue]]:
    out: dict[str, dict[str, StateVariableValue]] = {}
    for item in items:
        v = StateVariableValue.from_dict(item["value"])
        out.setdefault(item["participant_id"], {})[v.variable_id] = v
    return out


@dataclass(frozen=True)
class MacroCheckpoint:
    checkpoint_id: str
    run_id: str
    step_index: int
    at: TimePoint
    identities: Mapping[str, str]
    slow_state: State
    fast_state: State
    contracts: tuple[ParticipantStateContract, ...]
    material_state_digests: tuple[str, ...]
    environment_context_digest: str
    representative: tuple[Mapping[str, Any], ...]
    aggregation_digests: tuple[str, ...]
    degradation_digests: tuple[str, ...]
    chain_digest: str
    selected_seconds: Fraction | None
    accounting: Mapping[str, Any]

    @property
    def resumable(self) -> bool:
        return all(c.restartable for c in self.contracts)

    @property
    def resumable_reason(self) -> str:
        missing = sorted(c.participant_id for c in self.contracts if not c.restartable)
        return "" if not missing else (f"checkpoint-completeness of fast participants {missing} is NOT_ESTABLISHED; "
                                       "resume and deterministic replay are refused")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CHECKPOINT_SCHEMA, "classification": "execution_checkpoint_not_evidence",
                "checkpoint_id": self.checkpoint_id, "run_id": self.run_id, "step_index": self.step_index,
                "at": self.at.to_dict(), "identities": dict(sorted(self.identities.items())),
                "slow_state": state_to_list(self.slow_state), "fast_state": state_to_list(self.fast_state),
                "contracts": [c.to_dict() for c in sorted(self.contracts, key=lambda c: c.participant_id)],
                "material_state_digests": list(self.material_state_digests),
                "environment_context_digest": self.environment_context_digest,
                "representative": [dict(r) for r in self.representative], "aggregation_digests": list(self.aggregation_digests),
                "degradation_digests": list(self.degradation_digests), "chain_digest": self.chain_digest,
                "selected_seconds": None if self.selected_seconds is None else fraction_text(self.selected_seconds),
                "accounting": dict(sorted(self.accounting.items())), "resumable": self.resumable,
                "resumable_reason": self.resumable_reason}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def serialize(self) -> dict[str, Any]:
        """A self-verifying payload: the body plus its digest."""
        return {"checkpoint": self.to_dict(), "digest": self.digest}

    @classmethod
    def deserialize(cls, payload: Mapping[str, Any]) -> "MacroCheckpoint":
        if set(payload) != {"checkpoint", "digest"}:
            raise InvalidScientificProblem("checkpoint payload must be {'checkpoint', 'digest'}")
        body = payload["checkpoint"]
        if body.get("schema") != CHECKPOINT_SCHEMA or body.get("classification") != "execution_checkpoint_not_evidence":
            raise InvalidScientificProblem("not a macro checkpoint payload")
        cp = cls(body["checkpoint_id"], body["run_id"], int(body["step_index"]), TimePoint.from_dict(body["at"]),
                 dict(body["identities"]), state_from_list(body["slow_state"]), state_from_list(body["fast_state"]),
                 tuple(ParticipantStateContract.from_dict(c) for c in body["contracts"]), tuple(body["material_state_digests"]),
                 body["environment_context_digest"], tuple(body["representative"]), tuple(body["aggregation_digests"]),
                 tuple(body["degradation_digests"]), body["chain_digest"],
                 None if body["selected_seconds"] is None else parse_fraction(body["selected_seconds"], "selected_seconds"),
                 dict(body["accounting"]))
        if cp.to_dict() != body:
            raise InvalidScientificProblem("checkpoint body does not re-serialize identically; refusing a mutated payload")
        if cp.digest != payload["digest"]:
            raise InvalidScientificProblem("checkpoint digest mismatch; the payload was altered")
        return cp
