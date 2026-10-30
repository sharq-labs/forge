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
from collections.abc import Mapping, Sequence
from typing import Any

from engcore.blindfold.isolation import DISCOVERY_UID

from . import harness as h2

ISOLATION_LABEL = "os_isolated_per_universe"
DEFAULT_HIDDEN = ("/home", "/root", "/mnt", "/var/tmp", "/srv")
WHITELIST_ROOT = "/opt"
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
    steps += ["mount -t tmpfs -o size=1g,mode=1777 tmpfs /tmp", "cd /tmp"]
    clean = " ".join(q(f"{k}={v}") for k, v in sorted({"PATH": "/usr/bin:/bin", "HOME": "/tmp", **THREAD_ENV,
                                                       **dict(env)}.items()))
    inner = " && ".join(steps) + (
        f" && exec setpriv --reuid={DISCOVERY_UID} --regid={DISCOVERY_UID} --clear-groups --inh-caps=-all "
        f"--bounding-set=-all --no-new-privs -- /usr/bin/env -i {clean} {q(python)} -I "
        f"{q(str(_HOST))} {q(str(_ROOT))} {q(str(_ROOT / 'src'))}")
    return ["unshare", "--mount", "--pid", "--fork", "--net", "--ipc", "--uts", "--mount-proc", "--", "/bin/sh", "-c",
            inner]


def _leaf(pid: int) -> int:
    from engcore.blindfold.isolation import _leaf as leaf  # noqa: PLC0415 - the launcher's own /proc walk
    return leaf(pid)


def inspect(pid: int, hidden: Sequence[str], exposed: Sequence[str] = ()) -> dict[str, Any]:
    """What the launcher sees of the proposer process from OUTSIDE (never the process's own report)."""
    status = dict(line.split(":", 1) for line in open(f"/proc/{pid}/status").read().splitlines() if ":" in line)
    ids = lambda k: [int(x) for x in status.get(k, "").split()]  # noqa: E731
    caps = {k: int(status.get(k, "f").strip() or "f", 16) for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}
    ns = {n: os.readlink(f"/proc/{pid}/ns/{n}") != os.readlink(f"/proc/self/ns/{n}") for n in ("mnt", "pid", "net", "ipc", "uts")}
    mounts = [ln.split() for ln in open(f"/proc/{pid}/mountinfo").read().splitlines()]
    tmpfs = {m[4] for m in mounts if "-" in m and m[m.index("-") + 1] == "tmpfs"}
    read_only = {m[4] for m in mounts if len(m) > 5 and m[5].split(",")[0] == "ro"}
    return {"inspected": True, "uid": ids("Uid"), "gid": ids("Gid"), "groups": ids("Groups"), "caps": caps,
            "no_new_privs": status.get("NoNewPrivs", "").strip() == "1", "private_namespaces": ns,
            "hidden": {p: p in tmpfs for p in hidden}, "private_tmp": "/tmp" in tmpfs,
            "whitelist_covered": WHITELIST_ROOT in tmpfs, "exposed_read_only": {e: e in read_only for e in exposed}}


def verified(o: Mapping[str, Any]) -> bool:
    return bool(o.get("inspected") and o["uid"] == [DISCOVERY_UID] * 4 and o["gid"] == [DISCOVERY_UID] * 4
                and not o["groups"] and not any(o["caps"].values()) and o["no_new_privs"]
                and all(o["private_namespaces"].values()) and o["hidden"] and all(o["hidden"].values())
                and o["private_tmp"] and o.get("whitelist_covered") is True and bool(o.get("exposed_read_only"))
                and all(o["exposed_read_only"].values()))


class IsolatedProposerHost(h2.ProposerHost):
    """``ProposerHost``'s protocol, in another security domain; verified from outside before any card is sent."""

    def __init__(self, hidden: Sequence[str], *, env: Mapping[str, str] | None = None, timeout: float = 600.0,
                 python: str = sys.executable, exposed: Sequence[str] | None = None) -> None:
        ok, why = support()
        if not ok:
            raise IsolationUnavailable(why)
        self._dir = None
        self._timeout = timeout
        exposed = exposures() if exposed is None else tuple(exposed)
        self._err = tempfile.TemporaryFile()                     # operator-side; the proposer's private /tmp cannot see it
        self._proc = subprocess.Popen(command(hidden, env or {}, python, exposed), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=self._err, cwd="/", env={"PATH": "/usr/bin:/bin"}, bufsize=0,
                                      start_new_session=True)
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        hello = self._recv()
        expected = str((_ROOT / "src" / "engcore" / "__init__.py").resolve())
        if hello.get("op") != "hello" or str(pathlib.Path(hello.get("engcore", "")).resolve()) != expected:
            self.close()
            raise IsolationUnavailable(f"the isolated proposer did not import this tree's engcore: {hello}")
        self.outside = inspect(_leaf(self._proc.pid), hidden, exposed)
        if not verified(self.outside):
            self.close()
            raise IsolationUnavailable(f"the proposer process failed outside verification: {json.dumps(self.outside)}")

    def close(self) -> None:
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

    def stderr_tail(self, limit: int = 600) -> str:
        """The last bytes the proposer wrote to stderr (its own text: diagnostic, never evidence)."""
        try:
            self._err.seek(0)
            return self._err.read().decode("utf-8", "replace")[-limit:]
        except ValueError:
            return ""

    def _recv(self) -> dict[str, Any]:
        try:
            return super()._recv()
        except RuntimeError as exc:
            raise RuntimeError(f"{exc}; proposer stderr: {self.stderr_tail()!r}") from None


def per_universe_arm(spec: str, hidden: Sequence[str], checks: list[dict[str, Any]], *,
                     env: Mapping[str, str] | None = None, timeout: float = 600.0,
                     exposed: Sequence[str] | None = None):
    """An arm callable for ``harness_v3._run_v3``: a fresh verified isolated process for every universe. Each
    process's outside verification is appended to ``checks`` (the run record keeps them)."""
    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> Mapping[str, Any]:
        host = IsolatedProposerHost(hidden, env=env, timeout=timeout, exposed=exposed)
        try:
            checks.append({"universe_id": card["universe_id"], **host.outside})
            return host.propose(spec, card, seed, client)
        finally:
            host.close()
    return arm


__all__ = ["DEFAULT_HIDDEN", "ISOLATION_LABEL", "IsolatedProposerHost", "IsolationUnavailable", "WHITELIST_ROOT",
           "command", "exposures", "hidden_paths", "inspect", "per_universe_arm", "support", "verified"]
