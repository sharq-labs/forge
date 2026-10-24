"""Synthetic scientific fixtures whose answers are known from construction (development evidence only).

Each fixture is a driven first-order electrical system: a controlled current waveform, a charge state integrated from
it, a fixed open-circuit curve, and one RC branch.  The DECLARED family is always ``rc1/1`` (rival ``rint/1``, R1 = 0);
what generates the data differs per fixture, and that difference is the ground truth:

====================================  ========================================================================  =========
fixture                               data-generating process / design                                          decides
====================================  ========================================================================  =========
IDENTIFIABLE                          rc1 itself; pulses from rest excite R0 (step), R1 and C1 (relaxation)     all axes
NON_IDENTIFIABLE                      rc1; constant current from a steady polarization: V = g(s) - I (R0 + R1)  ID = NOT
                                      exactly, so R0/R1 enter only as a sum and C1 not at all
MODEL_INADEQUATE                      rc1 plus a charge-transfer overpotential 0.08 asinh(I / 0.3) V: not       ADEQ/DISC/
                                      linear in I, so no single R0 carries it at both protocol levels (1, 2 A)  WITHIN = NOT
                                      and the 1.5 A held-out level misses it by over 10 mV
CROSS_DOMAIN_TRANSFER_FAIL            rc1; the cross-unit cell has R0 = 0.026 ohm instead of 0.010 (24 mV       CROSS = NOT
                                      during 1.5 A pulses), so the calibrated rc1 misses it
MODEL_DISCREPANCY                     rc1 with an open-circuit curve that differs from the declared one by a    DISC = NOT,
                                      3 mV sinusoid in s (3 sigma, structured), well inside the 5 mV bar        ADEQ = SUP
OUT_OF_DOMAIN                         rc1; held-out pulses at 3 A and 40 C, beyond the calibration's 0-2 A,     WITHIN/CROSS
                                      25 C and charge range                                                     = REFUSE
====================================  ========================================================================  =========

Roles are part of each problem specification (protocol metadata), never inferred: ``current_A`` CONTROLLED_INPUT,
``level_A`` (the pulse amplitude the protocol set for the run) FIXED_PROTOCOL_CONDITION, ``soc`` STATE_VARIABLE driven
by the current (its column is a noisy estimate the judgment must not use), ``voltage_V`` MEASUREMENT, ``power_W``
DERIVED_QUANTITY, ``temperature_C`` NUISANCE_VARIABLE, ``t_s`` FIXED_PROTOCOL_CONDITION (the sampling schedule),
``R0``/``R1``/``C1`` LATENT_PARAMETER.  No battery v1 data, answer or truth is used anywhere here.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
from scipy.signal import lfilter

from engcore.mind.repsem import BoundTrajectory, DeclaredFamily, FamilySlot, VariableRole

FIXTURES = ("IDENTIFIABLE", "NON_IDENTIFIABLE", "MODEL_INADEQUATE", "CROSS_DOMAIN_TRANSFER_FAIL", "MODEL_DISCREPANCY",
            "OUT_OF_DOMAIN")
SEEDS = (0, 1, 2, 3, 4)
#: "short": 20 s pulses / 60 s rests at 1 s sampling (the design written first).  "long": 200 s pulses / 300 s rests,
#: added after the OLD_MIND probe showed that v1's adapter cannot pose a 20 s pulse at all (its time box starts at
#: median(dt) / 0.05 = 20 s), so that the Mind-based arms are also tested where they can act.
PROTOCOLS = ("short", "long")
SUP, NOT, REFUSE = "SUPPORTED", "NOT_SUPPORTED", "REFUSE"

#: Ground truth from construction; None = not scored (identifiability under a misspecified family has no single
#: construction-time answer, so it is left out rather than guessed).
TRUTH = {
    "IDENTIFIABLE": {"IDENTIFIABILITY": SUP, "MODEL_ADEQUACY": SUP, "MODEL_DISCREPANCY": SUP,
                     "WITHIN_CELL_GENERALIZATION": SUP, "CROSS_CELL_TRANSFER": REFUSE},
    "NON_IDENTIFIABLE": {"IDENTIFIABILITY": NOT, "MODEL_ADEQUACY": SUP, "MODEL_DISCREPANCY": SUP,
                         "WITHIN_CELL_GENERALIZATION": SUP, "CROSS_CELL_TRANSFER": REFUSE},
    # WITHIN is SUP, not NOT: the construction audit shows the calibrated rc1 predicts the interpolated 1.5 A level to
    # 2.2 mV rmse although it misses the calibration levels by 16 mV (an inadequate family can still interpolate).
    "MODEL_INADEQUATE": {"IDENTIFIABILITY": None, "MODEL_ADEQUACY": NOT, "MODEL_DISCREPANCY": NOT,
                         "WITHIN_CELL_GENERALIZATION": SUP, "CROSS_CELL_TRANSFER": REFUSE},
    "CROSS_DOMAIN_TRANSFER_FAIL": {"IDENTIFIABILITY": SUP, "MODEL_ADEQUACY": SUP, "MODEL_DISCREPANCY": SUP,
                                   "WITHIN_CELL_GENERALIZATION": SUP, "CROSS_CELL_TRANSFER": NOT},
    "MODEL_DISCREPANCY": {"IDENTIFIABILITY": None, "MODEL_ADEQUACY": SUP, "MODEL_DISCREPANCY": NOT,
                          "WITHIN_CELL_GENERALIZATION": SUP, "CROSS_CELL_TRANSFER": REFUSE},
    "OUT_OF_DOMAIN": {"IDENTIFIABILITY": SUP, "MODEL_ADEQUACY": SUP, "MODEL_DISCREPANCY": SUP,
                      "WITHIN_CELL_GENERALIZATION": REFUSE, "CROSS_CELL_TRANSFER": REFUSE},
}

#: Labels the construction audit does not support under the long protocol are unscored there (None), never guessed:
#: at the true parameters the long design is only WEAKLY_IDENTIFIABLE (fewer steps), and the inadequate family's 1.5 A
#: interpolation (2.8 mV rmse) lies between the audit's SUP and NOT margins.
TRUTH_OVERRIDES = {"long": {("IDENTIFIABLE", "IDENTIFIABILITY"): None, ("CROSS_DOMAIN_TRANSFER_FAIL", "IDENTIFIABILITY"): None,
                            ("OUT_OF_DOMAIN", "IDENTIFIABILITY"): None, ("MODEL_INADEQUATE", "WITHIN_CELL_GENERALIZATION"): None}}


def truth(kind: str, protocol: str = "short") -> dict[str, str | None]:
    out = dict(TRUTH[kind])
    for (k, axis), label in TRUTH_OVERRIDES.get(protocol, {}).items():
        if k == kind:
            out[axis] = label
    return out


SIGMA = 0.001
TRUE = {"R0": 0.010, "R1": 0.015, "C1": 1000.0}
BOUNDS = {"R0": [1e-4, 0.5], "R1": [1e-4, 0.5], "C1": [1.0, 1e5]}
OCV_KNOTS = [[s, 3.0 + 1.0 * s + 0.15 * math.sin(3.0 * s)] for s in np.linspace(0.0, 1.0, 11)]
BAR = {"rmse_max": 0.005, "p95_abs_max": 0.010}


# ---- the declared families -----------------------------------------------------------------------------------------
def _ocv(s: np.ndarray, knots: Any) -> np.ndarray:
    k = np.asarray(knots, float)
    return np.interp(s, k[:, 0], k[:, 1])


def _charge(t: np.ndarray, i: np.ndarray, s0: float, q: float) -> np.ndarray:
    """Backward hold: the current reported at sample k flowed over [t_(k-1), t_k]."""
    return s0 - np.concatenate([[0.0], np.cumsum(i[1:] * np.diff(t))]) / q


def _branch(t: np.ndarray, i: np.ndarray, r: float, c: float, v0: float) -> np.ndarray:
    dt = np.diff(t)
    if not np.allclose(dt, dt[0]):
        raise ValueError("the fixture families need uniform sampling")
    a = math.exp(-dt[0] / (r * c))
    out = np.empty_like(i)
    out[0] = v0
    out[1:] = lfilter([r * (1.0 - a)], [1.0, -a], i[1:], zi=[a * v0])[0]
    return out


def _rc1(params: Mapping[str, float], traj: BoundTrajectory, constants: Mapping[str, Any]):
    t, i = traj.clock, traj.slots["driver"]
    s = _charge(t, i, traj.initial_state["charge_state"], float(constants["capacity_As"]))
    pol = traj.conditions["initial_polarization"]
    v0 = params["R1"] * i[0] if pol == "steady_state" else float(pol)
    v1 = _branch(t, i, params["R1"], params["C1"], v0)
    return _ocv(s, constants["ocv_knots"]) - i * params["R0"] - v1, {"charge_state": s}


def _rint(params: Mapping[str, float], traj: BoundTrajectory, constants: Mapping[str, Any]):
    t, i = traj.clock, traj.slots["driver"]
    s = _charge(t, i, traj.initial_state["charge_state"], float(constants["capacity_As"]))
    return _ocv(s, constants["ocv_knots"]) - i * params["R0"], {"charge_state": s}


_SLOTS = (FamilySlot("driver", (VariableRole.CONTROLLED_INPUT,)),
          FamilySlot("charge_state", (VariableRole.STATE_VARIABLE,), state_of="driver"))
FAMILIES = {
    "rc1/1": DeclaredFamily("rc1/1", "V = g(s) - I R0 - v1; dv1/dt = I/C1 - v1/(R1 C1); ds/dt = -I/Q", _SLOTS,
                            ("R0", "R1", "C1"), _rc1, ("initial_polarization",)),
    "rint/1": DeclaredFamily("rint/1", "V = g(s) - I R0; ds/dt = -I/Q (the R1 = 0 reduction)", _SLOTS, ("R0",), _rint),
}


# ---- data generation -----------------------------------------------------------------------------------------------
def _pulses(level: float, n: int, dt: float = 1.0, rest0: int = 30, on: int = 20, off: int = 60) -> tuple[np.ndarray, np.ndarray]:
    i = [0.0] * rest0
    for _ in range(n):
        i += [level] * on + [0.0] * off
    i = np.array(i)
    return np.arange(len(i)) * dt, i


def _truth_voltage(kind: str, t: np.ndarray, i: np.ndarray, s: np.ndarray, p: Mapping[str, float], pol: Any) -> np.ndarray:
    v0 = p["R1"] * i[0] if pol == "steady_state" else float(pol)
    v = _ocv(s, OCV_KNOTS) - i * p["R0"] - _branch(t, i, p["R1"], p["C1"], v0)
    if kind == "MODEL_INADEQUATE":
        v -= 0.08 * np.arcsinh(i / 0.3)
    if kind == "MODEL_DISCREPANCY":
        v += 0.003 * np.sin(2.0 * math.pi * s / 0.25)
    return v


def _make(kind: str, rng: np.random.Generator, tid: str, unit: str, t: np.ndarray, i: np.ndarray, level: float,
                s0: float, q: float, temp0: float, params: Mapping[str, float], pol: Any, noise: bool = True) -> dict[str, Any]:
    s = _charge(t, i, s0, q)
    v = _truth_voltage(kind, t, i, s, params, pol) + rng.normal(0.0, SIGMA, len(t)) * (1.0 if noise else 0.0)
    temp = temp0 + 0.3 * np.sin(t / 200.0) + rng.normal(0.0, 0.02, len(t))
    soc_est = s + rng.normal(0.0, 0.01, len(t))
    cols = {"t_s": t, "current_A": i, "level_A": np.full(len(t), level), "voltage_V": v, "temperature_C": temp,
            "soc": soc_est, "power_W": i * v}
    return {"id": tid, "unit_id": unit, "columns": {k: [round(float(x), 9) for x in vals] for k, vals in cols.items()},
            "initial_state": {"soc": s0}, "conditions": {"initial_polarization": pol}}


def _variables() -> list[dict[str, Any]]:
    def v(name, role, unit, basis, **kw):
        return {"name": name, "role": role.value, "unit": unit, "source": "protocol_metadata", "basis": basis, **kw}
    R = VariableRole
    return [
        v("t_s", R.FIXED_PROTOCOL_CONDITION, "s", "the protocol's sampling schedule"),
        v("current_A", R.CONTROLLED_INPUT, "A", "the cycler applies the programmed current waveform"),
        v("level_A", R.FIXED_PROTOCOL_CONDITION, "A", "the pulse amplitude the protocol set for the run"),
        v("soc", R.STATE_VARIABLE, "1", "charge state; evolves by coulomb counting of the applied current; the column "
          "is an onboard estimate", driven_by=["current_A"]),
        v("voltage_V", R.MEASUREMENT, "V", "terminal voltage, the measured response"),
        v("power_W", R.DERIVED_QUANTITY, "W", "logged as current times voltage", derived_from=["current_A", "voltage_V"]),
        v("temperature_C", R.NUISANCE_VARIABLE, "degC", "ambient/cell temperature, logged, not controlled"),
        v("R0", R.LATENT_PARAMETER, "ohm", "declared family parameter"),
        v("R1", R.LATENT_PARAMETER, "ohm", "declared family parameter"),
        v("C1", R.LATENT_PARAMETER, "F", "declared family parameter"),
    ]


def build(kind: str, seed: int, *, noise: bool = True, protocol: str = "short") -> dict[str, Any]:
    """The candidate-visible problem specification of one fixture instance (deterministic in its arguments).
    ``noise=False`` is for :func:`construction_audit` only: the same instance without measurement noise.
    ``protocol``: see :data:`PROTOCOLS`."""
    if kind not in FIXTURES or protocol not in PROTOCOLS:
        raise KeyError((kind, protocol))
    long_ = protocol == "long"
    rng = np.random.default_rng([FIXTURES.index(kind), int(seed)] + ([1] if long_ else []))
    on, off, n_cal, n_ho = (200, 300, 6, 5) if long_ else (20, 60, 10, 8)

    def _trajectory(*a: Any) -> dict[str, Any]:
        return _make(*a, noise=noise)
    q = 7200.0 if long_ else 720.0
    within: dict[str, list] = {}
    cross: dict[str, list] = {}
    if kind == "NON_IDENTIFIABLE":
        q = 7200.0
        n = 337
        t = np.arange(n) * 10.0
        i = np.full(n, 1.5)
        cal = [_trajectory(kind, rng, "A1", "A", t, i, 1.5, 1.0, q, 25.0, TRUE, "steady_state")]
        t2 = np.arange(150) * 10.0
        within["continued"] = [_trajectory(kind, rng, "A2", "A", t2, np.full(150, 1.5), 1.5, 0.62, q, 25.0, TRUE,
                                           "steady_state")]
    else:
        cal = []
        for tid, level, s0 in (("A1", 1.0, 1.0), ("A2", 2.0, 0.9), ("A3", 1.0, 0.6)):
            t, i = _pulses(level, n_cal, on=on, off=off)
            cal.append(_trajectory(kind, rng, tid, "A", t, i, level, s0, q, 25.0, TRUE, 0.0))
        if kind == "OUT_OF_DOMAIN":
            t, i = _pulses(3.0, n_cal, on=on, off=off)
            within["high_current_hot"] = [_trajectory(kind, rng, "A4", "A", t, i, 3.0, 0.95, q, 40.0, TRUE, 0.0)]
            cross["high_current_hot"] = [_trajectory(kind, rng, "B1", "B", t, i, 3.0, 0.95, q, 40.0, TRUE, 0.0)]
        else:
            t, i = _pulses(1.5, n_ho, on=on, off=off)
            within["mid_level"] = [_trajectory(kind, rng, "A4", "A", t, i, 1.5, 0.85, q, 25.0, TRUE, 0.0)]
        if kind == "CROSS_DOMAIN_TRANSFER_FAIL":
            t, i = _pulses(1.5, n_ho, on=on, off=off)
            cross["other_unit"] = [_trajectory(kind, rng, "B1", "B", t, i, 1.5, 0.85, q, 25.0, {**TRUE, "R0": 0.026}, 0.0)]
    sets: dict[str, Any] = {"calibration": cal}
    acceptance = {}
    if within:
        sets["within_unit_heldout"] = within
        acceptance.update({f"within_unit_heldout/{k}": dict(BAR) for k in within})
    if cross:
        sets["cross_unit_heldout"] = cross
        acceptance.update({f"cross_unit_heldout/{k}": dict(BAR) for k in cross})
    return {
        "schema": "forge.mind.repsem.problem/1", "problem_id": f"{kind}{'@long' if long_ else ''}#{seed}", "clock": "t_s", "observable": "voltage_V",
        "variables": _variables(),
        "declared_family": {"family_id": "rc1/1", "rival": "rint/1", "parameter_bounds": BOUNDS,
                            "constants": {"capacity_As": q, "ocv_knots": OCV_KNOTS}},
        "requested_parameters": ["R0", "R1", "C1"],
        "measurement_noise": {"sigma": SIGMA, "independent": True},
        "adequacy_bar": dict(BAR),
        "applicability": {"variables": ["current_A", "level_A", "soc", "temperature_C"],
                          "widen": {"current_A": 0.05, "level_A": 0.05, "soc": 0.02, "temperature_C": 1.0}},
        "sets": sets, "acceptance": acceptance,
    }


# ---- construction audit: every TRUTH label checked on noise-free data, by a path independent of the assessor -------
AUDIT_MARGIN = 2.0          # a decided label needs the noise-free quantity at least this factor on its side of the bar
_NAMES = ("R0", "R1", "C1")


def _bt(traj: Mapping[str, Any]) -> BoundTrajectory:
    c = traj["columns"]
    return BoundTrajectory(traj["id"], traj["unit_id"], np.asarray(c["t_s"], float),
                           {"driver": np.asarray(c["current_A"], float)}, {"charge_state": traj["initial_state"]["soc"]},
                           traj["conditions"], np.asarray(c["voltage_V"], float), {})


def _err(params: Mapping[str, float], trajs: list[BoundTrajectory], consts: Mapping[str, Any]) -> np.ndarray:
    return np.concatenate([(_rc1(params, t, consts)[0] - t.measurement)[1:] for t in trajs])


def _oracle_fit(trajs: list[BoundTrajectory], consts: Mapping[str, Any]) -> dict[str, float]:
    """The family's best fit to noise-free data, from a dense 4^3 grid of starts (the assessor uses 2^3 + 1)."""
    from scipy.optimize import least_squares
    lo = np.log([BOUNDS[n][0] for n in _NAMES])
    hi = np.log([BOUNDS[n][1] for n in _NAMES])
    best = None
    for q in np.array(np.meshgrid(*[[0.125, 0.375, 0.625, 0.875]] * 3)).reshape(3, -1).T:
        r = least_squares(lambda x: _err(dict(zip(_NAMES, np.exp(x))), trajs, consts), lo + q * (hi - lo),
                          bounds=(lo, hi), xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=2000)
        if best is None or r.cost < best.cost:
            best = r
    return dict(zip(_NAMES, (float(v) for v in np.exp(best.x))))


