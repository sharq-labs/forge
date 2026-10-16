# OD-6 approval package: moving the active epic from Battery to Genesis

Prepared 2026-10-14 for the owner. **Nothing below has been applied.** No ledger, checker, test, template, policy or
plan file was changed. Approving this package authorizes a separate reviewed PR. It changes no scientific maturity and
grants no evidence.

Requested transition: active epic `battery.thevenin_1rc` → research epic `genesis.scientific_reasoning`.

## 1. What the active epic does today

| Consumer | Role |
|---|---|
| `docs/project/scientific_capability_completion.json` (schema `forge.scientific_capability_completion/1`) | `active_epic` must name a tracked **capability**. Every capability carries all 19 maturity gates. |
| `tools/capability_maturity.py` | `validate` checks the following, and `render` writes `docs/SCIENTIFIC_CAPABILITY_MATRIX.md`, including the line "Active completion epic: …" and a fixed policy text. The checks: unique ids; the exact field set; the owner path exists; all 19 gates are present; every PASS has existing evidence; the capability meets FOUNDATION; the declared stage is ≤ the computed stage; `active_epic` is a tracked capability and is not already PRODUCTION_READY; `horizontal_expansion_paused` is true. |
| `tests/test_capability_completion.py` | Pins `active_epic == "battery.thevenin_1rc"`, its FOUNDATION stage and `execution` missing. Two other tests use the battery entry as a fixture. |
| `.github/pull_request_template.md` | Line 3 names the epic. The "Active-epic exception" section follows. |
| `docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md` | The active-epic rule, the change mechanism (OD-6), the track table (A2 needs an epic change or an exception), the 8 exception fields, the anti-loophole rule and Genesis Gate H (a benchmark result never promotes a capability). |
| `docs/work/ACTIVE_PLAN.md`, `docs/discovery/FORGE_GENESIS.md` §18, `docs/discovery/BR17_MINIMAL_MIND_READINESS.md`, `docs/project/FORGE_MASTER_PLAN.md` (N2) | Document the A2 start condition that depends on the epic. |
| `tools/forge_check.py` (certified) | Runs the test on every `--changed` run. It does not need to change. |

Nothing under `src/` or `.github/workflows` reads the ledger.

## 2. Options

| | Description | Verdict |
|---|---|---|
| **A. Exception** | Battery stays the epic. One narrowly scoped A2 exception with the 8 fields; no file format changes. | Smallest change, but it does not express a priority transition. It is temporary by design: the anti-loophole rule forbids renewing it. If Genesis is the program's priority for more than one step, this is the mechanism the policy says must not become the roadmap. |
| **B. Genesis as a capability** | Keep schema /1 and add `genesis.scientific_reasoning` as a capability with 19 maturity gates. | **Rejected.** It forces a research program into the maturity vocabulary. `real_data`, `calibration`, `parameter_uq` and the other gates would be faked, NOT_APPLICABLE, or eventually PASS on benchmark evidence. That is exactly the "research success implies maturity" leak Gate H forbids. |
| **C. Research program entry (recommended)** | Schema /2 adds one top-level array, `research_programs`. Entries have their own gate vocabulary and **no** stage. `active_epic` may name a capability or a program. | The smallest change that expresses the priority in the machine-checked ledger without touching maturity semantics. The capability schema and validation stay byte-identical in meaning. |

On the owner's proposed architecture: keeping two separate epic types ("Scientific Capability Epic" with maturity stages, "Research Program Epic" with explicit gates) is correct. C is that design in its minimal form. It adds no new governance file, makes no change to capability validation, and keeps one ledger with one `active_epic`.

## 3. Option C specification

### 3.1 Ledger (`scientific_capability_completion.json`)

- `schema` becomes `"forge.scientific_capability_completion/2"`. `policy` is unchanged.
- `active_epic` becomes `"genesis.scientific_reasoning"`.
- `capabilities` is unchanged. **Battery stays FOUNDATION with every gate, evidence path and next action as today.**
- New array `research_programs`, with exactly one entry:

```json
{
  "id": "genesis.scientific_reasoning",
  "kind": "research_program",
  "title": "Genesis: measured scientific reasoning (Minimal Mind)",
  "contract": "docs/discovery/FORGE_GENESIS.md",
  "owner": "docs/discovery",
  "allowed_scope": ["benchmarks/genesis_lite/**", "<one new non-certified Mind package, named in the A2 PR>"],
  "prohibited": ["new Trust, evidence, hypothesis or benchmark authority", "domain capability work",
                 "LLM authority over priors, thresholds or verdicts", "certified-area change without recertification",
                 "any capability maturity change from a research result (Gate H)"],
  "gates": [
    {"id": "A1", "title": "Genesis-lite formal baselines", "requires": [], "status": "MISSING",
     "evidence": [], "next_action": "OD-3, OD-8, OD-18, OD-19, OD-20, then the formal baseline tier"},
    {"id": "A2", "title": "Minimal Mind beats the strongest frozen baseline", "requires": ["A1"], "status": "MISSING",
     "evidence": [], "next_action": "blocked until A1 PASS"}
  ],
  "exit": "A2 is PASS, FAIL or BLOCKED_WITH_EVIDENCE; the owner then names the next epic"
}
```

- Program gate statuses: `PASS`, `FAIL`, `MISSING`, `BLOCKED_WITH_EVIDENCE`, `DEFERRED_BY_OWNER`. These are Genesis §18 outcomes plus MISSING, never maturity statuses.

### 3.2 `tools/capability_maturity.py`

