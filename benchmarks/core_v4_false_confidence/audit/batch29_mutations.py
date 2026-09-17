"""Batch-29 guard mutations (I-22 part D, R-48 finding 58: a spread converts by the slope): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch29_mutations
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
OR = "src/engcore/scientific/oracles.py"
T = "tests/test_core_scientific_audit_batch29.py"
RC = "tests/test_core_runtime_caches.py"

MUTATIONS = [
    # --- a spread is converted by the slope only ---------------------------
    Mutation(
        "B29a", f"{QU}::Quantity.magnitude_as_spread_in",
        "        return self.magnitude * (\n"
        "            _slope_against_base(self.units) / _slope_against_base(target)\n"
        "        )\n",
        "        return self.to(target).magnitude\n",
        f"{T}::test_r48_a_spread_can_be_read_against_an_offset_unit_without_the_backend_refusing",
        "the spread reader becomes the absolute reader, which is R-48 itself: the whole affine map applied "
        "to a difference, so 0.5 degC as a band is 273.65 kelvin. That is the number that let a prediction "
        "273 kelvin wrong pass a half-degree tolerance and earn EXPERIMENTALLY_VALIDATED. Repointed while running: it first named the delta-to-delta test, where `to` is already correct -- delta units are multiplicative, so only a pair involving an ABSOLUTE offset unit can tell the two readers apart"),
    Mutation(
        "B29b", f"{QU}::_slope_against_base",
        "    one = Quantity(1.0, canonical).magnitude_in(base)\n"
        "    zero = Quantity(0.0, canonical).magnitude_in(base)\n"
        "    return one - zero\n",
        "    return Quantity(1.0, canonical).magnitude_in(base)\n",
        f"{T}::test_r48_a_spread_can_be_read_against_an_offset_unit_without_the_backend_refusing",
        "the offset stops being subtracted, so the 'slope' of degC against kelvin is 274.15 rather than 1. "
        "Taking TWO points is the whole content of the rule -- an affine map's linear part is a "
        "difference of images, not an image. Repointed for the reason B29a was"),
    Mutation(
        "B29c", f"{QU}::Quantity.magnitude_as_spread_in",
        "        if target == self.units:\n            return self.magnitude\n",
        "        if False:\n            return self.magnitude\n",
        f"{T}::test_r48_a_ratio_scale_spread_is_the_plain_conversion_it_always_was",
        "EXPECTED SURVIVED, and the reason is the finding. The two slopes of one unit are the same "
        "float, so their quotient is exactly 1.0 in IEEE arithmetic and no test can distinguish the "
        "short-circuit from the division. It is kept for the reason `to` states at length -- a "
        "conversion to the unit already carried is not a conversion, and that is almost the only case, "
        "549 of 552 calls in one measured run -- which is a performance and exactness rule rather than "
        "a scientific guard. Recorded here so a reader does not mistake the survival for a hole",
        expect="SURVIVED"),
    # --- a spread must be on a ratio scale ---------------------------------
    Mutation(
        "B29d", f"{QU}::require_spread_unit",
        "    if not is_ratio_scale(canonical):\n",
        "    if False:\n",
        f"{T}::test_r48_a_spread_unit_whose_zero_is_a_convention_is_refused_by_name",
        "the guard the domains have had all along, and the generic core never did, goes again: '0.5 degC' "
        "as a tolerance is AMBIGUOUS -- a half-degree band, or the temperature 0.5 degC -- and a boundary "
        "that guesses is what this whole round is about"),
    # --- the backend's refusal is this package's error ---------------------
    Mutation(
        "B29e", f"{QU}::Quantity.to",
        "        except Exception as exc:\n"
        "            raise UnitCompatibilityError(\n"
        "                f\"cannot convert {self.units!r} to {target!r}: {exc}. The two \"\n",
        "        except ZeroDivisionError as exc:\n"
        "            raise UnitCompatibilityError(\n"
        "                f\"cannot convert {self.units!r} to {target!r}: {exc}. The two \"\n",
        f"{T}::test_r48_a_conversion_the_backend_refuses_is_this_packages_error",
        "pint's DimensionalityError escapes again. It is a TypeError, caught by nothing in this package, "
        "so the RIGHT declaration -- a Celsius band on a Celsius value -- died with an exception type the "
        "caller is not supposed to know about while the wrong one was accepted silently"),
    # --- an oracle tolerance is a difference -------------------------------
    Mutation(
        "B29f", f"{OR}::OracleObservation.__post_init__",
        "            require_spread_unit(\n"
        "                self.absolute_tolerance.units,\n"
        "                context=f\"oracle observation {metric!r} tolerance\",\n"
        "            )\n",
        "            pass\n",
        f"{T}::test_r48_an_oracle_tolerance_on_an_offset_scale_is_refused_at_declaration",
        "the rule exists and is not called at the one site R-48 names as the designed route to "
        "EXPERIMENTALLY_VALIDATED -- a rule written and not reached, which is the shape this round keeps "
        "finding"),
    Mutation(
        "B29g", f"{OR}::OracleObservation.__post_init__",
        "        if self.absolute_tolerance.magnitude < 0.0:\n",
        "        if self.absolute_tolerance.magnitude_in(self.expected.units) < 0.0:\n",
        f"{T}::test_r48_a_valid_band_on_an_expected_value_in_celsius_is_not_called_negative",
        "the sign is checked on the ABSOLUTELY converted magnitude again, so a perfectly good 0.5 kelvin "
        "band on an expected value in degC is -272.65 and is refused for being negative -- a message "
        "about a sign, for a value that is positive"),
    Mutation(
        "B29h", f"{OR}::OracleEvidenceSet.compare",
        "                tolerance = observation.absolute_tolerance.magnitude_as_spread_in(unit)\n",
        "                tolerance = observation.absolute_tolerance.magnitude_in(unit)\n",
        f"{T}::test_r48_no_spelling_of_a_half_degree_band_admits_a_273_kelvin_error",
        also=((f"{OR}::OracleObservation.__post_init__",
               "            require_spread_unit(\n"
               "                self.absolute_tolerance.units,\n"
               "                context=f\"oracle observation {metric!r} tolerance\",\n"
               "            )\n",
               "            pass\n"),),
        note="the comparison reads the band absolutely again. PAIRED with the declaration guard, "
        "because the two rules protect this invariant as a disjunction and the single-edit mutation "
        "SURVIVED: with the guard in place only a RATIO-scale unit reaches the comparison, and there "
        "the absolute reader and the spread reader agree exactly, the offset being zero. Remove both and "
        "a 0.5 degC band is admitted and read as 273.65 kelvin, which is the audited case"),
    Mutation(
        "B29i", f"{OR}::OracleEvidenceSet.compare",
        "                unit = base_unit(observation.expected.units)\n",
        "                unit = observation.expected.units\n",
        f"{T}::test_r48_the_physically_correct_declaration_does_not_crash_untyped",
        "the comparison happens on the expected value's own scale, so `residual_ratio` -- a RATIO -- is "
        "taken where zero is a convention, and a delta band must be converted into an absolute unit, "
        "which the backend refuses outright"),
    # --- the memo joins the enumerations ----------------------------------
    Mutation(
        "B29j", f"{QU}::clear_unit_caches",
        "    _slope_against_base.cache_clear()\n",
        "    pass\n",
        f"{RC}::test_clear_unit_caches_clears_every_memo_in_the_module",
        "a memo in front of the registry survives a clear -- the Sprint 7 defect, and the reason batch 26 "
        "made the populate block complete rather than leaving 'nothing was populated' as the floor"),
]

_CHANGED_FILES = (QU, OR)


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
    status = run(MUTATIONS, label="BATCH29", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH29_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 29 changed ---", flush=True)
    status |= run(existing, label="BATCH29_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH29_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
