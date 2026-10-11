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

### 7.1 Genesis graduation suite

The target graduation program is deliberately bounded. FORGE should not claim domain-generality from one flagship or from many closely related tasks.

The planned suite is:

1. **Battery / electrochemistry** — evidence-closed flagship and electrochemical reasoning.
2. **Thermal / thermodynamics** — independent energy/transport reasoning.
3. **Mechanics + fluids** — geometry, continuous physics and coupled engineering behavior.
4. **Electromagnetism** — a physically distinct field/energy-conversion family.
5. **Therapeutics / biology** — bounded research reasoning over noisy biological evidence and mechanistic models.
6. **Materials / chemistry** — advanced anonymous-primitive and reaction/property search.
7. **High-level nuclear-energy principles** — advanced safe, non-operational multiphysics reasoning only.

The first five are the minimum target for a **Genesis Graduation** claim. Domains six and seven are strengthening challenges, not prerequisites for beginning external evaluation.

Every graduation domain should include, where scientifically meaningful:

```text
Historical Blind Rediscovery
        +
Anonymous Primitive Selection
        +
Synthetic / Transformed Universe
        +
No-Solution / Insufficient-Evidence Control
```

Passing requires the same generic cognition architecture across domains. Domain packs may supply domain semantics, admissible primitives, models, providers, data and safety constraints; they may not supply target-specific reasoning paths or hidden-answer logic.

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

### 8.1 Non-linear reasoning, dependency invalidation and automatic replanning

The FORGE Mind must not be implemented as a one-way pipeline in which step N permanently assumes that steps 1..N-1 were correct.

Every hypothesis, design decision, inferred state and experiment plan must declare the upstream assumptions and evidence on which it depends. Later evidence may invalidate an earlier assumption. When that happens, FORGE must propagate the invalidation through the dependency graph and replan from the earliest scientifically affected state rather than patching only the latest output.

Required behavior:

```text
state / assumption A
        ↓
decision B
        ↓
experiment C
        ↓
decision D
        ↓
new evidence contradicts A
        ↓
mark A weakened / falsified
        ↓
invalidate B, C, D only where dependency exists
        ↓
preserve unaffected evidence and sub-designs
        ↓
construct a new belief state
        ↓
choose the next-best recovery experiment or redesign
        ↺
```

This is a **belief-revision and replanning requirement**, not an undo stack. The runtime must be able to:

- trace every downstream decision to the assumptions and evidence that justified it;
- distinguish a failed numerical execution from a falsified scientific hypothesis;
- weaken, falsify or reopen an earlier hypothesis when later evidence requires it;
- invalidate only dependent descendants rather than discarding unrelated valid work;
- preserve negative evidence and failed paths in Design / Discovery Memory;
- reuse unaffected geometry, models, evidence and solver results where their identities and applicability remain valid;
- regenerate the active plan from the updated belief state;
- move backward across multiple reasoning stages when necessary, including to an early architecture or primitive-selection decision;
- move forward along a different branch without pretending the previous branch never happened;
- stop with `INSUFFICIENT_EVIDENCE` or `REFUSED` when no admissible recovery path exists within budget.

A benchmark must therefore score not only whether FORGE eventually reaches the hidden target, but whether it can **recover correctly from a deliberately wrong early assumption**.

At least one Genesis task should inject or permit an initially plausible but incorrect assumption whose contradiction appears only after later simulation or evidence. Passing that task requires dependency-aware rollback/replanning, preservation of unaffected work, and a replayable record explaining:

1. which earlier assumption became untenable;
2. which downstream decisions were invalidated;
3. which prior results remained admissible;
4. why the replacement branch was selected;
5. what additional experiment or evidence justified the revised path.

Target-specific rescue code is prohibited. The same generic mechanism must work across all qualified domains.

### 8.2 Universal FORGE Mind

FORGE Discovery must expose one **domain-general scientific cognition loop**, not separate minds for battery, engineering, therapeutics, materials or other domains.

The cognition loop is:

```text
objective
  ↓
world / system state model
  ↓
competing hypotheses
  ↓
predictions
  ↓
next-best experiment / simulation
  ↓
provider execution
  ↓
falsification
  ↓
belief update
  ↓
replanning / redesign
  ↺
Trust Layer assessment
```

The domain changes the admissible knowledge and tools; it must not change the generic reasoning semantics.

The generic Mind must support:

- a world/system state model with explicit unknowns;
- a hypothesis graph containing competing explanations or candidate designs;
- belief state updates from new evidence;
- next-best-experiment selection based on expected information or decision value;
- explicit falsification attempts rather than confirmation-only search;
- meta-reasoning over whether to continue, change strategy, increase fidelity, request new evidence or stop;
- domain-independent dependency invalidation and replanning as specified above;
- correct refusal when available evidence, models or budget cannot support a defensible conclusion.

