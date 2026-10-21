"""Genesis-lite v0.3 D5, family 3a: the low-level root helper (spike section 6.1 steps only).

It runs as root inside the formal WSL2 VM, started by the declared operator action
(``wsl.exe -d Ubuntu-24.04 -u root --exec /usr/bin/python3 -I /var/lib/forge-f3a/helper.py <operation>``). It is one
self-contained standard-library file, so its sha256 pins it (:attr:`.family3a.RuntimeConfig.helper_sha256`); it imports
nothing from the repository, which the formal VM does not mount.

It is not a command facility. Its operations are fixed (:data:`OPERATIONS`) and none takes a command:

* ``identity``: prints the measured identity (``family3a.IDENTITY_KEYS``) as one JSON line;
* ``install-rootfs <image digest>``: extracts the card image's exported tar from stdin into :data:`ROOTFS` (tarfile's
  ``tar`` filter: nothing outside the directory, no setuid/setgid/sticky bits), adds the two kept mount points and
  records the image digest the operator declares. The image digest is the operator's provenance claim; the tree digest
  is measured by ``identity`` every time;
* ``configure-kept <tree> [<venv>]``: records the WSL directories bound read-only at :data:`KEPT_TREE` and
  :data:`KEPT_VENV`;
* ``run <request as hex>``: ONE card from a request that :func:`request_problems` accepts. The card's stdin and stdout
  are the helper's own; its stderr is a pipe the helper drains and discards (never ``/dev/null``: an open descriptor
  on the host's devtmpfs node would hand the card a BLOCKER-1 node, as the first smoke card showed); the helper's
  last stderr line is the result record;
* ``residue``: the residue counts of every family-3a card;
* ``control-teardown``: unmounts the power control's shared device tmpfs.

One card (``run``), exactly the spike's steps: a fresh tmpfs made private, holding mknod'd null, zero and full, an
empty ``shm`` directory and an empty mask file; an OCI spec with ``/dev`` bound from it ro, nosuid, noexec (rw only in
the power control, whose cards share ONE tmpfs); the mask file, never crun's ``maskedPaths``, over /proc files;
``rootfsPropagation: rprivate``; a user-namespace mapping (0 -> host 100000), empty capability sets and no_new_privs;
Podman's default seccomp profile in OCI form; a device cgroup allowing only 1:3, 1:5 and 1:7; a read-only rootfs; the
kept tree and venv bound read-only. Then ``crun run``, then cleanup with residue counts. Any refusal exits non-zero
before anything is created.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import time

BASE = "/var/lib/forge-f3a"
ROOTFS = f"{BASE}/rootfs"
MANIFEST = f"{BASE}/manifest.json"
RUN = "/run/forge-f3a"
CRUN_ROOT = f"{RUN}/crun"
SHARED = f"{RUN}/shared-dev"
CGROUP_NAME = "forge-f3a"
CGROUP_PARENT = f"/sys/fs/cgroup/{CGROUP_NAME}"
CRUN, MOUNT, UMOUNT = "/usr/bin/crun", "/usr/bin/mount", "/usr/bin/umount"
SECCOMP_SOURCE = "/usr/share/containers/seccomp.json"
ROOT_LAUNCH = "wsl.exe -u root"
KEPT_TREE, KEPT_VENV = "/forge/tree", "/forge/venv"
REQUEST_SCHEMA = "forge.genesis_lite.v0_3/family3a_helper_request/1"
RESULT_SCHEMA = "forge.genesis_lite.v0_3/family3a_helper_result/1"
RESULT_PREFIX = "F3A-RESULT "
CARD, POWER_CONTROL = "card", "power_control_shared_device_tmpfs"
NODES = {"null": (1, 3), "zero": (1, 5), "full": (1, 7)}
ENTRYPOINTS = {"proposer_host": "benchmarks/genesis_lite/proposer_host.py",
               "container_probe": "benchmarks/genesis_lite/v0_3/container_probe.py"}
#: the card's interpreter per entrypoint: the probe uses the image's own python, the proposer the kept venv
INTERPRETERS = {"container_probe": "/usr/bin/python3", "proposer_host": f"{KEPT_VENV}/bin/python3"}
CARD_ENV = {"PYTHONDONTWRITEBYTECODE": "1"}
CARD_PATHS = {"HOME": "/tmp/home", "TMPDIR": "/tmp", "XDG_CACHE_HOME": "/tmp/cache",
              "PYTHONPYCACHEPREFIX": "/tmp/pycache"}
MAX_ARGS, MAX_TIMEOUT_S = 16, 3600.0
CARD_ID = re.compile(r"gl3a-[0-9a-f]{8,32}")
ABS_ARG = re.compile(r"/[A-Za-z0-9._/-]*")
HEX64 = re.compile(r"[0-9a-f]{64}")
IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
KEPT_PARENTS = ("/home/", "/opt/")
READONLY = ["/proc/asound", "/proc/bus", "/proc/fs", "/proc/irq", "/proc/sys", "/proc/sysrq-trigger"]
MASK_FILES = ["/proc/kcore", "/proc/keys", "/proc/latency_stats", "/proc/timer_list", "/proc/timer_stats",
              "/proc/sched_debug"]
MASK_DIRS = ["/proc/acpi", "/proc/scsi", "/sys/firmware", "/sys/fs/selinux", "/sys/dev/block"]
TMPFS = ["rw", "nosuid", "nodev", "mode=1777", "size=65536k"]
ID_MAP = [{"containerID": 0, "hostID": 100000, "size": 65536}]
CARD_UID = 1000
#: the residue counts of one card (``family3a.CLEAN``): every one must be zero
CLEAN_KEYS = ("mounts", "card_dirs", "containers", "cgroups", "processes")
OPERATIONS = ("identity", "install-rootfs", "configure-kept", "run", "residue", "control-teardown")


class Refused(Exception):
    """The helper will not do this; nothing was created."""


def _sh(*argv: str, check: bool = True) -> subprocess.CompletedProcess:
    if argv[0] not in (CRUN, MOUNT, UMOUNT):            # the only programs this helper ever runs
        raise Refused(f"program {argv[0]!r} is not one of the helper's fixed programs")
    return subprocess.run(list(argv), check=check, capture_output=True, text=True, timeout=120)


def _sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(doc: object) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


# ---- the request -----------------------------------------------------------------------------------------------------
def _kept_arg(arg: object) -> bool:
    return (isinstance(arg, str) and bool(ABS_ARG.fullmatch(arg)) and ".." not in arg.split("/")
            and any(arg == root or arg.startswith(root + "/") for root in (KEPT_TREE, KEPT_VENV)))


def request_problems(request: object) -> list[str]:
    """The helper's own strict check of a request (the same rules as ``family3a.helper_request_problems``)."""
    if not isinstance(request, dict) or set(request) != {"schema", "mode", "config_sha256", "card"}:
        return ["not exactly schema, mode, config_sha256 and card"]
    problems = []
    if request["schema"] != REQUEST_SCHEMA or request["mode"] not in (CARD, POWER_CONTROL):
        problems.append("schema or mode")
    if not isinstance(request["config_sha256"], str) or not HEX64.fullmatch(request["config_sha256"]):
        problems.append("config digest")
    card = request["card"]
    if not isinstance(card, dict) or set(card) != {"card_id", "entrypoint", "args", "env", "timeout_s"}:
        return [*problems, "the card is not exactly id, entrypoint, args, env and timeout"]
    if not isinstance(card["card_id"], str) or not CARD_ID.fullmatch(card["card_id"]):
        problems.append("card id")
    if card["entrypoint"] not in ENTRYPOINTS:
        problems.append("entrypoint")
    args = card["args"]
    if (not isinstance(args, list) or len(args) > MAX_ARGS or not all(_kept_arg(a) for a in args)
            or (card["entrypoint"] == "container_probe" and args)):
        problems.append("arguments")
    env = card["env"]
    if not isinstance(env, dict) or any(CARD_ENV.get(k) != v for k, v in env.items()):
        problems.append("environment")
    t = card["timeout_s"]
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 < t <= MAX_TIMEOUT_S:
        problems.append("timeout")
    if request["mode"] == POWER_CONTROL and card["entrypoint"] != "container_probe":
        problems.append("the power control runs the container probe only")
    return problems


