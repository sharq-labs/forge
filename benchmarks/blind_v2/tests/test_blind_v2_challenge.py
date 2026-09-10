"""Phase-1 tests for Blind Challenge v2. No Forge execution anywhere here.

Two jobs. The first is to show the challenge machinery does what it says:
generation is deterministic, truth is stable, digests hold, the audit catches a
peeker. The second is to show the oracles are worth believing -- every one of
them is checked against something that is not itself: an analytic limit, a
conservation law, a dimensional identity, a refinement, or a second route.

A numerical value that looks right and has nothing behind it is not evidence,
so every oracle here has at least one **non-vacuity** test: a check that fails
when the oracle is broken, demonstrated by breaking it.
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest

from challenge import audit, build, freeze, generator, shadows, truth, units
from challenge.oracles import battery, conduction1d, cstr, electrical_dc, material_tcr
from challenge.oracles import numeric, thermal_lumped
from challenge.systems import SYSTEMS, BY_ID

BLIND = pathlib.Path(__file__).resolve().parent.parent


def _jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return _jsonl(BLIND / "cases" / "primary.jsonl")


@pytest.fixture(scope="module")
def truths() -> list[dict]:
    return _jsonl(BLIND / "truth" / "truth.jsonl")


@pytest.fixture(scope="module")
def shadow_records() -> list[dict]:
    return _jsonl(BLIND / "cases" / "shadows.jsonl")


# =========================================================================
# the unit algebra
# =========================================================================
class TestUnits:
    def test_an_affine_unit_states_a_temperature(self):
        assert units.to_si(25.0, "degC") == pytest.approx(298.15)
        assert units.to_si(77.0, "degF") == pytest.approx(298.15)
        assert units.to_si(0.0, "degC") == pytest.approx(273.15)

    def test_an_affine_unit_does_not_state_a_span(self):
        """25 degC is 298.15 K as a state and 25 K as a difference."""
        assert units.to_si(25.0, "degC") == pytest.approx(298.15)
        assert units.si_span(25.0, "degC") == pytest.approx(25.0)
        assert units.si_span(9.0, "degF") == pytest.approx(5.0)

    def test_an_affine_unit_may_not_enter_a_compound(self):
        with pytest.raises(units.UnitError):
            units.parse("degC / second")
        with pytest.raises(units.UnitError):
            units.parse("joule / degC")

    def test_an_undefined_unit_is_refused_rather_than_guessed(self):
        with pytest.raises(units.UnitError):
            units.parse("kilohm")
        assert units.parse("kiloohm").factor == 1000.0

    @pytest.mark.parametrize(
        "value,unit,expected",
        [
            (1.0, "ampere_hour", 3600.0),
            (1.0, "kilowatt_hour", 3.6e6),
            (1.0, "hour", 3600.0),
            (1.0, "1 / hour", 1.0 / 3600.0),
            (1.0, "gram / centimeter ** 3", 1000.0),
            (1.0, "millimole / liter", 1.0),
            (1.0, "joule / gram / kelvin", 1000.0),
        ],
    )
    def test_conversions_are_the_si_definitions(self, value, unit, expected):
        assert units.to_si(value, unit) == pytest.approx(expected, rel=1e-15)

    def test_dimensions_separate_what_names_do_not(self):
        assert units.same_dimension("watt / kelvin / meter", "watt / meter / kelvin")
        assert not units.same_dimension("ohm", "volt")
        assert not units.same_dimension("joule / kelvin", "watt / kelvin")

    def test_ratio_scale_is_a_property_of_the_unit(self):
        assert units.is_ratio_scale("kelvin")
        assert units.is_ratio_scale("degR")
        assert not units.is_ratio_scale("degC")
        assert not units.is_ratio_scale("degF")


# =========================================================================
# oracle self-verification -- Phase 1L
# =========================================================================
class TestLumpedOracle:
    BODY = dict(
        heat_capacity=900.0,
        ambient_conductance=1.5,
        duration=3000.0,
        initial_temperature=300.0,
        ambient_temperature=295.0,
        heat_input=12.0,
        surface_area=0.02,
        characteristic_length=1e-3,
        body_conductivity=200.0,
    )

    def test_the_two_routes_agree_on_the_trajectory(self):
        """Closed form against RK4: an analytic limit met by an integration."""
        result = thermal_lumped.evaluate(self.BODY)
        route = result["routes"]["final_temperature"]
        assert route["gap"] < 1e-10
        assert route["refinement_movement"] < 1e-10

    def test_the_body_relaxes_to_its_steady_state(self):
        """A limiting case: over many time constants the endpoint IS T_ss."""
        long_run = dict(self.BODY, duration=1e6)
        result = thermal_lumped.evaluate(long_run)
        steady = result["intermediate"]["steady_state_temperature"]
        assert result["routes"]["final_temperature"]["numerical"] == pytest.approx(
            steady, rel=1e-9
        )

    def test_a_body_with_no_heat_input_sits_at_ambient(self):
        result = thermal_lumped.evaluate(dict(self.BODY, heat_input=0.0, initial_temperature=295.0))
        assert result["intermediate"]["steady_state_temperature"] == pytest.approx(295.0)
        assert result["quantities"]["biot_number"] is not None

    def test_the_energy_balance_closes_at_steady_state(self):
        """Conservation: at T_ss the heat in equals the heat out, exactly."""
        result = thermal_lumped.evaluate(self.BODY)
        t_ss = result["intermediate"]["steady_state_temperature"]
        out = self.BODY["ambient_conductance"] * (t_ss - self.BODY["ambient_temperature"])
        assert out == pytest.approx(self.BODY["heat_input"], rel=1e-12)

    def test_biot_is_dimensionless_by_construction(self):
        """h L / k: W/m^2K * m / (W/mK) cancels. Checked, not asserted."""
        h = units.dimension("watt / meter ** 2 / kelvin")
        length = units.dimension("meter")
        k = units.dimension("watt / meter / kelvin")
        combined = tuple(a + b - c for a, b, c in zip(h, length, k))
        assert combined == units.DIMENSIONLESS

    def test_fourier_matches_its_independent_definition(self):
        """Fo = (t/tau)/Bi must equal alpha t / L^2 with alpha = k V / C."""
        result = thermal_lumped.evaluate(self.BODY)
        fourier = result["quantities"]["internal_fourier_number"]
        volume = self.BODY["characteristic_length"] * self.BODY["surface_area"]
        alpha = self.BODY["body_conductivity"] * volume / self.BODY["heat_capacity"]
        direct = alpha * self.BODY["duration"] / self.BODY["characteristic_length"] ** 2
        assert fourier == pytest.approx(direct, rel=1e-12)

    def test_radiation_coefficient_matches_the_quartic_it_factorises(self):
        """h_r (T_s - T_sur) must equal eps sigma (T_s^4 - T_sur^4)."""
        result = thermal_lumped.evaluate(dict(self.BODY, surface_emissivity=0.4))
        ratio = result["quantities"]["radiation_to_convection_ratio"]
        h = result["intermediate"]["surface_coefficient"]
        peak = result["intermediate"]["peak_temperature"]
        ambient = self.BODY["ambient_temperature"]
        h_r = ratio * h
        exact = 0.4 * numeric.STEFAN_BOLTZMANN * (peak**4 - ambient**4)
        assert h_r * (peak - ambient) == pytest.approx(exact, rel=1e-12)

    def test_non_vacuity_a_broken_biot_is_caught(self):
        """Break the oracle's own inputs and the checks must move."""
        good = thermal_lumped.evaluate(self.BODY)["quantities"]["biot_number"]
        bad = thermal_lumped.evaluate(dict(self.BODY, body_conductivity=2.0))
        assert bad["quantities"]["biot_number"] > good * 50


