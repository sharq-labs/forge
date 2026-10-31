---
ai_schema_version: 1
doc_id: FORGE-STEP-RECORD-TEMPLATE
doc_kind: POLICY_GUIDE
doc_status: ACTIVE
authority_scope: NONE
source_ref: a9ddbf274cc5d24a8f14236586d8bd94a2760fcb
evidence_level: DERIVED
last_reviewed: 2026-10-30
supersedes: none
---

# Step record template (one file per step)

Owner direction 2026-10-30: new bounded steps use **one** record instead of the four files
`*_ARCHITECTURE_DECISION.md`, `*_COMPATIBILITY_MATRIX.md`, `*_MERGE_PACKAGE.md`, `*_STATIC_REVIEW.md`.
Existing records stay as they are. This template is a format, not an approval; `ACTIVE_PLAN.md` stays the only
queue and `PROGRESS.md` keeps the executed commands. Copy it to `docs/work/<STEP_ID>.md` and delete unused rows.

## 1. Decision

- Step ID / ACTIVE_PLAN section:
- Owner approval (quote, date):
- Options considered (at least two) and the one chosen, one line each:

## 2. Compatibility

| Surface | Changed? | Identity/serialization effect | Certified scope? |
|---|---|---|---|
| | | | |

## 3. Review

- Reviewer (skill/agent), date, verdict:
- Findings: ID, severity, fixed / recorded-not-fixed (reason):

## 4. Evidence and merge readiness

| Axis | State | Command / SHA / location |
|---|---|---|
| Implementation | | |
| Execution (tests) | | |
| Scientific validation | | |
| Certification (OD-3) | | |
| Owner permission (commit/push/merge) | | |

Missing evidence is written UNKNOWN / NOT RUN, never PASS.
