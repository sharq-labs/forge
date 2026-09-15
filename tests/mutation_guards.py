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
import re
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
    # GUARD 27 is the Hybrid UQ trust-boundary round (HUQ1-HUQ6): Core V2 is
    # CORE_CERTIFIED and its fail-closed guards had never been observed to
    # fail. Each mutation restores the behaviour from before its fix, and
    # `tests/hybrid_uq/test_hybrid_uq_trust_boundary.py` joins TARGETS for
    # them -- without it these would run against suites that cannot see
    # them and be reported GREEN. G27g (HUQ7) was added in review: a serialized
    # grid record carries no grid, so its moments are bound by a digest.
    ("G27a", "src/engcore/hybrid_uq/sensitivity.py::_bind_supplied_sensitivity",
     "    mismatches = [label for label, (found, wanted) in expected.items() if found != wanted]\n",
     "    mismatches = [label for label, (found, wanted) in expected.items() "
     "if found != wanted and label != \"observation sigmas\"]\n",
     "HUQ1: a supplied LocalSensitivity is no longer held to the request's "
     "observation sigmas, so a stale record with the same ids and estimate "
     "and other sigmas reshapes the covariance"),
    ("G27b", "src/engcore/hybrid_uq/_records.py::require_valid_covariance",
     "    if smallest < -tolerance:\n",
     "    if False:\n",
     "HUQ2: an indefinite covariance with a positive diagonal is accepted "
     "again, so a record can carry a negative variance direction as "
     "uncertainty"),
    ("G27c", "src/engcore/hybrid_uq/predictive.py::linearized_predictive_uq",
     "        skipped = 2 * len(z0)\n",
     "        skipped = 0\n",
     "HUQ3: a linearized prediction whose nonlinearity check was switched off "
     "keeps a SUPPORTED claim again"),
    ("G27d", "src/engcore/hybrid_uq/sensitivity.py::central_difference",
     "            if error == 0.0:\n                break\n",
     "            if True:\n                break\n",
     "HUQ4: the first finite-difference quotient is accepted without showing "
     "it converged, so a biased or noise-dominated Jacobian becomes a "
     "covariance"),
    ("G27e", "src/engcore/hybrid_uq/router.py::HybridUQResult._require_one_truth",
     "            if self.mean != local.inference_point:\n",
     "            if False:\n",
     "HUQ5: a LOCAL_GAUSSIAN routed record may report a mean its own local "
     "posterior contradicts"),
    ("G27f", "src/engcore/hybrid_uq/local_gaussian.py::_coefficient_in_output_unit",
     "    term = Quantity(magnitude, unit) * Quantity(1.0, source)\n",
     "    term = Quantity(magnitude, output)\n",
     "HUQ6: a reparameterization combines coordinates of any dimensions under "
     "any declared unit again, so volt plus ampere reads as a voltage"),
    ("G27g", "src/engcore/hybrid_uq/router.py::HybridUQResult._require_one_truth",
     "            if summary.get(\"moments_digest\") != moments:\n",
     "            if False:\n",
     "HUQ7: a serialized grid record is no longer bound to the moments its "
     "summarized grid produced, so it can keep the grid digest and report "
     "another mean or covariance"),
    # GUARD 28 is the core trust closure round: the invariants PR #39 and PR
    # #24 proposed, reproduced against main and enforced in the form current
    # main's architecture allows. `tests/test_core_trust_closure.py` joins
    # TARGETS for them.
    ("G28a", "src/engcore/inference/admissibility.py::_require_applicability_not_refuted",
     "    if refuted:\n",
     "    if False:\n",
     "inference admits a numerically clean source whose model was assessed "
     "OUTSIDE_VALIDATED_DOMAIN or UNKNOWN, so it enters a posterior as evidence"),
    ("G28b", "src/engcore/scientific/results/result.py::ScientificResult._require_provenance_consistency",
     "        missing_models = sorted(result_models - set(self.provenance.models))\n",
     "        missing_models = []\n",
     "a result may again attribute itself to a model its own provenance does "
     "not name"),
    ("G28c", "src/engcore/scientific/solvers/protocol.py::DeclaredSupport.support_gap",
     "            served = {model.key for model in self.served_models}\n"
     "            referenced = {reference.key for reference in problem.models}\n",
     "            served = {(model.model_id,) for model in self.served_models}\n"
     "            referenced = {(reference.model_id,) for reference in problem.models}\n",
     "declared solver support matches a model by id again, so a problem naming "
     "model@2 runs on a solver that implements model@1"),
    ("G28d", "src/engcore/sria/evidence.py::Evidence.require_integrity",
     "        if self._compute_content_hash() != self.content_hash:\n",
     "        if False:\n",
     "SRIA evidence whose live content no longer matches its hash keeps its "
     "record identity and is accepted by the gateway"),
    ("G28e", "src/engcore/sria/gateway.py::BeliefEntry.__post_init__",
     "        object.__setattr__(self, \"claim_payload\", freeze(dict(self.claim_payload)))\n",
     "        object.__setattr__(self, \"claim_payload\", dict(self.claim_payload))\n",
     "a stored belief entry's payload is mutable through a read again"),
    ("G28f", "src/engcore/sria/uncertainty.py::UncertaintyDeclaration.__post_init__",
     "        object.__setattr__(self, \"channels\", freeze(channels))\n",
     "        object.__setattr__(self, \"channels\", channels)\n",
     "an uncertainty channel inside evidence content identity can be changed "
     "after the evidence was hashed"),
    ("G28g", "src/engcore/scientific/solvers/registry.py::SolverDefinition._remember",
     "            raise TypeError(\n"
     "                f\"the factory registered for {label} returned a solver session \"\n",
     "            return None\n"
     "            raise TypeError(\n"
     "                f\"the factory registered for {label} returned a solver session \"\n",
     "a solver session that cannot be tracked is issued again, so a factory "
     "returning one instance hands two requests the same bindings"),
    ("G28h", "src/engcore/inference/calibration.py::CalibrationSpec.__post_init__",
     "        object.__setattr__(self, \"fixed\", freeze(dict(fixed)))\n",
     "        object.__setattr__(self, \"fixed\", dict(fixed))\n",
     "a calibration record's held-fixed inputs can be rewritten through a "
     "caller alias after the run"),

    # ---- main audit round (2026-09-15): GUARDS 29-35 --------------------------
    # GUARD 29 (sria): the evidence-to-belief chain: assessments bound to the record and to a trusted critic registry, obligations bound to the charter, check ownership, one decision per record, gateway history, derived obligation state, persisted-state derivation, claim binding.
    # GUARD 30 (consensus): consensus and level authority: gate-bound thresholds, execution-bound routes, artifact bytes Forge resolves, issuer-bound strongest levels, scale-relative DC checks, trusted execution coherence.
    # GUARD 31 (results): stored results: silent provenance marked and never laundered, older schemas carrying newer keys refused, required keys, validity coverage of declared conditions, evaluation status, truthful declaration flags.
    # GUARD 32 (inference): inference applicability: collapsed grids refused before any waiver, weights bound to the likelihood, held-out applicability, declared sigma, content-bound posteriors, coverage containment, split digests, bounds, identifiability thresholds.
    # GUARD 33 (hybrid): Hybrid UQ: minimum multistart, grid predictive judgement, unit-invariant log widths, grid and rebuild binding, diagonal probes, saddles, read-side re-derivation, probe coverage, closed records.
    # GUARD 34 (domains): domain claims: CSTR liquid envelope, declared battery pulse, self-heating resistance variation, the flagship example's cited part, the Debye floor's conductor assertion, refused coupling reporting.
    # GUARD 35: CERT-02, the thin-ridge (RIDGE-1..8) and Core V2 (HD-1..10) side
    # matrices, which ran once and were never re-run, folded into the certified population.
    ('G29a', 'src/engcore/sria/assurance/arbiter.py',
     '        subjects = self._recorded.get(digest)\n',
     '        subjects = self._recorded.get(digest) or {subject_key}\n',
     'SRIA-TRUST-01 (SRIA-T01-unrecorded-assessment-counts) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29b', 'src/engcore/sria/assurance/arbiter.py',
     '        if subject_key not in subjects:\n',
     '        if False:\n',
     'SRIA-TRUST-01 (SRIA-T01-recorded-for-other-subject-counts) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29c', 'src/engcore/sria/assurance/arbiter.py',
     '            if not bound:\n',
     '            if False:\n',
     'SRIA-TRUST-01 (SRIA-T01-structural-binding-removed) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29d', 'src/engcore/sria/assurance/arbiter.py',
     '        if refused:\n            return AssuranceVerdict.INCONCLUSIVE\n',
     '        if False:\n            return AssuranceVerdict.INCONCLUSIVE\n',
     'SRIA-TRUST-01 (SRIA-T01-refused-assessment-allows-valid) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29e', 'src/engcore/sria/assurance/arbiter.py',
     '            if evidence is None or not budget_describes_claim(budget, evidence):\n',
     '            if evidence is None:\n',
     'SRIA-TRUST-01 (SRIA-T01-budget-quantity-unchecked) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29f', 'src/engcore/sria/assurance/arbiter.py',
     '        if mismatches:\n',
     '        if False:\n',
     'SRIA-TRUST-01 (SRIA-T01-misattributed-critic-output-recorded) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29g', 'src/engcore/sria/campaign/runner.py',
     '        if obligations.campaign_id != charter.campaign_id:\n',
     '        if False:\n',
     'SRIA-TRUST-02 (SRIA-T02-runner-campaign-id-unchecked) -- tests/test_audit_sria_policy_binding.py'),
    ('G29h', 'src/engcore/sria/campaign/runner.py',
     '        if obligations.charter_digest != charter.digest:\n',
     '        if False:\n',
     'SRIA-TRUST-02 (SRIA-T02-runner-charter-digest-unchecked) -- tests/test_audit_sria_policy_binding.py'),
    ('G29i', 'src/engcore/sria/campaign/runner.py',
     '        elif str(charter_version) != derived_version:\n',
     '        elif False:\n',
     'SRIA-TRUST-02 (SRIA-T02-charter-version-free-string) -- tests/test_audit_sria_policy_binding.py'),
    ('G29j', 'src/engcore/sria/assurance/arbiter.py',
     '            policy_digest=obligations.digest,\n',
     '            policy_digest="",\n',
     'SRIA-TRUST-02 (SRIA-T02-decision-omits-policy-digest) -- tests/test_audit_sria_policy_binding.py'),
    ('G29k', 'src/engcore/sria/assurance/arbiter.py',
     '        return f"{self._version}#policy={decision.policy_digest}"\n',
     '        return self._version\n',
     'SRIA-TRUST-02 (SRIA-T02-authorization-policy-version-omits-digest) -- tests/test_audit_sria_policy_binding.py'),
    ('G29l', 'src/engcore/sria/campaign/stopping.py',
     '        if proposal.campaign_id != obligations.campaign_id:\n',
     '        if False:\n',
     'SRIA-TRUST-02 (SRIA-T02-stop-review-borrows-another-campaigns-policy) -- tests/test_audit_sria_policy_binding.py'),
    ('G29m', 'src/engcore/sria/assurance/arbiter.py',
     '            not_passing = [a for a in of_class if a.verdict is not CriticVerdict.PASS]\n',
     '            not_passing = [a for a in of_class[-1:] if a.verdict is not CriticVerdict.PASS]\n',
     'SRIA-TRUST-03 (SRIA-T03-required-critic-last-wins) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29n', 'src/engcore/sria/assurance/arbiter.py',
     '        if len(found) > 1:\n            return "ambiguous", None, refs\n        return "found", found[0][1], refs\n',
     '        return "found", found[-1][1], refs\n',
     'SRIA-TRUST-03 (SRIA-T03-duplicate-check-last-wins) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29o', 'src/engcore/sria/assurance/arbiter.py',
     '        domain_scope = [a for a in counted if a.critic_class is CriticClass.DOMAIN]\n',
     '        domain_scope = list(counted)\n',
     'SRIA-TRUST-03 (SRIA-T03-domain-check-resolved-across-classes) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29p', 'src/engcore/sria/assurance/arbiter.py',
     '                and assessment.domain_pack_ref != evidence.domain_pack_ref\n',
     '                and False\n',
     'SRIA-TRUST-03 (SRIA-T03-domain-pack-unchecked) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29q', 'src/engcore/sria/assurance/arbiter.py',
     '            decision.subject_kind == SUBJECT_EVIDENCE\n            and decision.subject_ref == record_hash\n',
     '            decision.subject_ref in (record_hash, evidence.evidence_id)\n',
     'SRIA-TRUST-04 (SRIA-T04-authorize-accepts-evidence-id-or-reference) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29r', 'src/engcore/sria/assurance/arbiter.py',
     '        if decision.decision_hash in self._authorized:\n',
     '        if False:\n',
     'SRIA-TRUST-04 (SRIA-T04-decision-authorizes-repeatedly) -- tests/test_audit_sria_assurance_binding.py'),
    ('G29s', 'src/engcore/sria/gateway.py',
     '        if current is not None and current.record_hash != entry.record_hash:\n',
     '        if False:\n',
     'SRIA-05 (SRIA-05-belief-id-overwritten-by-other-record) -- tests/test_audit_sria_gateway_history.py'),
    ('G29t', 'src/engcore/sria/gateway.py',
     '        if current is not None and current.status in _TERMINAL_STANDING:\n',
     '        if False:\n',
     'SRIA-05 (SRIA-05-terminal-standing-readmitted) -- tests/test_audit_sria_gateway_history.py'),
    ('G29u', 'src/engcore/sria/gateway.py',
     '        self._history.append(entry)\n',
     '        pass\n',
     'SRIA-05 (SRIA-05-history-not-kept) -- tests/test_audit_sria_gateway_history.py'),
    ('G29v', 'src/engcore/sria/campaign/runner.py',
     '        self._obligation_state = derive_obligation_state(self._events)\n\n        assessed = evidence\n',
     '        self._obligation_state = derive_obligation_state(self._events)\n        self._obligation_state.update(bundle.obligation_state)\n\n        assessed = evidence\n',
     'SRIA-06 (SRIA-06-harness-satisfaction-merged) -- tests/test_audit_sria_obligation_state.py'),
    ('G29w', 'src/engcore/sria/campaign/runner.py',
     '            if not self._arbiter.issued(decision):\n',
     '            if False:\n',
     'SRIA-06 (SRIA-06-adopt-accepts-foreign-decision) -- tests/test_audit_sria_obligation_state.py'),
    ('G29x', 'src/engcore/sria/campaign/runner.py',
     '            if decision.policy_digest != policy:\n',
     '            if False:\n',
     'SRIA-06 (SRIA-06-adopt-accepts-other-policy) -- tests/test_audit_sria_obligation_state.py'),
    ('G29y', 'src/engcore/sria/campaign/runner.py',
     '        self._require_derivable_assurance(checkpoint)\n        self._run = checkpoint.run\n        self._events = CampaignEventLog(',
     '        self._run = checkpoint.run\n        self._events = CampaignEventLog(',
     'SRIA-06 (SRIA-06-restore-adopts-unbacked-state) -- tests/test_audit_sria_obligation_state.py'),
    ('G29z', 'src/engcore/sria/campaign/events.py',
     '    if stored_state != derived_state:\n',
     '    if False:\n',
     'SER-01 (SER-01-materialize-trusts-stored-obligation-state) -- tests/test_audit_sria_persistence_derivation.py'),
    ('G29aa', 'src/engcore/sria/campaign/events.py',
     '        if stored != expected:\n',
     '        if False:\n',
     'SER-01 (SER-01-materialize-trusts-stored-iteration-records) -- tests/test_audit_sria_persistence_derivation.py'),
    ('G29ab', 'src/engcore/sria/campaign/persistence.py',
     '        if problems:\n            raise PersistenceIntegrityError(\n',
     '        if False:\n            raise PersistenceIntegrityError(\n',
     'SER-01 (SER-01-materialize-ignores-disagreement) -- tests/test_audit_sria_persistence_derivation.py'),
    ('G29ac', 'src/engcore/sria/campaign/persistence.py',
     '            if not allow_legacy_migration:\n',
     '            if False:\n',
     'SER-01 (SER-01-legacy-file-migrated-implicitly) -- tests/test_audit_sria_persistence_derivation.py'),
    ('G29ad', 'src/engcore/sria/calibration/critic.py',
     '        coverage_ok = False\n        if coverage is None:\n',
     '        coverage_ok = True\n        if coverage is None:\n',
     'INF-11 (INF-11-missing-coverage-passes) -- tests/test_audit_sria_cost_critic.py'),
    ('G29ae', 'src/engcore/sria/calibration/critic.py',
     '        censoring_blocks_trust = True\n',
     '        censoring_blocks_trust = False\n',
     'INF-11 (INF-11-unknown-censoring-passes) -- tests/test_audit_sria_cost_critic.py'),
    ('G29af', 'src/engcore/sria/calibration/critic.py',
     '        if censored_fraction is None and training_provenance and (\n            "observed_costs_used" in training_provenance\n            or "censored_excluded" in training_provenance\n        ):\n            used = float(training_provenance.get("observed_costs_used", 0) or 0)\n            excluded = float(training_provenance.get("censored_excluded", 0) or 0)\n            total = used + excluded\n            censored_fraction = (excluded / total) if total else None\n',
     '        if censored_fraction is None and training_provenance:\n            used = float(training_provenance.get("observed_costs_used", 0) or 0)\n            excluded = float(training_provenance.get("censored_excluded", 0) or 0)\n            total = used + excluded\n            censored_fraction = (excluded / total) if total else 0.0\n',
     'INF-11 (INF-11-countless-provenance-reads-as-uncensored) -- tests/test_audit_sria_cost_critic.py'),
    ('G29ag', 'src/engcore/sria/admission.py',
     '        if binding.critic_registry_digest != self._critic_registry_digest or not (\n            self._critic_registry_digest\n        ):\n',
     '        if False:\n',
     'SRIA-TRUST-01 follow-up (trust root) (SRIA-ROOT-foreign-registry-authorizes) -- tests/test_audit_sria_trust_root.py'),
    ('G29ah', 'src/engcore/sria/admission.py',
     '        if binding.policy_digest not in self._policy_digests:\n',
     '        if False:\n',
     'SRIA-TRUST-02 follow-up (trust root) (SRIA-ROOT-undeclared-policy-authorizes) -- tests/test_audit_sria_trust_root.py'),
    ('G29ai', 'src/engcore/sria/admission.py',
     '    if authority._bound_registrar is not None:\n',
     '    if False:\n',
     'SRIA-TRUST-01 follow-up (trust root) (SRIA-ROOT-second-arbiter-allowed) -- tests/test_audit_sria_trust_root.py'),
    ('G29aj', 'src/engcore/sria/assurance/arbiter.py',
     '        implementation=f"{type(critic).__module__}.{type(critic).__qualname__}",\n',
     '        implementation="",\n',
     'SRIA-TRUST-01 follow-up (trust root) (SRIA-ROOT-registry-digest-ignores-implementation) -- tests/test_audit_sria_trust_root.py'),
    ('G29ak', 'src/engcore/sria/campaign/stopping.py',
     '            decision = self._arbiter.issued_decision(decision_hash)\n',
     '            decision = self._arbiter.issued_decision(decision_hash) or (\n                item if isinstance(item, ArbiterDecision) else None\n            )\n',
     'SRIA-06 follow-up (stop review grounds) (SRIA-GROUNDS-caller-decision-object-counts) -- tests/test_audit_sria_stop_review_grounds.py'),
    ('G29al', 'src/engcore/sria/campaign/stopping.py',
     '                or decision.policy_digest != obligations.digest\n',
     '',
     'SRIA-06 follow-up (stop review grounds) (SRIA-GROUNDS-other-policy-counts) -- tests/test_audit_sria_stop_review_grounds.py'),
    ('G29am', 'src/engcore/sria/campaign/stopping.py',
     '            if str(obligation_id) in declared:\n                state[str(obligation_id)] = False\n',
     '            if str(obligation_id) in declared:\n                pass\n',
     'SRIA-06 follow-up (stop review grounds) (SRIA-GROUNDS-reported-unmet-ignored) -- tests/test_audit_sria_stop_review_grounds.py'),
    ('G29an', 'src/engcore/sria/assurance/arbiter.py',
     '    if not backed:\n',
     '    if False:\n',
     'SRIA-TRUST-01 follow-up (claim binding) (SRIA-CLAIM-value-mismatch-counts) -- tests/test_audit_sria_claim_binding.py'),
    ('G29ao', 'src/engcore/sria/assurance/arbiter.py',
     '        return f"the assessed result holds no quantity {name!r}"\n',
     '        return ""\n',
     'SRIA-TRUST-01 follow-up (claim binding) (SRIA-CLAIM-absent-quantity-counts) -- tests/test_audit_sria_claim_binding.py'),
    ('G29ap', 'src/engcore/sria/assurance/arbiter.py',
     '        if assessed is not None:\n            self._assessed_results[digest] = assessed\n',
     '',
     'SRIA-TRUST-01 follow-up (claim binding) (SRIA-CLAIM-assessed-result-not-recorded) -- tests/test_audit_sria_claim_binding.py'),
    ('G29aq', 'src/engcore/sria/assurance/arbiter.py',
     '                != _declaration_digest(evidence.uncertainty)\n',
     '                != _declaration_digest(budget.declaration)\n',
     'SRIA-TRUST-01 follow-up (claim binding) (SRIA-CLAIM-budget-declaration-unchecked) -- tests/test_audit_sria_claim_binding.py'),
    ('G30a', 'src/engcore/scientific/consensus.py',
     '            and self.comparison.agreed\n            and self.threshold_authority_gap is None\n',
     '            and self.comparison.agreed\n',
     'CONS-01 (CONS-01a) -- tests/test_audit_consensus_threshold_authority.py'),
    ('G30b', 'src/engcore/scientific/consensus.py',
     '        if gate != thresholds.gate_id or key != tolerance_key:',
     '        if gate != thresholds.gate_id:',
     'CONS-01 (CONS-01b) -- tests/test_audit_consensus_threshold_authority.py'),
    ('G30c', 'src/engcore/scientific/consensus.py',
     '    if {d.value: frozenset(n) for d, n in route.dependencies.identities.items()} != listed:',
     '    if False:',
     'IND-05 (IND-05a) -- tests/test_audit_consensus_resolution_and_floor.py'),
    ('G30d', 'src/engcore/scientific/consensus.py',
     '                difference = _floored_difference(first, second, tolerance, floor)',
     '                difference = relative_difference(first, second)',
     'NUM-03 (NUM-03a) -- tests/test_audit_consensus_resolution_and_floor.py'),
    ('G30e', 'src/engcore/scientific/consensus.py',
     '            and self.execution_binding_gap is None\n',
     '',
     'IND-02 (IND-02a) -- tests/test_audit_consensus_execution_binding.py'),
    ('G30f', 'src/engcore/scientific/consensus.py',
     '            if not isinstance(result, ScientificResult):\n',
     '            if False:\n',
     'IND-02 (IND-02b) -- tests/test_audit_consensus_execution_binding.py'),
    ('G30g', 'src/engcore/scientific/consensus.py',
     '        for label, kind in (("result_id", "result"), ("run_id", "run")):',
     '        for label, kind in (("result_id", "result"),):',
     'IND-02 (IND-02c) -- tests/test_audit_consensus_execution_binding.py'),
    ('G30h', 'src/engcore/scientific/consensus.py',
     '            if produced is None or _values_digest(produced) != binding["values_digest"]:',
     '            if produced is None:',
     'IND-02 (IND-02d) -- tests/test_audit_consensus_execution_binding.py'),
    ('G30i', 'src/engcore/scientific/consensus.py',
     '            if (solver["solver_id"], solver["version"], solver["backend"]) != (',
     '            if False and (solver["solver_id"], solver["version"], solver["backend"]) != (',
     'IND-02 (IND-02e) -- tests/test_audit_consensus_execution_binding.py'),
    ('G30j', 'src/engcore/scientific/consensus.py',
     '            if result.solver is not None and (\n',
     '            if False and (\n',
     'IND-02 (IND-02f) -- tests/test_audit_consensus_execution_binding.py'),
    ('G30k', 'src/engcore/scientific/independence_evidence.py',
     '                    if not _authoritative_bytes(\n',
     '                    if False and not _authoritative_bytes(\n',
     'IND-03 (IND-03a) -- tests/test_audit_consensus_artifact_authority.py'),
    ('G30l', 'src/engcore/scientific/independence_evidence.py',
     '        if expected != artifact.digest:\n',
     '        if False:\n',
     'IND-03 (IND-03b) -- tests/test_audit_consensus_artifact_authority.py'),
    ('G30m', 'src/engcore/scientific/independence_evidence.py',
     '    if artifact.digest not in _pinned_artifact_digests(route_id, identity):\n',
     '    if False:\n',
     'IND-03 (IND-03c) -- tests/test_audit_consensus_artifact_authority.py'),
    ('G30n', 'src/engcore/domains/kinetics/cstr/validation.py',
     '                # independent evidence, and it is not a closed form.\n                establishes=None,',
     '                establishes=self.thresholds.award(ValidationLevel.CROSS_SOLVER_VALIDATED, earned=self.steady_state_verified),',
     'IND-04 (IND-04a) -- tests/domains/kinetics/test_audit_consensus_cstr_levels.py'),
    ('G30o', 'src/engcore/domains/kinetics/cstr/validation.py',
     '            # check and establishes nothing. See the module docstring.\n        )',
     '            self.thresholds.award(ValidationLevel.CROSS_SOLVER_VALIDATED, earned=self.steady_state_verified),\n        )',
     'IND-04 (IND-04b) -- tests/domains/kinetics/test_audit_consensus_cstr_levels.py'),
    ('G30p', 'src/engcore/domains/kinetics/cstr/validation.py',
     '    if comparison.agreed:\n        return (',
     '    if True:\n        return (',
     'IND-06 (IND-06a) -- tests/domains/kinetics/test_audit_consensus_cstr_levels.py'),
    ('G30q', 'src/engcore/domains/kinetics/cstr/validation.py',
     '    if not comparison.compared_anything:\n        return (\n            f"{method} and {cross_method} at {rung_label}: no comparison',
     '    if False:\n        return (\n            f"{method} and {cross_method} at {rung_label}: no comparison',
     'IND-06 (IND-06b) -- tests/domains/kinetics/test_audit_consensus_cstr_levels.py'),
    ('G30r', 'src/engcore/domains/electrical/dc/validation.py',
     '    floor = settings.kcl_atol_ampere * current_scale\n',
     '    floor = settings.kcl_atol_ampere\n',
     'NUM-01 (NUM-01a) -- tests/domains/electrical/test_audit_consensus_dc_scale.py'),
    ('G30s', 'src/engcore/domains/electrical/dc/validation.py',
     '        floor = thresholds["residual_atol"] * float(np.max(row_scale[start:stop]))\n',
     '        floor = thresholds["residual_atol"]\n',
     'NUM-01 (NUM-01b) -- tests/domains/electrical/test_audit_consensus_dc_scale.py'),
    ('G30t', 'src/engcore/domains/electrical/dc/validation.py',
     '        settings.power_atol_watt * power_scale + settings.residual_rtol * magnitude\n',
     '        settings.power_atol_watt + settings.residual_rtol * magnitude\n',
     'NUM-01 (NUM-01c) -- tests/domains/electrical/test_audit_consensus_dc_scale.py'),
    ('G30u', 'src/engcore/domains/electrical/dc/validation.py',
     '    floor = settings.source_atol_volt * voltage_scale\n',
     '    floor = settings.source_atol_volt\n',
     'NUM-01 (NUM-01d) -- tests/domains/electrical/test_audit_consensus_dc_scale.py'),
    ('G30v', 'src/engcore/domains/electrical/ngspice.py',
     '        current_floor = voltage_floor / abs(ohms)\n',
     '        current_floor = voltage_floor\n',
     'NUM-02 (NUM-02a) -- tests/domains/electrical/test_audit_consensus_dc_scale.py'),
    ('G30w', 'src/engcore/domains/electrical/ngspice.py',
     '        power_floor = voltage_floor * (abs(current) + abs(v_drop) / abs(ohms))\n',
     '        power_floor = voltage_floor\n',
     'NUM-02 (NUM-02b) -- tests/domains/electrical/test_audit_consensus_dc_scale.py'),
    ('G30x', 'src/engcore/scientific/results/validation.py',
     '        issuer_gap = _issuer_gap(\n            self.establishes, self.outcome, self.residual, self.tolerance, self.evidence\n        )\n',
     '        issuer_gap = None\n',
     'VAL-01 (VAL-01a) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30y', 'src/engcore/scientific/results/validation.py',
     '        self._require_every_strong_level_issued()\n        return frozenset(',
     '        return frozenset(',
     'VAL-01 (VAL-01b) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30z', 'src/engcore/scientific/results/validation.py',
     '    if residual is None or tolerance is None or float(tolerance) != thresholds[key]:',
     '    if residual is None or tolerance is None:',
     'VAL-01 (VAL-01c) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30aa', 'src/engcore/scientific/results/validation.py',
     '    if not thresholds.is_declared:\n',
     '    if False:\n',
     'VAL-01 (VAL-01d) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30ab', 'src/engcore/scientific/results/validation.py',
     '    if oracles._LEVEL_BY_KIND.get(kind) is not level:\n',
     '    if False:\n',
     'VAL-01 (VAL-01e) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30ac', 'src/engcore/scientific/results/validation.py',
     '    if len(set(results)) != len(results) or len(set(runs)) != len(runs):\n',
     '    if False:\n',
     'VAL-01 (VAL-01f) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30ad', 'src/engcore/scientific/results/validation.py',
     '        if not isinstance(pin, Mapping) or (\n            pin.get("threshold_gate_id"), pin.get("tolerance_key")\n        ) != (thresholds.gate_id, key):\n',
     '        if not isinstance(pin, Mapping):\n',
     'VAL-01 (VAL-01g) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30ae', 'src/engcore/scientific/results/validation.py',
     '        if "status" in payload and payload.get("status") != report.status.value:\n',
     '        if False:\n',
     'RES-08 (RES-08a) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30af', 'src/engcore/scientific/results/validation.py',
     '        if "attained_levels" in payload:\n',
     '        if payload.get("attained_levels"):\n',
     'RES-08 (RES-08b) -- tests/test_audit_consensus_level_issuers.py'),
    ('G30ag', 'src/engcore/execution/trusted.py',
     '        self._require_one_execution()\n',
     '',
     'RES-07 (RES-07a) -- tests/test_audit_consensus_trusted_record.py'),
    ('G30ah', 'src/engcore/execution/trusted.py',
     '        if mismatched:\n            raise ScientificCoreError(\n                f"trusted execution manifest does not attest',
     '        if False:\n            raise ScientificCoreError(\n                f"trusted execution manifest does not attest',
     'RES-07 (RES-07b) -- tests/test_audit_consensus_trusted_record.py'),
    ('G30ai', 'src/engcore/execution/trusted.py',
     '        return usable and self.validation.status is not ValidationOutcome.FAIL\n',
     '        return True\n',
     'RES-07 (RES-07c) -- tests/test_audit_consensus_trusted_record.py'),
    ('G31a', 'src/engcore/scientific/results/result.py',
     '        object.__setattr__(self, _ATTRIBUTION_GAP_ATTRIBUTE, (*existing, gap))',
     '        return',
     'RES-01 (results-RES01c-gap-never-recorded) -- tests/test_audit_results_stored_results.py'),
    ('G31b', 'src/engcore/mcp/evidence.py',
     '            + _attribution_gap_checks(result)\n',
     '',
     'RES-01 (results-RES01d-report-launders-gap) -- tests/test_audit_results_stored_results.py'),
    ('G31c', 'src/engcore/scientific/results/result.py',
     '        if stored and missing_models and not self.provenance.models:\n            self._record_attribution_gap(',
     '        if stored and missing_models and not self.provenance.models:\n            (lambda *_: None)(',
     'RES-01 (results-RES01f-model-gap-not-marked) -- tests/test_audit_results_stored_results.py'),
    ('G31d', 'src/engcore/scientific/results/result.py',
     '        if solver_key not in set(self.provenance.solvers) and stored and not self.provenance.solvers:\n            self._record_attribution_gap(',
     '        if solver_key not in set(self.provenance.solvers) and stored and not self.provenance.solvers:\n            (lambda *_: None)(',
     'RES-01 (results-RES01g-solver-gap-not-marked) -- tests/test_audit_results_stored_results.py'),
    ('G31e', 'src/engcore/scientific/results/result.py',
     '        if stored and missing_models and not self.provenance.models:',
     '        if stored and missing_models:',
     'RES-01 (results-RES01h-contradiction-exempted) -- tests/test_audit_results_stored_results.py'),
    ('G31f', 'src/engcore/scientific/results/result.py',
     '        if key in payload and not written_by_declared:',
     '        if False:',
     'RES-02 (results-RES02a-result-relabel-drops-content) -- tests/test_audit_results_stored_results.py'),
    ('G31g', 'src/engcore/scientific/results/result.py',
     '        if key not in payload and written_by_declared:',
     '        if False:',
     'RES-02 (results-RES02b-result-required-key-absent) -- tests/test_audit_results_stored_results.py'),
    ('G31h', 'src/engcore/scientific/results/provenance.py',
     '        if key in payload and not written_by_declared:',
     '        if False:',
     'RES-02 (results-RES02c-provenance-relabel-drops-bindings) -- tests/test_audit_results_stored_results.py'),
    ('G31i', 'src/engcore/scientific/results/provenance.py',
     '        if key not in payload and written_by_declared:',
     '        if False:',
     'RES-02 (results-RES02d-provenance-bindings-key-deleted) -- tests/test_audit_results_stored_results.py'),
    ('G31j', 'src/engcore/scientific/results/provenance.py',
     '            if typed:',
     '            if False:',
     'RES-02 (results-RES02e-provenance-typed-input-relabelled) -- tests/test_audit_results_stored_results.py'),
    ('G31k', 'src/engcore/scientific/results/result.py',
     '        if payload.get(key) is None:',
     '        if False:',
     'RES-05 (results-RES05a-missing-convergence-validation) -- tests/test_audit_results_stored_results.py'),
    ('G31l', 'src/engcore/mcp/evidence.py',
     '        self._require_conditions_of_the_declared_model(assessment)\n',
     '',
     'RES-04 (results-RES04a-condition-binding-skipped) -- tests/mcp/test_audit_results_validity_binding.py'),
    ('G31m', 'src/engcore/mcp/evidence.py',
     '        if stray or missing:',
     '        if False:',
     'RES-04 (results-RES04b-omitted-conditions-accepted) -- tests/mcp/test_audit_results_validity_binding.py'),
    ('G31n', 'src/engcore/mcp/evidence.py',
     '        if repeated:',
     '        if False:',
     'RES-04 (results-RES04c-condition-in-two-lists) -- tests/mcp/test_audit_results_validity_binding.py'),
    ('G31o', 'src/engcore/mcp/evidence.py',
     '    if unresolved_models:\n        return CredibilityVerdict.INSUFFICIENT_EVIDENCE\n',
     '',
     'RES-04 (results-RES04d-unresolved-model-supported) -- tests/mcp/test_audit_results_validity_binding.py'),
    ('G31p', 'src/engcore/scientific/experiments/evaluation.py',
     '        if not result.is_usable:',
     '        if False:',
     'RES-06 (results-RES06a-ok-over-unusable) -- tests/test_audit_results_evaluation.py'),
    ('G31q', 'src/engcore/scientific/experiments/evaluation.py',
     '        if outside:',
     '        if False:',
     'RES-06 (results-RES06b-ok-over-outside-domain) -- tests/test_audit_results_evaluation.py'),
    ('G31r', 'src/engcore/scientific/experiments/evaluation.py',
     '            if not math.isclose(',
     '            if False and not math.isclose(',
     'RES-06 (results-RES06c-objective-disagrees) -- tests/test_audit_results_evaluation.py'),
    ('G31s', 'src/engcore/scientific/experiments/evaluation.py',
     '            self._require_a_result_that_supports_ok(evaluation_id, objectives)',
     '            pass',
     'RES-06 (results-RES06d-ok-check-skipped-on-read) -- tests/test_audit_results_evaluation.py'),
    ('G31t', 'src/engcore/mcp/battery.py',
     '                description="caller-declared cell limits",\n                consumed_by_verdict=True,\n',
     '                description="caller-declared cell limits",\n',
     'CAP-04 (results-CAP04a-battery-flag-unstated) -- tests/mcp/test_audit_results_declarations.py'),
    ('G31u', 'src/engcore/mcp/problem.py',
     '                        consumed_by_verdict=True,\n',
     '',
     'CAP-04 (results-CAP04b-electrothermal-flag-unstated) -- tests/mcp/test_audit_results_declarations.py'),
    ('G31v', 'src/engcore/mcp/evidence.py',
     '            "consumed_by_verdict": self.consumed_by_verdict,',
     '            "consumed_by_verdict": False,',
     'CAP-04 (results-CAP04c-literal-false-on-wire) -- tests/mcp/test_audit_results_declarations.py'),
    ('G31w', 'src/engcore/mcp/evidence.py',
     '                None\n                if version == ASSERTED_CONTEXT_SCHEMA_V1\n                else payload.get("consumed_by_verdict")',
     '                payload.get("consumed_by_verdict")',
     'CAP-04 (results-CAP04d-v1-false-believed) -- tests/mcp/test_audit_results_declarations.py'),
    ('G31x', 'src/engcore/mcp/evidence.py',
     '        if "verdict" not in payload:\n            raise CredibilityEvidenceError(\n                "serialized report carries no verdict; every writer of "\n                f"{EVIDENCE_PACKAGE_SCHEMA} emits the derived verdict beside "\n                "the contents, and a report with it removed cannot be checked "\n                "against them"\n            )\n        declared = payload.get("verdict")\n        if declared != report.verdict.value:',
     '        declared = payload.get("verdict")\n        if declared is not None and declared != report.verdict.value:',
     'RES-08 (results-RES08a-verdict-optional-again) -- tests/mcp/test_audit_results_declarations.py'),
    ('G31y', 'src/engcore/mcp/evidence.py',
     '        if stated is not None:\n            _require_qualifiers_as_derived(stated, report)\n',
     '',
     'RES-08 (results-RES08b-qualifiers-not-read-back) -- tests/mcp/test_audit_results_declarations.py'),
    ('G31z', 'src/engcore/mcp/evidence.py',
     '        if value != derived[name]:',
     '        if False:',
     'RES-08 (results-RES08c-qualifier-mismatch-accepted) -- tests/mcp/test_audit_results_declarations.py'),
    ('G32a', 'src/engcore/inference/calibration.py',
     '    ess = posterior_effective_sample_size(posterior)\n    if ess < p + 1:\n',
     '    ess = posterior_effective_sample_size(posterior)\n    if False:\n',
     'INF-04 (INF-04-ess-before-discrete-waiver) -- tests/inference/test_audit_inference_grid_resolution.py'),
    ('G32b', 'src/engcore/inference/grid.py',
     '    if not deviation <= _WEIGHT_LIKELIHOOD_TOLERANCE:\n',
     '    if False:\n',
     'HUQ-04 (grid part) (HUQ-04-weights-bound-to-log-likelihood) -- tests/inference/test_audit_inference_posterior_binding.py'),
    ('G32c', 'src/engcore/inference/grid.py',
     '    if stray > 0.0:\n',
     '    if False:\n',
     'HUQ-04 (grid part) (HUQ-04-no-mass-off-support) -- tests/inference/test_audit_inference_posterior_binding.py'),
    ('G32d', 'src/engcore/uq/admission.py',
     '        conditioned_log_likelihood[rejected] = -np.inf\n',
     '        pass\n',
     'HUQ-04 (grid part) (HUQ-04-conditioned-likelihood-states-conditioning) -- tests/inference/test_audit_inference_posterior_binding.py'),
    ('G32e', 'src/engcore/studies/calibration_study.py',
     '    if problems:\n        raise InferenceAdmissibilityError(\n',
     '    if False:\n        raise InferenceAdmissibilityError(\n',
     'INF-01 (INF-01-applicability-at-declared-conditions) -- tests/inference/test_audit_inference_heldout_study.py'),
    ('G32f', 'src/engcore/studies/calibration_study.py',
     '        if not math.isclose(given, declared, rel_tol=1.0e-12, abs_tol=0.0):\n',
     '        if False:\n',
     'INF-02 (INF-02-declared-sigma-only) -- tests/inference/test_audit_inference_heldout_study.py'),
    ('G32g', 'src/engcore/inference/split.py',
     '    if not same_support or not np.allclose(\n',
     '    if False and not same_support or False and not np.allclose(\n',
     'INF-03 (INF-03-posterior-content-bound-to-calibration-half) -- tests/inference/test_audit_inference_heldout_study.py'),
    ('G32h', 'src/engcore/studies/calibration_study.py',
     '    if band_low <= low and high <= band_high:\n',
     '    if True:\n',
     'INF-05 (INF-05-calibrated-only-when-contained) -- tests/inference/test_audit_inference_heldout_study.py'),
    ('G32i', 'src/engcore/studies/calibration_study.py',
     '    if total <= 0:\n        raise ValueError(\n',
     '    if False:\n        raise ValueError(\n',
     'INF-05 (INF-05-no-intervals-refused) -- tests/inference/test_audit_inference_heldout_study.py'),
    ('G32j', 'src/engcore/studies/tcr.py',
     '    for r_ref, alpha in points:\n        parameters.require_all_in_bounds({\n',
     '    for r_ref, alpha in []:\n        parameters.require_all_in_bounds({\n',
     'INF-08 (INF-08-tcr-table-rows-within-declared-bounds) -- tests/inference/test_audit_inference_heldout_study.py'),
    ('G32k', 'src/engcore/inference/split.py',
     '    unit = base_unit(observation.value.units)\n',
     '    unit = observation.value.units\n',
     'INF-06 (INF-06-digest-in-base-unit) -- tests/inference/test_audit_inference_split_guards.py'),
    ('G32l', 'src/engcore/inference/split.py',
     '    text = f"{float(value) + 0.0:.12g}"\n',
     '    text = repr(float(value) + 0.0)\n',
     'INF-06 (INF-06-digest-rounds-away-ulps) -- tests/inference/test_audit_inference_split_guards.py'),
    ('G32m', 'src/engcore/inference/split.py',
     '        if shared_conditions:\n',
     '        if False:\n',
     'INF-06 (INF-06-shared-condition-refused) -- tests/inference/test_audit_inference_split_guards.py'),
    ('G32n', 'src/engcore/adequacy/predictive.py',
     '    if str(heldout_dataset_id).strip() == str(posterior.dataset_id).strip():\n',
     '    if False:\n',
     'INF-07 (INF-07-heldout-is-not-posterior-dataset) -- tests/inference/test_audit_inference_split_guards.py'),
    ('G32o', 'src/engcore/inference/calibration.py',
     '        if looser:\n',
     '        if False:\n',
     'INF-10 (INF-10-thresholds-cannot-be-loosened) -- tests/inference/test_audit_inference_identifiability.py'),
    ('G32p', 'src/engcore/inference/calibration.py',
     '        if not math.isfinite(value) or value <= 0.0:\n',
     '        if False:\n',
     'INF-10 (INF-10-thresholds-must-be-meaningful) -- tests/inference/test_audit_inference_identifiability.py'),
    ('G32q', 'src/engcore/inference/parameters.py',
     '        if not is_ratio_scale(self.unit):\n',
     '        if False:\n',
     'NUM-04 (NUM-04-no-offset-scale-parameters) -- tests/inference/test_audit_inference_identifiability.py'),
    ('G32r', 'src/engcore/domains/battery/empirical.py',
     '    if applicability_status is not None and not isinstance(applicability_status, ValidityAssessment):\n',
     '    if False:\n',
     'INF-09 (INF-09-applicability-is-a-validity-assessment) -- tests/domains/battery/test_audit_inference_ocv_applicability.py'),
    ('G32s', 'src/engcore/domains/battery/empirical.py',
     '        if self.applicability_status is not None and self.applicability_status not in _VALIDITY_STATUS_VALUES:\n',
     '        if False:\n',
     'INF-09 (INF-09-record-carries-only-a-validity-status) -- tests/domains/battery/test_audit_inference_ocv_applicability.py'),
    ('G33a', 'src/engcore/hybrid_uq/local_gaussian.py',
     '    if incomplete or below:\n',
     '    if incomplete:\n',
     'HUQ-01 (HYB-HUQ01a) -- tests/hybrid_uq/test_audit_hybrid_local_route.py'),
    ('G33b', 'src/engcore/hybrid_uq/local_gaussian.py',
     '        thresholds.update(_policy_record(multistart, p))\n',
     '        pass\n',
     'HUQ-01 (HYB-HUQ01b) -- tests/hybrid_uq/test_audit_hybrid_local_route.py'),
    ('G33c', 'src/engcore/hybrid_uq/local_gaussian.py',
     '            directions.append((scaled[i] + scaled[j]) / math.sqrt(2.0))\n            directions.append((scaled[i] - scaled[j]) / math.sqrt(2.0))\n',
     '            pass\n',
     'HUQ-08 (HYB-HUQ08a) -- tests/hybrid_uq/test_audit_hybrid_local_route.py'),
    ('G33d', 'src/engcore/hybrid_uq/local_gaussian.py',
     '                elif refit.objective_value < chi_min - lower_tolerance:\n',
     '                elif False:\n',
     'HUQ-08 (HYB-HUQ08b) -- tests/hybrid_uq/test_audit_hybrid_local_route.py'),
    ('G33e', 'src/engcore/hybrid_uq/local_gaussian.py',
     '    if evaluated < p:\n',
     '    if False:\n',
     'HUQ-10 (HYB-HUQ10) -- tests/hybrid_uq/test_audit_hybrid_local_route.py'),
    ('G33f', 'src/engcore/hybrid_uq/predictive.py',
     '    claim = _grid_route_claim(posterior)\n',
     '    claim = RouteClaim.SUPPORTED\n',
     'HUQ-02 (HYB-HUQ02) -- tests/hybrid_uq/test_audit_hybrid_grid_route.py'),
    ('G33g', 'src/engcore/hybrid_uq/predictive.py',
     '    h.update(b"\\x00log_likelihood\\x00" + np.ascontiguousarray(posterior.log_likelihood, dtype="<f8").tobytes())\n',
     '    pass\n',
     'HUQ-04 (HYB-HUQ04a) -- tests/hybrid_uq/test_audit_hybrid_grid_route.py'),
    ('G33h', 'src/engcore/hybrid_uq/predictive.py',
     '    h.update(b"\\x00admissible_mask\\x00" + np.ascontiguousarray(posterior.admissible_mask, dtype=np.uint8).tobytes())\n',
     '    pass\n',
     'HUQ-04 (HYB-HUQ04b) -- tests/hybrid_uq/test_audit_hybrid_grid_route.py'),
    ('G33i', 'src/engcore/hybrid_uq/router.py',
     '        _require_weights_follow_likelihood(grid)\n',
     '        pass\n',
     'HUQ-04 (HYB-HUQ04c) -- tests/hybrid_uq/test_audit_hybrid_grid_route.py'),
    ('G33j', 'src/engcore/hybrid_uq/router.py',
     '    _require_table_agrees_with_forward(table, natural, mesh, np.asarray(local.inference_point), observations, forward)\n',
     '    pass\n',
     'HUQ-05 (HYB-HUQ05) -- tests/hybrid_uq/test_audit_hybrid_grid_route.py'),
    ('G33k', 'src/engcore/hybrid_uq/router.py',
     '    if isinstance(observations, ObservationSet) and str(grid.dataset_id) != str(observations.dataset_id):\n',
     '    if False:\n',
     'HUQ-06 (HYB-HUQ06a) -- tests/hybrid_uq/test_audit_hybrid_grid_route.py'),
    ('G33l', 'src/engcore/hybrid_uq/router.py',
     '        if tuple(grid.parameter_names) != requested:\n',
     '        if False:\n',
     'HUQ-06 (HYB-HUQ06b) -- tests/hybrid_uq/test_audit_hybrid_grid_route.py'),
    ('G33m', 'src/engcore/hybrid_uq/identifiability.py',
     '            if transform == "log":\n',
     '            if False:\n',
     'HUQ-03 (HYB-HUQ03) -- tests/hybrid_uq/test_audit_hybrid_identifiability.py'),
    ('G33n', 'src/engcore/hybrid_uq/identifiability.py',
     '        return digest_of(self.to_dict())\n',
     '        payload = self.to_dict()\n        payload["report"].pop("why")\n        return digest_of(payload)\n',
     'HUQ-14 (HYB-HUQ14) -- tests/hybrid_uq/test_audit_hybrid_identifiability.py'),
    ('G33o', 'src/engcore/hybrid_uq/predictive.py',
     '        directions = _probe_directions(lam, vec)\n',
     '        directions = _probe_directions(lam, vec)[:len(z0)]\n',
     'HUQ-07 (HYB-HUQ07a) -- tests/hybrid_uq/test_audit_hybrid_predictive.py'),
    ('G33p', 'src/engcore/hybrid_uq/predictive.py',
     '                directions.append((cov @ G[i]) / parameter_sd[i])\n',
     '                pass\n',
     'HUQ-07 (HYB-HUQ07b) -- tests/hybrid_uq/test_audit_hybrid_predictive.py'),
    ('G33q', 'src/engcore/hybrid_uq/predictive.py',
     'deviation / np.where(parameter_sd > 0.0, parameter_sd, 1.0)',
     'deviation / np.where(total_sd > 0.0, total_sd, 1.0)',
     'HUQ-11 (HYB-HUQ11) -- tests/hybrid_uq/test_audit_hybrid_predictive.py'),
    ('G33r', 'src/engcore/hybrid_uq/local_gaussian.py',
     '        _require_reasons_follow_measurements(self)\n',
     '        pass\n',
     'HUQ-09 (HYB-HUQ09a) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33s', 'src/engcore/hybrid_uq/router.py',
     '                    problems.extend(_report_differences(ident.report, assess_routed_identifiability(local).report))\n',
     '                    pass\n',
     'HUQ-09 (HYB-HUQ09b) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33t', 'src/engcore/hybrid_uq/router.py',
     '                    problems.extend(_grid_report_problems(ident.report, self.mean, self.covariance))\n',
     '                    pass\n',
     'HUQ-09 (HYB-HUQ09c) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33u', 'src/engcore/hybrid_uq/identifiability.py',
     '        if status is not r.status or not explained:\n',
     '        if False:\n',
     'HUQ-09 (HYB-HUQ09d) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33v', 'src/engcore/hybrid_uq/router.py',
     '            problems.extend(_posterior_record_problems(local))\n',
     '            pass\n',
     'HUQ-09 (HYB-HUQ09e) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33w', 'src/engcore/hybrid_uq/local_gaussian.py',
     '        problems = _posterior_record_problems(posterior)\n',
     '        problems = []\n',
     'HUQ-09 (HYB-HUQ09f) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33x', 'src/engcore/hybrid_uq/local_gaussian.py',
     '        if (math.isinf(rise) or total - skipped < p) and not math.isnan(index):\n',
     '        if False:\n',
     'HUQ-10 (HYB-HUQ10b) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33y', 'src/engcore/hybrid_uq/router.py',
     '            if not all(math.isfinite(v) for v in self.mean):\n',
     '            if False:\n',
     'HUQ-12 (HYB-HUQ12a) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33z', 'src/engcore/hybrid_uq/router.py',
     '            if set(summary) != _GRID_SUMMARY_KEYS:\n',
     '            if False:\n',
     'HUQ-12 (HYB-HUQ12b) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33aa', 'src/engcore/hybrid_uq/router.py',
     '"grid_digest": grid_identity, "dataset_id": dataset_id, "points": points,',
     '"grid_digest": grid_identity,',
     'HUQ-12 (HYB-HUQ12c) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33ab', 'src/engcore/hybrid_uq/predictive.py',
     '                if abs(low - (mean - q * sd)) > tolerance or abs(high - (mean + q * sd)) > tolerance:\n',
     '                if False:\n',
     'HUQ-12 (HYB-HUQ12d) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33ac', 'src/engcore/hybrid_uq/predictive.py',
     '                if (float(nonlinearity) > PREDICTIVE_NONLINEARITY_DOWNGRADE) != (RouteReason.PREDICTIVE_NONLINEAR in self.reasons):\n',
     '                if False:\n',
     'HUQ-12 (HYB-HUQ12e) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33ad', 'src/engcore/hybrid_uq/predictive.py',
     '                if low < mean - reach or high > mean + reach:\n',
     '                if False:\n',
     'HUQ-12 (HYB-HUQ12f) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33ae', 'src/engcore/hybrid_uq/local_gaussian.py',
     '        object.__setattr__(self, "thresholds", freeze({str(k): float(v) for k, v in dict(self.thresholds).items()}))\n',
     '        object.__setattr__(self, "thresholds", {str(k): float(v) for k, v in dict(self.thresholds).items()})\n',
     'HUQ-13 (HYB-HUQ13a) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33af', 'src/engcore/hybrid_uq/router.py',
     '        object.__setattr__(self, "considered", tuple(freeze(dict(c)) for c in self.considered))\n',
     '        object.__setattr__(self, "considered", tuple(dict(c) for c in self.considered))\n',
     'HUQ-13 (HYB-HUQ13b) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33ag', 'src/engcore/hybrid_uq/local_gaussian.py',
     '        object.__setattr__(self, "multistart", tuple(freeze(dict(m)) for m in self.multistart))\n',
     '        object.__setattr__(self, "multistart", tuple(dict(m) for m in self.multistart))\n',
     'HUQ-13 (HYB-HUQ13c) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G33ah', 'src/engcore/hybrid_uq/router.py',
     '            object.__setattr__(self, "grid_summary", freeze(dict(self.grid_summary)))\n',
     '            object.__setattr__(self, "grid_summary", dict(self.grid_summary))\n',
     'HUQ-13 (HYB-HUQ13d) -- tests/hybrid_uq/test_audit_hybrid_records.py'),
    ('G34a', 'src/engcore/domains/kinetics/cstr/problem.py',
     '            *LIQUID_PHASE_CONDITIONS,\n        ),\n        description=(\n            "Well-mixed constant-volume',
     '        ),\n        description=(\n            "Well-mixed constant-volume',
     'CAP-01 (domains-cap01-cstr-liquid-phase-conditions-dropped) -- tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py'),
    ('G34b', 'src/engcore/domains/kinetics/cstr/alternatives.py',
     '            *LIQUID_PHASE_CONDITIONS,\n',
     '',
     'CAP-01 (domains-cap01-k4-liquid-phase-conditions-dropped) -- tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py'),
    ('G34c', 'src/engcore/domains/kinetics/cstr/problem.py',
     '        name=DECLARED_TEMPERATURE_TO_BOILING_RATIO,\n        maximum=Quantity(1.0, DIMENSIONLESS),\n        maximum_inclusive=False,',
     '        name=DECLARED_TEMPERATURE_TO_BOILING_RATIO,\n        maximum=Quantity(1.0, DIMENSIONLESS),\n        maximum_inclusive=True,',
     'CAP-01 (domains-cap01-boiling-bound-made-inclusive) -- tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py'),
    ('G34d', 'src/engcore/domains/kinetics/cstr/context.py',
     '    return Quantity(coldest - max(-rise, 0.0), TEMPERATURE_UNIT)',
     '    return Quantity(coldest, TEMPERATURE_UNIT)',
     'CAP-01 (domains-cap01-endothermic-floor-ignored) -- tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py'),
    ('G34e', 'src/engcore/domains/kinetics/cstr/solver.py',
     '    assessment = run.validity_context(reached_temperature_range=reached).assess(',
     '    assessment = run.validity_context(reached_temperature_range=None).assess(',
     'CAP-01 (domains-cap01-realised-extremes-ignored) -- tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py'),
    ('G34f', 'src/engcore/domains/kinetics/cstr/context.py',
     '    reachable_maximum = ceiling if reached_maximum is None else _as_quantity(\n        reached_maximum,',
     '    reachable_maximum = ceiling if reached_maximum is None else _as_quantity(\n        reached_minimum,',
     'CAP-01 (domains-cap01-realised-maximum-read-as-minimum) -- tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py'),
    ('G34g', 'src/engcore/domains/battery/context.py',
     '        PULSE_POLARIZATION_UNMODELLED_FRACTION: polarization_unmodelled_fraction(\n            duration=base.get(PULSE_DURATION),',
     '        PULSE_POLARIZATION_UNMODELLED_FRACTION: polarization_unmodelled_fraction(\n            duration=polarization_duration,',
     'CAP-02 (domains-cap02-pulse-polarization-reads-the-step) -- tests/domains/battery/test_audit_domains_battery_pulse.py'),
    ('G34h', 'src/engcore/domains/battery/context.py',
     '    return Quantity(pulse_cut.magnitude_in(DIMENSIONLESS) - binding, DIMENSIONLESS)',
     '    return Quantity(0.0, DIMENSIONLESS)',
     'CAP-02 (domains-cap02-pulse-cutoff-shift-zeroed) -- tests/domains/battery/test_audit_domains_battery_pulse.py'),
    ('G34i', 'src/engcore/domains/battery/context.py',
     '    pulse_terminal = terminal_voltage(\n        open_circuit=worst_ocv,\n        current=base.get(PULSE_CURRENT),',
     '    pulse_terminal = terminal_voltage(\n        open_circuit=worst_ocv,\n        current=discharge_current,',
     'CAP-02 (domains-cap02-pulse-terminal-voltage-at-continuous-current) -- tests/domains/battery/test_audit_domains_battery_pulse.py'),
    ('G34j', 'src/engcore/domains/electrical/dc_applicability.py',
     '    return Quantity(abs(alpha) * abs(end - start) / budget, DIMENSIONLESS)',
     '    return Quantity(0.0, DIMENSIONLESS)',
     'CAP-03 (domains-cap03-resistance-variation-zeroed) -- tests/mcp/test_audit_domains_electrothermal_transient.py'),
    ('G34k', 'src/engcore/domains/electrical/material.py',
     '        if base.get(CONDUCTOR_CLASS) in (None, ELEMENTAL_METAL)\n        else None',
     '        if True\n        else None',
     'CAP-05 (domains-cap05c-debye-derivation-ungated) -- tests/domains/electrical/test_audit_domains_debye_conductor_class.py'),
    ('G34l', 'src/engcore/domains/electrical/material.py',
     '    if declared.get(CONDUCTOR_CLASS) not in (None, ELEMENTAL_METAL):\n        declared = {',
     '    if False:\n        declared = {',
     'CAP-05 (domains-cap05c-debye-cross-limits-ungated) -- tests/domains/electrical/test_audit_domains_debye_conductor_class.py'),
    ('G34m', 'src/engcore/mcp/problem.py',
     '                + _conductor_class_declarations(system),',
     '',
     'CAP-05 (domains-cap05c-assertion-not-recorded-in-report) -- tests/domains/electrical/test_audit_domains_debye_conductor_class.py'),
    ('G34n', 'src/engcore/systems/electrothermal/coupled.py',
     '                    largest_iterate_change=(\n                        iterations[-1].largest_iterate_change\n                        if iterations\n                        else Quantity(0.0, unit)\n                    ),',
     '                    largest_iterate_change=Quantity(0.0, unit),',
     'CAP-06 (domains-cap06-refused-sweep-change-zeroed) -- tests/mcp/test_audit_domains_refused_coupling.py'),
    ('G34o', 'src/engcore/mcp/server.py',
     '    if case.run.refusal is not None:',
     '    if False:',
     'CAP-06 (domains-cap06-refused-report-attributed-by-position) -- tests/mcp/test_audit_domains_refused_coupling.py'),
    ('G35a', 'src/engcore/inference/calibration.py',
     '    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if aliasing is not None:\n',
     '    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if False:\n',
     'CERT-02 fold of RIDGE-1: remove the aliasing check'),
    ('G35b', 'src/engcore/inference/calibration.py',
     '    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n',
     '    aliasing = _minimum_aliasing_number(np.diag(np.diag(lattice_covariance)), _ALIASING_NUMBER_MINIMUM)\n',
     'CERT-02 fold of RIDGE-2: use the diagonal of the fitted covariance only'),
    ('G35c', 'src/engcore/inference/calibration.py',
     '                if np.any(n != 0):\n',
     '                if np.count_nonzero(n) == 1:\n',
     'CERT-02 fold of RIDGE-3: enumerate axis lattice vectors only (drop off-axis n)'),
    ('G35d', 'src/engcore/inference/calibration.py',
     '        x = (points[index] - points[top]) / steps\n',
     '        x = points[index] - points[top]\n',
     'CERT-02 fold of RIDGE-4: disable scale normalization (fit in parameter units)'),
    ('G35e', 'src/engcore/inference/calibration.py',
     '    if ess < p + 1:\n',
     '    if ess < 1.0:\n',
     'CERT-02 fold of RIDGE-5: let ESS ~ 1 pass'),
    ('G35f', 'src/engcore/uq/predictive.py',
     '    refusal = _grid_resolution_refusal(posterior, discrete_posterior_passes=True)\n    if refusal is not None:\n',
     '    refusal = _grid_resolution_refusal(posterior, discrete_posterior_passes=True)\n    if False:\n',
     'CERT-02 fold of RIDGE-6: predictive UQ ignores the refusal'),
    ('G35g', 'src/engcore/inference/calibration.py',
     '    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if aliasing is not None:\n',
     '    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if aliasing is None:\n',
     'CERT-02 fold of RIDGE-7: threshold comparison reversed'),
    ('G35h', 'src/engcore/inference/calibration.py',
     '    if lattice_covariance is None:\n        return (\n',
     '    if lattice_covariance is None:\n        return None\n        return (\n',
     'CERT-02 fold of RIDGE-8: covariance fit failure treated as PASS'),
    ('G35i', 'src/engcore/hybrid_uq/local_gaussian.py',
     '    claim = claim_for(refusals + downgrades)\n',
     '    refusals, downgrades = [], []\n    claim = claim_for(refusals + downgrades)\n',
     'CERT-02 fold of HD-1: bypass the local-route validity check'),
    ('G35j', 'src/engcore/hybrid_uq/local_gaussian.py',
     '    if at_bound:\n        refusals.append(RouteReason.PARAMETER_AT_BOUND)\n',
     '    if False:\n        refusals.append(RouteReason.PARAMETER_AT_BOUND)\n',
     'CERT-02 fold of HD-2: ignore the bound-active refusal'),
    ('G35k', 'src/engcore/hybrid_uq/local_gaussian.py',
     '    elif condition > NUMERICAL_CONDITION_LIMIT:\n        structural = RouteReason.NUMERICALLY_SINGULAR_JACOBIAN\n',
     '    elif False:\n        structural = RouteReason.NUMERICALLY_SINGULAR_JACOBIAN\n',
     'CERT-02 fold of HD-3: ignore a singular Jacobian'),
    ('G35l', 'src/engcore/hybrid_uq/local_gaussian.py',
     '    if multistart is None:\n        uniqueness = "NOT_ASSESSED"\n',
     '    if True:\n        uniqueness = "NOT_ASSESSED"\n',
     'CERT-02 fold of HD-4: remove the multistart'),
    ('G35m', 'src/engcore/hybrid_uq/vocabulary.py',
     'Neither is the continuous posterior, and no member may say so.\n        return False\n',
     'Neither is the continuous posterior, and no member may say so.\n        return True\n',
     'CERT-02 fold of HD-5: mislabel an approximation as exact'),
    ('G35n', 'src/engcore/hybrid_uq/predictive.py',
     '    parameter_var = np.einsum("ij,jk,ik->i", G, cov, G)\n',
     '    parameter_var = np.zeros(G.shape[0])\n',
     'CERT-02 fold of HD-6: drop parameter uncertainty from the prediction'),
    ('G35o', 'src/engcore/hybrid_uq/predictive.py',
     '    total_sd = np.asarray([math.sqrt(parameter_var[i] + (m ** 2 if m is not None else 0.0)) for i, m in enumerate(measurement)])\n',
     '    total_sd = np.asarray([parameter_sd[i] + (m if m is not None else 0.0) for i, m in enumerate(measurement)])\n',
     'CERT-02 fold of HD-7: merge measurement and parameter uncertainty incorrectly (linear sum)'),
    ('G35p', 'src/engcore/hybrid_uq/router.py',
     '        try:\n            identifiability = assess_routed_identifiability(grid)\n',
     '        try:\n            identifiability = None\n',
     'CERT-02 fold of HD-8: route an unresolved grid as trusted'),
    ('G35q', 'src/engcore/hybrid_uq/local_gaussian.py',
     '        identity = digest_of({"parent": self.parameterization_digest,',
     '        identity = self.parameterization_digest or digest_of({"parent": self.parameterization_digest,',
     'CERT-02 fold of HD-9: ignore parameterization identity'),
    ('G35r', 'src/engcore/hybrid_uq/predictive.py',
     '    cov = posterior._require_numbers()\n    if posterior.parameterization != "declared":',
     '    cov = posterior._require_numbers() if posterior.covariance is not None else posterior._design_covariance\n    if posterior.parameterization != "declared":',
     'CERT-02 fold of HD-10: predictive UQ accepts a refused local route'),
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

