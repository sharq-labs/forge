"""BIG 10 on the REAL BIG 9 heterogeneous coupled system: FEniCSx plate (dolfinx/PETSc) <-> SciPy heater circuit.

Proof F: representative fast windows are real FEniCSx + SciPy coupled executions
through the existing MultiphysicsRuntime.  The same run is also proof B (long
horizon, represented >> resolved, state and future physics change), A (72 h
more temporally resolved numerical reference vs representative execution) and E
(checkpoint -> serialization -> fresh runtime + fresh mesh -> continuation).

BIG 10 sees the FEniCSx system only through the FastSystem contract; it does
not import dolfinx or preCICE.  Nothing here is validation.
"""

from __future__ import annotations

import importlib.util
import json
import os
from fractions import Fraction

import pytest

from engcore.materials import MaterialState
from engcore.multiscale import ComponentStatus, ErrorComponent, MacroCheckpoint, ReferenceDiscrepancy, compare_resume
from engcore.pde import SourcedQuantity
from engcore.scenarios import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import RegionMaterialMap, gmsh_available
from forge_fenicsx import FenicsxProvider, fenicsx_available

OK = fenicsx_available()[0] and gmsh_available()[0]
pytestmark = pytest.mark.skipif(not OK, reason="FEniCSx or Gmsh unavailable")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load("multiscale_reference_fx", "tests/multiscale_reference.py")
C = _load("coupling_fixtures_fx", "providers/fenicsx/tests/test_coupling_fenicsx.py") if OK else None
P = C.P if OK else None
PROVIDER = FenicsxProvider() if OK else None
DAY, HOUR = R.DAY, R.HOUR
METRICS = os.environ.get("FORGE_BIG10_METRICS", "")


class FenicsxHeaterSystem(R.ReferenceHeaterSystem):
    """The BIG 9 FEniCSx joule plate (alloy | mineral-wool board) as the thermal participant."""

    thermal_solver = ("fenicsx.dolfinx", PROVIDER.identity.version) if OK else ("fenicsx.dolfinx", "unavailable")

    def provider_versions(self):
        import scipy
        return (self.thermal_solver, ("scipy", scipy.__version__))
    #: A larger series resistance than the lumped system keeps the insulated plate inside the
    #: declared data/Arrhenius ranges (at 1 ohm the plate mean reached 588 K and at 15, 25 and 35 ohm the plate maximum (496.6 K at 25, ~480 K at 35 ohm) still left the
    #: board data range -- both refused, see PROGRESS).
    series_ohm = 60.0

    def __init__(self, environment, **kw):
        self.mesh = P.plate()
        self.alloy = alloy_set_wide()
        super().__init__(environment, **kw)

    def configuration(self):
        c = super().configuration()
        c.pop("lumped")
        c.update({"mesh_digest": self.mesh.digest, "pde": "STEADY_DIFFUSION P1 with uniform Joule source and Robin edges (quasi-static per coupling window)",
                  "petsc": {"ksp_type": "preonly", "pc_type": "lu"}, "provider": list(self.thermal_solver),
                  "alloy_property_set": self.alloy.digest,
                  "alloy_conductivity": "DECLARED approximation: resolved at 450 K (illustrative data 273.15-600 K, "
                                        "198-225 W/(m K)); its temperature dependence is not iterated inside a coupling "
                                        "window; every solve refuses a plate min/max outside the data range"})
        return c

    def _states(self, moisture, board_temperature):
        alloy = MaterialState(R.M.ALLOY, (NamedQuantity("temperature", Quantity(450, "K")),), "solid")
        board = MaterialState(R.M.BOARD, (NamedQuantity("moisture_content", moisture), NamedQuantity("temperature", board_temperature)))
        binding = RegionMaterialMap(self.mesh, ((self.mesh.region("left_plate"), alloy), (self.mesh.region("right_plate"), board)))
        field, resolved = binding.property_field({R.M.ALLOY.digest: self.alloy, R.M.BOARD.digest: self.board}, "thermal_conductivity", "W/(m*K)", "k")
        return ((alloy, resolved[0]), (board, resolved[1])), field

    def material_states(self, moisture, temperature):
        return self._states(moisture, temperature)[0]

    def thermal_solve(self, power_W, ambient_K, moisture, start_s):
        _, k = self._states(moisture, Quantity(ambient_K, "K"))
        env = self.environment.channel_value("air_temperature", R.p(Fraction(repr(start_s))))
        ambient = SourcedQuantity(env.value.value, "environment", env.to_dict())
        rec = PROVIDER.execute(C.thermal_problem(self.mesh, Quantity(power_W, "W"), ambient, k))
        if not rec.succeeded:
            return rec, None, None
        for bound in (float(rec.field.values.min()), float(rec.field.values.max())):
            state = MaterialState(R.M.ALLOY, (NamedQuantity("temperature", Quantity(bound, "K")),), "solid")
            if self.alloy.resolve("thermal_conductivity", state).status != "known":
                raise R.CouplingRefusal(f"solved plate temperature {bound:.6g} K is outside the alloy data range")
        # the plate maximum bounds the board temperature from above
        return rec, C.mean_temperature(rec.field), Quantity(float(rec.field.values.max()), "K")


