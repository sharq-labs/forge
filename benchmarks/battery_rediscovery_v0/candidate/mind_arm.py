"""The Minimal Mind arm: ``engcore.mind.minimal`` (byte-exact from e2b8037c) posed the battery questions it can express.

The Mind's hypotheses are log-linear structures of a positive observable over settable inputs and passive covariates,
and its experiments are interventions at a requested point of a continuous box.  Recorded battery data are a passive
pool, so this adapter declares (frozen in PLAN.json before any run):

* the WORLD serves the nearest unused recorded sample to the requested settings (max |ln x - ln x_req| over the
  settable inputs).  A request with no unused sample within TOLERANCE_LN is refused (ObservationRefused); exhausting the
  budget is refused as budget.  No sample is interpolated or synthesized.  The Mind records the REQUESTED settings,
  not the served ones (it cannot be told otherwise); the mismatch is at most TOLERANCE_LN per input.
* a time-like input's box starts at median(dt) / TOLERANCE_LN, where the sampling is dense enough in ln t for the
  tolerance; it ends at the largest recorded value.
* two probes per problem, each one Mind run per seed:
    RELAXATION  (rest after load) y = (V(t) - V_last_loaded) / |I_last_loaded| [ohm]; input t_off; covariate T
    PREDICTION  (loaded samples) with a measured OCV declared: y = (OCV(z) - V) / |I| [ohm], input t_on, covariates
                |I|, T, z; without one: y = V [V], inputs t_on, |I|, covariates T, z.  The region of use is the held-out
                subset's range of the settable inputs; one run per subset.  A transient response is divided by the
                current that drives it (an impedance) so that replicates served from different current levels measure
                one quantity; with no OCV the voltage itself is the only positive observable.
* a fixed translation of the Mind's ConclusionKind into the pilot's dispositions (TRANSLATION below).  For
  IDENTIFIABILITY the relaxation impedance r(t) = R0 + R1 (1 - exp(-T_load/tau)) (1 - exp(-t/tau)) is the evidence:
  a law curved in ln t over the box carries a level, an amplitude and a time scale (SUPPORTED); a flat one means the
  branch is relaxed or absent in the sampled window (NOT_SUPPORTED); anything else is REVIEW.  (A step-response probe
  "does V_before - V_after depend on |I|" was dropped in development: on a synthetic single-level problem it read "no
  dependence on I" as "R0 not identifiable", which is physically wrong, since R0 = dV/I at one step.)

MODEL_ADEQUACY and MODEL_DISCREPANCY ask about the DECLARED 1RC family, which is not in the Mind's hypothesis space, and
the Mind produces no R0/R1/C1 estimates: those are reported as NOT_ASSESSABLE / not representable, never filled in by
the adapter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from engcore.mind.minimal import (
    FULL, ConclusionKind, ExperimentalProblem, InputSpec, ObservationRefused, ProblemRefused, replay, run_mind,
)
from engcore.mind.minimal.runner import MIND_ID, MIND_VERSION

from . import model as m
from .common import (
    AXES, NOT_ASSESSABLE, NOT_SUPPORTED, OUTPUT_SCHEMA, REFUSED, REVIEW, SUPPORTED, Problem, Trajectory, combine, digest,
)

TOLERANCE_LN = 0.05
BUDGET_MAX = 40
QUERY_COST = 1.0
PRIMARY_SEED = 0
STABILITY_SEEDS = (1, 2)
KELVIN = 273.15
MIN_SOC = 0.01
COVERAGE_Z = 1.96

# ConclusionKind -> disposition, per probe (RELAXATION needs the law's structure; see _translate)
TRANSLATION = {
    "RELAXATION": {"law_with_curvature": SUPPORTED, "law_linear_only": REVIEW, "law_without_input": REVIEW,
                   "no_dependence": NOT_SUPPORTED, "insufficient_evidence": REVIEW, "indistinguishable": REVIEW,
                   "unidentifiable_passive_association": REVIEW, "refused": REFUSED, "problem_refused": REFUSED},
    "PREDICTION": {"law": "compare to the declared bar", "no_dependence": NOT_ASSESSABLE,
                   "insufficient_evidence": NOT_ASSESSABLE, "indistinguishable": NOT_ASSESSABLE,
                   "unidentifiable_passive_association": NOT_ASSESSABLE, "refused": REFUSED,
                   "problem_refused": REFUSED, "empty_region": NOT_ASSESSABLE},
}
NOT_REPRESENTABLE = ("the declared 1RC family is not in the Minimal Mind's hypothesis space (log-linear structures of a "
                     "positive observable); the Mind cannot judge it")


@dataclass
class Pool:
    """Recorded samples: settable input values, covariate values and the observable, plus their provenance."""

    settable: tuple[str, ...]
    covariates: tuple[str, ...]
    X: np.ndarray            # (n, len(settable)) positive input values
    C: np.ndarray            # (n, len(covariates))
    y: np.ndarray
    refs: list[str]
    dt_median: float
    scale: np.ndarray        # volts per unit of y (|I| for an impedance observable, 1 for a voltage)
    unit: str

    def __len__(self) -> int:
        return len(self.y)


def _runs(current: np.ndarray, band: float) -> list[tuple[int, int]]:
    """Maximal loaded runs [s, e] (inclusive) that start after a rest sample (a run with no rest before it is skipped)."""
    loaded = np.abs(current) > band
    out, k, n = [], 1, len(current)
    while k < n:
        if loaded[k] and not loaded[k - 1]:
            e = k
            while e + 1 < n and loaded[e + 1]:
                e += 1
            out.append((k, e))
            k = e + 1
        else:
            k += 1
    return out


def _dt_median(trajs: Sequence[Trajectory]) -> float:
    d = np.concatenate([np.diff(tr.t) for tr in trajs])
    return float(np.median(d[d > 0]))


def _z(trajs: Sequence[Trajectory]) -> list[np.ndarray]:
    b = m.Batch.build(trajs, "backward")
    return [b.z[i, :b.lengths[i]] for i in range(len(trajs))]


def relax_pool(trajs: Sequence[Trajectory], band: float) -> Pool:
    X, C, y, refs, sc = [], [], [], [], []
    for tr in trajs:
        runs = _runs(tr.current, band)
        for idx, (_, e) in enumerate(runs):
            stop = runs[idx + 1][0] if idx + 1 < len(runs) else len(tr.t)
            for j in range(e + 1, stop):
                if abs(tr.current[j]) > band:
                    break
                X.append([tr.t[j] - tr.t[e]]); C.append([tr.temperature[j] + KELVIN])
                y.append((tr.voltage[j] - tr.voltage[e]) / abs(tr.current[e])); sc.append(abs(tr.current[e]))
                refs.append(f"{tr.traj_id}#{j}")
    return Pool(("t_off_s",), ("T_K",), np.array(X, float).reshape(-1, 1), np.array(C, float).reshape(-1, 1),
                np.array(y, float), refs, _dt_median(trajs), np.array(sc, float), "ohm")


def load_pool(trajs: Sequence[Trajectory], band: float, ocv_knots: np.ndarray | None) -> Pool:
    X, C, y, refs, sc = [], [], [], [], []
    for tr, z in zip(trajs, _z(trajs)):
        for s, e in _runs(tr.current, band):
            for k in range(s, e + 1):
                if z[k] <= MIN_SOC:
                    continue
                i, t_on, temp = abs(tr.current[k]), tr.t[k] - tr.t[s - 1], tr.temperature[k] + KELVIN
                if ocv_knots is not None:
                    X.append([t_on]); C.append([i, temp, z[k]]); sc.append(i)
                    y.append((float(np.interp(z[k], ocv_knots[:, 0], ocv_knots[:, 1])) - tr.voltage[k]) / i)
                else:
                    X.append([t_on, i]); C.append([temp, z[k]]); sc.append(1.0)
                    y.append(tr.voltage[k])
                refs.append(f"{tr.traj_id}#{k}")
    if ocv_knots is not None:
        return Pool(("t_on_s",), ("I_A", "T_K", "z"), np.array(X, float).reshape(-1, 1), np.array(C, float).reshape(-1, 3),
                    np.array(y, float), refs, _dt_median(trajs), np.array(sc, float), "ohm")
    return Pool(("t_on_s", "I_A"), ("T_K", "z"), np.array(X, float).reshape(-1, 2), np.array(C, float).reshape(-1, 2),
                np.array(y, float), refs, _dt_median(trajs), np.array(sc, float), "V")


class PoolWorld:
    """Serves the nearest unused recorded sample within the tolerance; never interpolates; enforces the budget."""

    def __init__(self, pool: Pool, budget: int) -> None:
        self.pool, self.budget = pool, budget
        self.logX = np.log(pool.X)
        self.used = np.zeros(len(pool), bool)
        self.served: list[dict[str, Any]] = []
        self.refused: list[dict[str, Any]] = []

    def __call__(self, settings: Mapping[str, float], query_ref: str) -> dict[str, float]:
        if len(self.served) >= self.budget:
            raise ObservationRefused("the query budget is spent", budget=True)
        req = np.log(np.array([float(settings[n]) for n in self.pool.settable]))
        d = np.max(np.abs(self.logX - req), axis=1)
        d[self.used] = np.inf
        i = int(np.argmin(d))
        if not math.isfinite(d[i]) or d[i] > TOLERANCE_LN:
            self.refused.append({"query_ref": query_ref, "requested": dict(settings),
                                 "nearest_ln_distance": None if not math.isfinite(d[i]) else round(float(d[i]), 6)})
            raise ObservationRefused(f"no unused recorded sample within {TOLERANCE_LN} ln of the requested settings")
        self.used[i] = True
        obs = {n: float(self.pool.X[i, j]) for j, n in enumerate(self.pool.settable)}
        obs.update({n: float(self.pool.C[i, j]) for j, n in enumerate(self.pool.covariates)})
        obs["y"] = float(self.pool.y[i])
        self.served.append({"query_ref": query_ref, "sample": self.pool.refs[i], "ln_distance": round(float(d[i]), 6)})
        return obs


def _box(pool: Pool) -> list[InputSpec]:
    specs = []
    for j, n in enumerate(pool.settable):
        col = pool.X[:, j]
        lo = pool.dt_median / TOLERANCE_LN if n.startswith("t_") else float(col.min())
        specs.append(InputSpec(n, lo, float(col.max()), "s" if n.startswith("t_") else "A"))
    return specs


def make_problem(pid: str, probe: str, pool: Pool, region: Mapping[str, tuple[float, float]] | None = None) -> ExperimentalProblem:
    inputs = _box(pool)
    return ExperimentalProblem(problem_id=f"{pid}:{probe}", inputs=tuple(inputs), covariates=pool.covariates,
                               observable="y", observable_unit=pool.unit, budget=min(BUDGET_MAX, len(pool)),
                               query_cost=QUERY_COST, region=dict(region or {}))


def _translate(probe: str, run: Any, input_name: str) -> tuple[str, str]:
    kind = run.conclusion.kind
    table = TRANSLATION[probe]
    if kind is ConclusionKind.LAW:
        law = run.conclusion.laws[0]
        if input_name not in law.linear:
            return table["law_without_input"], "law_without_input"
        key = "law_with_curvature" if input_name in law.quadratic else "law_linear_only"
        return table[key], key
    return table[kind.value], kind.value


def _run_record(problem: ExperimentalProblem, run: Any, world: PoolWorld, seed: int) -> dict[str, Any]:
    trace = run.trace
    final = trace["final_state"]
    hyps = [{"hypothesis_id": h["hypothesis_id"], "status": h["status"], "weight": h["weight"]} for h in final["hypotheses"]]
    sealed_predictions = sum(len(s["pre_result"]["predictions"]) for s in trace["steps"])
    return {"seed": seed, "problem": problem.to_dict(), "problem_digest": problem.digest,
            "conclusion": run.conclusion.to_dict(), "hypotheses": hyps,
            "eliminated": sorted(h["hypothesis_id"] for h in hyps if h["status"] == "refuted"),
            "queries_served": len(world.served), "queries_refused": world.refused, "served": world.served,
            "sealed_pre_result_predictions": sealed_predictions, "steps": len(trace["steps"]),
            "evidence_refs": [s["evidence"]["evidence_digest"] for s in trace["steps"] if s.get("evidence")],
            "final_stop": trace["final_stop"], "trace_digest": digest(trace), "registry_head": trace["registry"]["head"]}


def run_probe(pid: str, probe: str, pool: Pool, seed: int, region: Mapping[str, tuple[float, float]] | None = None
              ) -> tuple[dict[str, Any], Any, ExperimentalProblem | None]:
    if len(pool) == 0:
        return {"seed": seed, "problem_refused": "the pool holds no recorded sample"}, None, None
    try:
        problem = make_problem(pid, probe, pool, region)
    except ProblemRefused as exc:
        return {"seed": seed, "problem_refused": str(exc)}, None, None
    world = PoolWorld(pool, problem.budget)
    run = run_mind(problem, world, seed=seed, config=FULL)
    return _run_record(problem, run, world, seed), run, problem


def _region(ho: Pool) -> dict[str, tuple[float, float]] | None:
    if len(ho) == 0:
        return None
    t = ho.X[:, 0]
    lo = ho.dt_median / TOLERANCE_LN
    if lo > t.max():
        return None
    region = {"t_on_s": (lo, float(t.max()))}
    for j, n in enumerate(ho.settable[1:], start=1):
        region[n] = (float(ho.X[:, j].min()), float(ho.X[:, j].max()))
    return region


def _evaluate_law(run: Any, problem: ExperimentalProblem, ho: Pool, bar: Mapping[str, float], sigma_v: float | None
                  ) -> dict[str, Any]:
    comp = run.competition
    lead = run.conclusion.laws[0].hypothesis_id
    fitted = comp.rivals[lead].fitted
    lo = problem.region["t_on_s"][0]
    keep = ho.X[:, 0] >= lo
    pts = [{n: float(x[j]) for j, n in enumerate(ho.settable)} for x in ho.X[keep]]
    mean, _, sd_obs = comp.model.predict_many(fitted, pts, comp.covmodels)
    yobs = ho.y[keep]
    scale = ho.scale[keep]
    err = (yobs - np.exp(mean)) * scale                  # in volts, whatever the observable's unit
    a = np.abs(err) * 1e3
    stats = {"rmse_mV": float(np.sqrt(np.mean(err ** 2)) * 1e3), "p95_abs_mV": float(np.percentile(a, 95)),
             "bias_mV": float(np.mean(err) * 1e3), "samples": int(keep.sum()), "samples_outside_scope": int((~keep).sum())}
    coverage = None
    if sigma_v is not None and np.all(yobs > 0):
        s = np.sqrt(sd_obs ** 2 + (sigma_v / (yobs * scale)) ** 2)
        coverage = float(np.mean(np.abs(np.log(yobs) - mean) <= COVERAGE_Z * s))
    meets = stats["rmse_mV"] <= bar["rmse_mV_max"] and stats["p95_abs_mV"] <= bar["p95_abs_mV_max"]
    return {"law": run.conclusion.laws[0].to_dict(), "stats": stats, "meets_bar": bool(meets), "coverage_95": coverage,
            "predicted_digest": digest([round(float(v), 9) for v in mean])}


def mind_problem(problem: Problem, seeds: Sequence[int], traces: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every probe for every seed.  ``traces`` (if given) receives the full primary-seed trace of each probe."""
    pid, band = problem.problem_id, problem.rest_band
    cal = problem.calibration()
    pools = {"RELAXATION": relax_pool(cal, band), "PREDICTION": load_pool(cal, band, problem.ocv_knots)}
    probes: dict[str, Any] = {}
    for probe, input_name in (("RELAXATION", "t_off_s"),):
        per_seed = {}
        for seed in seeds:
            rec, run, _ = run_probe(pid, probe, pools[probe], seed)
            if run is not None and traces is not None and seed == PRIMARY_SEED:
                traces[probe] = run.trace
            if run is None:
                rec["translation"] = {"key": "problem_refused", "disposition": TRANSLATION[probe]["problem_refused"]}
            else:
                d, key = _translate(probe, run, input_name)
                rec["translation"] = {"key": key, "disposition": d}
            per_seed[str(seed)] = rec
        probes[probe] = {"pool_size": len(pools[probe]), "per_seed": per_seed}
    prediction: dict[str, Any] = {}
    for set_name in ("within_cell_heldout", "cross_cell_heldout"):
        sets = problem.heldout(set_name)
        if sets is None:
            continue
        for subset, trajs in sets.items():
            ho = load_pool(trajs, band, problem.ocv_knots)
            region = _region(ho)
            per_seed = {}
            for seed in seeds:
                if region is None:
                    per_seed[str(seed)] = {"seed": seed, "translation": {"key": "empty_region", "disposition": NOT_ASSESSABLE}}
                    continue
                rec, run, mp = run_probe(pid, f"PREDICTION[{set_name}/{subset}]", pools["PREDICTION"], seed, region)
                if run is not None and traces is not None and seed == PRIMARY_SEED:
                    traces[f"PREDICTION[{set_name}/{subset}]"] = run.trace
                if run is None:
                    rec["translation"] = {"key": "problem_refused", "disposition": REFUSED}
                elif run.conclusion.kind is ConclusionKind.LAW:
                    ev = _evaluate_law(run, mp, ho, problem.acceptance(set_name, subset), problem.voltage_sigma())
                    rec["heldout"] = ev
                    rec["translation"] = {"key": "law", "disposition": SUPPORTED if ev["meets_bar"] else NOT_SUPPORTED}
                else:
                    kind = run.conclusion.kind.value
                    rec["translation"] = {"key": kind, "disposition": TRANSLATION["PREDICTION"][kind]}
                per_seed[str(seed)] = rec
            prediction[f"{set_name}/{subset}"] = {"set": set_name, "subset": subset, "heldout_pool_size": len(ho),
                                                  "region": None if region is None else {k: list(v) for k, v in region.items()},
                                                  "per_seed": per_seed}
    return {"pools": {k: len(v) for k, v in pools.items()}, "probes": probes, "prediction": prediction}


