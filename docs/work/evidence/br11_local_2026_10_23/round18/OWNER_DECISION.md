# Owner decision needed: stable published account bindings

PROPOSED, NOT APPROVED. Supersedes the broader acknowledgement wording in round16/OWNER_HANDOFF_DECISION.md.
Exact reviewed source: cc7ef06b0d08398173d9448ff47d8abb7e375d44. Final skeptical/critic status is in this directory.

Approve changing the BudgetReader.following account-publication obligation so each successful accounts() return
publishes stable recoverable account bindings and history: later owner checkpoint replacement must not overwrite
that already-returned observation before the reader can retain/compare it. Owners may publish detached native
mapping snapshots using existing canonical account objects, whose retained histories remain available. Specify
legacy callbacks that reuse mutable live mappings as unsupported for this guarantee and migrate/reject them
explicitly; do not silently treat live mutable callbacks as safe. Stability cannot be inferred from dict type alone; require a defined publication obligation and its implementation evidence.

Matched exact-source runtime controls show owner-created fresh dictionaries prevent the demonstrated mapping-entry
replacement failure at the same interruption points/native stack depths. No new callback signature, budget ledger,
scientific evidence record, reservation or durable at-most-once execution is required by this evidence. A full
publication/acknowledgement protocol is an optional design, NOT a demonstrated prerequisite.

Why this decision is needed: the current callback contract permits live mutable dictionaries and replacement.
After initial capture and immediate recovery both fail, it can retain only the live mapping. Ordinary replacement
of its spent ledger by an older checkpoint then erases the only available version before the next recovery.
An unchanged honest handing and a spent-then-restored handing may leave identical reader inputs. Current evidence
shows later recovery accepts and dispatches twice. Forgetting the unresolved observation would improve assurance
from missing evidence; permanently refusing every honest interrupted reader violates the user's recovery rule.
Reader-side copying/retrying narrows failure windows but still starts after the callback returned the live version.
Fresh-stack work fixes a specific recursion trigger, not arbitrary repeated allocation/interruption before capture.

An authoritative recoverable owner history or a concrete atomic retention mechanism could also satisfy the requirement; those alternatives need a defined owner contract and evidence. A weaker observation boundary is another option: only successfully captured handings count, accepting
pre-capture loss as an exclusion. That conflicts with the requested all-handed-spend guarantee and is NOT selected.

This proposal is a concrete architectural contract decision, not a claim of formal impossibility for every possible
implementation. No owner adapter, new protocol, or narrowing of semantics has been applied. BR1.1 remains NOT CLOSED.
