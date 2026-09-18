"""Compatibility import for claim sensitivity and robustness analysis.

Implementation moved to engcore.claims.analysis.sensitivity. This compatibility module preserves old
import paths and object identity; new internal code should use the grouped path.
"""

from importlib import import_module as _import_module

_impl = _import_module("engcore.claims.analysis.sensitivity")
for _name, _value in vars(_impl).items():
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value
__all__ = getattr(_impl, "__all__", ())
