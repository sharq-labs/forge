"""Genesis-lite v0.3 D5-A1b: the in-container observation probe (stdlib only; run as ``python -I container_probe.py``).

It runs as the card's process in a card container, reads one JSON configuration line from stdin, prints one JSON
observation line, then waits for one more stdin line so that the operator can read the container's mount table from
the host while the container is alive, and exits.

Observed: the raw and parsed ``/proc/self/mountinfo``; per declared private mount a canary (phase A writes a fresh
256-bit token with O_EXCL, fsyncs it and reads it back; later phases look for the token card A wrote at the identical
path), every open attributed to its mount by ``/proc/self/fdinfo`` ``mnt_id``; capability sets and NoNewPrivs; whether
the source tree and the Python environment can be opened for writing (nothing is written); whether the network
targets are reachable; the network interfaces; the path environment and working directory; ``/run/.containerenv``.
Canaries go only into declared mounts of an allowed filesystem type, never into a device or pseudo-file.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import pathlib
import secrets
import socket
import sys

try:
    from . import container_evidence as contract
except ImportError:                       # run as a script under -I (no script directory on sys.path): load by path
    _spec = importlib.util.spec_from_file_location("container_evidence",
                                                   pathlib.Path(__file__).with_name("container_evidence.py"))
    contract = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(contract)    # the same parser as the validator


def fd_mount_id(fd: int) -> str:
    fields = dict(line.split(":", 1) for line in pathlib.Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
                  if ":" in line)
    return fields["mnt_id"].strip()


def observe_marker(directory: str, marker: str, phase: str, token: str, expected_mount: str) -> dict:
    result = {"path": str(pathlib.PurePosixPath(directory) / marker), "expected_mount": expected_mount,
              "token": token, "read": "NOT_PROBED", "write": "NOT_ATTEMPTED"}
    fd = None
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        actual = fd_mount_id(fd)
        result["actual_mount"] = actual
        if actual != expected_mount:
            result["read"] = "OBSCURED_MOUNT"
            return result
        try:
            f = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                result["read_mount"] = fd_mount_id(f)
                result["seen"] = os.read(f, 4096).hex()
                result["read"] = "READ_OK"
            finally:
                os.close(f)
        except FileNotFoundError:
            result["read"] = "READ_ABSENT"
        except OSError as exc:
            result.update(read="READ_ERROR", error=repr(exc))
            return result
        if phase == "A":
            f = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                result["write_mount"] = fd_mount_id(f)
                payload = bytes.fromhex(token)
                if os.write(f, payload) != len(payload):
                    raise OSError("short canary write")
                os.fsync(f)
            finally:
                os.close(f)
            f = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                result["readback_mount"] = fd_mount_id(f)
                result["readback"] = os.read(f, 4096).hex()
            finally:
                os.close(f)
            result["write"] = ("WRITE_OK" if result["readback"] == token and result["write_mount"] == expected_mount
                               == result["readback_mount"] else "READBACK_ERROR")
    except OSError as exc:
        result.update(error=repr(exc), write="WRITE_ERROR" if phase == "A" else "NOT_ATTEMPTED")
        if result["read"] == "NOT_PROBED":
            result["read"] = "READ_ERROR"
    finally:
        if fd is not None:
            os.close(fd)
    return result


def _write_probe(path: str) -> str:
    """READ_ONLY only for EROFS: a permission error says nothing about the mount."""
    try:
        fd = os.open(path, os.O_WRONLY)
    except OSError as exc:
        return "READ_ONLY" if exc.errno == errno.EROFS else f"ERROR_{errno.errorcode.get(exc.errno, exc.errno)}"
    os.close(fd)
    return "WRITABLE"


def _reach(address) -> str:
    try:
        with socket.create_connection((address[0], int(address[1])), timeout=1.0):
            return "REACHED"
    except OSError:
        return "REFUSED"


def _containerenv() -> dict:
    out = {}
    try:
        for line in pathlib.Path("/run/.containerenv").read_text().splitlines():
            key, eq, value = line.partition("=")
            if eq:
                out[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return out


def pid_namespace(proc: str = "/proc") -> dict:
    """What a card sees of its PID namespace THROUGH ``proc``. NSpid lists one PID per namespace from the namespace of
    that procfs mount down to the reader's; the card's own procfs shows exactly ["1"] for the card's PID 1, a host
    procfs shows the host PID first."""
    status = dict(line.split(":", 1) for line in pathlib.Path(proc, "self", "status").read_text().splitlines()
                  if ":" in line)
    return {"pid": os.getpid(), "nspid": status.get("NSpid", "").split(), "ns": os.readlink(f"{proc}/self/ns/pid"),
            "visible_processes": sum(1 for e in os.listdir(proc) if e.isdigit())}


def probe(config: dict) -> dict:
    if config.get("pid_probe_path"):                  # the positive control: a host procfs the operator bound in
        return {"pid_namespace": pid_namespace(config["pid_probe_path"])}
    raw = pathlib.Path("/proc/self/mountinfo").read_text()
    mounts = contract.parse_mountinfo(raw)
    allowed = tuple(config.get("write_fstypes", ("tmpfs",)))
    canaries = []
    for target in config["targets"]:
        rows = [r for r in mounts if r["target"] == target]
        if len(rows) != 1 or "rw" not in rows[0]["options"] or rows[0]["fstype"] not in allowed:
            canaries.append({"target": target, "path": str(pathlib.PurePosixPath(target) / config["marker"]),
                             "token": (config.get("tokens") or {}).get(target), "read": "UNPROBEABLE",
                             "write": "NOT_ATTEMPTED", "rows": [r["id"] for r in rows]})
            continue
        token = secrets.token_hex(32) if config["phase"] == "A" else (config.get("tokens") or {}).get(target)
        if not token:
            canaries.append({"target": target, "read": "NOT_PROBED", "write": "NOT_ATTEMPTED"})
            continue
        canaries.append({"target": target, **observe_marker(target, config["marker"], config["phase"], token,
                                                            rows[0]["id"])})
    status = {}
    for line in pathlib.Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in (*contract.CAPABILITY_FIELDS, "NoNewPrivs"):
            status[key] = value.strip()
    return {"mountinfo": raw, "mounts": mounts, "canaries": canaries, "status": status,
            "writes": {name: _write_probe(path) for name, path in config.get("read_only_files", {}).items()},
            "network": {**{label: _reach(address) for label, address in config.get("network_targets", {}).items()},
                        "interfaces": sorted(p.name for p in pathlib.Path("/sys/class/net").iterdir())},
            "paths": {**{k: os.environ.get(k) for k in contract.PATH_KEYS}, "workdir": os.getcwd()},
            "containerenv": _containerenv(), "uid": os.getuid(), "pid_namespace": pid_namespace()}


def main() -> int:
    config = json.loads(sys.stdin.readline())
    sys.stdout.write(json.dumps(probe(config), sort_keys=True) + "\n")
    sys.stdout.flush()
    sys.stdin.readline()                      # the operator reads the host-side mount view meanwhile
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
