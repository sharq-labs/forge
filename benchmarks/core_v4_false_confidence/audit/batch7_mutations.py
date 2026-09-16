"""Batch-7 guard mutations (I-10): each new guard removed as if it had never been written, in an ISOLATED copy.

Not in tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core
Freeze V4 round (I-30). The runner is ``isolated_mutations``, which fixes the R-67 defects of the batch-1..5
runners: a fresh copy per mutation and never the checkout, and KILLED only for a real test failure.

Run from the repository root, with SCRATCH pointing at a scratch directory::

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch7_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

EVIDENCE = "src/engcore/mcp/evidence.py"
SRIA = "src/engcore/sria/uncertainty.py"
BUDGET = "src/engcore/sria/assurance/uncertainty_budget.py"
PREDICTIVE = "src/engcore/uq/predictive.py"
T = "tests/mcp/test_core_scientific_audit_batch7.py"

_RULE = ("        if state not in _CONVERGENCE_STATES_THAT_FINISHED:\n"
         "            return CredibilityVerdict.INSUFFICIENT_EVIDENCE\n")
_RULE_OFF = "        if False:\n            return CredibilityVerdict.INSUFFICIENT_EVIDENCE\n"
_CHECK = "            + _convergence_checks(result)\n"
_CHECK_OFF = "            + ()\n"

MUTATIONS = [
    Mutation(
        "B7a", f"{EVIDENCE}::derive_verdict", _RULE, _RULE_OFF,
        f"{T}::test_r10_derive_verdict_reads_convergence_on_its_own",
        "R-10: the exported verdict function stops reading the solver's termination state"),
    Mutation(
        "B7b", f"{EVIDENCE}::CredibilityEvidenceReport.from_result", _CHECK, _CHECK_OFF,
        f"{T}::test_r10_the_downgrade_survives_a_payload_with_the_new_field_deleted",
        "R-10: the NOT_RUN check goes, so a payload with the additive field deleted re-derives SUPPORTED"),
    Mutation(
        "B7c", f"{EVIDENCE}::derive_verdict", _RULE, _RULE_OFF,
        f"{T}::test_r10_a_result_whose_solver_did_not_finish_is_never_supported",
        "R-10: BOTH halves removed -- the verdict rule and the check -- which is the audited behaviour "
        "exactly, so a DIVERGED result reports SUPPORTED again",
        also=((f"{EVIDENCE}::CredibilityEvidenceReport.from_result", _CHECK, _CHECK_OFF),)),
    Mutation(
        "B7d", f"{EVIDENCE}::CredibilityEvidenceReport.from_result",
        "            convergence=result.convergence,\n", "            convergence=None,\n",
        f"{T}::test_r10_the_convergence_state_is_in_the_report_and_its_json",
        "R-10: the report stops carrying the state, so a reader cannot see it"),
    Mutation(
        "B7e", f"{EVIDENCE}::CredibilityEvidenceReport.to_dict",
        '            **({} if self.convergence is None else {"convergence": self.convergence.value}),\n',
        '            **({} if True else {"convergence": self.convergence.value}),\n',
        f"{T}::test_r10_the_convergence_state_is_in_the_report_and_its_json",
        "R-10: the state is carried and then not serialized, so it is absent from the report JSON again"),
    Mutation(
        "B7f", f"{EVIDENCE}::CredibilityEvidenceReport.from_result",
        "            + tuple(result.models)\n"
        "            + tuple(_declared_model_keys(result, result.validity_not_assessed)),\n",
        "            ,\n",
        f"{T}::test_r40_a_provenance_override_cannot_drop_a_declared_model",
        "R-40: an override provenance narrows the inventory again"),
    Mutation(
        "B7g", f"{SRIA}::UncertaintyDeclaration.__post_init__",
        '            require_source_fits_channel(channel, value, where="uncertainty declaration")\n',
        "            pass\n",
        f"{T}::test_r43_a_numerical_estimate_may_not_be_declared_as_aleatoric_or_model_form",
        "R-43: a declaration files a NUMERICAL estimate under any channel again"),
    Mutation(
        "B7h", f"{BUDGET}::ChannelEntry.__post_init__",
        '            require_source_fits_channel(self.channel, self.uncertainty, where="uncertainty budget")\n',
        "            pass\n",
        f"{T}::test_r43_a_budget_channel_entry_refuses_a_contradictory_source",
        "R-43: the budget aggregates a contradictory source again"),
    Mutation(
        "B7i", SRIA,
        "        {UncertaintySource.UNSPECIFIED, UncertaintySource.MEASUREMENT}\n",
        "        {UncertaintySource.UNSPECIFIED, UncertaintySource.NUMERICAL}\n",
        f"{T}::test_r43_a_numerical_estimate_may_not_be_declared_as_aleatoric_or_model_form",
        "R-43: the map itself says a mesh estimate is aleatoric uncertainty"),
    Mutation(
        "B7j", f"{EVIDENCE}::CredibilityEvidenceReport.from_result",
        "            uncertainty=dict(result.uncertainty),\n", "            uncertainty={},\n",
        f"{T}::test_r43_the_report_carries_per_value_uncertainty_and_its_source",
        "R-43: from_result drops result.uncertainty again"),
    Mutation(
        "B7k", PREDICTIVE,
        "        source_kind=UncertaintySource.PARAMETER,\n",
        "        source_kind=UncertaintySource.UNSPECIFIED,\n",
        f"{T}::test_r43_the_v1_predictive_intervals_declare_what_they_are_of",
        "R-43: the V1 producer stops saying what its epistemic interval is of"),
    Mutation(
        "B7l", f"{SRIA}::UncertaintyDeclaration.unattributed_channels",
        "                    and UncertaintySource(record.source_kind) is UncertaintySource.UNSPECIFIED\n",
        "                    and False\n",
        f"{T}::test_r43_an_undeclared_source_is_recorded_as_unattributed_not_as_compatible",
        "R-43: an undeclared source stops being named as unattributed"),
]

#: The pinned mutations that target the files this batch changed, re-run under the isolated runner.
_CHANGED_FILES = (EVIDENCE, SRIA, BUDGET, PREDICTIVE)


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
    status = run(MUTATIONS, label="BATCH7", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH7_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 7 changed ---", flush=True)
    status |= run(existing, label="BATCH7_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH7_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
