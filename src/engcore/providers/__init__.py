"""External scientific providers: solvers Forge executes but does not own.

Forge's product claim is not that it computes battery physics better than the
battery community does. It is that a number, whoever computed it, can be bound
to evidence and judged. This package is the boundary where a solver Forge did
not write enters that judgement.

Where this sits
---------------
``providers`` is an outer boundary, in the same sense ``mcp`` is: it is not
scientific authority, it imports the Scientific Core and the domains rather
than being imported by them, and nothing below it knows a provider exists. A
Core that imported a provider would be a Core whose availability depended on an
optional third-party wheel, which is the inversion this placement prevents.

    Scientific Core -> domains/systems -> credibility -> claims/SRIA -> MCP
                            ^
                            |
                       providers

Optional by construction
------------------------
None of PyBaMM, PyBOP or SALib is imported at module scope anywhere in this
package. Every import is inside the function that needs it, so importing
``engcore.providers`` on a bare install succeeds and a request to an absent
provider returns ``PROVIDER_UNAVAILABLE`` rather than raising ImportError
somewhere a caller cannot see.

The three, and what each is for
--------------------------------
=================  ===============================  ==========================
provider           what it computes                 what it may NOT be used for
=================  ===============================  ==========================
PyBaMM             battery models and their solves  granting its own support
PyBOP              parameter fits, calibration only validation or holdout data
SALib              parameter sensitivity indices    validation evidence
=================  ===============================  ==========================

The third column is enforced in code, not in prose: see
``PyBOPProvider`` (calibration-only dataset roles) and
``SensitivityEvidence.is_validation_evidence`` (permanently ``False``).
"""

from .contract import (
    ExecutionOutcome,
    ProviderCapability,
    ProviderError,
    ProviderExecutionFailure,
    ProviderExecutionReceipt,
    ProviderIdentity,
    ProviderReplayReport,
    ProviderRequest,
    ProviderResult,
    ProviderUnavailable,
    ScientificProvider,
    replay_provider_request,
    unavailable_result,
)
from .environment import EnvironmentIdentity
from .licenses import PROVIDER_LICENSES, manifest_rows

__all__ = [
    "PROVIDER_LICENSES",
    "EnvironmentIdentity",
    "ExecutionOutcome",
    "ProviderCapability",
    "ProviderError",
    "ProviderExecutionFailure",
    "ProviderExecutionReceipt",
    "ProviderIdentity",
    "ProviderReplayReport",
    "ProviderRequest",
    "ProviderResult",
    "ProviderUnavailable",
    "ScientificProvider",
    "manifest_rows",
    "replay_provider_request",
    "unavailable_result",
]
