"""Who ran what, where: git identity, content-addressed WORKLOAD_ID and ENVIRONMENT_ID.

Two runs are only ever compared through these identities, so each one is built from content, never
from a timestamp, a path that moves with the checkout, or a value a caller merely asserts.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import site
import socket
import struct
import subprocess
import sys
import time
from typing import Iterable, Mapping, Sequence

from tools.run_observatory import ENVIRONMENT_SCHEMA, WORKLOAD_SCHEMA
from tools.run_observatory.redaction import Redactor, is_secret_name

#: Environment configuration that changes what a command computes or how fast. Bound into the
#: workload's config component by hash of value, never by value.
RELEVANT_ENV = ("PYTHONHASHSEED", "PYTHONOPTIMIZE", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "PYTEST_XDIST_AUTO_NUM_WORKERS")

#: Untracked files above this size are bound by (size, mtime) instead of content.
_LARGE_UNTRACKED_BYTES = 64 * 1024 * 1024
_GIT_TIMEOUT = 120

#: Environment-facts cache. An entry is reused only while every input its key binds is unchanged,
#: and never longer than the TTL, which bounds what the key cannot see (a GPU driver updated
#: without a reboot).
ENV_CACHE_VERSION = 1
ENV_CACHE_TTL_SECONDS = 24 * 3600


def canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def sha256_json(obj: object) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Git identity


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "--no-optional-locks", *args], cwd=cwd, capture_output=True, timeout=_GIT_TIMEOUT)


def _unknown_git(status: str, detail: str = "") -> dict:
    return {"status": status, "detail": detail, "repository_root": None, "branch": None, "detached": None,
            "head_sha": None, "tree_id": None, "tree_clean": None, "TREE_CLEAN": None,
            "uncommitted_diff_sha256": None, "untracked_sha256": None, "changed_paths": None, "code_identity": None}


def capture_git(path: Path | str) -> dict:
    """The exact code a run executes: HEAD, its tree, and a digest of every uncommitted change.

    ``--no-optional-locks`` keeps this read-only: ``git status`` would otherwise refresh and rewrite
    the observed checkout's index. A dirty tree is never collapsed into its HEAD -- its
    ``code_identity`` binds the diff and the untracked files, so it can never equal a clean one.
    """
    path = Path(path)
    if shutil.which("git") is None:
        return _unknown_git("GIT_UNAVAILABLE")
    try:
        # One call for root, HEAD, its tree and the symbolic ref; it fails as a whole outside a
        # repository or before the first commit, and the slow path below says which.
        fast = _git(path, "rev-parse", "--show-toplevel", "HEAD", "HEAD^{tree}", "--symbolic-full-name", "HEAD")
    except OSError as exc:
        return _unknown_git("UNAVAILABLE", str(exc))
    lines = fast.stdout.decode().splitlines()
    if fast.returncode != 0 or len(lines) != 4:
        top = _git(path, "rev-parse", "--show-toplevel")
        if top.returncode != 0:
            return _unknown_git("NOT_A_REPOSITORY")
        return {**_unknown_git("NO_COMMITS"), "repository_root": top.stdout.decode().strip()}
    root, head_sha, tree_id, ref = (Path(lines[0].strip()), *(line.strip() for line in lines[1:]))
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else None
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = [e for e in status.stdout.split(b"\0") if e]
    clean = not entries
    diff_digest = untracked_digest = None
    if not clean:
        diff = _git(root, "diff", "HEAD", "--binary", "--no-color", "--no-ext-diff", "--no-textconv")
        diff_digest = hashlib.sha256(diff.stdout).hexdigest()
        untracked_digest = _untracked_digest(root)
    code_identity = (f"tree:{tree_id}" if clean else
                     "dirty:" + sha256_json({"tree": tree_id, "diff": diff_digest, "untracked": untracked_digest}))
    return {
        "status": "OK", "detail": "", "repository_root": str(root),
        "branch": branch, "detached": branch is None, "head_sha": head_sha, "tree_id": tree_id,
        "tree_clean": clean, "TREE_CLEAN": clean, "uncommitted_diff_sha256": diff_digest,
        "untracked_sha256": untracked_digest, "changed_paths": len(entries), "code_identity": code_identity,
    }


def _untracked_digest(root: Path) -> str:
    listing = _git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    digest = hashlib.sha256()
    for raw in sorted(e for e in listing.split(b"\0") if e):
        target = root / raw.decode("utf-8", "surrogateescape")
        try:
            size = target.stat().st_size
            content = (f"stat:{size}:{target.stat().st_mtime_ns}" if size > _LARGE_UNTRACKED_BYTES
                       else sha256_file(target))
        except OSError:
            content = "unreadable"
        digest.update(raw + b"\0" + content.encode() + b"\n")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Workload identity


def _path_pattern(root: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in re.split(r"[\\/]+", root.rstrip("\\/")) if p]
    prefix = "/" if root.startswith(("/", "\\")) and not root.startswith("\\\\") else ""
    flags = re.IGNORECASE if os.name == "nt" else 0
    return re.compile(re.escape(prefix) + r"[\\/]+".join(parts) + r"(?![A-Za-z0-9_.~-])", flags)


def _roots(markers: Sequence[tuple[str, Path | None]]) -> list[tuple[str, re.Pattern[str]]]:
    out: list[tuple[str, re.Pattern[str]]] = []
    for marker, root in markers:
        if root is None:
            continue
        variants = {str(root), str(Path(root).resolve())}
        for variant in sorted(variants, key=len, reverse=True):
            out.append((marker, _path_pattern(variant)))
    return out


def _normalize(token: str, roots: list[tuple[str, re.Pattern[str]]]) -> str:
    for marker, pattern in roots:
        token = pattern.sub(lambda _m, marker=marker: marker, token)
    return token


def executable_name(argv0: str) -> str:
    """The program's name without its directory or Windows extension: where it is installed is environment."""
    name = re.split(r"[\\/]", argv0)[-1].lower()
    return re.sub(r"\.(exe|bat|cmd|com)$", "", name)


