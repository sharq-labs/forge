"""OS-isolated proposer processes for Genesis-lite v0.4 (owner decisions D3 and D11, 2026-10-30; gaps G5, G14, FDA-18).

Every UNIVERSE gets a fresh proposer process (D11: a proposer never sees a second card, so answer exclusivity inside a
campaign cannot be exploited by elimination). The process speaks the existing ``proposer_host`` protocol over its
stdin/stdout pipes -- the operator keeps the escrow, the presentation and the query cap, exactly as in the
``proposer_process`` mode -- and runs in another security domain, built with the mechanism of
:mod:`engcore.blindfold.isolation`:

* private mount, pid (own /proc), network (loopback only), ipc and uts namespaces (``unshare``);
* an empty mode-000 tmpfs over every HIDDEN path (by default /home, /root, /mnt, /var/tmp, /srv, plus the operator's
  root-file directory, output directory and every ``pilot_results`` directory of the tree), and a fresh private /tmp;
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
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from engcore.blindfold.isolation import DISCOVERY_UID

from . import harness as h2

ISOLATION_LABEL = "os_isolated_per_universe"
DEFAULT_HIDDEN = ("/home", "/root", "/mnt", "/var/tmp", "/srv")
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


def hidden_paths(extra: Sequence[str | os.PathLike[str]] = ()) -> tuple[str, ...]:
    """Existing absolute directories to hide: the defaults, every ``pilot_results`` directory of this tree, ``extra``.
    A path that is not an existing directory refuses (a silently skipped hide would be a silent leak)."""
    out = [p for p in DEFAULT_HIDDEN if os.path.isdir(p)]
    out += [str(p) for p in sorted(_ROOT.glob("benchmarks/**/pilot_results")) if p.is_dir()]
    for p in extra:
        path = pathlib.Path(p).resolve()
        if not path.is_dir():
            raise IsolationUnavailable(f"hidden path {path} is not an existing directory")
        out.append(str(path))
    if any(_ROOT.resolve() == pathlib.Path(p) or _ROOT.resolve().is_relative_to(p) for p in out):
        raise IsolationUnavailable("a hidden path contains the code tree itself; the proposer could not run")
    return tuple(dict.fromkeys(out))


def command(hidden: Sequence[str], env: Mapping[str, str], python: str = sys.executable) -> list[str]:
    """The launcher command: namespaces, tmpfs hides, a private /tmp, then the uid switch and a clean environment."""
    hides = " && ".join(f"mount -t tmpfs -o size=64k,mode=000 tmpfs {shlex.quote(p)}" for p in hidden)
    clean = " ".join(shlex.quote(f"{k}={v}") for k, v in sorted({"PATH": "/usr/bin:/bin", "HOME": "/tmp", **THREAD_ENV,
                                                                    **dict(env)}.items()))
    inner = (f"{hides + ' && ' if hides else ''}mount -t tmpfs -o size=1g,mode=1777 tmpfs /tmp && cd /tmp && "
             f"exec setpriv --reuid={DISCOVERY_UID} --regid={DISCOVERY_UID} --clear-groups --inh-caps=-all "
             f"--bounding-set=-all --no-new-privs -- /usr/bin/env -i {clean} {shlex.quote(python)} -I "
             f"{shlex.quote(str(_HOST))} {shlex.quote(str(_ROOT))} {shlex.quote(str(_ROOT / 'src'))}")
    return ["unshare", "--mount", "--pid", "--fork", "--net", "--ipc", "--uts", "--mount-proc", "--", "/bin/sh", "-c",
            inner]


def _leaf(pid: int) -> int:
    from engcore.blindfold.isolation import _leaf as leaf  # noqa: PLC0415 - the launcher's own /proc walk
    return leaf(pid)


def inspect(pid: int, hidden: Sequence[str]) -> dict[str, Any]:
    """What the launcher sees of the proposer process from OUTSIDE (never the process's own report)."""
    status = dict(line.split(":", 1) for line in open(f"/proc/{pid}/status").read().splitlines() if ":" in line)
    ids = lambda k: [int(x) for x in status.get(k, "").split()]  # noqa: E731
    caps = {k: int(status.get(k, "f").strip() or "f", 16) for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}
    ns = {n: os.readlink(f"/proc/{pid}/ns/{n}") != os.readlink(f"/proc/self/ns/{n}") for n in ("mnt", "pid", "net", "ipc", "uts")}
    mounts = [ln.split() for ln in open(f"/proc/{pid}/mountinfo").read().splitlines()]
    tmpfs = {m[4] for m in mounts if "-" in m and m[m.index("-") + 1] == "tmpfs"}
    return {"inspected": True, "uid": ids("Uid"), "gid": ids("Gid"), "groups": ids("Groups"), "caps": caps,
            "no_new_privs": status.get("NoNewPrivs", "").strip() == "1", "private_namespaces": ns,
            "hidden": {p: p in tmpfs for p in hidden}, "private_tmp": "/tmp" in tmpfs}


def verified(o: Mapping[str, Any]) -> bool:
    return bool(o.get("inspected") and o["uid"] == [DISCOVERY_UID] * 4 and o["gid"] == [DISCOVERY_UID] * 4
                and not o["groups"] and not any(o["caps"].values()) and o["no_new_privs"]
                and all(o["private_namespaces"].values()) and o["hidden"] and all(o["hidden"].values())
                and o["private_tmp"])


class IsolatedProposerHost(h2.ProposerHost):
    """``ProposerHost``'s protocol, in another security domain; verified from outside before any card is sent."""

    def __init__(self, hidden: Sequence[str], *, env: Mapping[str, str] | None = None, timeout: float = 600.0,
                 python: str = sys.executable) -> None:
        ok, why = support()
        if not ok:
            raise IsolationUnavailable(why)
        self._dir = None
        self._timeout = timeout
        self._proc = subprocess.Popen(command(hidden, env or {}, python), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, cwd="/", env={"PATH": "/usr/bin:/bin"}, bufsize=0,
                                      start_new_session=True)
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        hello = self._recv()
        expected = str((_ROOT / "src" / "engcore" / "__init__.py").resolve())
        if hello.get("op") != "hello" or str(pathlib.Path(hello.get("engcore", "")).resolve()) != expected:
            self.close()
            raise IsolationUnavailable(f"the isolated proposer did not import this tree's engcore: {hello}")
        self.outside = inspect(_leaf(self._proc.pid), hidden)
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


def per_universe_arm(spec: str, hidden: Sequence[str], checks: list[dict[str, Any]], *,
                     env: Mapping[str, str] | None = None, timeout: float = 600.0):
    """An arm callable for ``harness_v3._run_v3``: a fresh verified isolated process for every universe. Each
    process's outside verification is appended to ``checks`` (the run record keeps them)."""
    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> Mapping[str, Any]:
        host = IsolatedProposerHost(hidden, env=env, timeout=timeout)
        try:
            checks.append({"universe_id": card["universe_id"], **host.outside})
            return host.propose(spec, card, seed, client)
        finally:
            host.close()
    return arm


__all__ = ["DEFAULT_HIDDEN", "ISOLATION_LABEL", "IsolatedProposerHost", "IsolationUnavailable", "command",
           "hidden_paths", "inspect", "per_universe_arm", "support", "verified"]
