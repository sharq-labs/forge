"""BR-MIND-REPSEM-01 failing-first tests: the battery_rediscovery_v1 failure classes, on synthetic fixtures.

Written before ``engcore.mind.repsem`` existed.  Each test reproduces one CLASS of v1 failure (from the gap map in
``benchmarks/mind_repsem_v1/results/GAP_MAP.json``) on a synthetic system whose answer is known from construction;
no battery v1 data, answer or truth is read here.

A. model inadequacy is representable as NOT_SUPPORTED
B. non-identifiability is representable explicitly
C. cross-cell transfer can be NOT_SUPPORTED without refusing the question
D. model discrepancy can be represented (and is not adequacy)
E. SOC is a STATE_VARIABLE, not a free observed predictor
F. fixed current levels stay FIXED_PROTOCOL_CONDITION
G. latent RC parameters are not observed variables
H. negative scientific evidence does not become NOT_ASSESSABLE

Counter-tests: unsupported evidence never becomes SUPPORTED, missing evidence still refuses, out-of-domain still refuses.
"""

from __future__ import annotations

import copy

import pytest

from benchmarks.mind_repsem_v1 import fixtures as fx
from engcore.mind.repsem import (
    ClaimState, Disposition, Refusal, RefusalReason, RoleRefused, RoleTable, ScopedClaim, ScopedClaimRefused, VariableRole,
    assess, legacy_role_table,
)

SEED = 0


@pytest.fixture(scope="module")
def runs():
    return {name: assess(fx.build(name, SEED), fx.FAMILIES) for name in fx.FIXTURES}


# ---- A. model inadequacy ----------------------------------------------------------------------------------------
def test_a_model_inadequacy_is_a_representable_negative_claim():
    claim = ScopedClaim("MODEL_ADEQUACY", Disposition.NOT_SUPPORTED, state=ClaimState.MODEL_INADEQUATE,
                        scope={"family": "f"}, evidence=("sha256:x",), reason="residual exceeds the declared bar")
    assert ScopedClaim.from_dict(claim.to_dict()) == claim


def test_a_inadequate_family_is_judged_not_supported(runs):
    c = runs["MODEL_INADEQUATE"].claims["MODEL_ADEQUACY"]
    assert (c.disposition, c.state, c.refusal) == (Disposition.NOT_SUPPORTED, ClaimState.MODEL_INADEQUATE, None)


# ---- B. non-identifiability -------------------------------------------------------------------------------------
def test_b_non_identifiability_is_explicit(runs):
    c = runs["NON_IDENTIFIABLE"].claims["IDENTIFIABILITY"]
    assert (c.disposition, c.state) == (Disposition.NOT_SUPPORTED, ClaimState.NOT_IDENTIFIABLE)
    assert c.evidence, "a decisive claim names its evidence"


def test_b_claim_state_and_refusal_reason_are_different_things():
    # The brief names both NOT_IDENTIFIABLE: one is a decisive negative claim, the other a reason to refuse.
    decided = ScopedClaim("IDENTIFIABILITY", Disposition.NOT_SUPPORTED, state=ClaimState.NOT_IDENTIFIABLE,
                          evidence=("e",), reason="rank-deficient").to_dict()
    refusal = ScopedClaim("WITHIN_CELL_GENERALIZATION", Disposition.REFUSED,
                          refusal=Refusal(RefusalReason.NOT_IDENTIFIABLE, {"why": "x"}), reason="x").to_dict()
    assert (decided["state"], decided["refusal"]) == ("NOT_IDENTIFIABLE", None)
    assert (refusal["state"], refusal["refusal"]["reason"]) == (None, "NOT_IDENTIFIABLE")
    assert type(ClaimState.NOT_IDENTIFIABLE) is not type(RefusalReason.NOT_IDENTIFIABLE)


# ---- C. cross-cell transfer -------------------------------------------------------------------------------------
def test_c_cross_cell_transfer_not_supported_without_refusal(runs):
    c = runs["CROSS_DOMAIN_TRANSFER_FAIL"].claims["CROSS_CELL_TRANSFER"]
    assert (c.disposition, c.state, c.refusal) == (Disposition.NOT_SUPPORTED, ClaimState.CROSS_CELL_NOT_SUPPORTED, None)
    w = runs["CROSS_DOMAIN_TRANSFER_FAIL"].claims["WITHIN_CELL_GENERALIZATION"]
    assert (w.disposition, w.state) == (Disposition.SUPPORTED, ClaimState.WITHIN_CELL_SUPPORTED)


