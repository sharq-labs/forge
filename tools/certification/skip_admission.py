"""Semantic, fail-closed admission of skipped tests in the hardened-core functional gates.

    python -m tools.certification.skip_admission probe --out FILE
    python -m tools.certification.skip_admission audit --junit FILE --availability FILE \\
        --suite junit_fast [--gate fast311] [--out FILE]

WHY A COUNT WAS THE WRONG AUTHORITY
-----------------------------------
``hardening_assurance.SKIP_CEILING`` allowed FAST 19 and SCIENTIFIC 5 skips --
the counts the last certificate measured. A ceiling says nothing about WHICH
tests skipped or why: under it, a trust test that started skipping was admitted
as long as some provider test stopped skipping, and a correct, explained
provider skip added by BIG 12/13 refused the whole run. The first complete
local run (source d5d886f9, 2026-10-08) passed every execution gate and was
refused at assurance build with 142 skips in each functional suite, almost all
of them tests bound to external solvers that the assurance runtime does not
install.

WHAT REPLACES IT
----------------
Every observed skip must be individually admitted by a committed rule, and
``unexpected == 0`` is the authority. A rule admits a skip only when ALL hold:

* the skip's node id lies in the rule's exact file and, unless the module's own
  top-level ``pytestmark`` governs every test in it, among its exact test names;
* the skip was raised in that file (the JUnit location), as ``pytest.skip``;
* its reason is EXACTLY the rule's reason, rendered with the details the
  provider availability probe itself reported -- not the test's own words;
* for an optional provider or extra: at least one declared provider is
  ``UNAVAILABLE`` according to the probe recorded in the same gate, under the
  same interpreter, and none is ``UNKNOWN``. Every registry answer is
  corroborated by an independent facet (the module or executable it looks
  for), and only an exact absence reason counts as absent: a provider whose
  probes disagree, raise, time out, or report anything else is ``UNKNOWN``,
  and ``UNKNOWN`` never admits;
* the test is not one the mutation harnesses kill with (Formal TARGETS, V4
  target tests, trust tests), not a certificate self-check and not the
  dependency guard -- those are refused even if a rule names them;
* the suite is one the rule allows (FAST or SCIENTIFIC; never the dependency
  guard, campaign or regression suites).

Three admitted classes exist. ``OPTIONAL_PROVIDER_UNAVAILABLE``: an external
solver adapter or mesh provider. ``OPTIONAL_EXTRA_UNAVAILABLE``: a declared
optional-dependency group the assurance install command does not install.
``DECLARED_CONDITIONAL_SKIP``: an exact node id whose skip is a stated property
of the tree or the process (named one by one, never a module).

WHAT AN ADMITTED SKIP DOES NOT PROVE
------------------------------------
That the skipped test ran, or that the provider it needs works. Provider
qualification is a separate activity from Core assurance; the record says
"CORE ASSURANCE PASSED WITH DECLARED OPTIONAL PROVIDERS UNAVAILABLE", never
"all providers tested". Historical counts (19, 5, 142) are kept only as
telemetry.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import importlib.util
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

AVAILABILITY_SCHEMA = "forge.provider_availability/1"
SKIP_ADMISSION_SCHEMA = "forge.skip_admission/1"

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
STATUSES = (AVAILABLE, UNAVAILABLE, UNKNOWN)

OPTIONAL_PROVIDER_UNAVAILABLE = "OPTIONAL_PROVIDER_UNAVAILABLE"
OPTIONAL_EXTRA_UNAVAILABLE = "OPTIONAL_EXTRA_UNAVAILABLE"
DECLARED_CONDITIONAL_SKIP = "DECLARED_CONDITIONAL_SKIP"
PROVIDER_CLASSES = (OPTIONAL_PROVIDER_UNAVAILABLE, OPTIONAL_EXTRA_UNAVAILABLE)
ADMITTED_CLASSES = (*PROVIDER_CLASSES, DECLARED_CONDITIONAL_SKIP)
UNEXPECTED_SKIP = "UNEXPECTED_SKIP"

CLAIM_WITH_PROVIDERS = "CORE ASSURANCE PASSED WITH DECLARED OPTIONAL PROVIDERS UNAVAILABLE"
CLAIM_WITH_PROVIDERS_AND_CONDITIONAL = (
    "CORE ASSURANCE PASSED WITH DECLARED OPTIONAL PROVIDERS UNAVAILABLE AND DECLARED CONDITIONAL SKIPS")
CLAIM_WITH_CONDITIONAL = "CORE ASSURANCE PASSED WITH DECLARED CONDITIONAL SKIPS"
CLAIM_NO_SKIPS = "CORE ASSURANCE PASSED WITH NO SKIPPED TEST"

#: The only registry reasons that mean ABSENT. ``ProviderStatus.found_but_refused`` recognises
#: three "present but refused" prefixes, but several other present-but-broken paths (no
#: distribution metadata, a missing dependency distribution, a probe that raised or timed out)
#: are also UNAVAILABLE to the registry. Here anything not on this list is UNKNOWN.
REGISTRY_ABSENCE = (
    re.compile(r"python module '[A-Za-z0-9_.]+' is not installed"),
    re.compile(r"executable '[A-Za-z0-9_.+-]+' not found"),
    re.compile(r"OpenFOAM icoFoam not found under the provider prefix"),
)
DOES_NOT_PROVE = (
    "an admitted skip is a test that did NOT execute; nothing bound to an unavailable provider was tested",
    "provider qualification is separate from Core assurance and is not claimed here",
    "a DECLARED_CONDITIONAL_SKIP is a stated property of the tree or process, not a passing test",
)

#: The functional suites a rule may admit skips in. The dependency guard, campaign and
#: regression suites are not here: a skip there is always unexpected.
ADMISSIBLE_SUITES = ("junit_fast", "junit_scientific")
#: The dependency extras the assurance runtime installs (``pip install -e ".[dev,mcp,oracles]"``).
#: An extra in this set cannot be "not installed", so it can never admit a skip.
INSTALLED_EXTRAS = ("dev", "mcp", "oracles")
DEPENDENCY_GUARD = "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared"
FORMAL_HARNESS = "tests/mutation_guards.py"


class SkipPolicyError(RuntimeError):
    """The skip policy or a protected-test source cannot be established."""


# ---------------------------------------------------------------------------
# the committed policy
# ---------------------------------------------------------------------------
FACET_KINDS = ("registry", "callable", "module_spec", "module_import", "executable")


@dataclass(frozen=True)
class Facet:
    """One way of asking whether a provider is installed.

    ``registry``      ``engcore.providers.default_registry().status(target)``: available ->
                      AVAILABLE; a reason in :data:`REGISTRY_ABSENCE` -> UNAVAILABLE; anything
                      else (present but refused, broken, timed out) -> UNKNOWN.
    ``callable``      ``module:function`` returning ``(ok, detail)``, the helper the tests use.
    ``module_spec``   ``importlib.util.find_spec(target) is None`` -> UNAVAILABLE.
    ``module_import`` importing ``target`` succeeds -> AVAILABLE, ImportError -> UNAVAILABLE.
    ``executable``    ``shutil.which(target) is None`` -> UNAVAILABLE.

    A facet that raises is UNKNOWN. Each facet records its raw observation, and its status is
    re-derived from that observation wherever the record is read (:func:`facet_status`).
    """

    kind: str
    target: str


@dataclass(frozen=True)
class OptionalProvider:
    provider_id: str
    classification: str
    facets: tuple[Facet, ...]
    #: which facet's detail renders ``{provider_id}`` in a reason template
    detail_facet: int = 0
    #: the pyproject optional-dependency group it belongs to, for an optional extra
    extra: str = ""
    module: str = ""


@dataclass(frozen=True)
class SkipRule:
    rule_id: str
    path: str
    reason: str
    classification: str
    providers: tuple[str, ...] = ()
    #: exact test names (``name[params]`` or ``Class::name``); empty only when the module's own
    #: top-level ``pytestmark`` skips every test in it on exactly this reason
    tests: tuple[str, ...] = ()
    suites: tuple[str, ...] = ADMISSIBLE_SUITES
    why: str = ""


def _registry(provider_id: str, *extra: Facet) -> tuple[Facet, ...]:
    return (Facet("registry", provider_id), *extra)


PROVIDERS: tuple[OptionalProvider, ...] = (
    # Every registry answer is corroborated by an independent facet: the module or the
    # executable the adapter's own probe looks for. Disagreement is UNKNOWN.
    OptionalProvider("calculix", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("calculix", Facet("executable", "ccx"))),
    OptionalProvider("cantera", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("cantera", Facet("module_spec", "cantera"))),
    OptionalProvider("code_aster", OPTIONAL_PROVIDER_UNAVAILABLE, _registry(
        "code_aster", Facet("executable", "run_aster"))),
    OptionalProvider("coolprop", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("coolprop", Facet("module_spec", "CoolProp"))),
    OptionalProvider("fenicsx", OPTIONAL_PROVIDER_UNAVAILABLE, _registry(
        "fenicsx", Facet("callable", "forge_fenicsx:fenicsx_available"), Facet("module_spec", "dolfinx")),
        detail_facet=1),
    # OpenFOAM is looked up under a conda provider prefix, not on PATH; its registry reason is
    # the one exact absence string the adapter writes, and nothing else admits.
    OptionalProvider("openfoam", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("openfoam")),
    OptionalProvider("openmodelica", OPTIONAL_PROVIDER_UNAVAILABLE, _registry(
        "openmodelica", Facet("executable", "omc"))),
    # forge_precice has no registry descriptor; its tests ask precice_available(), so that
    # helper is the authority, corroborated by the module being absent.
    OptionalProvider("precice", OPTIONAL_PROVIDER_UNAVAILABLE, (
        Facet("callable", "forge_precice:precice_available"), Facet("module_spec", "precice"))),
    OptionalProvider("pybamm", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("pybamm", Facet("module_spec", "pybamm"))),
    OptionalProvider("su2", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("su2", Facet("executable", "SU2_CFD"))),
    OptionalProvider("tespy", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("tespy", Facet("module_spec", "tespy"))),
    # Big Rocks G/H/I adapters. The PyPI package named `pychrono` is NOT Project Chrono: when it is installed the
    # module facet says present while the registry refuses it, and the disagreement is UNKNOWN (never admitted).
    OptionalProvider("chrono", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("chrono", Facet("module_spec", "pychrono"))),
    OptionalProvider("openvsp", OPTIONAL_PROVIDER_UNAVAILABLE, _registry("openvsp", Facet("module_spec", "openvsp"))),
    OptionalProvider("openradioss", OPTIONAL_PROVIDER_UNAVAILABLE, _registry(
        "openradioss", Facet("executable", "engine_linux64_gf"))),
    OptionalProvider("gmsh", OPTIONAL_PROVIDER_UNAVAILABLE, (
        Facet("callable", "engcore.spatial:gmsh_available"), Facet("module_spec", "gmsh")),
        extra="mesh", module="gmsh"),
    OptionalProvider("sympy", OPTIONAL_EXTRA_UNAVAILABLE, (Facet("module_spec", "sympy"),),
                     extra="symbolic", module="sympy"),
    OptionalProvider("meshio", OPTIONAL_EXTRA_UNAVAILABLE, (Facet("module_spec", "meshio"),),
                     extra="mesh", module="meshio"),
    OptionalProvider("psutil", OPTIONAL_EXTRA_UNAVAILABLE, (
        Facet("module_spec", "psutil"), Facet("module_import", "psutil")), extra="benchmarks", module="psutil"),
    OptionalProvider("jsonschema", OPTIONAL_EXTRA_UNAVAILABLE, (
        Facet("module_spec", "jsonschema"), Facet("module_import", "jsonschema")),
        extra="benchmarks", module="jsonschema"),
)

_P, _E, _C = OPTIONAL_PROVIDER_UNAVAILABLE, OPTIONAL_EXTRA_UNAVAILABLE, DECLARED_CONDITIONAL_SKIP

RULES: tuple[SkipRule, ...] = (
    # --- BIG 13 flagships: each module's pytestmark requires its whole provider stack ----------
    SkipRule("flagship-battery", "flagships/tests/test_flagship_battery.py",
             "PyBaMM and TESPy are both required", _P, ("pybamm", "tespy")),
    SkipRule("flagship-cavity", "flagships/tests/test_flagship_cavity.py",
             "OpenFOAM, SU2 and CoolProp are all required", _P, ("openfoam", "su2", "coolprop")),
    SkipRule("flagship-chemistry", "flagships/tests/test_flagship_chemistry.py",
             "Cantera and TESPy are both required", _P, ("cantera", "tespy")),
    SkipRule("flagship-thermo-mechanical", "flagships/tests/test_flagship_thermo_mechanical.py",
             "FEniCSx, CalculiX and Code_Aster are all required", _P, ("fenicsx", "calculix", "code_aster")),
    # --- BIG 11/12 provider adapters ------------------------------------------------------------
    SkipRule("calculix", "providers/calculix/tests/test_calculix_provider.py",
             "CalculiX or FEniCSx/Gmsh unavailable", _P, ("calculix", "fenicsx", "gmsh")),
    SkipRule("cantera", "providers/cantera/tests/test_cantera_provider.py", "Cantera unavailable", _P, ("cantera",)),
    SkipRule("code-aster", "providers/code_aster/tests/test_code_aster_provider.py",
             "Code_Aster or Gmsh unavailable", _P, ("code_aster", "gmsh")),
    SkipRule("code-aster-vs-calculix", "providers/code_aster/tests/test_code_aster_provider.py",
             "CalculiX unavailable", _P, ("calculix",),
             tests=("test_code_aster_executes_and_corroborates_calculix_on_the_same_records",)),
    SkipRule("coolprop", "providers/coolprop/tests/test_coolprop_provider.py", "CoolProp unavailable", _P,
             ("coolprop",), tests=(
                 "test_explicit_properties_are_computed_records_bound_to_request_and_provider",
                 "test_two_phase_quality_and_refusals_are_explicit",
                 "test_request_is_content_only_and_the_reference_state_is_pinned")),
    SkipRule("fenicsx-coupling", "providers/fenicsx/tests/test_coupling_fenicsx.py",
             "FEniCSx or Gmsh unavailable", _P, ("fenicsx", "gmsh")),
    SkipRule("fenicsx-multiscale", "providers/fenicsx/tests/test_multiscale_fenicsx.py",
             "FEniCSx or Gmsh unavailable", _P, ("fenicsx", "gmsh")),
    SkipRule("fenicsx-pde", "providers/fenicsx/tests/test_pde_fenicsx.py",
             "FEniCSx: {fenicsx}; Gmsh: {gmsh}", _P, ("fenicsx", "gmsh"), tests=(
                 "test_steady_two_material_conduction_matches_series_solution_and_is_a_big7_field",
                 "test_material_change_changes_solution_and_identity",
                 "test_celsius_boundary_value_is_converted_not_confused",
                 "test_plane_stress_elasticity_returns_framed_vector_field",
                 "test_transient_heat_with_environment_robin_bc_on_big2_window",
                 "test_lifecycle_moisture_changes_the_next_real_pde_solve",
                 "test_two_resolutions_are_compared_not_validated",
                 "test_replay_reproduces_identity_and_values_within_declared_tolerance",
                 "test_failed_solve_exposes_no_field",
                 "test_p2_node_mapping_matches_analytic_solution")),
    SkipRule("fenicsx-pde-gmsh-mesh", "providers/fenicsx/tests/test_pde_fenicsx.py", "{gmsh}", _P, ("gmsh",),
             tests=("test_identity_changes_with_bc_and_mesh_and_refusals",
                    "test_missing_or_unknown_material_property_refuses_before_solve")),
    SkipRule("fenicsx-pde-gmsh-record", "providers/fenicsx/tests/test_pde_fenicsx.py", "Gmsh: {gmsh}", _P,
             ("gmsh",), tests=("test_execution_record_refuses_fabricated_fields",)),
    SkipRule("openfoam", "providers/openfoam/tests/test_openfoam_provider.py", "OpenFOAM unavailable", _P,
             ("openfoam",)),
    SkipRule("openmodelica", "providers/openmodelica/tests/test_openmodelica_provider.py",
             "OpenModelica unavailable", _P, ("openmodelica",)),
    SkipRule("precice", "providers/precice/tests/test_precice_provider.py", "preCICE unavailable: {precice}", _P,
             ("precice",), tests=(
                 "test_precice_two_way_coupling_really_runs_and_matches_forge_fixed_point",
                 "test_precice_iteration_limit_is_refused_even_though_precice_continues")),
    SkipRule("pybamm-coupling-options", "providers/pybamm/tests/test_pybamm_coupling_options.py",
             "PyBaMM is required", _P, ("pybamm",)),
    SkipRule("pybamm-multiphysics", "providers/pybamm/tests/test_pybamm_multiphysics.py",
             "PyBaMM and TESPy are both required", _P, ("pybamm", "tespy")),
    SkipRule("pybamm-multiscale", "providers/pybamm/tests/test_pybamm_multiscale.py",
             "PyBaMM unavailable", _P, ("pybamm",)),
    SkipRule("pybamm", "providers/pybamm/tests/test_pybamm_provider.py", "PyBaMM unavailable", _P, ("pybamm",),
             tests=(
                 "test_proof_a_discharge_records_voltage_current_soc_temperature",
                 "test_proof_a_charge_discharge_cycle_and_infeasible_request_fails_closed",
                 "test_proof_a_temperature_dependence_is_real_and_bound_to_identity",
                 "test_capacity_fade_mapping_changes_the_cell_and_the_identity",
                 "test_proof_h_ambient_and_current_come_from_exact_big3_big2_records")),
    SkipRule("pybamm-system-runtime", "providers/pybamm/tests/test_system_runtime_battery.py",
             "PyBaMM and TESPy are both required", _P, ("pybamm", "tespy")),
    SkipRule("su2", "providers/su2/tests/test_su2_provider.py", "SU2 unavailable", _P, ("su2",)),
    SkipRule("su2-vs-openfoam", "providers/su2/tests/test_su2_provider.py", "OpenFOAM unavailable", _P,
             ("openfoam",), tests=(
                 "test_proof_e_openfoam_vs_su2_whole_field_disagrees_near_the_lid_recorded_negative_result",
                 "test_proof_e_openfoam_vs_su2_lower_half_corroborate_and_converge_with_refinement")),
    SkipRule("tespy", "providers/tespy/tests/test_tespy_provider.py", "TESPy unavailable", _P, ("tespy",)),
    # --- Big Rocks: provider adapters whose real-run qualification tests need the provider ----------
    SkipRule("chrono", "providers/chrono/tests/test_chrono_adapter.py", "Project Chrono unavailable", _P, ("chrono",),
             tests=("test_pendulum_period_matches_the_analytic_reference[sparse_qr]",
                    "test_pendulum_period_matches_the_analytic_reference[sparse_lu]")),
    SkipRule("openvsp", "providers/openvsp/tests/test_openvsp_adapter.py", "OpenVSP unavailable", _P, ("openvsp",),
             tests=("test_real_openvsp_build_meshes_through_the_gmsh_adapter",)),
    SkipRule("openradioss", "providers/openradioss/tests/test_openradioss_adapter.py", "OpenRadioss unavailable", _P,
             ("openradioss",), tests=("test_real_impact_run_conserves_energy_before_contact",)),
    SkipRule("geometry-slice-gmsh", "flagships/tests/test_geometry_slice.py", "Gmsh unavailable: {gmsh}", _P, ("gmsh",),
             tests=("test_slice_runs_end_to_end_and_ends_at_insufficient_evidence",
                    "test_every_result_changing_input_moves_the_bound_identities",
                    "test_face_temperatures_outside_the_material_data_are_out_of_domain_even_when_the_mean_is_inside")),
    # --- core suites that exercise an optional mesh provider or dependency extra --------------
    SkipRule("spatial-gmsh", "tests/test_spatial_core.py", "Gmsh unavailable: {gmsh}", _P, ("gmsh",),
             tests=("test_gmsh_plate_is_real_exact_and_replayable",)),
    SkipRule("spatial-meshio", "tests/test_spatial_core.py", "meshio unavailable (the 'mesh' extra)", _E,
             ("meshio",), tests=("test_meshio_roundtrip_preserves_identity",
                                 "test_duplicate_facet_and_flattening_are_refused")),
    SkipRule("foundations-geometry-gmsh", "tests/foundations/test_geometry_foundation.py", "Gmsh unavailable: {gmsh}", _P,
             ("gmsh",), tests=(
                 "test_gmsh_2d_plate_maps_every_declared_entity_and_is_deterministic",
                 "test_gmsh_3d_cutout_and_interface_measures", "test_gmsh_refuses_rather_than_guessing",
                 "test_region_material_map_follows_geometry_bindings",
                 "test_imported_geometry_requires_and_checks_declared_units",
                 "test_review_h1_swapped_or_foreign_mesh_binding_is_refused",
                 "test_review_h2_flush_faces_of_other_bodies_and_internal_faces_are_not_boundaries",
                 "test_review_m1_m6_thin_bodies_and_foreign_frames_are_refused")),
    SkipRule("pde-contracts-gmsh", "tests/test_pde_contracts.py", "{gmsh}", _P, ("gmsh",), tests=(
        "test_identity_changes_with_bc_and_mesh_and_refusals",
        "test_missing_or_unknown_material_property_refuses_before_solve")),
    SkipRule("numerical-sympy", "tests/test_numerical_foundation.py", "SymPy unavailable (the 'symbolic' extra)",
             _E, ("sympy",), tests=("test_symbolic_operator_identity_is_derived_and_its_jacobian_solves",
                                    "test_symbolic_system_refuses_undeclared_symbols")),
    SkipRule("benchmarks-extra-psutil", "tests/test_core_api_contracts.py",
             "the [benchmarks] extra is not installed in this environment", _E, ("psutil",),
             tests=("test_a_declared_extra_can_actually_import[benchmarks-psutil]",)),
    SkipRule("benchmarks-extra-jsonschema", "tests/test_core_api_contracts.py",
             "the [benchmarks] extra is not installed in this environment", _E, ("jsonschema",),
             tests=("test_a_declared_extra_can_actually_import[benchmarks-jsonschema]",)),
    # --- declared conditional skips: exact node ids, each with its reason ----------------------
    SkipRule("reason-truth-no-repair-U00048", "tests/oracles/test_independent_reason_truth.py",
             "U00048 has only conditions with no defined repair", _C,
             tests=("test_every_repair_moves_the_condition_it_targets[U00048]",),
             why="the case's violated conditions are all NOT_REPAIRABLE, so no counterfactual exists to check"),
    SkipRule("reason-truth-no-repair-U01031", "tests/oracles/test_independent_reason_truth.py",
             "U01031 has only conditions with no defined repair", _C,
             tests=("test_every_repair_moves_the_condition_it_targets[U01031]",),
             why="the case's violated conditions are all NOT_REPAIRABLE, so no counterfactual exists to check"),
    SkipRule("freeze-exact-domain-digest", "tests/test_core_freeze_manifest.py",
             "this tree is a descendant; the domain digest is informational", _C,
             tests=("test_on_the_exact_freeze_the_domain_digest_binds",),
             why="binds only on the exact V1 freeze commit; the test skips only in DESCENDANT mode and "
                 "fails in any other non-exact mode, and the descendant checks apply instead"),
    # Not admitted: tests/test_blind_challenge_guards.py::test_importing_the_truth_layer_loads_no_runtime_module
    # used to skip whenever its pytest worker had already imported engcore -- in every gate. It now
    # runs its check in a fresh interpreter and never skips.
)


@dataclass(frozen=True)
class SkipPolicy:
    providers: tuple[OptionalProvider, ...] = PROVIDERS
    rules: tuple[SkipRule, ...] = RULES

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(p.provider_id for p in self.providers)

    def provider(self, provider_id: str) -> OptionalProvider | None:
        return next((p for p in self.providers if p.provider_id == provider_id), None)

    def digest(self) -> str:
        payload = {"providers": [asdict(p) for p in self.providers], "rules": [asdict(r) for r in self.rules]}
        return hashlib.sha256(_canonical(payload)).hexdigest()


DEFAULT_POLICY = SkipPolicy()
_PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def render_reason(template: str, details: Mapping[str, str]) -> str:
    """``template`` with each ``{provider_id}`` replaced by that provider's probe detail."""
    def substitute(found: re.Match[str]) -> str:
        key = found.group(1)
        if key not in details:
            raise SkipPolicyError(f"no probe detail for {key!r}")
        return details[key]
    return _PLACEHOLDER.sub(substitute, template)


