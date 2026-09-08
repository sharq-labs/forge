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
been written**, and run every suite in :data:`TARGETS` against it. They must go
red. A mutation that leaves them green names a check that is decoration.

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
    ("G1e", "src/engcore/domains/derived_context.py",
     "        read_and_unreserved = sorted(\n"
     "            (set(self.assembled) & set(model.validity.context_keys)) - reserved\n"
     "        )",
     "        read_and_unreserved = []",
     "assess goes back to silently dropping a derived quantity a model reads "
     "and does not reserve (the sixth-domain door)"),
    ("G1f", "src/engcore/domains/derived_context.py",
     "            (set(self.assembled) & set(model.validity.context_keys)) - reserved\n",
     "            set(self.assembled) - reserved\n",
     "the same refusal stops distinguishing another model's business from "
     "this model's forgery"),
    ("G8a", "src/engcore/domains/electrical/dc_applicability.py",
     "SOURCE_REGULATION_UTILIZATION = \"source_regulation_utilization\"",
     "import _an_optional_dependency_that_is_not_installed\n"
     "SOURCE_REGULATION_UTILIZATION = \"source_regulation_utilization\"",
     "a domain module stops importing and the model sweep silently shrinks "
     "(the floor that could not see it)"),
    ("G8b", "src/engcore/domains/electrical/dc/validation.py",
     "            check_power_balance(prepared, solution, settings),\n",
     "",
     "a domain quietly stops emitting one validation check (the live-solve "
     "count that was a floor)"),
    # Repointed. The old target text -- `return exponent if
    # _no_derating_line(context) else None` -- has not existed since the
    # offset refactor, so this entry reported MUTATION DID NOT APPLY and the
    # guard behind it was verified by nobody. That is the harness being
    # honest and it is still an unverified guard, which is the whole point of
    # the file. The claim is unchanged: with a derating line declared the
    # utilization is affine in 1/P_rated, and forcing the offset to zero
    # inverts it against the PRINTED rating instead.
    ("G8c", "src/engcore/domains/electrical/dc/models.py",
     "    if _no_derating_line(context):",
     "    if True:",
     "the power utilization inverts against the PRINTED rating when a "
     "derating line is declared -- a hint that leaves the design refused"),
    ("G1d", "src/engcore/domains/electrical/dc/models.py",
     "        derived_quantities=frozenset(\n"
     "            {DISSIPATED_POWER_UTILIZATION, WORKING_VOLTAGE_UTILIZATION}\n"
     "        ),",
     "",
     "a domain forgets to reserve its derived quantities (the import lock)"),
    ("G2a", "src/engcore/scientific/results/validation.py",
     "    if establishes is None:\n        return True",
     "    return True\n    if establishes is None:\n        return True",
     "level_is_earned stops distinguishing anything"),
    ("G2e", "src/engcore/scientific/results/validation.py",
     "            if not isinstance(check, ValidationCheck):",
     "            if False:",
     "a report takes back anything with a `passed` and an `establishes`"),
    ("G2f", "src/engcore/scientific/results/validation.py",
     "        self._require_every_level_earned()\n        names = [c.name for c in self.checks]",
     "        names = [c.name for c in self.checks]",
     "a report stops re-applying the rule to what it was handed"),
    ("G2g", "src/engcore/scientific/results/validation.py",
     "        self._require_every_level_earned()\n        return frozenset(",
     "        return frozenset(",
     "attained_levels trusts a check that may have been altered since"),
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
    ("G9a", "src/engcore/scientific/results/result.py",
     "        silent = sorted(declared - set(checked) - set(declined))",
     "        silent = []",
     "a result may again declare a model and say nothing about it"),
    ("G9b", "src/engcore/scientific/results/result.py",
     "    parts = module.split(\".\")",
     "    return \"exempt\"\n    parts = module.split(\".\")",
     "the package exemption becomes universal (every caller excused)"),
    ("G9c", "src/engcore/domains/kinetics/cstr/solver.py",
     "        validity={CSTR_MODEL.model_id: assessment},",
     "",
     "the CSTR goes back to computing its assessment and discarding it"),
    ("G12a", "src/engcore/domains/electrical/dc/models.py",
     "    if not isinstance(ambient, QuantityTransfer):",
     "    if False:",
     "a crossed quantity may arrive undeclared again (bare Quantity)"),
    ("G12b", "src/engcore/scientific/composition/transfer.py",
     "        if expected != actual:",
     "        if False:",
     "a transfer stops checking that both sides mean the same thing"),
    ("G12c", "src/engcore/scientific/composition/transfer.py",
     "        if existing == transfer:\n            continue",
     "        if True:\n            continue",
     "two contradicting values for one crossing are resolved by order"),
    ("G12d", "src/engcore/domains/electrical/dc/models.py",
     "    ambient = context.get(AMBIENT_TEMPERATURE)",
     "    ambient = None",
     "the offset stops being formable, and repair loses the inversion again"),
    ("G11a", "src/engcore/scientific/results/provenance.py",
     "        if parent is None:\n            if claimed:",
     "        if parent is None:\n            if False:",
     "provenance takes back a lineage name with no record behind it"),
    ("G11b", "src/engcore/scientific/results/provenance.py",
     "        if claimed and claimed != named:",
     "        if False:",
     "a typed parent name silently outranks the record that exists"),
    ("G11c", "src/engcore/scientific/results/provenance.py",
     "        if named == run_id:",
     "        if False:",
     "a provenance record may name itself as its own source"),
    ("G10a", "src/engcore/scientific/results/result.py",
     "        unrecordable = unwritable(self.metadata, path=\"metadata\")",
     "        unrecordable = None",
     "a result may again hold a value it could never record"),
    ("G10b", "src/engcore/scientific/serialization.py",
     "    return (path, type(value).__name__)",
     "    return None",
     "the writability rule stops refusing anything it does not recognise"),
    ("G10c", "src/engcore/scientific/serialization.py",
     "        if isinstance(value, float) and value != value:\n"
     "            return (path, \"float('nan')\")",
     "",
     "a NaN travels into a record and out as a token no reader accepts"),
    ("G8a", "src/engcore/scientific/units/quantity.py",
     "        self.__dict__[\"_crafty_sealed\"] = True",
     "        pass",
     "the unit registry is never sealed (every refusal becomes a no-op)"),
    ("G8b", "src/engcore/scientific/units/quantity.py",
     "    units, prefixes = reg._units, reg._prefixes",
     "    return True\n    units, prefixes = reg._units, reg._prefixes",
     "a name appearing after the seal is taken on trust as pint's own prefixing"),
    ("G7b", "src/engcore/domains/electrical/ngspice.py",
     "        require_finite(\n            values,\n"
     "            error=NgspiceExecutionFailure,\n"
     "            source=\"the ngspice provider\",\n        )",
     "",
     "the provider adapter stops admitting its parsed values"),
    ("G13a", "src/engcore/scientific/models/definition.py",
     "        if self.varies_with is None:",
     "        if False:",
     "an input declared as a constant stops refusing a declared curve -- the "
     "fail-closed edge of the curve mechanism"),
    ("G13b", "src/engcore/scientific/models/curves.py",
     "        if x < self.lower or x > self.upper:",
     "        if False:",
     "a curve extrapolates past the interval it was declared over instead of "
     "answering OUTSIDE_VALIDATED_DOMAIN"),
    ("G13c", "src/engcore/scientific/models/curves.py",
     "            if lower < first or upper > last:",
     "            if False:",
     "a declared interval may reach past the samples, claiming evidence that "
     "was never measured"),
    ("G13d", "src/engcore/domains/battery/cell.py",
     "            else self.open_circuit_voltage_curve.fingerprint,",
     "            else \"\",",
     "a declared curve stops entering the cell's physical identity, so two "
     "cells with different OCV curves are cached as one"),
    ("G14a", "src/engcore/domains/electrical/dc/models.py",
     "    exclusions=_DC_EXCLUSIONS,",
     "    exclusions=None,",
     "a shipped model stops declaring what it does not represent, and the "
     "tree sweep is what notices"),
    ("G14b", "src/engcore/mcp/evidence.py",
     # Repointed: the line this named changed when the property learned to
     # tell NOT_DECLARED from None, and the harness said so rather than going
     # green. The claim is unchanged.
     "        return model.exclusions",
     "        return None",
     "the credibility report stops carrying exclusions beside validity, so a "
     "reader sees only the checkable half"),
    ("G14c", "src/engcore/scientific/models/definition.py",
     "            if any(not e for e in exclusions):",
     "            if False:",
     "a blank exclusion is admitted -- a statement-shaped thing that states "
     "nothing"),
    ("G14d", "src/engcore/scientific/models/definition.py",
     "        if self.exclusions is NOT_DECLARED:",
     "        if False:",
     "exclusions go back to being optional, so omitting them is accepted at "
     "construction instead of refused"),
    ("G14e", "src/engcore/scientific/models/definition.py",
     "            if not exclusions and not because:",
     "            if False:",
     "an empty exclusion list stops having to justify itself -- the strongest "
     "claim the field can carry, made for free"),
    ("G15a", "src/engcore/scientific/composition/dependency.py",
     "        if carries_energy and self.conversion is None:",
     "        if False:",
     "a crossing may carry energy again without saying how much of it "
     "arrives -- the fail-closed edge of the conversion record"),
    ("G15b", "src/engcore/scientific/composition/conversion.py",
     "        if abs(total - 1.0) > CONSERVATION_TOLERANCE:",
     "        if False:",
     "conservation stops being checked, so a conversion that loses energy to "
     "nowhere constructs"),
    ("G15c", "src/engcore/scientific/composition/conversion.py",
     "        if self.efficiency is None:\n            return ConversionOutcome(\n"
     "                ValidityStatus.UNKNOWN,",
     "        if self.efficiency is None:\n            return ConversionOutcome(\n"
     "                ValidityStatus.IN_DOMAIN,",
     "an undeclared efficiency stops reporting UNKNOWN"),
    ("G16a", "src/engcore/scientific/composition/transfer.py",
     "        if abs(arrived - budgeted) > BUDGET_TOLERANCE * scale:",
     "        if False:",
     "a transfer may carry more than its conversion budgets -- declared 0.5 "
     "while transporting all of it"),
    ("G16b", "src/engcore/scientific/composition/transfer.py",
     "        if self.source_value is None:",
     "        if False:",
     "a conversion transfer stops having to say what entered it, so the "
     "declared ratio has nothing to be checked against"),
    ("G16c", "src/engcore/systems/electrothermal/coupled.py",
     "    if dependency.conversion is None:\n        return value",
     "    return value\n    if dependency.conversion is None:\n        return value",
     "the coupling loop stops spending the budget at the transport boundary, "
     "so a declared efficiency decorates a crossing that ignores it"),
    # GUARD 17 inverts the usual shape. Every mutation above REMOVES a check
    # and expects the suite to notice; a static guard over the source text
    # cannot be verified that way, because deleting its check makes the suite
    # greener rather than redder. So these two INTRODUCE the leak the guard
    # exists to catch -- the same direction as G8a, which adds an import to
    # break a module -- and the guard is what must go red.
    ("G17a", "src/engcore/scientific/results/result.py",
     "from __future__ import annotations",
     "from __future__ import annotations\n\n\n"
     "def _special_case(domain: str) -> bool:\n"
     "    return domain == \"battery\"\n",
     "the core branches on a domain by name and GUARD 17's derived reach is "
     "what notices -- the leak a sixth domain arrives through"),
    ("G17b", "src/engcore/scientific/ir/conditions.py",
     "from __future__ import annotations",
     "from __future__ import annotations\n\n\n"
     "def thrust_margin(a: float, b: float) -> float:\n"
     "    return a - b\n",
     "the core learns the name of a thing -- a relation between two "
     "quantities is stated as a fact about thrust"),
    # Planted in `trust.py` on purpose. That module owns the import scanner
    # this repository has used for layering since M1, and it discards every
    # relative import -- so this is the one leak it structurally cannot see,
    # sitting in the file that cannot see it. GUARD 18 resolves relative
    # imports and is what goes red.
    ("G18a", "src/engcore/sria/trust.py",
     "from __future__ import annotations",
     "from __future__ import annotations\n\n"
     "from ..domains import kinetics as _kinetics\n",
     "SRIA reaches into a domain through a relative import -- the syntax it "
     "uses for all 50 of its real imports, and the one the existing scanner "
     "is blind to"),
    # Both of these name a package that IS INSTALLED here and is NOT declared
    # in pyproject.toml -- `joblib` and `threadpoolctl` arrive under
    # scikit-learn. That is deliberate: the import succeeds, nothing else in
    # the suite breaks, and the ONLY thing that goes red is GUARD 19. A
    # mutation naming a package that does not exist would also go red, on
    # ImportError, from every test that touches the module -- red for a
    # reason that says nothing about the guard.
    ("G19a", "src/engcore/mcp/evidence.py",
     "from __future__ import annotations",
     "from __future__ import annotations\n\nimport joblib\n",
     "a module acquires an undeclared dependency by import statement, and a "
     "clean install stops working -- the `mcp` half of 8107745"),
    ("G19b", "src/engcore/scientific/units/quantity.py",
     "from __future__ import annotations",
     "from __future__ import annotations\n\n\n"
     "def _lazy_backend():\n"
     "    import importlib\n\n"
     "    return importlib.import_module(\"threadpoolctl\")\n",
     "the same, reached as a STRING rather than a statement -- the `anyio` "
     "half, which a scan of ast.Import alone would miss"),
)

