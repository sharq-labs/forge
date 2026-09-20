"""Composition-pack contract errors."""


class CompositionPackError(Exception):
    """Base error for composition-pack infrastructure."""


class InvalidCompositionPackManifest(CompositionPackError):
    """A composition manifest is malformed or contradictory."""


class InvalidCompositionPackProvider(CompositionPackError):
    """A provider disagrees with the manifest it declares."""


class CompositionDependencyError(CompositionPackError):
    """A required Domain Pack is absent, ambiguous, or digest-mismatched."""


class DuplicateCompositionPack(CompositionPackError):
    """The same exact composition-pack identity was registered twice."""


class CompositionPackNotFound(CompositionPackError):
    """An exact composition-pack identity was requested but not registered."""


class CompositionPackNotEnabled(CompositionPackError):
    """A registered composition pack was used without explicit enablement."""
