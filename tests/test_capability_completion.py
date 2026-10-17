"""Capability completion governance must fail closed against maturity overclaim."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from tools import capability_maturity as maturity


def test_checked_in_capability_ledger_is_valid_and_matrix_is_current() -> None:
    data = maturity.load_ledger()

    assert maturity.validate(data) == ()
    assert maturity.check() == ()


# OD-6 (owner, 2026-10-18): the active epic is the research program engrt.numerical_foundations
# (docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md).  These two tests replace the battery pin; the battery
# capability itself must keep every stage, gate and piece of evidence it had.
BATTERY_SNAPSHOT = {
    "scientific_definition": ("PASS", 1), "applicability": ("PASS", 2), "implementation": ("PASS", 1),
    "regression_tests": ("PASS", 1), "execution": ("PASS", 4), "verification": ("PASS", 2), "failure_cases": ("PASS", 2),
    "provenance_replay": ("PASS", 4), "real_data": ("PASS", 9), "calibration": ("PASS", 6),
    "independent_validation": ("MISSING", 5), "measurement_uq": ("PASS", 3), "benchmark_metrics": ("PASS", 3),
    "parameter_uq": ("MISSING", 2), "numerical_uq": ("NOT_APPLICABLE", 0), "model_discrepancy": ("MISSING", 1),
    "claims_integration": ("MISSING", 0), "domainpack_integration": ("MISSING", 0), "documentation": ("PASS", 1),
}


def _program(data):
    return next(p for p in data["research_programs"] if p["id"] == "engrt.numerical_foundations")


def test_active_epic_is_the_engineering_foundations_program_with_every_gate_open() -> None:
    data = maturity.load_ledger()
    assert data["schema"] == "forge.scientific_capability_completion/2"
    assert data["active_epic"] == "engrt.numerical_foundations"
    program = _program(data)
    assert program["kind"] == "research_program"
    assert [g["id"] for g in program["gates"]] == ["DV0", "M1", "M2", "E1", "E2", "E3"]
    assert all(g["status"] == "MISSING" for g in program["gates"])          # nothing is claimed by the migration
    assert {g["id"]: g["requires"] for g in program["gates"]}["E3"] == ["M1"]
    assert data["policy"]["horizontal_expansion_paused"] is True             # still paused OUTSIDE the program scope


def test_dv0_gates_no_other_work_and_requires_only_order_decisions() -> None:
    """Build-first (owner, 2026-10-18): the deferred-validation gate DV0 is required by no gate, so building any gate's
    scope never waits for a test run; M2 and E3 wait only for M1's DECISION."""
    program = _program(maturity.load_ledger())
    requires = {g["id"]: g["requires"] for g in program["gates"]}
    assert all("DV0" not in deps for deps in requires.values())
    assert requires == {"DV0": [], "M1": [], "M2": ["M1"], "E1": [], "E2": [], "E3": ["M1"]}
    assert all("build-first" in g["next_action"] for g in program["gates"] if g["id"] != "DV0")
    # M1 still MISSING (built or not): deciding M2 is refused, leaving M2 MISSING is allowed
    def decide_m2(d):
        next(g for g in _program(d)["gates"] if g["id"] == "M2").update(
            status="PASS", evidence=["docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md"])
    assert any("needs 'M1' PASS first" in e for e in _with(decide_m2))
    assert _with(lambda d: None) == ()


def test_battery_1rc_stays_functional_with_its_evidence() -> None:
    data = maturity.load_ledger()
    battery = next(cap for cap in data["capabilities"] if cap["id"] == "battery.thevenin_1rc")
    # FUNCTIONAL since 2026-10-14. Calibration PASSES on LG HG2 (identifiable with a measured OCV); held-out
    # validation does not (MODEL_REJECTED on the constant-current test, no cross-cell transfer).
    assert maturity.computed_stage(battery) == "FUNCTIONAL" and battery["declared_stage"] == "FUNCTIONAL"
    assert "independent_validation" in maturity.missing_for_next_stage(battery)
    for name, (status, count) in BATTERY_SNAPSHOT.items():
        gate = battery["gates"][name]
        assert gate["status"] == status, name
        assert len(gate.get("evidence", [])) >= count, name          # evidence may grow, never shrink


