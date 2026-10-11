# FORGE Genesis — Blind Scientific Rediscovery Benchmark

Status: **design / preregistration**
Owner intent: validate the FORGE Discovery Runtime by rediscovering established physical mechanisms under controlled information constraints.

This document refines the `Blind Scientific Discovery Runtime` and `FORGE Genesis` roadmap already authorized in `docs/work/ACTIVE_PLAN.md`. It does not change current scientific maturity, validation status, certification state, or production readiness.

## 1. Purpose

FORGE Genesis asks a deliberately narrower question than "can FORGE invent new science?":

> Given a bounded objective, a preregistered set of physical laws, constants, materials/properties, solvers and compute budget — while withholding the historical solution — can FORGE independently search, falsify and recover a mechanism that is materially equivalent to an established human discovery?

The benchmark exists to test the **Discovery Engine itself**, not to claim scientific novelty.

The desired progression is:

```text
Battery evidence closure
        ↓
Blind Scientific Discovery Runtime
        ↓
FORGE Genesis historical rediscovery
        ↓
Repeated success across independent physics domains
        ↓
Only then: stronger autonomous-discovery research claims
```

The battery flagship proves that FORGE can carry evidence, applicability, uncertainty, provenance and replay around a known scientific model. Genesis tests whether the system can also conduct a bounded scientific search without being handed the answer.

## 2. Core claim under test

Genesis does **not** preregister the claim that FORGE can discover unknown physics.

It preregisters the weaker, falsifiable claim:

> FORGE can recover known physical mechanisms from admissible primitives under blinded conditions, while preserving a complete record of hypotheses, experiments, failures, evidence and replay.

A successful benchmark run must demonstrate all of the following:

1. the historical target solution was withheld from the discovery process;
2. the required physics were representable by the allowed model classes;
3. hypotheses were generated and tested through the FORGE runtime;
4. physically invalid or unsupported candidates were rejected rather than silently repaired;
5. the final candidate satisfies preregistered success criteria;
6. the run is replayable from frozen inputs and evidence;
7. no stronger scientific claim is made than the evidence supports.

## 3. Non-goals

Genesis v1 is **not**:

- proof that FORGE can discover novel laws of nature;
- proof that a language model has no latent memory of a historical invention;
- a benchmark for unrestricted internet research;
- a competition to maximize raw simulation count;
- evidence that a simulated design will work experimentally;
- permission to promote a candidate to `SUPPORTED` without the normal FORGE evidence gates;
- a replacement for experiment, domain experts, safety review or engineering sign-off;
- a route to actionable hazardous system design.

High-consequence domains may be represented only at a safe, high-level benchmark layer unless a separately reviewed scientific and safety contract authorizes more.

## 4. Benchmark architecture

```text
Objective
   ↓
Preregistered admissible knowledge
   ↓
Anonymous Primitive / Candidate Selector
   ↓
Hypothesis Generator
   ↓
Experiment / Simulation Planner
   ↓
Multiphysics Composer
   ↓
Provider Execution
   ↓
Evidence Capture
   ↓
Falsifier / Constraint Checker
   ↓
Discovery Memory
   ↓
Next-Best-Experiment Selection
   ↺
Candidate Mechanism
   ↓
FORGE Trust Layer
   ↓
Rediscovery Assessment + Evidence Bundle
```

The Discovery Runtime proposes and searches.

The Trust Layer does not assume the proposal is correct. It attempts to establish what is supported, what remains uncertain, and what must be refused.

## 5. Mandatory preregistration

Every Genesis benchmark must freeze a machine-readable preregistration before the search begins.

At minimum it records:

### 5.1 Objective

A measurable physical objective, for example:

```text
Convert an imposed temperature difference into useful work.
```

The objective must not contain the name, topology, equation set or historical label of the hidden solution.

### 5.2 Allowed physics

Explicitly enumerate the model families the run may use.

Examples may include:

