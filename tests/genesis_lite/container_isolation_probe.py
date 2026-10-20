"""Test-only mount observation; device and pseudo-files never receive canaries."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sys


def decode(value):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def parse_mountinfo(raw):
    rows = []
    for line in raw.splitlines():
        fields = line.split()  # decode AFTER tokenization (spaces may be escaped)
        try:
            sep = fields.index("-")
            if sep < 6 or len(fields) != sep + 4:
                raise ValueError("field count")
            int(fields[0]); int(fields[1])
            if not re.fullmatch(r"[0-9]+:[0-9]+", fields[2]):
                raise ValueError("device")
            row = dict(id=fields[0], parent=fields[1], device=fields[2],
                       root=decode(fields[3]), target=decode(fields[4]),
                       options=fields[5].split(","), optional=fields[6:sep],
                       fstype=fields[sep+1], source=decode(fields[sep+2]),
                       super_options=fields[sep+3].split(","))
            if not row["target"].startswith("/") or not row["root"].startswith("/"):
                raise ValueError("nonabsolute path")
            if ("ro" in row["options"]) == ("rw" in row["options"]):
                raise ValueError("ambiguous view writeability")
        except (ValueError, IndexError) as exc:
            raise ValueError("MALFORMED_MOUNTINFO: " + line) from exc
        if any(r["id"] == row["id"] for r in rows):
            raise ValueError("DUPLICATE_MOUNT_ID")
        rows.append(row)
    if not rows:
        raise ValueError("EMPTY_MOUNTINFO")
    return rows


def fd_mount_id(fd):
    fields = dict(line.split(":", 1) for line in Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
                  if ":" in line)
    return fields["mnt_id"].strip()


def observe_marker(directory, marker, phase, token, expected_mount):
    result = dict(path=str(Path(directory)/marker), expected_mount=expected_mount,
                  token=token, read="NOT_PROBED", write="NOT_ATTEMPTED")
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
            f = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=fd)
            try:
                result["write_mount"] = fd_mount_id(f)
                if result["write_mount"] != expected_mount:
                    result["write"] = "MOUNT_MISMATCH"
                    return result
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
                result["write"] = ("WRITE_OK" if result["readback"] == token and
                                   result["readback_mount"] == expected_mount else "READBACK_ERROR")
            finally:
                os.close(f)
    except OSError as exc:
        result.update(error=repr(exc), write="WRITE_ERROR" if phase == "A" else "NOT_ATTEMPTED")
        if result["read"] == "NOT_PROBED":
            result["read"] = "READ_ERROR"
    finally:
        if fd is not None:
            os.close(fd)
    return result


def probe(config):
    raw = Path("/proc/self/mountinfo").read_text()
    mounts = parse_mountinfo(raw)
    for row in mounts:
        row["canary"] = "READ_ONLY" if "ro" in row["options"] else "NOT_PROBED"
        if "rw" not in row["options"] or not config.get("write_canaries"):
            continue
        target = row["target"]
        # No device endpoint or pseudo-filesystem writes, including /dev itself.
        safe = (row["fstype"] in ("tmpfs", "overlay", "ext4") and
                (not target.startswith("/dev") or target == "/dev/shm") and
                Path(target).is_dir())
        if not safe:
            row["canary"] = "UNPROBEABLE"
            continue
        token = (secrets.token_hex(32) if config["phase"] == "A" else
                 config.get("tokens", {}).get(target))
        if not token:
            row["canary"] = "MISSING_A_TOKEN"
            continue
        result = observe_marker(target, config["marker"], config["phase"], token, row["id"])
        row["observation"] = result
        row["canary"] = result["write"] if config["phase"] == "A" else result["read"]
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
                  if ":" in line)
    writes = {}
    for name, filename in config.get("read_only_files", {}).items():
        try:
            fd = os.open(filename, os.O_WRONLY)
            os.close(fd)
            writes[name] = "WRITABLE"
        except OSError as exc:
            writes[name] = type(exc).__name__
    network = {}
    for label, address in config.get("network_targets", {}).items():
        try:
            with socket.create_connection(tuple(address), timeout=0.2):
                network[label] = "REACHED"
        except OSError as exc:
            network[label] = type(exc).__name__
    paths = {name: os.environ.get(name) for name in
             ("HOME", "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX")}
    return dict(mountinfo=raw, mounts=mounts, status=status, writes=writes,
                network=network, interfaces=sorted(p.name for p in Path("/sys/class/net").iterdir()),
                environment=paths, cwd=os.getcwd(), uid=os.getuid(), machine=socket.gethostname())


if __name__ == "__main__":
    print(json.dumps(probe(json.loads(sys.argv[1])), sort_keys=True))
