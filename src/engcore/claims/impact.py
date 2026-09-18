"""Phase 9 -- decision dependency and impact: which decisions rest on what, and what a change touches.

This is an *index*, not a provenance system. Every node and edge is read off
identities an assessment record already carries -- the claim's identity
digest, the plan digest and run id, the capability digest, the models and
solvers the plan names (id@version), the trusted oracles' pinned digests, the
evidence record hash, the decision context's policy profile digest, the
charter and the decision id. Nothing is added to a record to build it, so the
graph can be rebuilt from any archive of records at any time.

    claim -> plan -> capability -> model@version / solver@version
                  -> oracle@digest -> evidence -> policy@digest -> decision

Impact analysis answers "if X changed, which assessments must be re-assessed?"
and reports them with the chain of identities that links each to X. It never
edits a historical record: an old decision stays what it was, and the report
says it now needs reassessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ._records import tagged_digest

_RECORD_TAG = "crafty.claims.assessment_record/1"
_IMPACT_TAG = "crafty.claims.impact/1"


class NodeKind(str, Enum):
    ASSESSMENT = "assessment"
    CLAIM = "claim"
    PLAN = "plan"
    CAPABILITY = "capability"
    MODEL = "model"
    SOLVER = "solver"
    ORACLE = "oracle"
    EVIDENCE = "evidence"
    POLICY = "policy"
    DECISION = "decision"
    TRUST_REGISTRY = "trust_registry"
    EXTERNAL_RECORD = "external_record"


def node(kind: NodeKind, key: str) -> str:
    return f"{kind.value}:{key}"


def record_digest(record: Mapping[str, Any]) -> str:
    """The identity of one assessment record, exactly as stored."""
    return tagged_digest(_RECORD_TAG, record)


def _edges_of(record: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """(from, relation, to) for one record. Every endpoint is an identity the record carries."""
    rid = node(NodeKind.ASSESSMENT, record_digest(record))
    edges: list[tuple[str, str, str]] = []
    compilation = record.get("compilation") or {}
    identity = compilation.get("claim_identity")
    if identity:
        claim = node(NodeKind.CLAIM, identity)
        edges.append((rid, "assesses", claim))
    decision_id = ((record.get("claim") or {}).get("decision") or {}).get("decision_id")
    plan = record.get("plan")
    if plan is not None:
        content = plan["content"]
        p = node(NodeKind.PLAN, content["core_digest"])
        edges.append((rid, "executed", p))
        cap = content["capability"]
        c = node(NodeKind.CAPABILITY, f"{cap['capability_id']}@{cap['version']}#{cap['digest']}")
        edges.append((p, "runs", c))
        for model in content["models"]:
            edges.append((c, "uses_model", node(NodeKind.MODEL, f"{model['model_id']}@{model['version']}")))
        for solver in content["solvers"]:
            edges.append((c, "uses_solver", node(NodeKind.SOLVER, f"{solver['solver_id']}@{solver['version']}")))
        if decision_id:
            edges.append((rid, "decides", node(NodeKind.DECISION, f"{decision_id}#charter:{content['decision']['charter_digest']}")))
    for match in record.get("external_evidence") or []:
        edges.append((rid, "consulted_oracle", node(NodeKind.ORACLE, f"{match['oracle_id']}@{match['version']}#{match['trusted_digest']}")))
    for item in record.get("external_evidence_assessments") or []:
        edges.append((rid, "ingested", node(NodeKind.EXTERNAL_RECORD, f"{item['source_class']}:{item['record_digest']}")))
    if record.get("external_trust_registry"):
        edges.append((rid, "judged_under", node(NodeKind.TRUST_REGISTRY, record["external_trust_registry"])))
    evidence = record.get("evidence")
    if evidence is not None:
        edges.append((rid, "rests_on", node(NodeKind.EVIDENCE, evidence["record_hash"])))
    policy = record.get("policy")
    if policy is not None:
        req = policy["requirement"]
        edges.append((rid, "under_policy", node(NodeKind.POLICY, f"{req['profile_id']}@{req['profile_version']}#{req['profile_digest']}")))
    return edges


@dataclass(frozen=True)
class AssessmentSummary:
    digest: str
    claim_identity: str | None
    decision_id: str | None
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {"assessment": self.digest, "claim_identity": self.claim_identity, "decision_id": self.decision_id, "verdict": self.verdict}


class DecisionGraph:
    """A queryable dependency index over a set of assessment records."""

    def __init__(self, records: Iterable[Mapping[str, Any]]) -> None:
        self._summaries: dict[str, AssessmentSummary] = {}
        self._edges: dict[str, set[tuple[str, str]]] = {}
        self._reverse: dict[str, set[tuple[str, str]]] = {}
        for record in records:
            digest = record_digest(record)
            self._summaries[digest] = AssessmentSummary(
                digest, (record.get("compilation") or {}).get("claim_identity"),
                ((record.get("claim") or {}).get("decision") or {}).get("decision_id"), str(record.get("verdict")),
            )
            for a, rel, b in _edges_of(record):
                self._edges.setdefault(a, set()).add((rel, b))
                self._reverse.setdefault(b, set()).add((rel, a))

    @property
    def nodes(self) -> frozenset[str]:
        return frozenset(self._edges) | frozenset(self._reverse)

    def edges(self) -> list[tuple[str, str, str]]:
        return sorted((a, rel, b) for a, outs in self._edges.items() for rel, b in outs)

    def _dependents(self, target: str) -> dict[str, tuple[str, ...]]:
        """Assessments that reach ``target``, each with one identity chain (breadth-first, deterministic)."""
        found: dict[str, tuple[str, ...]] = {}
        frontier = [(target, (target,))]
        seen = {target}
        while frontier:
            nxt = []
            for current, chain in sorted(frontier):
                for rel, source in sorted(self._reverse.get(current, ())):
                    if source in seen:
                        continue
                    seen.add(source)
                    path = (source, rel) + chain
                    if source.startswith(NodeKind.ASSESSMENT.value + ":"):
                        found[source.split(":", 1)[1]] = path
                    nxt.append((source, path))
            frontier = nxt
        return found

    def _matching(self, kind: NodeKind, prefix: str) -> list[str]:
        head = node(kind, prefix)
        return sorted(n for n in self.nodes if n == head or n.startswith(head + "@") or n.startswith(head + "#"))

    def dependents_of(self, kind: NodeKind, key: str) -> dict[str, tuple[str, ...]]:
        """Every assessment depending on any node of ``kind`` whose identity is ``key`` or starts ``key@``/``key#``."""
        out: dict[str, tuple[str, ...]] = {}
        for target in self._matching(kind, key):
            for digest, chain in self._dependents(target).items():
                out.setdefault(digest, chain)
        return out

    def decisions_depending_on_model(self, model_id: str, version: str | None = None) -> list[AssessmentSummary]:
        key = model_id if version is None else f"{model_id}@{version}"
        return [self._summaries[d] for d in sorted(self.dependents_of(NodeKind.MODEL, key))]

    def assessments_depending_on_oracle(self, oracle_id: str, version: str | None = None) -> list[AssessmentSummary]:
        key = oracle_id if version is None else f"{oracle_id}@{version}"
        return [self._summaries[d] for d in sorted(self.dependents_of(NodeKind.ORACLE, key))]

    def decisions_using_policy(self, profile_id: str, version: str | None = None) -> list[AssessmentSummary]:
        key = profile_id if version is None else f"{profile_id}@{version}"
        return [self._summaries[d] for d in sorted(self.dependents_of(NodeKind.POLICY, key))]

    def summary(self, digest: str) -> AssessmentSummary:
        return self._summaries[digest]


