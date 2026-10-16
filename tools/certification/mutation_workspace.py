"""Per-shard isolated mutation storage. No verdict, population or resume authority.

Only the seed is populated from source. Workers use independent copies; after
an attempt, differences are repaired and the complete manifest is checked.
Unsupported seed links/special files are refused rather than followed.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import configparser
import ctypes
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import sys
from types import MappingProxyType
from typing import Mapping

from tools.certification.performance_telemetry import PerformanceTelemetry


class WorkspaceError(RuntimeError):
    """Storage/lifecycle failure: never a mutation verdict."""


class UndrainedProcessError(WorkspaceError):
    """Keep isolated storage for diagnosis; a child may still be using it."""


@dataclass(frozen=True)
class OwnedRoot:
    """In-memory proof of a newly created root and its original real ancestors.

    A filename/marker supplied by a caller is not deletion authority.
    """
    path: pathlib.Path
    identities: tuple

    @classmethod
    def create(cls, *, prefix, parent=None):
        path = pathlib.Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).absolute()
        chain = (path, *path.parents)
        identities = tuple((p, cls._identity(p)) for p in chain)
        return cls(path, identities)

    @staticmethod
    def _identity(path):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or path.resolve() != path.absolute():
            raise WorkspaceError("owned directory or ancestor is linked/substituted")
        return info.st_dev, info.st_ino

    def check(self):
        if any(self._identity(path) != identity for path, identity in self.identities):
            raise WorkspaceError("owned directory identity changed; cleanup refused")

    def remove(self):
        self.check()
        shutil.rmtree(self.path)


@dataclass(frozen=True)
class Entry:
    kind: str
    mode: int
    sha256: str = ""
    target: str = ""
    links: int = 1
    size: int = 0


def require_isolated(root, path):
    root, path = pathlib.Path(root).resolve(), pathlib.Path(path).resolve()
    if path == root or root in path.parents or path in root.parents:
        raise WorkspaceError(f"{path}: isolated storage must not overlap source {root}")


def _digest(path, *, telemetry=None, area=None, relative=None):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            if telemetry is not None:
                telemetry.increment(f"{area}_bytes_read", len(chunk))
                if relative and relative.startswith(".git/"):
                    telemetry.increment("git_bytes_processed", len(chunk))
    if telemetry is not None:
        telemetry.increment(f"{area}_files_hashed")
    return digest.hexdigest()


#: Windows ``IO_REPARSE_TAG_MOUNT_POINT`` (a junction). ``stat`` defines it only on Windows; only Windows sets the tag.
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003


def _is_junction(entry, info):
    """A Windows junction: ``DirEntry.is_junction`` on 3.12+, the stat reparse tag on 3.11. Never walked."""
    probe = getattr(entry, "is_junction", None)
    if probe is not None:
        return probe()
    return getattr(info, "st_reparse_tag", 0) == _IO_REPARSE_TAG_MOUNT_POINT


def snapshot(tree, *, identity=None, telemetry=None, area=None):
    """Complete deterministic relative manifest; never follow directory links."""
    tree = pathlib.Path(tree)
    info = tree.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise WorkspaceError("workspace root is missing, linked or not a directory")
    rows = {"": Entry("directory", stat.S_IMODE(info.st_mode))}
    # Relative names are built from scandir names, not pathlib.relative_to: per-entry
    # pathlib work cost ~5x the SHA-256 of every byte (Pass 9 profile). Same rows.
    scanned = {"entries_structurally_scanned": 0, "files_structurally_scanned": 0,
               "git_files_processed": 0}

    def walk(directory, prefix):
        with os.scandir(directory) as handle:
            children = sorted(handle, key=lambda e: os.fsencode(e.name))
        for child in children:
            relative = prefix + child.name
            info = child.stat(follow_symlinks=False)
            if info.st_nlink == 0:
                # Windows: a scandir entry's stat always reports st_nlink 0 (and no inode); a hard link is
                # only visible to a real lstat. Never read 0 as "not linked" -- ask the filesystem.
                info = os.lstat(child.path)
            mode = stat.S_IMODE(info.st_mode)
            scanned["entries_structurally_scanned"] += 1
            if _is_junction(child, info):
                # A Windows junction is a directory link that S_ISDIR does not distinguish; never walked.
                rows[relative] = Entry("special", mode)
            elif stat.S_ISDIR(info.st_mode):
                rows[relative] = Entry("directory", mode)
                walk(child.path, relative + "/")
            elif stat.S_ISREG(info.st_mode):
                scanned["files_structurally_scanned"] += 1
                if relative.startswith(".git/"):
                    scanned["git_files_processed"] += 1
                path = pathlib.Path(child.path)
                rows[relative] = Entry("file", mode,
                                       identity(path, relative) if identity else _digest(
                                           path, telemetry=telemetry, area=area, relative=relative),
                                       links=info.st_nlink, size=info.st_size)
            elif stat.S_ISLNK(info.st_mode):
                rows[relative] = Entry("symlink", mode, target=os.readlink(child.path))
            else:
                rows[relative] = Entry("special", mode)
    try:
        walk(os.fspath(tree), "")
    finally:
        if telemetry is not None:
            for category, amount in scanned.items():
                if amount:
                    telemetry.increment(category, amount)
    return dict(sorted(rows.items()))


def owned_snapshot(root, *, telemetry=None, area=None):
    """A manifest of a SOURCE checkout: only repository-owned files (tracked, or untracked outside
    environment roots), never an environment tree such as ``.forge/venvs``.

    :func:`snapshot` stays a complete record of a seed or worker -- that is integrity checking, and a
    worker that grew an environment must show it. A traversal of the checkout itself is an ownership
    question, answered once by :mod:`tools.certification.ownership`; a refused symlink fails it.
    """
    from tools.certification.ownership import owned_files

    owned = owned_files(root)
    if owned.refused:
        raise WorkspaceError(f"source checkout holds symlinks that are never followed: {list(owned.refused)}")
    rows = {}
    for relative in owned.files:
        path = pathlib.Path(owned.root) / relative
        info = path.lstat()
        rows[relative] = Entry("file", stat.S_IMODE(info.st_mode),
                               _digest(path, telemetry=telemetry, area=area, relative=relative),
                               links=info.st_nlink, size=info.st_size)
    return dict(sorted(rows.items()))


def environment_trees(tree):
    """Environment roots present in a populated tree (an explicit external root, or a directory that IS an env)."""
    from tools.certification.ownership import EXTERNAL_ROOTS, is_environment_dir

    tree = pathlib.Path(tree)
    found = [name for name in EXTERNAL_ROOTS if (tree / name).exists()]
    for directory, dirnames, _files in os.walk(tree, followlinks=False):
        for name in list(dirnames):
            path = pathlib.Path(directory) / name
            if is_environment_dir(path):
                found.append(path.relative_to(tree).as_posix())
                dirnames.remove(name)
    return sorted(set(found))


def manifest_digest(rows):
    blob = json.dumps({name: asdict(entry) for name, entry in rows.items()},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(blob).hexdigest()



@dataclass(frozen=True)
class PristineIndex:
    entries: Mapping[str, Entry]
    sha256: str

    @classmethod
    def build(cls, seed, *, telemetry=None):
        # File bytes are streamed in bounded chunks, never retained in the index.
        entries = snapshot(seed, telemetry=telemetry, area="seed")
        if any(e.kind not in {"file", "directory"} or
               (e.kind == "file" and e.links != 1) for e in entries.values()):
            raise WorkspaceError("pristine seed contains links or special files")
        return cls(MappingProxyType(entries), manifest_digest(entries))


@dataclass(frozen=True)
class WorkerDeltas:
    intended: frozenset[str] = frozenset()
    created: frozenset[str] = frozenset()
    deleted: frozenset[str] = frozenset()
    metadata_changed: frozenset[str] = frozenset()
    content_changed: frozenset[str] = frozenset()


def _metadata(entry):
    return replace(entry, sha256="")


def mutation_target(work, spec):
    """A declared edit can reach only a regular independent file in its worker."""
    relative = spec.partition("::")[0]
    parts = pathlib.PurePosixPath(relative)
    if (not relative or "\\" in relative or parts.is_absolute()
            or any(part in {".", ".."} for part in relative.split("/"))):
        raise WorkspaceError(f"unsafe mutation target {relative!r}")
    work = pathlib.Path(work)
    target = work
    for part in parts.parts:
        target = target / part
        if target.is_symlink():
            raise WorkspaceError(f"linked mutation target {relative!r}")
    info = target.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise WorkspaceError(f"mutation target is not an independent regular file: {relative}")
    if work.resolve() not in target.resolve().parents:
        raise WorkspaceError(f"mutation target escapes worker: {relative}")
    return target


def artifact_path(root, scratch, *parts):
    """Owned external outputs must not redirect writes/pytest cleanup via links."""
    scratch = pathlib.Path(scratch).resolve()
    require_isolated(root, scratch)
    relative = pathlib.PurePosixPath(*parts)
    if relative.is_absolute() or any(p in {".", ".."} for p in relative.parts):
        raise WorkspaceError("unsafe artifact path")
    target = scratch
    for part in relative.parts:
        if "\\" in part:
            raise WorkspaceError("unsafe artifact path")
        target = target / part
        if target.is_symlink():
            raise WorkspaceError("linked artifact path")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _remove(path):
    info = path.lstat()
    if stat.S_ISDIR(info.st_mode):
        # Owner-only permissions allow repair of a directory made read-only by a test.
        path.chmod(stat.S_IMODE(info.st_mode) | stat.S_IRWXU)
        shutil.rmtree(path)
    else:
        path.unlink()



def _unlock_directories(tree):
    # Cleanup never follows a substituted seed directory link into source.
    if not stat.S_ISDIR(tree.lstat().st_mode):
        return
    tree.chmod(stat.S_IMODE(tree.lstat().st_mode) | 0o700)
    with os.scandir(tree) as handle:
        directories = [pathlib.Path(e.path) for e in handle if e.is_dir(follow_symlinks=False)]
    for directory in directories:
        _unlock_directories(directory)

def _check_git_seed(seed):
    git = seed / ".git"
    if not git.exists():
        return
    if not git.is_dir():
        raise WorkspaceError("pristine .git is not an independent directory")
    config = configparser.ConfigParser(interpolation=None)
    config_path = git / "config"
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            text = handle.read(1024 * 1024 + 1)
        if len(text) > 1024 * 1024:
            raise WorkspaceError("pristine .git config exceeds bounded admission size")
        try:
            config.read_string(text)
        except configparser.Error as exc:
            raise WorkspaceError("pristine .git config syntax is unsupported") from exc
    external_core = {"worktree", "hookspath", "fsmonitor", "attributesfile",
                     "excludesfile", "sshcommand", "pager", "alternateobjectdirectories"}
    for section in config.sections():
        # ConfigParser is not Git grammar. Refuse forms we cannot interpret safely.
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*(?: "[^"\\\r\n]+")?', section) is None:
            raise WorkspaceError("pristine .git config has unsupported section syntax")
        folded = section.casefold()
        if folded.startswith("include"):
            raise WorkspaceError("pristine .git config includes external configuration")
        if folded == "core" and external_core.intersection(config[section]):
            raise WorkspaceError("pristine .git config redirects storage or external helpers")
        if folded == "extensions" and config.has_option(section, "objectformat"):
            if config.get(section, "objectformat").strip().casefold() != "sha1":
                raise WorkspaceError("pristine .git config uses an unsupported object format")
        if (folded.startswith(("filter ", "diff ", "merge ", "credential")) or
                (folded == "diff" and config.has_option(section, "external")) or
                (folded == "extensions" and any(key != "objectformat" for key in config[section])) or
                (folded.startswith("remote ") and config.has_option(section, "promisor"))):
            raise WorkspaceError("pristine .git config selects external helpers or worktree state")
    # Partial clones can make even git show fetch missing objects from outside.
    if any(path.name.endswith(".promisor") for path in (git / "objects" / "pack").glob("*")):
        raise WorkspaceError("pristine .git contains promisor objects")
    if (seed / ".gitmodules").exists() or (git / "modules").exists():
        raise WorkspaceError("pristine Git submodule state is unsupported")
    for pointer in ("commondir", "gitdir", "objects/info/alternates",
                    "objects/info/http-alternates", "config.worktree", "worktrees",
                    "info/grafts", "refs/replace"):
        if (git / pointer).exists():
            raise WorkspaceError("pristine .git refers to external Git storage or rewritten history")
    packed = git / "packed-refs"
    if packed.exists():
        with packed.open(encoding="utf-8") as handle:
            while True:
                line = handle.readline(1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 1024 * 1024:
                    raise WorkspaceError("pristine .git packed ref exceeds bounded admission size")
                if any(part == "refs/replace" or part.startswith("refs/replace/") for part in line.split()):
                    raise WorkspaceError("pristine .git packed refs rewrite history")


def mutation_environment(runtime, inherited=None, *, work=None):
    """Seal host redirects; preserve cwd discovery for test-created repositories.

    Builtin pytest plugins and conftest remain; external autoload is disabled.
    PATH, virtualenv, solver/provider settings remain controlled toolchain inputs.
    """
    inherited = os.environ if inherited is None else inherited
    neutralized = {"PYTEST_ADDOPTS", "PYTEST_PLUGINS"}
    env = {key: value for key, value in inherited.items()
           if not key.upper().startswith(("GIT_", "PYTHON")) and key not in neutralized}
    template = pathlib.Path(runtime) / "git-template"
    template.mkdir()
    if work is not None:
        ceiling = pathlib.Path(work).resolve().parent
        env["GIT_CEILING_DIRECTORIES"] = str(ceiling)
    env["GIT_DISCOVERY_ACROSS_FILESYSTEM"] = "0"
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TEMPLATE_DIR": str(template),
                "GIT_CONFIG_COUNT": "3", "GIT_CONFIG_KEY_0": "core.hooksPath",
                "GIT_CONFIG_VALUE_0": os.devnull,
                "GIT_CONFIG_KEY_1": "core.excludesFile", "GIT_CONFIG_VALUE_1": os.devnull,
                "GIT_CONFIG_KEY_2": "core.attributesFile", "GIT_CONFIG_VALUE_2": os.devnull,
                "PYTHONNOUSERSITE": "1",
                "TMPDIR": str(runtime), "TEMP": str(runtime), "TMP": str(runtime)})
    from tools.certification.mutation_startup import MUTATION_ENVIRONMENT
    env.update(MUTATION_ENVIRONMENT)
    return env


class PersistentWorkspace:
    """Independent seed/worker/index per shard; every worker boundary is hashed.

    Seed files are protected against accidental writes and hashed in full against
    immutable indexed digests. Restoration streams from the checked seed.
    Restore hints never authorize skipping worker SHA.
    """
    def __init__(self, root, scratch, populate, telemetry=None):
        self.root = pathlib.Path(root).resolve()
        self.scratch = pathlib.Path(scratch).resolve()
        require_isolated(self.root, self.scratch)
        self.populate = populate
        from tools.certification.mutation_startup import StartupInputs
        self.startup = StartupInputs.capture()
        self.telemetry = telemetry or PerformanceTelemetry(
            self.scratch / "performance.json", shard=os.environ.get("FORGE_MUTATION_SHARD", "standalone"))
        self.poisoned = False
        self.home = None
        self.undrained = False
        self.started = None
        self.intended = frozenset()
        self.last_deltas = WorkerDeltas()

    def __enter__(self):
        require_isolated(self.root, self.scratch)
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.started = self.telemetry.start()
        self.owned = OwnedRoot.create(prefix="workspace-", parent=self.scratch)
        self.home = self.owned.path
        self.seed, self.work = self.home / "seed", self.home / "worker"
        try:
            self.artifacts = self.home / "artifacts"
            self.artifacts.mkdir()
            self.artifact_identity = OwnedRoot._identity(self.artifacts)
            self.telemetry.stage("seed_population_started")
            with self.telemetry.measure("seed_population"):
                self.populate(self.root, self.seed)
            # Scanner ownership (hostile review): mutation evidence is about repository source, never a toolchain.
            carried = environment_trees(self.seed)
            if carried:
                raise WorkspaceError(f"the populated seed carries environment trees {carried}; refused")
            self.telemetry.stage("seed_created")
            self.telemetry.stage("seed_indexing_started")
            with self.telemetry.measure("seed_indexing"):
                self.index = PristineIndex.build(self.seed, telemetry=self.telemetry)
                self.baseline = self.index.entries  # Compatibility for existing callers/specifications.
                self.baseline_sha256 = self.index.sha256
                _check_git_seed(self.seed)
                self.structure = MappingProxyType({n: _metadata(e) for n, e in self.baseline.items()})
            self.telemetry.stage("seed_indexed")
            self.telemetry.stage("worker_initialization_started")
            with self.telemetry.measure("worker_initialization"):
                shutil.copytree(self.seed, self.work, symlinks=True)
            self.telemetry.stage("worker_created")
            # Change seed permissions only after the worker inherits original modes.
            self.seed_baseline = MappingProxyType({
                n: replace(e, mode=e.mode & ~0o222) for n, e in self.baseline.items()})
            for name in reversed(tuple(self.baseline)):
                (self.seed / name).chmod(self.seed_baseline[name].mode)
            self.verify()
            return self
        except BaseException as exc:
            self.poisoned = True
            self.telemetry.failure(exc)
            try:
                self._cleanup()
            finally:
                self.telemetry.finish("shard_total", self.started)
                self.telemetry.write()
            raise

    def artifact_path(self, *parts):
        self.owned.check()
        if OwnedRoot._identity(self.artifacts) != self.artifact_identity:
            self.poisoned = True
            raise WorkspaceError("owned artifact directory identity changed")
        return artifact_path(self.root, self.artifacts, *parts)

    def _verify_seed(self):
        try:
            self.owned.check()
            self.telemetry.stage("seed_identity_verification_started")
            with self.telemetry.measure("seed_identity_verification"):
                checked = snapshot(self.seed, telemetry=self.telemetry, area="seed")
                if checked != self.seed_baseline:
                    changed = next((n for n in sorted(set(checked) | set(self.seed_baseline))
                                    if checked.get(n) != self.seed_baseline.get(n)), None)
                    error = WorkspaceError("pristine seed changed; round is invalid")
                    error.path = changed
                    raise error
            self.telemetry.stage("seed_verified")
        except BaseException as exc:
            self.poisoned = True
            self.telemetry.failure(exc, category="seed_identity_failure")
            raise

    def _worker_snapshot(self):
        self.telemetry.stage("cryptographic_verification_started")
        with self.telemetry.measure("cryptographic_verification"):
            return snapshot(self.work, telemetry=self.telemetry, area="worker")  # All files, including .git.

    def verify(self):
        if self.poisoned:
            raise WorkspaceError("workspace was invalidated; cannot continue")
        try:
            self._verify_seed()
            if self._worker_snapshot() != self.baseline:
                raise WorkspaceError("worker is contaminated; round is invalid")
            self.telemetry.stage("worker_verified_pristine")
        except BaseException as exc:
            self.poisoned = True
            self.telemetry.failure(exc)
            raise

    def _detect_deltas(self):
        self.telemetry.stage("delta_detection_started")
        with self.telemetry.measure("delta_detection"):
            current = snapshot(self.work, identity=lambda path, name: "", telemetry=self.telemetry, area="worker")
            common = set(current) & set(self.structure)
            self.last_deltas = WorkerDeltas(
                intended=self.intended,
                created=frozenset(set(current) - set(self.structure)),
                deleted=frozenset(set(self.structure) - set(current)),
                metadata_changed=frozenset(n for n in common if current[n] != self.structure[n]))
        return current

    def _real_directory(self, name):
        # Inspect each component: checking only the final component follows ancestors.
        path = self.work
        for component in ("", *pathlib.PurePosixPath(name).parts):
            if component:
                path = path / component
            try:
                if not stat.S_ISDIR(path.lstat().st_mode):
                    return None
            except FileNotFoundError:
                return None
        return path

    def _restore_file(self, name):
        # The seed filesystem is the only restoration source, never worker bytes.
        if self._real_directory(str(pathlib.PurePosixPath(name).parent)) is None:
            raise WorkspaceError("worker restoration ancestor is not a real directory")
        seed_path = mutation_target(self.seed, name)  # No linked ancestors or hardlinks.
        expected = self.seed_baseline[name]
        path = self.work / name
        with open(seed_path, "rb", opener=lambda file, flags: os.open(file, flags | os.O_NOFOLLOW)) as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != expected.links or
                    info.st_size != expected.size or stat.S_IMODE(info.st_mode) != expected.mode):
                raise WorkspaceError("pristine seed metadata changed during restoration")
            if path.exists() or path.is_symlink():
                _remove(path)
            digest, size = hashlib.sha256(), 0
            with path.open("xb") as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
                    self.telemetry.increment("seed_bytes_read", len(chunk))
                    self.telemetry.increment("restoration_bytes_copied", len(chunk))
                    if name.startswith(".git/"):
                        self.telemetry.increment("git_bytes_processed", len(chunk))
            self.telemetry.increment("seed_files_hashed")
            if name.startswith(".git/"):
                self.telemetry.increment("git_files_processed")
            if size != expected.size or digest.hexdigest() != expected.sha256:
                error = WorkspaceError("pristine seed content changed during restoration")
                error.path = name
                raise error
        path.chmod(self.baseline[name].mode)
        self.telemetry.increment("files_restored")

    def _repair(self, current, names):
        names = set(names)
        directories = {n for n in names if n in self.baseline and self.baseline[n].kind == "directory"}
        for name in tuple(names):
            parent = pathlib.PurePosixPath(name).parent
            while str(parent) != ".":
                directories.add(parent.as_posix())
                parent = parent.parent
        if names:
            directories.add("")
        reset_modes = set()
        # Enable only affected existing directory ancestors, without following links.
        for name in sorted(directories, key=lambda n: (n.count("/"), n)):
            path = self._real_directory(name)
            if path is None:
                continue
            mode = stat.S_IMODE(path.lstat().st_mode)
            if mode & 0o700 != 0o700:
                path.chmod(mode | 0o700)
                reset_modes.add(name)
        for name in sorted((n for n in names if n), key=lambda n: (n.count("/"), n), reverse=True):
            actual, wanted = current.get(name), self.baseline.get(name)
            if actual is not None and (wanted is None or actual.kind != wanted.kind):
                if self._real_directory(str(pathlib.PurePosixPath(name).parent)) is None:
                    raise WorkspaceError("worker deletion ancestor is not a real directory")
                _remove(self.work / name)
        # Recreate only missing/replaced directories and restore changed directory modes.
        directories.update(n for n in names if n in self.baseline and self.baseline[n].kind == "directory")
        for name in sorted(directories, key=lambda n: (n.count("/"), n)):
            if name not in self.baseline:
                continue
            if name and self._real_directory(str(pathlib.PurePosixPath(name).parent)) is None:
                raise WorkspaceError("worker directory restoration ancestor is not a real directory")
            path = self.work / name
            if not path.exists():
                path.mkdir()
                reset_modes.add(name)
            if name in names:
                reset_modes.add(name)
        for name in sorted(names):
            if name in self.baseline and self.baseline[name].kind == "file":
                wanted, actual = self.baseline[name], current.get(name)
                if actual is not None and actual.kind == "file" and actual.links == 1 and actual.size == wanted.size:
                    digest = actual.sha256 or _digest(self.work / name, telemetry=self.telemetry,
                                                      area="worker_candidate", relative=name)
                    if digest == wanted.sha256:
                        # An authenticated clean candidate needs no seed read or rewrite.
                        if actual.mode != wanted.mode:
                            (self.work / name).chmod(wanted.mode)
                        continue
                self._restore_file(name)
        for name in sorted(reset_modes, key=lambda n: (n.count("/"), n), reverse=True):
            if name in self.baseline and self.baseline[name].kind == "directory":
                path = self._real_directory(name)
                if path is None:
                    raise WorkspaceError("worker mode restoration ancestor is not a real directory")
                path.chmod(self.baseline[name].mode)

    def restore(self):
        if self.poisoned or self.undrained:
            raise WorkspaceError("workspace is invalidated; restoration cannot authorize reuse")
        try:
            self.telemetry.stage("restore_started")
            # Validate the entire seed before repairing even one worker entry.
            self._verify_seed()
            current = self._detect_deltas()
            dirty = (self.last_deltas.intended | self.last_deltas.created |
                     self.last_deltas.deleted | self.last_deltas.metadata_changed)
            with self.telemetry.measure("restore"):
                self._repair(current, dirty)
            # Hints/metadata are never proof. Detect unrelated same-size byte changes here.
            checked = self._worker_snapshot()
            if checked != self.baseline:
                hidden = {n for n in self.baseline if n in checked and
                          self.baseline[n].kind == "file" and
                          _metadata(checked[n]) == self.structure[n] and
                          checked[n].sha256 != self.baseline[n].sha256}
                # Structural repair failures/new contamination are not silently retried.
                if {n: _metadata(e) for n, e in checked.items()} != dict(self.structure) or not hidden:
                    raise WorkspaceError("worker repair did not restore pristine structure")
                self.last_deltas = replace(self.last_deltas, content_changed=frozenset(hidden))
                self.telemetry.stage("unrelated_content_detected", paths=sorted(hidden))
                with self.telemetry.measure("restore"):
                    self._repair(checked, hidden)
                self.verify()  # Full verification again after the additional, bounded repair.
            self.telemetry.stage("restore_finished")
            self.telemetry.stage("pristine_verified")
        except BaseException as exc:
            self.poisoned = True
            self.telemetry.failure(exc)
            raise WorkspaceError("restoration failed; mutation round is invalid") from exc

    @contextmanager
    def attempt(self, *, mutation_id=None, intended=()):
        self.telemetry.context(mutation_id=mutation_id)
        self.intended = frozenset(spec.partition("::")[0] for spec in intended)
        for name in self.intended:
            if name not in self.baseline or self.baseline[name].kind != "file":
                self.poisoned = True
                error = WorkspaceError(f"declared mutation path is outside pristine index: {name}")
                self.telemetry.failure(error, category="invalid_mutation_path")
                raise error
        self.verify()
        try:
            yield self.work
        except BaseException as exc:
            self.telemetry.failure(exc)
            if isinstance(exc, WorkspaceError):
                self.poisoned = True
            if isinstance(exc, UndrainedProcessError):
                self.poisoned = True
                self.undrained = True
                self.telemetry.context(worker_retained=True, retained_path=str(self.home), descendant_quiescence=False)
            raise
        finally:
            if not self.undrained and not self.poisoned:
                self.restore()

    def _cleanup(self):
        self.telemetry.stage("cleanup_started")
        try:
            with self.telemetry.measure("cleanup"):
                require_isolated(self.root, self.home)
                self.owned.check()
                if self.seed.exists() or self.seed.is_symlink():
                    _unlock_directories(self.seed)
                self.owned.remove()
            self.telemetry.stage("cleanup_finished")
        except BaseException as exc:
            self.telemetry.context(worker_retained=True, retained_path=str(self.home))
            self.telemetry.failure(exc)
            raise

    def __exit__(self, kind, value, trace):
        try:
            if self.undrained:
                self.telemetry.context(worker_retained=True, retained_path=str(self.home), descendant_quiescence=False)
                self.telemetry.stage("workspace_retained")
                raise UndrainedProcessError(f"undrained target; isolated storage retained at {self.home}")
            self._cleanup()
        finally:
            self.telemetry.finish("shard_total", self.started)
            self.telemetry.write()


_PROCESS_LOCK = threading.Lock()
_PROCESS_POISONED = False


def _subreaper(setting=None):
    if not sys.platform.startswith("linux"):
        raise WorkspaceError("persistent target ownership requires Linux child-subreaper support")
    libc = ctypes.CDLL(None, use_errno=True)
    if setting is None:
        value = ctypes.c_int()
        result = libc.prctl(37, ctypes.byref(value), 0, 0, 0)  # PR_GET_CHILD_SUBREAPER
        if result != 0:
            raise WorkspaceError("cannot inspect Linux child-subreaper state")
        return value.value
    if libc.prctl(36, int(setting), 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise WorkspaceError("cannot establish Linux child-subreaper ownership")


def _children(pid):
    """Kernel-owned children across threads; errors cannot establish an empty scope."""
    tasks = pathlib.Path(f"/proc/{pid}/task")
    try:
        threads = list(tasks.iterdir())
    except FileNotFoundError as exc:
        raise WorkspaceError("Linux /proc child ownership is unavailable") from exc
    if not threads:
        raise WorkspaceError("Linux /proc contains no inspectable owner thread")
    children = set()
    for thread in threads:
        try:
            text = (thread / "children").read_text(encoding="ascii")
        except FileNotFoundError as exc:
            if thread.exists():
                raise WorkspaceError("Linux /proc child listing is unavailable") from exc
            continue  # An exited thread cannot be an active owner.
        children.update(int(value) for value in text.split())
    return children


def _drain_children():
    # The single shard process has no unrelated children. As a subreaper it
    # adopts orphaned descendants, including children that detach with setsid.
    deadline = time.monotonic() + 3.0
    while True:
        _check_reaper_state(expected_subreaper=1)
        children = _children(os.getpid())
        for pid in children:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        while True:
            try:
                reaped, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if reaped == 0:
                break
        if not _children(os.getpid()):
            _check_reaper_state(expected_subreaper=1)
            return
        if time.monotonic() >= deadline:
            raise UndrainedProcessError("owned target descendants could not be drained")
        time.sleep(0.01)


def _check_reaper_state(*, expected_subreaper=None):
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise UndrainedProcessError("SIGCHLD handler may compete for child ownership")
    if signal.SIGCHLD in signal.pthread_sigmask(signal.SIG_BLOCK, set()):
        raise UndrainedProcessError("blocked SIGCHLD makes shard ownership incompatible")
    if len(tuple(pathlib.Path(f"/proc/{os.getpid()}/task").iterdir())) != 1:
        raise UndrainedProcessError("dedicated shard requires exactly one kernel thread")
    if expected_subreaper is not None and _subreaper() != expected_subreaper:
        raise UndrainedProcessError("shard subreaper state changed during ownership")


def _check_process_owner():
    """Fail closed on detectable competing owners before any target launch."""
    if not sys.platform.startswith("linux") or threading.current_thread() is not threading.main_thread():
        raise UndrainedProcessError("dedicated Linux shard main thread is required")
    _check_reaper_state()
    if _children(os.getpid()):
        raise UndrainedProcessError("shard process has unrelated children; ownership is ambiguous")
    if _subreaper() != 0:
        raise UndrainedProcessError("shard process already owns a subreaper role")


def run_captured(argv, *, cwd, timeout, telemetry=None, inherited=None):
    """Exclusive Linux descendant ownership; diagnostics cannot establish quiescence."""
    global _PROCESS_POISONED
    performance = telemetry or PerformanceTelemetry(None)
    if not _PROCESS_LOCK.acquire(blocking=False):
        performance.context(worker_retained=True, descendant_quiescence=False)
        performance.increment("workers_retained_ownership_uncertain")
        raise UndrainedProcessError("concurrent targets cannot share one shard process")
    prior = None
    process = None
    term_handler = None
    ownership_active = False
    runtime = None
    quiescent = False
    runtime_owned = None
    try:
        if _PROCESS_POISONED:
            raise UndrainedProcessError("target ownership was invalidated; cannot execute again")
        try:
            _check_process_owner()
        except BaseException as exc:
            _PROCESS_POISONED = True
            performance.context(worker_retained=True, descendant_quiescence=False)
            performance.increment("workers_retained_ownership_uncertain")
            performance.failure(exc, category="process_ownership_ambiguous")
            raise UndrainedProcessError("dedicated shard ownership cannot be established") from exc
        try:
            prior = _subreaper()
            _subreaper(1)
            if _subreaper() != 1:
                raise WorkspaceError("Linux subreaper ownership was not established")
        except BaseException as exc:
            _PROCESS_POISONED = True
            performance.context(worker_retained=True, descendant_quiescence=False)
            performance.increment("workers_retained_ownership_uncertain")
            performance.failure(exc, category="process_ownership_setup_failure")
            raise UndrainedProcessError("Linux ownership setup failed") from exc
        ownership_active = True
        term_handler = signal.getsignal(signal.SIGTERM)
        def interrupted(signum, frame):
            raise KeyboardInterrupt("mutation worker interrupted")
        signal.signal(signal.SIGTERM, interrupted)
        performance.context(descendant_quiescence=False)
        runtime_owned = OwnedRoot.create(prefix="runtime-", parent=pathlib.Path(cwd).parent)
        runtime = runtime_owned.path
        env = mutation_environment(runtime, inherited, work=cwd)
        performance.stage("subprocess_starting")
        with performance.measure("test_subprocess"):
            process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, start_new_session=True,
                                       close_fds=True, pass_fds=(), env=env)
            performance.stage("subprocess_started")
            stdout, stderr = process.communicate(timeout=timeout)
            performance.stage("subprocess_finished")
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    except BaseException as exc:
        performance.failure(exc)
        raise
    finally:
        try:
            # Include failures during Popen construction: a child may exist even
            # though assignment of the process object never completed.
            if ownership_active:
                try:
                    if term_handler is not None:
                        signal.signal(signal.SIGTERM, signal.SIG_IGN)
                    performance.stage("descendant_drain_started")
                    with performance.measure("descendant_drain"):
                        _drain_children()
                        if process is not None:
                            process.wait(timeout=0)
                    quiescent = True
                    performance.context(descendant_quiescence=True)
                    performance.stage("descendants_drained")
                except BaseException as exc:
                    _PROCESS_POISONED = True
                    performance.context(descendant_quiescence=False, worker_retained=True)
                    performance.increment("workers_retained_ownership_uncertain")
                    performance.failure(exc, category="descendant_quiescence_unproven")
                    raise UndrainedProcessError("target lifetime is unproven; round refused") from exc
        finally:
            try:
                if process is not None:
                    try:
                        if process.stdout is not None:
                            process.stdout.close()
                    finally:
                        if process.stderr is not None:
                            process.stderr.close()
            finally:
                try:
                    try:
                        if runtime is not None and quiescent:
                            runtime_owned.remove()
                    finally:
                        if prior is not None and not _PROCESS_POISONED:
                            try:
                                _subreaper(prior)
                            except BaseException as exc:
                                _PROCESS_POISONED = True
                                performance.context(worker_retained=True)
                                performance.failure(exc, category="process_ownership_release_failure")
                                raise UndrainedProcessError("shard ownership release failed") from exc
                finally:
                    try:
                        if term_handler is not None:
                            signal.signal(signal.SIGTERM, term_handler)
                    finally:
                        _PROCESS_LOCK.release()
