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
import shutil
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
from benchmarks.genesis_lite.v0_3 import formal, harness, readiness, secret_scan
from benchmarks.genesis_lite.v0_3 import preregistration as v03p
from benchmarks.genesis_lite.v0_3.registry import AttemptRefused, AttemptRegistry, EvaluatorInbox
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


def test_fda21_v0_3_keeps_every_v0_2_arm_and_adds_corrected_variants():
    """Arms may be added, never removed or weakened (review 2026-10-20 finding 7)."""
    for name, entry in v02_arms.ARMS.items():
        assert v03_arms.ARMS[name] == entry                          # the very same v0.2 callables
    added = sorted(set(v03_arms.ARMS) - set(v02_arms.ARMS))
    assert added == sorted(f"{n}_dof" for n in v03_arms.CORRECTED)
    for name in added:
        fn, original = v03_arms.ARMS[name][0], v02_arms.ARMS[name[:-4]][0]
        assert fn.__code__ is original.__code__ and fn.__globals__["_fit"] is v03_arms._fit
        assert v03_arms.ARMS[name][3] == v02_arms.ARMS[name[:-4]][3]
    differ = sorted(k for k, v in v03_arms._NAMESPACE.items() if callable(v) and getattr(v02_arms, k, None) is not v
                    and not (hasattr(v, "__code__") and v.__code__ is getattr(getattr(v02_arms, k, None), "__code__", 0)))
    assert differ == sorted(v03_arms.REPLACED)
    assert set(v03a.registered_roles()) == set(v03_arms.ARMS) == set(formal.registered_arms())


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


def test_readiness_p3_network_attack_reaches_a_listener_and_is_untestable_without_a_target(monkeypatch):
    monkeypatch.delenv("FORGE_ATTACK_NETWORK_TARGET", raising=False)
    assert _verdict(attacks.network(CARD, None)) == ("network", attacks.UNTESTABLE)       # never a vacuous REFUSED
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        monkeypatch.setenv("FORGE_ATTACK_NETWORK_TARGET", f"127.0.0.1:{srv.getsockname()[1]}")
        assert _verdict(attacks.network(CARD, None)) == ("network", attacks.REACHED)


def test_readiness_p3_root_file_and_run_log_attacks_read_what_the_command_line_names(monkeypatch, tmp_path):
    secret = tmp_path / "root.hex"
    secret.write_bytes(b"00" * 32)
    monkeypatch.setattr(attacks, "_proc_available", lambda: False)
    assert _verdict(attacks.cmdline(CARD, None)) == ("cmdline", attacks.UNTESTABLE)
    assert _verdict(attacks.root_file(CARD, None)) == ("root_file", attacks.UNTESTABLE)
    monkeypatch.setattr(attacks, "_proc_available", lambda: True)
    monkeypatch.delenv("FORGE_ATTACK_RUN_LOGS", raising=False)
    assert _verdict(attacks.run_log(CARD, None)) == ("run_log", attacks.UNTESTABLE)
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


def test_readiness_p3_the_deployment_is_verified_only_if_every_channel_is_refused_and_the_scan_is_clean():
    refused = lambda spec: [f"{spec.rsplit(':', 1)[1]}:{attacks.REFUSED}:x"]  # noqa: E731
    assert attacks.verify_deployment(refused, scan_findings=[])["verified"] is True
    assert attacks.verify_deployment(refused)["verified"] is False                        # the scan did not run
    assert attacks.verify_deployment(refused, scan_findings=[{"path": "x"}])["verified"] is False
    leaky = lambda spec: [f"{spec.rsplit(':', 1)[1]}:{attacks.REACHED if 'network' in spec else attacks.REFUSED}:x"]  # noqa: E731
    out = attacks.verify_deployment(leaky, scan_findings=[])
    assert out["verified"] is False and out["verdicts"]["network"] == attacks.REACHED
    assert attacks.verify_deployment(lambda spec: [], scan_findings=[])["missing"] == sorted(attacks.CHANNELS)
    untestable = lambda spec: [f"{spec.rsplit(':', 1)[1]}:{attacks.UNTESTABLE if 'cmdline' in spec else attacks.REFUSED}:x"]  # noqa: E731
    assert attacks.verify_deployment(untestable, scan_findings=[])["verified"] is False


