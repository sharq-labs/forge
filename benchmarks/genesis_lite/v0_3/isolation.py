"""Genesis-lite v0.3: the OD-20 deployment (owner D5, 2026-10-20: option A1, rootless Linux namespaces).

Every proposer card runs under ``unshare`` in fresh user, PID, mount, network, IPC and UTS namespaces:

* the proposer is PID 1 of its own PID namespace (the operator's processes, command line and memory are not visible),
  and every process it starts dies with it (``--kill-child`` and the PID namespace);
* the network namespace has only a loopback interface, and it is down (no outbound connection);
* :data:`MASKED` directories are covered by empty private tmpfs mounts (operator files, the root, run logs, the
  registry, other cards' state, ``/run`` with the WSL interop sockets, ``/dev/shm``); the benchmark tree and the Python
  environment are re-bound READ-ONLY at their own paths, so the proposer imports this tree and can write nothing back;
* the card's working and temporary directory is created inside the private ``/tmp``, so nothing survives the card.

No root and no install are needed (unprivileged user namespaces). The deployment counts as verified only by
:func:`verify` run on the formal machine: every attack channel REFUSED there, each channel REACHED by the same probe
without the namespaces (the probes have power), and the evidence pinned by digest in the preregistration.

Residual, disclosed: the proposer runs under the same Linux account outside its namespaces; files of the re-bound tree
and environment are readable (they must hold no secret); on WSL the namespaces share the host's utility VM.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import posixpath
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Sequence

DEPLOYMENT = "rootless_namespaces"
EVIDENCE_SCHEMA = "forge.genesis_lite.v0_3/deployment_evidence/1"
UNSHARE_FLAGS = ("--user", "--map-root-user", "--pid", "--fork", "--kill-child", "--mount", "--mount-proc", "--net",
                 "--ipc", "--uts")
MASKED = ("/mnt", "/home", "/root", "/tmp", "/var/tmp", "/run", "/opt", "/media", "/dev/shm")
STAGE = "/srv"
#: runs as root of the new user namespace; positional: card dir, number of kept paths, kept paths, masked paths
_SCRIPT = r"""
set -eu
card="$1"; n="$2"; shift 2
keep=""; i=0
mount --make-rprivate /
mount -t tmpfs -o mode=0755 gl-stage "$STAGE_DIR"
while [ "$i" -lt "$n" ]; do
  mkdir "$STAGE_DIR/k$i"; mount --bind "$1" "$STAGE_DIR/k$i"; keep="$keep $1"; shift; i=$((i+1))
done
while [ "$1" != "--" ]; do
  if [ -d "$1" ]; then mount -t tmpfs -o mode=0755 gl-mask "$1"; fi; shift
done
shift
i=0
for k in $keep; do
  mkdir -p "$k"; mount --bind "$STAGE_DIR/k$i" "$k"; mount -o remount,bind,ro "$k"; i=$((i+1))
done
umount -R "$STAGE_DIR"
mount -t tmpfs -o mode=0755 gl-mask "$STAGE_DIR"
mkdir -p "$card"; cd "$card"
exec "$@"
"""


class DeploymentUnavailable(RuntimeError):
    """The D5 deployment cannot run here (not Linux, no ``unshare``, or no unprivileged user namespaces)."""


def available() -> bool:
    return sys.platform.startswith("linux") and shutil.which("unshare") is not None


class NamespaceLauncher:
    """Wraps one proposer command so it runs in the D5 namespaces. ``keep``: absolute directories re-bound read-only
    at their own paths (the benchmark tree, the Python environment)."""

    def __init__(self, keep: Sequence[str]) -> None:  # noqa: D107
        if not available():
            raise DeploymentUnavailable("the D5 deployment needs Linux with unshare (unprivileged user namespaces)")
        bad = [k for k in keep if not posixpath.isabs(k) or " " in k or not any(k.startswith(m + "/") for m in MASKED)]
        if bad:
            raise DeploymentUnavailable(f"kept paths must be absolute, space-free and under a masked root: {bad}")
        self.keep = tuple(dict.fromkeys(posixpath.realpath(k) for k in keep))      # Linux paths, always

    def argv(self, inner: Sequence[str], card_dir: str) -> list[str]:
        return [shutil.which("unshare") or "unshare", *UNSHARE_FLAGS, "--", "/bin/sh", "-c",
                _SCRIPT.replace("$STAGE_DIR", STAGE), "gl-d5", card_dir, str(len(self.keep)), *self.keep, *MASKED,
                "--", *inner]

    def describe(self) -> dict[str, Any]:
        return {"deployment": DEPLOYMENT, "unshare_flags": list(UNSHARE_FLAGS), "masked": list(MASKED),
                "kept_read_only": list(self.keep), "script_sha256": hashlib.sha256(_SCRIPT.encode()).hexdigest()}


def formal_launcher() -> NamespaceLauncher:
    """The launcher every FORMAL proposer card must use: this tree and this interpreter's environment kept read-only."""
    root = pathlib.Path(__file__).resolve().parents[3]
    return NamespaceLauncher((str(root), sys.prefix))


