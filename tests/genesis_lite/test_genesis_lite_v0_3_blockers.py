"""Genesis-lite v0.3 freeze blockers (BR-MIND-02B): FDA-18, FDA-21, FDA-22, pilot P-1/P-2/P-3, readiness P-3, the v0.3
harness binding, one attempt per root, and the freeze-readiness gate.

Each defect that v0.2 carries is pinned on the frozen v0.2 code (it stays there) and shown gone in v0.3. Worlds are
synthetic (generator seeds named here, never a pilot or formal root), and records are the synthetic shape of
``lift_records``.
"""

from __future__ import annotations

import hashlib
import json
import math
import socket

import numpy as np
import pytest

from benchmarks.genesis_lite import analysis as v02_analysis
from benchmarks.genesis_lite import arms as v02_arms
from benchmarks.genesis_lite import harness as v02_harness
from benchmarks.genesis_lite import preregistration as v02_prereg
from benchmarks.genesis_lite.v0_3 import analysis as v03a
from benchmarks.genesis_lite.v0_3 import arms as v03_arms
from benchmarks.genesis_lite.v0_3 import deployment_attacks as attacks
from benchmarks.genesis_lite.v0_3 import environment
from benchmarks.genesis_lite.v0_3 import evaluator as v03e
from benchmarks.genesis_lite.v0_3 import formal, harness, readiness
from benchmarks.genesis_lite.v0_3 import preregistration as v03p
from benchmarks.genesis_lite.v0_3.registry import AttemptRefused, AttemptRegistry
from tests.genesis_lite import lift_records as lr

MASTER = bytes(range(32))
TEST_BOUND = v03e.PairBound("tol_multiple", 5.0)          # a TEST value; the owner's w is not chosen here
MANIFEST = {"schema": environment.MANIFEST_SCHEMA, "python": {"version": "3.12.3"}, "distributions": {"numpy": "2.5.2"}}
H = hashlib.sha256


# ---- FDA-18: one proposer process per card ---------------------------------------------------------------------------
def test_fda18_v0_2_one_process_carries_state_across_the_cards_of_a_campaign():
    """Pinned defect (v0.2 is frozen): the stateful arm sees all six cards in one process."""
    rec = v02_harness.run_one("remembers", None, master_seed=MASTER, campaign_id="gl-fda18-0", presentation="anonymous",
                              isolation="proposer_process", arm_spec="tests.genesis_lite.stateful_arms:remembers")
    answers = sorted(u["answer"] for u in rec.universes)
    assert answers == ["insufficient_evidence"] * 5 + ["no_law"]


def test_fda18_v0_3_a_fresh_proposer_process_per_card_keeps_nothing_between_cards():
    arm = harness.fresh_process_per_card("tests.genesis_lite.stateful_arms:remembers")
    rec = v02_harness.run_one("remembers", arm, master_seed=MASTER, campaign_id="gl-fda18-0", presentation="anonymous",
                              isolation="in_process")
    assert [u["answer"] for u in rec.universes] == ["no_law"] * 6
    assert len(arm.host_starts) == 6


# ---- FDA-21: residual degrees of freedom -----------------------------------------------------------------------------
def _resid_ratio(fit, draws=3000):
    rng, sigma, out = np.random.default_rng(7), 0.1, []
    for _ in range(draws):
        x = rng.uniform(1.0, 10.0, (6, 3))
        y = 2.0 * x[:, 0] ** 0.5 * x[:, 1] * np.exp(rng.normal(0.0, sigma, 6))
        rows = [{"a": x[i, 0], "b": x[i, 1], "c": x[i, 2], "y": y[i]} for i in range(6)]
        out.append(fit(rows, ["a", "b", "c"], "y")[1] ** 2)
    return float(np.mean(out)) / sigma ** 2


def test_fda21_v0_2_residual_variance_is_biased_by_the_fitted_parameters():
    """Pinned defect: 6 rows, 4 parameters -> E[resid^2] / sigma^2 = 2/6."""
    assert abs(_resid_ratio(v02_arms._fit) - 2 / 6) < 0.03


def test_fda21_v0_3_residual_variance_is_unbiased():
    assert abs(_resid_ratio(v03_arms._fit) - 1.0) < 0.06