def test_readiness_p3_the_suite_through_per_card_processes_is_not_verified_on_a_same_account_host():
    """Review 2026-10-20 (round 2) defect A: run through the harness's own per-card processes, with the operator's
    targets passed as FORGE_ATTACK_* variables, the suite reports what it reaches; on this host it is not verified."""
    shared = __import__("pathlib").Path(__import__("tempfile").gettempdir()).resolve() / "gl-cross-card-state"
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(8)
        env = {"FORGE_ATTACK_NETWORK_TARGET": f"127.0.0.1:{srv.getsockname()[1]}"}
        try:
            out = attacks.verify_deployment(attacks.deployment_runner(env), scan_findings=[])
        finally:
            shutil.rmtree(shared, ignore_errors=True)
    assert out["verified"] is False and out["missing"] == []
    assert out["verdicts"]["network"] == attacks.REACHED
    assert out["verdicts"]["cmdline"] in (attacks.REACHED, attacks.UNTESTABLE)
    with pytest.raises(ValueError):
        harness.CardProposerHost(attack_env={"PATH": "x"})


def test_readiness_p3_per_card_temp_dirs_hold_nothing_but_same_account_files_elsewhere_do():
    """FDA-18 residual, measured: each card's temp directory is new (temp_carry finds nothing), but a directory beside
    it survives (cross_card_state reaches the earlier card's marker). The residual is D5 / OD-20."""
    shared = __import__("pathlib").Path(__import__("tempfile").gettempdir()).resolve() / "gl-cross-card-state"
    shutil.rmtree(shared, ignore_errors=True)
    try:
        verdicts = []
        for spec in ("tests.genesis_lite.stateful_arms:temp_carry", "tests.genesis_lite.stateful_arms:temp_carry",
                     "benchmarks.genesis_lite.v0_3.deployment_attacks:cross_card_state",
                     "benchmarks.genesis_lite.v0_3.deployment_attacks:cross_card_state"):
            host = harness.CardProposerHost()
            try:
                verdicts.append(host.propose(spec, {"universe_id": "bf-x"}, 0, None)["rationale"])
            finally:
                host.close()
        assert verdicts[0].startswith("temp_carry:REFUSED") and verdicts[1].startswith("temp_carry:REFUSED")
        assert verdicts[2].startswith("cross_card_state:REFUSED") and verdicts[3].startswith("cross_card_state:REACHED")
    finally:
        shutil.rmtree(shared, ignore_errors=True)


def test_fda19_the_secret_scan_finds_every_inventory_item_and_nothing_in_clean_files(tmp_path):
    root, master = H(b"scan root").digest(), H(b"scan master").digest()
    digests = secret_scan.digests_for([root, master])
    (tmp_path / "root.hex").write_bytes(root.hex().encode())
    (tmp_path / "root.bin").write_bytes(root)
    (tmp_path / "note.txt").write_bytes(b"master=" + master.hex().upper().encode())
    reg = AttemptRegistry(tmp_path / "registry")
    _admit(reg)
    log = formal.SealedLog(tmp_path / "runs.jsonl")
    log({"arm": "a"})
    log.close()
    (tmp_path / "clean.txt").write_bytes(b"nothing here " + H(b"unrelated").hexdigest().encode())
    found = {(pathlib_name(f["path"]), f["found"]) for f in secret_scan.scan([tmp_path], digests)}
    assert {("root.hex", "hex secret"), ("root.bin", "raw secret"), ("note.txt", "hex secret"),
            ("attempts.jsonl", "attempt registry"), ("runs.jsonl", "run log")} <= found
    assert not any(name == "clean.txt" for name, _ in found)


def test_fda19_the_scan_finds_wrapped_utf16_and_streamed_secrets(tmp_path, monkeypatch):
    secret = H(b"wrapped").digest()
    digests = secret_scan.digests_for([secret])
    text = secret.hex()
    (tmp_path / "wrapped.txt").write_bytes((text[:30] + "\n  " + text[30:]).encode())
    (tmp_path / "utf16.txt").write_bytes(text.encode("utf-16-le"))
    monkeypatch.setattr(secret_scan, "CHUNK", 1024)
    (tmp_path / "big.log").write_bytes(b"x" * 5000 + text.encode() + b"y" * 5000)
    found = {pathlib_name(f["path"]) for f in secret_scan.scan([tmp_path], digests)}
    assert found == {"wrapped.txt", "utf16.txt", "big.log"}


