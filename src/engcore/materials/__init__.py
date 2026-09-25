"""Scientific data + materials layer (BIG 5), built on ``scientific.knowledge``.

Sourced values are :class:`~engcore.scientific.knowledge.claim.KnowledgeClaim`
records from a :class:`~engcore.scientific.knowledge.source.KnowledgeSource`,
versioned as a :class:`~engcore.scientific.knowledge.snapshot.KnowledgeSnapshot`
and imported under a
:class:`~engcore.scientific.knowledge.ingestion.KnowledgeIngestionReceipt`.
This package adds what those records could not say on their own: which exact
material and state a value applies to, over which declared range, and how a
value may be resolved at a state no claim names.
"""

from .ranges import ApplicabilityRange
from .identity import (
    CompositionEntry, MaterialIdentity, MaterialState,
    MaterialStateSchema, SourceIdentity, source_identity,
)
from .fluids import FluidIdentity, FluidPropertyRecord, FluidState
from .properties import (
    DatumOrigin, InterpolationRule, MaterialPropertySet, PropertyApplicability,
    PropertyDatum, PropertyDerivation, ResolvedProperty, TransformationRecord,
)

__all__ = [
    "FluidIdentity", "FluidPropertyRecord", "FluidState",
    "ApplicabilityRange", "CompositionEntry", "MaterialIdentity", "MaterialState",
    "MaterialStateSchema", "SourceIdentity", "source_identity",
    "DatumOrigin", "InterpolationRule", "MaterialPropertySet", "PropertyApplicability",
    "PropertyDatum", "PropertyDerivation", "ResolvedProperty", "TransformationRecord",
]
