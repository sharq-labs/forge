"""Genesis-lite v0.3: the OD-20 deployment, owner decision D5-A1b (2026-10-21): rootless Podman per-card isolation.

History. D5 was decided on 2026-10-20 as option A1: each card under ``unshare`` in fresh namespaces, operator state
masked by private tmpfs mounts and capabilities dropped with ``setpriv``. The owner superseded A1 for the formal
deployment by A1b on 2026-10-21, because the fifth review showed that the hand-built namespace probe had not proven
cross-card state isolation outside ``/tmp`` (N-1). A1b is a bounded refinement of the same route, not a weakening:
Podman provides the rootless Linux namespace boundary, and the scientific deployment contract is now

* a brand-new container for every card (``podman run --rm``, a fresh name and label each time), never reused;
* a read-only root filesystem (``--read-only``, ``/dev`` a read-only tmpfs) and read-only binds of exactly the FORGE
  source tree and the Python environment, at their own paths (the proposer imports this tree);
* ``--network=none``, every capability dropped, no-new-privileges, a rootless user namespace (``--userns=keep-id``)
  and private IPC;
* private writable mounts for the card (:data:`PRIVATE_TMPFS`, fresh tmpfs) and nothing else writable;
* a complete writable-mount inventory, Card-A/Card-B canary isolation, a deliberately shared-volume positive control and
  deployment verification before admission (:func:`collect_container_evidence`, validated by
  :func:`.container_evidence.validate_container_evidence`; :func:`.formal.deployment_problems` runs it before every
  formal admission).

The owner decided on 2026-10-21 that no device-node exemption applies: rootless Podman bind-mounts six host character
devices (``/dev/null``, ``zero``, ``full``, ``random``, ``urandom``, ``tty``) read-write into every container, and
these stay blocking. D5 stays NOT_PROVEN until complete evidence passes and is pinned.

Residual, disclosed: the containers share the host kernel (and on WSL the utility VM); the tree and environment are
readable (they must hold no secret; ``formal.main`` refuses operator files there); the certified escrow stays in the
operator process.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import posixpath
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping, Sequence

from .container_evidence import (DEV_READ_ONLY, SCHEMA as CONTAINER_SCHEMA, TMPFS_OPTIONS, parse_mountinfo,
                                 validate_container_evidence)

__all__ = ["DeploymentUnavailable", "NamespaceLauncher", "available", "collect_container_evidence",
           "expected_evidence", "formal_launcher", "kept_paths", "operator_path_problems",
           "validate_container_evidence", "verify"]

DECISION = "D5-A1b"
DEPLOYMENT = "rootless_podman_per_card"
EVIDENCE_SCHEMA = "forge.genesis_lite.v0_3/deployment_evidence/3"
HERE = pathlib.Path(__file__).resolve().parent
PROBE = HERE / "container_probe.py"
CONTAINERFILE = HERE / "container" / "Containerfile"
#: the card image, built on the formal machine from :data:`CONTAINERFILE` and pinned by digest and id
IMAGE_REPOSITORY = "localhost/forge-card"
IMAGE_DIGEST = "sha256:89847920916e46363fe52f7cecc3a2b937d34d6b355dd3e8cc14527fe65a8261"
IMAGE_ID = "2d2651e4d002c518bb669cb044209897ff02e33318a4b92ac185cf23be33f532"
PODMAN_VERSION = "4.9.3"
PRIVATE_TMPFS = ("/tmp", "/var/tmp", "/run", "/dev/shm")
WORKDIR = "/tmp"
CARD_PATHS = {"HOME": "/tmp/home", "TMPDIR": "/tmp", "XDG_CACHE_HOME": "/tmp/cache", "PYTHONPYCACHEPREFIX": "/tmp/pycache"}
CARD_LABEL = "org.forge.genesis_lite.card"
#: every formal card: the contract options (:data:`.container_evidence.REQUIRED_FLAGS`)
FINAL_FLAGS = ("--pull=never", "--rm", "--read-only", "--read-only-tmpfs=false",
               "--security-opt=proc-opts=ro,nosuid,nodev,noexec", "--ipc=private", "--network=none",
               "--cap-drop=ALL", "--security-opt=no-new-privileges", "--userns=keep-id")
#: the verification's power control ONLY (``drop_caps=False``): root of the user namespace with CAP_SYS_ADMIN, so the
#: unmask / remount probes can show they work; a formal card never uses it
ESCAPABLE_FLAGS = ("--pull=never", "--rm", "--read-only", "--read-only-tmpfs=false",
                   "--security-opt=proc-opts=ro,nosuid,nodev,noexec", "--ipc=private", "--network=none",
                   "--userns=keep-id", "--user=0", "--cap-add=SYS_ADMIN")
MARKER = "gl-n1-canary"
#: a TEST-NET-1 address (RFC 5737): never routed, so a card's connection attempt cannot leave the machine
EXTERNAL_TARGET = ("192.0.2.1", 9)
CONTROL_FSTYPES = ("tmpfs", "ext4", "xfs", "btrfs", "overlay")


class DeploymentUnavailable(RuntimeError):
    """The D5 deployment cannot run here (not Linux, or no rootless ``podman``)."""


def available() -> bool:
    return sys.platform.startswith("linux") and shutil.which("podman") is not None


def _kept_problem(path: str) -> str | None:
    real = posixpath.realpath(path)                      # validated AFTER resolution: '/tmp/..' is '/', refused
    if not posixpath.isabs(real) or real == "/" or any(ch.isspace() or ch in ":," for ch in real):
        return f"{path!r} resolves to {real!r}: not an absolute path below / free of whitespace, ':' and ','"
    return None


def _podman() -> str:
    return shutil.which("podman") or "podman"


class NamespaceLauncher:
    """Wraps one proposer command so it runs in a brand-new D5-A1b card container. ``keep``: absolute directories bound
    read-only at their own paths (the FORGE tree, the Python environment). ``drop_caps=False`` exists ONLY so that
    :func:`verify` can show the unmask / remount probes have power; a formal card never uses it."""

    def __init__(self, keep: Sequence[str], *, drop_caps: bool = True) -> None:  # noqa: D107
        if not available():
            raise DeploymentUnavailable("the D5 deployment (D5-A1b) needs Linux with rootless podman")
        bad = [p for p in (_kept_problem(k) for k in keep) if p]
        if bad:
            raise DeploymentUnavailable(f"kept paths must be absolute, below / and free of whitespace, ':' and ',': "
                                        f"{bad}")
        self.keep = tuple(dict.fromkeys(posixpath.realpath(k) for k in keep))      # Linux paths, always
        self.drop_caps = drop_caps

    def argv(self, inner: Sequence[str], card_dir: str, *, name: str | None = None,
             env: Mapping[str, str] | None = None, extra_volumes: Sequence[str] = ()) -> list[str]:
        """``podman run`` for ONE card. ``card_dir`` is the operator's directory for the card; inside the container
        the card works in its private ``/tmp``. ``env`` may only carry PYTHONDONTWRITEBYTECODE and FORGE_ATTACK_*
        (deployment verification); ``extra_volumes`` exists for the shared-volume positive control only."""
        name = name or new_card_name()
        out = [_podman(), "run", "-i", *(FINAL_FLAGS if self.drop_caps else ESCAPABLE_FLAGS), "--log-driver=none",
               "--mount", DEV_READ_ONLY]
        for target in PRIVATE_TMPFS:
            out += ["--tmpfs", f"{target}:{TMPFS_OPTIONS}"]
        for path in self.keep:
            out += ["--volume", f"{path}:{path}:ro"]
        for volume in extra_volumes:
            out += ["--volume", volume]
        out += ["--workdir", WORKDIR]
        for key, value in CARD_PATHS.items():
            out += ["--env", f"{key}={value}"]
        for key, value in sorted((env or {}).items()):
            if key != "PYTHONDONTWRITEBYTECODE" and not key.startswith("FORGE_ATTACK_"):
                raise ValueError(f"only PYTHONDONTWRITEBYTECODE and FORGE_ATTACK_* reach a card container, not {key}")
            out += ["--env", f"{key}={value}"]
        out += ["--name", name, "--label", f"{CARD_LABEL}={name}", f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}", *inner]
        return out

    @staticmethod
    def client_env() -> dict[str, str]:
        """What the rootless podman CLIENT needs to find its storage and runtime directory (never passed into the
        container, whose environment is only the ``--env`` entries of :meth:`argv`)."""
        return {k: os.environ[k] for k in ("HOME", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "USER",
                                           "LOGNAME", "DBUS_SESSION_BUS_ADDRESS") if k in os.environ}

    def remove(self, name: str) -> None:
        """Remove the card's container if it still exists (the client may have died before ``--rm`` ran); only a
        container carrying this launcher's label for ``name`` is ever removed."""
        seen = subprocess.run([_podman(), "container", "inspect", "--format",
                               "{{index .Config.Labels \"" + CARD_LABEL + "\"}}", name],
                              capture_output=True, text=True, timeout=30)
        if seen.returncode == 0 and seen.stdout.strip() == name:
            subprocess.run([_podman(), "rm", "--force", "--time", "0", name], capture_output=True, timeout=60)

    def describe(self) -> dict[str, Any]:
        return {"decision": DECISION, "deployment": DEPLOYMENT, "image": f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}",
                "image_id": IMAGE_ID, "podman_version": PODMAN_VERSION,
                "flags": list(FINAL_FLAGS if self.drop_caps else ESCAPABLE_FLAGS), "dev": DEV_READ_ONLY,
                "private_tmpfs": [f"{t}:{TMPFS_OPTIONS}" for t in PRIVATE_TMPFS], "kept_read_only": list(self.keep),
                "card_paths": dict(CARD_PATHS), "workdir": WORKDIR, "drop_caps": self.drop_caps}