class ChangeKind(str, Enum):
    MODEL = "model"
    SOLVER = "solver"
    CAPABILITY = "capability"
    ORACLE = "oracle"
    POLICY = "policy"
    TRUST_REGISTRY = "trust_registry"


_NODE_OF = {
    ChangeKind.MODEL: NodeKind.MODEL, ChangeKind.SOLVER: NodeKind.SOLVER, ChangeKind.CAPABILITY: NodeKind.CAPABILITY,
    ChangeKind.ORACLE: NodeKind.ORACLE, ChangeKind.POLICY: NodeKind.POLICY, ChangeKind.TRUST_REGISTRY: NodeKind.TRUST_REGISTRY,
}


@dataclass(frozen=True)
class Change:
    """Something that changed: a model version, an oracle's pin, a policy profile, ..."""

    kind: ChangeKind
    key: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "key": self.key, "detail": self.detail}


@dataclass(frozen=True)
class ImpactReport:
    changes: tuple[Change, ...]
    affected: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "requires_reassessment": [dict(a) for a in self.affected],
            "notice": "historical decisions are not modified; each listed assessment needs reassessment under the change",
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_IMPACT_TAG, self.to_dict())


def impact_of(graph: DecisionGraph, changes: Iterable[Change]) -> ImpactReport:
    changes = tuple(changes)
    affected: dict[str, dict[str, Any]] = {}
    for change in changes:
        for digest, chain in graph.dependents_of(_NODE_OF[change.kind], change.key).items():
            entry = affected.setdefault(digest, {**graph.summary(digest).to_dict(), "because": []})
            entry["because"].append({"change": change.to_dict(), "chain": list(chain)})
    return ImpactReport(changes, tuple(affected[d] for d in sorted(affected)))