def decode_request(hexed: str) -> dict:
    try:
        request = json.loads(bytes.fromhex(hexed).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise Refused(f"the request is not hex-encoded JSON: {exc}") from exc
    problems = request_problems(request)
    if problems:
        raise Refused("; ".join(problems))
    return request


# ---- identity --------------------------------------------------------------------------------------------------------
def seccomp_profile(source: dict, release: str) -> dict:
    """Podman's default profile reduced to OCI form for a card without capabilities (the spike's derivation)."""
    kernel = tuple(int(x) for x in release.split("-")[0].split(".")[:2])
    rules = []
    for r in source["syscalls"]:
        inc, exc = r.get("includes") or {}, r.get("excludes") or {}
        if inc.get("caps") or (inc.get("arches") and "amd64" not in inc["arches"]):
            continue
        if exc.get("arches") and "amd64" in exc["arches"]:
            continue
        if inc.get("minKernel") and tuple(int(x) for x in inc["minKernel"].split(".")[:2]) > kernel:
            continue
        rule = {"names": r["names"], "action": r["action"]}
        for k in ("args", "errnoRet"):
            if r.get(k):
                rule[k] = r[k]
        rules.append(rule)
    return {"defaultAction": source["defaultAction"], "defaultErrnoRet": source.get("defaultErrnoRet", 1),
            "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_X86", "SCMP_ARCH_X32"], "syscalls": rules}


