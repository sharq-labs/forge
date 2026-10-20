"""The Minimal Mind's closed loop and its conclusion.

    scientific state -> competing hypotheses -> pre-result predictions -> candidate experiments -> selection
    -> execution (the caller's observe) -> evidence release / falsifier verdicts -> belief update -> stop / replan

:func:`run_mind` drives the loop; :func:`conclude` turns the final state into ONE of six conclusions.  The conclusion
is a proposal for the caller's authority (a benchmark evaluator, an evidence gateway); it is not a verdict, it carries
the leading hypothesis's registry status exactly as verified, and nothing in it is promoted beyond what the evidence
shows:

* ``LAW`` -- the region of use lies inside the box, the leading rival predicts it to within :data:`PRECISION` (ln
  units, the same bar as the Genesis-lite baselines' ``arms.PRECISION``), the rivals that still carry weight agree
  with it to that precision, and it fits to within the replicate noise.
* ``NO_DEPENDENCE`` -- rivals that use no settable input hold at least half of the posterior.
* ``UNIDENTIFIABLE_PASSIVE_ASSOCIATION`` -- the posterior inclusion of a passive covariate is at least
  :data:`ASSOCIATION_INCLUSION` (strong evidence of association) and the covariate varies
  independently of every settable input.  No admissible experiment sets it, so its causal coefficient cannot be
  separated from a hidden common cause: the association is reported, never promoted to a mechanism.
* ``INDISTINGUISHABLE`` -- the region leaves the box and two rivals that both carry weight, are both pinned down to
  :data:`PRECISION` inside the box and agree there within the noise, diverge in the region: both are preserved,
  neither is chosen.
* ``INSUFFICIENT_EVIDENCE`` -- anything else (precision not reached; extrapolation with no rival to preserve; no
  rival survives).
* ``REFUSED`` -- the model of the observable is inapplicable (e.g. a non-positive observation).

Once any rival has been refuted by a sealed falsifier, only rivals that have themselves survived a decisive sealed test
carry the conclusion: an untested rival does not inherit the standing of the refuted ones.

A passive covariate that is (almost) a function of the settable inputs (R^2 >= :data:`COPY_R2`) is a copy of the
intervened inputs: the rivals that use it are set aside for the conclusion, because the intervened inputs identify
the interventional dependence and the copy adds nothing that an intervention could test (SPURIOUS_CORRELATE).

Ablations (:class:`MindConfig`) remove one capability at a time and keep everything else identical.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from ...claims.multiplicity import MultiplicityLedger
from ...sria.decision import ActionFamily, HypothesisStatus
from ...sria.decision.external import ExternalSuggestion
from . import experiments as ex
from . import falsifier as fz
from .competition import HypothesisCompetition, mixture_logscore, view_digest
from .outcome_model import OutcomeModelRefused
from .problem import ExperimentalProblem
from .stopping import StopKind, decide
from .structures import Structure
from .trace import GENESIS, TRACE_SCHEMA, ReplayObserver, ReplayRefused, compare, digest, step_record, verify_chain

MIND_ID = "forge.mind.minimal"
MIND_VERSION = "1.0.0"
PRECISION = 0.02
COPY_R2 = 0.9
ASSOCIATION_INCLUSION = 0.9
NULL_DECISION = 0.5
PRESERVE_WEIGHT = 0.1
MAX_SEALED_PREDICTIONS = 8
CONCLUSION_SCHEMA = "forge.mind.minimal.conclusion/1"


class ObservationRefused(RuntimeError):
    """The world refused an observation; ``budget`` says whether it was the budget."""

    def __init__(self, message: str, *, budget: bool = False) -> None:
        super().__init__(message)
        self.budget = budget


@dataclass(frozen=True)
class MindConfig:
    variant: str = "full"
    adaptive_selection: bool = True
    belief_update: bool = True
    falsifier: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"variant": self.variant, "adaptive_selection": self.adaptive_selection, "belief_update": self.belief_update,
                "falsifier": self.falsifier, "mind": f"{MIND_ID}@{MIND_VERSION}", "precision": PRECISION}


FULL = MindConfig("full")
NO_BELIEF_UPDATE = MindConfig("no_belief_update", belief_update=False)
NO_ADAPTIVE_SELECTION = MindConfig("no_adaptive_selection", adaptive_selection=False)
NO_FALSIFIER = MindConfig("no_falsifier", falsifier=False)
VARIANTS = {c.variant: c for c in (FULL, NO_BELIEF_UPDATE, NO_ADAPTIVE_SELECTION, NO_FALSIFIER)}


class ConclusionKind(str, Enum):
    LAW = "law"
    NO_DEPENDENCE = "no_dependence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNIDENTIFIABLE_PASSIVE_ASSOCIATION = "unidentifiable_passive_association"
    INDISTINGUISHABLE = "indistinguishable"
    REFUSED = "refused"


@dataclass(frozen=True)
class FittedLaw:
    """ln y = intercept + sum b_i ln x_i + sum c_j (ln x_j)^2 (the leading rival's least-squares fit)."""

    hypothesis_id: str
    intercept: float
    linear: Mapping[str, float]
    quadratic: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"hypothesis_id": self.hypothesis_id, "intercept": round(self.intercept, 12),
                "linear": {k: round(v, 12) for k, v in sorted(self.linear.items())},
                "quadratic": {k: round(v, 12) for k, v in sorted(self.quadratic.items())}}


