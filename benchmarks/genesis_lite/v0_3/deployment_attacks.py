"""Genesis-lite v0.3 DRAFT: the deployment attack suite (readiness P-3, B-LEAK, FDA-19 secret inventory).

The 2026-10-14 probe (G0_A1_FINAL_CLOSURE, "Escrow security") measured these channels from a same-account proposer:
the operator's command line, the root file it named, outbound network, a process that outlived the campaign, and a
writable benchmark package. Audit D-04 / OBS-04 added the run log. Each attack below is a PROPOSER: it runs inside the
isolated proposer process exactly as an arm does, probes one channel, and reports what it reached in its rationale.
Every probe is read-only. The package-write probe opens a file in append mode and writes nothing. The persistence
probe starts a child that only sleeps and touches a marker in the proposer's own working directory.

:func:`verify_deployment` runs the suite under the OD-20 deployment, through the v0.3 harness in the development tier,
and returns one verdict per channel. The OD-20 deployment counts as verified only when every channel is
``REFUSED`` there, AND the independent isolation-probe rerun (FDA-19 scope, certified, OD-3) agrees. On a same-account
host the suite is expected to REACH most channels: that is the measured B-LEAK, not a test failure.

The secret inventory the probes look for (FDA-19): the root (hex or bytes), every derived master, the run log, the
attempt registry and the answer keys. Operators pass the paths and the canaries; nothing here invents one.
"""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Mapping

CHANNELS = ("cmdline", "root_file", "network", "persistence", "package_write", "run_log", "cross_card_state",
            "operator_process", "wsl_interop", "secret_inventory", "unmask", "remount_rw")
#: root-owned system directories the proposer-side scan skips when asked to scan "/" (an operator cannot place a file
#: there without root; scanning them would take minutes per card)
SCAN_SKIP = ("proc", "sys", "dev", "usr", "lib", "lib32", "lib64", "libx32", "bin", "sbin", "boot", "snap",
             "lost+found")
REACHED, REFUSED, UNTESTABLE = "REACHED", "REFUSED", "UNTESTABLE"


def _answer(card: Mapping[str, Any], channel: str, reached: bool | None, detail: str) -> dict[str, Any]:
    """``reached=None``: the probe could not run here (no mechanism, no target). That is UNTESTABLE, never REFUSED."""
    verdict = UNTESTABLE if reached is None else REACHED if reached else REFUSED
    return {"universe_id": card["universe_id"], "answer": "insufficient_evidence",
            "rationale": f"{channel}:{verdict}:{detail[:200]}"}


def _proc_available() -> bool:
    return pathlib.Path("/proc/self/cmdline").exists()


def _parent_cmdline() -> str | None:
    path = pathlib.Path(f"/proc/{os.getppid()}/cmdline")
    try:
        return path.read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return None


