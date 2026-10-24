"""Scoped judgments of a declared model family, bound through declared roles; deterministic and replayable.

:func:`assess` answers the five battery_rediscovery_v1 questions about a problem's declared family:

1. bind the family to the problem through its role table (:mod:`.families`); a binding failure refuses every question
   that needs the family as REPRESENTATION_UNAVAILABLE;
2. calibrate the latent parameters by least squares from a fixed, deterministic set of starts (no randomness);
3. judge each question under its claim type (:data:`.claims.CLAIM_TYPES`), applying the refusal rule: a non-committal
   answer only under a named condition that is shown to hold, and a representable negative conclusion (NOT_SUPPORTED)
   in preference to NOT_ASSESSABLE whenever the evidence decides it;
4. record a :class:`.hypothesis.ScientificHypothesis` and every evidence payload by digest.

Order of checks, where it matters scientifically: an absent held-out set is answered before anything is fitted;
applicability (domain and unit relation) is checked before any held-out prediction is computed, and an out-of-domain
subset is never scored; identifiability needs a declared noise to be SUPPORTED but a rank-deficient Jacobian decides
NOT_IDENTIFIABLE without one; compatibility of residuals with noise needs a declared noise, but resolved structure
decides PRESENT without one.

This layer issues proposals for the caller's authority.  It validates nothing and quantifies no uncertainty that was
not declared: a missing noise is never replaced by a residual estimate.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import chi2

from ...hybrid_uq.identifiability import CANONICAL_IDENTIFIABILITY_THRESHOLDS, classify
from ...inference.calibration import IdentifiabilityStatus
from .claims import CLAIM_TYPES, Disposition, RefusalReason, ScopedClaim, decided, refused
from .families import Binding, BindingRefused, BoundTrajectory, DeclaredFamily, bind, bind_trajectory
from .hypothesis import EvidenceItem, ParameterEstimate, ScientificHypothesis
from .roles import PROBLEM_SCHEMA, RoleRefused, RoleTable, VariableRole, legacy_role_table

ASSESSMENT_SCHEMA = "forge.mind.repsem.assessment/1"
ENGINE_ID = "forge.mind.repsem"
ENGINE_VERSION = "1.0.0"

START_QUANTILES = (0.3, 0.7)          # per-parameter starts in log-bounds, plus the centre: 2^p + 1 starts
MAX_NFEV = 200
FD_STEP = 1e-6                        # central-difference step in ln(parameter)
RANK_TOL = 1e-8                       # structural rank deficiency: smallest/largest singular value of the scaled Jacobian
CHI2_LEVEL = 0.999
AUTOCORR_Z = 3.29                     # one-sided 0.0005: resolved positive lag-1 residual correlation
COVERAGE_Z = 1.959963984540054        # the 95% marginal interval the frozen V1 rule classifies
BOUND_TOL = 1e-6                      # an estimate this close (in ln) to its bound is on the bound
SETS = {"WITHIN_CELL_GENERALIZATION": "within_unit_heldout", "CROSS_CELL_TRANSFER": "cross_unit_heldout"}
AXES = ("IDENTIFIABILITY", "MODEL_ADEQUACY", "MODEL_DISCREPANCY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER")


class ReplayMismatch(RuntimeError):
    """A recorded assessment that does not re-execute byte-identically against its problem."""


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _num(x: float) -> float | None:
    """A deterministic, JSON-safe number: 12 significant digits, None when not finite."""
    x = float(x)
    return float(f"{x:.12g}") if math.isfinite(x) else None


# ---- the fit -------------------------------------------------------------------------------------------------------
@dataclass
class Fit:
    family: DeclaredFamily
    binding: Binding
    names: tuple[str, ...]
    theta: np.ndarray
    log_lo: np.ndarray
    log_hi: np.ndarray
    residuals: list[np.ndarray]          # per calibration trajectory, scored samples (after the first)
    jac_log: np.ndarray                  # d residual / d ln(theta), unweighted
    states: list[Mapping[str, np.ndarray]]
    starts: int
    converged_cost: float

    @property
    def n(self) -> int:
        return int(sum(len(r) for r in self.residuals))

    @property
    def flat(self) -> np.ndarray:
        return np.concatenate(self.residuals)


def _predict(family: DeclaredFamily, params: Mapping[str, float], traj: BoundTrajectory, constants: Mapping[str, Any]
             ) -> tuple[np.ndarray, Mapping[str, np.ndarray]]:
    y, states = family.simulate(params, traj, constants)
    return np.asarray(y, float), {k: np.asarray(v, float) for k, v in states.items()}


def _fit(family: DeclaredFamily, binding: Binding, trajs: Sequence[BoundTrajectory], bounds: Mapping[str, Sequence[float]],
         constants: Mapping[str, Any]) -> Fit:
    names = tuple(family.parameters)
    lo = np.array([math.log(float(bounds[n][0])) for n in names])
    hi = np.array([math.log(float(bounds[n][1])) for n in names])

    def resid(x: np.ndarray) -> np.ndarray:
        p = dict(zip(names, np.exp(x)))
        return np.concatenate([(_predict(family, p, t, constants)[0] - t.measurement)[1:] for t in trajs])

    starts = [lo + 0.5 * (hi - lo)] + [lo + np.array(q) * (hi - lo)
                                       for q in itertools.product(START_QUANTILES, repeat=len(names))]
    best = None
    for x0 in starts:
        r = least_squares(resid, x0, bounds=(lo, hi), method="trf", xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=MAX_NFEV)
        if best is None or r.cost < best.cost - 1e-15:
            best = r
    x = best.x
    jac = np.zeros((len(resid(x)), len(names)))
    for j in range(len(names)):
        up, dn = x.copy(), x.copy()
        up[j] = min(x[j] + FD_STEP, hi[j]); dn[j] = max(x[j] - FD_STEP, lo[j])
        jac[:, j] = (resid(up) - resid(dn)) / (up[j] - dn[j])
    p = dict(zip(names, np.exp(x)))
    res, states = [], []
    for t in trajs:
        y, s = _predict(family, p, t, constants)
        res.append((y - t.measurement)[1:]); states.append(s)
    return Fit(family, binding, names, np.exp(x), lo, hi, res, jac, states, len(starts), float(best.cost))


# ---- the judgments -------------------------------------------------------------------------------------------------
class _Ledger:
    """Evidence payloads by digest: every number a claim rests on is recorded and replayed."""

    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def add(self, kind: str, payload: Mapping[str, Any]) -> str:
        body = {"kind": kind, **payload}
        d = "sha256:" + _digest(body)
        self.items[d] = body
        return d


def _scope(fit: Fit | None, binding: Binding | None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if binding is not None:
        out["family"] = binding.family_id
        out["binding"] = binding.to_dict()
    if extra:
        out.update(extra)
    return out


def _identifiability(fit: Fit, spec: Mapping[str, Any], roles: RoleTable, sigma: float | None, led: _Ledger) -> ScopedClaim:
    axis = "IDENTIFIABILITY"
    requested = list(spec.get("requested_parameters", ()))
    latent = set(roles.names(VariableRole.LATENT_PARAMETER))
    bad = sorted(set(requested) - (latent & set(fit.names)))
    if not requested or bad:
        return refused(axis, Disposition.REFUSED, RefusalReason.REPRESENTATION_UNAVAILABLE,
                       {"requested": requested, "not_declared_latent_parameters_of_family": bad},
                       scope=_scope(fit, fit.binding), why="the requested parameters are not declared latent parameters "
                       "of the bound family")
    idx = [fit.names.index(n) for n in requested]
    J = fit.jac_log
    norms = np.linalg.norm(J, axis=0)
    scaled = J / np.where(norms > 0, norms, 1.0)
    sv = np.linalg.svd(scaled, compute_uv=False)
    ratio = float(sv[-1] / sv[0]) if sv[0] > 0 else 0.0
    sub_rank_deficient = bool(np.any(norms[idx] == 0.0)) or _sub_ratio(scaled[:, idx]) < RANK_TOL
    structural = {"singular_values_scaled": [_num(v) for v in sv], "ratio": _num(ratio),
                  "column_norms": {n: _num(norms[i]) for i, n in enumerate(fit.names)}, "rank_tol": RANK_TOL,
                  "requested": requested}
    scope = _scope(fit, fit.binding, {"design": "calibration set", "parameters": requested,
                                      "bounds": {n: [_num(math.exp(fit.log_lo[i])), _num(math.exp(fit.log_hi[i]))]
                                                 for i, n in enumerate(fit.names)}})
    if sub_rank_deficient:
        ev = led.add("jacobian_rank", structural)
        return decided(axis, False, evidence=(ev,), scope=scope,
                       reason="the residual Jacobian is rank-deficient in the requested parameters: no data of this "
                              "design separate them, whatever the noise")
    if sigma is None:
        return refused(axis, Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE,
                       {**structural, "declared_noise": None}, scope=scope,
                       why="full rank, but practical identifiability needs a declared measurement noise, and none is "
                           "declared (a residual estimate is not substituted)")
    on_bound = [n for i, n in enumerate(fit.names) if n in requested and
                (math.log(fit.theta[i]) - fit.log_lo[i] < BOUND_TOL or fit.log_hi[i] - math.log(fit.theta[i]) < BOUND_TOL)]
    Jn = J / fit.theta[None, :]                       # d residual / d theta
    info = (Jn.T @ Jn) / sigma ** 2
    try:
        cov = np.linalg.inv(info)
    except np.linalg.LinAlgError:
        cov = np.full_like(info, np.inf)
    sub = cov[np.ix_(idx, idx)]
    mean = fit.theta[idx]
    if not np.all(np.isfinite(sub)) or np.any(np.diag(sub) <= 0):
        ev = led.add("fisher_information", {**structural, "covariance": None, "declared_noise": _num(sigma)})
        return decided(axis, False, evidence=(ev,), scope=scope,
                       reason="the Fisher information is singular in the requested parameters")
    sd = np.sqrt(np.diag(sub))
    status, condition, max_corr, widths, why = classify(mean, sub, mean - COVERAGE_Z * sd, mean + COVERAGE_Z * sd, requested,
                                                        **CANONICAL_IDENTIFIABILITY_THRESHOLDS)
    payload = {**structural, "declared_noise": _num(sigma), "estimate": {n: _num(v) for n, v in zip(requested, mean)},
               "standard_error": {n: _num(v) for n, v in zip(requested, sd)}, "condition": _num(condition),
               "max_correlation": _num(max_corr), "relative_widths": [_num(w) for w in widths],
               "frozen_rule": "engcore.hybrid_uq.identifiability.classify", "thresholds": CANONICAL_IDENTIFIABILITY_THRESHOLDS,
               "status": status.value, "on_bound": on_bound}
    ev = led.add("local_identifiability", payload)
    if status is IdentifiabilityStatus.NOT_IDENTIFIABLE:
        return decided(axis, False, evidence=(ev,), scope=scope, reason=why)
    if on_bound:
        return refused(axis, Disposition.REVIEW, RefusalReason.INSUFFICIENT_EVIDENCE, payload, scope=scope,
                       why=f"{on_bound} sit on their declared bounds, where the local covariance does not describe them")
    if status is IdentifiabilityStatus.IDENTIFIABLE:
        return decided(axis, True, evidence=(ev,), scope=scope, reason=why)
    return refused(axis, Disposition.REVIEW, RefusalReason.INSUFFICIENT_EVIDENCE, payload, scope=scope,
                   why="weakly identified (a ridge): " + why)


def _sub_ratio(m: np.ndarray) -> float:
    sv = np.linalg.svd(m, compute_uv=False)
    return float(sv[-1] / sv[0]) if sv.size and sv[0] > 0 else 0.0


def _residual_stats(fit: Fit, sigma: float | None, independent: bool | None) -> dict[str, Any]:
    r = fit.flat
    a = np.abs(r)
    num = sum(float(np.dot(x[1:], x[:-1])) for x in fit.residuals if len(x) > 1)
    den = float(np.dot(r, r))
    pairs = sum(max(len(x) - 1, 0) for x in fit.residuals)
    rho = num / den if den > 0 else 0.0
    out = {"n": fit.n, "parameters": len(fit.names), "rmse": _num(np.sqrt(np.mean(r ** 2))),
           "p95_abs": _num(np.percentile(a, 95)), "bias": _num(np.mean(r)), "lag1_autocorrelation": _num(rho),
           "lag1_pairs": pairs, "lag1_z": _num(rho * math.sqrt(pairs)) if pairs else None,
           "declared_noise": None if sigma is None else _num(sigma), "declared_independent": independent}
    if sigma is not None:
        dof = fit.n - len(fit.names)
        out.update({"chi2": _num(den / sigma ** 2), "dof": dof, "chi2_critical": _num(chi2.ppf(CHI2_LEVEL, dof)),
                    "chi2_level": CHI2_LEVEL})
    return out


def _adequacy(fit: Fit, spec: Mapping[str, Any], sigma: float | None, stats: Mapping[str, Any], led: _Ledger) -> ScopedClaim:
    axis = "MODEL_ADEQUACY"
    bar = spec.get("adequacy_bar")
    scope = _scope(fit, fit.binding, {"set": "calibration"})
    if bar:
        ok = stats["rmse"] <= bar["rmse_max"] and stats["p95_abs"] <= bar["p95_abs_max"]
        ev = led.add("calibration_residuals_vs_bar", {**stats, "bar": dict(bar)})
        return decided(axis, ok, evidence=(ev,), scope={**scope, "basis": "declared adequacy bar"},
                       reason=f"calibration rmse {stats['rmse']:.4g} / p95 {stats['p95_abs']:.4g} against the declared bar "
                              f"{bar['rmse_max']:.4g} / {bar['p95_abs_max']:.4g}")
    if sigma is not None:
        ok = stats["chi2"] <= stats["chi2_critical"]
        ev = led.add("calibration_chi2", dict(stats))
        return decided(axis, ok, evidence=(ev,), scope={**scope, "basis": "declared measurement noise"},
                       reason=f"chi-square {stats['chi2']:.4g} against its {CHI2_LEVEL} quantile {stats['chi2_critical']:.4g}")
    return refused(axis, Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE,
                   {"adequacy_bar": None, "declared_noise": None}, scope=scope,
                   why="neither an adequacy bar nor a measurement noise is declared, so no residual can be judged large")


def _discrepancy(fit: Fit, sigma: float | None, independent: bool | None, stats: Mapping[str, Any], led: _Ledger
                 ) -> ScopedClaim:
    axis = "MODEL_DISCREPANCY"
    scope = _scope(fit, fit.binding, {"set": "calibration"})
    structure = bool(independent) and stats["lag1_z"] is not None and stats["lag1_z"] > AUTOCORR_Z
    magnitude = sigma is not None and stats["chi2"] > stats["chi2_critical"]
    if structure or magnitude:
        ev = led.add("residual_structure", {**stats, "structure_resolved": structure, "magnitude_resolved": magnitude,
                                            "autocorr_z": AUTOCORR_Z})
        what = " and ".join(w for w, on in (("residual autocorrelation", structure), ("excess residual variance", magnitude)) if on)
        return decided(axis, False, evidence=(ev,), scope=scope,
                       reason=f"structured model-form error resolved above the declared noise: {what}")
    if sigma is not None and independent:
        resolution = math.sqrt(max(stats["chi2_critical"] / max(stats["dof"], 1) - 1.0, 0.0)) * sigma
        ev = led.add("residual_structure", {**stats, "structure_resolved": False, "magnitude_resolved": False,
                                            "autocorr_z": AUTOCORR_Z, "resolution_rms": _num(resolution)})
        return decided(axis, True, evidence=(ev,),
                       scope={**scope, "not_quantified_as_zero": True, "resolution_rms": _num(resolution)},
                       reason=f"no discrepancy resolved above the declared noise; anything below about {resolution:.3g} rms "
                              "is not excluded")
    return refused(axis, Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE,
                   {**stats, "structure_resolved": False}, scope=scope,
                   why="no structure is resolved, and compatibility with noise cannot be shown without a declared noise "
                       "and a declared independence")


def _domain(fit: Fit, spec: Mapping[str, Any], roles: RoleTable, trajs: Sequence[BoundTrajectory]) -> dict[str, list[float]]:
    app = spec.get("applicability") or {}
    widen = app.get("widen", {})
    state_slot = {v: s for s, v in fit.binding.slots.items()}
    out = {}
    for var in app.get("variables", ()):
        try:
            role = roles.role(var)
        except RoleRefused as exc:
            raise BindingRefused(str(exc), {"applicability_variable": var, "declared": False}) from None
        if role in (VariableRole.LATENT_PARAMETER, VariableRole.MEASUREMENT, VariableRole.DERIVED_QUANTITY) or (
                role is VariableRole.STATE_VARIABLE and var not in state_slot):
            raise BindingRefused(f"applicability variable {var!r} ({role.value}) cannot bound a domain here: a domain is "
                                 "stated over inputs, protocol conditions, nuisances, or a state the family reconstructs",
                                 {"applicability_variable": var, "role": role.value})
        vals = _values(var, roles, state_slot, trajs, fit.states)
        out[var] = [_num(float(np.min(vals)) - float(widen.get(var, 0.0))), _num(float(np.max(vals)) + float(widen.get(var, 0.0)))]
    return out


def _values(var: str, roles: RoleTable, state_slot: Mapping[str, str], trajs: Sequence[BoundTrajectory],
            states: Sequence[Mapping[str, np.ndarray]]) -> np.ndarray:
    """A domain variable's values: a STATE through the family's reconstruction, never its observed column."""
    if roles.role(var) is VariableRole.STATE_VARIABLE:
        return np.concatenate([s[state_slot[var]] for s in states])
    return np.concatenate([t.columns[var] for t in trajs])


def _transfer(axis: str, fit: Fit | None, spec: Mapping[str, Any], roles: RoleTable, family: DeclaredFamily,
              cal_units: set[str], domain: Mapping[str, Sequence[float]] | None, led: _Ledger) -> ScopedClaim:
    set_name = SETS[axis]
    sets = (spec.get("sets") or {}).get(set_name)
    if not sets:
        return refused(axis, Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE, {"set": set_name, "present": False},
                       why=f"no {set_name} set is supplied")
    if fit is None:
        raise AssertionError("unreachable: a bound family is fitted before transfer is judged")
    if not (spec.get("applicability") or {}).get("variables"):
        return refused(axis, Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE, {"applicability": None},
                       scope=_scope(fit, fit.binding), why="no applicability domain is declared; it is never defaulted")
    constants = spec["declared_family"].get("constants", {})
    params = dict(zip(fit.names, fit.theta))
    state_slot = {v: s for s, v in fit.binding.slots.items()}
    subsets, failed, ood, nobar, met = {}, [], [], [], []
    for sub, raw in sorted(sets.items()):
        bound = [bind_trajectory(family, fit.binding, roles, t) for t in raw]
        units = sorted({t.unit_id for t in bound})
        relation_ok = set(units) <= cal_units if axis == "WITHIN_CELL_GENERALIZATION" else not (set(units) & cal_units)
        preds = [_predict(family, params, t, constants) for t in bound]
        outside = {}
        for var, (lo, hi) in domain.items():
            vals = _values(var, roles, state_slot, bound, [p[1] for p in preds])
            vmin, vmax = float(np.min(vals)), float(np.max(vals))
            if vmin < lo - 1e-12 or vmax > hi + 1e-12:
                outside[var] = {"heldout": [_num(vmin), _num(vmax)], "domain": [lo, hi]}
        if not relation_ok or outside:
            subsets[sub] = {"units": units, "calibration_units": sorted(cal_units), "unit_relation_ok": relation_ok,
                            "outside": outside, "scored": False}
            ood.append(sub)
            continue
        bar = (spec.get("acceptance") or {}).get(f"{set_name}/{sub}")
        if not bar:
            subsets[sub] = {"units": units, "bar": None, "scored": False}
            nobar.append(sub)
            continue
        err = np.concatenate([(y - t.measurement)[1:] for (y, _), t in zip(preds, bound)])
        stats = {"rmse": _num(np.sqrt(np.mean(err ** 2))), "p95_abs": _num(np.percentile(np.abs(err), 95)),
                 "bias": _num(np.mean(err)), "samples": int(err.size)}
        ok = stats["rmse"] <= bar["rmse_max"] and stats["p95_abs"] <= bar["p95_abs_max"]
        subsets[sub] = {"units": units, "bar": dict(bar), "heldout_stats": stats, "meets_bar": ok, "scored": True}
        (met if ok else failed).append(sub)
    scope = _scope(fit, fit.binding, {"set": set_name, "domain": dict(domain), "calibration_units": sorted(cal_units)})
    if failed:
        ev = led.add("heldout_prediction", {"set": set_name, "subsets": subsets})
        return decided(axis, False, evidence=(ev,), scope=scope,
                       reason=f"in-domain held-out subsets {failed} fail the declared bar")
    if ood:
        return refused(axis, Disposition.REFUSED, RefusalReason.OUT_OF_DOMAIN,
                       {"set": set_name, "out_of_domain": {k: subsets[k] for k in ood}}, scope=scope,
                       why=f"held-out subsets {ood} leave the declared applicability domain or the unit relation; they are "
                           "not scored, and the rest cannot carry support for the whole set")
    if nobar:
        return refused(axis, Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE,
                       {"set": set_name, "subsets_without_bar": nobar}, scope=scope,
                       why=f"no acceptance bar is declared for {nobar}; risk policy sets the bar and none was set")
    ev = led.add("heldout_prediction", {"set": set_name, "subsets": subsets})
    return decided(axis, True, evidence=(ev,), scope=scope, reason=f"every held-out subset {met} meets its declared bar")


def _rival(spec: Mapping[str, Any], families: Mapping[str, DeclaredFamily], roles: RoleTable, fit: Fit,
           cal_raw: Sequence[Mapping[str, Any]], sigma: float | None, led: _Ledger
           ) -> tuple[list[dict[str, Any]], list[EvidenceItem], list[EvidenceItem], list[str]]:
    decl = spec["declared_family"]
    rid = decl.get("rival")
    if not rid:
        return [], [], [], ["no competing family is declared, so none was discriminated"]
    if rid not in families:
        return [{"family_id": rid, "status": "NOT_REPRESENTED"}], [], [], [f"rival {rid} has no implementation here"]
    rival = families[rid]
    try:
        rb = bind(rival, roles, spec["clock"])
        rtrajs = [bind_trajectory(rival, rb, roles, t) for t in cal_raw]
        rbounds = decl.get("rival_parameter_bounds") or decl["parameter_bounds"]
        rfit = _fit(rival, rb, rtrajs, rbounds, decl.get("constants", {}))
    except BindingRefused as exc:
        return [{"family_id": rid, "status": "NOT_BOUND", "why": str(exc)}], [], [], [f"rival {rid} cannot be bound"]
    rss_f, rss_r = float(np.dot(fit.flat, fit.flat)), float(np.dot(rfit.flat, rfit.flat))
    payload = {"family": fit.binding.family_id, "rival": rid, "rss_family": _num(rss_f), "rss_rival": _num(rss_r),
               "parameters_family": len(fit.names), "parameters_rival": len(rfit.names)}
    if sigma is None:
        ev = led.add("rival_comparison", {**payload, "declared_noise": None})
        return ([{"family_id": rid, "status": "NOT_DISCRIMINATED"}], [], [],
                [f"{fit.binding.family_id} vs {rid}: no declared noise to judge the residual difference"])
    df = len(fit.names) - len(rfit.names)
    delta = (rss_r - rss_f) / sigma ** 2
    crit = float(chi2.ppf(CHI2_LEVEL, max(df, 1)))
    payload.update({"declared_noise": _num(sigma), "delta_chi2": _num(delta), "critical": _num(crit), "df": df})
    ev = led.add("rival_comparison", payload)
    item = EvidenceItem("rival_comparison", ev, f"delta chi-square {delta:.4g} vs {crit:.4g} ({df} df)")
    if delta > crit:
        return [{"family_id": rid, "status": "DISFAVOURED", "evidence": ev}], [item], [], []
    return ([{"family_id": rid, "status": "NOT_DISCRIMINATED", "evidence": ev}], [], [],
            [f"{fit.binding.family_id} vs {rid}: the calibration data do not discriminate them"])


# ---- the record ----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Assessment:
    problem_digest: str
    roles: RoleTable
    binding: Mapping[str, Any]
    claims: Mapping[str, ScopedClaim]
    hypothesis: ScientificHypothesis
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ASSESSMENT_SCHEMA, "engine": f"{ENGINE_ID}@{ENGINE_VERSION}", "problem_digest": self.problem_digest,
                "roles": self.roles.to_dict(), "binding": dict(self.binding),
                "claims": {k: c.to_dict() for k, c in sorted(self.claims.items())},
                "hypothesis": self.hypothesis.to_dict(), "evidence": dict(sorted(self.evidence.items())),
                "claim_types": {k: CLAIM_TYPES[k].to_dict() for k in sorted(self.claims)}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Assessment":
        if d.get("schema") != ASSESSMENT_SCHEMA:
            raise ReplayMismatch(f"not an assessment: {d.get('schema')!r}")
        return cls(d["problem_digest"], RoleTable.from_dict(d["roles"]), dict(d["binding"]),
                   {k: ScopedClaim.from_dict(v) for k, v in d["claims"].items()},
                   ScientificHypothesis.from_dict(d["hypothesis"]), dict(d["evidence"]))

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def problem_digest(spec: Mapping[str, Any]) -> str:
    return _digest(spec)


def assess(spec: Mapping[str, Any], families: Mapping[str, DeclaredFamily], *, roles: RoleTable | None = None) -> Assessment:
    if spec.get("schema") != PROBLEM_SCHEMA:
        raise ValueError(f"not a repsem problem: {spec.get('schema')!r}")
    pdig = problem_digest(spec)
    roles = roles if roles is not None else RoleTable.from_spec(spec)
    decl = spec["declared_family"]
    family = families[decl["family_id"]]
    noise = spec.get("measurement_noise") or {}
    sigma = None if noise.get("sigma") is None else float(noise["sigma"])
    independent = noise.get("independent")
    led = _Ledger()
    cal_raw = list(spec["sets"]["calibration"])
    claims: dict[str, ScopedClaim] = {}
    try:
        binding = bind(family, roles, spec["clock"])
        cal = [bind_trajectory(family, binding, roles, t) for t in cal_raw]
    except BindingRefused as exc:
        cond = {"family": decl["family_id"], **exc.condition, "why": str(exc)}
        for axis in AXES:
            if axis in SETS and not (spec.get("sets") or {}).get(SETS[axis]):
                claims[axis] = refused(axis, Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE,
                                       {"set": SETS[axis], "present": False}, why=f"no {SETS[axis]} set is supplied")
            else:
                claims[axis] = refused(axis, Disposition.REFUSED, RefusalReason.REPRESENTATION_UNAVAILABLE, cond,
                                       why=f"the declared family cannot be bound through the declared roles: {exc}")
        hyp = ScientificHypothesis(f"repsem:{decl['family_id']}:{pdig[:16]}", {**family.to_dict(), "bound": False}, (),
                                   {}, roles, tuple(claims[a] for a in AXES), (), (), (),
                                   ("the family is not bound, so nothing about it was discriminated",))
        return Assessment(pdig, roles, {"refused": cond}, claims, hyp, led.items)
    fit = _fit(family, binding, cal, decl["parameter_bounds"], decl.get("constants", {}))
    stats = _residual_stats(fit, sigma, independent)
    claims["IDENTIFIABILITY"] = _identifiability(fit, spec, roles, sigma, led)
    claims["MODEL_ADEQUACY"] = _adequacy(fit, spec, sigma, stats, led)
    claims["MODEL_DISCREPANCY"] = _discrepancy(fit, sigma, independent, stats, led)
    cal_units = {t.unit_id for t in cal}
    try:
        domain = _domain(fit, spec, roles, cal)
    except BindingRefused as exc:
        domain = {}
        for axis in SETS:
            claims[axis] = (_transfer(axis, fit, {**spec, "applicability": None}, roles, family, cal_units, {}, led)
                            if not (spec.get("sets") or {}).get(SETS[axis]) else
                            refused(axis, Disposition.REFUSED, RefusalReason.REPRESENTATION_UNAVAILABLE,
                                    {**exc.condition, "why": str(exc)}, scope=_scope(fit, fit.binding),
                                    why=f"the declared applicability domain cannot be represented: {exc}"))
    else:
        for axis in SETS:
            claims[axis] = _transfer(axis, fit, spec, roles, family, cal_units, domain, led)
    alternatives, ev_for, ev_against, unresolved = _rival(spec, families, roles, fit, cal_raw, sigma, led)
    for c in claims.values():
        if c.disposition is Disposition.SUPPORTED:
            ev_for += [EvidenceItem(c.axis, e, c.reason) for e in c.evidence]
        elif c.disposition is Disposition.NOT_SUPPORTED:
            ev_against += [EvidenceItem(c.axis, e, c.reason) for e in c.evidence]
        else:
            unresolved.append(f"{c.axis}: {c.disposition.value} ({c.refusal.reason.value})")
    se = {}
    if sigma is not None:
        Jn = fit.jac_log / fit.theta[None, :]
        try:
            cov = np.linalg.inv((Jn.T @ Jn) / sigma ** 2)
            se = {n: _num(math.sqrt(cov[i, i])) if cov[i, i] > 0 else None for i, n in enumerate(fit.names)}
        except np.linalg.LinAlgError:
            se = {}
    params = tuple(ParameterEstimate(n, _num(math.exp(fit.log_lo[i])), _num(math.exp(fit.log_hi[i])), _num(fit.theta[i]),
                                     se.get(n)) for i, n in sorted(enumerate(fit.names), key=lambda x: x[1]))
    hyp = ScientificHypothesis(
        f"repsem:{decl['family_id']}:{pdig[:16]}", {**family.to_dict(), "bound": True, "starts": fit.starts,
                                                    "cost": _num(fit.converged_cost)},
        params, {"variables": dict(domain), "units": sorted(cal_units)}, roles, tuple(claims[a] for a in AXES),
        tuple(alternatives), tuple(ev_for), tuple(ev_against), tuple(unresolved))
    return Assessment(pdig, roles, binding.to_dict(), claims, hyp, led.items)


def replay(record: Mapping[str, Any], spec: Mapping[str, Any], families: Mapping[str, DeclaredFamily]) -> dict[str, Any]:
    """Re-execute a recorded assessment against its problem; any byte of difference raises :class:`ReplayMismatch`."""
    try:
        stored = Assessment.from_dict(record)
    except (ValueError, KeyError, TypeError) as exc:      # an unreadable or self-contradictory record is not replayable
        raise ReplayMismatch(f"the record does not parse as an assessment: {exc}") from exc
    if stored.problem_digest != problem_digest(spec):
        raise ReplayMismatch("the record was produced for another problem (problem digest differs)")
    declared = {RoleTable.from_spec(spec).digest: "declared"}
    try:
        declared[legacy_role_table(spec).digest] = "legacy"
    except Exception:                                  # noqa: BLE001 - a spec without legacy fields has no legacy table
        pass
    if stored.roles.digest not in declared:
        raise ReplayMismatch("the record's roles are neither the problem's declared roles nor the legacy adapter rule")
    again = assess(spec, families, roles=stored.roles).to_dict()
    if canonical_bytes(again) != canonical_bytes(dict(record)):
        diff = sorted(k for k in set(again) | set(record) if canonical_bytes(again.get(k)) != canonical_bytes(record.get(k)))
        raise ReplayMismatch(f"re-execution differs in {diff}")
    return {"status": "EXACT", "digest": _digest(again), "roles": declared[stored.roles.digest]}


__all__ = ["ASSESSMENT_SCHEMA", "AXES", "Assessment", "ENGINE_ID", "ENGINE_VERSION", "PROBLEM_SCHEMA", "ReplayMismatch",
           "assess", "canonical_bytes", "problem_digest", "replay"]
