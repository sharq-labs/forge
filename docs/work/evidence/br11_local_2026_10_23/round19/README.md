# Round19 immutable review and corrective disposition

Reviewed SHA: `0b605b43416d575b60f87ca57eea7a1d646489d5`. Six independent lenses A–F, focused skeptic S2, and completeness critic. E is explicitly a supplied-source static review; its summary must not be mistaken for local test execution. Full-path A/C/D/F reviews supply the broader authority/admission coverage missing from E.

Verdict at reviewed SHA: **CHANGES REQUIRED / NOT CLOSED**. Two unique substantive families, conservatively tracked as MAJOR; no BLOCKER, no additional open substantive MINOR. E calls false refusal MEDIUM; campaign conservatively counts it MAJOR due positive-progress gate regression.

1. S2-F1 / E-F1 / FAST R6: a newly installed raw unread barrier can be identity-incomparable to an older snapshot yet canonically extend its history. Permanent divergence was inferred without canonical conflict. RED 1failed/1passed; fix keeps it unresolved until normalization, retaining true conflict sealing.
2. B-F1 / B-LATE-PUBLICATION: late first publication of a spent replacement can miss a pin already past readback. B/S2 reproduce two executions; E disputes classification under acquisition-snapshot semantics. This is not loss of a previously published spend. Resolve semantics explicitly under approved pending-reader lifetime contract: reconcile new generations through final source check; a publication after that check orders later. Bounded retries refuse transiently under churn. Preserve the pin's original binding, rather than switching its account view. RED 1failed/1passed; prepublished matched control refuses.

Ordinary overlapping dispatch without restore reproduces even when spend is retained: separate executor-reservation limitation, not a third lost-history defect. No at-most-once claim.

Q1–Q7 at reviewed SHA: NO, NO, NO, YES, NO, NO, NO for closure accounting (Q4 open budget-authority/lifetime challenge). No scientific applicability, units, model verdict, or admission bypass introduced in reviewed bounds. Reviewer-local NO answers remain scoped; they do not erase the two substantive findings.

Completeness requests incorporated into corrective tests: constructor and pin final checks, ledger and experiment parity, identical and forward replacement, interruption during retry, closure/retirement and sustained churn. Additional tests are finite software traces, not exhaustive proof. Original six review reports and skeptic/critic artifacts retained unchanged; implementation_result.json is separate from review findings.

Corrective source hash: `efad8b564d00331877308151648554970222652a3249220c7fe934d4118eb7a3`. Focused combined run118passed. Full ladder and fresh independent Round20 must evaluate the corrected commit before closure.