@dataclass(frozen=True)
class MindConclusion:
    kind: ConclusionKind
    reason: str
    laws: tuple[FittedLaw, ...] = ()
    leading_status: str = ""
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONCLUSION_SCHEMA, "kind": self.kind.value, "reason": self.reason,
                "laws": [law.to_dict() for law in self.laws], "leading_status": self.leading_status,
                "diagnostics": dict(self.diagnostics)}


@dataclass
class MindRun:
    trace: dict[str, Any]
    conclusion: MindConclusion
    competition: HypothesisCompetition


def initial_design(problem: ExperimentalProblem, seed: int) -> list[dict[str, float]]:
    """A space-filling start (the rivals cannot predict anything before data) plus replicates for the noise estimate."""
    d = len(problem.inputs)
    replicates = min(4, problem.budget // 6)
    base = min(max(d + 2, problem.budget // 4), problem.budget - replicates)
    pts = ex.lhs(problem, max(base, 1), problem.rng(seed, "initial_design"))
    return (pts + pts[:replicates])[: problem.budget]


def _authority_key(problem: ExperimentalProblem, seed: int) -> bytes:
    return hashlib.sha256(f"forge.mind.minimal.release-authority\n{problem.design_seed(seed)}".encode()).digest()


def _region_sd(problem: ExperimentalProblem, comp: HypothesisCompetition, hid: str | None) -> float | None:
    if hid is None or comp.rivals[hid].fitted is None or not comp.rivals[hid].fitted.fit_ok:
        return None
    _, sdm, _ = comp.model.predict_many(comp.rivals[hid].fitted, problem.region_points(), comp.covmodels)
    return float(np.sqrt(np.mean(sdm ** 2)))


def run_mind(problem: ExperimentalProblem, observe: Callable[[Mapping[str, float], str], Mapping[str, float]], *,
             seed: int = 0, config: MindConfig = FULL, proposals: Sequence[tuple[Mapping[str, Any], str, str]] = (),
             suggestions: Sequence[ExternalSuggestion] = (), ledger_campaign: str | None = None) -> MindRun:
    """Run the closed loop on one problem.  ``observe(settings, query_ref)`` returns the observation (every input, every
    covariate, the observable) or raises :class:`ObservationRefused`."""
    comp = HypothesisCompetition(problem, seed=seed, authority_key=_authority_key(problem, seed),
                                 campaign_id=f"mind-{problem.design_seed(seed)[:16]}", falsify=config.falsifier)
    for payload, kind, pid in proposals:
        comp.ingest_proposal(payload, proposer_kind=kind, proposer_id=pid)
    ledger = MultiplicityLedger(ledger_campaign) if ledger_campaign else None
    if ledger is not None:
        ledger.strategy(MIND_ID, MIND_VERSION)
        ledger.seed(problem.design_seed(seed))
        ledger.count("generated", len(comp.rivals))
        ledger.count("deduplicated", len(comp.rivals))
        ledger.count("admitted", len(comp.rivals))
    initial = initial_design(problem, seed)
    fixed = ex.lhs(problem, max(problem.budget - len(initial), 1), problem.rng(seed, "fixed_policy"))
    cand_rng = problem.rng(seed, "candidates")
    suggested = [ex.from_suggestion(s) for s in suggestions]
    steps: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    observations: list[dict[str, float]] = []
    previous, spent = GENESIS, 0
    refusal: dict[str, Any] | None = None
    inapplicable: str | None = None
    final_stop = None
    while True:
        prior_view = comp.view(budget_spent=spent)
        prior_digest = view_digest(prior_view)
        posterior = comp.weights()
        used = posterior if config.belief_update else comp.weights(prior_only=True)
        lead = comp.leading(posterior)
        fprops: list[fz.FalsificationProposal] = []
        if spent < len(initial):
            phase, policy = False, "initial_design"
            chosen = ex.candidate(initial[spent], ActionFamily.EXPLORE, "initial_design", "design",
                                  "space-filling start and replicates; no rival can predict before evidence exists")
            selection = ex.Selection(chosen, (), dict(used), comp.model.basis_digest(comp.rows), policy, None)
        elif not config.adaptive_selection:
            phase, policy = False, "fixed_space_filling"
            chosen = ex.candidate(fixed[(spent - len(initial)) % len(fixed)], ActionFamily.EXPLORE, "fixed_space_filling",
                                  "design", "matched fixed policy: the next point of a preset space-filling design")
            selection = ex.Selection(chosen, (), dict(used), comp.model.basis_digest(comp.rows), policy, None)
        else:
            phase, policy = True, "expected_discrimination_plus_precision"
            pool = ex.adaptive_candidates(problem, cand_rng, comp, suggested) if used else []
            if config.falsifier and used:
                fprops = fz.propose(problem, comp, used, pool)
                pool += [fp.candidate for fp in fprops]
            if used:
                selection = ex.select(problem, comp, pool, used, policy)
            else:                                        # no rival can be fitted yet: keep exploring, matched to the start
                chosen = ex.candidate(fixed[(spent - len(initial)) % len(fixed)], ActionFamily.EXPLORE, "no_fitted_rival",
                                      "design", "no rival is fitted yet; continue the space-filling design")
                selection = ex.Selection(chosen, (), {}, comp.model.basis_digest(comp.rows), "no_fitted_rival", None)
        stop = decide(budget_remaining=problem.budget - spent, inapplicable=inapplicable,
                      has_candidate=selection.selected is not None, adaptive_phase=phase,
                      leading_weight=posterior.get(lead) if lead else None, region_sd=_region_sd(problem, comp, lead),
                      max_utility=selection.max_utility, precision=PRECISION)
        if stop.kind is not StopKind.CONTINUE:
            final_stop = stop
            break
        settings = dict(selection.selected.settings)
        query_ref = f"mind-{spent:03d}-{selection.selected.candidate_id[:12]}"
        tested = sorted(posterior, key=lambda h: (-posterior[h], h))[:MAX_SEALED_PREDICTIONS]
        preds = comp.predictions(settings, query_ref, tested)
        seals = comp.seal(query_ref, settings, preds, {h: posterior[h] for h in tested})
        mix = {h: posterior[h] for h in tested}
        pre_result = {"query_ref": query_ref, "settings": settings,
                      "predictions": {h: p.to_dict() for h, p in sorted(preds.items())},
                      "mixture_weights": {h: round(w, 12) for h, w in sorted(mix.items())},
                      "falsifiers": seals, "expected_cost": float(problem.query_cost)}
        prediction_seal_digest = digest(pre_result)
        try:
            obs = dict(observe(settings, query_ref))
        except ObservationRefused as exc:
            refusal = {"query_index": spent, "budget": bool(exc.budget), "message": str(exc)[:300]}
            final_stop = decide(budget_remaining=0 if exc.budget else problem.budget - spent, inapplicable=None if exc.budget
                                else f"the world refused the query: {exc}", has_candidate=True, adaptive_phase=False,
                                leading_weight=None, region_sd=None, max_utility=None, precision=PRECISION)
            break
        execution = {"query_ref": query_ref, "settings": settings, "observation_digest": digest(obs)}
        executions.append(execution)
        observations.append(obs)
        spent += 1
        try:
            row, item, verdicts = comp.admit(query_ref, settings, obs)
        except OutcomeModelRefused as exc:
            inapplicable = str(exc)
            row, item, verdicts = None, None, []
        y = float(obs.get(problem.observable, float("nan")))
        score = (mixture_logscore(preds, mix, math.log(y)) if y > 0 and math.isfinite(y)
                 else {"available": False, "reason": "non-positive observation: no ln-scale score"})
        if ledger is not None:
            ledger.count("escrow_queries")
            if phase:
                ledger.count("adaptive_decisions")
            for v in verdicts:
                ledger.tested(v["hypothesis_id"])
                if v["after"] == HypothesisStatus.REFUTED.value and v["before"] != HypothesisStatus.REFUTED.value:
                    ledger.count("eliminated")
        post_digest = view_digest(comp.view(budget_spent=spent))
        rec = step_record(step=spent - 1, previous=previous, prior_state_digest=prior_digest, policy=policy,
                          selection=selection.summary(), falsifier_proposals=[fp.to_dict() for fp in fprops],
                          pre_result=pre_result, prediction_seal_digest=prediction_seal_digest, execution=execution,
                          evidence=None if item is None else {"evidence_digest": item.content_digest,
                                                               "exposure_sequence": item.exposure_sequence,
                                                               "uncertainty": item.uncertainty,
                                                               "noise": comp.noise.to_dict()},
                          verdicts=verdicts, posterior_state_digest=post_digest, stop=stop.to_dict(),
                          prediction_score=score)
        steps.append(rec)
        previous = rec["record_digest"]
    conclusion = conclude(problem, comp, inapplicable=inapplicable)
    multiplicity = None
    if ledger is not None:
        if conclusion.kind is ConclusionKind.LAW:
            lead_id = conclusion.laws[0].hypothesis_id
            ledger.tested(lead_id)
            from ...claims.multiplicity import promote  # noqa: PLC0415
            multiplicity = {"promoted": promote(f"conclusion:{lead_id}", lead_id, ledger).hypothesis_id}
        ctx = ledger.close()
        multiplicity = {**(multiplicity or {}), "family_size": ctx.family_size, "context_digest": ctx.digest,
                        "statement": ctx.statement()}
    trace = {"schema": TRACE_SCHEMA, "mind": f"{MIND_ID}@{MIND_VERSION}", "config": config.to_dict(), "seed": seed,
             "problem": problem.to_dict(), "problem_digest": problem.digest, "steps": steps, "executions": executions,
             "observations": observations, "refusal": refusal,
             "final_stop": None if final_stop is None else final_stop.to_dict(),
             "conclusion": conclusion.to_dict(), "final_state": comp.view(budget_spent=spent),
             "registry": {"head": comp.registry.head, "entries": len(comp.registry.entries),
                          "verdicts": list(comp.verdict_digests)},
             "multiplicity": multiplicity}
    return MindRun(trace, conclusion, comp)


def replay(trace: Mapping[str, Any], problem: ExperimentalProblem, *, config: MindConfig | None = None,
           proposals: Sequence[tuple[Mapping[str, Any], str, str]] = ()) -> dict[str, Any]:
    """Exact reasoning-path replay: re-run the Mind on the recorded observations (no world is queried)."""
    if problem.digest != trace["problem_digest"]:
        return {"status": "DIVERGED", "detail": "another problem than the trace's"}
    cfg = config or VARIANTS[trace["config"]["variant"]]
    observer = ReplayObserver(trace["executions"], trace["observations"], trace.get("refusal"))
    try:
        again = run_mind(problem, observer, seed=int(trace["seed"]), config=cfg, proposals=proposals)
    except ReplayRefused as exc:
        chain = verify_chain(trace["steps"])
        if chain:
            return {"status": "CHAIN_BROKEN", "steps": len(trace["steps"]), "first_divergence": None,
                    "detail": "; ".join(chain[:3])}
        return {"status": "DIVERGED", "steps": len(trace["steps"]), "first_divergence": observer.calls, "detail": str(exc)}
    return compare(trace, again.trace).to_dict()


# ---------------------------------------------------------------------------------------------------- the conclusion
def _law(comp: HypothesisCompetition, hid: str) -> FittedLaw:
    f = comp.rivals[hid].fitted
    s = f.structure
    names = list(s.linear) + list(s.quadratic)
    coef = {n: float(c) for n, c in zip(names[:len(s.linear)], f.coef[:len(s.linear)])}
    quad = {n: float(c) for n, c in zip(s.quadratic, f.coef[len(s.linear):])}
    intercept = f.ybar - float(np.dot(f.coef, f.means)) if f.p else f.ybar
    return FittedLaw(hid, intercept, coef, quad)


def conclude(problem: ExperimentalProblem, comp: HypothesisCompetition, *, inapplicable: str | None = None) -> MindConclusion:
    if inapplicable:
        return MindConclusion(ConclusionKind.REFUSED, inapplicable)
    w = comp.weights()
    diag: dict[str, Any] = {"evidence": len(comp.rows), "noise": comp.noise.to_dict(),
                            "refuted": sorted(h for h, r in comp.rivals.items() if r.hypothesis.status is HypothesisStatus.REFUTED),
                            "extrapolates": problem.extrapolates}
    if not w:
        return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, "no rival is both fitted and unrefuted", diagnostics=diag)
    if diag["refuted"]:
        # survivorship of the untested: once tested rivals were refuted, a rival that never faced a decisive test does
        # not inherit their standing (found on development worlds: refuting the tested leaders left untested rivals that
        # use a passive covariate holding the posterior, and the conclusion read association into them)
        tested = {h: v for h, v in w.items() if comp.faced_decisive_test(h)}
        diag["untested_set_aside"] = sorted(set(w) - set(tested))
        z = sum(tested.values())
        if z <= 0:
            return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, "every rival that faced a decisive test was refuted; "
                                  "the untested rivals have not earned standing", diagnostics=diag)
        w = {h: v / z for h, v in tested.items()}
    for cov in problem.covariates:
        model = comp.covmodels.get(cov)
        diag[f"settable_r2:{cov}"] = None if model is None else round(model.r2, 9)
        if model is not None and model.r2 >= COPY_R2:
            diag[f"copy:{cov}"] = "set aside: a function of the settable inputs, which identify the interventional dependence"
            w = {h: v for h, v in w.items() if cov not in comp.rivals[h].structure.linear}
            z = sum(w.values())
            w = {h: v / z for h, v in w.items()} if z > 0 else {}
    if not w:
        return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, "no rival remains without the copied covariate",
                              diagnostics=diag)
    # no association is read from a structure that does not fit: a misfitting family can absorb its misfit into any
    # covariate (found on development worlds: after refutations, a lone misfitting survivor that used u1 read as
    # confounding in worlds where u1 is irrelevant)
    first = max(sorted(w), key=lambda h: w[h])
    first_sd = math.sqrt(comp.rivals[first].fitted.s2)
    if comp.noise.upper95 is not None and first_sd > 2.0 * comp.noise.upper95:
        diag["leading"], diag["fit_sd"] = first, round(first_sd, 9)
        return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, "the leading rival does not fit to within the replicate "
                              "noise: the rivals entertained do not contain the dependence",
                              leading_status=comp.rivals[first].hypothesis.status.value, diagnostics=diag)
    for cov in problem.covariates:
        if f"copy:{cov}" in diag:
            continue
        pi = sum(v for h, v in w.items() if cov in comp.rivals[h].structure.linear)
        diag[f"inclusion:{cov}"] = round(pi, 9)
        if pi < ASSOCIATION_INCLUSION:
            continue
        return MindConclusion(ConclusionKind.UNIDENTIFIABLE_PASSIVE_ASSOCIATION,
                              f"the observable is associated with the passive covariate {cov} (inclusion {pi:.3f}), which varies "
                              "independently of every settable input; no admissible experiment sets it, so its causal effect "
                              "cannot be separated from a hidden common cause", diagnostics=diag)
    settable = {x.name for x in problem.inputs}
    p_null = sum(v for h, v in w.items() if not set(comp.rivals[h].structure.linear) & settable)
    diag["p_null"] = round(p_null, 9)
    if p_null >= NULL_DECISION:
        return MindConclusion(ConclusionKind.NO_DEPENDENCE, f"rivals using no settable input hold {p_null:.3f} of the "
                              "posterior", diagnostics=diag)
    lead = max(sorted(w), key=lambda h: w[h])
    status = comp.rivals[lead].hypothesis.status.value
    diag["leading"] = lead
    diag["leading_weight"] = round(w[lead], 9)
    region = problem.region_points()
    model = comp.model
    lf = comp.rivals[lead].fitted
    lm, lsd, _ = model.predict_many(lf, region, comp.covmodels)
    region_sd = float(np.sqrt(np.mean(lsd ** 2)))
    disagreement = 0.0
    for h, v in w.items():
        if h != lead and v >= 1e-3:
            hm, _, _ = model.predict_many(comp.rivals[h].fitted, region, comp.covmodels)
            disagreement += v * float(np.mean((hm - lm) ** 2))
    disagreement = math.sqrt(disagreement)
    diag["region_sd"] = round(region_sd, 9)
    diag["model_disagreement"] = round(disagreement, 9)
    s_fit = math.sqrt(lf.s2)
    diag["fit_sd"] = round(s_fit, 9)
    if comp.noise.upper95 is not None and s_fit > 2.0 * comp.noise.upper95:
        return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, "the leading rival does not fit to within the replicate "
                              "noise: the rivals entertained do not contain the dependence", leading_status=status, diagnostics=diag)
    if problem.extrapolates:
        box_pts = ex.lhs(problem, 24, problem.rng(0, "box_probe"))
        lm_box, lsd_box, _ = model.predict_many(lf, box_pts, comp.covmodels)
        lead_box_sd = float(np.sqrt(np.mean(lsd_box ** 2)))
        diag["leading_box_sd"] = round(lead_box_sd, 9)
        for h in sorted(w, key=lambda h: (-w[h], h)):
            if h == lead or w[h] < PRESERVE_WEIGHT or lead_box_sd > PRECISION:
                continue
            hm_box, hsd_box, _ = model.predict_many(comp.rivals[h].fitted, box_pts, comp.covmodels)
            hm_reg, _, _ = model.predict_many(comp.rivals[h].fitted, region, comp.covmodels)
            inbox = float(np.sqrt(np.mean((hm_box - lm_box) ** 2)))
            outside = float(np.sqrt(np.mean((hm_reg - lm) ** 2)))
            # both rivals are pinned down inside the box, agree there to within the noise, and differ in the region
            if float(np.sqrt(np.mean(hsd_box ** 2))) <= PRECISION and inbox <= s_fit and outside > 3 * PRECISION:
                diag["preserved_rival"] = {"hypothesis_id": h, "inbox_rms": round(inbox, 9), "region_rms": round(outside, 9)}
                return MindConclusion(ConclusionKind.INDISTINGUISHABLE, "two rivals agree inside the box and diverge in the "
                                      "region; no admissible experiment reaches the region, so both are preserved",
                                      laws=(_law(comp, lead), _law(comp, h)), leading_status=status, diagnostics=diag)
        return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, "the region of use leaves the box every experiment can "
                              "reach; the in-box evidence does not determine the dependence there", leading_status=status,
                              diagnostics=diag)
    law = _law(comp, lead)
    finite = all(math.isfinite(x) and abs(x) < 600 for x in (law.intercept, *law.linear.values(), *law.quadratic.values()))
    if region_sd <= PRECISION and disagreement <= PRECISION and not finite:
        return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, "the leading rival's fitted constants are not representable",
                              leading_status=status, diagnostics=diag)
    if region_sd <= PRECISION and disagreement <= PRECISION:
        return MindConclusion(ConclusionKind.LAW, f"the leading rival predicts the region to {region_sd:.4f} (ln) and the "
                              f"weighted rivals agree to {disagreement:.4f}", laws=(_law(comp, lead),), leading_status=status,
                              diagnostics=diag)
    return MindConclusion(ConclusionKind.INSUFFICIENT_EVIDENCE, f"precision not reached (region sd {region_sd:.4f}, rival "
                          f"disagreement {disagreement:.4f}, required {PRECISION})", leading_status=status, diagnostics=diag)


__all__ = ["COPY_R2", "ConclusionKind", "FULL", "FittedLaw", "MIND_ID", "MIND_VERSION", "MindConclusion", "MindConfig",
           "MindRun", "NO_ADAPTIVE_SELECTION", "NO_BELIEF_UPDATE", "NO_FALSIFIER", "ObservationRefused", "PRECISION",
           "VARIANTS", "conclude", "initial_design", "replay", "run_mind"]
