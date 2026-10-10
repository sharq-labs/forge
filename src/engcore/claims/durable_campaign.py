"""A discovery campaign whose authorities survive restart: exposure clock, sealed falsifiers, multiplicity, novelty.

The in-memory authorities (:class:`~engcore.claims.falsification.ExposureAuthority` and the registry, novelty ledger and
:class:`~engcore.claims.multiplicity.MultiplicityLedger` it governs) are unchanged.  :class:`DurableCampaign` drives
them and JOURNALS every state-changing operation into the persistent, signed authority ledger
(:mod:`engcore.authority`) as an attestation of kind ``campaign_op``:

* signed by the campaign's EXPOSURE-role issuer (an unauthorized, revoked or wrong-key issuer cannot journal anything);
* carrying the operation, its arguments (whole records: hypotheses, falsifiers, releases, snapshots) and the HEADS after
  it (falsifier-registry head, authority clock, novelty head, multiplicity state digest).

:meth:`DurableCampaign.resume` rebuilds the campaign by REPLAYING the journal through the same code paths and refuses
the moment any recorded head differs: a dropped, reordered or rewritten operation (truncation of the authority ledger
itself is caught by its anchor) or a code change that alters the outcome cannot pass as the same campaign.  Key
material comes from the externally supplied :class:`~engcore.authority.KeyProvider` (``secret(issuer_id)``), and owner
tickets are DERIVED from it, so the restored campaign has the same authority fingerprint, the same evidence MACs and
the same owner tickets.  Every operation first checks that the live state still equals the last journaled heads: a
mutation made around the journal (calling the registry directly) is refused, never silently lost on restart.

Residuals (stated): inside one process the wrapped objects are reachable (construction, not isolation); a multiplicity
context sealed in a previous process is verified by DIGEST against the replayed ledger (:meth:`verify_context`), since
its HMAC seal is per process.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from ..authority import Attestation, AuthorityLedger, KeyProvider, Role
from ..sria.decision import Hypothesis
from . import multiplicity as _mult
from .falsification import EvidenceItem, ExposureAuthority, Falsifier, FalsifierVerdict, HypothesisTicket, apply_verdicts, judge
from .novelty import PriorArtEntry, PriorArtSnapshot

OP_KIND = "campaign_op"
OP_SCHEMA = "engcore.claims.durable_campaign_op/1"
_MULT_OPS = ("count", "tested", "evaluated", "compute", "seed", "strategy")


class CampaignRefused(ValueError):
    pass


def campaign_subject(campaign_id: str) -> str:
    return hashlib.sha256(f"forge.durable-campaign\n{campaign_id}".encode()).hexdigest()


def snapshot_to_record(s: PriorArtSnapshot) -> dict[str, Any]:
    return {"snapshot_id": s.snapshot_id, "covers_kinds": list(s.covers_kinds), "sources": list(s.sources),
            "coverage_criteria": s.coverage_criteria, "canonicalizer_id": s.canonicalizer_id,
            "equivalence": None if s.equivalence is None else dict(s.equivalence),
            "entries": [{"entry_id": e.entry_id, "structure_digest": e.structure_digest, "source_ref": e.source_ref,
                         "expression": None if e.expression is None else dict(e.expression)} for e in s.entries],
            "digest": s.digest}


def snapshot_from_record(d: Mapping[str, Any]) -> PriorArtSnapshot:
    s = PriorArtSnapshot(d["snapshot_id"], tuple(d["covers_kinds"]),
                         tuple(PriorArtEntry(e["entry_id"], e["structure_digest"], e["source_ref"], e["expression"]) for e in d["entries"]),
                         tuple(d["sources"]), d["coverage_criteria"], d["canonicalizer_id"], d["equivalence"])
    if s.digest != d["digest"]:
        raise CampaignRefused("a journaled prior-art snapshot does not rebuild to its sealed digest")
    return s


def falsifier_from_record(d: Mapping[str, Any]) -> Falsifier:
    f = Falsifier(d["falsifier_id"], d["hypothesis_id"], d["hypothesis_content_digest"], d["observable"], d["unit"], d["test_conditions"],
                  d["evidence_source"], d["criterion"], d["parameters"], d["version"], d["supersedes"], d["allow_exact_observation"])
    if f.to_dict() != {k: v for k, v in d.items()}:
        raise CampaignRefused("a journaled falsifier does not rebuild to itself")
    return f


class DurableCampaign:
    """See the module docstring.  Use :meth:`start` or :meth:`resume`."""

    def __init__(self, ledger: AuthorityLedger, keys: KeyProvider, *, issuer_id: str, campaign_id: str, config: Mapping[str, Any],
                 _token: object = None) -> None:
        if _token is not _CONSTRUCT:
            raise CampaignRefused("a durable campaign is started (DurableCampaign.start) or resumed from its journal")
        if not isinstance(ledger, AuthorityLedger):
            raise CampaignRefused("a durable campaign journals into an opened AuthorityLedger")
        self._ledger, self._keys, self._issuer, self._campaign = ledger, keys, issuer_id, campaign_id
        self._config = dict(config)
        scales = {(o, u): v for o, u, v in config["resolution_scales"]}
        self._authority = ExposureAuthority(config["authority_id"], key=keys.secret(issuer_id), resolution_scales=scales,
                                            derived_tickets=True)
        self._registry = self._authority.registry(campaign_id)
        self._novelty = self._authority.novelty_ledger(campaign_id)
        self._mult = _mult.MultiplicityLedger(campaign_id, _replay=_mult._REPLAY)
        self._ops = 0
        self._last_heads: dict[str, Any] = {}
        self._poisoned = ""

    # -- construction
    @classmethod
    def start(cls, ledger: AuthorityLedger, keys: KeyProvider, *, issuer_id: str, campaign_id: str, authority_id: str,
              context_digest: str, resolution_scales: Mapping[tuple[str, str], float] | None = None) -> "DurableCampaign":
        if ledger.attestations(record_kind=OP_KIND, subject_digest=campaign_subject(campaign_id)):
            raise CampaignRefused(f"campaign {campaign_id!r} already has a journal in this ledger; resume it")
        config = {"authority_id": authority_id, "context_digest": context_digest,
                  "resolution_scales": sorted([o, u, float(v)] for (o, u), v in dict(resolution_scales or {}).items())}
        c = cls(ledger, keys, issuer_id=issuer_id, campaign_id=campaign_id, config=config, _token=_CONSTRUCT)
        c._journal("start", {"config": config})
        return c

    @classmethod
    def resume(cls, ledger: AuthorityLedger, keys: KeyProvider, *, issuer_id: str, campaign_id: str) -> "DurableCampaign":
        journal = [r for r in ledger.attestations(record_kind=OP_KIND, subject_digest=campaign_subject(campaign_id))]
        if not journal:
            raise CampaignRefused(f"no journal for campaign {campaign_id!r}")
        for n, r in enumerate(journal):
            rec = r.attestation.record
            if r.issuer_id != issuer_id or r.attestation.role is not Role.EXPOSURE or rec.get("campaign_id") != campaign_id \
                    or rec.get("index") != n:
                raise CampaignRefused(f"journal entry {n} is not this campaign's (issuer, role, campaign or index differs)")
        first = journal[0].attestation.record
        if first["op"] != "start":
            raise CampaignRefused("a campaign journal begins with its start")
        c = cls(ledger, keys, issuer_id=issuer_id, campaign_id=campaign_id, config=first["args"]["config"], _token=_CONSTRUCT)
        c._ops = 1
        c._check(first["heads"], 0)
        for n, r in enumerate(journal[1:], start=1):
            rec = r.attestation.record
            c._replay(rec["op"], rec["args"])
            c._check(rec["heads"], n)
            c._ops = n + 1
        return c

    # -- read access (the wrapped authorities; mutate ONLY through this object)
    @property
    def authority(self) -> ExposureAuthority:
        return self._authority

    @property
    def registry(self):
        return self._registry

    @property
    def novelty(self):
        return self._novelty

    @property
    def multiplicity(self) -> _mult.MultiplicityLedger:
        return self._mult

    @property
    def campaign_id(self) -> str:
        return self._campaign

    @property
    def context_digest(self) -> str:
        return self._config["context_digest"]

    @property
    def journal_length(self) -> int:
        return self._ops

    def heads(self) -> dict[str, Any]:
        m = self._mult
        mult_state = {"counts": dict(m._counts), "per_fidelity": dict(sorted(m._per_fidelity.items())),
                      "compute": dict(sorted(m._compute.items())), "seeds": sorted(m._seeds), "strategies": sorted(m._strategies),
                      "tested": sorted(m._tested), "promoted": sorted(m._promoted), "closed": m._closed is not None}
        return {"registry": self._registry.head, "clock": self._authority.clock, "novelty": self._novelty.head,
                "multiplicity": hashlib.sha256(json.dumps(mult_state, sort_keys=True).encode()).hexdigest(),
                "fingerprint": self._authority.fingerprint}

    def verify_context(self, context_record: Mapping[str, Any]) -> bool:
        """A multiplicity context dict saved before a restart equals the replayed ledger's FINAL context."""
        final = self._mult.final
        return final is not None and dict(context_record) == _mult._context_dict(
            campaign_id=final.campaign_id, counts=final.counts, evaluated_per_fidelity=final.evaluated_per_fidelity,
            compute=final.compute, seeds=final.seeds, strategy_versions=final.strategy_versions, tested_ids=final.tested_ids,
            promoted_ids=final.promoted_ids)

    # -- journaled operations
    def register(self, hypothesis: Hypothesis, ticket: HypothesisTicket | None = None) -> HypothesisTicket:
        self._guard()
        t = self._registry.register(hypothesis, ticket)
        self._journal("register", {"hypothesis": hypothesis.to_dict()})
        return t

    def seal(self, falsifier: Falsifier, ticket: HypothesisTicket) -> None:
        self._guard()
        self._registry.seal(falsifier, ticket)
        self._journal("seal", {"falsifier": falsifier.to_dict()})

    def release(self, **kwargs: Any) -> EvidenceItem:
        self._guard()
        item = self._authority.release(**kwargs)
        args = {k: (v.value if hasattr(v, "value") else v) for k, v in kwargs.items()}
        self._journal("release", {"release": args})
        return item

    def judge(self, falsifier_digest: str, evidence_id: str) -> FalsifierVerdict:
        self._guard()
        v = judge(falsifier_digest, self._registry, self._authority._released[evidence_id])
        self._journal("judge", {"falsifier_digest": falsifier_digest, "evidence_id": evidence_id})
        return v

    def apply_verdicts(self, hypothesis: Hypothesis) -> Hypothesis:
        self._guard()
        h = apply_verdicts(hypothesis, self._registry)
        self._journal("apply_verdicts", {"hypothesis": hypothesis.to_dict()})
        return h

    def seal_prior_art(self, snapshot: PriorArtSnapshot) -> int:
        self._guard()
        clock = self._novelty.seal(snapshot)
        self._journal("seal_prior_art", {"snapshot": snapshot_to_record(snapshot)})
        return clock

    def record_proposal(self, hypothesis: Hypothesis) -> int:
        self._guard()
        clock = self._novelty.record_proposal(hypothesis)
        self._journal("record_proposal", {"hypothesis": hypothesis.to_dict()})
        return clock

    def count(self, op: str, *args: Any) -> None:
        """Multiplicity accounting: ``op`` is one of count / tested / evaluated / compute / seed / strategy."""
        self._guard()
        if op not in _MULT_OPS:
            raise CampaignRefused(f"multiplicity operations are {_MULT_OPS}")
        getattr(self._mult, op)(*args)
        self._journal("multiplicity", {"op": op, "args": list(args)})

    def promote(self, result_id: str, hypothesis_id: str) -> _mult.PromotedResult:
        self._guard()
        r = _mult.promote(result_id, hypothesis_id, self._mult)
        self._journal("promote", {"result_id": result_id, "hypothesis_id": hypothesis_id})
        return r

    def close_multiplicity(self) -> _mult.MultiplicityContext:
        self._guard()
        ctx = self._mult.close()
        self._journal("close_multiplicity", {})
        return ctx

    # -- internals
    def _guard(self) -> None:
        if self._poisoned:
            raise CampaignRefused(f"the campaign journal could not be written ({self._poisoned}); it must be resumed")
        if self._last_heads and self.heads() != self._last_heads:
            raise CampaignRefused("the campaign state changed outside its journal (an authority was mutated directly); "
                                  "that change would be lost on restart, so nothing more is accepted")

    def _journal(self, op: str, args: Mapping[str, Any]) -> None:
        heads = self.heads()
        record = {"campaign_id": self._campaign, "index": self._ops, "op": op, "args": dict(args), "heads": heads}
        att = Attestation(OP_KIND, OP_SCHEMA, record, campaign_subject(self._campaign), self.context_digest, Role.EXPOSURE)
        try:
            self._ledger.attest(self._keys.signer(self._issuer), self._issuer, att)
        except Exception as exc:
            self._poisoned = str(exc)[:160]
            raise
        self._ops += 1
        self._last_heads = heads

    def _check(self, recorded: Mapping[str, Any], n: int) -> None:
        now = self.heads()
        if dict(recorded) != now:
            diff = sorted(k for k in now if now.get(k) != recorded.get(k))
            raise CampaignRefused(f"replaying journal entry {n} does not reproduce its recorded heads ({diff}): the journal was "
                                  "altered, an entry is missing, or the code no longer reproduces this campaign")
        self._last_heads = now

    def _replay(self, op: str, args: Mapping[str, Any]) -> None:
        if op == "register":
            h = Hypothesis.from_dict(args["hypothesis"])
            owner = self._registry._owners.get(h.hypothesis_id)
            self._registry.register(h, None if owner is None else HypothesisTicket(h.hypothesis_id, owner))
        elif op == "seal":
            f = falsifier_from_record(args["falsifier"])
            self._registry.seal(f, HypothesisTicket(f.hypothesis_id, self._registry._owners[f.hypothesis_id]))
        elif op == "release":
            self._authority.release(**args["release"])
        elif op == "judge":
            judge(args["falsifier_digest"], self._registry, self._authority._released[args["evidence_id"]])
        elif op == "apply_verdicts":
            apply_verdicts(Hypothesis.from_dict(args["hypothesis"]), self._registry)
        elif op == "seal_prior_art":
            self._novelty.seal(snapshot_from_record(args["snapshot"]))
        elif op == "record_proposal":
            self._novelty.record_proposal(Hypothesis.from_dict(args["hypothesis"]))
        elif op == "multiplicity":
            getattr(self._mult, args["op"])(*args["args"])
        elif op == "promote":
            _mult.promote(args["result_id"], args["hypothesis_id"], self._mult)
        elif op == "close_multiplicity":
            self._mult.close()
        else:
            raise CampaignRefused(f"unknown journaled operation {op!r}")


_CONSTRUCT = object()

__all__ = ["OP_KIND", "OP_SCHEMA", "CampaignRefused", "DurableCampaign", "campaign_subject", "falsifier_from_record",
           "snapshot_from_record", "snapshot_to_record"]
