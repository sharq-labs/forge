"""Genesis-lite baseline arms (Genesis §10.5). Baselines, not the Mind: no belief state, no planner, no outcome model.

Every arm has the same signature ``arm(card, client, *, seed) -> proposal`` and the same information: the presented
card and an observe client whose budget the escrow enforces. The structure-search arms share ONE design routine, ONE
fit and ONE decision gate (generalised from ``engcore.blindfold.baselines.careful``: replicate-noise estimate, own
held-out check, precision bar, lack-of-fit test, residual-vs-covariate confounding check, and -- except in the two
extrapolating arms -- no extrapolation outside the query box). Structure is SELECTED by cross-validation inside the
training split and JUDGED on the untouched hold-out (review M5).

What the search arms search is the frozen v0 family of :mod:`.primitives` -- monomials over variable subsets -- not the
whole law grammar. The generator also draws exponential, two-term and regime forms, which no v0 arm can represent; the
preregistration therefore records "no strong applicable baseline" for law recovery outside that family, and each
world's ``truth_in_searched_family`` flag is reported (review H2).

Arms that need a library this environment does not have are never substituted: :func:`availability` reports them
``NOT_AVAILABLE`` (absent) or ``NOT_INTEGRATED`` (importable, not identity-bound to a frozen configuration here).
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import random
import secrets
from typing import Any, Callable, Mapping

import numpy as np

from engcore.blindfold import baselines as bf
from engcore.blindfold.escrow import EscrowRefused, is_budget_refusal
from engcore.blindfold.expression import add, c, mul, pw, v

PRECISION = 0.02
LACK_OF_FIT_RATIO = bf.LACK_OF_FIT_RATIO
OCCAM_SLACK = 0.05
CV_FOLDS = 3
RIVAL_POWER = 4.0
RIVAL_SIGMAS = 0.5


# ------------------------------------------------------------------------------------------------ shared machinery
def _design_random(card: Mapping[str, Any], n: int, rng: random.Random) -> list[dict[str, float]]:
    xs = [x for x in card["inputs"] if x["settable"]]
    return [{x["name"]: math.exp(rng.uniform(math.log(x["range"][0]), math.log(x["range"][1]))) for x in xs} for _ in range(n)]


def _design_lhs(card: Mapping[str, Any], n: int, rng: random.Random) -> list[dict[str, float]]:
    """Latin hypercube in log space: every input's range cut into n strata, one point per stratum, strata paired at random."""
    xs = [x for x in card["inputs"] if x["settable"]]
    columns = {}
    for x in xs:
        lo, hi = math.log(x["range"][0]), math.log(x["range"][1])
        cells = [lo + (hi - lo) * (i + rng.random()) / n for i in range(n)]
        rng.shuffle(cells)
        columns[x["name"]] = cells
    return [{name: math.exp(col[i]) for name, col in columns.items()} for i in range(n)]


def _collect(card: Mapping[str, Any], client: Any, points: list[dict[str, float]], tag: str) -> list[dict[str, float]]:
    rows = []
    for i, pt in enumerate(points):
        try:
            rows.append(client.observe(card["universe_id"], pt, query_id=f"{tag}{i}-{secrets.token_hex(6)}")["observation"])
        except EscrowRefused as exc:
            if not is_budget_refusal(exc):
                raise
            break
    return rows


