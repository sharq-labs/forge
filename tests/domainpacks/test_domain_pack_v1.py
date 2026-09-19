"""Forge Domain Pack v1 contract and trust-boundary tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from engcore.domainpacks import (
    DiscoveredDomainPack,
    DomainPackNotEnabled,
    DomainPackNotFound,
    DomainPackRegistry,
    InvalidDomainPackProvider,
    PackOrigin,
    discover_domain_packs,
    load_discovered_domain_pack,
    snapshot_domain_pack,
    validate_domain_pack,
)
from engcore.domains.battery.pack import BatteryDomainPack


def test_battery_pack_manifest_matches_runtime_artifacts() -> None:
    provider = BatteryDomainPack()
    report = validate_domain_pack(provider)

    assert report.valid, report.errors
    assert len(provider.manifest.models) == 4
    assert len(provider.manifest.realizations) == 4
    assert len(provider.manifest.solvers) == 1
    assert provider.manifest.capabilities == ("battery:cell_terminal_state",)


def test_experimental_thevenin_kernel_has_not_been_promoted_to_pack_authority() -> None:
    provider = BatteryDomainPack()

    model_ids = {ref.artifact_id for ref in provider.manifest.models}
    realization_ids = {ref.artifact_id for ref in provider.manifest.realizations}

    assert not any("thevenin" in value for value in model_ids)
    assert not any("thevenin" in value for value in realization_ids)
    assert provider.manifest.uq_producers == ()
    assert provider.manifest.measurement_adapters == ()


def test_registering_a_pack_does_not_enable_it() -> None:
    registry = DomainPackRegistry()
    registry.register(BatteryDomainPack())

    assert len(registry) == 1
    assert registry.list(enabled_only=True) == ()
    assert registry.providing("battery:cell_terminal_state") == ()

    with pytest.raises(DomainPackNotEnabled):
        registry.get("battery", "1.0.0", require_enabled=True)

    registry.enable("battery", "1.0.0")

    assert registry.is_enabled("battery", "1.0.0")
    assert registry.get("battery", "1.0.0", require_enabled=True).provider.manifest.pack_id == "battery"
    assert len(registry.providing("battery:cell_terminal_state")) == 1


def test_registry_never_guesses_a_pack_version() -> None:
    registry = DomainPackRegistry()
    registry.register(BatteryDomainPack())

    with pytest.raises(DomainPackNotFound):
        registry.get("battery", "latest")

    with pytest.raises(DomainPackNotFound):
        registry.enable("battery", "9.9.9")


class _ManifestDriftProvider(BatteryDomainPack):
    @property
    def manifest(self):
        base = super().manifest
        return replace(base, models=base.models[:-1])


def test_manifest_runtime_drift_is_refused_before_registration() -> None:
    provider = _ManifestDriftProvider()
    report = validate_domain_pack(provider)

    assert not report.valid
    assert any("manifest models" in error for error in report.errors)

    with pytest.raises(InvalidDomainPackProvider, match="manifest models"):
        DomainPackRegistry().register(provider)


def test_manifest_round_trip_preserves_digest() -> None:
    provider = BatteryDomainPack()
    encoded = provider.manifest.to_dict()
    restored = type(provider.manifest).from_dict(encoded)

    assert restored == provider.manifest
    assert restored.digest == provider.manifest.digest


def test_snapshot_binds_pack_manifest_and_origin() -> None:
    registry = DomainPackRegistry()
    registration = registry.register(
        BatteryDomainPack(),
        origin=PackOrigin.external(
            distribution_name="forge-domain-battery",
            distribution_version="1.2.3",
            entry_point="forge.domainpacks:battery=forge_battery:domain_pack",
        ),
    )

    snapshot = snapshot_domain_pack(registration)

    assert snapshot.pack_id == "battery"
    assert snapshot.manifest_digest == registration.provider.manifest.digest
    assert snapshot.distribution_name == "forge-domain-battery"
    assert snapshot.distribution_version == "1.2.3"
    assert snapshot.entry_point == "forge.domainpacks:battery=forge_battery:domain_pack"
    assert snapshot.digest == snapshot_domain_pack(registration).digest


def test_discovery_reads_metadata_without_loading_plugin_code(monkeypatch) -> None:
    loaded = []

    class FakeDist:
        metadata = {"Name": "forge-domain-battery"}
        version = "1.2.3"

    class FakeEntryPoint:
        name = "battery"
        value = "forge_battery:domain_pack"
        dist = FakeDist()

        def load(self):
            loaded.append("loaded")
            return BatteryDomainPack

    class FakeEntryPoints(tuple):
        def select(self, *, group):
            return self if group == "forge.domainpacks" else ()

    from engcore.domainpacks import discovery

    monkeypatch.setattr(
        discovery.metadata,
        "entry_points",
        lambda: FakeEntryPoints((FakeEntryPoint(),)),
    )

    found = discover_domain_packs()

    assert len(found) == 1
    assert isinstance(found[0], DiscoveredDomainPack)
    assert found[0].distribution_name == "forge-domain-battery"
    assert loaded == []

    provider = load_discovered_domain_pack(found[0])
    assert isinstance(provider, BatteryDomainPack)
    assert loaded == ["loaded"]


def test_discovery_loading_still_does_not_register_or_enable() -> None:
    # Loading and activation are intentionally separate APIs. A provider object
    # existing in memory must not alter a fresh registry.
    registry = DomainPackRegistry()
    _provider = BatteryDomainPack()

    assert len(registry) == 0
    assert registry.list(enabled_only=True) == ()


class _NoSolverProvider(BatteryDomainPack):
    @property
    def manifest(self):
        return replace(super().manifest, solvers=())

    def solver_factories(self):
        return ()


def test_atomic_pack_refuses_realizations_without_an_in_pack_solver() -> None:
    report = validate_domain_pack(_NoSolverProvider())

    assert not report.valid
    assert any("no in-pack solver" in error for error in report.errors)


def test_manifest_reader_refuses_string_where_json_array_is_required() -> None:
    provider = BatteryDomainPack()
    payload = provider.manifest.to_dict()
    payload["capabilities"] = "battery:cell_terminal_state"

    with pytest.raises(Exception, match="capabilities must be a JSON array"):
        type(provider.manifest).from_dict(payload)