class TestCSTROracle:
    RUN = dict(
        k0=7.2e10,
        activation_energy=72750.0,
        heat_of_reaction=-5.0e4,
        density=1000.0,
        heat_capacity=239.0,
        feed_concentration=1000.0,
        feed_temperature=350.0,
        coolant_temperature=300.0,
        ua=5.0e4,
        residence_time=60.0,
        end_time=600.0,
        initial_concentration=500.0,
        initial_temperature=350.0,
        volume=0.1,
    )

    def test_the_ceiling_bounds_the_integrated_trajectory(self):
        """The analytic invariant is checked against a numerical integration."""
        route = cstr.evaluate(self.RUN)["routes"]["adiabatic_ceiling_temperature"]
        assert route["ceiling_respected"] is True
        assert route["slack"] > 0.0

    def test_the_ceiling_still_bounds_an_uncooled_reactor(self):
        """The bound is derived with or without cooling; test it without.

        Uncooled and mild, so the explicit integrator can actually follow it.
        The uncooled runaway is the next test, and it is a different question.
        """
        mild = dict(self.RUN, ua=0.0, heat_of_reaction=-2.0e2, k0=1.0e6)
        result = cstr.evaluate(mild)
        assert result["numerical_route_converged"] is True
        route = result["routes"]["adiabatic_ceiling_temperature"]
        assert route["ceiling_respected"] is True

    def test_a_divergent_integration_abstains_instead_of_asserting(self):
        """The failure this test was written after finding.

        An uncooled exotherm is stiff and a fixed-step explicit scheme run into
        one returns a number with nothing behind it. Before the fix the oracle
        reported that number as a peak temperature of 3.5e11 K and concluded
        the ceiling had been breached. It now reports that it did not converge
        and offers no second route, so the case is not counted as
        dual-oracle. Found by this suite, before the freeze, with no help from
        the system under test.
        """
        runaway = cstr.evaluate(dict(self.RUN, ua=0.0))
        assert runaway["numerical_route_converged"] is False
        assert runaway["routes"] == {}
        assert runaway["quantities"]["adiabatic_ceiling_temperature"] is not None

    def test_a_reaction_that_does_not_run_leaves_the_feed_alone(self):
        """Limiting case: with no reaction the tank washes out to the feed."""
        inert = dict(self.RUN, k0=1e-30, end_time=60.0 * 200)
        result = cstr.evaluate(inert)
        assert result["intermediate"]["final_concentration"] == pytest.approx(
            self.RUN["feed_concentration"], rel=1e-6
        )

    def test_the_integration_converges(self):
        assert cstr.evaluate(self.RUN)["intermediate"]["refinement_movement"] < 1e-6

    def test_non_vacuity_a_hotter_reaction_raises_the_ceiling(self):
        cool = cstr.evaluate(self.RUN)["quantities"]["adiabatic_ceiling_temperature"]
        hot = cstr.evaluate(dict(self.RUN, heat_of_reaction=-5.0e5))["quantities"][
            "adiabatic_ceiling_temperature"
        ]
        assert hot > cool + 100.0


