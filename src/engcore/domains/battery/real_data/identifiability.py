"""Identifiability gate for ``battery.thevenin_1rc`` on measured discharge/rest data.

The question this module answers is not "what are R0, R1 and C1" but "does
this experiment contain enough independent information to determine them".
Its output is a decision -- CAN_CALIBRATE, or a refusal / review with the
reasons -- never a parameter set. Any parameter value inside the record is
the linearization point of a temporary diagnostic fit and is labelled so.

The model the gate analyses
---------------------------
Inside one analysis window the gate uses the equations of
:mod:`engcore.domains.battery.thevenin`, with the open-circuit voltage held
at one unknown constant per window::

    a_k = exp(-(t_k - t_{k-1}) / (R1 C1))
    v_k = a_k v_{k-1} + (1 - a_k) R1 I_k
    y_k = OCV_w - I_k R0 - v_k

``I_k`` is the canonical (discharge-positive) current recorded at sample k
and held over ``(t_{k-1}, t_k]`` -- the kernel's constant-current interval.
:func:`thevenin_1rc_overpotential` is that recursion; a test holds it equal
to chained :func:`~engcore.domains.battery.thevenin.evaluate_thevenin_step`.

OCV treatment. OCV is not a source channel here and no OCV curve is
identified. Each relaxation window carries its own constant ``OCV_w`` as a
nuisance parameter, estimated jointly and MARGINALIZED out of the R0/R1/C1
information (a Schur complement), so the RC verdict is conditional on OCV
being unknown, not on it being known. Its constancy over the window's loaded
look-back is checked at the check noise scale (the smaller of the declared
noise and the residual RMS).

Structural identifiability, stated once
---------------------------------------
In Laplace form ``Z(s) = R0 + R1 / (1 + s R1 C1)``:

* ``R0 = Z(inf)`` -- fixed by the voltage jump across a current step
  resolved much faster than ``tau``;
* ``R1 = Z(0) - R0`` -- fixed by the relaxation amplitude, PROVIDED the
  polarization reached before the interruption is known (a constant current
  held for many ``tau`` drives it to ``I R1``);
* ``tau = R1 C1`` -- fixed by the relaxation shape; ``C1 = tau / R1``.

The degenerate designs follow directly, and each one is detected:

* no current change -- only ``OCV_w - I (R0 + R1)``: nothing separates;
* steps sampled slower than ``tau`` -- only ``R0 + R1``; ``tau`` invisible;
* a transient observed for much less than ``tau`` -- ``v ~ I t / C1``:
  ``R0`` and ``C1`` seen, ``R1`` and ``tau`` coupled;
* a relaxation whose pre-interruption polarization is unknown -- the
  amplitude becomes a free nuisance and only ``tau = R1 C1`` is seen:
  ``R1`` and ``C1`` are coupled.

The gate checks structure numerically as the generic rank of the EXACT
(analytic) sensitivity matrix of the design -- time grid and measured
current only, no voltage data -- at seeded random points, after projecting
out the nuisance columns. A null direction names the coupled combination.

Practical identifiability, never on one metric
----------------------------------------------
On the calibration data only:

1. a deterministic multi-start diagnostic least-squares fit (never promoted);
2. finite differences at the declared step compared with the analytic
   sensitivity: disagreement, or a perturbation below the output's floating
   point resolution, is NUMERICALLY_UNRESOLVED;
3. excitation relative to the diagnostic ``tau``: rest length, samples
   inside the first ``tau``, step bracket against ``tau``;
4. the normalized (log-parameter, noise-scaled) sensitivity matrix, its
   Fisher information, singular values and conditioning, and the FROZEN
   identifiability rule of :mod:`engcore.hybrid_uq.identifiability`
   applied to the marginal covariance -- the same thresholds every other
   Forge identifiability verdict uses;
5. profile likelihood for each of R0, R1, C1;
6. stability of the estimate across declared nested rest horizons: a
   parameter that moves outside its own local interval when the window is
   shortened is a property of the window, not of the cell.

Two noise scales, chosen by which direction is conservative. Interval
widths and the profile use the LARGER of the declared voltage noise and the
residual RMS, inflated for residual autocorrelation. Checks that must catch a
bad fit or an unstable window -- horizon stability, step consistency, OCV
drift -- use the SMALLER, which neither an inflated declaration nor a worse
fit can enlarge. Neither scale is a measurement uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares

from ....hybrid_uq.identifiability import CANONICAL_IDENTIFIABILITY_THRESHOLDS, classify
from ....inference.calibration import IdentifiabilityStatus
from ....scientific.serialization import schema_string
from ....scientific.units.quantity import Quantity
from .ingest import BatteryDataset, BatteryTimeSeries, Channel, RealDataError, passive_step_test
from .quality import (
    DEFAULT_SEGMENTATION,
    SegmentationPolicy,
    SegmentKind,
    TransitionKind,
    segment_series,
)
from .split import CalibrationHoldoutSplit, calibration_series

GATE_SCHEMA = schema_string("battery_thevenin_1rc_identifiability_gate")
DESIGN_VERSION = "engcore.domains.battery.real_data.thevenin_1rc_identifiability_design/1"
MODEL_ID = "battery.thevenin_1rc"
PARAMETERS = ("R0", "R1", "C1")
PARAMETER_UNITS = {"R0": "ohm", "R1": "ohm", "C1": "farad"}
TAU = "R1*C1"
_GATE_TAG = "engcore.domains.battery.real_data.thevenin_1rc_identifiability_gate/1"

#: chi-square, one degree of freedom, 95 %.
CHI2_95_1DOF = 3.841458820694124
_Z95 = 1.959963984540054

AUTHORITY_NOTE = (
    "Identifiability diagnostic only. This record is not a calibration, not a validation and not evidence of "
    "model adequacy; it grants no ValidationLevel and supports no claim. Parameter values in it are the "
    "linearization point of a temporary diagnostic fit and must not be used as calibrated parameters; "
    "profile intervals are diagnostics of constraint, not parameter uncertainties."
)


class GateDecision(str, Enum):
    CAN_CALIBRATE = "CAN_CALIBRATE"
    WEAKLY_IDENTIFIABLE = "WEAKLY_IDENTIFIABLE"
    NON_IDENTIFIABLE = "NON_IDENTIFIABLE"
    INSUFFICIENT_EXCITATION = "INSUFFICIENT_EXCITATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NUMERICALLY_UNRESOLVED = "NUMERICALLY_UNRESOLVED"

    @property
    def action(self) -> str:
        if self is GateDecision.CAN_CALIBRATE:
            return "CAN_CALIBRATE"
        if self is GateDecision.WEAKLY_IDENTIFIABLE:
            return "REVIEW"
        return "REFUSE"


#: Most restrictive first: combining per-cell results keeps the earliest.
_PRECEDENCE = (
    GateDecision.INSUFFICIENT_DATA,
    GateDecision.INSUFFICIENT_EXCITATION,
    GateDecision.NUMERICALLY_UNRESOLVED,
    GateDecision.NON_IDENTIFIABLE,
    GateDecision.WEAKLY_IDENTIFIABLE,
    GateDecision.CAN_CALIBRATE,
)


def _positive(value: float, label: str) -> float:
    value = float(value)
    if not (math.isfinite(value) and value > 0.0):
        raise RealDataError(f"{label} must be finite and strictly positive")
    return value


@dataclass(frozen=True)
class VoltageNoiseDeclaration:
    """The voltage noise scale the caller declares, and where it comes from.

    There is no default: a missing noise statement is refused, never zero.
    """

    sigma: Quantity
    source: str
    basis: str

    def __post_init__(self) -> None:
        if not isinstance(self.sigma, Quantity):
            raise RealDataError("voltage noise sigma must be a Quantity in a voltage unit")
        if not self.sigma.is_compatible_with(Quantity(1.0, "volt")):
            raise RealDataError(f"voltage noise sigma must be a voltage, got {self.sigma.units!r}")
        _positive(self.sigma.magnitude_in("volt"), "voltage noise sigma")
        for label in ("source", "basis"):
            if not str(getattr(self, label)).strip():
                raise RealDataError(f"voltage noise {label} must be stated")

    @property
    def sigma_v(self) -> float:
        return self.sigma.magnitude_in("volt")

    def to_dict(self) -> dict[str, Any]:
        return {"sigma": self.sigma.to_dict(), "source": self.source, "basis": self.basis}


@dataclass(frozen=True)
class IdentifiabilityDesign:
    """Every threshold the gate uses. Its dictionary is part of the record."""

    segmentation: SegmentationPolicy = DEFAULT_SEGMENTATION
    loaded_lookback_s: float = 10.0
    min_rest_s: float = 60.0
    min_rest_samples: int = 5
    min_residual_dof: int = 5
    horizon_fractions: tuple[float, ...] = (0.25, 0.5)
    history_factor: float = 5.0
    transient_span_factor: float = 3.0
    min_samples_in_first_tau: int = 3
    bracket_to_tau_max: float = 0.1
    fd_relative_step: float = 1.0e-6
    fd_agreement_tolerance: float = 1.0e-4
    structural_points: int = 8
    structural_spread: float = math.log(3.0)
    structural_seed: int = 20261009
    rank_tolerance: float = 1.0e-8
    profile_offsets_sd: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 8.0)
    profile_far_offset: float = math.log(3.0)
    resistance_bounds_ohm: tuple[float, float] = (1.0e-6, 1.0e2)
    capacitance_bounds_f: tuple[float, float] = (1.0e-3, 1.0e8)
    max_rms_to_declared_noise: float = 2.0
    max_residual_lag1_autocorrelation: float = 0.5
    sign_test_current_step_a: float = 0.1
    sign_test_voltage_step_v: float = 1.0e-3
    a1_residual_fraction: float = 0.1
    #: No single cell's OCV and terminal voltage lie more than 5 V apart, so neither can the polarization at
    #: the first recorded sample. A record above 5 V (a series string) raises the bound to its highest
    #: recorded voltage. Gate-owned; a non-default design is capped.
    pre_record_polarization_bound_v: float = 5.0

    def __post_init__(self) -> None:
        if not isinstance(self.segmentation, SegmentationPolicy):
            raise RealDataError("design.segmentation must be a SegmentationPolicy")
        for label in ("loaded_lookback_s", "min_rest_s", "history_factor", "transient_span_factor",
                      "bracket_to_tau_max", "fd_relative_step", "fd_agreement_tolerance", "structural_spread",
                      "rank_tolerance", "profile_far_offset", "max_rms_to_declared_noise",
                      "max_residual_lag1_autocorrelation", "sign_test_current_step_a", "sign_test_voltage_step_v",
                      "a1_residual_fraction", "pre_record_polarization_bound_v"):
            object.__setattr__(self, label, _positive(getattr(self, label), f"design.{label}"))
        for label in ("min_rest_samples", "min_residual_dof", "min_samples_in_first_tau", "structural_points"):
            value = int(getattr(self, label))
            if value < 1:
                raise RealDataError(f"design.{label} must be a positive integer")
            object.__setattr__(self, label, value)
        fractions = tuple(float(f) for f in self.horizon_fractions)
        if any(not (0.0 < f < 1.0) for f in fractions):
            raise RealDataError("horizon fractions must lie strictly between 0 and 1")
        object.__setattr__(self, "horizon_fractions", tuple(sorted(set(fractions))))
        offsets = tuple(sorted({_positive(o, "profile offset") for o in self.profile_offsets_sd}))
        object.__setattr__(self, "profile_offsets_sd", offsets)
        for label in ("resistance_bounds_ohm", "capacitance_bounds_f"):
            low, high = (float(v) for v in getattr(self, label))
            if not (0.0 < low < high and math.isfinite(high)):
                raise RealDataError(f"design.{label} must be 0 < low < high")
            object.__setattr__(self, label, (low, high))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": DESIGN_VERSION,
            "segmentation": self.segmentation.to_dict(),
            "loaded_lookback_s": self.loaded_lookback_s,
            "min_rest_s": self.min_rest_s,
            "min_rest_samples": self.min_rest_samples,
            "min_residual_dof": self.min_residual_dof,
            "horizon_fractions": list(self.horizon_fractions),
            "history_factor": self.history_factor,
            "transient_span_factor": self.transient_span_factor,
            "min_samples_in_first_tau": self.min_samples_in_first_tau,
            "bracket_to_tau_max": self.bracket_to_tau_max,
            "fd_relative_step": self.fd_relative_step,
            "fd_agreement_tolerance": self.fd_agreement_tolerance,
            "structural_points": self.structural_points,
            "structural_spread": self.structural_spread,
            "structural_seed": self.structural_seed,
            "rank_tolerance": self.rank_tolerance,
            "profile_offsets_sd": list(self.profile_offsets_sd),
            "profile_far_offset": self.profile_far_offset,
            "resistance_bounds_ohm": list(self.resistance_bounds_ohm),
            "capacitance_bounds_f": list(self.capacitance_bounds_f),
            "max_rms_to_declared_noise": self.max_rms_to_declared_noise,
            "max_residual_lag1_autocorrelation": self.max_residual_lag1_autocorrelation,
            "sign_test_current_step_a": self.sign_test_current_step_a,
            "sign_test_voltage_step_v": self.sign_test_voltage_step_v,
            "a1_residual_fraction": self.a1_residual_fraction,
            "pre_record_polarization_bound_v": self.pre_record_polarization_bound_v,
            "frozen_identifiability_thresholds": dict(CANONICAL_IDENTIFIABILITY_THRESHOLDS),
            "parameterization": "natural logarithm of R0, R1 and C1; OCV_w (and an unknown initial polarization) as nuisances",
            "perturbation_method": "analytic forward sensitivities; central finite differences as an independent check",
        }


DEFAULT_DESIGN = IdentifiabilityDesign()


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------

def thevenin_1rc_overpotential(
    time_s: Sequence[float],
    current_a: Sequence[float],
    *,
    r0_ohm: float,
    r1_ohm: float,
    c1_farad: float,
    initial_polarization_v: float = 0.0,
) -> np.ndarray:
    """``OCV - V`` at every sample: ``I_k R0 + v_k``, the kernel's exact update."""

    t = np.asarray(time_s, dtype=np.float64)
    i = np.asarray(current_a, dtype=np.float64)
    tau = float(r1_ohm) * float(c1_farad)
    v = float(initial_polarization_v)
    out = np.empty(t.size)
    out[0] = i[0] * r0_ohm + v
    for k in range(1, t.size):
        a = math.exp(-(t[k] - t[k - 1]) / tau)
        v = a * v + (1.0 - a) * r1_ohm * i[k]
        out[k] = i[k] * r0_ohm + v
    return out