def policy_problems(policy: SkipPolicy = DEFAULT_POLICY, root: pathlib.Path | None = None,
                    *, trust_script: str | None = None) -> list[str]:
    """Why the policy is not narrow and well-formed. With ``root``, also against that tree."""
    problems: list[str] = []
    ids = policy.provider_ids
    if len(set(ids)) != len(ids):
        problems.append("duplicate provider ids")
    for provider in policy.providers:
        if provider.classification not in PROVIDER_CLASSES:
            problems.append(f"provider {provider.provider_id}: classification {provider.classification!r}")
        if not provider.facets or not 0 <= provider.detail_facet < len(provider.facets):
            problems.append(f"provider {provider.provider_id}: no usable probe facet")
        for facet in provider.facets:
            if facet.kind not in FACET_KINDS:
                problems.append(f"provider {provider.provider_id}: unknown facet kind {facet.kind!r}")
        if provider.classification == OPTIONAL_EXTRA_UNAVAILABLE and not provider.extra:
            problems.append(f"provider {provider.provider_id}: an optional extra must name its group")
        if provider.extra and provider.extra in INSTALLED_EXTRAS:
            problems.append(f"provider {provider.provider_id}: extra {provider.extra!r} is installed by assurance")
    rule_ids = [r.rule_id for r in policy.rules]
    if len(set(rule_ids)) != len(rule_ids):
        problems.append("duplicate rule ids")
    for rule in policy.rules:
        label = f"rule {rule.rule_id}"
        if not rule.path.endswith(".py") or any(c in rule.path for c in "*?[]\\") or rule.path.startswith(("/", ".")) \
                or ".." in rule.path.split("/") or not rule.path.startswith(("tests/", "providers/", "flagships/")):
            problems.append(f"{label}: path {rule.path!r} is not one exact test file")
        if rule.classification not in ADMITTED_CLASSES:
            problems.append(f"{label}: classification {rule.classification!r}")
        if not set(rule.suites) <= set(ADMISSIBLE_SUITES) or not rule.suites:
            problems.append(f"{label}: suites {rule.suites!r}")
        if not rule.reason.strip():
            problems.append(f"{label}: empty reason")
        if any(not t or any(c in t for c in "*?") for t in rule.tests) or len(set(rule.tests)) != len(rule.tests):
            problems.append(f"{label}: tests must be exact, distinct names")
        placeholders = set(_PLACEHOLDER.findall(rule.reason))
        if rule.classification == DECLARED_CONDITIONAL_SKIP:
            if rule.providers or placeholders:
                problems.append(f"{label}: a conditional skip names no provider")
            if not rule.tests:
                problems.append(f"{label}: a conditional skip must name its exact tests, never a module")
            if not rule.why:
                problems.append(f"{label}: a conditional skip must state why")
        else:
            if not rule.providers:
                problems.append(f"{label}: a provider skip must name its provider")
            for pid in rule.providers:
                provider = policy.provider(pid)
                if provider is None:
                    problems.append(f"{label}: unknown provider {pid!r}")
                elif provider.classification != rule.classification:
                    problems.append(f"{label}: provider {pid} is {provider.classification}, not {rule.classification}")
            if not placeholders <= set(rule.providers):
                problems.append(f"{label}: reason renders a provider it does not declare")
    for index, left in enumerate(policy.rules):
        for right in policy.rules[index + 1:]:
            if left.path != right.path or left.reason != right.reason:
                continue
            if not left.tests or not right.tests or set(left.tests) & set(right.tests):
                problems.append(f"rules {left.rule_id} and {right.rule_id} overlap on {left.path}")
    if root is not None:
        problems += _tree_policy_problems(policy, root, trust_script=trust_script)
    return problems


