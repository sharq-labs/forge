"""Domain-pack contract errors.

Kept outside the Scientific Core: a broken plugin package is a platform
integration error, not evidence about physics.
"""

class DomainPackError(Exception):
    """Base error for domain-pack infrastructure."""


class InvalidDomainPackManifest(DomainPackError):
    """A manifest is malformed or internally contradictory."""


class InvalidDomainPackProvider(DomainPackError):
    """A provider does not match the manifest it declares."""


class DuplicateDomainPack(DomainPackError):
    """The same exact pack identity was registered twice."""


class DomainPackNotFound(DomainPackError):
    """An exact pack identity was requested but is not registered."""


class DomainPackNotEnabled(DomainPackError):
    """A registered pack was used without explicit enablement."""


class DomainPackDiscoveryError(DomainPackError):
    """Installed entry-point metadata could not be resolved safely."""