- mechanics;
- thermodynamics;
- heat transfer;
- fluid mechanics;
- electromagnetism;
- bounded chemistry / electrochemistry;
- material-property relations.

A benchmark cannot fail FORGE for not discovering a mechanism that the allowed physics cannot represent.

### 5.3 Allowed knowledge

Freeze:

- physical constants;
- admissible material/property tables;
- governing equations or equation families;
- solver/provider versions;
- units and dimensional conventions;
- allowed geometric primitives;
- admissible boundary and initial conditions.

Every allowed source must be hashed and versioned.

### 5.4 Forbidden knowledge

Freeze what the discovery process may **not** access, including:

- internet search;
- historical invention names;
- benchmark answer descriptions;
- target schematics;
- target patents/papers/textbooks;
- answer-specific templates;
- hidden evaluator notes.

### 5.5 Compute budget

Preregister:

- maximum candidate count;
- maximum solver calls;
- wall-clock or CPU/GPU budget where relevant;
- fidelity levels;
- stopping criteria;
- retry policy.

The benchmark is invalid if the budget is expanded after seeing results without starting a new preregistered run.

### 5.6 Success criteria

Define success before execution.

A criterion must be based on measurable physics or functional equivalence, not visual resemblance or a language-model judgement alone.

## 6. Leakage control

Historical rediscovery is only meaningful if answer leakage is treated as a first-class threat.

Genesis must distinguish at least three knowledge boundaries:

```text
A. Discovery runtime knowledge
B. Evaluation-only hidden target knowledge
C. External historical corpus
```

The discovery runtime must not receive B or C.

Controls should include, where technically possible:

- network-disabled execution;
- frozen local dependency set;
- no retrieval tools;
- no answer-bearing prompt text;
- no hidden-solution metadata in filenames or schemas;
- hash-pinned benchmark packages;
- evaluator-only answer key;
- immutable event log of every hypothesis and experiment;
- reproducible environment manifest.

### 6.1 LLM contamination limitation

A pretrained model may already contain historical knowledge in its parameters. Therefore a single historical rediscovery benchmark cannot prove genuine independent invention.

Genesis must explicitly report this limitation.

The strongest v1 evidence comes from combining historical targets with:

- transformed-physics tasks;
- synthetic universes;
- renamed and permuted primitives;
- held-out generated mechanisms;
- no-solution tasks.

Success across these classes reduces the chance that the system is merely recalling a memorized answer.

### 6.2 Anonymous primitive selection

For stronger rediscovery tests, Genesis must not hand the Discovery Runtime the historically correct material, isotope, component, mechanism family or other privileged primitive when the objective is to test whether the system can identify it.

Instead, the runtime receives a bounded, preregistered candidate library whose entries are represented by neutral identifiers such as:

```text
PRIMITIVE_A17
PRIMITIVE_B04
PRIMITIVE_C91
...
```

The discovery process may see only the physical properties and relationships explicitly authorized by the benchmark contract. Historical names, common-use labels, answer-bearing categories and target-specific hints remain evaluator-only information.

The intended loop is:

```text
anonymous candidate library
        ↓
physics-based screening
        ↓
hypothesis generation
        ↓
simulation / experiment
        ↓
falsification
        ↓
belief update
        ↓
next-best candidate / experiment
        ↺
surviving mechanism
```

The benchmark must distinguish between:

- candidates eliminated before execution by valid physical constraints;
- candidates tested and falsified;
- candidates surviving because evidence is genuinely supportive;
- candidates surviving only because evidence is insufficient.

A candidate must never be promoted merely because it resembles a historically familiar answer.

For high-consequence domains, anonymous primitive selection remains bounded to safe, non-operational scientific properties. Genesis does not expose or optimize actionable construction, fuel-cycle, weapons-relevant or other hazardous procedures.

### 6.3 Synthetic-universe anti-memorization control

