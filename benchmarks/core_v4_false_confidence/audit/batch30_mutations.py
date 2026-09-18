"""Batch-30 guard mutations (I-22 part E, R-48 finding 99: every declared spread): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch30_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

CN = "src/engcore/scientific/ir/constraints.py"
GR = "src/engcore/inference/grid.py"
SP = "src/engcore/inference/split.py"
UQ = "src/engcore/uq/predictive.py"
T = "tests/test_core_scientific_audit_batch30.py"

MUTATIONS = [
    # --- every declared spread states a spread unit ------------------------
    Mutation(
        "B30a", f"{CN}::ConstraintDefinition.__post_init__",
        "                require_spread_unit(\n"
        "                    self.tolerance.units, context=f\"constraint {name!r} tolerance\"\n"
        "                )\n",
        "                pass\n",
        f"{T}::test_r48_a_constraint_tolerance_on_an_offset_scale_is_refused_at_declaration",
        "R-48's constraint half restored exactly: a '2 degC' tolerance on a 358.15 kelvin bound is "
        "accepted and read as 275.15 kelvin, so a 600 kelvin reading SATISFIES a 358.15 kelvin limit and "
        "the check reports a 33.3 kelvin margin to prove it"),
    Mutation(
        "B30b", f"{GR}::GaussianObservation.__post_init__",
        "            require_spread_unit(\n"
        "                self.sigma.units,\n"
        "                context=f\"observation {self.condition_id}:{self.observable_name} sigma\",\n"
        "            )\n",
        "            pass\n",
        f"{T}::test_r48_an_observation_sigma_on_an_offset_scale_is_refused_at_declaration",
        "R-48's likelihood half: a '0.5 degC' sigma on a 300 kelvin reading is read as 273.65 kelvin, so "
        "the chi-squared of a 50 kelvin misfit is 0.033 instead of 10000 -- and every goodness-of-fit, "
        "containment and near-duplicate test computed on it is measuring nothing at all"),
    Mutation(
        "B30c", f"{UQ}::PredictiveObservableSpec.__post_init__",
        "                require_spread_unit(\n"
        "                    self.observation_sigma.units,\n"
        "                    context=f\"predictive noise {key}\",\n"
        "                )\n",
        "                pass\n",
        f"{T}::test_r48_a_predictive_observation_sigma_on_an_offset_scale_is_refused_at_declaration",
        "the predictive spec goes back to STORING a 273.65 kelvin sigma for a declared half-degree one, "
        "so every interval the predictive layer builds from it is meaningless and the record a reader "
        "checks it against agrees with itself"),
    # --- a positivity check is on the magnitude as declared ----------------
    Mutation(
        "B30d", f"{CN}::ConstraintDefinition.__post_init__",
        "            if self.tolerance.magnitude < 0.0:\n",
        "            if self.tolerance.to(self.bound.units).magnitude < 0.0:\n",
        f"{T}::test_r48_a_valid_tolerance_on_a_celsius_bound_is_not_called_negative",
        "the sign is read off the absolutely converted magnitude again, so a perfectly good 2 kelvin "
        "tolerance on an 85 degC bound is -271.15 and is refused for being negative -- a message about a "
        "sign, for a value that is positive"),
    Mutation(
        "B30e", f"{GR}::GaussianObservation.__post_init__",
        "        if self.sigma.magnitude <= 0.0:\n",
        "        if self.sigma.magnitude_in(self.value.units) <= 0.0:\n",
        f"{T}::test_r48_a_valid_sigma_on_a_celsius_value_is_not_called_non_positive",
        "the same defect for a sigma, in the direction that costs a valid declaration rather than "
        "admitting an invalid one: a 0.5 kelvin sigma on a 26.85 degC reading converts to -272.65 and is "
        "refused as non-positive"),
    # --- every conversion of a declared spread is a spread conversion ------
    Mutation(
        "B30f", f"{CN}::ConstraintDefinition.check",
        "            self.tolerance.magnitude_as_spread_in(self.bound.units)\n",
        "            self.tolerance.to(self.bound.units).magnitude\n",
        f"{T}::test_r48_the_physically_correct_declarations_work",
        "the tolerance is read absolutely in the check. With the declaration guard in place only a ratio "
        "scale reaches here, where the two readers agree -- EXCEPT against an offset BOUND, where the "
        "absolute reader has no conversion at all and raises. That is the case the guard cannot cover, "
        "and it is the physically correct declaration"),
    Mutation(
        "B30g", f"{GR}::ObservationSet.numeric_vectors",
        "            [item.sigma.magnitude_as_spread_in(item.value.units) for item in self.observations],\n",
        "            [item.sigma.magnitude_in(item.value.units) for item in self.observations],\n",
        f"{T}::test_r48_the_physically_correct_declarations_work",
        "the same, for the likelihood's sigma vector: a delta_degC sigma against a degC value is a "
        "conversion the backend refuses, so the right declaration cannot be used"),
    Mutation(
        "B30h", f"{SP}::observation_content_digest",
        "    sigma = abs(observation.sigma.magnitude_as_spread_in(unit))\n",
        "    sigma_in_value_unit = observation.sigma.magnitude_in(observation.value.units)\n"
        "    upper = Quantity(observation.value.magnitude + sigma_in_value_unit, observation.value.units)\n"
        "    sigma = abs(upper.magnitude_in(unit) - value)\n",
        f"{T}::test_r48_the_split_content_digest_reads_a_sigma_as_a_difference",
        "the hand-written two-point trick comes back, and with it the half it did not correct: it fixed "
        "the value-unit-to-base step and read the sigma's OWN declared unit absolutely, so the same "
        "measurement written on two scales digests differently and a duplicate crosses the split unseen"),
    Mutation(
        "B30i", f"{UQ}::PredictiveObservableSpec.__post_init__",
        "            sigma_unit = self.unit if is_ratio_scale(self.unit) else base_unit(self.unit)\n",
        "            sigma_unit = self.unit\n",
        f"{T}::test_r48_the_physically_correct_declarations_work",
        "an observable declared on an offset scale tries to store its spread in an absolute unit, which "
        "cannot carry one: the conversion raises, so a degC observable can declare no noise at all"),
    # --- a reported margin is on a scale that can carry a difference -------
    Mutation(
        "B30j", f"{CN}::ConstraintDefinition.check",
        "        margin_unit = (\n"
        "            self.bound.units\n"
        "            if is_ratio_scale(self.bound.units)\n"
        "            else base_unit(self.bound.units)\n"
        "        )\n",
        "        margin_unit = self.bound.units\n",
        f"{T}::test_r48_a_reported_margin_is_a_difference_and_not_an_absolute_value",
        "a twelve-degree margin under an 85 degC limit is labelled `12.0 degree_Celsius` again, and every "
        "consumer that converts it reads 285.15 kelvin. The check's own number is right and its unit "
        "makes it wrong, which is the hardest kind of record to doubt"),
    Mutation(
        "B30k", f"{CN}::ConstraintDefinition.check",
        "            margin=Quantity(\n"
        "                Quantity(margin, self.bound.units).magnitude_as_spread_in(margin_unit),\n"
        "                margin_unit,\n"
        "            ),\n",
        "            margin=Quantity(margin, margin_unit),\n",
        f"{T}::test_r48_a_reported_margin_is_a_difference_and_not_an_absolute_value",
        "the margin's unit is corrected and its MAGNITUDE is not carried across, so on a Fahrenheit bound "
        "the number would be a Fahrenheit difference labelled kelvin -- a relabelling, which is worse "
        "than the original because it looks canonical"),
]

_CHANGED_FILES = (CN, GR, SP, UQ)


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
    status = run(MUTATIONS, label="BATCH30", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH30_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 30 changed ---", flush=True)
    status |= run(existing, label="BATCH30_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH30_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