def _gather(card: Mapping[str, Any], client: Any, rng: random.Random, design: str, tag: str) -> tuple[list[dict], int]:
    budget = int(card["query_budget"])
    replicate = min(4, budget // 4)
    maker = _design_lhs if design == "lhs" else _design_random
    points = maker(card, max(0, budget - replicate), rng)
    points += points[:replicate]
    return _collect(card, client, points, tag), replicate


def _positive(rows: list[dict], names: list[str], out: str) -> list[dict]:
    return [r for r in rows if r[out] > 0 and all(r[n] > 0 for n in names)]


def _fit(rows: list[dict], names: list[str], out: str) -> tuple[np.ndarray, float] | None:
    ok = _positive(rows, names, out)
    if len(ok) < len(names) + 2:
        return None
    X = np.column_stack([np.ones(len(ok))] + [np.log([r[n] for r in ok]) for n in names])
    y = np.log([r[out] for r in ok])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef, float(np.std(y - X @ coef))


def _predict(coef: np.ndarray, names: list[str], r: Mapping[str, float]) -> float:
    return float(coef[0] + sum(a * math.log(r[n]) for n, a in zip(names, coef[1:])))


def _cv_mse(train: list[dict], names: list[str], out: str) -> float:
    """K-fold cross-validated log-MSE inside the TRAINING split only (the hold-out is never used for selection)."""
    errs = []
    for k in range(CV_FOLDS):
        fit = _fit([r for i, r in enumerate(train) if i % CV_FOLDS != k], names, out)
        test = _positive([r for i, r in enumerate(train) if i % CV_FOLDS == k], names, out)
        if fit is None:
            return math.inf
        errs += [(math.log(r[out]) - _predict(fit[0], names, r)) ** 2 for r in test]
    return float(np.mean(errs)) if errs else math.inf


def _split(rows: list[dict], replicate: int) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    reps, base = rows[len(rows) - replicate:], rows[:replicate]
    fresh = rows[: len(rows) - replicate]
    return fresh[: int(0.75 * len(fresh))], fresh[int(0.75 * len(fresh)):], reps, base


def _replicate_noise(rows: list[dict], replicate: int, out: str) -> float | None:
    _, _, reps, base = _split(rows, replicate)
    diffs = [math.log(r[out]) - math.log(b[out]) for r, b in zip(reps, base) if r[out] > 0 and b[out] > 0]
    return float(np.std(diffs) / math.sqrt(2)) if len(diffs) >= 2 else None


def _law(coef: np.ndarray, names: list[str]) -> dict:
    if not names:
        return c(math.exp(coef[0]))
    return mul(c(math.exp(coef[0])), *[pw(v(n), round(float(a), 6)) for n, a in zip(names, coef[1:])])


def _gate(card: Mapping[str, Any], rows: list[dict], replicate: int, names: list[str], why: str, *,
          extrapolate: bool = False, precision: float | None = PRECISION) -> dict[str, Any]:
    """careful's decision rule over any variable subset: refuse unless the evidence pins the law down."""
    uid, out = card["universe_id"], card["output"]["name"]
    if len(rows) < len(names) + 6 + replicate:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "too few observations"}
    train, hold, _, _ = _split(rows, replicate)
    noise = _replicate_noise(rows, replicate, out)
    fit = _fit(train, names, out)
    if fit is None or len(hold) < 3:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "cannot fit and hold out"}
    coef, resid = fit
    ok_hold = _positive(hold, names, out)
    err_fit = [abs(math.log(r[out]) - _predict(coef, names, r)) for r in ok_hold]
    mean_train = float(np.mean([math.log(r[out]) for r in train if r[out] > 0]))
    err_const = [abs(math.log(r[out]) - mean_train) for r in ok_hold]
    if not err_fit or float(np.mean(np.square(err_fit))) > 0.8 * float(np.mean(np.square(err_const))):
        return {"universe_id": uid, "answer": "no_law", "rationale": "on held-out queries the variables do not beat a constant"}
    se = resid * math.sqrt((len(names) + 1) / len(train))
    scale = noise if noise is not None and noise > 0 else resid
    rms_hold = float(np.sqrt(np.mean(np.square(err_fit))))
    if (precision is not None and se > precision) or not (rms_hold <= LACK_OF_FIT_RATIO * scale and resid <= LACK_OF_FIT_RATIO * scale):
        covs = list(card.get("observed_covariates", ()))
        if covs:
            pos = _positive(rows, names + covs[:1], out)
            res = [math.log(r[out]) - _predict(coef, names, r) for r in pos]
            cv = [math.log(r[covs[0]]) for r in pos]
            if len(res) > 3 and float(np.std(cv)) > 0 and abs(float(np.corrcoef(res, cv)[0, 1])) > 0.5:
                return {"universe_id": uid, "answer": "confounded", "rationale": "residuals track a passive covariate"}
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "precision or lack-of-fit bar not met"}
    if not extrapolate and bf._extrapolates(card):
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "assessment region lies outside the query box"}
    return {"universe_id": uid, "answer": "law", "law": _law(coef, names), "rationale": why, "_noise": scale}