@dataclass(frozen=True)
class RelaxationWindow:
    group_id: str
    history_start: int
    onset_observed: bool
    first_observed: int
    interruption: int
    rest_end: int
    rest_duration_s: float
    history_duration_s: float
    bracket_s: float
    loaded_current_a: float
    loaded_samples: int
    group_start: int = 0

    @property
    def observed(self) -> range:
        return range(self.first_observed, self.rest_end + 1)

    def truncated(self, t: np.ndarray, fraction: float) -> "RelaxationWindow":
        limit = t[self.interruption] + fraction * self.rest_duration_s
        end = self.interruption
        while end + 1 <= self.rest_end and t[end + 1] <= limit + 1e-9:
            end += 1
        return RelaxationWindow(
            self.group_id, self.history_start, self.onset_observed, self.first_observed, self.interruption,
            end, float(t[end] - t[self.interruption]), self.history_duration_s, self.bracket_s,
            self.loaded_current_a, self.loaded_samples, self.group_start,
        )

    def rest_samples(self) -> int:
        return self.rest_end - self.interruption + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "history_start_sample": self.history_start,
            "discharge_onset_observed": self.onset_observed,
            "initial_polarization": (
                "zero at the observed discharge onset (assumption A1, checked against the history length)"
                if self.onset_observed else "unknown: a free nuisance parameter"
            ),
            "first_observed_sample": self.first_observed,
            "interruption_sample": self.interruption,
            "rest_end_sample": self.rest_end,
            "loaded_samples_observed": self.loaded_samples,
            "rest_samples_observed": self.rest_samples(),
            "rest_duration_s": self.rest_duration_s,
            "discharge_history_s": self.history_duration_s,
            "interruption_bracket_s": self.bracket_s,
            "loaded_current_a": self.loaded_current_a,
        }


