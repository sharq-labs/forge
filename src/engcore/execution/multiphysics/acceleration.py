"""Interface quasi-Newton acceleration of the joint coupling fixed point (Phase 3 BR14).

One reusable accelerator for the two IQN kinds the runtime admits (Jacobi
only, see ``CouplingPlan``):

IQN-ILS (Degroote et al. 2009; ERT V1 BR2/BR16, unchanged arithmetic)
    ``x_{k+1} = H(x_k) + W c``, ``c = argmin || D (V c + r_k) ||`` over the
    secant pairs of THIS window; first iteration: constant relaxation.

IQN-IMVJ (Bogaers et al. 2014; Lindner, Mehl, Uekermann 2017)
    The same secant pairs update the inverse-Jacobian approximation carried
    from the previous ACCEPTED window,
    ``J_k = J_prev + (W - J_prev V) (D V)^+ D``, and the step is
    ``x_{k+1} = H(x_k) - J_k r_k``.  With ``J_prev = 0`` this is IQN-ILS
    exactly; with no secant pair yet (first iteration of a window) the step
    is ``H(x_0) - J_prev r_0``.  ``J_k V = W`` holds for the kept columns.

``V`` and ``W`` hold differences of residuals ``r_i = H(x_i) - x_i`` and of
images ``H(x_i)``; ``D`` scales each edge by the RMS of its first non-zero
residual in the window (unit independence); near-dependent columns are dropped
by the newest-first QR filter.  Nothing here measures convergence: the runtime
judges every iterate on the UNRELAXED transfer of every required edge, so an
accelerated step can never be labelled converged on its own.

History validity (when a carried approximation is discarded, and why, is
recorded -- never silent):

* every window starts with an empty secant history;
* IMVJ carries ``J`` only from a window that was ACCEPTED and CONVERGED, into
  a window of the SAME exact duration, interface layout and supports (mesh
  fingerprint, location, components per edge); a rejected attempt, a rollback,
  an event-aligned re-run (duration unknown), an iteration-limit acceptance, a
  layout or support change, or ``imvj_reuse_windows`` consecutive reuses
  discard it;
* a non-finite candidate falls back to constant relaxation for that step and
  discards the carried approximation (it is no longer admissible);
* a joint interface larger than ``imvj_max_dimension`` is refused.

What acceleration does NOT do: it guarantees no convergence, no convergence
rate and no error bound; the propagated uncertainty of an accelerated iterate
is UNKNOWN (no propagation rule is declared for a least-squares combination).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import numpy as np

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import RelaxationKind, RelaxationPolicy


def qr_filter(scaled: np.ndarray, threshold: float, *, relative_to_largest: bool = False) -> list[int]:
    """Columns to keep, newest first: drop one whose new direction is negligible (ERT V1 BR16).

    Modified Gram-Schmidt over the columns from newest to oldest; a column is
    kept only when its component orthogonal to the kept ones exceeds
    ``threshold`` times its own norm.  With ``relative_to_largest`` (IQN-IMVJ
    only) it must also exceed ``threshold`` times the LARGEST column norm: a
    round-off-level secant pair near convergence is orthogonal "noise" that the
    own-norm test keeps, and an approximation carried into later windows must
    not absorb it (a QR1-type filter; Haelterman et al. 2016).
    """
    basis: list[np.ndarray] = []
    keep: list[int] = []
    largest = float(np.max(np.linalg.norm(scaled, axis=0))) if relative_to_largest and scaled.size else 0.0
    for index in range(scaled.shape[1] - 1, -1, -1):
        column = scaled[:, index].astype(float).copy()
        norm = float(np.linalg.norm(column))
        if norm <= np.finfo(np.float64).tiny:
            continue
        for q in basis:
            column -= float(q @ column) * q
        remainder = float(np.linalg.norm(column))
        if remainder > threshold * norm and remainder > 0.0 and remainder > threshold * largest:
            basis.append(column / remainder)
            keep.append(index)
    return sorted(keep)


class InterfaceQuasiNewton:
    """The joint-vector IQN accelerator (ILS or IMVJ) and its history-validity rules (module docstring)."""

    def __init__(self, policy: RelaxationPolicy) -> None:
        if policy.kind not in (RelaxationKind.IQN_ILS, RelaxationKind.IQN_IMVJ):
            raise InvalidScientificProblem("InterfaceQuasiNewton implements IQN-ILS and IQN-IMVJ only")
        self.policy = policy
        self.events: list[dict[str, Any]] = []
        #: events that are not routine (IMVJ always records; ILS records only fallbacks)
        self.non_routine = False
        self._window_index: int | None = None
        self._duration: Fraction | None = None
        self._residuals: list[np.ndarray] = []
        self._images: list[np.ndarray] = []
        self._layout: tuple[tuple[str, int], ...] = ()
        self._supports: tuple[Any, ...] = ()
        self._scales: dict[str, float] = {}
        # IMVJ state
        self._carried: np.ndarray | None = None
        self._carried_key: tuple[Any, ...] | None = None
        #: how many windows have started from the carried approximation since it was last built afresh
        self._reuses = 0
        self._used_carry = False
        self._staged: np.ndarray | None = None
        self._checked_carry = False

    @property
    def imvj(self) -> bool:
        return self.policy.kind is RelaxationKind.IQN_IMVJ

    def _log(self, action: str, reason: str, *, routine: bool = False) -> None:
        if not routine:
            self.non_routine = True
        self.events.append({"window_index": self._window_index, "action": action, "reason": reason})

    def _discard(self, reason: str) -> None:
        if self._carried is not None:
            self._log("imvj_discarded", reason)
        self._carried = None
        self._carried_key = None
        self._reuses = 0

    # ---- window lifecycle --------------------------------------------------------------------

    def begin_window(self, window_index: int | None, duration: Fraction | None) -> None:
        """A new attempt over one window: the secant history starts empty."""
        self._window_index = window_index
        self._duration = duration
        self._residuals.clear()
        self._images.clear()
        self._layout = ()
        self._supports = ()
        self._scales.clear()
        self._staged = None
        self._checked_carry = False
        self._used_carry = False
        if self.imvj and duration is None:
            self._discard("an attempt of unknown exact duration (event-aligned re-run) cannot reuse a carried approximation")

    def end_window(self, *, accepted: bool, converged: bool, reason: str = "") -> None:
        """Close the current attempt: commit the IMVJ approximation only for an accepted, converged window."""
        if not self.imvj:
            return
        if not accepted:
            self._staged = None
            self._discard(f"attempt rejected and rolled back: {reason}" if reason else "attempt rejected and rolled back")
            return
        if not converged:
            self._staged = None
            self._discard("the accepted window did not converge; its secant information is not carried")
            return
        if self._staged is None:
            return
        key = (self._layout, self._supports, self._duration)
        self._reuses = self._reuses + 1 if self._used_carry else 0
        self._carried = self._staged
        self._carried_key = key
        self._staged = None

    # ---- one step ----------------------------------------------------------------------------

    def _admit_carry(self) -> np.ndarray | None:
        if not self.imvj or self._checked_carry:
            return self._carried
        self._checked_carry = True
        if self._carried is None:
            return None
        key = (self._layout, self._supports, self._duration)
        if self._carried_key != key:
            changed = [name for name, a, b in zip(("layout", "supports", "duration"), self._carried_key or (None,) * 3, key) if a != b]
            self._discard(f"the window differs from the one the approximation was built for: {', '.join(changed)}")
            return None
        if self._reuses >= self.policy.imvj_reuse_windows:
            self._discard(f"restart after {self._reuses} reuse(s) (imvj_reuse_windows = {self.policy.imvj_reuse_windows})")
            return None
        self._used_carry = True
        self._log("imvj_reused", f"reuse {self._reuses + 1} of at most {self.policy.imvj_reuse_windows}", routine=True)
        return self._carried

    def step(
        self,
        layout: tuple[tuple[str, int], ...],
        supports: tuple[Any, ...],
        old: np.ndarray,
        new: np.ndarray,
    ) -> np.ndarray:
        """The next joint iterate from ``x_k = old`` and ``H(x_k) = new`` (vectors in ``layout`` order)."""
        if self._layout and layout != self._layout:
            raise InvalidScientificProblem("IQN-ILS interface layout changed inside a coupling window")
        if self._supports and supports != self._supports:
            raise InvalidScientificProblem(
                "the support of an interface field changed inside a coupling window; its secant history "
                "relates values on another support and is refused"
            )
        self._layout, self._supports = layout, supports
        n = int(sum(size for _, size in layout))
        if self.imvj and n > self.policy.imvj_max_dimension:
            raise InvalidScientificProblem(
                f"IQN-IMVJ joint interface has {n} values; imvj_max_dimension is {self.policy.imvj_max_dimension} "
                f"(a dense {n}x{n} approximation is not held)"
            )
        residual = new - old
        weights = []
        offset = 0
        for edge_id, size in layout:
            if edge_id not in self._scales:
                part = residual[offset:offset + size]
                scale = float(np.linalg.norm(part)) / np.sqrt(max(1, size))
                resolved = True
                if self.imvj:
                    # Phase 3 review M5: a round-off residual (after a window already landed on its fixed point)
                    # would set a ~1e13 weight that amplifies round-off into the CARRIED approximation
                    image = float(np.linalg.norm(new[offset:offset + size])) / np.sqrt(max(1, size))
                    resolved = scale > 64.0 * np.finfo(np.float64).eps * max(image, np.finfo(np.float64).tiny)
                if scale > 0.0 and np.isfinite(scale) and resolved:
                    self._scales[edge_id] = scale
            weights.append(np.full(size, 1.0 / self._scales.get(edge_id, 1.0)))
            offset += size
        weight = np.concatenate(weights) if weights else np.zeros(0)
        self._residuals.append(residual.copy())
        self._images.append(new.copy())
        keep_count = self.policy.iqn_columns + 1
        del self._residuals[:-keep_count]
        del self._images[:-keep_count]
        carried = self._admit_carry()
        fallback = old + self.policy.factor * residual
        step = fallback
        staged: np.ndarray | None = carried
        if carried is not None:
            step = new - carried @ residual
        if len(self._residuals) >= 2:
            pairs = list(zip(self._residuals, self._residuals[1:]))
            v = np.column_stack([b - a for a, b in pairs])
            w = np.column_stack([b - a for a, b in zip(self._images, self._images[1:])])
            scaled = v * weight[:, None]
            if np.all(np.isfinite(scaled)) and float(np.max(np.abs(scaled))) > np.finfo(np.float64).tiny:
                keep = qr_filter(scaled, self.policy.iqn_filter, relative_to_largest=self.imvj)
                if keep and not self.imvj:
                    coefficients, *_ = np.linalg.lstsq(scaled[:, keep], -residual * weight, rcond=None)
                    candidate = new + w[:, keep] @ coefficients
                    if np.all(np.isfinite(candidate)):
                        step = candidate
                    else:
                        self._log("fallback_constant", "the least-squares IQN-ILS candidate is not finite")
                elif keep:
                    pinv = np.linalg.pinv(scaled[:, keep]) * weight[None, :]       # (D V)^+ D
                    base = np.zeros((n, n)) if carried is None else carried
                    update = w[:, keep] - base @ v[:, keep]
                    jacobian = base + update @ pinv
                    candidate = new - jacobian @ residual
                    if np.all(np.isfinite(candidate)) and np.all(np.isfinite(jacobian)):
                        step, staged = candidate, jacobian
                    else:
                        step, staged = fallback, None
                        self._log("fallback_constant", "the IQN-IMVJ candidate or approximation is not finite")
                        self._discard("a non-finite multi-vector update is inadmissible")
                else:
                    self._log("secant_columns_filtered", "every secant column was filtered as dependent", routine=not self.imvj)
            else:
                self._log("secant_columns_degenerate", "the scaled secant differences are zero or not finite",
                          routine=not self.imvj)
        if self.imvj and not np.all(np.isfinite(step)):
            step, staged = fallback, None
            self._log("fallback_constant", "the carried-approximation step is not finite")
            self._discard("a non-finite carried-approximation step is inadmissible")
        self._staged = staged
        return step

    def to_dict(self) -> dict[str, Any]:
        return {"policy": self.policy.to_dict(), "events": list(self.events),
                "notice": ("interface quasi-Newton acceleration changes the iteration path only; convergence is judged "
                           "on the unrelaxed transfer; no convergence guarantee, rate or error bound is implied")}


__all__ = ["InterfaceQuasiNewton", "qr_filter"]
