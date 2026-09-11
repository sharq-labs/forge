"""Standing guards over this round's claims.

The published artifacts are the subject of most of these: a round whose report
says one thing while its JSON says another is worse than no round at all, so
the numbers quoted in ROUND_REPORT.md are pinned here against the files they
came from.

The rest are live and cheap. They check the things that would quietly stop
being true if someone refactored: that the reference branch still reaches no
engcore module, that the netlist writer still refuses to import an adapter,
and that no fixture has acquired a pre-derived quantity.

The full 49-second rebuild is marked expensive and runs on demand.
"""

import ast
import json
import pathlib
import sys

import pytest

ROUND = pathlib.Path(__file__).resolve().parent.parent

# ``adapters``, ``reference`` and ``audit`` are top-level names inside this
# round's directory, so that directory has to be importable. It is APPENDED
# rather than inserted: the repository's own ``tests`` package is a namespace
# package, and putting a directory that also contains a ``tests`` directory at
# the front of sys.path would shadow it for every other suite in the session.
#
# This is done here rather than in a conftest.py on purpose. A conftest in this
# directory would be imported as a top-level module called ``conftest``, which
# is the same name the previous round's conftest already claims, and the
# repository has test modules that do ``from conftest import ...``.
if str(ROUND) not in sys.path:
    sys.path.append(str(ROUND))