def detect_changes(records: Iterable[Mapping[str, Any]], registry: Any, *, policy_profiles: Mapping[str, Any] | None = None) -> tuple[Change, ...]:
    """What in today's registry (and built-in policy profiles) differs from what the records were assessed against."""
    from .policy import BUILTIN_PROFILES

    profiles = BUILTIN_PROFILES if policy_profiles is None else policy_profiles
    changes: dict[tuple, Change] = {}
    for record in records:
        plan = record.get("plan")
        if plan is not None:
            cap = plan["content"]["capability"]
            if cap["capability_id"] not in registry:
                changes[(ChangeKind.CAPABILITY, cap["capability_id"])] = Change(ChangeKind.CAPABILITY, cap["capability_id"], "no longer registered")
            else:
                now = registry.get(cap["capability_id"])
                if now.digest != cap["digest"]:
                    changes[(ChangeKind.CAPABILITY, cap["capability_id"])] = Change(
                        ChangeKind.CAPABILITY, f"{cap['capability_id']}@{cap['version']}#{cap['digest']}",
                        f"declaration digest is now {now.digest[:16]} (version {now.version})")
                    current = {(m.model_id, m.version) for m in now.models}
                    for m in plan["content"]["models"]:
                        if (m["model_id"], m["version"]) not in current:
                            changes[(ChangeKind.MODEL, m["model_id"], m["version"])] = Change(
                                ChangeKind.MODEL, f"{m['model_id']}@{m['version']}", "the registry no longer declares this model version")
                    solvers = {(s.solver_id, s.version) for s in now.solvers}
                    for s in plan["content"]["solvers"]:
                        if (s["solver_id"], s["version"]) not in solvers:
                            changes[(ChangeKind.SOLVER, s["solver_id"], s["version"])] = Change(
                                ChangeKind.SOLVER, f"{s['solver_id']}@{s['version']}", "the registry no longer declares this solver version")
        policy = record.get("policy")
        if policy is not None:
            req = policy["requirement"]
            current = profiles.get(req["profile_id"])
            if current is not None and current.digest != req["profile_digest"]:
                changes[(ChangeKind.POLICY, req["profile_id"], req["profile_digest"])] = Change(
                    ChangeKind.POLICY, f"{req['profile_id']}@{req['profile_version']}#{req['profile_digest']}",
                    f"the profile is now {current.version} ({current.digest[:16]})")
        for match in record.get("external_evidence") or []:
            if not match["trusted"]:
                changes[(ChangeKind.ORACLE, match["oracle_id"])] = Change(ChangeKind.ORACLE, f"{match['oracle_id']}@{match['version']}", "the oracle no longer reproduces its pin")
    return tuple(changes[k] for k in sorted(changes, key=str))


__all__ = [
    "AssessmentSummary",
    "Change",
    "ChangeKind",
    "DecisionGraph",
    "ImpactReport",
    "NodeKind",
    "detect_changes",
    "impact_of",
    "record_digest",
]
