"""Genesis-lite v0.3 D5-A1b: the STATELESS_DEVICE contract (owner, 2026-10-21), as a pure validator.

Rootless Podman (crun) bind-mounts six host character devices read-write into every card container, from the host
devtmpfs; rootless crun cannot create device nodes, so they cannot simply be left out. The owner decided on 2026-10-21
(superseding the strict "no exemption" rule of the same day) that a shared writable character device is not
automatically a failure when executed evidence proves it is a non-state-carrying operating-system endpoint under the
D5 threat model. Only the six devices of :data:`DEVICES` are admissible, and each is admitted on its own evidence:

* identity, in every card: exactly one mount at the canonical path, a devtmpfs bind from the operator's own devtmpfs
  (root ``/<name>``, under the card's ``/dev``, private, nosuid and noexec); in the card, a character device (not a
  symlink, ``realpath`` the path itself) with the exact major:minor, mode 0666, the overflow owner (host root is not
  mapped into the rootless user namespace), the host node's device and inode, and the mount id of that row; on the
  host, the same node with its expected owner;
* no state: the node's metadata (size, link count, atime, mtime, ctime) is the same in every card and on the host,
  before and after card A wrote to it;
* semantics fixed by the device: ``null`` accepts and keeps nothing and reads EOF; ``zero`` accepts and reads zeros;
  ``full`` refuses writes (ENOSPC) and reads zeros; ``random`` and ``urandom`` accept unprivileged writes (mixed into
  the kernel pool without entropy credit) and refuse every state-setting ioctl (EPERM); the entropy counters a card can
  read are the same in every card whatever card A did; ``tty`` cannot be opened (ENXIO): the card has no controlling
  terminal, no terminal on stdin, stdout or stderr, no ``/dev/pts``, a dangling ``/dev/ptmx`` and only its three
  pipes as descriptors, and was launched without ``--tty``;
* no channel: in at least :data:`MIN_TRIALS` trials an encoder card writes one of two operator-chosen 256-bit messages
  (the selected bit) to every device and tries every RNG ioctl with it, and a FRESH decoder card reads
  :data:`READ_SIZE` bytes from every device; no decoder ever finds an 8-byte window of either message. The same
  encoder/decoder code through a deliberately shared file MUST recover the bit, and the metadata comparison MUST see
  that file change (the positive control); a container given a terminal MUST fail the tty rules (the tty control);
* no alias: the card's ``/dev`` holds exactly the six devices, Podman's six symlinks with their exact targets and the
  private ``/dev/shm``; every other devtmpfs row is one of Podman's read-only masks of a ``/proc`` or ``/sys`` file,
  which is ``/dev/null`` itself (same device and inode) and is admitted only with ``/dev/null``; a walk of everything
  the card can traverse outside ``/proc``, ``/sys`` and ``/dev`` finds no device node and no symlink to any device but
  a canonical one.

What is NOT claimed: the cards do not receive statistically independent physical entropy. ``random`` and ``urandom``
(and ``getrandom(2)``, which needs no device node) are one shared kernel CRNG; the claim is only that a card cannot set
or read its state through them, so they are no controllable cross-card channel. Scientific randomness never comes from
them: :func:`scientific_randomness_problems` is a static screen that every stochastic generator in the Genesis-lite and
blindfold code takes an explicit seed and that implicit entropy (``os.urandom``, ``secrets``, ``uuid4``) appears only
at declared operational sites (identifiers, nonces that are recorded and bound into the claims stream, verification
tokens). It is a static screen, not a proof: dynamic attribute access is not followed.

:func:`assess` returns findings and one verdict per device; :mod:`.container_evidence` folds them into the N-1 verdict.
Every missing, malformed, unknown or contradictory field blocks.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re
from typing import Any, Iterable, Mapping

CONTRACT = "forge.genesis_lite.v0_3/stateless_device/1"
#: the owner's admissible set (2026-10-21): canonical path -> (major:minor, host owner gid, kind). Nothing else.
DEVICES: dict[str, tuple[str, int, str]] = {
    "/dev/null": ("1:3", 0, "null"), "/dev/zero": ("1:5", 0, "zero"), "/dev/full": ("1:7", 0, "full"),
    "/dev/random": ("1:8", 0, "rng"), "/dev/urandom": ("1:9", 0, "rng"), "/dev/tty": ("5:0", 5, "tty")}
#: the devices a card writes to and reads from (the tty cannot be opened at all)
SINKS = ("/dev/null", "/dev/zero", "/dev/full", "/dev/random", "/dev/urandom")
RNG = ("/dev/random", "/dev/urandom")
PERM = 0o666
#: the kernel's overflow uid/gid: what an unmapped host id (host root) looks like inside a rootless user namespace
OVERFLOW_ID = 65534
#: Podman's symlinks in the card's /dev, with their exact targets; the only directory is the private /dev/shm
DEV_LINKS = {"core": "/proc/kcore", "fd": "/proc/self/fd", "ptmx": "pts/ptmx", "stdin": "/proc/self/fd/0",
             "stdout": "/proc/self/fd/1", "stderr": "/proc/self/fd/2"}
DEV_DIRS = ("shm",)
#: the ioctls that would credit, set, clear or reseed the kernel RNG; each must be refused with EPERM
RNG_IOCTLS = ("RNDADDTOENTCNT", "RNDADDENTROPY", "RNDZAPENTCNT", "RNDCLEARPOOL", "RNDRESEEDCRNG")
READ_SIZE = 1 << 20
WINDOW = 8
MIN_TRIALS = 5
MIN_CONTROL_TRIALS = 2
METADATA = ("size", "nlink", "atime_ns", "mtime_ns", "ctime_ns")
DEVICE_ID = re.compile(r"[0-9]+:[0-9]+")
HEX64 = re.compile(r"[0-9a-f]{64}")
PIPE = re.compile(r"pipe:\[[0-9]+\]")
ADMITTED, BLOCKED = "ADMITTED", "BLOCKED"
NODE_KEYS = ("type", "perm", "uid", "gid", "dev", "ino", "rdev", *METADATA)


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def node_problem(node: Any, *, want_rdev: str | None = None) -> str | None:
    """Why a recorded node is malformed (None if every field is present and well typed)."""
    if not isinstance(node, Mapping):
        return "not recorded"
    if node.get("type") != "chr":
        return f"type {node.get('type')!r} is not a character device"
    for key in ("perm", "uid", "gid", "ino", *METADATA):
        if not _int(node.get(key)):
            return f"{key} {node.get(key)!r} is malformed"
    for key in ("dev", "rdev"):
        if not isinstance(node.get(key), str) or not DEVICE_ID.fullmatch(node[key]):
            return f"{key} {node.get(key)!r} is malformed"
    if want_rdev is not None and node["rdev"] != want_rdev:
        return f"major:minor {node['rdev']} is not {want_rdev}"
    return None


def window_found(data: bytes, message: bytes) -> bool:
    """Whether any WINDOW-byte window of ``message`` occurs in ``data`` (the decoder's test, also the control's)."""
    return any(message[i:i + WINDOW] in data for i in range(len(message) - WINDOW + 1))


def metadata_changed(before: Any, after: Any) -> bool | None:
    """Whether the node metadata differs (None when either side is malformed)."""
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return None
    if not all(_int(before.get(k)) and _int(after.get(k)) for k in (*METADATA, "ino")):
        return None
    return any(before[k] != after[k] for k in (*METADATA, "ino"))


class _Device:
    def __init__(self) -> None:
        self.reasons: dict[str, set[str]] = {p: set() for p in DEVICES}

    def block(self, path: str, reason: str, detail: str, found: Any) -> None:
        self.reasons[path].add(reason)
        found.add(reason, f"{path}: {detail}")


def _tty_problems(devices: Mapping[str, Any], argv: Any) -> list[str]:
    """The tty rules on one card's observation; an empty list is the only pass."""
    problems = []
    tty = devices.get("tty") if isinstance(devices.get("tty"), Mapping) else None
    if tty is None:
        return ["no terminal observation"]
    if tty.get("open") != "ENXIO":
        problems.append(f"opening /dev/tty gave {tty.get('open')!r}, not ENXIO (no controlling terminal)")
    if tty.get("isatty") != [False, False, False]:
        problems.append(f"isatty(0, 1, 2) is {tty.get('isatty')!r}")
    if tty.get("tty_nr") != 0 or tty.get("tpgid") != -1:
        problems.append(f"a controlling terminal is recorded (tty_nr {tty.get('tty_nr')!r}, tpgid {tty.get('tpgid')!r})")
    if not _int(tty.get("pid")) or tty.get("sid") != tty.get("pid"):
        problems.append("the card is not its own session leader")
    if tty.get("pts") is not False:
        problems.append("/dev/pts exists")
    if tty.get("ptmx") != "ENOENT":
        problems.append(f"opening /dev/ptmx gave {tty.get('ptmx')!r}, not ENOENT")
    fds = devices.get("fds")
    if not isinstance(fds, Mapping) or not {"0", "1", "2"} <= set(fds):
        problems.append("no descriptor inventory")
    else:
        listing = [k for k in fds if k not in ("0", "1", "2")]
        if any(not isinstance(fds.get(k), str) or not PIPE.fullmatch(fds[k]) for k in ("0", "1", "2")):
            problems.append(f"stdin, stdout and stderr are not pipes ({[fds.get(k) for k in ('0', '1', '2')]})")
        if len(listing) != 1 or fds[listing[0]] != f"/proc/{tty.get('pid')}/fd":
            problems.append(f"descriptors other than the three pipes and the inventory's own listing: "
                            f"{ {k: fds[k] for k in listing} }")
    if not isinstance(argv, list) or any(isinstance(a, str) and (a in ("-t", "-it", "-ti") or a.startswith("--tty"))
                                         for a in argv):
        problems.append("the container was launched with a terminal (or without a recorded command)")
    return problems


