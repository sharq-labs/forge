"""Metadata-only discovery for external Domain Packs.

Discovery does not import plugin code. Loading is a separate explicit call, and
registration/enablement are separate again.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata

from .errors import DomainPackDiscoveryError
from .provider import DomainPackProvider

ENTRY_POINT_GROUP = "forge.domainpacks"


@dataclass(frozen=True, order=True)
class DiscoveredDomainPack:
    group: str
    name: str
    value: str
    distribution_name: str
    distribution_version: str

    @property
    def entry_point(self) -> str:
        return f"{self.group}:{self.name}={self.value}"


def _selected(group: str):
    points = metadata.entry_points()
    if hasattr(points, "select"):
        return tuple(points.select(group=group))
    return tuple(points.get(group, ()))


def discover_domain_packs(group: str = ENTRY_POINT_GROUP) -> tuple[DiscoveredDomainPack, ...]:
    """Read installed metadata only; do not import provider modules."""

    found: list[DiscoveredDomainPack] = []
    for point in _selected(group):
        dist = getattr(point, "dist", None)
        dist_name = (
            "<unknown>"
            if dist is None
            else str(dist.metadata.get("Name") or getattr(dist, "name", "<unknown>"))
        )
        dist_version = "<unknown>" if dist is None else str(dist.version)
        found.append(
            DiscoveredDomainPack(
                group=group,
                name=str(point.name),
                value=str(point.value),
                distribution_name=dist_name,
                distribution_version=dist_version,
            )
        )
    return tuple(sorted(found))


def load_discovered_domain_pack(descriptor: DiscoveredDomainPack) -> DomainPackProvider:
    """Explicitly import one exact discovered provider factory.

    The entry point must resolve to a zero-argument factory. Loading does not
    register or enable the returned provider.
    """

    matches = [
        point
        for point in _selected(descriptor.group)
        if point.name == descriptor.name and point.value == descriptor.value
    ]
    if len(matches) != 1:
        raise DomainPackDiscoveryError(
            f"entry point {descriptor.entry_point!r} resolved to {len(matches)} matches; "
            "refusing an ambiguous or disappeared plugin"
        )
    factory = matches[0].load()
    if not callable(factory):
        raise DomainPackDiscoveryError(
            f"entry point {descriptor.entry_point!r} must resolve to a zero-argument provider factory"
        )
    provider = factory()
    if not isinstance(provider, DomainPackProvider):
        raise DomainPackDiscoveryError(
            f"entry point {descriptor.entry_point!r} returned {type(provider).__name__}, "
            "which does not satisfy DomainPackProvider"
        )
    return provider
