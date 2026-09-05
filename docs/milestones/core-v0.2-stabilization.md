# Core V0.2 Stabilization

Baseline `4da598d` (T2 freeze) → T3 freeze `f4e9b4b` → this document.

Core V0.2 is a stabilization pass, not an expansion. Its governing rule was
*experiment pulls architecture; architecture does not invent work for itself*.
A concept was promoted only if the production loop required it, it recurred
across independent evidence, or it protected correctness or reproducibility.

The headline outcome is that **the Core needed almost no change**. M1–M5 had
already built the contracts T1/T2/T3 turned out to need, and in the one case
where a frozen experiment exercised a core contract against real data — T1's
fidelity ladder — the contract carried it with no source edit at all. What
V0.2 actually found was a reproducibility defect that made every freeze
unverifiable on a clean checkout, and a set of load-bearing invariants that no
test was protecting.

---

## A. Baseline verification

| item | result |
|---|---|
| Worktree | `.claude/worktrees/scientific-computation-platform-47741c` |
| Branch | `sria/v0.1-m5-campaign-loop` |
| Starting HEAD | `4da598d` — T2 freeze |
| T3 at start | uncommitted, as expected (`experiments/thermal_t3/`, one test file) |
| T3 freeze commit | `f4e9b4b` |
| Starting regression | **876 passed** |
| T3 module | 37 passed |
| T3 artifact reproduction | `t3_report.md`, `t3_results.json`, `t3_config_frozen.json` regenerate **byte-identically** |
| T1/T2 digest pins | verified by suite; unchanged |
| Frozen trees since T3 | 0 commits touching `thermal_t1/2/3`, `electrical_e1/2/3`, `shared`, `domains/thermal` |

The prompt's assumed history was checked against the repository rather than
assumed. One correction: `hardening/electrical-dc-v0.0.1` is an *ancestor* of
the SRIA branch, not a divergent line — the progression is linear from `main`
through Scientific Core V0/V0.0.1, Electrical DC V0/V0.0.1, SRIA M1–M5,
S1/S1.1, E1–E3, the thermal gate, then T1 → T2 → T3.

### T3 freeze review

T3 was reviewed before freezing and not modified. It is a **negative result**
and is frozen as one.

- Preregistered criteria: A1 **FAIL**, A2 **FAIL**, A3 PASS, A4 PASS,
  A5 **FAIL**, A6 PASS, A7 PASS.
- Falsification triggers fired: `F1_policy_failed_to_beat_baselines`,
  `F4_saving_bought_with_reliability`.
- The policy is cost-optimal at **no** swept wrong-decision cost
  (`policy_wins_from_wrong_decision_cost: null`).
- The benchmark itself passed its own soundness criteria (A6, A7), so the
  comparison is informative and the failure is the rule's, not the bench's.

Integrity checks that made the freeze defensible:

- **No post-result tuning.** The preregistration (`t3_config.py`) declares the
  bands, costs, safety factor, rules and criteria, and declares in advance
  that the error indicator is conservative and will over-escalate in MODERATE.
  It did, and that was measured rather than removed.
- **Strategy code cannot reach grader truth.** Enforced by AST parsing, not
  convention: `test_no_strategy_reads_anything_it_could_not_know` refuses any
  read of `scenario.alpha_true` / `terminal_truth` / `margin` / `sign` /
  `correct_decision` or of `RungView.numerical_error` inside the strategy
  functions, and `test_grading_happens_outside_the_strategies` refuses a
  strategy that marks its own homework.
- **The one favourable result is fenced.** The policy made 0 incorrect
  confident decisions against Always Reference's 5. Both the results payload
  and the rendered report state this does **not** offset A1/A2/A5, and a test
  asserts that wording is present.

Nothing about the policy was fixed. Escalation cost accounting, debiased μ,
new error indicators, alternative thresholds and safety factors are research
hypotheses, recorded in §F, not production behaviour.

---

