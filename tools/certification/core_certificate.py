"""Build and verify a Core certificate: what was certified, and is it still that.

The question this answers, in one command, is the one V1 could not be asked:

    is the checked-out tree exactly the tree that was certified?

V1 could be *computed* — its algorithm is written out inside the certificate
itself and reproduces its stored digest exactly at the commit it names — but
nothing executed it. There was no script, no test, and no command. So the
certificate went two sprints out of date without anything noticing, which is a
gap in the infrastructure rather than in the algorithm.

What V2 adds
------------
* **an executable algorithm**, here, rather than a snippet quoted in prose;
* **a per-file manifest**, so a failure names the file that moved instead of
  reporting that two hex strings differ;
* **named scope areas**, so what is certified is a table a reader can argue
  with rather than one path;
* **a verifier that reads the stored certificate** and compares the tree to
  it — never regenerating the expected values from the same tree it is
  checking, which would make verification a tautology.

The digest algorithm, stated exactly
------------------------------------
Per file::

    file_digest = sha256(exact bytes on disk)

Per area, over its files sorted by UTF-8 path bytes::

    area_digest = sha256( for each: path_utf8 + b"\\x00" + file_digest_bytes )

Over the whole certificate, areas sorted by name::

    aggregate = sha256( for each: area_name_utf8 + b"\\x00" + area_digest_bytes )

and the rules that make that deterministic:

=========================  ====================================================
root                       the repository root
included                   each area's explicit glob patterns, files only
excluded                   any path with a ``__pycache__`` component; ``*.pyc``
path normalization         repository-relative, POSIX separators, no ``./``
ordering                   sorted by the UTF-8 encoded path bytes
byte handling              exact bytes; nothing is decoded
line endings               **not normalized** — CRLF and LF are different files
symlinks                   refused: a symlink in scope fails the build
generated files            none in scope beyond the exclusions above
hash                       SHA-256 throughout
=========================  ====================================================

Line endings are deliberately not normalized. This repository pins several
trees by SHA-256 over raw bytes already, and a certificate that silently
normalized would disagree with them and would also hide a real change to what
ships.

The per-area construction is V1's, with repository-relative paths in place of
area-relative ones. That means **V2's core area digest is not comparable to
V1's stored value by construction**, so the certificate also records
``v1_compatible_core_digest``, computed exactly V1's way, which makes the
continuity between them checkable rather than asserted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: Bumped when the algorithm or the certificate's shape changes. A verifier
#: refuses a certificate whose schema it does not implement rather than
#: comparing fields that may not mean what it thinks.
CERTIFICATE_SCHEMA = "core_certificate/2"

#: Identity of the code that produced a certificate, recorded in it. Not a
#: version of the repository: a version of *this algorithm*.
TOOL_ID = "tools/certification/core_certificate.py"
TOOL_VERSION = "2.0.0"

EXCLUDED_DIR_PARTS = frozenset({"__pycache__"})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo"})


@dataclass(frozen=True)
class ScopeArea:
    """One named part of what is certified, and the argument for including it."""

    name: str
    classification: str
    patterns: tuple[str, ...]
    why: str


#: What V2 certifies, and why each part is in.
#:
#: The criterion is deliberately narrow: an area is in when a silent edit to it
#: would change **what a verdict means**, rather than change an answer. A domain
#: solver produces answers and is assured by its own tests; the registry the
#: core reads to decide whether a threshold set is *declared* decides whether a
#: level may be awarded at all, and that is a different kind of thing.
SCOPE: tuple[ScopeArea, ...] = (
    ScopeArea(
        name="core",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/scientific/**/*.py",),
        why=(
            "the Scientific Core's contracts: the records, their invariants and "
            "their refusals. This is what V1 certified and it remains the "
            "centre of the certificate"
        ),
    ),
    ScopeArea(
        name="trust_registry",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/domains/__init__.py",),
        why=(
            "the domain-layer declarations the core verifies against and cannot "
            "see past: SCIENTIFIC_THRESHOLD_DECLARATIONS decides whether a "
            "threshold set is declared, and SCIENTIFIC_ROUTE_DECLARATIONS "
            "decides whether two routes are independent. An edit here turns a "
            "gate that awards nothing into one that awards a level, without "
            "touching a line of the core. One file, and the strongest case for "
            "inclusion outside scientific/"
        ),
    ),
    ScopeArea(
        name="runtime_data",
        classification="RUNTIME_SUPPORT",
        patterns=("src/engcore/data/**/*.py",),
        why=(
            "the plane a ScientificDataReference resolves through. The core "
            "names bulk data by digest and count and never reads it; the "
            "length-then-digest verification that makes that reference worth "
            "anything is here, as is the field container's shape, support and "
            "finiteness enforcement"
        ),
    ),
    ScopeArea(
        name="evidence_identity",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/adequacy/**/*.py",),
        why=(
            "predictive evidence identity and pairing. Two models may only "
            "receive a comparative conclusion if they were assessed against the "
            "same canonical evidence, and this is where that is decided"
        ),
    ),
    ScopeArea(
        name="inference_admission",
        classification="CORE_CERTIFIED",
        patterns=("src/engcore/inference/**/*.py",),
        why=(
            "the admission invariant for forward rows: a posterior may only be "
            "built from predictions that were admitted. A trust boundary in its "
            "own right, and one the certified mutation harness exercises"
        ),
    ),
    ScopeArea(
        name="harness",
        classification="HARNESS",
        patterns=(
            "tests/mutation_guards.py",
            "tests/test_core_guards.py",
            "tests/test_repair_guidance.py",
            "tests/test_offset_unit_declaration.py",
            "tests/test_core_semantic_invariants.py",
        ),
        why=(
            "the mutation harness and the four suites it runs each mutant "
            "against. '79/79 killed' is a statement about these exact bytes: "
            "the same sentence over a weakened suite would be worth nothing, "
            "so the suites are pinned alongside the runner"
        ),
    ),
)

#: Named here rather than left implicit, because a reader's first question about
#: any certificate is what it does *not* cover.
OUT_OF_SCOPE: tuple[tuple[str, str], ...] = (
    ("src/engcore/domains/** (except __init__.py)",
     "scientific models and solvers. They produce answers rather than decide "
     "what a verdict means, and they carry their own assurance — three of them "
     "are byte-pinned by frozen experiments"),
    ("src/engcore/mcp/**", "the product boundary: a consumer of the core"),
    ("src/engcore/design/**, sria/**, systems/**", "applications built on the core"),
    ("src/engcore/uq/**", "representation only; it computes nothing a verdict rests on"),
    ("tests/** (except the harness area)",
     "assurance for everything above, not part of what is certified"),
    ("benchmarks/**, experiments/**, certification/**",
     "measurements, frozen artefacts, and the certificate itself — a "
     "certificate whose scope contained its own bytes would need a fixed point"),
)


class CertificationError(RuntimeError):
    """A certificate could not be built or does not describe this tree."""


# ---------------------------------------------------------------------------
# enumeration and hashing
# ---------------------------------------------------------------------------
def repo_root(start: pathlib.Path | None = None) -> pathlib.Path:
    """The repository root, found by walking up to the directory holding .git."""
    here = (start or pathlib.Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    raise CertificationError(
        f"no repository root above {here}: expected a directory holding both "
        f".git and pyproject.toml"
    )


def _excluded(path: pathlib.Path) -> bool:
    return bool(EXCLUDED_DIR_PARTS.intersection(path.parts)) or (
        path.suffix in EXCLUDED_SUFFIXES
    )


def enumerate_area(root: pathlib.Path, area: ScopeArea) -> list[str]:
    """Repository-relative POSIX paths for one area, in canonical order.

    Refuses a symlink rather than following it: what a symlink points at is not
    recorded by a digest of the link, and following one could reach outside the
    tree entirely.
    """
    found: set[str] = set()
    for pattern in area.patterns:
        for path in root.glob(pattern):
            if not path.is_file() or _excluded(path.relative_to(root)):
                continue
            if path.is_symlink():
                raise CertificationError(
                    f"{path.relative_to(root).as_posix()} is a symlink and is in "
                    f"certified scope. A digest of a link does not record what it "
                    f"points at, so this is refused rather than resolved"
                )
            found.add(path.relative_to(root).as_posix())
    return sorted(found, key=lambda text: text.encode("utf-8"))


def file_digest(path: pathlib.Path) -> str:
    """SHA-256 over the file's exact bytes. Nothing is decoded or normalized."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def area_digest(entries: Mapping[str, str]) -> str:
    """SHA-256 over ``path + NUL + file digest`` for each entry, in path order."""
    accumulator = hashlib.sha256()
    for relative in sorted(entries, key=lambda text: text.encode("utf-8")):
        accumulator.update(relative.encode("utf-8"))
        accumulator.update(b"\x00")
        accumulator.update(bytes.fromhex(entries[relative]))
    return accumulator.hexdigest()


