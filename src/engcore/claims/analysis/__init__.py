"""Post-assessment scientific analysis.

The analysis modules depend on the claim UQ runtime, while that runtime also
imports the model-discrepancy implementation from this package.  Eagerly
star-importing every analysis module here therefore makes a fresh import of
``engcore.claims`` order-dependent.  Keep the package initializer inert;
canonical callers import the concrete analysis module and the legacy flat
modules remain the compatibility surface.
"""

from importlib import import_module


_PUBLIC_MODULES = (
    "sensitivity",
    "challenge",
    "impact",
    "diagnostics",
    "model_discrepancy",
)


def __getattr__(name: str):
    """Resolve legacy package-level names without eager circular imports."""

    for module_name in _PUBLIC_MODULES:
        module = import_module(f"{__name__}.{module_name}")
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