def test_fda21_v0_3_replicate_noise_uses_mean_zero_pairs():
    rows = [{"y": math.exp(v)} for v in (0.0, 0.0, 0.0, 0.0, 0.2, 0.2, 0.4, -0.2)]
    diffs = [0.2, 0.2, 0.4, -0.2]                                  # replicates 4..7 minus their bases 0..3
    assert v03_arms._replicate_noise(rows, 4, "y") == pytest.approx(math.sqrt(sum(d * d for d in diffs) / 8))
    assert v02_arms._replicate_noise(rows, 4, "y") == pytest.approx(float(np.std(diffs)) / math.sqrt(2))


def test_fda21_v0_3_arms_are_the_v0_2_arms_with_exactly_two_names_replaced():
    assert {n: e[1:] for n, e in v03_arms.ARMS.items()} == {n: e[1:] for n, e in v02_arms.ARMS.items()}
    assert v02_arms._fit is not v03_arms._fit and v02_arms._fit.__module__ == v02_arms.__name__
    differ = sorted(k for k, v in v03_arms._NAMESPACE.items() if callable(v) and getattr(v02_arms, k, None) is not v
                    and not (hasattr(v, "__code__") and v.__code__ is getattr(getattr(v02_arms, k, None), "__code__", 0)))
    assert differ == sorted(v03_arms.REPLACED)
    for name, (fn, *_rest) in v03_arms.ARMS.items():
        original = v02_arms.ARMS[name][0]
        assert fn.__code__ is original.__code__
        if fn is not original:
            assert fn.__globals__["_fit"] is v03_arms._fit


# ---- FDA-22: the kind-conditional form prior is declared and measured ------------------------------------------------
def _forms(kind, n=120):
    from engcore.blindfold.universe import generate_universe

    out = set()
    for i in range(n):
        w = generate_universe(f"fda22-test-{kind}-{i}", kind)
        out.add(harness.law_form({"kind": kind, "law": w.law, "alternative_law": w.alternative_law}))
    return out


def test_fda22_the_generator_tell_exists_and_v0_3_declares_it():
    assert _forms("indistinguishable") <= {"power", "exp"}
    assert {"two_term", "regime"} <= _forms("discoverable")
    doc = json.loads(v03p.PREREG_PATH.read_bytes())
    assert any(t.startswith("FDA-22") for t in doc["known_structural_tells"])
    assert not any("FDA-22" in t for t in json.loads(v02_prereg.PREREG_PATH.read_bytes())["known_structural_tells"])


def test_fda22_law_form_classifies_every_generator_form():
    from benchmarks.genesis_lite.evaluator.expr import value  # noqa: F401 - grammar reference

    pw = {"pow": [{"var": "x"}, {"const": 2.0}]}
    assert harness.law_form({"kind": "discoverable", "law": {"mul": [{"const": 2.0}, pw]}}) == "power"
    assert harness.law_form({"kind": "discoverable", "law": {"mul": [pw, {"exp": {"var": "x"}}]}}) == "exp"
    assert harness.law_form({"kind": "discoverable", "law": {"add": [pw, pw]}}) == "two_term"
    assert harness.law_form({"kind": "discoverable", "law": {"piecewise": {"if_below": [{"var": "x"}, {"const": 1.0}],
                                                                         "then": pw, "else": pw}}}) == "regime"
    rival = {"mul": [pw, {"add": [{"const": 1.0}, {"var": "x"}]}]}
    assert harness.law_form({"kind": "indistinguishable", "law": rival, "alternative_law": pw}) == "power"
    assert harness.law_form({"kind": "no_solution", "law": None}) is None


# ---- pilot P-1 / P-2 / P-3 (docs/discovery/GENESIS_LITE_V0.md) -------------------------------------------------------
def _field(**override):
    return lr.field(careful=lr.records("careful", lr.CAREFUL), **override)


def test_pilot_p1_a_floor_arm_that_always_proposes_gains_nothing_under_the_joint_endpoint():
    """P-1 (v0): always_law won the discoverable cell 0.70 vs 0.27 while failing every control. The v0.1 joint endpoint
    and the comparison over every non-adversarial arm already make that a loss; v0.3 keeps it."""
    always = lr.records("mind", dict({k: 0.0 for k in lr.KINDS}, discoverable=0.7))
    out = v03a.lift_decision(_field() + always, "mind", grid=lr.GRID)
    assert out["primary"]["pooled"]["mean_difference"] < 0
    assert not any(out["kind_noninferiority"][k]["ok"] for k in v03a.CONTROL_KINDS)
    assert out["lift_claimed"] is False