class TestConductionOracle:
    SLAB = dict(alpha=1e-5, length=0.05, end_time=20.0)

    def test_crank_nicolson_converges_to_the_exact_solution(self):
        route = conduction1d.evaluate(self.SLAB)["routes"]["midpoint_amplitude"]
        assert route["gap"] < 1e-3

    def test_the_scheme_converges_at_second_order(self):
        """Halving h must cut the error by about four. A refinement check."""
        exact = conduction1d.analytic_decay(**{"length": 0.05, "alpha": 1e-5, "time": 20.0})
        coarse = abs(
            conduction1d.crank_nicolson_midpoint(
                length=0.05, alpha=1e-5, time=20.0, cells=40, steps=100
            )
            - exact
        )
        fine = abs(
            conduction1d.crank_nicolson_midpoint(
                length=0.05, alpha=1e-5, time=20.0, cells=80, steps=200
            )
            - exact
        )
        assert 3.0 < coarse / fine < 5.0

    def test_at_time_zero_the_field_is_the_initial_condition(self):
        assert conduction1d.analytic_decay(length=0.05, alpha=1e-5, time=0.0) == 1.0
        assert conduction1d.analytic_field(0.025, length=0.05, alpha=1e-5, time=0.0) == (
            pytest.approx(1.0)
        )

    def test_the_boundaries_are_held_at_zero(self):
        for x in (0.0, 0.05):
            assert conduction1d.analytic_field(
                x, length=0.05, alpha=1e-5, time=5.0
            ) == pytest.approx(0.0, abs=1e-15)

    def test_the_field_decays_monotonically(self):
        previous = 2.0
        for t in (0.0, 5.0, 10.0, 40.0, 200.0):
            value = conduction1d.analytic_decay(length=0.05, alpha=1e-5, time=t)
            assert value < previous
            previous = value

    def test_non_vacuity_a_wrong_diffusivity_is_caught(self):
        exact = conduction1d.analytic_decay(length=0.05, alpha=1e-5, time=20.0)
        scheme = conduction1d.crank_nicolson_midpoint(
            length=0.05, alpha=2e-5, time=20.0, cells=80, steps=200
        )
        assert abs(scheme - exact) / exact > 0.1