def _tree_policy_problems(policy: SkipPolicy, root: pathlib.Path, *, trust_script: str | None) -> list[str]:
    problems: list[str] = []
    try:
        files, nodeids = protected_tests(root, trust_script=trust_script)
    except SkipPolicyError as exc:
        return [f"protected tests cannot be established: {exc}"]
    for rule in policy.rules:
        target = root / rule.path
        if not target.is_file():
            problems.append(f"rule {rule.rule_id}: {rule.path} does not exist")
            continue
        if rule.path in files or any(f"{rule.path}::{t}" in nodeids for t in rule.tests):
            problems.append(f"rule {rule.rule_id}: {rule.path} holds hardened-core trust tests")
        tree = ast.parse(target.read_bytes().decode("utf-8-sig"))
        defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for test in rule.tests:
            if test.split("[", 1)[0].split("::")[-1] not in defined:
                problems.append(f"rule {rule.rule_id}: {rule.path} defines no {test}")
        if not rule.tests and not _module_pytestmark_reason(tree, rule.reason):
            problems.append(f"rule {rule.rule_id}: {rule.path} has no top-level pytestmark skipif "
                            f"with reason {rule.reason!r}, so module scope is not the module's own")
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        import tomllib
        extras = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get(
            "optional-dependencies", {})
        for provider in policy.providers:
            if not provider.extra:
                continue
            group = [re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip().lower() for spec in extras.get(provider.extra, ())]
            if provider.module.lower() not in group:
                problems.append(f"provider {provider.provider_id}: not declared in the [{provider.extra}] extra")
    return problems


