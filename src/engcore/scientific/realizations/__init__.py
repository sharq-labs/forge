"""Computational realizations: how a scientific model is actually computed.

A scientific model is a claim about nature. A realization is one way of
computing that claim. They are separate records with separate identities and
separate versions, because they fail independently — a model can be valid
where its cheapest realization is inadequate, and a realization can be
replaced without the science changing at all.

Nothing here executes anything, selects anything, or ranks anything.
"""

from .definition import (
    IMPLEMENTATION_REFERENCE_SCHEMA,
    REALIZATION_REFERENCE_SCHEMA,
    REALIZATION_SCHEMA,
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
    RealizationReference,
)
from .registry import RealizationRegistry

__all__ = [
    "ImplementationReference",
    "ModelFormulation",
    "ModelRealizationDefinition",
    "RealizationReference",
    "RealizationRegistry",
    "REALIZATION_SCHEMA",
    "REALIZATION_REFERENCE_SCHEMA",
    "IMPLEMENTATION_REFERENCE_SCHEMA",
]
