"""Genesis-lite v0.3: the D5-A1b container evidence contract (owner, 2026-10-21), as a pure validator.

D5-A1b runs every proposer card in a brand-new rootless Podman container (:mod:`.isolation`). A deployment counts as
verified for N-1 only when per-card evidence shows, for three fresh cards A, B and C and two positive controls:

* the complete mount inventory, three times: the raw ``/proc/self/mountinfo`` the card saw, its parsed rows, and the
  runtime view the operator read from the host (``/proc/<container pid>/mountinfo``), all reconciled row for row;
* every writable mount is a declared private tmpfs (``writable_targets``) and nothing else; the source tree and the
  Python environment are read-only binds; no writable mount is shared, host-backed, Windows-backed, stacked under
  another mount or undeclared. A writable device or pseudo-file mount is blocking (owner, 2026-10-21: no device-node
  exemption);
* every READ-ONLY host-backed mount is one of: a declared ``--volume`` bind whose source is the source tree, the
  Python environment or a path inside them; Podman's own userdata files (:data:`USERDATA_TARGETS`); or Podman's
  read-only ``/dev/null`` masks over ``/proc`` and ``/sys`` pseudo-files. Any other host path visible to a card, even
  read-only (``/``, a socket directory, a default volume), is blocking;
* card A wrote a fresh token into each private mount (O_EXCL, fsync, readback, mount-attributed by the open file
  descriptor) and fresh cards B and C, at the identical path, found it ABSENT;
* a deliberately shared volume IS seen across two containers (the probe has power), and a host listener the cards
  cannot reach IS reachable from the host (the network probe has power);
* the container was new (distinct ids), ran the pinned image, had no capabilities, no-new-privileges, private IPC, no
  network but loopback, was removed after the card and could not be restarted;
* the card's recorded provenance equals the expected deployment: image, Podman version, rootless mode, launcher,
  probe, Containerfile and source revision (a full commit id). What makes the expected launcher, probe and source the
  preregistered ones is the identity check of the formal driver, not this validator.

:func:`validate_container_evidence` returns ``{"status": "PASS", "reasons": []}`` or ``{"status": "BLOCKED",
"reasons": [...], "details": [...]}``. It never raises on malformed evidence, and it is deterministic. It decides
nothing about the twelve attack channels (:mod:`.deployment_attacks`); a deployment needs both.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

SCHEMA = "checkpoint2.container_evidence.contract/2"
PHASES = ("A", "B", "C")
CAPABILITY_FIELDS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
PATH_KEYS = ("HOME", "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX")
ROW_KEYS = ("id", "parent", "device", "root", "target", "options", "optional", "fstype", "source", "super_options")
RUNTIME_KEYS = ROW_KEYS[:-1]
CARD_KEYS = ("phase", "id", "provenance", "mounts", "mountinfo", "runtime_mounts", "argv", "paths", "status",
             "actual_image_digest", "actual_image_id", "ipc", "network", "writes", "canaries", "restart", "removed")
EXPECTED_KEYS = ("source_sha", "image_digest", "image_id", "podman_version", "containerfile_sha256",
                 "launcher_sha256", "probe_sha256", "writable_targets", "source_host", "venv_host", "source_path",
                 "venv_path", "rootless")
CONTROL_KEYS = ("a_write", "a_token", "b_read", "b_seen", "a_mount", "b_mount", "a_actual", "b_actual", "a_path",
                "b_path", "a_image_digest", "b_image_digest")
#: the exact options every card container is created with (D5-A1b); a missing one is a configuration mismatch
REQUIRED_FLAGS = ("--pull=never", "--rm", "--read-only", "--read-only-tmpfs=false",
                  "--security-opt=proc-opts=ro,nosuid,nodev,noexec", "--ipc=private", "--network=none",
                  "--cap-drop=ALL", "--security-opt=no-new-privileges", "--userns=keep-id")
#: options that may appear besides the required ones; anything else (e.g. --privileged, --cap-add) is refused
OPTIONAL_FLAGS = ("-i", "--interactive", "--log-driver=none")
DEV_READ_ONLY = "type=tmpfs,destination=/dev,ro=true"
VALUED = ("--tmpfs", "--volume", "--env", "--workdir", "--name", "--label", "--mount")
TMPFS_OPTIONS = "rw,nosuid,nodev,mode=1777"
EXTRA_ENV = ("PYTHONDONTWRITEBYTECODE",)
WINDOWS_FSTYPES = ("9p", "drvfs", "v9fs")
DEVICE_FSTYPES = ("devtmpfs", "devpts", "mqueue")
CGROUP_FSTYPES = ("cgroup", "cgroup2")
#: Podman's own per-container files, bound read-only from the container's userdata directory
USERDATA_TARGETS = ("/etc/hosts", "/etc/hostname", "/etc/resolv.conf", "/run/.containerenv")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


def _decode(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def parse_mountinfo(raw: str) -> list[dict[str, Any]]:
    """Rows of ``/proc/<pid>/mountinfo`` (proc(5)); escapes are decoded after tokenisation. ValueError on a malformed,
    duplicate or ambiguous row, or on an empty table."""
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        fields = line.split()
        try:
            sep = fields.index("-")
            if sep < 6 or len(fields) != sep + 4:
                raise ValueError("field count")
            int(fields[0])
            int(fields[1])
            if not re.fullmatch(r"[0-9]+:[0-9]+", fields[2]):
                raise ValueError("device")
            row = {"id": fields[0], "parent": fields[1], "device": fields[2], "root": _decode(fields[3]),
                   "target": _decode(fields[4]), "options": fields[5].split(","), "optional": fields[6:sep],
                   "fstype": fields[sep + 1], "source": _decode(fields[sep + 2]),
                   "super_options": fields[sep + 3].split(",")}
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


def _reconciled(row: Mapping[str, Any]) -> tuple[str, ...]:
    """The fields the card's and the operator's views must agree on. The one exception is the ``root`` of a
    cgroup filesystem. The kernel reports it relative to the READER's cgroup namespace (cgroup_namespaces(7)): "/"
    inside the card, the libpod scope path from the host. Every other field of that row, and every field of every
    other row, must match."""
    return tuple(k for k in RUNTIME_KEYS if not (k == "root" and row["fstype"] in CGROUP_FSTYPES))


def _within(path: Any, targets: list[str]) -> bool:
    return isinstance(path, str) and any(path == t or path.startswith(t.rstrip("/") + "/") for t in targets)


class _Findings:
    def __init__(self) -> None:
        self.reasons: set[str] = set()
        self.details: set[str] = set()

    def add(self, reason: str, detail: str) -> None:
        self.reasons.add(reason)
        self.details.add(f"{reason}: {detail}")


def _argv(card: Mapping[str, Any], expected: Mapping[str, Any], found: _Findings, phase: str) -> set[str] | None:
    """Check the launch command; return the container-side targets of its read-only binds (None if unparseable)."""
    argv = card["argv"]
    if not isinstance(argv, list) or len(argv) < 3 or not all(isinstance(a, str) for a in argv):
        found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: argv is not a list of strings")
        return None
    if argv[0].rsplit("/", 1)[-1] != "podman" or argv[1] not in ("run", "create"):
        found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: not a podman run/create command")
        return None
    image_at = next((i for i, a in enumerate(argv) if "@sha256:" in a and not a.startswith("-")), None)
    if image_at is None:
        found.add("IMAGE_DIGEST_MISMATCH", f"{phase}: no immutable image reference")
        return None
    if not argv[image_at].endswith("@" + str(expected["image_digest"])):
        found.add("IMAGE_DIGEST_MISMATCH", f"{phase}: image {argv[image_at]!r} is not the pinned digest")
    flags, valued, i = set(), [], 2
    while i < image_at:
        a = argv[i]
        name, eq, value = a.partition("=")
        if a in REQUIRED_FLAGS or a in OPTIONAL_FLAGS:
            flags.add(a)
            i += 1
        elif name in VALUED and eq:
            valued.append((name, value))
            i += 1
        elif a in VALUED and i + 1 < image_at:
            valued.append((a, argv[i + 1]))
            i += 2
        elif a.startswith("--ipc="):
            found.add("IPC_NOT_PRIVATE", f"{phase}: {a}")
            i += 1
        else:
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: option {a!r} is not part of the D5-A1b launch")
            i += 1
    for flag in REQUIRED_FLAGS:
        if flag not in flags:
            reason = "IPC_NOT_PRIVATE" if flag == "--ipc=private" else "RUNTIME_CONFIGURATION_MISMATCH"
            found.add(reason, f"{phase}: required option {flag} absent")
    targets = list(expected["writable_targets"])
    tmpfs = [v for n, v in valued if n == "--tmpfs"]
    for t in targets:
        if tmpfs.count(f"{t}:{TMPFS_OPTIONS}") != 1:
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: no single private tmpfs declaration for {t}")
    for v in tmpfs:
        if v.split(":", 1)[0] not in targets:
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: tmpfs for an undeclared target {v!r}")
    volumes = [v for n, v in valued if n == "--volume"]
    for host, path, label in ((expected["source_host"], expected["source_path"], "source"),
                              (expected["venv_host"], expected["venv_path"], "venv")):
        if f"{host}:{path}:ro" not in volumes:
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: the {label} is not bound read-only")
    bound: set[str] = set()
    kept = [str(expected["source_host"]), str(expected["venv_host"])]
    for v in volumes:
        parts = v.split(":")
        if len(parts) != 3 or parts[2] != "ro":
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: volume {v!r} is not a read-only host:target bind")
            continue
        if not _within(parts[0], kept):
            found.add("UNDECLARED_HOST_MOUNT", f"{phase}: volume source {parts[0]!r} is outside the kept trees")
        bound.add(parts[1])
    for n in ("--name", "--label"):
        if sum(1 for k, _v in valued if k == n) > 1:
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: {n} given more than once")
    for n, v in valued:
        if n == "--mount" and v != DEV_READ_ONLY:
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: mount {v!r} is not part of the D5-A1b launch")
    env = {}
    for n, v in valued:
        if n == "--env":
            key, eq, value = v.partition("=")
            if not eq or key in env:
                found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: environment entry {v!r}")
            elif key not in PATH_KEYS and key not in EXTRA_ENV and not key.startswith("FORGE_ATTACK_"):
                found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: environment variable {key} is not allowed")
            env[key] = value
    paths = card["paths"] if isinstance(card["paths"], Mapping) else {}
    for key in PATH_KEYS:
        if env.get(key) != paths.get(key):
            found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: {key} is not set as observed")
    workdirs = [v for n, v in valued if n == "--workdir"]
    if workdirs != [paths.get("workdir")]:
        found.add("RUNTIME_CONFIGURATION_MISMATCH", f"{phase}: the working directory is not set as observed")
    return bound


def _host_read_only_admitted(row: Mapping[str, Any], bound: set[str]) -> bool:
    """A read-only host-backed row a card may see: a declared bind, Podman userdata, or a /proc or /sys mask."""
    if row["target"] in bound:
        return True
    if row["target"] in USERDATA_TARGETS and row["fstype"] == "tmpfs" and "/userdata/" in row["root"]:
        return True
    return (row["fstype"] == "devtmpfs" and row["root"] == "/null"
            and row["target"].startswith(("/proc/", "/sys/")))


def _mounts(card: Mapping[str, Any], expected: Mapping[str, Any], found: _Findings, phase: str,
            bound: set[str] | None) -> dict[str, str]:
    """Reconcile the three inventories and classify every writable row; return {target: mount id} of the declared
    private mounts (empty when the inventory itself cannot be trusted)."""
    try:
        parsed = parse_mountinfo(card["mountinfo"]) if isinstance(card["mountinfo"], str) else None
    except ValueError as exc:
        found.add("MOUNT_INVENTORY_MISMATCH", f"{phase}: raw inventory unreadable ({str(exc)[:80]})")
        return {}
    rows, runtime = card["mounts"], card["runtime_mounts"]
    if parsed is None or not isinstance(rows, list) or not isinstance(runtime, list):
        found.add("MOUNT_INVENTORY_MISMATCH", f"{phase}: inventory missing")
        return {}
    clean = [{k: r.get(k) for k in ROW_KEYS} if isinstance(r, Mapping) else None for r in rows]
    if clean != parsed:
        found.add("MOUNT_INVENTORY_MISMATCH", f"{phase}: parsed rows differ from the raw inventory")
        return {}
    if len(runtime) != len(parsed) or any(
            not isinstance(rt, Mapping) or any(rt.get(k) != row[k] for k in _reconciled(row))
            for rt, row in zip(runtime, parsed)):
        found.add("MOUNT_INVENTORY_MISMATCH", f"{phase}: the runtime view differs from the card's inventory")
        return {}
    targets = list(expected["writable_targets"])
    by_target: dict[str, list[dict[str, Any]]] = {}
    for row in parsed:
        by_target.setdefault(row["target"], []).append(row)
    if "/" not in by_target:
        found.add("MOUNT_INVENTORY_MISMATCH", f"{phase}: no root mount")
    for path, label in ((expected["source_path"], "SOURCE"), (expected["venv_path"], "VENV")):
        hits = by_target.get(path, [])
        if not hits:
            found.add("MOUNT_INVENTORY_MISMATCH", f"{phase}: no mount for the {label.lower()} at {path}")
        elif any("rw" in r["options"] for r in hits):
            found.add(f"{label}_WRITABLE", f"{phase}: {path} is mounted read-write")
    private: dict[str, str] = {}
    for row, rt in zip(parsed, runtime):
        if "rw" not in row["options"]:
            if rt.get("backing") in ("host", "windows") and not _host_read_only_admitted(row, bound or set()):
                found.add("UNDECLARED_HOST_MOUNT", f"{phase}: mount {row['id']} {row['target']} ({row['fstype']}) "
                                                   "exposes an undeclared host path read-only")
            continue
        where = f"{phase}: mount {row['id']} {row['target']} ({row['fstype']})"
        if any(child["parent"] == row["id"] and child["target"] == row["target"] for child in parsed):
            found.add("OBSCURED_WRITABLE_MOUNT", where + " lies under another mount at the same target")
        if any(o.startswith(("shared:", "master:", "propagate_from:")) for o in row["optional"]):
            found.add("SHARED_WRITABLE_MOUNT", where + f" propagates {row['optional']}")
        backing = rt.get("backing")
        if row["fstype"] in WINDOWS_FSTYPES or backing == "windows" or re.match(r"^[A-Za-z]:", row["source"]):
            found.add("WINDOWS_WRITABLE_MOUNT", where + " is backed by Windows")
        elif row["fstype"] in DEVICE_FSTYPES:
            found.add("DEVICE_NODE_WRITABLE_MOUNT", where + " is a writable device or pseudo-file mount")
        elif backing != "container" or row["fstype"] != "tmpfs" or row["root"] != "/":
            found.add("HOST_WRITABLE_MOUNT", where + " is not a fresh container tmpfs")
        if row["target"] not in targets:
            found.add("UNDECLARED_WRITABLE_MOUNT", where + " is not a declared private mount")
        elif row["target"] in private:
            found.add("OBSCURED_WRITABLE_MOUNT", where + " duplicates a declared private mount")
        else:
            private[row["target"]] = row["id"]
    for t in targets:
        hits = by_target.get(t, [])
        if not any("rw" in r["options"] for r in hits):
            found.add("MOUNT_INVENTORY_MISMATCH", f"{phase}: no writable mount at declared target {t}")
        elif len(hits) != 1:
            found.add("OBSCURED_WRITABLE_MOUNT", f"{phase}: {len(hits)} mounts at declared target {t}")
    return private


def _canaries(cards: dict[str, Mapping[str, Any]], private: dict[str, dict[str, str]], expected: Mapping[str, Any],
              found: _Findings) -> None:
    targets = list(expected["writable_targets"])
    by_phase: dict[str, dict[str, Mapping[str, Any]]] = {}
    for phase, card in cards.items():
        entries = card["canaries"] if isinstance(card["canaries"], list) else []
        mapped: dict[str, Mapping[str, Any]] = {}
        for entry in entries:
            if isinstance(entry, Mapping) and entry.get("target") in targets and entry["target"] not in mapped:
                mapped[entry["target"]] = entry
        for t in targets:
            if t not in mapped:
                found.add("CANARY_COVERAGE_INCOMPLETE", f"{phase}: no canary for {t}")
        by_phase[phase] = mapped
    a = by_phase.get("A", {})
    tokens = [e.get("token") for e in a.values()]
    if len(set(map(str, tokens))) != len(tokens):
        found.add("CANARY_TOKEN_MISMATCH", "A: two private mounts share a token")
    for phase, mapped in by_phase.items():
        for t, entry in mapped.items():
            where = f"{phase} {t}"
            token, read = entry.get("token"), entry.get("read")
            if not isinstance(token, str) or not HEX64.fullmatch(token):
                found.add("CANARY_TOKEN_MISMATCH", where + ": no 256-bit token")
            path = entry.get("path")
            if not isinstance(path, str) or not path.startswith(t.rstrip("/") + "/") or "/" in path[len(t) + 1:]:
                found.add("CANARY_PATH_MISMATCH", where + f": {path!r} is not directly inside {t}")
            mount = private.get(phase, {}).get(t)
            if entry.get("expected_mount") != mount or entry.get("actual_mount") != mount:
                found.add("CANARY_MOUNT_MISMATCH", where + ": not attributed to the declared private mount")
            if read == "UNPROBEABLE":
                found.add("UNPROBEABLE_WRITABLE_MOUNT", where)
            elif read == "READ_ERROR":
                found.add("CANARY_READ_ERROR", where + f": {entry.get('error')}")
            elif read == "OBSCURED_MOUNT":
                found.add("CANARY_MOUNT_MISMATCH", where + ": the directory is on another mount")
            elif read == "READ_OK":
                found.add("CROSS_CARD_CANARY_REACHED", where + ": a token was readable in a fresh container")
            elif read != "READ_ABSENT":
                found.add("CANARY_COVERAGE_INCOMPLETE", where + f": read outcome {read!r}")
            if phase == "A":
                if (entry.get("write") != "WRITE_OK" or entry.get("readback") != token
                        or entry.get("write_mount") != mount or entry.get("readback_mount") != mount):
                    reason = ("CANARY_MOUNT_MISMATCH" if entry.get("write") == "WRITE_OK"
                              and entry.get("readback") == token else "CANARY_WRITE_FAILED")
                    found.add(reason, where + ": the token was not written and read back on its own mount")
            else:
                first = a.get(t, {})
                if token != first.get("token"):
                    found.add("CANARY_TOKEN_MISMATCH", where + ": not the token card A wrote")
                if path != first.get("path"):
                    found.add("CANARY_PATH_MISMATCH", where + ": not the path card A wrote")
                if entry.get("write") not in ("NOT_ATTEMPTED", None):
                    found.add("CANARY_COVERAGE_INCOMPLETE", where + ": a later card wrote")


def _controls(report: Mapping[str, Any], expected: Mapping[str, Any], found: _Findings) -> list[str]:
    controls = report.get("positive_controls")
    if not isinstance(controls, Mapping):
        found.add("EVIDENCE_INCOMPLETE", "no positive controls")
        return []
    if controls.get("host_listener") != "REACHED":
        found.add("NETWORK_CONTROL_FAILED", "the host listener was not reachable from the host")
    shared = controls.get("shared_canary")
    if not isinstance(shared, Mapping):
        found.add("EVIDENCE_INCOMPLETE", "no shared-volume control")
        return []
    ids = [shared.get("a_id"), shared.get("b_id")]
    if not all(isinstance(i, str) and i for i in ids):
        found.add("CANARY_CONTROL_IDENTITY_MISSING", "the control containers are not identified")
    elif ids[0] == ids[1]:
        found.add("CANARY_CONTROL_IDENTITY_REUSED", "both control phases ran in one container")
    missing = [k for k in CONTROL_KEYS if k not in shared]
    if missing:
        found.add("EVIDENCE_INCOMPLETE", f"shared-volume control lacks {missing}")
        return [i for i in ids if isinstance(i, str)]
    if (shared["a_write"] != "WRITE_OK" or shared["b_read"] != "READ_OK" or shared["b_seen"] != shared["a_token"]
            or shared["a_mount"] != shared["a_actual"] or shared["b_mount"] != shared["b_actual"]):
        found.add("CANARY_CONTROL_FAILED", "the deliberately shared volume was not seen across containers")
    if shared["a_path"] != shared["b_path"]:
        found.add("CANARY_CONTROL_PATH_MISMATCH", "the control phases used different paths")
    if not shared["a_image_digest"] == shared["b_image_digest"] == expected["image_digest"]:
        found.add("CANARY_CONTROL_IMAGE_MISMATCH", "the control containers did not run the pinned image")
    return [i for i in ids if isinstance(i, str)]


def _card(card: Mapping[str, Any], expected: Mapping[str, Any], found: _Findings, phase: str) -> dict[str, str]:
    provenance = card["provenance"]
    if not isinstance(provenance, Mapping) or set(provenance) != set(EXPECTED_KEYS) or any(
            provenance[k] != expected[k] for k in EXPECTED_KEYS):
        found.add("PROVENANCE_MISMATCH", f"{phase}: provenance differs from the expected deployment")
    if card["actual_image_digest"] != expected["image_digest"]:
        found.add("IMAGE_DIGEST_MISMATCH", f"{phase}: ran {card['actual_image_digest']!r}")
    if card["actual_image_id"] != expected["image_id"]:
        found.add("IMAGE_ID_MISMATCH", f"{phase}: ran image id {card['actual_image_id']!r}")
    status = card["status"] if isinstance(card["status"], Mapping) else {}
    try:
        if any(int(str(status[k]), 16) != 0 for k in CAPABILITY_FIELDS):
            found.add("NONZERO_CAPABILITIES", f"{phase}: a capability set is not empty")
    except (KeyError, ValueError):
        found.add("EVIDENCE_INCOMPLETE", f"{phase}: capability sets not observed")
    if str(status.get("NoNewPrivs", "")).strip() != "1":
        found.add("NO_NEW_PRIVILEGES_MISSING", f"{phase}: NoNewPrivs is not set")
    if card["ipc"] != "private":
        found.add("IPC_NOT_PRIVATE", f"{phase}: IPC mode {card['ipc']!r}")
    network = card["network"] if isinstance(card["network"], Mapping) else {}
    if network.get("host_listener") != "REFUSED" or network.get("external") != "REFUSED":
        found.add("NETWORK_REACHED", f"{phase}: a network target was reachable")
    if network.get("interfaces") != ["lo"]:
        found.add("NETWORK_REACHED", f"{phase}: interfaces {network.get('interfaces')}")
    writes = card["writes"] if isinstance(card["writes"], Mapping) else {}
    for label, reason in (("source", "SOURCE_WRITABLE"), ("venv", "VENV_WRITABLE")):
        if writes.get(label) != "READ_ONLY":
            found.add(reason, f"{phase}: {label} write probe {writes.get(label)!r}")
    paths = card["paths"] if isinstance(card["paths"], Mapping) else {}
    targets = list(expected["writable_targets"])
    for key in (*PATH_KEYS, "workdir"):
        if not _within(paths.get(key), targets):
            found.add("PATH_OUTSIDE_PRIVATE_MOUNTS", f"{phase}: {key}={paths.get(key)!r}")
    restart = card["restart"] if isinstance(card["restart"], Mapping) else {}
    if restart.get("attempted") is not True or restart.get("refused") is not True or restart.get("exit_code") in (0, None):
        found.add("RESTART_NOT_REFUSED", f"{phase}: restart {dict(restart)}")
    if card["removed"] is not True:
        found.add("CONTAINER_NOT_REMOVED", f"{phase}: the container outlived its card")
    bound = _argv(card, expected, found, phase)
    return _mounts(card, expected, found, phase, bound)


def validate_container_evidence(report: Any, *, expected: Any) -> dict[str, Any]:
    """The D5-A1b verdict on one evidence report. Deterministic; never raises on malformed input."""
    found = _Findings()
    try:
        _validate(report, expected, found)
    except Exception as exc:  # noqa: BLE001 - malformed evidence is a blocked verdict, never a crash
        found.add("EVIDENCE_INCOMPLETE", f"unreadable evidence ({type(exc).__name__})")
    if not found.reasons:
        return {"status": "PASS", "reasons": []}
    return {"status": "BLOCKED", "reasons": sorted(found.reasons), "details": sorted(found.details)}


def _validate(report: Any, expected: Any, found: _Findings) -> None:
    if not isinstance(expected, Mapping) or any(k not in expected for k in EXPECTED_KEYS):
        found.add("EVIDENCE_INCOMPLETE", "no complete expected deployment to compare with")
        return
    if expected["rootless"] is not True:
        found.add("PROVENANCE_MISMATCH", "the expected deployment is not rootless")
    if not isinstance(expected["source_sha"], str) or not HEX40.fullmatch(expected["source_sha"]):
        found.add("PROVENANCE_MISMATCH", "the expected source revision is not a full commit id")
    if not isinstance(report, Mapping) or not report:
        found.add("EVIDENCE_INCOMPLETE", "empty report")
        return
    if report.get("schema") != SCHEMA:
        found.add("SCHEMA_MISMATCH", f"schema {report.get('schema')!r}")
    cards = report.get("cards")
    if not isinstance(cards, list) or [c.get("phase") if isinstance(c, Mapping) else None for c in cards] != list(PHASES):
        found.add("EVIDENCE_INCOMPLETE", "the report does not hold exactly the cards A, B and C")
        cards = [c for c in cards if isinstance(c, Mapping)] if isinstance(cards, list) else []
    complete: dict[str, Mapping[str, Any]] = {}
    for card in cards:
        phase = str(card.get("phase"))
        missing = [k for k in CARD_KEYS if k not in card]
        if missing:
            found.add("EVIDENCE_INCOMPLETE", f"{phase}: missing {missing}")
            continue
        complete[phase] = card
    private = {phase: _card(card, expected, found, phase) for phase, card in complete.items()}
    if complete:
        _canaries(complete, private, expected, found)
    ids = [card.get("id") for card in cards]
    control_ids = _controls(report, expected, found)
    if len(set(map(str, ids))) != len(ids) or set(map(str, ids)) & set(control_ids):
        found.add("CONTAINER_REUSED", "two cards (or a card and a control) share a container")
    if not all(isinstance(i, str) and i for i in ids):
        found.add("EVIDENCE_INCOMPLETE", "a card has no container id")
