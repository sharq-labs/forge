"""FORGE Blindfold L5: synthetic scientific universes (runs INSIDE the escrow only).

A universe is generated from a seed that never leaves the escrow.  It has:

* invented base dimensions and input variables with integer dimension vectors;
* dimensionless groups found by search (Buckingham-pi style), so the hidden
  law is dimensionally consistent in its own invented unit system;
* a hidden law: a constant times a scale monomial (a randomly chosen input to
  the power 1, 2 or -1) times power laws of the groups with NON-INTEGER
  exponents (optionally an exponential factor, a second additive term, or a
  regime switch), with constants drawn per instance;
* a noise model (multiplicative measurement noise; a latent cause in the
  CONFOUNDED control);
* allowed queries (a box over the settable inputs; one passively OBSERVED,
  dimensionless covariate ``u1`` in every universe), a query budget, a cost
  model, a public ASSESSMENT REGION where predictions will be judged, and
  hidden evaluation points drawn from it.

Control universes -- the system must earn credit by REFUSING them (or, for
CONFOUNDED, by naming the interventional law it cannot have learned passively):

=====================  ==========================================================
NO_SOLUTION            the output is noise independent of every input
INSUFFICIENT_EVIDENCE  the budget/noise make the law unrecoverable
INDISTINGUISHABLE      a rival law differs from the law by at most 0.5 sigma
                       inside the box (verified on the box corners and a dense
                       sample) and by more than 3x the tolerance at >= 90% of
                       the evaluation points in the (extended) assessment
                       region (verified; regenerated otherwise).  Which of the
                       two is true is hidden.  By construction this is
                       observationally equivalent in the box to a DISCOVERABLE
                       universe with an extended region: the control measures
                       whether a proposer extrapolates beyond what its evidence
                       supports, not whether it can see the rival.
SPURIOUS_CORRELATE     ``u1`` tracks a settable driver in observation but has
                       no effect; evaluation decouples it
CONFOUNDED             a latent cause drives ``u1`` (observed only, never
                       settable) AND the output; ``u1`` also has a true causal
                       effect.  The passive association of y with u1 is biased;
                       truth is the INTERVENTIONAL expectation E[y | do(x, u1)]
=====================  ==========================================================

Every card has the same shape (one covariate ``u1``, an assessment region), so
neither covariate presence nor card layout reveals the kind.  An extended
assessment region is drawn for half of the non-INDISTINGUISHABLE universes too.
The region is still a PARTIAL tell: a box region rules INDISTINGUISHABLE out,
and the extension follows the first group, hinting which inputs carry
structure.  Credit is designed so that this information cannot be farmed
(see :mod:`.roles`), not on the assumption that it is hidden.

Textbook guard: the effective per-variable exponents of the power part (scale
exponent plus group contributions) must include at least two values off the
textbook grid (multiples of 1/2, 1/3, 1/4 and 1/5 up to 4, e.g. Kleiber's 3/4,
Dittus-Boelter's 0.8/0.4); generated exponents avoid that grid entirely.  This
is a signature guard, not a comparison against a prior-art library.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .expression import add, c, evaluate, mul, pw, structure_digest, v, validate


class UniverseKind(str, Enum):
    DISCOVERABLE = "discoverable"
    NO_SOLUTION = "no_solution"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INDISTINGUISHABLE = "indistinguishable"
    SPURIOUS_CORRELATE = "spurious_correlate"
    CONFOUNDED = "confounded"


CONTROL_KINDS = frozenset(UniverseKind) - {UniverseKind.DISCOVERABLE}
COVARIATE = "u1"
HIDDEN_SIGMA = 0.4          # log-sd of the latent cause
TEXTBOOK_EXPONENTS = tuple(sorted({round(k / d, 6) for d in (1, 2, 3, 4, 5) for k in range(1, 4 * d + 1)}))
_TEXTBOOK_GAP = 0.02


def _textbook(e: float) -> bool:
    return abs(e) < _TEXTBOOK_GAP or min(abs(abs(e) - t) for t in TEXTBOOK_EXPONENTS) < _TEXTBOOK_GAP


@dataclass(frozen=True)
class Variable:
    name: str
    dimension: tuple[int, ...]
    low: float
    high: float

    def public(self, base_dimensions: tuple[str, ...]) -> dict[str, Any]:
        unit = "*".join(f"{b}^{e}" for b, e in zip(base_dimensions, self.dimension) if e) or "1"
        return {"name": self.name, "unit": unit, "settable": True, "range": [self.low, self.high]}


@dataclass(frozen=True)
class HiddenWorld:
    """Everything the escrow knows.  Never serialized to the proposer."""

    universe_id: str
    kind: UniverseKind
    base_dimensions: tuple[str, ...]
    inputs: tuple[Variable, ...]
    output: str
    output_dimension: tuple[int, ...]
    law: Mapping[str, Any] | None          # the INTERVENTIONAL truth E[y | do(inputs, u1)]; None for NO_SOLUTION
    alternative_law: Mapping[str, Any] | None = None  # INDISTINGUISHABLE: the rival that agrees inside the box
    noise_sigma: float = 0.01
    budget: int = 60
    query_cost: float = 1.0
    covariates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # name -> how it is produced
    assessment_region: Mapping[str, tuple[float, float]] = field(default_factory=dict)   # public
    evaluation_points: tuple[Mapping[str, float], ...] = ()                              # hidden, inside the region
    inbox_points: tuple[Mapping[str, float], ...] = ()                                   # hidden, inside the query box
    tolerance: float = 0.05                    # relative error a law must meet at the evaluation points
    confounder_effect: float = 0.0             # CONFOUNDED: exponent of the latent cause on y

    @property
    def law_structure(self) -> str:
        return "" if self.law is None else structure_digest(self.law)

    def public_card(self) -> dict[str, Any]:
        """What the proposer is told.  No law, seed, evaluation point, tolerance, covariate mechanism or kind."""
        return {"universe_id": self.universe_id, "level": "L5", "base_dimensions": list(self.base_dimensions),
                "inputs": [x.public(self.base_dimensions) for x in self.inputs],
                "observed_covariates": sorted(self.covariates),
                "covariate_units": {name: "1" for name in sorted(self.covariates)},
                "output": {"name": self.output, "unit": "*".join(f"{b}^{e}" for b, e in zip(self.base_dimensions, self.output_dimension) if e) or "1"},
                "assessment_region": {k: [lo, hi] for k, (lo, hi) in sorted(self.assessment_region.items())},
                "query_budget": self.budget, "query_cost": self.query_cost,
                "answers": ["law", "no_law", "insufficient_evidence", "indistinguishable", "confounded"]}


# ---------------------------------------------------------------------------- textbook guard


def known_law_signature(exponents: tuple[float, ...]) -> bool:
    """True when an EFFECTIVE per-variable exponent vector looks like a textbook law: fewer than two of its non-zero
    exponents lie off the textbook grid (multiples of 1/2, 1/3, 1/4, 1/5 up to 4).  Such a universe would test
    retrieval, not discovery (Blindfold L0)."""
    off_grid = [e for e in exponents if not _textbook(e)]
    return len(off_grid) < 2


def _exponent(rng: random.Random, low: float = 0.2, high: float = 2.8) -> float:
    while True:
        e = round(rng.uniform(low, high) * rng.choice((-1, 1)), 3)
        if not _textbook(e):
            return e


def effective_exponents(scale: Mapping[str, int], groups: list[dict[str, int]], exps: tuple[float, ...]) -> dict[str, float]:
    """Per-variable exponent of the power part: scale exponent plus every group's contribution."""
    eff: dict[str, float] = {n: float(k) for n, k in scale.items()}
    for g, e in zip(groups, exps):
        for n, k in g.items():
            eff[n] = eff.get(n, 0.0) + k * e
    return {n: round(e, 6) for n, e in eff.items()}


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


