"""v0.4 per-universe OS isolation (gaps G5, G14, FDA-19; owner decisions D3, D11).

Pure checks run everywhere. The integration checks need Linux, root and a code tree readable by uid 65534 (on WSL a
checkout under /opt with drvfs umask=077); elsewhere they skip, and a skip here is never evidence of isolation."""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import shlex

import pytest

from benchmarks.genesis_lite import isolated_host as ih

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _readable_by_nobody(path: pathlib.Path) -> bool:
    p = path.resolve()
    while True:
        st = p.stat()
        if not st.st_mode & 0o005:
            return False
        if p.parent == p:
            return True
        p = p.parent


def _can_isolate() -> bool:
    return ih.support()[0] and _readable_by_nobody(ROOT / "benchmarks" / "genesis_lite" / "proposer_host.py")


integration = pytest.mark.skipif(not _can_isolate(), reason="needs Linux, root and a tree readable by uid 65534")


# ------------------------------------------------------------------------------------------- pure (every platform)
def test_the_command_builds_every_namespace_hide_and_privilege_drop():
    cmd = ih.command(["/home", "/srv/x"], {"EXTRA": "1"}, python="/opt/py")
    assert cmd[:9] == ["unshare", "--mount", "--pid", "--fork", "--net", "--ipc", "--uts", "--mount-proc", "--"]
    inner = cmd[-1]
    for p in ("/home", "/srv/x"):
        assert f"mount -t tmpfs -o size=64k,mode=000 tmpfs {shlex.quote(p)}" in inner
    assert "mount -t tmpfs -o size=1g,mode=1777 tmpfs /tmp" in inner
    assert "--reuid=65534 --regid=65534 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs" in inner
    assert "/usr/bin/env -i" in inner and "EXTRA=1" in inner and "OMP_NUM_THREADS=1" in inner
    assert inner.index("mount -t tmpfs") < inner.index("setpriv")          # hides are mounted before the uid switch
    # re-review M3: a fresh user namespace after the uid switch (private keyrings), the bounding set dropped again in it
    assert inner.index("--no-new-privs") < inner.index(ih.USER_NAMESPACE) < inner.index("/usr/bin/env -i")
    assert ih.USER_NAMESPACE.startswith("unshare --user --map-root-user -- setpriv --inh-caps=-all --bounding-set=-all")


def test_the_outside_verification_requires_a_private_user_namespace():
    good = {"inspected": True, "uid": [65534] * 4, "gid": [65534] * 4, "groups": [], "caps": {"CapEff": 0},
            "no_new_privs": True, "private_namespaces": {"mnt": True, "user": True}, "hidden": {"/home": True},
            "private_tmp": True, "whitelist_covered": True, "exposed_read_only": {"/opt/code": True},
            "private_writable": {"/tmp": True}, "shared_state_covered": {"/run": True}}
    assert ih.verified(good)
    assert not ih.verified({**good, "private_namespaces": {"mnt": True, "user": False}})


def test_the_operator_environment_never_reaches_the_proposer(monkeypatch):
    monkeypatch.setenv("FORGE_ROOT_SECRET", "s3cr3t")
    inner = ih.command([], {})[-1]
    assert "FORGE_ROOT_SECRET" not in inner and "s3cr3t" not in inner


EXPOSED = (str(ROOT.resolve()),)


def test_a_missing_hidden_path_refuses_instead_of_being_skipped(tmp_path):
    with pytest.raises(ih.IsolationUnavailable, match="not an existing directory"):
        ih.hidden_paths([tmp_path / "does-not-exist"], exposed=EXPOSED)


def test_hiding_the_code_tree_itself_refuses():
    with pytest.raises(ih.IsolationUnavailable, match="contains an exposed directory"):
        ih.hidden_paths([ROOT], exposed=EXPOSED)


def test_every_pilot_results_directory_of_the_tree_is_hidden(monkeypatch):
    # a checkout under a default hide (/home on a Linux CI runner) is refused as a whole, which the test above covers;
    # drop that one default here so the per-directory hides are still checked on every host
    monkeypatch.setattr(ih, "DEFAULT_HIDDEN", tuple(d for d in ih.DEFAULT_HIDDEN if not ih._under(EXPOSED[0], d)))
    hidden = ih.hidden_paths(exposed=EXPOSED)
    for p in ROOT.glob("benchmarks/**/pilot_results"):
        assert str(p.resolve()) in hidden


def test_nested_hides_collapse_to_their_ancestor():
    assert set(ih._minimal(["/root/a/b", "/root", "/home/x", "/home/x/y"])) == {"/home/x", "/root"}


