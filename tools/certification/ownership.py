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

Outside a Git checkout (a synthetic tree in a test) nothing is tracked, so only
the second and third rules apply.
"""

from __future__ import annotations

import os
import pathlib
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


def tracked_files(root: pathlib.Path) -> frozenset[str] | None:
    """The files Git tracks under ``root``; ``None`` when ``root`` is not the top of a Git checkout."""
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached"],
                             check=True, capture_output=True, env=_git_environment()).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        raise OwnershipError(
            f"{root} is a Git checkout and its tracked files could not be listed "
            f"({detail.decode('utf-8', 'replace').strip() or exc}); treating every file as untracked would "
            f"hide tracked files under artifact or environment names, so nothing is guessed"
        ) from exc
    return frozenset(name for name in out.decode("utf-8", "surrogateescape").split("\0") if name)


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
    files: set[str] = set(name for name in (tracked or ()) if (root / name).is_file() and not (root / name).is_symlink())
    tracked_by_fold = {name.casefold(): name for name in files}
    refused: set[str] = set()
    excluded: set[str] = set()

    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        here = pathlib.Path(directory)
        rel_dir = here.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        keep = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            path = here / name
            if path.is_symlink():
                refused.add(rel)
                continue
            if rel == ".git":
                continue
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
    "owned_entry",
    "owned_files",
    "tracked_files",
]
