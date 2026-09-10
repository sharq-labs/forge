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

It takes about half an hour: seventy-two copies of the tree, three suites
against each. The cheap half of it -- that every mutation still matches the
source it names -- runs on every FAST invocation in
`tests/test_mutation_harness.py`, because five patterns once went stale and
nobody found out until somebody spent the half hour.

It is deliberately **not** a pytest module -- it
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

import ast
import hashlib
import io
import pathlib
import shutil
import subprocess
import sys
import time
import tokenize

#: Generous on purpose. A timeout is an absence of evidence and is reported
#: as one, so the only thing a tight budget buys is mutations nobody checked.
TEST_TIMEOUT = 2400

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
    # Repaired, and the repair is the reason `file` may now carry a `::scope`.
    #
    # Both of these anchored a TWO-LINE window whose second line was the code
    # that happened to sit under the guard rather than any part of it, and
    # 6238531 inserted GUARD 21's re-check between the two. From that commit
    # both reported MUTATION DID NOT APPLY and neither guard was verified by
    # anything again. Checked rather than assumed: each pattern counts 1 at
    # 6238531^ and 0 at 6238531, and 0 at every commit since.
    #
    # The honest anchor is the call itself -- and the call appears TWICE in
    # the file, once per place where a level stops being a field and becomes a
    # claim. Text alone cannot tell those two apart, and re-encoding the
    # neighbouring line to disambiguate is what broke them the first time. So
    # the search is confined to one function, located by `ast`. That scope is
    # the whole of the AST in this harness: it is what makes these two
    # expressible without naming code they are not about.
    ("G2f", "src/engcore/scientific/results/validation.py"
            "::ValidationReport.__post_init__",
     "        self._require_every_level_earned()\n",
     "",
     "a report stops re-applying the rule to what it was handed"),
    ("G2g", "src/engcore/scientific/results/validation.py"
            "::ValidationReport.attained_levels",
     "        self._require_every_level_earned()\n",
     "",
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
    # RENAMED, from `G8a`/`G8b`, which were already taken above.
    #
    # Two mutations carried each of those ids and the runner writes its work
    # tree at `mut_<id>`, so the second of each pair DELETED the first's tree
    # before running -- and the summary counted both, one line per entry, with
    # nothing saying that two different files had been reported under one
    # name. `_validate_declarations` now refuses a duplicate id outright.
    #
    # These two are the ones renamed because the electrical three are cited by
    # id in `docs/reviews/2026-09-07-adversarial-review.md` and a citation that
    # silently comes to mean another mutation is worse than an odd letter.
    # Worth recording while renaming them: GUARD 8 is the units guard -- "the
    # units backend cannot be changed by a run" -- so it is THESE that are
    # named for their guard and `G8a`-`G8c` that are historical labels on
    # electrical mutations. Renumbering the tree to fix that is a churn this
    # round is not, and the ids are labels rather than claims.
    ("G8d", "src/engcore/scientific/units/quantity.py",
     "        self.__dict__[\"_crafty_sealed\"] = True",
     "        pass",
     "the unit registry is never sealed (every refusal becomes a no-op)"),
    ("G8e", "src/engcore/scientific/units/quantity.py",
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
    # Repointed, and the description corrected with it. The old form passed
    # `exclusions=None`, which is not "a model that forgot to declare" but a
    # TYPE the field never accepts, and it died on `TypeError: 'NoneType'
    # object is not iterable` from inside the constructor -- red, and red for
    # a reason that says nothing about GUARD 14. The old description said the
    # TREE SWEEP was what noticed. It was not, and it structurally cannot be:
    # a model that stops declaring exclusions is refused at construction, so
    # its module never imports and the sweep never runs. Deleting the
    # declaration is what a domain would actually do, and the refusal is what
    # meets it.
    ("G14a", "src/engcore/domains/electrical/dc/models.py",
     "    exclusions=_DC_EXCLUSIONS,\n",
     "",
     "a shipped model stops declaring what it does not represent, and the "
     "constructor refuses it before the tree sweep can be reached"),
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
    # Repointed. The old form deleted the WHOLE `is NOT_DECLARED` branch,
    # which does not make exclusions optional -- it makes an undeclared one
    # fall into the `else` and iterate the sentinel, so the single exempted
    # model in the tree died on `TypeError: '_NotDeclared' object is not
    # iterable` at import. The mutation was red and its stated claim --
    # "omitting them is accepted at construction instead of refused" -- was
    # never exercised, because omitting them was not accepted. That is the
    # vacuity this file exists to refuse, one level up: a mutation whose
    # observed behaviour is not the behaviour it says it produces.
    #
    # The decision the description names is the exemption test, so that is
    # what is mutated: with it always true, every module is exempt and a model
    # may omit exclusions everywhere.
    ("G14d", "src/engcore/scientific/models/definition.py",
     "            if _exclusions_exempted(_constructing_module()) is None:\n",
     "            if False:\n",
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
    # Two halves, mutated separately, because they fail independently and a
    # single mutation could not tell them apart: the run must RECORD the
    # crossing, and the report must RENDER it. G20a is the line as it stood
    # before this commit.
    ("G20a", "src/engcore/systems/electrothermal/coupled.py",
     "            transfers=(\n"
     "                ambient_transfers(system, final)\n"
     "                + converted_transfers(plan, final)\n"
     "            ),",
     "            transfers=ambient_transfers(system, final),",
     "the coupled run goes back to dropping every converting crossing from "
     "its provenance, so a declared efficiency is spent and recorded nowhere"),
    ("G20b", "src/engcore/mcp/evidence.py",
     "            conversion = transfer.dependency.conversion\n"
     "            if conversion is None:\n"
     "                continue",
     "            conversion = transfer.dependency.conversion\n"
     "            if True:\n"
     "                continue",
     "the credibility report stops rendering the conversions its provenance "
     "carries, so the record exists and no reader sees it"),
    ("G21a", "src/engcore/scientific/models/definition.py",
     "            and self.conservative_screen\n",
     "            and True\n",
     "every range condition becomes a screen, so no bound in the repository "
     "can find against a design again"),
    ("G21b", "src/engcore/scientific/models/definition.py",
     "        if (\n"
     "            outcome is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN\n"
     "            and self.conservative_screen\n"
     "        ):\n"
     "            return ValidityStatus.UNKNOWN\n",
     "",
     "a declared screen stops being one, so the two records that say a value "
     "past their bound is not shown to be wrong go back to reporting it as "
     "evidence against"),
    ("G21c", "src/engcore/scientific/models/definition.py",
     "            \"conservative_screen\": self.conservative_screen,\n",
     "",
     "the screen stops crossing the record boundary, so a consumer reading a "
     "condition cannot tell a screen from a bound that certifies"),
    # Repaired, all three. These never applied AT ALL -- not once, at any
    # commit. `git log -S` finds no revision of `definition.py` containing
    # `if set(condition.requires) <= established:` or `missing =
    # sorted(set(required) - known)`, and `unknown.append(condition.name)`
    # has never stood at the indentation G22b named. They arrived in 695dd6a,
    # reconciled from a working tree whose gate was written one way, against a
    # `definition.py` where 03125e0 had landed it another: the gate is a
    # NEGATIVE test on the unmet prerequisites rather than a positive one on
    # the established set, and `_dependency_order` reads its requirements
    # through the index c9b3eba added. So GUARD 23 has never had a verified
    # mutation, and these three are written against the code that exists.
    ("G22a", "src/engcore/scientific/models/definition.py"
             "::ValidityDomain.assess",
     "            if unmet:\n",
     "            if False:\n",
     "the gate stops gating: a dependent condition is evaluated even when what "
     "it depends on was violated or never established, which is the whole "
     "defect and moves no benchmark number while it happens"),
    # Reporting moved into a second pass over the conditions in declaration
    # order, so the blocked dependent is no longer appended to a list at the
    # gate -- it is recorded as an OUTCOME there and read back below. The
    # outcome is what the mutation has to change, and changing it there keeps
    # the mutation on one decision: `unknown.append` in the reporting loop
    # would move every unknown condition, whatever blocked it.
    ("G22b", "src/engcore/scientific/models/definition.py"
             "::ValidityDomain.assess",
     "                outcomes[condition.name] = ValidityStatus.UNKNOWN\n",
     "                outcomes[condition.name] = ValidityStatus.IN_DOMAIN\n",
     "a blocked dependent is reported SATISFIED instead of unknown -- an "
     "untested bound entering the list that reads as evidence"),
    ("G22c", "src/engcore/scientific/models/definition.py"
             "::_dependency_order",
     "        missing = sorted(requirements[condition.name] - known)\n",
     "        missing = []\n",
     "a requires naming a condition the domain does not have stops being "
     "refused, so the condition is permanently UNKNOWN and nothing says why"),
    ("G22d", "src/engcore/scientific/models/definition.py",
     "            \"requires\": list(self.requires),\n",
     "",
     "the dependency stops crossing the record boundary, so a consumer "
     "reading a condition cannot tell a gated bound from an independent one"),
    # GUARD 24 has no number in `test_core_guards.py` and is not a guard in
    # that file's sense. These three cover the two unit semantics the first
    # blind round found, and they are here because a defect found by a
    # benchmark and fixed once is a defect nothing is watching: both fixes are
    # a single branch, and a single branch is exactly what a refactor
    # straightens out. `tests/test_offset_unit_declaration.py` joins TARGETS
    # for them -- it is the suite that asserts the repaired behaviour, and a
    # guard whose suite is not in that tuple is verified by nobody.
    ("G24a", "src/engcore/scientific/units/quantity.py::Quantity.parse",
     "        if separator and unit.strip():\n",
     "        if False:\n",
     "a declaration may no longer state a temperature in degrees Celsius: "
     "the payload boundary hands '20 degC' to the backend's string parser "
     "again, which reads it as a multiplication and refuses"),
    ("G24b", "src/engcore/scientific/models/definition.py::CrossLimitCondition",
     "        if is_ratio_scale(numerator.units) and is_ratio_scale(denominator.units):\n",
     "        if True:\n",
     "a ratio of two temperatures is taken on an interval scale again, so the "
     "answer depends on which unit the caller wrote and a satisfied condition "
     "reports as violated"),
    # GUARD 25 is the core semantic invariants round: four contracts that
    # were reachable through the public API and produced an ambiguous, lossy
    # or inverted declaration rather than a refusal. Each mutation restores
    # exactly the behaviour that was there before the fix, so a green one
    # means the repair is unguarded.
    ("G25a", "src/engcore/scientific/results/result.py"
             "::ScientificResult._checked_validity",
     "            if model_id in versions and versions[model_id] != version:\n",
     "            if False:\n",
     "a result may again declare one model at two versions, so a single "
     "validity verdict answers for two different claims"),
    ("G25b", "src/engcore/scientific/models/definition.py::_declared_bool",
     "    if not isinstance(value, bool):\n",
     "    if False:\n",
     "a semantic flag takes a non-boolean again -- 'false' is truthy, so the "
     "declaration is stored as its own opposite"),
    ("G25c", "src/engcore/scientific/models/registry.py::ModelRegistry.from_dict",
     "        require_schema(payload, REGISTRY_SCHEMA)\n",
     "",
     "a registry writes a versioned schema and reads any payload at all, "
     "including a future version of its own family"),
    ("G25d", "src/engcore/scientific/results/data_reference.py"
             "::ScientificDataReference.__post_init__",
     "        if isinstance(self.count, bool) or not isinstance(self.count, int):\n",
     "        if False:\n",
     "a declared count is silently truncated again, so a reference naming "
     "1.9 values compares equal to one naming 1"),
    ("G24c", "src/engcore/systems/electrothermal/coupled.py::_require_ratio_scale",
     "    if not is_ratio_scale(normalized):\n",
     "    if False:\n",
     "a difference -- a coupling tolerance -- is admitted on a scale whose "
     "zero is a convention, which is the refusal the degC fix had to leave "
     "standing"),
    ("G26a", "src/engcore/scientific/results/uncertainty.py"
             "::Uncertainty.__post_init__",
     "            if self.confidence_level is not None:\n",
     "            if False:\n",
     "an uncertainty that says nothing was evaluated carries a coverage "
     "probability again, so a reader sizes an interval off a record that "
     "computed none"),
    ("G26b", "src/engcore/scientific/results/provenance.py"
             "::ProvenanceRecord.__post_init__",
     "            if not math.isfinite(tolerance):\n",
     "            if False:\n",
     "provenance records the bound a run was judged against as an infinity "
     "again, so a run solved to no bound reads as one that was"),
    ("G26c", "src/engcore/scientific/solvers/protocol.py"
             "::SolverSettings.__post_init__",
     "        unrecordable = unwritable(self.options, path=\"options\")\n",
     "        unrecordable = None\n",
     "the settings a run says it used stop being held to what a record can "
     "carry, so a NaN or a non-string key survives into provenance"),
)


# ---------------------------------------------------------------------
# WHAT KILLED IT, and why that is a second table rather than a sixth field.
#
# `MUTATIONS` says what was removed. It does not say what noticed, and until
# this table existed the harness could not tell a guard firing from the suite
# being red anyway -- which it was, under every mutation, for twenty commits.
# See `_COPIED`.
#
# Each entry is ``id: (mechanism, expect)``.
#
# `expect` is a SUBSTRING OF A FAILING TEST NAME, and it is the whole of the
# relevance check: a mutation that turns the suite red without it among the
# failures is reported RED (UNRELATED), which fails the round exactly as a
# green one does. That is what makes "64 of 64 red" a claim about guards
# rather than about exit codes.
#
# `mechanism` is the kind of rule that fired, for review rather than for the
# machine. The three unacceptable ones are named so they can be refused:
# a mutation killed only by a broken import, a broken parse, or a failure that
# has nothing to do with it is not evidence that any guard works.
#
# LAYERING_INVARIANT is an addition to the categories, and is recorded as one.
# Six mutations here attack guards that police the TREE -- what the core may
# know, what SRIA may import, what a clean install must contain -- rather than
# a scientific record. Filing those under OTHER would mark six real guards as
# unproven, so they get a name instead.
MECHANISMS = (
    "SCIENTIFIC_ASSERTION",
    "CONTRACT_REFUSAL",
    "SERIALIZATION_INVARIANT",
    "PROVENANCE_INVARIANT",
    "VALIDITY_INVARIANT",
    "VALIDATION_INVARIANT",
    "TYPE_INVARIANT",
    "LAYERING_INVARIANT",
)
#: Not proof. A mutation whose observed kill is one of these fails the round.
UNACCEPTABLE = ("IMPORT_OR_SYNTAX_FAILURE", "UNRELATED_FAILURE", "OTHER")

#: `expect` for a mutation that makes the CORE REFUSE at import: the domain
#: module builds its own model at import time, so a mutation that makes that
#: model invalid stops the suite during collection and no named test runs. The
#: refusal is the guard, and the harness checks that it IS a refusal -- the
#: mutated file must parse, and the collection error must not be an
#: ImportError, a SyntaxError or a NameError. Without that check this sentinel
#: would excuse exactly the kill mechanism it exists to keep out.
REFUSED_AT_IMPORT = "<refused at import>"

#: Python-level failures that mean the mutation broke the language rather than
#: a rule. Matched against the mutated run's output when nothing was collected.
_NOT_A_REFUSAL = (
    "SyntaxError",
    "IndentationError",
    "ModuleNotFoundError",
    "ImportError",
    "NameError",
)

EVIDENCE: dict[str, tuple[str, str]] = {
    "G1a": ("CONTRACT_REFUSAL",
            "test_a_caller_parameter_named_after_a_derived_quantity_is_refused"),
    "G1b": ("CONTRACT_REFUSAL",
            "test_a_reserved_name_is_refused_in_the_declared_half_of_an_assessment"),
    "G1c": ("CONTRACT_REFUSAL",
            "test_a_domain_cannot_assemble_a_name_it_did_not_reserve"),
    "G1e": ("CONTRACT_REFUSAL",
            "test_a_derived_quantity_declared_as_an_input_is_refused_at_assessment"),
    # One target module builds the affected system at import and errors;
    # the other two collect, and the guard that names this exact rule --
    # that the refusal fires on forgery and not on another model's
    # business -- is among the tests that then fail.
    "G1f": ("CONTRACT_REFUSAL",
            "test_the_refusal_does_not_fire_on_another_model_s_business"),
    "G1d": ("CONTRACT_REFUSAL", REFUSED_AT_IMPORT),
    "G8a": ("LAYERING_INVARIANT",
            "test_the_discovery_found_exactly_the_repository"),
    "G8b": ("VALIDATION_INVARIANT",
            "test_every_check_a_live_solve_produces_earns_its_level"),
    "G8c": ("SCIENTIFIC_ASSERTION",
            "test_a_declared_derating_line_repairs_the_rating_and_refuses_the_rest"),
    "G2a": ("VALIDATION_INVARIANT",
            "test_a_check_altered_after_it_was_built_cannot_carry_a_level"),
    "G2e": ("TYPE_INVARIANT",
            "test_a_report_refuses_anything_that_is_not_a_validation_check"),
    "G2f": ("VALIDATION_INVARIANT",
            "test_a_check_altered_after_it_was_built_cannot_carry_a_level"),
    "G2g": ("VALIDATION_INVARIANT",
            "test_a_check_altered_after_it_was_built_cannot_carry_a_level"),
    "G2b": ("VALIDATION_INVARIANT",
            "test_every_check_a_live_solve_produces_earns_its_level"),
    "G2c": ("VALIDATION_INVARIANT",
            "test_every_check_a_live_solve_produces_earns_its_level"),
    "G2d": ("CONTRACT_REFUSAL",
            "test_the_construction_axis_is_still_closed_on_every_route_to_it"),
    "G3a": ("VALIDATION_INVARIANT", "test_a_derived_threshold_set_awards_nothing"),
    "G3b": ("VALIDATION_INVARIANT",
            "test_no_gate_lets_its_caller_set_the_threshold_it_awards_a_level_against"),
    "G4a": ("CONTRACT_REFUSAL",
            "test_the_registry_refuses_a_solver_that_decides_its_own_support"),
    "G4b": ("CONTRACT_REFUSAL", "test_a_problem_requesting_a_superset_is_refused"),
    "G5a": ("PROVENANCE_INVARIANT",
            "test_provenance_refuses_a_solver_no_binding_covers"),
    "G6a": ("CONTRACT_REFUSAL",
            "test_the_core_refuses_a_problem_that_declares_no_fingerprint"),
    "G6b": ("CONTRACT_REFUSAL",
            "test_the_cstr_domain_refuses_an_unfingerprinted_problem"),
    "G7a": ("CONTRACT_REFUSAL",
            "test_a_succeeded_solve_cannot_return_a_number_that_is_not_a_number"),
    "G9a": ("CONTRACT_REFUSAL",
            "test_a_result_that_declares_a_model_and_says_nothing_is_refused"),
    "G9b": ("CONTRACT_REFUSAL",
            "test_a_result_that_declares_a_model_and_says_nothing_is_refused"),
    "G9c": ("VALIDITY_INVARIANT",
            "test_every_result_construction_in_the_repository_states_a_position"),
    "G12a": ("CONTRACT_REFUSAL",
             "test_a_crossed_quantity_arriving_undeclared_is_refused"),
    "G12b": ("CONTRACT_REFUSAL",
             "test_a_transfer_states_a_source_an_instant_and_an_agreeing_dimension"),
    "G12c": ("CONTRACT_REFUSAL",
             "test_two_values_crossing_one_declaration_at_one_instant_are_refused"),
    "G12d": ("SCIENTIFIC_ASSERTION",
             "test_the_declared_crossing_is_what_lets_repair_invert_the_condition"),
    "G11a": ("PROVENANCE_INVARIANT",
             "test_a_lineage_claim_without_the_record_it_names_is_refused"),
    "G11b": ("PROVENANCE_INVARIANT",
             "test_a_typed_name_cannot_outrank_the_record_that_exists"),
    "G11c": ("PROVENANCE_INVARIANT", "test_a_record_cannot_be_its_own_source"),
    "G10a": ("SERIALIZATION_INVARIANT",
             "test_a_result_refuses_at_construction_what_it_could_not_record"),
    "G10b": ("SERIALIZATION_INVARIANT",
             "test_a_result_refuses_at_construction_what_it_could_not_record"),
    "G10c": ("SERIALIZATION_INVARIANT",
             "test_a_result_refuses_at_construction_what_it_could_not_record"),
    "G8d": ("CONTRACT_REFUSAL",
            "test_every_route_pint_offers_for_changing_the_registry_is_refused"),
    "G8e": ("CONTRACT_REFUSAL",
            "test_the_fingerprint_detects_what_the_refusal_cannot_prevent"),
    "G7b": ("CONTRACT_REFUSAL",
            "test_the_admission_layer_is_still_the_route_that_says_what_went_wrong"),
    "G13a": ("CONTRACT_REFUSAL",
             "test_an_input_declared_as_a_constant_refuses_a_curve"),
    "G13b": ("VALIDITY_INVARIANT",
             "test_outside_a_declared_interval_there_is_no_number_only_a_status"),
    "G13c": ("CONTRACT_REFUSAL",
             "test_a_declared_interval_may_not_reach_past_the_samples"),
    "G13d": ("PROVENANCE_INVARIANT",
             "test_a_cell_declaring_a_curve_is_a_different_cell_and_says_so_everywhere"),
    "G14a": ("CONTRACT_REFUSAL", REFUSED_AT_IMPORT),
    "G14b": ("SERIALIZATION_INVARIANT",
             "test_the_credibility_report_carries_exclusions_beside_validity"),
    "G14c": ("CONTRACT_REFUSAL",
             "test_an_empty_exclusion_list_is_a_claim_and_nobody_makes_it_by_accident"),
    # Not the tree sweep. Every shipped model still declares its exclusions
    # under this mutation -- what changes is that omitting them stops being
    # refused, and the test that constructs a model with none is what says so.
    "G14d": ("CONTRACT_REFUSAL",
             "test_an_empty_exclusion_list_is_a_claim_and_nobody_makes_it_by_accident"),
    "G14e": ("CONTRACT_REFUSAL",
             "test_an_empty_exclusion_list_is_a_claim_and_nobody_makes_it_by_accident"),
    "G15a": ("CONTRACT_REFUSAL",
             "test_a_crossing_that_carries_energy_must_say_how_much_arrives"),
    "G15b": ("SCIENTIFIC_ASSERTION",
             "test_conservation_is_checked_and_a_conversion_that_does_not_balance_fails"),
    "G15c": ("VALIDITY_INVARIANT",
             "test_an_undeclared_efficiency_is_unknown_and_never_one"),
    "G16a": ("SCIENTIFIC_ASSERTION",
             "test_a_transfer_may_not_carry_more_than_its_conversion_budgets"),
    "G16b": ("CONTRACT_REFUSAL",
             "test_a_conversion_transfer_must_say_what_entered_and_a_transport_may_not"),
    "G16c": ("SCIENTIFIC_ASSERTION",
             "test_the_coupling_loop_spends_the_budget_where_the_value_crosses"),
    "G17a": ("LAYERING_INVARIANT",
             "test_the_scientific_core_knows_shapes_and_not_things"),
    "G17b": ("LAYERING_INVARIANT",
             "test_the_scientific_core_knows_shapes_and_not_things"),
    "G18a": ("LAYERING_INVARIANT",
             "test_nothing_under_sria_imports_a_domain_or_a_system"),
    "G19a": ("LAYERING_INVARIANT",
             "test_every_dependency_the_tree_reaches_for_is_declared"),
    "G19b": ("LAYERING_INVARIANT",
             "test_every_dependency_the_tree_reaches_for_is_declared"),
    "G20a": ("PROVENANCE_INVARIANT",
             "test_a_declared_conversion_reaches_the_credibility_report"),
    "G20b": ("SERIALIZATION_INVARIANT",
             "test_the_report_shows_where_the_energy_that_did_not_arrive_went"),
    # The screen still screens under this mutation -- what stops working
    # is the bound that is NOT a screen, so the guard that names the
    # rule is the one asserting an undeclared bound still finds. G21b
    # is the other direction and keeps the screen test.
    "G21a": ("VALIDITY_INVARIANT",
             "test_an_undeclared_bound_still_finds_against_a_design"),
    "G21b": ("VALIDITY_INVARIANT",
             "test_a_conservative_screen_reports_a_gap_and_not_a_finding"),
    "G21c": ("SERIALIZATION_INVARIANT",
             "test_the_screen_survives_the_record_a_consumer_reads"),
    "G22a": ("VALIDITY_INVARIANT",
             "test_a_dependent_condition_is_not_evaluated_until_its_gate_holds"),
    "G22b": ("VALIDITY_INVARIANT",
             "test_a_blocked_dependent_is_a_gap_and_never_a_finding"),
    "G22c": ("CONTRACT_REFUSAL",
             "test_a_dependency_that_cannot_be_satisfied_is_refused_at_construction"),
    "G22d": ("SERIALIZATION_INVARIANT",
             "test_the_dependency_survives_the_record_a_consumer_reads"),
    "G24a": ("SCIENTIFIC_ASSERTION",
             "test_a_celsius_declaration_parses_to_the_kelvin_it_means"),
    "G24b": ("SCIENTIFIC_ASSERTION",
             "test_a_ratio_of_two_temperatures_does_not_depend_on_the_scale_written"),
    "G24c": ("CONTRACT_REFUSAL",
             "test_an_affine_coupling_tolerance_is_still_refused"),
    "G25a": ("CONTRACT_REFUSAL",
             "test_a_result_cannot_declare_one_model_at_two_versions"),
    "G25b": ("CONTRACT_REFUSAL",
             "test_a_semantic_flag_refuses_anything_that_is_not_a_boolean"),
    "G25c": ("SERIALIZATION_INVARIANT",
             "test_a_registry_refuses_a_schema_it_did_not_write"),
    "G25d": ("TYPE_INVARIANT",
             "test_a_declared_count_is_never_silently_coerced"),
    "G26a": ("CONTRACT_REFUSAL",
             "test_an_unknown_uncertainty_cannot_carry_a_confidence_level"),
    "G26b": ("PROVENANCE_INVARIANT",
             "test_a_provenance_tolerance_must_be_finite"),
    "G26c": ("CONTRACT_REFUSAL",
             "test_solver_options_are_held_to_the_free_form_rule"),
}

#: The five that were dead when this round opened, pinned by name. Deleting or
#: renaming one is how the problem comes back quietly, so it is a failure here
#: and in `tests/test_mutation_harness.py`, which re-applies all of them
#: against the live source on every FAST run.
REPAIRED = ("G2f", "G2g", "G22a", "G22b", "G22c")


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
#: clean 72/72 either way -- "a guard derived from a hand-maintained list
#: guards only what someone remembered", which is the same defect one level up
#: from the five mutations that had silently stopped applying.
#:
#: It cannot be derived: which suite covers which guard is a fact about intent,
#: not about the tree. So it is written down, kept short, and every entry in
#: MUTATIONS names the suite it expects to fail in its description. The rule
#: for the next person is the cheap one: **a guard whose suite is not in this
#: tuple is not verified, whatever the harness prints.**
TARGETS = (
    "tests/test_core_guards.py",
    "tests/test_repair_guidance.py",
    # Added with G24. It is the suite that pins the two unit semantics
    # benchmarks/blind/v1 found, and without it those two mutations would
    # be run against suites that cannot see them and reported GREEN --
    # a real finding about nothing.
    "tests/test_offset_unit_declaration.py",
    # Added with G25. It carries the four contracts the core semantic
    # invariants round proved and repaired, and without it those four
    # mutations would run against suites that cannot see them.
    "tests/test_core_semantic_invariants.py",
)
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
#
# `benchmarks` was added for the same reason a THIRD time, and this one
# had already done its damage. `tests/test_blind_challenge_guards.py`
# imports `benchmarks.blind`; GUARD 19 excuses a top-level name it can
# find on the path and reports every other one as an undeclared
# dependency. With no `benchmarks/` in the copy the name is not findable,
# so `test_every_dependency_the_tree_reaches_for_is_declared` FAILED
# UNDER EVERY MUTATION AND UNDER NONE -- including in an unmutated tree.
# Sixty-four mutations were reported RED with that failure among their
# causes, and for `G19a` and `G19b` it was the ONLY failure: the two
# mutations written to verify GUARD 19 were verified by a test that was
# already red, which is a green result wearing a red hat.
#
# Reasoning about this tuple is what failed twice; `_control` below
# measures it instead.
_COPIED = ("src", "tests", "experiments", "docs", "benchmarks", "pyproject.toml")


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


def _scope_span(text: str, scope: str) -> tuple[int, int]:
    """Character bounds of ``Class.function`` in `text`, located by `ast`.

    THE ONLY SEMANTIC TARGETING IN THIS FILE, and deliberately the smallest
    thing that works. Two mutations need to remove a call that appears twice
    in one module, once per place where a level becomes a claim; a whole-line
    match cannot tell them apart, and the previous answer -- pinning the
    NEIGHBOURING line to disambiguate -- is what silently killed both when a
    line was inserted between them.

    Narrowing the search to a named function is enough for that, and it
    survives anything that does not move the code out of the function it is
    in. It is not a mutation framework and must not become one: it resolves a
    name to a span and the replacement below is still ordinary text.
    """
    node: ast.AST = ast.parse(text)
    for name in scope.split("."):
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, (ast.ClassDef, ast.FunctionDef,
                                   ast.AsyncFunctionDef))
                and child.name == name
            ):
                node = child
                break
        else:
            raise LookupError(f"{scope!r}: no {name!r} here")
    lines = text.splitlines(keepends=True)
    start = sum(len(l) for l in lines[: node.lineno - 1])  # type: ignore[attr-defined]
    end = sum(len(l) for l in lines[: node.end_lineno])  # type: ignore[attr-defined]
    return start, end


