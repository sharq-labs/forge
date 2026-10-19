# Genesis / Blindfold Blocker Matrix — Deep Audit 2026-10-19

> Static dependency analysis at `abed661f`. No Genesis run, benchmark, test or reproduction was executed for this
> matrix. "Blocks" means the step's gate cannot honestly be decided PASS while the item is open. Dependencies are
> stated per cell, not assumed globally.

## 1. Gates being evaluated (from `docs/discovery/FORGE_GENESIS.md` §18)

| Step | Gate (abridged) |
|---|---|
| **Step-0 Trust lane** | Certificate/authority state matches the intended code; unresolved failures explicitly classified. SCIENTIFIC_CORRECTNESS and UNCLASSIFIED stay blocking. The ACTIVE_PLAN G0 wording is global; OD-B1 is open. |
| **Genesis-lite Step-1** | Scoring frozen; baseline families and budgets frozen (§10.5); trap/leakage controls; evaluator outside Mind/Core authority; ≥ 20-seed baseline distributions; identity frozen; compute owner-approved. |
| **Minimal Mind Step-2** | The Mind beats the strongest applicable frozen baseline with CIs; calibrated predictions (proper scoring rule); LLM-ablation reported. Starts after Step-1 PASS. |
| **Real Engineering Demo (Step 2B, Track B)** | Infeasible-spec refusal names the binding constraint; the corrected spec executes on real providers with uncertainty and applicability; the evidence bundle replays; independent review finds no false support. **Runs only after Step-2 PASS.** Drone recommended (OD-13). |
| **Independent Blindfold Graduation (Step 6)** | Held-out (third-party) domain passes without Mind changes; evidence replayable and externally auditable; needs Step-5 PASS and an external evaluator (OD-8). |

## 2. Matrix

Legend:
- **B**: blocks, with a direct dependency.
- **B\***: blocks only under the global OD-B1 reading of the G0 exit.
- **C**: conditional; it blocks only if the step's chosen design uses that code path (dependency named).
- **I**: inherited, because a predecessor step is blocked.
- **—**: no dependency found.

| Item | Status | Step-0 | Step-1 | Step-2 | Demo 2B | Graduation |
|---|---|---|---|---|---|---|
| **B-LEAK** (known) | OPEN, measured | B\*: the readiness review lists it as SCIENTIFIC_CORRECTNESS for formal Genesis claims, so the global reading blocks the Route-2 exit; Route 1 (certificate binds HEAD) is unaffected | **B**: no formal tier while answers leak | **B** | — (no hidden-answer benchmark) | **B** |
| **FDA-05** vacuous pair credit | ER | B\* (as an SC item) | **B**: scoring cannot be frozen with a rule that credits UNKNOWN as knowledge | **B**: lift validity | — | **B** |
| **FDA-06** uncapped out-of-family law credit | ER (capping function) | B\* | **B**: §10.5 baseline rule not implemented; fix before the freeze | **B** | — | **B** |
| O-1 bootstrap "p" calibration (known) | static | — | **B** for freezing the decision contract (the FWER claim must be valid at freeze) | **B** | — | **B** |
| FDA-18 campaign answer exclusivity | SP channel | — | C: must be decided in the v0.3 design (randomise the mix or declare it) | **B** while FDA-05 is open; otherwise C | — | B |
| FDA-19 isolation probe scope | SP | — | **B** for lifting B-LEAK (the verifier cannot see the Genesis-lite leak class) | I | — | **B** |
| FDA-21 / FDA-22 baseline dof, kind-prior tell | SP | — | C: baseline strength and tell disclosure (§10.5, §10.3); v0.3 items | C | — | C |
| FDA-20 presentation-invariance metric | SP | — | — (descriptive) | — | — | — |
| **FDA-01** replay UQ not reproduced | SP | B\* | — (Genesis-lite uses Blindfold escrow and evaluator, not assembly replay) | — | **C**: if the demo's "evidence bundle replays" is attested through `assembly/replay.py` / assembly certification. The drone chain today runs `MultiphysicsRuntime` directly (`systems/products/drone_coupled.py:41`); the replay route is undesigned. | C (externally auditable replay) |
| **FDA-02** state clock unbound | SP | B\* | — | — | **C**: only if the demo runs through `system_runtime` authorities (it does not today) | C |
| **FDA-03** material source arbitration | ER | B\* | — | — | **C**: only if the demo resolves interpolated material properties (the drone chain imports no `materials` today) | C |
| **FDA-04 / FDA-14** MCP UQ intervals | ER | B\* | — | — | **C**: if the demo reports uncertainty through `answer_engineering_uncertainty` (`mcp/server.py:885`) | C |
| FDA-07 / 08 / 09 claims replay MINORs | SP / contract | — (MINOR; classify) | — | — | C: if the demo bundle is a claims bundle replayed with `replay_bundle` (FDA-08 makes grounded records never VERIFIED; FDA-09 VERIFIED ≠ support) | C |
| FDA-16 discovery holdout gate | SP | — | — | C: only if `scientific/discovery` becomes a Mind component | — | C |
| OBS-06 Mind trusts result-id labels | observation | — | — | C: the Minimal Mind design must bind authority result ids | — | C |
| **G0 known items**: stale cert `05522b59`, #169 unmerged, OD-22..34, D4 UNCLASSIFIED, CI dark | known | **B** | I | I | I | I |
| P-4 formal driver + fresh root; P-5 environment manifest; OD-8/18/19/20 | known | — | **B** | I | — | **B** (OD-8) |
| Remaining MINOR numerics (FDA-10..13, 15, 17, 23..26) | SP | — (classify; MINOR) | — | — | C: only if the demo touches those modules (DC validation, FTCS, mapping, PDE contracts, PyBaMM) | — |