## B. Evidence-to-Core audit

Classification: **A** promote/strengthen · **B** exists but interface
insufficient · **C** domain-owned · **D** experiment-only · **E** known debt,
non-blocking.

| # | Concept | Evidence | Where it lives now | Class | Action |
|---|---|---|---|---|---|
| 1 | Byte-digest freeze pins | T1, T2, T3, E1, E2, E3, electrical demo, thermal gate | digests in `*_config.py`, verified in tests | **A** | Fixed: pins were unverifiable on a clean Windows checkout. `.gitattributes` added. |
| 2 | Four-channel uncertainty (aleatoric / parameter / model-form / numerical) | T1, T2 (numerical bias is load-bearing); T3 (statistical and numerical terms must stay separate) | `sria/uncertainty.py` `UncertaintyChannel`, consumed by budget, critics, obligations, arbiter | **B→none** | No change. The distinction already exists and is enforced. See §H. |
| 3 | Solver convergence ≠ numerical adequacy | T1/T2: coarse rung converges exactly and is still biased | `critics.py` keeps `residual_evidence` and `numerical_uncertainty_declared` as separate checks; `is_usable` docstring refuses to mean "valid" | **B→none** | No change. Already correct. |
| 4 | Fidelity rung identity, rank, declared relationship, measured cost | T1 registered a real 3-rung ladder; T2, T3 reused it | core `FidelityRung` / `ModelFidelityRelationship`; ladder itself experiment-side | **B** | Docstring corrected — it claimed no fidelity data exists. No API change: T1 proved the contract carries a real ladder unedited. |
| 5 | Measured work/cost as a typed result field | T1/T2/T3 each defined `work_proxy` locally | experiment-side; `wall_seconds` is telemetry in result metadata | **E** | Refused. Cost is already expressible as relationship `median_ratio`. One domain lineage is not enough. |
| 6 | Grid Bayesian inference | T1, T2, T3 | `experiments/shared/grid_inference.py` (225 lines) | **D** | Stays experiment-side. Deliberately a copy of E2's frozen maths, with a test asserting the two agree. |
| 7 | Inference boundary contract | only one implementation exists | `BeliefSnapshot` + `FactorAvailability.UNAVAILABLE` already represents "no posterior exists yet" honestly | **B→none** | No change. A boundary that represents absence is what §10.4 asked for; a contract for imagined future inference engines would be speculative. |
| 8 | Decision-aware fidelity escalation policy | T3 — and it **lost** | `experiments/thermal_t3/t3_run.py`, ~40 lines | **D** | Never promoted. Verified: no production file references it. |
| 9 | Posterior confidence ≠ numerical adequacy ≠ decision robustness ≠ validity ≠ certification | T3 | separate types across `assurance/`, `decision/`, `campaign/certification.py` | **B→none** | Separation preserved; nothing merged. |
| 10 | Solver failure as scientific data | both domain solvers emit `FAILED`/`DIVERGED`; critic handles them | `ConvergenceState`, `RawSolverOutput` (sanctioned home for non-finite values) | **E** | Timeout / infeasible-region states are absent but unpulled — no experiment has produced one. Deferred to the kinetics domain. |
| 11 | Result → Evidence path | E1, E2, E3, electrical demo | `evidence.py`, `gateway.py`, `admission.py` | **B→none** | No shared glue extracted; the transformations are not yet demonstrably shared across domains. |
| 12 | Checkpoint / restore / effect idempotence | M5.1, exercised by durability tests | `campaign/checkpoint.py` `EffectLedger.once` | **B→none** | No change. Restart-from-JSON is genuinely tested. |
| 13 | Commitments / obligations semantics | none from T1/T2/T3 | `assurance/obligations.py` | **E** | Left as recorded debt. No experiment demonstrated a production blocker. |
| 14 | Immutability of scientific records | mutation probe | 39 frozen dataclasses in `scientific/` | **A** | Tests added — nothing asserted it. |
| 15 | `ScientificResult.is_usable` | mutation probe | `results/result.py` | **A** | Tests added — the whole predicate was unguarded. |
| 16 | `Uncertainty` boundaries | mutation probe | `results/uncertainty.py` | **A** | Tests added — `confidence_level` had zero references in the suite. |
| 17 | Shared experiment harness growth | §11 concern | `experiments/shared/` = 260 lines | **D** | Audited, not grown. It has not become a second framework. |