def test_fda19_the_scan_does_not_flag_the_benchmark_sources():
    assert secret_scan.scan([v03p.HERE, v03p.HERE.parent / "evaluator"], secret_scan.digests_for([MASTER])) == []


def pathlib_name(path):
    import pathlib  # noqa: PLC0415

    return pathlib.Path(path).name


# ---- the v0.3 harness binding ----------------------------------------------------------------------------------------
def _frozen_bytes(**changes):
    doc = json.loads(v03p.PREREG_PATH.read_bytes())
    doc["status"] = "FROZEN"
    doc["evaluator"]["pair_bound"] = TEST_BOUND.to_dict()
    doc["formal"]["environment_manifest_sha256"] = environment.manifest_digest(MANIFEST)
    doc["formal"]["candidate"] = formal.NO_CANDIDATE
    for path, value in changes.items():
        node = doc
        *head, last = path.split(".")
        for key in head:
            node = node[key]
        node[last] = value
    return v03p.canonical(doc)


@pytest.fixture
def frozen_stand_in(monkeypatch):
    """A FROZEN stand-in with w and the manifest set; its committed-bytes check is bypassed for these tests only, and
    the measured environment is the test manifest."""
    monkeypatch.setattr(v03p, "committed_doc_problems", lambda doc_bytes: [])
    monkeypatch.setattr(environment, "build_manifest", lambda *a, **k: dict(MANIFEST))
    return _frozen_bytes()


def test_harness_refuses_the_v0_2_preregistration():
    with pytest.raises(harness.HarnessRefused, match="not the committed"):
        harness.bind(v02_prereg.PREREG_PATH.read_bytes(), tier="development", development_bound=TEST_BOUND)


def test_harness_refuses_an_arbitrary_frozen_dict():
    with pytest.raises(harness.HarnessRefused, match="not the committed"):
        harness.bind(_frozen_bytes(), tier="formal")


def test_harness_a_formal_binding_never_takes_a_callers_manifest(frozen_stand_in):
    with pytest.raises(harness.HarnessRefused, match="measures its environment itself"):
        harness.bind(frozen_stand_in, tier="formal", manifest=MANIFEST)


def test_harness_refuses_a_changed_w():
    with pytest.raises(harness.HarnessRefused, match="is not the bound one"):
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST,
                     development_bound=TEST_BOUND, pair_bound=v03e.PairBound("tol_multiple", 6.0))


def test_harness_refuses_a_changed_w_against_a_frozen_bound(frozen_stand_in):
    with pytest.raises(harness.HarnessRefused, match="is not the bound one"):
        harness.bind(frozen_stand_in, tier="formal", pair_bound=v03e.PairBound("absolute", 1e31))
    with pytest.raises(harness.HarnessRefused, match="may not differ"):
        harness.bind(frozen_stand_in, tier="development", manifest=MANIFEST,
                     development_bound=v03e.PairBound("absolute", 1e31))


def test_harness_refuses_a_changed_credit_table(monkeypatch):
    changed = {k: dict(v) for k, v in v03e.CREDIT.items()}
    changed["indistinguishable"]["insufficient_evidence"] = 0.0
    monkeypatch.setattr(v03e, "CREDIT", changed)
    with pytest.raises(harness.HarnessRefused, match="credit table"):
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST, development_bound=TEST_BOUND)


def test_harness_refuses_a_changed_environment_manifest(frozen_stand_in, monkeypatch):
    monkeypatch.setattr(environment, "build_manifest",
                        lambda *a, **k: {**MANIFEST, "distributions": {"numpy": "9.9.9"}})
    with pytest.raises(harness.HarnessRefused, match="environment manifest"):
        harness.bind(frozen_stand_in, tier="formal")


def test_harness_refuses_a_modified_evaluator(monkeypatch):
    real = v03p._sha
    monkeypatch.setattr(v03p, "_sha", lambda path: "0" * 64 if path.name == "evaluator.py" else real(path))
    with pytest.raises(harness.HarnessRefused, match="does not rebuild"):
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST, development_bound=TEST_BOUND)


