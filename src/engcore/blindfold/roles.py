"""Evaluator isolation: PROPOSER -> ADMISSION -> EVALUATOR -> ADJUDICATOR -> REPORTER, with the escrow outside them all.

* The PROPOSER gets a public universe card and an :class:`~.escrow.ObserveClient` (whose API sends only observe; it is
  handed no score token, operator credential, evaluator configuration, falsifier or truth -- by construction, not
  isolation: in-process introspection reaches all of them).  Its output is a proposal (data), stored
  CONTENT-ADDRESSED in a write-once :class:`ProposalStore`; a replay reads the stored proposals -- for EVERY universe,
  or it is refused -- and never calls the proposer (or a language model) again.
* ADMISSION checks the proposal against the card and the expression grammar only (no truth involved).  An inadmissible
  proposal is stored as it was and scored as ``inadmissible`` (negative credit): it never becomes a refusal.
* The EVALUATOR holds the :class:`~.escrow.ScoreClient` and submits the stored proposal, by digest, once.
* The ADJUDICATOR applies a sealed :class:`EvaluatorConfig` (credit table + version) whose digest is fixed before the
  campaign; a different config at adjudication time is refused.
* The REPORTER aggregates adjudications, checks that every score receipt is a member of the escrow's hash chain (the
  chain's response digests are keyed, so this proves membership and order, not the content of a verdict), binds the
  transport label, and reports credit RELATIVE TO THE BEST CONSTANT ANSWER so a blanket refusal earns nothing, with
  discovery and control credit apart.

Within one Python process these roles are separated by construction and by digests, not by an operating-system
boundary: SECURITY_BOUNDARY_NOT_PROVEN (see :mod:`.escrow`).  While that holds, no report counts as novel discovery.
"""

from __future__ import annotations

import hashlib
import json
import reprlib
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from . import NOVEL_DISCOVERY_LEVELS
from .escrow import ANSWERS, SECURITY_LABEL, EscrowRefused, ObserveClient, OperatorClient, ScoreClient, verify_log
from .expression import ExpressionRefused, validate

REFUSALS = ("no_law", "insufficient_evidence", "confounded")
#: boundary labels that count as a PROVEN escrow boundary.  Empty: no transport here has an isolation attestation, so
#: no report can count as novel discovery.  (Allow-list -- never "anything but the unproven label".)
PROVEN_BOUNDARY_LABELS: frozenset[str] = frozenset()
_REPR = reprlib.Repr()
_REPR.maxlevel, _REPR.maxstring, _REPR.maxother, _REPR.maxlist, _REPR.maxdict = 6, 400, 400, 40, 40


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RoleRefused(RuntimeError):
    """A role boundary was crossed (wrong store content, changed config, inadmissible proposal, replay mismatch)."""


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

    def put_any(self, proposal: Any) -> str:
        """Store whatever a proposer returned, even when it is not a JSON object (as its repr): an inadmissible original
        is kept, never lost."""
        try:
            return self.put(dict(proposal))
        except Exception:  # noqa: BLE001 - whatever it was, a bounded record of it is kept
            try:
                text = _REPR.repr(proposal)[:4000]
            except Exception:  # noqa: BLE001
                text = f"<unrepresentable {type(proposal).__name__}>"
            return self.put({"unserializable_proposal_repr": text})

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
    """Grammar, variables and answer type only -- admission sees the card, never the truth.  Any malformed proposal is a
    :class:`RoleRefused`, never a crash."""
    try:
        return _admit(proposal, card, store)
    except RoleRefused:
        raise
    except Exception as exc:  # noqa: BLE001 - any malformed proposal is inadmissible, never a crash
        raise RoleRefused(f"malformed proposal: {type(exc).__name__}: {str(exc)[:200]}") from exc


def _admit(proposal: Mapping[str, Any], card: Mapping[str, Any], store: ProposalStore) -> AdmittedProposal:
    if not isinstance(proposal, Mapping):
        raise RoleRefused("a proposal is a JSON object")
    if proposal.get("universe_id") != card["universe_id"]:
        raise RoleRefused("the proposal names another universe than the card")
    answer = proposal.get("answer")
    if answer not in ANSWERS:
        raise RoleRefused(f"answer must be one of {ANSWERS}")
    proposer = proposal.get("proposer") or {}
    if not str(proposer.get("id", "")).strip() or not str(proposer.get("kind", "")).strip():
        raise RoleRefused("a proposal names its proposer (kind, id)")
    allowed = {x["name"] for x in card["inputs"]} | set(card.get("observed_covariates", ()))
    if answer == "law":
        if "law" not in proposal:
            raise RoleRefused("a LAW answer carries its law")
        laws = [proposal["law"]]
    elif answer == "indistinguishable":
        laws = list(proposal.get("laws", ()))
        if len(laws) != 2:
            raise RoleRefused("INDISTINGUISHABLE names exactly two laws (agreeing in the box, differing in the assessment region)")
    else:
        if "law" in proposal or "laws" in proposal:
            raise RoleRefused("a refusal carries no law")
        laws = []
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