---

## C. Production changes

Two, both small. Everything else in V0.2 is tests.

### 1. `.gitattributes` (new) — `503cae8`

**Why.** Frozen experiments pin inputs by SHA-256 over raw file *bytes*. With
`core.autocrlf=true` (the Windows default) and no `.gitattributes`, a clean
clone materializes CRLF and every pin breaks.

**Evidence.** Reproduced before fixing: cloning the branch and running the T2
digest test failed with six mismatches across `experiments/thermal_t1` and
`experiments/shared` — T1 "changed" on a tree nobody had touched. After the
fix, the same clean clone runs **876 passed**.

**Deliberately not generalized.** No CI job, no digest-manifest tool, no
pre-commit hook. The defect was that checkout rewrote bytes; the fix is to
stop it rewriting bytes.

### 2. `src/engcore/sria/calibration/fidelity.py` — `e8738d2`

**Why.** The module docstring asserted the repository contains no genuine
low/high-fidelity model pairs — "no coarse/fine mesh runs, no
surrogate-vs-full comparisons". T1/T2/T3 falsify that: one conduction model at
three rungs (8×10, 64×80, 512×640) with measured terminal errors ~1.7e-02,
1.6e-03, 3.6e-04. A future planner reading that claim would conclude no
fidelity evidence exists.

**Docstring only — no API change.** The correction records *why* nothing
changed: T1 registered the ladder and its cost ratios through the existing
`FidelityRung` / `ModelFidelityRelationship` types and
`fidelity_corpus_status` reported a real ladder, with no `src` edit. The
contract was shaped correctly before there was data to shape it against.

**Deliberately not generalized.** No per-rung cost field (redundant with
relationship `median_ratio`), no registered production ladder, no accuracy
field (accuracy stays `DOMAIN_OWNED`).

---

## D. Core V0.2 architecture

Boundaries as stabilized. None of this is new in V0.2; it is what the audit
confirmed is load-bearing and correctly placed.

- **ScientificProblem** (`scientific/ir/`) — what is asked: variables, units,
  conditions, constraints, objectives. Domain-neutral.
- **Domain Pack / Mind** (`domains/`) — owns governing equations, models,
  discretization, validity envelopes, domain validation, and what "coarse"
  means. `domains/thermal/conduction1d` is digest-pinned and immutable.
- **Solver** (`scientific/solvers/protocol.py`) — four deliberately distinct
  types: `ScientificProblem` → `PreparedSolve` → `RawSolverOutput` →
  `ScientificResult`. `RawSolverOutput` is the one sanctioned home for
  non-finite values; interpreted science may not be non-finite.
- **ScientificResult** (`scientific/results/`) — value + unit + model + solver
  + convergence + assumptions + uncertainty + validation + provenance. Values
  must be `Quantity`; provenance is mandatory.
- **Validation** — checks coexist and the level is *derived*, never asserted.
  `NOT_RUN ≠ PASS`. `from_dict` recomputes `attained_levels` and refuses a
  payload that claims more than its checks establish.
- **Evidence / admission** — `Evidence`, `ClaimBinding`, single-use
  authorization consumed through an `AdmissionAuthority`.
- **Inference boundary** — represented, not implemented. `BeliefSnapshot`
  carries `FactorAvailability.UNAVAILABLE` rather than a plausible prior.
- **Fidelity** — core owns identity, rank, declared relationship and
  structure-transferable cost ratios. Accuracy and sufficiency are
  `DOMAIN_OWNED` and constructing them here raises.
