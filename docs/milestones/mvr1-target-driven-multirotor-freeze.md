# MVR1 — Target-Driven Multirotor Study V0.1 freeze

Status: **PASS / FROZEN**

Milestone ID: `MVR1`

## Frozen identities

- Starting frozen checkpoint (MVR0 PASS/FROZEN): `f1409e474f554b17a83be6c73d5bdfdc8cefd0a5`
- MVR1 preregistration commit: `b329369d29b6661d4a3c587c4ede244adce3f093`
- Final MVR1 scientific implementation source tested before freeze record: `1112652ef44b6d795ba99a9ee80e64c24658fb85`
- Preregistration: `docs/mvr1-target-driven-multirotor-prereg.md`

The MVR1 preregistration remained **FROZEN BEFORE IMPLEMENTATION** and was not rewritten after observing tests, study results or adversarial review findings.

## Implementation and hardening history

| Commit | Content |
|---|---|
| `9a75af5359760f902071b5149b1430a692b98a8c` | initial MVR1 implementation |
| `6d3f594b6a9002d9656639be8aa7dcb3a70a2ae9` | study attribution hardening |
| `1112652ef44b6d795ba99a9ee80e64c24658fb85` | physical result attribution hardening |

## Scope actually delivered

MVR1 introduces an explicit **Study** layer above the frozen MVR0 multirotor vertical slice, so that the same design space and the same candidate population can be evaluated under different explicit target/operating conditions with separately attributable results.

Delivered behavior:

- explicit Study identity, including a deterministic study identity digest;
- explicit study operating conditions, including `payload_mass`, treated as physical inputs;
- explicit study target thresholds, treated as assessment-only;
- per-Study result, evaluation and run attribution over reused candidates and Candidate Twins;
- study attribution boundary enforcement;
- deterministic physical-consistency recomputation gate for result attribution;
- two canonical studies (Study A, Study B) executed over the same candidate population.

MVR1 remains an analytic **reference study layer** built on frozen MVR0 physics.

## Study A — canonical reproduction

Executed against `1112652ef44b6d795ba99a9ee80e64c24658fb85`:

- accepted candidates: `1000`;
- rejected proposals: `671`;
- reference-target pass count: `93`;
- global Pareto members: `26`;
- rotor-count distribution: `335 / 333 / 332` for `4 / 6 / 8` rotors.

Study identity:

`multirotor-study-v0.1:sha256:591616a4da0649b0894fa816c2dbe1d3741dd8ee3f02b73330d3a607a3e92279`

## Study B — observed result

- accepted candidates: `1000`;
- rejected proposals: `671`;
- reference-target pass count: `163`;
- global Pareto members: `28`;
- rotor-count distribution: `335 / 333 / 332` for `4 / 6 / 8` rotors.

Study identity:

`multirotor-study-v0.1:sha256:11493992e8da46864897d570759b91b181b748902da7a6773cd6a2be1f69c2e7`

## Important semantic result

- `payload_mass` is an **operating condition** and therefore changes the physics of an evaluation;
- target thresholds **assess** results but do not change physics;
- target failure does **not** imply scientific invalidity;
- target-failing but scientifically valid evaluations remain **D1 eligible**;
- Pareto construction uses the complete eligible universe, not the target-passing subset.

This is why Study A and Study B differ in target pass count and Pareto membership while sharing the same accepted/rejected population structure.

## Same Candidate / Twin reuse

Study A and Study B **intentionally** reuse:

- the same candidate IDs;
- the same candidate assignments;
- the same Candidate Twin references.

What differs by Study is:

- study identity;
- result attribution;
- evaluation attribution;
- run attribution.

Candidate reuse is a deliberate design property of the Study layer, not an attribution defect.

## Attribution adversarial history

- The original **cross-study metadata spoof** — forging study metadata on a result — was closed by the study attribution hardening commit `6d3f594b6a9002d9656639be8aa7dcb3a70a2ae9`.
- A stronger, **fully coherent Study-A-physics-as-Study-B spoof** was subsequently discovered: metadata alone was internally consistent, so metadata-level checks could not detect it.
- Physical attribution was then hardened by deterministic recomputation in `1112652ef44b6d795ba99a9ee80e64c24658fb85`.
- The previously successful spoof now **fails closed**.

## Physical consistency gate

`require_study_physical_consistency(...)` recomputes the frozen MVR0 physics for the claimed study operating conditions and checks:

- `total_mass`;
- `battery_mass`;
- `total_disk_area`;
- `disk_loading`;
- `ideal_induced_power`;
- `hover_electrical_power`;
- `hover_endurance`.

A result whose physics does not match its claimed Study is rejected.

## Deferred Core integrity debt

Two residual integrity concerns are acknowledged:

- same-reference altered `ScientificTwin` contents;
- same-reference altered `DesignSpace` contents.

These are **generic Core identity/integrity debt** for a future milestone.

They are explicitly **NOT** classified as MVR1-specific blockers and **MUST NOT** be patched inside MVR1. Any fix belongs in a successor Core identity/integrity milestone (e.g. content hashing of Twin and DesignSpace objects), not in the multirotor study layer.

## Known P3

Exact Pareto/archive construction remains `O(N^2)`.

This is carried forward as successor **scaling evidence**, not an MVR1 freeze blocker, and is unchanged in classification from MVR0.

## Targeted test gate

MVR1 targeted suite against implementation source `1112652ef44b6d795ba99a9ee80e64c24658fb85`:

- `25 passed`;
- `0 failed`;
- `0 errors`.

## Full regression gate

Full repository regression executed against exact implementation source `1112652ef44b6d795ba99a9ee80e64c24658fb85`.

Command:

```
py -m pytest -q --basetemp=.pytest_tmp_mvr1
```

Result:

- `1410 passed`;
- `0 failed`;
- `0 errors`;
- `4 warnings`;
- wall time: `581.68 s` (`0:09:41`).

The four warnings are the existing scikit-learn Gaussian-process `ConvergenceWarning` messages from `tests/test_smoke.py`; they are not MVR1 failures.

**A20 FULL REGRESSION = PASS.**

## Explicit nonclaims

MVR1 does **not** prove:

- CFD validation;
- FEA validation;
- motor-map validation;
- battery dynamic validation;
- structural validation;
- controls/stability validation;
- physical aircraft validation;
- certification;
- flight readiness;
- cryptographic authenticity of arbitrary Core scientific objects;
- autonomous scientific discovery;
- generic Study architecture;
- adaptive/Bayesian optimization;
- Design Memory;
- Generation 1;
- LLM scientific interpretation.

## Frozen boundary

MVR1 is **complete**.

It must not receive further polishing, refactoring into generic Study abstractions, additional hardening, or threat-model expansion unless a genuine scientific corruption issue is later demonstrated.

Future extensions — generic Study architecture, Core identity/integrity hashing, archive scaling work, adaptive generation, Design Memory — must be introduced through successor milestones rather than by rewriting MVR1 after observing downstream behavior.

## Frozen outcome

MVR1 is **PASS / FROZEN**.

The milestone demonstrates that the same frozen design space, candidate population and Candidate Twins can be studied under distinct explicit operating conditions and targets with separately attributable, physically verified results, while preserving the frozen distinction between scientific validity, D1 selection eligibility and target assessment.