def _encoder_problems(path: str, entry: Any, message: bytes) -> list[str]:
    if not isinstance(entry, Mapping):
        return ["no encoder record"]
    kind = DEVICES[path][2]
    want = "ENOSPC" if kind == "full" else len(message)
    problems = [] if entry.get("write") == want else [f"write gave {entry.get('write')!r}, not {want!r}"]
    if kind == "rng":
        ioctls = entry.get("ioctls")
        if not isinstance(ioctls, Mapping) or any(ioctls.get(n) != "EPERM" for n in RNG_IOCTLS):
            problems.append(f"a state-setting RNG ioctl was not refused with EPERM ({ioctls!r})")
    changed = metadata_changed(entry.get("before"), entry.get("after"))
    if changed is not False:
        problems.append("the node's metadata changed when written (or is not recorded)")
    return problems


def _decoder_problems(path: str, entry: Any) -> list[str]:
    if not isinstance(entry, Mapping):
        return ["no decoder record"]
    kind, problems = DEVICES[path][2], []
    size = entry.get("bytes")
    if kind == "null":
        if size != 0:
            problems.append(f"read {size!r} bytes, not EOF")
    elif size != READ_SIZE:
        problems.append(f"read {size!r} bytes, not {READ_SIZE}")
    if kind in ("zero", "full") and entry.get("all_zero") is not True:
        problems.append("did not read zeros")
    if entry.get("found") != [False, False]:
        problems.append(f"an encoder's message was found ({entry.get('found')!r})")
    return problems