# ---- D. model discrepancy ---------------------------------------------------------------------------------------
def test_d_model_discrepancy_is_representable_and_distinct_from_adequacy(runs):
    r = runs["MODEL_DISCREPANCY"]
    d, a = r.claims["MODEL_DISCREPANCY"], r.claims["MODEL_ADEQUACY"]
    assert (d.disposition, d.state) == (Disposition.NOT_SUPPORTED, ClaimState.MODEL_DISCREPANCY_PRESENT)
    assert (a.disposition, a.state) == (Disposition.SUPPORTED, ClaimState.MODEL_ADEQUATE)


def test_d_unresolved_discrepancy_is_not_zero_discrepancy(runs):
    d = runs["IDENTIFIABLE"].claims["MODEL_DISCREPANCY"]
    assert d.state is ClaimState.MODEL_DISCREPANCY_UNRESOLVED
    assert "not_quantified_as_zero" in d.scope


# ---- E. state variables -----------------------------------------------------------------------------------------
def test_e_soc_is_a_state_variable_not_a_free_predictor():
    table = RoleTable.from_spec(fx.build("IDENTIFIABLE", SEED))
    assert table.role("soc") is VariableRole.STATE_VARIABLE
    assert "soc" not in table.free_predictors()
    assert table.declaration("soc").driven_by == ("current_A",)


def test_e_the_observed_soc_column_never_enters_the_judgment():
    spec = fx.build("IDENTIFIABLE", SEED)
    tampered = copy.deepcopy(spec)
    for traj in tampered["sets"]["calibration"]:
        traj["columns"]["soc"] = [0.5 for _ in traj["columns"]["soc"]]
    a, b = assess(spec, fx.FAMILIES), assess(tampered, fx.FAMILIES)
    assert {k: c.to_dict() for k, c in a.claims.items()} == {k: c.to_dict() for k, c in b.claims.items()}


# ---- F. fixed protocol conditions -------------------------------------------------------------------------------
def test_f_fixed_current_level_stays_a_protocol_condition():
    spec = fx.build("IDENTIFIABLE", SEED)
    table = RoleTable.from_spec(spec)
    assert table.role("level_A") is VariableRole.FIXED_PROTOCOL_CONDITION
    assert "level_A" in table.interventional() and "level_A" not in table.passive()


def test_f_roles_are_never_inferred_from_names_or_data():
    spec = fx.build("IDENTIFIABLE", SEED)
    spec["variables"] = [v for v in spec["variables"] if v["name"] != "soc"]
    with pytest.raises(RoleRefused, match="soc"):
        RoleTable.from_spec(spec)
    spec = fx.build("IDENTIFIABLE", SEED)
    for v in spec["variables"]:
        if v["name"] == "level_A":
            v["source"] = "column_name"
    with pytest.raises(RoleRefused, match="source"):
        RoleTable.from_spec(spec)


# ---- G. latent parameters ---------------------------------------------------------------------------------------
def test_g_latent_parameters_have_no_data_column():
    spec = fx.build("IDENTIFIABLE", SEED)
    for traj in spec["sets"]["calibration"]:
        traj["columns"]["R0"] = [0.01] * len(traj["columns"]["t_s"])
    with pytest.raises(RoleRefused, match="latent"):
        assess(spec, fx.FAMILIES)


def test_g_latent_parameters_are_estimated_not_observed(runs):
    h = runs["IDENTIFIABLE"].hypothesis
    names = [p.name for p in h.parameter_set]
    assert names == ["C1", "R0", "R1"]
    assert all(p.estimate is not None for p in h.parameter_set)
    assert not set(names) & set(RoleTable.from_spec(fx.build("IDENTIFIABLE", SEED)).observed())


# ---- H. negative evidence ---------------------------------------------------------------------------------------
def test_h_negative_evidence_is_not_supported_not_unassessable(runs):
    # v1 answered every one of these NOT_ASSESSABLE.  (Written first against MODEL_INADEQUATE's within-cell set, whose
    # NOT label the construction audit later disproved: the interpolated level is predicted within the bar.)
    r = runs["MODEL_INADEQUATE"]
    for axis in ("MODEL_ADEQUACY", "MODEL_DISCREPANCY"):
        assert r.claims[axis].disposition is Disposition.NOT_SUPPORTED
    cross = runs["CROSS_DOMAIN_TRANSFER_FAIL"].claims["CROSS_CELL_TRANSFER"]
    assert cross.disposition is Disposition.NOT_SUPPORTED and cross.evidence