#: credit[kind][outcome]; outcome is one of: law_pass, law_fail, <refusal answer>, indistinguishable_hit,
#: indistinguishable_miss, inadmissible.  Unlisted outcomes score 0.
DEFAULT_CREDIT: Mapping[str, Mapping[str, float]] = {
    "discoverable": {"law_pass": 1.0, "law_fail": -1.0, "indistinguishable_hit": -0.5, "indistinguishable_miss": -1.0,
                     "inadmissible": -1.0},
    "no_solution": {"no_law": 1.0, "law_pass": -1.0, "law_fail": -1.0, "indistinguishable_hit": -1.0, "indistinguishable_miss": -1.0,
                    "inadmissible": -1.0},
    "insufficient_evidence": {"insufficient_evidence": 1.0, "law_pass": 0.0, "law_fail": -1.0, "indistinguishable_hit": -1.0,
                              "indistinguishable_miss": -1.0, "inadmissible": -1.0},
    "indistinguishable": {"indistinguishable_hit": 1.0, "insufficient_evidence": 0.5, "law_pass": 0.0, "law_fail": -1.0,
                          "indistinguishable_miss": -1.0, "inadmissible": -1.0},
    "spurious_correlate": {"law_pass": 1.0, "law_fail": -1.0, "indistinguishable_hit": -0.5, "indistinguishable_miss": -1.0,
                           "inadmissible": -1.0},
    "confounded": {"confounded": 1.0, "law_pass": 1.0, "law_fail": -1.0, "indistinguishable_hit": -1.0, "indistinguishable_miss": -1.0,
                   "inadmissible": -1.0},
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

    def credit_for(self, kind: str, outcome: str) -> float:
        return float(self.credit.get(kind, {}).get(outcome, 0.0))


@dataclass(frozen=True)
class Adjudication:
    universe_id: str
    proposal_digest: str
    proposer_digest: str
    universe_kind: str
    answer: str
    outcome: str
    credit: float
    structure_match: bool
    config_digest: str
    score_receipt_digest: str
    security_boundary: str
    transport: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def outcome_key(self) -> tuple:
        """What a faithful replay must reproduce (receipts differ: a replay makes no observe queries)."""
        return (self.universe_id, self.proposal_digest, self.proposer_digest, self.universe_kind, self.outcome, self.credit)


def adjudicate(score: Mapping[str, Any], config: EvaluatorConfig, *, sealed_config_digest: str, proposer_digest: str) -> Adjudication:
    if config.digest != sealed_config_digest:
        raise RoleRefused("the evaluator configuration changed after it was sealed; adjudication refused")
    kind, answer = score["universe_kind"], score["answer"]
    laws = score.get("laws") or []
    structure_match = False
    if answer == "law":
        outcome = "law_pass" if laws[0]["passed"] else "law_fail"
        structure_match = bool(laws[0]["passed"] and laws[0].get("structure_matches_hidden_law"))
    elif answer == "indistinguishable":
        outcome = "indistinguishable_hit" if (score.get("pair") or {}).get("hit") else "indistinguishable_miss"
    else:
        outcome = answer                       # a refusal, or "inadmissible"
    return Adjudication(score["universe_id"], score["proposal_digest"], proposer_digest, kind, answer, outcome,
                        config.credit_for(kind, outcome), structure_match, config.digest, score["receipt"]["digest"],
                        score.get("security_boundary", SECURITY_LABEL), str(score.get("transport", "unknown")))


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
    constant_answer_credit: Mapping[str, float]      # total credit each constant refusal would have earned on this mix
    transport: str
    security_boundary: str = SECURITY_LABEL
    replay_of: str = ""                               # outcome digest of the report this run replayed ("" = a live run)

    @property
    def outcome_digest(self) -> str:
        return _digest([list(a.outcome_key()) for a in self.adjudications])

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, list[Adjudication]] = {}
        for a in self.adjudications:
            by_kind.setdefault(a.universe_kind, []).append(a)
        laws = [a for a in self.adjudications if a.answer in ("law", "indistinguishable")]
        controls = [a for a in self.adjudications if a.universe_kind != "discoverable"]
        disc = by_kind.get("discoverable", [])
        total = sum(a.credit for a in self.adjudications)
        best_constant = max(self.constant_answer_credit.values()) if self.constant_answer_credit else 0.0
        boundary_proven = self.security_boundary in PROVEN_BOUNDARY_LABELS
        disc_credit = sum(a.credit for a in disc)
        control_credit = sum(a.credit for a in self.adjudications if a.universe_kind != "discoverable")
        return {
            "universes": len(self.adjudications),
            "total_credit": total,
            "best_constant_answer_credit": best_constant,
            "credit_over_best_constant_answer": total - best_constant,
            # reported apart: control credit can be earned by classifying nuisance statistics without discovering anything
            "discovery_credit": disc_credit,
            "control_credit": control_credit,
            "mean_credit_by_kind": {k: sum(a.credit for a in v) / len(v) for k, v in sorted(by_kind.items())},
            "discovery_success_rate": None if not disc else sum(a.outcome == "law_pass" for a in disc) / len(disc),
            "false_discovery_rate": None if not laws else sum(a.credit < 0 for a in laws) / len(laws),
            # refusals only (a passing law on a control is not a refusal); an INDISTINGUISHABLE hit is a refusal to
            # extrapolate that also demonstrates why
            "correct_refusal_rate_on_controls": None if not controls else sum(
                a.credit > 0 and (a.answer in REFUSALS or a.outcome == "indistinguishable_hit") for a in controls) / len(controls),
            "control_credit_rate": None if not controls else sum(a.credit > 0 for a in controls) / len(controls),
            "inadmissible": sum(a.outcome == "inadmissible" for a in self.adjudications),
            "structure_match_rate": None if not disc else sum(a.structure_match for a in disc) / len(disc),
            "queries": self.queries,
            "transport": self.transport,
            "level_eligible_for_novel_discovery": self.level in NOVEL_DISCOVERY_LEVELS,
            # never while the escrow boundary is unproven, and never without a passing law on a discoverable universe
            "counts_as_novel_discovery": bool(self.level in NOVEL_DISCOVERY_LEVELS and boundary_proven
                                              and any(a.outcome == "law_pass" for a in disc)),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "engcore.blindfold.report/2", "campaign_id": self.campaign_id, "level": self.level,
                "config_digest": self.config_digest, "adjudication_digests": [a.digest for a in self.adjudications],
                "outcome_digest": self.outcome_digest, "queries": self.queries, "escrow_log_head": self.escrow_log_head,
                "proposer": dict(self.proposer), "constant_answer_credit": dict(sorted(self.constant_answer_credit.items())),
                "transport": self.transport, "security_boundary": self.security_boundary, "replay_of": self.replay_of,
                "summary": self.summary()}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


