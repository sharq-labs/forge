"""Genesis-lite v0.3 DRAFT amendment: failing-first reproductions of FDA-05, FDA-06 and O-1, and the proposed repairs.

Every defect is pinned twice. On the frozen v0.2 code it stays (v0.2 is a historical identity and is never repaired in
place), so those tests assert the defect. On the v0.3 draft code it must be gone. Every world and record here is
synthetic: the R-05 / R-06 constructions of the deep audit 2026-10-19
(docs/work/evidence/deep_audit_2026_10_19/repro/). No pilot root secret, pilot world, formal-grid world or cases file is
read; the only pilot artefact used is the v0.2 root that its own summary already revealed, to show it is refused.
"""

from __future__ import annotations

import ast
import hashlib
import itertools
import json
import math
import pathlib
import subprocess
import sys

import pytest

from benchmarks.genesis_lite import analysis as v02_analysis
from benchmarks.genesis_lite import arms, pilot
from benchmarks.genesis_lite import preregistration as v02_prereg
from benchmarks.genesis_lite.evaluator import score as v02_score
from benchmarks.genesis_lite.evaluator.expr import value
from benchmarks.genesis_lite.v0_3 import analysis as v03a
from benchmarks.genesis_lite.v0_3 import environment
from benchmarks.genesis_lite.v0_3 import evaluator as v03e
from benchmarks.genesis_lite.v0_3 import formal
from benchmarks.genesis_lite.v0_3 import preregistration as v03p
from engcore.blindfold.roles import DEFAULT_CREDIT

ROOT = pathlib.Path(__file__).resolve().parents[2]


# ---- FDA-05: the R-05 synthetic world -------------------------------------------------------------------------------
def c(k):
    return {"const": k}


def v(n):
    return {"var": n}


def mul(*a):
    return {"mul": list(a)}


def add(*a):
    return {"add": list(a)}


def pw(b, e):
    return {"pow": [b, c(e)]}


TOL, SIGMA = 0.05, 0.01
X = v("x")
HALF_X = mul(X, c(0.5))
BASE_TRUE = mul(c(3.0), pw(X, 1.5))
T_UP = mul(BASE_TRUE, add(c(1.0), mul(c(0.005), pw(HALF_X, 8))))
T_DOWN = mul(BASE_TRUE, pw(add(c(1.0), mul(c(0.005), pw(HALF_X, 8))), -1))
IN_BOX_FIT = mul(c(3.02), pw(X, 1.5))
EVAL_PTS = [{"x": 1.0 + 3.0 * (i + 0.5) / 60} for i in range(60)]     # the public region [1, 4]
INBOX_PTS = [{"x": 1.0 + (i + 0.5) / 20} for i in range(20)]          # the query box [1, 2]


def vacuous_pair(k=1e-3, m=60):
    """Built ONLY from an in-box fit and the public box edge: A = L (1 + k s), B = L / (1 + k s), s = (x/2)^m."""
    grow = add(c(1.0), mul(c(k), pw(HALF_X, m)))
    return [mul(IN_BOX_FIT, grow), mul(IN_BOX_FIT, pw(grow, -1))]


def narrow_bracket(spread=0.1):
    """Brackets T_UP with a bounded spread: (1 + u) T and T / (1 + u), u ~ 0 in the box and ~ ``spread`` outside it.
    Neither law passes (each is off by ~spread > tol outside the box), so a hit can only come from the bracket."""
    s = pw(HALF_X, 400)
    u = mul(c(spread), s, pw(add(c(1.0), s), -1))
    grow = add(c(1.0), u)
    return [mul(T_UP, grow), mul(T_UP, pw(grow, -1))]


def entry(truth, kind="indistinguishable"):
    return {"universe_id": f"synthetic-{kind}", "kind": kind, "variables": ["x"], "tolerance": TOL, "noise_sigma": SIGMA,
            "box": {"x": [1.0, 2.0]}, "evaluation": [(p, value(truth, p)) for p in EVAL_PTS],
            "inbox": [(p, value(truth, p)) for p in INBOX_PTS]}


def pair(laws):
    return {"answer": "indistinguishable", "laws": laws}


#: a TEST value only: the owner's w (ODC-05b) is not chosen here and is never derived from pilot or formal worlds
TEST_BOUND = v03e.PairBound("tol_multiple", 5.0)


def test_fda05_v0_2_credits_one_vacuous_pair_for_two_mutually_exclusive_truths():
    """Pinned defect (v0.2 is frozen): the R-05 pair earns full credit whichever truth is hidden."""
    laws = vacuous_pair()
    for truth in (T_UP, T_DOWN):
        s = v02_score.score_universe(pair(laws), entry(truth))
        assert (s["outcome"], s["credit"]) == ("indistinguishable_hit", 1.0)
    assert value(laws[0], {"x": 4.0}) / value(laws[1], {"x": 4.0}) > 1e29


@pytest.mark.parametrize("bound", [TEST_BOUND, v03e.PairBound("tol_multiple", 2.0), v03e.PairBound("absolute", 1.0),
                                   v03e.PairBound("absolute", 1e6)])
