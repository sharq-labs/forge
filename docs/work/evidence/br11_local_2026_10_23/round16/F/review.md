# A. Scope

Independent Round 16 lens F: scientific semantics and review completeness. Exact committed SHA `b8a65bb9d02b5a18e0a8b26779773c1552204dc1`, native checkout `/home/dev_kaeem/forge-r16-review`, comparison base `95f3869e`. `git rev-parse HEAD` returned the required SHA; `git status --short` returned no changes. This is STATIC REVIEW. Tests and probes were NOT RUN by this lens. No physical validation, certification or formal proof is claimed.

Applied `.claude/skills/forge-scientific-review/SKILL.md`. Read the brief, CLAUDE contract, architecture map, Scientific Core ownership and freeze policy, scientific-intelligence layer, relevant Master Plan and Genesis authority sections, current BR1.1 queue, README lifecycle clarification/R15 dispositions, all 25 threat-matrix rows and repair self-checks, changed production source, full R15 controls and generated trace source, changed R14 control, and closest owner/admission/applicability/UQ code and tests. Historical findings are context, not current-tree proof.

# B. Authority boundary

The intended `_RetainedHanding`, `_uncompared`, `_unread_entries` and `_seen` structures are reader lifecycle and change-detection bookkeeping. They do not settle charges, reserve budget, choose models, create scientific evidence or issue scientific support. They are not inherently a second scientific authority. Their comparisons must nevertheless preserve the canonical owner's accounting identity and must not forget a handed spend. The findings below show failures of those obligations.

The public interface keeps the Mind behind `AdmissionGateway`. `admit` rebuilds and verifies the projection, and `authorize_dispatch` requires live readers and identical re-admission. Neither finding requires private mutation of owner accounting. A deterministic interruption hook selects an asynchronous event; it is not the substantive accounting operation.

| Question | Answer | Reason within this lens |
|---|---|---|
| Q1 second state authority | NO | Canonical run state remains the owner; no new defect found. |
| Q2 second applicability authority | NO | Core validity assessment governs; UNKNOWN and non-exact inputs refuse model execution. |
| Q3 duplicate units authority | NO | No changed units owner or independent conversion authority found. |
| Q4 duplicate design/search/budget authority, currentness and hidden spend | YES | Proposed MAJOR R16-F-2; substantive MINORs R16-F-1 and R16-F-3 also apply. These findings are static, not executed probes. |
| Q5 scientific verdict or probabilistic evidence promoted to deterministic truth | NO | Admission is explicitly not scientific support; uncertain current values do not prove containment. |
| Q6 external proposer bypass | NO | No new bypass of public admission established. |
| Q7 execution of an unadmitted action | NO | No raw/unadmitted-action path established; R16-F-2 is erroneous re-admission after lost handed spend, classified under Q4 by the brief. |

There is an explicit handoff-contract decision, not a demonstrated impossibility of a repair. Once an interruption has lost all information about a handed mutable mapping, two histories can leave identical reader/current-owner state: (a) unchanged S0 handed then interrupted; (b) S1 containing a spend handed, interrupted before retention, then restored to S0. The old API supplies no observation that distinguishes them at recovery. Clearing the uncertainty accepts (b); permanently refusing both rejects the honest (a). This is a conditional information-loss argument about that state, not a proof that all generic designs fail.

A concrete generic alternative is an execution-side handoff that retains an immutable owner snapshot/version until acknowledgement, publishes it into a pre-registered reader slot at an explicit commit point, and permits replay of every unacknowledged handoff. A failure before publication commits no handoff; after publication the same immutable state remains recoverable. Comparison uses existing canonical owner read-back rules, and acknowledgement follows authoritative comparison. This need not be a second budget ledger, reservation mechanism or evidence authority: its records are transport/lifecycle obligations over owner records. It does require explicit execution-side retention/restore obligations and a clear definition of the handoff commit point. Mutable legacy callbacks cannot silently inherit stronger guarantees. No production change is proposed as authorized by this review.

Evidence needed for such a narrow alternative: deterministic checkpoints before and after publication, during capture/comparison/acknowledgement, repeated interruption, concurrent restore and multiple readers; canonical-normalization equivalence; no owner-content execution under the comparison lock; no permanent corruption classification from resource failure alone; finite-interruption honest recovery and spent-restore refusal; bounded mutation controls and preserved replay identities. Resource exhaustion or endless interruption may prevent progress, but must not count as acceptance or evidence of corruption.

# C. Applicability and model use

`feasibility.py:854-918` delegates exact-point validity to the core model. UNKNOWN and unassessable inputs become MISSING_INFORMATION. Current values, including declared set points, do not become exact applicability inputs. Gating is explicit for MODEL_EXECUTION; annotations on other action kinds do not grant model validity. The repair changes no applicability/model-selection owner. No new applicability defect was established.

# D. Verification / validation

The README and new tests label fixtures and the bounded trace grammar as synthetic development/contract evidence. They withhold physical validation, formal proof, certification and BR1.1 closure. Preserved logs read here report 89 passed in `completed_mutation_batch/mutant_control.log`, 115 passed in `l1_release.log`, and 781 passed in `l2_native_handoff.log`. These are historical log results, not commands executed by this lens. The earlier `l2_completed_source.log` reports 759 and must not replace the later result.