def test_declared_stage_cannot_exceed_supported_gates() -> None:
    data = deepcopy(maturity.load_ledger())
    target = next(cap for cap in data["capabilities"] if cap["id"] == "battery.thevenin_1rc")
    target["declared_stage"] = "PRODUCTION_READY"

    errors = maturity.validate(data)

    assert any(
        "declares PRODUCTION_READY but gates support only FUNCTIONAL" in error
        for error in errors
    )


def test_not_applicable_cannot_hide_missing_work_without_rationale() -> None:
    data = deepcopy(maturity.load_ledger())
    target = next(cap for cap in data["capabilities"] if cap["id"] == "battery.thevenin_1rc")
    target["gates"]["real_data"] = {
        "status": "NOT_APPLICABLE",
        "evidence": [],
        "rationale": "",
    }

    errors = maturity.validate(data)

    assert any(
        "battery.thevenin_1rc.real_data: NOT_APPLICABLE requires rationale" in error
        for error in errors
    )


def test_incomplete_capability_must_keep_concrete_next_actions() -> None:
    data = deepcopy(maturity.load_ledger())
    target = next(cap for cap in data["capabilities"] if cap["id"] == "platform.domain_pack")
    target["next_actions"] = []

    errors = maturity.validate(data)

    assert any(
        "platform.domain_pack: incomplete capability must have next_actions" in error
        for error in errors
    )


# ---- OD-6 negative cases: a research program cannot become a back door ---------------------------------------------


def _with(mutate):
    data = deepcopy(maturity.load_ledger())
    mutate(data)
    return maturity.validate(data)


def test_an_unknown_active_epic_is_refused() -> None:
    errors = _with(lambda d: d.update(active_epic="engrt.nope"))
    assert any("must identify a tracked capability or research program" in e for e in errors)


@pytest.mark.parametrize("field", ["contract", "allowed_scope", "prohibited", "gates"])
def test_an_incomplete_program_contract_is_refused(field) -> None:
    assert _with(lambda d: _program(d).pop(field))


def test_a_program_contract_path_must_exist_and_statuses_are_its_own() -> None:
    assert any("contract path does not exist" in e for e in _with(lambda d: _program(d).update(contract="docs/nope.md")))
    assert any("invalid status" in e for e in _with(lambda d: _program(d)["gates"][0].update(status="FUNCTIONAL")))


def test_ids_are_unique_across_capabilities_and_programs() -> None:
    errors = _with(lambda d: _program(d).update(id="battery.thevenin_1rc"))
    assert any("unique across capabilities and research programs" in e for e in errors)


def test_a_program_pass_needs_existing_evidence() -> None:
    assert any("PASS requires evidence" in e for e in _with(lambda d: _program(d)["gates"][1].update(status="PASS")))
    errors = _with(lambda d: _program(d)["gates"][1].update(status="PASS", evidence=["docs/does/not/exist.json"]))
    assert any("evidence path does not exist" in e for e in errors)


def test_a_program_carries_no_maturity_vocabulary_and_never_moves_a_capability() -> None:
    assert any("no maturity vocabulary" in e for e in _with(lambda d: _program(d).update(declared_stage="FUNCTIONAL")))
    assert any("maturity vocabulary" in e for e in _with(lambda d: _program(d)["gates"][0].update(id="calibration")))
    data = deepcopy(maturity.load_ledger())
    before = {c["id"]: maturity.computed_stage(c) for c in data["capabilities"]}
    for gate in _program(data)["gates"]:
        gate.update(status="PASS", evidence=["docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md"])
    assert {c["id"]: maturity.computed_stage(c) for c in data["capabilities"]} == before
    battery = next(c for c in data["capabilities"] if c["id"] == "battery.thevenin_1rc")
    battery["declared_stage"] = "EVIDENCE_BACKED"                         # "because the program passed"
    assert any("declares EVIDENCE_BACKED but gates support only FUNCTIONAL" in e for e in maturity.validate(data))


@pytest.mark.parametrize("status", ["PASS", "FAIL", "BLOCKED_WITH_EVIDENCE"])
def test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes(status) -> None:
    def decide_e3(d):
        e3 = next(g for g in _program(d)["gates"] if g["id"] == "E3")
        e3.update(status=status, evidence=["docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md"])
    assert any("needs 'M1' PASS first" in e for e in _with(decide_e3))


def test_a_deferred_gate_may_wait_on_an_open_requirement() -> None:
    assert _with(lambda d: next(g for g in _program(d)["gates"] if g["id"] == "E3").update(status="DEFERRED_BY_OWNER")) == ()


