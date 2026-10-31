"""OS-isolated proposer processes for Genesis-lite v0.4 (owner decisions D3 and D11, 2026-10-30; gaps G5, G14, FDA-18).

Every UNIVERSE gets a fresh proposer process (D11: a proposer never sees a second card, so answer exclusivity inside a
campaign cannot be exploited by elimination). The process speaks the existing ``proposer_host`` protocol over its
stdin/stdout pipes -- the operator keeps the escrow, the presentation and the query cap, exactly as in the
``proposer_process`` mode -- and runs in another security domain, built with the mechanism of
:mod:`engcore.blindfold.isolation`:

* private mount, pid (own /proc), network (loopback only), ipc and uts namespaces (``unshare``);
* /opt is a WHITELIST: an empty tmpfs over it, with only the code tree, the interpreter's environment and the
  explicitly exposed directories bound back READ-ONLY (another checkout's results under /opt stay invisible);
* an empty mode-000 tmpfs over every HIDDEN path (by default /home, /root, /mnt, /var/tmp, /srv, plus every
  ``pilot_results`` directory of the tree and the operator's extra paths), and a fresh private /tmp;
* PRIVATE instances of every location a process may write and a later one read (review finding 1): /tmp and
  /dev/shm as fresh tmpfs, /dev/mqueue as a fresh mqueue of the new ipc namespace, /run and /var/crash covered; so no
  state passes from one proposer process to the next (D11, and the unit independence D9 relies on);
* uid/gid 65534 with cleared groups, empty inheritable and bounding capability sets and no_new_privs (``setpriv``);
* an environment of only PATH, HOME=/tmp, the thread limits and the explicitly passed variables.

The LAUNCHER (operator) verifies each process from OUTSIDE, through /proc, after the readiness ``hello`` and before
the first card: uid/gid, groups, capabilities, no_new_privs, the five namespaces and a tmpfs over every hidden path.
A failed check refuses the run (no card is sent). The operator runs as root in its own domain; the proposer, in a
separate pid namespace without capabilities, can neither see nor ptrace it. Same kernel: a kernel escape is out of
scope, so the boundary level this can establish is OS_ISOLATION_BOUNDARY_VERIFIED at most, and only through the
verification record, never by this module's say-so.

The code tree and the interpreter must be readable by uid 65534 (on WSL: a checkout under /opt with drvfs mounted
umask=077, PROGRESS 2026-10-28); that is a deployment precondition this module checks, not one it creates.
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

from engcore.blindfold.isolation import DISCOVERY_UID

from . import harness as h2

ISOLATION_LABEL = "os_isolated_per_universe"
DEFAULT_HIDDEN = ("/home", "/root", "/mnt", "/var/tmp", "/srv")
WHITELIST_ROOT = "/opt"
#: covered (mode 000) when present: shared writable state a proposer could leave for the next one
SHARED_STATE = ("/run", "/var/crash")
#: fresh private instances, writable by the proposer, gone with its mount namespace
PRIVATE_WRITABLE = ("/tmp", "/dev/shm")
#: after the uid switch, a fresh user namespace per process (re-review M3): kernel user keyrings are per user namespace,
#: so a key one proposer leaves on uid 65534's keyring (it outlives the process) is not there for the next one. The
#: process is root only inside its own empty namespace (65534 outside); dropping the bounding set again there leaves
#: every capability at zero, which the outside verification checks
#: Inside it, before the second drop, root of that namespace sets its max_user_namespaces to 0, so the proposer cannot
#: create a nested namespace and regain capabilities there (review 2026-10-31 M-b)
USER_NAMESPACE = ("unshare --user --map-root-user -- /bin/sh -c 'echo 0 > /proc/sys/user/max_user_namespaces && "
                  "exec setpriv --inh-caps=-all --bounding-set=-all -- \"$@\"' userns")
#: the namespaces and capability sets the outside verification requires, exactly (review 2026-10-31 M-c)
NAMESPACES = ("mnt", "pid", "net", "ipc", "uts", "user")
CAP_SETS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
THREAD_ENV = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
_HOST = pathlib.Path(__file__).resolve().parent / "proposer_host.py"
_ROOT = pathlib.Path(__file__).resolve().parents[2]


class IsolationUnavailable(RuntimeError):
    """This host cannot build the isolated deployment; a run here is never labelled isolated."""


def support() -> tuple[bool, str]:
    if sys.platform != "linux":
        return False, "OS isolation needs Linux namespaces"
    if os.geteuid() != 0:
        return False, "the launcher needs root to create namespaces and switch to the discovery uid"
    missing = [t for t in ("unshare", "setpriv", "mount") if shutil.which(t) is None]
    if missing:
        return False, f"missing tools: {missing}"
    return True, "ok"


def _under(path: str | os.PathLike[str], ancestor: str | os.PathLike[str]) -> bool:
    return pathlib.PurePosixPath(path).is_relative_to(pathlib.PurePosixPath(ancestor))


def _minimal(paths: Sequence[str]) -> tuple[str, ...]:
    """Drop every path that a shorter path already covers (a nested mount point would no longer exist)."""
    out: list[str] = []
    for p in sorted(dict.fromkeys(paths), key=lambda s: (len(pathlib.PurePosixPath(s).parts), s)):
        if not any(_under(p, q) for q in out):
            out.append(p)
    return tuple(out)


def exposures(extra: Sequence[str | os.PathLike[str]] = ()) -> tuple[str, ...]:
    """Directories under /opt bound back read-only: the code tree, the interpreter's environment, ``extra``. The code
    tree must live under /opt (a deployment precondition: elsewhere the whitelist would not cover it)."""
    root = str(_ROOT.resolve())
    if not _under(root, WHITELIST_ROOT):
        raise IsolationUnavailable(f"the code tree {root} is not under {WHITELIST_ROOT}")
    out = [root] + [p for p in (str(pathlib.Path(sys.prefix).resolve()),) if _under(p, WHITELIST_ROOT)]
    for p in extra:
        path = pathlib.Path(p).resolve()
        if not path.is_dir() or not _under(path, WHITELIST_ROOT):
            raise IsolationUnavailable(f"exposed path {path} is not an existing directory under {WHITELIST_ROOT}")
        out.append(str(path))
    return _minimal(out)


def hidden_paths(extra: Sequence[str | os.PathLike[str]] = (), *,
                 exposed: Sequence[str] | None = None) -> tuple[str, ...]:
    """The minimal set of directories to cover with an empty tmpfs: the defaults, every ``pilot_results`` directory of
    this tree, ``extra``. A path that is not an existing directory refuses (a silently skipped hide would be a silent
    leak); a path under /opt outside every exposure is already covered by the whitelist and is not repeated."""
    exposed = exposures() if exposed is None else tuple(exposed)
    out = [p for p in DEFAULT_HIDDEN if os.path.isdir(p)]
    out += [str(p.resolve()) for p in sorted(_ROOT.glob("benchmarks/**/pilot_results")) if p.is_dir()]
    for p in extra:
        path = pathlib.Path(p).resolve()
        if not path.is_dir():
            raise IsolationUnavailable(f"hidden path {path} is not an existing directory")
        out.append(str(path))
    if any(_under(e, p) for e in exposed for p in out):
        raise IsolationUnavailable("a hidden path contains an exposed directory (the code tree); the proposer could not run")
    out = [p for p in out if not (_under(p, WHITELIST_ROOT) and not any(_under(p, e) for e in exposed))]
    return _minimal(out)


def command(hidden: Sequence[str], env: Mapping[str, str], python: str = sys.executable,
            exposed: Sequence[str] = ()) -> list[str]:
    """The launcher command: namespaces; /opt whitelisted (exposures staged under a private /mnt, /opt covered, the
    exposures bound back read-only); tmpfs hides (/mnt among them, covering the staging); a private /tmp; then the
    uid switch and a clean environment."""
    q = shlex.quote
    steps = ["mount -t tmpfs -o size=1m,mode=755 tmpfs /mnt"] if exposed else []
    for i, e in enumerate(exposed):
        steps += [f"mkdir -p /mnt/fg{i}", f"mount --bind {q(e)} /mnt/fg{i}"]
    if exposed:
        steps.append(f"mount -t tmpfs -o size=1m,mode=755 tmpfs {WHITELIST_ROOT}")
    for i, e in enumerate(exposed):
        steps += [f"mkdir -p {q(e)}", f"mount --bind /mnt/fg{i} {q(e)}", f"mount -o remount,bind,ro {q(e)}"]
    steps += [f"mount -t tmpfs -o size=64k,mode=000 tmpfs {q(p)}" for p in hidden]
    steps += [f"if [ -d {p} ]; then mount -t tmpfs -o size=64k,mode=000 tmpfs {p}; fi" for p in SHARED_STATE]
    steps += ["mount -t tmpfs -o size=1g,mode=1777 tmpfs /tmp", "mount -t tmpfs -o size=256m,mode=1777 tmpfs /dev/shm",
              "if [ -d /dev/mqueue ]; then mount -t mqueue mqueue /dev/mqueue; fi", "cd /tmp"]
    clean = " ".join(q(f"{k}={v}") for k, v in sorted({"PATH": "/usr/bin:/bin", "HOME": "/tmp", **THREAD_ENV,
                                                       **dict(env)}.items()))
    host_script = _HOST.with_name("proposer_profile_v4.py") if env.get("FORGE_PERF_DIAGNOSTICS") == "1" else _HOST
    inner = " && ".join(steps) + (
        f" && exec setpriv --reuid={DISCOVERY_UID} --regid={DISCOVERY_UID} --clear-groups --inh-caps=-all "
        f"--bounding-set=-all --no-new-privs -- {USER_NAMESPACE} /usr/bin/env -i {clean} {q(python)} -I "
        f"{q(str(host_script))} {q(str(_ROOT))} {q(str(_ROOT / 'src'))}")
    return ["unshare", "--mount", "--pid", "--fork", "--net", "--ipc", "--uts", "--mount-proc", "--", "/bin/sh", "-c",
            inner]


def _fresh_session_keyring() -> None:
    """In the launched child before exec: join a new anonymous session keyring, so no proposer inherits the launcher's
    (a PAM session under sudo/ssh has one) or shares one with another proposer (review 2026-10-31 M-a)."""
    import ctypes  # noqa: PLC0415 - Linux only, in the forked child
    if ctypes.CDLL(None, use_errno=True).syscall(250, 1, None) < 0:      # keyctl(KEYCTL_JOIN_SESSION_KEYRING, NULL)
        raise OSError(ctypes.get_errno(), "could not join a fresh session keyring")


def _leaf(pid: int) -> int:
    from engcore.blindfold.isolation import _leaf as leaf  # noqa: PLC0415 - the launcher's own /proc walk
    return leaf(pid)


def inspect(pid: int, hidden: Sequence[str], exposed: Sequence[str] = ()) -> dict[str, Any]:
    """What the launcher sees of the proposer process from OUTSIDE (never the process's own report)."""
    status = dict(line.split(":", 1) for line in open(f"/proc/{pid}/status").read().splitlines() if ":" in line)
    ids = lambda k: [int(x) for x in status.get(k, "").split()]  # noqa: E731
    caps = {k: int(status.get(k, "f").strip() or "f", 16) for k in CAP_SETS}
    ns = {n: os.readlink(f"/proc/{pid}/ns/{n}") != os.readlink(f"/proc/self/ns/{n}") for n in NAMESPACES}
    mounts = [ln.split() for ln in open(f"/proc/{pid}/mountinfo").read().splitlines()]
    tmpfs = {m[4] for m in mounts if "-" in m and m[m.index("-") + 1] == "tmpfs"}
    read_only = {m[4] for m in mounts if len(m) > 5 and m[5].split(",")[0] == "ro"}
    # a private instance has a device id the operator's own namespace does not have at that path
    theirs = {m[4]: m[2] for m in mounts if len(m) > 4}
    ours = {m[4]: m[2] for m in (ln.split() for ln in open("/proc/self/mountinfo").read().splitlines()) if len(m) > 4}
    fresh = {path: path in theirs and theirs[path] != ours.get(path) for path in PRIVATE_WRITABLE}
    if os.path.isdir("/dev/mqueue"):
        fresh["/dev/mqueue"] = "/dev/mqueue" in theirs and theirs["/dev/mqueue"] != ours.get("/dev/mqueue")
    shared = {path: path in tmpfs for path in SHARED_STATE if os.path.isdir(path)}
    return {"inspected": True, "uid": ids("Uid"), "gid": ids("Gid"), "groups": ids("Groups"), "caps": caps,
            "no_new_privs": status.get("NoNewPrivs", "").strip() == "1", "private_namespaces": ns,
            "hidden": {p: p in tmpfs for p in hidden}, "private_tmp": "/tmp" in tmpfs,
            "private_writable": fresh, "shared_state_covered": shared,
            "whitelist_covered": WHITELIST_ROOT in tmpfs, "exposed_read_only": {e: e in read_only for e in exposed}}


def verified(o: Mapping[str, Any]) -> bool:
    return bool(o.get("inspected") and o["uid"] == [DISCOVERY_UID] * 4 and o["gid"] == [DISCOVERY_UID] * 4
                and not o["groups"] and set(o["caps"]) == set(CAP_SETS) and not any(o["caps"].values())
                and o["no_new_privs"] and set(o["private_namespaces"]) == set(NAMESPACES)
                and all(o["private_namespaces"].values()) and o["hidden"] and all(o["hidden"].values())
                and o["private_tmp"] and o.get("whitelist_covered") is True and bool(o.get("exposed_read_only"))
                and all(o["exposed_read_only"].values()) and bool(o.get("private_writable"))
                and all(o["private_writable"].values()) and all(o.get("shared_state_covered", {"": False}).values()))


class IsolatedProposerHost(h2.ProposerHost):
    """``ProposerHost``'s protocol, in another security domain; verified from outside before any card is sent."""

    def __init__(self, hidden: Sequence[str], *, env: Mapping[str, str] | None = None, timeout: float = 600.0,
                 python: str = sys.executable, exposed: Sequence[str] | None = None) -> None:
        ok, why = support()
        if not ok:
            raise IsolationUnavailable(why)
        self._dir = None
        self._started = time.perf_counter()
        self.timing: dict[str, Any] = {"source": "operator", "diagnostic_events_untrusted": []}
        self._sampler = None
        self._usage_before = None
        self._closed = False
        if (env or {}).get("FORGE_PERF_RESOURCES") == "1":
            from .telemetry_v4 import usage
            self._usage_before = usage()
        self._timeout = timeout
        exposed = exposures() if exposed is None else tuple(exposed)
        self._err = tempfile.TemporaryFile()                     # operator-side; the proposer's private /tmp cannot see it
        self._proc = subprocess.Popen(command(hidden, env or {}, python, exposed), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=self._err, cwd="/", env={"PATH": "/usr/bin:/bin"}, bufsize=0,
                                      start_new_session=True, preexec_fn=_fresh_session_keyring)
        self.timing["popen_seconds"] = time.perf_counter() - self._started
        if self._usage_before is not None:
            from .telemetry_v4 import ProcessSampler
            self._sampler = ProcessSampler(self._proc.pid)
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        try:
            hello = self._recv()
        except BaseException:
            self.close()
            raise
        self.timing["launch_to_hello_seconds"] = time.perf_counter() - self._started
        expected = str((_ROOT / "src" / "engcore" / "__init__.py").resolve())
        if hello.get("op") != "hello" or str(pathlib.Path(hello.get("engcore", "")).resolve()) != expected:
            self.close()
            raise IsolationUnavailable(f"the isolated proposer did not import this tree's engcore: {hello}")
        inspected = time.perf_counter()
        try:
            self.outside = inspect(_leaf(self._proc.pid), hidden, exposed)
        except BaseException:
            self.close()
            raise
        self.timing["outside_verification_seconds"] = time.perf_counter() - inspected
        if not verified(self.outside):
            self.close()
            raise IsolationUnavailable(f"the proposer process failed outside verification: {json.dumps(self.outside)}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        teardown = time.perf_counter()
        if self._proc.poll() is None:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
                self._proc.wait(timeout=10)
            except Exception:  # noqa: BLE001 - it must not outlive its universe
                try:
                    os.killpg(self._proc.pid, 9)
                except ProcessLookupError:
                    pass
                self._proc.wait(timeout=10)
        self._err.close()
        self.timing["teardown_seconds"] = time.perf_counter() - teardown
        self.timing["lifetime_seconds"] = time.perf_counter() - self._started
        if self._sampler is not None:
            self.timing["resources"] = self._sampler.close()
            from .telemetry_v4 import usage
            self.timing["resources"].update({k: v - self._usage_before[k] for k, v in usage().items()})

    def stderr_tail(self, limit: int = 600) -> str:
        """The last bytes the proposer wrote to stderr (its own text: diagnostic, never evidence)."""
        try:
            self._err.seek(0)
            return self._err.read().decode("utf-8", "replace")[-limit:]
        except ValueError:
            return ""

    def _recv(self) -> dict[str, Any]:
        try:
            while True:
                msg = super()._recv()
                if msg.get("op") != "diagnostic":
                    return msg
                events = self.timing["diagnostic_events_untrusted"]
                if len(events) >= 200:
                    raise RuntimeError("too many proposer diagnostic messages")
                events.append({"parent_elapsed_seconds": time.perf_counter() - self._started, "message": msg})
        except RuntimeError as exc:
            raise RuntimeError(f"{exc}; proposer stderr: {self.stderr_tail()!r}") from None


def per_universe_arm(spec: str, hidden: Sequence[str], checks: list[dict[str, Any]], *,
                     env: Mapping[str, str] | None = None, timeout: float = 600.0,
                     exposed: Sequence[str] | None = None, timings: list[dict[str, Any]] | None = None):
    """An arm callable for ``harness_v3._run_v3``: a fresh verified isolated process for every universe. Each
    process's outside verification is appended to ``checks`` (the run record keeps them)."""
    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> Mapping[str, Any]:
        # An INFRASTRUCTURE failure (the launch, the outside verification, a dead or silent process) is recorded so
        # the run becomes INVALID_BENCHMARK; only the arm's own reported error is a method failure (inadmissible).
        try:
            host = IsolatedProposerHost(hidden, env=env, timeout=timeout, exposed=exposed)
        except Exception as exc:
            checks.append({"universe_id": card["universe_id"], "infrastructure_failure": f"{type(exc).__name__}: {exc}"[:400]})
            raise
        try:
            checks.append({"universe_id": card["universe_id"], **host.outside})
            try:
                return host.propose(spec, card, seed, client)
            except Exception as exc:  # noqa: BLE001 - a dead pipe (OSError) is the host's failure too (re-review L2)
                if not (isinstance(exc, RuntimeError) and str(exc).startswith("the proposer failed:")):
                    checks.append({"universe_id": card["universe_id"], "infrastructure_failure": str(exc)[:400]})
                raise
        finally:
            host.close()
            if timings is not None:
                timings.append({"universe_id": card["universe_id"], **host.timing})
    return arm


__all__ = ["DEFAULT_HIDDEN", "ISOLATION_LABEL", "IsolatedProposerHost", "IsolationUnavailable", "WHITELIST_ROOT",
           "command", "exposures", "hidden_paths", "inspect", "per_universe_arm", "support", "verified"]