def _control_only_gain(p, c, s, k):
    return 1.0 if k == "confounded" else lr.credit(lr.CAREFUL[k], int(c[1:]), s, k)


def test_pilot_p2_v0_2_credits_a_control_cell_that_a_non_discoverer_already_solves():
    """Pinned (v0.2 is frozen): single_setting solves confounded; a candidate gaining only there still shows a gain."""
    rows = _field(single_setting=lr.records("single_setting", dict(lr.WEAK, confounded=1.0)))
    rows += lr.records("mind", None, credit_fn=_control_only_gain)
    out = v02_analysis.lift_decision(rows, "mind", grid=lr.GRID)
    assert out["primary"]["pooled"]["mean_difference"] > 0


def test_pilot_p2_v0_3_caps_control_cells_that_a_registered_arm_solves():
    rows = _field(single_setting=lr.records("single_setting", dict(lr.WEAK, confounded=1.0)))
    rows += lr.records("mind", None, credit_fn=_control_only_gain)
    out = v03a.lift_decision(rows, "mind", grid=lr.GRID)
    assert {("confounded", p) for p in lr.PRESENTATIONS} <= set(out["control_solved_cells"])
    assert out["primary"]["pooled"]["mean_difference"] == 0.0
    assert out["claim_scope"].startswith("JOINT_BENCHMARK_LIFT")


def test_pilot_p2_the_binary_lower_bound_is_the_exact_bootstrap_quantile():
    assert v03a.binary_lower_bound([1.0] * 60) == 1.0 and v03a.binary_lower_bound([0.0] * 60) == 0.0
    hits = [1.0] * 36 + [0.0] * 24                               # p_hat = 0.6, n = 60: Binomial 2.5% quantile is 28
    assert v03a.binary_lower_bound(hits) == 28 / 60


def test_pilot_p3_a_gain_only_in_out_of_family_worlds_is_capped():
    """P-3: 30-60 % of law-bearing worlds lie outside the searched family. v0.2 capped discoverable; v0.3 caps every
    law-credit kind (FDA-06)."""
    everywhere = lambda ws: True  # noqa: E731
    rows = []
    for name in lr.BASELINES:
        rows += lr.records(name, lr.CAREFUL if name == "careful" else lr.WEAK, out_of_family=everywhere)
    rows += lr.records("mind", dict(lr.CAREFUL, discoverable=1.0), out_of_family=everywhere)
    out = v03a.lift_decision(rows, "mind", grid=lr.GRID)
    assert out["primary"]["pooled"]["mean_difference"] == 0.0


# ---- readiness P-3: the deployment attack suite ----------------------------------------------------------------------
CARD = {"universe_id": "bf-attack"}


def _verdict(proposal):
    channel, verdict, _ = proposal["rationale"].split(":", 2)
    return channel, verdict


def test_readiness_p3_network_attack_reaches_a_listener_and_reports_refused_without_a_target(monkeypatch):
    monkeypatch.delenv("FORGE_ATTACK_NETWORK_TARGET", raising=False)
    assert _verdict(attacks.network(CARD, None)) == ("network", attacks.REFUSED)
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        monkeypatch.setenv("FORGE_ATTACK_NETWORK_TARGET", f"127.0.0.1:{srv.getsockname()[1]}")
        assert _verdict(attacks.network(CARD, None)) == ("network", attacks.REACHED)


def test_readiness_p3_root_file_and_run_log_attacks_read_what_the_command_line_names(monkeypatch, tmp_path):
    secret = tmp_path / "root.hex"
    secret.write_bytes(b"00" * 32)
    monkeypatch.setattr(attacks, "_parent_cmdline", lambda: f"python -m driver --root-file {secret}")
    assert _verdict(attacks.root_file(CARD, None)) == ("root_file", attacks.REACHED)
    assert _verdict(attacks.cmdline(CARD, None)) == ("cmdline", attacks.REACHED)
    monkeypatch.setattr(attacks, "_parent_cmdline", lambda: None)
    assert _verdict(attacks.root_file(CARD, None)) == ("root_file", attacks.REFUSED)
    monkeypatch.setenv("FORGE_ATTACK_RUN_LOGS", str(secret))
    assert _verdict(attacks.run_log(CARD, None)) == ("run_log", attacks.REACHED)
    monkeypatch.setenv("FORGE_ATTACK_RUN_LOGS", str(tmp_path / "absent.jsonl"))
    assert _verdict(attacks.run_log(CARD, None)) == ("run_log", attacks.REFUSED)


