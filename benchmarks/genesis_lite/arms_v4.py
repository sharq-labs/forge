"""Genesis-lite v0.4 DEVELOPMENT baseline arms (owner decisions D2/EXC-5 and D14, 2026-10-30; ACTIVE_PLAN "Blindfold
Step 1 gap closure"). New arms only: the registered v0.2/v0.3 arms and their recorded results are untouched.

* ``random_grammar`` -- Genesis §10.5 "constrained random valid expressions": RANDOM_DRAWS structures drawn uniformly
  (seeded per universe) from the SAME five-shape grammar ``grammar_enumeration`` enumerates, fitted on the training
  split and chosen by the same evidence rule, then judged by the same gate. It isolates what enumeration adds over a
  random draw of equal form; it is not a weakened copy of the grammar arm's code path (same functions, fewer
  structures).
* ``pysr_units`` -- EXC-5: PySR on the SETTABLE inputs only (as the grammar arm), fitting ln y on the training split
  (the gate is on the ln scale), with the card's declared units passed as ``X_units`` after a pure renaming of the
  invented base dimensions to SI symbols. The equation is chosen on PySR's Pareto front by validation error on a part
  of the TRAINING split (never the hold-out), the smallest complexity within ``OCCAM_SLACK`` of the best, and it is
  judged by the grammar arm's gate WITH the precision bar, using the chosen equation's constant count as its
  parameters (FDA-21). The law is ``exp(g(x))``.

Failure semantics (D14): an import, Julia, fit or grammar-translation failure RAISES, so the campaign scores the
universe ``inadmissible``; a broken method never earns a refusal's credit. Ordinary refusals (too few rows,
non-positive outputs, a gate bar) stay refusals, exactly as for the grammar arm.

Configurations are fixed here before any pilot; nothing is tuned on EXC-2/3/4 results. DEVELOPMENT_ONLY.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import tempfile
from typing import Any, Callable, Mapping

import numpy as np

from engcore.blindfold.expression import ExpressionRefused, validate
from engcore.mind.grammar import DimensionRefused, InputDimension, analyse, enumerate_structures, select, to_expression
from engcore.mind.grammar.dimensions import parse_unit

from . import arms
from .arms_grammar_v3 import design_matrix, gate
from .arms_v3 import GrammarRefused, _int_seed, _refuse, to_grammar

RANDOM_DRAWS = 10                    # equal to the grammar evidence rule's TOP list, declared before any pilot
PYSR_UNITS_SETTINGS = {"niterations": 40, "populations": 8, "population_size": 33, "maxsize": 20,
                       "binary_operators": ["+", "-", "*", "/"], "unary_operators": ["exp", "log"]}
VALIDATION_FRACTION = 0.25          # of the training rows, for choosing on the Pareto front
OCCAM_SLACK = 0.05                  # smallest complexity within 5% of the best validation error (as the grammar rule)
SI_BASES = ("m", "kg", "s", "A", "K", "mol", "cd")


class ArmFailure(RuntimeError):
    """A method failure that must score ``inadmissible`` (D14), never a refusal."""


# ------------------------------------------------------------------------------------------------ random_grammar
def random_grammar(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    uid, out = card["universe_id"], card["output"]["name"]
    rng = random.Random(f"random_grammar:{seed}:{uid}")
    rows, replicate = arms._gather(card, client, rng, "lhs", "r")
    settable = [x for x in card["inputs"] if x.get("settable")]
    if len(rows) < len(settable) + 6 + replicate:
        return _refuse(card, "too few observations")
    if any(not (r[out] > 0) for r in rows):
        return _refuse(card, "a non-positive output: the ln-scale grammar does not apply")
    try:
        basis = analyse([InputDimension(x["name"], x["unit"], x["range"][0], x["range"][1]) for x in settable],
                        card["output"]["unit"], card["base_dimensions"])
    except DimensionRefused as exc:
        return _refuse(card, f"dimensional analysis refused: {exc}")
    sigma = arms._replicate_noise(rows, replicate, out)
    if sigma is None or not sigma > 0:
        return _refuse(card, "no replicate-noise estimate: the grammar's likelihood is not defined")
    train, _, _, _ = arms._split(rows, replicate)
    every, _ = enumerate_structures(len(basis.groups))           # the same capped set grammar_enumeration fits
    drawn = random.Random(f"random_grammar:draw:{seed}:{uid}").sample(every, min(RANDOM_DRAWS, len(every)))
    L, z = design_matrix(basis, train, out)
    bound = hashlib.sha256(json.dumps([uid, seed, train], sort_keys=True).encode()).hexdigest()[:24]
    sel = select(drawn, L, z, sigma=sigma, ledger_id=f"random_grammar:{bound}", generated=len(drawn))
    note = f"random grammar ({len(drawn)} of {len(every)} structures drawn; {len(basis.groups)} groups)"
    if sel.chosen is None:
        return _refuse(card, f"{note}: {sel.reason}")
    law = to_expression(sel.chosen.structure, np.asarray(sel.chosen.theta), basis)
    try:
        validate(law)
    except ExpressionRefused as exc:
        return _refuse(card, f"{note}: the selected law is outside the escrow grammar limits: {exc}")
    return gate(card, rows, replicate, law, sel.chosen.structure.n_params, f"{note}: selected {sel.chosen.structure.key}")


# ------------------------------------------------------------------------------------------------ pysr_units
def si_unit(unit: str, bases: list[str]) -> str:
    """The card unit renamed onto SI base symbols (a pure renaming of invented dimensions; refuses >7 bases)."""
    if len(bases) > len(SI_BASES):
        raise DimensionRefused("more invented base dimensions than SI base symbols")
    vec = parse_unit(unit, bases)
    parts = [f"{SI_BASES[i]}^{e}" for i, e in enumerate(vec) if e]
    return "*".join(parts) if parts else "1"


def _dimension(expr: Any, dims: Mapping[str, tuple[int, ...]], width: int) -> tuple[float, ...] | None:
    """The dimension vector of a SymPy expression with DIMENSIONLESS constants, or None if inconsistent."""
    import sympy
    zero = (0.0,) * width
    if expr.is_Symbol:
        return tuple(float(e) for e in dims[str(expr)])
    if expr.is_number:
        return zero
    if isinstance(expr, sympy.Add):
        parts = [_dimension(a, dims, width) for a in expr.args]
        return parts[0] if parts and all(p is not None and p == parts[0] for p in parts) else None
    if isinstance(expr, sympy.Mul):
        parts = [_dimension(a, dims, width) for a in expr.args]
        return None if any(p is None for p in parts) else tuple(map(sum, zip(*parts)))
    if isinstance(expr, sympy.Pow):
        base, k = expr.args
        d = _dimension(base, dims, width)
        return None if d is None or not k.is_number else tuple(float(k) * x for x in d)
    if isinstance(expr, (sympy.exp, sympy.log)):
        d = _dimension(expr.args[0], dims, width)
        return zero if d == zero else None
    return None


def _constants(expr: Any) -> int:
    return sum(1 for a in expr.atoms() if a.is_number and not a.is_Integer)


def _log_space_law(equation: Any, aliases: Mapping[str, str]) -> dict:
    """``exp(g)`` in the escrow grammar, for an equation g of ln y."""
    try:
        law = {"exp": to_grammar(equation, aliases)}
        validate(law)
    except (GrammarRefused, ExpressionRefused) as exc:
        raise ArmFailure(f"the PySR equation does not translate into the escrow grammar: {exc}") from exc
    return law


def pysr_units(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    uid, out = card["universe_id"], card["output"]["name"]
    rng = random.Random(f"pysr_units:{seed}:{uid}")
    rows, replicate = arms._gather(card, client, rng, "lhs", "p")
    settable = [x for x in card["inputs"] if x.get("settable")]
    names = [x["name"] for x in settable]
    if len(rows) < len(names) + 6 + replicate:
        return _refuse(card, "too few observations")
    if any(not (r[out] > 0) for r in rows):
        return _refuse(card, "a non-positive output: the ln-scale fit does not apply")
    bases = list(card["base_dimensions"])
    try:
        units = [si_unit(x["unit"], bases) for x in settable]
        dims = {f"x{i}": parse_unit(x["unit"], bases) for i, x in enumerate(settable)}
    except DimensionRefused as exc:
        return _refuse(card, f"declared units refused: {exc}")
    train, _, _, _ = arms._split(rows, replicate)
    cut = max(1, int(round(len(train) * (1 - VALIDATION_FRACTION))))
    fit_rows, val_rows = train[:cut], train[cut:]
    if len(val_rows) < 3:
        return _refuse(card, "too few training rows to hold out a validation part")
    aliases = {f"x{i}": n for i, n in enumerate(names)}
    try:
        from pysr import PySRRegressor
        import sympy
        with tempfile.TemporaryDirectory(prefix="gl-pysr-units-") as scratch:
            model = PySRRegressor(**PYSR_UNITS_SETTINGS, deterministic=True, parallelism="serial",
                                  random_state=_int_seed("pysr_units", seed, uid), progress=False, verbosity=0,
                                  output_directory=scratch)
            model.fit(np.array([[r[n] for n in names] for r in fit_rows]), np.log([r[out] for r in fit_rows]),
                      variable_names=list(aliases), X_units=units, y_units="1")    # ln y is dimensionless
            front = [(int(row["complexity"]), sympy.sympify(row["sympy_format"]))
                     for _, row in model.equations_.iterrows()]
    except Exception as exc:  # noqa: BLE001 - every library failure must score inadmissible, never a refusal (D14)
        raise ArmFailure(f"PySR failed: {type(exc).__name__}: {exc}") from exc
    if not front:
        raise ArmFailure("PySR returned no equation")
    xv = {a: np.array([r[n] for r in val_rows]) for a, n in aliases.items()}
    target = np.log([r[out] for r in val_rows])
    scored = []
    for complexity, eq in front:
        fn = sympy.lambdify(list(aliases), eq, modules="numpy")
        with np.errstate(all="ignore"):
            pred = np.broadcast_to(np.asarray(fn(*[xv[a] for a in aliases]), dtype=float), target.shape)
        if np.all(np.isfinite(pred)):
            scored.append((float(np.mean((pred - target) ** 2)), complexity, eq))
    if not scored:
        raise ArmFailure("no Pareto-front equation is finite on the validation rows")    # a method failure (D14)
    best = min(s[0] for s in scored)
    mse, complexity, equation = min((s for s in scored if s[0] <= best * (1 + OCCAM_SLACK) + 1e-300),
                                    key=lambda s: (s[1], s[0]))
    law = _log_space_law(equation, aliases)
    consistent = _dimension(equation, dims, len(bases)) == (0.0,) * len(bases)
    why = (f"PySR (units passed; chosen complexity {complexity} of {len(front)} on the Pareto front, validation mse "
           f"{mse:.3g})")
    out = dict(gate(card, rows, replicate, law, max(1, _constants(equation)), why))
    out["dimensionally_consistent"] = consistent             # EXC-5: recorded per universe, never a scoring input
    return out


#: name -> (callable, family, stochastic, role), the arms.ARMS layout
ARMS_V4: dict[str, tuple[Callable[..., dict[str, Any]], str, bool, str]] = {
    "random_grammar": (random_grammar, "law recovery: constrained random valid expressions from the five-shape grammar",
                       True, "competence"),
    "pysr_units": (pysr_units, "law recovery: units-aware PySR on ln y, Pareto choice on training validation (EXC-5)",
                   True, "competence"),
}
_MODULES = {"pysr_units": "pysr"}

__all__ = ["ARMS_V4", "ArmFailure", "OCCAM_SLACK", "PYSR_UNITS_SETTINGS", "RANDOM_DRAWS", "pysr_units",
           "random_grammar", "si_unit"]
