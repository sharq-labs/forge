"""Genesis-lite v0.3: the OD-20 deployment (owner D5, 2026-10-20: option A1, rootless Linux namespaces).

Every proposer card runs under ``unshare`` in fresh user, PID, mount, network, IPC and UTS namespaces:

* the proposer is PID 1 of its own PID namespace (the operator's processes, command line and memory are not visible),
  and every process it starts dies with it (``--kill-child`` and the PID namespace);
* the network namespace has only a loopback interface, and it is down (no outbound connection);
* :data:`MASKED` directories are covered by empty private tmpfs mounts (operator files, the root, run logs, the
  registry, other cards' state, ``/run`` with the WSL interop sockets, ``/dev/shm``); the benchmark tree and the Python
  environment are re-bound READ-ONLY at their own paths, so the proposer imports this tree;
* the card's working and temporary directory is created inside the private ``/tmp``, so nothing survives the card;
* the proposer itself runs WITHOUT capabilities (``setpriv --inh-caps=-all --bounding-set=-all --no-new-privs``, as the
  certified ``engcore.blindfold.isolation`` does): as root of its own user namespace it could otherwise unmount the masks
  or remount the kept tree read-write (scientific review 2026-10-20, I-1). Without capabilities it can do neither, and a
  nested user namespace it might create inherits the masks LOCKED.

No root and no install are needed (unprivileged user namespaces). The deployment counts as verified only by
:func:`verify` run on the formal machine: every attack channel REFUSED there, and each channel REACHED by the same probe
either without the namespaces or in the namespaces WITH capabilities (the probes have power), the evidence pinned by
digest in the preregistration.

Residual, disclosed: the proposer runs under the same Linux account outside its namespaces; files of the re-bound tree
and environment, and unmasked system directories, are readable (they must hold no secret; ``formal.main`` refuses
operator files there); on WSL the namespaces share the host's utility VM.
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
EVIDENCE_SCHEMA = "forge.genesis_lite.v0_3/deployment_evidence/2"
UNSHARE_FLAGS = ("--user", "--map-root-user", "--pid", "--fork", "--kill-child", "--mount", "--mount-proc", "--net",
                 "--ipc", "--uts")
SETPRIV_FLAGS = ("--inh-caps=-all", "--bounding-set=-all", "--no-new-privs")
MASKED = ("/mnt", "/home", "/root", "/tmp", "/var/tmp", "/run", "/opt", "/media", "/dev/shm")
STAGE = "/srv"
#: runs as root of the new user namespace; positional: card dir, number of kept paths, kept paths, masked paths, "--",
#: the proposer command (already wrapped in setpriv). Kept paths travel through a private list file, never word-split.
_SCRIPT = r"""
set -eu
card="$1"; n="$2"; shift 2
mount --make-rprivate /
mount -t tmpfs -o mode=0700 gl-stage "$STAGE_DIR"
: > "$STAGE_DIR/list"
i=0
while [ "$i" -lt "$n" ]; do
  mkdir "$STAGE_DIR/k$i"; mount --bind "$1" "$STAGE_DIR/k$i"; printf '%s\n' "$1" >> "$STAGE_DIR/list"; shift; i=$((i+1))
done
while [ "$1" != "--" ]; do
  if [ -d "$1" ]; then mount -t tmpfs -o mode=0755 gl-mask "$1"; fi; shift
done
shift
i=0
while IFS= read -r k; do
  mkdir -p "$k"; mount --bind "$STAGE_DIR/k$i" "$k"; mount -o remount,bind,ro "$k"; i=$((i+1))
done < "$STAGE_DIR/list"
umount -R "$STAGE_DIR"
mount -t tmpfs -o mode=0755 gl-mask "$STAGE_DIR"
mkdir -p "$card"; cd "$card"
exec "$@"
"""


class DeploymentUnavailable(RuntimeError):
    """The D5 deployment cannot run here (not Linux, no ``unshare`` / ``setpriv``, or no unprivileged namespaces)."""


def available() -> bool:
    return (sys.platform.startswith("linux") and shutil.which("unshare") is not None
            and shutil.which("setpriv") is not None)


def _kept_problem(path: str) -> str | None:
    real = posixpath.realpath(path)                      # validated AFTER resolution: '/tmp/..' is '/', refused
    if not posixpath.isabs(real) or any(ch.isspace() for ch in real):
        return f"{path!r}: not an absolute, whitespace-free path"
    if not any(real.startswith(m + "/") for m in MASKED):
        return f"{path!r} resolves to {real!r}, not under a masked root"
    return None


class NamespaceLauncher:
    """Wraps one proposer command so it runs in the D5 namespaces. ``keep``: absolute directories re-bound read-only
    at their own paths (the benchmark tree, the Python environment). ``drop_caps=False`` exists ONLY so that
    :func:`verify` can show the unmask / remount probes have power; a formal card never uses it."""

    def __init__(self, keep: Sequence[str], *, drop_caps: bool = True) -> None:  # noqa: D107
        if not available():
            raise DeploymentUnavailable("the D5 deployment needs Linux with unshare and setpriv (unprivileged user "
                                        "namespaces)")
        bad = [p for p in (_kept_problem(k) for k in keep) if p]
        if bad:
            raise DeploymentUnavailable(f"kept paths must be absolute, whitespace-free and under a masked root: {bad}")
        self.keep = tuple(dict.fromkeys(posixpath.realpath(k) for k in keep))      # Linux paths, always
        self.drop_caps = drop_caps

    def argv(self, inner: Sequence[str], card_dir: str) -> list[str]:
        proposer = ([shutil.which("setpriv") or "setpriv", *SETPRIV_FLAGS, "--", *inner] if self.drop_caps
                    else list(inner))
        return [shutil.which("unshare") or "unshare", *UNSHARE_FLAGS, "--", "/bin/sh", "-c",
                _SCRIPT.replace("$STAGE_DIR", STAGE), "gl-d5", card_dir, str(len(self.keep)), *self.keep, *MASKED,
                "--", *proposer]

    def describe(self) -> dict[str, Any]:
        return {"deployment": DEPLOYMENT, "unshare_flags": list(UNSHARE_FLAGS), "masked": list(MASKED),
                "setpriv_flags": list(SETPRIV_FLAGS) if self.drop_caps else [], "kept_read_only": list(self.keep),
                "script_sha256": hashlib.sha256(_SCRIPT.encode()).hexdigest()}


def kept_paths() -> tuple[str, str]:
    """The directories every formal card keeps readable: this tree and this interpreter's environment."""
    return (str(pathlib.Path(__file__).resolve().parents[3]), sys.prefix)