class TestBatteryOracle:
    CELL = dict(
        nominal_capacity=9000.0,
        internal_resistance=0.035,
        coulombic_efficiency=1.0,
        duration=600.0,
        discharge_current=2.5,
        state_of_charge=0.9,
        cell_temperature=298.15,
        open_circuit_voltage_at_full=4.2,
        open_circuit_voltage_at_empty=3.0,
    )

    def test_charge_is_conserved_between_the_two_routes(self):
        route = battery.evaluate(self.CELL)["routes"]["final_state_of_charge"]
        assert route["gap"] < 1e-12

    def test_the_charge_removed_is_current_times_time(self):
        """Conservation, stated independently of the oracle's own formula."""
        result = battery.evaluate(self.CELL)
        moved = self.CELL["state_of_charge"] - result["intermediate"]["final_state_of_charge"]
        coulombs = self.CELL["discharge_current"] * self.CELL["duration"]
        assert moved * self.CELL["nominal_capacity"] == pytest.approx(coulombs, rel=1e-12)

    def test_at_zero_current_nothing_moves(self):
        result = battery.evaluate(dict(self.CELL, discharge_current=0.0))
        assert result["intermediate"]["final_state_of_charge"] == pytest.approx(0.9)
        assert result["intermediate"]["heat_generation"] == pytest.approx(0.0)

    def test_the_open_circuit_chord_hits_its_declared_endpoints(self):
        full = battery.evaluate(dict(self.CELL, state_of_charge=1.0, duration=0.0))
        empty = battery.evaluate(dict(self.CELL, state_of_charge=0.0, duration=0.0))
        assert full["intermediate"]["open_circuit_voltage_worst"] == pytest.approx(4.2)
        assert empty["intermediate"]["open_circuit_voltage_worst"] == pytest.approx(3.0)

    def test_peukert_derates_and_never_raises_above_the_reference(self):
        above = battery.evaluate(
            dict(
                self.CELL,
                peukert_exponent=1.2,
                peukert_reference_current=1.0,
                discharge_current=10.0,
            )
        )
        assert above["quantities"]["peukert_capacity_ratio"] < 1.0

    def test_non_vacuity_a_doubled_current_halves_the_runtime_margin(self):
        base = battery.evaluate(self.CELL)["intermediate"]["final_state_of_charge"]
        faster = battery.evaluate(dict(self.CELL, discharge_current=5.0))["intermediate"][
            "final_state_of_charge"
        ]
        assert (0.9 - faster) == pytest.approx(2.0 * (0.9 - base), rel=1e-9)


class TestMaterialOracle:
    CONDUCTOR = dict(
        temperature=350.0,
        reference_temperature=293.15,
        temperature_coefficient=0.00393,
        reference_resistance=100.0,
    )

    def test_the_integral_and_the_closed_form_agree(self):
        route = material_tcr.evaluate(self.CONDUCTOR)["routes"]["resistance"]
        assert route["gap"] < 1e-12

    def test_at_the_reference_the_resistance_is_the_reference(self):
        at_reference = material_tcr.evaluate(dict(self.CONDUCTOR, temperature=293.15))
        assert at_reference["quantities"]["linear_resistance_ratio"] == pytest.approx(1.0)

    def test_the_sign_at_the_zero_crossing_is_decided_exactly(self):
        """1 + alpha (T - T_ref) is formed in rationals, so the sign is exact."""
        crossing = dict(self.CONDUCTOR, temperature_coefficient=-1.0 / 56.85)
        ratio = material_tcr.evaluate(crossing)["quantities"]["linear_resistance_ratio"]
        assert abs(ratio) < 1e-12

    def test_non_vacuity_a_negative_coefficient_crosses_zero(self):
        cold = material_tcr.evaluate(
            dict(self.CONDUCTOR, temperature_coefficient=-0.02)
        )
        assert cold["quantities"]["linear_resistance_ratio"] < 0.0