def test_a_decided_program_cannot_stay_the_active_epic() -> None:
    def decide_all(d):
        for gate in _program(d)["gates"]:
            gate.update(status="PASS", evidence=["docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md"])
    assert any("the owner names the next epic" in e for e in _with(decide_all))


def test_every_decided_gate_needs_evidence_and_blocked_follows_a_failed_requirement() -> None:
    blocked_without_evidence = _with(lambda d: _program(d)["gates"][0].update(status="BLOCKED_WITH_EVIDENCE"))
    assert any("BLOCKED_WITH_EVIDENCE requires evidence" in e for e in blocked_without_evidence)
    evidence = ["docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md"]

    def m1_failed_m2_blocked(d):
        gates = {g["id"]: g for g in _program(d)["gates"]}
        gates["M1"].update(status="FAIL", evidence=evidence)
        gates["M2"].update(status="BLOCKED_WITH_EVIDENCE", evidence=evidence)
    assert _with(m1_failed_m2_blocked) == ()                              # the exit stays reachable after a FAIL

    def m1_failed_m2_failed(d):
        gates = {g["id"]: g for g in _program(d)["gates"]}
        gates["M1"].update(status="FAIL", evidence=evidence)
        gates["M2"].update(status="FAIL", evidence=evidence)
    assert any("needs 'M1' PASS first" in e for e in _with(m1_failed_m2_failed))


def test_a_deferred_gate_states_why_and_paths_stay_inside_the_repository() -> None:
    assert any("DEFERRED_BY_OWNER requires next_action" in e
               for e in _with(lambda d: _program(d)["gates"][1].update(status="DEFERRED_BY_OWNER", next_action="")))
    assert any("repository-relative" in e
               for e in _with(lambda d: _program(d)["gates"][1].update(status="PASS", evidence=["C:/Windows/win.ini"])))
    assert any("repository-relative" in e
               for e in _with(lambda d: _program(d)["gates"][1].update(status="PASS", evidence=["../outside.json"])))


def test_two_programs_with_one_id_and_duplicate_planned_capabilities_are_refused() -> None:
    assert any("research program ids must be unique" in e
               for e in _with(lambda d: d["research_programs"].append(deepcopy(_program(d)))))
    assert any("planned_capabilities must be unique" in e
               for e in _with(lambda d: _program(d)["planned_capabilities"].append(_program(d)["planned_capabilities"][0])))


def test_the_program_contract_carries_the_cross_domain_architecture_requirements() -> None:
    """Owner direction (2026-10-18): the shared structure is physics-agnostic; heat is the first reference application.
    The requirements are part of the program's acceptance criteria and bind the program gates M1-E3 (not the 19
    maturity gates of a capability)."""
    contract = (maturity.ROOT / "docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md").read_bytes().decode()
    assert "## Cross-Domain Scientific Architecture Requirements" in contract
    for number in range(1, 11):
        assert f"| CDAR-{number} |" in contract, number
    section = contract.split("### Multi-domain acceptance criteria per gate", 1)[1].split("###", 1)[0]
    for gate in ("M1", "M2", "E1", "E2", "E3"):
        assert f"| {gate} |" in section, gate
    assert "### Architectural fixtures" in contract
    assert "tests/architecture/test_cross_domain_fixtures.py" in contract      # a named, test-only location
    assert (maturity.ROOT / "docs/work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md").exists()


def test_a_superseded_schema_is_refused_not_read(tmp_path) -> None:
    data = maturity.load_ledger()
    data["schema"] = "forge.scientific_capability_completion/1"
    path = tmp_path / "ledger.json"
    path.write_bytes(json.dumps(data).encode())
    with pytest.raises(ValueError, match="migrate the ledger"):
        maturity.load_ledger(path)


def test_the_governance_documents_name_the_ledgers_active_epic() -> None:
    epic = maturity.load_ledger()["active_epic"]
    root = maturity.ROOT
    policy = (root / "docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md").read_bytes().decode()
    template = (root / ".github/pull_request_template.md").read_bytes().decode()
    matrix = (root / "docs/SCIENTIFIC_CAPABILITY_MATRIX.md").read_bytes().decode()
    assert f"The current active epic is **{epic}**" in policy
    assert f"`{epic}`" in template.splitlines()[2]
    assert f"Active completion epic: {epic} " in matrix
    plan = (root / "docs/work/ACTIVE_PLAN.md").read_bytes().decode()
    assert f"Active epic: `{epic}`" in plan.splitlines()[2]