def test_harness_refuses_a_formal_run_of_a_draft_and_an_open_w_outside_development():
    committed = v03p.PREREG_PATH.read_bytes()
    with pytest.raises(harness.HarnessRefused, match="FROZEN"):
        harness.bind(committed, tier="formal")
    with pytest.raises(harness.HarnessRefused, match="OWNER_DECISION_REQUIRED"):
        harness.bind(committed, tier="development", manifest=MANIFEST)


def test_harness_never_falls_back_without_the_escrow_half(frozen_stand_in, monkeypatch):
    monkeypatch.setattr(harness, "escrow_bound", None)
    with pytest.raises(harness.HarnessRefused, match="BLOCKED_BY_OD3"):
        harness.bind(frozen_stand_in, tier="formal")


def _formal_binding(candidate=None):
    return harness.Binding("a" * 64, "FROZEN", "formal", TEST_BOUND, None, "", "", TEST_BOUND.to_dict(), candidate)


@pytest.mark.parametrize("extra", [{"card_hook": lambda card: card}, {"extra_paths": ("x",)},
                                   {"arm_spec": "tests.genesis_lite.vacuous_arm:vacuous_pair"},
                                   {"isolation": "in_process"}])
def test_harness_a_formal_run_takes_no_hook_path_spec_or_in_process_arm(extra):
    """Review 2026-10-20 finding 2: no weakened baseline can be recorded under a registered name."""
    with pytest.raises(harness.HarnessRefused):
        harness.run_one("careful", binding=_formal_binding(), master_seed=MASTER, campaign_id="gl-x",
                        presentation="anonymous", **extra)


def test_harness_a_formal_run_refuses_an_arm_that_is_neither_registered_nor_the_candidate():
    with pytest.raises(harness.HarnessRefused, match="neither a registered"):
        harness.run_one("mind", binding=_formal_binding(), master_seed=MASTER, campaign_id="gl-x",
                        presentation="anonymous")


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
    doc = {"status": "FROZEN", "arms": {n: {} for n in formal.registered_arms()},
           "formal": {"root_commitment_sha256": H(root).hexdigest(), "candidate": formal.NO_CANDIDATE,
                      "environment_manifest_sha256": environment.manifest_digest(MANIFEST)}}

    def crash(*args, **kwargs):
        raise RuntimeError("crash in the first world")

    reg, published = AttemptRegistry(tmp_path / "reg"), []
    with pytest.raises(RuntimeError):
        formal.run_formal(root, doc, manifest=MANIFEST, registry=reg, sink=lambda r: None, runner=crash,
                          publish=published.append)
    assert len(published) == 1                                       # published before the first world
    with pytest.raises(formal.FormalRefused, match="one formal attempt per root"):
        formal.run_formal(root, doc, manifest=MANIFEST, registry=AttemptRegistry(tmp_path / "reg"),
                          sink=lambda r: None, runner=crash, publish=published.append)
    assert len(published) == 1


def test_attempt_a_revealed_pilot_root_is_refused_before_admission(tmp_path):
    revealed = bytes.fromhex(json.loads((v03p.HERE.parent / "pilot_results/v0_2-2026-10-14/summary.json")
                                        .read_bytes())["pilot_root_revealed_hex"])
    doc = {"status": "FROZEN", "arms": {n: {} for n in formal.registered_arms()},
           "formal": {"root_commitment_sha256": H(revealed).hexdigest(), "candidate": formal.NO_CANDIDATE,
                      "environment_manifest_sha256": environment.manifest_digest(MANIFEST)}}
    reg = AttemptRegistry(tmp_path / "reg")
    with pytest.raises(formal.FormalRefused, match="retired"):
        formal.run_formal(revealed, doc, manifest=MANIFEST, registry=reg, sink=lambda r: None, publish=print)
    assert reg.entries() == []


