"""EXC-4: engcore.mind.grammar -- dimensions, grammar limits, fitting, scoring and selection (development)."""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest

from engcore.blindfold.expression import evaluate, validate
from engcore.mind.grammar import (MAX_DEPTH, MAX_NODES, SHAPES, DimensionRefused, InputDimension, Structure, analyse,
                                  enumerate_structures, fit, log_f, parse_unit, select, to_expression)
from engcore.mind.grammar.grammar import jacobian

BASES = ("L", "T")


def _dims(basis, units):
    return {n: parse_unit(units[n], BASES) for n in basis.inputs}


# ---------------------------------------------------------------------------------------------------- dimensions
def test_parse_unit_reads_declared_powers_and_dimensionless():
    assert parse_unit("L^1*T^-2", BASES) == (1, -2)
    assert parse_unit("L^1*L^2", BASES) == (3, 0)
    assert parse_unit("1", BASES) == (0, 0)


@pytest.mark.parametrize("unit", ["", "  ", "L", "L^x", "M^1", "L^1.5", "L^1/T^1", "L**2"])
def test_parse_unit_refuses_anything_it_cannot_read_exactly(unit):
    with pytest.raises(DimensionRefused):
        parse_unit(unit, BASES)


UNITS = {"a": "L^1", "b": "L^1", "c": "T^-1", "d": "L^1*T^-1"}
INPUTS = [InputDimension("a", UNITS["a"], 0.5, 2.0), InputDimension("b", UNITS["b"], 1.0, 3.0),
          InputDimension("c", UNITS["c"], 0.2, 4.0), InputDimension("d", UNITS["d"], 0.1, 9.0)]


def test_scale_has_the_output_dimension_and_groups_are_dimensionless_and_independent():
    basis = analyse(INPUTS, "L^2*T^-1", BASES)
    dims = _dims(basis, UNITS)
    out = [sum(Fraction(e) * dims[n][i] for n, e in basis.scale.items()) for i in range(2)]
    assert out == [2, -1]
    for g in basis.groups:
        assert [sum(e * dims[n][i] for n, e in g.items()) for i in range(2)] == [0, 0] and g
    assert len(basis.groups) == 2                                  # 4 inputs, rank-2 dimension matrix
    M = np.array([[g.get(n, 0) for n in basis.inputs] for g in basis.groups], dtype=float)
    assert np.linalg.matrix_rank(M) == 2


def test_an_output_no_monomial_can_carry_refuses_never_defaults():
    with pytest.raises(DimensionRefused):
        analyse(INPUTS[:2], "T^1", BASES)                           # inputs are only lengths


def test_no_group_when_inputs_are_dimensionally_independent():
    basis = analyse([InputDimension("a", "L^1", 1, 2), InputDimension("c", "T^1", 1, 2)], "L^1*T^1", BASES)
    assert basis.groups == () and basis.scale == {"a": 1, "c": 1}


def test_renaming_and_reordering_give_the_same_groups_up_to_the_renaming():
    a = analyse(INPUTS, "L^2*T^-1", BASES)
    rename = {"a": "v9", "b": "v3", "c": "v7", "d": "v1"}
    shuffled = [InputDimension(rename[x.name], x.unit.replace("L", "B1").replace("T", "B2"), x.low, x.high)
                for x in reversed(INPUTS)]
    b = analyse(shuffled, "B1^2*B2^-1", ("B1", "B2"))
    assert [{rename[n]: e for n, e in g.items()} for g in a.groups] == [dict(g) for g in b.groups]
    assert {rename[n]: e for n, e in a.scale.items()} == dict(b.scale)


# ---------------------------------------------------------------------------------------------------- grammar
@pytest.mark.parametrize("g", [0, 1, 2, 3])
def test_every_enumerated_structure_respects_the_exc4_limits(g):
    structures, cap_hit = enumerate_structures(g)
    assert not cap_hit and structures
    assert all(s.nodes <= MAX_NODES and s.depth <= MAX_DEPTH and s.shape in SHAPES for s in structures)
    assert len({s.key for s in structures}) == len(structures)
    assert structures == enumerate_structures(g)[0]                 # deterministic
    for s in structures:
        if s.shape in ("exp", "sum_exp"):
            assert s.atoms[-1], "the exp argument is never a bare constant"


def test_zero_groups_leaves_only_the_constant_power_structure():
    assert [s.key for s in enumerate_structures(0)[0]] == ["power[]"]


