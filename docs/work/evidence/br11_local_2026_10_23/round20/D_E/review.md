# Round 20 D/E independent serialization, replay and scientific review

## A. Scope
Immutable SHA b4bbee0f6df40b7dd0de9b0739beef392dab6be5; owners.py SHA256 efad8b564d00331877308151648554970222652a3249220c7fe934d4118eb7a3. Native WSL Ubuntu-24.04, existing .venv. Source was read, not edited. Read CLAUDE.md, forge-scientific-review SKILL.md, architecture README, scientific-intelligence-layer, relevant owners.py paths and closest lifetime/R19 tests; traced projection, feasibility and admission consumers. The review is independent of the builder. No claim of exhaustive scheduling exploration or physical validation.

## B. Authority boundary
AccountPublication retains native bindings; it is not a competing ledger and computes no remaining budget. BudgetReader normalizes through BudgetLedger/BudgetCharge and ScientificExperiment/ScientificEvaluation (owners.py:598-649). Comparison retains canonical history prefixes; it does not manufacture scientific evidence. The new final source check (445-455, 1057-1087) retries when another generation arrives; retained bindings remain original handoff bindings while newly published histories constrain them. Equal detached identities are unresolved until canonical comparison, not evidence of permanent divergence (832-857, 904-916). That correction preserves the distinction between unknown relation and proven rewrite.

## C. Applicability and model use
No new applicability authority in this change. Projection reads exact model owner records (projection.py:69-74), while feasibility delegates validity to existing Core. A publication token does not select a model or assert applicability. Static consumer tracing only; no new model-qualification evidence was generated.

## D. Verification / validation
Executed tests establish bounded software behavior. They do not validate physics, qualify a model, certify a solver, or promote verification to validation. Feasibility remains action_feasibility_not_scientific_support (feasibility.py:77). The publication/history methods produce no Evidence or ValidationLevel records. No scientific verdict route was introduced.

## E. Uncertainty
No new UQ vocabulary or missing-to-zero rule. Projection reconstructs the owner's uncertainty (projection.py:67), rather than filling absence. Existing feasibility current-value containment remains MISSING_INFORMATION without hard enclosure (feasibility.py:28-38). Independently executed a cyclic, unreadable retained charge detail followed by an empty detached replacement: three acquisitions refused; unknown retained history did not become zero spend. This is an authority control, not an uncertainty-model validation.

## F. Evidence / context / policy
Admission refuses failed owner verification as missing information (admission.py:285-289, 326-330) and rechecks current execution-side authorities before dispatch (410-439). Publication lifetime cannot make risk policy or caller metadata into evidence. Retained history remains source-bound; independently replacing the callback with a foreign-source valid token refused. Scope assumes the stated execution-side publication contract; an owner that never publishes an object before discarding it provides no recoverable lifetime record. New sources are explicitly new timelines, not proof of continuity.

## G. Provenance / replay
Fresh independent probes verified JSON-detached equal ledger histories, including tuple/nested metadata normalized by JSON, retain the same canonical digest; rederive gives the same identity. Conflicting published histories were refused both by the existing reader and a new reader on the same publication source. FrozenReader rebuilds payload identities (owners.py:1399-1503), is never live (1489,1543-1545), and correctly remains historical after the source closes/retires. Forged derived spent_total was rejected. Replay consistency is not proof the owner held the record then, nor authority to execute now. Publication identity/lifetime is in-process and not serialized into a transferable live source.

## H. Adversarial test coverage
Executed exact argv in execution.json; output in focused.log. Command: .venv/bin/python -m pytest -q -p no:cacheprovider /home/dev_kaeem/br11-review/r20/D_E/test_independent.py tests/mind/test_authority_lifetime.py tests/mind/test_authority_publication_currency_r19.py tests/mind/test_authority_review_r16.py
Result: 57 passed in 1.83s, exit 0. Seven fresh independent cases plus 50 existing targeted cases. PYTHONDONTWRITEBYTECODE=1; cache plugin disabled. Source SHA/hash checked after execution, unchanged. No repository writes or PROGRESS edits by this reviewer. One exploratory read of nonexistent world/replay.py failed (FileNotFoundError); actual replay implementation was found in owners.py/admission.py and read. No test harness failures.

## I. Findings
No actionable defect demonstrated in this bounded D/E review. Counts: 0 BLOCKER, 0 MAJOR, 0 MINOR.

Explicit scoped closure questions:
- Q1 second state authority: NO. Owner payload identities and bound projection remain authoritative; publication is lifetime retention.
- Q2 second applicability authority: NO. No added model selection/applicability decision.
- Q3 duplicate units: NO. No added conversion/quantity vocabulary; existing unit authority retained.
- Q4 duplicate design/search or budget authority: NO. Source retains bindings; existing canonical owners derive charges/accounting. History comparison limits admissibility, not spend computation.
- Q5 world issues scientific verdicts: NO. Action feasibility remains expressly distinct from scientific support.
- Q6 external proposer bypass: NO in inspected admission/dispatch consumer paths; foreign publication rejected. This is not a fresh full external-adapter audit.
- Q7 provider executes unadmitted action: NO in inspected guarded dispatch flow. No provider executor changed; concurrency reservation/exactly-once execution remains execution-owner responsibility.

Limits: bounded probes cannot exhaust arbitrary schedules, hostile private-object mutation, catastrophic resource failures, or indefinitely moving owners. Open-source generations grow until terminal closure; retention is a lifecycle/resource tradeoff, not evidence inflation. Final publication observation is a linearization boundary, not a reservation through executor completion. No installs, broad FAST run, certification or physical measurements were performed by this reviewer.

## J. Verdict
PASS
