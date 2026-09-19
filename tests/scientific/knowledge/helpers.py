from datetime import datetime, timezone

from engcore.scientific.knowledge import (
    FreshnessPolicy, KnowledgeClaim, KnowledgeKind, KnowledgeSnapshot,
    KnowledgeSource, KnowledgeSourceClass, SourcePin, TrustedSourceRegistry,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

CONTEXT = "c" * 64
DOCUMENT = "a" * 64
NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def source(
    *,
    digest=DOCUMENT,
    version="2026.1",
    issuer="Reference Lab",
    published="2026-01-01T00:00:00+00:00",
    source_class=KnowledgeSourceClass.STANDARD,
):
    return KnowledgeSource(
        "source-1", issuer, digest, version,
        "urn:reference:source-1", source_class,
        published, "2026-09-19T00:00:00+00:00",
    )


def uncertainty():
    return Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(0.55, "watt / meter / kelvin"),
        upper=Quantity(0.65, "watt / meter / kelvin"),
        method="published interval",
    )


def claim(*, source_digest=DOCUMENT, context=CONTEXT, value=0.60):
    return KnowledgeClaim(
        "claim-1", KnowledgeKind.MATERIAL_PROPERTY, "reference-material",
        "thermal_conductivity", Quantity(value, "watt / meter / kelvin"), "",
        uncertainty(), "source-1", source_digest, context,
    )


def snapshot(**kwargs):
    src=kwargs.pop("src", source())
    clm=kwargs.pop("clm", claim(source_digest=src.document_digest))
    return KnowledgeSnapshot("snapshot-1", (src,), (clm,))


def registry(src=None):
    src=src or source()
    return TrustedSourceRegistry((
        SourcePin(src.source_id, src.issuer, src.document_digest, src.version),
    ))


def freshness(limit=3650, require_timestamp=True):
    return FreshnessPolicy(
        {KnowledgeSourceClass.STANDARD: limit},
        require_timestamp=require_timestamp,
    )