def aggregate_digest(areas: Mapping[str, str]) -> str:
    """SHA-256 over ``area name + NUL + area digest``, areas in name order."""
    accumulator = hashlib.sha256()
    for name in sorted(areas, key=lambda text: text.encode("utf-8")):
        accumulator.update(name.encode("utf-8"))
        accumulator.update(b"\x00")
        accumulator.update(bytes.fromhex(areas[name]))
    return accumulator.hexdigest()


def build_manifest(
    root: pathlib.Path, scope: Sequence[ScopeArea] | None = None
) -> dict[str, Any]:
    """The full manifest for ``scope`` as it stands in the tree at ``root``.

    ``scope`` resolves to the module's :data:`SCOPE` at call time rather than
    through a default argument, so the table can be substituted — which is what
    the drift tests do to build a synthetic repository rather than experimenting
    on the checkout.
    """
    areas: dict[str, Any] = {}
    for area in SCOPE if scope is None else scope:
        relatives = enumerate_area(root, area)
        if not relatives:
            raise CertificationError(
                f"scope area {area.name!r} matched no files under {root}; an "
                f"area that certifies nothing is a silent hole in the scope"
            )
        files = {rel: file_digest(root / rel) for rel in relatives}
        areas[area.name] = {
            "classification": area.classification,
            "patterns": list(area.patterns),
            "why": area.why,
            "file_count": len(files),
            "digest": area_digest(files),
            "files": files,
        }
    return {
        "areas": areas,
        "file_count": sum(a["file_count"] for a in areas.values()),
        "aggregate_digest": aggregate_digest(
            {name: a["digest"] for name, a in areas.items()}
        ),
    }