def test_readiness_p3_package_write_probe_writes_nothing():
    target = v03p.HERE.parent / "__init__.py"
    before = target.read_bytes()
    assert _verdict(attacks.package_write(CARD, None))[0] == "package_write"
    assert target.read_bytes() == before


def test_readiness_p3_the_deployment_is_verified_only_if_every_channel_is_refused():
    refused = lambda spec: [f"{spec.rsplit(':', 1)[1]}:{attacks.REFUSED}:x"]  # noqa: E731
    assert attacks.verify_deployment(refused)["verified"] is True
    leaky = lambda spec: [f"{spec.rsplit(':', 1)[1]}:{attacks.REACHED if 'network' in spec else attacks.REFUSED}:x"]  # noqa: E731
    out = attacks.verify_deployment(leaky)
    assert out["verified"] is False and out["verdicts"]["network"] == attacks.REACHED
    assert attacks.verify_deployment(lambda spec: [])["missing"] == sorted(attacks.CHANNELS)


# ---- the v0.3 harness binding ----------------------------------------------------------------------------------------
def _frozen_bytes(**changes):
    doc = json.loads(v03p.PREREG_PATH.read_bytes())
    doc["status"] = "FROZEN"
    doc["evaluator"]["pair_bound"] = TEST_BOUND.to_dict()
    doc["formal"]["environment_manifest_sha256"] = environment.manifest_digest(MANIFEST)
    for path, value in changes.items():
        node = doc
        *head, last = path.split(".")
        for key in head:
            node = node[key]
        node[last] = value
    return v03p.canonical(doc)


@pytest.fixture
def frozen_stand_in(monkeypatch):
    """A FROZEN stand-in with w and the manifest set; its committed-bytes check is bypassed for these tests only."""
    monkeypatch.setattr(v03p, "committed_doc_problems", lambda doc_bytes: [])
    return _frozen_bytes()


def test_harness_refuses_the_v0_2_preregistration():
    with pytest.raises(harness.HarnessRefused, match="not the committed"):
        harness.bind(v02_prereg.PREREG_PATH.read_bytes(), tier="development", development_bound=TEST_BOUND)


def test_harness_refuses_an_arbitrary_frozen_dict():
    with pytest.raises(harness.HarnessRefused, match="not the committed"):
        harness.bind(_frozen_bytes(), tier="formal", manifest=MANIFEST)


def test_harness_refuses_a_changed_w():
    with pytest.raises(harness.HarnessRefused, match="is not the bound one"):
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST,
                     development_bound=TEST_BOUND, pair_bound=v03e.PairBound("tol_multiple", 6.0))


def test_harness_refuses_a_changed_w_against_a_frozen_bound(frozen_stand_in):
    with pytest.raises(harness.HarnessRefused, match="is not the bound one"):
        harness.bind(frozen_stand_in, tier="formal", manifest=MANIFEST, pair_bound=v03e.PairBound("absolute", 1e31))
    with pytest.raises(harness.HarnessRefused, match="may not differ"):
        harness.bind(frozen_stand_in, tier="development", manifest=MANIFEST,
                     development_bound=v03e.PairBound("absolute", 1e31))


def test_harness_refuses_a_changed_credit_table(monkeypatch):
    changed = {k: dict(v) for k, v in v03e.CREDIT.items()}
    changed["indistinguishable"]["insufficient_evidence"] = 0.0
    monkeypatch.setattr(v03e, "CREDIT", changed)
    with pytest.raises(harness.HarnessRefused, match="credit table"):
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST, development_bound=TEST_BOUND)


def test_harness_refuses_a_changed_environment_manifest(frozen_stand_in):
    changed = {**MANIFEST, "distributions": {"numpy": "9.9.9"}}
    with pytest.raises(harness.HarnessRefused, match="environment manifest"):
        harness.bind(frozen_stand_in, tier="formal", manifest=changed)


def test_harness_refuses_a_modified_evaluator(monkeypatch):
    real = v03p._sha
    monkeypatch.setattr(v03p, "_sha", lambda path: "0" * 64 if path.name == "evaluator.py" else real(path))
    with pytest.raises(harness.HarnessRefused, match="does not rebuild"):
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST, development_bound=TEST_BOUND)