def _artifact(name):
    return json.loads((ROUND / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def surface():
    return _artifact("VALIDATION_SURFACE.json")


@pytest.fixture(scope="session")
def results():
    return _artifact("VALIDATION_RESULTS.json")


@pytest.fixture(scope="session")
def gates():
    return _artifact("SAFETY_GATES.json")


# =====================================================================
# The model surface
# =====================================================================

SHIPPED_MODELS = {
    "thermal.lumped.first_order_capacity",
    "thermal.conduction1d.linear_diffusion",
    "battery.cell.coulomb_counting",
    "battery.cell.rint_ocv",
    "battery.cell.constant_current_runtime",
    "battery.cell.peukert_capacity_derating",
    "electrical.dc.kcl",
    "electrical.dc.resistor_ohm",
    "electrical.dc.ideal_voltage_source",
    "electrical.dc.ideal_current_source",
    "electrical.dc.regulated_voltage_source",
    "electrical.dc.self_heated_resistor",
    "electrical.material.linear_tcr_resistance",
    "electrical.material.rated_linear_tcr_resistance",
    "kinetics.cstr.nonisothermal_first_order",
    "kinetics.cstr.nonisothermal_first_order_constant_rate",
}


def test_every_shipped_model_is_on_the_surface(surface):
    assert {m["model_id"] for m in surface["models"]} == SHIPPED_MODELS


def test_every_model_has_an_independent_construction_case(surface):
    without = [m["model_id"] for m in surface["models"] if m["primary_rows"] == 0]
    assert without == []


def test_no_model_disagrees(surface):
    bad = [
        (m["model_id"], m["primary_disagreements"], m["holdout_disagreements"])
        for m in surface["models"]
        if m["primary_disagreements"] or m["holdout_disagreements"]
    ]
    assert bad == []


def test_empirical_coverage_is_not_overclaimed(surface):
    """A model without an external dataset must never read as empirically validated."""
    overclaimed = [
        m["model_id"]
        for m in surface["models"]
        if m["empirical_status"] == "EXTERNAL_EVIDENCE_AGREES"
        and not m["external_dataset"]
    ]
    assert overclaimed == []


def test_most_of_the_surface_has_no_external_evidence_and_says_so(surface):
    """The honest answer is mostly NO. A round that had drifted to mostly YES
    would have started calling its own mathematics evidence."""
    counts = surface["empirical_evidence_possible_counts"]
    assert counts["NO"] >= counts["YES"]
    assert counts["NO"] + counts["PARTIAL"] + counts["YES"] == 16


# =====================================================================
# Problem construction
# =====================================================================


def test_no_quantity_arrived_altered_or_lost():
    construction = _artifact("PROBLEM_CONSTRUCTION.json")
    assert construction["fields_not_exact_or_transformed"] == []
    assert construction["counts"].get("ALTERED", 0) == 0
    assert construction["counts"].get("LOST", 0) == 0


def test_the_construction_comparison_actually_compared_something():
    construction = _artifact("PROBLEM_CONSTRUCTION.json")
    total = sum(construction["counts"].values())
    assert total >= 100, "a construction audit over a handful of fields proves little"


# =====================================================================
# The comparisons
# =====================================================================


def test_primary_and_holdout_are_clean(results):
    assert results["primary"]["disagreements"] == 0
    assert results["holdout"]["disagreements"] == 0
    assert results["primary"]["rows"] >= 100
    assert results["holdout"]["rows"] >= 40


def test_external_evidence_rows_exist(results):
    """LEVEL 4 and LEVEL 3 rows must be present, or nothing external was used."""
    levels = results["primary"]["by_evidence_level"]
    assert levels.get("LEVEL 4 external canonical implementation", 0) > 0
    assert levels.get("LEVEL 3 reference data", 0) > 0


def test_oracle_resolution_is_finer_than_the_tolerance_it_supports(results):
    """A tolerance is only meaningful if the oracle is better than it."""
    tolerance = results["tolerances"]["cstr_trajectory"]["value"]
    for key in ("cstr_rk4_arrhenius", "cstr_rk4_constant_rate"):
        assert results["oracle_self_resolution"][key] < tolerance / 100.0
    assert results["oracle_self_resolution"]["lumped_rk4"] < 1e-12


def test_every_refinement_ladder_actually_settles(results):
    for ladder in results["oracle_refinement_ladders"].values():
        assert len(ladder) >= 3


def test_cstr_steady_states_satisfy_the_species_balance(results):
    rows = results["cstr_steady_states"]
    assert rows, "the bisection found no steady state at all"
    assert all(row["verdict"] == "AGREES" for row in rows)


def test_dc_condition_numbers_are_recorded(results):
    circuits = [d for d in results["dc_diagnostics"] if "condition_number" in d]
    assert len(circuits) >= 5
    assert all(d["ngspice"] for d in circuits)


# =====================================================================
# Error shape
# =====================================================================


def test_the_slab_error_has_the_shape_its_scheme_predicts():
    shape = _artifact("ERROR_SHAPE.json")["slab"]
    assert shape["verdict"] == "ERROR_HAS_THE_PREDICTED_SHAPE"
    for order in shape["observed_spatial_orders_with_the_time_floor_removed"]:
        assert abs(order - 2.0) < 0.1
    for order in shape["observed_temporal_orders_with_the_space_floor_removed"]:
        assert abs(order - 1.0) < 0.1


def test_the_platinum_residual_is_the_next_term_of_the_expansion():
    shape = _artifact("ERROR_SHAPE.json")["platinum"]
    assert shape["verdict"] == "RESIDUAL_IS_THE_NEXT_TERM_OF_THE_EXPANSION"
    deviations = [row["observed_deviation"] for row in shape["rows"]]
    assert deviations == sorted(deviations), "the deviation must grow with temperature"
    assert deviations[-1] / deviations[0] > 20.0, (
        "if the deviation barely moved across the range, agreeing with the "
        "prediction at one end would say nothing"
    )


def test_the_dc_disagreement_is_round_off():
    shape = _artifact("ERROR_SHAPE.json")["dc_conditioning"]
    assert shape["verdict"] == "DISAGREEMENT_IS_ROUND_OFF"


def test_the_default_ngspice_disagreement_was_the_output_format():
    shape = _artifact("ERROR_SHAPE.json")["ngspice_precision"]
    assert shape["verdict"] == "THE_DEFAULT_DISAGREEMENT_WAS_THE_OUTPUT_FORMAT"
    assert shape["worst_relative_difference_twelve_figures"] < 1e-10


# =====================================================================
# Mutations and falsification
# =====================================================================


def test_construction_mutations_behaved_as_declared():
    mutations = _artifact("CONSTRUCTION_MUTATIONS.json")
    assert mutations["unexpected"] == 0
    assert mutations["caught"] == 5
    assert mutations["blind_as_expected"] == 2


def test_the_shared_precomputation_blindness_is_large_not_marginal():
    mutations = _artifact("CONSTRUCTION_MUTATIONS.json")
    ipm6 = next(m for m in mutations["mutations"] if m["id"] == "IPM-6")
    assert not ipm6["detected"]
    assert ipm6["size_of_the_undetected_error_k"] > 10.0


def test_a_netlist_from_the_core_stops_detecting_a_fault_the_fixture_catches():
    mutations = _artifact("CONSTRUCTION_MUTATIONS.json")
    ipm7 = next(m for m in mutations["mutations"] if m["id"] == "IPM-7")
    assert ipm7["detected_by_the_fixture_netlist"]
    assert not ipm7["detected_by_the_derived_netlist"]
    assert ipm7["relative_difference_against_the_fixture_netlist"] > 0.1


def test_harness_control_is_green():
    harness = _artifact("HARNESS_FALSIFICATION.json")
    assert harness["control"]["verdict"] == "GREEN"
    assert harness["control"]["disagreements"] == 0


@pytest.mark.parametrize("index", range(6))
def test_every_injected_fault_was_caught(index):
    harness = _artifact("HARNESS_FALSIFICATION.json")
    injection = harness["injections"][index]
    assert injection["verdict"] == "CAUGHT", injection["injection"]
    assert injection["disagreements"] > 0


# =====================================================================
# Independence, checked live rather than read off a file
# =====================================================================


def test_the_reference_branch_reaches_no_engcore_module():
    from audit import independence

    reached = [m for m in independence.closure("adapters.adapter_b") if m.startswith("engcore")]
    assert reached == []


def test_the_reference_branch_reaches_no_scipy_or_numpy_solver():
    from audit import independence

    closure = independence.closure("adapters.adapter_b") | independence.closure(
        "reference.physics"
    ) | independence.closure("reference.nodal")
    forbidden = [
        m
        for m in closure
        if m.startswith(("scipy.linalg", "scipy.integrate", "scipy.optimize",
                         "scipy.sparse", "numpy.linalg"))
    ]
    assert forbidden == [], (
        "the Core reaches LAPACK through scipy.linalg and integrates with "
        "solve_ivp; a reference branch that did the same would share the kernel"
    )


def test_the_import_tracer_can_see_a_dependency():
    """Guards the failure mode a previous round hit: an off-by-one in the
    relative-import arithmetic made every closure size one, and everything
    looked independent of everything."""
    from audit import independence

    check = independence.tracer_self_check()
    assert check["verdict"] == "TRACER_SEES_DEPENDENCIES"
    assert check["branch_A_engcore_modules"] > 10
    assert check["branch_A_reaches_engcore_through_function_level_imports"]


@pytest.mark.parametrize(
    "path,forbidden",
    [
        ("adapters/adapter_b.py", ("engcore", "adapter_a")),
        ("reference/spice.py", ("engcore", "adapter")),
        ("reference/physics.py", ("engcore", "adapter")),
        ("reference/nodal.py", ("engcore", "adapter")),
        ("reference/linalg.py", ("engcore", "numpy", "scipy")),
    ],
)
def test_reference_sources_name_nothing_they_must_not(path, forbidden):
    """Text, not imports. A module that merely mentioned an engcore symbol
    would be a sign the separation had started to leak."""
    tree = ast.parse((ROUND / path).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in forbidden:
        assert not any(module.startswith(name) for module in imported), (
            f"{path} imports {name}"
        )


def _imported_modules(path):
    tree = ast.parse((ROUND / path).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_the_two_adapters_do_not_share_a_conversion_helper():
    a = _imported_modules("adapters/adapter_a.py")
    b = _imported_modules("adapters/adapter_b.py")
    assert not any("adapter_b" in module for module in a)
    assert not any("adapter_a" in module for module in b)
    # Branch B must define its own factors rather than import anyone's.
    text = (ROUND / "adapters/adapter_b.py").read_text(encoding="utf-8")
    assert "MAH_TO_COULOMB = 3.6" in text
    assert "CELSIUS_OFFSET = 273.15" in text
    assert b <= {"scipy.constants", "__future__"}, (
        f"branch B should import nothing but a constants table, got {b}"
    )


# =====================================================================
# Fixtures
# =====================================================================

FIXTURE_NAMES = [
    p.name for p in sorted((ROUND / "fixtures").glob("*.json"))
]


def _identifiers(payload):
    """Keys, and short string values that function as identifiers.

    Prose is excluded deliberately. The fixtures explain in words what they are
    and why they are kept apart from the Core, and a rule that forbade the word
    would forbid the explanation. What must not appear is an engcore name in a
    position where something READS it -- a key, a node name, a component id.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key
            yield from _identifiers(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _identifiers(item)
    elif isinstance(payload, str) and len(payload) <= 40:
        yield payload


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixtures_name_no_engcore_type(name):
    payload = json.loads((ROUND / "fixtures" / name).read_text(encoding="utf-8"))
    names = list(_identifiers(payload))
    for forbidden in ("engcore", "Quantity", "CellSpecification", "ReactorRun",
                      "ThermalBody", "DCCircuit", "ConductionSlab",
                      "TemperatureDependentConductor"):
        offenders = [n for n in names if forbidden in n]
        assert offenders == [], f"{name}: {offenders}"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_quantity_keys_carry_their_unit(name):
    """A key that names no unit lets each side read it however it likes."""
    payload = json.loads((ROUND / "fixtures" / name).read_text(encoding="utf-8"))
    quantities = payload.get("quantities")
    if not quantities:
        return
    dimensionless = {
        "coulombic_efficiency", "initial_state_of_charge", "peukert_exponent",
        "n_cells", "n_steps", "published_W_100",
    }
    for key in quantities:
        if key in dimensionless:
            continue
        assert any(
            marker in key
            for marker in (
                "_g", "_mm", "_cm", "_m", "_s", "_min", "_mV", "_mA", "_mAh",
                "_mOhm", "_kohm", "_mW", "_L", "_K", "_degC", "_ppm", "_J",
                "_kJ", "_W", "_ohm", "_nOhm", "_mol", "_per_", "_C",
            )
        ), f"{name}: {key} names no unit"


def test_no_fixture_carries_a_pre_derived_quantity():
    """The derivations must stay in the adapters, done twice."""
    derived = (
        "heat_capacity_j", "conductance_w_per_k", "diffusivity",
        "beta_m3", "gamma_per_s", "reference_resistance_ohm",
        "dilution_rate",
    )
    for name in FIXTURE_NAMES:
        text = (ROUND / "fixtures" / name).read_text(encoding="utf-8")
        payload = json.loads(text)
        keys = set(payload.get("quantities", {}))
        for forbidden in derived:
            assert not any(forbidden in key for key in keys), (
                f"{name} carries {forbidden}; a quantity derived once and "
                f"shared is a quantity neither branch can check"
            )


# =====================================================================
# Tolerances and gates
# =====================================================================


def test_no_tolerance_is_justified_by_what_the_implementation_achieves(results):
    for name, entry in results["tolerances"].items():
        basis = entry["basis"].lower()
        assert "implementation" not in basis, name
        assert "passes" not in basis, name
        assert "large enough" not in basis, name


def test_preregistered_tolerances_still_match_the_plan(results):
    plan = _artifact("VALIDATION_PLAN.json")
    planned = {
        entry["case"]: entry["tolerance"]
        for entry in plan["preregistered_metrics_and_tolerances"]
    }
    for name, entry in results["tolerances"].items():
        if entry["added_after_preregistration"]:
            continue
        case = entry["plan_case"]
        if case in planned and isinstance(planned[case], (int, float)):
            assert entry.get("value") == planned[case], name


def test_all_gates_pass(gates):
    assert gates["failed"] == 0
    assert gates["passed"] == 11
    assert [g["verdict"] for g in gates["gates"]] == ["PASS"] * 11


def test_the_core_was_not_touched(gates):
    assert gates["core_unchanged"]["matches"]
    assert gates["core_unchanged"]["files_touched_under_src_or_tests"] == []


# =====================================================================
# The report against the artifacts
# =====================================================================


def test_the_report_and_the_artifacts_agree():
    audit = _artifact("CONSISTENCY_AUDIT.json")
    assert audit["verdict"] == "CONSISTENT"
    assert audit["inconsistencies"] == 0
    assert audit["numbers_missing_from_the_report"] == []
    assert audit["forbidden_reasoning_found"] == []


def test_the_consistency_checker_can_fail():
    """A green light with no bulb behind it is worse than a red one."""
    audit = _artifact("CONSISTENCY_AUDIT.json")
    assert audit["checker_self_falsification"]["verdict"] == "CHECKER_CAN_FAIL"


def test_the_consistency_checker_is_live_not_just_recorded():
    from audit import check_consistency

    assert check_consistency.self_check()["verdict"] == "CHECKER_CAN_FAIL"
    assert check_consistency.forbidden_reasoning() == []


# =====================================================================
# The full rebuild
# =====================================================================


@pytest.mark.expensive
def test_rebuilding_everything_reproduces_the_published_gates():
    from audit import build_gates

    payload = build_gates.build()
    assert payload["failed"] == 0
    assert payload["primary_disagreements"] == 0
    assert payload["holdout_disagreements"] == 0
    assert payload["core_unchanged"]["matches"]
