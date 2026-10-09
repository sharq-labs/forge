"""Seeded flaw suite for the Scientific Red Team: claims with a KNOWN planted flaw, plus clean controls and traps.

Every case is a cantilever-beam serviceability claim ("tip deflection, or deflection/span, stays within a limit over the
declared envelope") built from closed-form beam physics, so the ground truth of each case is known exactly:

* Euler-Bernoulli (family ``eb``): ``delta = F L^3 / (3 E I)``, ``I = b h^3 / 12``;
* Timoshenko (family ``timoshenko``): Euler-Bernoulli plus shear ``F L / (kappa G A)``, ``G = E / (2 (1 + nu))``;
* a discretized route (family ``fe``) with ``n`` elements: Timoshenko times ``(1 - 0.8 / n^2)`` (a coarse mesh is stiff).

The routes are REFERENCE ANALYTIC FORMS for a benchmark of the red-team machinery, not qualified solvers; the suite
measures whether the red team finds planted flaws, not anything about real beams.

Flawed cases (the claim is false, or unverified, in a known way) and what detection means:

=================================  ==================================================  ==================
case                               planted flaw                                        detected when
=================================  ==================================================  ==================
wrong_bc                           simply-supported formula used for a cantilever      FALSIFIED
material_outside_applicability     room-temperature modulus used up to 400 C          FALSIFIED
under_resolved_mesh                claim made on a 2-element mesh                      FALSIFIED
incorrect_model_family             Euler-Bernoulli for a short, deep beam (shear)      FALSIFIED
hidden_parameter_sensitivity       thickness tolerance never varied (delta ~ 1/h^3)    FALSIFIED
unsupported_extrapolation          a surrogate fitted on L<=1 m claimed to 1.3 m       FALSIFIED (EDGE)
insufficient_convergence           the claim's solver does not converge at high load   UNKNOWN (non-conv.)
interior_only_violation            an amplified load band away from every corner       FALSIFIED (interior)
=================================  ==================================================  ==================

A KNOWN BLIND SPOT, ``flaw_outside_attack_space`` (the thickness flaw with ``h`` left out of the attack space), is
expected to SURVIVE: the red team cannot find what its space does not contain, which is why SURVIVED is always stated
with its region, budget and method.  It is reported, never counted as a detection.  Because the suite's flaws are
planted INSIDE the attack spaces by its author, its detection rate measures the red-team machinery (replay,
independent confirmation, classification), not the ability to discover flaws nobody anticipated.

Controls (the claim is true in the declared region): ``clean_safe`` (SURVIVED), ``artifact_trap`` (a coarse route shows a
spurious violation that its refined route removes: SURVIVED, never FALSIFIED), ``implausible_trap`` (violated only beyond
plausibility: SURVIVED), ``flaky_trap`` (a non-reproducible violation: UNKNOWN, never FALSIFIED), ``model_form_trap`` (two
equal-fidelity families disagree: UNKNOWN).  A FALSIFIED control is a false alarm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .redteam import (
    AttackDimension, AttackKind, AttackPlan, AttackSpace, ClaimSubject, CounterexampleClass, EnvelopeOutcome, Route, RouteResult,
    Sense, TrustEnvelope, run_red_team,
)

E0 = 200e9          # Pa, steel at 20 C
NU = 0.3
KAPPA = 5.0 / 6.0


def _eb(F: float, L: float, E: float, b: float, h: float) -> float:
    return F * L ** 3 / (3.0 * E * (b * h ** 3 / 12.0))


def _timo(F: float, L: float, E: float, b: float, h: float) -> float:
    return _eb(F, L, E, b, h) + F * L / (KAPPA * (E / (2.0 * (1.0 + NU))) * b * h)


def _fe(F: float, L: float, E: float, b: float, h: float, n: int) -> float:
    return _timo(F, L, E, b, h) * (1.0 - 0.8 / n ** 2)


def _e_of_t(T: float) -> float:
    return E0 * (1.0 - 0.0006 * (T - 20.0))


def _route(route_id: str, family: str, fidelity: int, fn: Callable[[Mapping[str, float]], float],
           converged: Callable[[Mapping[str, float]], bool] | None = None) -> Route:
    def evaluate(p: Mapping[str, float]) -> RouteResult:
        return RouteResult(float(fn(p)), True if converged is None else bool(converged(p)))
    return Route(route_id, family, fidelity, evaluate)


def _dim(name: str, low: float, high: float, unit: str, source: str, kind: AttackKind = AttackKind.OPERATING_POINT,
         **kw: Any) -> AttackDimension:
    return AttackDimension(name, kind, source, low=low, high=high, unit=unit, **kw)


def _routes_dim(choices: tuple[str, ...], kind: AttackKind, source: str) -> AttackDimension:
    return AttackDimension("route", kind, source, choices=choices)


LOAD = _dim("F", 1000.0, 8000.0, "N", "load spec LS-1 (tip load envelope)")
SPAN = _dim("L", 0.5, 1.0, "m", "installation drawing D-7 (span envelope)")
B, H = 0.05, 0.1


@dataclass(frozen=True)
class SeededCase:
    name: str
    flawed: bool
    expected: EnvelopeOutcome
    subject: ClaimSubject
    space: AttackSpace
    plan_kwargs: Mapping[str, Any]
    note: str
    blind_spot: bool = False            # a real flaw OUTSIDE the attack space: a SURVIVED here is the documented limit

    def run(self, budget: int = 600) -> TrustEnvelope:
        plan = AttackPlan(self.space.digest, budget, f"suite:{self.name}", **dict(self.plan_kwargs))
        return run_red_team(self.subject, self.space, plan)


def _case(name: str, flawed: bool, expected: EnvelopeOutcome, threshold: float, routes: tuple[Route, ...], claim_route: str,
          dims: tuple[AttackDimension, ...], note: str, *, observable: str = "tip_deflection", unit: str = "m",
          plan_kwargs: Mapping[str, Any] | None = None, blind_spot: bool = False) -> SeededCase:
    subject = ClaimSubject(name, observable, unit, Sense.AT_MOST, threshold, routes, claim_route)
    return SeededCase(name, flawed, expected, subject, AttackSpace(name, dims), dict(plan_kwargs or {}), note, blind_spot)


def seeded_cases() -> tuple[SeededCase, ...]:
    F_hi, L_hi = LOAD.high, SPAN.high
    cases = []

    # 1. wrong boundary condition: the claim used the simply-supported midspan formula (F L^3 / 48 E I)
    ss = _route("ss_formula", "eb_simply_supported", 1, lambda p: p["F"] * p["L"] ** 3 / (48 * E0 * B * H ** 3 / 12))
    cases.append(_case("wrong_bc", True, EnvelopeOutcome.FALSIFIED, 1.0e-3,
                       (ss, _route("cantilever_eb", "eb", 1, lambda p: _eb(p["F"], p["L"], E0, B, H)),
                        _route("cantilever_fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))), "ss_formula",
                       (LOAD, SPAN, _routes_dim(("ss_formula", "cantilever_eb", "cantilever_fe"), AttackKind.BOUNDARY_CONDITION,
                                                "support drawing: clamped root")),
                       "the claim's route models the wrong support"))

    # 2. material outside applicability: E fixed at its 20 C value while the envelope reaches 400 C
    temp = _dim("T", 20.0, 400.0, "degC", "operating environment spec ENV-3", AttackKind.ENVIRONMENT)
    lim2 = 1.15 * _eb(F_hi, L_hi, E0, B, H)
    cases.append(_case("material_outside_applicability", True, EnvelopeOutcome.FALSIFIED, lim2,
                       (_route("eb_E20", "eb", 1, lambda p: _eb(p["F"], p["L"], E0, B, H)),
                        _route("eb_ET", "eb", 2, lambda p: _eb(p["F"], p["L"], _e_of_t(p["T"]), B, H)),
                        _route("fe_ET", "fe", 3, lambda p: _fe(p["F"], p["L"], _e_of_t(p["T"]), B, H, 64))), "eb_E20",
                       (LOAD, SPAN, temp, _routes_dim(("eb_E20", "eb_ET", "fe_ET"), AttackKind.MATERIAL_ASSUMPTION,
                                                      "material data sheet MDS-12 (E(T))")),
                       "a room-temperature material model applied outside its temperature range"))

    # 3. under-resolved mesh: the claim's FE run used two elements (20 % too stiff)
    lim3 = 1.1 * _fe(F_hi, L_hi, E0, B, H, 2)
    cases.append(_case("under_resolved_mesh", True, EnvelopeOutcome.FALSIFIED, lim3,
                       (_route("fe_n2", "fe", 1, lambda p: _fe(p["F"], p["L"], E0, B, H, 2)),
                        _route("fe_n64", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64)),
                        _route("timoshenko", "timoshenko", 2, lambda p: _timo(p["F"], p["L"], E0, B, H))), "fe_n2",
                       (LOAD, SPAN, _routes_dim(("fe_n2", "fe_n64", "timoshenko"), AttackKind.DISCRETIZATION, "mesh study MS-2")),
                       "the claim rests on an unconverged discretization"))

    # 4. incorrect model family: Euler-Bernoulli for a short deep beam (h = 0.3 m, L/h ~ 1.3-2.7): shear matters
    b4, h4 = 0.1, 0.3
    span4 = _dim("L", 0.4, 0.8, "m", "bracket drawing D-9")
    load4 = _dim("F", 5.0e4, 2.5e5, "N", "load spec LS-4")
    cases.append(_case("incorrect_model_family", True, EnvelopeOutcome.FALSIFIED, 1.0 / 800.0,
                       (_route("eb", "eb", 1, lambda p: _eb(p["F"], p["L"], E0, b4, h4) / p["L"]),
                        _route("timoshenko", "timoshenko", 2, lambda p: _timo(p["F"], p["L"], E0, b4, h4) / p["L"]),
                        _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, b4, h4, 64) / p["L"])), "eb",
                       (load4, span4, _routes_dim(("eb", "timoshenko", "fe"), AttackKind.MODEL_FORM, "beam theory selection note")),
                       "slender-beam theory applied to a deep beam", observable="deflection_over_span", unit="1"))

    # 5. hidden parameter sensitivity: thickness tolerance +-5 % never varied; delta ~ 1/h^3 (+17 % at h_min)
    thick = _dim("h", 0.095, 0.105, "m", "drawing tolerance h = 100 +- 5 mm", AttackKind.INPUT_PARAMETER)
    lim5 = 1.08 * _eb(F_hi, L_hi, E0, B, H)
    cases.append(_case("hidden_parameter_sensitivity", True, EnvelopeOutcome.FALSIFIED, lim5,
                       (_route("eb", "eb", 1, lambda p: _eb(p["F"], p["L"], E0, B, p["h"])),
                        _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, p["h"], 64))), "eb",
                       (LOAD, SPAN, thick), "a parameter the claim depends on strongly was never varied"))

    # 6. unsupported extrapolation: a linear-in-L surrogate fitted on L in [0.5, 1.0] claimed up to 1.3 m (EDGE band)
    def surrogate(p: Mapping[str, float]) -> float:
        lo, hi = _eb(p["F"], 0.5, E0, B, H), _eb(p["F"], 1.0, E0, B, H)
        return lo + (hi - lo) * (p["L"] - 0.5) / 0.5
    span6 = _dim("L", 0.5, 1.0, "m", "fitted range of surrogate SG-1; claim states up to 1.3 m", edge_high=1.3)
    # between the surrogate's own (linear) extrapolation to 1.3 m and the physics there: the fit "looks fine" to the end
    lim6 = 0.5 * (surrogate({"F": F_hi, "L": 1.3}) + _eb(F_hi, 1.3, E0, B, H))
    assert surrogate({"F": F_hi, "L": 1.3}) < lim6 < _eb(F_hi, 1.3, E0, B, H)
    cases.append(_case("unsupported_extrapolation", True, EnvelopeOutcome.FALSIFIED, lim6,
                       (_route("surrogate", "fit", 1, surrogate), _route("eb", "eb", 2, lambda p: _eb(p["F"], p["L"], E0, B, H)),
                        _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))), "surrogate",
                       (LOAD, span6, _routes_dim(("surrogate", "eb", "fe"), AttackKind.MODEL_FORM, "surrogate validity note")),
                       "a fit extrapolated beyond its data"))

    # 7. insufficient convergence: the claim's iterative solver does not converge above 6 kN (the claim may be true)
    lim7 = 1.5 * _fe(F_hi, L_hi, E0, B, H, 64)
    cases.append(_case("insufficient_convergence", True, EnvelopeOutcome.UNKNOWN, lim7,
                       (_route("iterative", "fe", 2, lambda p: _fe(p["F"], p["L"], E0, B, H, 16), converged=lambda p: p["F"] <= 6000.0),
                        _route("fe_ref", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))), "iterative",
                       (LOAD, SPAN), "the claim's evidence includes non-converged solves"))

    # 8. interior-only violation: a load band where the response is amplified (a resonance-like band); no corner, edge
    #    or centre point lies in it -- only the seeded interior sampling can find it
    def amplified(p: Mapping[str, float], family_scale: float = 1.0) -> float:
        amp = 5.0 if 3500.0 <= p["F"] <= 5000.0 else 1.0
        return family_scale * amp * _eb(p["F"], p["L"], E0, B, H)
    lim8 = 1.2 * _eb(F_hi, L_hi, E0, B, H)
    cases.append(_case("interior_only_violation", True, EnvelopeOutcome.FALSIFIED, lim8,
                       (_route("eb_static", "eb", 1, lambda p: _eb(p["F"], p["L"], E0, B, H)),
                        _route("dynamic", "dynamic_eb", 2, amplified),
                        _route("dynamic_fe", "fe", 3, lambda p: amplified(p, 1.0 - 0.8 / 64 ** 2))), "eb_static",
                       (LOAD, SPAN), "a violation only inside the envelope, away from every corner"))

    # 9. KNOWN BLIND SPOT: the same thickness flaw as case 5, but the attack space omits h.  The red team cannot find what
    #    its space does not contain; SURVIVED here is correct and its statement is limited to the declared region.
    cases.append(_case("flaw_outside_attack_space", True, EnvelopeOutcome.SURVIVED, lim5,
                       (_route("eb", "eb", 1, lambda p: _eb(p["F"], p["L"], E0, B, 0.1)),
                        _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, 0.1, 64))), "eb",
                       (LOAD, SPAN), "a real flaw in a dimension the attack space does not include", blind_spot=True))

    # ---- controls ------------------------------------------------------------------------------------------------
    lim_ok = 1.5 * _timo(F_hi, L_hi, E0, B, H)
    cases.append(_case("clean_safe", False, EnvelopeOutcome.SURVIVED, lim_ok,
                       (_route("eb", "eb", 1, lambda p: _eb(p["F"], p["L"], E0, B, H)),
                        _route("timoshenko", "timoshenko", 2, lambda p: _timo(p["F"], p["L"], E0, B, H)),
                        _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))), "eb",
                       (LOAD, SPAN), "a true claim with ample margin"))

    def coarse_with_spike(p: Mapping[str, float]) -> float:   # locking-like spurious overshoot at the load/span corner
        base = _fe(p["F"], p["L"], E0, B, H, 8)
        return base * (3.0 if p["F"] >= 7999.0 and p["L"] >= 0.999 else 1.0)
    cases.append(_case("artifact_trap", False, EnvelopeOutcome.SURVIVED, lim_ok,
                       (_route("fe_coarse", "fe", 1, coarse_with_spike), _route("fe_fine", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))),
                       "fe_coarse", (LOAD, SPAN), "a numerical artifact that refinement removes"))

    span_imp = _dim("L", 0.5, 1.0, "m", "installation drawing D-7", edge_high=1.1)
    lim_imp = 1.02 * _timo(F_hi, 1.1, E0, B, H)
    cases.append(_case("implausible_trap", False, EnvelopeOutcome.SURVIVED, lim_imp,
                       (_route("timoshenko", "timoshenko", 2, lambda p: _timo(p["F"], p["L"], E0, B, H)),
                        _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))), "timoshenko",
                       (LOAD, span_imp), "violated only beyond plausibility", plan_kwargs={"probe_implausible": True}))

    calls: dict[str, int] = {}

    def flaky(p: Mapping[str, float]) -> float:                # solver noise that does not reproduce: a deterministic function
        key = f"{p['F']:.6g}:{p['L']:.6g}"                     # of the point and of how often it was asked (so a replay differs)
        calls[key] = calls.get(key, 0) + 1
        spike = 4.0 if (calls[key] % 2 == 1 and p["F"] >= 7999.0) else 0.0      # first ask spikes, its replay does not
        return _timo(p["F"], p["L"], E0, B, H) * (1.0 + spike)
    lim_flaky = 1.3 * _timo(F_hi, L_hi, E0, B, H)
    cases.append(_case("flaky_trap", False, EnvelopeOutcome.UNKNOWN, lim_flaky,
                       (_route("flaky", "timoshenko", 2, flaky), _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))),
                       "flaky", (LOAD, SPAN), "a violation that does not reproduce"))

    lim_mf = 1.02 * _timo(F_hi, L_hi, E0, B, H)
    cases.append(_case("model_form_trap", False, EnvelopeOutcome.UNKNOWN, lim_mf,
                       (_route("timoshenko", "timoshenko", 2, lambda p: _timo(p["F"], p["L"], E0, B, H)),
                        _route("alt_family", "alt", 3, lambda p: 1.1 * _timo(p["F"], p["L"], E0, B, H)),
                        _route("fe", "fe", 3, lambda p: _fe(p["F"], p["L"], E0, B, H, 64))), "timoshenko",
                       (LOAD, SPAN, _routes_dim(("timoshenko", "alt_family"), AttackKind.MODEL_FORM, "model selection note")),
                       "two equal-fidelity families disagree about the violation"))
    return tuple(cases)


def detected(case: SeededCase, env: TrustEnvelope) -> bool:
    if case.expected is EnvelopeOutcome.UNKNOWN and case.flawed:      # the convergence flaw: UNKNOWN for non-convergence
        return env.outcome is EnvelopeOutcome.UNKNOWN and not env.candidates and env.points_covered > 0 \
            and env.reason.endswith("evaluations did not converge")
    return env.outcome is case.expected


def run_suite(budget: int = 600) -> dict[str, Any]:
    """Run every case; report per-case outcomes and the suite metrics."""
    rows = []
    for case in seeded_cases():
        env = case.run(budget)
        rows.append({"case": case.name, "flawed": case.flawed, "blind_spot": case.blind_spot, "expected": case.expected.value,
                     "outcome": env.outcome.value,
                     "as_expected": detected(case, env), "evaluations": env.evaluations,
                     "evaluations_to_first_candidate": env.evaluations_to_first_candidate,
                     "evaluations_to_falsification": env.evaluations if env.outcome is EnvelopeOutcome.FALSIFIED else None,
                     "counterexample_plausibility": None if env.counterexample is None else env.counterexample.plausibility.value,
                     "cross_family_confirmed": None if env.counterexample is None else env.counterexample.cross_family_confirmed,
                     "candidate_classes": sorted({c.classification.value for c in env.candidates}), "reason": env.reason,
                     "statement": env.statement()})
    flawed = [r for r in rows if r["flawed"] and not r["blind_spot"]]
    controls = [r for r in rows if not r["flawed"]]
    falsified = [r for r in rows if r["outcome"] == "falsified"]
    to_first = [r["evaluations_to_falsification"] for r in falsified]
    return {
        "cases": rows,
        "detection_rate": sum(r["as_expected"] for r in flawed) / len(flawed),
        "false_alarm_rate": sum(r["outcome"] == "falsified" for r in controls) / len(controls),
        "controls_as_expected": sum(r["as_expected"] for r in controls) / len(controls),
        # evaluations spent until a counterexample was CONFIRMED (replays and confirmations included)
        "evaluations_to_confirmed_counterexample": {"min": min(to_first), "max": max(to_first),
                                                "mean": sum(to_first) / len(to_first)} if to_first else None,
        "cross_family_confirmation_rate": (sum(bool(r["cross_family_confirmed"]) for r in falsified) / len(falsified))
        if falsified else None,
        # flaws outside the attack space are missed BY DESIGN; they are reported, never counted as detected
        "blind_spots_missed": [r["case"] for r in rows if r["blind_spot"] and r["outcome"] == "survived"],
        "artifact_classified": any(CounterexampleClass.NUMERICAL_ARTIFACT.value in r["candidate_classes"] for r in rows),
    }


__all__ = ["SeededCase", "detected", "run_suite", "seeded_cases"]