def _validate_declarations() -> None:
    """Refuse a table that cannot produce evidence, before anything is run.

    Every check here is one the harness previously could not make, and one of
    them had already gone wrong: two mutations shared the id ``G8a`` and two
    shared ``G8b``, the runner writes its tree at ``mut_<id>``, so the second
    of each pair deleted the first's tree and both were counted.
    """
    seen: set[str] = set()
    for mid, *_rest in MUTATIONS:
        if mid in seen:
            raise SystemExit(
                f"duplicate mutation id {mid!r}: two mutations under one name "
                f"share a work tree and are reported as one result"
            )
        seen.add(mid)
    unclassified = sorted(seen - set(EVIDENCE))
    if unclassified:
        raise SystemExit(
            f"no kill mechanism declared for {unclassified}; a result nobody "
            f"can classify is not evidence"
        )
    orphaned = sorted(set(EVIDENCE) - seen)
    if orphaned:
        raise SystemExit(f"EVIDENCE names mutations that do not exist: {orphaned}")
    for mid, (mechanism, _expect) in sorted(EVIDENCE.items()):
        if mechanism in UNACCEPTABLE:
            raise SystemExit(
                f"{mid} declares {mechanism}, which is not proof that a guard "
                f"works"
            )
        if mechanism not in MECHANISMS:
            raise SystemExit(f"{mid} declares unknown mechanism {mechanism!r}")
    missing = sorted(set(REPAIRED) - seen)
    if missing:
        raise SystemExit(
            f"the mutations repaired in this round are gone: {missing}. They "
            f"were dead once; deleting one is how that becomes true again "
            f"without anybody noticing"
        )


