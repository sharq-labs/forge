"""MindStepRecord (M-9) and MindReplay (M-10).

Every step of the loop is one content-addressed record chained to the previous one.  It binds:

* the PRIOR state (digest of the read-only state view before the step);
* the candidate set and the selection (with its utility components and the weights it used);
* the falsifier role's proposals;
* the PRE-RESULT predictions of every tested rival at the selected setting and the falsifiers sealed on them -- their
  digest (``prediction_seal_digest``) is fixed before the observation exists;
* the execution (query reference, settings, the digest of the observation as returned);
* the evidence (the release's content digest, exposure sequence and the uncertainty basis);
* the falsifier verdicts the release produced;
* the POSTERIOR state (digest of the state view after the step);
* the post-result score of the sealed prediction (kept apart from any final credit).

Replay re-executes the same Mind on the recorded observations (it never queries a world) and must reproduce every
step record digest and the conclusion digest exactly; any divergence names the first step that differs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

STEP_SCHEMA = "forge.mind.minimal.step_record/1"
TRACE_SCHEMA = "forge.mind.minimal.trace/1"
GENESIS = "0" * 64


def digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class ReplayRefused(RuntimeError):
    """The replayed Mind asked for an experiment the recorded trace did not run (the reasoning path diverged)."""


def step_record(**fields: Any) -> dict[str, Any]:
    body = {"schema": STEP_SCHEMA, **fields}
    return {**body, "record_digest": digest(body)}


def verify_chain(steps: Sequence[Mapping[str, Any]]) -> list[str]:
    problems, previous = [], GENESIS
    for i, s in enumerate(steps):
        body = {k: v for k, v in s.items() if k != "record_digest"}
        if s.get("schema") != STEP_SCHEMA:
            problems.append(f"step {i}: schema {s.get('schema')!r}")
        if digest(body) != s.get("record_digest"):
            problems.append(f"step {i}: record digest does not match its content")
        if s.get("previous") != previous:
            problems.append(f"step {i}: not chained to the previous record")
        previous = s.get("record_digest")
    return problems


@dataclass
class ReplayObserver:
    """Feeds the recorded observations back in order; refuses a query the trace did not make."""

    executions: Sequence[Mapping[str, Any]]
    observations: Sequence[Mapping[str, float]]
    refusal: Mapping[str, Any] | None = None
    calls: int = 0

    def __call__(self, settings: Mapping[str, float], query_ref: str) -> Mapping[str, float]:
        if self.calls >= len(self.observations):
            if self.refusal is not None and int(self.refusal["query_index"]) == self.calls:
                from .runner import ObservationRefused  # noqa: PLC0415 - the world's recorded refusal, replayed as recorded
                raise ObservationRefused(str(self.refusal["message"]), budget=bool(self.refusal["budget"]))
            raise ReplayRefused(f"the replay asked for query {self.calls}, the trace ran {len(self.observations)}")
        rec = self.executions[self.calls]
        if rec["query_ref"] != query_ref or rec["settings"] != {k: float(f"{float(v):.12g}") for k, v in sorted(settings.items())}:
            raise ReplayRefused(f"step {self.calls}: the replay chose {query_ref}, the trace ran {rec['query_ref']}")
        obs = self.observations[self.calls]
        self.calls += 1
        return obs


@dataclass(frozen=True)
class ReplayReport:
    status: str                       # VERIFIED | DIVERGED | CHAIN_BROKEN
    steps: int
    first_divergence: int | None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "steps": self.steps, "first_divergence": self.first_divergence, "detail": self.detail}


def compare(original: Mapping[str, Any], replayed: Mapping[str, Any]) -> ReplayReport:
    a, b = original["steps"], replayed["steps"]
    problems = verify_chain(a)
    if problems:
        return ReplayReport("CHAIN_BROKEN", len(a), None, "; ".join(problems[:3]))
    for i, (x, y) in enumerate(zip(a, b)):
        if x["record_digest"] != y["record_digest"]:
            return ReplayReport("DIVERGED", len(a), i, "step record digests differ")
    if len(a) != len(b):
        return ReplayReport("DIVERGED", len(a), min(len(a), len(b)), "different number of steps")
    if digest(original["conclusion"]) != digest(replayed["conclusion"]):
        return ReplayReport("DIVERGED", len(a), len(a), "the conclusion differs")
    return ReplayReport("VERIFIED", len(a), None)


__all__ = ["GENESIS", "ReplayObserver", "ReplayRefused", "ReplayReport", "STEP_SCHEMA", "TRACE_SCHEMA", "compare", "digest",
           "step_record", "verify_chain"]