LLMs may participate in interpretation, hypothesis generation or planning, but they are not scientific authority. Numerical claims must be produced or checked by appropriate models, solvers, data and evidence gates.

### 8.3 Intelligent generative design

For engineering-design tasks, FORGE must not reduce discovery to random geometry generation followed by filtering.

A generated design should be a **semantic, parametric, editable system model** whose components, interfaces, constraints and purposes are represented explicitly.

Examples of required semantics include:

```text
system
 ├─ components
 ├─ interfaces / attachment points
 ├─ geometry parameters
 ├─ mass / energy / transport relationships
 ├─ reserved design space
 ├─ operational constraints
 ├─ validity / uncertainty state
 └─ decision lineage
```

When a requirement changes or a missing component is introduced, FORGE should perform impact analysis and local redesign where possible:

```text
new requirement
      ↓
affected dependency subgraph
      ↓
preserve unaffected valid sub-designs
      ↓
modify/recompose affected components
      ↓
re-run only required physics/evidence
      ↓
re-optimize
      ↓
updated evidence-backed design
```

The system should support reserved interfaces or design margin when explicitly requested or justified, so later additions do not necessarily require a complete redesign.

Generated artifacts must retain lineage explaining why each major design decision exists and which evidence or requirement justified it.

### 8.4 Advanced cognition capabilities

The following capabilities are part of the planned FORGE Mind roadmap. They are not prerequisites for Genesis v0.1 unless a benchmark explicitly exercises them, but they should be implemented as generic cross-domain cognition mechanisms rather than domain-specific helpers.

#### Causal and counterfactual reasoning

FORGE should maintain explicit causal hypotheses where the science supports them and should be able to ask bounded counterfactual questions before paying for expensive execution.

Examples:

```text
What changed?
What downstream quantities should change if this cause is real?
What if this variable changes while the rest of the admissible state is held fixed?
Which intervention best discriminates competing causal explanations?
```

Counterfactuals are hypotheses, not evidence. They become authoritative only after appropriate model or provider execution and Trust Layer assessment.

#### Scientific Imagination Sandbox

FORGE may generate deliberately unconventional mechanisms, architectures or hypotheses inside an isolated speculative workspace.

Every object in this workspace must be explicitly marked as speculative and must not inherit validation, support or confidence from ordinary evidence simply because it was generated by the Mind.

Promotion path:

```text
SPECULATIVE
    ↓
physically / biologically representable
    ↓
admissible model available
    ↓
simulation / evidence
    ↓
falsification
    ↓
ordinary Trust Layer
```

The sandbox exists to increase exploration breadth without contaminating evidence.

#### Cross-domain analogy engine

FORGE may transfer abstract reasoning patterns across domains when the analogy is expressed in generic scientific structure rather than copied answers.

Examples of transferable abstractions include:

- diffusion / transport;
- feedback;
- resonance;
- conservation;
- competing pathways;
- bottlenecks;
- stability / instability;
- source-sink structure;
- multi-scale separation.

An analogy is only a proposal for a new hypothesis. It must be re-expressed in the target domain's own semantics, models and admissibility rules before testing.

#### Value-of-information planning

Where multiple admissible experiments or simulations are available, FORGE should prefer the action with the best expected decision value rather than the action with the highest raw predicted score.

A planning policy may consider:

- expected information gain;
- expected uncertainty reduction;
- expected falsification power;
- compute cost;
- wall-clock cost;
- experimental cost;
- risk of invalidating large dependency subgraphs;
- fidelity required.

The precise utility function must be benchmark-specific and preregistered when it affects scoring.

#### Unknown-unknown detection and search-space expansion

FORGE must not assume that failure of all current candidates means the objective is impossible.

If the active hypothesis set repeatedly fails, the Mind should test whether the search representation itself is inadequate.

Possible outcomes include:

- missing primitive;
- missing model class;
- missing coupling;
- missing measurement;
- incorrect shared assumption;
- insufficient resolution or fidelity;
- genuinely infeasible objective inside the current contract.

The resulting state must distinguish between:

`SEARCH_SPACE_INADEQUATE`, `INSUFFICIENT_MODEL_CAPABILITY`, `INSUFFICIENT_EVIDENCE`, and a supported infeasibility conclusion.

The runtime may expand the search space only within preregistered or explicitly authorized bounds. It must not silently import forbidden knowledge to rescue a failed run.

#### Evidence-conflict resolution

When independent models, datasets, providers or measurements disagree, FORGE should not average them blindly or pick the result it prefers.

The Mind should:

1. localize the conflicting claims;
2. identify differing assumptions, validity envelopes and uncertainty channels;
3. generate competing explanations for the disagreement;
4. choose an experiment, model refinement or higher-fidelity run that can discriminate between them;
5. preserve unresolved conflict explicitly when no decisive test is available.