def _input_record(path: Path, roots: list[tuple[str, re.Pattern[str]]]) -> dict:
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file())
        listing = [(p.relative_to(path).as_posix(), sha256_file(p), p.stat().st_size) for p in files]
        return {"path": _normalize(str(path), roots), "kind": "directory", "files": len(listing),
                "bytes": sum(size for _, _, size in listing), "sha256": sha256_json(listing)}
    if not path.is_file():
        raise FileNotFoundError(f"declared workload input does not exist: {path}")
    return {"path": _normalize(str(path), roots), "kind": "file", "files": 1, "bytes": path.stat().st_size,
            "sha256": sha256_file(path)}


def workload_identity(*, argv: Sequence[str], cwd: Path | str, repo_root: Path | str | None = None,
                      run_root: Path | str | None = None, adapter: str = "GENERIC_COMMAND",
                      inputs: Iterable[Path | str] = (), configs: Iterable[Path | str] = (),
                      seeds: Iterable[str] = (), declared: Mapping[str, object] | None = None,
                      workload_env: Iterable[str] = (), environ: Mapping[str, str] | None = None,
                      redactor: Redactor | None = None) -> dict:
    """A content-addressed WORKLOAD_ID and the four components it is made of.

    ``command`` (adapter, program name, normalized arguments, working directory), ``inputs``
    (dataset content), ``declared`` (plan / provider / model identities a caller binds) and
    ``config`` (config-file content, seeds, relevant environment configuration). Paths under the
    repository or the run root are written relative to them, so the same workload has the same id
    in any checkout. Secret values never enter it.
    """
    environ = os.environ if environ is None else environ
    redactor = redactor or Redactor.from_environ(environ)
    roots = _roots([("{repo}", Path(repo_root) if repo_root else None),
                    ("{run_root}", Path(run_root) if run_root else None)])
    argv = redactor.redact_argv(list(argv))
    if not argv:
        raise ValueError("a workload needs a command")
    command = {"adapter": adapter, "executable": executable_name(argv[0]),
               "args": [_normalize(a, roots) for a in argv[1:]], "cwd": _normalize(str(cwd), roots)}
    input_records = sorted((_input_record(Path(p), roots) for p in inputs), key=lambda r: r["path"])
    config_records = sorted((_input_record(Path(p), roots) for p in configs), key=lambda r: r["path"])
    names = list(RELEVANT_ENV)
    for name in workload_env:
        if is_secret_name(name):
            raise ValueError(f"refusing to bind secret-named variable {name!r} into a workload identity")
        names.append(name)
    relevant_env = {n: hashlib.sha256(environ[n].encode()).hexdigest() if n in environ else "UNSET"
                    for n in sorted(set(names))}
    config = {"files": config_records, "seeds": [str(s) for s in seeds], "env_sha256": relevant_env}
    declared_record = {str(k): v for k, v in sorted(redactor.redact_mapping(dict(declared or {})).items())}
    components = {"command": sha256_json(command), "inputs": sha256_json(input_records),
                  "config": sha256_json(config), "declared": sha256_json(declared_record)}
    return {"schema": WORKLOAD_SCHEMA, "workload_id": sha256_json({"schema": WORKLOAD_SCHEMA, **components}),
            "components": components, "command": command, "inputs": input_records, "config": config,
            "declared": declared_record}