def test_h_structural_non_identifiability_is_decided_without_declared_noise():
    spec = fx.build("NON_IDENTIFIABLE", SEED)
    spec["measurement_noise"] = {"sigma": None, "independent": None}
    c = assess(spec, fx.FAMILIES).claims["IDENTIFIABILITY"]
    assert (c.disposition, c.state) == (Disposition.NOT_SUPPORTED, ClaimState.NOT_IDENTIFIABLE)


# ---- counter-tests ----------------------------------------------------------------------------------------------
def test_counter_unsupported_evidence_never_becomes_support():
    with pytest.raises(ScopedClaimRefused):
        ScopedClaim("IDENTIFIABILITY", Disposition.SUPPORTED, state=ClaimState.NOT_IDENTIFIABLE, evidence=("e",), reason="x")
    with pytest.raises(ScopedClaimRefused):
        ScopedClaim("IDENTIFIABILITY", Disposition.SUPPORTED, state=ClaimState.IDENTIFIABLE, evidence=(), reason="x")
    for seed in range(3):
        c = assess(fx.build("NON_IDENTIFIABLE", seed), fx.FAMILIES).claims["IDENTIFIABILITY"]
        assert c.disposition is not Disposition.SUPPORTED


def test_counter_missing_evidence_still_refuses():
    spec = fx.build("IDENTIFIABLE", SEED)
    spec["measurement_noise"] = {"sigma": None, "independent": None}
    spec["adequacy_bar"] = None
    r = assess(spec, fx.FAMILIES)
    for axis in ("MODEL_ADEQUACY", "MODEL_DISCREPANCY"):
        assert r.claims[axis].disposition is Disposition.NOT_ASSESSABLE
        assert r.claims[axis].refusal.reason is RefusalReason.INSUFFICIENT_EVIDENCE
    absent = r.claims["CROSS_CELL_TRANSFER"]
    assert (absent.disposition, absent.refusal.reason) == (Disposition.NOT_ASSESSABLE, RefusalReason.INSUFFICIENT_EVIDENCE)
    spec = fx.build("IDENTIFIABLE", SEED)
    spec["acceptance"] = {}
    w = assess(spec, fx.FAMILIES).claims["WITHIN_CELL_GENERALIZATION"]
    assert w.disposition is Disposition.NOT_ASSESSABLE and w.refusal.reason is RefusalReason.INSUFFICIENT_EVIDENCE


def test_counter_out_of_domain_still_refuses(runs):
    c = runs["OUT_OF_DOMAIN"].claims["WITHIN_CELL_GENERALIZATION"]
    assert (c.disposition, c.refusal.reason) == (Disposition.REFUSED, RefusalReason.OUT_OF_DOMAIN)
    assert "heldout_stats" not in c.refusal.condition, "applicability precedes evidence-bearing execution"


@pytest.mark.parametrize("var", ["R0", "voltage_V", "nonexistent"])
def test_counter_an_unrepresentable_domain_refuses_transfer_without_crashing(var):
    spec = fx.build("IDENTIFIABLE", SEED)
    spec["applicability"]["variables"] = ["current_A", var]
    c = assess(spec, fx.FAMILIES).claims["WITHIN_CELL_GENERALIZATION"]
    assert (c.disposition, c.refusal.reason) == (Disposition.REFUSED, RefusalReason.REPRESENTATION_UNAVAILABLE)


def test_counter_every_refusal_names_a_condition():
    with pytest.raises(ScopedClaimRefused):
        ScopedClaim("MODEL_ADEQUACY", Disposition.REFUSED, reason="no reason given")


def test_counter_legacy_roles_cannot_bind_the_declared_family():
    spec = fx.build("IDENTIFIABLE", SEED)
    r = assess(spec, fx.FAMILIES, roles=legacy_role_table(spec))
    for axis in ("IDENTIFIABILITY", "MODEL_ADEQUACY", "MODEL_DISCREPANCY", "WITHIN_CELL_GENERALIZATION"):
        assert r.claims[axis].disposition is Disposition.REFUSED
        assert r.claims[axis].refusal.reason is RefusalReason.REPRESENTATION_UNAVAILABLE