@dataclass
class _Problem:
    t: np.ndarray
    i: np.ndarray
    v: np.ndarray
    windows: tuple[RelaxationWindow, ...]

    @property
    def nuisance_names(self) -> list[str]:
        names = []
        for n, w in enumerate(self.windows):
            names.append(f"OCV_w{n}")
            if not w.onset_observed:
                names.append(f"vp0_w{n}")
        return names

    @property
    def n_params(self) -> int:
        return 3 + len(self.nuisance_names)

    @property
    def n_obs(self) -> int:
        return sum(len(w.observed) for w in self.windows)

    def data(self) -> np.ndarray:
        return np.concatenate([self.v[list(w.observed)] for w in self.windows])

    def evaluate(self, p: np.ndarray, *, jacobian: bool = True) -> tuple[np.ndarray, np.ndarray | None]:
        r0, r1, c1 = (math.exp(x) for x in p[:3])
        tau = r1 * c1
        ys: list[np.ndarray] = []
        js: list[np.ndarray] = []
        col = 3
        n_params = self.n_params
        for w in self.windows:
            ocv_col = col
            col += 1
            vp_col = None
            if not w.onset_observed:
                vp_col = col
                col += 1
            vp = p[vp_col] if vp_col is not None else 0.0
            obs = w.observed
            y = np.empty(len(obs))
            jac = np.zeros((len(obs), n_params)) if jacobian else None
            vk, w1, w2, w3 = vp, 0.0, 0.0, 1.0
            ocv = p[ocv_col]
            for k in range(w.history_start, w.rest_end + 1):
                if k > w.history_start:
                    dt = self.t[k] - self.t[k - 1]
                    a = math.exp(-dt / tau)
                    da = a * dt / tau
                    drive = r1 * self.i[k]
                    w1 = a * w1 + da * (vk - drive) + (1.0 - a) * drive
                    w2 = a * w2 + da * (vk - drive)
                    w3 = a * w3
                    vk = a * vk + (1.0 - a) * drive
                if k >= w.first_observed:
                    row = k - w.first_observed
                    y[row] = ocv - self.i[k] * r0 - vk
                    if jac is not None:
                        jac[row, 0] = -self.i[k] * r0
                        jac[row, 1] = -w1
                        jac[row, 2] = -w2
                        jac[row, ocv_col] = 1.0
                        if vp_col is not None:
                            jac[row, vp_col] = -w3
            ys.append(y)
            if jac is not None:
                js.append(jac)
        return np.concatenate(ys), (np.vstack(js) if jacobian else None)

    def bounds(self, design: IdentifiabilityDesign) -> tuple[np.ndarray, np.ndarray]:
        lr = [math.log(b) for b in design.resistance_bounds_ohm]
        lc = [math.log(b) for b in design.capacitance_bounds_f]
        low = [lr[0], lr[0], lc[0]]
        high = [lr[1], lr[1], lc[1]]
        for name in self.nuisance_names:
            if name.startswith("OCV"):
                low.append(0.0)
                high.append(10.0)
            else:
                low.append(-5.0)
                high.append(5.0)
        return np.asarray(low), np.asarray(high)

    def restricted(self, windows: tuple[RelaxationWindow, ...]) -> "_Problem":
        return _Problem(self.t, self.i, self.v, windows)


# ---------------------------------------------------------------------------
# Excitation features and windows
# ---------------------------------------------------------------------------

def _features(series: BatteryTimeSeries, design: IdentifiabilityDesign) -> dict[str, Any]:
    segments, transitions = segment_series(series, design.segmentation)
    t = series.array(Channel.TIME)
    i = series.array(Channel.CURRENT)
    in_domain = {TransitionKind.ONSET, TransitionKind.INTERRUPTION}
    steps = [tr for tr in transitions if tr.kind in in_domain]
    windows: list[RelaxationWindow] = []
    excluded: list[dict[str, Any]] = []
    for tr in transitions:
        if tr.kind in (TransitionKind.CHARGE_INTERRUPTION, TransitionKind.REVERSAL):
            excluded.append({
                "group_id": series.group_id,
                "transition": tr.to_dict(),
                "reason": "charge current: outside battery.thevenin_1rc's declared discharge/rest domain",
            })
            continue
        if tr.kind is not TransitionKind.INTERRUPTION:
            continue
        dis, rest = segments[tr.before], segments[tr.after]
        if rest.duration_s < design.min_rest_s or rest.samples < design.min_rest_samples:
            excluded.append({
                "group_id": series.group_id,
                "transition": tr.to_dict(),
                "reason": (
                    f"rest after the interruption lasts {rest.duration_s:.6g} s over {rest.samples} samples; "
                    f"the design needs at least {design.min_rest_s:g} s and {design.min_rest_samples} samples"
                ),
            })
            continue
        previous = segments[dis.index - 1] if dis.index > 0 else None
        onset_observed = previous is not None and previous.kind is SegmentKind.REST
        lookback = [k for k in range(dis.first, dis.last + 1) if t[k] >= t[dis.last] - design.loaded_lookback_s]
        windows.append(
            RelaxationWindow(
                group_id=series.group_id,
                history_start=dis.first,
                onset_observed=onset_observed,
                first_observed=lookback[0],
                interruption=rest.first,
                rest_end=rest.last,
                rest_duration_s=float(t[rest.last] - t[rest.first]),
                history_duration_s=float(t[dis.last] - t[dis.first]),
                bracket_s=tr.bracket_s,
                loaded_current_a=float(np.median(i[lookback])),
                loaded_samples=len(lookback),
            )
        )
    levels = sorted({round(abs(seg.current_median_a), 3) for seg in segments if seg.kind is SegmentKind.DISCHARGE})
    return {
        "segments": segments,
        "steps": steps,
        "resolved_steps": [tr for tr in steps if tr.resolved],
        "windows": windows,
        "excluded": excluded,
        "discharge_levels_a": levels,
        "in_domain_samples": int(np.sum(i >= -design.segmentation.rest_band_a)),
    }


# ---------------------------------------------------------------------------
# Numerical building blocks
# ---------------------------------------------------------------------------

def _project_out(columns: np.ndarray, nuisance: np.ndarray) -> np.ndarray:
    if nuisance.shape[1] == 0:
        return columns
    q, _ = np.linalg.qr(nuisance)
    return columns - q @ (q.T @ columns)


def _null_directions(j_theta: np.ndarray, j_nuisance: np.ndarray, tol: float) -> tuple[int, np.ndarray, list[float]]:
    projected = _project_out(j_theta, j_nuisance)
    raw = np.linalg.norm(j_theta, axis=0)
    norms = np.linalg.norm(projected, axis=0)
    scale = max(float(np.max(raw)), 1e-300)
    zero = norms <= tol * scale
    null: list[np.ndarray] = [np.eye(3)[j] for j in np.flatnonzero(zero)]
    live = np.flatnonzero(~zero)
    singular: list[float] = []
    if live.size:
        normalized = projected[:, live] / norms[live]
        _, s, vt = np.linalg.svd(normalized, full_matrices=False)
        singular = [float(x) for x in s]
        for row, value in zip(vt, s):
            if value <= tol * s[0]:
                direction = np.zeros(3)
                direction[live] = row / norms[live]
                null.append(direction / np.linalg.norm(direction))
    rank = 3 - len(null)
    basis = np.linalg.qr(np.array(null).T)[0] if null else np.zeros((3, 0))
    return rank, basis, singular


_COMBINATIONS = {
    "R0": np.array([1.0, 0.0, 0.0]),
    "R1": np.array([0.0, 1.0, 0.0]),
    "C1": np.array([0.0, 0.0, 1.0]),
    TAU: np.array([0.0, 1.0, 1.0]) / math.sqrt(2.0),
}


def _structural(problem: _Problem, reference: np.ndarray, design: IdentifiabilityDesign) -> dict[str, Any]:
    rng = np.random.default_rng(design.structural_seed)
    points = []
    determined: dict[str, list[bool]] = {name: [] for name in _COMBINATIONS}
    last_basis = np.zeros((3, 0))
    for _ in range(design.structural_points):
        p = reference.copy()
        p[:3] = reference[:3] + rng.uniform(-design.structural_spread, design.structural_spread, 3)
        for n, name in enumerate(problem.nuisance_names):
            if name.startswith("vp0"):
                p[3 + n] = float(rng.uniform(0.005, 0.05))
        _, jac = problem.evaluate(p)
        rank, basis, singular = _null_directions(jac[:, :3], jac[:, 3:], design.rank_tolerance)
        last_basis = basis
        for name, vector in _COMBINATIONS.items():
            leak = float(np.linalg.norm(basis.T @ vector)) if basis.shape[1] else 0.0
            determined[name].append(leak <= 1e-6)
        points.append({
            "log_parameters": [float(x) for x in p[:3]],
            "rank": rank,
            "normalized_singular_values": singular,
        })
    ranks = {pt["rank"] for pt in points}
    if ranks == {3}:
        status = IdentifiabilityStatus.IDENTIFIABLE
    elif 3 not in ranks:
        status = IdentifiabilityStatus.NOT_IDENTIFIABLE
    else:
        status = None
    per: dict[str, Any] = {}
    for name, flags in determined.items():
        if all(flags):
            per[name] = IdentifiabilityStatus.IDENTIFIABLE.value
        elif not any(flags):
            per[name] = IdentifiabilityStatus.NOT_IDENTIFIABLE.value
        else:
            per[name] = "NUMERICALLY_UNRESOLVED"
    coupled = None
    if (per["R1"] == per["C1"] == IdentifiabilityStatus.NOT_IDENTIFIABLE.value
            and per[TAU] == IdentifiabilityStatus.IDENTIFIABLE.value):
        coupled = "R1 and C1 are coupled: only tau = R1*C1 is determined by this design"
    null_vectors = [
        {"d_ln_R0": float(col[0]), "d_ln_R1": float(col[1]), "d_ln_C1": float(col[2])}
        for col in last_basis.T
    ]
    return {
        "method": (
            "generic rank of the exact sensitivity matrix of the design (time grid and measured current) at seeded "
            "random log-parameter points around a reference point read from step and relaxation features, "
            "nuisance columns projected out, columns unit-normalized"
        ),
        "rank_tolerance": design.rank_tolerance,
        "points": points,
        "status": None if status is None else status.value,
        "mixed_rank": status is None,
        "per_parameter": per,
        "coupling": coupled,
        "null_directions": null_vectors,
    }