def test_fda05_v0_3_scores_the_vacuous_pair_a_miss_for_both_truths(bound):
    for truth in (T_UP, T_DOWN):
        s = v03e.score_universe(pair(vacuous_pair()), entry(truth), bound=bound)
        assert (s["outcome"], s["credit"]) == ("indistinguishable_miss", -1.0)


@pytest.mark.parametrize("bound", [v03e.PairBound("tol_multiple", 0.5), TEST_BOUND])
def test_fda05_v0_3_keeps_the_informative_pair_whatever_w_is(bound):
    """The honest pair contains the truth, so it hits through the 'one law passes' route, which the bound never touches
    (the generator's rival ratio grows without limit outside the box, so a bound there would refuse correct answers)."""
    s = v03e.score_universe(pair([T_UP, T_DOWN]), entry(T_UP), bound=bound)
    assert (s["outcome"], s["credit"]) == ("indistinguishable_hit", 1.0)


def test_fda05_v0_3_keeps_the_audit_controls():
    refusal = v03e.score_universe({"answer": "insufficient_evidence"}, entry(T_UP), bound=TEST_BOUND)
    assert refusal["credit"] == 0.5
    disagree = v03e.score_universe(pair(vacuous_pair(k=5e-2, m=1)), entry(T_UP), bound=TEST_BOUND)
    assert disagree["outcome"] == "indistinguishable_miss"
    disc = v03e.score_universe(pair(vacuous_pair()), entry(BASE_TRUE, "discoverable"), bound=TEST_BOUND)
    assert disc["outcome"] == "indistinguishable_miss"
    law = v03e.score_universe({"answer": "law", "law": BASE_TRUE}, entry(BASE_TRUE, "discoverable"), bound=TEST_BOUND)
    assert (law["outcome"], law["credit"]) == ("law_pass", 1.0)


def test_fda05_bracket_credit_survives_inside_the_bound_and_only_there():
    laws, e = narrow_bracket(0.1), entry(T_UP)
    assert all(v02_score.fraction_within(law, e["evaluation"], TOL) < v02_score.PASS_FRACTION for law in laws)
    ratio = max(value(laws[0], p) / value(laws[1], p) for p, _ in e["evaluation"] if p["x"] > 2.0)
    assert 1.2 < ratio < 1.25
    assert v03e.score_universe(pair(laws), e, bound=v03e.PairBound("absolute", 0.25))["outcome"] == "indistinguishable_hit"
    assert v03e.score_universe(pair(laws), e, bound=v03e.PairBound("absolute", 0.15))["outcome"] == "indistinguishable_miss"
    assert v02_score.score_universe(pair(laws), e)["outcome"] == "indistinguishable_hit"


@pytest.mark.parametrize("bad", [None, "OWNER_DECISION_REQUIRED", v03e.PairBound("absolute", 0.0),
                                 v03e.PairBound("absolute", math.inf), v03e.PairBound("absolute", math.nan),
                                 v03e.PairBound("log_width", 1.0)])
def test_fda05_w_is_an_owner_decision_never_a_default(bad):
    assert v03e.PAIR_BOUND == v03e.PairBound("tol_multiple", 3.0)          # D1, owner decision 2026-10-20
    with pytest.raises(v03e.EvaluatorRefused):
        v03e.score_universe(pair(vacuous_pair()), entry(T_UP), bound=bad)
    with pytest.raises(TypeError):
        v03e.score_universe(pair(vacuous_pair()), entry(T_UP))  # type: ignore[call-arg]


def test_fda05_v0_3_fails_closed_against_an_escrow_that_still_credits_the_vacuous_pair():
    """Until the escrow half of FDA-05 lands (certified, OD-3), a v0.3 run on the vacuous pair is an
    EVALUATOR_DISAGREEMENT: invalid, never credited."""
    laws, e = vacuous_pair(), entry(T_UP)
    unrepaired = {"kind": "indistinguishable", "outcome": "indistinguishable_hit", "credit": 1.0,
                  "fractions": [v02_score.fraction_within(law, e["evaluation"], TOL) for law in laws]}
    graded = v03e.evaluate_campaign({e["universe_id"]: pair(laws)}, {"universes": [e]}, {e["universe_id"]: unrepaired},
                                    expected_credit_digest=v03e.CREDIT_DIGEST, bound=TEST_BOUND,
                                    expected_pair_bound=TEST_BOUND.to_dict())
    assert graded["status"] == "EVALUATOR_DISAGREEMENT"
    repaired = dict(unrepaired, outcome="indistinguishable_miss", credit=-1.0)
    graded = v03e.evaluate_campaign({e["universe_id"]: pair(laws)}, {"universes": [e]}, {e["universe_id"]: repaired},
                                    expected_credit_digest=v03e.CREDIT_DIGEST, bound=TEST_BOUND,
                                    expected_pair_bound=TEST_BOUND.to_dict())
    assert graded["status"] == "VALID" and graded["schema"] == v03e.EVALUATOR_SCHEMA
    assert graded["pair_bound"] == {"form": "tol_multiple", "value": 5.0}


