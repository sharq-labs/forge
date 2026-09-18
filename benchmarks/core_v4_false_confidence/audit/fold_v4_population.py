"""Fold every batch guard mutation of this round into the pinned harness area (I-30, R-67).

    python -m benchmarks.core_v4_false_confidence.audit.fold_v4_population

Reads every ``batch*_mutations.py`` in this directory BY PARSING IT, never by importing it: the early
scripts of the round run their mutations at import time and one of them still names an absolute path from
the machine the round started on. Parsing is also what makes this generator honest about what it found --
an entry it cannot read is reported rather than skipped silently.

It writes ``tests/mutation_population_v4.py``: the same entries, as literal data, inside the harness area
that the certificate pins. R-67's finding is that this evidence sat OUTSIDE that area and that the runners
counted any failure as a kill; the per-entry target test travels with each entry here, so a kill is the
named test failing and nothing else.
"""

from __future__ import annotations

import ast
import hashlib
import io
import tokenize
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
OUT = ROOT / "tests" / "mutation_population_v4.py"


def _constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings, which the specs are spelled with."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    out[target.id] = node.value.value
    return out


def _text(node: ast.AST, constants: dict[str, str]) -> str:
    """Evaluate a string expression built from literals, names and f-strings."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in constants:
            raise ValueError(f"unknown name {node.id!r}")
        return constants[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _text(node.left, constants) + _text(node.right, constants)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                parts.append(_text(value.value, constants))
            else:  # pragma: no cover - no other shape occurs
                raise ValueError(f"unsupported f-string part {type(value).__name__}")
        return "".join(parts)
    if isinstance(node, ast.IfExp):
        # Two batch-13 specs are spelled `"<a>" if False else "<b>"`: an author left the first
        # replacement text beside the one actually used. Only a literal condition is read, so which
        # branch the harness ran is not a guess.
        if not (isinstance(node.test, ast.Constant) and isinstance(node.test.value, bool)):
            raise ValueError("a conditional expression whose condition is not a literal")
        return _text(node.body if node.test.value else node.orelse, constants)
    if isinstance(node, ast.Attribute):
        # `Mutation(... expect=Mutation.KILLED)` never occurs; enum-ish attributes do not.
        raise ValueError(f"unsupported attribute {ast.dump(node)[:60]}")
    raise ValueError(f"unsupported expression {type(node).__name__}")


#: Entries whose target moved AFTER the batch that wrote them, repointed here with the reason.
#:
#: A stale mutation is a guard verified by nobody -- the finding `tests/test_mutation_harness.py`
#: exists for -- and a round that folds its own evidence into the pinned area cannot fold entries
#: that no longer describe the tree. So each one is repointed at the code the rule lives in NOW, and
#: the move is written down: what it used to name, where the rule went, and that the mutation still
#: removes the same rule. None of these weakens a mutation; where a rule moved into a helper the
#: mutation is now narrower, which is stronger evidence about that rule and not less.
#:
#: Retiring one instead was available and is not used anywhere below: every rule these entries name
#: is still in the tree, so there is nothing here that a repoint cannot say honestly.
REPOINTED: dict[str, dict[str, str]] = {
    "B1a": {"scope": "_one_fit_test",
            "old": '    if float(statistic) / float(null_mean) > MISFIT_REFUSE_VARIANCE_RATIO:\n',
            "why": "the variance-ratio refusal moved out of `_goodness_of_fit` into `_one_fit_test` when "
                   "R-03 added the leverage test as a second application of the same rule"},
    "B1b": {"old": '    downgrades = {RouteReason.RESIDUALS_EXCEED_DECLARED_NOISE} if verdict == 1 else set()\n',
            "new": '    downgrades = set()\n',
            "why": "the same downgrade, now derived from the worse of two tests' verdicts rather than "
                   "returned from one branch"},
    "B1c": {"old": '    fit_refusals, fit_downgrades = _goodness_of_fit(chi_min, n, p, leverage_statistic, '
                   'leverage_cumulants)\n',
            "why": "`_goodness_of_fit` gained the leverage statistic and its null (R-03), so the call the "
                   "mutation removes has two more arguments"},
    "B1d": {"old": '            found_refusals, found_downgrades = _goodness_of_fit(chi_minimum, n, p, statistic, '
                   'cumulants)\n',
            "why": "the read-side recomputation calls the same widened `_goodness_of_fit` (R-03)"},
    "B1f": {"old": '                tail_ratio = min(tail_ratio, (value - chi_min) / reached ** 2)\n',
            "why": "the probe radius is named `reached` since the clipped-radius change; the rise ratio it "
                   "accumulates is the same one"},
    "B1j": {"old": '                           or grid_goodness_of_fit(grid, observations, calibration=calibration, '
                   'forward=forward)\n',
            "new": '                           or None\n',
            "why": "the router's supplied-grid gates are a disjunction of one-per-line calls now, so the fit "
                   "gate is removed on its own line instead of by rewriting a two-call expression. NOT dropped: "
                   "the mission's final round expected these two to be unrepointable, and both rules are still "
                   "here, so retiring them would retire a live guard"},
    "B1k": {"old": '                           or grid_containment(grid, calibration)\n',
            "new": '                           or None\n',
            "why": "the containment gate of the same disjunction, for the same reason as B1j"},
    "B1l": {"old": '        binding = grid_is_this_evidence(grid, calibration, observations, forward) if bound else None\n',
            "new": '        binding = None\n',
            "why": "I-07 (R-30) turned the router's raise into a REPORTED finding, so the binding the mutation "
                   "removes is computed here and consumed in the disjunction below"},
    "B1m": {"scope": "grid_is_this_evidence",
            "why": "the chi-square agreement moved from the raising wrapper into the reporting function it now "
                   "delegates to (I-07, R-30); `require_grid_is_this_evidence` is three lines of re-raise"},
    "B1n": {"scope": "grid_is_this_evidence", "why": "the admission comparison moved with it, same change"},
    "B20e": {"scope": "_invariant_basis",
             "old": '    mu, w = np.linalg.eigh(correlation)\n    return mu, sd[:, None] * w\n',
             "new": '    return np.linalg.eigh(cov)\n',
             "why": "R-16's fix is now a named basis rather than two lines inside the route, and this is the "
                    "same mutation: it puts the probe axes back on `eigh(cov)`, the unit-dependent basis"},
    "B23k": {"old": '        found = _prediction_domain_reasons(spec, calibration_observations) | _table_reasons(\n'
                    '            result.grid, predictive_table, spec, predict) | unbound\n',
             "new": '        found = _prediction_domain_reasons(spec, calibration_observations) | unbound\n',
             "why": "the same line gained R-34's `unbound` term, which the mutation must keep: removing it too "
                    "would let a second rule take the kill"},
    "B2d": {"old": '        if worst <= UNIFORM_STEP_RELATIVE_TOLERANCE * mean:\n',
            "new": '        if True:\n',
            "why": "I-07 (R-29) inverted this test into an early `continue` and judges uneven spacing by what "
                   "the reweighting moves; skipping every axis is what removing the gate means now"},
    "B2f": {"old": '                           or grid_prior_uniformity(grid, calibration)\n',
            "new": '                           or None\n',
            "why": "one line of the router's disjunction, as for B1j"},
    "B2g": {"old": '    problem = (grid_prior_uniformity(posterior, calibration)\n',
            "new": '    problem = (None\n',
            "why": "the standalone grid predictive's binding call moved one line up, so the uniformity gate is "
                   "the first term rather than the second"},
    "B3e": {"path": "src/engcore/scientific/results/requirements.py", "scope": "result_establishment_problems",
            "old": '        != "IN_DOMAIN"\n',
            "new": '        != "IN_DOMAIN" and False\n',
            "why": "R-44 moved CORE-015 into the results layer, where `_established` now delegates. The "
                   "mutation keeps its meaning exactly -- an assessed model passes whatever its status -- and "
                   "is applied where the rule is"},
    "B3f": {"old": '        if not comparable:\n',
            "new": '        if False:\n',
            "why": "R-53 (I-26) made the comparison point by point, so the NOT_RUN is taken when NOTHING is "
                   "comparable rather than when anything was observed elsewhere"},
    "B49a": {"old": '        crossings=recorded_crossings(final, _recorded_transfers(system, plan, final)),\n',
             "why": "batch 49's own follow-up introduced `_recorded_transfers` to keep the G20a anchor "
                    "byte-identical, which moved this line in the same round that wrote the mutation"},
    "B4a": {"old": '    if residual > PREDICTION_RANGE_RELATIVE_TOLERANCE:\n',
            "why": "R-31 replaced the per-condition box test with the joint support residual, so the same "
                   "OUTSIDE_CALIBRATED_CONDITIONS gate is one comparison instead of two"},
    "B4b": {"old": '    if design is None or not spec.conditions:\n',
            "why": "the calibration design is resolved by `_calibration_design` now; the guard is the same "
                   "DOMAIN_NOT_DECLARED branch"},
    "B4c": {"old": '        spec_reasons = reasons | _prediction_domain_reasons(spec, calibration_observations, '
                   'posterior)\n',
            "why": "`_prediction_domain_reasons` gained the posterior so a grid route can supply the design"},
    "B4e": {"old": '    if not all(item.content_binding_verified for item in (*a, *b)):\n',
            "new": '    if False:\n',
            "why": "R-34: the comparison stopped reading the recorded `content_bound` claim and checks the "
                   "binding verified IN THIS PROCESS. Same gate, on the field that is evidence"},
    "B4f": {"scope": "_decisive_preference",
            "old": '    if abs(float(delta)) <= COMPARISON_MINIMUM_ABS_DELTA:\n',
            "new": '    if False:\n',
            "why": "R-33 moved the three decisiveness conditions into `_decisive_preference` so the gate can "
                   "be read at its own boundary; the floor is the second of them"},
    "B7j": {"old": '            convergence=result.convergence,\n            uncertainty=dict(result.uncertainty),\n',
            "new": '            convergence=result.convergence,\n            uncertainty={},\n',
            "why": "I-19 added a SECOND `uncertainty=dict(result.uncertainty)` in this method, for the "
                   "re-derived requirement checks. The preceding line is carried so the mutation still names "
                   "the report field the target test reads, and not the checks"},
    "B17f": {"test": "tests/test_core_scientific_audit_batch17.py::test_r02_the_claim_names_the_prediction_domain",
             "why": "the target test was RENAMED inside its own batch -- the claim it checks is the one the "
                    "audit's R-02 names and the '_it_cannot_yet_show' tail went away with a rewrite. The "
                    "mutation and the rule are untouched; only the nodeid a kill must carry is corrected. "
                    "Found by the formal round, which reported NOT_COLLECTED where the old rule would have "
                    "read 'pytest exited 4' as a kill"},
    "B36c": {"scope": "local_gaussian_posterior",
             "why": "`_refused` now writes the same digest for a refused route, so the unscoped pattern matches "
                    "twice; the target test reads the FITTED record"},
}

#: The two entries a batch declared as NOT MUTATED at the time it ran, with their reason in the note.
#:
#: Each has an empty `old` and `new` and was excluded from its own run: one edits a JSON file, which
#: `mutation_guards._apply` reports as MUTATION BROKE THE PARSE, and the other edits only prose,
#: which it reports as MUTATION CHANGED NO CODE. They are kept because a reader of the population
#: should not have to wonder why a row's move is unmutated, and they are marked so that nothing
#: tries to apply them.
NOT_MUTATED = "NOT_MUTATED"


def _entries_of(path: pathlib.Path):
    """Every mutation in one batch script, as ``(id, spec, old, new, test, expect, note, also)``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = _constants(tree)
    found = []
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        name = target.id if isinstance(target, ast.Name) else None
        if name != "MUTATIONS" or not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        for item in node.value.elts:
            if isinstance(item, (ast.Tuple, ast.List)):
                values = [_text(e, constants) for e in item.elts]
                if len(values) == 5:
                    mid, spec, old, new, test = values
                    found.append((mid, spec, old, new, test, "KILLED", "", ()))
                    continue
                raise ValueError(f"{path.name}: a {len(values)}-tuple mutation")
            if isinstance(item, ast.Call):
                positional = [_text(a, constants) for a in item.args]
                keywords = {}
                also: list[tuple[str, str, str]] = []
                for kw in item.keywords:
                    if kw.arg == "also":
                        for triple in kw.value.elts:
                            also.append(tuple(_text(e, constants) for e in triple.elts))
                        continue
                    keywords[kw.arg] = _text(kw.value, constants)
                fields = ["id", "spec", "old", "new", "test", "note", "expect"]
                values = dict(zip(fields, positional))
                values.update(keywords)
                found.append((
                    values["id"], values["spec"], values["old"], values["new"],
                    values["test"], values.get("expect", "KILLED"),
                    values.get("note", ""), tuple(also),
                ))
                continue
            raise ValueError(f"{path.name}: unsupported entry {type(item).__name__}")
    return found