- `SCHEMA` becomes `/2`.
- `load_ledger` refuses `/1` with "migrate to /2". There is no dual-mode reader, because the repository holds one ledger. This is a single-step migration, not silent compatibility.
- `validate`:
  - The capability rules are unchanged.
  - New `validate_programs`:
    - exactly the program field set;
    - `kind == "research_program"`;
    - `contract` and `owner` paths exist;
    - non-empty `allowed_scope`, `prohibited` and `gates`;
    - gate ids are unique;
    - every `requires` names an earlier gate;
    - a status other than MISSING or DEFERRED_BY_OWNER needs every required gate to be PASS (an A2 PASS, FAIL or BLOCKED_WITH_EVIDENCE before A1 PASS is refused);
    - a PASS or FAIL needs non-empty evidence whose paths exist;
    - MISSING needs a `next_action`;
    - no maturity key (`declared_stage` or any of the 19 gate names) may appear.
  - Ids must be unique across capabilities and programs.
  - `active_epic` must resolve to exactly one capability or program. A capability epic still must not be PRODUCTION_READY; a program epic must not have its exit gate decided.
- `render`:
  - "Active epic: <id> (capability | research program)".
  - A new "Research programs" table (id, gate, status, requires, next action). It never has a stage column.
  - The policy text gains the line "A research program has gates, not maturity stages. A research result never promotes a capability."
- `computed_stage` and `REQUIREMENTS` are untouched. Programs never enter them.

### 3.3 `tests/test_capability_completion.py`

- `test_active_epic_is_battery_1rc_and_still_incomplete` is replaced by two tests:
  - `test_active_epic_is_the_genesis_research_program_with_a2_blocked_until_a1`;
  - `test_battery_1rc_stays_foundation_with_its_evidence`. It compares the battery entry with a frozen snapshot: every PASS gate stays PASS with a superset of its evidence, the stage stays FOUNDATION and the MISSING gates keep a next action.
- The two fixture tests keep using the battery entry unchanged.
- **Editing this file is a recertification trigger** (`tests/**`, `tools/certification/recertification_scope.py`).

### 3.4 Other consumers

| File | Change |
|---|---|
| `docs/SCIENTIFIC_CAPABILITY_MATRIX.md` | Regenerate (`python -m tools.capability_maturity --write`). |
| `.github/pull_request_template.md` | Line 3 becomes "Advances the active epic (`genesis.scientific_reasoning`, research program) or is G0/defect work". The exception section is kept for capability foundations outside the program's `allowed_scope`. |
| `SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md` | Active-epic rule names the program. New section "Research program epics": gates, not stages; allowed scope; Gate H restated; battery remains a FOUNDATION capability, its work allowed as defect, stabilization and evidence work. Track table: A2 allowed inside `allowed_scope` once A1 is PASS; no exception needed. |
| `docs/work/ACTIVE_PLAN.md` | The epic and the A2 start condition. |
| `FORGE_GENESIS.md` §18 Step 2 | The start condition reads "A1 PASS (ledger gate)". |
| `BR17_MINIMAL_MIND_READINESS.md`, `FORGE_MASTER_PLAN.md` N2 | A one-line status update. |
| `docs/biomedical/README.md`, `BLINDFOLD_DISCOVERY.md` | These mention the epic historically: date the mention, no rule change. |

## 4. Negative tests (all in `tests/test_capability_completion.py`)

1. **Nonexistent active epic:** `active_epic = "genesis.nope"` → "must identify a tracked capability or research program".
2. **Incomplete research contract:** in turn, drop `contract` / `allowed_scope` / `prohibited` / `gates`; use a contract path that does not exist; set an unknown status → each is refused.
3. **Duplicate ids:** a program whose id equals a capability id, and two programs with one id → refused.
4. **False research PASS:** A1 PASS with empty evidence; A1 PASS with an evidence path that does not exist → refused.
5. **False maturity promotion:**
   - a program carrying `declared_stage` or any maturity gate name → refused;
   - adding a program with every gate PASS leaves every capability's `computed_stage` unchanged (asserted);
   - setting battery to EVIDENCE_BACKED "because A1 passed" → the existing declared > computed error.
6. **A2 before A1:** A2 PASS, FAIL or BLOCKED_WITH_EVIDENCE while A1 is MISSING → refused. A2 MISSING or DEFERRED_BY_OWNER → allowed.
7. **Battery evidence discarded:** remove one evidence path from a battery PASS gate, or flip a PASS to MISSING → the snapshot test fails.
8. **Inconsistent governance documents:** the policy's "current active epic is **…**", the PR template's line 3, ACTIVE_PLAN's epic line and the regenerated matrix must all name the ledger's `active_epic` → a mismatch fails.

## 5. Battery impact

- `battery.thevenin_1rc` stays a tracked capability at **FOUNDATION**. 7 gates PASS, 11 MISSING and 1 NOT_APPLICABLE, all unchanged.
- Its historical outcomes stay recorded: Sprint 3 Gate A not passed; Kirkaldy fade NOT MET; Practical Pass 1 WEAKLY_IDENTIFIABLE (local only).
- It is no longer the active epic. Defects, stabilization and evidence work on it stay allowed. New battery capability foundations then need their own exception.
- Nothing about it is discarded; test 7 enforces that.

## 6. Sequencing and certification impact

- The ledger, checker, matrix, policy and template are outside the certificate. **The test edit triggers recertification.**
- If OD-6 is approved before OD-3, put the migration PR into the same recertification candidate. Otherwise one more hardened recertification is needed afterwards.
- Approving OD-6 does not open A2. A2 still requires A1 PASS, and A1 needs OD-3, OD-8, OD-18, OD-19 and OD-20 plus the formal tier.

## 7. Decision requested

**OD-6:** approve Option C (schema /2 research-program epic `genesis.scientific_reasoning`, battery kept at FOUNDATION, Gate H unchanged), or Option A (one time-boxed exception), or neither. Also say whether the migration PR joins the OD-3 recertification candidate.