def _answers(problem: Problem, detail: dict[str, Any], seed: int) -> dict[str, dict[str, Any]]:
    s = str(seed)
    rx = detail["probes"]["RELAXATION"]["per_seed"][s]["translation"]
    answers = {
        "IDENTIFIABILITY": {"disposition": rx["disposition"], "reason": f"RELAXATION -> {rx['key']} ({rx['disposition']})",
                            "sub": {"RELAXATION": rx["disposition"]}},
        "MODEL_ADEQUACY": {"disposition": NOT_ASSESSABLE, "reason": NOT_REPRESENTABLE},
        "MODEL_DISCREPANCY": {"disposition": NOT_ASSESSABLE, "reason": NOT_REPRESENTABLE},
    }
    for set_name, axis in (("within_cell_heldout", "WITHIN_CELL_GENERALIZATION"), ("cross_cell_heldout", "CROSS_CELL_TRANSFER")):
        subs = {k: v for k, v in detail["prediction"].items() if v["set"] == set_name}
        if not subs:
            answers[axis] = {"disposition": NOT_ASSESSABLE, "reason": "no held-out set of this kind is supplied"}
            continue
        d = {k: v["per_seed"][s]["translation"]["disposition"] for k, v in subs.items()}
        keys = {k: v["per_seed"][s]["translation"]["key"] for k, v in subs.items()}
        answers[axis] = {"disposition": combine(list(d.values())), "sub": d,
                         "reason": "; ".join(f"{k} -> {keys[k]} ({d[k]})" for k in sorted(d))}
    return answers


