"""Battery blind confirmatory campaign: READINESS (Big Rocks campaign, Rock 3).  Nothing here runs a confirmatory test.

The Kirkaldy 2024 throughput-Arrhenius fade study stays NOT MET (``kirkaldy_fade.py``, docs/flagships/README.md); its
observed holdout is EXPLORATORY now.  This module prepares the NEXT campaign without exposing any confirmatory datum:

* :func:`prior_art_snapshot` -- a frozen, NOT-exhaustive snapshot of battery fade-law FAMILIES, canonicalized by
  :func:`fade_family_digest` (constants AND exponents abstracted: any power-law exponent is the same family), for the
  novelty check.  Citations are author / year / venue as recalled by the campaign designer; they were NOT verified in
  this environment and are marked so.
* :func:`hypothesis_set` -- the campaign's hypotheses (canonical ``Hypothesis`` records, kind EQUATION, PROPOSED):
  statement as a restricted expression, scope, parameters with priors (bounds; values UNKNOWN until fitted), prediction
  semantics, complexity, proposer provenance and falsifier references.
* :func:`real_preregistration` -- the machine-readable pre-registration DRAFT for the real campaign.  Its confirmatory
  dataset is named by REQUIREMENTS only (to be designated and digest-pinned by the owner): no confirmatory value exists
  in this repository.
* :func:`red_team_plan` -- the battery AttackSpace + AttackPlan, fixed before any result exists.
* :func:`dry_run` -- the WHOLE machinery on SYNTHETIC battery-like data (never the confirmatory holdout):
  hypothesis -> ExposureAuthority (durable campaign, dataset gate) -> sealed falsifiers -> multiplicity ->
  FidelityGraph screening (+ false-elimination audit) -> adjudication -> Red Team -> credibility -> Discovery Passport.
* :func:`readiness` -- the owner-approval gate record (``BATTERY_CONFIRMATORY_READINESS.md``).
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from engcore.blindfold.expression import add, c, evaluate, mul, pw, v
from engcore.claims.novelty import (
    Canonicalizer,
    EquivalenceSpec,
    PriorArtEntry,
    PriorArtSnapshot,
    register_canonicalizer,
    register_evaluator,
)
from engcore.sria.decision import (
    Hypothesis,
    HypothesisKind,
    HypothesisParameter,
    HypothesisPrediction,
    ProposalProvenance,
)

FAMILY_CANONICALIZER = "forge.battery.fade_family/1"
FALSIFIER_K = 3.0
RESOLUTION_RULE = {"relative_cap": 0.25, "uncertainty_multiplier": 1.2, "absolute_floor": 0.004}
OBSERVABLE, UNIT = "capacity_fade_fraction", "1"
T_REF = 298.15


def _ex(e: dict) -> dict:
    return {"exp": e}


def _arr(b: float) -> dict:
    """exp(b * (1/T - 1/T_REF)) written as exp(b T^-1 - b/T_REF)."""
    return _ex(add(mul(c(b), pw(v("T"), -1.0)), c(-b / T_REF)))


# ---------------------------------------------------------------------------- family canonicalization


def _canon(node: Mapping[str, Any]) -> Any:
    (op, arg), = node.items()
    if op == "const":
        return "C"
    if op == "var":
        return ["pow", ["var", arg], "C"]                     # x == x^1: an exponent is a constant, abstracted
    if op == "pow":
        base = _canon(arg[0])
        return base if base[:1] == ["pow"] else ["pow", base, "C"]
    if op in ("add", "mul"):
        kids = []
        for k in (_canon(a) for a in arg):
            kids.extend(k[1] if isinstance(k, list) and k[:1] == [op] else [k])
        kids = [k for k in kids if k != "C"] + (["C"] if any(k == "C" for k in kids) else [])
        return [op, sorted(kids, key=lambda x: json.dumps(x, sort_keys=True))] if len(kids) > 1 else kids[0]
    if op == "exp":
        inner = _canon(arg)
        if isinstance(inner, list) and inner[:1] == ["add"] and "C" in inner[1]:
            rest = [k for k in inner[1] if k != "C"]           # exp(f + C) = C' exp(f): the offset joins the coefficient
            inner = rest[0] if len(rest) == 1 else ["add", rest]
        return "C" if inner == "C" else [op, inner]
    if op in ("log", "neg"):
        inner = _canon(arg)
        return "C" if inner == "C" else [op, inner]
    if op == "piecewise":
        return ["piecewise", _canon(arg["if_below"][0]), _canon(arg["then"]), _canon(arg["else"])]
    raise ValueError(f"unknown node {op!r}")


def fade_family_digest(expr: Mapping[str, Any]) -> str:
    """The FAMILY of a fade law: its structure with every constant -- coefficient, exponent, offset -- abstracted."""
    return hashlib.sha256(json.dumps(_canon(expr), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


register_canonicalizer(FAMILY_CANONICALIZER, fade_family_digest)
CANONICALIZER = Canonicalizer.resolve(FAMILY_CANONICALIZER)
FADE_EVALUATOR = "forge.battery.fade_eval/1"


def _fade_eval(expr: Mapping[str, Any], point: Mapping[str, float]) -> float:
    try:
        return float(evaluate(expr, point))
    except (ArithmeticError, KeyError, ValueError, TypeError):
        return float("nan")                                     # undecidable at this probe: never "not equivalent"


register_evaluator(FADE_EVALUATOR, _fade_eval)
#: numeric equivalence (up to a constant factor) on probes inside the applicability box; t is the calendar time [h]
EQUIVALENCE = EquivalenceSpec(FADE_EVALUATOR, _fade_eval, ({"q": 150.0, "T": 288.15, "t": 500.0}, {"q": 600.0, "T": 303.15, "t": 2000.0},
                                                            {"q": 950.0, "T": 313.15, "t": 4000.0}), rel_tol=1e-6)


# ---------------------------------------------------------------------------- prior art (frozen, NOT exhaustive)

PRIOR_ART_FAMILIES: tuple[tuple[str, dict, str], ...] = (
    ("arrhenius_throughput_linear", mul(c(1e-4), v("q"), _arr(-3600.0)),
     "Kirkaldy et al. 2024 (Zenodo 10637534) study model; throughput-linear Arrhenius (engcore.domains.battery.throughput_fade)"),
    ("power_law_throughput_arrhenius", mul(c(1e-3), pw(v("q"), 0.55), _arr(-3800.0)),
     "Wang et al. 2011, J. Power Sources, cycle-life model of graphite-LiFePO4 cells (power law in Ah throughput x Arrhenius)"),
    ("sqrt_time_calendar_sei", mul(c(1e-3), pw(v("t"), 0.5), _arr(-4000.0)),
     "Broussely et al. 2001, J. Power Sources, SEI growth ~ t^0.5 calendar ageing"),
    ("combined_calendar_cycle", add(mul(c(1e-3), pw(v("t"), 0.75), _arr(-4000.0)), mul(c(1e-3), pw(v("q"), 0.5))),
     "Schmalstieg et al. 2014, J. Power Sources, holistic ageing model (calendar t^0.75 + cycle Q^0.5)"),
    ("two_mechanism_arrhenius_throughput", mul(v("q"), add(mul(c(1e-4), _arr(-5000.0)), mul(c(1e-4), _arr(6000.0)))),
     "Waldmann et al. 2014, J. Power Sources, temperature-dependent ageing mechanisms (plating below / SEI above ~25 C)"),
    ("power_plus_linear_throughput", add(mul(c(1e-3), pw(v("q"), 0.5), _arr(-4000.0)), mul(c(1e-5), v("q"), _arr(-4000.0))),
     "SEI (sqrt) + linear side-reaction throughput models, common in the cycle-ageing literature"),
    ("double_exponential_capacity", add(mul(c(1.0), _ex(mul(c(-1e-4), v("q")))), mul(c(-0.1), _ex(mul(c(1e-3), v("q"))))),
     "He et al. 2011, J. Power Sources, empirical double-exponential capacity-fade model"),
)


def prior_art_snapshot() -> PriorArtSnapshot:
    entries = tuple(PriorArtEntry(name, fade_family_digest(expr), ref, expr) for name, expr, ref in PRIOR_ART_FAMILIES)
    return PriorArtSnapshot(
        "battery-fade-laws/2026-10", ("equation",), entries,
        sources=("campaign designer's literature recall (citations NOT verified in this environment)",),
        coverage_criteria=("capacity-fade law FAMILIES (calendar / cycle / combined; Arrhenius, power-law, sqrt, two-mechanism, "
                           "exponential) known to the designer; NOT a systematic review, NOT exhaustive -- novelty against it is "
                           "POSSIBLY_NOVEL at most and must be re-checked against a systematic search before any novelty claim"),
        canonicalizer_id=FAMILY_CANONICALIZER, equivalence=EQUIVALENCE.to_dict())


# ---------------------------------------------------------------------------- hypotheses

#: (id, statement, builder(theta) -> expression, parameter specs [(name, unit, low, high)], scope, note)
HYPOTHESES: tuple[tuple[str, str, Callable[[np.ndarray], dict], tuple[tuple[str, str, float, float], ...], str], ...] = (
    ("bat-h0-arrhenius-linear", "fade = k q exp(-Ea/R (1/T - 1/Tref)) -- the Kirkaldy probe law, kept as the reference competitor",
     lambda th: mul(c(th[0]), v("q"), _arr(-th[1])), (("k", "1/Ah", 1e-7, 1e-2), ("Ea_over_R", "K", 0.0, 2.4e4)),
     "the NOT MET reference: re-tested only as a competitor, never re-scored on its observed holdout"),
    ("bat-h1-two-mechanism", "fade = q [A1 exp(-B1 (1/T - 1/Tref)) + A2 exp(+B2 (1/T - 1/Tref))] -- SEI above, plating below",
     lambda th: mul(v("q"), add(mul(c(th[0]), _arr(-th[1])), mul(c(th[2]), _arr(th[3])))),
     (("A1", "1/Ah", 1e-8, 1e-2), ("B1", "K", 0.0, 2.4e4), ("A2", "1/Ah", 1e-9, 1e-2), ("B2", "K", 0.0, 2.4e4)),
     "non-monotone temperature dependence (a minimum of the fade rate inside the window)"),
    ("bat-h2-power-law", "fade = B q^z exp(-Ea/R (1/T - 1/Tref))",
     lambda th: mul(c(th[0]), pw(v("q"), th[2]), _arr(-th[1])), (("B", "1/Ah^z", 1e-8, 1.0), ("Ea_over_R", "K", 0.0, 2.4e4),
                                                                  ("z", "1", 0.2, 1.5)),
     "sub-linear throughput dependence (z selected by the pre-registered FidelityGraph screen)"),
    ("bat-h3-sqrt-plus-cold-plating", "fade = a q^0.5 exp(-Ea/R (1/T - 1/Tref)) + b q exp(-g T)",
     lambda th: add(mul(c(th[0]), pw(v("q"), 0.5), _arr(-th[1])), mul(c(th[2]), v("q"), _ex(mul(c(-th[3]), v("T"))))),
     (("a", "1/Ah^0.5", 1e-8, 1.0), ("Ea_over_R", "K", 0.0, 2.4e4), ("b", "1/Ah", 1e-9, 1e3), ("g", "1/K", 0.0, 0.3)),
     "SEI (sqrt) plus plating that grows exponentially as T falls"),
)


def _template(th_len: int) -> np.ndarray:
    return np.ones(th_len)


def hypothesis_set(confirmatory_conditions: tuple[Mapping[str, Any], ...] = ({"profile": "confirmatory", "point": "designated"},)) \
        -> tuple[Hypothesis, ...]:
    out = []
    for hid, statement, build, params, note in HYPOTHESES:
        expr = build(_template(len(params)))
        out.append(Hypothesis(
            hypothesis_id=hid, model_ref=f"battery-fade:{hid}", kind=HypothesisKind.EQUATION, statement=statement,
            statement_payload={"expression": expr, "variables": {"q": "Ah discharge throughput", "T": "K cell temperature"},
                               "parameter_priors": {n: {"unit": u, "low": lo, "high": hi} for n, u, lo, hi in params}},
            structure_digest=fade_family_digest(expr),
            predictions=tuple(HypothesisPrediction(OBSERVABLE, UNIT, f"cond:{json.dumps(dict(cc), sort_keys=True)}",
                                                   "capacity fade fraction at the declared confirmatory condition")
                              for cc in confirmatory_conditions),
            parameters=tuple(HypothesisParameter(n, u) for n, u, _lo, _hi in params),     # values UNKNOWN until fitted
            complexity=len(params), scope_ref="T 10-40 C; throughput 0-1000 Ah; constant-current and drive-cycle profiles",
            proposal=ProposalProvenance("human", "forge-battery-campaign-design", note=note),
            falsifier_refs=tuple(f"{hid}-f{n + 1}@v1" for n in range(len(confirmatory_conditions)))))
    return tuple(out)


def hypothesis_registry_digest(hs: tuple[Hypothesis, ...]) -> str:
    return hashlib.sha256(json.dumps(sorted([h.hypothesis_id, h.content_digest, h.claim_digest] for h in hs)).encode()).hexdigest()


# ---------------------------------------------------------------------------- the real-campaign pre-registration (DRAFT)


def _sections(hs: tuple[Hypothesis, ...], *, exploratory: Mapping[str, Any], confirmatory: Mapping[str, Any],
              declared_observation_uncertainty: float | None = None) -> dict[str, Any]:
    return {
        "scientific_question": "Does a non-linear-in-throughput or non-monotone-in-temperature fade law predict capacity fade of "
                               "fresh, independently tested cells better than the throughput-linear Arrhenius law that was NOT MET?",
        "hypothesis_set": [{"hypothesis_id": h.hypothesis_id, "content_digest": h.content_digest, "claim_digest": h.claim_digest}
                           for h in hs],
        "primary_outcome": {"observable": OBSERVABLE, "unit": UNIT, "metric": "per-falsifier REFUTED / NOT_REFUTED / INCONCLUSIVE at "
                            "every confirmatory checkpoint, k = 3"},
        "secondary_outcomes": ["pooled RMSE of capacity fade fraction (reported, not judged)", "per-temperature bias (reported)"],
        "applicability_domain": {"temperature_C": [10, 40], "throughput_Ah": [0, 1000],
                                 "profiles": ["constant-current cycling", "drive cycle"], "chemistry": "as the exploratory cells"},
        "exploratory_data": dict(exploratory),
        "confirmatory_dataset": dict(confirmatory),
        "falsification_criteria": {
            "criterion": "prediction_deviation", "k": FALSIFIER_K,
            "resolution": dict(RESOLUTION_RULE),
            # u_obs: the measurement uncertainty the DATA AUTHORITY declares for the confirmatory instrument at designation
            # (null until then: no falsifier can be checked against the rule, verify_discipline says so)
            "declared_observation_uncertainty": declared_observation_uncertainty,
            "rule": "resolution = min(relative_cap |predicted|, max(uncertainty_multiplier k sqrt(u_pred^2 + u_obs^2), "
                    "absolute_floor)); a falsifier is sealed only where k sqrt(u_pred^2 + u_obs^2) <= resolution, otherwise "
                    "it is declared untestable WITH the rule inputs (re-checked by verify_discipline)",
            "prediction_uncertainty": "exploratory-fit residual RMS (parameter uncertainty NOT added: declared as a deviation risk)",
            "observation_uncertainty": "u_obs = the uncertainty RELEASED with the exploratory data (same instrument); a larger "
                                       "confirmatory uncertainty at release makes the verdict INCONCLUSIVE; UNKNOWN -> INCONCLUSIVE",
            "blind_spot": "with k = 3 and u_obs = 0.0015, a hypothesis predicting |fade| below about 0.018 at a condition "
                          "cannot reach a resolution there (0.25 |p| < k u_obs): small predictions are untestable by this rule, "
                          "stated before any exposure"},
        "uncertainty_treatment": "missing uncertainty stays UNKNOWN (inconclusive), never zero; model discrepancy is NOT quantified "
                                 "from a failed confirmatory test",
        "multiplicity_budget": {"max_generated_hypotheses": 16, "max_admitted_hypotheses": 4, "confirmatory_query_budget": 32},
        "selection_rule": "every pre-registered hypothesis is tested; no post-hoc selection among them; a power-law exponent is "
                          "selected ONLY by the pre-registered FidelityGraph screen on exploratory data",
        "fidelity_graph_policy": {"low": "fit on the sparse exploratory RPT subset", "high": "fit on all exploratory RPTs",
                                  "candidates": "z = 0.3 + 0.075 i, i = 0..11 (12 paired evaluations)",
                                  "admission": {"min_pairs": 10, "min_rank_correlation": 0.6, "min_decision_agreement": 0.6},
                                  "threshold": "fit RMS at most 0.004 (near band 0.001)",
                                  "audit": {"fraction": 0.5, "strata": 2, "bound": 0.2, "min_audits": 1}},
        "false_elimination_audit_rate": 0.5,
        "red_team_attack_space": {"digest": red_team_plan()["space_digest"], "plan_digest": red_team_plan()["plan_digest"]},
        "independent_confirmation": "confirmatory cells from another test campaign than the exploratory data (another lab or rig); "
                                    "solver / route agreement never counts as confirmation",
        "novelty_protocol": {"snapshot": prior_art_snapshot().digest, "canonicalizer": FAMILY_CANONICALIZER,
                             "rule": "POSSIBLY_NOVEL at most; a family in the snapshot is KNOWN_EQUIVALENT"},
        "abstention_policy": "INCONCLUSIVE verdicts are reported as such; insufficient data -> no claim",
        "stopping_rule": "stop when every confirmatory row in the pre-registered budget is released and judged, or on any "
                         "discipline violation (the campaign then becomes exploratory)",
        "compute_query_budget": {"fits": "unbounded on exploratory data", "confirmatory_releases": 32},
        "success_criteria": "a hypothesis is SURVIVING if no sealed falsifier refuted it and at least one NOT_REFUTED verdict exists; "
                            "a discovery additionally needs POSSIBLY_NOVEL, issuer-bound credibility and a SURVIVED Red Team envelope",
        "negative_result_rule": "every REFUTED and INCONCLUSIVE verdict is published with the passport; the Kirkaldy NOT MET stays",
    }


KIRKALDY_EXPLORATORY = {
    "dataset": "Kirkaldy et al. 2024, Zenodo 10637534",
    "files": {"Expt 5 - Standard Cycle Aging (Control).zip": "md5:298aa767 (pinned in big14_a_kirkaldy_fade_preregistration.json)",
              "Expt 4 - Drive Cycle Aging (Control).zip": "md5:99083707 (OBSERVED holdout of BIG 14: exploratory now)"},
    "status": "EXPLORATORY ONLY -- both archives were opened by BIG 14",
    "location": "outside this container (D:/forge-data/kirkaldy2024); not copied",
}
CONFIRMATORY_REQUIREMENTS = {
    "status": "TO_BE_DESIGNATED_BY_OWNER",
    "identity": None,
    "requirements": ["never loaded by FORGE before the seal", "cells tested by another campaign than the exploratory data",
                     "the same chemistry and observable (C/10 capacity at RPTs)", "pinned by file digest before any release",
                     "values held by a data authority and released only through the ExposureGate"],
}


def real_preregistration():
    from engcore.claims.preregistration import Preregistration
    return Preregistration("battery-blind-confirmatory", 1, _sections(hypothesis_set(), exploratory=KIRKALDY_EXPLORATORY,
                                                                      confirmatory=CONFIRMATORY_REQUIREMENTS))


# ---------------------------------------------------------------------------- Red Team plan (fixed before results)


def red_team_space():
    from engcore.claims.redteam import AttackDimension, AttackKind, AttackSpace
    return AttackSpace("battery-fade-claim", (
        AttackDimension("temperature_C", AttackKind.ENVIRONMENT, "pre-registered applicability domain", low=10.0, high=40.0, unit="degC",
                        edge_low=5.0, edge_high=45.0),
        AttackDimension("throughput_Ah", AttackKind.INPUT_PARAMETER, "pre-registered applicability domain", low=0.0, high=1000.0,
                        unit="A h", edge_high=1200.0),
        AttackDimension("route", AttackKind.MODEL_FORM, "pre-registered hypothesis set (model-form alternatives)",
                        choices=tuple(h[0] for h in HYPOTHESES)),
    ))


def red_team_plan() -> dict[str, Any]:
    from engcore.claims.redteam import AttackPlan
    space = red_team_space()
    plan = AttackPlan(space.digest, 400, "battery-blind/1", edge_interior_points=4)
    return {"space_digest": space.digest, "plan_digest": plan.digest, "method": plan.method,
            "dimensions": [d.name for d in space.dimensions]}


# ---------------------------------------------------------------------------- the synthetic dry run


def _truth(theta: np.ndarray, q: float, T: float) -> float:
    return float(evaluate(HYPOTHESES[1][2](theta), {"q": q, "T": T}))


SYNTH_U_OBS = 0.0015                                          # the synthetic instrument's declared measurement uncertainty
SYNTH_TRUTH = np.array([4e-5, 6000.0, 2e-6, 9000.0])          # a two-mechanism law, unknown to every proposer


def synthetic_dataset(seed: int = 11) -> tuple[Any, dict[str, dict[str, Any]]]:
    """Battery-LIKE synthetic data (never a measurement): exploratory constant-current cells at 10/25/40 C, confirmatory
    drive-cycle cells at 15/32 C.  Returns (manifest, rows); rows are held by the data authority, not the proposer."""
    from engcore.claims.exposure_dataset import DatasetManifest, commit_row
    rng = random.Random(seed)
    rows: dict[str, dict[str, Any]] = {}
    expl, conf = [], []
    for temp in (10.0, 25.0, 40.0):
        for q in (100.0, 200.0, 400.0, 600.0, 800.0):
            rid = f"cc-{int(temp)}C-{int(q)}Ah"
            rows[rid] = {"value": _truth(SYNTH_TRUTH, q, temp + 273.15) + rng.gauss(0, SYNTH_U_OBS), "uncertainty": SYNTH_U_OBS,
                         "conditions": {"profile": "constant_current", "temperature_C": temp, "throughput_Ah": q}}
            expl.append(rid)
    for temp in (15.0, 32.0):
        for q in (500.0, 900.0):
            rid = f"dc-{int(temp)}C-{int(q)}Ah"
            rows[rid] = {"value": _truth(SYNTH_TRUTH, q, temp + 273.15) + rng.gauss(0, SYNTH_U_OBS), "uncertainty": SYNTH_U_OBS,
                         "conditions": {"profile": "drive_cycle", "temperature_C": temp, "throughput_Ah": q}}
            conf.append(rid)
    dataset_id = "synthetic-battery-dry-run"
    salts = {rid: rng.getrandbits(128).to_bytes(16, "big") for rid in rows}      # held by the data authority with the rows
    for rid, row in rows.items():
        row["salt"] = salts[rid].hex()
    manifest = DatasetManifest(dataset_id, "1", f"engcore flagship synthetic generator (seed {seed})",
                               "one row per (profile, temperature, throughput) checkpoint", {"exploratory": expl, "confirmatory": conf},
                               row_commitments={rid: commit_row(dataset_id, rid, row, salts[rid]) for rid, row in rows.items()},
                               conditions={rid: row["conditions"] for rid, row in rows.items()})
    return manifest, rows


def _fit(build: Callable[[np.ndarray], dict], params, data: list[tuple[float, ...]]) -> tuple[np.ndarray, float]:
    lo = np.array([p[2] for p in params])
    hi = np.array([p[3] for p in params])
    scale = np.where(hi > 0, hi, 1.0)

    def resid(x):
        th = x * scale
        return np.array([evaluate(build(th), {"q": q, "T": T}) - y for q, T, y, *_u in data])
    x0 = np.sqrt(np.maximum(lo, 1e-12) * hi) / scale
    sol = least_squares(resid, x0, bounds=(lo / scale, hi / scale))
    r = resid(sol.x)
    return sol.x * scale, float(np.sqrt(np.mean(r ** 2)))


def _computation_receipt(output_digest: str, node_id: str, data: list, *, output: str = "prediction") -> Any:
    """The dry-run harness's OWN execution record of a fit (it is the executor: an EXECUTOR-role issuer attests it).
    Inputs are the digest of the exploratory data the fit consumed; the single output (``output``) is the digest of what
    the fit produced (the prediction, or an abstention's rule inputs)."""
    from engcore.execution.orchestration.resources import ResourceUsage
    from engcore.system_runtime.records import NodeReceipt, NodeStatus

    def h(x: Any) -> str:
        return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()
    inputs = h([[float(a) for a in row] for row in data])
    return NodeReceipt(node_id, NodeStatus.SUCCEEDED, h("battery-dry-run plan"), h("battery-dry-run request"), h(node_id),
                       h("battery_blind._fit/least_squares"), h([node_id, inputs]), (("exploratory_data", inputs),),
                       ((output, output_digest),), (), (), (), h("state-before"), h("state-after"), ResourceUsage(), "", (), 1)


def dry_run(workdir: str, *, seed: int = 11) -> dict[str, Any]:
    """The full chain on synthetic data in a TEST-profile authority ledger.  Returns the run report (no claim)."""
    import pathlib

    from engcore.authority import (
        AuthorityLedger,
        EphemeralKeyProvider,
        FileLedgerStore,
        Role,
    )
    from engcore.claims.attestation import attest_receipt, attest_record
    from engcore.claims.credibility_vector import (
        ClaimNode,
        DecisionRequirement,
        Factor,
        FactorClaim,
        RiskClass,
        assess_credibility,
        record_digest,
    )
    from engcore.claims.discovery_passport import STANDARD_LIMITS, DiscoveryPassport
    from engcore.claims.durable_campaign import DurableCampaign
    from engcore.claims.exposure_dataset import (
        ExposureGate,
        approve_confirmatory,
        declare_untestable,
        register_manifest,
        rule_inputs_digest,
        rule_resolution,
        structured_rule,
        verify_discipline,
    )
    from engcore.claims.falsification import CriterionKind, EvidenceSource, Falsifier
    from engcore.claims.novelty import check_novelty
    from engcore.claims.preregistration import Preregistration, freeze
    from engcore.claims.redteam import (
        AttackPlan,
        ClaimSubject,
        Route,
        RouteResult,
        Sense,
        run_red_team,
    )
    from engcore.credibility.evidence_graph import EvidenceAuthority as EA
    from engcore.credibility.evidence_graph import (
        EvidenceEdge,
        EvidenceGraph,
        EvidenceNode,
        EvidenceRelation,
    )
    from engcore.design.fidelity_graph import (
        EliminationLedger,
        FalseEliminationPolicy,
        FidelityGraphRefusal,
        FidelityLink,
        FidelityNode,
        LinkAdmissionPolicy,
        PairedEvaluation,
        ScreeningOutcome,
        ValidityDomain,
        draw_audit,
        measure_link,
        record_audit,
        screen,
    )
    from engcore.design.fidelity_graph import (
        Sense as FSense,
    )
    from engcore.design.multifidelity import standard_ladder
    from engcore.system_runtime.records import ApplicabilityReport

    work = pathlib.Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    keys = EphemeralKeyProvider()
    root = keys.signer("root")
    store = FileLedgerStore(work / "authority.jsonl")
    led = AuthorityLedger.create(store, ledger_id="battery-dry-run", profile="test", root=root)
    for issuer, roles in (("exposure", [Role.EXPOSURE]), ("owner", [Role.OWNER]), ("exec", [Role.EXECUTOR]),
                          ("app", [Role.APPLICABILITY]), ("rt", [Role.RED_TEAM])):
        led.register_issuer(root, issuer, keys.signer(issuer).possession("battery-dry-run", issuer), roles=roles)
    ctx = hashlib.sha256(b"battery-blind dry run (synthetic)").hexdigest()
    camp = DurableCampaign.start(led, keys, issuer_id="exposure", campaign_id="battery-dry-run", authority_id="synthetic-lab",
                                 context_digest=ctx, resolution_scales={(OBSERVABLE, UNIT): 0.1})
    manifest, rows = synthetic_dataset(seed)
    register_manifest(camp, led, keys.signer("exposure"), "exposure", manifest)
    snapshot = prior_art_snapshot()
    camp.seal_prior_art(snapshot)
    # the confirmatory DESIGN (where rows will be measured) is public in the manifest; the rows themselves go only to the gate
    conf_conditions = tuple(dict(manifest.conditions[r]) for r in manifest.partitions["confirmatory"])
    hs = {h.hypothesis_id: h for h in hypothesis_set(tuple({"profile": cc["profile"], "temperature_C": cc["temperature_C"],
                                                             "throughput_Ah": cc["throughput_Ah"]} for cc in conf_conditions))}
    tickets = {}
    for hid, h in hs.items():
        tickets[hid] = camp.register(h)
        camp.record_proposal(h)
    camp.count("count", "generated", len(hs))
    camp.count("count", "deduplicated", len(hs))
    camp.count("count", "admitted", len(hs))
    prereg = Preregistration("battery-blind-dry-run", 1, _sections(tuple(hs.values()), exploratory={
        "dataset": manifest.dataset_id, "partition": "exploratory", "manifest_digest": manifest.digest},
        confirmatory={"dataset": manifest.dataset_id, "partition": "confirmatory", "manifest_digest": manifest.digest,
                      "identity": "synthetic (dry run)"}, declared_observation_uncertainty=SYNTH_U_OBS))
    freeze(led, keys.signer("exposure"), "exposure", prereg, campaign_id=camp.campaign_id, context_digest=ctx)
    gate = ExposureGate(camp, led, manifest=manifest, rows=rows.__getitem__, observable=OBSERVABLE, unit=UNIT)
    del rows                                                       # from here on the proposer side holds no row
    # --- exploratory data: released through the authority, then fitted
    data = []
    for rid in manifest.partitions["exploratory"]:
        item = gate.exploratory(rid)
        data.append((item.conditions["throughput_Ah"], item.conditions["temperature_C"] + 273.15, item.value, item.uncertainty))
    # --- FidelityGraph: screen power-law exponents on a sparse subset (low) against the full fit (high)
    ladder = standard_ladder()
    low = FidelityNode(ladder.rung("analytic"), "battery-fade:h2", "sparse-rpt-fit", "1")
    high = FidelityNode(ladder.rung("numerical"), "battery-fade:h2", "full-rpt-fit", "1")
    sparse = [d for d in data if d[0] in (200.0, 600.0)]
    h2 = HYPOTHESES[2]
    zs = [round(0.3 + 0.075 * i, 3) for i in range(12)]
    camp.count("count", "generated", len(zs))                      # the exponent search is part of the search scale
    camp.count("count", "deduplicated", len(zs))

    def fit_z(z, sample):
        params = (h2[3][0], h2[3][1])
        _th, rms = _fit(lambda t: h2[2](np.array([t[0], t[1], z])), params, sample)
        return rms
    pairs = [PairedEvaluation(f"z{z}", {"z": z}, fit_z(z, sparse), fit_z(z, data)) for z in zs]
    link = FidelityLink("battery.fit_rms", low, high, "fit_rms", "1", ValidityDomain({"z": (min(zs), max(zs))}, {"z": "1"}),
                        measure_link(pairs, threshold=0.004, sense=FSense.AT_MOST, near_band=0.001))
    admitted, admission_refusal = True, ""
    try:
        link = link.admit(LinkAdmissionPolicy("battery.admission", 10, 0.6, 0.6), actor="dry-run", reason="pre-registered policy")
    except FidelityGraphRefusal as exc:                            # an unadmitted link screens nothing; the reason is reported
        admitted, admission_refusal = False, str(exc)
    elim = EliminationLedger()
    decisions = []
    if admitted:
        for pe in pairs:
            d = screen(pe.candidate_key, low_value=pe.low_value, point=pe.point, link=link, low_node=low, observable="fit_rms")
            decisions.append(d)
            if d.outcome is not ScreeningOutcome.PROMOTE:
                elim.record(d, link=link, low_node=low)
        policy = FalseEliminationPolicy("battery.audit", fraction=0.5, strata=2, bound=0.2, min_audits=1)
        drawn = draw_audit(elim, link, policy)
        link, audit = record_audit(elim, link, {p.candidate_key: p.high_value for p in pairs if p.candidate_key in drawn}, policy,
                                   actor="dry-run")
    promoted_z = [float(p.candidate_key[1:]) for p in pairs if not decisions or any(
        d.candidate_key == p.candidate_key and d.outcome is ScreeningOutcome.PROMOTE for d in decisions)]
    z_best = min(promoted_z or zs, key=lambda z: fit_z(z, data))
    # --- fit every hypothesis on exploratory data; seal falsifiers at the confirmatory conditions
    # the observation uncertainty that sizes the resolution is the one the pre-registration DECLARES for the instrument
    # (confirmatory rows are never read here); a larger uncertainty at release makes the verdict INCONCLUSIVE, never a pass
    rule = structured_rule(prereg)
    u_obs_declared = float(rule["declared_observation_uncertainty"])

    def fit_receipt(hid: str, inputs: tuple) -> Any:              # the executor attests the abstention's rule inputs
        return attest_receipt(led, keys.signer("exec"), "exec", _computation_receipt(rule_inputs_digest(inputs), f"abstain-{hid}-"
                              f"{len(inputs)}-{rule_inputs_digest(inputs)[:8]}", data, output="rule_inputs"), context_digest=ctx)
    fitted: dict[str, tuple[np.ndarray, float, dict]] = {}
    sealed_refs = {}
    for hid, statement, build, params, _note in HYPOTHESES:
        if hid == "bat-h2-power-law":
            sub_params = params[:2]
            th2, rms = _fit(lambda t, b=build: b(np.array([t[0], t[1], z_best])), sub_params, data)
            th = np.array([th2[0], th2[1], z_best])
        else:
            th, rms = _fit(build, params, data)
        fitted[hid] = (th, rms, build(th))
        h = hs[hid]
        refs, dropped = [], []
        for n, cc in enumerate(conf_conditions):
            pred = float(evaluate(build(th), {"q": cc["throughput_Ah"], "T": cc["temperature_C"] + 273.15}))
            u = max(rms, 1e-6)
            rule_in = {"predicted": pred, "prediction_uncertainty": u, "observation_uncertainty": u_obs_declared}
            resolution, ku = rule_resolution(rule, **rule_in)
            if not resolution >= ku:                               # too uncertain to discriminate: recorded, never silent
                dropped.append((h.falsifier_refs[n], {**rule_in, "condition": dict(cc)}))
                continue
            f = Falsifier(f"{hid}-f{n + 1}", hid, h.content_digest, OBSERVABLE, UNIT,
                          {"profile": cc["profile"], "temperature_C": cc["temperature_C"], "throughput_Ah": cc["throughput_Ah"]},
                          EvidenceSource.MEASUREMENT_RECORD, CriterionKind.PREDICTION_DEVIATION,
                          {"k": float(rule["k"]), "predicted": pred, "prediction_uncertainty": u, "resolution": resolution})
            camp.seal(f, tickets[hid])
            refs.append({"ref": f.ref, "digest": f.digest, "predicted": pred})
        sealed_refs[hid] = refs
        if refs:
            for ref, rin in dropped:                               # per-condition abstention, with the rule inputs
                declare_untestable(camp, led, keys.signer("exposure"), "exposure", hypothesis_id=hid, content_digest=h.content_digest,
                                   falsifier_ref=ref, rule_inputs=(rin,), fit_receipt=fit_receipt(hid, (rin,)),
                                   reason="the pre-registered rule reaches no resolution at this condition")
        listed = tuple(r["ref"] for r in refs)
        if refs and listed != hs[hid].falsifier_refs:              # some planned falsifiers could not reach the resolution:
            hs[hid] = hs[hid].revise(falsifier_refs=listed)          # the record lists exactly what was sealed, BEFORE exposure
            camp.register(hs[hid], tickets[hid])
        if not refs:                                               # abstain BEFORE exposure, with the reason -- never dropped
            declare_untestable(camp, led, keys.signer("exposure"), "exposure", hypothesis_id=hid, content_digest=h.content_digest,
                               rule_inputs=tuple(rin for _ref, rin in dropped),
                               fit_receipt=fit_receipt(hid, tuple(rin for _ref, rin in dropped)),
                               reason=f"exploratory fit RMS {rms:.4g}: k*sqrt(u_pred^2+u_obs^2) exceeds every resolution the "
                                      "pre-registered rule allows at the confirmatory conditions")
    for hid in hs:
        camp.count("tested", hid)
    # --- owner approval, then the confirmatory release through the gate
    approve_confirmatory(led, keys.signer("owner"), "owner", campaign_id=camp.campaign_id, context_digest=ctx,
                         preregistration_digest=prereg.digest, manifest_digest=manifest.digest,
                         note="dry run on SYNTHETIC data: approval exercised, no real confirmatory data involved")
    for rid in manifest.partitions["confirmatory"]:
        gate.confirmatory(rid, preregistration=prereg)
    judged = {hid: camp.apply_verdicts(hs[hid]) if sealed_refs[hid] else hs[hid] for hid in hs}   # untestable: not scored
    discipline = verify_discipline(led, camp)
    # --- novelty, Red Team and credibility for every hypothesis; one passport each
    survivors = [hid for hid, h in judged.items() if h.status.value == "surviving"]
    for hid in survivors:
        camp.promote(f"result:{hid}", hid)
    final = camp.close_multiplicity()
    passports = {}
    space = red_team_space()
    for hid, h in judged.items():
        nov = check_novelty(h, snapshot, camp.novelty, canonicalizer=CANONICALIZER, equivalence=EQUIVALENCE)
        th, rms, expr = fitted[hid]

        def route_of(r_hid):
            _r_th, _r, r_expr = fitted[r_hid]
            return Route(r_hid, f"family:{fade_family_digest(HYPOTHESES[[x[0] for x in HYPOTHESES].index(r_hid)][2](np.ones(4)))[:8]}",
                         1, lambda p, e=r_expr: RouteResult(float(evaluate(e, {"q": p["throughput_Ah"], "T": p["temperature_C"] + 273.15}))))
        threshold = float(evaluate(expr, {"q": 1000.0, "T": 40.0 + 273.15})) * 1.1
        subject = ClaimSubject(space.claim_ref, OBSERVABLE, UNIT, Sense.AT_MOST, threshold, tuple(route_of(x[0]) for x in HYPOTHESES), hid)
        env = run_red_team(subject, space, AttackPlan(space.digest, 400, "battery-blind/1", edge_interior_points=4))
        # credibility, issuer-bound against the TEST ledger in explicit test mode: the prediction is the subject
        out_digest = hashlib.sha256(json.dumps({"hypothesis": hid, "theta": [float(x) for x in th]}, sort_keys=True).encode()).hexdigest()
        rec = attest_receipt(led, keys.signer("exec"), "exec", _computation_receipt(out_digest, f"fit-{hid}", data),
                             context_digest=ctx)
        within = ApplicabilityReport(f"{hid}.domain", "within", out_digest, "evaluated inside the pre-registered T / throughput box")
        attest_record(led, keys.signer("app"), "app", within, receipt=rec, subject_output="prediction", context_digest=ctx,
                      role=Role.APPLICABILITY)
        attest_record(led, keys.signer("rt"), "rt", env, receipt=rec, subject_output="prediction", context_digest=ctx, role=Role.RED_TEAM)
        g = EvidenceGraph((EvidenceNode(hid, EA.SIMULATION, out_digest, f"fit:{hid}", applicability=ctx),
                           EvidenceNode(f"{hid}.domain", EA.ANALYTICAL, record_digest(within), "applicability", applicability=ctx)),
                          (EvidenceEdge(f"{hid}.domain", hid, EvidenceRelation.SUPPORTS),))
        anchor = led.anchor()
        opened = AuthorityLedger.open(FileLedgerStore(work / "authority.jsonl"), anchor=anchor)
        cred = assess_credibility(ClaimNode(f"claim:{hid}", (FactorClaim(Factor.APPLICABILITY, 1, (f"{hid}.domain",), "applicability"),),
                                            subject_id=hid), g, DecisionRequirement(f"decision:{hid}", ctx, RiskClass.LOW),
                                  applicability_reports=(within,), red_team=(env,), authority=opened, trust_anchor=anchor,
                                  allow_test_profile=True)
        passports[hid] = DiscoveryPassport(
            f"passport:{hid}", "dry_run_synthetic",
            {"hypothesis_id": hid, "content_digest": h.content_digest, "claim_digest": h.claim_digest, "status": h.status.value,
             "novelty_status": nov.status.value, "family": fade_family_digest(expr)[:16]},
            {"preregistration_digest": prereg.digest, "preregistration_revision": prereg.revision, "manifest_digest": manifest.digest,
             "discipline": discipline["status"], "discipline_issues": discipline["issues"],
             "untestable": [u for u in discipline["untestable"] if u["hypothesis_id"] == hid]},
            tuple({**r, "verdicts": [x.verdict.value for x in camp.registry.verdicts_for(hid, h.content_digest)
                                     if x.falsifier_digest == r["digest"]],
                   "confirmatory_verdicts": [x.verdict.value for x in camp.registry.verdicts_for(hid, h.content_digest)
                                             if x.falsifier_digest == r["digest"]
                                             and x.evidence_id in discipline["confirmatory_evidence_ids"]]}
                  for r in sealed_refs[hid]),
            {"final_context_digest": final.digest, "family_size": final.family_size, "selected_from": final.selected_from},
            {"link": link.link_id, "link_status": link.status.value, "screened": len(decisions),
             "eliminated": sum(d.outcome is ScreeningOutcome.ELIMINATE for d in decisions), "z_selected": z_best,
             "false_elimination_rate": None if not admitted else audit.false_elimination_rate},
            {"envelope_digest": record_digest(env), "outcome": env.outcome.value, "statement": env.statement()},
            {"report_digest": cred.digest, "requirement_met": cred.requirement_met, "issuer_bound": cred.issuer_bound,
             "test_mode": cred.test_mode, "dominant_gap": cred.dominant_blocking_gap},
            dict(led.anchor().to_dict()),
            STANDARD_LIMITS + ("DRY RUN on SYNTHETIC battery-like data in a TEST-profile ledger: no scientific claim of any kind.",))
    camp_anchor = camp.anchor
    camp.close()
    return {"run_kind": "dry_run_synthetic", "campaign_anchor": camp_anchor.to_dict(), "discipline": discipline,
            "statuses": {hid: h.status.value for hid, h in judged.items()}, "survivors": survivors, "z_selected": z_best,
            "multiplicity": {"family_size": final.family_size, "selected_from": final.selected_from, "digest": final.digest},
            "falsifiers_sealed": {hid: len(r) for hid, r in sealed_refs.items()},
            "passports": {hid: p.to_dict() for hid, p in passports.items()},
            "passport_digests": {hid: p.digest for hid, p in passports.items()},
            "counts_as_discovery": {hid: p.counts_as_discovery for hid, p in passports.items()},
            "fidelity_link_admitted": admitted, "fidelity_admission_refusal": admission_refusal}


# ---------------------------------------------------------------------------- the owner-approval readiness record

#: what the real campaign HAS -- each None is a fact the readiness record derives a blocker from (filled only by the
#: owner's provisioning, never to make the record read READY)
REAL_FALSIFIER_ANCHOR: Mapping[str, Any] | None = None       # anchor of the production ledger after real falsifiers are sealed
PRODUCTION_TRUST_ANCHOR: Mapping[str, Any] | None = None     # the operator-held production authority anchor
DATA_AUTHORITY_ROUTE: str | None = None                      # the deployed (isolated) data authority holding confirmatory rows

BLOCKER_TEXT = {
    "CONFIRMATORY_DATASET_NOT_DESIGNATED": "no confirmatory dataset is named or digest-pinned; the owner designates it "
                                           "(CONFIRMATORY_REQUIREMENTS) and a DatasetManifest is registered before anything else",
    "REAL_FALSIFIERS_NOT_SEALED": "real predictions need the exploratory fit on the Kirkaldy archives (outside this container) at "
                                  "the owner-designated confirmatory conditions; nothing real is sealed, so FALSIFIER_ANCHOR is empty",
    "PRIOR_ART_NOT_SYSTEMATIC": "the prior-art snapshot is the designer's recall with unverified citations; a systematic search "
                                "is required before any novelty statement beyond the dry run",
    "PRODUCTION_AUTHORITY_NOT_PROVISIONED": "no production-profile authority ledger, operator-held root key or OWNER issuer "
                                            "exists for the real campaign (the dry run used a TEST-profile ledger with ephemeral keys)",
    "DATA_AUTHORITY_ROUTE_NOT_WIRED": "the confirmatory rows must be held by a data authority outside the proposer's process; the "
                                      "ExposureGate is that release point, but no escrow-hosted (isolated) battery data authority "
                                      "is deployed yet",
}


def readiness_blockers() -> tuple[str, ...]:
    """Each blocker is DERIVED from a fact about the repository / configuration, never listed by hand."""
    snap = prior_art_snapshot()
    found = []
    if CONFIRMATORY_REQUIREMENTS.get("identity") is None or CONFIRMATORY_REQUIREMENTS.get("status") == "TO_BE_DESIGNATED_BY_OWNER":
        found.append("CONFIRMATORY_DATASET_NOT_DESIGNATED")
    if REAL_FALSIFIER_ANCHOR is None:
        found.append("REAL_FALSIFIERS_NOT_SEALED")
    if any("NOT verified" in src or "recall" in src for src in snap.sources) or "NOT exhaustive" in snap.coverage_criteria:
        found.append("PRIOR_ART_NOT_SYSTEMATIC")
    if PRODUCTION_TRUST_ANCHOR is None or PRODUCTION_TRUST_ANCHOR.get("profile") != "production":
        found.append("PRODUCTION_AUTHORITY_NOT_PROVISIONED")
    if not DATA_AUTHORITY_ROUTE:
        found.append("DATA_AUTHORITY_ROUTE_NOT_WIRED")
    return tuple(f"{k}: {BLOCKER_TEXT[k]}" for k in found)


def readiness(dry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The readiness record (deterministic fields only).  ``dry``: an optional :func:`dry_run` report to summarize."""
    prereg = real_preregistration()
    hs = hypothesis_set()
    plan = red_team_plan()
    blockers = readiness_blockers()
    rec: dict[str, Any] = {
        "PREREGISTRATION_DIGEST": prereg.digest,
        "PREREGISTRATION_STATE": "DRAFT revision 1 (validated; NOT frozen in a production authority ledger); its hypothesis "
                                 "predictions name a placeholder condition until the owner designates the confirmatory design",
        "HYPOTHESIS_REGISTRY_DIGEST": hypothesis_registry_digest(hs),
        "HYPOTHESES": [h.hypothesis_id for h in hs],
        "FALSIFIER_ANCHOR": "NONE (no real falsifier sealed; see REAL_FALSIFIERS_NOT_SEALED)" if REAL_FALSIFIER_ANCHOR is None
                            else dict(REAL_FALSIFIER_ANCHOR),
        "PRIOR_ART_SNAPSHOT_DIGEST": prior_art_snapshot().digest,
        "DATASET_ADAPTER_STATUS": "IMPLEMENTED (DatasetManifest with salted row commitments + ExposureGate + verify_discipline; "
                                  "exercised on synthetic data); confirmatory dataset NOT DESIGNATED",
        "CONFIRMATORY_DATA_EXPOSED": "NO" if CONFIRMATORY_REQUIREMENTS.get("identity") is None else "UNKNOWN (re-derive from the ledger)",
        "RED_TEAM_PLAN_DIGEST": plan["plan_digest"],
        "RED_TEAM_SPACE_DIGEST": plan["space_digest"],
        "MULTIPLICITY_BUDGET": dict(prereg.multiplicity_budget),
        "BLINDFOLD_ESCROW_ROUTE": "confirmatory rows released one at a time through ExposureGate -> DurableCampaign "
                                  "ExposureAuthority (journaled, signed, owner-approved, row-commitment checked, discipline "
                                  "re-derived from the ledger); escrow-hosted isolated data authority: "
                                  + (DATA_AUTHORITY_ROUTE or "NOT WIRED for battery rows"),
        "KIRKALDY_2024": "NOT MET (unchanged; its observed holdout is exploratory now)",
        "READINESS_BLOCKERS": list(blockers),
    }
    if dry is not None:
        rec["DRY_RUN"] = {"run_kind": dry["run_kind"], "discipline": dry["discipline"]["status"] + " (synthetic dry run)",
                          "statuses": dict(dry["statuses"]), "falsifiers_sealed": dict(dry["falsifiers_sealed"]),
                          "fidelity_link_admitted": dry["fidelity_link_admitted"], "z_selected": dry["z_selected"],
                          "multiplicity_family_size": dry["multiplicity"]["family_size"],
                          "novelty": {hid: p["hypothesis"]["novelty_status"] for hid, p in dry["passports"].items()},
                          "counts_as_discovery": dict(dry["counts_as_discovery"])}
    rec["BATTERY_READINESS"] = ("NOT_READY(" + "; ".join(b.split(":")[0] for b in blockers) + ")") if blockers \
        else "READY_FOR_OWNER_APPROVAL"
    return rec


__all__ = [
    "BLOCKER_TEXT",
    "CANONICALIZER",
    "CONFIRMATORY_REQUIREMENTS",
    "EQUIVALENCE",
    "FAMILY_CANONICALIZER",
    "HYPOTHESES",
    "KIRKALDY_EXPLORATORY",
    "dry_run",
    "fade_family_digest",
    "hypothesis_registry_digest",
    "hypothesis_set",
    "prior_art_snapshot",
    "readiness",
    "readiness_blockers",
    "real_preregistration",
    "red_team_plan",
    "red_team_space",
    "synthetic_dataset",
]