def v1_compatible_core_digest(root: pathlib.Path) -> str:
    """The V1 algorithm, reproduced exactly, over ``src/engcore/scientific``.

    Paths relative to *that root* rather than to the repository, which is the
    one difference from :func:`area_digest`. Recorded so continuity with V1 is
    a number a reader can check rather than a claim in prose.
    """
    base = root / "src" / "engcore" / "scientific"
    accumulator = hashlib.sha256()
    for path in sorted(
        p for p in base.rglob("*.py") if "__pycache__" not in p.parts
    ):
        accumulator.update(path.relative_to(base).as_posix().encode())
        accumulator.update(b"\x00")
        accumulator.update(hashlib.sha256(path.read_bytes()).digest())
    return accumulator.hexdigest()


# ---------------------------------------------------------------------------
# repository identity
# ---------------------------------------------------------------------------
def _git(root: pathlib.Path, *args: str, strip: bool = True) -> str:
    """Run git and return its stdout.

    ``strip`` is a parameter rather than always-on because ``status
    --porcelain`` encodes the index and worktree states in the **first two
    columns**, and one of them is very often a space. Stripping the output
    silently removes that space from the first line only, and every path parsed
    from it then loses its first character — which is how this function spent
    its first draft reporting an uncommitted file as ``ools/...``.
    """
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise CertificationError(f"git {' '.join(args)} failed: {exc}") from exc
    if done.returncode != 0:
        raise CertificationError(
            f"git {' '.join(args)} failed: {done.stderr.strip()}"
        )
    return done.stdout.strip() if strip else done.stdout


def _porcelain_paths(output: str) -> list[str]:
    """The paths in ``git status --porcelain`` output, columns intact.

    A rename is reported as ``R  old -> new``; the new name is the one that
    exists in the tree, so that is the one recorded.
    """
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else line.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip().strip('"'))
    return sorted(paths)