def _box(inputs: tuple[Variable, ...]) -> dict[str, tuple[float, float]]:
    return {x.name: (x.low, x.high) for x in inputs}


def _sample(rng: random.Random, region: Mapping[str, tuple[float, float]]) -> dict[str, float]:
    return {n: math.exp(rng.uniform(math.log(lo), math.log(hi))) for n, (lo, hi) in sorted(region.items())}


def _corners(region: Mapping[str, tuple[float, float]]) -> list[dict[str, float]]:
    names = sorted(region)
    return [dict(zip(names, combo)) for combo in itertools.product(*[region[n] for n in names])]


def _sig(x: float) -> float:
    return float(f"{x:.6g}")


def _extended_region(inputs: tuple[Variable, ...], group: Mapping[str, int], near: float, far: float) -> dict[str, tuple[float, float]]:
    """Beyond the box in the direction that grows ``group``: inputs in the group move out by ``near``..``far`` box spans."""
    reg = {}
    for x in inputs:
        e, span = group.get(x.name, 0), math.log(x.high / x.low)
        if e > 0:
            reg[x.name] = (_sig(x.high * math.exp(near * span)), _sig(x.high * math.exp(far * span)))
        elif e < 0:
            reg[x.name] = (_sig(x.low * math.exp(-far * span)), _sig(x.low * math.exp(-near * span)))
        else:
            reg[x.name] = (x.low, x.high)
    return reg