The exact owner/test hashes read here match `tested_source_manifest.json`. The gate manifest identifies `ec4d23dc238d2e8818170a4029a010538e23af72` as its clean source snapshot and reports unchanged-base failures explicitly. That is not an all-green gate claim. Bounded controls and killed mutants do not establish exhaustive interruption coverage; the three families below are absent from the inspected new controls.

# E. Uncertainty

`feasibility._world_basis` at `feasibility.py:305-323` preserves unknown uncertainty and the missing hard-enclosure capability as explicit inability to decide containment. Quantified intervals do not become guaranteed bounds; UNKNOWN does not improve the answer. Requested configurations are labeled exact as requested, with realization uncertainty unassessed. The repair adds no uncertainty/discrepancy producer or zero-uncertainty inference.

# F. Evidence / context / policy

Ordinary failed owner reads become authority refusal. Structural invalid handing now seals separately from asynchronous/resource interruption. Seal checks under the comparison lock and after waiting (`owners.py:752-756,839-840`) address the inspected R15 seal family. Unresolved retained history ordinarily refuses at `804-806`. A handing lost before lifecycle registration, however, becomes indistinguishable from no observation on a later pin (R16-F-2).

Declarations remain caller-declared and held in force by the execution side, not measurement evidence. Risk policy is unchanged. No scientific evidence removal was found to increase scientific assurance in the changed implementation. The defects are accounting-currentness and false-corruption decisions, not new physical validation claims.

# G. Provenance / replay

Replay remains self-consistency under owner rules, not proof the owner held a record historically or is current now. Fresh dispatch re-admits against live readers. Recovery hashes govern temporal accounting consistency, so they must match the owner read-back identity. R16-F-1 currently creates a false different-history assertion for an honest checkpoint.

Read file hashes: owners.py `96a576efb138aa76fd0c9a687ae0b09e702d8a90a65466f06a5a917e272f1367`; R15 controls `fb7401741ca3dd115cc2933887e359d162eae96c44d3026d6f41d34904736ada`; R15 trace source `d6686cf2e32a209de108f6624ed4a90d4fd6a9e3bd44268cb71889aea61ab69c`.

# H. Adversarial test coverage

Statically inspected controls cover seal before comparison/after waiting; atomic comparison; interruption inside `_handed`; rollback/ABA/history-length mismatch; append-only growth; ordinary detached recovery; repeated current-content KeyboardInterrupt; retired-account skip; native pair subclasses; and immediate/deferred recovery after native retention. The generated grammar has 24 owner traces, 6 dispatch traces and 24 inflight traces. It is not every Python interruption boundary.

Missing coverage:

- Owner-valid raw numeric entries whose `from_dict` normalization changes representation, then interruption and honest detached restoration. Existing recovery fixtures use `settle`, which already casts realized costs to floats.
- One interruption after `accounts()` returns but before `_uncompared` registration.
- Repeated interruption during native capture, before stable entries exist, followed by live dictionary replacement. Existing `retry_later` controls interrupt `_handed` after capture.
- Two separate interrupted pins returning canonically identical detached objects, rather than repeated recovery of one retained handing.
- The analogous owner-normalization matrix for experiments; this is a gap, not an additional established defect.

Cross-process coordination, durable reservations/at-most-once effects and spend/rollback wholly between verifications remain explicit limits. No tests/probes were executed by this lens. Static traces below are not presented as observed runtime outputs.

# I. Findings

## R16-F-1 — MINOR — Q4: retained reconciliation hashes raw entries instead of owner-normalized entries

**Location:** `src/engcore/mind/world/owners.py:745`, `BudgetReader._observe_all`; supporting `472-474,488-492,763-767,789-794`. Owner: `src/engcore/sria/campaign/budget.py:83-94,117-130,259-271`.

**Smallest counterexample (static; NOT RUN):** Start a following reader over an empty `BudgetLedger(100)`. Hand a replacement ledger constructed publicly with one `BudgetCharge(charge_id='c', action_id='a', iteration=0, family=ActionFamily.EXPLORE, realized=1, from_general_pool=1)`. Integer numeric inputs are accepted. Let one KeyboardInterrupt arrive before that ledger's `_account` read-back; native recovery retains the charge. Replace the mapping entry with `BudgetLedger.from_dict(raw_ledger.to_dict())`, an honest unchanged checkpoint restore, and read again.

**Actual result derived from source:** line 745 hashes raw integer `1` fields; since seen history is empty, `763-765` installs that hash in `_seen`. Normal `_read_once` hashes owner-normalized float `1.0` fields (budget.py `124,129`). JSON distinguishes the representations. Equal-length histories now differ, so `790-794` permanently mark `_diverged` with a false rewritten-history reason. This result was not executed here.

**Expected:** an unchanged canonical checkpoint recovers without retirement. Interruption alone does not establish corruption.

**Threat families:** canonicalization/identity; interruption recovery; detached restore; false corruption/availability; parallel accounting comparison semantics.