def formal_launcher() -> NamespaceLauncher:
    """The launcher every FORMAL proposer card must use (capabilities dropped)."""
    return NamespaceLauncher(kept_paths())


def operator_path_problems(paths: dict[str, pathlib.Path]) -> list[str]:
    """Review I-4: an operator file (run directory, registry, evaluator inbox) must lie under a MASKED root and outside
    every kept tree, or a proposer could read it through the read-only re-bind or an unmasked directory."""
    problems = []
    kept = [posixpath.realpath(k) for k in kept_paths()]
    for name, path in paths.items():
        real = posixpath.realpath(str(path))
        if any(real == k or real.startswith(k + "/") for k in kept):
            problems.append(f"the {name} lies inside a tree every proposer can read ({real})")
        elif not any(real.startswith(m + "/") for m in MASKED):
            problems.append(f"the {name} lies outside every masked root ({real}); a proposer could read it")
    return problems


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
    versions = {}
    for tool in ("unshare", "setpriv"):
        try:
            versions[tool] = subprocess.run([tool, "--version"], capture_output=True, text=True).stdout.strip()
        except OSError:
            versions[tool] = "UNKNOWN"
    return {"head": git("rev-parse", "HEAD"), "tree_clean": git("status", "--porcelain") == "", "code_sha256": code,
            "python": sys.version.split()[0], "platform": platform.platform(), "kernel": platform.release(),
            "tools": versions, "wsl": pathlib.Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()}


def verify(cards: int = 2) -> dict[str, Any]:
    """Run the attack suite three times through the v0.3 per-card host, with canary secrets the operator controls:
    WITHOUT namespaces, IN the namespaces WITH capabilities (the escapable launcher the review found), and in the D5
    deployment (capabilities dropped). Verified only when every channel is REFUSED in the D5 deployment and REACHED by
    the same probe in at least one of the other two (the probes have power)."""
    from . import deployment_attacks as attacks  # noqa: PLC0415
    from . import secret_scan  # noqa: PLC0415
    from .harness import CardProposerHost  # noqa: PLC0415

    final, escapable = formal_launcher(), NamespaceLauncher(kept_paths(), drop_caps=False)
    canary = pathlib.Path(tempfile.mkdtemp(prefix="gl-d5-canary-"))
    root = secrets.token_bytes(32)
    (canary / "root.bin").write_bytes(root)
    (canary / "run.log").write_bytes(b'{"root": "' + root.hex().encode() + b'"}\n')
    (canary / "registry.jsonl").write_bytes(b'{"nonce": "' + secrets.token_hex(16).encode() + b'"}\n')
    server, target = _listener()
    common = {"FORGE_ATTACK_NETWORK_TARGET": target,
              "FORGE_ATTACK_ROOT_FILES": str(canary / "root.bin"),
              "FORGE_ATTACK_RUN_LOGS": os.pathsep.join([str(canary / "run.log"), str(canary / "registry.jsonl")]),
              "FORGE_ATTACK_SCAN_DIGESTS": ",".join(secret_scan.digests_for([root]))}
    plain_env = {**common, "FORGE_ATTACK_SCAN_ROOTS": str(canary)}      # the host: the canary directory itself
    ns_env = {**common, "FORGE_ATTACK_SCAN_ROOTS": "/"}                  # a namespace: everything it can see
    try:
        started = time.time()
        plain = attacks.verify_deployment(attacks.deployment_runner(plain_env, cards), scan_findings=[])
        caps = attacks.verify_deployment(
            attacks.deployment_runner(ns_env, cards, host_factory=lambda **kw: CardProposerHost(launcher=escapable, **kw)),
            scan_findings=[])
        isolated = attacks.verify_deployment(
            attacks.deployment_runner(ns_env, cards, host_factory=lambda **kw: CardProposerHost(launcher=final, **kw)),
            scan_findings=[])
    finally:
        server.close()
        shutil.rmtree(canary, ignore_errors=True)
    power = {c: attacks.REACHED in (plain["verdicts"].get(c), caps["verdicts"].get(c)) for c in attacks.CHANNELS}
    return {"schema": EVIDENCE_SCHEMA, "status": "DEPLOYMENT_VERIFICATION", "deployment": final.describe(),
            "provenance": _provenance(), "cards_per_channel": cards, "wall_seconds": round(time.time() - started, 1),
            "without_namespaces": plain["verdicts"], "namespaces_with_capabilities": caps["verdicts"],
            "with_namespaces": isolated["verdicts"], "probe_power": power, "missing": isolated["missing"],
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