def repository_identity(root: pathlib.Path) -> dict[str, Any]:
    """The commit a certificate is about, and whether the tree was clean."""
    dirty = _git(root, "status", "--porcelain", strip=False)
    return {
        "commit": _git(root, "rev-parse", "HEAD"),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "clean": not dirty.strip(),
        "dirty_paths": _porcelain_paths(dirty),
    }


def environment() -> dict[str, Any]:
    """Facts about where this ran. Metadata: no comparison depends on them."""
    packages: dict[str, str] = {}
    for name in ("numpy", "scipy", "pint", "pytest"):
        try:
            module = __import__(name)
        except Exception:  # pragma: no cover - a missing package is a fact too
            packages[name] = "absent"
        else:
            packages[name] = getattr(module, "__version__", "unknown")
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
    }


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def build_certificate(
    root: pathlib.Path,
    *,
    allow_dirty: bool = False,
    assurance: Mapping[str, Any] | None = None,
    certification_id: str = "FORGE-CORE-V2",
    notes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a certificate for the tree at ``root``.

    Refuses a dirty tree unless ``allow_dirty``: a certificate names a commit,
    and one built from uncommitted edits describes a tree nobody else can check
    out. The escape hatch exists for diagnosis and marks what it produces.
    """
    identity = repository_identity(root)
    if not identity["clean"] and not allow_dirty:
        raise CertificationError(
            "refusing to certify a dirty tree: "
            f"{len(identity['dirty_paths'])} uncommitted path(s), first "
            f"{identity['dirty_paths'][:3]}. A certificate names a commit, and "
            f"one built from uncommitted edits describes a tree nobody can "
            f"check out. Commit first, or pass --allow-dirty for a diagnostic "
            f"certificate that says so in its own diagnostic field"
        )
    manifest = build_manifest(root)
    return {
        "schema": CERTIFICATE_SCHEMA,
        "certification_id": certification_id,
        "diagnostic": not identity["clean"],
        "generator": {"tool": TOOL_ID, "version": TOOL_VERSION},
        "repository": identity,
        "environment": environment(),
        "scope": {
            "in": [
                {
                    "area": area.name,
                    "classification": area.classification,
                    "patterns": list(area.patterns),
                    "why": area.why,
                }
                for area in SCOPE
            ],
            "out": [{"area": name, "why": why} for name, why in OUT_OF_SCOPE],
        },
        "digest_algorithm": {
            "hash": "sha256",
            "per_file": "sha256(exact file bytes)",
            "per_area": "sha256( path_utf8 + 0x00 + file_digest_bytes, in path order )",
            "aggregate": "sha256( area_name_utf8 + 0x00 + area_digest_bytes, in name order )",
            "path_form": "repository-relative, POSIX separators",
            "ordering": "sorted by UTF-8 encoded path bytes",
            "line_endings": "not normalized; exact bytes are hashed",
            "excluded": ["**/__pycache__/**", "*.pyc", "*.pyo"],
            "symlinks": "refused in scope",
            "implemented_by": TOOL_ID,
        },
        "manifest": manifest,
        "v1_continuity": {
            "v1_certificate": "certification/current_core_v1.json",
            "v1_algorithm_recovered": True,
            "v1_algorithm_source": (
                "certification/current_core_v1.json -> "
                "verification.how_to_reproduce_the_certified_tree"
            ),
            "v1_core_digest_at_its_own_commit": (
                "82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507"
            ),
            "v1_compatible_core_digest_now": v1_compatible_core_digest(root),
            "note": (
                "V2 area digests use repository-relative paths where V1 used "
                "paths relative to src/engcore/scientific, so the two are not "
                "comparable by construction. The field above recomputes the core "
                "tree the V1 way against this tree, so the continuity between "
                "the two certificates is a number rather than a claim"
            ),
        },
        "assurance": dict(assurance or {}),
        "notes": dict(notes or {}),
    }


# ---------------------------------------------------------------------------
# verify  --  reads the stored certificate; never rebuilds expectations
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AreaDrift:
    """What moved in one area, by path."""

    area: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    modified: tuple[str, ...]
    expected_digest: str
    actual_digest: str

    @property
    def clean(self) -> bool:
        return not (self.added or self.removed or self.modified) and (
            self.expected_digest == self.actual_digest
        )


@dataclass(frozen=True)
class VerificationResult:
    """Whether the tree is the certified tree, and if not, precisely how not."""

    ok: bool
    areas: tuple[AreaDrift, ...]
    expected_aggregate: str
    actual_aggregate: str
    commit_expected: str
    commit_actual: str
    commit_matches: bool
    clean_tree: bool
    problems: tuple[str, ...]

    def render(self) -> str:
        lines: list[str] = []
        for drift in self.areas:
            if drift.clean:
                continue
            lines.append(f"AREA {drift.area}")
            for label, paths in (
                ("ADDED", drift.added),
                ("REMOVED", drift.removed),
                ("MODIFIED", drift.modified),
            ):
                for path in paths:
                    lines.append(f"  {label}: {path}")
            if drift.expected_digest != drift.actual_digest:
                lines.append(f"  expected area digest: {drift.expected_digest}")
                lines.append(f"  actual area digest:   {drift.actual_digest}")
        for problem in self.problems:
            lines.append(f"PROBLEM: {problem}")
        if self.expected_aggregate != self.actual_aggregate:
            lines.append(f"expected aggregate: {self.expected_aggregate}")
            lines.append(f"actual aggregate:   {self.actual_aggregate}")
        if not lines:
            lines.append("certificate matches the tree")
        return "\n".join(lines)


def verify_certificate(
    root: pathlib.Path,
    certificate: Mapping[str, Any],
    *,
    require_clean: bool = True,
    require_commit: bool = True,
) -> VerificationResult:
    """Compare the tree at ``root`` against a **stored** certificate.

    Every expected value is read from ``certificate``. Nothing here calls
    :func:`build_certificate`, and no expectation is recomputed from the tree
    being checked — a verifier that regenerated its own expectations would
    compare the tree to itself and pass for any tree at all.

    Files are enumerated from the certificate's recorded patterns rather than
    from :data:`SCOPE`, so a certificate written under an older scope is checked
    against the scope it was written under.
    """
    problems: list[str] = []
    schema = str(certificate.get("schema", ""))
    if schema != CERTIFICATE_SCHEMA:
        problems.append(
            f"certificate schema is {schema!r} and this verifier implements "
            f"{CERTIFICATE_SCHEMA!r}; refusing to compare fields that may not "
            f"mean the same thing"
        )
        return VerificationResult(
            ok=False, areas=(), expected_aggregate="", actual_aggregate="",
            commit_expected="", commit_actual="", commit_matches=False,
            clean_tree=False, problems=tuple(problems),
        )

    manifest = certificate.get("manifest") or {}
    stored_areas: Mapping[str, Any] = manifest.get("areas") or {}
    if not stored_areas:
        problems.append("certificate carries no manifest areas")

    drifts: list[AreaDrift] = []
    actual_area_digests: dict[str, str] = {}
    for name, stored in sorted(stored_areas.items()):
        area = ScopeArea(
            name=name,
            classification=stored.get("classification", ""),
            patterns=tuple(stored.get("patterns") or ()),
            why="",
        )
        stored_files: Mapping[str, str] = stored.get("files") or {}
        try:
            present = enumerate_area(root, area)
        except CertificationError as exc:
            problems.append(str(exc))
            present = []
        actual_files = {rel: file_digest(root / rel) for rel in present}

        added = tuple(sorted(set(actual_files) - set(stored_files)))
        removed = tuple(sorted(set(stored_files) - set(actual_files)))
        modified = tuple(
            sorted(
                rel
                for rel in set(stored_files) & set(actual_files)
                if stored_files[rel] != actual_files[rel]
            )
        )
        actual = area_digest(actual_files)
        actual_area_digests[name] = actual
        drifts.append(
            AreaDrift(
                area=name,
                added=added,
                removed=removed,
                modified=modified,
                expected_digest=str(stored.get("digest", "")),
                actual_digest=actual,
            )
        )
        stored_count = stored.get("file_count")
        if stored_count is not None and stored_count != len(stored_files):
            problems.append(
                f"area {name!r} records file_count {stored_count} and lists "
                f"{len(stored_files)} files; the certificate disagrees with itself"
            )

    expected_aggregate = str(manifest.get("aggregate_digest", ""))
    actual_aggregate = aggregate_digest(actual_area_digests)

    repository = certificate.get("repository") or {}
    commit_expected = str(repository.get("commit", ""))
    try:
        identity = repository_identity(root)
        commit_actual = identity["commit"]
        clean_tree = bool(identity["clean"])
    except CertificationError as exc:  # pragma: no cover - no git available
        problems.append(str(exc))
        commit_actual, clean_tree = "", False

    commit_matches = bool(commit_expected) and commit_expected == commit_actual
    if require_commit and not commit_matches:
        problems.append(
            f"certificate names commit {commit_expected or '<none>'} and HEAD is "
            f"{commit_actual or '<unknown>'}"
        )
    if require_clean and not clean_tree:
        problems.append(
            "the working tree has uncommitted changes, so what is being verified "
            "is not any commit"
        )
    if certificate.get("diagnostic"):
        problems.append(
            "this certificate was built with --allow-dirty and is marked "
            "diagnostic; it does not certify a commit"
        )

    ok = (
        not problems
        and all(drift.clean for drift in drifts)
        and expected_aggregate == actual_aggregate
    )
    return VerificationResult(
        ok=ok,
        areas=tuple(drifts),
        expected_aggregate=expected_aggregate,
        actual_aggregate=actual_aggregate,
        commit_expected=commit_expected,
        commit_actual=commit_actual,
        commit_matches=commit_matches,
        clean_tree=clean_tree,
        problems=tuple(problems),
    )


def load_certificate(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_certificate(path: pathlib.Path, certificate: Mapping[str, Any]) -> None:
    """Write deterministically: sorted keys, two-space indent, LF, trailing LF."""
    payload = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode("utf-8"))


# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build, verify or list the Core certificate.",
    )
    parser.add_argument("--build", action="store_true", help="write a certificate")
    parser.add_argument("--verify", action="store_true", help="check the tree against one")
    parser.add_argument("--manifest", action="store_true", help="print the manifest")
    parser.add_argument(
        "--certificate",
        default="certification/current_core_v2.json",
        help="path to the certificate (default: %(default)s)",
    )
    parser.add_argument("--assurance", help="JSON file of assurance results to embed")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--require-commit",
        action="store_true",
        help=(
            "also require HEAD to be the commit the certificate names. Off by "
            "default because a certificate is committed as a child of the "
            "commit whose tree it certifies, so HEAD is normally that child; "
            "the content comparison is unaffected, since the certificate file "
            "is outside certified scope"
        ),
    )
    args = parser.parse_args(argv)

    root = repo_root(pathlib.Path.cwd() / "x")
    certificate_path = root / args.certificate

    if args.manifest:
        print(json.dumps(build_manifest(root), indent=2, sort_keys=True))
        return 0

    if args.build:
        assurance = (
            json.loads((root / args.assurance).read_text(encoding="utf-8"))
            if args.assurance
            else None
        )
        certificate = build_certificate(
            root, allow_dirty=args.allow_dirty, assurance=assurance
        )
        write_certificate(certificate_path, certificate)
        print(f"wrote {args.certificate}")
        print(f"  files      {certificate['manifest']['file_count']}")
        print(f"  aggregate  {certificate['manifest']['aggregate_digest']}")
        print(f"  commit     {certificate['repository']['commit']}")
        return 0

    if args.verify:
        if not certificate_path.exists():
            print(f"no certificate at {args.certificate}", file=sys.stderr)
            return 2
        result = verify_certificate(
            root,
            load_certificate(certificate_path),
            require_clean=not args.allow_dirty,
            require_commit=args.require_commit,
        )
        print(result.render())
        if not args.require_commit:
            relation = (
                "HEAD is the certified commit"
                if result.commit_matches
                else f"certified commit {result.commit_expected[:12]}, "
                     f"HEAD {result.commit_actual[:12]}"
            )
            print(f"commit: {relation}")
        print("OK" if result.ok else "FAILED")
        return 0 if result.ok else 1

    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