- **Numerical uncertainty** — `UncertaintyChannel` keeps aleatoric, parameter,
  model-form and numerical apart; `UncertaintyKind.UNKNOWN` is the honest
  default and is distinct from a computed zero.
- **Execution / cost** — `BudgetLedger` with a validation reservation, and a
  `guarantee_statement` that states plainly whether a cap is executor-enforced
  or merely declared.
- **Campaign / decision** — `CampaignRunner`, `EffectLedger.once` keyed
  idempotence, Arbiter-owned stopping.
- **Provenance** — `ProvenanceRecord` mandatory on every result;
  `canonical_digest` for replay.

### Drone thought experiment

Applied as an architecture check only. No core type names propellers, meshes,
batteries, slabs or dividers. `ScientificProblem`, `ScientificResult`,
`FidelityRung`, `UncertaintyChannel`, `Evidence` and `BudgetLedger` are all
expressible without knowing what a drone is. What the core cannot yet do is
*couple* domains — there is no multiphysics coordination and none was added.

---

## E. Debt removed

1. **Digest freezes were unverifiable from a clean checkout on Windows.**
   Freeze condition 10 was not actually satisfied before V0.2. Now proven by
   clone-and-run.
2. **A false claim about repository evidence** in the fidelity module.
3. **Unprotected core invariants** — see §G.

## F. Debt deliberately retained

Nothing here was pulled by existing evidence, so nothing here was built.

- **T3 follow-ups as hypotheses only**: terminal-only cost accounting;
  debiased μ in the give-up rule; a less conservative error indicator with an
  order-of-accuracy correction; alternative thresholds and safety factors.
  These are exactly what the T3 preregistration forbade adjusting.
- **Solver failure taxonomy**: no `TIMEOUT`, no `INFEASIBLE_REGION`. No
  experiment has produced either. Expected from the kinetics domain.
- **Measured work/cost as a typed `ScientificResult` field**, and **fidelity
  identity on a result**. Both experiment-side today.
- **Commitment / obligation semantics redesign.** No production blocker shown.
- **A generic inference contract.** One implementation is not a pattern.
- **Result→Evidence shared glue.** Not yet demonstrably shared.
- **Cross-process determinism.** Restart-from-JSON is tested inside one
  process; no stronger claim is made.
- **45 of 69 confirmed-uncaught mutations**, classified in §G. The genuinely
  actionable remainder is the `admission.py` single-use-authorization consume
  path.
- **Property-based and stateful testing.** Not added; see §G.

## G. Test hardening

**Regression count: 876 → 957 passed.** 81 tests added across two modules.
No production behaviour changed by either.

### Method

A targeted mutation probe over ten load-bearing modules, run in a throwaway
clone. Operators: comparison-boundary flips (`<`↔`<=`, `>`↔`>=`, `==`↔`!=`,
`is`↔`is not`, `in`↔`not in`), `and`↔`or`, and boolean-constant flips — which
includes `frozen=True` on dataclass decorators.

Run in two phases, because the second is what makes the first honest:

| phase | what it did | result |
|---|---|---|
| 1 | each mutant against a hand-mapped test subset | 186 mutants, 88 survived |
| 2 | **every** phase-1 survivor re-run against the **entire** suite | 69 genuinely uncaught; **19 were false alarms** |

Phase 2 was not optional. `budget.py` alone is referenced by 16 test files and
phase 1 pointed at 3. Without re-verification this report would have claimed
19 gaps that do not exist.

No mutation-testing dependency was added; the probe is a throwaway script.

### What was found and fixed

**Scientific Core results package — 13 uncaught, all 13 now killed**
(`e8738d2`, `tests/test_core_v02_invariants.py`, 48 tests).

- `ScientificResult.is_usable` — the entire predicate was unguarded. The only
  three tests touching it assert `not result.is_usable`, so the True side and
  the boundary were unpinned. Added the full 6×4 truth table.
