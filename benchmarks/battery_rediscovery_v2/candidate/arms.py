"""The four ablation arms and the careful baseline of battery_rediscovery_v2 (plus three reference arms).

OLD_MIND                  battery_rediscovery_v1's Mind arm (``candidate.mind_arm.mind``, which runs the byte-exact
                          ``engcore.mind.minimal``) on the v1 view of the specification, seeds ``SEEDS``.
REPRESENTATION_ONLY       ``engcore.mind.repsem.assess`` under the v1 adapter's two-class semantics
                          (``legacy_role_table``): no state, no latent parameter, every non-clock column a passive covariate.
SEMANTIC_ROLES_ONLY       the same Mind, adapter and translation as OLD_MIND, with its PREDICTION probe posed by the declared
                          roles: the CONTROLLED_INPUT current is settable, the STATE_VARIABLE charge state is never a free
                          covariate, only the NUISANCE temperature stays passive.  With a measured OCV this is the repsem
                          ablation's pool (``benchmarks.mind_repsem_v1.arms._roles_load_pool``, imported, not copied); with
                          an UNKNOWN OCV the observable is the voltage itself (v1's own no-OCV observable) over settable
                          (t_on, |I|) and the temperature, the charge state again excluded.  The v1 answer vocabulary is
                          unchanged, so adequacy and discrepancy stay NOT_ASSESSABLE and identifiability keeps v1's
                          relaxation proxy.
REPRESENTATION_PLUS_ROLES ``assess`` under the problem's declared roles.
CAREFUL_BASELINE          v1's careful baseline (``candidate.baselines.careful``) on the v1 view.
FIXED_FIT, ALWAYS_FIT, ALWAYS_REFUSE   v1's reference baselines on the v1 view (context only; no hypothesis uses them).

Every arm sees the same specification.  No arm reads another arm's output, any held-out truth or any history.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.battery_rediscovery_v1.candidate import baselines as v1base
from benchmarks.battery_rediscovery_v1.candidate import common as v1common
from benchmarks.battery_rediscovery_v1.candidate import mind_arm as v1
from benchmarks.mind_repsem_v1.arms import _roles_load_pool
from engcore.mind.minimal import ConclusionKind
from engcore.mind.repsem import RoleTable, VariableRole, assess, legacy_role_table

from .common import AXES, NOT_ASSESSABLE, NOT_SUPPORTED, OUTPUT_SCHEMA, PRIMARY_SEED, REFUSED, SEEDS, SUPPORTED, combine
from .families import build_families
from .views import v1_problem

ARMS = ("OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES", "CAREFUL_BASELINE")
REFERENCE_ARMS = ("FIXED_FIT", "ALWAYS_FIT", "ALWAYS_REFUSE")
ALL_ARMS = ARMS + REFERENCE_ARMS


def families_for(spec: Mapping[str, Any]):
    ocv = spec["declared_family"]["ocv"]
    return build_families(len(ocv["knots_soc"]) if ocv["status"] == "UNKNOWN_FITTED_TABLE" else 0)


def _record(arm: str, spec: Mapping[str, Any], answers: Mapping[str, Mapping[str, Any]], **extra: Any) -> dict[str, Any]:
    assert set(answers) == set(AXES), sorted(answers)
    return {"schema": OUTPUT_SCHEMA, "arm": arm, "problem_id": spec["problem_id"],
            "answers": {a: dict(answers[a]) for a in AXES}, **extra}


# ---- OLD_MIND --------------------------------------------------------------------------------------------------
def old_mind(spec: Mapping[str, Any], traces: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = v1.mind(v1_problem(spec), seeds=SEEDS, traces=traces)
    answers = {a: {"disposition": v["disposition"], "reason": v["reason"]} for a, v in rec["answers"].items()}
    return _record("OLD_MIND", spec, answers, seeds=list(SEEDS), primary_seed=PRIMARY_SEED,
                   disposition_by_seed=rec["disposition_by_seed"], v1_record=rec)


# ---- SEMANTIC_ROLES_ONLY ---------------------------------------------------------------------------------------
def _roles_voltage_pool(trajs: Sequence[v1common.Trajectory], band: float) -> v1.Pool:
    """No measured OCV: v1's voltage observable posed by role: settable (t_on, current), covariate (temperature).
    The charge state is not a free covariate."""
    X, C, y, refs, sc = [], [], [], [], []
    for tr, z in zip(trajs, v1._z(trajs)):
        for s, e in v1._runs(tr.current, band):
            for k in range(s, e + 1):
                if z[k] <= v1.MIN_SOC:
                    continue
                X.append([tr.t[k] - tr.t[s - 1], abs(tr.current[k])]); C.append([tr.temperature[k] + v1.KELVIN])
                y.append(tr.voltage[k]); sc.append(1.0); refs.append(f"{tr.traj_id}#{k}")
    return v1.Pool(("t_on_s", "I_A"), ("T_K",), np.array(X, float).reshape(-1, 2), np.array(C, float).reshape(-1, 1),
                   np.array(y, float), refs, v1._dt_median(trajs), np.array(sc, float), "V")


def _roles_pool(trajs: Sequence[v1common.Trajectory], band: float, ocv_knots: np.ndarray | None) -> v1.Pool:
    return _roles_load_pool(trajs, band, ocv_knots) if ocv_knots is not None else _roles_voltage_pool(trajs, band)


def _roles_answers(spec: Mapping[str, Any], seed: int) -> dict[str, dict[str, Any]]:
    problem = v1_problem(spec)
    roles = RoleTable.from_spec(spec)
    if not [n for n in roles.names(VariableRole.CONTROLLED_INPUT) if n != spec["clock"]]:
        raise ValueError("SEMANTIC_ROLES_ONLY is defined for a declared controlled input")
    pid, band = problem.problem_id, problem.rest_band
    cal = problem.calibration()
    _rec, run, _ = v1.run_probe(pid, "RELAXATION", v1.relax_pool(cal, band), seed)
    if run is None:
        rx = v1.TRANSLATION["RELAXATION"]["problem_refused"]
        rx_reason = "the relaxation probe is refused by the Mind's problem constructor"
    else:
        rx, key = v1._translate("RELAXATION", run, "t_off_s")
        rx_reason = f"relaxation probe: {key}"
    na = "not representable: the v1 answer vocabulary has no judgment of the declared family"
    answers = {"IDENTIFIABILITY": {"disposition": rx, "reason": rx_reason},
               "MODEL_ADEQUACY": {"disposition": NOT_ASSESSABLE, "reason": na},
               "MODEL_DISCREPANCY": {"disposition": NOT_ASSESSABLE, "reason": na}}
    pool = _roles_pool(cal, band, problem.ocv_knots)
    for set_name, axis in (("within_cell_heldout", "WITHIN_CELL_GENERALIZATION"), ("cross_cell_heldout", "CROSS_CELL_TRANSFER")):
        sets = problem.heldout(set_name)
        if sets is None:
            answers[axis] = {"disposition": NOT_ASSESSABLE, "reason": "no held-out set of this kind is supplied"}
            continue
        subs, why = [], {}
        for subset, trajs in sets.items():
            ho = _roles_pool(trajs, band, problem.ocv_knots)
            region = v1._region(ho)
            if region is None:
                subs.append(NOT_ASSESSABLE); why[subset] = "empty region"
                continue
            _rec, run, mp = v1.run_probe(pid, f"PREDICTION[{set_name}/{subset}]", pool, seed, region)
            if run is None:
                subs.append(REFUSED); why[subset] = "problem refused"
            elif run.conclusion.kind is ConclusionKind.LAW:
                ev = v1._evaluate_law(run, mp, ho, problem.acceptance(set_name, subset), problem.voltage_sigma())
                subs.append(SUPPORTED if ev["meets_bar"] else NOT_SUPPORTED)
                why[subset] = f"law against the bar: rmse {ev['stats']['rmse_mV']:.4g} mV"
            else:
                subs.append(v1.TRANSLATION["PREDICTION"][run.conclusion.kind.value]); why[subset] = run.conclusion.kind.value
        answers[axis] = {"disposition": combine(subs), "reason": "; ".join(f"{k}: {v}" for k, v in sorted(why.items()))}
    return answers


def roles_mind(spec: Mapping[str, Any]) -> dict[str, Any]:
    per_seed = {str(s): _roles_answers(spec, s) for s in SEEDS}
    answers = per_seed[str(PRIMARY_SEED)]
    return _record("SEMANTIC_ROLES_ONLY", spec, answers, seeds=list(SEEDS), primary_seed=PRIMARY_SEED,
                   disposition_by_seed={s: {a: v["disposition"] for a, v in ans.items()} for s, ans in per_seed.items()},
                   answers_by_seed=per_seed)


# ---- the representation arms -----------------------------------------------------------------------------------
def _claim_answer(c: Any) -> dict[str, Any]:
    out = {"disposition": c.disposition.value, "reason": c.reason}
    if c.refusal is not None:
        out["refusal_reason"] = c.refusal.reason.value
    return out


def representation_arm(arm: str, spec: Mapping[str, Any], legacy: bool) -> dict[str, Any]:
    a = assess(spec, families_for(spec), roles=legacy_role_table(spec) if legacy else None)
    answers = {axis: _claim_answer(c) for axis, c in a.claims.items()}
    return _record(arm, spec, answers, roles="legacy" if legacy else "declared", assessment=a.to_dict())


def representation_only(spec: Mapping[str, Any]) -> dict[str, Any]:
    return representation_arm("REPRESENTATION_ONLY", spec, legacy=True)


def combined(spec: Mapping[str, Any]) -> dict[str, Any]:
    return representation_arm("REPRESENTATION_PLUS_ROLES", spec, legacy=False)


# ---- the baselines (v1 code on the v1 view) --------------------------------------------------------------------
def _v1_baseline(arm: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    rec = v1base.ARMS[arm](v1_problem(spec))
    answers = {a: {"disposition": v["disposition"], "reason": v["reason"]} for a, v in rec["answers"].items()}
    return _record(arm, spec, answers, v1_record=rec)


RUN = {"OLD_MIND": old_mind, "REPRESENTATION_ONLY": representation_only, "SEMANTIC_ROLES_ONLY": roles_mind,
       "REPRESENTATION_PLUS_ROLES": combined,
       **{a: (lambda spec, _a=a: _v1_baseline(_a, spec)) for a in ("CAREFUL_BASELINE", *REFERENCE_ARMS)}}

__all__ = ["ALL_ARMS", "ARMS", "REFERENCE_ARMS", "RUN", "combined", "families_for", "old_mind", "representation_arm",
           "representation_only", "roles_mind"]