class TestElectricalOracle:
    NETWORK = electrical_dc.Network(
        circuit_id="selftest",
        resistors=(
            electrical_dc.Resistor("R1", "n1", "n2", 1000.0),
            electrical_dc.Resistor("R2", "n2", "0", 2200.0),
        ),
        sources=(electrical_dc.VoltageSource("V1", "n1", "0", 12.0),),
    )

    def test_the_divider_has_the_answer_a_divider_has(self):
        solution = electrical_dc.solve_mna(self.NETWORK)
        assert solution["node_voltages"]["n2"] == pytest.approx(12.0 * 2200 / 3200)

    def test_kirchhoff_holds_at_the_internal_node(self):
        """Conservation, computed from the solution rather than assumed."""
        solution = electrical_dc.solve_mna(self.NETWORK)
        v2 = solution["node_voltages"]["n2"]
        into = (solution["node_voltages"]["n1"] - v2) / 1000.0
        out_of = v2 / 2200.0
        assert into == pytest.approx(out_of, rel=1e-12)

    def test_power_balances(self):
        solution = electrical_dc.solve_mna(self.NETWORK)
        elements = electrical_dc.element_quantities(self.NETWORK, solution)
        dissipated = elements["R1"]["dissipated_power"] + elements["R2"]["dissipated_power"]
        delivered = abs(solution["source_currents"]["V1"]) * 12.0
        assert dissipated == pytest.approx(delivered, rel=1e-12)

    @pytest.mark.skipif(
        electrical_dc.ngspice_version() is None, reason="ngspice is not installed here"
    )
    def test_the_external_engine_agrees_and_says_who_it_is(self):
        solved = electrical_dc.solve(self.NETWORK)
        assert solved["dual_oracle"] is True
        assert solved["independence_level"] == "A"
        assert solved["worst_gap"] <= electrical_dc.ROUTE_AGREEMENT_TOLERANCE
        assert solved["external"]["exit_code"] == 0
        assert len(solved["external"]["netlist_sha256"]) == 64
        assert len(solved["external"]["output_sha256"]) == 64

    @pytest.mark.skipif(
        electrical_dc.ngspice_version() is None, reason="ngspice is not installed here"
    )
    def test_non_vacuity_the_external_engine_disagrees_with_a_wrong_answer(self):
        """The dual-oracle check must be able to fail. Feed it a wrong network."""
        wrong = electrical_dc.Network(
            circuit_id="selftest_wrong",
            resistors=(
                electrical_dc.Resistor("R1", "n1", "n2", 1000.0),
                electrical_dc.Resistor("R2", "n2", "0", 4700.0),
            ),
            sources=(electrical_dc.VoltageSource("V1", "n1", "0", 12.0),),
        )
        external = electrical_dc.solve_ngspice(wrong)
        mine = electrical_dc.solve_mna(self.NETWORK)
        gap = numeric.relative_gap(
            mine["node_voltages"]["n2"], external["node_voltages"]["n2"]
        )
        assert gap > electrical_dc.ROUTE_AGREEMENT_TOLERANCE * 1000


