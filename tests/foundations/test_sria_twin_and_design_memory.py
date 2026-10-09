"""Rock 3: twin evidence resolved against SRIA records + belief; design memory anchored in the campaign event chain.

Admission here goes through the real SRIA path (authority, registrar, signed declaration, gateway) using the
test-only authority of ``tests/test_sria_m1.py``; nothing in this file grants standing any other way.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import tests.test_sria_m1 as M1
from engcore.design.history import AttemptOutcome, DesignAttempt, DesignHistory
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.twins import ScientificTwin, TwinDatum, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.sria.assurance.obligations import obligations_from_charter
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.campaign.events import CampaignEventType
from engcore.sria.campaign.persistence import IncrementalCheckpointStore
from engcore.sria.campaign.persistence_runner import IncrementalCampaignRunner
from engcore.sria.charter import CampaignCharter, TerminalDecision
from engcore.claims.design_memory import (
    CHAIN_KIND, DesignMemoryRefused, anchor_design_history, load_design_history, restore_design_history, save_design_history,
)
from engcore.sria.campaign.anchors import AnchorRefused, chain_anchors
from engcore.sria.evidence import ClaimBinding, ClaimType, Evidence, SourceClass
from engcore.claims.twin_evidence import TwinEvidenceRefused, resolve_twin_evidence, sria_reference
from engcore.systems.twin_revision import EvidenceReference, EvidenceRole, TwinRevision, TwinRevisionRefusal

# ---------------------------------------------------------------- twin evidence


def revision(kind=TwinKind.REFERENCE, thickness=0.01):
    twin = ScientificTwin("slab", "1", kind, models=(ModelReference("conduction.steady_1d", "1"),),
                          declarations=(TwinDatum("thickness", Quantity(thickness, "m")),))
    return TwinRevision(twin=twin, geometry_digests=("1" * 64,), material_digests=("3" * 64,))


def record(eid, ctx, *, source=SourceClass.MEASUREMENT, claim=ClaimType.MODEL_SUPPORT_OR_CONTRADICTION, value=310.0):
    return Evidence(evidence_id=eid, source_class=source, claim_type=claim,
                    claim_binding=ClaimBinding(subject_kind="model", subject_ref="conduction.steady_1d"),
                    claim_payload={"value": value, "units": "kelvin"}, uncertainty=M1.make_uncertainty(),
                    provenance_ref=f"lab-run-{eid}", domain_pack_ref="thermal.lumped", context_ref=ctx)


def admitted(ev, gateway):
    assessed = ev.with_assessment(M1.make_assessment(f"as-{ev.evidence_id}"))
    accepted = assessed.admit(M1.make_admission(assessed))
    gateway.submit(accepted)
    return accepted


def test_a_validation_pointer_resolves_only_to_an_admitted_record_of_this_context():
    base = revision()
    ctx = base.context_digest
    gateway = M1.make_gateway()
    ev = admitted(record("val-1", ctx), gateway)
    rev = base.with_evidence(sria_reference(ev, EvidenceRole.VALIDATION))
    resolved = resolve_twin_evidence(rev, [ev], belief=gateway.belief)
    assert resolved.entries[0]["status"] == "accepted" and resolved.entries[0]["record_hash"] == ev.record_hash
    # the authority of a validation role is admission into belief: no belief, no support
    with pytest.raises(TwinEvidenceRefused, match="belief must be supplied"):
        resolve_twin_evidence(rev, [ev])
    # a record carrying ACCEPTED that the gateway never admitted is not belief
    other_gateway = M1.make_gateway()
    with pytest.raises(TwinEvidenceRefused, match="not an active belief entry"):
        resolve_twin_evidence(rev, [ev], belief=other_gateway.belief)
    # a missing record backs nothing; removing it never leaves the revision supported
    with pytest.raises(TwinEvidenceRefused, match="missing record backs nothing"):
        resolve_twin_evidence(rev, [], belief=gateway.belief)


def test_withdrawn_standing_withdraws_the_support():
    base = revision()
    gateway = M1.make_gateway()
    ev = admitted(record("val-2", base.context_digest), gateway)
    rev = base.with_evidence(sria_reference(ev, EvidenceRole.VALIDATION))
    suspended = ev.suspend("instrument calibration lapsed")
    gateway.update_standing(suspended)
    with pytest.raises(TwinEvidenceRefused, match="suspended"):
        resolve_twin_evidence(rev, [suspended], belief=gateway.belief)
    with pytest.raises(TwinEvidenceRefused, match="not an active belief entry"):
        resolve_twin_evidence(rev, [ev], belief=gateway.belief)  # the stale ACCEPTED copy no longer matches belief


def test_roles_contexts_and_record_identity_are_enforced():
    base = revision()
    ctx = base.context_digest
    gateway = M1.make_gateway()
    sim = record("sim-1", ctx, source=SourceClass.SIMULATION, claim=ClaimType.QOI_VALUE)
    with pytest.raises(TwinEvidenceRefused, match="cannot back the validation role"):
        sria_reference(sim, EvidenceRole.VALIDATION)  # a simulation never validates
    with pytest.raises(TwinEvidenceRefused, match="needs"):
        sria_reference(record("cand-1", ctx), EvidenceRole.VALIDATION)  # candidate standing is not admission
    # a provider run is recorded, not admitted: it resolves without belief
    run_rev = base.with_evidence(sria_reference(sim, EvidenceRole.PROVIDER_RUN))
    assert resolve_twin_evidence(run_rev, [sim]).entries[0]["role"] == "provider_run"
    # a record produced for another context cannot be attached, and a pointer that lies about its context does not resolve
    foreign = admitted(record("val-3", "9" * 64), gateway)
    with pytest.raises(TwinRevisionRefusal, match="another context"):
        base.with_evidence(sria_reference(foreign, EvidenceRole.VALIDATION))
    lying = base.with_evidence(EvidenceReference(f"sria:val-3@{foreign.record_hash}", EvidenceRole.VALIDATION, ctx))
    with pytest.raises(TwinEvidenceRefused, match="produced for context"):
        resolve_twin_evidence(lying, [foreign], belief=gateway.belief)
    # the pointer names one exact record: a different record under the same id does not resolve
    ev = admitted(record("val-4", ctx), gateway)
    rev = base.with_evidence(sria_reference(ev, EvidenceRole.VALIDATION))
    swapped = admitted(record("val-4", ctx, value=999.0), M1.make_gateway())
    with pytest.raises(TwinEvidenceRefused, match="another record"):
        resolve_twin_evidence(rev, [swapped], belief=gateway.belief)
    # a pointer that is not an SRIA reference is not resolved by assumption
    plain = base.with_evidence(EvidenceReference("run:abc", EvidenceRole.PROVIDER_RUN, ctx))
    with pytest.raises(TwinEvidenceRefused, match="does not name an SRIA record"):
        resolve_twin_evidence(plain, [sim])


def test_a_candidate_twin_still_refuses_physical_evidence_even_when_admitted():
    base = revision(kind=TwinKind.CANDIDATE)
    gateway = M1.make_gateway()
    ev = admitted(record("val-5", base.context_digest), gateway)
    with pytest.raises(TwinRevisionRefusal, match="CANDIDATE"):
        base.with_evidence(sria_reference(ev, EvidenceRole.VALIDATION))


# ---------------------------------------------------------------- design memory


def attempt(key, outcome=AttemptOutcome.REFUSED, ctx="c" * 64):
    return DesignAttempt(key, "analytic", ctx, outcome, f"{key}: {outcome.value}")


def history(*keys):
    h = DesignHistory()
    for k in keys:
        h.record(attempt(k))
    return h


def runner(store):
    charter = CampaignCharter(campaign_id="design-memory", terminal_decisions=(TerminalDecision(decision_id="d", statement="s"),))
    return IncrementalCampaignRunner(run_id="dm-run", charter=charter, harness=MagicMock(), gateway=MagicMock(), arbiter=MagicMock(),
                                     obligations=obligations_from_charter(charter), budget=BudgetLedger(total_budget=10.0),
                                     max_iterations=2, checkpoints=store, liveness=MagicMock(), stopping=MagicMock(),
                                     clock=lambda: "t")


def test_design_memory_is_committed_into_the_campaign_chain_and_survives_resume(tmp_path):
    store = IncrementalCheckpointStore()
    r = runner(store)
    h = history("a", "b")
    event = anchor_design_history(r, h)
    assert event.event_type is CampaignEventType.RECORD_CHAIN_ANCHORED and event.payload["head"] == h.head
    h.record(attempt("c"))
    anchor_design_history(r, h)  # growth extends the anchor
    rewritten = history("a", "x", "c")
    with pytest.raises(DesignMemoryRefused, match="rewritten"):
        anchor_design_history(r, rewritten)
    # SRIA's own primitive refuses a shrinking or rewritten chain even when called directly
    with pytest.raises(AnchorRefused, match="shrank"):
        r.anchor_record_chain(CHAIN_KIND, h.to_dict()["schema"], history("a").head, 1)
    with pytest.raises(AnchorRefused, match="rewritten"):
        r.anchor_record_chain(CHAIN_KIND, h.to_dict()["schema"], rewritten.head, 3)
    path = tmp_path / "design_history.json"
    save_design_history(path, h)

    resumed = runner(store)
    resumed.restore_latest()
    assert len(chain_anchors(resumed.events, CHAIN_KIND)) == 2
    memory = load_design_history(path, resumed.events)
    assert memory.history.head == h.head and memory.unanchored_attempts == 0
    assert memory.history.should_skip("a", "analytic", "c" * 64, provider="")[0]  # the known negative is remembered

    # a truncated memory (the last negative dropped) is refused, not treated as a fresh start
    with pytest.raises(DesignMemoryRefused, match="truncated"):
        restore_design_history(resumed.events, history("a", "b").to_dict())
    # growth after the last anchor is allowed and counted, never silently anchored
    h.record(attempt("d"))
    assert restore_design_history(resumed.events, h.to_dict()).unanchored_attempts == 1
    # no anchor, no memory: an absent anchor is not an empty history; an absent file is not either
    with pytest.raises(DesignMemoryRefused, match="anchors no design history"):
        restore_design_history(runner(IncrementalCheckpointStore()).events, h.to_dict())
    with pytest.raises(DesignMemoryRefused, match="not an empty one"):
        load_design_history(tmp_path / "missing.json", resumed.events)


def test_anchoring_never_happens_inside_an_iteration():
    r = runner(IncrementalCheckpointStore())
    r._plan = object()  # an in-flight iteration
    with pytest.raises(ValueError, match="between iterations"):
        anchor_design_history(r, history("a"))


# ---------------------------------------------------------------- review round (Rock 3)


def test_only_the_gateways_belief_is_admission():
    import dataclasses
    import types

    from engcore.sria.evidence import EvidenceStatus

    base = revision()
    forged = dataclasses.replace(record("val-f", base.context_digest), status=EvidenceStatus.ACCEPTED)  # status is not identity-bound
    rev = base.with_evidence(sria_reference(forged, EvidenceRole.VALIDATION))
    fake = types.SimpleNamespace(active_view=lambda: {"val-f": types.SimpleNamespace(record_hash=forged.record_hash)})
    with pytest.raises(TwinEvidenceRefused, match="look-alike"):
        resolve_twin_evidence(rev, [forged], belief=fake)
    with pytest.raises(TwinEvidenceRefused, match="not an active belief entry"):
        resolve_twin_evidence(rev, [forged], belief=M1.make_gateway().belief)
    # an invalidated record backs nothing
    gateway = M1.make_gateway()
    ev = admitted(record("val-i", base.context_digest), gateway)
    with pytest.raises(TwinEvidenceRefused, match="invalid"):
        sria_reference(ev.invalidate("instrument fault found"), EvidenceRole.VALIDATION)


def _assessed(ev, verdict):
    from engcore.sria.evidence import Assessment, AssessmentVerdict
    from engcore.sria.provenance import AssessmentProvenance

    return ev.with_assessment(Assessment(AssessmentVerdict(verdict), AssessmentProvenance(
        assessment_id=f"as-{ev.evidence_id}-{verdict}", critic_id="critic.residual", critic_version="1.0")))


def test_verification_needs_a_passing_assessment():
    base = revision()
    ctx = base.context_digest
    sim = record("ver-1", ctx, source=SourceClass.SIMULATION, claim=ClaimType.QOI_VALUE)
    with pytest.raises(TwinEvidenceRefused, match="needs"):
        sria_reference(sim, EvidenceRole.VERIFICATION)  # unassessed
    with pytest.raises(TwinEvidenceRefused, match="PASS assessment"):
        sria_reference(_assessed(sim, "fail"), EvidenceRole.VERIFICATION)
    with pytest.raises(TwinEvidenceRefused, match="PASS assessment"):
        sria_reference(_assessed(_assessed(sim, "pass"), "inconclusive"), EvidenceRole.VERIFICATION)
    ok = _assessed(sim, "pass")
    bench = _assessed(record("ver-2", ctx, source=SourceClass.BENCHMARK, claim=ClaimType.QOI_VALUE), "pass")
    rev = base.with_evidence(sria_reference(ok, EvidenceRole.VERIFICATION), sria_reference(bench, EvidenceRole.VERIFICATION))
    resolved = resolve_twin_evidence(rev, [ok, bench])
    assert {e["standing"] for e in resolved.entries} == {"assessed_pass"}


def test_physical_roles_are_about_the_twins_model_and_omissions_are_listed():
    base = revision()
    ctx = base.context_digest
    gateway = M1.make_gateway()
    meas = admitted(record("m-1", ctx, claim=ClaimType.PARAMETER_VALUE), gateway)
    cal = admitted(record("c-1", ctx, claim=ClaimType.CALIBRATION_REFERENCE), gateway)
    support = admitted(Evidence(evidence_id="s-1", source_class=SourceClass.MEASUREMENT, claim_type=ClaimType.MODEL_SUPPORT_OR_CONTRADICTION,
                                claim_binding=ClaimBinding(subject_kind="model", subject_ref="conduction.steady_1d"),
                                claim_payload={"polarity": "supports", "residual": 0.4}, uncertainty=M1.make_uncertainty(),
                                provenance_ref="lab-s-1", domain_pack_ref="thermal.lumped", context_ref=ctx), gateway)
    contra = admitted(Evidence(evidence_id="x-1", source_class=SourceClass.MEASUREMENT, claim_type=ClaimType.MODEL_SUPPORT_OR_CONTRADICTION,
                               claim_binding=ClaimBinding(subject_kind="model", subject_ref="conduction.steady_1d", qualifiers={"rig": "B"}),
                               claim_payload={"polarity": "contradicts", "residual": 9.0}, uncertainty=M1.make_uncertainty(),
                               provenance_ref="lab-x-1", domain_pack_ref="thermal.lumped", context_ref=ctx), gateway)
    rev = base.with_evidence(sria_reference(meas, EvidenceRole.MEASUREMENT), sria_reference(cal, EvidenceRole.CALIBRATION),
                             sria_reference(support, EvidenceRole.VALIDATION))
    resolved = resolve_twin_evidence(rev, [meas, cal, support, contra], belief=gateway.belief)
    assert resolved.classification == "pointer_resolution_not_a_validation_verdict"
    assert {e["evidence_id"]: e["polarity"] for e in resolved.entries}["s-1"] == "supports"
    assert resolved.unreferenced_active_evidence == ("x-1",)  # the omitted contradiction is visible
    other_model = admitted(Evidence(evidence_id="o-1", source_class=SourceClass.MEASUREMENT, claim_type=ClaimType.MODEL_SUPPORT_OR_CONTRADICTION,
                                    claim_binding=ClaimBinding(subject_kind="model", subject_ref="radiation.gray_body"),
                                    claim_payload={"polarity": "supports"}, uncertainty=M1.make_uncertainty(), provenance_ref="lab-o-1",
                                    domain_pack_ref="thermal.lumped", context_ref=ctx), gateway)
    wrong = base.with_evidence(sria_reference(other_model, EvidenceRole.VALIDATION))
    with pytest.raises(TwinEvidenceRefused, match="not one of the twin's models"):
        resolve_twin_evidence(wrong, [other_model], belief=gateway.belief)


def test_anchors_appended_around_the_runner_are_revalidated(tmp_path):
    from engcore.design.history import GENESIS, HISTORY_SCHEMA
    from engcore.sria.campaign.anchors import RECORD_CHAIN_ANCHOR_SCHEMA
    from engcore.sria.campaign.events import derive_obligation_state

    r = runner(IncrementalCheckpointStore())
    h = history("a", "b")
    anchor_design_history(r, h)
    before = derive_obligation_state(r.events)
    # the log's append is public: a shrinking anchor written around anchor_record_chain makes the anchors refused
    r.events.append(CampaignEventType.RECORD_CHAIN_ANCHORED, iteration=0, payload={
        "schema": RECORD_CHAIN_ANCHOR_SCHEMA, "chain_kind": CHAIN_KIND, "chain_schema": HISTORY_SCHEMA, "head": GENESIS, "length": 0})
    with pytest.raises(AnchorRefused, match="shrank"):
        restore_design_history(r.events, DesignHistory().to_dict())
    r2 = runner(IncrementalCheckpointStore())
    r2.events.append(CampaignEventType.RECORD_CHAIN_ANCHORED, iteration=0, payload={
        "schema": RECORD_CHAIN_ANCHOR_SCHEMA, "chain_kind": CHAIN_KIND, "chain_schema": HISTORY_SCHEMA, "head": GENESIS, "length": -1})
    with pytest.raises(AnchorRefused, match="malformed"):
        restore_design_history(r2.events, DesignHistory().to_dict())
    # an anchor is not assurance: obligation derivation ignores it
    assert derive_obligation_state(r.events) == before


def test_no_anchor_after_the_run_ended():
    import dataclasses

    from engcore.sria.campaign.state import ExecutionState

    r = runner(IncrementalCheckpointStore())
    r._run = dataclasses.replace(r._run, state=ExecutionState.COMPLETED)
    with pytest.raises(ValueError, match="after the run ended"):
        anchor_design_history(r, history("a"))