Historical rediscovery alone cannot rule out latent model memory. Therefore the stronger control replaces real-world names and may also transform admissible constants, scales, property values or primitive relationships while preserving a hidden solvable structure.

Example evaluator view:

```text
Universe PHI-3
PRIMITIVE_Q17
PRIMITIVE_L82
PRIMITIVE_R05
...
```

The Discovery Runtime is not told which transformed primitive corresponds to any real-world material or mechanism.

A valid synthetic-universe benchmark freezes:

- the transformed laws/relationships;
- the anonymous primitive library;
- the evaluator-only latent solution;
- the no-solution status, when applicable;
- the same compute and evidence rules used by historical benchmarks.

Success on historical rediscovery plus anonymous transformed controls is stronger evidence of search competence than historical rediscovery alone.

## 7. FORGE Genesis benchmark families

### G0 — Search sanity

Purpose: prove the closed-loop search machinery functions.

Characteristics:

- small parameter space;
- single-domain physics;
- analytically or numerically checkable optimum;
- cheap replay.

Exit requirement: deterministic evidence capture, failure logging and replay.

### G1 — Single-domain blind rediscovery

Examples of target classes:

- mechanical energy conversion;
- simple heat-to-work mechanisms;
- elementary electromagnetic conversion.

The historical mechanism name and topology remain hidden.

Exit requirement: recover a functionally equivalent mechanism within the preregistered budget.

### G2 — Coupled multiphysics rediscovery

Search must compose two or more physical domains.

Examples of target classes:

- thermo-mechanical conversion;
- electro-mechanical conversion;
- electro-thermal behavior.

Exit requirement: correct coupling semantics, not merely separate successful simulations.

### G3 — Competing-mechanism falsification

The benchmark includes multiple plausible but wrong mechanisms.

FORGE must reject candidates for explicit reasons such as:

- conservation-law violation;
- dimensional inconsistency;
- impossible boundary conditions;
- material/property invalidity;
- numerical non-convergence;
- outside applicability;
- insufficient evidence.

Exit requirement: high-quality refusal is scored positively.

### G4 — Anonymous primitive selection

The benchmark provides a large bounded library of neutral candidate primitives rather than the historically correct choice.

The Discovery Runtime must determine which candidates merit testing from their allowed physical properties and constraints.

Exit requirement:

- identify a physically plausible subset without answer-bearing labels;
- correctly eliminate invalid candidates;
- retain potentially valid candidates when evidence is insufficient rather than falsely rejecting them;
- recover a viable mechanism within the preregistered budget.

The benchmark reports selection efficiency and false-elimination / invalid-survivor rates.

### G5 — Transformed-physics / synthetic-universe tasks

The evaluator changes names, constants, scales or admissible relationships while preserving a solvable latent structure.

Purpose: reduce dependence on memorized historical answers and test whether primitive selection still works when familiar names and values are absent.

Exit requirement: recover the latent mechanism from the transformed problem, not from historical naming cues.

### G6 — No-solution / insufficient-evidence tasks

Some tasks intentionally have:

- no feasible mechanism inside the allowed physics;
- an underdetermined objective;
- insufficient measurements;
- missing model classes.

Correct output may be `REFUSED` or `INSUFFICIENT_EVIDENCE`.

A system that always returns a candidate fails Genesis.

### G7 — Frontier historical principles

Only after G0–G6 are stable, test more demanding historical principles requiring broader physics.

These remain **rediscovery benchmarks**, not novelty claims.

High-consequence topics must remain non-operational and bounded to safe scientific principles. For example, a nuclear-energy benchmark may test high-level energy-conversion reasoning but must not include reactor construction, fuel-cycle procedures, enrichment, criticality engineering, or other actionable hazardous instructions.

## 8. Search strategy

Genesis must not equate intelligence with brute force.

The preferred loop is:

```text
propose
→ simulate
→ falsify
→ update belief
→ select next-best experiment
→ repeat
```

