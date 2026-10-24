"""HypothesisCompetition (M-2), BeliefUpdate (M-7) and the read-only MindStateView (M-1).

The competition holds EVERY rival structure for the whole run.  Nothing is ever deleted:

* a hypothesis's scientific STATUS (PROPOSED, SURVIVING, REFUTED, UNKNOWN) is set only by
  :func:`engcore.claims.falsification.apply_verdicts` from sealed falsifier verdicts, and every status the Mind acts on
  is first checked with :func:`~engcore.claims.falsification.verify_status` against the registry anchor the Mind
  expects (a status label alone is never trusted -- deep-audit observation OBS-06);
* a hypothesis's STANDING (its posterior weight) is a number derived from admitted evidence by the outcome model and the
  declared prior, with its basis digest; it is not a status, and a low weight removes nothing;
* a REFUTED hypothesis stays in the competition with its refuting verdicts; it only stops receiving weight.

The exposure authority here is the Mind's local wrapper around the observations the escrow returns: it RELEASES each
observation once, on its clock, so a falsifier sealed before a query is provably sealed before its result.  The
observation uncertainty attached to a release is an ESTIMATE from replicate observations (a pooled pure-error
standard deviation, raised to its one-sided 95% upper confidence bound), with the replicates' evidence ids as its
basis.  Without a replicate degree of freedom it is UNKNOWN (``None``) and every verdict is INCONCLUSIVE: missing
uncertainty never becomes zero.  Within one process the authority's key protects ordering by construction only (the
Blindfold escrow's SECURITY_BOUNDARY_NOT_PROVEN caveat applies unchanged).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ...claims.falsification import (
    CriterionKind, EvidenceItem, EvidenceSource, ExposureAuthority, FalsificationRefused, Falsifier, K_MAX,
    MAX_RELATIVE_RESOLUTION, apply_verdicts, verify_status,
)
from ...sria.decision import Hypothesis, HypothesisStatus, ProposalProvenance, ProposerKind
from .outcome_model import AdmittedObservation, FittedStructure, OutcomeModel, OutcomePrediction
from .problem import ExperimentalProblem
from .structures import PRIOR_SPEC, Structure, hypothesis_for, log_prior, structure_from_proposal, structures_for

STATE_VIEW_SCHEMA = "forge.mind.minimal.state_view/1"
#: coverage factor of every sealed falsifier (policy ceiling K_MAX in claims.falsification)
FALSIFIER_K = 4.0
#: one-sided 5% lower quantiles of chi-square(dof), dof = 1..10 (exact); Wilson-Hilferty beyond
_CHI2_LOW05 = (0.003932, 0.102587, 0.351846, 0.710723, 1.145476, 1.635383, 2.167350, 2.732637, 3.325113, 3.940299)
#: hypotheses below this posterior weight are not tested by a sealed falsifier at a step (they stay in the competition)
TEST_WEIGHT_FLOOR = 0.02
#: largest |ln y| a sealed prediction may state (exp() of it stays a finite double with room for k * u)
MAX_LN = 600.0
MAX_TESTED_PER_STEP = 4


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _chi2_low05(dof: int) -> float:
    if dof <= len(_CHI2_LOW05):
        return _CHI2_LOW05[dof - 1]
    z = -1.6448536269514722
    return dof * (1 - 2 / (9 * dof) + z * math.sqrt(2 / (9 * dof))) ** 3


@dataclass(frozen=True)
class NoiseEstimate:
    """Pooled replicate (pure-error) sd of ln(observable) and its 95% upper bound; None when no replicate exists."""

    sd: float | None
    upper95: float | None
    dof: int
    basis: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        r = (lambda x: None if x is None else round(x, 9))
        return {"sd_ln": r(self.sd), "upper95_ln": r(self.upper95), "dof": self.dof, "basis": list(self.basis),
                "kind": "ESTIMATED_FROM_REPLICATES" if self.dof else "UNKNOWN"}


def pure_error(rows: Sequence[AdmittedObservation]) -> NoiseEstimate:
    groups: dict[str, list[AdmittedObservation]] = {}
    for r in rows:
        groups.setdefault(json.dumps(dict(sorted(r.settings.items())), sort_keys=True), []).append(r)
    ss, dof, basis = 0.0, 0, []
    for members in groups.values():
        if len(members) > 1:
            logs = [math.log(m.value) for m in members if m.value > 0]
            if len(logs) == len(members):
                mu = sum(logs) / len(logs)
                ss += sum((v - mu) ** 2 for v in logs)
                dof += len(logs) - 1
                basis += [m.evidence_id for m in members]
    if dof == 0:
        return NoiseEstimate(None, None, 0, ())
    sd = math.sqrt(ss / dof)
    return NoiseEstimate(sd, sd * math.sqrt(dof / _chi2_low05(dof)), dof, tuple(sorted(basis)))


@dataclass
class Rival:
    structure: Structure
    hypothesis: Hypothesis
    ticket: Any
    log_prior: float
    fitted: FittedStructure | None = None
    weight: float | None = None


class HypothesisCompetition:
    """All rivals, their statuses (from the falsification registry only) and their standing (from evidence only)."""

    def __init__(self, problem: ExperimentalProblem, *, seed: int, authority_key: bytes, campaign_id: str,
                 extra: Iterable[Structure] = (), falsify: bool = True) -> None:
        self.problem = problem
        self.model = OutcomeModel(problem)
        self.falsify = falsify
        self.authority = ExposureAuthority("forge.mind.minimal.observation_release", key=authority_key, derived_tickets=True)
        self.registry = self.authority.registry(campaign_id)
        self.anchor = self.registry.anchor
        self.rows: list[AdmittedObservation] = []
        self.items: dict[str, EvidenceItem] = {}
        self.rivals: dict[str, Rival] = {}
        self.proposals: list[dict[str, Any]] = []
        for s in structures_for(problem, extra):
            self._add(s)
        self.covmodels: dict = {}
        self.noise = NoiseEstimate(None, None, 0, ())
        self.verdict_digests: list[str] = []
        self._sealed_at: dict[str, set[str]] = {}
        self._verified: dict[str, HypothesisStatus] = {}
        self.refit()

    # ---- membership --------------------------------------------------------------------------------------------------
    def _add(self, s: Structure, proposer: ProposalProvenance | None = None) -> Rival:
        h = hypothesis_for(s, self.problem, proposer=proposer)
        if h.hypothesis_id in self.rivals:
            return self.rivals[h.hypothesis_id]
        ticket = self.registry.register(h)
        rival = Rival(s, h, ticket, log_prior(s, self.problem))
        self.rivals[h.hypothesis_id] = rival
        return rival

    def ingest_proposal(self, proposal: Mapping[str, Any], *, proposer_kind: ProposerKind | str, proposer_id: str) -> str:
        """An external (e.g. language-model) structure proposal joins the competition PROPOSED, at the declared prior.

        It names variables only: any status, weight, confidence, uncertainty, threshold or outcome is refused
        (``StructureRefused``).  A proposal of a structure already in the competition adds its provenance and nothing
        else -- the same claim is one hypothesis."""
        s = structure_from_proposal(proposal, self.problem)
        prov = ProposalProvenance(proposer_kind, proposer_id, proposal_digest=_digest(dict(proposal)))
        rival = self._add(s, prov)
        self.proposals.append({"hypothesis_id": rival.hypothesis.hypothesis_id, "provenance": prov.to_dict()})
        self.refit()
        return rival.hypothesis.hypothesis_id

    # ---- status (from the registry only) -----------------------------------------------------------------------------
    def status(self, hid: str) -> HypothesisStatus:
        h = self.rivals[hid].hypothesis
        problems = verify_status(h, self.registry, anchor=self.anchor)
        if problems:
            raise FalsificationRefused(f"status of {hid} does not verify against the expected registry: {problems}")
        return h.status

    def refuted(self, hid: str) -> bool:
        return self.falsify and self.status(hid) is HypothesisStatus.REFUTED

    def faced_decisive_test(self, hid: str) -> bool:
        """Whether this rival has at least one NOT_REFUTED verdict on its current content (a decisive test it survived)."""
        h = self.rivals[hid].hypothesis
        return any(v.verdict.value == "not_refuted" for v in self.registry.verdicts_for(hid, h.content_digest))

    def _verify(self, hid: str) -> None:
        """Every status the Mind will act on is verified against the expected registry when it is set (OBS-06)."""
        h = self.rivals[hid].hypothesis
        problems = verify_status(h, self.registry, anchor=self.anchor)
        if problems:
            raise FalsificationRefused(f"status of {hid} does not verify against the expected registry: {problems}")
        self._verified[h.digest] = h.status

    # ---- belief update (M-7) -----------------------------------------------------------------------------------------
    def refit(self) -> None:
        """Refit every non-refuted rival to the admitted evidence and recompute the posterior weights."""
        self.covmodels = self.model.covariate_models(self.rows) if self.rows else {}
        self.noise = pure_error(self.rows)
        logw = {}
        for hid, r in self.rivals.items():
            if self.falsify and r.hypothesis.status is HypothesisStatus.REFUTED                     and self._verified.get(r.hypothesis.digest) is HypothesisStatus.REFUTED:
                r.fitted, r.weight = None, 0.0
                continue
            r.fitted = self.model.fit(r.structure, self.rows, hid)
            if r.fitted.fit_ok:
                logw[hid] = r.log_prior + float(r.fitted.log_bf_null)
            else:
                r.weight = None                         # no number exists: never a default
        if logw:
            top = max(logw.values())
            z = sum(math.exp(v - top) for v in logw.values())
            for hid, v in logw.items():
                self.rivals[hid].weight = math.exp(v - top) / z

    def weights(self, *, prior_only: bool = False) -> dict[str, float]:
        """Posterior weights of the fitted, non-refuted rivals (or, for the fixed-policy ablation, the declared prior
        renormalised over the same set)."""
        live = {hid: r for hid, r in self.rivals.items() if r.fitted is not None and r.fitted.fit_ok}
        if prior_only:
            if not live:
                return {}
            top = max(r.log_prior for r in live.values())
            z = sum(math.exp(r.log_prior - top) for r in live.values())
            return {hid: math.exp(r.log_prior - top) / z for hid, r in live.items()}
        return {hid: float(r.weight) for hid, r in live.items() if r.weight is not None}

    def leading(self, weights: Mapping[str, float] | None = None) -> str | None:
        w = self.weights() if weights is None else weights
        return max(sorted(w), key=lambda h: w[h]) if w else None

    # ---- predictions (M-3) --------------------------------------------------------------------------------------------
    def predictions(self, point: Mapping[str, float], query_ref: str, hids: Iterable[str]) -> dict[str, OutcomePrediction]:
        out = {}
        for hid in hids:
            r = self.rivals[hid]
            if r.fitted is None:
                out[hid] = OutcomePrediction(hid, query_ref, False, None, None, None, None, "", reason="REFUTED: not fitted")
            else:
                out[hid] = self.model.prediction(r.fitted, point, self.covmodels, query_ref)
        return out

    # ---- sealed falsifiers ---------------------------------------------------------------------------------------------
    def seal(self, query_ref: str, settings: Mapping[str, float], predictions: Mapping[str, OutcomePrediction],
             weights: Mapping[str, float]) -> list[dict]:
        """Seal one PREDICTION_DEVIATION falsifier per tested hypothesis at this setting, BEFORE its result exists.

        The test conditions are the SETTINGS: the registry refuses a seal where an observation at those settings was
        already released (a replicate's outcome could be read off the data, so it is never a falsifier test)."""
        sealed = []
        if not self.falsify:
            return sealed
        conditions = {"settings": dict(sorted((k, float(v)) for k, v in settings.items()))}
        skey = _digest(conditions)
        tested = [h for h in sorted(weights, key=lambda h: (-weights[h], h)) if weights[h] >= TEST_WEIGHT_FLOOR][:MAX_TESTED_PER_STEP]
        for hid in tested:
            p = predictions.get(hid)
            r = self.rivals[hid]
            if p is None or not p.available or r.hypothesis.status is HypothesisStatus.REFUTED:
                continue
            if not (math.isfinite(p.mean) and math.isfinite(p.sd_mean) and abs(p.mean) < MAX_LN):
                sealed.append({"hypothesis_id": hid, "sealed": False,
                               "reason": "the prediction is not a finite representable value; no falsifier is sealed on it"})
                continue
            predicted = math.exp(p.mean)
            # the structure claims that ln y is its linear form PLUS MEASUREMENT NOISE ONLY: when replicates bound the
            # measurement noise, its parameter uncertainty is computed with that bound, never with a residual variance
            # inflated by its own misfit (a misfitting structure would otherwise be too vague ever to be refuted)
            sd_mean = p.sd_mean
            fitted = r.fitted
            if self.noise.upper95 is not None and fitted is not None and fitted.fit_ok and fitted.s2 > 0:
                own = math.sqrt(fitted.s2 * fitted.dof / max(fitted.dof - 2, 1))
                sd_mean = p.sd_mean * min(1.0, self.noise.upper95 / own)
            pred_u = predicted * sd_mean
            resolution = MAX_RELATIVE_RESOLUTION * predicted
            if not FALSIFIER_K * pred_u < resolution:
                sealed.append({"hypothesis_id": hid, "sealed": False,
                               "reason": "the prediction is too uncertain to be a falsifier (k x u_pred >= resolution)"})
                continue
            f = Falsifier(falsifier_id=f"{hid}|{query_ref[:24]}", hypothesis_id=hid,
                          hypothesis_content_digest=r.hypothesis.content_digest, observable=self.problem.observable,
                          unit=self.problem.observable_unit or "1", test_conditions=conditions,
                          evidence_source=EvidenceSource.ESCROW_OBSERVATION, criterion=CriterionKind.PREDICTION_DEVIATION,
                          parameters={"k": FALSIFIER_K, "predicted": predicted, "prediction_uncertainty": pred_u,
                                      "resolution": resolution})
            assert FALSIFIER_K <= K_MAX
            try:
                entry = self.registry.seal(f, r.ticket)
            except FalsificationRefused as exc:
                sealed.append({"hypothesis_id": hid, "sealed": False, "reason": f"registry refused the seal: {exc}"})
                continue
            self._sealed_at.setdefault(skey, set()).add(hid)
            r.hypothesis = r.hypothesis.revise(falsifier_refs=tuple(sorted({*r.hypothesis.falsifier_refs, f.ref})))
            sealed.append({"hypothesis_id": hid, "sealed": True, "falsifier_ref": f.ref, "falsifier_digest": f.digest,
                           "registry_entry": entry.digest})
        return sealed

    # ---- admission of an executed observation --------------------------------------------------------------------------
    def admit(self, query_ref: str, settings: Mapping[str, float], observation: Mapping[str, float]) -> tuple[AdmittedObservation, EvidenceItem, list[dict]]:
        """Release the observation on the authority's clock, judge every sealed falsifier it matches, refit."""
        value = float(observation[self.problem.observable])
        covs = {c: float(observation[c]) for c in self.problem.covariates if c in observation}
        provisional = [*self.rows, AdmittedObservation(query_ref, "", query_ref, dict(settings), covs, value)]
        noise = pure_error(provisional)
        u = None if noise.upper95 is None or not math.isfinite(value) else abs(value) * noise.upper95
        conditions = {"settings": dict(sorted((k, float(v)) for k, v in settings.items()))}
        item = self.authority.release(evidence_id=query_ref, source=EvidenceSource.ESCROW_OBSERVATION,
                                      observable=self.problem.observable, unit=self.problem.observable_unit or "1",
                                      value=value, uncertainty=u, conditions={**conditions, "query_ref": query_ref})
        row = AdmittedObservation(query_ref, item.content_digest, query_ref, dict(settings), covs, value)
        self.rows.append(row)
        self.items[query_ref] = item
        verdicts = []
        if self.falsify:
            for hid in sorted(self._sealed_at.get(_digest(conditions), ())):
                r = self.rivals[hid]
                before = r.hypothesis.status
                r.hypothesis = apply_verdicts(r.hypothesis, self.registry)
                self._verify(hid)
                for b in r.hypothesis.status_basis:
                    if b.verdict_digest not in self.verdict_digests:
                        self.verdict_digests.append(b.verdict_digest)
                verdicts.append({"hypothesis_id": hid, "before": before.value, "after": r.hypothesis.status.value,
                                 "basis": [b.verdict_digest for b in r.hypothesis.status_basis]})
        self.refit()
        return row, item, verdicts

    # ---- M-1: read-only view -----------------------------------------------------------------------------------------
    def view(self, *, budget_spent: int, actions: Sequence[str] = ()) -> dict[str, Any]:
        w = self.weights()
        hyps = []
        for hid in sorted(self.rivals):
            r = self.rivals[hid]
            hyps.append({"hypothesis_id": hid, "claim_digest": r.hypothesis.claim_digest, "status": r.hypothesis.status.value,
                         "falsifiers": len(r.hypothesis.falsifier_refs),
                         "verdicts": [b.verdict_digest for b in r.hypothesis.status_basis],
                         "weight": None if hid not in w else round(w[hid], 9),
                         "fit": None if r.fitted is None else r.fitted.summary(),
                         "proposer": r.hypothesis.proposal.proposer_kind.value if r.hypothesis.proposal else None})
        unknowns = []
        if self.noise.upper95 is None:
            unknowns.append("observation uncertainty: UNKNOWN (no replicate degree of freedom yet)")
        unfit = sorted(h["hypothesis_id"] for h in hyps if h["fit"] is not None and not h["fit"]["fit_ok"])
        if unfit:
            unknowns.append(f"{len(unfit)} rival(s) UNFIT: no standing can be computed for them yet")
        if self.problem.covariates:
            unknowns.append("passive covariates at a planned query: predicted through a fitted submodel, never set")
        return {
            "schema": STATE_VIEW_SCHEMA,
            "problem_digest": self.problem.digest,
            "knowns": {"admitted_evidence": [r.evidence_digest for r in self.rows], "noise": self.noise.to_dict()},
            "unknowns": unknowns,
            "hypotheses": hyps,
            "contradictions": sorted(h["hypothesis_id"] for h in hyps if h["status"] == HypothesisStatus.REFUTED.value),
            "evidence_count": len(self.rows),
            "actions": list(actions),
            "budget": {"spent": budget_spent, "remaining": self.problem.budget - budget_spent, "total": self.problem.budget},
            "prior": PRIOR_SPEC, "outcome_model": OutcomeModel.identity,
            "registry_head": self.registry.head, "proposals": list(self.proposals),
        }


def view_digest(view: Mapping[str, Any]) -> str:
    return _digest(dict(view))


def mixture_logscore(predictions: Mapping[str, OutcomePrediction], weights: Mapping[str, float], t_obs: float) -> dict[str, Any]:
    """Proper scoring of a sealed mixture prediction after its result: log predictive density, PIT, 90% coverage."""
    from .outcome_model import t_cdf, t_logpdf

    terms, cdf, wsum = [], 0.0, 0.0
    for hid, p in predictions.items():
        w = weights.get(hid, 0.0)
        if not p.available or w <= 0 or not (math.isfinite(p.mean) and math.isfinite(p.sd_obs) and p.sd_obs > 0):
            continue
        terms.append(math.log(w) + t_logpdf(t_obs, p.mean, p.sd_obs, p.dof))
        cdf += w * t_cdf(t_obs, p.mean, p.sd_obs, p.dof)
        wsum += w
    if not terms or wsum <= 0:
        return {"available": False, "reason": "no sealed prediction was available before this result"}
    top = max(terms)
    log_score = top + math.log(sum(math.exp(t - top) for t in terms)) - math.log(wsum)
    pit = cdf / wsum
    return {"available": True, "log_score": round(log_score, 9), "pit": round(pit, 9), "covered90": 0.05 <= pit <= 0.95}


__all__ = ["FALSIFIER_K", "HypothesisCompetition", "NoiseEstimate", "Rival", "STATE_VIEW_SCHEMA", "mixture_logscore",
           "pure_error", "view_digest"]
