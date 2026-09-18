"""Backward-compatible MCP import for credibility evidence records.

The implementation moved during repository architecture cleanup. This module
remains a compatibility surface; new internal code should import from
engcore.credibility.evidence.
"""

from importlib import import_module as _import_module

_impl = _import_module("engcore.credibility.evidence")
for _name, _value in vars(_impl).items():
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value
__all__ = getattr(_impl, "__all__", ())