The runtime should support:

- active learning;
- Bayesian or surrogate-guided optimization where appropriate;
- multi-fidelity evaluation;
- constraint propagation;
- dimensional pruning;
- symmetry/equivalence reduction;
- design-memory reuse;
- explicit exploration/exploitation accounting.

Random search may be retained as a baseline.

The benchmark should compare the discovery policy against at least one simple baseline when feasible.

## 9. Evidence model

Every run must emit an immutable evidence bundle containing at least:

```text
benchmark_id
preregistration_digest
environment_digest
allowed_knowledge_digest
forbidden_knowledge_contract
objective
seed / determinism settings
solver/provider versions
hypothesis event log
experiment event log
candidate lineage
rejection reasons
resource consumption
final candidate
validation checks
uncertainty state
applicability state
replay receipt
final verdict
```

Unknown uncertainty is recorded as unknown. It must never be silently converted to zero.

A failed run remains evidence and must not be deleted from the benchmark history.

## 10. Scoring

Genesis should report a vector of measurements rather than one opaque score.

Recommended metrics:

| Metric | Meaning |
|---|---|
| Rediscovery success | Did the run satisfy the preregistered functional target? |
| Experiment count | Number of distinct executed experiments |
| Solver-call count | Total provider executions |
| Compute cost | CPU/GPU/wall-clock budget actually consumed |
| Falsification precision | How often rejected candidates were rejected for valid reasons |
| Search efficiency | Progress relative to a simple baseline |
| Candidate selection efficiency | Useful candidates identified per screened/executed candidate |
| False-elimination rate | Physically viable candidates incorrectly removed during screening |
| Invalid-survivor rate | Physically invalid candidates incorrectly retained after screening/falsification |
| Mechanism distance | Distance from the hidden reference under an evaluator-defined equivalence relation |
| Replay success | Whether the evidence bundle reproduces the assessed result |
| Leakage audit | PASS / FAIL / UNKNOWN |
| Evidence completeness | Required receipts and provenance present |
| Correct refusal rate | No-solution/insufficient-evidence cases refused correctly |

No benchmark is considered passed if replay or leakage controls fail, even when the final mechanism resembles the hidden target.

## 11. Verdict semantics

Genesis keeps the normal FORGE discipline.

Possible benchmark-level outcomes include:

- `REDISCOVERED`
- `PARTIAL`
- `NOT_FOUND_WITHIN_BUDGET`
- `REFUSED`
- `INSUFFICIENT_EVIDENCE`
- `INVALID_BENCHMARK`
- `LEAKAGE_SUSPECTED`
- `REPLAY_FAILED`

`NOT_FOUND_WITHIN_BUDGET` is not proof that the target mechanism is impossible.

`REDISCOVERED` is not proof of novelty.

## 12. Independence ladder

A credible Discovery Runtime should succeed at progressively stronger forms of independence:

1. **Known target, hidden label** — weakest.
2. **Known target, hidden topology**.
3. **Target reconstructed from primitive laws only**.
4. **Correct primitive hidden inside an anonymous candidate library**.
5. **Renamed/permuted primitive universe**.
6. **Transformed constants and scales**.
7. **Synthetic mechanism absent from historical corpus**.
8. **No-solution cases correctly refused**.

Claims must be tied to the highest rung actually demonstrated.

## 13. Initial execution sequence

Genesis should not interrupt the current battery evidence-closure work.

Recommended order:

```text
1. Close battery real-data evidence path.
2. Freeze Genesis benchmark schema and event model.
3. Implement G0 search sanity task.
4. Implement one G1 historical rediscovery task.
5. Add one G3 falsification task.
6. Add one G4 anonymous-primitive selection task.
7. Add one G5 transformed/synthetic control using anonymous primitives.
8. Add one G6 no-solution task.
9. Run hostile leakage and replay review.
10. Repeat across a second independent physics family.
11. Only then consider broader multiphysics historical benchmarks.
```