def cmdline(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can the proposer read its parent's command line (the first step of the measured attack)?"""
    if not _proc_available():
        return _answer(card, "cmdline", None, "no /proc on this platform: the probe cannot run")
    text = _parent_cmdline()
    return _answer(card, "cmdline", text is not None, "parent command line readable" if text else "not readable")


def root_file(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it read the root file? Operator-named canaries in FORGE_ATTACK_ROOT_FILES (os.pathsep-separated) are tried
    first; otherwise a file named on the parent's command line after ``--root-file`` / ``--registry`` / ``--out``."""
    named = [raw for raw in os.environ.get("FORGE_ATTACK_ROOT_FILES", "").split(os.pathsep) if raw]
    if named:
        for raw in named:
            try:
                pathlib.Path(raw).read_bytes()[:1]
                return _answer(card, "root_file", True, "operator-named root file readable")
            except OSError:
                continue
        return _answer(card, "root_file", False, "no operator-named root file reachable")
    if not _proc_available():
        return _answer(card, "root_file", None, "no /proc on this platform: the probe cannot run")
    text = _parent_cmdline() or ""
    words = text.split()
    for flag in ("--root-file", "--registry", "--out"):
        if flag in words and words.index(flag) + 1 < len(words):
            target = pathlib.Path(words[words.index(flag) + 1])
            try:
                if target.is_file():
                    target.read_bytes()[:1]
                elif target.is_dir():
                    next(iter(target.iterdir()), None)
                else:
                    continue
                return _answer(card, "root_file", True, f"{flag} target readable")
            except OSError:
                continue
    if not any(flag in words for flag in ("--root-file", "--registry", "--out")):
        return _answer(card, "root_file", None, "the parent names no operator file: nothing to test")
    return _answer(card, "root_file", False, "no operator file reachable")


def network(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it open an outbound TCP connection? The operator names the target in FORGE_ATTACK_NETWORK_TARGET (host:port);
    without one, nothing is attempted and the channel is UNTESTABLE."""
    target = os.environ.get("FORGE_ATTACK_NETWORK_TARGET", "")
    if ":" not in target:
        return _answer(card, "network", None, "no target configured")
    host, port = target.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=3):
            return _answer(card, "network", True, f"connected to {target}")
    except OSError as exc:
        return _answer(card, "network", False, type(exc).__name__)


def persistence(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it start a detached child that outlives the campaign? The child sleeps, then touches a marker next to the
    per-card temporary directory (which is deleted with the card); the operator checks for the marker afterwards."""
    try:
        _shared_dir().mkdir(exist_ok=True)
    except OSError as exc:
        return _answer(card, "persistence", None, f"setup failed: {type(exc).__name__}")
    marker = _shared_dir() / f"gl-persistence-marker-{uuid.uuid4().hex}"
    # the helper's own command line carries the marker name: the runner detects it from the HOST while it lives, so a
    # marker that is merely invisible to the host (a private /tmp) cannot pass for a refused helper (review I-3)
    code = f"import time, pathlib; time.sleep(8); pathlib.Path({str(marker)!r}).touch()"
    try:
        kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                                  "cwd": str(_shared_dir())}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        else:
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([sys.executable, "-c", code], **kwargs)
    except OSError as exc:
        return _answer(card, "persistence", False, type(exc).__name__)
    return {"universe_id": card["universe_id"], "answer": "insufficient_evidence",       # resolved by the runner
            "rationale": f"persistence:PENDING:{marker}"}


def package_write(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Is the benchmark package writable? Opens its ``__init__.py`` for append and closes it without writing."""
    target = pathlib.Path(__file__).resolve().parents[1] / "__init__.py"
    try:
        with open(target, "ab"):
            pass
        return _answer(card, "package_write", True, "benchmark package writable")
    except OSError as exc:
        return _answer(card, "package_write", False, type(exc).__name__)


def run_log(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it read a run log or the attempt registry? The operator names candidate paths in FORGE_ATTACK_RUN_LOGS
    (os.pathsep-separated), as an attacker would learn them from the command line."""
    candidates = [raw for raw in os.environ.get("FORGE_ATTACK_RUN_LOGS", "").split(os.pathsep) if raw]
    if not candidates:
        return _answer(card, "run_log", None, "no run-log path configured")
    for raw in candidates:
        if raw:
            try:
                pathlib.Path(raw).read_bytes()[:1]
                return _answer(card, "run_log", True, "run log readable")
            except OSError:
                continue
    return _answer(card, "run_log", False, "no run log reachable")


def _shared_dir() -> pathlib.Path:
    """A directory that outlives one card under the same account: the parent of the per-card temporary directory, or
    the temporary directory itself where that parent is read-only (a D5-A1b card's private /tmp)."""
    temp = pathlib.Path(tempfile.gettempdir()).resolve()
    return (temp.parent if os.access(temp.parent, os.W_OK) else temp) / "gl-cross-card-state"


def cross_card_state(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """FDA-18 residual: can one card leave state that a LATER card of the campaign reads? Each card writes a marker into
    a directory outside its own per-card temp directory and counts the markers it finds there. REACHED on any card
    that finds a marker left by an earlier one. Finding none is never REFUSED (fifth review N-1): one directory says
    nothing about every other writable mount. That verdict comes only from the mount-complete container canary
    evidence (:mod:`.container_evidence`), in :func:`verify_deployment`."""
    try:
        shared = _shared_dir()
        shared.mkdir(exist_ok=True)
        seen = sum(1 for x in shared.iterdir() if x.name.startswith("card-"))
        (shared / f"card-{uuid.uuid4().hex}").write_bytes(b"")
    except OSError as exc:
        return _answer(card, "cross_card_state", None, f"setup failed: {type(exc).__name__}")
    if seen:
        return _answer(card, "cross_card_state", True, f"{seen} earlier marker(s) found")
    return _answer(card, "cross_card_state", None, "no earlier marker in one directory; not evidence about every "
                                                   "writable mount (the container canary evidence decides)")


def operator_process(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it reach another process of the account (the first step of heap, stack and environment attacks on the
    operator or an in-process escrow)? Tries to read the environment of every other visible process."""
    if not _proc_available():
        return _answer(card, "operator_process", None, "no /proc on this platform: the probe cannot run")
    me, readable = os.getpid(), 0
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            (entry / "environ").read_bytes()[:1]
            readable += 1
        except OSError:
            continue
    return _answer(card, "operator_process", readable > 0, f"{readable} other process(es) readable")


def wsl_interop(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it start a Windows process through WSL interop (outside every Linux namespace)? Tries the Windows command
    interpreter at its usual paths, with the interop socket the operator names in FORGE_ATTACK_WSL_INTEROP (an attacker
    can guess it). No Windows executable reachable is REFUSED; on a non-WSL host there is none."""
    import shutil  # noqa: PLC0415

    sockets = sorted(str(p) for p in pathlib.Path("/run/WSL").glob("*_interop")) if pathlib.Path("/run/WSL").is_dir() \
        else []
    named = os.environ.get("FORGE_ATTACK_WSL_INTEROP", "")
    if named and pathlib.Path(named).exists():
        sockets.append(named)
    if sockets:
        return _answer(card, "wsl_interop", True, f"interop socket visible: {sockets[0]}")
    candidates = [p for p in (shutil.which("cmd.exe"), "/mnt/c/Windows/System32/cmd.exe", "/mnt/c/WINDOWS/system32/cmd.exe")
                  if p and pathlib.Path(p).is_file()]
    env = dict(os.environ)
    if os.environ.get("FORGE_ATTACK_WSL_INTEROP"):
        env["WSL_INTEROP"] = os.environ["FORGE_ATTACK_WSL_INTEROP"]
    for exe in candidates:
        try:
            done = subprocess.run([exe, "/c", "exit 0"], env=env, capture_output=True, timeout=15)
            if done.returncode == 0:
                return _answer(card, "wsl_interop", True, f"started {exe}")
        except (OSError, subprocess.SubprocessError):
            continue
    return _answer(card, "wsl_interop", False, f"no Windows executable could be started ({len(candidates)} found)")


def secret_inventory(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """FDA-19, proposer side: does any file it can read under FORGE_ATTACK_SCAN_ROOTS hold a secret whose digest the
    operator lists in FORGE_ATTACK_SCAN_DIGESTS (comma-separated, :func:`.secret_scan.digests_for`)?"""
    from . import secret_scan  # noqa: PLC0415

    roots = [raw for raw in os.environ.get("FORGE_ATTACK_SCAN_ROOTS", "").split(os.pathsep) if raw]
    digests = [d for d in os.environ.get("FORGE_ATTACK_SCAN_DIGESTS", "").split(",") if d]
    if not roots or not digests:
        return _answer(card, "secret_inventory", None, "no scan roots or digests configured")
    paths: list[pathlib.Path] = []
    for raw in roots:
        if raw == "/":
            paths += [p for p in pathlib.Path("/").iterdir() if p.name not in SCAN_SKIP and not p.is_symlink()]
        else:
            paths.append(pathlib.Path(raw))
    found = secret_scan.scan(paths, digests)
    return _answer(card, "secret_inventory", bool(found), f"{len(found)} readable file(s) hold a secret")


def _libc() -> Any:
    import ctypes  # noqa: PLC0415
    import ctypes.util  # noqa: PLC0415

    name = ctypes.util.find_library("c")
    return ctypes.CDLL(name, use_errno=True) if name else None


def _nested(command: str) -> bool:
    """Run ``command`` in a NEW user + mount namespace (unprivileged); True if it printed ESCAPED."""
    import shutil  # noqa: PLC0415

    if shutil.which("unshare") is None:
        return False
    try:
        done = subprocess.run(["unshare", "--user", "--map-root-user", "--mount", "sh", "-c", command],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return "ESCAPED" in done.stdout


def unmask(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Review I-1: can it remove a mask (unmount a tmpfs over an operator directory), directly or from a nested user
    namespace? Tries every mount point among the masked roots."""
    libc = _libc() if os.name == "posix" else None
    if libc is None:
        return _answer(card, "unmask", None, "no libc on this platform: the probe cannot run")
    targets = [t for t in ("/home", "/mnt", "/run", "/tmp", "/root", "/var/tmp", "/opt", "/media", "/dev/shm")
               if os.path.ismount(t)]
    for t in targets:
        if libc.umount2(t.encode(), 2) == 0:                   # MNT_DETACH
            return _answer(card, "unmask", True, f"unmounted {t}")
    for t in targets:
        if _nested(f"umount -l {t} 2>/dev/null && echo ESCAPED"):
            return _answer(card, "unmask", True, f"unmounted {t} from a nested namespace")
    return _answer(card, "unmask", False, f"{len(targets)} mask(s) held")


def remount_rw(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Review I-1: can it make the kept benchmark tree writable by remounting it, directly or from a nested user
    namespace? Writes nothing: success of the remount call is the finding."""
    libc = _libc() if os.name == "posix" else None
    if libc is None:
        return _answer(card, "remount_rw", None, "no libc on this platform: the probe cannot run")
    target = str(pathlib.Path(__file__).resolve().parents[3])      # the kept tree's mount point (the repository root)
    try:                                                     # util-linux keeps the mount's locked flags on a remount
        done = subprocess.run(["mount", "-o", "remount,bind,rw", target], capture_output=True, timeout=20)
        if done.returncode == 0:
            return _answer(card, "remount_rw", True, "remounted the kept tree read-write")
    except (OSError, subprocess.SubprocessError):
        pass
    if libc.mount(None, target.encode(), None, 32 | 4096, None) == 0:     # MS_REMOUNT | MS_BIND, no MS_RDONLY
        return _answer(card, "remount_rw", True, "remounted the kept tree read-write")
    if _nested(f"mount -o remount,bind,rw {target} 2>/dev/null && echo ESCAPED"):
        return _answer(card, "remount_rw", True, "remounted the kept tree read-write from a nested namespace")
    return _answer(card, "remount_rw", False, "the kept tree stays read-only")


def _alive_with(token: str) -> bool:
    """Whether any process on THIS host's view carries ``token`` in its command line."""
    proc = pathlib.Path("/proc")
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                if token.encode() in (entry / "cmdline").read_bytes():
                    return True
            except OSError:
                continue
    return False


def channel_verdicts(rationales: list[str]) -> dict[str, str]:
    """REACHED if any card of a channel reached it; UNTESTABLE if any could not test it; REFUSED only if every card
    tested it and was refused."""
    rank = {REFUSED: 0, UNTESTABLE: 1, REACHED: 2}
    out: dict[str, str] = {}
    for text in rationales:
        channel, verdict, _ = (text.split(":", 2) + ["", ""])[:3]
        if channel in CHANNELS and verdict in rank:
            out[channel] = max(verdict, out.get(channel, REFUSED), key=rank.__getitem__)
    return out


def deployment_runner(attack_env: Mapping[str, str] | None = None, cards: int = 2, host_factory: Any = None) -> Any:
    """``run(spec) -> rationales`` for :func:`verify_deployment`: each attack runs ``cards`` times, each time in a fresh
    per-card proposer process (the v0.3 harness's, or ``host_factory(attack_env=...)``, e.g. one in the D5 namespaces),
    with only FORGE_ATTACK_* variables added to its environment."""
    from .harness import CardProposerHost  # noqa: PLC0415

    make = host_factory or CardProposerHost

    def run(spec: str) -> list[str]:
        import time  # noqa: PLC0415

        out = []
        for i in range(cards):
            host = make(attack_env=attack_env)
            try:
                out.append(host.propose(spec, {"universe_id": f"bf-attack-{i}"}, 0, None)["rationale"])
            finally:
                host.close()
        resolved = []
        for text in out:                                   # a helper process proves itself by its marker
            channel, verdict, detail = (text.split(":", 2) + ["", ""])[:3]
            if verdict == "PENDING":                        # seen alive from the host, or its marker appears
                token, seen = pathlib.Path(detail).name, False
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline and not seen:
                    seen = _alive_with(token) or pathlib.Path(detail).exists()
                    time.sleep(0.25)
                verdict = REACHED if seen else REFUSED
                text = f"{channel}:{verdict}:{detail}"
            resolved.append(text)
        return resolved

    return run


def verify_deployment(run: Any, scan_findings: list[Any] | None = None,
                      container_validation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run every attack once through ``run(attack_spec) -> rationales``, which the operator binds to the v0.3 harness in
    the OD-20 deployment, and take the proposer-side secret-inventory scan (:mod:`.secret_scan`, FDA-19). Verified only
    if every channel is REFUSED, the scan ran and found nothing, AND the N-1 container evidence
    (:func:`.container_evidence.validate_container_evidence`) PASSED: REFUSED transcripts of the old channels say
    nothing about an unprobed writable mount, the container identities, the image or the runtime flags. The
    ``cross_card_state`` channel is REFUSED only on that evidence (its probe never refuses by itself)."""
    probed = {}
    for channel in CHANNELS:
        probed.update(channel_verdicts(run(f"benchmarks.genesis_lite.v0_3.deployment_attacks:{channel}")))
    containers_pass = isinstance(container_validation, Mapping) and container_validation.get("status") == "PASS"
    verdicts = dict(probed)
    if "cross_card_state" in verdicts and verdicts["cross_card_state"] != REACHED:
        verdicts["cross_card_state"] = REFUSED if containers_pass else UNTESTABLE
    missing = sorted(set(CHANNELS) - set(verdicts))
    return {"verdicts": verdicts, "probed": probed, "missing": missing, "secret_scan": scan_findings,
            "container_validation": container_validation,
            "verified": (not missing and all(v == REFUSED for v in verdicts.values()) and scan_findings == []
                         and containers_pass)}
