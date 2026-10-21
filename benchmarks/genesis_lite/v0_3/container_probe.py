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

The device observation (STATELESS_DEVICE, :mod:`.device_contract`) is taken FIRST, before anything else is opened:
the descriptor inventory, every entry of ``/dev`` (lstat, link targets, mount ids through ``O_PATH``), Podman's
``/dev/null`` masks, a walk of everything the card can traverse outside ``/proc``, ``/sys`` and ``/dev`` for device
nodes and symlinks to devices, the terminal state, the kernel RNG counters, and, when the operator asks, one side of a
selected-message trial: an encoder writes the operator's message to every device and tries every RNG ioctl with it; a
decoder reads from every device and looks for either message.
"""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import pathlib
import secrets
import socket
import stat
import struct
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


#: the kernel RNG ioctls (linux/random.h): the read-only counter, and the ones that credit, set, clear or reseed
RNDGETENTCNT = 0x80045200
RNG_IOCTLS = {"RNDADDTOENTCNT": 0x40045201, "RNDADDENTROPY": 0x40085203, "RNDZAPENTCNT": 0x5204,
              "RNDCLEARPOOL": 0x5206, "RNDRESEEDCRNG": 0x5207}
WINDOW = 8


def _errno(exc: OSError) -> str:
    return errno.errorcode.get(exc.errno, str(exc.errno))


def fd_inventory() -> dict:
    """Every open descriptor and what it points at; the listing's own directory descriptor is one of them."""
    out = {}
    with os.scandir("/proc/self/fd") as entries:
        for entry in entries:
            try:
                out[entry.name] = os.readlink(entry.path)
            except OSError as exc:
                out[entry.name] = "ERROR_" + _errno(exc)
    return out