The first milestone is therefore:

> **FORGE Genesis v0.1 — one blind rediscovery + one anonymous-primitive challenge + one transformed task + one no-solution control, all replayable.**

## 14. Promotion gates

The Discovery Runtime must not be described as scientifically validated until all required gates are satisfied.

Suggested gates:

### Gate A — Runtime integrity

- immutable event log;
- reproducible environment;
- deterministic replay where expected;
- correct provenance.

### Gate B — Search competence

- beats or materially improves on a preregistered simple baseline on at least one task;
- does not rely solely on random enumeration.

### Gate C — Falsification

- rejects invalid candidates correctly;
- no silent constraint repair;
- no unsupported success verdict.

### Gate D — Leakage resistance

- historical task plus transformed/synthetic controls;
- external corpus blocked;
- leakage audit recorded.

### Gate E — Cross-domain repeatability

- success in at least two independent physics families;
- same generic discovery architecture;
- no target-specific hard-coded solution path.

### Gate F — Trust integration

- applicability, uncertainty, provenance and replay flow through the normal FORGE evidence system;
- benchmark success cannot bypass Trust Layer semantics.

## 15. Failure rules

Genesis is designed so that negative results remain useful.

Do not:

- loosen a success threshold after a failed run;
- add the hidden answer to the admissible primitives;
- silently increase the compute budget;
- delete failed hypotheses from the event log;
- reclassify unknown uncertainty as zero;
- promote solver agreement to experimental validation;
- call a historically known mechanism a novel discovery.

If a benchmark specification is defective, mark the run `INVALID_BENCHMARK`, revise the preregistration, and start a new run with a new identity.

## 16. Relationship to Scientific Twins and Design Memory

Genesis should reuse the common FORGE identity and evidence architecture.

- **Scientific Twin**: candidate system identity, model state, geometry and evidence state.
- **Design Memory**: prior tested candidates, failures, constraints and evidence.
- **Discovery Memory**: ordered search history and belief updates.
- **Credibility Graph**: links claims to evidence and unresolved gaps.
- **Scientific Red Team / Design-Killer**: actively searches for reasons a candidate should fail.

A rediscovered candidate is not promoted because it is historically recognizable. It is promoted only through evidence.

## 17. Commercial interpretation

Genesis is primarily a technical validation benchmark, not marketing copy.

If successful, the defensible statement is:

> FORGE can autonomously search a bounded physical design space, falsify candidates and rediscover established mechanisms under preregistered blinded conditions, with replayable evidence.

Do not replace that statement with claims that FORGE discovers unknown science unless a separate, independently reviewed evidence program supports such a claim.

## 18. Definition of done for Genesis v0.1

Genesis v0.1 is complete only when all of the following are true:

- [ ] benchmark schema is committed;
- [ ] preregistration is immutable and hash-addressed;
- [ ] network/search isolation is demonstrated;
- [ ] one G1 historical rediscovery task runs end-to-end;
- [ ] one G4 anonymous-primitive selection task runs end-to-end;
- [ ] one G5 transformed/synthetic control with anonymous primitives runs end-to-end;
- [ ] one G6 no-solution control runs end-to-end;
- [ ] every hypothesis and experiment is recorded;
- [ ] invalid candidates have explicit rejection reasons;
- [ ] evidence bundle replays successfully;
- [ ] leakage audit is recorded;
- [ ] uncertainty and applicability are not overstated;
- [ ] no target-specific hard-coded answer path exists;
- [ ] historical names and privileged primitive labels are withheld from the discovery runtime;
- [ ] candidate-selection efficiency, false-elimination and invalid-survivor metrics are reported;
- [ ] hostile scientific review is completed;
- [ ] final claims use only the maturity level actually demonstrated.

Until these conditions are met, Genesis remains an experimental Discovery benchmark and must not be represented as validated autonomous science.