# =========================================================================
# truth engine
# =========================================================================
class TestTruthEngine:
    MODEL = "thermal.conduction1d.linear_diffusion"

    def test_an_uncomputable_quantity_is_unknown_and_never_a_pass(self):
        assert truth.assess(self.MODEL, {})["outcome"] == "INSUFFICIENT_EVIDENCE"

    def test_a_non_finite_quantity_is_unknown(self):
        assert truth.assess(self.MODEL, {"alpha": math.nan})["outcome"] == (
            "INSUFFICIENT_EVIDENCE"
        )

    def test_an_inclusive_bound_admits_its_own_edge(self):
        condition = {"maximum": {"magnitude": 0.1}, "maximum_inclusive": True}
        assert truth.classify_condition(condition, 0.1)[0] == truth.SATISFIED

    def test_an_exclusive_bound_refuses_its_own_edge(self):
        condition = {"minimum": {"magnitude": 0.0}, "minimum_inclusive": False}
        assert truth.classify_condition(condition, 0.0)[0] == truth.VIOLATED

    def test_a_conservative_screen_refuses_for_want_of_evidence(self):
        """Below its floor a screen is UNKNOWN, not a finding against the design."""
        condition = {
            "minimum": {"magnitude": 0.2},
            "minimum_inclusive": True,
            "conservative_screen": True,
        }
        status, reason = truth.classify_condition(condition, 0.05)
        assert status == truth.UNKNOWN
        assert reason == "conservative_screen"

    def test_violation_dominates_unknown_and_the_case_says_so(self):
        assessment = {
            "outcome": "NOT_SUPPORTED",
            "violated": ["a"],
            "unknown": ["b"],
            "satisfied": [],
        }
        reasons = truth.reason_truth(assessment)
        assert reasons["valid_mechanisms"] == ["a"]

    def test_several_mechanisms_are_not_forced_into_one(self):
        assessment = {
            "outcome": "NOT_SUPPORTED",
            "violated": ["a", "b"],
            "unknown": [],
            "satisfied": [],
        }
        assert truth.reason_truth(assessment)["reason_status"] == "MULTIPLE_VALID"

    def test_every_shipped_model_has_its_conditions_registered(self):
        surface = json.loads((BLIND / "CONTRACT_SURFACE.json").read_text())
        for model in surface["models"]:
            registered = {c["name"] for c in truth.conditions_for(model["model_id"])}
            declared = {c["name"] for c in model["conditions"]}
            assert registered == declared, model["model_id"]

    def test_no_bound_is_unclassified(self):
        register = truth.bound_register()
        assert register["unclassified"] == []
        assert all(b["class"] != "UNCLASSIFIED" for b in register["bounds"])