def _stats(e: np.ndarray) -> dict[str, float]:
    return {"rmse": float(np.sqrt(np.mean(e ** 2))), "p95_abs": float(np.percentile(np.abs(e), 95))}


def _fim_status(trajs: list[BoundTrajectory], consts: Mapping[str, Any]) -> str:
    """Identifiability of the TRUE parameters under this design and the declared noise (the frozen V1 rule)."""
    from engcore.hybrid_uq.identifiability import CANONICAL_IDENTIFIABILITY_THRESHOLDS, classify
    x = np.log([TRUE[n] for n in _NAMES])
    J = np.zeros((len(_err(TRUE, trajs, consts)), 3))
    for j in range(3):
        up, dn = x.copy(), x.copy()
        up[j] += 1e-6
        dn[j] -= 1e-6
        J[:, j] = (_err(dict(zip(_NAMES, np.exp(up))), trajs, consts) - _err(dict(zip(_NAMES, np.exp(dn))), trajs, consts)) / 2e-6
    norms = np.linalg.norm(J, axis=0)
    sv = np.linalg.svd(J / np.where(norms > 0, norms, 1.0), compute_uv=False)
    if norms.min() == 0 or sv[-1] / sv[0] < 1e-8:
        return "NOT_IDENTIFIABLE"
    Jn = J / np.exp(x)[None, :]
    cov = np.linalg.inv(Jn.T @ Jn / SIGMA ** 2)
    sd, m = np.sqrt(np.diag(cov)), np.exp(x)
    status = classify(m, cov, m - 1.96 * sd, m + 1.96 * sd, list(_NAMES), **CANONICAL_IDENTIFIABILITY_THRESHOLDS)[0]
    return status.value.replace("PARAMETERS_", "")