def _hex_pair(messages: Any) -> list[bytes] | None:
    if (not isinstance(messages, list) or len(messages) != 2 or messages[0] == messages[1]
            or not all(isinstance(m, str) and HEX64.fullmatch(m) for m in messages)):
        return None
    return [bytes.fromhex(m) for m in messages]


def _channel(card: Mapping[str, Any]) -> Mapping[str, Any]:
    devices = card.get("devices") if isinstance(card.get("devices"), Mapping) else {}
    return devices.get("channel") if isinstance(devices.get("channel"), Mapping) else {}


def assess(cards: Mapping[str, Mapping[str, Any]], rows: Mapping[str, list[dict[str, Any]] | None],
           trials: Any, controls: Any, *, masked: Iterable[str], kernel: Any, found: Any) -> dict[str, dict[str, Any]]:
    """The per-device verdicts. ``cards``: every validated card by label (A, B, C and the trial cards); ``rows``: each
    card's mount table when its inventory reconciled (None when it did not); ``trials``: the encoder/decoder trials;
    ``controls``: the shared-file channel control and the tty control; ``masked``: Podman's masked paths; ``kernel``:
    the expected kernel release. Findings go to ``found.add(reason, detail)``."""
    dev = _Device()
    masked = tuple(masked)
    host_ref: dict[str, Any] | None = None
    first_meta: dict[str, Mapping[str, Any]] = {}
    rng_seen: set[str] = set()
    for label, card in cards.items():
        devices = card.get("devices")
        host = card.get("host_devices") if isinstance(card.get("host_devices"), Mapping) else {}
        if not isinstance(devices, Mapping):
            for path in DEVICES:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"{label}: no device observation", found)
            continue
        table = rows.get(label)
        if table is None:
            for path in DEVICES:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"{label}: the mount inventory is not trusted", found)
            continue
        if devices.get("contract") != CONTRACT:
            for path in DEVICES:
                dev.block(path, "DEVICE_CONTRACT_MISMATCH", f"{label}: contract {devices.get('contract')!r}", found)
        if devices.get("kernel") != kernel or host.get("kernel") != kernel:
            for path in DEVICES:
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: kernel {devices.get('kernel')!r} / host "
                                                            f"{host.get('kernel')!r} is not {kernel!r}", found)
        devtmpfs = host.get("devtmpfs")
        nodes = host.get("nodes") if isinstance(host.get("nodes"), Mapping) else {}
        if not isinstance(devtmpfs, str) or not DEVICE_ID.fullmatch(devtmpfs):
            for path in DEVICES:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"{label}: the operator's devtmpfs is {devtmpfs!r}", found)
            continue
        snapshot = {"devtmpfs": devtmpfs, "nodes": dict(nodes)}
        if host_ref is None:
            host_ref = snapshot
        elif snapshot != host_ref:
            for path in DEVICES:
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: the operator's device record differs between "
                                                            "cards", found)
        overflow = devices.get("overflow") if isinstance(devices.get("overflow"), Mapping) else {}
        if overflow != {"uid": OVERFLOW_ID, "gid": OVERFLOW_ID}:
            for path in DEVICES:
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: overflow ids {overflow!r}", found)
        tree = devices.get("tree") if isinstance(devices.get("tree"), Mapping) else None
        by_target: dict[str, list[dict[str, Any]]] = {}
        for row in table:
            by_target.setdefault(row["target"], []).append(row)
        dev_rows = by_target.get("/dev", [])
        dev_id = dev_rows[0]["id"] if len(dev_rows) == 1 else None
        if tree is None:
            for path in DEVICES:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"{label}: no /dev inventory", found)
            continue
        # ---- the /dev inventory: exactly the six devices, Podman's links, the private /dev/shm
        for name, entry in tree.items():
            path = "/dev/" + str(name)
            if path in DEVICES:
                continue
            kind = entry.get("type") if isinstance(entry, Mapping) else None
            if name in DEV_LINKS and kind == "lnk" and entry.get("link") == DEV_LINKS[name]:
                continue
            if name in DEV_DIRS and kind == "dir":
                shm = by_target.get(path, [])
                if len(shm) == 1 and entry.get("mnt") == shm[0]["id"]:
                    continue
            for p in DEVICES:
                dev.block(p, "UNKNOWN_DEVICE_PATH", f"{label}: {path} ({kind}) is not part of the declared /dev", found)
        for name in (*DEV_LINKS, *DEV_DIRS):
            if name not in tree:
                for p in DEVICES:
                    dev.block(p, "UNKNOWN_DEVICE_PATH", f"{label}: /dev/{name} is missing from the inventory", found)
        # ---- every devtmpfs row: a canonical device, or a read-only /dev/null mask
        for row in table:
            if row["fstype"] != "devtmpfs":
                continue
            if row["target"] in DEVICES:
                continue
            alias = (devices.get("aliases") or {}).get(row["target"]) if isinstance(devices.get("aliases"),
                                                                                    Mapping) else None
            null = tree.get("null") if isinstance(tree.get("null"), Mapping) else {}
            ok = (row["target"] in masked and row["root"] == "/null" and "ro" in row["options"]
                  and row["device"] == devtmpfs and not row["optional"] and node_problem(alias, want_rdev="1:3") is None
                  and alias.get("ino") == null.get("ino") and alias.get("dev") == devtmpfs
                  and alias.get("mnt") == row["id"])
            if not ok:
                dev.block("/dev/null", "DEVICE_ALIAS_MISMATCH", f"{label}: devtmpfs row {row['id']} at "
                                                                f"{row['target']} is not a read-only /dev/null mask", found)
        aliases = devices.get("aliases")
        if not isinstance(aliases, Mapping) or set(aliases) != {r["target"] for r in table if r["fstype"] == "devtmpfs"
                                                                  and r["target"] not in DEVICES}:
            dev.block("/dev/null", "DEVICE_ALIAS_MISMATCH", f"{label}: the alias inventory does not match the "
                                                            "devtmpfs masks", found)
        walk = devices.get("walk") if isinstance(devices.get("walk"), Mapping) else None
        if walk is None or not _int(walk.get("entries")) or walk["entries"] < 1 or not isinstance(
                walk.get("devices"), list) or not isinstance(walk.get("device_links"), list):
            for p in DEVICES:
                dev.block(p, "DEVICE_EVIDENCE_INCOMPLETE", f"{label}: no reachable-device walk", found)
        else:
            for path in walk["devices"]:
                for p in DEVICES:
                    dev.block(p, "UNKNOWN_DEVICE_PATH", f"{label}: a device node at {path!r}", found)
            for link in walk["device_links"]:
                target = link[1] if isinstance(link, list) and len(link) == 2 else None
                if target in DEVICES:
                    continue                                    # a name for a canonical device: its contract applies
                for p in DEVICES:
                    dev.block(p, "UNKNOWN_DEVICE_PATH", f"{label}: a symlink {link!r} to another device", found)
        # ---- each device's identity in this card
        for path, (rdev, gid, kind) in DEVICES.items():
            name = path.rsplit("/", 1)[1]
            hits = by_target.get(path, [])
            node = tree.get(name)
            host_node = nodes.get(path)
            if len(hits) != 1:
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: {len(hits)} mounts at the path", found)
                continue
            row = hits[0]
            if (row["fstype"] != "devtmpfs" or row["root"] != "/" + name or row["device"] != devtmpfs
                    or row["parent"] != dev_id or row["optional"] or not {"nosuid", "noexec"} <= set(row["options"])):
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: mount {row['id']} is not a private nosuid,"
                                                            f"noexec bind of the operator's devtmpfs /{name}", found)
            problem = node_problem(node, want_rdev=rdev)
            if problem:
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: in the card, {problem}", found)
                continue
            if node.get("realpath") != path or node.get("mnt") != row["id"]:
                dev.block(path, "DEVICE_ALIAS_MISMATCH", f"{label}: realpath {node.get('realpath')!r} or mount "
                                                         f"{node.get('mnt')!r} is not the path's own", found)
            if (node["perm"], node["uid"], node["gid"]) != (PERM, OVERFLOW_ID, OVERFLOW_ID):
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: mode {oct(node['perm'])} owner "
                                                            f"{node['uid']}:{node['gid']}", found)
            host_problem = node_problem(host_node, want_rdev=rdev)
            if host_problem:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"{label}: on the host, {host_problem}", found)
                continue
            if (host_node["perm"], host_node["uid"], host_node["gid"]) != (PERM, 0, gid) or host_node["dev"] != devtmpfs:
                dev.block(path, "DEVICE_IDENTITY_MISMATCH", f"{label}: the host node is mode {oct(host_node['perm'])} "
                                                            f"owner {host_node['uid']}:{host_node['gid']}", found)
            if (node["dev"], node["ino"]) != (host_node["dev"], host_node["ino"]):
                dev.block(path, "DEVICE_ALIAS_MISMATCH", f"{label}: the card's node is not the host's node", found)
            meta = {k: node[k] for k in METADATA}
            if any(meta[k] != host_node[k] for k in METADATA):
                dev.block(path, "DEVICE_STATE_CHANGED", f"{label}: the card's metadata differs from the host's", found)
            if first_meta.setdefault(path, meta) != meta:
                dev.block(path, "DEVICE_STATE_CHANGED", f"{label}: the metadata differs between cards", found)
        # ---- the terminal rules
        for problem in _tty_problems(devices, card.get("argv")):
            dev.block("/dev/tty", "TTY_USABLE", f"{label}: {problem}", found)
        # ---- the kernel RNG counters a card can read
        rng = devices.get("rng") if isinstance(devices.get("rng"), Mapping) else None
        if rng is None or not all(_int(rng.get(k)) for k in ("entropy_avail", "poolsize", "getentcnt")):
            for path in RNG:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"{label}: the RNG counters are not recorded", found)
        else:
            rng_seen.add(repr(sorted(rng.items())))
    if len(rng_seen) > 1:
        for path in RNG:
            dev.block(path, "CROSS_CARD_DEVICE_CHANNEL", f"the RNG counters differ between cards: {sorted(rng_seen)}",
                      found)
    # ---- the encoder / decoder trials
    if not isinstance(trials, list) or len(trials) < MIN_TRIALS or {t.get("bit") if isinstance(t, Mapping) else None
                                                                    for t in trials} != {0, 1}:
        for path in SINKS:
            dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"fewer than {MIN_TRIALS} selected-message trials with "
                                                          "both bits", found)
        trials = trials if isinstance(trials, list) else []
    used: set[str] = set()
    for n, trial in enumerate(trials):
        if not isinstance(trial, Mapping):
            continue
        pair = _hex_pair(trial.get("messages"))
        enc, decs = trial.get("encoder"), trial.get("decoders")
        if (pair is None or trial.get("bit") not in (0, 1) or enc not in cards or not isinstance(decs, list)
                or not decs or any(d not in cards or d == enc for d in decs) or enc in used or used & set(decs)):
            for path in SINKS:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"trial {n}: malformed or reused cards", found)
            continue
        used |= {enc, *decs}
        message = pair[trial["bit"]]
        encoded = _channel(cards[enc])
        if encoded.get("role") != "encode" or encoded.get("message") != message.hex():
            for path in SINKS:
                dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"trial {n}: {enc} did not encode the selected message",
                          found)
            continue
        for path in SINKS:
            for problem in _encoder_problems(path, (encoded.get("paths") or {}).get(path), message):
                dev.block(path, "DEVICE_SEMANTICS_MISMATCH", f"trial {n} encoder {enc}: {problem}", found)
        if (encoded.get("paths") or {}).get("/dev/tty") != {"open": "ENXIO"}:
            dev.block("/dev/tty", "TTY_USABLE", f"trial {n} encoder {enc}: /dev/tty could be written", found)
        for d in decs:
            decoded = _channel(cards[d])
            if decoded.get("role") != "decode" or decoded.get("messages") != trial["messages"]:
                for path in SINKS:
                    dev.block(path, "DEVICE_EVIDENCE_INCOMPLETE", f"trial {n}: {d} did not decode this trial", found)
                continue
            for path in SINKS:
                entry = (decoded.get("paths") or {}).get(path)
                for problem in _decoder_problems(path, entry):
                    reason = "CROSS_CARD_DEVICE_CHANNEL" if "found" in problem else "DEVICE_SEMANTICS_MISMATCH"
                    dev.block(path, reason, f"trial {n} decoder {d}: {problem}", found)
    # ---- the positive controls
    controls = controls if isinstance(controls, Mapping) else {}
    channel = controls.get("device_channel")
    if not isinstance(channel, list) or len(channel) < MIN_CONTROL_TRIALS or {
            c.get("bit") if isinstance(c, Mapping) else None for c in channel} != {0, 1}:
        for path in SINKS:
            dev.block(path, "DEVICE_CHANNEL_CONTROL_FAILED", "no shared-file channel control with both bits", found)
        channel = channel if isinstance(channel, list) else []
    for n, c in enumerate(channel):
        pair = _hex_pair(c.get("messages")) if isinstance(c, Mapping) else None
        enc = c.get("encoder") if isinstance(c, Mapping) and isinstance(c.get("encoder"), Mapping) else {}
        dec = c.get("decoder") if isinstance(c, Mapping) and isinstance(c.get("decoder"), Mapping) else {}
        path = c.get("path") if isinstance(c, Mapping) else None
        e, d = (enc.get("paths") or {}).get(path, {}), (dec.get("paths") or {}).get(path, {})
        want = [b == c.get("bit") for b in (0, 1)] if pair else None
        ok = (pair is not None and enc.get("message") == pair[c["bit"]].hex() and dec.get("messages") == c["messages"]
              and isinstance(e, Mapping) and isinstance(d, Mapping) and e.get("write") == len(pair[c["bit"]])
              and d.get("found") == want and metadata_changed(e.get("before"), d.get("node")) is True
              and isinstance(c.get("a_id"), str) and isinstance(c.get("b_id"), str) and c["a_id"] != c["b_id"]
              and not {c["a_id"], c["b_id"]} & {card.get("id") for card in cards.values()})
        if not ok:
            for p in SINKS:
                dev.block(p, "DEVICE_CHANNEL_CONTROL_FAILED", f"control {n}: the shared file did not carry the bit "
                                                              "or its change was not seen", found)
    tty = controls.get("tty")
    if (not isinstance(tty, Mapping) or not isinstance(tty.get("devices"), Mapping)
            or not _tty_problems(tty["devices"], tty.get("argv"))
            or tty["devices"].get("tty", {}).get("open") != "OPENED"):
        dev.block("/dev/tty", "TTY_CONTROL_FAILED", "a container given a terminal was not told apart", found)
    return {path: ({"status": ADMITTED, "contract": CONTRACT, "reasons": []} if not dev.reasons[path] else
                   {"status": BLOCKED, "contract": CONTRACT, "reasons": sorted(dev.reasons[path])})
            for path in DEVICES}


