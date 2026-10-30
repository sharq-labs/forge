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


def test_every_pilot_results_directory_of_the_tree_is_hidden():
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
            "private_tmp": True, "whitelist_covered": True, "exposed_read_only": {"/opt/code": True}}
    assert ih.verified(good)
    for key, bad in (("uid", [0] * 4), ("groups", [27]), ("caps", {"CapEff": 1}), ("no_new_privs", False),
                     ("private_namespaces", {"mnt": True, "pid": False}), ("hidden", {"/home": False}),
                     ("hidden", {}), ("private_tmp", False), ("inspected", False), ("whitelist_covered", False),
                     ("exposed_read_only", {}), ("exposed_read_only", {"/opt/code": False})):
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
    assert report["uid"] == 65534 and report["ppid"] == 0
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
