"""Compatibility wrapper for product capability declarations."""
from importlib import import_module as _import_module

_impl = _import_module("engcore.product.capabilities")
for _name, _value in vars(_impl).items():
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value
__all__ = getattr(_impl, "__all__", ())
