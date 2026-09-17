"""Batch-44 guard mutations (I-28 part A, R-59): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch44_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

A = "src/engcore/uq/admission.py"
T = "tests/test_core_scientific_audit_batch44.py"

MUTATIONS = [
    Mutation(
        "B44a", f"{A}::PredictiveAdmissionAudit.__post_init__",
        "        if self.maximum_unsupported_mass > MAXIMUM_CONDITIONED_UNSUPPORTED_MASS:\n",
        "        if False:\n",
        f"{T}::test_r59_a_budget_that_would_condition_most_of_the_posterior_away_is_refused",
        "R-59 restored: any finite non-negative budget is declarable again, so a budget of 1.0 conditions "
        "away 99.9997% of a posterior and renormalizes by 3.4e5 -- and the record it hands on is called a "
        "posterior for the same question"),
    Mutation(
        "B44b", f"{A}",
        "MAXIMUM_CONDITIONED_UNSUPPORTED_MASS = 0.05\n",
        "MAXIMUM_CONDITIONED_UNSUPPORTED_MASS = 1.0\n",
        f"{T}::test_r59_the_core_declares_a_maximum_budget",
        "the maximum becomes the audited budget itself, which is the same defect with a constant in front "
        "of it: a cap that admits discarding the whole posterior is not a cap"),
    Mutation(
        "B44c", f"{A}",
        "MAXIMUM_CONDITIONED_UNSUPPORTED_MASS = 0.05\n",
        "MAXIMUM_CONDITIONED_UNSUPPORTED_MASS = 1.0e-13\n",
        f"{T}::test_r59_a_budget_inside_the_maximum_still_works",
        "the cap goes below the budget both in-repo callers declare (1e-12), so the module refuses every "
        "conditioning anybody actually asks for. The control: a rule nobody can satisfy is not a rule"),
    Mutation(
        "B44d", f"{A}::condition_posterior_on_predictive_admission",
        '            dataset_id=f"{posterior.dataset_id}|predictive-admitted:{identity}",\n',
        "            dataset_id=posterior.dataset_id,\n",
        f"{T}::test_r59_a_conditioned_posterior_does_not_claim_the_datasets_identity",
        "R-59 as audited: the conditioned posterior claims the dataset identity of the unconditioned fit, "
        "so a truncated record travels as the posterior for the data -- and the dataset id is the field "
        "every downstream route reads to decide what a posterior is about"),
    Mutation(
        "B44e", f"{A}::condition_posterior_on_predictive_admission",
        "        conditioned_log_likelihood[rejected] = -np.inf\n",
        "        pass\n",
        f"{T}::test_r59_the_conditioned_record_states_the_conditioning_and_reports_its_support",
        "AMENDED (amendment 1): the preregistered rule narrowed the admissible mask, and that WEAKENED the "
        "certified guard G32d -- HUQ-04 holds weights to the likelihood over `mask & isfinite(...)`, so a "
        "node taken out of the mask is taken out of the rule. The mask stays, and this mutation is the one "
        "that matters: a rejected node keeps a finite likelihood while its weight is zero, which is two "
        "arrays describing two different posteriors"),
    Mutation(
        "B44f", f"{A}::ConditionedPosterior.__post_init__",
        "            if carried != expected:\n",
        "            if False:\n",
        f"{T}::test_r59_an_audit_cannot_be_recombined_with_another_posterior",
        "the audit and the posterior come apart again: a record saying 1e-12 of the mass was discarded can "
        "travel beside one conditioned by 3.4e5"),
    Mutation(
        "B44g", f"{A}::ConditionedPosterior.__post_init__",
        "        if self.audit.conditional_on_predictive_admission:\n",
        "        if True:\n",
        f"{T}::test_r59_an_unconditioned_pair_is_still_a_valid_pair",
        "the digest is demanded of a pass-through too, where nothing was conditioned and there is nothing "
        "to bind. The control for the rule above"),
    Mutation(
        "B44h", f"{A}::condition_posterior_on_predictive_admission",
        "            conditioned_weights_digest(conditioned) if unsupported_mass > 0.0 else \"\"\n",
        "            \"\"\n",
        f"{T}::test_r59_the_audit_carries_the_digest_of_the_weights_it_describes",
        "the binding is computed nowhere, so the field exists and is always empty -- a rule written and not "
        "reached, which is the shape this round keeps finding"),
]

_CHANGED_FILES = (A,)


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
    status = run(MUTATIONS, label="BATCH44", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH44_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 44 changed ---", flush=True)
    status |= run(existing, label="BATCH44_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH44_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
