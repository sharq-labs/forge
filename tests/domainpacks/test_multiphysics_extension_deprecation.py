"""The deprecated multiphysics extension loader warns, then still validates.

Review finding B5: ``load_multiphysics_extension`` called ``warnings.warn``
without importing ``warnings``, so every call died with NameError before the
deprecation notice or any admission check ran.
"""

from __future__ import annotations

import warnings

import pytest

from engcore.domainpacks.errors import InvalidDomainPackProvider
from engcore.domainpacks.manifest import DOMAIN_PACK_API, DomainPackManifest
from engcore.domainpacks.multiphysics import (
    MultiphysicsPackExtension,
    load_multiphysics_extension,
)


def _manifest() -> DomainPackManifest:
    return DomainPackManifest(
        pack_id="b5_probe_pack",
        pack_version="1.0.0",
        domain="b5_probe",
        compatible_core_apis=(DOMAIN_PACK_API,),
    )


class _Provider:
    manifest = _manifest()


def test_a_call_warns_at_the_caller_and_returns_the_extension() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        extension = load_multiphysics_extension(_Provider())
    assert isinstance(extension, MultiphysicsPackExtension)
    assert extension.pack_id == "b5_probe_pack"
    assert extension.blueprints == () and extension.participant_factories == ()
    (warning,) = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert "deprecated" in str(warning.message)
    assert warning.filename == __file__


def test_a_provider_without_a_manifest_is_refused_after_the_warning() -> None:
    class Bare:
        manifest = None

    with pytest.warns(DeprecationWarning):
        with pytest.raises(InvalidDomainPackProvider, match="DomainPackManifest"):
            load_multiphysics_extension(Bare())


def test_a_non_callable_extension_hook_is_refused() -> None:
    class Broken(_Provider):
        multiphysics_blueprints = ("not", "callable")

    with pytest.warns(DeprecationWarning):
        with pytest.raises(InvalidDomainPackProvider, match="zero-argument callable"):
            load_multiphysics_extension(Broken())