# ---- verification ----------------------------------------------------------------------------------------------------
def _listener() -> tuple[socket.socket, str]:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)

    def accept() -> None:
        while True:
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    return srv, f"127.0.0.1:{srv.getsockname()[1]}"


def _provenance() -> dict[str, Any]:
    here = pathlib.Path(__file__).resolve().parent

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=here, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "UNKNOWN"

    code = {n: hashlib.sha256((here / n).read_bytes()).hexdigest()
            for n in ("isolation.py", "deployment_attacks.py", "harness.py", "secret_scan.py")}
    try:
        unshare = subprocess.run(["unshare", "--version"], capture_output=True, text=True).stdout.strip()
    except OSError:
        unshare = "UNKNOWN"
    return {"head": git("rev-parse", "HEAD"), "tree_clean": git("status", "--porcelain") == "", "code_sha256": code,
            "python": sys.version.split()[0], "platform": platform.platform(), "kernel": platform.release(),
            "unshare": unshare, "wsl": pathlib.Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()}


def verify(cards: int = 2) -> dict[str, Any]:
    """Run the attack suite twice through the v0.3 per-card host, with canary secrets the operator controls: once
    WITHOUT the namespaces (each probe must reach its channel: the probes have power) and once WITH them (each channel
    must be refused). Verified only when both hold for every channel."""
    from . import deployment_attacks as attacks  # noqa: PLC0415
    from . import secret_scan  # noqa: PLC0415
    from .harness import CardProposerHost  # noqa: PLC0415

    launcher = formal_launcher()
    canary = pathlib.Path(tempfile.mkdtemp(prefix="gl-d5-canary-"))
    root = secrets.token_bytes(32)
    (canary / "root.bin").write_bytes(root)
    (canary / "run.log").write_bytes(b'{"root": "' + root.hex().encode() + b'"}\n')
    (canary / "registry.jsonl").write_bytes(b'{"nonce": "' + secrets.token_hex(16).encode() + b'"}\n')
    server, target = _listener()
    env = {"FORGE_ATTACK_NETWORK_TARGET": target,
           "FORGE_ATTACK_ROOT_FILES": str(canary / "root.bin"),
           "FORGE_ATTACK_RUN_LOGS": os.pathsep.join([str(canary / "run.log"), str(canary / "registry.jsonl")]),
           "FORGE_ATTACK_SCAN_ROOTS": os.pathsep.join(["/tmp", "/var/tmp", "/dev/shm", "/run"]),
           "FORGE_ATTACK_SCAN_DIGESTS": ",".join(secret_scan.digests_for([root]))}
    try:
        started = time.time()
        plain = attacks.verify_deployment(attacks.deployment_runner(env, cards), scan_findings=[])
        isolated = attacks.verify_deployment(
            attacks.deployment_runner(env, cards, host_factory=lambda **kw: CardProposerHost(launcher=launcher, **kw)),
            scan_findings=[])
    finally:
        server.close()
        shutil.rmtree(canary, ignore_errors=True)
    power = {c: plain["verdicts"].get(c) == attacks.REACHED for c in attacks.CHANNELS}
    return {"schema": EVIDENCE_SCHEMA, "status": "DEPLOYMENT_VERIFICATION", "deployment": launcher.describe(),
            "provenance": _provenance(), "cards_per_channel": cards, "wall_seconds": round(time.time() - started, 1),
            "without_namespaces": plain["verdicts"], "with_namespaces": isolated["verdicts"],
            "probe_power": power, "missing": isolated["missing"],
            "verified": isolated["verified"] and all(power.values())}


def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 D5 deployment verification (development tier)")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--cards", type=int, default=2)
    args = parser.parse_args(argv)
    doc = verify(args.cards)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(doc, indent=1, sort_keys=True) + "\n").encode())
    print(json.dumps({k: doc[k] for k in ("verified", "with_namespaces", "probe_power")}, sort_keys=True))
    return 0 if doc["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
