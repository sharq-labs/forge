"""Runtime domain packages may bind to SRIA semantic DomainPacks explicitly."""

from __future__ import annotations

import pytest

from engcore.extensions import DomainExtension, DomainRuntime
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.sria.errors import DomainPackContractError


MODEL = ScientificModelDefinition(
    model_id="demo.linear",
    version="1",
    domain="demo.physics",
    exclusions=("nonlinear response",),
)


class DemoPack:
    pack_id = "demo.physics"
    pack_version = "1.0.0"

    def model_references(self):
        return ("demo.linear@1",)

    def parameter_semantics(self):
        return {"gain": "dimensionless linear gain"}

    def qois(self):
        return ("response",)

    def scope(self):
        return "declared-by-domain"

    def assumptions(self):
        return ("linear response",)

    def fidelity_ladder(self):
        return ()

    def extract_covariates(self, subject):
        return {"state_count": 1.0}

    def domain_critics(self):
        return ()

    def semantic_terms(self):
        return ("demo", "linear")


class IncompletePack:
    pack_id = "demo.physics"
    pack_version = "1.0.0"

    def model_references(self):
        return ("demo.linear@1",)


def _extension(pack=None):
    return DomainExtension(
        extension_id="demo.physics",
        version="1.0.0",
        namespace="demo",
        models=(MODEL,),
        domain_pack=pack,
    )


def test_valid_semantic_pack_is_identity_bound_into_install_receipt():
    runtime = DomainRuntime()
    extension = _extension(DemoPack())

    receipt = runtime.install(extension)

    assert extension.domain_pack_key == ("demo.physics", "1.0.0")
    assert receipt.domain_pack_key == extension.key
    assert runtime.models.contains(*MODEL.key)


def test_invalid_domain_pack_is_rejected_before_a_runtime_exists_to_mutate():
    with pytest.raises(DomainPackContractError, match="missing"):
        _extension(IncompletePack())


def test_semantic_pack_and_runtime_extension_must_share_identity_and_version():
    pack = DemoPack()
    pack.pack_id = "other.physics"

    with pytest.raises(ScientificCoreError, match="same identity/version"):
        _extension(pack)


def test_mutating_pack_identity_after_extension_construction_is_caught_at_install():
    pack = DemoPack()
    extension = _extension(pack)
    runtime = DomainRuntime()

    pack.pack_version = "2.0.0"

    with pytest.raises(ScientificCoreError, match="identity changed"):
        runtime.install(extension)
    assert not runtime.models.contains(*MODEL.key)
    assert runtime.installed_extensions == ()


def test_pack_overreach_is_rejected_by_existing_sria_contract_not_plugin_policy():
    class OverreachingPack(DemoPack):
        research_strategy = object()

    with pytest.raises(DomainPackContractError, match="platform responsibilities"):
        _extension(OverreachingPack())


def test_packless_low_level_extension_remains_supported():
    runtime = DomainRuntime()
    receipt = runtime.install(_extension())

    assert receipt.domain_pack_key is None
    assert runtime.models.contains(*MODEL.key)