def new_card_name() -> str:
    return f"gl-card-{secrets.token_hex(12)}"


def kept_paths() -> tuple[str, str]:
    """The directories every formal card keeps readable: this tree and this interpreter's environment."""
    return (str(pathlib.Path(__file__).resolve().parents[3]), sys.prefix)


def formal_launcher() -> NamespaceLauncher:
    """The launcher every FORMAL proposer card must use (capabilities dropped)."""
    return NamespaceLauncher(kept_paths())


def operator_path_problems(paths: dict[str, pathlib.Path]) -> list[str]:
    """Review I-4: an operator file (run directory, registry, evaluator inbox) must lie outside every kept tree, the
    only host paths a card container can see."""
    problems = []
    kept = [posixpath.realpath(k) for k in kept_paths()]
    for name, path in paths.items():
        real = posixpath.realpath(str(path))
        if any(real == k or real.startswith(k + "/") for k in kept):
            problems.append(f"the {name} lies inside a tree every proposer can read ({real})")
    return problems


# ---- container evidence (N-1) ----------------------------------------------------------------------------------------
def _sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(argv: Sequence[str], timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)


def _git_head(tree: str) -> str:
    done = _run(["git", "-C", tree, "rev-parse", "HEAD"])
    return done.stdout.strip() if done.returncode == 0 else "UNKNOWN"