def _copy_tree(repo: pathlib.Path, work: pathlib.Path) -> None:
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


def _apply(work: pathlib.Path, spec: str, old: str, new: str):
    """Mutate one file in the copy. Returns ``(before, after)`` or a refusal.

    The read stays binary -- a text read would hide a file whose bytes differ
    -- and newlines are normalised before the search, because a multi-line
    target is written with a bare line feed while a working tree on Windows
    holds a carriage return before it. Four mutations had silently stopped
    applying for exactly that reason.
    """
    relative, _, scope = spec.partition("::")
    path = work / relative
    text = path.read_bytes().decode("utf-8").replace(CRLF, LF)
    if scope:
        try:
            low, high = _scope_span(text, scope)
        except LookupError as exc:
            return f"SCOPE NOT FOUND ({exc})"
        region = text[low:high]
        if region.count(old) != 1:
            return f"MUTATION DID NOT APPLY (count={region.count(old)} in {scope})"
        mutated = text[:low] + region.replace(old, new) + text[high:]
    else:
        if text.count(old) != 1:
            return f"MUTATION DID NOT APPLY (count={text.count(old)})"
        mutated = text.replace(old, new)
    before, after = _code_digest(text), _code_digest(mutated)
    if before == after:
        return f"MUTATION CHANGED NO CODE ({before})"
    try:
        ast.parse(mutated)
    except SyntaxError as exc:
        # A mutation that breaks the parse turns every suite red and says
        # nothing about any guard. It is refused here rather than counted.
        return f"MUTATION BROKE THE PARSE ({exc})"
    path.write_bytes(mutated.encode("utf-8"))
    return (before, after)


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


