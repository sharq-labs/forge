"""Units: our scientific quantity contract over a mature units backend."""

from .quantity import (
    Quantity,
    coerce_quantity,
    dimension_of,
    dimensionality,
    normalize_unit,
    registry,
    registry_fingerprint,
    verify_registry_unmutated,
)
from .validation import (
    check_unit_map,
    require_expected_dimension,
    require_same_dimension,
    require_unit,
)

__all__ = [
    "Quantity",
    "coerce_quantity",
    "dimension_of",
    "dimensionality",
    "normalize_unit",
    "registry",
    "registry_fingerprint",
    "verify_registry_unmutated",
    "check_unit_map",
    "require_expected_dimension",
    "require_same_dimension",
    "require_unit",
]