def _fit(problem: _Problem, starts: Sequence[np.ndarray], design: IdentifiabilityDesign,
         fixed: tuple[int, float] | None = None) -> dict[str, Any]:
    data = problem.data()
    low, high = problem.bounds(design)
    free = np.arange(problem.n_params)
    if fixed is not None:
        free = free[free != fixed[0]]

    def full(x: np.ndarray) -> np.ndarray:
        p = np.empty(problem.n_params)
        p[free] = x
        if fixed is not None:
            p[fixed[0]] = fixed[1]
        return p

    def residual(x: np.ndarray) -> np.ndarray:
        return problem.evaluate(full(x), jacobian=False)[0] - data

    def jac(x: np.ndarray) -> np.ndarray:
        return problem.evaluate(full(x))[1][:, free]

    runs = []
    for start in starts:
        x0 = np.clip(np.asarray(start, dtype=float)[free], low[free] + 1e-9, high[free] - 1e-9)
        result = least_squares(residual, x0, jac=jac, bounds=(low[free], high[free]), method="trf",
                               x_scale="jac", xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=4000)
        runs.append(result)
    best = min(runs, key=lambda r: r.cost)
    p = full(best.x)
    at_bound = [PARAMETERS[j] for j in range(3)
                if (fixed is None or fixed[0] != j) and (p[j] - low[j] < 1e-6 or high[j] - p[j] < 1e-6)]
    costs = [float(r.cost) for r in runs]
    spread = [float(np.max(np.abs(r.x[: min(3, len(r.x))] - best.x[: min(3, len(best.x))]))) for r in runs]
    return {
        "p": p,
        "ssr": 2.0 * float(best.cost),
        "converged": bool(best.success and best.status > 0),
        "status": int(best.status),
        "message": str(best.message),
        "at_bound": at_bound,
        "start_costs": costs,
        "start_log_spread": spread,
        "n_obs": int(data.size),
    }


def _fd_check(problem: _Problem, p: np.ndarray, analytic: np.ndarray, design: IdentifiabilityDesign) -> dict[str, Any]:
    h = design.fd_relative_step
    y0 = problem.evaluate(p, jacobian=False)[0]
    resolution = 1.0e4 * np.finfo(float).eps * max(float(np.max(np.abs(y0))), 1e-300)
    errors, below = [], []
    for j in range(problem.n_params):
        step = h if j < 3 else h * max(1.0, abs(float(p[j])))
        up, down = p.copy(), p.copy()
        up[j] += step
        down[j] -= step
        yu = problem.evaluate(up, jacobian=False)[0]
        yd = problem.evaluate(down, jacobian=False)[0]
        change = float(np.max(np.abs(yu - yd)))
        column = analytic[:, j]
        norm = float(np.linalg.norm(column))
        fd = (yu - yd) / (2.0 * step)
        if norm <= 1e-300:
            errors.append(0.0 if change == 0.0 else math.inf)
            continue
        errors.append(float(np.linalg.norm(fd - column) / norm))
        if change < resolution:
            below.append(j)
    names = list(PARAMETERS) + problem.nuisance_names
    worst = max(errors) if errors else 0.0
    ok = worst <= design.fd_agreement_tolerance and not below
    problem_text = None
    if not ok:
        parts = []
        if below:
            parts.append(
                f"the declared step {h:g} moves the output of {[names[j] for j in below]} by less than "
                f"{resolution:.3g} V, the output's floating-point resolution, so the difference is rounding"
            )
        if worst > design.fd_agreement_tolerance:
            parts.append(
                f"finite differences disagree with the analytic sensitivity by {worst:.3g} (tolerance "
                f"{design.fd_agreement_tolerance:g}); the sensitivity is dominated by numerical noise"
            )
        problem_text = "; ".join(parts)
    return {
        "method": "central differences in log-parameter space, compared column-wise with the analytic Jacobian",
        "relative_step": h,
        "output_resolution_v": resolution,
        "max_relative_disagreement": worst,
        "per_column_relative_disagreement": {names[j]: errors[j] for j in range(len(errors))},
        "below_resolution": [names[j] for j in below],
        "agrees": ok,
        "problem": problem_text,
    }


def _local(problem: _Problem, jac: np.ndarray, sigma: float, p: np.ndarray) -> dict[str, Any]:
    s = jac / sigma
    fisher = s.T @ s
    diag = np.sqrt(np.clip(np.diag(fisher), 1e-300, None))
    scaled = fisher / np.outer(diag, diag)
    eig = np.linalg.eigvalsh(scaled)
    singular_fisher = (eig[0] <= 0.0) or (eig[-1] / max(eig[0], 1e-300) > 1e14)
    projected = _project_out(s[:, :3], s[:, 3:])
    sv = np.linalg.svd(projected, compute_uv=False)
    out: dict[str, Any] = {
        "sensitivity_matrix_shape": [int(s.shape[0]), int(s.shape[1])],
        "sensitivity_normalization": (
            "d y_k / d ln(theta_j) divided by the noise scale: dimensionless per unit relative change"
        ),
        "projected_singular_values": [float(x) for x in sv],
        "projected_condition_number": float(sv[0] / sv[-1]) if sv[-1] > 0.0 else math.inf,
        "fisher_scaled_condition_number": float(eig[-1] / eig[0]) if eig[0] > 0.0 else math.inf,
        "singular": bool(singular_fisher),
    }
    if singular_fisher:
        return out
    cov = np.linalg.inv(scaled) / np.outer(diag, diag)
    marginal = cov[:3, :3]
    sd = np.sqrt(np.diag(marginal))
    corr = marginal / np.outer(sd, sd)
    theta = np.exp(p[:3])
    lows = theta * np.exp(-_Z95 * sd)
    highs = theta * np.exp(_Z95 * sd)
    status, condition, max_corr, widths, why = classify(
        theta, marginal, lows, highs, PARAMETERS, **CANONICAL_IDENTIFIABILITY_THRESHOLDS
    )
    tau_sd = math.sqrt(max(marginal[1, 1] + marginal[2, 2] + 2.0 * marginal[1, 2], 0.0))
    collinearity = 1.0 / math.sqrt(max(float(np.linalg.eigvalsh(
        (projected / np.linalg.norm(projected, axis=0)).T @ (projected / np.linalg.norm(projected, axis=0)))[0]), 1e-300))
    out.update({
        "log_sd": {name: float(sd[j]) for j, name in enumerate(PARAMETERS)} | {TAU: tau_sd},
        "relative_width_95": {name: float(widths[j]) for j, name in enumerate(PARAMETERS)}
        | {TAU: float(2.0 * math.sinh(_Z95 * tau_sd))},
        "correlation": [[float(x) for x in row] for row in corr],
        "max_abs_correlation": float(max_corr),
        "correlation_condition_number": float(condition),
        "collinearity_index": float(collinearity),
        "frozen_rule_status": status.value,
        "frozen_rule_why": why,
        "marginal_log_covariance": [[float(x) for x in row] for row in marginal],
    })
    return out