def _range(trajs: list[Mapping[str, Any]], var: str, q: float) -> tuple[float, float]:
    if var == "soc":                                  # the true state, never the noisy column
        vals = np.concatenate([_charge(np.asarray(t["columns"]["t_s"]), np.asarray(t["columns"]["current_A"]),
                                       t["initial_state"]["soc"], q) for t in trajs])
    else:
        vals = np.concatenate([np.asarray(t["columns"][var], float) for t in trajs])
    return float(vals.min()), float(vals.max())


def construction_audit(kind: str, protocol: str = "short") -> dict[str, Any]:
    """The noise-free facts behind each TRUTH label of ``kind``, and whether each label follows from them."""
    spec = build(kind, 0, noise=False, protocol=protocol)
    consts = spec["declared_family"]["constants"]
    q = consts["capacity_As"]
    cal = [_bt(t) for t in spec["sets"]["calibration"]]
    p = _oracle_fit(cal, consts)
    facts: dict[str, Any] = {"oracle_params": p, "calibration": _stats(_err(p, cal, consts)),
                             "identifiability_at_truth": _fim_status(cal, consts)}
    app = spec["applicability"]
    dom = {}
    for v in app["variables"]:
        lo, hi = _range(spec["sets"]["calibration"], v, q)
        dom[v] = (lo - app["widen"][v], hi + app["widen"][v])
    checks = {}
    for axis, label in truth(kind, protocol).items():
        if label is None:
            continue
        c = facts["calibration"]
        if axis == "IDENTIFIABILITY":
            ok = facts["identifiability_at_truth"] == ("IDENTIFIABLE" if label == SUP else "NOT_IDENTIFIABLE")
        elif axis == "MODEL_ADEQUACY":
            ok = (c["rmse"] * AUDIT_MARGIN <= BAR["rmse_max"] and c["p95_abs"] * AUDIT_MARGIN <= BAR["p95_abs_max"]
                  if label == SUP else
                  c["rmse"] >= AUDIT_MARGIN * BAR["rmse_max"] or c["p95_abs"] >= AUDIT_MARGIN * BAR["p95_abs_max"])
        elif axis == "MODEL_DISCREPANCY":
            ok = c["rmse"] <= 0.1 * SIGMA if label == SUP else c["rmse"] >= 1.5 * SIGMA
        else:
            set_name = {"WITHIN_CELL_GENERALIZATION": "within_unit_heldout", "CROSS_CELL_TRANSFER": "cross_unit_heldout"}[axis]
            sets = spec["sets"].get(set_name)
            if not sets:
                facts[axis] = {"present": False}
                ok = label == REFUSE
            else:
                out = {}
                for sub, trajs in sorted(sets.items()):
                    inside = all(dom[v][0] - 1e-12 <= _range(trajs, v, q)[0] and _range(trajs, v, q)[1] <= dom[v][1] + 1e-12
                                 for v in app["variables"])
                    out[sub] = {"inside_domain": inside, **_stats(_err(p, [_bt(t) for t in trajs], consts))}
                facts[axis] = out
                if label == REFUSE:
                    ok = not all(o["inside_domain"] for o in out.values())
                elif label == SUP:
                    ok = all(o["inside_domain"] and o["rmse"] * AUDIT_MARGIN <= BAR["rmse_max"]
                             and o["p95_abs"] * AUDIT_MARGIN <= BAR["p95_abs_max"] for o in out.values())
                else:
                    ok = any(o["inside_domain"] and (o["rmse"] >= AUDIT_MARGIN * BAR["rmse_max"]
                                                     or o["p95_abs"] >= AUDIT_MARGIN * BAR["p95_abs_max"])
                             for o in out.values())
        checks[axis] = {"truth": label, "follows_from_construction": bool(ok)}
    return {"fixture": kind, "protocol": protocol, "facts": facts, "checks": checks}


__all__ = ["AUDIT_MARGIN", "BAR", "FAMILIES", "FIXTURES", "NOT", "PROTOCOLS", "REFUSE", "SEEDS", "SUP", "TRUTH", "TRUTH_OVERRIDES", "build",
           "construction_audit", "truth"]
