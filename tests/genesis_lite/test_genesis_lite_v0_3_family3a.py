"""Genesis-lite v0.3 D5, family 3a scaffold (BR-D5-RUNTIME-01, owner-approved 2026-10-21): failing-first tests.

Every record here is synthetic. A passing test shows what the validator and the gates accept and refuse. It is not
runtime proof: nothing here launches a card, measures the formal machine or closes BLOCKER 1. D5 stays NOT_PROVEN.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import os
import pathlib

import pytest

from benchmarks.genesis_lite.v0_3 import device_contract, family3a as f3a, family3a_helper as helper_mod
from benchmarks.genesis_lite.v0_3 import readiness

HOST_DEV = "0:5"                 # the host devtmpfs
CARD_DEV = "0:120"               # every card's /dev tmpfs: sequential cards reuse it, as the spike measured
T0 = 1_792_600_000_000_000_000
SLOT = 50_000_000                # one card per 50 ms
LIFE = 20_000_000                # each card's launch-to-cleanup window
MS = 1_000_000
HEX = "ab" * 32


def pinned_config(**changes):
    values = {k: HEX for k in ("runtime_sha256", "rootfs_tree_sha256", "seccomp_sha256", "helper_sha256")}
    return dataclasses.replace(f3a.PINNED_CONFIG, **{**values, **changes})


#: the shipped config with one digest not yet measured: what a stale or partial pin looks like
UNPINNED_CONFIG = dataclasses.replace(f3a.PINNED_CONFIG, runtime_sha256=f3a.UNPINNED)


def identity_of(config):
    return {k: getattr(config, k) for k in f3a.IDENTITY_KEYS}


def node(name, stamp, dev=CARD_DEV):
    rdev = device_contract.DEVICES["/dev/" + name][0]
    return {"type": "chr", "rdev": rdev, "perm": 0o666, "dev": dev, "ino": 3, "mtime_ns": stamp, "ctime_ns": stamp}


def card(slot, *, utimensat=None, stamps=None):
    start = T0 + slot * SLOT
    dev = {f3a.name_of(p): node(f3a.name_of(p), (stamps or {}).get(p, start + MS)) for p in f3a.ADMITTED}
    dev["shm"] = {"type": "dir", "mnt": 3}
    mounts = [
        {"id": 1, "target": "/", "fstype": "ext4", "device": "8:32", "options": ["ro"], "optional": []},
        {"id": 2, "target": "/dev", "fstype": "tmpfs", "device": CARD_DEV, "options": ["ro", "nosuid", "noexec"],
         "optional": []},
        {"id": 3, "target": "/dev/shm", "fstype": "tmpfs", "device": "0:121", "options": ["rw", "nosuid", "nodev"],
         "optional": []},
        {"id": 4, "target": "/tmp", "fstype": "tmpfs", "device": "0:122", "options": ["rw", "nosuid", "nodev"],
         "optional": []},
        {"id": 5, "target": "/proc", "fstype": "proc", "device": "0:123", "options": ["rw"], "optional": []},
        {"id": 6, "target": "/proc/kcore", "fstype": "tmpfs", "device": CARD_DEV, "options": ["ro"], "optional": []},
    ]
    return {"window": {"start_ns": start, "end_ns": start + LIFE}, "host_devtmpfs": HOST_DEV, "mounts": mounts,
            "dev": dev, "absent": {p: {"open": "ENOENT", "stat": "ENOENT"} for p in f3a.ABSENT},
            "walk": {"entries": 40, "devices": []}, "utimensat": utimensat or {}, "cleanup": dict(f3a.CLEAN)}


def touched():
    return {**{p: "EROFS" for p in f3a.ADMITTED}, **{p: "ENOENT" for p in f3a.ABSENT}}


def baseline(config=None, *, per_bit=f3a.MIN_TRIALS_PER_BIT, controls_per_bit=f3a.MIN_CONTROL_TRIALS_PER_BIT):
    config = config or pinned_config()
    cards, trials, slot = {}, [], 0
    for n in range(2 * per_bit):
        bit = n % 2
        cards[f"e{n}"] = card(slot, utimensat=touched() if bit else {})
        cards[f"d{n}"] = card(slot + 1)
        trials.append({"bit": bit, "encoder": f"e{n}", "decoder": f"d{n}"})
        slot += 2
    controls = []
    for n in range(2 * controls_per_bit):
        bit = n % 2
        enc = card(1000 + 2 * n, utimensat=touched() if bit else {})
        start = enc["window"]["start_ns"]
        seen = {p: (start + 2 * MS if bit else T0 - 10**9) for p in f3a.ADMITTED}
        controls.append({"bit": bit, "encoder": enc, "decoder": card(1001 + 2 * n, stamps=seen)})
    return {"schema": f3a.EVIDENCE_SCHEMA, "deployment": f3a.DEPLOYMENT, "device_contract": f3a.DEVICE_CONTRACT,
            "detector": f3a.DETECTOR, "config_sha256": config.digest(), "identity": identity_of(config),
            "cards": cards, "trials": trials, "controls": {f3a.POWER_CONTROL: controls}, "residue": dict(f3a.CLEAN)}


def reasons(doc, config=None):
    return set(f3a.validate_evidence(doc, config or pinned_config())["reasons"])


class FakeHandle:
    def __init__(self, result):
        self.stdin = self.stdout = None
        self.result = result

    def wait(self, timeout):
        return self.result


class FakeHelper:
    """A test-local helper: it records calls and runs nothing."""

    def __init__(self, ident, result=None):
        self.ident, self.result, self.started, self.asked = ident, result, [], 0

    def identity(self):
        self.asked += 1
        return dict(self.ident)

    def start(self, request):
        self.started.append(request)
        return FakeHandle(self.result if self.result is not None else {
            "schema": f3a.HELPER_RESULT_SCHEMA, "card_id": request["card"]["card_id"], "mode": request["mode"],
            "exit_code": 0, "window": {"start_ns": T0, "end_ns": T0 + LIFE}, "cleanup": dict(f3a.CLEAN)})


def spec(**changes):
    values = {"card_id": "gl3a-0001abcd", "entrypoint": "container_probe", "args": (), "env": (),
              "timeout_s": 60.0}
    return f3a.CardSpec(**{**values, **changes})


# ---- the root helper and the launcher interface ----------------------------------------------------------------------
def test_f3a_without_the_declared_root_launch_the_helper_fails_closed_as_not_implemented(monkeypatch):
    monkeypatch.setattr(f3a.sys, "platform", "linux")
    helper = f3a.default_root_helper()
    assert isinstance(helper, f3a.UnimplementedRootHelper)
    for call in (helper.identity, lambda: helper.start({})):
        with pytest.raises(f3a.RootHelperUnavailable) as exc:
            call()
        assert exc.value.reason == f3a.ROOT_HELPER_NOT_IMPLEMENTED
    launcher = f3a.Family3aLauncher(pinned_config(), helper)
    with pytest.raises(f3a.Family3aRefused) as refused:
        launcher.start(spec())
    assert f3a.ROOT_HELPER_NOT_IMPLEMENTED in refused.value.reasons
    ready = f3a.execution_readiness(pinned_config(), helper)
    assert ready["status"] == f3a.BLOCKED
    assert f3a.ROOT_HELPER_NOT_IMPLEMENTED in ready["reasons"]
    assert f3a.execution_readiness(helper=helper)["status"] == f3a.BLOCKED   # the tree's own config


def test_f3a_missing_identity_pins_are_never_defaulted_and_the_policy_cannot_be_widened():
    unpinned = {r for r, _ in f3a.config_problems(pinned_config(seccomp_sha256=f3a.UNPINNED))}
    assert unpinned == {f3a.CONFIG_UNPINNED}
    assert f3a.config_problems(pinned_config()) == []
    for change in ({"runtime_version": "1.14.0"}, {"admitted": (*f3a.ADMITTED, *f3a.ABSENT[:1])},
                   {"absent": f3a.ABSENT[1:]}, {"cgroup_allow": ("1:3", "1:5", "1:7", "1:8")},
                   {"capabilities": ("CAP_SYS_ADMIN",)}, {"read_only_rootfs": False},
                   {"rootfs_propagation": "rshared"}, {"root_launch": "sudo"}, {"runtime_sha256": "AB" * 32},
                   {"masks_from_card_tmpfs": False}):
        assert f3a.CONFIG_INVALID in {r for r, _ in f3a.config_problems(pinned_config(**change))}, change
    doc = pinned_config().to_dict()
    assert f3a.RuntimeConfig.from_mapping(doc) == pinned_config()
    for broken in ({k: v for k, v in doc.items() if k != "seccomp_sha256"}, {**doc, "extra": 1}, [doc], None):
        with pytest.raises(ValueError):
            f3a.RuntimeConfig.from_mapping(broken)


def test_f3a_a_helper_with_another_identity_is_refused_before_any_card_starts():
    config = pinned_config()
    for key in f3a.IDENTITY_KEYS:
        helper = FakeHelper({**identity_of(config), key: "1.14.0" if key == "runtime_version" else "cd" * 32})
        with pytest.raises(f3a.Family3aRefused) as refused:
            f3a.Family3aLauncher(config, helper).start(spec())
        assert f3a.HELPER_IDENTITY_MISMATCH in refused.value.reasons, key
        assert helper.started == []
        assert f3a.execution_readiness(config, helper)["status"] == f3a.BLOCKED
    missing = FakeHelper({k: v for k, v in identity_of(config).items() if k != "kernel_release"})
    assert f3a.HELPER_IDENTITY_MISMATCH in f3a.execution_readiness(config, missing)["reasons"]
    unpinned = FakeHelper(identity_of(UNPINNED_CONFIG))       # UNPINNED on both sides never matches
    result = f3a.execution_readiness(UNPINNED_CONFIG, unpinned)
    assert {f3a.CONFIG_UNPINNED, f3a.HELPER_IDENTITY_MISMATCH} <= set(result["reasons"])
    good = FakeHelper(identity_of(config))
    assert f3a.execution_readiness(config, good)["status"] == f3a.READY
    assert good.started == []                                    # readiness inspects; it never launches


def test_f3a_the_helper_request_is_typed_and_carries_no_command():
    config = pinned_config()
    request = f3a.helper_request(config, spec())
    assert set(request) == {"schema", "mode", "config_sha256", "card"}
    assert f3a.helper_request_problems(request, config) == []
    assert not {"argv", "command", "shell", "script"} & set(request["card"])
    for bad in (spec(entrypoint="sh"), spec(args=("-c",)), spec(args=("/tmp/x;id",)), spec(args=("rel/path",)),
                spec(env=(("LD_PRELOAD", "/x"),)), spec(env=(("PYTHONDONTWRITEBYTECODE", "0"),)),
                spec(card_id="../x"), spec(timeout_s=0.0), spec(timeout_s=float("nan"))):
        assert f3a.spec_problems(bad), bad
        with pytest.raises(f3a.Family3aRefused):
            f3a.Family3aLauncher(config, FakeHelper(identity_of(config))).start(bad)
    assert f3a.spec_problems(spec(entrypoint="proposer_host", args=("/forge/tree", "/forge/tree/src"))) == []
    for outside in ("/opt/forge", "/forge", "/forge/treehouse", "/forge/tree/../x"):
        assert f3a.spec_problems(spec(entrypoint="proposer_host", args=(outside,))), outside
    for tamper in ({**request, "argv": ["sh"]}, {**request, "mode": "shell"},
                   {**request, "card": {**request["card"], "command": "id"}}, {**request, "config_sha256": HEX}):
        assert f3a.helper_request_problems(tamper, config), tamper
    assert f3a.helper_request_problems(f3a.helper_request(config, spec(entrypoint="proposer_host"),
                                                          mode=f3a.POWER_CONTROL), config)
    helper = FakeHelper(identity_of(config))
    session = f3a.Family3aLauncher(config, helper).start(spec())
    assert helper.started == [request]
    assert session.close(5.0)["cleanup"] == f3a.CLEAN


# ---- Device Contract v2 and the evidence validator -------------------------------------------------------------------
def test_f3a_the_baseline_evidence_rederives_every_node_and_closes_blocker_1_in_readiness_terms():
    verdict = f3a.validate_evidence(baseline(), pinned_config())
    assert verdict["status"] == f3a.PASS, verdict["findings"][:5]
    section = verdict["boundary_findings"]["BLOCKER 1"]
    assert section["evidence"] == readiness.MEASURED and section["detector"] == f3a.DETECTOR
    assert set(section["nodes"]) == set(device_contract.DEVICES)
    assert {section["nodes"][p] for p in f3a.ADMITTED} == {"PRIVATE_TO_CARD"}
    assert {section["nodes"][p] for p in f3a.ABSENT} == {"ABSENT"}
    finding = readiness.BOUNDARY_FINDINGS["BLOCKER 1"]
    assert set(section["nodes"].values()) <= set(finding["closing_results"])
    assert not readiness._closed("BLOCKER 1", finding, verdict)        # no detector is declared: still open
    assert readiness._closed("BLOCKER 1", {**finding, "detectors": (f3a.DETECTOR,)}, verdict)
    assert set(f3a.ADMITTED) | set(f3a.ABSENT) == set(device_contract.DEVICES)
    assert not set(f3a.ADMITTED) & set(f3a.ABSENT)
    assert f3a.CGROUP_ALLOW == ("1:3", "1:5", "1:7")


def test_f3a_a_stale_schema_contract_or_detector_derives_nothing():
    for key, value in (("schema", "forge.genesis_lite.v0_3/family3a_evidence/0"),
                       ("schema", "forge.genesis_lite.v0_3/deployment_evidence/4"),
                       ("device_contract", device_contract.CONTRACT), ("detector", "content_window/1"),
                       ("deployment", "rootless_podman_per_card")):
        doc = {**baseline(), key: value}
        verdict = f3a.validate_evidence(doc, pinned_config())
        assert verdict["status"] == f3a.CHECK_BLOCKED
        assert f3a.EVIDENCE_SCHEMA_STALE in verdict["reasons"], key
        section = verdict["boundary_findings"]["BLOCKER 1"]
        assert section["evidence"] == f3a.NOT_MEASURED
        assert set(section["nodes"].values()) == {f3a.NOT_CLOSED}


def test_f3a_a_stored_pass_is_never_evidence():
    for key, value in (("verified", True), ("status", "PASS"), ("verdict", {"status": "PASS"}),
                       ("boundary_findings", {"BLOCKER 1": {"evidence": "MEASURED", "detector": f3a.DETECTOR,
                                                            "nodes": {p: "ABSENT" for p in device_contract.DEVICES}}})):
        assert f3a.STORED_VERDICT_NOT_EVIDENCE in reasons({**baseline(), key: value}), key
    broken = baseline()                                         # a decoder sees the encoder's stamp: a recovered bit
    one = next(t for t in broken["trials"] if t["bit"] == 1)
    start = broken["cards"][one["encoder"]]["window"]["start_ns"]
    broken["cards"][one["decoder"]]["dev"]["null"].update(mtime_ns=start + 2 * MS, ctime_ns=start + 2 * MS)
    broken["verified"] = True
    verdict = f3a.validate_evidence(broken, pinned_config())
    assert verdict["status"] == f3a.CHECK_BLOCKED
    assert {f3a.CHANNEL_RECOVERED, f3a.STORED_VERDICT_NOT_EVIDENCE} <= set(verdict["reasons"])
    assert verdict["boundary_findings"]["BLOCKER 1"]["nodes"]["/dev/null"] == f3a.NOT_CLOSED
    bare = {k: v for k, v in baseline().items() if k not in ("cards", "trials")}
    bare["verified"] = True
    assert f3a.validate_evidence(bare, pinned_config())["status"] == f3a.CHECK_BLOCKED


def test_f3a_missing_or_dirty_cleanup_blocks_in_the_evidence_and_at_the_launcher():
    doc = baseline()
    del doc["cards"]["d3"]["cleanup"]
    assert f3a.CLEANUP_EVIDENCE_MISSING in reasons(doc)
    doc = baseline()
    doc["cards"]["e0"]["cleanup"]["processes"] = 1
    assert f3a.CLEANUP_RESIDUE in reasons(doc)
    doc = baseline()
    del doc["controls"][f3a.POWER_CONTROL][0]["decoder"]["cleanup"]
    assert f3a.CLEANUP_EVIDENCE_MISSING in reasons(doc)
    doc = baseline()
    del doc["residue"]
    assert f3a.CLEANUP_EVIDENCE_MISSING in reasons(doc)
    doc = baseline()
    doc["residue"]["mounts"] = 2
    assert f3a.CLEANUP_RESIDUE in reasons(doc)
    config = pinned_config()
    for result in ({"schema": f3a.HELPER_RESULT_SCHEMA, "card_id": "gl3a-0001abcd", "mode": f3a.CARD, "exit_code": 0,
                    "window": {"start_ns": T0, "end_ns": T0 + LIFE}},
                   {"schema": f3a.HELPER_RESULT_SCHEMA, "card_id": "gl3a-0001abcd", "mode": f3a.CARD, "exit_code": 0,
                    "window": {"start_ns": T0, "end_ns": T0 + LIFE}, "cleanup": {**f3a.CLEAN, "cgroups": 1}}):
        session = f3a.Family3aLauncher(config, FakeHelper(identity_of(config), result)).start(spec())
        with pytest.raises(f3a.Family3aRefused) as refused:
            session.close(5.0)
        assert refused.value.reasons & {f3a.CLEANUP_EVIDENCE_MISSING, f3a.CLEANUP_RESIDUE}


def test_f3a_missing_or_powerless_positive_control_blocks_every_admitted_node():
    doc = baseline()
    doc["controls"] = {}
    verdict = f3a.validate_evidence(doc, pinned_config())
    assert f3a.POSITIVE_CONTROL_MISSING in verdict["reasons"]
    assert set(verdict["boundary_findings"]["BLOCKER 1"]["nodes"].values()) == {f3a.NOT_CLOSED}
    few = baseline(controls_per_bit=f3a.MIN_CONTROL_TRIALS_PER_BIT - 1)
    assert f3a.POSITIVE_CONTROL_MISSING in reasons(few)
    weak = baseline()
    for c in weak["controls"][f3a.POWER_CONTROL]:
        if c["bit"] == 1:
            c["decoder"]["dev"]["zero"].update(mtime_ns=T0 - 10**9, ctime_ns=T0 - 10**9)
    verdict = f3a.validate_evidence(weak, pinned_config())
    assert f3a.POSITIVE_CONTROL_NO_POWER in verdict["reasons"]
    assert verdict["status"] == f3a.CHECK_BLOCKED
    lazy = baseline()                                         # an encoder that never touched the nodes has no power
    lazy["controls"][f3a.POWER_CONTROL][1]["encoder"]["utimensat"] = {}
    assert f3a.POSITIVE_CONTROL_NO_POWER in reasons(lazy)
    few_trials = baseline(per_bit=f3a.MIN_TRIALS_PER_BIT - 1)
    assert f3a.DEVICE_EVIDENCE_INCOMPLETE in reasons(few_trials)


def test_f3a_an_identity_mismatch_in_the_evidence_blocks():
    doc = baseline()
    doc["identity"]["runtime_version"] = "1.14.0"
    assert f3a.EVIDENCE_IDENTITY_MISMATCH in reasons(doc)
    doc = baseline()
    del doc["identity"]["seccomp_sha256"]
    assert f3a.EVIDENCE_IDENTITY_MISMATCH in reasons(doc)
    doc = baseline()
    doc["config_sha256"] = "cd" * 32
    assert f3a.EVIDENCE_IDENTITY_MISMATCH in reasons(doc)
    other = pinned_config(seccomp_sha256="cd" * 32)               # evidence measured under another pinned config
    assert f3a.EVIDENCE_IDENTITY_MISMATCH in reasons(baseline(), other)
    assert f3a.validate_evidence(baseline(UNPINNED_CONFIG), UNPINNED_CONFIG)["status"] == f3a.CHECK_BLOCKED


def test_f3a_device_contract_v2_rederives_privacy_without_inode_identity():
    doc = baseline()                       # every card reuses one st_dev and one st_ino: privacy never rests on them
    assert {n["dev"] for c in doc["cards"].values() for n in c["dev"].values() if n["type"] == "chr"} == {CARD_DEV}
    assert {n["ino"] for c in doc["cards"].values() for n in c["dev"].values() if n["type"] == "chr"} == {3}
    assert f3a.validate_evidence(doc, pinned_config())["status"] == f3a.PASS
    cases = {
        "a node on the host devtmpfs": (lambda d: d["cards"]["d0"]["dev"]["full"].update(dev=HOST_DEV),
                                        f3a.DEVICE_NOT_CARD_PRIVATE, "/dev/full"),
        "a node older than its card (reused)": (
            lambda d: d["cards"]["d2"]["dev"]["null"].update(ctime_ns=d["cards"]["d1"]["window"]["end_ns"]),
            f3a.DEVICE_NOT_CARD_PRIVATE, "/dev/null"),
        "an mtime set from outside the card": (lambda d: d["cards"]["d3"]["dev"]["zero"].update(mtime_ns=T0 + 10**15),
                                               f3a.DEVICE_NOT_CARD_PRIVATE, "/dev/zero"),
        "a wrong major:minor": (lambda d: d["cards"]["e1"]["dev"]["zero"].update(rdev="1:8"),
                                f3a.DEVICE_NOT_CARD_PRIVATE, "/dev/zero"),
        "/dev on devtmpfs": (lambda d: d["cards"]["e2"]["mounts"][1].update(fstype="devtmpfs", device=HOST_DEV),
                             f3a.HOST_DEVICE_REACHABLE, "/dev/null"),
        "a mask bound from the host node": (
            lambda d: d["cards"]["e2"]["mounts"][5].update(fstype="devtmpfs", device=HOST_DEV),
            f3a.HOST_DEVICE_REACHABLE, "/dev/zero"),
        "a row from the host devtmpfs under another fstype": (
            lambda d: d["cards"]["e3"]["mounts"][5].update(device=HOST_DEV), f3a.HOST_DEVICE_REACHABLE, "/dev/full"),
        "a shared mount": (lambda d: d["cards"]["d4"]["mounts"][2].update(optional=["shared:7"]),
                           f3a.MOUNT_PROPAGATION_SHARED, "/dev/full"),
        "a device node found by the walk": (lambda d: d["cards"]["d4"]["walk"].update(devices=["/opt/x"]),
                                            f3a.HOST_DEVICE_REACHABLE, "/dev/null"),
        "a blocked node present": (lambda d: d["cards"]["d5"]["dev"].update(
            {f3a.name_of(f3a.ABSENT[0]): node("null", T0)}), f3a.DEVICE_PRESENT_NOT_ABSENT, f3a.ABSENT[0]),
        "a blocked node that opens": (lambda d: d["cards"]["d5"]["absent"][f3a.ABSENT[1]].update(open="OPENED"),
                                      f3a.DEVICE_PRESENT_NOT_ABSENT, f3a.ABSENT[1]),
        "overlapping card windows": (lambda d: d["cards"]["d0"]["window"].update(
            start_ns=d["cards"]["e0"]["window"]["end_ns"] - MS), f3a.DEVICE_EVIDENCE_INCOMPLETE, "/dev/null"),
        "cards closer than the coarse clock": (lambda d: d["cards"]["d0"]["window"].update(
            start_ns=d["cards"]["e0"]["window"]["end_ns"] + MS), f3a.DEVICE_EVIDENCE_INCOMPLETE, "/dev/zero"),
        "an encoder that did nothing on bit 1": (lambda d: d["cards"]["e1"].update(utimensat={}),
                                                 f3a.DEVICE_EVIDENCE_INCOMPLETE, "/dev/null"),
        "a card used twice": (lambda d: d["trials"][1].update(decoder="d0"), f3a.DEVICE_EVIDENCE_INCOMPLETE,
                              "/dev/null"),
    }
    for name, (mutate, reason, path) in cases.items():
        doc = baseline()
        mutate(doc)
        verdict = f3a.validate_evidence(doc, pinned_config())
        assert verdict["status"] == f3a.CHECK_BLOCKED, name
        assert reason in verdict["reasons"], name
        assert verdict["boundary_findings"]["BLOCKER 1"]["nodes"][path] == f3a.NOT_CLOSED, name


def test_f3a_the_validator_never_raises_and_reports_every_node():
    garbage = [None, [], "x", 3, {"schema": f3a.EVIDENCE_SCHEMA}, {**baseline(), "cards": []},
               {**baseline(), "cards": {"e0": None}}, {**baseline(), "trials": [None, 3]},
               {**baseline(), "controls": {f3a.POWER_CONTROL: [{"bit": 1}]}}, {**baseline(), "residue": "clean"}]
    doc = baseline()
    doc["cards"]["d0"]["dev"]["null"] = {"type": "chr"}
    garbage.append(doc)
    doc = copy.deepcopy(baseline())
    doc["cards"]["d0"]["mounts"] = [{"target": "/dev"}]
    garbage.append(doc)
    for item in garbage:
        verdict = f3a.validate_evidence(item, pinned_config())
        assert verdict["status"] == f3a.CHECK_BLOCKED
        assert set(verdict["boundary_findings"]["BLOCKER 1"]["nodes"]) == set(device_contract.DEVICES)


# ---- pre-admission ordering and fail-closed readiness ----------------------------------------------------------------
def test_f3a_pre_admission_runs_its_stages_in_order_and_stops_at_the_first_failure():
    calls = []

    def collect(launcher):
        calls.append(launcher)
        return baseline()

    result = f3a.pre_admission(UNPINNED_CONFIG, FakeHelper(identity_of(pinned_config())), collect)
    assert [s["stage"] for s in result["stages"]] == list(f3a.STAGES)
    assert [s["status"] for s in result["stages"]] == ["BLOCKED"] + ["NOT_REACHED"] * 4
    assert result["status"] == f3a.REFUSED and calls == []
    result = f3a.pre_admission(pinned_config(), f3a.UnimplementedRootHelper(), collect)
    assert [s["status"] for s in result["stages"]][:3] == [f3a.PASS, "BLOCKED", "NOT_REACHED"]
    assert f3a.ROOT_HELPER_NOT_IMPLEMENTED in result["reasons"] and calls == []
    wrong = FakeHelper({**identity_of(pinned_config()), "kernel_release": "6.6.0"})
    result = f3a.pre_admission(pinned_config(), wrong, collect)
    assert f3a.HELPER_IDENTITY_MISMATCH in result["reasons"] and calls == [] and wrong.started == []
    stored = FakeHelper(identity_of(pinned_config()))
    result = f3a.pre_admission(pinned_config(), stored, lambda _l: {**baseline(), "verified": True})
    assert result["status"] == f3a.REFUSED and f3a.STORED_VERDICT_NOT_EVIDENCE in result["reasons"]

    def crash(_launcher):
        raise OSError("helper died")

    result = f3a.pre_admission(pinned_config(), FakeHelper(identity_of(pinned_config())), crash)
    assert result["status"] == f3a.REFUSED and f3a.EVIDENCE_COLLECTION_FAILED in result["reasons"]
    result = f3a.pre_admission(pinned_config(), FakeHelper(identity_of(pinned_config())), collect)
    assert result["status"] == f3a.ADMISSIBLE and len(calls) == 1
    assert "root" not in f3a.pre_admission.__code__.co_varnames        # it never sees a root or a registry


def test_f3a_the_pinned_config_is_complete_and_names_the_helper_in_this_tree():
    assert f3a.config_problems(f3a.PINNED_CONFIG) == []
    assert f3a.PINNED_CONFIG.helper_sha256 == hashlib.sha256(f3a.HELPER_FILE.read_bytes()).hexdigest()
    result = f3a.execution_readiness(helper=f3a.UnimplementedRootHelper())   # no root launch: still blocked
    assert result["status"] == f3a.BLOCKED
    assert set(result["reasons"]) == {f3a.ROOT_HELPER_NOT_IMPLEMENTED}
    measured = FakeHelper(identity_of(f3a.PINNED_CONFIG))
    assert f3a.execution_readiness(helper=measured)["status"] == f3a.READY
    assert f3a.execution_readiness(helper=measured)["d5"] == "NOT_PROVEN"


def test_f3a_the_scaffold_passes_the_randomness_screen_and_stays_off_the_pinned_identity():
    root = pathlib.Path(f3a.__file__).resolve().parents[3]
    screen = device_contract.scientific_randomness_problems(root)
    assert "benchmarks/genesis_lite/v0_3/family3a.py" in screen["files"]
    assert [p for p in screen["problems"] if "family3a" in p] == []
    assert "family3a.py" not in readiness.v03p.V0_3_FILES            # scaffold: not yet on the formal path
    assert "family3a.py" not in device_contract.DEVICE_PATH_FILES


# ---- the low-level root helper (family3a_helper.py) ------------------------------------------------------------------
def canonical_hex(doc):
    return helper_mod.canonical(doc).hex()


def test_f3a_the_helper_and_the_client_share_every_contract_constant():
    assert helper_mod.REQUEST_SCHEMA == f3a.HELPER_REQUEST_SCHEMA
    assert helper_mod.RESULT_SCHEMA == f3a.HELPER_RESULT_SCHEMA
    assert helper_mod.RESULT_PREFIX == f3a.RESULT_PREFIX
    assert (helper_mod.CARD, helper_mod.POWER_CONTROL) == f3a.MODES
    assert helper_mod.ENTRYPOINTS == f3a.ENTRYPOINTS and helper_mod.CARD_ENV == f3a.CARD_ENV
    assert (helper_mod.KEPT_TREE, helper_mod.KEPT_VENV) == f3a.KEPT_ROOTS
    assert helper_mod.ROOT_LAUNCH == f3a.ROOT_LAUNCH
    assert f"{helper_mod.BASE}/helper.py" == f3a.HELPER_INSTALLED
    assert tuple(f"{ma}:{mi}" for ma, mi in helper_mod.NODES.values()) == f3a.CGROUP_ALLOW
    assert tuple("/dev/" + n for n in helper_mod.NODES) == f3a.ADMITTED
    assert helper_mod.MAX_ARGS == f3a.MAX_ARGS and helper_mod.MAX_TIMEOUT_S == f3a.MAX_TIMEOUT_S
    assert helper_mod.CARD_ID.pattern == f3a.CARD_ID.pattern
    assert helper_mod.CLEAN_KEYS == tuple(f3a.CLEAN)


def test_f3a_the_helper_refuses_exactly_what_the_client_refuses():
    config = pinned_config()
    good = f3a.helper_request(config, spec())
    corpus = [good, f3a.helper_request(config, spec(entrypoint="proposer_host", args=("/forge/tree", "/forge/venv"))),
              {**good, "argv": ["sh"]}, {**good, "mode": "shell"}, {**good, "schema": "x"},
              {**good, "card": {**good["card"], "command": "id"}}, {**good, "card": None}, None, [], "run",
              f3a.helper_request(config, spec(entrypoint="proposer_host", args=("/opt/forge",))),
              f3a.helper_request(config, spec(entrypoint="proposer_host", args=("/forge/tree/../../etc",))),
              f3a.helper_request(config, spec(env=(("LD_PRELOAD", "/x"),))),
              f3a.helper_request(config, spec(timeout_s=0.0)), f3a.helper_request(config, spec(card_id="gl3a-x")),
              f3a.helper_request(config, spec(entrypoint="proposer_host"), mode=f3a.POWER_CONTROL),
              f3a.helper_request(config, spec(), mode=f3a.POWER_CONTROL),
              {**good, "card": {**good["card"], "args": ["/forge/tree"]}}]
    for request in corpus:
        assert bool(helper_mod.request_problems(request)) == bool(f3a.helper_request_problems(request, config)), request
    assert helper_mod.request_problems(good) == []
    assert helper_mod.decode_request(canonical_hex(good)) == good
    for bad in ("zz", canonical_hex({**good, "mode": "shell"}), "", b"{}".hex()):
        with pytest.raises(helper_mod.Refused):
            helper_mod.decode_request(bad)


def test_f3a_the_helper_builds_only_the_spike_spec():
    config = pinned_config()
    dev_dir = "/run/forge-f3a/gl3a-0001abcd/t"
    manifest = {"tree": "/home/u/forge-tree", "venv": None, "image_digest": "sha256:" + HEX}
    card = helper_mod.build_spec(f3a.helper_request(config, spec()), dev_dir, manifest, {"defaultAction": "X"},
                                 ["/proc/kcore", "/proc/keys"])
    assert card["root"] == {"path": helper_mod.ROOTFS, "readonly": True}
    proc = card["process"]
    assert proc["terminal"] is False and proc["noNewPrivileges"] is True and proc["user"] == {"uid": 1000, "gid": 1000}
    assert all(v == [] for v in proc["capabilities"].values()) and len(proc["capabilities"]) == 5
    assert proc["args"] == ["/usr/bin/python3", "-I", "-X", "pycache_prefix=/tmp/pycache",
                            "/forge/tree/benchmarks/genesis_lite/v0_3/container_probe.py"]
    assert [e for e in proc["env"] if e.startswith("PYTHONDONTWRITEBYTECODE")] == []
    mounts = {m["destination"]: m for m in card["mounts"]}
    assert mounts["/dev"]["source"] == f"{dev_dir}/dev" and {"ro", "nosuid", "noexec"} <= set(mounts["/dev"]["options"])
    for masked in ("/proc/kcore", "/proc/keys"):
        assert mounts[masked]["source"] == f"{dev_dir}/mask/empty" and "ro" in mounts[masked]["options"]
    assert not [m for m in card["mounts"] if m["source"].startswith("/dev")]          # nothing from the host /dev
    assert mounts["/forge/tree"]["source"] == "/home/u/forge-tree" and "ro" in mounts["/forge/tree"]["options"]
    assert "/forge/venv" not in mounts
    linux = card["linux"]
    assert linux["rootfsPropagation"] == "rprivate" and linux["devices"] == []
    assert not set(linux["maskedPaths"]) & set(helper_mod.MASK_FILES)                # files are masked from the tmpfs
    assert {n["type"] for n in linux["namespaces"]} == {"pid", "network", "ipc", "uts", "mount", "cgroup", "user"}
    assert linux["uidMappings"] == linux["gidMappings"] == [{"containerID": 0, "hostID": 100000, "size": 65536}]
    rules = linux["resources"]["devices"]
    assert rules[0] == {"allow": False, "access": "rwm"}
    assert tuple(f"{r['major']}:{r['minor']}" for r in rules[1:]) == f3a.CGROUP_ALLOW
    assert linux["cgroupsPath"] == "/forge-f3a/gl3a-0001abcd" and linux["seccomp"] == {"defaultAction": "X"}
    control = helper_mod.build_spec(f3a.helper_request(config, spec(), mode=f3a.POWER_CONTROL), helper_mod.SHARED,
                                    {**manifest, "venv": "/home/u/venv"}, {}, [])
    cm = {m["destination"]: m for m in control["mounts"]}
    assert cm["/dev"]["source"] == f"{helper_mod.SHARED}/dev" and "rw" in cm["/dev"]["options"]
    assert cm["/forge/venv"]["source"] == "/home/u/venv" and "ro" in cm["/forge/venv"]["options"]
    proposer = helper_mod.build_spec(f3a.helper_request(config, spec(entrypoint="proposer_host", args=("/forge/tree",),
                                                                     env=(("PYTHONDONTWRITEBYTECODE", "1"),))),
                                     dev_dir, {**manifest, "venv": "/home/u/venv"}, {}, [])
    assert proposer["process"]["args"][0] == "/forge/venv/bin/python3"
    assert proposer["process"]["args"][-2:] == ["/forge/tree/benchmarks/genesis_lite/proposer_host.py", "/forge/tree"]
    assert "PYTHONDONTWRITEBYTECODE=1" in proposer["process"]["env"]


def test_f3a_the_helper_runs_only_its_fixed_programs_and_never_a_shell():
    source = pathlib.Path(helper_mod.__file__).read_text(encoding="utf-8")
    for banned in ("shell=True", "os.system", "os.exec", "os.popen", "/bin/sh", "bash", "eval(", "exec("):
        assert banned not in source, banned
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    sh_first = {ast.unparse(c.args[0]) for c in calls if ast.unparse(c.func) == "_sh"}
    assert sh_first == {"CRUN", "MOUNT", "UMOUNT"}
    spawned = [c for c in calls if ast.unparse(c.func) in ("subprocess.run", "subprocess.Popen")]
    assert sorted(ast.unparse(c.args[0]) for c in spawned) == sorted([
        "list(argv)", "[CRUN, '--root', CRUN_ROOT, 'run', '--bundle', f'{cdir}/bundle', cid]"])
    with pytest.raises(helper_mod.Refused):
        helper_mod._sh("/usr/bin/env", "id")
    assert set(helper_mod.OPERATIONS) == {"identity", "install-rootfs", "configure-kept", "run", "residue",
                                          "control-teardown"}


def test_f3a_the_helper_tree_digest_ignores_time_and_inode_but_not_content(tmp_path):
    a = tmp_path / "a"
    (a / "usr" / "bin").mkdir(parents=True)
    (a / "usr" / "bin" / "python3").write_bytes(b"\x7fELF")
    (a / "etc").mkdir()
    (a / "etc" / "hostname").write_bytes(b"card\n")
    first = helper_mod.tree_digest(str(a))
    os.utime(a / "etc" / "hostname", (1, 1))
    assert helper_mod.tree_digest(str(a)) == first
    b = tmp_path / "b"
    (b / "etc").mkdir(parents=True)
    (b / "etc" / "hostname").write_bytes(b"card\n")
    (b / "usr" / "bin").mkdir(parents=True)
    (b / "usr" / "bin" / "python3").write_bytes(b"\x7fELF")
    assert helper_mod.tree_digest(str(b)) == first                  # another copy, other inodes, other order
    (b / "etc" / "hostname").write_bytes(b"cards\n")
    assert helper_mod.tree_digest(str(b)) != first
    (b / "etc" / "hostname").write_bytes(b"card\n")
    assert helper_mod.tree_digest(str(b)) == first
    os.chmod(b / "etc" / "hostname", 0o444)                          # permission bits are part of the identity
    assert helper_mod.tree_digest(str(b)) != first
    os.chmod(b / "etc" / "hostname", 0o666 if os.name == "nt" else 0o644)
    assert helper_mod.tree_digest(str(b)) == first
    (b / "forge").mkdir()
    assert helper_mod.tree_digest(str(b)) != first


def test_f3a_the_helper_derives_the_seccomp_profile_like_the_spike():
    source = {"defaultAction": "SCMP_ACT_ERRNO", "defaultErrnoRet": 38, "syscalls": [
        {"names": ["read"], "action": "SCMP_ACT_ALLOW"},
        {"names": ["bpf"], "action": "SCMP_ACT_ALLOW", "includes": {"caps": ["CAP_SYS_ADMIN"]}},
        {"names": ["arm_only"], "action": "SCMP_ACT_ALLOW", "includes": {"arches": ["arm64"]}},
        {"names": ["not_amd64"], "action": "SCMP_ACT_ALLOW", "excludes": {"arches": ["amd64"]}},
        {"names": ["future"], "action": "SCMP_ACT_ALLOW", "includes": {"minKernel": "6.9"}},
        {"names": ["old"], "action": "SCMP_ACT_ALLOW", "includes": {"minKernel": "5.6"}},
        {"names": ["personality"], "action": "SCMP_ACT_ALLOW", "args": [{"index": 0, "value": 0, "op": "SCMP_CMP_EQ"}]},
        {"names": ["ptrace"], "action": "SCMP_ACT_ERRNO", "errnoRet": 1}]}
    out = helper_mod.seccomp_profile(source, "6.6.87.2-microsoft-standard-WSL2")
    assert [r["names"] for r in out["syscalls"]] == [["read"], ["old"], ["personality"], ["ptrace"]]
    assert out["syscalls"][2]["args"] and out["syscalls"][3]["errnoRet"] == 1
    assert out["defaultAction"] == "SCMP_ACT_ERRNO" and out["defaultErrnoRet"] == 38


def test_f3a_the_wsl_client_uses_the_declared_root_launch_without_a_shell():
    argv = f3a.wsl_argv("identity")
    assert argv[:6] == ["wsl.exe", "-d", f3a.WSL_DISTRO, "-u", "root", "--exec"]
    assert argv[6:] == ["/usr/bin/python3", "-I", f3a.HELPER_INSTALLED, "identity"]
    assert " ".join(argv[:1] + argv[3:5]) == f3a.ROOT_LAUNCH
    assert not {"bash", "sh", "-c", "--"} & set(argv)
    record = {"schema": f3a.HELPER_RESULT_SCHEMA, "card_id": "gl3a-0001abcd"}
    text = "warning\n" + f3a.RESULT_PREFIX + '{"old": 1}\n' + f3a.RESULT_PREFIX + json.dumps(record)
    assert f3a.parse_result(text) == record
    assert f3a.parse_result("nothing") is None and f3a.parse_result(f3a.RESULT_PREFIX + "{broken") is None
