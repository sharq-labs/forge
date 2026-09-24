"""IND-04 and IND-06: what the CSTR gate's reference arms may claim, and say.

IND-04. ``independent_steady_state_agreement`` awarded ``CROSS_SOLVER_VALIDATED``
and its detail said the reference "shares no arithmetic with the integrator".
It does share arithmetic: the Brent steady state is fed the SAME derived
parameters the solver assembles from -- ``run.chemistry.beta_m3_k_per_mol``,
``run.gamma_per_s``, ``run.operation.dilution_rate_per_s`` -- so an error in
that preprocessing is invisible to the comparison, exactly the kind of shared
machinery ``CrossSolverConsensus`` refuses a level for. It is not routed through
a pinned consensus, and it is not a closed form (a bracketed numerical root), so
it earns no level. The comparison is still run and reported.

IND-06. The cross-method detail always read "agree on every QoI to X", including
when the arms disagreed, and raised ``TypeError`` (``f"{None:.3e}"``) when
nothing could be compared.
"""

from __future__ import annotations

import inspect

import pytest

from engcore.domains.kinetics.cstr import validation as cstr_validation
from engcore.domains.kinetics.cstr.validation import run_verification_gate
from engcore.scientific.consensus import RouteComparison
from engcore.scientific.results.validation import ValidationLevel

pytestmark = pytest.mark.expensive


@pytest.fixture(scope="module")
def gate():
    from experiments.kinetics_k1.k1_config import regime

    return run_verification_gate(regime("R1").build(), run_id_prefix="audit-ind04")


def test_the_steady_state_arm_still_runs_and_agrees(gate):
    assert gate.steady_state_verified is True
    assert gate.steady_state_rel_error is not None


def test_the_steady_state_arm_establishes_no_cross_solver_level(gate):
    check = next(
        c for c in gate.to_report().checks if c.name == "independent_steady_state_agreement"
    )
    assert check.establishes is None
    # The separately translated LSODA route is still evidence-only in
    # production because no artifact-backed RouteIndependenceEvidence is
    # supplied to the trusted consensus gate yet.
    independent = next(
        c for c in gate.to_report().checks if c.name == "independent_solver_agreement"
    )
    assert independent.establishes is None
    # The gate's own authority must withhold the level too; checking only the
    # serialized report leaves a mutation in levels_earned invisible.
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in gate.levels_earned
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in gate.to_report().attained_levels


def test_the_steady_state_detail_no_longer_claims_it_shares_no_arithmetic(gate):
    assert "shares no arithmetic" not in gate.steady_state_detail
    assert "derived parameters" in gate.steady_state_detail
    source = inspect.getsource(cstr_validation)
    assert "shares no arithmetic with the integrator" not in source


def test_independent_solver_level_is_withheld_until_artifact_independence_exists():
    source = inspect.getsource(cstr_validation.CSTRVerificationReport)
    assert "TrustedConsensusGate().assess" in source
    assert "self.independent_solver_consensus" in source
    # Production deliberately supplies no independence evidence yet.
    assert "self.independent_solver_consensus,\n            ()," in source
    # The legacy steady-state arm remains evidence-only too.
    assert "steady_state_verified else ValidationLevel.CROSS_SOLVER_VALIDATED" not in source


# ---- IND-06 -----------------------------------------------------------------------------
def test_a_disagreeing_cross_method_comparison_is_not_described_as_agreement():
    comparison = RouteComparison(("ca",), "ca", 0.25, 1e-6)
    detail = cstr_validation._cross_method_detail("BDF", "Radau", "rtol=1e-12", comparison)
    assert "agree on every QoI" not in detail
    assert "disagree" in detail
    assert "2.500e-01" in detail


def test_a_comparison_of_nothing_is_described_and_does_not_raise():
    comparison = RouteComparison((), "", None, 1e-6, detail="nothing in common")
    detail = cstr_validation._cross_method_detail("BDF", "Radau", "rtol=1e-12", comparison)
    assert "no comparison" in detail
    assert "agree" not in detail.split("establishes")[0]


def test_an_agreeing_comparison_still_says_so():
    comparison = RouteComparison(("ca",), "ca", 1e-9, 1e-6)
    detail = cstr_validation._cross_method_detail("BDF", "Radau", "rtol=1e-12", comparison)
    assert "agree on every QoI to 1.000e-09" in detail
    assert "NO validation level" in detail