def _profile(problem: _Problem, fit: dict[str, Any], sigma: float, local: dict[str, Any],
             design: IdentifiabilityDesign) -> dict[str, Any]:
    p_hat = fit["p"]
    ssr0 = fit["ssr"]
    low, high = problem.bounds(design)
    results: dict[str, Any] = {}
    lower_found = []
    for j, name in enumerate(PARAMETERS):
        sd = local["log_sd"][name]
        offsets = sorted({k * sd for k in design.profile_offsets_sd} | {design.profile_far_offset})
        offsets = [o for o in offsets if o <= math.log(100.0)]
        rows = []
        bounded = {}
        edge = {}
        for sign, label in ((-1.0, "lower"), (1.0, "upper")):
            previous = (0.0, 0.0)
            warm = p_hat
            inner_p = p_hat
            crossing = None
            hit = False
            for o in offsets:
                value = p_hat[j] + sign * o
                if not (low[j] <= value <= high[j]):
                    hit = True
                    break
                # From the estimate AND the previous profile point: a refit stuck far from its own minimum
                # overstates the rise and narrows the interval.
                fit_j = _fit(problem, [p_hat, warm], design, fixed=(j, value))
                inner_p, warm = warm, fit_j["p"]
                delta = (fit_j["ssr"] - ssr0) / sigma ** 2
                rows.append({"offset_log": sign * o, "delta_chi2": float(delta)})
                if delta < -1e-6 * max(1.0, ssr0 / sigma ** 2):
                    lower_found.append(name)
                if delta > CHI2_95_1DOF and crossing is None:
                    # Bisection, not linear interpolation: a convex profile interpolated linearly crosses the
                    # threshold too early and narrows the interval.
                    inside, outside = previous[0], o
                    last = warm
                    for _ in range(12):
                        middle = 0.5 * (inside + outside)
                        trial = _fit(problem, [p_hat, inner_p, warm, last], design,
                                     fixed=(j, p_hat[j] + sign * middle))
                        last = trial["p"]
                        trial_delta = (trial["ssr"] - ssr0) / sigma ** 2
                        if trial_delta < -1e-6 * max(1.0, ssr0 / sigma ** 2):
                            lower_found.append(name)
                        if trial_delta > CHI2_95_1DOF:
                            outside = middle
                        else:
                            inside = middle
                    crossing = sign * 0.5 * (inside + outside)
                    break
                previous = (o, delta)
            bounded[label] = crossing is not None
            edge[label] = crossing if crossing is not None else (None if not hit else "parameter bound")
        theta = math.exp(p_hat[j])
        if bounded["lower"] and bounded["upper"]:
            lo, hi = theta * math.exp(edge["lower"]), theta * math.exp(edge["upper"])
            width = (hi - lo) / theta
        else:
            lo = hi = None
            width = math.inf
        ok = bounded["lower"] and bounded["upper"] and width <= CANONICAL_IDENTIFIABILITY_THRESHOLDS["width_threshold"]
        results[name] = {
            "points": sorted(rows, key=lambda r: r["offset_log"]),
            "bounded_below": bounded["lower"],
            "bounded_above": bounded["upper"],
            "diagnostic_interval_95_at_noise_scale": None if lo is None else [lo, hi],
            "interval_note": "a diagnostic of how tightly the data constrain the parameter; not a parameter uncertainty",
            "relative_width_95": width,
            "status": (IdentifiabilityStatus.IDENTIFIABLE if ok else IdentifiabilityStatus.NOT_IDENTIFIABLE).value,
        }
    return {
        "method": "profile likelihood: each of ln R0, ln R1, ln C1 fixed in turn, every other parameter re-fitted",
        "threshold_delta_chi2": CHI2_95_1DOF,
        "noise_scale_v": sigma,
        "per_parameter": results,
        "found_lower_minimum": sorted(set(lower_found)),
    }


def _horizons(problem: _Problem, fit: dict[str, Any], local: dict[str, Any], sigma: float,
              design: IdentifiabilityDesign, starts: Sequence[np.ndarray] = ()) -> dict[str, Any]:
    """``local`` and ``sigma`` must be the CHECK scale, which neither the caller nor the misfit can enlarge."""
    rows = []
    for fraction in design.horizon_fractions:
        windows = tuple(w.truncated(problem.t, fraction) for w in problem.windows)
        if any(w.rest_samples() < design.min_rest_samples for w in windows):
            rows.append({"fraction": fraction, "comparable": False,
                         "reason": f"fewer than {design.min_rest_samples} rest samples in the shortened window"})
            continue
        sub = problem.restricted(windows)
        if sub.n_obs < sub.n_params + design.min_residual_dof:
            rows.append({"fraction": fraction, "comparable": False, "reason": "too few observations"})
            continue
        # Every declared start as well as the full-window estimate: one start near the full estimate would
        # settle in its valley and bias the comparison towards "stable".
        sub_fit = _fit(sub, [fit["p"], *starts], design)
        _, jac = sub.evaluate(sub_fit["p"])
        sub_local = _local(sub, jac, sigma, sub_fit["p"])
        if not sub_fit["converged"] or sub_local["singular"] or sub_fit["at_bound"]:
            rows.append({"fraction": fraction, "comparable": False,
                         "reason": "the shortened window does not determine the parameters on its own"})
            continue
        z = {}
        ratio = {}
        for j, name in enumerate(PARAMETERS):
            # The short window is a subset of the full one, so the two estimates are positively
            # correlated: the variance of their difference is close to sd_short^2 - sd_full^2, not the sum.
            short, full = sub_local["log_sd"][name], local["log_sd"][name]
            sd = math.sqrt(max(short ** 2 - full ** 2, (0.1 * short) ** 2))
            z[name] = abs(sub_fit["p"][j] - fit["p"][j]) / sd
            ratio[name] = math.exp(sub_fit["p"][j] - fit["p"][j])
        rows.append({
            "fraction": fraction,
            "comparable": True,
            "rest_duration_s": [w.rest_duration_s for w in windows],
            "estimate_ratio_to_full_window": ratio,
            "z_score": z,
            "stable": all(value <= _Z95 for value in z.values()),
        })
    comparable = [r for r in rows if r["comparable"]]
    if any(not r["stable"] for r in comparable):
        verdict = "UNSTABLE"
    elif not comparable:
        verdict = "UNTESTED"
    elif len(comparable) < len(rows):
        verdict = "PARTIAL"
    else:
        verdict = "STABLE"
    return {
        "method": (
            "the rest of every window shortened to each declared fraction, re-fitted, and each parameter's shift "
            "compared with the 95% half-width of a nested difference (|d ln theta| <= 1.96 sqrt(sd_short^2 - "
            "sd_full^2), floored at 0.1 sd_short), at the check noise scale"
        ),
        "horizons": rows,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IdentifiabilityGateReport:
    decision: GateDecision
    reasons: tuple[str, ...]
    payload: Mapping[str, Any]

    @property
    def action(self) -> str:
        return self.decision.action

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GATE_SCHEMA,
            "model_id": MODEL_ID,
            "decision": self.decision.value,
            "action": self.action,
            "reasons": list(self.reasons),
            "authority": AUTHORITY_NOTE,
            **dict(self.payload),
        }

    @property
    def digest(self) -> str:
        return gate_record_digest(self.to_dict())