def test_attempt_a_fresh_registry_cannot_reproduce_an_attempt_or_its_worlds(tmp_path):
    """Review 2026-10-20 finding 3: every admission carries a nonce, and the masters mix it in."""
    a, b = _admit(AttemptRegistry(tmp_path / "one")), _admit(AttemptRegistry(tmp_path / "two"))
    assert a["nonce"] != b["nonce"] and a["attempt_sha256"] != b["attempt_sha256"] and a["admitted_at"]
    root = H(b"a root").digest()
    assert formal.master_for(root, PREREG_A, a["nonce"], "anonymous", "gl-formal-0", 0) != \
        formal.master_for(root, PREREG_A, b["nonce"], "anonymous", "gl-formal-0", 0)


def _stand_in(root, candidate):
    return {"status": "FROZEN", "arms": {n: {} for n in formal.registered_arms()},
            "formal": {"root_commitment_sha256": H(root).hexdigest(), "candidate": candidate,
                       "environment_manifest_sha256": environment.manifest_digest(MANIFEST)}}


def test_p4_candidate_runs_inside_the_attempt_world_set_major(monkeypatch, tmp_path):
    """Review 2026-10-20 finding 1 (BLOCKER): the identity names the candidate and the driver runs it beside every arm."""
    monkeypatch.setattr(formal, "committed_identity_problems", lambda doc: [])
    module = "tests/genesis_lite/stateful_arms.py"
    cand = {"name": "mind", "spec": "tests.genesis_lite.stateful_arms:remembers",
            "code_sha256": {module: H((v03p.v02.ROOT / module).read_bytes()).hexdigest()}}
    root, seen = H(b"candidate root").digest(), []

    def runner(arm, *, master_seed, campaign_id, presentation, seed):
        seen.append((arm, (presentation, campaign_id, seed)))
        return {"arm": arm, "status": "VALID", "prereg_sha256": formal.identity(_stand_in(root, cand)),
                "presentation": presentation, "campaign_id": campaign_id, "seed": seed, "universes": []}

    formal.run_formal(root, _stand_in(root, cand), manifest=MANIFEST, registry=AttemptRegistry(tmp_path / "r"),
                      sink=lambda r: None, runner=runner, publish=lambda e: None)
    per_ws = {}
    for arm, ws in seen:
        per_ws.setdefault(ws, []).append(arm)
    assert all(sorted(arms) == sorted(formal.registered_arms() + ["mind"]) for arms in per_ws.values())
    assert len(per_ws) == 2400


def test_p4_candidate_code_and_name_are_pinned():
    module = "tests/genesis_lite/stateful_arms.py"
    wrong = {"name": "mind", "spec": "tests.genesis_lite.stateful_arms:remembers", "code_sha256": {module: "0" * 64}}
    root = H(b"r").digest()
    assert any("not the preregistered code" in p for p in formal.preflight(_stand_in(root, wrong), root, MANIFEST))
    taken = dict(wrong, name="careful")
    assert any("registered arm's name" in p for p in formal.preflight(_stand_in(root, taken), root, MANIFEST))
    assert any("candidate" in p for p in formal.preflight(_stand_in(root, "OWNER_DECISION_REQUIRED"), root, MANIFEST))


def test_attempt_the_evaluator_recomputes_keys_and_shown_cards_after_the_reveal(tmp_path):
    """Review rounds 1-2: the evaluator accepts only the FIRST admission of a root, re-derives every answer key, and
    re-derives the cards each arm was shown, so a record carrying another arm's label does not verify."""
    root, prereg = H(b"verify root").digest(), H(b"prereg").hexdigest()
    reg, inbox = AttemptRegistry(tmp_path / "reg"), EvaluatorInbox(tmp_path / "inbox.jsonl")
    admission = reg.admit(root_commitment_sha256=H(root).hexdigest(), prereg_sha256=prereg, campaign_set_sha256=PLAN,
                          tier="formal")
    inbox.receive(admission)
    master = formal.master_for(root, prereg, admission["nonce"], "renamed", "gl-formal-3", 1)
    rec = v02_harness.run_one("always_refuse", v02_arms.ARMS["always_refuse"][0], master_seed=master,
                              campaign_id="gl-formal-3", presentation="renamed", seed=1).to_dict()
    rec["attempt_sha256"] = admission["attempt_sha256"]
    verify = lambda recs, **kw: formal.verify_attempt(recs, kw.get("root", root), kw.get("adm", admission),  # noqa: E731
                                                      inbox=inbox, prereg_sha256=kw.get("prereg", prereg))
    assert verify([rec]) == []
    assert any("cards this arm was shown" in p for p in verify([dict(rec, arm="careful")]))        # swapped label
    assert any("not from the published attempt" in p for p in verify([dict(rec, attempt_sha256="d" * 64)]))
    assert verify([rec], root=H(b"another root").digest())
    assert verify([rec], prereg=H(b"other identity").hexdigest())
    assert any("malformed" in p for p in verify([{"attempt_sha256": admission["attempt_sha256"], "status": "VALID"}]))
    assert any("invalid run" in p for p in verify([dict(rec, status="INVALID_BENCHMARK")]))
    second = AttemptRegistry(tmp_path / "fresh-registry").admit(
        root_commitment_sha256=H(root).hexdigest(), prereg_sha256=prereg, campaign_set_sha256=PLAN, tier="formal")
    with pytest.raises(AttemptRefused, match="already received"):
        inbox.receive(second)                                       # a fresh operator registry does not help
    assert any("not the first" in p for p in verify([rec], adm=second))
    with pytest.raises(AttemptRefused, match="well-formed"):
        inbox.receive(dict(admission, tier="development"))


