"""FORGE Blindfold L5: synthetic scientific universes (runs INSIDE the escrow only).

A universe is generated from a seed that never leaves the escrow.  It has:

* invented base dimensions and input variables with integer dimension vectors;
* dimensionless groups found by search (Buckingham-pi style), so the hidden
  law is dimensionally consistent in its own invented unit system;
* a hidden law: a constant times a scale monomial times a composition of
  power laws of the groups with NON-INTEGER exponents (optionally an
  exponential factor, a second additive term, or a regime switch), with
  constants drawn per instance;
* a noise model (multiplicative measurement noise; optional latent factor);
* allowed queries (a box over SETTABLE inputs; some variables are only
  observed), a query budget, hidden evaluation points and a cost model.

Control universes -- the system must earn credit by REFUSING them:

=====================  ==========================================================
NO_SOLUTION            the output is noise independent of every input
INSUFFICIENT_EVIDENCE  the budget/noise make the law unrecoverable
INDISTINGUISHABLE      two laws agree inside the query box, differ outside; the
                       hidden evaluation points are outside
SPURIOUS_CORRELATE     an observed covariate tracks a driver in observation but
                       has no effect; the evaluation decouples it
CONFOUNDED             a hidden common cause drives an observed covariate and the
                       output; only observation is allowed for the covariate
=====================  ==========================================================

Generated laws are canonicalized (:func:`~.expression.structure_digest`) and
rejected when they match the known-law signature library (small integer or
half-integer exponents in at most two factors), so a universe is never a
famous law with renamed symbols.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .expression import add, c, evaluate, mul, pw, structure_digest, v


class UniverseKind(str, Enum):
    DISCOVERABLE = "discoverable"
    NO_SOLUTION = "no_solution"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INDISTINGUISHABLE = "indistinguishable"
    SPURIOUS_CORRELATE = "spurious_correlate"
    CONFOUNDED = "confounded"


CONTROL_KINDS = frozenset(UniverseKind) - {UniverseKind.DISCOVERABLE}


@dataclass(frozen=True)
class Variable:
    name: str
    dimension: tuple[int, ...]
    low: float
    high: float
    settable: bool = True       # False: only observed (returned with each observation)

    def public(self, base_dimensions: tuple[str, ...]) -> dict[str, Any]:
        unit = "*".join(f"{b}^{e}" for b, e in zip(base_dimensions, self.dimension) if e) or "1"
        return {"name": self.name, "unit": unit, "settable": self.settable, "range": [self.low, self.high]}


@dataclass(frozen=True)
class HiddenWorld:
    """Everything the escrow knows.  Never serialized to the proposer."""

    universe_id: str
    kind: UniverseKind
    base_dimensions: tuple[str, ...]
    inputs: tuple[Variable, ...]
    output: str
    output_dimension: tuple[int, ...]
    law: Mapping[str, Any] | None          # None for NO_SOLUTION
    alternative_law: Mapping[str, Any] | None = None  # INDISTINGUISHABLE: the rival that agrees inside the box
    noise_sigma: float = 0.01
    budget: int = 60
    query_cost: float = 1.0
    covariates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # name -> how it is produced
    evaluation_points: tuple[Mapping[str, float], ...] = ()
    evaluation_mode: str = "interventional"   # covariates set independently of their drivers at evaluation
    tolerance: float = 0.05                    # relative error a law must meet at the evaluation points

    @property
    def law_structure(self) -> str:
        return "" if self.law is None else structure_digest(self.law)

    def public_card(self) -> dict[str, Any]:
        """What the proposer is told.  No law, seed, evaluation point, tolerance mechanism or kind."""
        return {"universe_id": self.universe_id, "level": "L5", "base_dimensions": list(self.base_dimensions),
                "inputs": [x.public(self.base_dimensions) for x in self.inputs],
                "observed_covariates": sorted(self.covariates),
                "output": {"name": self.output, "unit": "*".join(f"{b}^{e}" for b, e in zip(self.base_dimensions, self.output_dimension) if e) or "1"},
                "query_budget": self.budget, "query_cost": self.query_cost,
                "answers": ["law", "no_law", "insufficient_evidence", "indistinguishable", "confounded"]}


# ---------------------------------------------------------------------------- known-law signature library


def known_law_signature(exponents: tuple[float, ...]) -> bool:
    """True when a power-law signature looks like a textbook law: at most two factors, all exponents in
    {±1/2, ±1, ±3/2, ±2, ±3}.  Such a universe would test retrieval, not discovery (Blindfold L0)."""
    simple = {0.5, 1.0, 1.5, 2.0, 3.0}
    nonzero = [e for e in exponents if abs(e) > 1e-9]
    return len(nonzero) <= 2 and all(min(abs(abs(e) - s) for s in simple) < 1e-6 for e in nonzero)


def _exponent(rng: random.Random) -> float:
    while True:
        e = round(rng.uniform(0.2, 2.8) * rng.choice((-1, 1)), 3)
        if min(abs(abs(e) - k / 2) for k in range(1, 7)) > 0.06:   # never a half-integer: not a textbook exponent
            return e


# ---------------------------------------------------------------------------- dimensional bookkeeping


def _dimensionless_groups(inputs: tuple[Variable, ...], rng: random.Random, want: int) -> list[dict[str, int]]:
    """Small-integer exponent combinations of the inputs whose dimension vanishes (independent, non-trivial)."""
    names = [x.name for x in inputs]
    dims = [x.dimension for x in inputs]
    found: list[dict[str, int]] = []
    combos = list(itertools.product(range(-2, 3), repeat=len(inputs)))
    rng.shuffle(combos)
    for combo in combos:
        if not any(combo) or sum(1 for e in combo if e) < 2:
            continue
        total = [sum(e * d[i] for e, d in zip(combo, dims)) for i in range(len(dims[0]))]
        if any(total):
            continue
        vec = dict((n, e) for n, e in zip(names, combo) if e)
        if any(set(vec) == set(f) for f in found):          # crude independence: different support
            continue
        found.append(vec)
        if len(found) == want:
            break
    return found


def _monomial(exps: Mapping[str, int | float]) -> dict:
    factors = [pw(v(n), float(e)) for n, e in sorted(exps.items())]
    return factors[0] if len(factors) == 1 else mul(*factors)


def _random_inputs(rng: random.Random, base: tuple[str, ...], count: int, prefix: str) -> tuple[Variable, ...]:
    out = []
    for i in range(count):
        dim = tuple(rng.choice((-1, 0, 0, 1, 1, 2)) for _ in base)
        if not any(dim):
            dim = tuple(1 if j == i % len(base) else 0 for j in range(len(base)))
        low = round(10 ** rng.uniform(-1, 0.5), 4)
        out.append(Variable(f"{prefix}{i + 1}", dim, low, round(low * 10 ** rng.uniform(0.7, 1.3), 4)))
    return tuple(out)


def _sample(rng: random.Random, variables: tuple[Variable, ...], *, outside: bool = False) -> dict[str, float]:
    pt = {}
    for x in variables:
        lo, hi = math.log(x.low), math.log(x.high)
        if outside:  # beyond the query box (extrapolation), on the high side
            span = hi - lo
            pt[x.name] = math.exp(rng.uniform(hi + 0.5 * span, hi + 1.5 * span))
        else:
            pt[x.name] = math.exp(rng.uniform(lo, hi))
    return pt


# ---------------------------------------------------------------------------- generation


def generate_universe(seed: str, kind: UniverseKind | str = UniverseKind.DISCOVERABLE, *, n_eval: int = 40) -> HiddenWorld:
    """Generate one hidden world deterministically from ``seed`` (which must stay inside the escrow)."""
    kind = UniverseKind(kind)
    rng = random.Random(f"forge.blindfold.L5/1\n{seed}\n{kind.value}")
    base = tuple(f"D{chr(0x3B1 + i)}" for i in range(rng.choice((2, 3))))      # invented dimensions: Dα, Dβ, Dγ
    prefix = rng.choice(("q", "s", "z", "w"))
    for _attempt in range(200):
        inputs = _random_inputs(rng, base, rng.choice((3, 4)), prefix)
        groups = _dimensionless_groups(inputs, rng, want=2)
        if len(groups) >= 1:
            break
    else:  # pragma: no cover - generation is overwhelmingly successful
        raise RuntimeError("could not generate dimensionless groups")
    scale = {inputs[0].name: 1}
    out_dim = inputs[0].dimension
    exps = tuple(_exponent(rng) for _ in groups)
    if known_law_signature(exps):  # pragma: no cover - excluded by _exponent, kept as a guard
        exps = tuple(e + 0.137 for e in exps)
    const = round(10 ** rng.uniform(-1.0, 1.0), 6)
    factors = [c(const), _monomial(scale)] + [pw(_monomial(g), e) for g, e in zip(groups, exps)]
    law: dict | None = mul(*factors)
    form = rng.choice(("power", "power", "exp", "two_term", "regime"))
    if form == "exp" and groups:
        b = round(rng.uniform(0.05, 0.6), 4)
        law = mul(law, {"exp": mul(c(-b), _monomial(groups[0]))})
    elif form == "two_term" and len(groups) >= 1:
        e2 = _exponent(rng)
        law = add(law, mul(c(round(const * rng.uniform(0.2, 0.8), 6)), _monomial(scale), pw(_monomial(groups[0]), e2)))
    elif form == "regime" and groups:
        # switch on the first group at a threshold inside its observed range; continuous at the switch
        probe = [evaluate(_monomial(groups[0]), _sample(rng, inputs)) for _ in range(64)]
        probe = sorted(p for p in probe if math.isfinite(p) and p > 0)
        if probe:
            t = probe[len(probe) // 2]
            e_alt = _exponent(rng)
            k_alt = const * t ** (exps[0] - e_alt)                       # continuity at g1 = t
            other = [pw(_monomial(g), e) for g, e in zip(groups[1:], exps[1:])]
            below = mul(c(const), _monomial(scale), pw(_monomial(groups[0]), exps[0]), *other) if other else \
                mul(c(const), _monomial(scale), pw(_monomial(groups[0]), exps[0]))
            above = mul(c(k_alt), _monomial(scale), pw(_monomial(groups[0]), e_alt), *other) if other else \
                mul(c(k_alt), _monomial(scale), pw(_monomial(groups[0]), e_alt))
            law = {"piecewise": {"if_below": [_monomial(groups[0]), c(t)], "then": below, "else": above}}
    sigma = round(rng.uniform(0.005, 0.02), 4)
    budget = rng.choice((12, 30, 60))
    tol = max(0.03, 4 * sigma)
    covariates: dict[str, dict[str, Any]] = {}
    alternative = None
    eval_rng = random.Random(f"{seed}\neval")
    evaluation = tuple(_sample(eval_rng, inputs) for _ in range(n_eval))

    if kind is UniverseKind.NO_SOLUTION:
        law = None
    elif kind is UniverseKind.INSUFFICIENT_EVIDENCE:
        # the budget is drawn from the same set every universe uses, so the card does not reveal the kind;
        # the noise makes the law unrecoverable at that budget
        budget, sigma = rng.choice((12, 30, 60)), round(rng.uniform(0.6, 0.9), 3)
    elif kind is UniverseKind.INDISTINGUISHABLE:
        # the rival adds a term that is negligible inside the box and dominant outside it
        hi_pt = {x.name: x.high for x in inputs}
        lo_val = abs(evaluate(law, hi_pt))
        big = max(inputs, key=lambda x: x.high)
        growth = round(rng.uniform(3.2, 4.1), 3)
        k = 1e-4 * lo_val / max(big.high ** growth, 1e-300)
        alternative = add(law, mul(c(k), _monomial(scale), pw(v(big.name), growth), pw(_monomial(scale), -1.0)))
        if rng.random() < 0.5:                                           # which one is TRUE is hidden
            law, alternative = alternative, law
        evaluation = tuple(_sample(eval_rng, inputs, outside=True) for _ in range(n_eval))
    elif kind is UniverseKind.SPURIOUS_CORRELATE:
        driver = inputs[0].name
        covariates["u1"] = {"role": "spurious", "driver": driver, "exponent": round(rng.uniform(0.5, 1.5), 3)}
    elif kind is UniverseKind.CONFOUNDED:
        covariates["u1"] = {"role": "confounder_proxy", "exponent": round(rng.uniform(0.6, 1.4), 3)}
        law = mul(law, pw(v("__hidden_cause"), round(rng.uniform(0.7, 1.6), 3)))
    if not covariates and rng.random() < 0.5:
        # an irrelevant observed covariate, so that 'an observed covariate exists' is not a tell for the controls
        covariates["u1"] = {"role": "irrelevant", "exponent": 1.0}
    return HiddenWorld(universe_id=_universe_id(seed, kind), kind=kind,
                       base_dimensions=base, inputs=inputs, output="y", output_dimension=out_dim, law=law,
                       alternative_law=alternative, noise_sigma=sigma, budget=budget, covariates=covariates,
                       evaluation_points=evaluation, tolerance=tol)


def _universe_id(seed: str, kind: UniverseKind) -> str:
    return "bf-" + hashlib.sha256(f"universe-id\n{seed}\n{kind.value}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------- observation (inside the escrow)


def observe(world: HiddenWorld, settings: Mapping[str, float], rng: random.Random) -> dict[str, float]:
    """One noisy observation at the requested settings.  Refuses settings outside the box or for unsettable variables."""
    known = {x.name: x for x in world.inputs}
    extra = sorted(set(settings) - {n for n, x in known.items() if x.settable})
    if extra:
        raise ValueError(f"cannot set {extra}: not settable inputs of this universe")
    point: dict[str, float] = {}
    for name, x in known.items():
        if name not in settings:
            raise ValueError(f"the observation request does not set input {name!r}")
        val = float(settings[name])
        if not (math.isfinite(val) and x.low <= val <= x.high):
            raise ValueError(f"{name}={val} is outside the allowed query range [{x.low}, {x.high}]")
        point[name] = val
    hidden = math.exp(rng.gauss(0.0, 0.4))                                # a latent cause (used by CONFOUNDED)
    if world.law is None:
        y = math.exp(rng.gauss(0.0, 1.0))
    else:
        y = evaluate(world.law, {**point, "__hidden_cause": hidden})
        y *= math.exp(rng.gauss(0.0, world.noise_sigma))
    out = dict(point)
    for name, spec in world.covariates.items():
        if spec["role"] == "spurious":
            out[name] = point[spec["driver"]] ** spec["exponent"] * math.exp(rng.gauss(0.0, 0.01))
        elif spec["role"] == "irrelevant":
            out[name] = math.exp(rng.uniform(-1.0, 1.0))
        else:
            out[name] = hidden ** spec["exponent"] * math.exp(rng.gauss(0.0, 0.01))
    out[world.output] = y
    return out


def truth_at(world: HiddenWorld, point: Mapping[str, float], rng: random.Random) -> tuple[dict[str, float], float]:
    """Noise-free truth at an evaluation point, with covariates drawn INDEPENDENTLY of their drivers (intervention)."""
    hidden = math.exp(rng.gauss(0.0, 0.4))
    full = dict(point)
    for name, spec in world.covariates.items():
        full[name] = math.exp(rng.uniform(-1.0, 1.0))                     # decoupled from driver / cause
    if world.law is None:
        return full, float("nan")
    return full, evaluate(world.law, {**point, "__hidden_cause": hidden})


__all__ = ["CONTROL_KINDS", "HiddenWorld", "UniverseKind", "Variable", "generate_universe", "known_law_signature", "observe", "truth_at"]