def gate_record_digest(record: Mapping[str, Any]) -> str:
    """The digest of a gate record as written (``gate_digest`` itself excluded), for re-checking a stored copy."""
    body = {k: v for k, v in dict(record).items() if k != "gate_digest"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(_GATE_TAG.encode("utf-8") + b"\x00" + payload.encode("utf-8")).hexdigest()


def _clean(value: Any) -> Any:
    """JSON-safe: infinities become the string 'inf', never a bare token."""
    if isinstance(value, float):
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if math.isnan(value):
            return "nan"
        return value
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        return _clean(value.item())
    return value


def _starts(problem: _Problem, features: list[dict[str, Any]]) -> tuple[list[np.ndarray], np.ndarray]:
    t, i, v = problem.t, problem.i, problem.v
    jumps = [abs(tr.step_resistance_ohm) for f in features for tr in f["steps"]
             if tr.kind is TransitionKind.INTERRUPTION and tr.resolved and tr.step_resistance_ohm]
    r0 = float(np.median(jumps)) if jumps else 0.01
    amplitudes = []
    rests = []
    for w in problem.windows:
        current = max(abs(w.loaded_current_a), 1e-6)
        amplitudes.append(max(abs(v[w.rest_end] - v[w.interruption]), 1e-4) / current)
        rests.append(w.rest_duration_s)
    r1 = float(np.median(amplitudes))
    rest = float(np.median(rests))
    r0 = min(max(r0, 1e-5), 10.0)
    r1 = min(max(r1, 1e-5), 10.0)
    nuisance = []
    for w in problem.windows:
        nuisance.append(float(v[w.rest_end]))
        if not w.onset_observed:
            nuisance.append(0.0)
    starts = []
    for fraction in (0.05, 0.2, 0.5):
        tau = fraction * rest
        starts.append(np.array([math.log(r0), math.log(r1), math.log(tau / r1)] + nuisance))
    return starts, starts[1]


def _assess_cell(cell_id: str, series: Sequence[BatteryTimeSeries], noise: VoltageNoiseDeclaration,
                 design: IdentifiabilityDesign,
                 sign_verified: Mapping[str, bool],
                 sign_contradicted: frozenset[str] = frozenset()) -> tuple[GateDecision, list[str], dict[str, Any]]:
    reasons: list[str] = []
    feats = [_features(s, design) for s in series]
    payload: dict[str, Any] = {"cell_id": cell_id, "groups": [s.group_id for s in series]}
    steps = [tr for f in feats for tr in f["steps"]]
    resolved = [tr for f in feats for tr in f["resolved_steps"]]
    windows = [w for f in feats for w in f["windows"]]
    temperature = [s for s in series if s.has(Channel.TEMPERATURE)]
    excitation: dict[str, Any] = {
        "current_transitions_in_domain": len(steps),
        "resolved_steps": [
            {"group_id": series[n].group_id, **tr.to_dict()}
            for n, f in enumerate(feats) for tr in f["resolved_steps"]
        ],
        "discharge_current_levels_a": sorted({lvl for f in feats for lvl in f["discharge_levels_a"]}),
        "relaxation_windows": [w.to_dict() for w in windows],
        "excluded_windows": [x for f in feats for x in f["excluded"]],
        "temperature": (
            "no temperature channel in the calibration data: temperature variation is not observable, and any "
            "identified parameters hold only at the source's stated, unmeasured, test temperature"
            if not temperature else {
                "min_k": min(float(np.min(s.array(Channel.TEMPERATURE))) for s in temperature),
                "max_k": max(float(np.max(s.array(Channel.TEMPERATURE))) for s in temperature),
            }
        ),
    }
    payload["excitation"] = excitation
    payload["ocv_treatment"] = (
        "OCV is not measured during the windows and no OCV curve is identified. Each relaxation window carries "
        "one unknown constant OCV_w, estimated jointly and marginalized out of the R0/R1/C1 information. OCV "
        "hysteresis is not modelled: OCV_w is the relaxed voltage the window's own rest approaches."
    )
    payload["model_conventions"] = {
        "current_hold": (
            "the current recorded at sample k is held over (t_{k-1}, t_k]: the kernel's constant-current interval"
        ),
        "initial_polarization": (
            "zero at an observed discharge onset (A1), accepted only when the discharge lasts history_factor times "
            "the upper 95% tau; otherwise a free nuisance parameter"
        ),
    }

    contradicted = [g for g in payload["groups"] if g in sign_contradicted]
    if contradicted:
        return (GateDecision.INSUFFICIENT_DATA,
                [f"the declared current sign of {contradicted} is contradicted by the record's passive step "
                 "response: the voltage moves WITH the discharge current at a clear step, so the record cannot be "
                 "read in the model's convention"], payload)
    if sum(f["in_domain_samples"] for f in feats) == 0:
        return GateDecision.INSUFFICIENT_DATA, ["no calibration sample lies in the discharge/rest domain"], payload
    if not steps:
        return (GateDecision.INSUFFICIENT_EXCITATION,
                ["no discharge onset or interruption in the calibration data: steady or zero current cannot "
                 "separate R0 from R1 or determine C1"], payload)
    if not windows:
        return (GateDecision.INSUFFICIENT_EXCITATION,
                [f"no discharge interruption is followed by a rest of at least {design.min_rest_s:g} s: without a "
                 "relaxation R1 and C1 cannot be separated"], payload)
    if not resolved:
        return (GateDecision.INSUFFICIENT_EXCITATION,
                [f"no current step is resolved within {design.segmentation.step_bracket_max_s:g} s: R0 cannot be "
                 "separated from the polarization branch"], payload)

    # One problem over every window of this cell; the time series are concatenated per group.
    if len(series) > 1:
        offsets = []
        t_all, i_all, v_all = [], [], []
        base = 0
        shifted = []
        for s, f in zip(series, feats):
            offsets.append(base)
            t_all.append(s.array(Channel.TIME))
            i_all.append(s.array(Channel.CURRENT))
            v_all.append(s.array(Channel.VOLTAGE))
            for w in f["windows"]:
                shifted.append(RelaxationWindow(
                    w.group_id, w.history_start + base, w.onset_observed, w.first_observed + base,
                    w.interruption + base, w.rest_end + base, w.rest_duration_s, w.history_duration_s,
                    w.bracket_s, w.loaded_current_a, w.loaded_samples, base))
            base += len(s)
        problem = _Problem(np.concatenate(t_all), np.concatenate(i_all), np.concatenate(v_all), tuple(shifted))
    else:
        s = series[0]
        problem = _Problem(s.array(Channel.TIME), s.array(Channel.CURRENT), s.array(Channel.VOLTAGE), tuple(windows))

    payload["parameters_estimated"] = list(PARAMETERS)
    payload["nuisance_parameters"] = problem.nuisance_names
    if problem.n_obs < problem.n_params + design.min_residual_dof:
        return (GateDecision.INSUFFICIENT_DATA,
                [f"{problem.n_obs} observations for {problem.n_params} parameters leave fewer than "
                 f"{design.min_residual_dof} residual degrees of freedom"], payload)

    starts, reference = _starts(problem, feats)
    structural = _structural(problem, reference, design)
    payload["structural"] = structural
    if structural["mixed_rank"]:
        return (GateDecision.NUMERICALLY_UNRESOLVED,
                ["the design's sensitivity rank differs between generic points at the declared tolerance; "
                 "structural identifiability is not resolved"], payload)
    if structural["status"] == IdentifiabilityStatus.NOT_IDENTIFIABLE.value:
        why = structural["coupling"] or (
            "the design's sensitivity matrix is rank deficient at every generic point; null directions "
            f"{structural['null_directions']}"
        )
        return GateDecision.NON_IDENTIFIABLE, [f"structurally non-identifiable: {why}"], payload

    fit = _fit(problem, starts, design)
    payload["diagnostic_fit"] = {
        "use": "DIAGNOSTIC_ONLY_NOT_CALIBRATED",
        "converged": fit["converged"],
        "optimizer_status": fit["status"],
        "optimizer_message": fit["message"],
        "start_costs": fit["start_costs"],
        "start_log_spread": fit["start_log_spread"],
        "at_parameter_bound": fit["at_bound"],
        "observations": fit["n_obs"],
        "linearization_point": {
            name: {"value": math.exp(fit["p"][j]), "unit": PARAMETER_UNITS[name]}
            for j, name in enumerate(PARAMETERS)
        } | {TAU: {"value": math.exp(fit["p"][1] + fit["p"][2]), "unit": "second"}},
    }
    if not fit["converged"]:
        return (GateDecision.NUMERICALLY_UNRESOLVED,
                [f"the diagnostic fit did not converge ({fit['message']})"], payload)

    _, jac = problem.evaluate(fit["p"])
    fd = _fd_check(problem, fit["p"], jac, design)
    payload["finite_difference_check"] = fd
    if not fd["agrees"]:
        return GateDecision.NUMERICALLY_UNRESOLVED, [fd["problem"]], payload

    tau_hat = math.exp(fit["p"][1] + fit["p"][2])
    dof = max(fit["n_obs"] - problem.n_params, 1)
    rms = math.sqrt(fit["ssr"] / dof)
    sigma = max(noise.sigma_v, rms)
    # Interval widths are conservative at the LARGER scale; checks that must catch a bad fit or an unstable
    # window are lenient at a larger scale, so they use the SMALLER one, which neither an inflated declaration
    # nor a worse fit can enlarge.
    sigma_check = min(noise.sigma_v, rms)
    residual = problem.evaluate(fit["p"], jacobian=False)[0] - problem.data()
    lag1 = []
    start = 0
    for w in problem.windows:
        block = residual[start:start + len(w.observed)]
        start += len(w.observed)
        centred = block - block.mean()
        denominator = float(np.sum(centred ** 2))
        if block.size > 2 and denominator > 0.0:
            lag1.append(float(np.sum(centred[1:] * centred[:-1]) / denominator))
    # Autocorrelated residuals carry fewer independent samples than they number: for an AR(1) residual the
    # effective count is about n (1 - r) / (1 + r), so the width scale is inflated by sqrt((1 + r) / (1 - r)).
    worst_lag1 = min(max([0.0] + lag1), 0.99)
    inflation = math.sqrt((1.0 + worst_lag1) / (1.0 - worst_lag1))
    sigma = sigma * inflation
    payload["noise"] = {
        "declared": noise.to_dict(),
        "autocorrelation_width_inflation": inflation,
        "declared_noise_channel": (
            "the declared figure is used as a per-sample random scale; an instrument accuracy figure is partly "
            "systematic, and a constant offset is absorbed by OCV_w"
        ),
        "diagnostic_residual_rms_v": rms,
        "residual_rms_degrees_of_freedom": dof,
        "residual_lag1_autocorrelation": lag1,
        "width_scale_v": sigma,
        "check_scale_v": sigma_check,
        "rule": (
            "interval widths use the larger of the declared noise and the residual RMS, inflated by "
            "sqrt((1 + r1) / (1 - r1)) for the largest positive lag-1 residual autocorrelation (conservative); "
            "stability, step-consistency and drift checks use the smaller (not enlargeable by the caller or by "
            "misfit). Neither is a measurement uncertainty"
        ),
    }

    relative = []
    excitation_problems = []
    for n, w in enumerate(problem.windows):
        rest_t = problem.t[w.interruption: w.rest_end + 1] - problem.t[w.interruption]
        in_first_tau = int(np.sum((rest_t > 0.0) & (rest_t <= tau_hat)))
        row = {
            "window": n,
            "rest_over_tau": w.rest_duration_s / tau_hat,
            "history_over_tau": w.history_duration_s / tau_hat if w.onset_observed else None,
            "bracket_over_tau": w.bracket_s / tau_hat,
            "rest_samples_within_first_tau": in_first_tau,
        }
        relative.append(row)
        if w.rest_duration_s < design.transient_span_factor * tau_hat:
            excitation_problems.append(
                f"window {n}: the rest lasts {row['rest_over_tau']:.3g} tau; at least "
                f"{design.transient_span_factor:g} tau is needed to see the relaxation's shape -- the transient "
                "window is too short for R1 and C1 to be separated"
            )
        if in_first_tau < design.min_samples_in_first_tau:
            excitation_problems.append(
                f"window {n}: {in_first_tau} rest sample(s) within the first tau; at least "
                f"{design.min_samples_in_first_tau} are needed -- the transient is undersampled"
            )
        if w.bracket_s > design.bracket_to_tau_max * tau_hat:
            excitation_problems.append(
                f"window {n}: the interruption is located only to {row['bracket_over_tau']:.3g} tau; R0 cannot be "
                "separated from the polarization branch"
            )
    if fit["at_bound"]:
        excitation_problems.append(
            f"the diagnostic fit runs to the declared bound of {fit['at_bound']}: the data do not limit them"
        )
    excitation["relative_to_diagnostic_tau"] = relative
    if excitation_problems:
        return GateDecision.INSUFFICIENT_EXCITATION, excitation_problems, payload

    local = _local(problem, jac, sigma, fit["p"])
    payload["practical_local"] = local
    if local["singular"]:
        return (GateDecision.NON_IDENTIFIABLE,
                ["the Fisher information of the calibration data is singular at the width noise scale"], payload)

    profile = _profile(problem, fit, sigma, local, design)
    payload["profile_likelihood"] = profile
    if profile["found_lower_minimum"]:
        return (GateDecision.NUMERICALLY_UNRESOLVED,
                [f"the profile of {profile['found_lower_minimum']} found a lower minimum than the diagnostic fit"],
                payload)

    local_check = _local(problem, jac, sigma_check, fit["p"])
    horizons = _horizons(problem, fit, local_check, sigma_check, design, starts)
    payload["horizon_stability"] = horizons

    caps: list[str] = []
    if rms > design.max_rms_to_declared_noise * noise.sigma_v:
        caps.append(
            f"misfit: the residual RMS {rms * 1e3:.3g} mV exceeds {design.max_rms_to_declared_noise:g} x the declared "
            f"noise ({noise.sigma_v * 1e3:.3g} mV); the model does not describe the data at the declared noise"
        )
    if len(lag1) < len(problem.windows):
        caps.append("residual whiteness is untested for at least one window (too few samples or a zero residual)")
    if any(abs(r) > design.max_residual_lag1_autocorrelation for r in lag1):
        caps.append(
            f"structured residuals: lag-1 autocorrelation {[round(r, 3) for r in lag1]} exceeds "
            f"{design.max_residual_lag1_autocorrelation:g}; the residuals are not white, so the Fisher information "
            "overstates what the data determine"
        )
    tau_upper = tau_hat * math.exp(_Z95 * local["log_sd"][TAU])
    # The limit is a check, so it uses the CHECK scale: declaring more noise must not loosen it.
    r1_half_width = 0.5 * local_check["relative_width_95"]["R1"]
    limit = design.a1_residual_fraction * r1_half_width
    a1_rows = []
    for n, w in enumerate(problem.windows):
        if not w.onset_observed:
            continue
        drive = max(abs(w.loaded_current_a), 1e-12) * math.exp(fit["p"][1])
        start = problem.t[w.first_observed]
        # (a) Polarization left by EARLIER RECORDED current, decayed from the last active sample to the window.
        #     It enters the relaxation amplitude exactly as R1 does, so no residual test can see it.
        earlier = problem.i[w.group_start:w.history_start]
        active = np.flatnonzero(np.abs(earlier) > design.segmentation.rest_band_a)
        prior = float(np.max(np.abs(earlier))) if earlier.size else 0.0
        if active.size:
            since = start - problem.t[w.group_start + int(active[-1])]
            recorded = (prior / max(abs(w.loaded_current_a), 1e-12)) * math.exp(-since / tau_upper)
        else:
            recorded = 0.0
        # (b) Polarization from BEFORE the recording, never zero by assumption: bounded by the gate-owned
        #     single-cell bound and decayed over everything the record shows before the window.
        elapsed = start - problem.t[w.group_start]
        # The group runs to the next group's first sample (or the end). A group with no window of its own is
        # read into the one before it, which can only raise the bound.
        later_starts = [x.group_start for x in problem.windows if x.group_start > w.group_start]
        group_end = min(later_starts) if later_starts else problem.t.size
        bound = max(design.pre_record_polarization_bound_v,
                    float(np.max(np.abs(problem.v[w.group_start:group_end]))))
        unrecorded = bound * math.exp(-elapsed / tau_upper) / drive
        # I-a: both parts of the ignored polarization bias the same amplitude and can share a sign, so the
        # cap is on their SUM, not on each alone.
        combined = recorded + unrecorded
        a1_rows.append({
            "window": n,
            "max_prior_recorded_current_a": prior,
            "recorded_history_factor": recorded,
            "pre_record_bound_v": bound,
            "pre_record_factor": unrecorded,
            "combined_factor": combined,
            "limit": limit,
        })
        if recorded > limit:
            caps.append(
                f"window {n}: polarization left by earlier recorded current (up to {prior:.3g} A) may still bias "
                f"R1 by {recorded:.3g} relative, more than {design.a1_residual_fraction:g} of R1's 95% half-width"
            )
        if recorded <= limit and unrecorded <= limit and combined > limit:
            caps.append(
                f"window {n}: earlier recorded current and polarization from before the record together may "
                f"bias R1 by {combined:.3g} relative, more than {design.a1_residual_fraction:g} of R1's 95% "
                "half-width, though neither does alone"
            )
        if unrecorded > limit:
            caps.append(
                f"window {n}: polarization at the record's start is unknown; bounded by "
                f"{bound:g} V it may still bias R1 by {unrecorded:.3g} relative, "
                f"because the record shows only {elapsed / tau_upper:.3g} upper-95% tau before the window"
            )
    payload["initial_polarization_check"] = a1_rows
    for n, w in enumerate(problem.windows):
        if w.onset_observed and w.history_duration_s < design.history_factor * tau_upper:
            caps.append(
                f"window {n}: the discharge before the interruption lasts {w.history_duration_s / tau_upper:.3g} "
                f"times the upper 95% tau; the zero-initial-polarization assumption needs {design.history_factor:g}"
            )
        if w.loaded_samples < 2:
            caps.append(
                f"window {n}: only {w.loaded_samples} loaded sample in the look-back, so OCV constancy over the "
                "window is untested"
            )
        if w.loaded_samples >= 2:
            # Under a polarization already at steady state, the loaded voltage moves only with OCV. Two noisy
            # samples differ by sqrt(2) sigma at one standard deviation, so the limit is two of those.
            drift = abs(problem.v[w.interruption - 1] - problem.v[w.first_observed])
            drift_limit = 2.0 * math.sqrt(2.0) * sigma_check
            if drift > drift_limit:
                caps.append(
                    f"window {n}: the loaded voltage changes {drift * 1e3:.3g} mV over the look-back, more than "
                    f"{drift_limit * 1e3:.3g} mV of noise allows; OCV may not be constant over the window"
                )
    # R0 against the record's own resolved steps. A step read across a bracket far shorter than tau is the
    # instantaneous resistance at that bracket; a 1RC R0 that sits outside it lumps faster dynamics into R0.
    r0_hat = math.exp(fit["p"][0])
    r1_hat = math.exp(fit["p"][1])
    r0_sd = r0_hat * local_check["log_sd"]["R0"]
    step_rows = []
    for n, f in enumerate(feats):
        for tr in f["resolved_steps"]:
            resistance = tr.step_resistance_ohm
            if resistance is None or tr.bracket_s > design.bracket_to_tau_max * tau_hat:
                continue
            feature_sd = sigma_check * math.sqrt(2.0) / abs(tr.delta_current_a)
            # The 1RC model's own -dV/dI across a bracket b: R0 + R1 (1 - exp(-b / tau)).
            predicted = r0_hat + r1_hat * (1.0 - math.exp(-tr.bracket_s / tau_hat))
            z = abs(resistance - predicted) / math.hypot(r0_sd, feature_sd)
            step_rows.append({
                "group_id": series[n].group_id,
                "kind": tr.kind.value,
                "bracket_s": tr.bracket_s,
                "delta_current_a": tr.delta_current_a,
                "step_resistance_feature_ohm": resistance,
                "model_predicted_step_resistance_ohm": predicted,
                "ratio_to_model_prediction": resistance / predicted,
                "z_score": z,
                "consistent": z <= _Z95,
            })
    payload["step_resistance_consistency"] = {
        "method": (
            "every resolved in-domain step with a bracket b under bracket_to_tau_max * tau: |R_step - (R0 + R1 "
            "(1 - exp(-b / tau)))| against "
            "1.96 sqrt(sd_R0^2 + (sqrt(2) sigma / |dI|)^2), at the check noise scale"
        ),
        "steps": step_rows,
    }
    inconsistent = [r for r in step_rows if not r["consistent"]]
    if inconsistent:
        brackets = sorted({round(r["bracket_s"], 4) for r in inconsistent})
        caps.append(
            f"R0 is resolution-dependent: {len(inconsistent)} resolved step(s) read across brackets {brackets} s "
            "fall outside the 1RC model's own prediction at that bracket. Possible causes, none established here: dynamics faster than the "
            "interruption bracket lumped into R0, current-level nonlinearity, or onset/interruption asymmetry"
        )
    payload["assumption_checks"] = caps

    per: dict[str, Any] = {}
    for name in PARAMETERS + (TAU,):
        entry: dict[str, Any] = {
            "structural": structural["per_parameter"][name],
            "practical_local_relative_width_95": local["relative_width_95"][name],
        }
        if name in PARAMETERS:
            entry["practical_profile"] = profile["per_parameter"][name]["status"]
            entry["profile_relative_width_95"] = profile["per_parameter"][name]["relative_width_95"]
            j = PARAMETERS.index(name)
            entry["max_abs_correlation_with_others"] = max(
                abs(local["correlation"][j][m]) for m in range(3) if m != j)
        per[name] = entry
    windows_text = ", ".join(f"{w.rest_duration_s:.4g} s rest after {w.loaded_current_a:.4g} A" for w in problem.windows)
    per["R0"]["basis"] = (
        f"the voltage jump across the interruption, located to {min(w.bracket_s for w in problem.windows):.4g} s, "
        f"against tau of {tau_hat:.4g} s"
    )
    per["R1"]["basis"] = (
        "the relaxation amplitude, given the polarization reached during the preceding constant discharge "
        f"({windows_text})"
    )
    per["C1"]["basis"] = "C1 = tau / R1, determined once the relaxation shape (tau) and amplitude (R1) are"
    per[TAU]["basis"] = "the shape of the relaxation"
    payload["parameters"] = per

    status = local["frozen_rule_status"]
    profile_bad = [n for n in PARAMETERS if profile["per_parameter"][n]["status"] != IdentifiabilityStatus.IDENTIFIABLE.value]
    if status == IdentifiabilityStatus.NOT_IDENTIFIABLE.value:
        return GateDecision.NON_IDENTIFIABLE, [local["frozen_rule_why"]], payload
    if profile_bad:
        return (GateDecision.NON_IDENTIFIABLE,
                [f"the profile likelihood of {profile_bad} is not bounded inside a 95% interval narrower than "
                 "the parameter"], payload)
    if status == IdentifiabilityStatus.WEAKLY_IDENTIFIABLE.value:
        reasons.append(local["frozen_rule_why"])
    if horizons["verdict"] == "UNSTABLE":
        moved = sorted({name for r in horizons["horizons"] if r["comparable"] and not r["stable"]
                        for name, z in r["z_score"].items() if z > _Z95})
        reasons.append(
            f"window-unstable: shortening the rest moves {moved} outside their own 95% intervals, so the 1RC "
            "parameters fitted here depend on the analysis window. Possible causes, none established here: more "
            "than one relaxation time constant, or OCV relaxation/hysteresis during the rest"
        )
    elif horizons["verdict"] in ("UNTESTED", "PARTIAL"):
        reasons.append(
            f"horizon stability {horizons['verdict']}: not every declared shortened window could be compared, so "
            "robustness to the analysis window is not established"
        )
    reasons.extend(caps)
    unverified = [g for g in payload["groups"] if not sign_verified.get(g, False)]
    if unverified:
        reasons.append(
            f"the current sign of {unverified} is declared but cannot be tested from the record: no clear current "
            "step"
        )
    if design.to_dict() != DEFAULT_DESIGN.to_dict():
        reasons.append(
            "the gate ran under a non-default design; CAN_CALIBRATE is issued only under DEFAULT_DESIGN, so a "
            "loosened threshold cannot buy it"
        )
    if reasons:
        return GateDecision.WEAKLY_IDENTIFIABLE, reasons, payload
    return (GateDecision.CAN_CALIBRATE,
            ["R0, R1 and C1 are structurally identifiable, pass the frozen identifiability rule and the profile "
             "likelihood at the conservative noise scale, and are stable across the declared analysis windows"],
            payload)


def assess_thevenin_1rc_identifiability(
    dataset: BatteryDataset,
    split: CalibrationHoldoutSplit,
    noise: VoltageNoiseDeclaration,
    design: IdentifiabilityDesign = DEFAULT_DESIGN,
) -> IdentifiabilityGateReport:
    """Run the gate on the CALIBRATION groups of ``split`` only."""

    if not isinstance(noise, VoltageNoiseDeclaration):
        raise RealDataError("the gate needs a declared VoltageNoiseDeclaration; missing noise is never zero")
    if not isinstance(design, IdentifiabilityDesign):
        raise RealDataError("design must be an IdentifiabilityDesign")
    series = calibration_series(dataset, split)
    # The sign is re-tested here from the calibration series themselves, never read from a receipt's text:
    # a receipt is a plain record a caller can assemble.
    sign_tests = {}
    for item in series:
        clear, against = passive_step_test(
            item.array(Channel.CURRENT), item.array(Channel.VOLTAGE),
            current_step_a=design.sign_test_current_step_a, voltage_step_v=design.sign_test_voltage_step_v,
        )
        sign_tests[item.group_id] = {"clear_steps": clear, "voltage_against_current": against}
    sign_verified = {g: r["clear_steps"] > 0 and r["clear_steps"] == r["voltage_against_current"]
                     for g, r in sign_tests.items()}
    sign_contradicted = frozenset(g for g, r in sign_tests.items() if r["voltage_against_current"] < r["clear_steps"])
    by_cell: dict[str, list[BatteryTimeSeries]] = {}
    for item in series:
        by_cell.setdefault(item.cell_id, []).append(item)
    cells = {}
    decisions = []
    reasons: list[str] = []
    for cell_id in sorted(by_cell):
        decision, why, payload = _assess_cell(cell_id, by_cell[cell_id], noise, design, sign_verified,
                                              sign_contradicted)
        payload["decision"] = decision.value
        payload["reasons"] = why
        cells[cell_id] = payload
        decisions.append(decision)
        reasons.extend(f"{cell_id}: {w}" for w in why)
    overall = min(decisions, key=_PRECEDENCE.index)
    payload = {
        "receipt_digest": dataset.receipt.digest,
        "split_digest": split.digest,
        "calibration_groups": list(split.calibration_groups),
        "holdout_groups_not_read": list(split.holdout_groups),
        "design": design.to_dict(),
        "current_sign_retest": sign_tests,
        "cells": cells,
    }
    return IdentifiabilityGateReport(decision=overall, reasons=tuple(reasons), payload=_clean(payload))


__all__ = [
    "AUTHORITY_NOTE",
    "CHI2_95_1DOF",
    "DEFAULT_DESIGN",
    "GATE_SCHEMA",
    "GateDecision",
    "IdentifiabilityDesign",
    "IdentifiabilityGateReport",
    "MODEL_ID",
    "PARAMETERS",
    "RelaxationWindow",
    "VoltageNoiseDeclaration",
    "assess_thevenin_1rc_identifiability",
    "gate_record_digest",
    "thevenin_1rc_overpotential",
]