**Boundary/severity:** public constructors/restoration suffice; no private mutation. This is narrower accounting correctness/availability, not demonstrated wrong admission, hence MINOR and Q4 PARTIAL in isolation.

**Minimal correction:** normalize retained entries through exactly the existing owner's read-back and JSON rules before applying the existing history comparison. Do not change frozen owner semantics or invent a new normalization vocabulary. Add integer-charge and other owner-normalization recovery controls while retaining refusal for genuinely different canonical histories.

## R16-F-2 — MAJOR (proposed from static evidence) — Q4: interruption before retention loses a returned handing's spend

**Location:** `src/engcore/mind/world/owners.py:970-978`, `BudgetReader.pinned`; supporting `995-1003,865-874`.

**Smallest counterexample (static; NOT RUN):** Admit at checkpoint S0 and execute once; the ordinary executor settles a charge S1. Call `reader.pinned()`; `accounts()` returns valid plain dictionaries holding S1. Deliver one KeyboardInterrupt at `975/976`, after `handed=True` but before `_uncompared[ticket] = mapping`. Catch it, restore the mapping entry through public checkpoint restoration of S0, and re-dispatch the earlier admitted action. A one-shot line checkpoint can deterministically select this external interruption; no private owner accounting mutation is needed.

**Actual result derived from source:** the outer handler recovers only a ticket already in `_uncompared` (1000). S1 reaches neither `_seen` nor `_unread_entries`. `_leave` removes the ticket and only flags already waiting verifications; it retains no history. The later S0 equals the prior seen state, so the reader accepts it, allowing normal re-admission to authorize the old action again. Duplicate execution was NOT observed by this lens.

**Expected:** state handed before interruption remains unresolved/recoverable before any later acceptance. Aborting the interrupted call must not erase handed spend and improve subsequent currentness.

**Related transition:** line 977 initially stores the raw live mapping pair; line 978 replaces it only after capture succeeds. Interrupt capture and its immediate recovery before `_items` completes, then replace the dictionary entry with S0. Deferred recovery sees the replacement through the retained live pair. This is the same unretained-handing family, not a separately executed result.

**Threat families:** async interruption; acquisition/registration gap; hidden spend; live mapping replacement; rollback/restore; duplicate dispatch; missing regression boundary.

**Boundary/severity:** valid dict handing, operator interruption and public checkpoint restore cross the documented execution interface. S1 was handed; this is not spend/rollback wholly between verifications. The brief classifies handed-spend loss permitting redispatch as MAJOR. The grade here is proposed on precise static evidence for independent runtime falsification, not a claim of local execution. Q4 YES; no raw-action bypass claim under Q7.

**Minimal correction:** make handoff acquisition/retention and exceptional exit one recoverable lifecycle operation. A returned local mapping not yet registered cannot be forgotten on exception; interrupted capture cannot depend on a live mapping that can subsequently replace its contents. Add checkpoints before registration, during capture/recovery, then restore and assert executor call count. Section B describes a concrete generic retained/acknowledged owner handoff alternative if the existing callback contract cannot supply enough information. Do not solve this by permanently sealing an honest reader on interruption.

## R16-F-3 — MINOR — Q4: two interrupted detached handings falsely establish rewritten history

**Location:** `src/engcore/mind/world/owners.py:912`, `BudgetReader._recover_handing`; supporting `_note_unread` `677-692`, especially `687-690`.

**Smallest counterexample (static; NOT RUN):** The stable execution-side ledger has one ordinary settled charge. `accounts()` returns a fresh `BudgetLedger.from_dict(ledger.to_dict())` on every call. Construct a following reader. On each of two separate later pins, let a one-shot KeyboardInterrupt land in `_handed` after native capture; allow each exception handler's recovery to complete. The owner and canonical payload never change. Finally perform an uninterrupted read.

**Actual result derived from source:** first recovery records detached charge objects U1 as an unread barrier (they are not the baseline's objects). The second recovery calls `_note_unread` with equally valued U2 objects. Neither identity prefix relation holds, so `689-690` permanently set `_diverged` to the rewritten-history reason. Canonical reconciliation is never reached to establish U1 and U2 are the same owner history. The later read is permanently refused. This is not a runtime observation by this lens.

**Expected:** repeated finite interruption of an unchanged honest detached owner may delay acceptance, but cannot establish corruption or permanently retire the reader/account.

**Threat families:** interrupted-to-interrupted transition; detached identity versus canonical equality; false corruption; availability; recovery bypassing reconciliation.

**Boundary/severity:** ordinary public checkpoint copies and external interruptions suffice; no owner-private mutation. A substantive MINOR authority/correctness defect, making Q4 PARTIAL in isolation.

**Minimal correction:** do not classify incompatible entry identities as semantic rewrite during native-only recovery. Retain the unresolved obligations and compare them through canonical owner history outside the lock before deciding equality/divergence; apply the result only to the still-identical pending barriers. Cover two and three separate interrupted detached handings, then honest recovery, and a contrasting true spent/rewritten history. Preserve finite interruption recovery without making unavailable history equality.

# J. Verdict

CHANGES REQUIRED
