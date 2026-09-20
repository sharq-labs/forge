"""Capability completion governance must fail closed against maturity overclaim."""

from __future__ import annotations

from copy import deepcopy

from tools import capability_maturity as maturity


def test_checked_in_capability_ledger_is_valid_and_matrix_is_current() -> None:
    data = maturity.load_ledger()

    assert maturity.validate(data) == ()
    assert maturity.check() == ()


def test_active_epic_is_battery_1rc_and_still_incomplete() -> None:
    data = maturity.load_ledger()
    active = next(cap for cap in data["capabilities"] if cap["id"] == data["active_epic"])

    assert data["active_epic"] == "battery.thevenin_1rc"
    assert maturity.computed_stage(active) == "FOUNDATION"
    assert active["declared_stage"] == "FOUNDATION"
    assert "execution" in maturity.missing_for_next_stage(active)


def test_declared_stage_cannot_exceed_supported_gates() -> None:
    data = deepcopy(maturity.load_ledger())
    target = next(cap for cap in data["capabilities"] if cap["id"] == "battery.thevenin_1rc")
    target["declared_stage"] = "PRODUCTION_READY"

    errors = maturity.validate(data)

    assert any(
        "declares PRODUCTION_READY but gates support only FOUNDATION" in error
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
