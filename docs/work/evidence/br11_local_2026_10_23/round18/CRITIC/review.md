# R18 completeness critic

Exact SHA: `cc7ef06b0d08398173d9448ff47d8abb7e375d44`. Static critic; tests **NOT RUN** by this reviewer. Read exact-SHA runtime logs, all six final lenses, both final skeptic reports, R17 matrix, changed source/tests, current contracts and active task. No source edits.

**BR1.1 NOT CLOSED.** Q1 NO, Q2 NO, Q3 NO, Q4 YES, Q5 NO, Q6 NO, Q7 NO. One existing unique Q4 MAJOR, six A–F aliases, zero BLOCKER, zero open substantive MINOR, zero new defect family. S1 and S2 independently confirmed each exact alias. F remains static-only; skeptic execution supplies current corroboration. R17-D-2/F-2 are one repaired normalization MINOR family, supported by owner ordering inspection and fresh controls.

## Concrete remaining failure

At owners.py 1008 a callback returns live dictionaries. Native resource exhaustion during capture (1015–1016) and immediate recovery (1041–1042) leaves only a raw tuple pointing at these dictionaries. Replacing their ledger binding with a pre-spend checkpoint erases the handed spent owner from recovery inputs. `_recover_handing` later reads replacement contents and permits the original admitted action again. Genuine settlement, ordinary checkpoint replacement and native RecursionError reproduce this inside the documented boundary. This is observed-handing loss, distinct from spend/rollback entirely between verifications or absent at-most-once reservations.

Independent S1 native matched depths144/145 (limit150) and S2 depths143/144 (limit180) show raw returned tuple, live mapping calls2 versus detached mapping calls1/refusal. Call depths differ by harness. Empty-pending depths do not establish return and are excluded. A/B/D/E provide further matched controls. Test success that asserts calls2 means reproduction, never safety.

## Minimum decision

Approve or reject **stable execution-owner publication**: each returned account-ID association and relevant handed history remains recoverable across registry checkpoint replacement while reader retention/reconciliation is pending. A concrete small option publishes fresh dict pairs and never edits those published dictionaries; active registry replacement then leaves old owner references reachable. Existing canonical owner records continue to own budget/history. Callback signature need not change, but this is an added lifetime obligation for callbacks currently allowed to return live dictionaries.

For the demonstrated replacement family, Python reference lifetime suffices: **acknowledgement is not mandatory**. C's acknowledgement prescription is broader than its evidence; confirm its defect and reject that mechanism as a prerequisite. Full immutable owner snapshots, historical recovery sources, or acknowledgement for bounded retention are alternatives, not approved requirements. A shallow dict copies bindings only: supported in-place history/payload mutation needs an explicit scope. Do not silently claim deep immutability or exclude a previously supported mutation.

Existing authorization supports separable correctness repairs without another permission request; the JSON repair is such a repair and is complete in the bounded review. No further separable defect was established. Requiring stable publication changes the execution-owner contract; fixing fixtures alone cannot close generic `following()` under its unchanged live-map callback contract.

A generic post-callback wrapper/copy leaves a post-return/pre-copy failure boundary. Further retries or fresh stacks may improve bounded failure schedules; none here demonstrates preservation under repeated interruption. Once the prior binding is erased, later normalization has no input from which to reconstruct it. Permanent pending/refusal also blocks an honest interrupted unchanged callback without corruption; accepting after timeout lacks supporting evidence. This conditional information-loss argument does not prove all possible atomic retention mechanisms impossible. A concrete preserving-contract mechanism remains an alternative if designed and tested; none is currently demonstrated.

## Completeness and limits

Six lenses cover authority/currentness, dispatch/effects, concurrency/seal, identity/serialization, replay/restore and scientific semantics. R16/R17 regressions plus independent multi-history, ordering/conflict, exact-barrier, seal, exception and native matching probes support the local repair. Ledger normalization precedes its JSON/default=str roundtrip; experiment JSON precedes owner reconstruction and writability check. Whole-account validation remains in ordinary readback. No second authority or scientific verdict is introduced by this normalization.

Runtime log totals: A32+8, B32, C final44, D46, E48, S1 32 plus native probe, S2 49 including native probe/E reruns. These overlap and must not be summed as unique coverage. C's initial41 pass/3 harness failures and later collection SyntaxError are preserved; corrected controls pass. F and critic ran no tests. No exhaustive concurrency proof, arbitrary-interruption proof, full independent Q1–Q3/Q5–Q7 audit, publication implementation, full FAST, performance test, remote gate, scientific validation or certification follows.

## Handoff

Review gate still fails because one MAJOR remains. A precisely blocked owner handoff is justified **after** final records, provenance, failure logs and bundle are preserved. Ask for the stable-publication/lifetime decision above; do not request blanket approval for a full acknowledgement subsystem. Future implementation needs failing-first replacement controls, honest interrupted recovery, both account kinds, repeated restore and multiple-reader/publication lifetime checks, followed by independent review. Earlier gate results retain their own exact SHA and do not certify this review. No closure, push, PR, merge, certification, OD-3 or new capability is authorized by this report.