def test_the_code_tree_must_live_under_the_whitelist_root():
    if ih._under(str(ROOT.resolve()), ih.WHITELIST_ROOT):
        pytest.skip("this checkout is under /opt")
    with pytest.raises(ih.IsolationUnavailable, match="not under /opt"):
        ih.exposures()


def test_the_whitelist_stages_exposures_before_covering_opt_and_binds_them_back_read_only():
    inner = ih.command(["/mnt", "/home"], {}, python="/usr/bin/python3", exposed=("/opt/code", "/opt/venv"))[-1]
    order = [inner.index(s) for s in ("mount -t tmpfs -o size=1m,mode=755 tmpfs /mnt", "mount --bind /opt/code /mnt/fg0",
                                       "mount -t tmpfs -o size=1m,mode=755 tmpfs /opt", "mount --bind /mnt/fg0 /opt/code",
                                       "mount -o remount,bind,ro /opt/code", "mount -o remount,bind,ro /opt/venv",
                                       "mount -t tmpfs -o size=64k,mode=000 tmpfs /mnt", "setpriv")]
    assert order == sorted(order)


def test_outside_verification_fails_closed_on_any_missing_property():
    good = {"inspected": True, "uid": [65534] * 4, "gid": [65534] * 4, "groups": [], "caps": {"CapEff": 0},
            "no_new_privs": True, "private_namespaces": {"mnt": True, "pid": True}, "hidden": {"/home": True},
            "private_tmp": True, "whitelist_covered": True, "exposed_read_only": {"/opt/code": True},
            "private_writable": {"/tmp": True, "/dev/shm": True}, "shared_state_covered": {"/run": True}}
    assert ih.verified(good)
    for key, bad in (("uid", [0] * 4), ("groups", [27]), ("caps", {"CapEff": 1}), ("no_new_privs", False),
                     ("private_namespaces", {"mnt": True, "pid": False}), ("hidden", {"/home": False}),
                     ("hidden", {}), ("private_tmp", False), ("inspected", False), ("whitelist_covered", False),
                     ("exposed_read_only", {}), ("exposed_read_only", {"/opt/code": False}),
                     ("private_writable", {}), ("private_writable", {"/dev/shm": False}),
                     ("shared_state_covered", {"/run": False})):
        assert not ih.verified({**good, key: bad}), key


def test_off_linux_or_without_root_the_host_refuses_to_start():
    if ih.support()[0]:
        pytest.skip("this host can isolate")
    with pytest.raises(ih.IsolationUnavailable):
        ih.IsolatedProposerHost([])


# ------------------------------------------------------------------------------------------- integration (Linux root)
CARD = {"universe_id": "bf-v4-test", "inputs": [{"name": "a", "unit": "L^1", "settable": True, "range": [1.0, 2.0]}],
        "output": {"name": "y", "unit": "L^1"}}


class _Client:
    def __init__(self):
        self.calls = 0

    def observe(self, uid, settings, query_id=""):
        self.calls += 1
        return {"observation": {**settings, "y": 1.0}}


def _attack(fn: str, hidden):
    host = ih.IsolatedProposerHost(hidden)
    try:
        out = host.propose(f"tests.genesis_lite.attack_arms_v4:{fn}", CARD, 0, _Client())
        return json.loads(out["rationale"]) if out.get("answer") == "no_law" else out, host.outside
    finally:
        host.close()


@pytest.fixture
def secret_dir(tmp_path_factory):
    # world-traversable and world-readable on purpose, next to the code tree under /opt: only the whitelist protects it
    d = pathlib.Path("/opt") / f"forge-v4-secret-{secrets.token_hex(4)}"
    d.mkdir(mode=0o755)
    token = secrets.token_hex(16)
    (d / "root.bin").write_text(token)
    (d / "root.bin").chmod(0o644)                                  # world-readable on purpose: only the hide protects it
    yield d, token
    (d / "root.bin").unlink()
    d.rmdir()


@integration
def test_the_isolated_process_is_verified_from_outside():
    host = ih.IsolatedProposerHost(ih.hidden_paths())
    try:
        assert ih.verified(host.outside), host.outside
    finally:
        host.close()


@integration
def test_hidden_secrets_cannot_be_read_or_listed(secret_dir):
    d, token = secret_dir
    report, outside = _attack("read_secrets", ih.hidden_paths([d]))
    assert ih.verified(outside)
    assert token not in json.dumps(report)
    assert not [p for p in report["seen"] if p.startswith(("/root/", "/home/", "/mnt/", str(d)))
                or "pilot_results/" in p], report["seen"]
    exposed = ih.exposures()
    # under /opt only the exposures and the (otherwise empty) directories leading to them are visible
    others = [p for p in report["seen"] if p.startswith("/opt/")
              and not any(ih._under(p, e) or ih._under(e, p) for e in exposed)]
    assert not others, others                                    # another checkout under /opt is invisible
    # re-review M3: the process is uid 0 only of its own empty user namespace; outside, where file access is decided,
    # it is 65534 with every capability at zero (checked by verified above)
    assert report["uid"] == 0 and report["ppid"] == 0
    assert outside["uid"] == [65534] * 4 and not any(outside["caps"].values())
    assert not any(k.startswith("FORGE") for k in report["env"])


