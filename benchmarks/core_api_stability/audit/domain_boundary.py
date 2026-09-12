"""Part V: prove the Domain boundary was never crossed.

The standing instruction for this round is that ``src/engcore/domains/**`` is
READ-ONLY: inspectable, runnable, usable as regression evidence, and not
editable -- no model improvements, no equation changes, no compatibility shims.

A claim that the boundary held is worth nothing on its own, so this proves it
three ways, each of which fails differently:

1. CONTENT. A digest over the domain tree, recomputed from the working tree and
   from the sprint's base commit independently. The base-commit side is read
   out of git rather than from a number recorded earlier by hand -- a digest I
   wrote down at the start of the round is a claim about the past, and this is
   the thing it would be a claim about.

2. DIFF. ``git diff <base> -- src/engcore/domains`` must be empty. This catches
   what a digest over tracked files would miss on its own: a file that git
   knows about but that never reached the hashing walk.

3. BEHAVIOUR. The domain regression suites still pass. Content equality already
   implies the domain sources did not change, but the CORE underneath them did,
   and a Core change that breaks a domain is exactly the outcome this round's
   boundary exists to make visible.

    python -X utf8 benchmarks/core_api_stability/audit/domain_boundary.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
BASE = "973083e"
DOMAINS = "src/engcore/domains"

#: Suites that exercise the domains through the Core. Chosen because each one
#: runs a real domain model end to end rather than testing a domain in
#: isolation, which is what makes them evidence about the CORE.
REGRESSION_SUITES = (
    "tests/test_electrical_v01_demo.py",
    "tests/test_kinetics_k1.py",
    "tests/test_conduction2d.py",
    "tests/test_conduction2d_assembly.py",
    "tests/test_conduction2d_convergence.py",
    "tests/test_thermal_t1_fidelity_inference.py",
    "tests/test_thermal_t2_repeated_draw_calibration.py",
    "tests/test_thermal_t3_decision_aware_fidelity.py",
    "tests/test_min_foundation_electrothermal.py",
    "tests/test_electrothermal_vertical.py",
    "tests/test_sria_e1_electrical.py",
)


def tree_digest(entries: list[tuple[str, bytes]]) -> str:
    """Digest over (path, content) pairs, path-sorted.

    The path goes into the hash as well as the content: two files swapping
    names is a change, and a digest over contents alone would not see it.
    """
    hasher = hashlib.sha256()
    for path, blob in sorted(entries):
        hasher.update(path.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(hashlib.sha256(blob).digest())
    return hasher.hexdigest()


def working_tree() -> list[tuple[str, bytes]]:
    root = ROOT / DOMAINS
    return [
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]


def at_commit(commit: str) -> list[tuple[str, bytes]]:
    """The same tree as git holds it at `commit`, read blob by blob."""
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", DOMAINS],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    entries = []
    for path in listing:
        blob = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout
        entries.append((path[len(DOMAINS) + 1:], blob))
    return entries


def main() -> int:
    print("=" * 72)
    print("PART V -- DOMAIN BOUNDARY")
    print("=" * 72)

    now = working_tree()
    then = at_commit(BASE)
    end_digest = tree_digest(now)
    start_digest = tree_digest(then)

    print(f"  base commit            : {BASE}")
    print(f"  files (working tree)   : {len(now)}")
    print(f"  files (at base)        : {len(then)}")
    print(f"  DOMAIN_START_DIGEST    : {start_digest}")
    print(f"  DOMAIN_END_DIGEST      : {end_digest}")
    identical = start_digest == end_digest
    print(f"  CONTENT                : {'IDENTICAL' if identical else 'CHANGED'}")

    diff = subprocess.run(
        ["git", "diff", BASE, "--", DOMAINS],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    print(f"  git diff {BASE} -- {DOMAINS}: "
          f"{'EMPTY' if not diff.strip() else 'NON-EMPTY'}")

    print()
    print("REGRESSION SUITES (the domains, run through the changed Core)")
    results = []
    all_green = True
    for suite in REGRESSION_SUITES:
        proc = subprocess.run(
            [PYTHON, "-X", "utf8", "-m", "pytest", suite, "-q",
             "-p", "no:cacheprovider", "--basetemp", "D:/fbt_dom"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        summary = lines[-1] if lines else "(no output)"
        # Strip pytest's elapsed time. A proof artefact that changes on
        # every run cannot be compared with the last one, and the wall clock
        # is the only part of this line that is not a fact about the tree.
        # Past one minute pytest also appends "(0:01:09)", so both forms go.
        summary = re.sub(r" in [0-9.]+s( [(][0-9:]+[)])?$", "", summary.strip())
        green = proc.returncode == 0
        all_green &= green
        print(f"  {'PASS' if green else 'FAIL'}  {suite}")
        print(f"        {summary}")
        results.append({"suite": suite, "passed": green, "summary": summary})

    verdict = identical and not diff.strip() and all_green
    print()
    print(f"DOMAIN BOUNDARY: {'INTACT' if verdict else 'VIOLATED'}")

    out = ROOT / "benchmarks" / "core_api_stability" / "DOMAIN_BOUNDARY.json"
    out.write_bytes(json.dumps({
        "base_commit": BASE,
        "domain_start_digest": start_digest,
        "domain_end_digest": end_digest,
        "digests_identical": identical,
        "git_diff_empty": not diff.strip(),
        "file_count": len(now),
        "suites": results,
        "all_suites_green": all_green,
        "boundary_intact": verdict,
    }, indent=2).encode("utf-8"))
    print(f"wrote {out}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