def _variables(card: Mapping[str, Any]) -> list[str]:
    return [x["name"] for x in card["inputs"]] + list(card.get("observed_covariates", ()))


def _occam(scored: list[tuple[list[str], float]]) -> list[str]:
    """Smallest (then first) subset within OCCAM_SLACK of the best cross-validated MSE."""
    best = min(m for _, m in scored)
    if not math.isfinite(best):
        return []
    eligible = [(len(s), i, s) for i, (s, m) in enumerate(scored) if m <= best * (1 + OCCAM_SLACK)]
    return min(eligible)[2]


def _clean(proposal: dict[str, Any]) -> dict[str, Any]:
    proposal.pop("_noise", None)
    return proposal


# ------------------------------------------------------------------------------------------------ the arms
def monomial_enumeration(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Every variable subset of the frozen monomial family, in order of complexity; Occam selection by CV."""
    rng = random.Random(f"enum:{seed}:{card['universe_id']}")
    rows, replicate = _gather(card, client, rng, "random", "e")
    names, out = _variables(card), card["output"]["name"]
    train, _, _, _ = _split(rows, replicate)
    subsets = [list(s) for k in range(len(names) + 1) for s in itertools.combinations(names, k)]
    chosen = _occam([(s, _cv_mse(train, s, out)) for s in subsets])
    return _clean(_gate(card, rows, replicate, chosen, "enumeration over the frozen monomial family"))


def random_structures(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Constrained random valid structures from the same family: as many random subsets as enumeration evaluates."""
    rng = random.Random(f"rand:{seed}:{card['universe_id']}")
    rows, replicate = _gather(card, client, rng, "random", "r")
    names, out = _variables(card), card["output"]["name"]
    train, _, _, _ = _split(rows, replicate)
    draws = [[n for n in names if rng.random() < 0.5] for _ in range(2 ** len(names))]
    chosen = _occam([(s, _cv_mse(train, s, out)) for s in draws])
    return _clean(_gate(card, rows, replicate, chosen, "constrained random valid structures"))


def greedy_forward(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Greedy forward selection over the variables (variable-primitive selection)."""
    rng = random.Random(f"greedy:{seed}:{card['universe_id']}")
    rows, replicate = _gather(card, client, rng, "random", "g")
    names, out = _variables(card), card["output"]["name"]
    train, _, _, _ = _split(rows, replicate)
    chosen: list[str] = []
    current = _cv_mse(train, chosen, out)
    while True:
        options = [(_cv_mse(train, chosen + [n], out), n) for n in names if n not in chosen]
        if not options:
            break
        m, n = min(options)
        if not m < current * (1 - OCCAM_SLACK):
            break
        chosen, current = chosen + [n], m
    return _clean(_gate(card, rows, replicate, chosen, "greedy forward variable selection"))


def space_filling(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """careful's fit and gate on settable inputs, with a Latin-hypercube (space-filling) design instead of random."""
    rng = random.Random(f"lhs:{seed}:{card['universe_id']}")
    rows, replicate = _gather(card, client, rng, "lhs", "l")
    settable = [x["name"] for x in card["inputs"] if x["settable"]]
    return _clean(_gate(card, rows, replicate, settable, "space-filling design, log-linear fit on intervened inputs"))


def extrapolating_fit(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """The enumeration arm WITHOUT the no-extrapolation refusal: proposes its law wherever the region lies (review H3)."""
    rng = random.Random(f"xfit:{seed}:{card['universe_id']}")
    rows, replicate = _gather(card, client, rng, "random", "x")
    names, out = _variables(card), card["output"]["name"]
    train, _, _, _ = _split(rows, replicate)
    subsets = [list(s) for k in range(len(names) + 1) for s in itertools.combinations(names, k)]
    chosen = _occam([(s, _cv_mse(train, s, out)) for s in subsets])
    return _clean(_gate(card, rows, replicate, chosen, "monomial enumeration, extrapolated", extrapolate=True))


def extrapolation_pair(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Fixed heuristic for the indistinguishable answer (review H3): when the assessment region leaves the box and a law
    passes the in-box gate, propose that law AND a rival law * (1 + d * prod r_i^m) with r_i = x_i/high_i (or low_i/x_i)
    for every input the region extends beyond, d = RIVAL_SIGMAS x the replicate noise. Inside the box the rival agrees
    to within d; outside it diverges. It is a heuristic over the card, not a model of the hidden alternative."""
    rng = random.Random(f"pair:{seed}:{card['universe_id']}")
    rows, replicate = _gather(card, client, rng, "random", "p")
    settable = [x["name"] for x in card["inputs"] if x["settable"]]
    proposal = _gate(card, rows, replicate, settable, "in-box law", extrapolate=True)
    if proposal["answer"] != "law" or not bf._extrapolates(card):
        return _clean(proposal)
    d = RIVAL_SIGMAS * float(proposal.pop("_noise"))
    box = {x["name"]: x["range"] for x in card["inputs"]}
    factors = []
    for name, (lo, hi) in sorted(card["assessment_region"].items()):
        if hi > box[name][1]:
            factors.append((pw(v(name), RIVAL_POWER), box[name][1] ** -RIVAL_POWER))
        elif lo < box[name][0]:
            factors.append((pw(v(name), -RIVAL_POWER), box[name][0] ** RIVAL_POWER))
    if not factors or d <= 0:
        return {"universe_id": card["universe_id"], "answer": "insufficient_evidence", "rationale": "no rival direction"}
    scale = d * math.prod(k for _, k in factors)
    rival = mul(proposal["law"], add(c(1.0), mul(c(scale), *[f for f, _ in factors])))
    return {"universe_id": card["universe_id"], "answer": "indistinguishable", "laws": [proposal["law"], rival],
            "rationale": "in-box fit plus an outward-diverging rival within half a noise sigma in the box"}


def fit_all_gated(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """v0.1 (pilot finding P-1): always_law's fit -- every observed variable, log-linear -- behind the shared control
    checks (held-out improvement over a constant, lack of fit against replicate noise, residual-vs-covariate confounding)
    but WITHOUT the fixed precision bar and the no-extrapolation refusal. It raises the competence bar on discoverable
    worlds that the gated arms over-refuse; it is added, never substituted, and no arm is removed or weakened."""
    rng = random.Random(f"fitall:{seed}:{card['universe_id']}")
    rows, replicate = _gather(card, client, rng, "random", "f")
    return _clean(_gate(card, rows, replicate, _variables(card), "log-linear fit on every observed variable, control-checked",
                        extrapolate=True, precision=None))


def historical_answer(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Adversarial control: answers with the textbook law its vocabulary suggests (a memorising proposer). Fits only the
    constant. Without a familiar vocabulary it declines (insufficient_evidence)."""
    from .presentation import TRAP_TEMPLATES

    uid, out = card["universe_id"], card["output"]["name"]
    known = {t[0]: (t[1], t[2]) for t in TRAP_TEMPLATES}
    names = {x["name"] for x in card["inputs"]}
    if out not in known or known[out][0] not in names:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "no familiar law for this vocabulary"}
    x, e = known[out]
    rows, _ = _gather(card, client, random.Random(f"hist:{seed}:{uid}"), "random", "h")
    logs = [math.log(r[out]) - e * math.log(r[x]) for r in rows if r[out] > 0 and r[x] > 0]
    const = math.exp(float(np.mean(logs))) if logs else 1.0
    return {"universe_id": uid, "answer": "law", "law": mul(c(const), pw(v(x), e)), "rationale": "the textbook law"}


def _fixed(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
        return fn(card, client)
    arm.__name__ = fn.__name__
    return arm


#: name -> (callable, family, stochastic, role). "competence" arms are candidates for the strongest applicable baseline;
#: "floor"/"sanity" arms are never the competence bar; "adversarial" arms exist to fail (traps).
ARMS: dict[str, tuple[Callable[..., dict[str, Any]], str, bool, str]] = {
    "monomial_enumeration": (monomial_enumeration, "law recovery: enumeration of the frozen v0 monomial family", True, "competence"),
    "random_structures": (random_structures, "law recovery: constrained random structures (v0 family)", True, "competence"),
    "greedy_forward": (greedy_forward, "variable-primitive selection: greedy forward", True, "competence"),
    "space_filling": (space_filling, "experiment selection: space-filling design", True, "competence"),
    "extrapolating_fit": (extrapolating_fit, "law recovery that extrapolates outside the query box", True, "competence"),
    "fit_all_gated": (fit_all_gated, "law recovery: all-variable fit behind the control checks (v0.1)", True, "competence"),
    "extrapolation_pair": (extrapolation_pair, "indistinguishable answer: fixed rival-pair heuristic", True, "competence"),
    "careful": (_fixed(bf.careful), "experiment selection: random design + replicate/holdout (existing)", False, "competence"),
    "single_setting": (_fixed(bf.single_setting), "non-discoverer control (existing)", False, "sanity"),
    "always_law": (_fixed(bf.always_law), "floor: always proposes (existing)", False, "floor"),
    "always_refuse": (_fixed(bf.always_refuse), "floor: never proposes (existing)", False, "floor"),
    "always_insufficient": (_fixed(bf.always_insufficient), "floor: blanket refusal (existing)", False, "floor"),
    "historical_answer": (historical_answer, "adversarial: textbook answer for familiar vocabulary", False, "adversarial"),
}

#: Genesis §10.5 arms that are not run here, with the reason; never silently substituted
UNAVAILABLE_ARMS = {
    "full_grammar_enumeration": ("law recovery: enumeration of the full law grammar (exp / two-term / regime forms)", None),
    "pysr": ("law recovery: PySR symbolic regression", "pysr"),
    "bo_botorch": ("experiment selection: BO/BoTorch-only on the same observable", "botorch"),
    "pysindy": ("dynamics / inverse identification: PySINDy", "pysindy"),
    "discriminating_design": ("competing-mechanism falsification: fixed discriminating-design heuristic", None),
    "mechanism_enumeration": ("coupled mechanism recovery (G1/G2): structure enumeration in a port grammar", None),
    "llm_ablation": ("AI-proposer contribution: Mind with LLM workers replaced (§8.5)", None),
}


def availability() -> dict[str, dict[str, str]]:
    out = {}
    for name, (family, module) in sorted(UNAVAILABLE_ARMS.items()):
        if module is None:
            status = "NOT_APPLICABLE_IN_V0"
            why = "not built in v0 (needs the Mind, a port grammar, a distinguishable-rival generator or a nonlinear-form fitter)"
        elif importlib.util.find_spec(module) is None:
            status, why = "NOT_AVAILABLE", f"{module} is not installed in the benchmark environment"
        else:
            status, why = "NOT_INTEGRATED", f"{module} is importable but not identity-bound to a frozen configuration in v0"
        out[name] = {"family": family, "status": status, "reason": why}
    return out
