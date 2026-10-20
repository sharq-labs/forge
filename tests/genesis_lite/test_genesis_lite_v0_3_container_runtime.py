"""Checkpoint-2 development runtime controls and legacy-interface regressions.

This rig is not a production launcher. Strict pseudo/device policy remains red.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys

import pytest
from benchmarks.genesis_lite.v0_3 import deployment_attacks as attacks
from benchmarks.genesis_lite.v0_3 import isolation

IMAGE = "localhost/forge-card@sha256:89847920916e46363fe52f7cecc3a2b937d34d6b355dd3e8cc14527fe65a8261"
ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("container_isolation_probe.py")
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux runtime required")


def cleanup_owned(name, nonce, record):
    """Clean only our named AND labelled identity, even if create timed out."""
    inspection = subprocess.run(["podman", "inspect", name], capture_output=True, text=True, timeout=10)
    record["cleanup_inspect"] = vars(inspection)
    if inspection.returncode:
        if "no such" in inspection.stderr.lower():
            record["cleanup"] = {"returncode": 0, "already_absent": True}
            return
        inspection.check_returncode()
    actual = json.loads(inspection.stdout)[0]
    if actual["Config"]["Labels"].get("org.forge.checkpoint2") != nonce:
        raise RuntimeError("CLEANUP_OWNERSHIP_MISMATCH: refusing removal")
    cleanup = subprocess.run(["podman", "rm", "--force", "--ignore", actual["Id"]],
                             capture_output=True, text=True, timeout=15)
    record["cleanup"] = vars(cleanup)
    cleanup.check_returncode()


@pytest.fixture(scope="module")
def rig(tmp_path_factory):
    if not shutil.which("podman"):
        pytest.skip("RUNTIME_UNAVAILABLE: executable missing")
    exists = subprocess.run(["podman", "image", "exists", IMAGE], capture_output=True, text=True)
    if exists.returncode == 1:
        pytest.skip("RUNTIME_UNAVAILABLE: pinned local image absent")
    exists.check_returncode()  # Unexpected runtime/setup failures stay errors.
    inspected_image = subprocess.run(["podman", "image", "inspect", IMAGE], capture_output=True, text=True)
    inspected_image.check_returncode()
    image = json.loads(inspected_image.stdout)[0]
    assert image["Digest"] == IMAGE.split("@")[1]
    directory = tmp_path_factory.mktemp("container-correction")
    transcripts = []
    source_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    assert source_sha == os.environ["FORGE_CHECKPOINT_SOURCE_SHA"]
    rootless = subprocess.check_output(["podman", "info", "--format", "{{.Host.Security.Rootless}}"], text=True).strip()
    assert rootless == "true"
    metadata = dict(source_sha=source_sha, rootless=rootless, python=sys.version,
                    image=IMAGE, image_inspection=image,
                    podman=subprocess.check_output(["podman", "--version"], text=True).strip(),
                    probe_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),
                    launcher_sha256=hashlib.sha256(Path(isolation.__file__).read_bytes()).hexdigest(),
                    tests_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                  Path(__file__).parent.glob("*container*.py")},
                    containerfile_sha256=hashlib.sha256(Path("/home/dev_kaeem/forge-card/Containerfile").read_bytes()).hexdigest())
    server = socket.socket()
    server.bind(("127.0.0.1", 0)); server.listen(8)
    metadata["host_listener"] = server.getsockname()
    with socket.create_connection(server.getsockname(), timeout=1):
        metadata["host_listener_control"] = "REACHED"
    shared = directory / "shared"; shared.mkdir()
    marker = "cp2-" + secrets.token_hex(12)

    def run(phase="A", tokens=None, shared_volume=False, image_ref=IMAGE):
        nonce = secrets.token_hex(16)
        name = "forge-cp2-" + nonce
        argv = ["podman", "create", "--pull=never", "--rm", "--read-only",
                "--read-only-tmpfs=false", "--security-opt=proc-opts=ro,nosuid,nodev,noexec",
                "--network=none", "--ipc=private", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--userns=keep-id", "-i",
                "--name", name, "--label", "org.forge.checkpoint2=" + nonce]
        for target in ("/tmp", "/var/tmp", "/run", "/dev/shm"):
            argv += ["--tmpfs", target + ":rw,nosuid,nodev,mode=1777"]
        argv += ["--volume", f"{ROOT}:/source:ro", "--volume", f"{sys.prefix}:/venv:ro",
                 "--workdir", "/tmp", "--env", "HOME=/tmp/home", "--env", "TMPDIR=/tmp",
                 "--env", "XDG_CACHE_HOME=/tmp/cache", "--env", "PYTHONPYCACHEPREFIX=/tmp/pycache"]
        if shared_volume:
            argv += ["--volume", f"{shared}:/shared:rw"]
        config = dict(write_canaries=True, phase=phase, tokens=tokens or {}, marker=marker,
                      read_only_files=dict(source="/source/benchmarks/genesis_lite/v0_3/isolation.py", venv="/venv/pyvenv.cfg"),
                      network_targets=dict(host_listener=server.getsockname(), external=("192.0.2.1", 9)))
        argv += [image_ref, "python3", "-", json.dumps(config)]
        record = dict(argv=argv, config=config)
        transcripts.append(record)
        cid = None
        try:
            made = subprocess.run(argv, text=True, capture_output=True, timeout=30)
            record["create"] = vars(made)
            if made.returncode and image_ref != IMAGE:
                return record, None  # Deliberately absent-image control only.
            made.check_returncode()
            cid = made.stdout.strip(); record["cid"] = cid
            inspection = subprocess.run(["podman", "inspect", cid], text=True, capture_output=True, timeout=10)
            record["inspect_command"] = vars(inspection)
            inspection.check_returncode()
            record["inspect"] = json.loads(inspection.stdout)
            done = subprocess.run(["podman", "start", "--attach", "--interactive", cid],
                                  input=PROBE.read_text(), text=True, capture_output=True, timeout=30)
            record["start"] = vars(done)
            done.check_returncode()
            report = json.loads(done.stdout); record["report"] = report
            actual = record["inspect"][0]
            assert actual["Id"] == cid and report["machine"] == cid[:12]
            assert actual["ImageDigest"] == image["Digest"]
            assert actual["Image"] == image["Id"].removeprefix("sha256:")
            restart = subprocess.run(["podman", "start", cid], capture_output=True, text=True, timeout=10)
            record["restart"] = vars(restart)
            return record, report
        except BaseException as exc:
            record["error"] = repr(exc)
            if isinstance(exc, subprocess.TimeoutExpired):
                def decoded(value):
                    return value.decode(errors="replace") if isinstance(value, bytes) else value
                record["timeout"] = dict(argv=exc.cmd, timeout=exc.timeout,
                                         stdout=decoded(exc.stdout), stderr=decoded(exc.stderr))
            raise
        finally:
            cleanup_owned(name, nonce, record)

    try:
        yield run, transcripts, metadata
    finally:
        server.close()
        destination = Path(os.environ["FORGE_CHECKPOINT_EVIDENCE"])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "runtime.json").write_bytes(
            (json.dumps(dict(metadata=metadata, transcripts=transcripts), indent=2, sort_keys=True)+"\n").encode())


def tokens(report):
    return {r["target"]:r["observation"]["token"] for r in report["mounts"] if "observation" in r}


@pytest.fixture(scope="module")
def observations(rig):
    run, _, _ = rig
    a = run()
    b = run("B", tokens(a[1]))
    c = run("B", tokens(a[1]))
    shared_a = run(shared_volume=True)
    shared_b = run("B", tokens(shared_a[1]), shared_volume=True)
    return [a, b, c, shared_a, shared_b]


def test_real_kernel_security_controls(observations):
    for record, report in observations:
        assert report["interfaces"] == ["lo"]
        assert all(v != "REACHED" for v in report["network"].values())
        assert all(int(report["status"][key].strip(),16)==0 for key in ("CapInh","CapPrm","CapEff","CapBnd","CapAmb"))
        assert report["status"]["NoNewPrivs"].strip()=="1"
        assert report["writes"]=={"source":"OSError","venv":"OSError"}
        assert record["restart"]["returncode"] != 0
        assert record["inspect"][0]["HostConfig"]["IpcMode"] == "private"
        assert record["cleanup"]["returncode"] == 0


def test_fresh_cards_paths_and_inventory(observations):
    assert len({r["cid"] for r,_ in observations}) == 5
    for record, report in observations:
        rows=report["mounts"]
        assert len({r["id"] for r in rows})==len(rows)==len(report["mountinfo"].splitlines())
        assert report["cwd"]=="/tmp"
        assert all(v.startswith("/tmp") for v in report["environment"].values())
        for mount in record["inspect"][0]["Mounts"]:
            candidates=[r for r in rows if r["target"]==mount["Destination"]]
            # Multiple stacked targets must never silently choose the first.
            assert len(candidates)==1, candidates
            assert ("rw" in candidates[0]["options"])==mount["RW"]
            assert mount["Propagation"]=="rprivate"


def test_explicit_per_mount_a_write_b_absence_and_shared_control(observations):
    a=observations[0][1]
    eligible=[r for r in a["mounts"] if "observation" in r]
    assert {r["target"] for r in eligible}=={"/tmp","/var/tmp","/run","/dev/shm"}
    assert len({r["observation"]["token"] for r in eligible})==len(eligible)
    for row in eligible:
        obs=row["observation"]
        assert obs["read"]=="READ_ABSENT" and obs["write"]=="WRITE_OK"
        assert obs["readback"]==obs["token"] and len(obs["token"])==64
        assert obs["actual_mount"]==obs["write_mount"]==obs["readback_mount"]==row["id"]
        for _, report in observations[1:3]:
            candidates=[r for r in report["mounts"] if r["target"]==row["target"]]
            assert len(candidates)==1
            other=candidates[0]; seen=other["observation"]
            assert seen["path"]==obs["path"] and seen["token"]==obs["token"]
            assert seen["read"]=="READ_ABSENT" and seen["actual_mount"]==other["id"]
    sa=[r for r in observations[3][1]["mounts"] if r["target"]=="/shared"][0]
    sb=[r for r in observations[4][1]["mounts"] if r["target"]=="/shared"][0]
    assert sa["observation"]["write"]=="WRITE_OK"
    assert sb["observation"]["read"]=="READ_OK"
    assert sb["observation"]["seen"]==sa["observation"]["token"]
    assert sb["observation"]["read_mount"]==sb["id"]
    assert sa["observation"]["path"]==sb["observation"]["path"]
    assert observations[3][0]["cid"] != observations[4][0]["cid"]


def _legacy_verdict(report):
    # Fabricated REFUSED rationale + real detail: legacy evidence-enforcement
    # regression, NOT a malicious-card exploit or production container launch.
    return attacks.verify_deployment(lambda spec:[spec.rsplit(":",1)[1]+":REFUSED:"+json.dumps(report)], scan_findings=[])


def test_legacy_interface_does_not_accept_unprobeable_detail(observations):
    report=observations[0][1]
    blockers=[r for r in report["mounts"] if r["canary"]=="UNPROBEABLE"]
    assert len(blockers)==8
    assert _legacy_verdict(report)["verified"] is False, blockers


def test_legacy_interface_does_not_accept_shared_detail(observations):
    assert _legacy_verdict(observations[4][1])["verified"] is False


def test_absent_digest_refused_not_valid_image_substitution(rig):
    record, report=rig[0](image_ref="localhost/forge-card@sha256:"+"0"*64)
    assert report is None and record["create"]["returncode"] != 0
    assert "image" in record["create"]["stderr"].lower()


def test_current_launcher_binds_image(rig):
    launcher=isolation.NamespaceLauncher((str(ROOT),sys.prefix))
    assert launcher.describe().get("image_digest")==rig[2]["image"].split("@")[1]


def test_create_timeout_preserves_output_and_cleans_only_owned_identity(rig, monkeypatch):
    calls = []
    owner = {}
    def fake(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "create":
            owner["name"] = argv[argv.index("--name")+1]
            owner["nonce"] = argv[argv.index("--label")+1].split("=",1)[1]
            raise subprocess.TimeoutExpired(argv, 30, output=b"partial stdout", stderr=b"partial stderr")
        if argv[1] == "inspect":
            assert argv[2] == owner["name"]
            return subprocess.CompletedProcess(argv, 0, json.dumps([{
                "Id":"owned-id", "Config":{"Labels":{"org.forge.checkpoint2":owner["nonce"]}}}]), "")
        assert argv == ["podman", "rm", "--force", "--ignore", "owned-id"]
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(subprocess.TimeoutExpired):
        rig[0]()
    record = rig[1][-1]
    assert record["timeout"]["stdout"] == "partial stdout"
    assert record["timeout"]["stderr"] == "partial stderr"
    assert record["cleanup"]["returncode"] == 0 and len(calls) == 3


def test_cleanup_refuses_unowned_identity(monkeypatch):
    calls = []
    def fake(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps([{
            "Id":"not-owned", "Config":{"Labels":{"org.forge.checkpoint2":"someone-else"}}}]), "")
    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(RuntimeError, match="OWNERSHIP_MISMATCH"):
        cleanup_owned("claimed-name", "our-nonce", {})
    assert len(calls) == 1