#: A refusal at import must be RAISED BY THE CORE. Main audit CERT-08: the list
#: above only named what a refusal is not, so a TypeError or AttributeError at
#: import -- the vacuous kill the G14a note describes -- was credited as a
#: refusal. Python prints a non-builtin exception with its module path, so a
#: core refusal appears as ``E   engcore.<module>.<Name>: <message>``; anything
#: else (a bare builtin name) is not evidence that a rule fired.
_CORE_REFUSAL = re.compile(r"^E\s+(?:src\.)?engcore\.[\w.]+:\s", re.MULTILINE)

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
    "G27a": ("CONTRACT_REFUSAL",
             "other_material_state_is_rejected[A_sigma]"),
    "G27b": ("CONTRACT_REFUSAL",
             "test_j_an_indefinite_covariance_is_rejected_constructed_or_read_back"),
    "G27c": ("SCIENTIFIC_ASSERTION",
             "test_n_an_unchecked_affine_prediction_from_a_supported_posterior_is_downgraded"),
    "G27d": ("SCIENTIFIC_ASSERTION",
             "test_q_a_wide_bound_range_no_longer_biases_the_derivative"),
    "G27e": ("SERIALIZATION_INVARIANT",
             "test_v_to_x_the_same_contradictions_are_refused_in_memory"),
    "G27f": ("CONTRACT_REFUSAL",
             "test_ab_a_voltage_plus_a_current_is_refused"),
    "G27g": ("SERIALIZATION_INVARIANT",
             "test_a_serialized_grid_record_cannot_report_moments_its_summarized_grid_did_not_produce"),
    "G28a": ("VALIDITY_INVARIANT",
             "test_a_admission_refuses_a_usable_source_whose_model_was_assessed_and_not_shown_to_apply"),
    "G28b": ("PROVENANCE_INVARIANT",
             "test_b_a_result_declaring_a_model_its_provenance_does_not_name_is_refused"),
    "G28c": ("CONTRACT_REFUSAL",
             "test_c_a_solver_serving_model_at_1_does_not_support_a_problem_naming_model_at_2"),
    "G28d": ("PROVENANCE_INVARIANT",
             "test_d_content_mutated_around_the_frozen_record_cannot_reuse_its_identity_or_be_submitted"),
    "G28e": ("TYPE_INVARIANT",
             "test_e_a_belief_entry_payload_cannot_be_mutated_through_a_read"),
    "G28f": ("TYPE_INVARIANT",
             "test_f_an_uncertainty_channel_cannot_change_through_the_declaration_or_a_caller_alias"),
    "G28g": ("CONTRACT_REFUSAL",
             "test_a_session_that_cannot_be_tracked_is_refused_rather_than_shared_between_requests"),
    "G28h": ("PROVENANCE_INVARIANT",
             "test_a_calibration_spec_cannot_be_rewritten_through_its_mappings_after_construction"),
    # ---- main audit round: GUARDS 29-35 (each names the test that guards it) ----
    'G29a': ('CONTRACT_REFUSAL',
            'test_trust01_fabricated_assessments_about_the_evidence_are_refused'),
    'G29b': ('CONTRACT_REFUSAL',
            'test_trust01_assessment_run_for_another_record_is_refused'),
    'G29c': ('CONTRACT_REFUSAL',
            'test_trust01_a_result_from_another_run_does_not_count_even_when_it_agrees'),
    'G29d': ('CONTRACT_REFUSAL',
            'test_trust01_a_refused_assessment_blocks_valid_even_when_obligations_are_met'),
    'G29e': ('CONTRACT_REFUSAL',
            'test_trust01_e7_budget_for_another_quantity_leaves_the_channel_unmet'),
    'G29f': ('CONTRACT_REFUSAL',
            'test_trust01_unregistered_critic_cannot_run_and_misattributed_output_is_refused'),
    'G29g': ('CONTRACT_REFUSAL',
            'test_trust02_a_policy_naming_the_charter_digest_for_another_campaign_is_refused'),
    'G29h': ('CONTRACT_REFUSAL',
            'test_trust02_a_hand_built_policy_with_the_right_campaign_id_is_refused'),
    'G29i': ('CONTRACT_REFUSAL',
            'test_trust02_charter_version_is_checked_against_the_charter'),
    'G29j': ('CONTRACT_REFUSAL',
            'test_trust02_policy_digest_is_part_of_the_decision_hash'),
    'G29k': ('CONTRACT_REFUSAL',
            'test_trust02_decisions_record_the_policy_and_admission_carries_it'),
    'G29l': ('CONTRACT_REFUSAL',
            'test_trust02_stopping_review_refuses_a_proposal_from_another_campaign'),
    'G29m': ('CONTRACT_REFUSAL',
            'test_trust03_every_assessment_of_a_required_critic_class_must_pass'),
    'G29n': ('CONTRACT_REFUSAL',
            'test_trust03_a_required_check_reported_twice_is_ambiguous'),
    'G29o': ('CONTRACT_REFUSAL',
            'test_trust03_e4_a_numerical_check_cannot_discharge_a_domain_obligation'),
    'G29p': ('CONTRACT_REFUSAL',
            'test_trust03_a_domain_critic_for_another_pack_does_not_count'),
    'G29q': ('CONTRACT_REFUSAL',
            'test_trust04_a_reference_decision_never_authorizes_admission'),
    'G29r': ('CONTRACT_REFUSAL',
            'test_trust04_a_decision_authorizes_at_most_once'),
    'G29s': ('CONTRACT_REFUSAL',
            'test_sria05_an_active_record_cannot_be_replaced_under_its_id'),
    'G29t': ('CONTRACT_REFUSAL',
            'test_sria05_an_invalidated_record_cannot_be_readmitted_by_a_fresh_decision'),
    'G29u': ('CONTRACT_REFUSAL',
            'test_sria05_history_keeps_every_recorded_standing'),
    'G29v': ('CONTRACT_REFUSAL',
            'test_sria06_a_harness_cannot_mark_an_obligation_satisfied'),
    'G29w': ('CONTRACT_REFUSAL',
            'test_sria06_adopting_a_decision_from_another_arbiter_is_refused'),
    'G29x': ('CONTRACT_REFUSAL',
            'test_sria06_adopting_a_decision_made_under_another_policy_is_refused'),
    'G29y': ('CONTRACT_REFUSAL',
            'test_sria06_restoring_an_unbacked_obligation_state_is_refused'),
    'G29z': ('CONTRACT_REFUSAL',
            'test_ser01_t1_edited_obligation_state_with_recomputed_digest_is_refused'),
    'G29aa': ('CONTRACT_REFUSAL',
            'test_ser01_t2_rewritten_iteration_record_is_refused'),
    'G29ab': ('CONTRACT_REFUSAL',
            'test_ser01_t1b_flipping_an_unmet_obligation_is_refused'),
    'G29ac': ('CONTRACT_REFUSAL',
            'test_ser01_t3_legacy_file_is_not_migrated_implicitly'),
    'G29ad': ('CONTRACT_REFUSAL',
            'test_inf11_missing_coverage_caps_at_degraded'),
    'G29ae': ('CONTRACT_REFUSAL',
            'test_inf11_missing_censoring_caps_at_degraded'),
    'G29af': ('CONTRACT_REFUSAL',
            'test_inf11_provenance_without_censoring_counts_is_not_censoring_evidence'),
    'G29ag': ('CONTRACT_REFUSAL',
            'test_root_gateway_refuses_a_declaration_embedding_another_registry'),
    'G29ah': ('CONTRACT_REFUSAL',
            'test_root_a_policy_the_authority_does_not_serve_cannot_admit'),
    'G29ai': ('CONTRACT_REFUSAL',
            'test_root_a_second_arbiter_around_the_authority_is_refused'),
    'G29aj': ('CONTRACT_REFUSAL',
            'test_root_registry_digest_names_the_implementation'),
    'G29ak': ('CONTRACT_REFUSAL',
            'test_grounds_a_hand_built_decision_is_ignored'),
    'G29al': ('CONTRACT_REFUSAL',
            'test_grounds_a_decision_under_another_policy_is_ignored'),
    'G29am': ('CONTRACT_REFUSAL',
            'test_grounds_a_caller_may_only_lower_standing'),
    'G29an': ('CONTRACT_REFUSAL',
            'test_claim_a_different_value_for_the_assessed_quantity_does_not_count'),
    'G29ao': ('CONTRACT_REFUSAL',
            'test_claim_about_a_quantity_the_result_does_not_hold_does_not_count'),
    'G29ap': ('CONTRACT_REFUSAL',
            'test_claim_a_different_value_for_the_assessed_quantity_does_not_count'),
    'G29aq': ('CONTRACT_REFUSAL',
            'test_claim_budget_must_carry_the_evidences_uncertainty_declaration'),
    'G30a': ('VALIDATION_INVARIANT',
            'test_probe_ind1_routes_forty_percent_apart_under_another_gates_threshold_earn_nothing'),
    'G30b': ('VALIDATION_INVARIANT',
            'test_the_right_gate_under_a_key_the_routes_do_not_declare_awards_nothing'),
    'G30c': ('VALIDATION_INVARIANT',
            'test_reading_a_consensus_never_imports_a_module_the_payload_names'),
    'G30d': ('VALIDATION_INVARIANT',
            'test_round_off_on_a_near_zero_quantity_is_not_a_disagreement'),
    'G30e': ('VALIDATION_INVARIANT',
            'test_probe_identical_fabricated_numbers_under_both_production_route_ids_earn_nothing'),
    'G30f': ('VALIDATION_INVARIANT',
            'test_a_non_result_is_refused'),
    'G30g': ('VALIDATION_INVARIANT',
            'test_two_results_from_one_run_are_not_two_executions'),
    'G30h': ('VALIDATION_INVARIANT',
            'test_changed_numbers_under_an_intact_binding_cannot_keep_the_level'),
    'G30i': ('VALIDATION_INVARIANT',
            'test_a_tampered_binding_cannot_keep_the_level'),
    'G30j': ('VALIDATION_INVARIANT',
            'test_a_result_under_another_backend_is_refused'),
    'G30k': ('VALIDATION_INVARIANT',
            'test_probe_junk_bytes_for_external_identities_nobody_pinned_keep_no_level'),
    'G30l': ('VALIDATION_INVARIANT',
            'test_probe_junk_bytes_for_python_identities_keep_no_level'),
    'G30m': ('VALIDATION_INVARIANT',
            'test_external_bytes_count_only_when_the_domain_pins_their_digest'),
    'G30n': ('VALIDATION_INVARIANT',
            'test_the_steady_state_arm_establishes_no_cross_solver_level'),
    'G30o': ('VALIDATION_INVARIANT',
            'test_the_steady_state_arm_establishes_no_cross_solver_level'),
    'G30p': ('VALIDATION_INVARIANT',
            'test_a_disagreeing_cross_method_comparison_is_not_described_as_agreement'),
    'G30q': ('VALIDATION_INVARIANT',
            'test_a_comparison_of_nothing_is_described_and_does_not_raise'),
    'G30r': ('VALIDATION_INVARIANT',
            'test_probe_a_corrupted_gigaohm_solution_fails'),
    'G30s': ('VALIDATION_INVARIANT',
            'test_probe_a_corrupted_gigaohm_solution_fails'),
    'G30t': ('VALIDATION_INVARIANT',
            'test_probe_a_corrupted_gigaohm_solution_fails'),
    'G30u': ('VALIDATION_INVARIANT',
            'test_a_corrupted_nanovolt_source_node_fails_the_source_relation'),
    'G30v': ('VALIDATION_INVARIANT',
            'test_probe_admission_refuses_a_factor_two_current_at_every_scale'),
    'G30w': ('VALIDATION_INVARIANT',
            'test_probe_admission_refuses_a_zero_power_at_every_scale'),
    'G30x': ('VALIDATION_INVARIANT',
            'test_probe_a_hand_built_strong_level_is_refused'),
    'G30y': ('VALIDATION_INVARIANT',
            'test_a_report_re_verifies_issuers_on_every_read'),
    'G30z': ('VALIDATION_INVARIANT',
            'test_a_consensus_issuer_record_under_another_tolerance_is_refused'),
    'G30aa': ('VALIDATION_INVARIANT',
            'test_a_consensus_issuer_record_of_undeclared_numbers_is_refused_even_when_self_consistent'),
    'G30ab': ('VALIDATION_INVARIANT',
            'test_an_oracle_record_claiming_a_level_of_another_kind_is_refused'),
    'G30ac': ('VALIDATION_INVARIANT',
            'test_a_tampered_consensus_issuer_record_is_refused'),
    'G30ad': ('VALIDATION_INVARIANT',
            'test_a_consensus_issuer_record_for_a_gate_the_routes_do_not_name_is_refused'),
    'G30ae': ('VALIDATION_INVARIANT',
            'test_a_stored_status_that_is_not_the_recomputed_one_is_refused'),
    'G30af': ('VALIDATION_INVARIANT',
            'test_a_stored_empty_attained_levels_over_an_attained_level_is_refused'),
    'G30ag': ('VALIDATION_INVARIANT',
            'test_probe_an_admission_for_another_problem_is_refused'),
    'G30ah': ('VALIDATION_INVARIANT',
            'test_probe_a_manifest_of_another_execution_is_refused'),
    'G30ai': ('VALIDATION_INVARIANT',
            'test_probe_a_non_converged_output_is_not_trusted'),
    'G31a': ('SERIALIZATION_INVARIANT',
            'test_res01_a_credibility_report_cannot_launder_a_silent_record'),
    'G31b': ('SERIALIZATION_INVARIANT',
            'test_res01_a_credibility_report_cannot_launder_a_silent_record'),
    'G31c': ('SERIALIZATION_INVARIANT',
            'test_res01_provenance_naming_the_solver_but_no_model_marks_the_model'),
    'G31d': ('SERIALIZATION_INVARIANT',
            'test_res01_provenance_naming_the_model_but_no_solver_marks_the_solver'),
    'G31e': ('SERIALIZATION_INVARIANT',
            'test_res01_contradictory_provenance_is_still_refused'),
    'G31f': ('SERIALIZATION_INVARIANT',
            'test_res02_relabelling_to_an_older_version_is_refused_not_downgraded'),
    'G31g': ('SERIALIZATION_INVARIANT',
            'test_res02_a_key_the_declared_version_always_wrote_is_required'),
    'G31h': ('SERIALIZATION_INVARIANT',
            'test_res02_a_provenance_relabelled_v1_while_carrying_bindings_is_refused'),
    'G31i': ('SERIALIZATION_INVARIANT',
            'test_res02_a_current_provenance_with_its_bindings_key_deleted_is_refused'),
    'G31j': ('SERIALIZATION_INVARIANT',
            'test_res02_an_older_provenance_carrying_a_non_quantity_input_is_refused'),
    'G31k': ('SERIALIZATION_INVARIANT',
            'test_res05_a_missing_convergence_or_validation_is_refused'),
    'G31l': ('SERIALIZATION_INVARIANT',
            'test_res04_a_condition_the_model_does_not_declare_is_refused'),
    'G31m': ('SERIALIZATION_INVARIANT',
            'test_res04_an_assessment_omitting_the_conditions_it_did_not_like_is_refused'),
    'G31n': ('SERIALIZATION_INVARIANT',
            'test_res04_a_condition_reported_twice_is_refused'),
    'G31o': ('SERIALIZATION_INVARIANT',
            'test_res04_an_unresolvable_model_says_so_and_cannot_be_supported'),
    'G31p': ('SERIALIZATION_INVARIANT',
            'test_res06_ok_over_a_result_that_cannot_support_it_is_refused'),
    'G31q': ('SERIALIZATION_INVARIANT',
            'test_res06_ok_over_a_result_that_cannot_support_it_is_refused'),
    'G31r': ('SERIALIZATION_INVARIANT',
            'test_res06_an_objective_that_contradicts_the_result_it_names_is_refused'),
    'G31s': ('SERIALIZATION_INVARIANT',
            'test_res06_the_probe_shape_is_refused_on_read_too'),
    'G31t': ('SERIALIZATION_INVARIANT',
            'test_cap04_a_declaration_that_moves_the_battery_verdict_says_so'),
    'G31u': ('SERIALIZATION_INVARIANT',
            'test_cap04_a_declaration_that_moves_the_electrothermal_verdict_says_so'),
    'G31v': ('SERIALIZATION_INVARIANT',
            'test_cap04_an_unstated_flag_is_null_on_the_wire_never_false'),
    'G31w': ('SERIALIZATION_INVARIANT',
            'test_cap04_a_v1_record_is_read_but_its_literal_false_is_not_believed'),
    'G31x': ('SERIALIZATION_INVARIANT',
            'test_res08_a_report_without_its_verdict_is_refused'),
    'G31y': ('SERIALIZATION_INVARIANT',
            'test_res08_a_rewritten_verdict_qualifier_is_refused'),
    'G31z': ('SERIALIZATION_INVARIANT',
            'test_res08_a_rewritten_verdict_qualifier_is_refused'),
    'G32a': ('VALIDITY_INVARIANT',
            'test_a_collapsed_three_by_three_grid_is_refused_by_predictive_uq'),
    'G32b': ('VALIDITY_INVARIANT',
            'test_sharpened_weights_beside_the_honest_log_likelihood_are_refused'),
    'G32c': ('VALIDITY_INVARIANT',
            'test_mass_on_an_inadmissible_node_is_refused'),
    'G32d': ('VALIDITY_INVARIANT',
            'test_a_conditioned_posterior_still_binds_its_weights'),
    'G32e': ('VALIDITY_INVARIANT',
            'test_holding_out_far_outside_the_validated_domain_is_not_a_pass'),
    'G32f': ('VALIDITY_INVARIANT',
            'test_an_inflated_observation_sigma_cannot_flip_fail_to_pass'),
    'G32g': ('VALIDITY_INVARIANT',
            'test_a_posterior_fitted_on_every_row_and_relabelled_is_refused'),
    'G32h': ('VALIDITY_INVARIANT',
            'test_too_little_evidence_is_not_calibrated'),
    'G32i': ('VALIDITY_INVARIANT',
            'test_no_intervals_is_refused_not_calibrated'),
    'G32j': ('VALIDITY_INVARIANT',
            'test_a_tcr_forward_row_outside_the_declared_bounds_is_refused'),
    'G32k': ('VALIDITY_INVARIANT',
            'test_the_same_reading_in_another_unit_is_the_same_content'),
    'G32l': ('VALIDITY_INVARIANT',
            'test_a_one_ulp_nudge_is_still_the_same_content'),
    'G32m': ('VALIDITY_INVARIANT',
            'test_one_condition_in_both_halves_is_refused'),
    'G32n': ('VALIDITY_INVARIANT',
            'test_scoring_against_the_posteriors_own_dataset_is_refused'),
    'G32o': ('VALIDITY_INVARIANT',
            'test_relaxed_thresholds_cannot_buy_an_identifiable_verdict'),
    'G32p': ('VALIDITY_INVARIANT',
            'test_meaningless_thresholds_are_refused'),
    'G32q': ('VALIDITY_INVARIANT',
            'test_a_parameter_on_an_offset_scale_is_refused'),
    'G32r': ('VALIDITY_INVARIANT',
            'test_a_caller_string_is_not_an_applicability_verdict'),
    'G32s': ('VALIDITY_INVARIANT',
            'test_a_record_cannot_be_built_with_an_invented_status'),
    'G33a': ('SCIENTIFIC_ASSERTION',
            'test_huq01_a_weakened_multistart_can_never_support_the_route'),
    'G33b': ('SCIENTIFIC_ASSERTION',
            'test_huq01_the_policy_actually_used_is_committed_in_the_diagnostics_digest'),
    'G33c': ('SCIENTIFIC_ASSERTION',
            'test_huq08_a_cross_term_invisible_along_the_principal_axes_is_measured'),
    'G33d': ('SCIENTIFIC_ASSERTION',
            'test_huq08_a_converged_refit_below_the_estimate_is_never_the_same_optimum'),
    'G33e': ('SCIENTIFIC_ASSERTION',
            'test_huq10_a_route_whose_probes_all_left_the_bounds_emits_no_covariance'),
    # Repointed after the round reported it GREEN: the 3 x 3 case is refused twice over (here and by
    # INF-04's resolution check inside the frozen predictive call), so it could not see this guard go.
    'G33f': ('SCIENTIFIC_ASSERTION',
            'test_huq02_the_wrapper_judges_the_grid_itself_where_the_v1_checks_would_pass'),
    'G33g': ('SCIENTIFIC_ASSERTION',
            'test_huq04_the_grid_digest_covers_the_likelihood_and_the_mask'),
    'G33h': ('SCIENTIFIC_ASSERTION',
            'test_huq04_the_grid_digest_covers_the_likelihood_and_the_mask'),
    'G33i': ('SCIENTIFIC_ASSERTION',
            'test_huq04_a_refused_grid_laundered_with_a_smooth_likelihood_is_refused'),
    'G33j': ('SCIENTIFIC_ASSERTION',
            'test_huq05_a_rebuild_table_from_another_model_is_never_certified'),
    'G33k': ('SCIENTIFIC_ASSERTION',
            'test_huq06_a_grid_for_other_data_is_not_routed_for_this_request'),
    'G33l': ('SCIENTIFIC_ASSERTION',
            'test_huq06_a_grid_over_other_parameters_is_not_routed_for_this_request'),
    'G33m': ('SCIENTIFIC_ASSERTION',
            'test_huq03_a_log_parameter_is_as_identifiable_in_one_unit_as_in_its_multiple'),
    'G33n': ('SCIENTIFIC_ASSERTION',
            'test_huq14_the_explanation_is_part_of_the_identity'),
    'G33o': ('SCIENTIFIC_ASSERTION',
            'test_huq07_a_cross_term_between_two_principal_axes_is_not_linear'),
    'G33p': ('SCIENTIFIC_ASSERTION',
            'test_huq07_a_three_way_term_is_seen_along_the_predictive_gradient'),
    'G33q': ('SCIENTIFIC_ASSERTION',
            'test_huq11_a_large_measurement_sigma_does_not_hide_a_curved_parameter_part'),
    'G33r': ('SCIENTIFIC_ASSERTION',
            'test_huq09_diagnostics_that_contradict_their_claim_are_refused'),
    'G33s': ('SCIENTIFIC_ASSERTION',
            'test_huq09_an_identifiability_report_the_covariance_does_not_produce_is_refused'),
    'G33t': ('SCIENTIFIC_ASSERTION',
            'test_huq09_a_grid_covariance_shrunk_under_a_recomputed_commitment_is_refused'),
    'G33u': ('SCIENTIFIC_ASSERTION',
            'test_huq09_a_standalone_verdict_must_follow_from_its_own_numbers'),
    'G33v': ('SCIENTIFIC_ASSERTION',
            'test_huq12_a_routed_result_built_around_a_contradictory_posterior_is_refused_in_memory'),
    'G33w': ('SCIENTIFIC_ASSERTION',
            'test_huq12_an_estimate_that_is_not_its_inference_point_is_refused'),
    'G33x': ('SCIENTIFIC_ASSERTION',
            'test_huq09_a_legacy_route_with_every_probe_skipped_and_nonlinearity_zero_is_refused'),
    'G33y': ('SCIENTIFIC_ASSERTION',
            'test_huq12_a_non_finite_grid_mean_is_refused_even_with_a_recomputed_commitment'),
    'G33z': ('SCIENTIFIC_ASSERTION',
            'test_huq12_the_grid_summary_is_a_closed_committed_record'),
    'G33aa': ('SCIENTIFIC_ASSERTION',
            'test_huq12_the_grid_summary_is_a_closed_committed_record'),
    'G33ab': ('SCIENTIFIC_ASSERTION',
            'test_huq12_a_predictive_record_whose_numbers_contradict_each_other_is_refused'),
    'G33ac': ('SCIENTIFIC_ASSERTION',
            'test_huq12_a_predictive_record_whose_numbers_contradict_each_other_is_refused'),
    'G33ad': ('SCIENTIFIC_ASSERTION',
            'test_huq12_a_predictive_record_whose_numbers_contradict_each_other_is_refused'),
    'G33ae': ('SCIENTIFIC_ASSERTION',
            'test_huq13_nested_mappings_of_a_validated_record_are_immutable'),
    'G33af': ('SCIENTIFIC_ASSERTION',
            'test_huq13_nested_mappings_of_a_validated_record_are_immutable'),
    'G33ag': ('SCIENTIFIC_ASSERTION',
            'test_huq13_nested_mappings_of_a_validated_record_are_immutable'),
    'G33ah': ('SCIENTIFIC_ASSERTION',
            'test_huq13_nested_mappings_of_a_validated_record_are_immutable'),
    'G34a': ('VALIDITY_INVARIANT',
            'test_supercritical_water_like_reactor_is_not_in_domain_without_a_boiling_point'),
    'G34b': ('VALIDITY_INVARIANT',
            'test_the_competitor_model_claims_the_same_liquid_and_checks_it'),
    'G34c': ('VALIDITY_INVARIANT',
            'test_exactly_at_boiling_is_not_liquid'),
    'G34d': ('VALIDITY_INVARIANT',
            'test_endothermic_floor_reaches_freezing_even_when_every_declared_temperature_is_liquid'),
    'G34e': ('VALIDITY_INVARIANT',
            'test_a_solved_run_is_assessed_at_the_states_it_reached_not_the_ceiling'),
    'G34f': ('VALIDITY_INVARIANT',
            'test_a_solved_run_that_truly_boils_stays_outside'),
    'G34g': ('VALIDITY_INVARIANT',
            'test_the_pulse_polarization_reads_pulse_duration_not_the_step'),
    'G34h': ('VALIDITY_INVARIANT',
            'test_the_reviewer_pulse_is_no_longer_in_domain_on_rint_or_runtime'),
    'G34i': ('VALIDITY_INVARIANT',
            'test_a_pulse_driving_the_rint_terminal_voltage_negative_is_outside'),
    'G34j': ('VALIDITY_INVARIANT',
            'test_the_nickel_transient_violates_a_five_percent_budget'),
    'G34k': ('VALIDITY_INVARIANT',
            'test_the_public_derivation_withholds_the_floor_for_a_declared_non_elemental_class'),
    'G34l': ('VALIDITY_INVARIANT',
            'test_a_non_elemental_conductor_leaves_every_debye_condition_unknown'),
    'G34m': ('VALIDITY_INVARIANT',
            'test_the_report_carries_the_assertion'),
    'G34n': ('VALIDITY_INVARIANT',
            'test_a_refused_run_does_not_report_its_criterion_met'),
    'G34o': ('VALIDITY_INVARIANT',
            'test_the_refused_report_is_published_under_the_stage_that_was_refused'),
    'G35a': ('SCIENTIFIC_ASSERTION',
            'test_a_rotated_frame_with_an_unresolved_thin_axis_is_refused'),
    'G35b': ('SCIENTIFIC_ASSERTION',
            'test_predictive_uq_refuses_the_f5_thin_ridge'),
    'G35c': ('SCIENTIFIC_ASSERTION',
            'test_predictive_uq_refuses_the_f5_thin_ridge'),
    'G35d': ('SCIENTIFIC_ASSERTION',
            'test_a_rotated_frame_with_an_unresolved_thin_axis_is_refused'),
    'G35e': ('SCIENTIFIC_ASSERTION',
            'test_mass_on_one_node_is_refused_even_when_the_fitted_curvature_looks_resolved'),
    'G35f': ('SCIENTIFIC_ASSERTION',
            'test_a_collapsed_three_by_three_grid_is_refused_by_predictive_uq'),
    'G35g': ('SCIENTIFIC_ASSERTION',
            'test_the_f5_thin_ridge_is_refused'),
    'G35h': ('SCIENTIFIC_ASSERTION',
            'test_a_grid_whose_curvature_cannot_be_fitted_is_refused_not_passed'),
    'G35i': ('SCIENTIFIC_ASSERTION',
            'test_strong_nonlinearity_is_refused'),
    'G35j': ('SCIENTIFIC_ASSERTION',
            'test_a_parameter_at_its_bound_is_refused'),
    'G35k': ('SCIENTIFIC_ASSERTION',
            'test_a_nearly_singular_jacobian_is_refused'),
    'G35l': ('SCIENTIFIC_ASSERTION',
            'test_a_mirror_mode_is_refused_with_multistart_and_downgraded_without'),
    'G35m': ('SCIENTIFIC_ASSERTION',
            'test_no_approximation_class_is_an_exact_posterior'),
    'G35n': ('SCIENTIFIC_ASSERTION',
            'test_a_complete_linear_check_is_supported'),
    'G35o': ('SCIENTIFIC_ASSERTION',
            'test_a_merged_total_is_rejected_by_the_record'),
    'G35p': ('SCIENTIFIC_ASSERTION',
            'test_an_unresolved_grid_is_never_trusted'),
    'G35q': ('SCIENTIFIC_ASSERTION',
            'test_two_parameterizations_of_one_posterior_never_share_an_identity'),
    'G35r': ('SCIENTIFIC_ASSERTION',
            'test_predictive_uq_refuses_a_refused_local_route'),
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
    # Added with G27. The Hybrid UQ trust-boundary suite: the only module that
    # asserts the six Core V2 refusals those mutations remove.
    "tests/hybrid_uq/test_hybrid_uq_trust_boundary.py",
    # Added with G28. The core trust closure suite: the only module asserting
    # the eight refusals those mutations remove.
    "tests/test_core_trust_closure.py",
    # Added with GUARDS 29-35 (main audit round): the suites that assert each new
    # invariant, and the suites that kill the folded RIDGE/HD mutations.
    "tests/domains/battery/test_audit_domains_battery_pulse.py",
    "tests/domains/battery/test_audit_inference_ocv_applicability.py",
    "tests/domains/electrical/test_audit_consensus_dc_scale.py",
    "tests/domains/electrical/test_audit_domains_debye_conductor_class.py",
    "tests/domains/kinetics/test_audit_consensus_cstr_levels.py",
    "tests/domains/kinetics/test_audit_domains_cstr_liquid_envelope.py",
    "tests/hybrid_uq/test_audit_hybrid_grid_route.py",
    "tests/hybrid_uq/test_audit_hybrid_identifiability.py",
    "tests/hybrid_uq/test_audit_hybrid_local_route.py",
    "tests/hybrid_uq/test_audit_hybrid_predictive.py",
    "tests/hybrid_uq/test_audit_hybrid_records.py",
    "tests/hybrid_uq/test_hybrid_uq_identifiability_predictive.py",
    "tests/hybrid_uq/test_hybrid_uq_local_route.py",
    "tests/hybrid_uq/test_hybrid_uq_records.py",
    "tests/hybrid_uq/test_hybrid_uq_router.py",
    "tests/inference/test_audit_inference_grid_resolution.py",
    "tests/inference/test_audit_inference_heldout_study.py",
    "tests/inference/test_audit_inference_identifiability.py",
    "tests/inference/test_audit_inference_posterior_binding.py",
    "tests/inference/test_audit_inference_split_guards.py",
    "tests/inference/test_grid_resolution_repair.py",
    "tests/mcp/test_audit_domains_electrothermal_transient.py",
    "tests/mcp/test_audit_domains_refused_coupling.py",
    "tests/mcp/test_audit_results_declarations.py",
    "tests/mcp/test_audit_results_validity_binding.py",
    "tests/test_audit_consensus_artifact_authority.py",
    "tests/test_audit_consensus_execution_binding.py",
    "tests/test_audit_consensus_level_issuers.py",
    "tests/test_audit_consensus_resolution_and_floor.py",
    "tests/test_audit_consensus_threshold_authority.py",
    "tests/test_audit_consensus_trusted_record.py",
    "tests/test_audit_results_evaluation.py",
    "tests/test_audit_results_stored_results.py",
    "tests/test_audit_sria_assurance_binding.py",
    "tests/test_audit_sria_claim_binding.py",
    "tests/test_audit_sria_cost_critic.py",
    "tests/test_audit_sria_gateway_history.py",
    "tests/test_audit_sria_obligation_state.py",
    "tests/test_audit_sria_persistence_derivation.py",
    "tests/test_audit_sria_policy_binding.py",
    "tests/test_audit_sria_stop_review_grounds.py",
    "tests/test_audit_sria_trust_root.py",
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
# `tools` joined this list in Sprint 7, and the reason is worth keeping: the
# certificate drift test added in Sprint 6 imports `tools.certification`, and a
# copy without it made `test_every_dependency_the_tree_reaches_for_is_declared`
# fail with no mutation applied. The harness refused to run and said so —
# CONTROL RED, ROUND VOID — which is the behaviour it was built for, and it is
# how the omission was found at all. What the copy must contain is whatever
# `tests/` reaches for.
_COPIED = (
    "src", "tests", "tools", "experiments", "docs", "benchmarks", "pyproject.toml",
)


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
    # pytest creates --basetemp with mkdir(parents=False), lazily, the first time
    # a test asks for tmp_path. Until GUARDS 29-35 no target suite did, so the
    # missing `pt` parent went unnoticed; the first suite that used tmp_path
    # made CONTROL red for a reason unrelated to any guard.
    (scratch / "pt").mkdir(parents=True, exist_ok=True)
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
        elif expect == REFUSED_AT_IMPORT:
            # The core REFUSED while a module was being imported. With the
            # original six target suites that stopped collection and no test
            # ran. Since GUARDS 29-35 some target suites import the refusing
            # domain lazily, inside a test, so the SAME refusal also surfaces
            # as failed tests. Either way it is evidence only when the refusal
            # is raised by the core and nothing broke the language; a failure
            # list without a core refusal in it is not this mechanism.
            raised = "\n".join(
                l for l in output.splitlines() if l.startswith("E   ")
            )
            broke = next((n for n in _NOT_A_REFUSAL if n in raised), None)
            if broke:
                verdict, results[mid] = f"RED ({broke})", "IMPORT_OR_SYNTAX"
            elif not _CORE_REFUSAL.search(raised):
                verdict, results[mid] = "RED (not a core refusal)", "IMPORT_OR_SYNTAX"
            else:
                verdict, results[mid] = "RED (refused at import)", "RED"
        elif not failed:
            # Nothing was collected, and the mutation does not claim a refusal:
            # a stopped suite is not the guard it names.
            verdict, results[mid] = "RED (NOT THE GUARD)", "UNRELATED"
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
