"""Scientific Core error taxonomy.

Deliberately compact. Every error here marks a distinct failure mode that a
caller can reasonably act on; we do not create a class per message.
"""

from __future__ import annotations


class ScientificCoreError(Exception):
    """Base class for every Scientific Core failure."""


class InvalidScientificProblem(ScientificCoreError):
    """A problem/IR object violates its declared invariants."""


class UnitCompatibilityError(ScientificCoreError):
    """Units are unparsable, or dimensionally incompatible where compatibility
    was required. Raised instead of silently dropping or coercing units."""


class UnitRegistryMutationError(ScientificCoreError):
    """Something tried to change the units backend after it was sealed.

    The registry behind :mod:`engcore.scientific.units` is one object for the
    life of the process, and a unit definition is not run-scoped state: a
    ``Quantity`` is a magnitude and a *unit string*, so the meaning of
    ``"volt"`` has to be the same for every run that serializes one, and for
    every reader that deserializes one later. A run that redefined a unit
    would not be configuring itself; it would be changing the arithmetic of
    every other run in the process and the interpretation of every record
    already written.

    So the registry refuses to change rather than being copied per run. This
    is raised on any attempt.
    """


class ModelNotFoundError(ScientificCoreError):
    """No registered model matches the requested identity."""


class ModelValidityError(ScientificCoreError):
    """A model's validity domain is malformed, or a model was used where its
    validity could not be established."""


class InvalidScientificCapability(ScientificCoreError):
    """A scientific capability identifier is malformed, or a declared
    capability set is self-contradictory."""


class InvalidModelRealization(ScientificCoreError):
    """A computational realization record violates its declared invariants."""


class RealizationNotFoundError(ScientificCoreError):
    """No registered computational realization matches the requested identity.

    Deliberately distinct from :class:`ModelNotFoundError` and
    :class:`SolverNotFoundError`: "the science is unknown to us", "the science
    is known but nothing implements it" and "something implements it but no
    solver can run it" are three different answers, and a future planner must
    be able to tell a user which one it hit."""


class SolverNotFoundError(ScientificCoreError):
    """No registered solver can support the problem."""


class AmbiguousSolverError(ScientificCoreError):
    """More than one solver matches and no selection rule was supplied.
    The core never silently picks one."""


class DuplicateRegistrationError(ScientificCoreError):
    """An identity is already present in a registry."""


class ScientificValidationError(ScientificCoreError):
    """A validation report is malformed, or claims a validation level that was
    not actually established by a passing check."""