@integration
def test_the_hide_is_what_protects_it_positive_control(secret_dir):
    # exposing the same directory makes the secret readable: the attack and the probe can see a real leak
    d, token = secret_dir
    exposed = ih.exposures([d])
    host = ih.IsolatedProposerHost(ih.hidden_paths(exposed=exposed), exposed=exposed)
    try:
        out = host.propose("tests.genesis_lite.attack_arms_v4:read_secrets", CARD, 0, _Client())
    finally:
        host.close()
    assert token in out["rationale"]


@integration
def test_no_outbound_network_and_no_visible_operator():
    net, _ = _attack("reach_network", ih.hidden_paths())
    assert net["network"].startswith("refused")
    procs, _ = _attack("see_operator", ih.hidden_paths())
    assert procs["readable_maps"] == []
    assert os.getpid() not in procs["visible_pids"]


@integration
def test_the_observe_relay_works_through_the_isolated_process():
    client = _Client()
    host = ih.IsolatedProposerHost(ih.hidden_paths())
    try:
        out = host.propose("tests.genesis_lite.attack_arms_v4:honest", CARD, 0, client)
    finally:
        host.close()
    assert out["answer"] == "insufficient_evidence" and client.calls == 1


@integration
def test_a_campaign_runs_with_six_verified_processes_and_stays_valid():
    from benchmarks.genesis_lite.harness_v4 import run_one_v4
    rec = run_one_v4("careful", "careful",                       # proposer_host resolves a bare name in arms.ARMS
                     master_seed=b"\x01" * 32, campaign_id="gl-v04-iso-0", presentation="anonymous",
                     hidden=ih.hidden_paths())
    assert rec["status"] == "VALID", rec.get("reasons")
    assert len(rec["isolation_checks"]) == 6 and all(ih.verified(c) for c in rec["isolation_checks"])
    assert rec["isolation"] == ih.ISOLATION_LABEL



def test_an_infrastructure_failure_is_recorded_so_the_run_becomes_invalid(monkeypatch):
    # finding 5: a launch failure must not reach the campaign as an arm's -1; it is recorded for INVALID_BENCHMARK
    def boom(*a, **k):
        raise ih.IsolationUnavailable("no namespaces here")
    monkeypatch.setattr(ih, "IsolatedProposerHost", boom)
    checks = []
    arm = ih.per_universe_arm("careful", (), checks)
    with pytest.raises(ih.IsolationUnavailable):
        arm(CARD, _Client(), seed=0)
    assert checks and "infrastructure_failure" in checks[0] and not ih.verified(checks[0])


@pytest.mark.parametrize("error,infrastructure", [(BrokenPipeError("pipe closed"), True), (OSError("io"), True),
                                                  (RuntimeError("the proposer failed: bad law"), False)])
def test_a_proposer_dying_mid_relay_is_an_infrastructure_failure(monkeypatch, error, infrastructure):
    # re-review L2: a dead pipe is the host's failure, never the arm's -1 on a run that stays VALID
    class Host:
        outside = {"inspected": True}

        def __init__(self, *a, **k):
            pass

        def propose(self, *a, **k):
            raise error

        def close(self):
            pass
    monkeypatch.setattr(ih, "IsolatedProposerHost", Host)
    checks = []
    with pytest.raises(type(error)):
        ih.per_universe_arm("careful", (), checks)(CARD, _Client(), seed=0)
    assert any("infrastructure_failure" in c for c in checks) is infrastructure


@integration
def test_no_state_passes_from_one_proposer_process_to_the_next():
    # finding 1: process A writes a mark into every directory it can write and a key on its uid's kernel keyring
    # (re-review M3); process B, a later universe of the same uid, finds none
    first, outside_a = _attack("leave_marks", ih.hidden_paths())
    assert ih.verified(outside_a) and outside_a["private_namespaces"]["user"]
    assert "keyring:@u" in first["written"]                         # the key was really left: the probe is live
    found, _ = _attack("find_marks", ih.hidden_paths())
    assert found["found"] == [], found
    writable = set(first["written"]) - {"keyring:@u"}
    assert writable <= {"/tmp", "/dev/shm", "/dev/mqueue"} | {w for w in writable if w.startswith(("/tmp/", "/dev/shm/"))}, writable