# ---------------------------------------------------------------------------
# Environment identity


def _packages() -> dict:
    from importlib import metadata  # ~40 ms of imports, paid only when the environment is probed

    names = set()
    for dist in metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            names.add(f"{re.sub(r'[-_.]+', '-', name).lower()}=={dist.version}")
    listing = sorted(names)
    return {"count": len(listing), "sha256": sha256_json(listing)}


def _cpu_model() -> str | None:
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        if system == "Linux":
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith(("model name", "hardware", "cpu model")):
                    return line.split(":", 1)[1].strip()
        if system == "Darwin":
            out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                 timeout=5)
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return platform.processor() or None


def _total_memory() -> int | None:
    from tools.run_observatory import metrics

    if metrics.psutil is not None:
        return int(metrics.psutil.virtual_memory().total)
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = MEMORYSTATUSEX(dwLength=ctypes.sizeof(MEMORYSTATUSEX))
        if ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
        return None
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def _gpu() -> dict:
    """GPU models when a vendor tool reports them; UNSUPPORTED otherwise, never an empty 'no GPU'."""
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run([smi, "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True,
                                 timeout=10)
            if out.returncode == 0:
                models = sorted(line.strip() for line in out.stdout.splitlines() if line.strip())
                return {"support": "SUPPORTED", "method": "nvidia-smi", "models": models, "count": len(models)}
        except (OSError, subprocess.SubprocessError):
            pass
    return {"support": "UNSUPPORTED", "method": "NONE", "models": None, "count": None,
            "note": "no vendor-neutral GPU probe; only nvidia-smi is queried in v1"}


def _runtime() -> dict:
    container = "none"
    if Path("/.dockerenv").exists():
        container = "docker"
    else:
        try:
            cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="replace")
            for marker in ("kubepods", "docker", "containerd", "lxc", "podman"):
                if marker in cgroup:
                    container = marker
                    break
        except OSError:
            pass
    return {"container": container, "wsl": "microsoft" in platform.release().lower(),
            "virtualenv": sys.prefix != sys.base_prefix}


def environment_facts(*, salt: bytes, child_executable: Path | str | None = None) -> dict:
    """What explains performance variation between machines, without one environment value or secret.

    The host appears only as a salted hash (pseudonymous, not anonymous: the salt lives in the run
    root). ``packages`` describes the observing interpreter; the child's own interpreter is bound
    through ``child_executable_sha256``.
    """
    from tools.run_observatory import metrics

    physical = metrics.psutil.cpu_count(logical=False) if metrics.psutil is not None else None
    facts = {
        "schema": ENVIRONMENT_SCHEMA,
        "os": {"system": platform.system(), "release": platform.release(), "version": platform.version()},
        "arch": platform.machine(),
        "python": {"implementation": platform.python_implementation(), "version": platform.python_version(),
                   "compiler": platform.python_compiler(), "bits": struct.calcsize("P") * 8},
        "packages": _packages(),
        "host_id": hashlib.sha256(salt + socket.gethostname().lower().encode()).hexdigest()[:16],
        "cpu": {"model": _cpu_model(), "logical_cores": os.cpu_count(), "physical_cores": physical,
                "physical_cores_support": "SUPPORTED" if physical else "UNSUPPORTED"},
        "memory": {"total_bytes": _total_memory()},
        "gpu": _gpu(),
        "runtime": _runtime(),
    }
    if child_executable is not None:
        try:
            facts["child_executable_sha256"] = sha256_file(Path(child_executable))
        except OSError:
            facts["child_executable_sha256"] = None
    return facts


