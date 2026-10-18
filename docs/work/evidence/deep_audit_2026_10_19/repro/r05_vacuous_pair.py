"""R-05: FDA-05 -- a vacuous INDISTINGUISHABLE pair scored by the real evaluator and the real escrow assessment.

Synthetic world only: no escrow root, pilot world, cases_hard file or formal-grid entry is read.
One input x, query box [1, 2], public assessment region [1, 4], noise sigma 0.01, tolerance 0.05.
Two mutually exclusive truths that agree inside the box within 0.5 sigma:
    T_up   = 3 x^1.5 (1 + 0.005 (x/2)^8)
    T_down = 3 x^1.5 / (1 + 0.005 (x/2)^8)
The vacuous pair uses ONLY an in-box fit L = 3.02 x^1.5 and the public box edge:
    A = L (1 + K s),  B = L / (1 + K s),  s = (x/2)^60,  K = 1e-3
If the same pair is a HIT for both truths, it carries no information about the extrapolation.
"""
import sys
sys.path.insert(0, "D:/forge-main-337519d1")  # benchmarks package root (read-only)

from benchmarks.genesis_lite.evaluator.score import score_universe, CREDIT
from benchmarks.genesis_lite.evaluator.expr import value, check
import benchmarks.genesis_lite.evaluator.score as score_mod
from engcore.blindfold import escrow as esc
from engcore.blindfold.universe import HiddenWorld, UniverseKind, Variable

print("evaluator:", score_mod.__file__)
print("escrow:", esc.__file__)


def c(k): return {"const": k}
def v(n): return {"var": n}
def mul(*a): return {"mul": list(a)}
def add(*a): return {"add": list(a)}
def pw(b, e): return {"pow": [b, c(e)]}


x = v("x")
base_true = mul(c(3.0), pw(x, 1.5))
g8 = pw(mul(x, c(0.5)), 8)
T_up = mul(base_true, add(c(1.0), mul(c(0.005), g8)))
T_down = mul(base_true, pw(add(c(1.0), mul(c(0.005), g8)), -1))

L = mul(c(3.02), pw(x, 1.5))
def pair(K, M):
    grow = add(c(1.0), mul(c(K), pw(mul(x, c(0.5)), M)))
    return [mul(L, grow), mul(L, pw(grow, -1))]

TOL, SIGMA = 0.05, 0.01
eval_pts = [{"x": 1.0 + 3.0 * (i + 0.5) / 60} for i in range(60)]   # inside the public region [1, 4]
inbox_pts = [{"x": 1.0 + (i + 0.5) / 20} for i in range(20)]        # inside the query box [1, 2]


def entry(truth, kind):
    return {"universe_id": f"synthetic-{kind}", "kind": kind, "variables": ["x"], "tolerance": TOL,
            "noise_sigma": SIGMA, "box": {"x": [1.0, 2.0]},
            "evaluation": [(p, value(truth, p)) for p in eval_pts],
            "inbox": [(p, value(truth, p)) for p in inbox_pts]}


def world(truth, alt, kind):
    return HiddenWorld(universe_id="synthetic", kind=kind, base_dimensions=("L",), inputs=(Variable("x", (1,), 1.0, 2.0),),
                       output="y", output_dimension=(1,), law=truth, alternative_law=alt, noise_sigma=SIGMA,
                       assessment_region={"x": (1.0, 4.0)}, evaluation_points=tuple(eval_pts),
                       inbox_points=tuple(inbox_pts), tolerance=TOL)


def run(label, proposal, truth, kind, alt=None):
    e = entry(truth, kind)
    s = score_universe(proposal, e)
    line = f"{label}: kind={kind} outcome={s['outcome']} credit={s['credit']}"
    if proposal.get("answer") == "indistinguishable":
        a = esc._assess_pair(list(proposal["laws"]), list(e["evaluation"]), list(e["inbox"]),
                             world(truth, alt, UniverseKind(kind)))
        line += (f" | escrow hit={a['hit']} mutual_in_box={a['mutual_in_box']} differ_outside={a['differ_fraction_outside']}"
                 f" brackets={a['brackets_truth']} contains={a['contains_truth']}")
    print(line)
    return s


vac = {"answer": "indistinguishable", "laws": pair(1e-3, 60)}
print("vacuous pair admissible variables:", [sorted(check(l)) for l in vac["laws"]])
r1 = run("TRIGGER truth=T_up  ", vac, T_up, "indistinguishable", T_down)
r2 = run("TRIGGER truth=T_down", vac, T_down, "indistinguishable", T_up)
# spread of the vacuous pair at the far edge of the region
far = {"x": 4.0}
print("vacuous pair at x=4: A/B =", value(vac["laws"][0], far) / value(vac["laws"][1], far))

# controls
c1 = run("CONTROL honest refusal  ", {"answer": "insufficient_evidence"}, T_up, "indistinguishable")
c2 = run("CONTROL informative pair", {"answer": "indistinguishable", "laws": [T_up, T_down]}, T_up, "indistinguishable", T_down)
c3 = run("CONTROL in-box disagree ", {"answer": "indistinguishable", "laws": pair(5e-2, 1)}, T_up, "indistinguishable", T_down)
c4 = run("CONTROL discoverable    ", vac, base_true, "discoverable")

reproduced = r1["outcome"] == r2["outcome"] == "indistinguishable_hit" and r1["credit"] == r2["credit"] == 1.0
controls = (c1["credit"] == 0.5 and c2["outcome"] == "indistinguishable_hit" and c3["outcome"] == "indistinguishable_miss"
            and c4["credit"] == CREDIT["discoverable"]["indistinguishable_hit"])
print("VERDICT FDA-05:", "REPRODUCED" if reproduced else "NOT_REPRODUCED/CHECK")
print("CONTROL_OK:", controls)
