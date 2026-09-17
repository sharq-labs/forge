"""Batch-17 guard mutations (I-03 part A, the study routes through the V2 gates): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch17_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

CS = "src/engcore/studies/calibration_study.py"
AD = "src/engcore/adequacy/predictive.py"
UQ = "src/engcore/uq/predictive.py"
T = "tests/test_core_scientific_audit_batch17.py"
TH = "tests/inference/test_tcr_heldout_uq.py"
TR = "tests/inference/test_reproducibility_and_evidence.py"

MUTATIONS = [
    Mutation(
        "B17a", f"{CS}::_routed",
        "        observations=calibration, forward=forward,\n",
        "        observations=None, forward=None,\n",
        f"{T}::test_r02_a_box_that_truncates_the_posterior_yields_no_predictive_interval",
        "R-02, the audited case: the study hands the V2 record no evidence, so every gate that needs the "
        "observations and the forward model is skipped and a box over the mean +/- 0.6 sd is answered again"),
    # Repointed. The first draft of these two RENAMED `_routed` and its call site together, which
    # changes two identifiers and no behaviour -- the runner's own "MUTATION CHANGED NO CODE" refusal
    # does not catch a rename, and both survived, correctly. What has to be mutated is the EVIDENCE
    # each call site hands the judgement, which is the decision that site owns; the two sites are
    # told apart by their indentation as well as by their scope.
    Mutation(
        "B17b", f"{CS}::predict_held_out",
        "            calibration=split.calibration, forward=forward,\n",
        "            calibration=None, forward=None,\n",
        f"{T}::test_r02_a_box_that_truncates_the_posterior_yields_no_predictive_interval",
        "the predictive call site hands the judgement no evidence, so every gate that needs the observations "
        "and the forward model is skipped and the record is merely DOWNGRADED instead of refused"),
    Mutation(
        "B17c", f"{CS}::validate_held_out",
        "        calibration=split.calibration, forward=forward,\n",
        "        calibration=None, forward=None,\n",
        f"{T}::test_r02_a_box_that_truncates_the_posterior_yields_no_held_out_verdict",
        "R-02: the held-out call site hands the judgement no evidence, which is where a truncated box and a "
        "misfit calibration both used to pass"),
    Mutation(
        "B17d", f"{CS}::predict_held_out",
        "                route_claim=routed.route_claim.value,\n",
        '                route_claim="",\n',
        f"{T}::test_r02_a_predictive_decomposition_carries_its_route_claim_and_reasons",
        "the predictive record stops saying what claim it earned, so a downgrade reaches no reader"),
    Mutation(
        "B17e", f"{CS}::validate_held_out",
        "        route_claim=routed.route_claim.value,\n",
        '        route_claim="",\n',
        f"{T}::test_r02_held_out_metrics_carry_the_route_claim_and_reasons",
        "the held-out metrics stop saying what claim the statements behind the verdict earned"),
    Mutation(
        "B17f", f"{CS}::validate_held_out",
        "        reasons=tuple(reason.value for reason in routed.reasons),\n",
        "        reasons=(),\n",
        f"{T}::test_r02_the_claim_names_the_prediction_domain_it_cannot_yet_show",
        "the reasons are dropped, so PREDICTION_DOMAIN_NOT_DECLARED -- the one thing this batch can honestly "
        "say about the prediction domain -- is silence again"),
    Mutation(
        "B17g", f"{AD}::assess_predictive_observation",
        "        finding = (grid_prior_uniformity(posterior, None) or grid_containment(posterior, None))\n",
        "        finding = None\n",
        f"{T}::test_r02_an_assessment_over_a_truncating_grid_is_not_content_bound",
        "R-02 (finding 33) exactly: a box truncating the posterior to 0.34x is content-bound again, and the "
        "comparison names a preferred model on a 6.259-nat difference the honest box puts at 2.872"),
    Mutation(
        "B17h", f"{AD}::assess_predictive_observation",
        "        if finding is not None:\n",
        "        if False:\n",
        f"{T}::test_r02_an_assessment_over_a_truncating_grid_is_not_content_bound",
        "the finding is computed and ignored, which is the shape of every guard this round is about"),
    Mutation(
        "B17i", f"{UQ}::posterior_predictive_uq",
        "        conditions_not_checked=tuple(spec.conditions),\n",
        "        conditions_not_checked=(),\n",
        f"{T}::test_r02_the_frozen_predictive_records_the_conditions_it_ignores",
        "R-02 (finding 81): the frozen predictive goes back to ignoring a declared condition silently, so a "
        "spec saying T = 5000 K is answered without comment"),
    Mutation(
        "B17j", f"{CS}::run_coverage_study",
        "        except HybridUQError as refused:\n",
        "        except ZeroDivisionError as refused:\n",
        f"{TR}::test_the_coverage_study_is_a_function_of_its_seed_schedule",
        "a repetition the V2 judgement refuses kills the whole coverage study again -- the sweep is FAIL_FAST "
        "and a goodness-of-fit gate refuses well-specified repetitions at its own false-refusal rate"),
    Mutation(
        "B17k", f"{CS}::run_coverage_study",
        "    if refused:\n",
        "    if False:\n",
        f"{T}::test_r02_the_coverage_study_records_a_refused_repetition_and_says_the_number_is_conditional",
        "the study stops saying that its coverage fraction is conditional on the repetitions a gate routed, "
        "which is the selection effect its own lost-repetition guard was written against"),
    Mutation(
        "B17l", f"{CS}::_routed",
        "        confidence_level=credible_mass,\n",
        "        confidence_level=0.95,\n",
        f"{T}::test_r02_the_routed_record_honours_the_declared_credible_mass",
        "the routed record ignores the study's declared credible mass, so every interval is a 95 % one "
        "whatever was asked for -- the control that routing did not drop an argument"),
]

_CHANGED_FILES = (CS, AD, UQ)


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
    status = run(MUTATIONS, label="BATCH17", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH17_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 17 changed ---", flush=True)
    status |= run(existing, label="BATCH17_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH17_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