def expected_evidence(launcher: NamespaceLauncher) -> dict[str, Any]:
    """What the container evidence must show for ``launcher``: the pinned image, Podman version and code, and this
    tree's revision."""
    source, venv = launcher.keep[0], launcher.keep[-1]
    return {"source_sha": _git_head(source), "image_digest": IMAGE_DIGEST, "image_id": IMAGE_ID,
            "podman_version": PODMAN_VERSION, "containerfile_sha256": _sha_file(CONTAINERFILE),
            "launcher_sha256": _sha_file(pathlib.Path(__file__)), "probe_sha256": _sha_file(PROBE),
            "writable_targets": list(PRIVATE_TMPFS), "source_host": source, "venv_host": venv,
            "source_path": source, "venv_path": venv, "rootless": True}


def measured_provenance(launcher: NamespaceLauncher) -> dict[str, Any]:
    """The same fields, measured on this machine now (podman, the local image, the files on disk)."""
    source, venv = launcher.keep[0], launcher.keep[-1]
    image = _run([_podman(), "image", "inspect", "--format", "{{.Digest}} {{.Id}}", f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"])
    digest, _, image_id = image.stdout.strip().partition(" ") if image.returncode == 0 else ("MISSING", "", "MISSING")
    version = _run([_podman(), "version", "--format", "{{.Client.Version}}"]).stdout.strip()
    rootless = _run([_podman(), "info", "--format", "{{.Host.Security.Rootless}}"]).stdout.strip() == "true"
    return {"source_sha": _git_head(source), "image_digest": digest, "image_id": image_id, "podman_version": version,
            "containerfile_sha256": _sha_file(CONTAINERFILE), "launcher_sha256": _sha_file(pathlib.Path(__file__)),
            "probe_sha256": _sha_file(PROBE), "writable_targets": list(PRIVATE_TMPFS), "source_host": source,
            "venv_host": venv, "source_path": source, "venv_path": venv, "rootless": rootless}


def _backing(row: Mapping[str, Any], keep: Sequence[str]) -> str:
    """Where a mount's data lives, judged by the operator: a fresh container tmpfs / the image overlay ("container"),
    a host filesystem or host tmpfs bind ("host"), Windows ("windows"), or a kernel pseudo-filesystem ("kernel")."""
    if row["fstype"] in ("9p", "drvfs", "v9fs") or re.match(r"^[A-Za-z]:", row["source"]):
        return "windows"
    if row["fstype"] in ("proc", "sysfs", "cgroup", "cgroup2", "mqueue", "devpts"):
        return "kernel"
    if row["target"] in keep or row["fstype"] == "devtmpfs":
        return "host"
    if (row["fstype"] == "tmpfs" and row["root"] == "/") or (row["fstype"] == "overlay" and row["target"] == "/"):
        return "container"
    return "host"


def _primary_address() -> str:
    """The host's own non-loopback IPv4 address (a UDP connect sends no packet)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(EXTERNAL_TARGET)
        return s.getsockname()[0]


def _listener() -> tuple[socket.socket, tuple[str, int]]:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("0.0.0.0", 0))
    srv.listen(16)

    def accept() -> None:
        while True:
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    return srv, (_primary_address(), srv.getsockname()[1])


def _observe(launcher: NamespaceLauncher, config: Mapping[str, Any], *,
             extra_volumes: Sequence[str] = (), timeout: float = 120.0) -> dict[str, Any]:
    """Run the probe as one card in a fresh container: its own observation, the operator's host-side view of the same
    container while it lives, then removal and a restart attempt."""
    name = new_card_name()
    argv = launcher.argv([sys.executable, "-I", str(PROBE)], WORKDIR, name=name, extra_volumes=extra_volumes)
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps(dict(config)) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError(f"the card probe gave no observation: {proc.stderr.read()[:400] if proc.stderr else ''}")
        observation = json.loads(line)
        inspected = json.loads(_run([_podman(), "container", "inspect", name]).stdout)[0]
        pid = inspected["State"]["Pid"]
        runtime_raw = pathlib.Path(f"/proc/{pid}/mountinfo").read_text()
        proc.stdin.write("exit\n")
        proc.stdin.close()
        proc.wait(timeout=60)
        exists = _run([_podman(), "container", "exists", name])        # --rm, before any cleanup of ours
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
        launcher.remove(name)
    restart = _run([_podman(), "start", inspected["Id"]])
    runtime = [dict(row, private=not row["optional"], backing=_backing(row, launcher.keep))
               for row in parse_mountinfo(runtime_raw)]
    return {"name": name, "id": inspected["Id"], "argv": argv, "observation": observation,
            "runtime_mountinfo": runtime_raw, "runtime_mounts": runtime,
            "actual_image_digest": inspected.get("ImageDigest"), "actual_image_id": inspected.get("Image"),
            "ipc": inspected.get("HostConfig", {}).get("IpcMode"), "removed": exists.returncode == 1,
            "restart": {"attempted": True, "refused": restart.returncode != 0, "exit_code": restart.returncode},
            "exit_code": proc.returncode}


def collect_container_evidence(launcher: NamespaceLauncher | None = None) -> dict[str, Any]:
    """N-1 evidence on this machine: cards A, B and C in three fresh containers (A plants a token in every private
    mount, B and C look for it), then the two positive controls. Plants nothing outside the containers except the
    shared control directory, which is removed."""
    launcher = launcher or formal_launcher()
    source, venv = launcher.keep[0], launcher.keep[-1]
    provenance = measured_provenance(launcher)
    host_devices = host_pseudo_devices()
    marker = f"{MARKER}-{secrets.token_hex(6)}"
    server, address = _listener()
    try:
        common = {"marker": marker, "targets": list(PRIVATE_TMPFS),
                  "read_only_files": {"source": str(PROBE), "venv": _venv_file(venv)},
                  "network_targets": {"host_listener": list(address), "external": list(EXTERNAL_TARGET)}}
        cards, tokens = [], {}
        for phase in ("A", "B", "C"):
            seen = _observe(launcher, {**common, "phase": phase, "tokens": tokens})
            obs = seen["observation"]
            if phase == "A":
                tokens = {c["target"]: c.get("token") for c in obs["canaries"]}
            cards.append({"phase": phase, "id": seen["id"], "provenance": dict(provenance), "mounts": obs["mounts"],
                          "mountinfo": obs["mountinfo"], "runtime_mounts": seen["runtime_mounts"],
                          "argv": seen["argv"], "paths": obs["paths"], "status": obs["status"],
                          "actual_image_digest": seen["actual_image_digest"], "actual_image_id": seen["actual_image_id"],
                          "ipc": seen["ipc"], "network": obs["network"], "writes": obs["writes"],
                          "canaries": obs["canaries"], "restart": seen["restart"], "removed": seen["removed"],
                          "pid_namespace": obs.get("pid_namespace"), "host_devices": dict(host_devices),
                          "name": seen["name"], "containerenv": obs.get("containerenv"), "uid": obs.get("uid"),
                          "runtime_mountinfo": seen["runtime_mountinfo"], "exit_code": seen["exit_code"]})
        with socket.create_connection(address, timeout=3):
            host_listener = "REACHED"
    finally:
        server.close()
    shared_dir = tempfile.mkdtemp(prefix="gl-n1-shared-")
    try:
        volume = [f"{shared_dir}:/shared:rw"]
        control = {"marker": marker, "targets": ["/shared"], "write_fstypes": list(CONTROL_FSTYPES)}
        a = _observe(launcher, {**control, "phase": "A"}, extra_volumes=volume)
        a_canary = a["observation"]["canaries"][0]
        b = _observe(launcher, {**control, "phase": "B", "tokens": {"/shared": a_canary.get("token")}},
                     extra_volumes=volume)
        b_canary = b["observation"]["canaries"][0]
    finally:
        shutil.rmtree(shared_dir, ignore_errors=True)
    hostproc = _observe(launcher, {"pid_probe_path": "/hostproc"}, extra_volumes=["/proc:/hostproc:ro"])
    shared = {"a_write": a_canary.get("write"), "a_token": a_canary.get("token"), "b_read": b_canary.get("read"),
              "b_seen": b_canary.get("seen"), "a_mount": a_canary.get("expected_mount"),
              "b_mount": b_canary.get("expected_mount"), "a_actual": a_canary.get("actual_mount"),
              "b_actual": b_canary.get("actual_mount"), "a_id": a["id"], "b_id": b["id"],
              "a_path": a_canary.get("path"), "b_path": b_canary.get("path"),
              "a_image_digest": a["actual_image_digest"], "b_image_digest": b["actual_image_digest"]}
    return {"schema": CONTAINER_SCHEMA, "cards": cards,
            "positive_controls": {"host_listener": host_listener, "shared_canary": shared,
                                  "host_procfs": {**hostproc["observation"]["pid_namespace"], "id": hostproc["id"]}}}


def host_pseudo_devices() -> dict[str, str]:
    """The operator's own procfs and sysfs devices and PID namespace: a card's /proc and /sys must be on other
    devices, and the card's PID namespace must be another one (MINOR-A)."""
    rows = parse_mountinfo(pathlib.Path("/proc/self/mountinfo").read_text())
    device = {t: next((r["device"] for r in rows if r["target"] == t and r["fstype"] == f), "UNKNOWN")
              for t, f in (("/proc", "proc"), ("/sys", "sysfs"))}
    return {"proc": device["/proc"], "sys": device["/sys"], "pid_ns": os.readlink("/proc/self/ns/pid")}


def _venv_file(venv: str) -> str:
    """A regular file of the kept environment (the write probe opens it; nothing is written)."""
    cfg = pathlib.Path(venv) / "pyvenv.cfg"
    return str(cfg if cfg.is_file() else next(p for p in pathlib.Path(venv).rglob("*.py") if p.is_file()))


def verify_containers(launcher: NamespaceLauncher | None = None) -> dict[str, Any]:
    """Collect the container evidence and validate it against the expected deployment (pre-admission check)."""
    launcher = launcher or formal_launcher()
    report = collect_container_evidence(launcher)
    expected = expected_evidence(launcher)
    return {"report": report, "expected": expected, "validation": validate_container_evidence(report, expected=expected)}


# ---- verification ----------------------------------------------------------------------------------------------------
def _provenance() -> dict[str, Any]:
    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "UNKNOWN"

    code = {n: _sha_file(HERE / n) for n in ("isolation.py", "container_evidence.py", "container_probe.py",
                                             "deployment_attacks.py", "harness.py", "secret_scan.py")}
    code["container/Containerfile"] = _sha_file(CONTAINERFILE)
    podman = _run([_podman(), "--version"]).stdout.strip() if available() else "UNAVAILABLE"
    return {"head": git("rev-parse", "HEAD"), "tree_clean": git("status", "--porcelain") == "", "code_sha256": code,
            "python": sys.version.split()[0], "platform": platform.platform(), "kernel": platform.release(),
            "podman": podman, "wsl_kernel": "microsoft" in platform.release().lower(),
            "wsl_interop_registered": pathlib.Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()}


def verify(cards: int = 2) -> dict[str, Any]:
    """The D5-A1b deployment verification: the container evidence (N-1) plus the twelve-channel attack suite run three
    times through the v0.3 per-card host, with canary secrets the operator controls: WITHOUT containers, in containers
    WITH capabilities (the power control) and in the D5-A1b deployment. Verified only when the container evidence
    PASSES, every channel is REFUSED in the deployment, and each channel is REACHED by the same probe in at least one
    of the two control configurations (the probes have power)."""
    from . import deployment_attacks as attacks  # noqa: PLC0415
    from . import secret_scan  # noqa: PLC0415
    from .harness import CardProposerHost  # noqa: PLC0415

    final, escapable = formal_launcher(), NamespaceLauncher(kept_paths(), drop_caps=False)
    started = time.time()
    containers = verify_containers(final)
    canary = pathlib.Path(tempfile.mkdtemp(prefix="gl-d5-canary-"))
    root = secrets.token_bytes(32)
    (canary / "root.bin").write_bytes(root)
    (canary / "run.log").write_bytes(b'{"root": "' + root.hex().encode() + b'"}\n')
    (canary / "registry.jsonl").write_bytes(b'{"nonce": "' + secrets.token_hex(16).encode() + b'"}\n')
    srv, address = _listener()
    common = {"FORGE_ATTACK_NETWORK_TARGET": f"{address[0]}:{address[1]}",
              "FORGE_ATTACK_ROOT_FILES": str(canary / "root.bin"),
              "FORGE_ATTACK_RUN_LOGS": os.pathsep.join([str(canary / "run.log"), str(canary / "registry.jsonl")]),
              "FORGE_ATTACK_SCAN_DIGESTS": ",".join(secret_scan.digests_for([root]))}
    plain_env = {**common, "FORGE_ATTACK_SCAN_ROOTS": str(canary)}      # the host: the canary directory itself
    box_env = {**common, "FORGE_ATTACK_SCAN_ROOTS": "/"}                 # a container: everything it can see
    try:
        plain = attacks.verify_deployment(attacks.deployment_runner(plain_env, cards), scan_findings=[])
        caps = attacks.verify_deployment(
            attacks.deployment_runner(box_env, cards, host_factory=lambda **kw: CardProposerHost(launcher=escapable, **kw)),
            scan_findings=[])
        isolated = attacks.verify_deployment(
            attacks.deployment_runner(box_env, cards, host_factory=lambda **kw: CardProposerHost(launcher=final, **kw)),
            scan_findings=[], container_validation=containers["validation"])
    finally:
        srv.close()
        shutil.rmtree(canary, ignore_errors=True)
    power = {c: attacks.REACHED in (plain["verdicts"].get(c), caps["verdicts"].get(c)) for c in attacks.CHANNELS}
    return {"schema": EVIDENCE_SCHEMA, "status": "DEPLOYMENT_VERIFICATION", "decision": DECISION,
            "deployment": final.describe(), "power_control": escapable.describe(), "provenance": _provenance(),
            "cards_per_channel": cards, "wall_seconds": round(time.time() - started, 1),
            "container_evidence": containers["report"], "container_expected": containers["expected"],
            "container_validation": containers["validation"],
            "without_containers": plain["verdicts"], "containers_with_capabilities": caps["verdicts"],
            "with_containers": isolated["verdicts"], "probe_power": power, "missing": isolated["missing"],
            "verified": isolated["verified"] and all(power.values())}


def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 D5-A1b deployment verification (development tier)")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--cards", type=int, default=2)
    parser.add_argument("--containers-only", action="store_true", help="only the N-1 container evidence (fast)")
    args = parser.parse_args(argv)
    doc = verify_containers() if args.containers_only else verify(args.cards)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(doc, indent=1, sort_keys=True) + "\n").encode())
    if args.containers_only:
        print(json.dumps(doc["validation"], sort_keys=True))
        return 0 if doc["validation"]["status"] == "PASS" else 1
    print(json.dumps({k: doc[k] for k in ("verified", "with_containers", "probe_power")}
                     | {"containers": doc["container_validation"]["status"]}, sort_keys=True))
    return 0 if doc["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
