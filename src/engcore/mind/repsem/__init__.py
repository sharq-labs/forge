"""BR-MIND-REPSEM-01: the minimal representation and scientific-role repair indicated by battery_rediscovery_v1.

Research layer, development only.  The v1 gap map (``benchmarks/mind_repsem_v1/results/GAP_MAP.json``) attributes the
Minimal Mind's 8 failures to a missing representation (5), to variables posed in the wrong scientific role (2), and to
both together with the log-linear hypothesis family (1).  This package adds, and only adds:

* :mod:`.roles` -- seven declared variable roles, from the problem specification or protocol metadata only;
* :mod:`.claims` -- five candidate dispositions, ten scoped claim states (one positive and one negative per v1 question)
  and six named refusal conditions;
* :mod:`.hypothesis` -- a hypothesis record that separates family, parameters, domain, roles, claims, alternatives,
  evidence for and against, and unresolved discriminators;
* :mod:`.families` / :mod:`.assess` -- role-typed binding of a declared model family, and deterministic, replayable
  judgments of it.

:mod:`engcore.mind.minimal` is not modified (battery_rediscovery_v1 pins it byte-exact).  Like it, this layer proposes;
it issues no verdict, grants no validation and quantifies no undeclared uncertainty.
"""

from .assess import (
    ASSESSMENT_SCHEMA, AXES, Assessment, PROBLEM_SCHEMA, ReplayMismatch, assess, canonical_bytes, problem_digest, replay,
)
from .claims import (
    CLAIM_TYPES, ClaimState, ClaimType, Disposition, Refusal, RefusalReason, ScopedClaim, ScopedClaimRefused,
)
from .families import Binding, BindingRefused, BoundTrajectory, DeclaredFamily, FamilySlot, bind
from .hypothesis import EvidenceItem, ParameterEstimate, ScientificHypothesis
from .roles import RoleDeclaration, RoleRefused, RoleSource, RoleTable, VariableRole, legacy_role_table

__all__ = [
    "ASSESSMENT_SCHEMA", "AXES", "Assessment", "Binding", "BindingRefused", "BoundTrajectory", "CLAIM_TYPES", "ClaimState",
    "ClaimType", "DeclaredFamily", "Disposition", "EvidenceItem", "FamilySlot", "PROBLEM_SCHEMA", "ParameterEstimate",
    "Refusal", "RefusalReason", "ReplayMismatch", "RoleDeclaration", "RoleRefused", "RoleSource", "RoleTable",
    "ScientificHypothesis", "ScopedClaim", "ScopedClaimRefused", "VariableRole", "assess", "bind", "canonical_bytes",
    "legacy_role_table", "problem_digest", "replay",
]
