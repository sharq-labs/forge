# M1C/M1D model discovery compatibility proposal — owner approval required

2026-10-18. Static inspection only; discovery/imports/tests NOT RUN.
M1C Draft#166 introduces model20; M1D constructs no additional scientific model.
No pinned guard, frozen manifest, certificate or expected count changed here.
This proposal is not approval and does not establish integration readiness.

## Exact population impact if mandatory imports succeed

| Guard/population | Current pin/baseline | M1C/M1D delta | Expected intended tree | Exact reference / reason |
| --- | --- | --- | --- | --- |
| MODELS / EXPECTED_MODELS | 19 | +1 | 20 | tests/test_core_guards.py:154-181 discovers ScientificModelDefinition instances by module walk; :199 pins19; :534 asserts exact count |
| New key | absent | thermal.conduction1d.transient_piecewise_linear@0.1.0 | one unique key | conduction1d_transient_fv.py MODEL; walk deduplicates value.key, so aliases/imports do not multiply count |
| RESERVING / EXPECTED_RESERVING_MODELS | 16 | +0 | 16 | :187 selects m.derived_quantities; :200 pins16; :535 checks; new model reserves no derived quantities |
| Condition names / EXPECTED_CONDITION_NAMES | 96 | +0 | 96 | :226 pin; :541,:543 sum len(validity.context_keys); new ValidityDomain has no conditions, context_keys empty |
| Reserved names / EXPECTED_RESERVED_NAMES | 63 | +0 | 63 | :227 pin; :542,:544 sum derived_quantities; new model contributes empty set |
| Domain set | electrical, thermal, battery, kinetics | +0 | same set | :538-539; new domain is already-present thermal |
| MODEL_IDS |19 model keys | +1 |20 model keys | :186 drives MODELS-parameterized guards, including condition classification :550 and unreserved assembly :617 |
| RESERVING_IDS |16 reserving keys | +0 |16 reserving keys | :188; reserved-name/forgery/serialization cases stay unchanged |
| ScientificSolver population | EXPECTED_SOLVER_CLASSES11 | +0 |11 | :1318,:1323; new provider derives NumericalProvider, not ScientificSolver; driver/backend are neither |
| Registry union of reserved names | existing set | +0 | same set | :645 onward; no new reserved quantity or condition classification |

These are static deltas, not observed counts or passing guards. In the intended
importable tree, the exact-model-census test fails at its 19-vs20 assertion; later
assertions in that SAME function are not reached after failure. Parametrized guards
still collect against the expanded model list. No test may be skipped/suppressed.
Empty applicability conditions are UNKNOWN, not globally applicable or validated.

## Import failure control plane

Actual MODEL_DISCOVERY_FAILURES (line53) and optional absence contents remain UNKNOWN here. _classify_import_failure
(line130) records all failures except genuine ModuleNotFoundError names belonging to
pyproject-declared optional groups. _every_model (154 onward) records failed imports
instead of silently shrinking the census. test_the_only_modules_the_walk_lost_are_
declared_optional_ones (230 onward) additionally checks optional-skipped files cannot
construct ScientificModelDefinition/ScientificSolver and tests classifier strictness.
The exact-count guard first asserts no MODEL_DISCOVERY_FAILURES at529-533; a broken
import therefore fails BEFORE the count. ScientificSolver census repeats failure
refusal at1322. None of these guards are changed.

SciPy>=1.11 is mandatory (pyproject.toml:9). New M1C sparse provider imports the private
SuperLU extension; absence/API/load error is not an excused optional loss. New M1D
backend imports existing strict CheckpointSeal and M1C; a propagated failure remains
fatal under existing classifier rules. Compile-only success proves syntax, not import
success, backend availability or an empty failure dictionary. Do not invent an exact
runtime failure list without running the authorized sweep. Dependency/import behavior
on supported interpreters must be recorded during later execution.

## Proposed approval and execution sequence

1. Owner explicitly approves adding the separate unvalidated transient model and the
   intentional census19 ->20. Keep reserving16/condition96/reserved63/domain and solver11
   pins unchanged unless executed/static evidence independently identifies another change.
2. Make the count/comment change in tests/test_core_guards.py as an explicit reviewed
   certified-area compatibility change on the selected integration tree. Do not weaken
   exact equality, catch failures, omit modules, regenerate frozen references, alter
   classification or hide the model in a lazy factory.
3. Separately authorize targeted model/parent/M1D tests. Record exact commands, resulting
   populations, every import failure and all numerical/adversarial failures in PROGRESS.
   Failures remain failures; do not retune thresholds or scientific expectations for PASS.
4. Run required integration and certified dependency checks under separately authorized
   policy; owner selects the exact integrated HEAD and handles OD-3 recertification.
   A certificate for an earlier parent or static PASS is not certification of the stack.
5. Only executed contextual evidence can support M1 acceptance, capability maturity or
   integration. This build remains IMPLEMENTED / UNVERIFIED / UNCERTIFIED and INTEGRATION HOLD.

No approval is inferred and no requested pin edit is performed in M1D.