def test_harness_refuses_a_formal_run_of_a_draft_and_an_open_w_outside_development():
    committed = v03p.PREREG_PATH.read_bytes()
    with pytest.raises(harness.HarnessRefused, match="FROZEN"):
        harness.bind(committed, tier="formal", manifest=MANIFEST)
    with pytest.raises(harness.HarnessRefused, match="OWNER_DECISION_REQUIRED"):
        harness.bind(committed, tier="development", manifest=MANIFEST)


def test_harness_never_falls_back_without_the_escrow_half(frozen_stand_in, monkeypatch):
    monkeypatch.setattr(harness, "escrow_bound", None)
    with pytest.raises(harness.HarnessRefused, match="BLOCKED_BY_OD3"):
        harness.bind(frozen_stand_in, tier="formal", manifest=MANIFEST)


def test_harness_uses_only_v0_3_scoring():
    source = (v03p.HERE / "harness.py").read_text(encoding="utf-8")
    assert "_v02h.run_one" not in source and "independent.evaluate_campaign" not in source
    assert "independent=evaluator, CONFIG=binding.config" in source
    with pytest.raises(harness.HarnessRefused):
        harness.run_one("careful", binding=None, master_seed=MASTER, campaign_id="gl-x", presentation="anonymous")


# ---- one attempt per root --------------------------------------------------------------------------------------------
ROOT_C = H(b"root under test").hexdigest()
PREREG_A, PREREG_B, PLAN = H(b"identity A").hexdigest(), H(b"identity B").hexdigest(), H(b"plan").hexdigest()


def _admit(reg, tier="formal", prereg=PREREG_A, label="", root=ROOT_C):
    return reg.admit(root_commitment_sha256=root, prereg_sha256=prereg, campaign_set_sha256=PLAN, tier=tier,
                     attempt_label=label)


def test_attempt_first_formal_attempt_is_admitted_and_a_second_is_refused(tmp_path):
    reg = AttemptRegistry(tmp_path / "reg")
    entry = _admit(reg)
    assert entry["tier"] == "formal" and "root" not in json.dumps(entry).replace("root_commitment", "")
    with pytest.raises(AttemptRefused, match="one formal attempt per root"):
        _admit(reg)


def test_attempt_a_restart_still_refuses(tmp_path):
    _admit(AttemptRegistry(tmp_path / "reg"))
    with pytest.raises(AttemptRefused):
        _admit(AttemptRegistry(tmp_path / "reg"))


def test_attempt_a_copied_output_directory_or_new_label_or_identity_cannot_bypass(tmp_path):
    reg = AttemptRegistry(tmp_path / "reg")
    _admit(reg, label="run-1")
    for label, prereg in (("run-2-copied-out", PREREG_A), ("renamed", PREREG_B)):
        with pytest.raises(AttemptRefused):
            _admit(reg, label=label, prereg=prereg)


def test_attempt_development_roots_stay_apart_from_formal_roots(tmp_path):
    reg = AttemptRegistry(tmp_path / "reg")
    dev = H(b"development root").hexdigest()
    _admit(reg, tier="development", root=dev)
    _admit(reg, tier="development", root=dev)                   # development may repeat
    with pytest.raises(AttemptRefused):
        _admit(reg, tier="formal", root=dev)                    # never formal after development
    _admit(reg, tier="formal")
    with pytest.raises(AttemptRefused, match="never used for development"):
        _admit(reg, tier="development")


def test_attempt_a_crash_lock_and_a_tampered_registry_fail_closed(tmp_path):
    reg = AttemptRegistry(tmp_path / "reg")
    _admit(reg, tier="development", root=H(b"a").hexdigest())
    (tmp_path / "reg" / "attempts.lock").write_bytes(b"")
    with pytest.raises(AttemptRefused, match="locked"):
        _admit(reg)
    (tmp_path / "reg" / "attempts.lock").unlink()
    reg.path.write_bytes(reg.path.read_bytes().replace(b'"development"', b'"formal"'))
    with pytest.raises(AttemptRefused, match="broken"):
        _admit(reg)


