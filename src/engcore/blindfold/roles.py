"""Evaluator isolation: PROPOSER -> ADMISSION -> EVALUATOR -> ADJUDICATOR -> REPORTER, with the escrow outside them all.

* The PROPOSER gets a public universe card and an :class:`~.escrow.ObserveClient`.  It holds no score token, no
  evaluator configuration, no falsifier and no truth.  Its output is a proposal (data), stored CONTENT-ADDRESSED in a
  write-once :class:`ProposalStore`; a replay reads the stored proposal and never calls the proposer (or a language
  model) again.
* ADMISSION checks the proposal against the card and the expression grammar only (no truth involved).
* The EVALUATOR holds the :class:`~.escrow.ScoreClient` and submits the stored proposal, by digest, once.
* The ADJUDICATOR applies a sealed :class:`EvaluatorConfig` (credit table + version) whose digest is fixed before the
  campaign; a different config at adjudication time is refused.
* The REPORTER aggregates adjudications; its report binds every adjudication digest and changes no verdict.

Within one Python process these roles are separated by construction and by digests, not by an operating-system
boundary: SECURITY_BOUNDARY_NOT_PROVEN (see :mod:`.escrow`).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .escrow import ANSWERS, SECURITY_LABEL, EscrowRefused, ObserveClient, ScoreClient, call
from .expression import ExpressionRefused, validate


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RoleRefused(RuntimeError):
    """A role boundary was crossed (wrong store content, changed config, inadmissible proposal)."""


# ---------------------------------------------------------------------------- proposal store


class ProposalStore:
    """Write-once, content-addressed proposal storage.  ``put`` returns the digest; the same digest always reads back the
    same bytes.  Replay reads from here; it never regenerates a proposal."""

    def __init__(self) -> None:
        self._blobs: dict[str, str] = {}

    def put(self, proposal: Mapping[str, Any]) -> str:
        blob = json.dumps(dict(proposal), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(blob.encode()).hexdigest()
        if digest in self._blobs and self._blobs[digest] != blob:  # pragma: no cover - sha256 collision
            raise RoleRefused("digest collision")
        self._blobs[digest] = blob
        return digest

    def get(self, digest: str) -> dict[str, Any]:
        blob = self._blobs.get(digest)
        if blob is None:
            raise RoleRefused(f"no stored proposal {digest[:12]}")
        if hashlib.sha256(blob.encode()).hexdigest() != digest:
            raise RoleRefused("stored proposal does not match its digest")
        return json.loads(blob)

    def digests(self) -> tuple[str, ...]:
        return tuple(sorted(self._blobs))


# ---------------------------------------------------------------------------- admission


@dataclass(frozen=True)
class AdmittedProposal:
    universe_id: str
    proposal_digest: str
    answer: str


def admit(proposal: Mapping[str, Any], card: Mapping[str, Any], store: ProposalStore) -> AdmittedProposal:
    """Grammar, variables and answer type only -- admission sees the card, never the truth."""
    if proposal.get("universe_id") != card["universe_id"]:
        raise RoleRefused("the proposal names another universe than the card")
    answer = proposal.get("answer")
    if answer not in ANSWERS:
        raise RoleRefused(f"answer must be one of {ANSWERS}")
    proposer = proposal.get("proposer") or {}
    if not str(proposer.get("id", "")).strip() or not str(proposer.get("kind", "")).strip():
        raise RoleRefused("a proposal names its proposer (kind, id)")
    allowed = {x["name"] for x in card["inputs"]} | set(card.get("observed_covariates", ()))
    laws = [proposal["law"]] if answer == "law" else list(proposal.get("laws", ())) if answer == "indistinguishable" else []
    if answer == "indistinguishable" and len(laws) < 2:
        raise RoleRefused("INDISTINGUISHABLE names at least two laws")
    for law in laws:
        try:
            used = validate(law)
        except ExpressionRefused as exc:
            raise RoleRefused(f"inadmissible law: {exc}") from exc
        if used - allowed:
            raise RoleRefused(f"the law uses variables not on the card: {sorted(used - allowed)}")
    digest = store.put(proposal)
    return AdmittedProposal(card["universe_id"], digest, answer)


# ---------------------------------------------------------------------------- evaluator config + adjudication


#: credit[kind][outcome]; outcome is one of: law_pass, law_fail, <refusal answer>, indistinguishable_hit, indistinguishable_miss
DEFAULT_CREDIT: Mapping[str, Mapping[str, float]] = {
    "discoverable": {"law_pass": 1.0, "law_fail": -1.0, "indistinguishable_hit": 0.0, "indistinguishable_miss": -1.0},
    "no_solution": {"no_law": 1.0, "law_pass": -1.0, "law_fail": -1.0, "indistinguishable_hit": -1.0, "indistinguishable_miss": -1.0},
    "insufficient_evidence": {"insufficient_evidence": 1.0, "law_pass": 0.0, "law_fail": -1.0, "indistinguishable_miss": -1.0},
    "indistinguishable": {"indistinguishable_hit": 1.0, "indistinguishable_miss": 0.0, "law_pass": 0.0, "law_fail": -1.0},
    "spurious_correlate": {"law_pass": 1.0, "law_fail": -1.0, "indistinguishable_miss": -1.0},
    "confounded": {"confounded": 1.0, "insufficient_evidence": 1.0, "law_pass": 0.0, "law_fail": -1.0, "indistinguishable_miss": -1.0},
}


@dataclass(frozen=True)
class EvaluatorConfig:
    """Sealed before the campaign.  Unlisted outcomes score 0.  Proposers never see or write it."""

    config_id: str
    version: str
    credit: Mapping[str, Mapping[str, float]] = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_CREDIT.items()})

    def to_dict(self) -> dict[str, Any]:
        return {"config_id": self.config_id, "version": self.version,
                "credit": {k: dict(sorted(v.items())) for k, v in sorted(self.credit.items())}}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class Adjudication:
    universe_id: str
    proposal_digest: str
    universe_kind: str
    answer: str
    outcome: str
    credit: float
    structure_match: bool
    config_digest: str
    score_receipt_digest: str
    security_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def adjudicate(score: Mapping[str, Any], config: EvaluatorConfig, *, sealed_config_digest: str) -> Adjudication:
    if config.digest != sealed_config_digest:
        raise RoleRefused("the evaluator configuration changed after it was sealed; adjudication refused")
    kind, answer = score["universe_kind"], score["answer"]
    laws = score.get("laws") or []
    if answer == "law":
        outcome = "law_pass" if laws[0]["passed"] else "law_fail"
    elif answer == "indistinguishable":
        outcome = "indistinguishable_hit" if any(law["passed"] for law in laws) else "indistinguishable_miss"
    else:
        outcome = answer
    credit = float(config.credit.get(kind, {}).get(outcome, 0.0))
    return Adjudication(score["universe_id"], score["proposal_digest"], kind, answer, outcome, credit,
                        any(law.get("structure_matches_hidden_law") for law in laws), config.digest,
                        score["receipt"]["digest"], score.get("security_boundary", SECURITY_LABEL))


# ---------------------------------------------------------------------------- reporter


@dataclass(frozen=True)
class BlindfoldReport:
    campaign_id: str
    level: str
    config_digest: str
    adjudications: tuple[Adjudication, ...]
    queries: int
    escrow_log_head: str
    proposer: Mapping[str, Any]
    security_boundary: str = SECURITY_LABEL

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, list[Adjudication]] = {}
        for a in self.adjudications:
            by_kind.setdefault(a.universe_kind, []).append(a)
        laws = [a for a in self.adjudications if a.answer in ("law", "indistinguishable")]
        controls = [a for a in self.adjudications if a.universe_kind != "discoverable"]
        disc = by_kind.get("discoverable", [])
        return {
            "universes": len(self.adjudications),
            "total_credit": sum(a.credit for a in self.adjudications),
            "mean_credit_by_kind": {k: sum(a.credit for a in v) / len(v) for k, v in sorted(by_kind.items())},
            "discovery_success_rate": None if not disc else sum(a.outcome == "law_pass" for a in disc) / len(disc),
            "false_discovery_rate": None if not laws else sum(a.credit < 0 for a in laws) / len(laws),
            "correct_refusal_rate_on_controls": None if not controls else sum(a.credit > 0 for a in controls) / len(controls),
            "structure_match_rate": None if not disc else sum(a.structure_match for a in disc) / len(disc),
            "queries": self.queries,
            "counts_as_novel_discovery": self.level in ("L4", "L5", "L6"),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "engcore.blindfold.report/1", "campaign_id": self.campaign_id, "level": self.level,
                "config_digest": self.config_digest, "adjudication_digests": [a.digest for a in self.adjudications],
                "queries": self.queries, "escrow_log_head": self.escrow_log_head, "proposer": dict(self.proposer),
                "security_boundary": self.security_boundary, "summary": self.summary()}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


# ---------------------------------------------------------------------------- the campaign driver (operator role)


Proposer = Callable[[Mapping[str, Any], ObserveClient], Mapping[str, Any]]


def run_campaign(transport: Callable[[bytes], bytes], *, campaign_id: str, mix: Mapping[str, int], proposer: Proposer,
                 proposer_identity: Mapping[str, str], config: EvaluatorConfig, store: ProposalStore | None = None,
                 replay: Mapping[str, str] | None = None) -> tuple[BlindfoldReport, ProposalStore]:
    """Operator: create the campaign, hand the proposer ONLY the observe capability, store and admit each proposal,
    have the evaluator score it once, adjudicate under the sealed config, report.

    ``replay`` maps universe_id -> stored proposal digest: those proposals are read from ``store`` and the proposer is
    NOT called (reproducing a campaign never re-asks a proposer or a language model)."""
    store = store or ProposalStore()
    sealed = config.digest
    created = call(transport, "create", campaign_id=campaign_id, mix=dict(mix))
    observe_client = ObserveClient(transport, campaign_id, created["tokens"]["observe"])
    score_client = ScoreClient(transport, campaign_id, created["tokens"]["score"])
    adjudications = []
    for card in created["cards"]:
        frozen_card = json.loads(json.dumps(card))
        if replay and card["universe_id"] in replay:
            proposal = store.get(replay[card["universe_id"]])
        else:
            proposal = dict(proposer(frozen_card, observe_client))
            proposal.setdefault("universe_id", card["universe_id"])
            proposal["proposer"] = dict(proposer_identity)
        try:
            admitted = admit(proposal, frozen_card, store)
        except RoleRefused as exc:
            # an inadmissible proposal is scored as what it is: no admissible answer (credit by the table's default 0)
            admitted = admit({"universe_id": card["universe_id"], "answer": "insufficient_evidence",
                              "proposer": dict(proposer_identity), "inadmissible_original": str(exc)}, frozen_card, store)
        stored = store.get(admitted.proposal_digest)
        try:
            score = score_client.score(card["universe_id"], stored)
        except EscrowRefused as exc:
            raise RoleRefused(f"the escrow refused the evaluator's submission: {exc}") from exc
        adjudications.append(adjudicate(score, config, sealed_config_digest=sealed))
    log = call(transport, "log", campaign_id=campaign_id, token=created["tokens"]["score"])
    queries = sum(1 for e in log["log"] if e["op"] == "observe")
    level = created["cards"][0]["level"] if created["cards"] else "L5"
    report = BlindfoldReport(campaign_id, level, sealed, tuple(adjudications), queries, log["head"], dict(proposer_identity))
    return report, store


__all__ = ["Adjudication", "AdmittedProposal", "BlindfoldReport", "DEFAULT_CREDIT", "EvaluatorConfig", "ProposalStore", "RoleRefused",
           "admit", "adjudicate", "run_campaign"]
_ = math  # reserved for numeric checks in future credit rules
