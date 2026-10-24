"""The declared model families of battery_rediscovery_v2, as ``engcore.mind.repsem`` DeclaredFamily records.

Frozen in PLAN.json before any candidate run.  Every family is the Thevenin first-order equivalent circuit, or its
Rint reduction (R1 = 0) as the declared rival, with one of two open-circuit representations:

* ``*_measured_ocv/1``: the OCV is a measured, fixed table ``constants.ocv_knots`` ([[z, V], ...], linear
  interpolation).  Latent parameters: R0, R1, C1 (Rint: R0).
* ``*_fitted_ocv/1``: the OCV is UNKNOWN and is represented by a fitted piecewise-linear table whose knot positions
  ``constants.ocv_knots_soc`` are declared and whose knot VALUES are latent parameters ``ocv_k0 .. ocv_k{K-1}`` (volts,
  bounded by the declared ``parameter_bounds``).  This is the only fitted-OCV representation the candidate may reason
  about; it is the same function space as the v1 baselines' ``UNKNOWN_FITTED_TABLE`` with the same knots.

Exact piecewise-constant update with the BACKWARD hold (the current reported at sample k flowed over [t_(k-1), t_k]),
for sample k >= 1, on any (non-uniform) sampling:

    z_k  = z_(k-1) - I_k dt_k / Q            (Q in A s, a declared per-trajectory condition)
    a_k  = exp(-dt_k / (R1 C1))
    v1_k = a_k v1_(k-1) + R1 (1 - a_k) I_k
    V_k  = OCV(z_k) - I_k R0 - v1_k

with z_0 = the declared initial state and v1_0 = the declared initial polarization.  Positive current is discharge.
Slots are bound by ROLE (a CONTROLLED_INPUT driver and a STATE_VARIABLE charge state driven by it), never by name.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from engcore.mind.repsem import BoundTrajectory, DeclaredFamily, FamilySlot, VariableRole

OCV_PREFIX = "ocv_k"
EQUATIONS = ("V = OCV(z) - I*R0 - v1;  dv1/dt = I/C1 - v1/(R1*C1);  dz/dt = -I/Q.  Positive I is discharge.  "
             "Rint (R1 = 0) is the declared rival.")


def ocv_parameter_names(n_knots: int) -> tuple[str, ...]:
    return tuple(f"{OCV_PREFIX}{k}" for k in range(n_knots))


def _charge(t: np.ndarray, i: np.ndarray, z0: float, q_As: float) -> np.ndarray:
    return z0 - np.concatenate([[0.0], np.cumsum(i[1:] * np.diff(t))]) / q_As


def _branch(t: np.ndarray, i: np.ndarray, r1: float, c1: float, v0: float) -> np.ndarray:
    a = np.exp(-np.diff(t) / (r1 * c1)).tolist()
    b = (r1 * (1.0 - np.asarray(a)) * i[1:]).tolist()
    out = [float(v0)]
    v = float(v0)
    for ak, bk in zip(a, b):
        v = ak * v + bk
        out.append(v)
    return np.asarray(out)


def _conditions(traj: BoundTrajectory) -> tuple[float, float]:
    pol = traj.conditions["initial_polarization"]
    if not isinstance(pol, (int, float)):
        raise ValueError(f"trajectory {traj.traj_id}: the initial polarization must be a declared number, got {pol!r}")
    return float(pol), float(traj.conditions["capacity_As"])


def _measured_ocv(z: np.ndarray, constants: Mapping[str, Any], params: Mapping[str, float]) -> np.ndarray:
    k = np.asarray(constants["ocv_knots"], float)
    return np.interp(z, k[:, 0], k[:, 1])


def _fitted_ocv(z: np.ndarray, constants: Mapping[str, Any], params: Mapping[str, float]) -> np.ndarray:
    soc = np.asarray(constants["ocv_knots_soc"], float)
    vals = np.array([params[n] for n in ocv_parameter_names(len(soc))], float)
    return np.interp(z, soc, vals)


def _simulator(ocv, rc: bool):
    def simulate(params: Mapping[str, float], traj: BoundTrajectory, constants: Mapping[str, Any]):
        t, i = traj.clock, traj.slots["driver"]
        pol, q = _conditions(traj)
        z = _charge(t, i, traj.initial_state["charge_state"], q)
        v1 = _branch(t, i, params["R1"], params["C1"], pol) if rc else np.zeros_like(i)
        return ocv(z, constants, params) - i * params["R0"] - v1, {"charge_state": z}
    return simulate


_SLOTS = (FamilySlot("driver", (VariableRole.CONTROLLED_INPUT,)),
          FamilySlot("charge_state", (VariableRole.STATE_VARIABLE,), state_of="driver"))
_CONDITIONS = ("initial_polarization", "capacity_As")


def build_families(n_fitted_knots: int) -> dict[str, DeclaredFamily]:
    knots = ocv_parameter_names(n_fitted_knots)
    return {
        "rc1_measured_ocv/1": DeclaredFamily("rc1_measured_ocv/1", "Thevenin 1RC, measured fixed OCV table. " + EQUATIONS,
                                             _SLOTS, ("R0", "R1", "C1"), _simulator(_measured_ocv, True), _CONDITIONS),
        "rint_measured_ocv/1": DeclaredFamily("rint_measured_ocv/1", "Rint (R1 = 0), measured fixed OCV table.",
                                              _SLOTS, ("R0",), _simulator(_measured_ocv, False), _CONDITIONS),
        "rc1_fitted_ocv/1": DeclaredFamily("rc1_fitted_ocv/1", "Thevenin 1RC, OCV a fitted piecewise-linear table on the "
                                           "declared knots. " + EQUATIONS, _SLOTS, ("R0", "R1", "C1", *knots),
                                           _simulator(_fitted_ocv, True), _CONDITIONS),
        "rint_fitted_ocv/1": DeclaredFamily("rint_fitted_ocv/1", "Rint (R1 = 0), OCV a fitted piecewise-linear table on "
                                            "the declared knots.", _SLOTS, ("R0", *knots), _simulator(_fitted_ocv, False),
                                            _CONDITIONS),
    }


__all__ = ["EQUATIONS", "OCV_PREFIX", "build_families", "ocv_parameter_names"]