def test_p4_candidate_spec_module_and_its_imports_must_be_pinned():
    """Review round 2 defect B: the spec's own module and every first-party file it imports are pinned."""
    stateful = "tests/genesis_lite/stateful_arms.py"
    ok = {"name": "mind", "spec": "tests.genesis_lite.stateful_arms:remembers",
          "code_sha256": {stateful: H((v03p.v02.ROOT / stateful).read_bytes()).hexdigest()}}
    assert formal.candidate_code_problems(ok) == []
    readme = {"name": "mind", "spec": "tests.genesis_lite.stateful_arms:remembers",
              "code_sha256": {"README.md": H((v03p.v02.ROOT / "README.md").read_bytes()).hexdigest()}}
    assert any("is not one of its pinned files" in p for p in formal.candidate_code_problems(readme))
    analysis_tests = "tests/genesis_lite/test_genesis_lite_analysis.py"
    transitive = {"name": "mind", "spec": "tests.genesis_lite.test_genesis_lite_analysis:test_x",
                  "code_sha256": {analysis_tests: H((v03p.v02.ROOT / analysis_tests).read_bytes()).hexdigest()}}
    assert any("lift_records.py, which is not pinned" in p for p in formal.candidate_code_problems(transitive))


def test_p4_representation_cap_covers_both_enumeration_arms():
    """Review round 2 defect F."""
    rows = _field() + lr.records("monomial_enumeration_dof", dict(lr.WEAK, no_solution=1.0))
    rows += lr.records("mind", lr.BETTER)
    out = v03a.lift_decision(rows, "mind", grid=lr.GRID)
    assert {("no_solution", p) for p in lr.PRESENTATIONS} <= set(out["representation_limited_cells"])


def test_p4_the_identity_lists_a_fixed_retired_set():
    """Review round 2 defect G: committing a later preregistration must not change what v0.3 rebuilds to."""
    listed = json.loads(v03p.PREREG_PATH.read_bytes())["formal"]["retired_root_commitments"]
    pilots = {json.loads(path.read_bytes())["pilot_root_commitment_sha256"]
              for path in (v02_prereg.V0_PREREG_PATH, v02_prereg.V0_1_PREREG_PATH, v02_prereg.PREREG_PATH)}
    assert set(listed) == pilots and "glob" not in (v03p.HERE / "preregistration.py").read_text(encoding="utf-8")


# ---- the freeze-readiness gate ---------------------------------------------------------------------------------------
def _all_pass_evidence():
    required = {name for _s, names, _n in readiness.blockers().values() for name in names}
    return {"head": readiness._head(), "clean": True, "tests": {name: "passed" for name in required}}


