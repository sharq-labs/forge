"""Which files in a checkout belong to the repository: one rule for every assurance traversal of source.

Hostile review (BLOCKER, "scanner .forge/venvs"): assurance traversals of a
checkout read environment trees as if they were repository source. The local
assurance runner creates ``.forge/venvs/3.11`` and ``.forge/venvs/3.12`` INSIDE
the checkout, so a whole-tree walk parsed thousands of site-packages files as
first-party code (the impact graph reported joblib's test files as unparseable
repository modules), and a seed populated by copying whole trees could carry an
environment into mutation evidence.

The rule is ownership, not a list of names to ignore:

* **A tracked file is always the repository's**, wherever it lives -- under
  ``.forge``, under ``build``, in a directory that happens to be called
  ``venv``. A tracked scientific file cannot be hidden by its path.
* **An untracked file is the repository's unless it lies under an
  environment or artifact root**: an explicit external root
  (:data:`EXTERNAL_ROOTS`), a directory that IS an environment (it holds
  ``pyvenv.cfg`` or ``conda-meta``), or a cache/artifact directory
  (:data:`ARTIFACT_DIR_NAMES`; ``build``/``dist`` only when nothing under them
  is tracked). Untracked first-party source -- a module someone just created --
  is therefore still seen.
* **A symlink is never followed.** It is reported as refused, so a caller fails
  safe instead of reading what the link points at, inside or outside the tree.
* **Fail closed, not open** (third review C1-C6): a checkout whose ``git ls-files``
  fails raises instead of silently treating every file as untracked; inherited
  ``GIT_*`` variables are scrubbed so the listing describes THIS checkout; an
  environment marker inside a directory that holds tracked source, and any nested
  repository, are refused rather than pruned or walked; and a path that differs
  from a tracked one only by case (a case-insensitive filesystem) is the tracked file.
* **The inventory must be this checkout's** (2026-10-16): a Git top level other than
  the root, a ``.git`` file whose Git directory does not name this checkout back, or
  a listed name that escapes the root raises; a tracked file replaced by a directory
  is refused, never read as deleted.

Outside a Git checkout (a synthetic tree in a test) nothing is tracked, so only
the second and third rules apply.
"""

from __future__ import annotations

import os
import pathlib
import stat
import subprocess
from dataclasses import dataclass

#: Roots that hold the local toolchain, never repository source, whatever they contain.
EXTERNAL_ROOTS: tuple[str, ...] = (".forge/venvs", ".forge/tmp", ".forge/cache")

#: Directory names that hold caches or build artifacts. ``build`` and ``dist`` are artifacts only
#: when nothing under them is tracked (some repositories track a ``build`` directory of source).
ARTIFACT_DIR_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", "node_modules",
    ".eggs", "build", "dist",
})
_ARTIFACT_ONLY_WHEN_UNTRACKED = frozenset({"build", "dist"})

#: Directory names that are installed-package trees whatever else they hold (PEP 582, a bare site-packages).
ENVIRONMENT_DIR_NAMES = frozenset({"__pypackages__", "site-packages"})


class OwnershipError(RuntimeError):
    """The repository's ownership of its files could not be established; nothing is guessed."""


@dataclass(frozen=True)
class OwnedTree:
    """The repository-owned files of a checkout, and the paths refused rather than read."""

    root: pathlib.Path
    files: tuple[str, ...]          # repository-relative POSIX paths, sorted
    refused: tuple[str, ...]        # symlinks and other entries never followed
    excluded_roots: tuple[str, ...]  # environment/artifact directories pruned (untracked content only)


def is_environment_dir(path: pathlib.Path) -> bool:
    """A directory that IS a Python environment or installed-package tree.

    A virtualenv (``pyvenv.cfg``), a conda environment (``conda-meta``), a PEP 582 or bare
    ``site-packages`` tree, or a ``pip install --target`` directory (it holds ``*.dist-info``).
    """
    if path.name in ENVIRONMENT_DIR_NAMES:
        return True
    if (path / "pyvenv.cfg").is_file() or (path / "conda-meta").is_dir() or (path / "site-packages").is_dir():
        return True
    try:
        return any(child.suffix == ".dist-info" and child.is_dir() for child in path.iterdir())
    except OSError:
        return False


def _git_environment() -> dict[str, str]:
    """The process environment without inherited GIT_* variables, so git describes the checkout it is pointed at."""
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


def _git(root: pathlib.Path, *args: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(root), *args],
                              check=True, capture_output=True, env=_git_environment()).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        raise OwnershipError(
            f"{root} is a Git checkout and its tracked files could not be listed "
            f"({detail.decode('utf-8', 'replace').strip() or exc}); treating every file as untracked would "
            f"hide tracked files under artifact or environment names, so nothing is guessed"
        ) from exc