def _seccomp() -> dict:
    with open(SECCOMP_SOURCE, "rb") as f:
        return seccomp_profile(json.loads(f.read()), os.uname().release)


def tree_digest(top: str) -> str:
    """A digest of a directory tree that ignores timestamps and inode numbers: per entry, sorted by path, its kind,
    permission bits, owner, and content (sha256), link target or device number."""
    digest = hashlib.sha256()
    entries = []
    for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            entries.append(os.path.join(dirpath, name))
    for path in sorted(entries, key=lambda p: os.path.relpath(p, top).encode("utf-8", "surrogateescape")):
        st = os.lstat(path)
        rel = os.path.relpath(path, top).replace(os.sep, "/")
        kind = stat.S_IFMT(st.st_mode)
        if stat.S_ISREG(kind):
            body = "f " + _sha_file(path)
        elif stat.S_ISLNK(kind):
            body = "l " + os.readlink(path)
        elif stat.S_ISDIR(kind):
            body = "d"
        elif stat.S_ISCHR(kind) or stat.S_ISBLK(kind):
            body = f"{'c' if stat.S_ISCHR(kind) else 'b'} {os.major(st.st_rdev)}:{os.minor(st.st_rdev)}"
        else:
            body = f"o {kind:o}"
        digest.update(f"{rel}\0{stat.S_IMODE(st.st_mode):o}\0{st.st_uid}:{st.st_gid}\0{body}\n".encode(
            "utf-8", "surrogateescape"))
    return digest.hexdigest()