# ---- scientific randomness (static screen) -----------------------------------------------------------------------------
#: the code the screen covers, relative to the repository root
RANDOMNESS_SCOPE = ("benchmarks/genesis_lite", "src/engcore/blindfold")
#: implicit-entropy calls allowed at exactly these sites, each with what it is for; none seeds a scientific operation
OPERATIONAL_ENTROPY: dict[tuple[str, str, str], str] = {
    ("benchmarks/genesis_lite/arms.py", "_collect", "secrets.token_hex"): "query id label",
    ("src/engcore/blindfold/baselines.py", "_collect", "secrets.token_hex"): "query id label",
    ("src/engcore/blindfold/baselines.py", "single_setting", "secrets.token_hex"): "query id label",
    ("src/engcore/blindfold/escrow.py", "call", "secrets.token_hex"): "default query id label",
    ("src/engcore/blindfold/escrow.py", "EscrowStorage.__init__", "secrets.token_hex"): "storage canary",
    ("src/engcore/blindfold/escrow.py", "EscrowService.__init__", "os.urandom"):
        "master secret only when none is supplied; the Genesis-lite harness always supplies the derived master",
    ("benchmarks/genesis_lite/v0_3/registry.py", "AttemptRegistry.admit", "secrets.token_hex"):
        "admission nonce: recorded in the registry and bound into the claims-stream key (D2b)",
    ("benchmarks/genesis_lite/v0_3/container_probe.py", "probe", "secrets.token_hex"): "verification canary",
    ("benchmarks/genesis_lite/v0_3/isolation.py", "new_card_name", "secrets.token_hex"): "container name",
    ("benchmarks/genesis_lite/v0_3/isolation.py", "collect_container_evidence", "secrets.token_hex"):
        "verification marker",
    ("benchmarks/genesis_lite/v0_3/isolation.py", "collect_container_evidence.pair", "secrets.token_hex"):
        "selected-message trial messages",
    ("benchmarks/genesis_lite/v0_3/isolation.py", "verify", "secrets.token_bytes"): "verification canary",
    ("benchmarks/genesis_lite/v0_3/isolation.py", "verify", "secrets.token_hex"): "verification canary",
    ("benchmarks/genesis_lite/v0_3/deployment_attacks.py", "persistence", "uuid.uuid4"): "attack probe marker",
    ("benchmarks/genesis_lite/v0_3/deployment_attacks.py", "cross_card_state", "uuid.uuid4"): "attack probe marker",
    ("benchmarks/genesis_lite/v0_3/timing_pilot.py", "run", "secrets.token_bytes"):
        "synthetic non-formal root of the cost pilot",
    ("benchmarks/genesis_lite/v0_3/timing_pilot.py", "run", "secrets.token_hex"): "synthetic non-formal nonce",
}
#: files that may name the RNG device paths: the deployment verification itself
DEVICE_PATH_FILES = ("benchmarks/genesis_lite/v0_3/device_contract.py", "benchmarks/genesis_lite/v0_3/container_probe.py",
                     "benchmarks/genesis_lite/v0_3/isolation.py", "benchmarks/genesis_lite/v0_3/container_evidence.py",
                     "benchmarks/genesis_lite/v0_3/preregistration.py")          # the last: the decision text