def mind(problem: Problem, seeds: Sequence[int] = (PRIMARY_SEED, *STABILITY_SEEDS),
         traces: dict[str, Any] | None = None) -> dict[str, Any]:
    detail = mind_problem(problem, seeds, traces)
    answers = _answers(problem, detail, PRIMARY_SEED)
    stability = {str(s): {a: v["disposition"] for a, v in _answers(problem, detail, s).items()} for s in seeds}
    stable = all(stability[str(s)] == stability[str(PRIMARY_SEED)] for s in seeds)
    queries = 0
    hyps, elim = set(), set()
    for p in detail["probes"].values():
        r = p["per_seed"][str(PRIMARY_SEED)]
        queries += r.get("queries_served", 0)
        hyps |= {h["hypothesis_id"] for h in r.get("hypotheses", [])}
        elim |= set(r.get("eliminated", []))
    for p in detail["prediction"].values():
        r = p["per_seed"][str(PRIMARY_SEED)]
        queries += r.get("queries_served", 0)
        hyps |= {h["hypothesis_id"] for h in r.get("hypotheses", [])}
        elim |= set(r.get("eliminated", []))
    return {"schema": OUTPUT_SCHEMA, "arm": "MIND", "mind": f"{MIND_ID}@{MIND_VERSION}", "problem_id": problem.problem_id,
            "answers": answers, "primary_seed": PRIMARY_SEED, "seeds": list(seeds), "disposition_by_seed": stability,
            "dispositions_stable_across_seeds": stable, "hypotheses": sorted(hyps), "eliminated": sorted(elim),
            "parameters": {"R0": None, "R1": None, "C1": None, "basis": "not representable: the Mind's laws are log-linear "
                           "dependences of a probe observable, not 1RC parameters"},
            "refusal_reasons": sorted({a["reason"] for a in answers.values()
                                       if a["disposition"] in (REFUSED, NOT_ASSESSABLE, REVIEW)}),
            "observations_used": queries, "adapter": {"tolerance_ln": TOLERANCE_LN, "budget_max": BUDGET_MAX,
                                                      "translation": TRANSLATION}, "detail": detail}