def _repointed(entry: tuple) -> tuple:
    """One entry as it applies to the tree NOW, with any move recorded in its note."""
    mid, spec, old, new, test, expect, note, also = entry
    if not old and not new:
        return (mid, spec, old, new, test, NOT_MUTATED, note, also)
    move = REPOINTED.get(mid)
    if move is None:
        return entry
    path, _, scope = spec.partition("::")
    path, scope = move.get("path", path), move.get("scope", scope)
    moved = f"{path}::{scope}" if scope else path
    was = f"was {spec} {old!r} -> {new!r}"
    if "test" in move:
        was = f"was {spec} targeting {test}"
    test = move.get("test", test)
    return (mid, moved, move.get("old", old), move.get("new", new), test, expect,
            f"{note} [REPOINTED 2026-09-18: {move['why']}; {was}]".strip(), also)


def _conservative_digest(text: str) -> str:
    """``_code_digest`` as the OLDEST supported Python computes it.

    Copied in spirit from ``tests/test_mutation_harness.py``, and here for the same reason: before
    PEP 701 an f-string was ONE string token, so a mutation that only rewrites what is interpolated
    inside one changes executable tokens on 3.12+ and nothing at all on 3.11. Five entries of this
    population are exactly that -- a refusal MESSAGE mutated to the text the audit found misleading,
    killed by a test that reads the message -- so the population declares them rather than either
    dropping them or pretending they bite on every interpreter.
    """
    kept: list[str] = []
    depth = 0
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        name = tokenize.tok_name.get(token.type, "")
        if name == "FSTRING_START":
            depth += 1
            continue
        if name == "FSTRING_END":
            depth -= 1
            continue
        if depth:
            continue
        if token.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL,
                          tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            continue
        kept.append(token.string)
    return hashlib.sha256("\x00".join(kept).encode("utf-8")).hexdigest()[:16]


