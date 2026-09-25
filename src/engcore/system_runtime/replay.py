"""Replay and resume comparison, with three claims kept apart.

* **identity replay**: the same request, plan and per-node execution identities (authority identity,
  input digests, state) were reproduced.  This says the SAME computation was set up again.
* **numerical reproducibility**: the outputs agree within a declared tolerance.  Whether that can
  be exact is a property of each authority (``deterministic``); the comparison never promises
  bitwise equality for one that does not.
* **scientific validation**: never assessed here.  Reproducing a run says nothing about whether the
  run is right.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..scientific.errors import InvalidScientificProblem
from .records import NodeStatus
from .result import SystemRunResult

CLASSIFICATION = "reproducibility_not_validation"


@dataclass(frozen=True)
class OutputDifference:
    node_id: str
    output: str
    absolute: float
    relative: float
    within_tolerance: bool

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "output": self.output, "absolute": self.absolute, "relative": self.relative,
                "within_tolerance": self.within_tolerance}


@dataclass(frozen=True)
class RunComparison:
    identity_replay: bool
    identity_differences: tuple[str, ...]
    bitwise_identical: bool
    numerical_reproducibility: bool
    differences: tuple[OutputDifference, ...]
    non_deterministic_nodes: tuple[str, ...]
    scientific_validation: str = "not_assessed"
    classification: str = CLASSIFICATION

    def __post_init__(self) -> None:
        if self.classification != CLASSIFICATION or self.scientific_validation != "not_assessed":
            raise InvalidScientificProblem("a run comparison is reproducibility; it never assesses validation")

    def to_dict(self) -> dict[str, Any]:
        return {"classification": self.classification, "identity_replay": self.identity_replay,
                "identity_differences": list(self.identity_differences), "bitwise_identical": self.bitwise_identical,
                "numerical_reproducibility": self.numerical_reproducibility, "differences": [d.to_dict() for d in self.differences],
                "non_deterministic_nodes": list(self.non_deterministic_nodes), "scientific_validation": self.scientific_validation}


def compare_runs(a: SystemRunResult, b: SystemRunResult, *, rel_tol: float, abs_tol: float = 0.0,
                 non_deterministic_nodes: tuple[str, ...] = ()) -> RunComparison:
    """Compare two runs of the same request.  Tolerances are declared by the caller, never defaulted."""
    if rel_tol < 0 or abs_tol < 0:
        raise InvalidScientificProblem("tolerances must be non-negative and declared")
    ids: list[str] = []
    if a.request_digest != b.request_digest:
        ids.append("request digest")
    if a.plan_digest != b.plan_digest:
        ids.append("plan digest")
    ra, rb = {r.node_id: r for r in a.node_receipts}, {r.node_id: r for r in b.node_receipts}
    for node_id in sorted(set(ra) | set(rb)):
        x, y = ra.get(node_id), rb.get(node_id)
        if x is None or y is None:
            ids.append(f"{node_id}: present in one run only")
            continue
        if x.status is not y.status:
            ids.append(f"{node_id}: status {x.status.value} vs {y.status.value}")
        # execution identity binds authority identity + input digests + state; the state chain differs across runs only by design
        if x.status is NodeStatus.SUCCEEDED and y.status is NodeStatus.SUCCEEDED and x.authority_identity_digest != y.authority_identity_digest:
            ids.append(f"{node_id}: authority identity")
    diffs: list[OutputDifference] = []
    for node_id in sorted(set(a.node_outputs) & set(b.node_outputs)):
        for name in sorted(set(a.node_outputs[node_id]) & set(b.node_outputs[node_id])):
            va, vb = a.node_outputs[node_id][name].value, b.node_outputs[node_id][name].value
            xa = float(va.magnitude)
            xb = float(vb.to(va.units).magnitude)
            absolute = abs(xa - xb)
            scale = max(abs(xa), abs(xb))
            relative = absolute / scale if scale else 0.0
            diffs.append(OutputDifference(node_id, name, absolute, relative, absolute <= abs_tol or relative <= rel_tol))
    same_outputs = set(a.node_outputs) == set(b.node_outputs) and all(set(a.node_outputs[n]) == set(b.node_outputs[n]) for n in a.node_outputs)
    bitwise = same_outputs and all(a.node_outputs[n][k].digest == b.node_outputs[n][k].digest for n in a.node_outputs for k in a.node_outputs[n])
    return RunComparison(not ids, tuple(ids), bitwise, same_outputs and all(d.within_tolerance for d in diffs), tuple(diffs), tuple(sorted(non_deterministic_nodes)))