# =========================================================================
# generation and the frozen corpus
# =========================================================================
class TestGeneration:
    def test_generation_is_deterministic(self):
        """The same seed twice must produce byte-identical declarations."""
        spec = BY_ID["electrical.dc"]
        first, first_truth = build.build_system(spec, generator.GenerationLog())
        second, second_truth = build.build_system(spec, generator.GenerationLog())
        # Compared as serialized text: a NaN probe is a legitimate declaration
        # and NaN is never equal to itself, so a value comparison would report
        # a difference that is not one.
        def as_text(records):
            return [json.dumps(r["declaration"], sort_keys=True) for r in records]

        assert as_text(first) == as_text(second)
        assert [t["outcome"] for t in first_truth] == [t["outcome"] for t in second_truth]

    def test_case_ids_are_stable_and_unique(self, cases):
        ids = [c["case_id"] for c in cases]
        assert len(ids) == len(set(ids))
        assert all(c["case_id"].startswith("V2-") for c in cases)

    def test_the_frozen_truth_is_what_the_oracles_still_say(self, cases, truths):
        """Regenerate truth from the frozen declarations and compare."""
        by_id = {t["case_id"]: t for t in truths}
        checked = 0
        for case in cases:
            if case["family"] == "boundary_refusal":
                continue
            spec = BY_ID[case["system"]]
            si = {
                name: units.to_si(entry["value"], entry["unit"])
                for name, entry in case["declaration"].items()
            }
            if case["system"] == "electrical.material":
                si.setdefault("coldest_temperature", min(
                    si.get("reference_temperature", si.get("temperature", 0.0)),
                    si.get("temperature", 0.0),
                ))
                si.setdefault("furthest_temperature", si.get("temperature"))
            forward = spec.cheap or spec.oracle
            again = truth.assess(spec.model_id, forward(si)["quantities"])
            assert again["outcome"] == by_id[case["case_id"]]["outcome"], case["case_id"]
            checked += 1
        assert checked > 500

    def test_the_corpus_meets_its_registered_targets(self, cases, truths, shadow_records):
        spec = json.loads((BLIND / "CHALLENGE_SPEC.json").read_text())
        assert len(cases) >= spec["target_primary_cases"]
        assert len(shadow_records) >= spec["metamorphic_strategy"]["target_shadows"]
        per_system: dict[str, int] = {}
        for case in cases:
            per_system[case["system"]] = per_system.get(case["system"], 0) + 1
        assert len(per_system) == spec["target_system_count"]
        assert min(per_system.values()) >= spec["minimum_cases_per_system"]

    def test_dual_oracle_coverage_meets_its_registered_target(self, truths):
        spec = json.loads((BLIND / "CHALLENGE_SPEC.json").read_text())
        decided = [t for t in truths if t["outcome"] != "REJECTED_AT_BOUNDARY"]
        dual = [t for t in decided if t["oracle"]["dual_oracle"]]
        share = len(dual) / len(decided)
        assert share >= spec["dual_oracle_plan"]["target_share_of_scientifically_decided_cases"]

    def test_every_system_carries_enough_dual_oracle_cases(self, truths, cases):
        system_of = {c["case_id"]: c["system"] for c in cases}
        counts: dict[str, int] = {}
        for record in truths:
            if record["oracle"]["dual_oracle"]:
                system = system_of[record["case_id"]]
                counts[system] = counts.get(system, 0) + 1
        assert min(counts.values()) >= 30, counts

    def test_no_case_claims_level_d_independence(self, truths):
        for record in truths:
            assert record["oracle"]["independence_level"] in (None, "A", "B", "C")

    def test_unresolved_truth_is_zero(self, truths):
        assert [t["case_id"] for t in truths if t["truth_class"] == "UNRESOLVED"] == []

    def test_every_outcome_is_in_the_registered_vocabulary(self, truths):
        spec = json.loads((BLIND / "CHALLENGE_SPEC.json").read_text())
        allowed = set(spec["truth_outcome_vocabulary"])
        for record in truths:
            assert record["outcome"] in allowed
            assert set(record["acceptable_outcomes"]) <= allowed

    def test_refusal_cases_record_the_stage_they_predict(self, cases, truths):
        by_id = {t["case_id"]: t for t in truths}
        refusals = [c for c in cases if c["family"] == "boundary_refusal"]
        assert refusals
        for case in refusals:
            record = by_id[case["case_id"]]
            assert record["outcome"] == "REJECTED_AT_BOUNDARY"
            assert record["refusal_stage"] in ("unit_compatibility", "schema_type")
            assert record["reason_status"] == "CONTRACT_REFUSAL"

    def test_a_refusal_is_never_relabelled_as_a_generic_non_support(self, truths):
        for record in truths:
            if record["refusal_stage"] in ("unit_compatibility", "schema_type"):
                assert record["outcome"] == "REJECTED_AT_BOUNDARY"

    def test_boundary_cases_report_what_they_achieved(self, truths):
        kinds = {
            record["boundary"]["kind"]
            for record in truths
            if record["boundary"]["kind"]
        }
        assert kinds <= {
            "MATHEMATICAL_BOUNDARY",
            "REPRESENTABLE_BOUNDARY",
            "WITHIN_1_ULP_BOUNDARY",
        }
        assert "MATHEMATICAL_BOUNDARY" in kinds

    def test_causal_truth_is_frozen_for_every_refusing_case(self, truths):
        classes = {t["causal"]["class"] for t in truths}
        assert classes <= {
            "UNIQUE_CAUSAL_CATCHER",
            "ONE_CAUSAL_PLUS_REDUNDANT",
            "MULTIPLE_CAUSAL_CATCHERS",
            "NO_UNIQUE_PRIMARY",
            "UNRESOLVED",
            "NOT_APPLICABLE",
        }
        supported = [t for t in truths if t["outcome"] == "SUPPORTED"]
        assert all(t["causal"]["class"] == "NOT_APPLICABLE" for t in supported)

    def test_a_declaration_survives_its_own_unit_round_trip(self, cases):
        for case in cases:
            for name, entry in case["declaration"].items():
                if not isinstance(entry["value"], (int, float)):
                    continue
                if not math.isfinite(float(entry["value"])):
                    continue
                si = units.to_si(entry["value"], entry["unit"]) if entry["unit"] != "kilohm" else None
                if si is None:
                    continue
                assert math.isfinite(si)

    def test_a_span_is_never_declared_on_an_affine_scale_outside_its_probe(self, cases):
        for case in cases:
            spec = BY_ID[case["system"]]
            if case["family"] == "boundary_refusal":
                continue
            for name in spec.span_fields & set(case["declaration"]):
                assert units.is_ratio_scale(case["declaration"][name]["unit"])