def _region(mg, spec: str):
    """``(whole text, the span a mutation searches)`` for one spec, as the harness reads it."""
    relative, _, scope = spec.partition("::")
    path = ROOT / relative
    if not path.is_file():
        raise LookupError(f"{relative} does not exist")
    text = path.read_bytes().decode("utf-8").replace(mg.CRLF, mg.LF)
    if not scope:
        return text, 0, len(text)
    low, high = mg._scope_span(text, scope)
    return text, low, high


def _check(entries: list[tuple]) -> tuple[list[str], list[str]]:
    """Every folded entry must describe the live tree exactly once, and change code.

    The same checks `tests/test_mutation_harness.py` makes on the pinned set, made HERE as well,
    because an entry that does not match is precisely the state R-67 is about: evidence that reads as
    verification and verifies nothing. The generator refuses to write rather than emit one.

    Returns ``(problems, entries that change code only on 3.12+)``.
    """
    sys.path.insert(0, str(ROOT / "tests"))
    import mutation_guards as mg  # noqa: PLC0415 - the harness is the reference implementation
    problems: list[str] = []
    fstring_only: list[str] = []
    for mid, spec, old, new, _test, expect, _note, also, _source in entries:
        if expect == NOT_MUTATED:
            continue
        conservative_moved = False
        for target_spec, target_old, target_new in ((spec, old, new), *also):
            try:
                text, low, high = _region(mg, target_spec)
            except LookupError as exc:
                problems.append(f"{mid}: {exc}")
                continue
            if text[low:high].count(target_old) != 1:
                problems.append(f"{mid}: {target_spec} matched {text[low:high].count(target_old)} times")
                continue
            mutated = text[:low] + text[low:high].replace(target_old, target_new) + text[high:]
            if mg._code_digest(text) == mg._code_digest(mutated):
                problems.append(f"{mid}: {target_spec} changes no code")
            if _conservative_digest(text) != _conservative_digest(mutated):
                conservative_moved = True
        if not conservative_moved:
            fstring_only.append(mid)
    return problems, fstring_only