CHANGE_HOUR = 30 * 24 + 12


def alloy_set_wide():
    """Illustrative alloy conductivity 273.15-600 K (BIG 10 fixture values, not reference data)."""
    rows = [(f"k-wide-{t}", "thermal_conductivity", Quantity(v, "W/(m*K)"), None, (R.M.point("temperature", Quantity(t, "K")),), "solid", "compiled", None)
            for t, v in ((273.15, 198.0), (300, 200.0), (400, 210.0), (500, 220.0), (600, 225.0))]
    from engcore.materials import InterpolationRule
    return R.M._dataset(R.M.ALLOY, rows, source_id="fixture-alloy-wide", locator="providers/fenicsx/tests/test_multiscale_fenicsx.py::alloy_set_wide",
                        set_id="alloy-props-wide", rules=(InterpolationRule("thermal_conductivity", "temperature", "linear"),))[0]


@pytest.fixture(scope="module")
def long_run():
    runtime, system, env = R.build_runtime(63, change_at_hour=CHANGE_HOUR, system_cls=FenicsxHeaterSystem, run_id="fenicsx-63d")
    run = runtime.run(initial_slow_state=R.initial_slow())
    return runtime, system, env, run


def test_proof_f_representative_windows_are_real_fenicsx_scipy_coupled_executions(long_run):
    runtime, system, env, run = long_run
    assert run.status == "completed", run.reason
    import scipy
    assert dict(system.identity.providers) == {"fenicsx.dolfinx": PROVIDER.identity.version, "scipy": scipy.__version__}  # installed, not labels
    assert PROVIDER.identity.version.startswith("0.11")
    step = run.steps[0]
    result = step.results[0]
    assert result.coupled_windows == 24 and set(result.window_outcomes) == {"converged"}
    assert result.coupling_iterations > 24  # genuine two-way iteration in each coupling window
    materials = {p["material"] for p in step.executions[0].resolved_properties}
    assert materials == {"aluminium_alloy", "mineral_wool"}
    # BIG 10 does not depend on dolfinx: the multiscale package never imports it
    import engcore.multiscale as ms
    import sys
    assert all(not m.startswith("dolfinx") for m in getattr(ms, "__dict__", {}))
    assert "dolfinx" not in open(ms.__file__.replace("__init__.py", "runtime.py")).read()


def test_proof_b_fenicsx_63_day_long_horizon_feed_forward(long_run):
    runtime, system, env, run = long_run
    acc = run.accounting
    represented, resolved = Fraction(acc["represented_seconds"]), Fraction(acc["resolved_seconds"])
    assert represented == 63 * DAY and resolved < represented / 3
    m_end = run.final_slow_state["thermal"]["moisture_content"].value.magnitude
    d_end = run.final_slow_state["electrical"]["resistance_drift"].value.magnitude
    assert m_end > 0.05 and d_end > 0.005  # 60 ohm keeps the plate in range: less power, less drift than the lumped run
    ks = [s.executions[0].resolved_properties[0]["value_W_mK"] for s in run.steps]
    assert all(a < b for a, b in zip(ks, ks[1:]))  # board re-resolved from new moisture every window
    # same day-0 window/environment/usage; only the accumulated slow state differs
    from engcore.multiscale import FastExecutionRequest
    first = run.steps[0].executions[0].representative.resolved
    req = lambda slow: FastExecutionRequest("cf", system.identity.digest, env.timeline.scenario_digest, env.timeline.digest, env.digest,  # noqa: E731
                                            first, slow, {}, runtime._environment_context(first), runtime._usage_context(first))
    day0 = system.execute(req(run.steps[0].slow_before)).series_for("heater_temperature")
    dayN = system.execute(req(run.final_slow_state)).series_for("heater_temperature")
    diffs = [a.value.magnitude - b.value.magnitude for a, b in zip(day0.samples, dayN.samples)]
    assert max(abs(x) for x in diffs) > 0.5
    ends = [s.window.end.seconds for s in run.steps]
    assert CHANGE_HOUR * HOUR in ends
    if METRICS:
        per_step = [{"start_day": float(s.window.start.seconds) / DAY, "days": float(s.represented_seconds) / DAY,
                     "resolved_h": float(s.resolved_seconds) / HOUR, "weight": str(s.executions[0].representative.weight),
                     "moisture_after": s.slow_after["thermal"]["moisture_content"].value.magnitude,
                     "drift_after": s.slow_after["electrical"]["resistance_drift"].value.magnitude,
                     "k_board_W_mK": s.executions[0].resolved_properties[0]["value_W_mK"],
                     "adaptation": None if s.adaptation is None else s.adaptation.rule_id,
                     "refinements": [r.kind for r in s.refinements], "crossings": list(s.threshold_crossings)} for s in run.steps]
        json.dump({"accounting": acc, "wall_s": run.wall_seconds, "digest": run.digest, "steps": per_step,
                   "counterfactual_max_dT_K": max(abs(x) for x in diffs), "providers": [list(x) for x in system.identity.providers],
                   "ledger": run.ledger.to_dict()}, open(METRICS + "_long.json", "w"), indent=1)