def test_fda05_a_caller_chosen_w_is_refused_unless_it_is_the_preregistered_one():
    """Review finding 3: w = 1e31 would restore v0.2's credit for the R-05 pair, so w is bound like the credit table."""
    laws, e = vacuous_pair(), entry(T_UP)
    huge = v03e.PairBound("absolute", 1e31)
    assert v03e.score_universe(pair(laws), e, bound=huge)["outcome"] == "indistinguishable_hit"
    escrow = {e["universe_id"]: {"kind": "indistinguishable", "outcome": "indistinguishable_hit", "credit": 1.0,
                                 "fractions": [v02_score.fraction_within(law, e["evaluation"], TOL) for law in laws]}}
    for expected in (TEST_BOUND.to_dict(), "OWNER_DECISION_REQUIRED", None):
        with pytest.raises(v03e.EvaluatorRefused):
            v03e.evaluate_campaign({e["universe_id"]: pair(laws)}, {"universes": [e]}, escrow,
                                   expected_credit_digest=v03e.CREDIT_DIGEST, bound=huge, expected_pair_bound=expected)


def test_fda05_v0_3_changes_the_rule_not_the_credit_table():
    assert v03e.CREDIT_DIGEST == v02_score.CREDIT_DIGEST
    assert v03e.EVALUATOR_SCHEMA != v02_score.EVALUATOR_SCHEMA