def main() -> int:
    scripts = sorted(HERE.glob("batch*_mutations.py"))
    entries: list[tuple] = []
    seen: dict[str, str] = {}
    problems: list[str] = []
    for script in scripts:
        try:
            found = _entries_of(script)
        except Exception as exc:  # noqa: BLE001 - reported, never skipped silently
            problems.append(f"{script.name}: {exc}")
            continue
        if not found:
            problems.append(f"{script.name}: no MUTATIONS list")
            continue
        for entry in found:
            mid = entry[0]
            if mid in seen:
                problems.append(f"{mid}: declared in {seen[mid]} and in {script.name}")
                continue
            seen[mid] = script.name
            entries.append(_repointed(entry) + (script.stem,))
    found_problems, fstring_only = _check(entries)
    problems.extend(found_problems)
    if problems:
        print("PROBLEMS (nothing is written):")
        for line in problems:
            print("  ", line)
        return 1

    lines = [
        '"""Every batch guard mutation of the 2026-09-16 core re-audit, as data (I-30, R-67).',
        "",
        "GENERATED by benchmarks/core_v4_false_confidence/audit/fold_v4_population.py, and committed:",
        "the point of R-67 is that this evidence sat OUTSIDE the harness area the certificate pins, so a",
        "reader had to trust 55 scripts under benchmarks/ that nothing verified. Here every entry is",
        "checked on every FAST run by tests/test_mutation_harness.py -- it must still match the source it",
        "names, exactly once, and it must change CODE rather than a comment.",
        "",
        "Each entry is ``(id, spec, old, new, target_test, expect, note, also, source)``:",
        "",
        "* ``spec`` is ``path`` or ``path::scope``, read by mutation_guards._apply;",
        "* ``target_test`` is the ONE test whose failure counts as the kill. A mutation killed by anything",
        "  else is not evidence about the guard it names, which is R-67's other half;",
        "* ``expect`` is KILLED for every real guard, and SURVIVED only where a batch recorded, with its",
        "  reason, that one rule of a disjunction is not on its own what protects an invariant;",
        "* ``also`` carries the further edits a paired mutation applies together with the first.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "#: The `expect` of an entry that is NEVER APPLIED: one edits a JSON file, which the harness",
        "#: reports as MUTATION BROKE THE PARSE, and one edits only prose, which it reports as MUTATION",
        "#: CHANGED NO CODE. Both are carried with their batch's reason so that a reader does not have to",
        "#: wonder why the rule they name is unmutated, and both are marked so nothing tries to apply them.",
        'NOT_MUTATED = "NOT_MUTATED"',
        "",
        "#: The scripts folded here, in the order the round ran them.",
        "SOURCE_SCRIPTS = (",
    ]
    for script in scripts:
        lines.append(f'    "benchmarks/core_v4_false_confidence/audit/{script.name}",')
    lines += [")", "", "POPULATION_V4: tuple[tuple, ...] = ("]
    for mid, spec, old, new, test, expect, note, also, source in entries:
        lines.append("    (")
        for value in (mid, spec, old, new, test, expect, note):
            lines.append(f"        {value!r},")
        lines.append(f"        {also!r},")
        lines.append(f"        {source!r},")
        lines.append("    ),")
    lines += [
        ")",
        "",
        "#: The entries whose only effect is INSIDE an f-string, so they change executable tokens on",
        "#: Python 3.12+ (PEP 701) and nothing on 3.11. Each mutates a refusal MESSAGE to the text the",
        "#: audit found misleading and is killed by a test that reads the message, which is a real guard",
        "#: over a real finding -- and is informative only on the interpreter the formal round runs on.",
        "#: Declared rather than dropped, and checked by tests/test_mutation_population.py so the set",
        "#: cannot grow silently.",
        "FSTRING_ONLY_ON_3_12 = (",
        *[f"    {mid!r}," for mid in fstring_only],
        ")",
        "",
        "#: Order is semantic, exactly as it is for MUTATIONS: a shard is every position with",
        "#: ``position % count == index``, so a reordering moves mutations between shards.",
        "POPULATION_V4_IDS = tuple(entry[0] for entry in POPULATION_V4)",
        "",
    ]
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"wrote {OUT.relative_to(ROOT)}: {len(entries)} mutations from {len(scripts)} scripts")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
