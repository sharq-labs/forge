A. Scope
Fresh static review of cc7ef06b0d08398173d9448ff47d8abb7e375d44, lens F, using the repository forge-scientific-review skill. Reviewed the 98d72b2e..cc7ef06 retained normalization change, surrounding capture/reconciliation, canonical entry owners, closest R16/R17 controls, scoped contracts and R17 evidence. No source changes. Tests/probes/imports NOT RUN. Only these two review artifacts are written.

B. Authority boundary
Q1 NO; Q2 NO; Q3 NO; Q4 YES; Q5 NO; Q6 NO; Q7 NO within this bounded lens. The open defect is Q4 currentness after handed spend, not a newly demonstrated external-proposer escape or arbitrary unadmitted execution. Registry replacement is ordinary owner checkpoint use; no private mutation/introspection is needed. Capture failure caused by native resource exhaustion does not move the case outside the documented process boundary.

C. Applicability and model use
The changed helper normalizes owner entries for history ordering. It does not choose a model or grant applicability. ScientificEvaluation.from_dict retains the existing owner validity checks. Whole experiment readback still reconstructs the experiment and checks accounting/budget; per-entry reconciliation is not an independent experiment validator.

D. Verification / validation
Static source correspondence supports the R17 JSON-parity correction. R17 logs and repair summaries are historical software evidence, bound to their own source identity; they do not prove this R18 tree passes. The report correctly keeps BR1.1 NOT CLOSED and does not claim scientific validation or certification. No new execution result is asserted here.

E. Uncertainty
No uncertainty semantics changed. The documented lack of a hard enclosure or owner decision-coverage policy remains a refusal, not zero uncertainty or a guaranteed band. Owner JSON normalization does not promote evaluation status, probabilistic evidence or model discrepancy into deterministic physical truth.

F. Evidence / context / policy
_retained_entry follows the charge portion of BudgetLedger.from_dict -> sorted JSON/default=str -> BudgetLedger.from_dict. Iteration normalization precedes JSON, and numeric mapping keys/tuples obtain the same JSON transformations as ordinary history. Experiment entries use to_json -> ScientificEvaluation.from_dict -> to_json writability, matching their portion of _read_once without importing ledger permissiveness. Unknown or invalid retained serialization leaves unresolved obligations, not equality. Global experiment checks remain in _read_once. Hash agreement establishes an owner-normalized history relation, not scientific truth.

G. Provenance / replay
Every retained observation remains scoped to its (kind, account ID). Identity-incomparable observations remain together until canonical reconciliation. The lock accepts a resolved result only against the identical pending barrier. Every normalized history must be comparable with accumulated seen history; one convenient matching history cannot discard a conflicting branch. Seal checks remain before comparison and after waiting. The unresolved capture gap occurs earlier: a mutable returned mapping can lose the association to the spent owner object before native retention.

H. Adversarial test coverage
R17 controls cover numeric/string keys, tuples, ledger iteration-before-JSON, default=str/nonfinite contrast, real rollback/rewrite and unread invalid histories. R16 sources cover multiple detached handings, conflicting branches, changed barriers during unlocked reconciliation, experiment attempts and post-return interruption. These are relevant bounded controls, not an exhaustive state-space proof; none were run by this reviewer. The historical R17 S1 native probe reports calls=2 after raw returned handing and checkpoint replacement at depths 145/146. The capture mechanism is unchanged in the reviewed diff. A future stable owner handing fix needs matched repeated-interruption/refusal and honest-recovery controls, including multiple readers and experiments.

I. Findings
R18-F-1 — MAJOR — Q4 — src/engcore/mind/world/owners.py:1015, BudgetReader.pinned/_recover_handing.
Smallest counterexample: dispatch and settle after saving an old checkpoint; the callback returns its live account dict; capture and immediate recovery both fail before retaining its entries; owner replaces the dict entry with that old checkpoint; subsequent recovery reads the replacement and loses the handed spend. Static path: raw mapping assignment at 1015/1041, re-reading through 936/955, then removal of pending handoff at 949. Historical native R17 evidence independently records this family; no R18 probe run by F. Expected: unavailable handed history must not become acceptance, while honest interruption must not permanently poison the reader.
Minimal correction/decision: preserve the returned account association and append-only histories through reader retention/reconciliation. Returning fresh detached dicts containing the existing canonical owner objects is a concrete local owner-adapter option for this replacement family: the retained callback result keeps the spent object reachable after registry replacement. Specify that the returned dict is not subsequently mutated and define its lifetime/release; exercise repeated interruption and recovery. A full publication/acknowledgement subsystem is one possible wider solution, not a proven minimum. Additional reader retries/sentinels cannot reconstruct an object reference already erased from a shared dict. Keep this open for closure; do not claim all local fixes are impossible.

R17-F-2 disposition: repaired in static inspection. No new MINOR or additional scientific-authority defect established. Serializers must remain distinct; using ledger default=str for experiment entries would widen the owner rule.

J. Verdict
CHANGES REQUIRED
