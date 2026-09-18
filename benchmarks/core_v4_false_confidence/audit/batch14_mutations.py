"""Batch-14 guard mutations (I-11, the operating-point binding made load-bearing): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch14_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

DEF = "src/engcore/scientific/models/definition.py"
RES = "src/engcore/scientific/results/result.py"
EV = "src/engcore/mcp/evidence.py"
DC = "src/engcore/domains/derived_context.py"
EL = "src/engcore/domains/electrical/dc/models.py"
CP = "src/engcore/domains/battery/coupling.py"
T = "tests/test_core_scientific_audit_batch14.py"
BC = "tests/domains/battery/test_battery_coupling.py"

MUTATIONS = [
    # --- R-09: the binding is enabled where the verdict is formed ---
    Mutation(
        "B14a", f"{DC}::DomainValidityContext.assess",
        "    def assess(self, model: Any, *, record_values: bool = True) -> Any:\n",
        "    def assess(self, model: Any, *, record_values: bool = False) -> Any:\n",
        f"{T}::test_r09_the_derived_context_records_its_operating_point_by_default",
        "R-09: the domains' own helper goes back to the frozen method's default, so every domain that "
        "assesses through it records nothing and CORE-014 loops over an empty mapping"),
    Mutation(
        "B14b", f"{DEF}::ScientificModelDefinition.assess_validity",
        "        return replace(assessment, model_id=self.model_id, model_version=self.version)\n",
        "        return assessment\n",
        f"{T}::test_r50_an_assessment_filed_under_another_model_is_refused",
        "R-50: the model API stops naming the model it assessed, so an assessment filed under any declared "
        "key at all is accepted"),
    Mutation(
        "B14c", f"{EV}::ModelValidityRecord.__post_init__",
        '            evaluated=dict(getattr(self.assessment, "evaluated", {}) or {}),\n',
        "            evaluated={},\n",
        f"{T}::test_r09_the_report_keeps_the_operating_point",
        "R-09 (finding 46), the audited case exactly: the credibility boundary drops the operating point "
        "while rebuilding the assessment, so both production MCP tools form their verdict without it"),
    Mutation(
        "B14d", f"{EV}::CredibilityEvidenceReport.__post_init__",
        "        self._require_assessments_at_this_operating_point()\n",
        "",
        f"{T}::test_r09_the_report_refuses_a_supplied_assessment_made_at_another_operating_point",
        "R-09 (finding 46): from_result(validity=...) accepts an assembler-supplied record and never checks "
        "it against its own provenance, which is the route both production assemblers take"),
    Mutation(
        "B14e", f"{EV}::CredibilityEvidenceReport._require_assessments_at_this_operating_point",
        "                if name in inputs and not _same_operating_point(value, inputs[name]):\n",
        "                if name in inputs and False:\n",
        f"{T}::test_r09_the_report_refuses_a_supplied_assessment_made_at_another_operating_point",
        "R-09: the report-side comparison is made unconditionally true, so a disagreement is read as "
        "agreement"),
    Mutation(
        "B14f", f"{EV}::CredibilityEvidenceReport.unbound_assessment_values",
        "            if name not in inputs\n",
        "            if False\n",
        f"{T}::test_r09_the_report_records_the_names_its_provenance_cannot_bind",
        "R-09 (finding 80): the report stops saying which recorded names its provenance could not bind, so "
        "59 of 77 derived condition names go back to being silence that reads as agreement"),
    Mutation(
        "B14g", f"{EL}::assess_kcl_validity",
        "        declared={}, assembled=kcl_validity_context(), record_values=True\n",
        "        declared={}, assembled=kcl_validity_context()\n",
        f"{T}::test_r09_the_production_electrical_assessments_record_their_operating_point",
        "R-09 (finding 45): a production assessment site stops setting the flag, which is the state the "
        "re-audit found the whole tree in"),
    # --- R-50: the assessment is about a stated model, over stated conditions ---
    Mutation(
        "B14h", f"{DEF}::ValidityDomain.assess",
        "            declared_conditions=tuple(condition.name for condition in self.conditions),\n",
        "            declared_conditions=(),\n",
        f"{T}::test_r50_the_domain_records_the_conditions_it_decided",
        "R-50: the domain stops recording which conditions it decided, so nothing downstream has anything "
        "to compare a condition list against"),
    Mutation(
        "B14i", f"{RES}::ScientificResult._checked_validity",
        "            self._require_assessment_is_about_this_model(key, versions[key], assessment)\n",
        "",
        f"{T}::test_r50_an_assessment_over_conditions_the_model_does_not_have_is_refused",
        "R-50, the audited case exactly: satisfied=('anything_at_all',) is accepted by ScientificResult, "
        "round-trips, and reaches Experiment.best, the inference admission gate and validity_of"),
    Mutation(
        "B14j", f"{RES}::ScientificResult._require_assessment_is_about_this_model",
        "        if stray or missing:\n",
        "        if False:\n",
        f"{T}::test_r50_an_assessment_that_leaves_a_declared_condition_out_is_refused",
        "R-50: an assessment that omits a condition its own domain decided is accepted -- the violated ones "
        "are exactly what an omission hides"),
    Mutation(
        "B14k", f"{RES}::ScientificResult._require_assessment_is_about_this_model",
        "        if assessment.model_version and assessment.model_version != version:\n",
        "        if False:\n",
        f"{T}::test_r50_an_assessment_whose_version_is_not_the_declared_one_is_refused",
        "R-50: a verdict about another version of the model answers for this one, which the result's own "
        "one-version rule says is two claims"),
    Mutation(
        "B14l", f"{RES}::ScientificResult._require_assessment_is_about_this_model",
        "        if repeated:\n",
        "        if False:\n",
        f"{T}::test_r50_an_assessment_that_reports_one_condition_twice_is_refused",
        "R-50: a condition in two lists is accepted, so one name can be both satisfied and unknown and the "
        "count still accounts for the domain"),
    Mutation(
        "B14m", f"{DEF}::ValidityAssessment.__post_init__",
        "        if self.model_version and not self.model_id:\n",
        "        if False:\n",
        f"{T}::test_r50_a_version_without_a_model_id_is_refused_on_the_assessment_itself",
        "R-50: a version with no model id is accepted, and a version on its own names nothing the result "
        "can compare it with"),
    Mutation(
        "B14n", f"{DEF}::ValidityAssessment.to_dict",
        '            **({"declared_conditions": list(self.declared_conditions)} if self.declared_conditions else {}),\n',
        "",
        f"{T}::test_r50_the_new_keys_round_trip_and_are_written_only_when_present",
        "R-50: the conditions the domain decided stop crossing the record boundary, so the check stops at "
        "the first serialization"),
    # --- the interval verdict, which is where the new field had to be narrowed ---
    Mutation(
        "B14o", f"{CP}::_over_the_step",
        "                if name in other and _same_operating_point(value, other[name])\n",
        "                if name in other\n",
        f"{BC}::test_a_coupled_run_and_a_standalone_assessment_agree_at_the_same_point",
        "an interval verdict claims the first instant's value for a name that MOVED within the step, so a "
        "result carrying the other end would be refused for agreeing with itself"),
]

_CHANGED_FILES = (DEF, RES, EV, DC, EL, CP)


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
    status = run(MUTATIONS, label="BATCH14", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH14_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 14 changed ---", flush=True)
    status |= run(existing, label="BATCH14_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH14_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
