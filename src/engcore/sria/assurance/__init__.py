"""SRIA V0.1 M3 — the scientific assurance layer.

M3 answers: what uncertainty exists, which channels are known versus unknown,
is the numerical result trustworthy, is the domain interpretation trustworthy,
is calibration adequate, is the evidence admissible, and what verdict is
justified.

It answers none of these: what to run next, whether to explore or optimize,
when to stop, or what a result is worth. Those are decisions, and M3 is not a
decision layer.

The admission path is unchanged from M1, with the Arbiter now filled in:

    Evidence -> Critics -> Arbiter -> authorized AdmissionDeclaration
             -> Belief Update Gateway -> Scientific Belief

Critics are pure — they return assessments and hold nothing that could write
belief. The Arbiter is the only issuer of a final assurance verdict, and even
it cannot admit anything directly: it asks a registered AdmissionAuthority for
a signed declaration bound to one evidence record, which the Gateway then
verifies on its own. There is no second admission route.

The claim M3 supports is narrow and deliberate: **SRIA can enforce declared
validation obligations through typed critic assessments and a single
Arbiter/Gateway admission path.** It is not universal scientific validation,
not proof that outputs are physically true, not automated discovery, and not
safety certification.
"""

from __future__ import annotations

from .arbiter import (
    ARBITER_VERSION,
    Arbiter,
    ArbiterDecision,
    AssuranceVerdict,
    ObligationResult,
)
from .assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    Severity,
    UncertaintyObservation,
    observations_from_budget,
)
from .critics import (
    DOMAIN_CHECK_VOCABULARY,
    CalibrationCriticAdapter,
    Critic,
    DomainCritic,
    NumericalCritic,
    model_discrepancy_check,
)
from .obligations import (
    ObligationKind,
    ObligationSet,
    ValidationObligation,
    obligations_from_charter,
)
from .uncertainty_budget import (
    SURROGATE_APPROXIMATION_CHANNEL,
    AggregationRecord,
    BudgetError,
    ChannelEntry,
    ChannelState,
    IncomparableUncertainty,
    UncertaintyBudget,
    budget_from_declaration,
)

SRIA_ASSURANCE_VERSION = "0.1.0-m3-assurance"

__all__ = [
    "SRIA_ASSURANCE_VERSION",
    # uncertainty budget
    "UncertaintyBudget",
    "ChannelEntry",
    "ChannelState",
    "AggregationRecord",
    "BudgetError",
    "IncomparableUncertainty",
    "budget_from_declaration",
    "SURROGATE_APPROXIMATION_CHANNEL",
    # assessment
    "CriticAssessment",
    "CriticClass",
    "CriticVerdict",
    "CheckRecord",
    "Finding",
    "Severity",
    "UncertaintyObservation",
    "observations_from_budget",
    # critics
    "Critic",
    "NumericalCritic",
    "DomainCritic",
    "CalibrationCriticAdapter",
    "model_discrepancy_check",
    "DOMAIN_CHECK_VOCABULARY",
    # obligations
    "ObligationSet",
    "ValidationObligation",
    "ObligationKind",
    "obligations_from_charter",
    # arbiter
    "Arbiter",
    "ArbiterDecision",
    "AssuranceVerdict",
    "ObligationResult",
    "ARBITER_VERSION",
]