def _manifest() -> dict:
    try:
        with open(MANIFEST, "rb") as f:
            doc = json.loads(f.read())
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _write_manifest(doc: dict) -> None:
    tmp = MANIFEST + ".new"
    with open(tmp, "wb") as f:
        f.write(canonical(doc) + b"\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, MANIFEST)


def _crun_version() -> str:
    first = _sh(CRUN, "--version").stdout.splitlines()[0]
    return first.split("version", 1)[1].strip() if "version" in first else "UNKNOWN"


def identity() -> dict:
    manifest = _manifest()
    return {"runtime_name": "crun", "runtime_version": _crun_version(),
            "runtime_sha256": _sha_file(os.path.realpath(CRUN)), "kernel_release": os.uname().release,
            "image_digest": manifest.get("image_digest", "NOT_INSTALLED"),
            "rootfs_tree_sha256": tree_digest(ROOTFS) if os.path.isdir(ROOTFS) else "NOT_INSTALLED",
            "seccomp_sha256": hashlib.sha256(canonical(_seccomp())).hexdigest(),
            "helper_sha256": _sha_file(os.path.realpath(__file__)),
            "root_launch": ROOT_LAUNCH if os.geteuid() == 0 else "NOT_ROOT"}


# ---- installation ----------------------------------------------------------------------------------------------------
def install_rootfs(image_digest: str, stream) -> dict:
    if not IMAGE_DIGEST.fullmatch(image_digest):
        raise Refused(f"image digest {image_digest!r}")
    new, old = ROOTFS + ".new", ROOTFS + ".old"
    for path in (new, old):
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(new, mode=0o755)
    with tarfile.open(fileobj=stream, mode="r|*") as tar:
        tar.extractall(new, numeric_owner=True, filter="tar")
    for point in (KEPT_TREE, KEPT_VENV):
        os.makedirs(new + point, mode=0o755, exist_ok=True)
    if os.path.isdir(ROOTFS):
        os.rename(ROOTFS, old)
    os.rename(new, ROOTFS)
    shutil.rmtree(old, ignore_errors=True)
    manifest = {**_manifest(), "image_digest": image_digest, "installed_ns": time.time_ns()}
    _write_manifest(manifest)
    return manifest


def configure_kept(tree: str, venv: str | None) -> dict:
    for path in (tree, venv):
        if path is None:
            continue
        real = os.path.realpath(path)
        if (real != path or not path.startswith(KEPT_PARENTS) or not os.path.isdir(path)
                or BASE.startswith(path) or path.startswith(BASE)):
            raise Refused(f"kept path {path!r} must be a real directory under {KEPT_PARENTS}")
    manifest = {**_manifest(), "tree": tree, "venv": venv}
    _write_manifest(manifest)
    return manifest


# ---- one card --------------------------------------------------------------------------------------------------------
def make_dev(path: str) -> None:
    """One private tmpfs: ``dev`` holds the three mknod'd nodes and an empty ``shm``; ``mask/empty`` masks /proc
    files (crun's own maskedPaths would bind the HOST /dev/null over them)."""
    os.makedirs(path, exist_ok=True)
    _sh(MOUNT, "-t", "tmpfs", "-o", "size=64k,mode=755,nosuid,noexec", "tmpfs", path)
    _sh(MOUNT, "--make-private", path)                 # systemd's / is shared: the card's /dev/shm would propagate
    os.mkdir(f"{path}/dev")
    os.chmod(f"{path}/dev", 0o755)
    for name, (major, minor) in NODES.items():
        os.mknod(f"{path}/dev/{name}", stat.S_IFCHR | 0o666, os.makedev(major, minor))
        os.chmod(f"{path}/dev/{name}", 0o666)
    os.mkdir(f"{path}/dev/shm")
    os.mkdir(f"{path}/mask")
    os.chmod(f"{path}/mask", 0o755)
    with open(f"{path}/mask/empty", "wb"):
        pass
    os.chmod(f"{path}/mask/empty", 0o444)


def card_argv(card: dict) -> list[str]:
    entry = f"{KEPT_TREE}/{ENTRYPOINTS[card['entrypoint']]}"
    return [INTERPRETERS[card["entrypoint"]], "-I", "-X", f"pycache_prefix={CARD_PATHS['PYTHONPYCACHEPREFIX']}", entry,
            *card["args"]]


def build_spec(request: dict, dev_dir: str, manifest: dict, seccomp: dict, mask_files: list[str]) -> dict:
    """The OCI spec of one card: nothing in it comes from the request but the entrypoint name, its kept-path
    arguments, the allowed environment and the cgroup name."""
    card, shared = request["card"], request["mode"] == POWER_CONTROL
    dev_opts = ["rbind", "nosuid", "noexec", "rw" if shared else "ro"]
    allow = [{"allow": False, "access": "rwm"}] + [
        {"allow": True, "type": "c", "major": ma, "minor": mi, "access": "rwm"} for ma, mi in NODES.values()]
    env = [f"{k}={v}" for k, v in {"PATH": "/usr/bin:/bin", **CARD_PATHS, **card["env"]}.items()]
    kept = [(KEPT_TREE, manifest.get("tree"))] + ([(KEPT_VENV, manifest["venv"])] if manifest.get("venv") else [])
    return {
        "ociVersion": "1.0.2",
        "process": {"terminal": False, "user": {"uid": CARD_UID, "gid": CARD_UID}, "args": card_argv(card),
                    "env": env, "cwd": "/tmp",
                    "capabilities": {k: [] for k in ("bounding", "effective", "inheritable", "permitted", "ambient")},
                    "noNewPrivileges": True},
        "root": {"path": ROOTFS, "readonly": True},
        "hostname": "card",
        "mounts": [
            {"destination": "/proc", "type": "proc", "source": "proc", "options": ["ro", "nosuid", "noexec", "nodev"]},
            *({"destination": p, "type": "bind", "source": f"{dev_dir}/mask/empty",
               "options": ["bind", "ro", "nosuid", "nodev", "noexec"]} for p in mask_files),
            {"destination": "/sys", "type": "sysfs", "source": "sysfs", "options": ["nosuid", "noexec", "nodev", "ro"]},
            {"destination": "/dev", "type": "bind", "source": f"{dev_dir}/dev", "options": dev_opts},
            {"destination": "/dev/shm", "type": "tmpfs", "source": "shm", "options": TMPFS},
            {"destination": "/tmp", "type": "tmpfs", "source": "tmpfs", "options": TMPFS},
            {"destination": "/var/tmp", "type": "tmpfs", "source": "tmpfs", "options": TMPFS},
            {"destination": "/run", "type": "tmpfs", "source": "tmpfs", "options": TMPFS},
            *({"destination": dest, "type": "bind", "source": src, "options": ["rbind", "ro", "nosuid", "nodev"]}
              for dest, src in kept),
        ],
        "linux": {
            "uidMappings": ID_MAP, "gidMappings": ID_MAP,
            "namespaces": [{"type": t} for t in ("pid", "network", "ipc", "uts", "mount", "cgroup", "user")],
            "devices": [],
            "rootfsPropagation": "rprivate",
            "cgroupsPath": f"/{CGROUP_NAME}/{card['card_id']}",
            "resources": {"devices": allow},
            "maskedPaths": MASK_DIRS, "readonlyPaths": READONLY,
            "seccomp": seccomp,
        },
    }


def _procs_mapped() -> int:
    count = 0
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                with open(f"/proc/{d}/status") as f:
                    uid = int(f.read().split("Uid:")[1].split()[0])
            except (OSError, IndexError, ValueError):
                continue
            count += uid >= ID_MAP[0]["hostID"]
    return count


def residue(card_id: str | None = None) -> dict:
    """Residue counts (``family3a.CLEAN`` keys) of one card, or of every family-3a card."""
    prefix = f"{RUN}/{card_id}" if card_id else f"{RUN}/gl3a-"
    with open("/proc/self/mountinfo") as f:
        mounts = sum(prefix in line for line in f)
    names = [d for d in os.listdir(RUN) if d.startswith("gl3a-")] if os.path.isdir(RUN) else []
    listed = _sh(CRUN, "--root", CRUN_ROOT, "list", "--quiet", check=False).stdout.split()
    groups = [d for d in os.listdir(CGROUP_PARENT) if os.path.isdir(f"{CGROUP_PARENT}/{d}")] \
        if os.path.isdir(CGROUP_PARENT) else []
    keep = (lambda n: n == card_id) if card_id else (lambda n: n.startswith("gl3a-"))
    counts = (mounts, sum(map(keep, names)), sum(map(keep, listed)), sum(map(keep, groups)), _procs_mapped())
    return dict(zip(CLEAN_KEYS, counts))


def _discard(stream) -> None:
    """Drain the card's stderr pipe and keep nothing."""
    while stream.read(1 << 16):
        pass


def run_card(request: dict) -> dict:
    manifest = _manifest()
    card, cid = request["card"], request["card"]["card_id"]
    if not manifest.get("image_digest") or not os.path.isdir(ROOTFS) or not manifest.get("tree"):
        raise Refused("the rootfs or the kept tree is not installed")
    if card["entrypoint"] == "proposer_host" and not manifest.get("venv"):
        raise Refused("the proposer card needs the kept venv")
    cdir = f"{RUN}/{cid}"
    if os.path.exists(cdir) or os.path.isdir(f"{CGROUP_PARENT}/{cid}"):
        raise Refused(f"card id {cid} was used before")
    seccomp = _seccomp()
    mask_files = [p for p in MASK_FILES if os.path.exists(p)]
    os.makedirs(CRUN_ROOT, exist_ok=True)
    os.makedirs(CGROUP_PARENT, exist_ok=True)
    shared = request["mode"] == POWER_CONTROL
    dev_dir = SHARED if shared else f"{cdir}/t"
    start, code = time.time_ns(), -1                      # -1: the card never ran (setup failed)
    try:
        os.makedirs(f"{cdir}/bundle")
        if not shared or not os.path.ismount(SHARED):
            make_dev(dev_dir)
        with open(f"{cdir}/bundle/config.json", "wb") as f:
            f.write(canonical(build_spec(request, dev_dir, manifest, seccomp, mask_files)))
        proc = subprocess.Popen([CRUN, "--root", CRUN_ROOT, "run", "--bundle", f"{cdir}/bundle", cid],
                                stdin=sys.stdin.fileno(), stdout=sys.stdout.fileno(), stderr=subprocess.PIPE)
        drain = threading.Thread(target=_discard, args=(proc.stderr,), daemon=True)
        drain.start()
        try:
            code = proc.wait(timeout=card["timeout_s"])
        except subprocess.TimeoutExpired:
            _sh(CRUN, "--root", CRUN_ROOT, "kill", cid, "KILL", check=False)
            code = proc.wait()
        drain.join(timeout=5)
        proc.stderr.close()
    except (OSError, subprocess.SubprocessError):
        code = -1
    finally:                                              # cleanup always runs, and its residue is always reported
        if _sh(CRUN, "--root", CRUN_ROOT, "state", cid, check=False).returncode == 0:
            _sh(CRUN, "--root", CRUN_ROOT, "delete", "--force", cid, check=False)
        if os.path.isdir(f"{CGROUP_PARENT}/{cid}"):
            try:
                os.rmdir(f"{CGROUP_PARENT}/{cid}")
            except OSError:
                pass
        if not shared and os.path.ismount(dev_dir) and _sh(UMOUNT, dev_dir, check=False).returncode != 0:
            _sh(UMOUNT, "-R", "-l", dev_dir, check=False)
        shutil.rmtree(cdir, ignore_errors=True)
    left = residue(cid)
    return {"schema": RESULT_SCHEMA, "card_id": cid, "mode": request["mode"], "exit_code": code,
            "window": {"start_ns": start, "end_ns": time.time_ns()}, "cleanup": left}


def control_teardown() -> dict:
    if os.path.ismount(SHARED):
        _sh(UMOUNT, SHARED)
    shutil.rmtree(SHARED, ignore_errors=True)
    return {"shared": os.path.exists(SHARED)}


def main(argv: list[str]) -> int:
    op, args = (argv[0], argv[1:]) if argv else ("", [])
    try:
        if os.geteuid() != 0:
            raise Refused("the family-3a helper runs as root only")
        if op == "identity" and not args:
            out = identity()
        elif op == "install-rootfs" and len(args) == 1:
            out = install_rootfs(args[0], sys.stdin.buffer)
        elif op == "configure-kept" and len(args) in (1, 2):
            out = configure_kept(args[0], args[1] if len(args) == 2 else None)
        elif op == "run" and len(args) == 1:
            result = run_card(decode_request(args[0]))
            sys.stderr.write(RESULT_PREFIX + json.dumps(result, sort_keys=True) + "\n")
            return 0
        elif op == "residue" and not args:
            out = residue()
        elif op == "control-teardown" and not args:
            out = control_teardown()
        else:
            raise Refused(f"operation {op!r} with {len(args)} argument(s) is not one of {OPERATIONS}")
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(out, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