#### Meta-learning of reasoning strategies

FORGE may learn which **reasoning strategies** tend to work for classes of problems without memorizing target answers.

Reusable strategy patterns may include:

- dimensional pruning before numerical search;
- surrogate-first screening;
- coarse-to-fine mesh/fidelity schedules;
- which experiment classes have high falsification value;
- which decompositions reduce a large search graph effectively.

Strategy reuse must never bypass domain admissibility, Trust Layer gates or benchmark isolation.

The benchmark record should distinguish:

```text
reused reasoning strategy
!=
reused target answer
```

### 8.5 Compute-efficiency and heterogeneous execution requirement

Scientific correctness is necessary but not sufficient for high-throughput discovery. FORGE must also use available compute resources efficiently.

The runtime should be designed for heterogeneous execution:

- **GPU**: vectorized/batched screening, surrogate inference, compatible matrix/vector kernels, optimization and accelerator-capable providers;
- **CPU**: orchestration, branching logic, geometry/meshing paths and providers that are CPU-oriented;
- **HPC / distributed pools**: independent candidate simulations, expensive CFD/FEA/PDE runs and multi-node execution where supported;
- **cache / reuse**: reuse scientifically identical or still-applicable intermediate results rather than recomputing them;
- **multi-fidelity promotion**: expensive solvers should normally be reserved for the small subset of candidates that survive cheaper valid gates.

A search budget such as 10,000 candidate designs must not imply 10,000 identical high-fidelity runs. The intended pattern is:

```text
large candidate population
        ↓
batched cheap screening
        ↓
small promoted subset
        ↓
medium-fidelity evaluation
        ↓
very small finalist set
        ↓
high-fidelity verification
```

FORGE should behave as an **anytime system** where useful provisional results can appear before the full high-fidelity campaign is complete, while clearly distinguishing provisional search output from validated evidence.

Performance targets must be benchmarked on real hardware before being advertised as achieved. At minimum, every campaign should record:

- wall-clock time by stage;
- CPU and GPU allocation/utilization where measurable;
- worker count and concurrency;
- solver/provider call counts;
- candidate counts entering and leaving each fidelity level;
- cache/reuse rate;
- compute cost per candidate and per surviving design;
- time to first feasible candidate;
- time to useful shortlist;
- time to final evidence bundle.

A workflow that is scientifically correct but needlessly serial, recomputes unchanged work, or promotes excessive candidates to expensive fidelity is a performance failure to be diagnosed, not accepted as inevitable.

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
dependency graph
belief revisions
invalidation / replanning events
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
| Recovery efficiency | Cost and evidence quality required to recover from invalidated earlier assumptions |
| Replanning correctness | Whether dependency invalidation preserves unaffected work and removes only scientifically dependent conclusions |
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
- silently patch a downstream design after an upstream assumption was falsified;
- discard valid unrelated evidence merely because another branch was invalidated;
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
- [ ] hypothesis/design dependencies are recorded;
- [ ] at least one benchmark demonstrates dependency-aware rollback/replanning after a later contradiction invalidates an earlier assumption;
- [ ] unaffected valid evidence survives replanning with unchanged identity;
- [ ] invalid candidates have explicit rejection reasons;
- [ ] evidence bundle replays successfully;
- [ ] leakage audit is recorded;
- [ ] uncertainty and applicability are not overstated;
- [ ] no target-specific hard-coded answer path exists;
- [ ] historical names and privileged primitive labels are withheld from the discovery runtime;
- [ ] candidate-selection efficiency, false-elimination and invalid-survivor metrics are reported;
- [ ] one generic FORGE Mind executes across the qualified benchmark domains without target-specific reasoning code;
- [ ] causal/counterfactual proposals are separated from evidence and tested before promotion;
- [ ] speculative ideas remain isolated until they pass ordinary admissibility, falsification and Trust Layer gates;
- [ ] cross-domain analogies transfer abstract structure only, never target answers;
- [ ] value-of-information or equivalent planning is available where multiple next experiments are admissible;
- [ ] repeated hypothesis failure can trigger explicit search-space adequacy checks rather than blind continued optimization;
- [ ] conflicting evidence remains explicit until a discriminating test resolves it;
- [ ] reusable reasoning strategies are recorded separately from domain answers;
- [ ] intelligent-design tasks retain semantic/parametric editability and decision lineage where applicable;
- [ ] compute campaigns record CPU/GPU/concurrency, fidelity-promotion and time-to-result metrics;
- [ ] the graduation suite is evaluated against the five-core-domain target before any domain-general maturity claim;
- [ ] hostile scientific review is completed;
- [ ] final claims use only the maturity level actually demonstrated.

Until these conditions are met, Genesis remains an experimental Discovery benchmark and must not be represented as validated autonomous science.
