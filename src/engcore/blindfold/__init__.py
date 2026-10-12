"""FORGE Blindfold: the adversarial benchmark that tests whether Discovery is real.

Blindfold is NOT the discovery engine.  It is the instrument that measures one,
from outside: hidden worlds behind an escrow (:mod:`.escrow`), a restricted law
language (:mod:`.expression`), synthetic L5 universes with refusal controls
(:mod:`.universe`), isolated evaluation roles (:mod:`.roles`) and reference
baselines (:mod:`.baselines`).

Levels (:data:`LEVELS`): L0-L3 measure retrieval/reasoning/rediscovery and do
NOT count as genuine novel discovery; L4-L6 do.  This package implements L5.

Every escrow transport here is a development substitute and is labelled
SECURITY_BOUNDARY_NOT_PROVEN.
"""

from __future__ import annotations

LEVELS = {
    "L0": "retrieval control",
    "L1": "reasoning from supplied principles",
    "L2": "transformed known-law search",
    "L3": "historical rediscovery",
    "L4": "out-of-distribution prediction",
    "L5": "synthetic universe",
    "L6": "prospective real-world prediction",
}
NOVEL_DISCOVERY_LEVELS = frozenset({"L4", "L5", "L6"})

from .escrow import (  # noqa: E402
    EscrowRefused, EscrowService, EscrowStorage, InProcessTransport, ObserveClient, OperatorClient, SECURITY_LABEL, ScoreClient,
    SubprocessTransport,
)
from .roles import BlindfoldReport, EvaluatorConfig, ProposalStore, RoleRefused, run_campaign  # noqa: E402
from .universe import UniverseKind  # noqa: E402

__all__ = ["BlindfoldReport", "EscrowRefused", "EscrowService", "EscrowStorage", "EvaluatorConfig", "InProcessTransport", "LEVELS",
           "NOVEL_DISCOVERY_LEVELS", "ObserveClient", "OperatorClient", "ProposalStore", "RoleRefused", "SECURITY_LABEL", "ScoreClient",
           "SubprocessTransport", "UniverseKind", "run_campaign"]