def test_a_structure_cap_is_reported_not_hidden():
    structures, cap_hit = enumerate_structures(3, max_structures=10)
    assert cap_hit and len(structures) == 10


@pytest.mark.parametrize("shape_index", range(4))
def test_analytic_jacobian_matches_finite_differences(shape_index):
    rng = np.random.default_rng(shape_index)
    L = rng.normal(scale=0.6, size=(25, 2))
    shapes = [s for s in enumerate_structures(2)[0] if s.shape == ("power", "sum", "exp", "sum_exp")[shape_index]]
    for s in shapes[:: max(1, len(shapes) // 5)]:
        th = rng.normal(scale=0.4, size=s.n_params)
        h = 1e-6
        num = np.column_stack([(log_f(s, th + h * e, L) - log_f(s, th - h * e, L)) / (2 * h) for e in np.eye(len(th))])
        assert np.allclose(jacobian(s, th, L), num, atol=1e-5, rtol=1e-4), s.key


# ---------------------------------------------------------------------------------------------------- fit / expression
def _data(n=48, seed=0, noise=0.0):
    rng = np.random.default_rng(seed)
    return rng.normal(scale=0.7, size=(n, 2)), rng.normal(size=n) * noise


def test_power_fit_is_exact_and_exp_fit_recovers_a_noiseless_exp_law():
    L, _ = _data()
    z = 0.4 + 1.3 * L[:, 0]
    f = fit(Structure("power", ((0,),)), L, z)
    assert f.ok and f.rss < 1e-20 and np.allclose(f.theta, [0.4, 1.3])
    z = 0.2 + 0.7 * L[:, 1] - 0.5 * np.exp(0.9 * L[:, 0])
    f = fit(Structure("exp", ((1,), (0,))), L, z)
    assert f.ok and f.rss < 1e-10


def test_regime_fit_finds_the_switch_exactly_on_the_rows():
    L, _ = _data(n=60)
    z = np.where(L[:, 0] < 0.1, 0.5 + 1.0 * L[:, 1], -0.2 + 2.0 * L[:, 1])
    f = fit(Structure("regime", ((1,), (1,)), 0), L, z)
    assert f.ok and f.rss < 1e-20
    below = L[:, 0] < f.theta[-1]
    assert np.array_equal(below, L[:, 0] < 0.1)                    # the same rows on each side as the truth


def test_more_parameters_than_rows_is_not_a_fit():
    L, _ = _data(n=4)
    f = fit(Structure("sum_exp", ((0, 1), (0,), (1,))), L, L[:, 0])
    assert not f.ok and not math.isfinite(f.rss)


def test_the_expression_is_the_fitted_law_in_the_escrow_grammar():
    basis = analyse(INPUTS, "L^2*T^-1", BASES)
    rng = np.random.default_rng(3)
    for s in enumerate_structures(2)[0][::7]:
        th = rng.normal(scale=0.3, size=s.n_params)
        expr = to_expression(s, th, basis)
        assert validate(expr) <= set(basis.inputs)
        pt = {"a": 1.3, "b": 2.1, "c": 0.7, "d": 3.3}
        Lrow = np.array([[sum(e * math.log(pt[n]) for n, e in g.items()) for g in basis.groups]])
        ln_scale = sum(float(e) * math.log(pt[n]) for n, e in basis.scale.items())
        assert math.isclose(math.log(evaluate(expr, pt)), ln_scale + float(log_f(s, th, Lrow)[0]), rel_tol=1e-9,
                            abs_tol=1e-9), s.key


# ---------------------------------------------------------------------------------------------------- selection
def test_selection_follows_its_occam_rule_and_keeps_the_family_size():
    """The rule, not a hoped-for answer: the selected structure has the fewest parameters among the CV-best within
    OCCAM_SLACK; on power-law data it is a power structure carrying the true exponent (a chance extra group may pass the
    slack on one seed, with a negligible exponent)."""
    from engcore.mind.grammar.evidence import OCCAM_SLACK
    structures = enumerate_structures(2)[0]
    for seed in (5, 7, 9):
        L, eps = _data(n=40, seed=seed, noise=0.01)
        z = 0.3 + 1.1 * L[:, 0] + eps
        sel = select(structures, L, z, sigma=0.01, ledger_id=f"test-grammar-select-power-{seed}")
        cv = dict(sel.cv)
        best = min(cv.values())
        eligible = {k for k, m in cv.items() if m <= best * (1 + OCCAM_SLACK)}
        chosen = sel.chosen.structure
        assert chosen.key in eligible
        assert chosen.n_params == min(s.n_params for s in structures if s.key in eligible)
        assert chosen.shape == "power" and 0 in chosen.atoms[0]
        theta = dict(zip(chosen.atoms[0], sel.chosen.theta[1:]))
        assert abs(theta[0] - 1.1) < 0.02 and all(abs(b) < 0.02 for j, b in theta.items() if j != 0)
        assert sel.family_size == len(structures) - sel.unfitted


def test_selection_finds_an_exp_law_outside_the_power_family():
    L, eps = _data(n=40, seed=6, noise=0.005)
    z = 0.2 + 0.8 * L[:, 1] - 0.6 * np.exp(1.0 * L[:, 0]) + eps
    sel = select(enumerate_structures(2)[0], L, z, sigma=0.005, ledger_id="test-grammar-select-exp")
    assert sel.chosen is not None and sel.chosen.structure.shape in ("exp", "sum_exp")
    assert sel.chosen.rss < 0.01


# ---- review 2026-10-30 (forge-scientific-review: CHANGES REQUIRED) ------------------------------------------------------
@pytest.mark.parametrize("sigma", [None, 0.0, -0.1, float("nan"), float("inf"), True])
def test_m1_the_score_needs_a_replicate_noise_estimate_and_never_defaults_it(sigma):
    from engcore.mind.grammar import ScoreRefused
    L, _ = _data(n=20)
    with pytest.raises(ScoreRefused):
        select(enumerate_structures(1)[0], L, L[:, 0], sigma=sigma, ledger_id=f"test-grammar-sigma-{sigma!r}")


def test_m1_the_likelihood_uses_the_given_noise():
    """At sigma 0.02 an extra parameter must buy more than ln n of chi-square; profiled likelihood would differ."""
    from engcore.mind.grammar.evidence import score
    from engcore.mind.grammar.fit import Fit
    small = Fit(Structure("power", ((0,),)), (0.0, 1.0), 40 * 1.0e-4, 40, True)
    big = Fit(Structure("power", ((0, 1),)), (0.0, 1.0, 0.0), 40 * 0.9e-4, 40, True)
    assert score(small, 0.0, 0.02) < score(big, 0.0, 0.02)


def test_m2_a_fit_that_leans_on_the_exp_clip_is_not_a_fit(monkeypatch):
    """The emitted law is unclipped; a solution whose exp argument reaches the clip is refused (guard reachable)."""
    import types
    fitmod = __import__("sys").modules["engcore.mind.grammar.fit"]
    s = Structure("exp", ((0,), (1,)))
    L, _ = _data(n=30)

    def fake(fun, x0, **kw):
        return types.SimpleNamespace(x=np.array([0.0, 1.0, 1e-30, 80.0]), status=1)

    monkeypatch.setattr(fitmod, "least_squares", fake)
    f = fit(s, L, L[:, 0])
    assert not f.ok and "clipped" in f.reason


def test_l1_the_ledger_counts_eliminated_and_the_uncapped_grammar():
    L, eps = _data(n=12, seed=2, noise=0.01)
    z = 0.3 + 1.1 * L[:, 0] + eps
    structures = enumerate_structures(2)[0]
    sel = select(structures, L, z, sigma=0.01, ledger_id="test-grammar-ledger-counts", generated=len(structures) + 5)
    assert sel.unfitted > 0 and sel.family_size == len(structures) - sel.unfitted
    with pytest.raises(ValueError):
        select(structures, L, z, sigma=0.01, ledger_id="test-grammar-ledger-low", generated=1)


def test_l3_duplicate_input_names_refuse():
    with pytest.raises(DimensionRefused):
        analyse([InputDimension("a", "L^1", 1, 2), InputDimension("a", "T^1", 2, 3)], "L^1", BASES)


def test_no_fittable_structure_is_a_refusal_not_a_law():
    L, _ = _data(n=2)
    sel = select(enumerate_structures(1)[0], L, np.array([0.1, 0.2]), sigma=0.01, ledger_id="test-grammar-select-none")
    # with 2 rows only the 1-parameter constant fits, and CV cannot test it: no law is selected
    assert sel.chosen is None
