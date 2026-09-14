"""Fail if a gate left the repository checkout different from the commit it measured.

    python -m tools.certification.assert_clean_tree [--gate NAME --record FILE]

WHY EVERY GATE RUNS THIS
------------------------
The serial pipeline measured and certified in ONE checkout, so a test that
wrote into the repository was caught when the certify step found the tree
dirty. In the parallel pipeline every gate has its own checkout and certify
starts from a fresh one: a gate that rewrites a pinned file, deletes a test or
drops a module into ``src/`` can report success, and certify will never see
it. So each gate proves its own checkout is still the commit, at the end, in
that job. Temporary output belongs in ``$RUNNER_TEMP``.

The check never cleans first. ``git checkout -- .`` or ``git clean`` before it
would destroy exactly the evidence it exists to report.

WHAT "CLEAN" MEANS, EXACTLY
---------------------------
1. ``git status --porcelain=v1 -z --untracked-files=all`` is empty: no
   modified, staged, deleted, renamed or untracked path. Ignored paths
   (``__pycache__``, ``*.egg-info``, pytest's self-ignoring cache) are not
   reported, as Git defines them.
2. Every tracked regular file's exact bytes hash to the blob the index records
   (``git hash-object`` semantics, computed here without any filter). This is
   the half ``git status`` cannot do: with ``* text=auto eol=lf`` a CRLF
   rewrite of a pinned file normalizes back to the same blob and ``status``
   stays silent, while every SHA-256 byte pin in this repository breaks. A
   symlink is compared by its target; a submodule entry is not a file and is
   skipped.

With ``--record`` a small JSON record of the clean result, the gate's name and
the commit it measured is written for the certify job to consume. It is only
written when the tree is clean.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence

GATE_RECORD_SCHEMA = "forge.certification_gate/1"


class TreeCheckError(RuntimeError):
    """The checkout could not be inspected, which is not the same as clean."""


def _git(root: pathlib.Path, *args: str) -> bytes:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if done.returncode != 0:
        raise TreeCheckError(
            f"git {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace').strip()}"
        )
    return done.stdout


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


@dataclass(frozen=True)
class Dirty:
    """One way the checkout differs from its commit."""

    status: str
    path: str

    def render(self) -> str:
        return f"{self.status:>9}  {self.path}"


def status_entries(root: pathlib.Path) -> list[Dirty]:
    """Paths ``git status`` reports, with a readable status, renames split."""
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.split(b"\0")
    entries: list[Dirty] = []
    index = 0
    while index < len(fields):
        item = fields[index]
        index += 1
        if not item:
            continue
        code, path = _decode(item[:2]), _decode(item[3:])
        if code == "??":
            label = "UNTRACKED"
        elif "D" in code:
            label = "DELETED"
        elif "R" in code or "C" in code:
            label = "RENAMED"
            # -z puts the rename SOURCE in the following field.
            if index < len(fields):
                entries.append(Dirty("RENAMED", _decode(fields[index])))
                index += 1
        elif "A" in code:
            label = "ADDED"
        elif "U" in code:
            label = "UNMERGED"
        else:
            label = "MODIFIED"
        entries.append(Dirty(label, path))
    return entries


def _object_hasher(root: pathlib.Path):
    algorithm = _decode(_git(root, "rev-parse", "--show-object-format")).strip() or "sha1"
    if algorithm not in ("sha1", "sha256"):
        raise TreeCheckError(f"unsupported git object format {algorithm!r}")
    return lambda: hashlib.new(algorithm)


def byte_mismatches(root: pathlib.Path) -> list[Dirty]:
    """Tracked files whose exact on-disk bytes are not the blob the index holds."""
    new_hash = _object_hasher(root)
    mismatches: list[Dirty] = []
    for record in _git(root, "ls-files", "-s", "-z").split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        mode, blob, _stage = meta.split(b" ")
        path = _decode(raw_path)
        target = root / path
        if mode == b"160000":  # a submodule entry is a commit, not a file
            continue
        if mode == b"120000":
            if not target.is_symlink():
                mismatches.append(Dirty("NOT-A-LINK", path))
                continue
            content = os.fsencode(os.readlink(target))
        else:
            if target.is_symlink() or not target.is_file():
                # A deletion is reported by status; anything else here is a
                # tracked file replaced by something that is not a file.
                if target.exists() or target.is_symlink():
                    mismatches.append(Dirty("REPLACED", path))
                continue
            content = target.read_bytes()
        digest = new_hash()
        digest.update(b"blob %d\0" % len(content))
        digest.update(content)
        if digest.hexdigest().encode("ascii") != blob:
            mismatches.append(Dirty("BYTES", path))
    return mismatches


def tree_problems(root: pathlib.Path) -> list[Dirty]:
    """Every difference between the checkout and its commit. Empty means clean."""
    found = {(d.status, d.path): d for d in status_entries(root)}
    reported = {d.path for d in found.values()}
    for mismatch in byte_mismatches(root):
        if mismatch.path not in reported:
            found[(mismatch.status, mismatch.path)] = mismatch
    return sorted(found.values(), key=lambda d: (d.path.encode("utf-8", "surrogateescape"), d.status))


def gate_record(root: pathlib.Path, gate: str) -> dict[str, object]:
    return {
        "schema": GATE_RECORD_SCHEMA,
        "gate": gate,
        "head_commit": _decode(_git(root, "rev-parse", "HEAD")).strip(),
        "head_tree": _decode(_git(root, "rev-parse", "HEAD^{tree}")).strip(),
        "clean_tree_after_gate": True,
        "tracked_files_byte_verified": sum(
            1 for record in _git(root, "ls-files", "-z").split(b"\0") if record
        ),
    }


def _root(start: pathlib.Path) -> pathlib.Path:
    top = _decode(_git(start, "rev-parse", "--show-toplevel")).strip()
    return pathlib.Path(top)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--gate", help="the gate name recorded with --record")
    parser.add_argument("--record", help="write a clean-tree gate record here")
    args = parser.parse_args(argv)
    if bool(args.gate) != bool(args.record):
        parser.error("--gate and --record go together")

    try:
        root = _root(pathlib.Path(args.root).resolve())
        problems = tree_problems(root)
    except TreeCheckError as exc:
        print(f"CANNOT INSPECT THE CHECKOUT: {exc}", file=sys.stderr)
        return 2

    if problems:
        print(f"DIRTY: the checkout at {root} is not the commit it measured.")
        print("A gate must not modify, add or delete repository files; write "
              "temporary output under $RUNNER_TEMP.")
        for problem in problems:
            print(problem.render())
        return 1

    print(f"clean: {root} is byte-identical to HEAD")
    if args.record:
        record = gate_record(root, args.gate)
        target = pathlib.Path(args.record)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        print(f"wrote gate record {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