## 3. Dependency explanations (why each "—" is a "—")

- **The Genesis-lite path uses none of FDA-01..04/14.** The traced baseline path is `harness.run_one` →
  `run_campaign` → `blindfold.roles` → escrow synthetic universes → sealed proposals → stdlib evaluator
  (FROZEN_MODEL_ARCHIVE_READBACK §"Genesis-lite baseline"; reconfirmed here by the R-05/R-06 module paths). It uses no
  assembly replay, system runtime, materials or MCP UQ. Those findings therefore block Step-1 only through the
  global G0 reading (B\*).
- **The Real Engineering Demo does not use Blindfold**, so B-LEAK, FDA-05, FDA-06 and O-1 do not block it directly.
  By contract, though, it starts only after Step-2 PASS, which inherits them. If the owner wants the demo earlier,
  that is a contract change to §18. The existing circuit breaker allows only a separately labelled
  "Trust-only refusal" demonstration, explicitly NOT a B1 completion.
- **The demo's own correctness dependencies are conditional** because its design is not fixed. Today the drone
  chain (`systems/products/drone*.py`) imports `execution.multiphysics.MultiphysicsRuntime`,
  `systems.assembly` (not `engcore.assembly`) and admissibility, and no `system_runtime`, `materials`, MCP UQ or
  assembly replay. Each C becomes B as soon as the demo design selects that path for its "replayable evidence" or
  "reports uncertainty" requirement. **Recommendation:** fix FDA-01 before choosing an assembly-replay route for the
  demo, and FDA-04/14 before reporting uncertainty through MCP.

## 4. Minimum sets per step (under the recommended global OD-B1 reading)

| Step | Must be closed (new) | Must be closed (known) |
|---|---|---|
| Step-0 | FDA-01, 02, 03, 04, 05, 06, 14 closed or classified with evidence (as SC they must be fixed; the global reading allows no open SC item) | #169 merge, OD-3 recert, OD-22..34 dispositions, D4 disposition, governance six-question records |
| Step-1 | FDA-05, FDA-06, FDA-19 (+ FDA-18/21/22 decided in v0.3) | B-LEAK lifted (OD-20), O-1 resolved, P-4, P-5, OD-18/19/8 |
| Step-2 | (Step-1) + FDA-18 if FDA-05 is not yet closed; FDA-16 / OBS-06 only if the Mind design uses them | (Step-1) |
| Demo 2B | Whichever of FDA-01, 02, 03, 04/14, 07–09 its design uses (C → B) | Step-2 PASS (contract) |
| Graduation | All Step-2 items + FDA-01 / FDA-09 if replay is the external-audit mechanism | OD-8 external evaluator; Steps 3–5 |

Under the **dependency-scoped** reading (not recommended), Step-0 for Genesis-lite would need only the known G0
items plus classification of the new findings. FDA-01..04/14 would then block only their own dependent claims.

## 5. Shortest safe path to Independent Blindfold Graduation and the Real Engineering Demo

1. Evidence preservation (ODC-EV1/EV2), then decisions (ODC-CL1, OD-B1, ODC-05/06/01/02/03/04/14/O1).
2. Merge #169, then Batch A (certified: FDA-01/02/03 + escrow half of FDA-05 + FDA-19), with failing-first tests (ODC-EX1). Batch B (MCP: FDA-04/14) can go in parallel.
3. One OD-3 recertification on Linux 3.11/3.12. G0 then exits by Route 1, with the open OD-22..34 and D4 dispositions.
4. v0.3 amendment (FDA-05 evaluator half, FDA-06, O-1 route B, FDA-18/21/22, P-1..P-5). Then the B-LEAK lift with an independent probe rerun (OD-20), then OD-18/19/8, then freeze and ≥ 20-seed baselines: Step-1.
5. Minimal Mind (Step-2) against the frozen v0.3. The demo (2B) is prepared in parallel and run after Step-2 PASS, choosing replay and UQ routes only after FDA-01 and FDA-04/14 are closed.
6. Graduation requires Steps 3–5 and an external evaluator. No shortcut exists in the current contract.

**Stop. Awaiting explicit owner approval.**
