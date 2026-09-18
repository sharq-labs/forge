"""Backward-compatible MCP import for the credibility-to-SRIA bridge.

The implementation moved during repository architecture cleanup. This module
remains a compatibility surface; new internal code should import from
engcore.credibility.sria_bridge.
"""

from importlib import import_module as _import_module

_impl = _import_module("engcore.credibility.sria_bridge")
for _name, _value in vars(_impl).items():
    if not (_name.startswith("__") and _name.endswith("__")):
        globals()[_name] = _value
__all__ = getattr(_impl, "__all__", ())