def _run(where: pathlib.Path, scratch: pathlib.Path):
    """Run TARGETS in `where`. Returns ``(code, tail, failed, output)``.

    ``code is None`` means the harness ran out of time, which is NOT a red
    suite: nothing was observed, and a mutation whose only evidence is that
    the run did not finish is a mutation nobody checked.
    """
    try:
        done = subprocess.run(
            # `--continue-on-collection-errors`, because without it ONE
            # unimportable module stops the whole run and every guard that
            # would have fired never executes. `G8a` breaks a domain module
            # on purpose and the guard that must notice is an assertion in
            # `test_core_guards.py`, which collected fine -- but two other
            # target modules import that domain transitively, pytest
            # interrupted on their errors, and zero tests ran. The mutation
            # was red on the exit code and the guard was never asked.
            [sys.executable, "-X", "utf8", "-m", "pytest", *TARGETS, "-q",
             "-p", "no:randomly", "--continue-on-collection-errors",
             "--basetemp", str(scratch / "pt" / "bt")],
            cwd=where, capture_output=True, text=True, timeout=TEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, f"HARNESS TIMEOUT after {TEST_TIMEOUT}s", [], ""
    lines = [l for l in done.stdout.splitlines() if l.strip()]
    failed = [l.split("::")[-1].split()[0]
              for l in done.stdout.splitlines() if l.startswith("FAILED")]
    return done.returncode, (lines[-1] if lines else "?"), failed, done.stdout


def _control(repo: pathlib.Path, scratch: pathlib.Path) -> None:
    """TARGETS, on an unmutated copy, before any mutation is believed.

    THE CHECK THIS HARNESS DID NOT HAVE, and the one its own docstring twice
    described the need for while reasoning about `_COPIED` instead of
    measuring it. A suite that is red in the copy makes every mutation red for
    free: `G19a` and `G19b` were reported RED for twenty commits with a single
    failing test between them, and that test failed with no mutation applied
    at all.

    A red control does not fail one mutation. It makes the whole round
    unreadable, so it stops here.
    """
    work = scratch / "control"
    _copy_tree(repo, work)
    started = time.monotonic()
    code, tail, failed, _out = _run(work, scratch)
    took = time.monotonic() - started
    if code == 0:
        print(f"{'CONTROL':6} {'GREEN':20} unmutated copy, {took:.0f}s -- "
              f"a red result below is the mutation's doing")
        print(f"{'':26} {tail}")
        print()
        return
    print(f"{'CONTROL':6} {'RED -- ROUND VOID':20} the copied tree fails with "
          f"NO mutation applied")
    print(f"{'':26} {tail}")
    for name in sorted(set(failed)):
        print(f"{'':26} {name}")
    raise SystemExit(
        "every mutation below would be red for this reason and none of it "
        "would be evidence. Fix the copy (see _COPIED) before running again."
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: python -X utf8 tests/mutation_guards.py <scratch-dir> "
              "[id ...]")
        return 2
    _self_test()
    _validate_declarations()
    repo = pathlib.Path(__file__).resolve().parent.parent
    scratch = pathlib.Path(argv[0]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    only = set(argv[1:])
    selected = [m for m in MUTATIONS if not only or m[0] in only]
    unknown = sorted(only - {m[0] for m in MUTATIONS})
    if unknown:
        raise SystemExit(f"no such mutation: {unknown}")

    _control(repo, scratch)

    results: dict[str, str] = {}
    for mid, spec, old, new, what in selected:
        mechanism, expect = EVIDENCE[mid]
        work = scratch / f"mut_{mid}"
        _copy_tree(repo, work)

        applied = _apply(work, spec, old, new)
        if isinstance(applied, str):
            # Not a fact about the guard. Reported as loudly as a green
            # result, and never counted as one.
            print(f"{mid:5} {applied} -- {what}")
            results[mid] = "DID_NOT_APPLY"
            continue
        before, after = applied

        started = time.monotonic()
        code, tail, failed, output = _run(work, scratch)
        took = time.monotonic() - started

        if code is None:
            verdict, results[mid] = "HARNESS TIMEOUT", "TIMEOUT"
        elif code == 0:
            verdict, results[mid] = "GREEN -- DECORATION", "GREEN"
        elif not failed:
            # Nothing was collected: the suite stopped before any test ran.
            # That is evidence only when the core REFUSED, and only when the
            # mutation says so. A broken parse or a broken import is the kill
            # mechanism this harness refuses to accept.
            raised = "\n".join(
                l for l in output.splitlines() if l.startswith("E   ")
            )
            broke = next((n for n in _NOT_A_REFUSAL if n in raised), None)
            if expect != REFUSED_AT_IMPORT:
                verdict, results[mid] = "RED (NOT THE GUARD)", "UNRELATED"
            elif broke:
                verdict, results[mid] = f"RED ({broke})", "IMPORT_OR_SYNTAX"
            else:
                verdict, results[mid] = "RED (refused at import)", "RED"
        elif expect == REFUSED_AT_IMPORT:
            verdict, results[mid] = "RED (expected a refusal)", "UNRELATED"
        elif any(expect in name for name in failed):
            verdict, results[mid] = "RED", "RED"
        else:
            verdict, results[mid] = "RED (NOT THE GUARD)", "UNRELATED"

        print(f"{mid:5} {verdict:20} {what}")
        print(f"{'':26} code {before} -> {after}   {mechanism}   {took:.0f}s")
        print(f"{'':26} {tail}")
        if results[mid] == "UNRELATED":
            print(f"{'':26} expected {expect!r} among the failures")
        if failed:
            shown = sorted(set(failed))
            print(f"{'':26} {', '.join(shown[:3])}"
                  + (f" (+{len(shown) - 3} more)" if len(shown) > 3 else ""))

    print()
    missing = sorted({m[0] for m in selected} - set(results))
    counts = {state: sorted(k for k, v in results.items() if v == state)
              for state in ("RED", "GREEN", "DID_NOT_APPLY", "TIMEOUT",
                            "UNRELATED", "IMPORT_OR_SYNTAX")}
    print(f"{len(counts['RED'])}/{len(selected)} mutations were killed by the "
          f"guard they name.")
    for state in ("GREEN", "DID_NOT_APPLY", "TIMEOUT", "UNRELATED",
                  "IMPORT_OR_SYNTAX"):
        if counts[state]:
            print(f"{state}: {', '.join(counts[state])}")
    if missing:
        print(f"NO RESULT: {', '.join(missing)}")
    if counts["GREEN"]:
        print("A green mutation names a check that is decoration -- but check "
              "the mutation first: a green result is a claim about the "
              "mutation before it is a claim about the guard.")
    if counts["UNRELATED"]:
        print("A red suite is not evidence unless the guard that names the "
              "rule is what failed. Repoint the mutation or correct EVIDENCE; "
              "do not accept the exit code.")
    # FAIL CLOSED on every one of them. A mutation that did not apply, timed
    # out, was killed by a broken import or was killed by something else is a
    # guard nobody verified, and none of those may be reported as a pass.
    return 0 if len(counts["RED"]) == len(selected) and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