def node(path: str) -> dict:
    """lstat facts of one path; for anything but a symlink also the mount it is on (an O_PATH descriptor opens no
    device)."""
    s = os.lstat(path)
    kind = ("chr" if stat.S_ISCHR(s.st_mode) else "blk" if stat.S_ISBLK(s.st_mode) else "lnk" if stat.S_ISLNK(s.st_mode)
            else "dir" if stat.S_ISDIR(s.st_mode) else "reg" if stat.S_ISREG(s.st_mode) else "other")
    out = {"type": kind, "perm": stat.S_IMODE(s.st_mode), "uid": s.st_uid, "gid": s.st_gid,
           "dev": f"{os.major(s.st_dev)}:{os.minor(s.st_dev)}", "ino": s.st_ino, "nlink": s.st_nlink, "size": s.st_size,
           "atime_ns": s.st_atime_ns, "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns}
    if kind in ("chr", "blk"):
        out["rdev"] = f"{os.major(s.st_rdev)}:{os.minor(s.st_rdev)}"
    if kind == "lnk":
        out["link"] = os.readlink(path)
        return out
    out["realpath"] = os.path.realpath(path)
    fd = os.open(path, os.O_PATH | os.O_NOFOLLOW)
    try:
        out["mnt"] = fd_mount_id(fd)
    finally:
        os.close(fd)
    return out


def device_walk(top: str = "/", skip: tuple = ("/proc", "/sys", "/dev")) -> dict:
    """Every device node and every symlink to a device the card can reach outside ``skip`` (a directory the card cannot
    read is one it cannot traverse either: counted, not entered)."""
    entries, devices, links, unreadable = 0, [], [], []
    for root, dirs, files in os.walk(top, onerror=lambda exc: unreadable.append(exc.filename)):
        if root == top:
            dirs[:] = [d for d in dirs if os.path.join(root, d) not in skip]
        for name in dirs + files:
            path = os.path.join(root, name)
            try:
                s = os.lstat(path)
            except OSError:
                continue
            entries += 1
            if stat.S_ISCHR(s.st_mode) or stat.S_ISBLK(s.st_mode):
                devices.append(path)
            elif stat.S_ISLNK(s.st_mode):
                try:
                    target = os.stat(path)
                except OSError:
                    continue
                if stat.S_ISCHR(target.st_mode) or stat.S_ISBLK(target.st_mode):
                    links.append([path, os.path.realpath(path)])
    return {"entries": entries, "devices": devices, "device_links": links, "unreadable": len(unreadable)}


def tty_state() -> dict:
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        os.close(fd)
        opened = "OPENED"
    except OSError as exc:
        opened = _errno(exc)
    try:
        fd = os.open("/dev/ptmx", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        os.close(fd)
        ptmx = "OPENED"
    except OSError as exc:
        ptmx = _errno(exc)
    fields = pathlib.Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return {"open": opened, "isatty": [os.isatty(i) for i in (0, 1, 2)], "tty_nr": int(fields[4]),
            "tpgid": int(fields[5]), "pid": os.getpid(), "sid": os.getsid(0), "pts": os.path.lexists("/dev/pts"),
            "ptmx": ptmx}


def rng_state() -> dict:
    import fcntl  # noqa: PLC0415 - Linux only; the probe runs in a Linux card

    out = {k: int(pathlib.Path(f"/proc/sys/kernel/random/{k}").read_text()) for k in ("entropy_avail", "poolsize")}
    fd = os.open("/dev/urandom", os.O_RDONLY)
    try:
        out["getentcnt"] = struct.unpack("i", fcntl.ioctl(fd, RNDGETENTCNT, b"\0" * 4))[0]
    finally:
        os.close(fd)
    return out


def _found(data: bytes, message: bytes) -> bool:
    return any(message[i:i + WINDOW] in data for i in range(len(message) - WINDOW + 1))


def _ioctl(fd: int, request: int, arg) -> str:
    import fcntl  # noqa: PLC0415 - Linux only; the probe runs in a Linux card

    try:
        fcntl.ioctl(fd, request, arg)
        return "OK"
    except OSError as exc:
        return _errno(exc)


def encode(paths: list, message_hex: str, rng: list) -> dict:
    """One encoder: write the selected message to every path (and try every RNG ioctl with it); the node before and
    after. A path that cannot be opened records its errno."""
    message, out = bytes.fromhex(message_hex), {}
    for path in paths:
        try:
            before = node(path)
            fd = os.open(path, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            out[path] = {"open": _errno(exc)}
            continue
        entry = {"before": before}
        try:
            try:
                entry["write"] = os.write(fd, message)
            except OSError as exc:
                entry["write"] = _errno(exc)
            if path in rng:
                entry["ioctls"] = {name: _ioctl(fd, request, struct.pack("ii", len(message) * 8, len(message)) + message
                                                if name == "RNDADDENTROPY" else struct.pack("i", len(message) * 8)
                                                if name == "RNDADDTOENTCNT" else 0)
                                   for name, request in RNG_IOCTLS.items()}
        finally:
            os.close(fd)
        entry["after"] = node(path)
        out[path] = entry
    return out


def decode(paths: list, messages_hex: list, read_size: int) -> dict:
    """One decoder: read up to ``read_size`` bytes from every path and look for either message."""
    messages, out = [bytes.fromhex(m) for m in messages_hex], {}
    for path in paths:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            out[path] = {"open": _errno(exc)}
            continue
        chunks, total = [], 0
        try:
            while total < read_size:
                chunk = os.read(fd, min(65536, read_size - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        finally:
            os.close(fd)
        data = b"".join(chunks)
        out[path] = {"bytes": len(data), "all_zero": not data.strip(b"\0") and bool(data),
                     "found": [_found(data, m) for m in messages], "sha256": hashlib.sha256(data).hexdigest(),
                     "node": node(path)}
    return out


def device_observation(config: dict, fds: dict) -> dict:
    """What the STATELESS_DEVICE contract reads (``config``: the operator's ``devices`` entry)."""
    tree = {}
    for name in sorted(os.listdir("/dev")):
        tree[name] = node("/dev/" + name)
    aliases = {}
    for path in config.get("masked", ()):
        try:
            if stat.S_ISCHR(os.lstat(path).st_mode):
                aliases[path] = node(path)
        except OSError:
            pass
    out = {"contract": config.get("contract"), "fds": fds, "tree": tree, "aliases": aliases,
           "walk": device_walk() if config.get("walk", True) else None, "tty": tty_state(),
           "kernel": os.uname().release,
           "overflow": {k: int(pathlib.Path(f"/proc/sys/kernel/overflow{k}").read_text()) for k in ("uid", "gid")}}
    try:
        out["rng"] = rng_state()
    except OSError as exc:
        out["rng"] = {"error": _errno(exc)}
    channel = config.get("channel") or {}
    if channel.get("role") == "encode":
        out["channel"] = {"role": "encode", "message": channel["message"],
                          "paths": encode(channel["paths"], channel["message"], config.get("rng", ()))}
    elif channel.get("role") == "decode":
        out["channel"] = {"role": "decode", "messages": channel["messages"],
                          "paths": decode(channel["paths"], channel["messages"], int(config["read_size"]))}
    return out


def probe(config: dict) -> dict:
    fds = fd_inventory()                              # before the probe opens anything of its own
    if config.get("pid_probe_path"):                  # the positive control: a host procfs the operator bound in
        return {"pid_namespace": pid_namespace(config["pid_probe_path"])}
    devices = device_observation(config["devices"], fds) if config.get("devices") else None
    if config.get("devices_only"):                    # the tty positive control
        return {"devices": devices}
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
            "containerenv": _containerenv(), "uid": os.getuid(), "pid_namespace": pid_namespace(), "devices": devices}


def main() -> int:
    if sys.argv[1:2] == ["--config"]:         # the tty control: its stdin is a terminal, so the config is an argument
        sys.stdout.write(json.dumps(probe(json.loads(sys.argv[2])), sort_keys=True) + "\n")
        sys.stdout.flush()
        return 0
    config = json.loads(sys.stdin.readline())
    sys.stdout.write(json.dumps(probe(config), sort_keys=True) + "\n")
    sys.stdout.flush()
    sys.stdin.readline()                      # the operator reads the host-side mount view meanwhile
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
