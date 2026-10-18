"""R-04: FDA-04 (lattice LHS anti-correlation) and FDA-14 (realised interval mass) on the real FORGE functions."""
import statistics
import engcore
from engcore.mcp.probabilistic_uq import build_deterministic_samples, predictive_intervals
from engcore.scientific.units.quantity import Quantity

print("engcore:", engcore.__file__)


def uniform_inputs(k):
    return [{"path": f"x{c}", "distribution": "uniform", "lower": "0 m", "upper": "1 m"} for c in range(k)]


def mags(samples, path):
    return [Quantity.parse(s[path]).magnitude_in("m") for s in samples]


def interval_for(values, mass=0.95):
    answers = [{"verdict": "supported", "results": [{"subject": "y", "values": {"Y": {"magnitude": v, "units": "m"}}}]}
               for v in values]
    out = predictive_intervals(answers, credible_mass=mass)
    (iv,) = out["intervals"]
    return out["status"], iv["lower"]["magnitude"], iv["upper"]["magnitude"], iv["standard_uncertainty"]["magnitude"]


def case(n, k, a, b, label):
    s = build_deterministic_samples(uniform_inputs(k), sample_count=n, dependence="independent")
    y = [p + q for p, q in zip(mags(s, f"x{a}"), mags(s, f"x{b}"))]
    status, lo, hi, sd = interval_for(y)
    print(f"{label}: n={n} k={k} Y=x{a}+x{b} distinct_Y={len(set(round(v, 12) for v in y))} "
          f"status={status} lower={lo!r} upper={hi!r} width={hi - lo!r} sd={sd!r}")
    return hi - lo, sd


# FDA-04 trigger cases
w1, sd1 = case(4, 3, 1, 2, "TRIGGER-A")
w2, sd2 = case(32, 17, 15, 16, "TRIGGER-B")
# negative control: two inputs at default n=32 must give nonzero spread
w3, sd3 = case(32, 2, 0, 1, "CONTROL")

# FDA-14: monotone single input Y = x0, uniform[0,1] -> covered input mass = upper - lower
for n in (4, 32):
    s = build_deterministic_samples(uniform_inputs(1), sample_count=n, dependence="independent")
    status, lo, hi, sd = interval_for(mags(s, "x0"))
    print(f"MASS: n={n} stated=0.95 realised={hi - lo!r} expected_formula={0.95 - 0.95 / n!r}")

print("VERDICT FDA-04:", "REPRODUCED" if (w1 == 0 and sd1 == 0 and w2 == 0 and sd2 == 0 and w3 > 0 and sd3 > 0) else "NOT_REPRODUCED/CHECK")
print("CONTROL_OK:", w3 > 0 and sd3 > 0)
