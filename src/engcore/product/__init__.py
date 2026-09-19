"""Product-facing contracts over Forge's scientific runtime.

The product layer contains no physics and no transport-specific SDK. MCP,
HTTP, a web application or a vendor-specific LLM integration can all call the
same deterministic gateway.
"""

from .runtime import (
    PRODUCT_CAPABILITIES_SCHEMA,
    PRODUCT_PREPARATION_SCHEMA,
    PRODUCT_RUN_SCHEMA,
    ProductRequestError,
    describe_product,
    prepare_simulation,
    run_proposed_simulation,
    run_simulation,
)

__all__ = [
    "PRODUCT_CAPABILITIES_SCHEMA",
    "PRODUCT_PREPARATION_SCHEMA",
    "PRODUCT_RUN_SCHEMA",
    "ProductRequestError",
    "describe_product",
    "prepare_simulation",
    "run_proposed_simulation",
    "run_simulation",
]
