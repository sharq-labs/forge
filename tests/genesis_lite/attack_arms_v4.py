"""Hostile proposers for the v0.4 per-universe OS isolation tests (gaps FDA-19, G5, G14). Importable as
``tests.genesis_lite.attack_arms_v4:<function>`` so the same attack runs inside the isolated proposer process."""

from __future__ import annotations

import glob
import json
import os
import socket
from typing import Any, Mapping

#: places an operator keeps secrets in a v0.4 run (root file, outputs, pilot results, home directories, drvfs)
PROBES = ("/root/*", "/root/*/*", "/home/*", "/home/*/*", "/home/*/*/*", "/mnt/*", "/mnt/*/*", "/var/tmp/*", "/srv/*",
          "/opt/*", "/opt/*/*",
          "/opt/*/benchmarks/genesis_lite/pilot_results/*", "/opt/*/benchmarks/genesis_lite/pilot_results/*/*",
          "/tmp/*", "/proc/1/environ")


def _answer(card: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": json.dumps(report, sort_keys=True)}


def read_secrets(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """List and read whatever the operator might have left readable; report names and the first bytes read."""
    seen, read = [], {}
    for pattern in PROBES:
        for path in glob.glob(pattern):
            seen.append(path)
            if os.path.isfile(path):
                try:
                    with open(path, "rb") as fh:
                        read[path] = fh.read(64).decode("latin-1")
                except OSError as exc:
                    read[path] = f"refused:{type(exc).__name__}"
    return _answer(card, {"seen": sorted(seen)[:200], "read": read, "uid": os.getuid(), "ppid": os.getppid(),
                          "env": sorted(os.environ)})


def reach_network(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Try to open an outbound connection (no DNS: a literal address)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(("1.1.1.1", 53))
        outcome = "connected"
    except OSError as exc:
        outcome = f"refused:{type(exc).__name__}:{exc.errno}"
    finally:
        s.close()
    return _answer(card, {"network": outcome})


def see_operator(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Enumerate visible processes and try to read any other process's memory map (the operator's included)."""
    pids = sorted(int(p) for p in os.listdir("/proc") if p.isdigit())
    readable, readable_mem, readable_fds = [], [], []
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            with open(f"/proc/{pid}/maps", "rb") as fh:
                fh.readline()
            readable.append(pid)
        except OSError:
            pass
        try:
            with open(f"/proc/{pid}/mem", "rb"):
                readable_mem.append(pid)
        except OSError:
            pass
        try:
            os.listdir(f"/proc/{pid}/fd")
            readable_fds.append(pid)
        except OSError:
            pass
    return _answer(card, {"visible_pids": pids, "readable_maps": readable, "openable_mem": readable_mem,
                          "listable_fds": readable_fds})


def honest(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """One observation, then a refusal: shows the observe relay works through the isolated process."""
    settings = {x["name"]: float(x["range"][0]) for x in card["inputs"] if x.get("settable")}
    client.observe(card["universe_id"], settings, query_id="honest-1")
    return {"universe_id": card["universe_id"], "answer": "insufficient_evidence", "rationale": "one observation"}


MARK = ".forge-v4-persistence-mark"
_SKIP = ("/proc", "/sys")


def _walk_dirs():
    for top, dirs, _files in os.walk("/", onerror=lambda e: None):
        if top.startswith(_SKIP):
            dirs[:] = []
            continue
        yield top


_KEY_SPEC_USER_KEYRING, _SYS_ADD_KEY, _SYS_KEYCTL, _KEYCTL_SEARCH = -4, 248, 250, 10    # x86_64


def _libc():
    import ctypes  # noqa: PLC0415
    return ctypes.CDLL(None, use_errno=True)


_KEY_SPEC_SESSION_KEYRING = -3
_RINGS = {"keyring:@u": _KEY_SPEC_USER_KEYRING, "keyring:@s": _KEY_SPEC_SESSION_KEYRING}


def _leave_keys(payload: bytes) -> list[str]:
    """A kernel key on this uid's user keyring (it outlives the process, re-review M3) and on the session keyring
    (inherited across fork/exec, review 2026-10-31 M-a)."""
    return [name for name, ring in _RINGS.items()
            if _libc().syscall(_SYS_ADD_KEY, b"user", MARK.encode(), payload, len(payload), ring) > 0]


def _found_keys() -> list[str]:
    return [name for name, ring in _RINGS.items()
            if _libc().syscall(_SYS_KEYCTL, _KEYCTL_SEARCH, ring, b"user", MARK.encode(), 0) > 0]


def nested_namespace(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Try to create a nested user namespace (full capabilities inside it) and, in it, to unmount a hide (M-b)."""
    import ctypes  # noqa: PLC0415
    libc = ctypes.CDLL(None, use_errno=True)
    created = libc.unshare(0x10000000) == 0                                  # CLONE_NEWUSER
    errno = ctypes.get_errno()
    unmounted = created and libc.unshare(0x00020000) == 0 and libc.umount2(b"/home", 2) == 0    # CLONE_NEWNS, MNT_DETACH
    return _answer(card, {"nested_user_namespace": created, "errno": errno, "home_unmounted": bool(unmounted)})


def leave_marks(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Write a mark into EVERY directory this process can write (the persistence half of review finding 1), and a
    key on the uid's kernel keyring."""
    written = _leave_keys(card["universe_id"].encode())
    for d in _walk_dirs():
        if os.access(d, os.W_OK):
            try:
                with open(os.path.join(d, MARK), "w") as fh:
                    fh.write(card["universe_id"])
                written.append(d)
            except OSError:
                pass
    return _answer(card, {"written": sorted(written)})


def find_marks(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    found = [d for d in _walk_dirs() if os.path.exists(os.path.join(d, MARK))]
    found += _found_keys()
    return _answer(card, {"found": sorted(found)})