def _covariate_value(spec: Mapping[str, Any], point: Mapping[str, float], hidden: float | None, rng: random.Random,
                     region: Mapping[str, tuple[float, float]] | None = None) -> float:
    """Passive value when ``hidden`` is given (observation); an independent draw from its marginal otherwise
    (intervention at evaluation: the covariate is decoupled from its driver / cause)."""
    role = spec["role"]
    if role == "spurious":
        if hidden is None:
            lo, hi = (region or {})[spec["driver"]]
            driver = math.exp(rng.uniform(math.log(lo), math.log(hi)))
        else:
            driver = point[spec["driver"]]
        return driver ** spec["exponent"] * math.exp(rng.gauss(0.0, 0.01))
    if role == "confounded":
        if hidden is None:
            return math.exp(rng.gauss(0.0, HIDDEN_SIGMA * spec["c"]))
        return hidden ** spec["c"] * math.exp(rng.gauss(0.0, 0.01))
    return math.exp(rng.gauss(0.0, spec["spread"]))


# ---------------------------------------------------------------------------- generation


#: the generator's identity: part of every journaled world digest, so a generator change is a different universe
GENERATOR_TAG = "forge.blindfold.L5/2"


def generate_universe(seed: str, kind: UniverseKind | str = UniverseKind.DISCOVERABLE, *, n_eval: int = 40) -> HiddenWorld:
    """Generate one hidden world deterministically from ``seed`` (which must stay inside the escrow)."""
    kind = UniverseKind(kind)
    rng = random.Random(f"{GENERATOR_TAG}\n{seed}\n{kind.value}")
    base = tuple(f"D{chr(0x3B1 + i)}" for i in range(rng.choice((2, 3))))      # invented dimensions: Dα, Dβ, Dγ
    prefix = rng.choice(("q", "s", "z", "w"))
    for _attempt in range(200):
        inputs = _random_inputs(rng, base, rng.choice((3, 4)), prefix)
        groups = _dimensionless_groups(inputs, rng, want=2)
        if len(groups) >= 1:
            break
    else:  # pragma: no cover - generation is overwhelmingly successful
        raise RuntimeError("could not generate dimensionless groups")
    for _attempt in range(200):
        j = rng.randrange(len(inputs))
        p = rng.choice((1, 1, 2, -1))
        scale = {inputs[j].name: p}
        exps = tuple(_exponent(rng) for _ in groups)
        if not known_law_signature(tuple(effective_exponents(scale, groups, exps).values())):
            break
    else:  # pragma: no cover
        raise RuntimeError("could not draw a non-textbook exponent signature")
    out_dim = tuple(p * d for d in inputs[j].dimension)
    const = round(10 ** rng.uniform(-1.0, 1.0), 6)
    law: dict | None = mul(c(const), _monomial(scale), *[pw(_monomial(g), e) for g, e in zip(groups, exps)])
    form = rng.choice(("power", "power", "exp", "two_term", "regime"))
    if kind is UniverseKind.INDISTINGUISHABLE:
        form = rng.choice(("power", "exp"))          # keeps law + rival inside the expression size limits
    if form == "exp":
        # a saturating exponential factor exp(-b g / (1 + g/g_ref)): bounded in [exp(-b g_ref), 1] everywhere, so it never
        # underflows in an extended assessment region
        g0 = _monomial(groups[0])
        g_ref = _sig(max(evaluate(g0, pt) for pt in _corners(_box(inputs))))
        b = _sig(rng.uniform(0.3, 2.0) / g_ref)
        law = mul(law, {"exp": mul(c(-b), g0, pw(add(c(1.0), mul(c(1.0 / g_ref), g0)), -1.0))})
    elif form == "two_term":
        e2 = _exponent(rng)
        law = add(law, mul(c(round(const * rng.uniform(0.2, 0.8), 6)), _monomial(scale), pw(_monomial(groups[0]), e2)))
    elif form == "regime":
        # switch on the first group at a threshold inside its observed range; continuous at the switch
        probe = sorted(p_ for p_ in (evaluate(_monomial(groups[0]), _sample(rng, _box(inputs))) for _ in range(64))
                       if math.isfinite(p_) and p_ > 0)
        t = probe[len(probe) // 2]
        e_alt = _exponent(rng)
        k_alt = const * t ** (exps[0] - e_alt)                       # continuity at g1 = t
        other = [pw(_monomial(g), e) for g, e in zip(groups[1:], exps[1:])]
        below = mul(c(const), _monomial(scale), pw(_monomial(groups[0]), exps[0]), *other)
        above = mul(c(k_alt), _monomial(scale), pw(_monomial(groups[0]), e_alt), *other)
        law = {"piecewise": {"if_below": [_monomial(groups[0]), c(t)], "then": below, "else": above}}
    sigma = round(rng.uniform(0.005, 0.02), 4)
    budget = rng.choice((12, 30, 60))
    tol = max(0.03, 4 * sigma)
    box = _box(inputs)
    extended = kind is UniverseKind.INDISTINGUISHABLE or rng.random() < 0.5
    near, far = round(rng.uniform(0.3, 0.5), 3), round(rng.uniform(0.9, 1.3), 3)
    region = _extended_region(inputs, groups[0], near, far) if extended else dict(box)
    eval_rng = random.Random(f"{seed}\neval")
    alternative = None
    confounder_effect = 0.0

    # every universe has exactly one passively observed, dimensionless covariate u1 (no layout tell)
    covariates: dict[str, dict[str, Any]] = {COVARIATE: {"role": "irrelevant", "spread": round(HIDDEN_SIGMA * rng.uniform(0.6, 1.4), 4)}}
    if kind is UniverseKind.NO_SOLUTION:
        # noise drawn like INSUFFICIENT_EVIDENCE's, so the noise level alone does not separate the two controls
        law, sigma = None, round(rng.uniform(0.6, 0.9), 3)
    elif kind is UniverseKind.INSUFFICIENT_EVIDENCE:
        # the budget is drawn from the same set every universe uses, so the card does not reveal the kind;
        # the noise makes the law unrecoverable at that budget
        budget, sigma = rng.choice((12, 30, 60)), round(rng.uniform(0.6, 0.9), 3)
    elif kind is UniverseKind.SPURIOUS_CORRELATE:
        driver = rng.choice(inputs).name
        covariates[COVARIATE] = {"role": "spurious", "driver": driver, "exponent": round(rng.uniform(0.5, 1.5), 3)}
    elif kind is UniverseKind.CONFOUNDED:
        # a latent cause h drives u1 (observed only) AND y; u1 also has a true effect u1^b.  Passive slope: b + a/c.
        b = round(rng.uniform(0.3, 1.4), 3)
        confounder_effect = round(rng.uniform(0.7, 1.6), 3)
        covariates[COVARIATE] = {"role": "confounded", "c": round(rng.uniform(0.6, 1.4), 3)}
        law = mul(law, pw(v(COVARIATE), b))
    elif kind is UniverseKind.INDISTINGUISHABLE:
        law, alternative, region, evaluation = _rival(law, inputs, groups[0], sigma, tol, rng, eval_rng, n_eval, near, far)
    if kind is not UniverseKind.INDISTINGUISHABLE:
        evaluation = tuple(_sample(eval_rng, region) for _ in range(n_eval))
    inbox = tuple(_sample(eval_rng, box) for _ in range(n_eval))
    return HiddenWorld(universe_id=_universe_id(seed, kind), kind=kind,
                       base_dimensions=base, inputs=inputs, output="y", output_dimension=out_dim, law=law,
                       alternative_law=alternative, noise_sigma=sigma, budget=budget, covariates=covariates,
                       assessment_region=region, evaluation_points=evaluation, inbox_points=inbox, tolerance=tol,
                       confounder_effect=confounder_effect)


#: inside the box the rival differs from the law by at most this many noise sigmas (verified on corners + a dense sample)
INBOX_MAX_SIGMAS = 0.5
#: outside, at least this fraction of evaluation points must differ by more than OUTSIDE_TOLERANCES x the tolerance
OUTSIDE_FRACTION, OUTSIDE_TOLERANCES = 0.9, 3.0


def _rival(law: dict, inputs: tuple[Variable, ...], group: Mapping[str, int], sigma: float, tol: float, rng: random.Random,
           eval_rng: random.Random, n_eval: int, near: float, far: float) -> tuple[dict, dict, dict, tuple]:
    """INDISTINGUISHABLE: rival = law * (1 + d * (g / g_max)^m), g a dimensionless group, g_max its in-box maximum (a
    corner: g is monotone in every input).  Dimensionally homogeneous by construction; in-box and out-of-box margins
    are VERIFIED and the region pushed further out until they hold."""
    box = _box(inputs)
    g = _monomial(group)
    grid = _corners(box) + [_sample(rng, box) for _ in range(256)]
    g_max = max(evaluate(g, pt) for pt in grid)
    m = round(rng.uniform(3.0, 4.5), 3)
    d = INBOX_MAX_SIGMAS * sigma
    rival = mul(law, add(c(1.0), mul(c(d / g_max ** m), pw(g, m))))
    validate(rival)

    def rel(pt: Mapping[str, float]) -> float:
        a, b = evaluate(law, pt), evaluate(rival, pt)
        return abs(b - a) / abs(a) if math.isfinite(a) and math.isfinite(b) and a != 0 else float("inf")

    inbox_worst = max(rel(pt) for pt in grid)
    if not inbox_worst <= INBOX_MAX_SIGMAS * sigma * (1 + 1e-9):  # pragma: no cover - holds by construction
        raise RuntimeError("the INDISTINGUISHABLE rival is distinguishable inside the box")
    for _attempt in range(12):
        region = _extended_region(inputs, group, near, far)
        evaluation = tuple(_sample(eval_rng, region) for _ in range(n_eval))
        diffs = [rel(pt) for pt in evaluation]
        if sum(math.isfinite(x) and x > OUTSIDE_TOLERANCES * tol for x in diffs) >= OUTSIDE_FRACTION * n_eval:
            break
        near, far = near * 1.4, far * 1.4
    else:  # pragma: no cover
        raise RuntimeError("could not place the assessment region where the rival is distinguishable")
    if rng.random() < 0.5:                                                   # which one is TRUE is hidden
        law, rival = rival, law
    return law, rival, region, evaluation


def _universe_id(seed: str, kind: UniverseKind) -> str:
    return "bf-" + hashlib.sha256(f"universe-id\n{seed}\n{kind.value}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------- observation (inside the escrow)


def observe(world: HiddenWorld, settings: Mapping[str, float], rng: random.Random) -> dict[str, float]:
    """One noisy observation at the requested settings (every input, inside the box).  The covariate is passive: it is
    returned, never set."""
    known = {x.name: x for x in world.inputs}
    extra = sorted(set(settings) - set(known))
    if extra:
        raise ValueError(f"cannot set {extra}: not settable inputs of this universe")
    point: dict[str, float] = {}
    for name, x in known.items():
        if name not in settings:
            raise ValueError(f"the observation request does not set input {name!r}")
        raw = settings[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or (isinstance(raw, int) and abs(raw) > 1e300):
            raise ValueError(f"{name} is set by a finite number")
        val = float(raw)
        if not (math.isfinite(val) and x.low <= val <= x.high):
            raise ValueError(f"{name}={val} is outside the allowed query range [{x.low}, {x.high}]")
        point[name] = val
    hidden = math.exp(rng.gauss(0.0, HIDDEN_SIGMA))                       # the latent cause (acts only in CONFOUNDED)
    out = dict(point)
    for name, spec in sorted(world.covariates.items()):
        out[name] = _covariate_value(spec, point, hidden, rng)
    if world.law is None:
        y = math.exp(rng.gauss(0.0, world.noise_sigma))           # same noise distribution as INSUFFICIENT_EVIDENCE
    else:
        y = evaluate(world.law, out)
        a = world.confounder_effect
        if a:   # law is E[y | do(.)]; observation carries the latent cause, normalised so its mean effect is 1
            y *= hidden ** a / math.exp(0.5 * (a * HIDDEN_SIGMA) ** 2)
        y *= math.exp(rng.gauss(0.0, world.noise_sigma))
    out[world.output] = y
    return out


def truth_at(world: HiddenWorld, point: Mapping[str, float], rng: random.Random) -> tuple[dict[str, float], float]:
    """Noise-free INTERVENTIONAL truth at an evaluation point: covariates are set independently of their drivers and of
    the latent cause (drawn from their marginals), and the latent cause is averaged out (``world.law`` is E[y|do])."""
    full = dict(point)
    for name, spec in sorted(world.covariates.items()):
        full[name] = _covariate_value(spec, point, None, rng, _box(world.inputs))
    if world.law is None:
        return full, float("nan")
    return full, evaluate(world.law, full)


__all__ = ["CONTROL_KINDS", "COVARIATE", "HIDDEN_SIGMA", "HiddenWorld", "TEXTBOOK_EXPONENTS", "UniverseKind", "Variable",
           "effective_exponents", "generate_universe", "known_law_signature", "observe", "truth_at"]