def _inventory_name(name: str) -> str:
    """A tracked name as Git must report it: relative, POSIX, inside the root. Anything else is refused."""
    parts = name.split("/")
    if (name.startswith("/") or "\\" in name or ":" in parts[0]
            or any(part in ("", ".", "..") for part in parts)):
        raise OwnershipError(f"tracked-file inventory names a path outside the repository root: {name!r}")
    return name


def is_link(path: pathlib.Path | str) -> bool:
    """A symlink or a Windows junction (a directory link that ``is_symlink`` does not report). Never followed."""
    path = pathlib.Path(path)
    if path.is_symlink():
        return True
    junction = getattr(os.path, "isjunction", None)  # Python 3.12+
    if junction is not None:
        return junction(path)
    try:
        tag = getattr(os.lstat(path), "st_reparse_tag", 0)  # Python 3.11 on Windows
    except OSError:
        return False
    return bool(tag) and tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1)


def _same_path(left: str, right: pathlib.Path, *, base: pathlib.Path | None = None) -> bool:
    """Whether ``left`` names ``right``; a relative ``left`` is read against ``base``, never the CWD."""
    if not left:
        return False
    named = pathlib.Path(left)
    if not named.is_absolute():
        if base is None:
            return False
        named = base / named
    try:
        return named.resolve() == right.resolve()
    except OSError:
        return False


def _require_worktree_link(root: pathlib.Path) -> None:
    """A ``.git`` FILE must name a Git directory that names this checkout back.

    Git reports the directory holding a ``.git`` file as the top level whatever the file points at, so a
    ``gitdir:`` line naming another repository's Git directory would silently substitute that repository's
    index for this checkout's. A linked worktree's Git directory records its checkout in ``gitdir``; a
    separated or submodule Git directory records it as ``core.worktree``. Without either back-reference the
    link is refused.
    """
    git_dir = _git(root, "rev-parse", "--absolute-git-dir").decode("utf-8", "surrogateescape").strip()
    common = _git(root, "rev-parse", "--git-common-dir").decode("utf-8", "surrogateescape").strip()
    if not _same_path(common, pathlib.Path(git_dir), base=pathlib.Path(git_dir)):
        back = pathlib.Path(git_dir) / "gitdir"
        try:
            named = back.read_text(encoding="utf-8").strip()
        except OSError:
            named = ""
        # worktree.useRelativePaths writes this back-reference relative to the worktree's Git directory.
        if _same_path(named, root / ".git", base=pathlib.Path(git_dir)):
            return
    else:
        try:
            worktree = subprocess.run(["git", "-C", str(root), "config", "--get", "core.worktree"],
                                      capture_output=True, env=_git_environment()).stdout
        except OSError:
            worktree = b""
        named = worktree.decode("utf-8", "surrogateescape").strip()
        if _same_path(named, root, base=pathlib.Path(git_dir)):
            return
    raise OwnershipError(
        f"{root}/.git points at {git_dir!r}, which does not name this checkout back; another repository's "
        f"inventory is never this checkout's ownership"
    )


def tracked_files(root: pathlib.Path) -> frozenset[str] | None:
    """The files Git tracks under ``root``; ``None`` when ``root`` is not the top of a Git checkout.

    The checkout's Git metadata must describe ``root`` itself: a ``.git`` file (a worktree) that makes
    Git report another top-level directory is refused, and so is any listed name that is not a plain
    relative path inside the root.
    """
    if is_link(root / ".git"):
        # A linked .git (symlink or junction) is another repository's Git directory: Git would report this
        # root as its top level and list the foreign index.
        raise OwnershipError(f"{root}/.git is a link; another repository's inventory is never this checkout's ownership")
    if not (root / ".git").exists():
        return None
    top = _git(root, "rev-parse", "--show-toplevel").decode("utf-8", "surrogateescape").strip()
    try:
        same = bool(top) and pathlib.Path(top).resolve() == pathlib.Path(root).resolve()
    except OSError:
        same = False
    if not same:
        raise OwnershipError(
            f"{root}'s Git metadata describes another repository (top level {top!r}); its inventory is not "
            f"this checkout's ownership"
        )
    if (root / ".git").is_file():
        _require_worktree_link(pathlib.Path(root))
    else:
        git_dir = _git(root, "rev-parse", "--absolute-git-dir").decode("utf-8", "surrogateescape").strip()
        if not _same_path(git_dir, root / ".git"):
            raise OwnershipError(
                f"{root}/.git resolves to {git_dir!r}; another repository's inventory is never this checkout's ownership"
            )
    out = _git(root, "ls-files", "-z", "--cached")
    return frozenset(_inventory_name(name) for name in out.decode("utf-8", "surrogateescape").split("\0") if name)


