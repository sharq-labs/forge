"""Batch-26 guard mutations (I-22 part A, R-75: the parse grammar and the delta refusal): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch26_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

QU = "src/engcore/scientific/units/quantity.py"
PB = "src/engcore/mcp/problem.py"
T = "tests/mcp/test_core_scientific_audit_batch26.py"
RC = "tests/test_core_runtime_caches.py"

MUTATIONS = [
    # --- a magnitude is a number -------------------------------------------
    Mutation(
        "B26a", f"{QU}::Quantity.__post_init__",
        "        if isinstance(self.magnitude, bool) or isinstance(self.magnitude, str):\n",
        "        if False:\n",
        f"{T}::test_r75_a_bool_is_not_a_magnitude",
        "R-75's constructor half restored exactly: `bool` is an `int`, so `Quantity(True, 'volt')` is one "
        "volt and a flag becomes a measurement nothing downstream can question"),
    Mutation(
        "B26b", f"{QU}::Quantity.__post_init__",
        "        if isinstance(self.magnitude, bool) or isinstance(self.magnitude, str):\n",
        "        if isinstance(self.magnitude, bool):\n",
        f"{T}::test_r75_a_string_is_not_a_magnitude",
        "only half the rule survives, and it is the half whose other half matters more: a `str` magnitude "
        "reintroduces at the constructor every expression the parse grammar refuses, with no unit half to "
        "check it against"),
    # --- whitespace means a declaration, not an expression -----------------
    Mutation(
        "B26c", f"{QU}::Quantity.parse",
        "            quantity = cls(_declared_magnitude(text, magnitude), unit.strip())\n"
        "            _require_the_magnitude_written_is_the_magnitude_parsed(text, quantity)\n"
        "            return quantity\n",
        "            try:\n"
        "                quantity = cls(_declared_magnitude(text, magnitude), unit.strip())\n"
        "            except (ValueError, UnitCompatibilityError):\n"
        "                quantity = None\n"
        "            if quantity is not None:\n"
        "                _require_the_magnitude_written_is_the_magnitude_parsed(text, quantity)\n"
        "                return quantity\n",
        f"{T}::test_r75_text_after_the_unit_is_not_folded_into_the_magnitude",
        also=((
            f"{QU}::Quantity.parse",
            "            _require_the_unit_is_a_unit_and_not_arithmetic(text, unit)\n",
            "            pass\n",
        ),),
        note="the audited MECHANISM restored exactly: the split's refusal is swallowed again and the whole "
        "string falls through to the backend's expression parser, so '5 volt 2' is 5 * volt * 2 = 10 volt. "
        "This is the mutation that matters most in the batch, because the defect was never a missing check "
        "-- it was a check whose refusal was caught and discarded. PAIRED with amendment 1's split-path call, "
        "because the two rules protect the trailing-junk family as a disjunction: the single-edit mutation "
        "SURVIVED, amendment 1 refusing '5 volt 1' on the text before the swallow could be reached"),
    Mutation(
        "B26d", f"{QU}::_declared_magnitude",
        "    if _DECIMAL_LITERAL.fullmatch(token) is None:\n",
        "    if False:\n",
        f"{T}::test_r75_a_magnitude_is_a_decimal_literal_and_not_an_expression",
        "the magnitude half becomes whatever `float()` will read, which is 'inf', 'nan', '1_0' and '0x10' "
        "-- and for '1/2' an uncaught ValueError, a boundary crash where a refusal belongs"),
    # --- the magnitude written is the magnitude parsed ---------------------
    Mutation(
        "B26e", f"{QU}::_require_the_magnitude_written_is_the_magnitude_parsed",
        "    if written is None:\n",
        "    if False:\n",
        f"{T}::test_r75_a_unit_with_no_magnitude_is_refused",
        "text stating no magnitude at all stops being refused, so 'volt' goes back to being one volt -- the "
        "exact mirror of the bare number this method already refused at the top, and for the same reason"),
    Mutation(
        "B26f", f"{QU}::_require_the_magnitude_written_is_the_magnitude_parsed",
        "    if float(written.group()) != quantity.magnitude:\n",
        "    if False:\n",
        f"{T}::test_r75_an_arithmetic_expression_is_not_a_declaration",
        also=(
            (f"{QU}::Quantity.parse",
             "            _require_the_unit_is_a_unit_and_not_arithmetic(text, unit)\n",
             "            pass\n"),
            (f"{QU}::Quantity.parse",
             "        _require_the_unit_is_a_unit_and_not_arithmetic(\n"
             "            text, raw[head.end():] if head is not None else raw\n        )\n",
             "        pass\n"),
        ),
        note="the identity goes, and with it the only rule covering the no-separator path -- which has to stay "
        "open for '5volt' and is therefore still the expression parser, so '2volt+3volt' writes 2 and "
        "returns 5. PAIRED with amendment 1's two call sites for the same reason as B26c: amendment 1's "
        "digit rule refuses every magnitude-changing spelling reachable today on the TEXT, so the identity "
        "is the second statement of one invariant and the single-edit mutation SURVIVED. Both are kept -- "
        "the digit rule is a syntactic proxy and the identity is the thing actually meant"),
    Mutation(
        "B26g", f"{QU}::Quantity.parse",
        "        quantity = cls(float(parsed.magnitude), str(parsed.units))\n"
        "        _require_the_magnitude_written_is_the_magnitude_parsed(text, quantity)\n"
        "        return quantity\n",
        "        return cls(float(parsed.magnitude), str(parsed.units))\n",
        f"{T}::test_r75_a_unit_with_no_magnitude_is_refused",
        "the identity is still implemented but no longer CALLED on the fallback path, which is the one path "
        "that needs it: a rule written and not reached is the shape this whole round is about"),
    # --- a difference unit is not an absolute value ------------------------
    Mutation(
        "B26h", f"{QU}::is_delta_unit",
        '            if stem.startswith("delta_"):\n                return True\n',
        "            if False:\n                return True\n",
        f"{T}::test_r75_the_difference_scales_have_a_name",
        "no unit is a difference unit any more, so the one place a caller's 'this is a span, not a point' "
        "is recorded stops being read and the boundary refusal below can never fire"),
    Mutation(
        "B26i", f"{QU}::is_delta_unit",
        "        for _prefix, stem, _suffix in registry().parse_unit_name(name):\n",
        "        for stem in (name,):\n",
        f"{T}::test_r75_the_difference_scales_have_a_name",
        "the name is sliced instead of parsed, so `millidelta_degree_Celsius` -- a thousandth of a Celsius "
        "difference, and still a difference -- reads as absolute. This is why the rule goes through the "
        "registry's own prefix parser and not `startswith`"),
    Mutation(
        "B26j", f"{PB}::_read_quantity",
        "    if is_delta_unit(quantity.units) != is_delta_unit(exemplar):\n",
        "    if False:\n",
        f"{T}::test_r75_a_delta_temperature_is_refused_where_an_absolute_one_is_required",
        "R-75's production half restored exactly: the dimension-only check passes '27 delta_degC' against a "
        "`kelvin` exemplar, and an MCP run solves at 27 K where the caller meant 300.15 K"),
    Mutation(
        "B26k", f"{PB}::_read_quantity",
        "    if is_delta_unit(quantity.units) != is_delta_unit(exemplar):\n",
        "    if is_delta_unit(exemplar) and not is_delta_unit(quantity.units):\n",
        f"{T}::test_r75_a_delta_temperature_is_refused_where_an_absolute_one_is_required",
        "the symmetric rule keeps only the half that refuses nothing today -- no `unit_exemplar` in this "
        "repository is a delta unit -- so the refusal becomes syntactically present and operationally dead"),
    # --- amendment 1: the unit half is a unit, not arithmetic --------------
    Mutation(
        "B26m", f"{QU}::_require_the_unit_is_a_unit_and_not_arithmetic",
        "    if any(character.isdigit() for character in residue):\n",
        "    if False:\n",
        f"{T}::test_r75_text_after_the_unit_is_not_folded_into_the_magnitude",
        "amendment 1's rule goes and the hole it closed reopens: the unit half is evaluated by the "
        "backend, so 'volt 1' and 'volt * 2 / 2' both normalise to 'volt', the net factor of one leaves "
        "the magnitude untouched, and the identity rule has nothing to notice"),
    Mutation(
        "B26n", f"{QU}::Quantity.parse",
        "        _require_the_unit_is_a_unit_and_not_arithmetic(\n"
        "            text, raw[head.end():] if head is not None else raw\n        )\n",
        "        pass\n",
        f"{T}::test_r75_text_after_the_unit_is_not_folded_into_the_magnitude",
        "the rule stays but stops being called on the no-separator path, which is the SAME expression "
        "parser: '5volt*1' scales by one and passes the identity untouched"),
    # --- the memo joins the clear ------------------------------------------
    Mutation(
        "B26l", f"{QU}::clear_unit_caches",
        "    is_delta_unit.cache_clear()\n",
        "    pass\n",
        f"{RC}::test_clear_unit_caches_clears_every_memo_in_the_module",
        "a memo in front of the registry survives a clear, which is the Sprint 7 defect the enumeration "
        "test was written for -- and the reason that test, not this list, is what keeps the clear complete"),
]

_CHANGED_FILES = (QU, PB)


def _existing():
    out = []
    for identifier, spec, old, new, attribution in M.MUTATIONS:
        if spec.partition("::")[0] not in _CHANGED_FILES:
            continue
        files = [word for word in attribution.replace(",", " ").split() if word.startswith("tests/")]
        if not files:
            continue
        out.append(Mutation(identifier, spec, old, new, files[0], f"pinned: {attribution}"))
    return out


def main() -> int:
    scratch = scratch_from_environment()
    status = run(MUTATIONS, label="BATCH26", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH26_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 26 changed ---", flush=True)
    status |= run(existing, label="BATCH26_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH26_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