- `Uncertainty.confidence_level` — zero references in the entire suite.
- Zero standard uncertainty — never constructed, though the module calls
  computed-but-zero a distinct claim from UNKNOWN.
- The INTERVAL-bounds guard — a test existed but passed on a *downstream*
  dimensionality error, so deleting the guard left it green.
- `frozen=True` on the record types.

**SRIA trust layer — 69 uncaught, 24 now killed**
(`tests/test_core_v02_trust_invariants.py`, 33 tests).

The three that mattered most, all in stopping authority:

- `obligation_state.get(o, False)` → `.get(o, True)` survived. An obligation
  with **no recorded state would default to satisfied** — silence read as a
  pass, which is the exact failure the assurance layer exists to prevent.
- `if unassessed or unresolved` → `and` survived. Existing coverage of the
  unassessed path registers no stopping criterion, so the review exits at the
  later "no criterion" branch either way and the mutation is invisible. With
  an approving criterion present it is not: it lets a stop be **approved over
  obligations the campaign never assessed**. The new test supplies exactly
  that setup, with a control proving the same setup does approve when the
  obligations *are* assessed.
- `StopProposal.is_certification` — a documented constant `False` that nothing
  asserted.

Plus `frozen=True` across 18 trust record types (a mutable `StopReview` lets a
legal rejection be constructed and then overwritten to STOP_APPROVED, routing
around a constructor guard that refuses approval without an Arbiter decision),
and budget idempotence (`has_charge`'s `==`, which is what stops a resumed
campaign paying twice), zero-cost charges, and the reservation bound.

**Every claimed kill was verified by reapplying the mutation** and requiring
the new tests to fail: 11/11 for the results package, and the 24 SRIA kills
measured the same way.

### What remains uncovered — 45 of 69

Reported rather than implied fixed. Classified, not merely counted:

| count | what | why left |
|---|---|---|
| ~4 | `budget.py` comparisons at 86, 206, 227, 228 | **Equivalent mutants.** Each is padded with an epsilon (`<= pool + 1e-12`, `> total + 1e-9`), so `<`/`<=` differ only when the operand is *exactly* equal to the epsilon-padded bound in floating point. Not a reachable gap. |
| 5 | `stopping.py` `terminal_objective_available` flags | A diagnostic field on non-approving outcomes (REJECTED / NOT_ASSESSED). Flipping it changes no outcome and no authority. |
| ~9 | `evidence.py` / `admission.py` `payload.get(k) or default` | Deserialization defaults and message fallbacks. Mutating them changes a default string or a falsy-vs-missing distinction carrying no scientific claim. |
| 11 | `uncertainty_budget.py` combination path | Real, but no production caller drives it with quantified channels — both domain solvers report UNKNOWN. Tests here would pin behaviour no evidence has exercised. |
| ~11 | `admission.py` signature/consume paths, `checkpoint.py` | Genuine remaining gaps. The single-use-authorization consume path is the one worth doing next. |

Chasing all 45 would be the test-count theater this milestone was told not to
produce. The last row is real debt and is named as such.

### Not done

No property-based testing (Hypothesis) and no stateful sequence model were
added. The invariants the brief named for them — budget behaviour, restore
idempotence, legal/illegal status combinations — were reachable by direct
adversarial tests here, and adding a dependency to reach the same assertions
was not justified. This is a gap, and it is the honest place to start if
V0.3 wants deeper assurance.

## H. Architecture-creep report

Features explicitly refused, with the reason:

