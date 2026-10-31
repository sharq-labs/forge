"""Genesis-lite v0.3 DEVELOPMENT baselines: the strongest traditional methods available (owner-approved 2026-10-28).

Each arm has the shared signature ``arm(card, client, *, seed) -> proposal``, sees only the presented card and an observe
client whose budget the escrow enforces, and reuses the design, split and decision-gate machinery of :mod:`.arms` wherever
its method allows, so that a comparison isolates the method:

* ``pysindy_stlsq`` -- PySINDy's sequentially thresholded least squares (STLSQ) selects terms of the log-monomial library
  on the training split; the selected variables then pass the same refit and gate as ``monomial_enumeration``.
* ``bo_botorch_variance`` -- experiment selection only: after a small Latin-hypercube start, a BoTorch GP on log inputs
  chooses each next query where its posterior standard deviation is largest; the rows then go through
  ``monomial_enumeration``'s Occam selection and gate.
* ``pysr_symbolic`` -- PySR symbolic regression over {+, -, *, /, exp, log} on the training split. The chosen equation is
  translated into the escrow's expression grammar (refused, never approximated, when it cannot be) and judged on the arm's
  own held-out rows with the gate's constant-baseline, replicate-noise lack-of-fit, covariate and extrapolation checks.
  The gate's parameter-precision bar is defined for a log-linear fit and has no analogue for a free form: not applied.

Configurations are fixed here before any campaign (no tuning on final data). A library failure (import, Julia, GP fit) is
NOT caught: it propagates, and the campaign stores the universe as ``inadmissible`` (negative credit), so a broken method
can never earn a refusal's credit. The only design fallback is explicit and named in the rationale: the BoTorch arm spends
the rest of its budget on a Latin hypercube when fewer than three positive outputs leave nothing to model in log space.

Known differences from ``monomial_enumeration`` (a comparison isolates method and design together, not method alone):
PySINDy and PySR use the Latin-hypercube design; PySR fits squared error on raw outputs while scoring is relative; the
free-form gate omits the precision bar but refuses when the law is undefined on any training or held-out row. The grammar
translation is exact up to floating point: rational exponents and irrational constants become the nearest doubles.
DEVELOPMENT_ONLY: not frozen baselines.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import math
import random
import tempfile
from typing import Any, Callable, Mapping

import numpy as np

from engcore.blindfold import baselines as bf
from engcore.blindfold.expression import ExpressionRefused, add, c, evaluate, mul, pw, v, validate

from . import arms

STLSQ_THRESHOLD = 0.1          # exponents below this magnitude are dropped (log-log library)
BO_INIT_FRACTION = 0.25        # share of the fresh budget spent on the Latin-hypercube start
PYSR_SETTINGS = {"niterations": 40, "populations": 8, "population_size": 33, "maxsize": 15,
                 "binary_operators": ["+", "-", "*", "/"], "unary_operators": ["exp", "log"]}


class GrammarRefused(ValueError):
    """A symbolic result that the escrow's expression grammar cannot express exactly."""


def _int_seed(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256(":".join(map(str, parts)).encode()).digest()[:4], "big")


def to_setting(u: float, x: Mapping[str, Any]) -> float:
    """Map a unit-box coordinate to a log-uniform setting inside the input's range (exp(log(b)) can exceed b by an ulp,
    which the escrow refuses as outside the box)."""
    low, high = float(x["range"][0]), float(x["range"][1])
    if u <= 0.0:
        return low
    if u >= 1.0:
        return high
    value = math.exp(math.log(low) + (math.log(high) - math.log(low)) * u)
    return min(max(value, low), high)


def _refuse(card: Mapping[str, Any], why: str) -> dict[str, Any]:
    return {"universe_id": card["universe_id"], "answer": "insufficient_evidence", "rationale": why}


def _select_and_gate(card: Mapping[str, Any], rows: list[dict], replicate: int, why: str) -> dict[str, Any]:
    names, out = arms._variables(card), card["output"]["name"]
    train, _, _, _ = arms._split(rows, replicate)
    subsets = [list(s) for k in range(len(names) + 1) for s in itertools.combinations(names, k)]
    chosen = arms._occam([(s, arms._cv_mse(train, s, out)) for s in subsets])
    return arms._clean(arms._gate(card, rows, replicate, chosen, why))


