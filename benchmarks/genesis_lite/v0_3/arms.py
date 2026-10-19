"""Genesis-lite v0.3 DRAFT baseline arms: the v0.2 arms with the FDA-21 residual degrees of freedom corrected.

FDA-21 (deep audit 2026-10-19, E-07): ``arms._fit`` returned ``np.std(y - X @ coef)``, the ddof = 0 residual sd. It
ignores the p + 1 fitted parameters, so E[resid^2] = sigma^2 (n - p - 1) / n (factor 0.577 on the sd at budget 12 with
three names). ``resid`` drives the precision bar, the lack-of-fit bar and the fallback noise scale of every gated arm.
``arms._replicate_noise`` likewise took ``np.std`` of replicate differences, which subtracts their mean. Under the
model, replicate log-differences have mean zero, so the unbiased estimate is ``sqrt(sum(d^2) / (2 m))``.

v0.2's ``arms.py`` is pinned by the v0.2 preregistration and is not edited. This module rebinds every v0.2 arm
function to a COPY of the v0.2 module namespace in which exactly two names are replaced: ``_fit`` and
``_replicate_noise``. Every other line of arm logic (designs, splits, gates, thresholds) is the v0.2 code, unchanged
and digest-pinned through v0.2.

Arms may be ADDED by a new identity, never removed or weakened (preregistered rule). The corrected gates are stricter,
so they refuse more often and could weaken a baseline. v0.3 therefore KEEPS every v0.2 arm unchanged and ADDS one
corrected variant, ``<name>_dof``, for each gated competence arm; the strongest baseline is the maximum over both. The
gate constants (3.5, PRECISION, 0.5) are not re-tuned. ``careful`` comes from certified ``engcore.blindfold.baselines``
and keeps its ddof = 0 estimate (documented exception; changing it is a certified change).
"""

from __future__ import annotations

import math
from types import FunctionType
from typing import Any, Callable

import numpy as np

from .. import arms as _v02

RESIDUAL_DOF = "n - p - 1"
REPLICATE_NOISE = "sqrt(sum(d^2) / (2 m)) over mean-zero replicate log-differences"


def _fit(rows: list[dict], names: list[str], out: str) -> tuple[np.ndarray, float] | None:
    """v0.2's fit with the residual sd on n - p - 1 degrees of freedom (n >= p + 2 is already required)."""
    ok = _v02._positive(rows, names, out)
    if len(ok) < len(names) + 2:
        return None
    X = np.column_stack([np.ones(len(ok))] + [np.log([r[n] for r in ok]) for n in names])
    y = np.log([r[out] for r in ok])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    dof = len(ok) - len(names) - 1
    return coef, float(math.sqrt(float(np.sum(np.square(y - X @ coef))) / dof))


def _replicate_noise(rows: list[dict], replicate: int, out: str) -> float | None:
    _, _, reps, base = _v02._split(rows, replicate)
    diffs = [math.log(r[out]) - math.log(b[out]) for r, b in zip(reps, base) if r[out] > 0 and b[out] > 0]
    return float(math.sqrt(sum(d * d for d in diffs) / (2 * len(diffs)))) if len(diffs) >= 2 else None


def _rebind(namespace: dict[str, Any]) -> dict[str, Any]:
    """Every function defined in v0.2 ``arms`` re-created over ``namespace`` (same code objects, other globals)."""
    out = {}
    for name, obj in vars(_v02).items():
        if isinstance(obj, FunctionType) and obj.__module__ == _v02.__name__:
            fn = FunctionType(obj.__code__, namespace, obj.__name__, obj.__defaults__, obj.__closure__)
            fn.__kwdefaults__ = dict(obj.__kwdefaults__) if obj.__kwdefaults__ else None
            fn.__doc__, fn.__qualname__ = obj.__doc__, obj.__qualname__
            out[name] = fn
    return out


_NAMESPACE: dict[str, Any] = dict(vars(_v02))
_NAMESPACE.update(_rebind(_NAMESPACE))
_NAMESPACE.update(_fit=_fit, _replicate_noise=_replicate_noise)
REPLACED = ("_fit", "_replicate_noise")


def _resolve(fn: Callable[..., Any]) -> Callable[..., Any]:
    """The v0.3 counterpart of a v0.2 registry callable. ``_fixed`` wrappers (closures over engcore baselines that never
    call ``_fit``) are kept as they are."""
    return _NAMESPACE.get(fn.__name__, fn) if fn.__module__ == _v02.__name__ and fn.__name__ in _NAMESPACE else fn


#: the gated competence arms that call ``_fit`` / ``_replicate_noise`` and get a corrected variant
CORRECTED = ("extrapolating_fit", "extrapolation_pair", "fit_all_gated", "greedy_forward", "monomial_enumeration",
             "random_structures", "space_filling")
ARMS: dict[str, tuple[Callable[..., dict[str, Any]], str, bool, str]] = dict(_v02.ARMS)
ARMS.update({f"{name}_dof": (_resolve(_v02.ARMS[name][0]), _v02.ARMS[name][1] + " (FDA-21: n - p - 1 residual dof)",
                             _v02.ARMS[name][2], _v02.ARMS[name][3]) for name in CORRECTED})
UNAVAILABLE_ARMS = _v02.UNAVAILABLE_ARMS
PRECISION, LACK_OF_FIT_RATIO, OCCAM_SLACK = _v02.PRECISION, _v02.LACK_OF_FIT_RATIO, _v02.OCCAM_SLACK

# importable by name from the isolated proposer (``benchmarks.genesis_lite.v0_3.arms:<name>``)
globals().update({name: entry[0] for name, entry in ARMS.items()})
