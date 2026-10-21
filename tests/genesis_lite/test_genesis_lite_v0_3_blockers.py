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
    assert _verdict(attacks.root_file(CARD, None)) == ("root_file", attacks.UNTESTABLE)  # no operator file named
    monkeypatch.setattr(attacks, "_parent_cmdline", lambda: f"python -m driver --root-file {tmp_path / 'gone.hex'}")
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
    """D5-A1b: also only with N-1 container evidence that PASSED; cross_card_state is refused on that evidence only."""
    ok = {"status": "PASS", "reasons": []}
    no_marker = f"cross_card_state:{attacks.UNTESTABLE}:{attacks.CROSS_CARD_NO_MARKER}"   # what the probe really says

    def line(spec, verdict):
        channel = spec.rsplit(":", 1)[1]
        return no_marker if channel == "cross_card_state" and verdict == attacks.REFUSED else f"{channel}:{verdict}:x"

    refused = lambda spec: [line(spec, attacks.REFUSED)]  # noqa: E731
    assert attacks.verify_deployment(refused, scan_findings=[], container_validation=ok)["verified"] is True
    assert attacks.verify_deployment(refused, scan_findings=[])["verified"] is False      # no container evidence
    blocked = {"status": "BLOCKED", "reasons": ["DEVICE_NODE_WRITABLE_MOUNT"]}
    assert attacks.verify_deployment(refused, scan_findings=[], container_validation=blocked)["verified"] is False
    assert attacks.verify_deployment(refused, container_validation=ok)["verified"] is False   # the scan did not run
    assert attacks.verify_deployment(refused, scan_findings=[{"path": "x"}], container_validation=ok)["verified"] is False
    leaky = lambda spec: [line(spec, attacks.REACHED if 'network' in spec else attacks.REFUSED)]  # noqa: E731
    out = attacks.verify_deployment(leaky, scan_findings=[], container_validation=ok)
    assert out["verified"] is False and out["verdicts"]["network"] == attacks.REACHED
    assert attacks.verify_deployment(lambda spec: [], scan_findings=[])["missing"] == sorted(attacks.CHANNELS)
    untestable = lambda spec: [line(spec, attacks.UNTESTABLE if 'cmdline' in spec else attacks.REFUSED)]  # noqa: E731
    assert attacks.verify_deployment(untestable, scan_findings=[], container_validation=ok)["verified"] is False
    quiet = refused
    assert attacks.verify_deployment(quiet, scan_findings=[], container_validation=ok)["verdicts"]["cross_card_state"]         == attacks.REFUSED
    assert attacks.verify_deployment(quiet, scan_findings=[])["verdicts"]["cross_card_state"] == attacks.UNTESTABLE
    reached = lambda spec: [line(spec, attacks.REACHED if 'cross_card' in spec else attacks.REFUSED)]  # noqa: E731
    assert attacks.verify_deployment(reached, scan_findings=[], container_validation=ok)["verdicts"][
        "cross_card_state"] == attacks.REACHED                          # evidence never overrides a reached channel


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
    it survives (cross_card_state reaches the earlier card's marker). The residual is D5 / OD-20. The first card finds
    nothing, which is UNTESTABLE (N-1): one directory is no evidence about every writable mount."""
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
        assert verdicts[2].startswith("cross_card_state:UNTESTABLE") and verdicts[3].startswith("cross_card_state:REACHED")
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


def test_fda19_the_scan_does_not_flag_its_own_compiled_bytecode(tmp_path):
    """D5 verification (2026-10-20): inside the namespaces the proposer-side scan REACHED a 'secret' that was the
    scanner's own .pyc in the card's bytecode cache: CPython folds b'a' + b'b' into one constant, so the assembled
    markers appeared whole. Bytecode of every v0.3 module (in the per-card cache a proposer writes) holds no marker."""
    import pathlib
    import py_compile

    from benchmarks.genesis_lite.v0_3 import secret_scan

    here = pathlib.Path(secret_scan.__file__).resolve().parent
    for source in sorted(here.glob("*.py")):
        py_compile.compile(str(source), cfile=str(tmp_path / (source.stem + ".pyc")), doraise=True)
    assert secret_scan.scan([tmp_path], secret_scan.digests_for([b"\x01" * 32])) == []


def test_fda19_no_tracked_file_holds_an_inventory_marker():
    """D5 re-run (2026-10-20): the proposer-side scan of everything a card can see REACHED the committed preregistration,
    which recorded the registry schema under a key named 'schema' (the registry-line marker, in compact JSON). Every
    tracked text file of the kept tree is scanned here, so nothing public can pass for a run log or a registry."""
    import pathlib
    import subprocess

    from benchmarks.genesis_lite.v0_3 import secret_scan

    repo = pathlib.Path(secret_scan.__file__).resolve().parents[3]
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=True).stdout.split(b"\0")
    wanted = frozenset(secret_scan.digests_for([b"\x02" * 32]))
    hits = []
    for rel in tracked:
        path = repo / rel.decode()
        if rel and path.is_file() and path.stat().st_size < 50_000_000:
            hits += [(rel.decode(), what) for what in secret_scan._scan_file(path, wanted)]
    assert hits == []


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
    doc["formal"]["budget"]["candidate_hours"], doc["formal"]["budget"]["total_hours"] = 0.0, 72.0
    doc["formal"]["evaluator"]["name"] = "stand-in evaluator (tests only)"
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
                     pair_bound=v03e.PairBound("tol_multiple", 6.0))


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
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST)


def test_harness_refuses_a_changed_environment_manifest(frozen_stand_in, monkeypatch):
    monkeypatch.setattr(environment, "build_manifest",
                        lambda *a, **k: {**MANIFEST, "distributions": {"numpy": "9.9.9"}})
    with pytest.raises(harness.HarnessRefused, match="environment manifest"):
        harness.bind(frozen_stand_in, tier="formal")


def test_harness_refuses_a_modified_evaluator(monkeypatch):
    real = v03p._sha
    monkeypatch.setattr(v03p, "_sha", lambda path: "0" * 64 if path.name == "evaluator.py" else real(path))
    with pytest.raises(harness.HarnessRefused, match="does not rebuild"):
        harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", manifest=MANIFEST)


def test_harness_refuses_a_formal_run_of_a_draft_and_a_development_bound_other_than_the_decided_w():
    committed = v03p.PREREG_PATH.read_bytes()
    with pytest.raises(harness.HarnessRefused, match="FROZEN"):
        harness.bind(committed, tier="formal")
    with pytest.raises(harness.HarnessRefused, match="may not differ"):          # w is decided (D1): no other bound
        harness.bind(committed, tier="development", manifest=MANIFEST, development_bound=TEST_BOUND)


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
                      "environment_manifest_sha256": environment.manifest_digest(MANIFEST),
                      "budget": {"total_hours": 72.0}}}

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
                      "environment_manifest_sha256": environment.manifest_digest(MANIFEST),
                      "budget": {"total_hours": 72.0}}}
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
                       "environment_manifest_sha256": environment.manifest_digest(MANIFEST),
                      "budget": {"total_hours": 72.0}}}


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


def _attempt(tmp_path, tag, arms=("always_refuse",), presentation="renamed"):
    """One admitted, published attempt with real v0.2-harness records on one world set (synthetic root)."""
    root, prereg = H(b"verify root " + tag.encode()).digest(), H(b"prereg").hexdigest()
    reg, inbox = AttemptRegistry(tmp_path / tag / "reg"), EvaluatorInbox(tmp_path / tag / "inbox.jsonl")
    admission = reg.admit(root_commitment_sha256=H(root).hexdigest(), prereg_sha256=prereg, campaign_set_sha256=PLAN,
                          tier="formal")
    inbox.receive(admission)
    master = formal.master_for(root, prereg, admission["nonce"], presentation, "gl-formal-3", 1)
    from benchmarks.genesis_lite.answer_key import export_answer_key

    records = []
    for arm in arms:
        rec = v02_harness.run_one(arm, v02_arms.ARMS[arm][0], master_seed=master, campaign_id="gl-formal-3",
                                  presentation=presentation, seed=1).to_dict()
        key = export_answer_key(master, "gl-formal-3", v02_harness.MIX, [u["universe_id"] for u in rec["universes"]])
        entries = {e["universe_id"]: e for e in key["universes"]}
        for u in rec["universes"]:                       # what the v0.3 harness adds; v0.2 records have no proposals
            u["law_form"], u["proposal"] = harness.law_form(entries[u["universe_id"]]), None
        records.append({**rec, "attempt_sha256": admission["attempt_sha256"]})
    return {"root": root, "prereg": prereg, "reg": reg, "inbox": inbox, "admission": admission, "records": records,
            "runs": {(arm, (presentation, "gl-formal-3", 1)) for arm in arms}, "dir": tmp_path / tag}


def _publish_and_verify(ctx, records, *, extra_line=False, **kw):
    log = formal.SealedLog(ctx["dir"] / "runs.jsonl")
    for rec in records:
        log(rec)
    log.close()
    ctx["inbox"].receive_heads(ctx["admission"]["attempt_sha256"], run_log=log.head, registry=ctx["reg"].head())
    if extra_line:                                                   # appended after the head was published
        with open(ctx["dir"] / "runs.jsonl", "ab") as fh:
            fh.write(json.dumps({"prev_sha256": log.head, "record": records[0]}, sort_keys=True,
                                separators=(",", ":")).encode() + b"\n")
    return formal.verify_attempt(ctx["dir"] / "runs.jsonl", kw.get("root", ctx["root"]), kw.get("adm", ctx["admission"]),
                                 inbox=ctx["inbox"], prereg_sha256=kw.get("prereg", ctx["prereg"]),
                                 runs=kw.get("runs", ctx["runs"]), pair_bound=TEST_BOUND.to_dict(),
                                 replay_runner=kw.get("replay", _v02_runner))


def test_attempt_the_evaluator_verifies_the_whole_published_log_after_the_reveal(tmp_path):
    """Review rounds 1-3: only the FIRST admission of a root counts; the whole sealed log must be the published one and
    hold exactly the expected runs; every key and every card the arm was shown re-derive from the revealed root."""
    honest = _attempt(tmp_path, "honest")
    problems = _publish_and_verify(honest, honest["records"])
    assert problems and all("no sealed proposal" in p for p in problems)    # v0.2 records: only the proposals lack
    swapped = _attempt(tmp_path, "label")
    assert any("cards this arm was shown" in p for p in
               _publish_and_verify(swapped, [dict(swapped["records"][0], arm="careful")],
                                   runs={("careful", ("renamed", "gl-formal-3", 1))}))
    late = _attempt(tmp_path, "late")
    assert any("head is not the one published" in p for p in _publish_and_verify(late, late["records"], extra_line=True))
    partial = _attempt(tmp_path, "partial")
    assert any("expected runs" in p for p in _publish_and_verify(
        partial, partial["records"], runs=partial["runs"] | {("careful", ("renamed", "gl-formal-3", 1))}))
    other = _attempt(tmp_path, "other")
    assert _publish_and_verify(other, other["records"], prereg=H(b"other identity").hexdigest())
    bad = _attempt(tmp_path, "bad")
    assert any("malformed" in p for p in _publish_and_verify(
        bad, [{"attempt_sha256": bad["admission"]["attempt_sha256"], "status": "VALID", "arm": "always_refuse",
               "presentation": "renamed", "campaign_id": "gl-formal-3", "seed": 1, "universes": [1]}]))
    invalid = _attempt(tmp_path, "invalid")
    assert any("invalid run" in p for p in _publish_and_verify(invalid, [dict(invalid["records"][0],
                                                                                 status="INVALID_BENCHMARK")]))
    second = AttemptRegistry(tmp_path / "fresh-registry").admit(
        root_commitment_sha256=H(honest["root"]).hexdigest(), prereg_sha256=honest["prereg"], campaign_set_sha256=PLAN,
        tier="formal")
    with pytest.raises(AttemptRefused, match="already received"):
        honest["inbox"].receive(second)                              # a fresh operator registry does not help
    assert any("not the first" in p for p in formal.verify_attempt(
        honest["dir"] / "runs.jsonl", honest["root"], second, inbox=honest["inbox"], prereg_sha256=honest["prereg"],
        runs=honest["runs"], pair_bound=TEST_BOUND.to_dict(), replay_runner=_v02_runner))
    flagged = _attempt(tmp_path, "flag")
    forged = json.loads(json.dumps(flagged["records"][0]))
    forged["universes"][0]["truth_in_searched_family"] = not forged["universes"][0]["truth_in_searched_family"]
    assert any("searched-family flag does not re-derive" in p for p in _publish_and_verify(flagged, [forged]))
    unreplayed = _attempt(tmp_path, "unreplayed")
    assert any("not replayed" in p for p in _publish_and_verify(unreplayed, unreplayed["records"], replay=None))
    with pytest.raises(AttemptRefused, match="well-formed"):
        honest["inbox"].receive(dict(honest["admission"], tier="development"))
    with pytest.raises(AttemptRefused, match="already published"):
        honest["inbox"].receive_heads(honest["admission"]["attempt_sha256"], run_log="0" * 64, registry="0" * 64)


def test_attempt_a_screened_world_set_verifies_only_if_its_screen_rederives(tmp_path, monkeypatch):
    """Review round 5 (MAJOR): a preregistered screen (here a trap whose textbook law would pass) makes a world set
    INVALID for every arm; the evaluator re-derives the screen instead of rejecting or trusting the record."""
    monkeypatch.setattr(v02_harness, "_textbook_could_pass", lambda textbook, entry: True)
    screened = _attempt(tmp_path, "screened", presentation="trap")
    rec = screened["records"][0]
    assert rec["status"] == "INVALID_BENCHMARK" and all(r.startswith("trap ") for r in rec["reasons"])
    assert _publish_and_verify(screened, screened["records"]) == []
    dropped = _attempt(tmp_path, "dropped", presentation="trap")
    edited = dict(dropped["records"][0], reasons=dropped["records"][0]["reasons"] + ["leakage audit: [forged]"])
    assert any("do not re-derive exactly" in p for p in _publish_and_verify(dropped, [edited]))
    monkeypatch.setattr(v02_harness, "_textbook_could_pass", lambda textbook, entry: False)
    claimed = _attempt(tmp_path, "claimed", presentation="renamed")
    fake = dict(claimed["records"][0], status="INVALID_BENCHMARK", reasons=["trap bf-x (discoverable): claimed"])
    assert any("do not re-derive exactly" in p for p in _publish_and_verify(claimed, [fake]))
    other = _attempt(tmp_path, "other-reason")
    odd = dict(other["records"][0], status="INVALID_BENCHMARK", reasons=["run aborted: boom"])
    assert any("no preregistered screen explains" in p for p in _publish_and_verify(other, [odd]))


def test_p4_lift_decision_requires_a_clean_post_reveal_verification():
    rows = _field() + lr.records("mind", lr.BETTER)
    assert any("not verified after the reveal" in p for p in v03a.lift_decision(rows, "mind", grid=lr.GRID)["coverage_problems"])
    found = v03a.lift_decision(rows, "mind", grid=lr.GRID, verification=["x"])["coverage_problems"]
    assert any("found 1 problem" in p for p in found)


def test_p4_candidate_dynamic_calls_twins_and_markers(tmp_path, monkeypatch):
    """Review round 5 MINORs: dynamic code through attribute calls, __init__ compiled twins, pinned package markers."""
    pkg = tmp_path / "dyn"
    pkg.mkdir()
    (pkg / "__init__.py").write_bytes(b"")
    (pkg / "a.py").write_bytes(b"import builtins\n\ndef run(card, client, *, seed=0):\n    builtins.exec('1')\n")
    (pkg / "b.py").write_bytes(b"from os import *\n\ndef run(card, client, *, seed=0):\n    return {}\n")
    (pkg / "c.py").write_bytes(b"import re\n\ndef run(card, client, *, seed=0, model=None):\n"
                               b"    re.compile('x')\n    return model.eval() if model else {}\n")
    (pkg / "d.py").write_bytes(b"from builtins import exec as run_it\n\ndef run(card, client, *, seed=0):\n    return {}\n")
    monkeypatch.setattr(formal, "_ROOT", tmp_path)
    monkeypatch.setattr(formal, "_identity_pinned_files", lambda: frozenset())
    monkeypatch.setattr(formal, "_tracked_engcore", lambda: frozenset())

    def cand(module, *files):
        return {"name": "mind", "spec": f"{module}:run",
                "code_sha256": {f: H((tmp_path / f).read_bytes()).hexdigest() for f in files}}

    assert any("dynamic loading" in p for p in formal.candidate_code_problems(cand("dyn.a", "dyn/__init__.py", "dyn/a.py")))
    assert formal.candidate_code_problems(cand("dyn.b", "dyn/__init__.py", "dyn/b.py")) == []      # '*' is not a file
    assert formal.candidate_code_problems(cand("dyn.c", "dyn/__init__.py", "dyn/c.py")) == []      # ordinary methods
    assert any("dynamic loading" in p for p in formal.candidate_code_problems(cand("dyn.d", "dyn/__init__.py", "dyn/d.py")))
    (pkg / "__init__.pyc").write_bytes(b"\x00")
    assert any("ambiguous" in p for p in formal.candidate_code_problems(cand("dyn.b", "dyn/__init__.py", "dyn/b.py")))
    markers = json.loads(v03p.PREREG_PATH.read_bytes())["package_markers"]
    assert set(markers) == {"benchmarks/__init__.py", "benchmarks/genesis_lite/__init__.py"}


def test_p4_candidate_parent_packages_and_ambiguous_files_are_refused(tmp_path, monkeypatch):
    """Review round 4 N2 (a, b): the files of every parent package run on import; a compiled twin may run instead of
    the scanned source."""
    pkg = tmp_path / "candpkg"
    (pkg / "inner").mkdir(parents=True)
    (pkg / "__init__.py").write_bytes(b"x = 1\n")
    (pkg / "inner" / "__init__.py").write_bytes(b"")
    (pkg / "inner" / "agent.py").write_bytes(b"def run(card, client, *, seed=0):\n    return {}\n")
    monkeypatch.setattr(formal, "_ROOT", tmp_path)
    monkeypatch.setattr(formal, "_identity_pinned_files", lambda: frozenset())
    monkeypatch.setattr(formal, "_tracked_engcore", lambda: frozenset())

    def cand(*files):
        return {"name": "mind", "spec": "candpkg.inner.agent:run",
                "code_sha256": {f: H((tmp_path / f).read_bytes()).hexdigest() for f in files}}

    assert any("candpkg/__init__.py runs on import" in p for p in formal.candidate_code_problems(
        cand("candpkg/inner/agent.py")))
    assert formal.candidate_code_problems(cand("candpkg/__init__.py", "candpkg/inner/__init__.py",
                                               "candpkg/inner/agent.py")) == []
    (pkg / "inner" / "agent.pyd").write_bytes(b"MZ")
    assert any("ambiguous module file" in p for p in formal.candidate_code_problems(
        cand("candpkg/__init__.py", "candpkg/inner/__init__.py", "candpkg/inner/agent.py")))


def _v02_runner(arm, *, master_seed, campaign_id, presentation, seed):
    return v02_harness.run_one(arm, v02_arms.ARMS[arm][0], master_seed=master_seed, campaign_id=campaign_id,
                               presentation=presentation, seed=seed).to_dict()


def test_attempt_a_whole_record_swap_between_arms_does_not_replay(tmp_path):
    """Review round 3 N3: swapping arm AND shown cards between two records of one world set keeps the key and card
    checks happy; re-running the registered arm on its re-derived master exposes it."""
    ctx = _attempt(tmp_path, "swap", arms=("careful", "always_refuse"))
    careful, refuse = ctx["records"]
    kw = {"prereg_sha256": ctx["prereg"], "runner": _v02_runner}
    assert formal.replay_record(careful, ctx["root"], ctx["admission"], **kw) == []
    assert formal.replay_record(refuse, ctx["root"], ctx["admission"], **kw) == []
    forged = {**careful, "universes": refuse["universes"]}           # careful's label and cards, refuse's results
    assert any("does not reproduce" in p for p in formal.replay_record(forged, ctx["root"], ctx["admission"], **kw))
    assert formal.replay_record(dict(careful, arm="mind"), ctx["root"], ctx["admission"], **kw)


def test_p4_candidate_spec_module_and_its_imports_must_be_pinned():
    """Review round 2 defect B: the spec's own module and every first-party file it imports are pinned."""
    stateful = "tests/genesis_lite/stateful_arms.py"
    ok = {"name": "mind", "spec": "tests.genesis_lite.stateful_arms:remembers",
          "code_sha256": {stateful: H((v03p.v02.ROOT / stateful).read_bytes()).hexdigest()}}
    assert formal.candidate_code_problems(ok) == []
    readme = {"name": "mind", "spec": "tests.genesis_lite.stateful_arms:remembers",
              "code_sha256": {"README.md": H((v03p.v02.ROOT / "README.md").read_bytes()).hexdigest()}}
    assert any("is not one of its pinned files" in p for p in formal.candidate_code_problems(readme))
    host = "benchmarks/genesis_lite/proposer_host.py"
    dynamic = {"name": "mind", "spec": "benchmarks.genesis_lite.proposer_host:main",
               "code_sha256": {host: H((v03p.v02.ROOT / host).read_bytes()).hexdigest()}}
    assert any("dynamic loading" in p for p in formal.candidate_code_problems(dynamic))   # importlib: refused
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


def test_readiness_required_tests_match_the_test_files():
    """The gate's exact-name lists cannot drift from the files: every ledger-prefixed test in the draft's test files
    is required by some row, and every required name exists (the escrow file's names live on the escrow branch)."""
    import ast  # noqa: PLC0415

    names = set()
    for rel in readiness.TEST_FILES[:2]:
        tree = ast.parse((v03p.v02.ROOT / rel).read_text(encoding="utf-8"))
        names |= {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}
    required = {n for v in readiness.REQUIRED_TESTS.values() for n in v}
    prefixes = ("test_fda", "test_o1_", "test_pilot_", "test_readiness_p3_", "test_p4_", "test_p5_", "test_attempt_",
                "test_harness_", "test_d3b_", "test_d2b_", "test_d5_", "test_d7_")
    assert required <= names
    assert {n for n in names if n.startswith(prefixes)} == required


def test_readiness_every_d5_row_names_its_tests_and_needs_them_passed():
    """Each D5 ledger row, the isolation boundary included, names exact required tests. Without executed evidence that
    every one of them passed, the row cannot be verified, whatever status the pinned evidence gives it."""
    for row in readiness.D5_ROWS:
        names = readiness.REQUIRED_TESTS[row]
        assert names, row
        assert not readiness._row_verified(names, {})                                     # no evidence
        passed = {f"tests/x.py::{n}": "passed" for n in names}
        assert readiness._row_verified(names, passed)
        failed = dict(passed, **{f"tests/x.py::{names[0]}": "failed"})
        assert not readiness._row_verified(names, failed)                                  # one failure is enough
        missing = {k: v for k, v in passed.items() if not k.endswith("::" + names[-1])}
        assert not readiness._row_verified(names, missing)                                 # one missing is enough
