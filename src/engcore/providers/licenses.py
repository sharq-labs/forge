"""The provider license manifest: diligence visibility, and nothing more.

P19's scope is stated in its own words: *no legal conclusions beyond documented
license information*. So each record below carries what the project publishes
about itself and one field -- ``integration_mode`` -- that is a fact about
*this* repository rather than about the provider: whether Forge imports it at
run time, vendors its code, or redistributes it.

That field is the one a reviewer actually needs, because the distribution
question is not "what license is PyBaMM under" but "does shipping Forge ship
PyBaMM". It does not: all three are optional dependencies installed from PyPI
by the operator, so the answer in every row is the same and is recorded rather
than inferred.

``license_text_reviewed`` is deliberately absent. Recording that a license was
*read* would be a claim this module cannot support; recording what the package
metadata *states* is a fact it can.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .environment import distribution_version


@dataclass(frozen=True)
class ProviderLicense:
    """What one provider's published metadata says about its license."""

    provider: str
    #: The version this manifest was written against. The version actually
    #: installed is read separately by :func:`manifest_rows`, so a drift
    #: between them is visible rather than assumed away.
    recorded_version: str
    license_identifier: str
    source_repository: str
    #: How this repository uses it. One of "optional runtime import",
    #: "vendored source", "redistributed binary".
    integration_mode: str
    distribution_implication: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "recorded_version": self.recorded_version,
            "license_identifier": self.license_identifier,
            "source_repository": self.source_repository,
            "integration_mode": self.integration_mode,
            "distribution_implication": self.distribution_implication,
        }


#: Read from each distribution's own PyPI metadata on 2026-09-21.
PROVIDER_LICENSES = (
    ProviderLicense(
        provider="pybamm",
        recorded_version="26.8.0.0",
        license_identifier="BSD-3-Clause",
        source_repository="https://github.com/pybamm-team/PyBaMM",
        integration_mode="optional runtime import",
        distribution_implication=(
            "not vendored and not redistributed; installed from PyPI by the "
            "operator through the forge[battery-pybamm] extra"
        ),
    ),
    ProviderLicense(
        provider="pybop",
        recorded_version="26.3",
        license_identifier="BSD-3-Clause",
        source_repository="https://github.com/pybop-team/PyBOP",
        integration_mode="optional runtime import",
        distribution_implication=(
            "not vendored and not redistributed; installed from PyPI by the "
            "operator through the forge[battery-fit] extra"
        ),
    ),
    ProviderLicense(
        provider="salib",
        recorded_version="1.6.0",
        license_identifier="MIT",
        source_repository="https://github.com/SALib/SALib",
        integration_mode="optional runtime import",
        distribution_implication=(
            "not vendored and not redistributed; installed from PyPI by the "
            "operator through the forge[sensitivity] extra"
        ),
    ),
)


def manifest_rows() -> tuple[dict[str, Any], ...]:
    """The manifest, each row annotated with the version actually installed.

    ``installed_version`` is ``None`` on a host without the extra, which is the
    normal case for Forge Core and is not an error.
    """
    return tuple(
        dict(
            row.to_dict(),
            installed_version=distribution_version(row.provider),
        )
        for row in PROVIDER_LICENSES
    )


__all__ = ["PROVIDER_LICENSES", "ProviderLicense", "manifest_rows"]