def test_fda05_v0_3_evaluator_imports_nothing_but_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    path = ROOT / "benchmarks" / "genesis_lite" / "v0_3" / "evaluator.py"
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            assert all(a.name.split(".")[0] in stdlib for a in node.names), ast.dump(node)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            assert node.module.split(".")[0] in stdlib, node.module
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 2 and node.module.startswith("evaluator"), node.module   # only the v0.2 evaluator package
    probe = ("import sys; sys.path[:0] = [sys.argv[1]]; import benchmarks.genesis_lite.v0_3.evaluator as e; "
             "print(sorted(m for m in sys.modules if m.split('.')[0] == 'engcore'))")
    out = subprocess.run([sys.executable, "-I", "-c", probe, str(ROOT)], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


# ---- FDA-06: the R-06 synthetic records -----------------------------------------------------------------------------
WS = ("anonymous", "synthetic-0", 0)
REFUSE_ALL = {"no_solution": "no_law", "insufficient_evidence": "insufficient_evidence",
              "indistinguishable": "insufficient_evidence", "confounded": "confounded",
              "discoverable": "no_law", "spurious_correlate": "no_law"}


def r06_record(arm, outcomes, in_family):
    universes = []
    for kind in v02_analysis.KINDS:
        u = {"universe_id": f"{kind}-0", "kind": kind, "outcome": outcomes[kind],
             "credit": float(DEFAULT_CREDIT[kind].get(outcomes[kind], 0.0)), "independent_agrees": True}
        if in_family.get(kind) is not None:
            u["truth_in_searched_family"] = in_family[kind]
        universes.append(u)
    return {"status": "VALID", "arm": arm, "presentation": WS[0], "campaign_id": WS[1], "seed": WS[2], "universes": universes}


def flags(**out_of_family):
    return {k: not out_of_family.get(k, False) for k in v02_analysis.KINDS}


def r06_pair(kind, comparator_outcome, family, cand_outcome="law_pass"):
    cand = dict(REFUSE_ALL, **{kind: cand_outcome})
    base = dict(REFUSE_ALL, **{kind: comparator_outcome})
    return [r06_record("cand", cand, family), r06_record("ref", base, family)]


def test_fda06_v0_2_leaves_an_out_of_family_spurious_world_uncapped():
    """Pinned defect (v0.2 is frozen): R-06 -- the discoverable world is capped, the spurious world is not."""
    rows = [r06_record("cand", dict(REFUSE_ALL, discoverable="law_pass", spurious_correlate="law_pass"),
                       flags(discoverable=True, spurious_correlate=True)),
            r06_record("ref", REFUSE_ALL, flags(discoverable=True, spurious_correlate=True))]
    credits, off = v02_analysis.world_credits(rows), v02_analysis.out_of_family(rows)
    capped = v02_analysis._capped(credits["cand"][WS], credits["ref"][WS], WS, set(), off)
    assert (capped["discoverable"], capped["spurious_correlate"]) == (0.0, 1.0)
    assert sum(capped.values()) - sum(credits["ref"][WS].values()) == 1.0


@pytest.mark.parametrize("kind, comparator_outcome, cand_outcome", [
    ("spurious_correlate", "no_law", "law_pass"), ("confounded", "no_law", "law_pass"),
    ("confounded", "law_fail", "law_pass"), ("discoverable", "no_law", "law_pass"),
    ("indistinguishable", "indistinguishable_miss", "indistinguishable_hit"),
    ("indistinguishable", "insufficient_evidence", "indistinguishable_hit")])
def test_fda06_v0_3_caps_every_law_credit_kind_out_of_family(kind, comparator_outcome, cand_outcome):
    """Review finding 1 adds INDISTINGUISHABLE: with the bracket route bounded (FDA-05), a rival truth outside the
    monomial family is open only to a candidate whose grammar expresses it -- grammar reach, not reasoning."""
    rows = r06_pair(kind, comparator_outcome, flags(**{kind: True}), cand_outcome)
    credits, off = v03a.world_credits(rows), v03a.out_of_family(rows)
    assert off[(WS, kind)] is True
    capped = v03a.capped(credits["cand"][WS], credits["ref"][WS], WS, set(), off)
    assert capped[kind] == credits["ref"][WS][kind]
    assert sum(capped.values()) - sum(credits["ref"][WS].values()) == 0.0


@pytest.mark.parametrize("kind, cand_outcome", [("spurious_correlate", "law_pass"), ("confounded", "law_pass"),
                                                ("discoverable", "law_pass"), ("indistinguishable", "indistinguishable_hit")])
def test_fda06_v0_3_does_not_cap_law_credit_in_family(kind, cand_outcome):
    rows = r06_pair(kind, "no_law", flags(), cand_outcome)
    credits, off = v03a.world_credits(rows), v03a.out_of_family(rows)
    capped = v03a.capped(credits["cand"][WS], credits["ref"][WS], WS, set(), off)
    assert capped[kind] == 1.0 > credits["ref"][WS][kind]


@pytest.mark.parametrize("kind", ["spurious_correlate", "confounded", "discoverable", "indistinguishable"])
def test_fda06_v0_3_refuses_a_law_credit_kind_without_its_family_flag(kind):
    family = flags()
    family[kind] = None
    with pytest.raises(v02_analysis.AnalysisRefused):
        v03a.out_of_family([r06_record("cand", REFUSE_ALL, family)])
    disagree = [r06_record("a", REFUSE_ALL, flags()), r06_record("b", REFUSE_ALL, flags(**{kind: True}))]
    with pytest.raises(v02_analysis.AnalysisRefused):
        v03a.out_of_family(disagree)


def test_fda06_the_capped_kinds_are_derived_from_the_frozen_credit_table():
    from benchmarks.genesis_lite import harness

    derived = tuple(sorted(k for k in v02_analysis.KINDS
                           if any(DEFAULT_CREDIT[k].get(o, 0.0) > 0 for o in ("law_pass", "indistinguishable_hit"))))
    assert tuple(sorted(v03a.CAPPED_KINDS)) == derived
    assert set(derived) == {"confounded", "discoverable", "indistinguishable", "spurious_correlate"}
    assert set(harness.LAW_CREDIT_KINDS) < set(derived)


# ---- O-1: the significance used by Holm ------------------------------------------------------------------------------
MAGNITUDES = {"flat": [1.0, 1.0, 2.0, 1.0, 0.5, 1.5], "skewed_with_zeros": [6.0, 0.5, 0.5, 0.0, 1.0, 0.5, 0.0, 3.5]}


def null_rejection_rate(p_of, magnitudes, alpha):
    """Exact rejection rate under the sign-symmetric null: every sign pattern of the magnitudes is equally likely."""
    patterns = list(itertools.product((1.0, -1.0), repeat=len(magnitudes)))
    return sum(p_of([s * m for s, m in zip(signs, magnitudes)]) <= alpha for signs in patterns) / len(patterns)


def test_o1_v0_2_bootstrap_fraction_is_not_a_valid_p_value():
    """Pinned defect (v0.2 is frozen): under a null where all six signs are coin flips, the v0.2 'p' (2000 resamples,
    Random(0), as preregistered) is <= alpha/5 = 0.01 in 2/64 = 1/32 of the sign patterns and <= 0.05 in 5/64. The sign
    patterns are enumerated exactly; the p-function is the v0.2 bootstrap fraction."""
    p_of = lambda d: v02_analysis.bootstrap_mean_ci(d)[2]  # noqa: E731
    assert null_rejection_rate(p_of, MAGNITUDES["flat"], 0.01) == 2 / 64
    assert null_rejection_rate(p_of, MAGNITUDES["flat"], 0.05) == 5 / 64


@pytest.mark.parametrize("name", sorted(MAGNITUDES))
@pytest.mark.parametrize("alpha", [0.01, 0.0125, 0.05, 0.1])
def test_o1_v0_3_p_is_super_uniform_under_the_sign_symmetric_null(name, alpha):
    rate = null_rejection_rate(lambda d: v03a.sign_flip_p(d)["p"], MAGNITUDES[name], alpha)
    assert rate <= alpha + 1e-12


@pytest.mark.parametrize("diffs", [[1.0, 0.5, -0.5, 2.0], [0.0, 0.0], [3.0, -3.0, 1.5, 1.5, -0.5, 0.0, 2.5],
                                   [-1.0, -2.0, -0.5]])
def test_o1_v0_3_exact_p_equals_brute_force_enumeration(diffs):
    t_obs = sum(diffs)
    patterns = list(itertools.product((1, -1), repeat=len(diffs)))
    brute = sum(sum(s * abs(d) for s, d in zip(signs, diffs)) >= t_obs - 1e-12 for signs in patterns) / len(patterns)
    got = v03a.sign_flip_p(diffs)
    assert got["method"] == "exact" and got["p"] == pytest.approx(brute, abs=1e-15)


def test_o1_v0_3_monte_carlo_path_is_valid_deterministic_and_agrees_with_exact():
    diffs = [((i * 7) % 9 - 3) * 0.5 for i in range(60)]
    exact = v03a.sign_flip_p(diffs)
    mc = v03a.sign_flip_p(diffs, exact_work_limit=0)
    assert exact["method"] == "exact" and mc["method"] == "monte_carlo"
    assert mc == v03a.sign_flip_p(diffs, exact_work_limit=0)
    m = mc["resamples"]
    assert m == v03a.SIGN_FLIP_RESAMPLES and mc["p"] >= 1 / (m + 1)
    assert abs(mc["p"] - exact["p"]) <= 4 * math.sqrt(exact["p"] * (1 - exact["p"]) / m) + 1 / (m + 1)
    big = v03a.sign_flip_p([1.0] * 2400)
    assert big["method"] == "monte_carlo" and big["p"] == 1 / (big["resamples"] + 1)


def test_o1_v0_3_refuses_differences_outside_the_credit_lattice():
    for bad in ([0.3, 1.0], [math.nan], [math.inf]):
        with pytest.raises(v02_analysis.AnalysisRefused):
            v03a.sign_flip_p(bad)


def test_o1_the_claims_monte_carlo_stream_comes_from_the_committed_root(monkeypatch):
    """D2 (owner, 2026-10-20): the stream is keyed by the revealed root, fixed by its commitment, so a different key
    gives a different (still valid) p and no other key is accepted for a claim."""
    diffs = [((i * 7) % 9 - 3) * 0.5 for i in range(60)]
    public = v03a.sign_flip_p(diffs, exact_work_limit=0)
    root = hashlib.sha256(b"test-only formal root for the stream").digest()
    keyed = v03a.sign_flip_p(diffs, exact_work_limit=0, stream=v03a.sign_flip_stream(root, "a" * 64))
    assert keyed["p"] != public["p"] and keyed == v03a.sign_flip_p(diffs, exact_work_limit=0,
                                                                     stream=v03a.sign_flip_stream(root, "a" * 64))
    assert v03a.sign_flip_stream(root, "a" * 64) != v03a.sign_flip_stream(root, "b" * 64)
    from tests.genesis_lite import lift_records as lr

    rows = lr.field(careful=lr.records("careful", lr.CAREFUL)) + lr.records("mind", lr.BETTER)
    stream_problem = "revealed formal root is missing"
    assert any(stream_problem in p for p in v03a.lift_decision(rows, "mind", grid=lr.GRID)["coverage_problems"])
    monkeypatch.setattr(v03a, "_formal_root_commitment", lambda: hashlib.sha256(root).hexdigest())
    good = v03a.lift_decision(rows, "mind", grid=lr.GRID, revealed_root=root)["coverage_problems"]
    assert not any(stream_problem in p for p in good)
    bad = v03a.lift_decision(rows, "mind", grid=lr.GRID, revealed_root=b"x" * 32)["coverage_problems"]
    assert any(stream_problem in p for p in bad)


def test_o1_power_study_vectorised_bootstrap_is_the_same_estimator():
    """ODC-O1b study: the vectorised bootstrap keeps v0.2's estimator (same B, floor 2.5 % order statistic); only the
    resampling stream differs, so the bound agrees within Monte-Carlo error and the mean exactly."""
    from benchmarks.genesis_lite.v0_3 import power_study

    values = [((i * 7) % 11 - 4) * 0.5 for i in range(300)]
    mean, low, frac = power_study.fast_bootstrap_mean_ci(values)
    o_mean, o_low, o_frac = v02_analysis.bootstrap_mean_ci(values)
    assert mean == o_mean and abs(low - o_low) < 0.05 and abs(frac - o_frac) < 0.02
    assert power_study.fast_bootstrap_mean_ci([])[2] == 1.0


def test_o1_power_study_scores_with_the_real_rule_and_restores_it():
    """The study calls lift_decision itself, under the keyed stream of a per-replicate root, and leaves the module as
    it found it (the committed root commitment and the original bootstrap are back afterwards)."""
    from benchmarks.genesis_lite.v0_3 import power_study

    saved = (v03a._formal_root_commitment, v03a.bootstrap_mean_ci, v02_analysis.bootstrap_mean_ci)
    cells = {c["name"]: c for c in power_study.cells()}
    same = power_study.run_cell(cells["controls_unsolved/delta=0.0/rho=1.0"], 1, 7)
    better = power_study.run_cell(cells["controls_unsolved/delta=0.2/rho=1.0"], 1, 7)
    assert same["claim_rate"] == 0.0 and same["mean_pooled_difference"] == 0.0
    assert better["claim_rate"] == 1.0 and better["mean_pooled_difference"] > 0
    assert not any("revealed formal root" in p for p in better["coverage_problems_seen"])     # the keyed stream was used
    assert (v03a._formal_root_commitment, v03a.bootstrap_mean_ci, v02_analysis.bootstrap_mean_ci) == saved


def test_o1_lift_decision_passes_the_keyed_stream_to_the_monte_carlo_p(monkeypatch):
    """Review I-6: the committed root's stream must reach sign_flip_p. With the Monte-Carlo path forced, every p in the
    family is computed on HMAC(root, identity); two roots give two pooled p values, and no root gives the public one."""
    from tests.genesis_lite import lift_records as lr

    original, seen = v03a.sign_flip_p, []

    def forced(diffs, **kw):
        seen.append(kw.get("stream", v03a.SIGN_FLIP_STREAM))
        return original(diffs, exact_work_limit=0, **{k: v for k, v in kw.items() if k != "exact_work_limit"})

    monkeypatch.setattr(v03a, "sign_flip_p", forced)
    mixed = dict(lr.CAREFUL, discoverable=0.4, no_solution=0.7)      # signed differences: p is mid-range, not 1/(M+1)
    rows = lr.field(careful=lr.records("careful", lr.CAREFUL)) + lr.records("mind", mixed)
    identity = v03p.identity_problems()[1]
    ps = {}
    for tag in (b"root one", b"root two"):
        root = hashlib.sha256(tag).digest()
        monkeypatch.setattr(v03a, "_formal_root_commitment", lambda r=root: hashlib.sha256(r).hexdigest())
        seen.clear()
        out = v03a.lift_decision(rows, "mind", grid=lr.GRID, revealed_root=root)
        assert out["primary"]["pooled"]["p_method"] == "monte_carlo"
        assert seen and set(seen) == {v03a.sign_flip_stream(root, identity)}
        ps[tag] = out["primary"]["pooled"]["p"]
    seen.clear()
    public = v03a.lift_decision(rows, "mind", grid=lr.GRID)["primary"]["pooled"]["p"]
    assert set(seen) == {v03a.SIGN_FLIP_STREAM} and len({*ps.values(), public}) == 3


def test_o1_a_revealed_root_that_is_not_bytes_is_refused():
    from tests.genesis_lite import lift_records as lr

    rows = lr.field(careful=lr.records("careful", lr.CAREFUL)) + lr.records("mind", lr.BETTER)
    with pytest.raises(v03a.AnalysisRefused, match="must be bytes"):
        v03a.lift_decision(rows, "mind", grid=lr.GRID, revealed_root="00" * 32)


def test_o1_holm_is_unchanged():
    p = {"pooled": 0.004, "anonymous": 0.03, "renamed": 0.011, "paraphrased": 0.2, "trap": 0.012}
    assert v03a.holm(p, 0.05) == {"pooled": True, "renamed": True, "trap": True, "anonymous": False,
                                  "paraphrased": False}
    assert v03a.holm({**p, "pooled": 0.011}, 0.05)["pooled"] is False      # 0.011 > 0.05 / 5 stops the step-down


def test_o1_v0_3_lift_decision_uses_sign_flip_p_and_claims_nothing_while_draft():
    from tests.genesis_lite import lift_records as lr

    rows = lr.field(careful=lr.records("careful", lr.CAREFUL)) + lr.records("mind", lr.BETTER)
    out = v03a.lift_decision(rows, "mind", grid=lr.GRID)
    assert out["lift_claimed"] is False
    assert any("DRAFT" in p for p in out["coverage_problems"])
    assert any("formal root commitment" in p for p in out["coverage_problems"])     # D-09: pilot-style records
    for part in v02_analysis.PRIMARY_FAMILY:
        assert out["primary"][part]["p_method"] in ("exact", "monte_carlo")
        assert 0 < out["primary"][part]["p"] <= 1
    assert out["significance"] == "paired sign-flip randomisation (one-sided); bootstrap for the lower bound only"


# ---- identity: v0.3 is a new DRAFT identity; v0 / v0.1 / v0.2 stay byte for byte ------------------------------------
V0_2_SHA256 = "878e6812a825fc85dc1f181b323d9a1c7a630b55e346612ca73d6a5b4e696b64"


def test_earlier_identities_are_untouched_and_v0_2_stays_the_active_one():
    for path, sha in ((v02_prereg.V0_PREREG_PATH, v02_prereg.V0_PREREG_SHA256),
                      (v02_prereg.V0_1_PREREG_PATH, v02_prereg.V0_1_PREREG_SHA256), (v02_prereg.PREREG_PATH, V0_2_SHA256)):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        assert path.with_suffix(".sha256").read_bytes().strip().decode() == sha
    assert v02_prereg.PREREG_PATH.name == "genesis_lite_v0_2.json"
    assert pilot.prereg_matches_code() == (True, V0_2_SHA256)


def test_v0_3_is_a_draft_identity_that_amends_v0_2():
    doc = json.loads(v03p.PREREG_PATH.read_bytes())
    assert doc["status"] == "DRAFT" and doc["status"] != "FREEZE_READY"
    assert doc["benchmark_id"] == "genesis_lite.blindfold_l5.v0_3"
    assert doc["amends"]["preregistration_sha256"] == V0_2_SHA256
    assert v03p.PREREG_PATH != v02_prereg.PREREG_PATH


def test_v0_3_draft_is_exactly_what_the_code_rebuilds():
    committed = v03p.PREREG_PATH.read_bytes()
    assert v03p.canonical(v03p.build()) == committed
    assert v03p.PREREG_PATH.with_suffix(".sha256").read_bytes().strip().decode() == hashlib.sha256(committed).hexdigest()
    assert b"\r\n" not in committed


def test_v0_3_draft_names_every_open_owner_decision():
    doc = json.loads(v03p.PREREG_PATH.read_bytes())
    assert set(doc["owner_decisions_open"]) == {"D4-identity-freeze", "D5-deployment", "D6-evaluator",
                                                 "D7-budget-and-machine", "OD-3",
                                                 "D3b-cap-form-and-noninferiority"}
    assert set(doc["owner_decisions_taken"]) == {"D1-scoring", "D2-significance", "D3-baselines-and-tells"}
    covered = " ".join(list(doc["owner_decisions_open"].values()) + list(doc["owner_decisions_taken"].values()))
    for older in ("ODC-05a", "ODC-05b", "ODC-05c", "ODC-05d", "ODC-06a", "ODC-06b", "ODC-O1a", "ODC-O1b", "OD-19",
                  "OD-20", "OD-8", "OD-18"):
        assert older in covered, older                                     # every scattered question folds into one
    assert doc["evaluator"]["pair_bound"] == {"form": "tol_multiple", "value": 3.0}
    assert doc["formal"]["root_commitment_sha256"] == "OWNER_DECISION_REQUIRED"
    assert doc["formal"]["environment_manifest_sha256"] == "OWNER_DECISION_REQUIRED"


# ---- P-4: the formal-tier driver -------------------------------------------------------------------------------------
FRESH_ROOT = hashlib.sha256(b"test-only formal root; never a real one").digest()
REVEALED_V0_2_ROOT = bytes.fromhex(json.loads(
    (ROOT / "benchmarks/genesis_lite/pilot_results/v0_2-2026-10-14/summary.json").read_bytes())["pilot_root_revealed_hex"])
MANIFEST = {"schema": environment.MANIFEST_SCHEMA, "python": {"implementation": "cpython", "version": "3.12.3"},
            "distributions": {"numpy": "2.5.2"}}


def frozen_doc(root=FRESH_ROOT, manifest=MANIFEST):
    """A stand-in for a FROZEN v0.3 preregistration (tests only; the committed one is DRAFT)."""
    return {"status": "FROZEN", "benchmark_id": "genesis_lite.blindfold_l5.v0_3",
            "arms": {n: {} for n in formal.registered_arms()},
            "formal": {"root_commitment_sha256": hashlib.sha256(root).hexdigest(), "candidate": formal.NO_CANDIDATE,
                       "environment_manifest_sha256": environment.manifest_digest(manifest)}}


@pytest.fixture
def stand_in_accepted(monkeypatch):
    """Orchestration tests use a hand-written FROZEN stand-in, which the committed-identity check (correctly) refuses."""
    monkeypatch.setattr(formal, "committed_identity_problems", lambda doc: [])


@pytest.fixture
def registry(tmp_path):
    from benchmarks.genesis_lite.v0_3.registry import AttemptRegistry

    return AttemptRegistry(tmp_path / "attempt-registry")


def test_p4_a_document_that_merely_says_frozen_is_refused():
    """Review finding 4: the driver accepts only the committed v0.3 bytes that the code rebuilds."""
    assert formal.preflight(frozen_doc(), FRESH_ROOT, MANIFEST) == []
    assert formal.committed_identity_problems(frozen_doc()) == [
        "the preregistration given is not the committed genesis_lite_v0_3.json"]
    with pytest.raises(formal.FormalRefused, match="not the committed"):
        formal.run_formal(FRESH_ROOT, frozen_doc(), manifest=MANIFEST, runner=lambda *a, **k: {}, sink=lambda r: None,
                          publish=lambda e: None,
                          registry=None)
    committed = json.loads(v03p.PREREG_PATH.read_bytes())
    assert formal.committed_identity_problems(committed) == []      # the draft IS the committed document (then refused
    assert formal.preflight(committed, FRESH_ROOT, MANIFEST)         # as DRAFT by preflight)


def test_p4_the_driver_refuses_the_committed_draft():
    doc = json.loads(v03p.PREREG_PATH.read_bytes())
    problems = formal.preflight(doc, FRESH_ROOT, MANIFEST)
    assert any("DRAFT" in p for p in problems) and any("OWNER_DECISION_REQUIRED" in p for p in problems)
    with pytest.raises(formal.FormalRefused):
        formal.run_formal(FRESH_ROOT, doc, manifest=MANIFEST, runner=lambda *a, **k: {}, sink=lambda r: None,
                          publish=lambda e: None,
                          registry=None)


def test_p4_the_driver_refuses_a_retired_or_uncommitted_root_and_a_changed_environment():
    assert hashlib.sha256(REVEALED_V0_2_ROOT).hexdigest() in formal.retired_root_commitments()
    assert any("retired" in p for p in formal.preflight(frozen_doc(REVEALED_V0_2_ROOT), REVEALED_V0_2_ROOT, MANIFEST))
    assert any("commitment" in p for p in formal.preflight(frozen_doc(), b"\x00" * 32, MANIFEST))
    changed = {**MANIFEST, "distributions": {"numpy": "2.5.3"}}
    assert any("environment" in p for p in formal.preflight(frozen_doc(), FRESH_ROOT, changed))
    assert formal.preflight(frozen_doc(), FRESH_ROOT, MANIFEST) == []


def test_p4_the_driver_runs_every_arm_once_on_every_formal_world_set_and_releases_world_sets_whole(stand_in_accepted,
                                                                                                    registry):
    doc = frozen_doc()
    identity = formal.identity(doc)
    events, sunk = [], []

    def runner(arm, *, master_seed, campaign_id, presentation, seed):
        events.append(("run", arm, (presentation, campaign_id, seed)))
        return {"arm": arm, "status": "VALID", "presentation": presentation, "campaign_id": campaign_id, "seed": seed,
                "prereg_sha256": identity, "universes": [], "master": master_seed.hex()}

    def sink(rec):
        events.append(("sink", rec["arm"], (rec["presentation"], rec["campaign_id"], rec["seed"])))
        sunk.append(rec)

    published = []
    summary = formal.run_formal(FRESH_ROOT, doc, manifest=MANIFEST, runner=runner, sink=sink, registry=registry,
                                publish=lambda e: (published.append(e), events.append(("publish", None, None))))
    assert events[0][0] == "publish" and published[0]["attempt_sha256"] == summary["attempt_sha256"]
    events.pop(0)
    assert summary["registry_head"] == registry.head() and len(registry.entries()) == 1
    n_arms = len(formal.registered_arms())
    assert summary["world_sets"] == len(v02_analysis.FORMAL_GRID) == 2400
    assert len(sunk) == 2400 * n_arms
    assert {(r["arm"], (r["presentation"], r["campaign_id"], r["seed"])) for r in sunk} == {
        (a, ws) for a in formal.registered_arms() for ws in v02_analysis.FORMAL_GRID}
    first_sink, last_run = {}, {}
    for i, (what, _arm, ws) in enumerate(events):
        if what == "run":
            last_run[ws] = i
        else:
            first_sink.setdefault(ws, i)
    assert all(last_run[ws] < first_sink[ws] for ws in v02_analysis.FORMAL_GRID)
    assert all(r["tier"] == "formal" and r["root_commitment_sha256"] == hashlib.sha256(FRESH_ROOT).hexdigest()
               for r in sunk)
    assert len({r["master"] for r in sunk}) == 2400


def test_p4_a_record_under_another_identity_is_invalid_not_relabelled(stand_in_accepted, registry):
    doc = frozen_doc()
    sunk = []

    def runner(arm, *, master_seed, campaign_id, presentation, seed):
        return {"arm": arm, "status": "VALID", "presentation": presentation, "campaign_id": campaign_id, "seed": seed,
                "prereg_sha256": V0_2_SHA256, "universes": [], "reasons": []}

    formal.run_formal(FRESH_ROOT, doc, manifest=MANIFEST, runner=runner, sink=sunk.append, registry=registry,
                      publish=lambda e: None)
    assert all(r["status"] == "INVALID_BENCHMARK" and r["prereg_sha256"] == V0_2_SHA256 for r in sunk)


def test_p4_formal_masters_never_coincide_with_pilot_masters():
    for i, p, s in ((0, "anonymous", 0), (3, "trap", 7)):
        formal_master = formal.master_for(FRESH_ROOT, "a" * 64, "0" * 32, p, f"gl-formal-{i}", s)
        assert formal_master != pilot.master_for(FRESH_ROOT, i, p, s)
        assert formal_master != formal.master_for(FRESH_ROOT, "a" * 64, "1" * 32, p, f"gl-formal-{i}", s)  # nonce
        assert formal_master != formal.master_for(FRESH_ROOT, "b" * 64, "0" * 32, p, f"gl-formal-{i}", s)  # identity


def test_p4_the_root_never_travels_on_the_command_line():
    options = {opt for action in formal.parser()._actions for opt in action.option_strings}
    assert not any("root" in o for o in options)


def test_p4_the_production_runner_is_the_v0_3_harness_and_refuses_a_draft_identity():
    with pytest.raises(formal.FormalRefused, match="FROZEN"):
        formal.harness_runner(json.loads(v03p.PREREG_PATH.read_bytes()))
    assert not hasattr(formal, "unbound_runner")


def test_p4_the_sealed_log_is_append_only_and_hash_chained(tmp_path):
    path = tmp_path / "runs.jsonl"
    log = formal.SealedLog(path)
    log({"arm": "a", "n": 1})
    log({"arm": "b", "n": 2})
    with pytest.raises(FileExistsError):
        formal.SealedLog(path)
    assert formal.verify_log(path) == 2
    lines = path.read_bytes().splitlines()
    path.write_bytes(lines[0].replace(b'"n":1', b'"n":9') + b"\n" + lines[1] + b"\n")
    with pytest.raises(formal.FormalRefused):
        formal.verify_log(path)


# ---- P-5: the environment manifest -----------------------------------------------------------------------------------
def test_p5_the_manifest_names_the_interpreter_and_every_imported_distribution():
    m = environment.build_manifest()
    assert m["schema"] == environment.MANIFEST_SCHEMA
    assert m["python"]["version"] == ".".join(map(str, sys.version_info[:3]))
    assert "numpy" in m["distributions"] and m["installed"]["numpy"] == m["distributions"]["numpy"]
    assert "pytest" in m["installed"]                 # every installed distribution, not only the benchmark's imports
    assert all(name.split(".")[0] not in sys.stdlib_module_names for name in m["unmapped_modules"])
    assert environment.manifest_digest(m) == environment.manifest_digest(json.loads(json.dumps(m)))
    changed = json.loads(json.dumps(m))
    changed["distributions"]["numpy"] = "0.0.0"
    assert environment.compare(m, changed) == ["distributions.numpy: " + m["distributions"]["numpy"] + " != 0.0.0"]
    assert environment.compare(m, m) == []
