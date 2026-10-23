# Independent draft review (not Round 19)

Static review only; no tests executed or claimed. Reviewed uncommitted owners.py draft with AccountPublication and BudgetReader integration, based on a57f1fdd. Source SHA256 at report write: 5e321c27871dd789cbdcad15f8ef12fc64a5b223b26e9d2ccd2efc815b073e00. Root may edit concurrently; locations refer to the inspected draft.

## DRAFT-1: Writable returned publication token can erase retained authority

Affected: `_PublishedAccounts` lines 382-386; AccountPublication.publish lines 414-423; `_retain_publication` lines 1027-1029. Proposed severity MAJOR if public result fields are considered supported caller operations; otherwise make the private boundary explicit and enforce it.

The source retains the same token it returns, but token.source and token.bindings are ordinary writable slots. A caller can replace an older returned token's bindings with the bindings of a restored account publication. The source no longer has the original spent binding even though it still lists the older token. This defeats the stated stable-publication invariant through a public returned object's fields. Returning a private-named class does not make its public attributes immutable.

Suggested deterministic challenge: publish ledger L; retain token T; spend L; publish restored ledger R as token U; assign T.bindings = U.bindings; then pin the existing reader. The old spent object is absent from source history. Test expectation should either reject assignment or still retain L independently of token mutation. This trace is a static counterexample, NOT executed here.

Recommended correction: immutable token with read-only fields, immutable native entry tuples, and source-owned immutable generation state that a returned handle cannot rewrite. Ordinary account mutation remains through canonical append-only APIs. Deliberate object.__setattr__ / private storage mutation can remain the established private execution-side boundary; plain field assignment should not silently rewrite publication.

## DRAFT-2: Nominal source subclasses can replace the lifetime implementation

Affected: BudgetReader.following lines 549-554, `_retain_publication` 1025-1027, and source method dispatch. Proposed severity MAJOR subject to threat-boundary disposition.

The reader checks exact token type but never exact AccountPublication source type. A subclass can inherit publish (which creates the exact token) while overriding _history to return just the current token. Then previous generations are never reconciled and restoration may regain authority. This is structurally like trusting a caller implementation to assert that it retained sufficient history.

Recommended correction: exact AccountPublication type requirement, consistent with exact canonical owner types, and use canonical implementation methods where appropriate. Explicitly refuse a subclass at reader construction, rather than presenting it as dispatch-capable. A source instance's private method/storage monkeypatching remains a different trust-boundary question.

## DRAFT-3: Unreturned lease can prevent retirement permanently

Affected: `_acquire` lines 429-434 and pinned lines 1107-1109, cleanup 1171-1172. Severity MINOR availability/resource lifecycle, not duplicate-execution evidence.

An interrupt after `_leases.add(lease)` but before return leaves the caller's lease variable None. Cleanup cannot remove the token; no future normal path can recover its identity. retire then refuses forever. The retire docstring says callers may retry after the pin finishes, but retry does not cure this case. An interrupt in release before discard also leaves an orphan. Retaining history is safe; the concern is that the promised explicit retirement cannot complete even after actual quiescence.

Possible correction: caller allocates lease identity BEFORE attempting registration and encloses registration in the caller cleanup scope; failed release must leave an explicitly recoverable retirement obligation. Do not simply clear leases on timeout. A terminal source may use an explicit reader lifecycle registry to prove no future acceptance, but that proof must be concrete.

## Checked paths and limits

All generations being re-read on every pin correctly avoids naive cursor retirement after an early read followed by later spend. Source closure is checked again after comparison, and snapshot _read checks source open. Terminal close prevents new acquisitions; retire checks closure and leases. Constructor following has no lease, though source closure makes subsequent snapshot reads unavailable; test close during constructor readback to substantiate the quiescence claim rather than assuming it.

There remains an ordinary concurrency linearization question: source close or publish can occur immediately after the final source check. Document that acceptance is ordered at that check, and test dispatch re-verification against closed/new publications. Do not claim literal impossibility of any method returning after close without defining this ordering.

Migration rejects raw callback mappings at initial following construction. Update annotations/docs: following still advertises a tuple-of-mappings callback in its signature despite requiring a publication token. This is documentation/API typing, not another scientific finding.

No formal verdict or test result is asserted. DRAFT-1/2 deserve executable challenge or explicit defended scope disposition before the final independent review.