def test_proof_a_fenicsx_72h_resolved_reference_vs_representative():
    env, _ = R.build_environment(3)
    ref_rt, _, _ = R.build_runtime(3, environment=env, default_days=1, representative=R.FULLY_RESOLVED, near_threshold=False,
                                   system_cls=FenicsxHeaterSystem, run_id="fx-ref-72h")
    ms_rt, _, _ = R.build_runtime(3, environment=env, default_days=3, near_threshold=False, system_cls=FenicsxHeaterSystem, run_id="fx-ms-72h")
    ref = ref_rt.run(initial_slow_state=R.initial_slow())
    ms = ms_rt.run(initial_slow_state=R.initial_slow())
    assert ref.status == ms.status == "completed"
    ledger = ms.ledger
    scope = f"scenario {env.timeline.scenario_digest[:12]}, 72 h, FEniCSx+SciPy fast system"
    for pid, var in (("thermal", "moisture_content"), ("electrical", "resistance_drift")):
        ledger = ledger.with_observation(ReferenceDiscrepancy(f"{pid}.{var}", ref.final_slow_state[pid][var].value,
                                                              ms.final_slow_state[pid][var].value, scope))
    assert ledger.entry(ErrorComponent.REPRESENTATIVE_WINDOW).status is ComponentStatus.UNKNOWN
    assert ledger.observations[1].relative is not None and ledger.observations[1].relative > 0
    if METRICS:
        json.dump({"reference": ref.accounting, "multiscale": ms.accounting, "observations": [o.to_dict() for o in ledger.observations],
                   "wall_s": [ref.wall_seconds, ms.wall_seconds]}, open(METRICS + "_72h.json", "w"), indent=1)


def test_proof_e_fenicsx_checkpoint_resume_matches_uninterrupted():
    kw = dict(change_at_hour=10 * 24 + 12, near_threshold=False, system_cls=FenicsxHeaterSystem, run_id="fx-resume")
    full_rt, _, _ = R.build_runtime(21, **kw)
    uninterrupted = full_rt.run(initial_slow_state=R.initial_slow())
    first_rt, _, _ = R.build_runtime(21, **kw)
    first = first_rt.run(initial_slow_state=R.initial_slow(), until=R.p(7 * DAY))
    payload = json.loads(json.dumps(first.last_valid_checkpoint.serialize()))
    fresh_rt, fresh_system, _ = R.build_runtime(21, **kw)  # new runtime, new gmsh mesh, new provider objects
    resumed = fresh_rt.resume(MacroCheckpoint.deserialize(payload))
    comparison = compare_resume(uninterrupted, first, resumed)
    assert comparison.matched, comparison.first_mismatch
    # the fresh runtime really executed the whole second half itself (the checkpoint drove a continuation)
    assert fresh_system.executions == resumed.accounting["fast_executions"] - first.accounting["fast_executions"] > 0
    assert len(first.steps) + len(resumed.steps) == len(uninterrupted.steps)
    if METRICS:
        json.dump({"comparison": comparison.to_dict(), "first_steps": len(first.steps), "resumed_steps": len(resumed.steps),
                   "uninterrupted_digest": uninterrupted.digest, "resumed_digest": resumed.digest},
                  open(METRICS + "_resume.json", "w"), indent=1)