_IMPLICIT = ("os.urandom", "os.getrandom", "random.SystemRandom", "uuid.uuid1", "uuid.uuid4")
_SEEDED = {"random.Random", "np.random.default_rng", "numpy.random.default_rng", "np.random.Generator"}


def _calls(tree: ast.AST) -> Iterable[tuple[str, ast.Call | ast.AST]]:
    stack: list[str] = []

    def visit(node: ast.AST) -> Iterable[tuple[str, ast.AST]]:
        named = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        if named:
            stack.append(node.name)
        yield ".".join(stack) or "<module>", node
        for child in ast.iter_child_nodes(node):
            yield from visit(child)
        if named:
            stack.pop()

    yield from visit(tree)


def scientific_randomness_problems(root: pathlib.Path) -> dict[str, Any]:
    """The static screen over :data:`RANDOMNESS_SCOPE` under ``root``: {"files": {rel: sha256}, "problems": [...]}.
    A problem is an unseeded generator (``random.Random()``, ``default_rng()``), the module-global ``random`` or legacy
    ``numpy.random`` functions, implicit entropy outside :data:`OPERATIONAL_ENTROPY`, an import that would hide those
    names, or an RNG device path outside the deployment verification."""
    files, problems = {}, []
    paths = sorted(p for scope in RANDOMNESS_SCOPE for p in (root / scope).rglob("*.py"))
    if not paths:
        return {"files": {}, "problems": ["the screen found no file to read"]}
    for path in paths:
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        files[rel] = hashlib.sha256(data).hexdigest()
        try:
            tree = ast.parse(data)
        except SyntaxError:
            problems.append(f"{rel}: does not parse")
            continue
        for where, node in _calls(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("random", "secrets", "uuid", "numpy.random"):
                problems.append(f"{rel}:{node.lineno}: 'from {node.module} import' hides the screened names")
            elif isinstance(node, ast.ImportFrom) and node.module == "os" and any(
                    a.name in ("urandom", "getrandom") for a in node.names):
                problems.append(f"{rel}:{node.lineno}: imports os.urandom by name")
            elif isinstance(node, ast.Import) and any(a.name in ("random", "secrets", "uuid", "numpy.random")
                                                      and a.asname for a in node.names):
                problems.append(f"{rel}:{node.lineno}: an aliased import hides the screened names")
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                  and re.search(r"/dev/u?random\b", node.value) and rel not in DEVICE_PATH_FILES):
                problems.append(f"{rel}:{node.lineno}: names an RNG device")
            elif isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name in _SEEDED:
                    if not node.args and not node.keywords:
                        problems.append(f"{rel}:{node.lineno} {where}: {name}() has no explicit seed")
                elif name in _IMPLICIT or re.fullmatch(r"secrets\.\w+", name):
                    if (rel, where, name) not in OPERATIONAL_ENTROPY:
                        problems.append(f"{rel}:{node.lineno} {where}: {name} is implicit entropy at an undeclared "
                                        "site")
                elif re.fullmatch(r"(random|np\.random|numpy\.random)\.\w+", name):
                    problems.append(f"{rel}:{node.lineno} {where}: {name} uses an implicitly seeded global generator")
    return {"files": files, "problems": problems}
