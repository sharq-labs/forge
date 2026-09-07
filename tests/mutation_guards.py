"""Make every guard's check fail once, on purpose, and watch it fail.

**A check whose failure has never been observed is unverified.** That is not a
slogan; it is a rule this repository has now paid for three times.

* The hard benchmark reported a 100 % catch rate that no case could have
  lowered, because `electrical.dc.kcl` declared no validity conditions and
  nothing could ever reach SUPPORTED.
* `pytest.importorskip("mcp")` never skipped, because `tests/mcp/` is itself an
  importable PEP 420 namespace package named `mcp`. The guard imported the
  directory it lived in.
* GUARD 3's commit asserted a layering invariant -- the scientific core owns no
  domain-specific rule -- in the same commit that created a core file
  containing the string `CSTR`. A test encoding that invariant was already in
  the repository and would have said so, and was not run.

Each was a check that looked like a check. The only way to tell is to break the
thing it guards and watch it go red.

What this does
--------------
For each entry in :data:`MUTATIONS`, copy `src`, `tests` and `pyproject.toml`
into a throwaway directory, remove one guard from the copy **as if it had never
been written**, and run `tests/test_core_guards.py` against it. The suite must
go red. A mutation that leaves it green names a check that is decoration.

Nothing is written to the repository. Run it as::

    python -X utf8 tests/mutation_guards.py <scratch-dir>

It takes about a minute. It is deliberately **not** a pytest module -- it
copies trees and shells out, which is a tool's job rather than a test's, and it
sits beside `zero_provider.py` and `sria_m4_benchmark.py`, which are support
modules in this directory for the same reason.

On writing a mutation, and why this file verifies its own mutations
-------------------------------------------------------------------
The first attempt at `G2b` **inserted a comment without removing anything**,
and left the `evidence=` argument in place. The suite stayed green. A green
result in this harness means "that guard is decoration", and this one was
indistinguishable from that: **it was one keystroke from being reported as a
real gap in the guards, and the gap did not exist.** Nothing had been removed.
**A green result is a claim about your mutation before it is a claim about your
check.**

That is the same failure one level up. A check that cannot fail is the thing
this harness exists to find; a *mutation* that changes nothing is a verifier
that cannot fail, and it fails in the more dangerous direction, because its
output is a clean bill of health for a guard nobody tested.

So every mutation is now verified before its result is believed, and the
verification is **not** a file hash. A file hash would have passed the bad
`G2b`: the file did change -- a comment was added. What has to be compared is
the code, so :func:`_code_digest` tokenizes the file and hashes the token
stream with `COMMENT` and `STRING` tokens dropped. A mutation whose only effect
is a comment, a docstring or reformatting produces an identical digest and is
refused as `CHANGED NO CODE` before the suite is ever run.

Dropping `STRING` is deliberate and costs nothing here: no guard in this
repository is implemented by the contents of a string literal, and every
mutation below changes name or operator tokens. A future mutation that acted
only inside a string would be refused, which is the safe direction to be wrong
in.
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import shutil
import subprocess
import sys
import tokenize

#: ``(id, file, old, new, what the mutation removes)``. Each entry deletes one
#: guard from a copy of the tree; the suite is expected to fail.
#: Line-ending forms, named rather than written inline so the normalisation
#: below reads as a decision instead of as an escape sequence.
CRLF = chr(13) + chr(10)
LF = chr(10)

MUTATIONS: tuple[tuple[str, str, str, str, str], ...] = (
    ("G1a", "src/engcore/scientific/ir/problem.py",
     "        forged = sorted(reserved & set(context))",
     "        forged = []",
     "validity_context stops refusing a parameter that occupies a reserved name"),
    ("G1b", "src/engcore/scientific/models/definition.py",
     "        forged = sorted(set(declared) & self.derived_quantities)",
     "        forged = []",
     "assess stops refusing a reserved name in the caller's half"),
    ("G1c", "src/engcore/scientific/models/definition.py",
     "        unregistered = sorted(set(assembled) - self.derived_quantities)",
     "        unregistered = []",
     "assess stops refusing an assembled name the model does not reserve"),
    ("G1d", "src/engcore/domains/electrical/dc/models.py",
     "        derived_quantities=frozenset(\n"
     "            {DISSIPATED_POWER_UTILIZATION, WORKING_VOLTAGE_UTILIZATION}\n"
     "        ),",
     "",
     "a domain forgets to reserve its derived quantities (the import lock)"),
    ("G2a", "src/engcore/scientific/results/validation.py",
     "        if self.establishes is None:\n            return True",
     "        return True\n        if self.establishes is None:\n            return True",
     "earns_its_level stops distinguishing anything"),
    ("G2b", "src/engcore/domains/electrical/dc/validation.py",
     "        evidence=tuple(\n"
     "            f\"{prefix}={unit}\" for prefix, unit in sorted(expected.items())\n"
     "        ),\n",
     "",
     "a PASS goes back to claiming a level with no evidence (static audit)"),
    ("G2c", "src/engcore/domains/kinetics/cstr/validation.py",
     "        evidence=tuple(\n"
     "            f\"{CSTR_MODEL.model_id}@{CSTR_MODEL.version}:{metric}={exemplar}\"\n"
     "            for metric, exemplar in sorted(declared.items())\n"
     "        ),\n",
     "",
     "the repaired CSTR check loses its evidence (runtime half)"),
    ("G2d", "src/engcore/scientific/results/validation.py",
     "        if not self.earns_its_level:",
     "        if False:",
     "the constructor stops refusing a claimed level (GUARD 2 back to opt-in)"),
    ("G3a", "src/engcore/scientific/results/thresholds.py",
     "        if not self.is_declared:\n            return None",
     "        pass",
     "award stops withholding a level from a caller-supplied threshold"),
    ("G3b", "src/engcore/domains/kinetics/cstr/validation.py",
     "    thresholds: VerificationThresholds = CSTR_GATE_THRESHOLDS,\n"
     "    cross_method: str = \"Radau\",",
     "    thresholds: VerificationThresholds = CSTR_GATE_THRESHOLDS,\n"
     "    invariant_rel_tol: float = INVARIANT_REL_TOL,\n"
     "    cross_method: str = \"Radau\",",
     "a gate takes a bare float threshold again (parameter sweep)"),
    ("G4a", "src/engcore/scientific/solvers/registry.py",
     "        self._require_core_support_decision(solver)",
     "        pass",
     "the registry stops refusing a solver that decides its own support"),
    ("G4b", "src/engcore/scientific/solvers/protocol.py",
     "        missing = sorted(requested - declared)",
     "        missing = []",
     "support_gap stops checking that capabilities cover the request"),
    ("G5a", "src/engcore/scientific/results/provenance.py",
     "                if label == \"solvers\":",
     "                if False:",
     "provenance stops refusing a solver no binding covers"),
    ("G6a", "src/engcore/scientific/ir/fingerprints.py",
     "    if not declared:",
     "    if False:",
     "the fingerprint check goes back to passing on absence"),
    ("G6b", "src/engcore/domains/kinetics/cstr/problem.py",
     "    require_matching_fingerprint(\n        problem=problem,\n"
     "        key=\"physics_fingerprint\",",
     "    if not problem.metadata.get(\"physics_fingerprint\"):\n        return\n"
     "    require_matching_fingerprint(\n        problem=problem,\n"
     "        key=\"physics_fingerprint\",",
     "a domain reintroduces the permissive compare (source sweep)"),
    ("G7a", "src/engcore/scientific/solvers/protocol.py",
     "        if not self.succeeded:\n            return",
     "        return\n        if not self.succeeded:\n            return",
     "RawSolverOutput stops refusing a non-finite value on a succeeded solve"),
    ("G7b", "src/engcore/domains/electrical/ngspice.py",
     "        require_finite(\n            values,\n"
     "            error=NgspiceExecutionFailure,\n"
     "            source=\"the ngspice provider\",\n        )",
     "",
     "the provider adapter stops admitting its parsed values"),
)

TARGET = "tests/test_core_guards.py"
_COPIED = ("src", "tests", "pyproject.toml")


def _code_digest(text: str) -> str:
    """A hash of the file's executable tokens, ignoring comments and strings.

    The point of comparison, not decoration. A plain file hash cannot tell a
    mutation that removed a guard from one that added a comment beside it, and
    the second is exactly the mistake this guards against: it changes the file,
    leaves the code alone, and reports the guard as unchecked.
    """
    kept: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in (
                tokenize.COMMENT,
                tokenize.STRING,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
            ):
                continue
            kept.append(token.string)
    except tokenize.TokenError:  # pragma: no cover - a mutation broke the parse
        return "unparseable:" + hashlib.sha256(text.encode()).hexdigest()[:16]
    blob = "\x00".join(kept).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _self_test() -> None:
    """Make the verifier fail once, on purpose, before trusting it.

    The rule this harness enforces applies to the harness. `_code_digest` is a
    check, and a check whose failure has never been observed is unverified --
    so it is exercised here against the two cases it has to tell apart, on a
    synthetic pair rather than on a real source file, so it cannot rot when
    that file is edited.

    If this fails, nothing below is worth running: every mutation would be
    accepted and every green result would be a false clean bill of health.
    """
    base = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    commented = "def f(x):\n    # a comment, and nothing else\n    if x:\n        return 1\n    return 0\n"
    changed = "def f(x):\n    if False:\n        return 1\n    return 0\n"

    if _code_digest(base) != _code_digest(commented):
        raise SystemExit(
            "_code_digest reports a comment as a code change; it would accept "
            "a mutation that mutates nothing"
        )
    if _code_digest(base) == _code_digest(changed):
        raise SystemExit(
            "_code_digest is blind to a real code change; it would refuse "
            "every mutation"
        )
    # And the reason it is not a file hash, stated as an assertion rather than
    # a claim: a file hash cannot tell these two apart.
    if hashlib.sha256(base.encode()).digest() == hashlib.sha256(
        commented.encode()
    ).digest():  # pragma: no cover - would mean sha256 collided
        raise SystemExit("file hashes collided; this test is meaningless")


def _run(where: pathlib.Path, scratch: pathlib.Path) -> tuple[int, str, list[str]]:
    done = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", TARGET, "-q",
         "-p", "no:randomly", "--basetemp", str(scratch / "pt" / "bt")],
        cwd=where, capture_output=True, text=True, timeout=900,
    )
    lines = [l for l in done.stdout.splitlines() if l.strip()]
    failed = [l.split("::")[-1].split()[0]
              for l in done.stdout.splitlines() if l.startswith("FAILED")]
    return done.returncode, (lines[-1] if lines else "?"), failed


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: python -X utf8 tests/mutation_guards.py <scratch-dir>")
        return 2
    _self_test()
    repo = pathlib.Path(__file__).resolve().parent.parent
    scratch = pathlib.Path(argv[0]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)

    unchecked: list[str] = []
    for mid, relative, old, new, what in MUTATIONS:
        work = scratch / f"mut_{mid}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        for item in _COPIED:
            source, target = repo / item, work / item
            if source.is_dir():
                shutil.copytree(
                    source, target, ignore=shutil.ignore_patterns("__pycache__")
                )
            else:
                shutil.copy2(source, target)

        path = work / relative
        # Newlines are normalised before the search, and this is not
        # fastidiousness. The read stays binary -- a text read would hide
        # a file whose bytes differ -- but a multi-line search string is
        # written with a bare line feed while a working tree on Windows
        # may hold a carriage return before it, and four mutations below
        # had silently stopped applying for exactly that reason: G1d,
        # G2a, G2c and G3b, every one a multi-line target in a CRLF file.
        # They were reported as NOT APPLIED rather than green, which is
        # this harness being honest, and they were still four guards
        # nobody was verifying. A mutation that cannot apply is a verifier
        # that reports nothing -- the failure this file exists to catch
        # one level down, in its own machinery.
        text = path.read_bytes().decode("utf-8").replace(CRLF, LF)
        if text.count(old) != 1:
            # The mutation did not apply. That is a fact about this file, not
            # about the guard, and it is reported as loudly as a green result
            # because it is the same mistake wearing a different hat.
            print(f"{mid:5} MUTATION DID NOT APPLY (count={text.count(old)}) -- {what}")
            unchecked.append(mid)
            continue

        mutated = text.replace(old, new)
        before, after = _code_digest(text), _code_digest(mutated)
        if before == after:
            # The file changed and the code did not: a comment, a docstring or
            # whitespace. Running the suite now would produce a green result
            # that says nothing about the guard, which is how the bad G2b
            # mutation nearly reported a real gap that did not exist.
            print(f"{mid:5} MUTATION CHANGED NO CODE ({before}) -- {what}")
            unchecked.append(mid)
            continue
        path.write_bytes(mutated.encode("utf-8"))

        code, tail, failed = _run(work, scratch)
        verdict = "RED" if code else "GREEN -- DECORATION"
        print(f"{mid:5} {verdict:20} {what}")
        print(f"{'':26} code {before} -> {after}")
        print(f"{'':26} {tail}")
        if failed:
            shown = sorted(set(failed))
            print(f"{'':26} {', '.join(shown[:3])}"
                  + (f" (+{len(shown) - 3} more)" if len(shown) > 3 else ""))
        if not code:
            unchecked.append(mid)

    print()
    print(f"{len(MUTATIONS) - len(unchecked)}/{len(MUTATIONS)} mutations turned "
          f"the suite red.")
    if unchecked:
        print("NOT OBSERVED FAILING:", ", ".join(unchecked))
        print("Check the mutation before the guard: a green result is a claim "
              "about the mutation first. Every mutation above was verified to "
              "change executable tokens, so a GREEN here is a real finding.")
    return 1 if unchecked else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