def _module_pytestmark_reason(tree: ast.Module, reason: str) -> bool:
    """Whether the module assigns ``pytestmark = pytest.mark.skipif(..., reason=<reason>)`` at top level."""
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "pytestmark" for t in node.targets)):
            continue
        call = node.value
        if isinstance(call, ast.Call) and getattr(call.func, "attr", None) == "skipif":
            for keyword in call.keywords:
                if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant) and keyword.value.value == reason:
                    return True
    return False


# ---------------------------------------------------------------------------
# tests that must never be skipped
# ---------------------------------------------------------------------------
def _literal_tuple(path: pathlib.Path, name: str) -> tuple[str, ...]:
    if not path.is_file():
        raise SkipPolicyError(f"{path.name} is missing")
    tree = ast.parse(path.read_bytes().decode("utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, (tuple, list)) and all(isinstance(v, str) for v in value):
                return tuple(value)
    raise SkipPolicyError(f"{path.name} declares no literal {name}")


def _existing_test_files(root: pathlib.Path, entries: Iterable[str], source: str) -> set[str]:
    """Protection is by exact file: a directory or a missing path would protect nothing."""
    files = set(entries)
    bad = sorted(f for f in files if not f.endswith(".py") or not (root / f).is_file())
    if bad:
        raise SkipPolicyError(f"{source} names {bad[:5]}, which are not existing test files")
    return files


def protected_tests(root: pathlib.Path, *, trust_script: str | None = None) -> tuple[frozenset[str], frozenset[str]]:
    """``(files, nodeids)`` whose skip is never admissible, read from the tree at ``root``.

    Files: the Formal harness's TARGETS, the trust runner's TESTS and every V4 entry's target test
    file -- the suites whose failure is what kills a certified mutant. Node ids: the certificate
    self-checks and the dependency guard.
    """
    from tools.certification import mutation_population
    from tools.certification.recertification_scope import CERTIFICATE_SELF_CHECKS

    if trust_script is None:
        raise SkipPolicyError("the trust runner path was not given")
    files = _existing_test_files(root, _literal_tuple(root / FORMAL_HARNESS, "TARGETS"), "the Formal TARGETS")
    files |= _existing_test_files(root, _literal_tuple(root / trust_script, "TESTS"), "the trust TESTS")
    try:
        entries = mutation_population.v4_entries(root)
    except Exception as exc:  # the V4 population is part of what must be established
        raise SkipPolicyError(f"V4 target tests: {type(exc).__name__}: {exc}") from exc
    files |= _existing_test_files(root, {str(entry[4]).split("::", 1)[0] for entry in entries}, "the V4 targets")
    return frozenset(files), frozenset({*CERTIFICATE_SELF_CHECKS, DEPENDENCY_GUARD})


# ---------------------------------------------------------------------------
# provider availability, in the gate's own interpreter
# ---------------------------------------------------------------------------
def _pytest_roots(root: pathlib.Path) -> list[pathlib.Path]:
    import tomllib
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    roots = config["tool"]["pytest"]["ini_options"]["pythonpath"]
    return [root / entry for entry in roots]


def _facet(facet: Facet, registry: Any) -> dict[str, Any]:
    """One facet's raw observation, and the status :func:`facet_status` derives from it."""
    import shutil

    row: dict[str, Any] = {"kind": facet.kind, "target": facet.target}
    try:
        if facet.kind == "registry":
            if isinstance(registry, Exception):
                raise registry
            status = registry.status(facet.target)
            row.update(available=bool(status.available), found_but_refused=bool(status.found_but_refused),
                       detail=str(status.reason or status.version), version=str(status.version))
        elif facet.kind == "callable":
            module, _, name = facet.target.partition(":")
            ok, detail = getattr(importlib.import_module(module), name)()
            row.update(ok=bool(ok), detail=str(detail))
        elif facet.kind == "module_spec":
            present = importlib.util.find_spec(facet.target) is not None
            row.update(present=present, detail="present" if present else f"no module named {facet.target!r}")
        elif facet.kind == "module_import":
            try:
                importlib.import_module(facet.target)
            except ImportError as exc:
                row.update(imported=False, detail=f"{type(exc).__name__}: {exc}")
            else:
                row.update(imported=True, detail="imported")
        elif facet.kind == "executable":
            path = shutil.which(facet.target) or ""
            row.update(path=path, detail=path or f"executable {facet.target!r} not on PATH")
        else:
            row.update(error=f"unknown facet kind {facet.kind!r}", detail=f"unknown facet kind {facet.kind!r}")
    except Exception as exc:
        row.update(error=f"{type(exc).__name__}: {exc}", detail=f"probe raised {type(exc).__name__}: {exc}")
    row["status"] = facet_status(row)
    return row


def facet_status(row: Mapping[str, Any]) -> str:
    """A facet's status from its raw observation alone. A recorded ``status`` is never read here."""
    if not isinstance(row, Mapping) or row.get("error") is not None or row.get("kind") not in FACET_KINDS:
        return UNKNOWN
    kind, detail = row["kind"], row.get("detail")
    if not isinstance(detail, str):
        return UNKNOWN
    if kind == "registry":
        available, refused = row.get("available"), row.get("found_but_refused")
        if not isinstance(available, bool) or not isinstance(refused, bool):
            return UNKNOWN
        if available:
            return UNKNOWN if refused else AVAILABLE
        if refused or not any(pattern.fullmatch(detail) for pattern in REGISTRY_ABSENCE):
            return UNKNOWN
        return UNAVAILABLE
    field = {"callable": "ok", "module_spec": "present", "module_import": "imported"}.get(kind)
    if field is not None:
        value = row.get(field)
        return UNKNOWN if not isinstance(value, bool) else (AVAILABLE if value else UNAVAILABLE)
    path = row.get("path")  # executable
    return UNKNOWN if not isinstance(path, str) else (AVAILABLE if path else UNAVAILABLE)


def aggregate(facets: Sequence[Mapping[str, Any]]) -> str:
    """One status from every facet, each re-derived from its observation: agreement or UNKNOWN."""
    statuses = [facet_status(row) for row in facets]
    if not statuses or any(s not in STATUSES for s in statuses) or UNKNOWN in statuses:
        return UNKNOWN
    if all(s == AVAILABLE for s in statuses):
        return AVAILABLE
    if all(s == UNAVAILABLE for s in statuses):
        return UNAVAILABLE
    return UNKNOWN


def probe(root: pathlib.Path, policy: SkipPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Every policy provider's availability, asked the way its tests ask, under pytest's import roots."""
    for entry in reversed(_pytest_roots(root)):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    try:
        from engcore.providers import default_registry
        registry: Any = default_registry()
    except Exception as exc:
        registry = exc
    providers: dict[str, Any] = {}
    for provider in policy.providers:
        facets = [_facet(facet, registry) for facet in provider.facets]
        providers[provider.provider_id] = {
            "classification": provider.classification,
            "status": aggregate(facets),
            "detail": str(facets[provider.detail_facet].get("detail", "")),
            "facets": facets,
        }
    return {
        "schema": AVAILABILITY_SCHEMA,
        "python": f"Python {sys.version.split()[0]}",
        "policy_sha256": policy.digest(),
        "providers": providers,
    }


def availability_statuses(document: Any, policy: SkipPolicy = DEFAULT_POLICY) -> tuple[dict[str, dict[str, str]], list[str]]:
    """``provider -> {status, detail}`` re-derived from the recorded facets, plus problems.

    No recorded status is believed: every facet's status is re-derived from its raw observation
    (:func:`facet_status`, with the registry absence allowlist) and the provider's from those. A
    provider the document does not carry, or carries inconsistently, is UNKNOWN. Facets edited
    consistently by hand are not detectable here; ``local_assurance verify`` binds them to the
    frozen evidence file the gate wrote.
    """
    problems: list[str] = []
    statuses = {pid: {"status": UNKNOWN, "detail": ""} for pid in policy.provider_ids}
    if not isinstance(document, Mapping) or document.get("schema") != AVAILABILITY_SCHEMA:
        return statuses, ["provider availability evidence is absent or has the wrong schema"]
    if document.get("policy_sha256") != policy.digest():
        problems.append("provider availability was probed under a different skip policy")
        return statuses, problems
    rows = document.get("providers")
    if not isinstance(rows, Mapping) or set(rows) != set(policy.provider_ids):
        return statuses, problems + ["provider availability does not cover exactly the policy's providers"]
    for pid in policy.provider_ids:
        row = rows[pid]
        facets = row.get("facets") if isinstance(row, Mapping) else None
        provider = policy.provider(pid)
        if not isinstance(facets, list) or provider is None or len(facets) != len(provider.facets) or any(
                not isinstance(f, Mapping) or (f.get("kind"), f.get("target")) != (e.kind, e.target)
                for f, e in zip(facets, provider.facets)):
            problems.append(f"provider {pid}: probe facets do not match the policy")
            continue
        stale = [f.get("kind") for f in facets if f.get("status") != facet_status(f)]
        if stale:
            problems.append(f"provider {pid}: recorded facet status disagrees with its observation {stale}")
            continue
        derived = aggregate(facets)
        if row.get("status") != derived:
            problems.append(f"provider {pid}: recorded {row.get('status')!r} but its facets say {derived}")
            continue
        detail = facets[provider.detail_facet].get("detail")
        if not isinstance(detail, str) or row.get("detail") != detail:
            problems.append(f"provider {pid}: recorded detail is not its probe's")
            continue
        statuses[pid] = {"status": derived, "detail": detail}
    return statuses, problems


# ---------------------------------------------------------------------------
# reading the skips a JUnit report records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ObservedSkip:
    nodeid: str
    path: str
    test: str
    reason: str
    location: str
    malformed: str = ""

    def row(self) -> dict[str, str]:
        return {"nodeid": self.nodeid, "reason": self.reason, "location": self.location}


def _resolve(classname: str, name: str, located: str) -> tuple[str, str] | None:
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = "/".join(parts[:cut]) + ".py"
        if located == candidate or located.endswith("/" + candidate):
            return candidate, "::".join([*parts[cut:], name])
    return None


def junit_skips(xml_bytes: bytes) -> tuple[list[ObservedSkip], list[str]]:
    """Every skipped testcase, with its node id, reason and location; plus report-level problems."""
    try:
        document = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        return [], [f"not a JUnit report ({exc})"]
    suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
    declared = 0
    problems: list[str] = []
    for suite in suites:
        try:
            declared += int(suite.get("skipped", "0"))
        except ValueError:
            problems.append("a testsuite declares a non-integer skip count")
    skips: list[ObservedSkip] = []
    for case in document.iter("testcase"):
        marks = case.findall("skipped")
        if not marks:
            continue
        classname, name = case.get("classname") or "", case.get("name") or ""
        raw = f"{classname}::{name}"
        if len(marks) != 1:
            skips.append(ObservedSkip(raw, "", name, "", "", "a testcase carries more than one skip"))
            continue
        mark = marks[0]
        message, text = mark.get("message"), mark.text or ""
        problem = ""
        if mark.get("type") != "pytest.skip":
            problem = f"skip type {mark.get('type')!r} is not pytest.skip"
        elif not classname or not name or message is None:
            problem = "the skip carries no classname, name or reason"
        elif not text.endswith(": " + message):
            problem = "the skip's location text does not carry its reason"
        if problem:
            skips.append(ObservedSkip(raw, "", name, message or "", "", problem))
            continue
        located, _, line = text[: -len(": " + message)].rpartition(":")
        resolved = _resolve(classname, name, located) if line.isdigit() else None
        if resolved is None:
            skips.append(ObservedSkip(raw, "", name, message, "",
                                      "the skip was not raised in the test's own module"))
            continue
        path, test = resolved
        skips.append(ObservedSkip(f"{path}::{test}", path, test, message, f"{path}:{line}"))
    if declared != len(skips):
        problems.append(f"the report declares {declared} skipped but carries {len(skips)} skipped testcases")
    return skips, problems


# ---------------------------------------------------------------------------
# admission
# ---------------------------------------------------------------------------
def classify(skip: ObservedSkip, *, suite: str, statuses: Mapping[str, Mapping[str, str]],
             protected: tuple[frozenset[str], frozenset[str]] | None, policy: SkipPolicy = DEFAULT_POLICY,
             ) -> dict[str, Any]:
    """The admission decision for one skip. ``admitted`` is True only when every fact holds."""
    row: dict[str, Any] = {**skip.row(), "suite": suite}

    def refuse(why: str) -> dict[str, Any]:
        return {**row, "classification": UNEXPECTED_SKIP, "admitted": False, "refused_because": why}

    if skip.malformed:
        return refuse(f"malformed skip metadata: {skip.malformed}")
    if protected is None:
        return refuse("the hardened-core trust tests could not be established, so no skip is admissible")
    files, nodeids = protected
    if skip.path in files or skip.nodeid in nodeids:
        return refuse("a hardened-core trust test skipped; no rule can admit it")
    scoped = [r for r in policy.rules if r.path == skip.path and (not r.tests or skip.test in r.tests)]
    if not scoped:
        return refuse("no committed rule covers this node id")
    scoped = [r for r in scoped if suite in r.suites]
    if not scoped:
        return refuse(f"no committed rule admits skips in {suite}")
    details = {pid: s.get("detail", "") for pid, s in statuses.items()}
    rule = None
    for candidate in scoped:
        try:
            rendered = render_reason(candidate.reason, details)
        except SkipPolicyError:
            continue
        if rendered == skip.reason:
            rule = candidate
            break
    if rule is None:
        return refuse("the reason is not the declared reason rendered from the provider probe")
    row.update(rule_id=rule.rule_id, classification=rule.classification)
    if rule.classification == DECLARED_CONDITIONAL_SKIP:
        return {**row, "providers": {}, "admitted": True}
    observed = {pid: str((statuses.get(pid) or {}).get("status", UNKNOWN)) for pid in rule.providers}
    row["providers"] = observed
    if any(policy.provider(pid) is None for pid in rule.providers):
        return refuse("the rule names a provider the policy does not know")
    if any(state not in (AVAILABLE, UNAVAILABLE) for state in observed.values()):
        return refuse("provider availability could not be established (UNKNOWN never admits)")
    if UNAVAILABLE not in observed.values():
        return refuse("every declared provider is AVAILABLE, so this is not provider unavailability")
    return {**row, "admitted": True}


def inventory_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    """Digest of an admission inventory; independent of gate and interpreter, ordered by node id."""
    keys = ("suite", "nodeid", "reason", "location", "classification", "rule_id", "providers", "admitted")
    canonical = sorted(_canonical([[k, row.get(k)] for k in keys]).decode("ascii") for row in rows)
    return sha256_bytes(_canonical(canonical))


def admit_suite(xml_bytes: bytes, *, suite: str, statuses: Mapping[str, Mapping[str, str]],
                protected: tuple[frozenset[str], frozenset[str]] | None,
                policy: SkipPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Every skip in one JUnit report, admitted or not, with the suite's totals."""
    skips, problems = junit_skips(xml_bytes)
    rows = [classify(s, suite=suite, statuses=statuses, protected=protected, policy=policy) for s in skips]
    rows.sort(key=lambda r: (r["nodeid"], r["reason"]))
    accepted = [r for r in rows if r["admitted"]]
    unexpected = [r for r in rows if not r["admitted"]]
    return {
        "suite": suite,
        "skipped": len(rows),
        "accepted": len(accepted),
        "unexpected": len(unexpected),
        "report_problems": problems,
        "inventory_sha256": inventory_digest(rows),
        "rows": rows,
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Telemetry: skips per class, per rule, and per unavailable provider (a row with two absent
    providers counts once for each)."""
    by_class: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    for row in rows:
        by_class[row.get("classification", "")] = by_class.get(row.get("classification", ""), 0) + 1
        by_rule[str(row.get("rule_id"))] = by_rule.get(str(row.get("rule_id")), 0) + 1
        for pid, state in (row.get("providers") or {}).items():
            if state == UNAVAILABLE:
                by_provider[pid] = by_provider.get(pid, 0) + 1
    return {"by_classification": dict(sorted(by_class.items())), "by_rule": dict(sorted(by_rule.items())),
            "by_unavailable_provider": dict(sorted(by_provider.items()))}


def claim(rows: Sequence[Mapping[str, Any]]) -> str:
    providers = any(r.get("classification") in PROVIDER_CLASSES for r in rows)
    conditional = any(r.get("classification") == DECLARED_CONDITIONAL_SKIP for r in rows)
    if providers and conditional:
        return CLAIM_WITH_PROVIDERS_AND_CONDITIONAL
    if providers:
        return CLAIM_WITH_PROVIDERS
    if conditional:
        return CLAIM_WITH_CONDITIONAL
    return CLAIM_NO_SKIPS


def readmission_problems(stored_rows: Sequence[Mapping[str, Any]], *, suite: str,
                         statuses: Mapping[str, Mapping[str, str]],
                         protected: tuple[frozenset[str], frozenset[str]] | None,
                         policy: SkipPolicy = DEFAULT_POLICY) -> list[str]:
    """Why stored accepted rows would not be admitted again by the policy in this tree."""
    problems: list[str] = []
    for stored in stored_rows:
        if not isinstance(stored, Mapping):
            problems.append(f"{suite}: a stored skip row is not an object")
            continue
        nodeid, location = str(stored.get("nodeid") or ""), str(stored.get("location") or "")
        path, sep, test = nodeid.partition("::")
        located, _, line = location.rpartition(":")
        malformed = "" if (sep and located == path and line.isdigit()) else "stored node id / location are inconsistent"
        skip = ObservedSkip(nodeid, path, test, str(stored.get("reason") or ""), location, malformed)
        again = classify(skip, suite=suite, statuses=statuses, protected=protected, policy=policy)
        keys = ("classification", "rule_id", "providers", "admitted")
        if not again["admitted"] or any(again.get(k) != stored.get(k) for k in keys):
            problems.append(f"{suite}: {nodeid} is not re-admitted ({again.get('refused_because', 'record differs')})")
    return problems


# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    probe_cmd = commands.add_parser("probe", help="record optional provider availability")
    probe_cmd.add_argument("--out", required=True)
    audit_cmd = commands.add_parser("audit", help="classify the skips of one JUnit report")
    audit_cmd.add_argument("--junit", required=True)
    audit_cmd.add_argument("--availability", required=True)
    audit_cmd.add_argument("--suite", required=True, choices=("junit_fast", "junit_scientific",
                                                              "junit_dependency_guard", "junit_campaign",
                                                              "junit_regression"))
    audit_cmd.add_argument("--out")
    args = parser.parse_args(argv)
    root = pathlib.Path.cwd()
    if args.command == "probe":
        document = probe(root)
        pathlib.Path(args.out).write_bytes((json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        for pid, row in document["providers"].items():
            print(f"{pid:13} {row['status']:12} {row['detail'][:90]}")
        return 0
    from tools.certification.hardening_assurance import TRUST_SCRIPT
    statuses, problems = availability_statuses(json.loads(pathlib.Path(args.availability).read_bytes()))
    try:
        protected = protected_tests(root, trust_script=TRUST_SCRIPT)
    except SkipPolicyError as exc:
        protected = None
        problems.append(str(exc))
    problems += policy_problems(DEFAULT_POLICY, root, trust_script=TRUST_SCRIPT)
    result = admit_suite(pathlib.Path(args.junit).read_bytes(), suite=args.suite,
                         statuses=statuses, protected=protected)
    result["availability_problems"] = problems
    result.update(summarize(result["rows"]))
    if args.out:
        pathlib.Path(args.out).write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(f"skipped {result['skipped']}  accepted {result['accepted']}  unexpected {result['unexpected']}")
    print(f"inventory_sha256 {result['inventory_sha256']}")
    for key, value in result["by_classification"].items():
        print(f"  {key:32} {value}")
    for key, value in result["by_unavailable_provider"].items():
        print(f"  unavailable {key:20} {value}")
    for row in result["rows"]:
        if not row["admitted"]:
            print(f"UNEXPECTED {row['nodeid']}: {row['refused_because']}")
    for problem in problems + result["report_problems"]:
        print(f"PROBLEM {problem}")
    return 0 if not result["unexpected"] and not problems and not result["report_problems"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