# ------------------------------------------------------------------------------------------------ PySINDy
def pysindy_stlsq(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    rng = random.Random(f"sindy:{seed}:{card['universe_id']}")
    rows, replicate = arms._gather(card, client, rng, "lhs", "y")
    names, out = arms._variables(card), card["output"]["name"]
    train, _, _, _ = arms._split(rows, replicate)
    ok = arms._positive(train, names, out)
    if len(ok) < len(names) + 2:
        return _refuse(card, "too few positive training rows for the log-monomial library")
    from pysindy.optimizers import STLSQ           # a library failure propagates: the universe is scored inadmissible
    X = np.column_stack([np.ones(len(ok))] + [np.log([r[n] for r in ok]) for n in names])
    y = np.log([r[out] for r in ok])
    opt = STLSQ(threshold=STLSQ_THRESHOLD, alpha=0.0)
    opt.fit(X, y.reshape(-1, 1))
    coef = np.asarray(opt.coef_).reshape(-1)
    selected = [n for n, a in zip(names, coef[1:]) if abs(a) > 0]
    return arms._clean(arms._gate(card, rows, replicate, selected, "PySINDy STLSQ term selection, refit and gate"))


# ------------------------------------------------------------------------------------------------ BoTorch
def bo_botorch_variance(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    uid, out = card["universe_id"], card["output"]["name"]
    xs = [x for x in card["inputs"] if x["settable"]]
    budget = int(card["query_budget"])
    replicate = min(4, budget // 4)
    fresh_budget = max(0, budget - replicate)
    rng = random.Random(f"bo:{seed}:{uid}")
    n_init = min(fresh_budget, max(2 * len(xs) + 2, int(BO_INIT_FRACTION * fresh_budget)))
    init = arms._design_lhs(card, n_init, rng)
    rows = arms._collect(card, client, init, "bi")
    design_note = "BoTorch GP posterior-sd design"
    # library failures (import, GP fit, acquisition) propagate: the universe is scored inadmissible, never relabelled
    import torch
    from botorch.acquisition.analytic import PosteriorStandardDeviation
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import SingleTaskGP
    from botorch.optim import optimize_acqf
    from gpytorch.mlls import ExactMarginalLogLikelihood
    torch.manual_seed(_int_seed("bo", seed, uid))
    exhausted = len(rows) < len(init)
    while not exhausted and len(rows) < fresh_budget:
        pos = [r for r in rows if r[out] > 0]
        if len(pos) < 3:
            design_note = ("design fallback: fewer than three positive outputs to model in log space; "
                           "Latin hypercube for the remaining budget")
            rest = arms._design_lhs(card, fresh_budget - len(rows), rng)
            got = arms._collect(card, client, rest, "bf")
            rows += got
            exhausted = len(got) < len(rest)
            break
        X = torch.tensor([[(math.log(r[x["name"]]) - math.log(x["range"][0])) /
                           (math.log(x["range"][1]) - math.log(x["range"][0])) for x in xs] for r in pos], dtype=torch.double)
        Y = torch.tensor([[math.log(r[out])] for r in pos], dtype=torch.double)
        Y = (Y - Y.mean()) / (Y.std() if float(Y.std()) > 0 else 1.0)
        model = SingleTaskGP(X, Y)
        fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
        bounds = torch.tensor([[0.0] * len(xs), [1.0] * len(xs)], dtype=torch.double)
        cand, _ = optimize_acqf(PosteriorStandardDeviation(model), bounds=bounds, q=1, num_restarts=4, raw_samples=64)
        u = cand.detach().numpy().reshape(-1)
        got = arms._collect(card, client, [{x["name"]: to_setting(float(u[i]), x) for i, x in enumerate(xs)}],
                            f"b{len(rows)}")
        if not got:
            exhausted = True                             # the escrow refused on budget (any other refusal propagates)
        rows += got
    if not exhausted:
        rows += arms._collect(card, client, init[:replicate], "br")   # replicates of the first points, as _split expects
    return _select_and_gate(card, rows, replicate, f"{design_note}; enumeration and gate")


# ------------------------------------------------------------------------------------------------ PySR
def to_grammar(expr: Any, names: Mapping[str, str]) -> dict:
    """Translate a SymPy expression into the escrow grammar (exact up to floating point), or refuse."""
    import sympy
    if expr.is_Symbol:
        if str(expr) not in names:
            raise GrammarRefused(f"unknown symbol {expr}")
        return v(names[str(expr)])
    if expr.is_number:
        value = complex(expr)
        if value.imag != 0 or not math.isfinite(value.real):
            raise GrammarRefused("a constant is a finite real number")
        return c(value.real)
    if isinstance(expr, sympy.Add):
        return add(*[to_grammar(a, names) for a in expr.args])
    if isinstance(expr, sympy.Mul):
        return mul(*[to_grammar(a, names) for a in expr.args])
    if isinstance(expr, sympy.Pow):
        base, k = expr.args
        if not k.is_number:
            raise GrammarRefused("an exponent is a constant in the escrow grammar")
        return pw(to_grammar(base, names), float(k))
    if isinstance(expr, sympy.exp):
        return {"exp": to_grammar(expr.args[0], names)}
    if isinstance(expr, sympy.log):
        return {"log": to_grammar(expr.args[0], names)}
    raise GrammarRefused(f"{type(expr).__name__} is outside the escrow grammar")


def _log_value(law: Mapping[str, Any], row: Mapping[str, float]) -> float | None:
    try:
        value = evaluate(law, row)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
    return math.log(value) if math.isfinite(value) and value > 0 else None


def _gate_free_form(card: Mapping[str, Any], rows: list[dict], replicate: int, law: dict, why: str) -> dict[str, Any]:
    """The gate's held-out checks for a free-form law (log space; the parameter-precision bar does not apply)."""
    uid, out = card["universe_id"], card["output"]["name"]
    train, hold, _, _ = arms._split(rows, replicate)
    noise = arms._replicate_noise(rows, replicate, out)
    fit_train = [(math.log(r[out]), _log_value(law, r)) for r in train if r[out] > 0]
    fit_hold = [(math.log(r[out]), _log_value(law, r)) for r in hold if r[out] > 0]
    if len(fit_hold) < 3 or any(p is None for _, p in fit_train + fit_hold):
        return _refuse(card, "the symbolic law is undefined on some queries or there are too few held-out rows")
    err_fit = [y - p for y, p in fit_hold]
    mean_train = float(np.mean([y for y, _ in fit_train]))
    err_const = [y - mean_train for y, _ in fit_hold]
    if float(np.mean(np.square(err_fit))) > 0.8 * float(np.mean(np.square(err_const))):
        return {"universe_id": uid, "answer": "no_law", "rationale": "on held-out queries the variables do not beat a constant"}
    resid = float(np.sqrt(np.mean(np.square([y - p for y, p in fit_train]))))
    scale = noise if noise is not None and noise > 0 else resid
    rms_hold = float(np.sqrt(np.mean(np.square(err_fit))))
    if not (rms_hold <= arms.LACK_OF_FIT_RATIO * scale and resid <= arms.LACK_OF_FIT_RATIO * scale):
        covs = list(card.get("observed_covariates", ()))
        pos = [r for r in rows if r[out] > 0 and covs and r[covs[0]] > 0 and _log_value(law, r) is not None]
        if covs and len(pos) > 3:
            res = [math.log(r[out]) - _log_value(law, r) for r in pos]
            cv = [math.log(r[covs[0]]) for r in pos]
            if float(np.std(cv)) > 0 and abs(float(np.corrcoef(res, cv)[0, 1])) > 0.5:
                return {"universe_id": uid, "answer": "confounded", "rationale": "residuals track a passive covariate"}
        return _refuse(card, "lack-of-fit bar not met")
    if bf._extrapolates(card):
        return _refuse(card, "assessment region lies outside the query box")
    return {"universe_id": uid, "answer": "law", "law": law, "rationale": why}


def pysr_symbolic(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    rng = random.Random(f"pysr:{seed}:{card['universe_id']}")
    rows, replicate = arms._gather(card, client, rng, "lhs", "s")
    names, out = arms._variables(card), card["output"]["name"]
    if len(rows) < len(names) + 6 + replicate:
        return _refuse(card, "too few observations")
    train, _, _, _ = arms._split(rows, replicate)
    aliases = {f"x{i}": n for i, n in enumerate(names)}
    from pysr import PySRRegressor                 # a library or Julia failure propagates: scored inadmissible
    with tempfile.TemporaryDirectory(prefix="gl-pysr-") as scratch:
        model = PySRRegressor(**PYSR_SETTINGS, deterministic=True, parallelism="serial",
                              random_state=_int_seed("pysr", seed, card["universe_id"]), progress=False, verbosity=0,
                              output_directory=scratch)
        model.fit(np.array([[r[n] for n in names] for r in train]), np.array([r[out] for r in train]),
                  variable_names=list(aliases))
        equation = model.sympy()
    try:
        law = to_grammar(equation, aliases)
        validate(law)
    except (GrammarRefused, ExpressionRefused) as exc:
        return _refuse(card, f"the PySR equation is outside the escrow grammar: {exc}")
    return _gate_free_form(card, rows, replicate, law, "PySR symbolic regression with held-out gate")


#: name -> (callable, family, stochastic, role), the arms.ARMS layout
ARMS_V3: dict[str, tuple[Callable[..., dict[str, Any]], str, bool, str]] = {
    "pysr_symbolic": (pysr_symbolic, "law recovery: PySR symbolic regression (development configuration)", True,
                      "competence"),
    "pysindy_stlsq": (pysindy_stlsq, "sparse identification: PySINDy STLSQ over the log-monomial library", True,
                      "competence"),
    "bo_botorch_variance": (bo_botorch_variance, "experiment selection: BoTorch GP posterior-sd design", True,
                            "competence"),
}
_MODULES = {"pysr_symbolic": "pysr", "pysindy_stlsq": "pysindy", "bo_botorch_variance": "botorch"}


def availability_v3() -> dict[str, dict[str, str]]:
    """Installed arms are AVAILABLE_DEVELOPMENT (not frozen); missing ones are NOT_AVAILABLE and never substituted."""
    out = {}
    for name, module in sorted(_MODULES.items()):
        installed = importlib.util.find_spec(module) is not None
        out[name] = {"family": ARMS_V3[name][1], "status": "AVAILABLE_DEVELOPMENT" if installed else "NOT_AVAILABLE",
                     "reason": f"{module} {'is installed' if installed else 'is not installed'} in this environment"}
    return out


__all__ = ["ARMS_V3", "GrammarRefused", "availability_v3", "bo_botorch_variance", "pysindy_stlsq", "pysr_symbolic",
           "to_grammar"]
