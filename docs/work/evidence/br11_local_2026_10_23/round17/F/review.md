# A. Scope
Fresh static lens F review of 98d72b2ef854012780f4222706884b911c4a2f03 against b8a65bb9. Read repository scientific-review skill, CLAUDE, architecture and scientific-intelligence contracts, active BR1.1 entry, lifecycle README, R16 matrix/owner proposal, changed production implementation, closest R16 controls and canonical BudgetCharge/ScientificEvaluation definitions. Git HEAD matches the requested SHA. Only file/git reads and these two output writes were performed. Tests and probes: **NOT RUN**.

# B. Authority boundary
BudgetLedger and ScientificExperiment remain the authorities for charge/evaluation content. The follower may preserve observations and refuse currentness; it may not invent charges or establish corruption from missing data. Multiple retained identities are provisional observations, not independent budgets. Caller handoff is the execution-side trust boundary; ordinary checkpoint replacement is in scope. The open pre-capture case needs no private scientific-record mutation. Q1 NO, Q2 NO, Q3 NO, Q4 YES, Q5 NO, Q6 NO, Q7 NO within this bounded diff; Q4 is YES for hidden spend, not a demonstrated new design/search subsystem. Redispatch here reuses an admitted action, so it is not separately classified as an unadmitted-action Q7 bypass.

# C. Applicability and model use
The repair neither selects models nor changes applicability. Reconstructing ScientificEvaluation invokes existing owner checks; it does not create an independent validity assessment. No changed-code evidence supports an applicability bypass.

# D. Verification / validation
Synthetic regression controls establish software properties only when executed. I inspected their code but ran none. The retained open-capture log is historical execution evidence, explicitly separated from my source-level reasoning. Neither its negative outcome nor the reported suite counts confer scientific validation, certification, owner approval or complete concurrent correctness.

# E. Uncertainty
No new uncertainty values or enclosure policy appear in this diff. Missing hard enclosure remains a failed-closed owner capability, not zero uncertainty. Preserving an evaluation in budget history does not make its values physically true or improve its validation status.

# F. Evidence / context / policy
Canonical reconciliation must preserve every unresolved observation. At 774-786 all normalized histories must form a prefix chain with seen history; incompatibility refuses, and unavailable normalization does not clear the barrier. This respects unresolved alternatives better than interpreting identity mismatch as divergence. Account kind/id keys remain the context; no policy statement becomes evidence. However, the owner normalization must include the entire text/read-back transformation, not just from_dict (R17-F-2).

# G. Provenance / replay
Exact barrier object identity guards unlocked reconciliation against replacement. The updated history is compared under the same lock as seal status; a verification starting open has no entitlement to finish its authoritative comparison after sealing. The post-wait seal check remains. No changed path claims authenticity of externally supplied records; owner replay/self-consistency is distinct from physical provenance. Native retention still preserves account references only after capture succeeds: a mutable pending mapping is not a historical snapshot (R17-F-1).

# H. Adversarial test coverage
Inspected 16 R16 parametrized controls covering iteration normalization, repeated detached interruption, post-return one-shot interruption, rollback/different histories, unread reconciliation, concurrent barrier replacement, malformed owner normalization, experiment attempts and returning to a conflicting first branch. These do not cover the full JSON-roundtrip mismatch below. Separate expected-refusal pre-capture challenge remains failing in preserved evidence. No test execution by this lens. Interruption during reconciliation remains refusal while barriers survive, rather than equality; exact barrier staleness is controlled. Memory growth with identity-incomparable unresolved histories is documented and cannot be cured by silently dropping observations.

# I. Findings
## R17-F-1 — MAJOR — Q4
**File/symbol:** owners.py:999-1000, BudgetReader.pinned; _recover_handing:919-920; _handed:939.
**Smallest counterexample:** A dispatch settles a charge; a following reader is handed the live mapping; initial native capture and immediate recovery both interrupt before retaining account references. Owner replaces mapping entry with a pre-charge checkpoint. Later recovery reads the restored mapping and admits redispatch. Source supports this information-loss transition; preserved REPAIR/open-capture.log records the refusal assertion failing. I did not rerun it.
**Expected/actual:** Preserve the handed spend or refuse uncertainty; instead the recoverable state contains only the mapping's new contents. This crosses the documented boundary through ordinary owner restore, not private introspection.
**Minimal correction and decision:** A stable retained snapshot/history publication through owner acknowledgement addresses the missing lifetime. OWNER_HANDOFF_DECISION.md is PROPOSED, NOT APPROVED. Do not interpret it as authorization. Local alternatives should still be evaluated: immediate map/account/entry capture and exception-safe registration reduce reachable gaps; they do not recover information after all capture attempts failed. A persistent unresolved marker is locally fail-closed but cannot regain honest unchanged usability from an indistinguishable restored state without further authoritative information. A fresh reader changes timeline semantics and is not recovery. Moving capture into a callback or native helper does not alone specify the lifetime through interruption/restore. An owner-provided immutable handoff or existing canonical owner history plus explicit publication/acknowledgement may satisfy the requirement without a second ledger. The evidence is conditional information loss, not blanket impossibility of local engineering or a formal proof.

## R17-F-2 — MINOR — Q4
**File/symbol:** owners.py:759, BudgetReader._observe_all, versus _read_once:497-501 and _history:481-483; budget.py:130,321.
**Smallest counterexample:** After creating a following reader on an empty ledger, settle a charge with detail={2: "a", 10: "b"}. Interrupt after mapping capture, retaining the new entry. Hand back an unchanged detached BudgetLedger.from_dict(account.to_dict()). The existing owner accepts the detail and preserves it; no private mutation is necessary.
**Expected/actual:** Honest owner-readable checkpoint should recover. Static derivation: retained BudgetCharge.from_dict leaves integer detail keys, whose sorted JSON order is 2,10; ordinary owner read serializes and JSON-decodes them to strings, whose next sorted JSON order is "10","2". Hashes differ; after resolved history adoption the ordinary current history is labelled rewritten and permanently refused at 807-811. This is a narrower false-refusal correctness defect, not hidden spend or scientific truth promotion. Executable confirmation was requested from parent; this report asserts source reasoning only.
**Minimal correction:** Reuse the complete existing owner text/read-back normalization before retained hashing, with deterministic numeric-key equivalence and true-conflict controls. Merely banning owner-accepted values in the follower would create a second readability authority.

# J. Verdict
CHANGES REQUIRED