def owned_files(root: pathlib.Path) -> OwnedTree:
    """Every repository-owned file under ``root`` (see the module docstring for the rule)."""
    root = pathlib.Path(root).resolve()
    tracked = tracked_files(root)
    tracked_dirs: set[str] = set()
    if tracked:
        for name in tracked:
            parts = name.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                tracked_dirs.add("/".join(parts[:i]))
    files: set[str] = set(name for name in (tracked or ()) if (root / name).is_file() and not is_link(root / name))
    tracked_by_fold = {name.casefold(): name for name in files}
    refused: set[str] = set()
    excluded: set[str] = set()
    # A tracked FILE that is now something else (a directory) is refused, never read as absent: dropping it
    # would make a tracked module silently vanish from every traversal.
    for name in tracked or ():
        path = root / name
        if not is_link(path) and path.exists() and not path.is_file():
            refused.add(name)
    refused_by_fold = {name.casefold() for name in refused}

    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        here = pathlib.Path(directory)
        rel_dir = here.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        keep = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            path = here / name
            if is_link(path):
                refused.add(rel)
                continue
            if rel == ".git":
                continue
            if rel.casefold() in refused_by_fold:
                continue  # a tracked file replaced by a directory: refused above, its contents never walked
            if name == ".git" or (path / ".git").exists():
                # A nested repository or submodule: another repository's files, never walked as ours.
                refused.add(rel)
                continue
            environment = (rel in EXTERNAL_ROOTS or is_environment_dir(path)
                           or (name in ARTIFACT_DIR_NAMES
                               and not (name in _ARTIFACT_ONLY_WHEN_UNTRACKED and rel in tracked_dirs)))
            if environment and rel in tracked_dirs and rel not in EXTERNAL_ROOTS and name not in ARTIFACT_DIR_NAMES:
                # An environment marker inside tracked source (a stray pyvenv.cfg in src/): pruning would hide
                # untracked modules below it, walking would read an environment. Refused: the caller fails safe.
                refused.add(rel)
                keep.append(name)
                continue
            if environment:
                # Not walked. Any tracked file inside is already in ``files`` from the tracked set.
                excluded.add(rel)
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir else name
            path = here / name
            if path.is_symlink():
                refused.add(rel)
                continue
            twin = tracked_by_fold.get(rel.casefold())
            if twin is not None and twin != rel:
                try:
                    if path.samefile(root / twin):
                        continue  # the tracked file, reached under another case on a case-insensitive filesystem
                except OSError:
                    pass
            files.add(rel)
    order = lambda text: text.encode("utf-8")  # noqa: E731 - the certificate's canonical order
    return OwnedTree(root, tuple(sorted(files, key=order)), tuple(sorted(refused, key=order)),
                     tuple(sorted(excluded, key=order)))


def copy_ignore(root: pathlib.Path, *patterns: str):
    """An ``ignore`` for :func:`shutil.copytree` that leaves out environment roots holding nothing tracked.

    ``patterns`` are the caller's own name patterns (caches), applied as before. A pruned environment
    root that holds tracked files is still copied: ownership, not the name, decides.
    """
    import fnmatch

    root = pathlib.Path(root).resolve()
    owned = owned_files(root)
    holding = {"/".join(name.split("/")[:i]) for name in owned.files for i in range(1, name.count("/") + 1)}
    pruned = {rel for rel in owned.excluded_roots if rel not in holding}

    def ignore(directory: str, names: list[str]) -> set[str]:
        here = pathlib.Path(directory).resolve()
        try:
            rel_dir = here.relative_to(root).as_posix()
        except ValueError:
            rel_dir = None
        out = {name for name in names if any(fnmatch.fnmatch(name, p) for p in patterns)}
        if rel_dir is not None:
            prefix = "" if rel_dir == "." else rel_dir + "/"
            out.update(name for name in names if prefix + name in pruned)
        return out

    return ignore


def owned_entry(root: pathlib.Path, relative: str, owned: OwnedTree | None = None) -> bool:
    """Whether ``relative`` (a file or a directory) holds repository-owned content."""
    owned = owned or owned_files(root)
    prefix = relative.rstrip("/") + "/"
    return relative in owned.files or any(name.startswith(prefix) for name in owned.files)


__all__ = [
    "ARTIFACT_DIR_NAMES",
    "ENVIRONMENT_DIR_NAMES",
    "EXTERNAL_ROOTS",
    "OwnedTree",
    "OwnershipError",
    "copy_ignore",
    "is_environment_dir",
    "is_link",
    "owned_entry",
    "owned_files",
    "tracked_files",
]
