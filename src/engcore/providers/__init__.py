"""Provider-neutral boundary for external scientific solvers and libraries (BIG 11).

External providers compute; Forge keeps authority over identity, applicability,
materials/data, units, time, state, provenance, uncertainty and admission.

* :mod:`.catalog` -- descriptive capability registry and discovery; never ranks,
  never selects, never falls back (``require`` or ``ProviderUnavailable``).
* :mod:`.identity` -- execution identity from CONTENT (problem, generated
  configuration, input bytes, window, environment, state, provider digest).
* :mod:`.process` -- argv-only external process boundary with fresh workspaces,
  digest-bound inputs/outputs and stale/foreign-output refusal.
* :mod:`.records` -- generic provider execution record (not evidence).
* :mod:`.compare` -- declared cross-provider comparison (corroboration only).

Provider-specific adapters live in separate distributions under ``providers/``;
no provider name is branched on here.
"""

from ..numerical.core import ProviderUnavailable
from .catalog import (
    Availability, ProviderCapability, ProviderMode, ProviderRegistry, ProviderStatus, default_registry,
    distribution_digest, executable_probe, python_package_probe,
)
from .compare import ComparisonDeclaration, ExecutionRef, OutputSelection, ProviderComparison, compare_providers, shared_dependencies
from .identity import ProviderExecutionIdentity, canonical_json, content_digest
from .process import GeneratedFile, ProcessExecutionRecord, ProcessInvocation, ProcessWorkspace, minimal_environment, safe_relative
from .records import ProviderExecutionRecord, ProviderRefusal, QuantitySeries, failed

__all__ = [
    "ProviderUnavailable", "Availability", "ProviderCapability", "ProviderMode", "ProviderRegistry", "ProviderStatus",
    "default_registry", "distribution_digest", "executable_probe", "python_package_probe",
    "ComparisonDeclaration", "ExecutionRef", "OutputSelection", "ProviderComparison", "compare_providers", "shared_dependencies",
    "ProviderExecutionIdentity", "canonical_json", "content_digest",
    "GeneratedFile", "ProcessExecutionRecord", "ProcessInvocation", "ProcessWorkspace", "minimal_environment", "safe_relative",
    "ProviderExecutionRecord", "ProviderRefusal", "QuantitySeries", "failed",
]