def environment_identity(facts: Mapping[str, object]) -> str:
    return sha256_json(dict(facts))


# ---------------------------------------------------------------------------
# Environment-facts cache


def _boot_marker() -> int | None:
    """Boot time to the minute: a reboot (OS update, hardware change) invalidates every cached entry."""
    from tools.run_observatory import metrics

    try:
        if metrics.psutil is not None:
            return int(metrics.psutil.boot_time() // 60)
        if os.name == "nt":
            import ctypes

            uptime = ctypes.WinDLL("kernel32").GetTickCount64
            uptime.restype = ctypes.c_ulonglong
            return int((time.time() - uptime() / 1000) // 60)
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return int(line.split()[1]) // 60
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _site_stamp() -> list[list]:
    """Every site-packages directory and its mtime: installing or removing a distribution changes it."""
    dirs = list(site.getsitepackages()) if hasattr(site, "getsitepackages") else []
    user = site.getusersitepackages() if hasattr(site, "getusersitepackages") else None
    out = []
    for folder in sorted(set(dirs + ([user] if user else []))):
        try:
            out.append([folder, os.stat(folder).st_mtime_ns])
        except OSError:
            out.append([folder, None])
    return out


def _cache_key(salt: bytes, child_executable: Path | str | None) -> str:
    from tools.run_observatory import metrics

    child = None
    if child_executable is not None:
        try:
            stat = os.stat(child_executable)
            child = [str(child_executable), stat.st_size, stat.st_mtime_ns]
        except OSError:
            child = [str(child_executable), None, None]
    return sha256_json({"version": ENV_CACHE_VERSION, "schema": ENVIRONMENT_SCHEMA, "salt": salt.hex(),
                        "python": [sys.executable, sys.version, sys.prefix], "site": _site_stamp(),
                        "boot": _boot_marker(), "host": socket.gethostname(), "child": child,
                        "psutil": metrics.psutil is not None})


def cached_environment_facts(*, salt: bytes, child_executable: Path | str | None = None,
                             cache_dir: Path | None = None, refresh: bool = False) -> tuple[dict, str]:
    """Environment facts and where they came from: ``CACHE`` or ``PROBED``.

    Probing costs ~0.3 s (distribution list, WMI, ``nvidia-smi``); none of it changes without a
    reboot, a package (un)install, a new interpreter or a new child executable, and the key binds
    all of those. The facts are returned byte-identical either way, so the ENVIRONMENT_ID never
    depends on the cache.
    """
    if cache_dir is None:
        return environment_facts(salt=salt, child_executable=child_executable), "PROBED"
    key = _cache_key(salt, child_executable)
    entry = Path(cache_dir) / f"env-{key[:32]}.json"
    if not refresh:
        try:
            cached = json.loads(entry.read_text(encoding="utf-8"))
            fresh = 0 <= time.time() - cached["created_unix"] <= ENV_CACHE_TTL_SECONDS
            if fresh and cached["key"] == key and cached["facts"]["schema"] == ENVIRONMENT_SCHEMA:
                return cached["facts"], "CACHE"
        except (OSError, ValueError, KeyError, TypeError):
            pass
    facts = environment_facts(salt=salt, child_executable=child_executable)
    try:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        tmp = entry.with_name(f".{entry.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"key": key, "created_unix": time.time(), "facts": facts}), encoding="utf-8")
        os.replace(tmp, entry)
    except OSError:
        pass  # a cache that cannot be written only costs the next run a probe
    return facts, "PROBED"
