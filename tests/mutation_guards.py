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

On writing a mutation
---------------------
The first attempt at `G2b` inserted a comment and left the `evidence=` argument
in place. The suite stayed green, which looked exactly like an unchecked guard
and was not: nothing had been removed. **A green result is a claim about your
mutation before it is a claim about the check**, and the first thing to do with
one is to confirm the mutation removed what it says it removed.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

#: ``(id, file, old, new, what the mutation removes)``. Each entry deletes one
#: guard from a copy of the tree; the suite is expected to fail.
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
        text = path.read_bytes().decode("utf-8")
        if text.count(old) != 1:
            # The mutation did not apply. That is a fact about this file, not
            # about the guard, and it is reported as loudly as a green result
            # because it is the same mistake wearing a different hat.
            print(f"{mid:5} MUTATION DID NOT APPLY (count={text.count(old)}) -- {what}")
            unchecked.append(mid)
            continue
        path.write_bytes(text.replace(old, new).encode("utf-8"))

        code, tail, failed = _run(work, scratch)
        verdict = "RED" if code else "GREEN -- DECORATION"
        print(f"{mid:5} {verdict:20} {what}")
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
              "about the mutation first.")
    return 1 if unchecked else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