def test_readiness_a_claimed_row_without_passing_tests_is_technical():
    evidence = _all_pass_evidence()
    evidence["tests"] = {k: v for k, v in evidence["tests"].items() if not k.startswith("test_fda21_")}
    out = readiness.check(evidence=evidence)
    assert any(r.startswith("FDA-21: claimed") for r in out["technical_blockers"])
    failing = _all_pass_evidence()
    failing["tests"][readiness.REQUIRED_TESTS["FDA-06"][0] + "[case1]"] = "failed"          # one parametrization
    assert any(r.startswith("FDA-06: claimed") for r in readiness.check(evidence=failing)["technical_blockers"])
    prefix_only = _all_pass_evidence()
    prefix_only["tests"] = {k: v for k, v in prefix_only["tests"].items() if k not in readiness.REQUIRED_TESTS["FDA-19"
                            " (Genesis-lite secret inventory)"]}
    prefix_only["tests"]["test_fda19_trivially_true"] = "passed"                              # a prefix proves nothing
    assert any(r.startswith("FDA-19") for r in readiness.check(evidence=prefix_only)["technical_blockers"])
    assert any("no test evidence" in r for r in readiness.check()["technical_blockers"])
    stale = dict(_all_pass_evidence(), head="0" * 40)
    assert any("not from a clean tree" in r for r in readiness.check(evidence=stale)["technical_blockers"])


def test_readiness_is_never_pass_with_pending_owner_decisions(tmp_path):
    approvals = tmp_path / "approvals.json"
    approvals.write_bytes(json.dumps({d: {"status": "APPROVED", "choice": "x", "certified_head": readiness._head()}
                                      for d in readiness.REQUIRED_APPROVALS}).encode())
    out = readiness.check(approvals, evidence=_all_pass_evidence())
    assert out["status"] != readiness.PASS
    assert any("OWNER_DECISION_REQUIRED" in r for r in out["owner_and_certification"])   # w is still open
    assert any("DRAFT" in r for r in out["owner_and_certification"])


def test_readiness_lists_every_consolidated_decision_when_none_is_approved(tmp_path):
    out = readiness.check(tmp_path / "absent.json", evidence=_all_pass_evidence())
    for decision in readiness.REQUIRED_APPROVALS:
        assert any(f"owner decision {decision} " in r for r in out["owner_and_certification"])


def test_readiness_without_the_escrow_half_is_blocked_technically(monkeypatch):
    monkeypatch.setattr(readiness, "_escrow_half", lambda: None)
    out = readiness.check(evidence=_all_pass_evidence())
    assert out["status"] == readiness.BLOCKED
    assert any(r.startswith("FDA-05 escrow half: SPECIFIED_BLOCKED_BY_OD3") for r in out["technical_blockers"])


def test_readiness_pass_needs_everything(monkeypatch, tmp_path):
    """The PASS path exists: with every check satisfied (stubbed here) and every decision approved for this HEAD."""
    frozen = _frozen_bytes(**{"formal.root_commitment_sha256": "a" * 64})
    path = tmp_path / "genesis_lite_v0_3.json"
    path.write_bytes(frozen)
    monkeypatch.setattr(v03p, "PREREG_PATH", path)
    monkeypatch.setattr(v03p, "committed_doc_problems", lambda doc_bytes: [])
    monkeypatch.setattr(readiness, "blockers", lambda: {"x": (readiness.FIXED, ("test_x_1",), "stub")})
    monkeypatch.setattr(readiness, "agreement_cases", lambda: [{"agree": True}])
    monkeypatch.setattr(readiness, "_escrow_half", lambda: None)
    evidence = {"head": readiness._head(), "clean": True, "tests": {"test_x_1": "passed"}}
    sha = H(frozen).hexdigest()

    def approve(**over):
        rows = {d: {"status": "APPROVED", "choice": "x", "prereg_sha256": sha} for d in readiness.REQUIRED_APPROVALS}
        rows["D1-scoring"]["pair_bound"] = TEST_BOUND.to_dict()
        rows["OD-3"]["certified_head"] = readiness._head()
        for decision, fields in over.items():
            rows[decision.replace("_", "-")].update(fields)
        approvals = tmp_path / "approvals.json"
        approvals.write_bytes(json.dumps(rows).encode())
        return readiness.check(approvals, evidence=evidence)["status"]

    assert approve() == readiness.PASS
    assert approve(OD_3={"certified_head": "0" * 40}) == readiness.PENDING_OWNER          # another HEAD
    assert approve(D2_significance={"prereg_sha256": "0" * 64}) == readiness.PENDING_OWNER  # another identity
    assert approve(D1_scoring={"pair_bound": {"form": "absolute", "value": 9.0}}) == readiness.PENDING_OWNER