# WHAT THESE TWO CANNOT VERIFY, stated rather than left to be assumed.
#
# GUARD 17 has two reaches: derived domain names in CODE, and curated
# thing-terms in ALL TEXT, prose included. The prose reach is the one that
# matters most -- the `CSTR` GUARD 3 leaked was in a class docstring, and a
# code-only rule would have let it through -- and it is the one this harness
# structurally CANNOT exercise. `_code_digest` drops COMMENT and STRING
# tokens, by a deliberate decision recorded in this module's docstring, so a
# mutation that writes a forbidden term into a docstring changes no code and
# is refused as CHANGED NO CODE before the suite ever runs.
#
# That is the right call for the verifier and it leaves a real gap here. The
# prose reach was instead made to fail by hand, on a throwaway copy, by
# restoring the exact docstring sentence from c0ec657 that GUARD 3 leaked:
#
#     src/engcore/scientific/results/thresholds.py:
#         'cstr' names a thing -- the core knows shapes, not things
#
# Recorded here because the next person to read this list should not conclude
# from two green mutations that both reaches are covered.

#: The suites a mutation must turn red.
#:
#: **A list, and therefore the thing this file is worst at.** The harness's own
#: reach is the one guard here nothing else checks: a guard written into a
#: module not named below is verified by nobody, and the harness reports a
#: clean 21/21 either way -- "a guard derived from a hand-maintained list
#: guards only what someone remembered", which is the same defect one level up
#: from the four mutations that had silently stopped applying.
#:
#: It cannot be derived: which suite covers which guard is a fact about intent,
#: not about the tree. So it is written down, kept short, and every entry in
#: MUTATIONS names the suite it expects to fail in its description. The rule
#: for the next person is the cheap one: **a guard whose suite is not in this
#: tuple is not verified, whatever the harness prints.**
TARGETS = ("tests/test_core_guards.py", "tests/test_repair_guidance.py")
#: What the mutated copy needs to be a faithful copy. ``experiments`` is here
#: because a guard in the target suite reads the frozen experiment configs to
#: check that every package-level validity exemption names a file a freeze
#: actually pins. Without it that guard failed in the scratch tree for a reason
#: having nothing to do with any mutation -- which is a RED result that says
#: nothing, the same failure this harness exists to catch, one level up in its
#: own machinery. A mutation is only informative if everything else is
#: identical.
#:
#: `docs` was added for the same reason, one guard later and with the mistake
#: actually made rather than reasoned about. GUARD 18 checks that the
#: dependency table in `docs/SRIA.md` still agrees with the tree, because a
#: published number with nothing checking it goes stale silently -- and in a
#: scratch tree with no `docs/` that guard raised FileNotFoundError under
#: EVERY mutation. The harness printed 58/58 RED and the run was worthless:
#: every mutation was red on a missing file, so a guard that had become
#: decoration would have been reported as verified. A RED result that says
#: nothing is the failure this file exists to catch, and it had reappeared in
#: this very tuple two paragraphs below the sentence warning about it.
_COPIED = ("src", "tests", "experiments", "docs", "pyproject.toml")


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
        [sys.executable, "-X", "utf8", "-m", "pytest", *TARGETS, "-q",
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