# ---------------------------------------------------------------------------- the campaign driver (operator role)


Proposer = Callable[[Mapping[str, Any], ObserveClient], Mapping[str, Any]]


def run_campaign(transport: Callable[[bytes], bytes], *, campaign_id: str, mix: Mapping[str, int], proposer: Proposer,
                 proposer_identity: Mapping[str, str], config: EvaluatorConfig, store: ProposalStore | None = None,
                 replay: Mapping[str, str] | None = None, replay_of: BlindfoldReport | None = None,
                 operator_token: str | None = None) -> tuple[BlindfoldReport, ProposalStore]:
    """Operator: create the campaign, hand the proposer ONLY an observe client, store and admit each proposal, have the
    evaluator score it once, adjudicate under the sealed config, verify receipts against the escrow log, report.

    ``replay`` maps EVERY universe_id -> stored proposal digest (anything else is refused): the proposals are read from
    ``store``, their recorded proposer must be ``proposer_identity``, and the proposer is NOT called.  With
    ``replay_of`` the replayed outcomes must equal that report's, or the replay is refused, and the report says it is a
    replay.  Replaying the same universes needs the escrow's master seed; whoever holds it can derive every hidden
    world, so it stays with the escrow operator.  The recorded proposer is whatever the store's writer recorded."""
    store = store or ProposalStore()
    sealed = config.digest
    identity = dict(proposer_identity)
    proposer_digest = _digest(identity)
    token = operator_token if operator_token is not None else getattr(transport, "operator_token", None)
    if not token:
        raise RoleRefused("the operator credential is required to create a campaign")
    operator = OperatorClient(transport, token)
    created = operator.create(campaign_id, mix, evaluator_config_digest=sealed)   # declared before any kind is revealed
    observe_client = ObserveClient(transport, campaign_id, created["tokens"]["observe"])
    score_client = ScoreClient(transport, campaign_id, created["tokens"]["score"])
    card_ids = [card["universe_id"] for card in created["cards"]]
    if replay is not None:
        if set(replay) != set(card_ids):
            raise RoleRefused("a replay names a stored proposal for every universe of the campaign and nothing else; "
                              "it never regenerates a missing one (wrong master seed or a partial map)")
        for uid in card_ids:
            recorded = store.get(replay[uid]).get("proposer")
            if recorded != identity:
                raise RoleRefused(f"stored proposal for {uid} was made by {recorded!r}, not {identity!r}: identity cannot be reassigned")
    adjudications = []
    receipts: dict[str, dict[str, Any]] = {}
    for card in created["cards"]:
        uid = card["universe_id"]
        frozen_card = json.loads(json.dumps(card))
        if replay is not None:
            stored = store.get(replay[uid])
            if stored.get("answer") == "inadmissible":
                store.get(stored["original_digest"])               # the original must still be there
            else:
                admit(stored, frozen_card, store)
        else:
            raw: Any = None
            try:
                raw = proposer(frozen_card, observe_client)
                proposal = dict(raw)
                proposal.setdefault("universe_id", uid)
                proposal["proposer"] = identity
                stored = store.get(admit(proposal, frozen_card, store).proposal_digest)
            except Exception as exc:  # noqa: BLE001 - a proposer that raises or returns garbage is scored, never a non-result
                # kept as it was, scored as what it is: inadmissible (negative credit), never a substitute refusal
                original = store.put_any(raw)
                try:
                    reason = f"{type(exc).__name__}: {str(exc)[:300]}"
                except Exception:  # noqa: BLE001
                    reason = type(exc).__name__
                stored = store.get(store.put({"universe_id": uid, "answer": "inadmissible", "original_digest": original,
                                              "reason": reason, "proposer": identity}))
        try:
            score = score_client.score(uid, stored)
        except EscrowRefused as exc:
            raise RoleRefused(f"the escrow refused the evaluator's submission: {exc}") from exc
        receipts[score["receipt"]["digest"]] = score["receipt"]
        adjudications.append(adjudicate(score, config, sealed_config_digest=sealed, proposer_digest=proposer_digest))
    log = operator.log(campaign_id)
    head = verify_log(log["log"])
    if head != log["head"]:
        raise RoleRefused("the escrow log head does not match its chain")
    chained = {e["digest"]: e for e in log["log"]}
    if not log["log"] or log["log"][0].get("public", {}).get("evaluator_config_digest") != sealed:
        raise RoleRefused("the escrow did not record this sealed evaluator config at campaign creation")
    for digest, receipt in receipts.items():
        if chained.get(digest) != receipt:
            raise RoleRefused("a score receipt is not in the escrow's hash chain")
    for a in adjudications:                   # each adjudication cites a score entry of THIS chain, for its own universe
        entry = chained.get(a.score_receipt_digest)
        if entry is None or entry["op"] != "score" or a.score_receipt_digest not in receipts:
            raise RoleRefused("an adjudication cites a receipt that is not a score entry of the escrow chain")
    queries = sum(1 for e in log["log"] if e["op"] == "observe")
    level = created["cards"][0]["level"] if created["cards"] else "L5"
    constant = {r: sum(config.credit_for(a.universe_kind, r) for a in adjudications) for r in REFUSALS}
    transports = {a.transport for a in adjudications}
    report = BlindfoldReport(campaign_id, level, sealed, tuple(adjudications), queries, head, identity, constant,
                             transports.pop() if len(transports) == 1 else "mixed",
                             replay_of="" if replay_of is None else replay_of.outcome_digest)
    if replay_of is not None and [a.outcome_key() for a in replay_of.adjudications] != [a.outcome_key() for a in adjudications]:
        raise RoleRefused("the replay does not reproduce the original report's outcomes")
    return report, store


__all__ = ["Adjudication", "AdmittedProposal", "BlindfoldReport", "DEFAULT_CREDIT", "EvaluatorConfig", "PROVEN_BOUNDARY_LABELS",
           "ProposalStore", "REFUSALS",
           "RoleRefused", "admit", "adjudicate", "run_campaign"]