| Refused | Why |
|---|---|
| `DecisionAwareFidelityPolicy` in Core | T3's policy lost. Promoting it would promote a falsified rule. |
| Any adaptive fidelity selection framework | Out of scope by §7 and unsupported by evidence. |
| Per-rung cost field on `FidelityRung` | Redundant with relationship `median_ratio`; single-domain evidence. |
| Fidelity identity / work field on `ScientificResult` | No production consumer reads it as fidelity. |
| Generic inference engine contract | One implementation is not a pattern; would be an abstract factory for imagined domains. |
| Promoting `grid_inference` into Core | Experiment-only; freeze integrity requires the duplication. |
| `UncertaintySource` enum on `Uncertainty` | The channel distinction already exists in `sria/uncertainty.py`, and **no production producer has a quantified uncertainty to tag** — both domain solvers honestly report `UNKNOWN`. |
| `TIMEOUT` / `INFEASIBLE_REGION` convergence states | Speculative until a stiff domain produces them. |
| Growing `experiments/shared/` | Audited at 260 lines and left alone. |
| BoTorch, FEniCS, Cantera, OpenFOAM | §14. Nothing needed them to verify existing behaviour. |
| Hypothesis / mutation-testing dependencies | The probe was written as a throwaway script instead. Evidence was mandatory; tooling was not. |
| Rewriting historical experiments to remove duplication | Freeze integrity outranks DRY. |

## I. Generality check

- **Electrical** — supported and exercised (E1, E2, E3, demo, DC solver).
- **Thermal** — supported and exercised (gate, T1, T2, T3).
- **Kinetics / CSTR** — *untested*. The core is domain-neutral by inspection,
  but stiffness, real solver failure, competing model families and correlated
  parameters have never touched it. This is the point of the next milestone.
- **Drone multiphysics** — *unsupported*. No coupling layer exists. The core
  can represent each domain's results; nothing coordinates them.

Two domains sharing a core is weak evidence of neutrality, and both were
built alongside it. The honest statement is that the core has not yet been
*stressed* by a structurally different domain.

## J. Allowed claims

Core V0.2 proves:

1. Every frozen artifact reproduces from a **clean clone**, verified by
   cloning and running: 876 passed before the hardening tests, 924 after.
2. T3's negative result is frozen, reproducible byte-for-byte, and its
   integrity properties (no truth leakage, no self-grading, no post-hoc
   tuning) are machine-checked rather than asserted.
3. The four uncertainty channels are kept apart in the assurance layer, and
   solver residual is not treated as numerical adequacy.
4. The M2 fidelity contract carries a real measured ladder without
   modification.
5. Specific named invariants are now protected against specific named
   mutations, each verified by reapplying the mutation: all 13 previously
   uncaught in the results package, and 24 of 69 in the trust layer —
   including the stopping-authority defect where an unassessed obligation
   would have defaulted to satisfied.

## K. Forbidden claims

Core V0.2 does **not** prove:

1. That the core is domain-neutral in general. Two co-developed domains is not
   a neutrality proof.
2. That any scientific result here is physically validated. All hidden truths
   are synthetic; no measurement of a real system is involved.
3. That a cost-aware fidelity rule can work. T3 shows *that* rule does not.
4. That the tests are adequate. The probe covered ten modules with three
   operator families, and 45 of its 69 confirmed findings remain uncovered.
   It establishes a floor, not a ceiling.
5. That uncertainty propagation works end-to-end. No production solver emits a
   quantified uncertainty; every one reports `UNKNOWN`, honestly.
6. Durability beyond restart-from-JSON within one process.
7. Any multiphysics, Digital Twin, or optimization-backend capability.

## L. Next recommended milestone

**One only: a Kinetics / CSTR domain-admission gate**, in the shape of the
frozen thermal conduction gate — an analytic or reference-verified solver,
declared validity envelope, and a refusal to admit results outside it.

Why this and not something else: every §K limitation that is actionable
traces to the same root — the core has only ever met two co-developed,
well-behaved linear domains. A stiff kinetics problem is the cheapest way to
find out whether `ConvergenceState` needs `TIMEOUT`, whether the failure path
is really scientific data, and whether the fidelity contract survives a domain
whose rungs are model families rather than mesh refinements. It tests the
retained debt in §F directly instead of guessing at it.

Not started.
