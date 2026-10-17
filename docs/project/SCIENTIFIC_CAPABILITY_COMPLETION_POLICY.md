# Scientific Capability Completion Policy

Forge now distinguishes **having a foundation** from **having a complete capability**.

## Stages

1. **FOUNDATION**  
   Scientific definition, applicability boundary, implementation, and regression tests exist.

2. **FUNCTIONAL**  
   The capability additionally executes end to end, is verified, has explicit failure behavior, and is replay/provenance-aware.

3. **EVIDENCE_BACKED**  
   The functional capability additionally has the required real/external evidence path, calibration when applicable, independent validation, measurement uncertainty when applicable, and quantitative benchmark metrics.

4. **PRODUCTION_READY**  
   Remaining applicable uncertainty channels are closed, model discrepancy is handled where relevant, claims/planning integration is complete, the domain is integrated through the Domain Pack contract when domain-owned, and documentation is complete.

A stage is cumulative. A capability cannot skip an earlier incomplete gate.

## Gate semantics

- **PASS** requires repository evidence.
- **MISSING** requires a concrete next action.
- **NOT_APPLICABLE** requires a rationale. It must never mean "not implemented yet" or "unknown".

The machine-readable source of truth is:

`docs/project/scientific_capability_completion.json`

The human matrix is generated from it:

`docs/SCIENTIFIC_CAPABILITY_MATRIX.md`

The checker is:

`python -m tools.capability_maturity`

To regenerate the matrix after a reviewed ledger change:

`python -m tools.capability_maturity --write`

## Active epic rule

The current active epic is **engrt.numerical_foundations** (a research program; OD-6, owner decision 2026-10-18,
contract [ENGINEERING_FOUNDATIONS_PROGRAM.md](ENGINEERING_FOUNDATIONS_PROGRAM.md)).

Until every gate of the program is decided (PASS, FAIL or BLOCKED_WITH_EVIDENCE), horizontal expansion into new
capability foundations OUTSIDE the program's `allowed_scope` is paused by policy. Inside it, the capability work the
program contract names is allowed without a further exception. Work on defects, stabilization, verification
infrastructure, or prerequisites is still allowed everywhere. Starting any other genuinely new capability foundation
requires an explicit reviewed exception in the PR rationale.

(Before OD-6 the active epic was the capability `battery.thevenin_1rc`; it stays tracked at its computed stage with
every gate and its evidence unchanged.)

## Research program epics (schema /2, OD-6)

The ledger's `active_epic` may name a capability (maturity stages, 19 gates) or a research program
(`research_programs`). A research program has **gates, not maturity stages** (`PASS`, `FAIL`, `MISSING`,
`BLOCKED_WITH_EVIDENCE`, `DEFERRED_BY_OWNER`); a gate is decided only after every gate it requires passed; PASS and
FAIL need existing evidence; a program carries no maturity vocabulary. Gate dependencies order DECISIONS only:
any work inside a program's scope may be built at any time, before any gate (including a validation gate) is run. **A research result never promotes a
capability** (Gate H): every capability a program builds is tracked in `capabilities`, enters at FOUNDATION only when
its four FOUNDATION gates pass, and climbs only through the maturity gates. `tools/capability_maturity.py` enforces
this, and `tests/test_capability_completion.py` pins the epic and the negative cases.

This is intentionally a repository-development policy, not scientific evidence and not a verdict rule.

The active epic is pinned in `scientific_capability_completion.json`, in `tests/test_capability_completion.py` and in
`.github/pull_request_template.md`. Planning documents cannot change it. The canonical mechanism for changing it is a
separate, reviewed PR that changes the ledger's `active_epic` (and therefore the test and template pins) with the
owner's approval (OWNER_DECISION_REQUIRED OD-6 in `docs/work/ACTIVE_PLAN.md`).

## The active epic and the current plan tracks (2026-10-11)

This section applies the rule above to the tracks in `docs/work/ACTIVE_PLAN.md`. It neither relaxes the rule nor changes
any maturity requirement. There is **no blanket exemption** for any track.

| Work | Allowed under the current active epic? | Condition |
|---|---|---|
| G0 Trust lane | Yes | Defects, stabilization, verification infrastructure. |
| A1 Genesis-lite preparation | Yes, within limits | Only benchmark, governance, measurement, stabilization or evaluation infrastructure: extending the existing Blindfold harness, its baselines, scoring, preregistration, leakage controls and cost measurement. It must not add a new scientific capability (no new hypothesis generator, planner, belief state, outcome model or domain capability). A change that would is handled like A2. |
| A2 Minimal Mind | **Not until one condition holds** | Either (1) the active epic was formally changed through the canonical mechanism above to a program whose scope includes it (OD-6 chose `engrt.numerical_foundations`, which does not), or (2) a narrowly scoped reviewed exception that meets every requirement below exists, is owner-approved and has not expired. |
| B1 demo preparation | Yes, using already-built capabilities | Existing Trust layer, `drone_coupled`, existing providers, and data admitted through existing provenance contracts. |
| B1 new capability foundations (a new model, provider adapter or synthesis engine for the demo) | Same rule as A2 | Active-epic change, or its own narrowly scoped reviewed exception. |

A reviewed exception must state all of:

1. **exact scope** — the capability or capabilities, and the code areas it may touch;
2. **allowed capability work** — what may be built;
3. **reason** — why it cannot wait for the active epic;
4. **start condition;**
5. **exit condition** — the gate that closes it;
6. **expiry / timebox** — when it lapses even if unfinished;
7. **owner approval** — who approved and when;
8. **what remains prohibited.**

It is recorded in the PR's "Active-epic exception" section and listed in `docs/work/ACTIVE_PLAN.md` while open. An
exception that is missing any field is not an exception. "Track A and Track B are exempt" is not a valid exception.

**Anti-loophole rule.** Repeated or program-wide exceptions are evidence that the active-epic policy itself must be
reviewed; exceptions may not become the default roadmap mechanism. A second concurrent exception, or the renewal of an
expired one, therefore triggers an OWNER_DECISION_REQUIRED review of the active epic, and no further exception is
granted until that review is decided.

## Relationship to the planning documents (2026-10-11)

- This policy and its ledger own maturity vocabulary and promotion: FOUNDATION → FUNCTIONAL → EVIDENCE_BACKED →
  PRODUCTION_READY. No planning document may assert, imply or schedule a stage the ledger does not compute.
- **Primary progress metric** for the whole program (`docs/project/FORGE_MASTER_PLAN.md` Part I §5.4): how many relevant
  capabilities advanced in computed evidence maturity — not how many foundations, providers or features were added.
- A Genesis benchmark result, a Blindfold score or the Track B demo never promotes a capability by itself. Promotion
  happens only through this ledger's gates with repository evidence (Genesis Gate H).
- Building something new is FOUNDATION at most until its own gates pass; "built", "merged" and "executed" are not stages.

## Why this exists

The anti-pattern being prevented is:

Feature -> foundation -> tests -> merge -> move to another feature

The required pattern is:

Capability -> foundation -> functional execution -> evidence -> UQ/benchmark closure -> production integration -> done

Small PRs are still encouraged. The restriction is on abandoning the active epic, not on forcing all work into one large pull request.