def test_attempt_the_driver_consumes_the_root_before_any_world(monkeypatch, tmp_path):
    monkeypatch.setattr(formal, "committed_identity_problems", lambda doc: [])
    root = H(b"driver root").digest()
    doc = {"status": "FROZEN", "arms": {n: {} for n in v02_arms.ARMS},
           "formal": {"root_commitment_sha256": H(root).hexdigest(),
                      "environment_manifest_sha256": environment.manifest_digest(MANIFEST)}}

    def crash(*args, **kwargs):
        raise RuntimeError("crash in the first world")

    reg = AttemptRegistry(tmp_path / "reg")
    with pytest.raises(RuntimeError):
        formal.run_formal(root, doc, manifest=MANIFEST, registry=reg, sink=lambda r: None, runner=crash)
    with pytest.raises(formal.FormalRefused, match="one formal attempt per root"):
        formal.run_formal(root, doc, manifest=MANIFEST, registry=AttemptRegistry(tmp_path / "reg"),
                          sink=lambda r: None, runner=crash)


def test_attempt_a_revealed_pilot_root_is_refused_before_admission(tmp_path):
    revealed = bytes.fromhex(json.loads((v03p.HERE.parent / "pilot_results/v0_2-2026-10-14/summary.json")
                                        .read_bytes())["pilot_root_revealed_hex"])
    doc = {"status": "FROZEN", "arms": {n: {} for n in v02_arms.ARMS},
           "formal": {"root_commitment_sha256": H(revealed).hexdigest(),
                      "environment_manifest_sha256": environment.manifest_digest(MANIFEST)}}
    reg = AttemptRegistry(tmp_path / "reg")
    with pytest.raises(formal.FormalRefused, match="retired"):
        formal.run_formal(revealed, doc, manifest=MANIFEST, registry=reg, sink=lambda r: None)
    assert reg.entries() == []


# ---- the freeze-readiness gate ---------------------------------------------------------------------------------------
def test_readiness_is_never_pass_with_pending_owner_decisions(tmp_path):
    approvals = tmp_path / "approvals.json"
    approvals.write_bytes(json.dumps({d: {"status": "APPROVED", "choice": "x", "certified_head": readiness._head()}
                                      for d in readiness.REQUIRED_APPROVALS}).encode())
    out = readiness.check(approvals)
    assert out["status"] != readiness.PASS
    assert any("OWNER_DECISION_REQUIRED" in r for r in out["owner_and_certification"])   # w is still open
    assert any("DRAFT" in r for r in out["owner_and_certification"])


def test_readiness_lists_every_consolidated_decision_when_none_is_approved(tmp_path):
    out = readiness.check(tmp_path / "absent.json")
    for decision in readiness.REQUIRED_APPROVALS:
        assert any(f"owner decision {decision} " in r for r in out["owner_and_certification"])


def test_readiness_without_the_escrow_half_is_blocked_technically(monkeypatch):
    monkeypatch.setattr(readiness, "_escrow_half", lambda: None)
    out = readiness.check()
    assert out["status"] == readiness.BLOCKED
    assert any(r.startswith("FDA-05 escrow half: SPECIFIED_BLOCKED_BY_OD3") for r in out["technical_blockers"])


def test_readiness_pass_needs_everything(monkeypatch, tmp_path):
    """The PASS path exists: with every check satisfied (stubbed here) and every decision approved for this HEAD."""
    frozen = _frozen_bytes(**{"formal.root_commitment_sha256": "a" * 64})
    path = tmp_path / "genesis_lite_v0_3.json"
    path.write_bytes(frozen)
    monkeypatch.setattr(v03p, "PREREG_PATH", path)
    monkeypatch.setattr(v03p, "committed_doc_problems", lambda doc_bytes: [])
    monkeypatch.setattr(readiness, "blockers", lambda: {"x": (readiness.FIXED, "stub")})
    monkeypatch.setattr(readiness, "agreement_cases", lambda: [{"agree": True}])
    approvals = tmp_path / "approvals.json"
    approvals.write_bytes(json.dumps({d: {"status": "APPROVED", "choice": "x", "certified_head": readiness._head()}
                                      for d in readiness.REQUIRED_APPROVALS}).encode())
    assert readiness.check(approvals)["status"] == readiness.PASS
    approvals.write_bytes(json.dumps({d: {"status": "APPROVED", "choice": "x", "certified_head": "0" * 40}
                                      for d in readiness.REQUIRED_APPROVALS}).encode())
    assert readiness.check(approvals)["status"] == readiness.PENDING_OWNER        # OD-3 names another HEAD