class TestShadows:
    def test_every_shadow_names_a_parent_that_exists(self, shadow_records, cases):
        known = {c["case_id"] for c in cases}
        for shadow in shadow_records:
            assert shadow["parent_case_id"] in known

    def test_a_semantics_preserving_shadow_is_the_same_physical_state(
        self, shadow_records, cases
    ):
        by_id = {c["case_id"]: c for c in cases}
        checked = 0
        for shadow in shadow_records:
            if not shadow["semantics_preserving"]:
                continue
            parent = by_id[shadow["parent_case_id"]]
            for name, entry in shadow["declaration"].items():
                mine = units.to_si(entry["value"], entry["unit"])
                theirs = units.to_si(
                    parent["declaration"][name]["value"],
                    parent["declaration"][name]["unit"],
                )
                assert mine == pytest.approx(theirs, rel=1e-9), (shadow["shadow_id"], name)
            checked += 1
        assert checked > 100

    def test_the_affine_probe_declares_itself_not_semantics_preserving(
        self, shadow_records
    ):
        probes = [s for s in shadow_records if s["transformation"] == "affine_span_probe"]
        assert probes
        for probe in probes:
            assert probe["semantics_preserving"] is False
            assert probe["detail"]["invariance_expected"] is False
            assert probe["detail"]["state_reading_kelvin"] == pytest.approx(
                probe["detail"]["kelvin_span"] + 273.15
            )

    def test_every_registered_transformation_is_present(self, shadow_records):
        present = {s["transformation"] for s in shadow_records}
        assert present == set(shadows.TRANSFORMATIONS)


# =========================================================================
# blindness
# =========================================================================
class TestNoPeek:
    def test_the_challenge_imports_nothing_it_is_challenging(self):
        result = audit.run_all()
        assert result["clean"], result["checks"]

    def test_the_audit_catches_a_module_that_peeks(self):
        """A falsification test. An audit never shown to fail is a decoration."""
        proof = audit.prove_audit_catches_a_peeker()
        assert proof["audit_is_effective"], proof["detail"]
        assert all(proof["caught_by"].values())

    def test_no_forbidden_corpus_is_named_anywhere_in_the_challenge(self):
        assert audit.audit_strings() == []

    def test_the_runtime_check_sees_what_actually_loaded(self):
        assert audit.audit_runtime() == []


class TestFreezeManifest:
    def test_every_frozen_artifact_still_has_the_digest_it_was_sealed_with(self):
        result = freeze.verify()
        assert result["verified"], result

    def test_the_manifest_covers_the_whole_challenge(self):
        manifest = json.loads((BLIND / "FREEZE.json").read_text())
        covered = set(manifest["artifacts"])
        for source in freeze.FROZEN_SOURCE:
            assert source in covered
        for data in freeze.FROZEN_DATA:
            assert data in covered

    def test_the_manifest_pins_the_certified_core(self):
        manifest = json.loads((BLIND / "FREEZE.json").read_text())
        snapshot = json.loads((BLIND.parent.parent / "certification/current_core_v1.json").read_text())
        assert manifest["certified_core_tree_sha256"] == snapshot["core"]["tree_sha256"]