def probe_problems(problem: Problem) -> dict[str, ExperimentalProblem | None]:
    """The ExperimentalProblem of every probe, rebuilt from the pack alone (None where the problem is refused)."""
    pid, band = problem.problem_id, problem.rest_band
    cal = problem.calibration()
    jobs = {"RELAXATION": (relax_pool(cal, band), None)}
    load = load_pool(cal, band, problem.ocv_knots)
    for set_name in ("within_cell_heldout", "cross_cell_heldout"):
        for subset, trajs in (problem.heldout(set_name) or {}).items():
            region = _region(load_pool(trajs, band, problem.ocv_knots))
            if region is not None:
                jobs[f"PREDICTION[{set_name}/{subset}]"] = (load, region)
    out: dict[str, ExperimentalProblem | None] = {}
    for probe, (pool, region) in jobs.items():
        try:
            out[probe] = make_problem(pid, probe, pool, region) if len(pool) else None
        except ProblemRefused:
            out[probe] = None
    return out


def replay_traces(problem: Problem, sealed: Mapping[str, Any]) -> dict[str, Any]:
    """Replay every sealed primary-seed trace from its own recorded observations (no world is queried)."""
    problems = probe_problems(problem)
    out = {}
    for probe, trace in sorted(sealed.items()):
        mp = problems.get(probe)
        if mp is None:
            out[probe] = {"status": "NO_PROBLEM", "detail": "the probe's problem could not be rebuilt from the pack"}
            continue
        out[probe] = {"problem_digest_matches": mp.digest == trace["problem_digest"], **replay(trace, mp)}
    return out


__all__ = ["BUDGET_MAX", "NOT_REPRESENTABLE", "PoolWorld", "TOLERANCE_LN", "TRANSLATION", "load_pool", "mind",
           "mind_problem", "probe_problems", "relax_pool", "replay_traces", "run_probe"]
