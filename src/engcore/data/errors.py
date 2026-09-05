"""Failure taxonomy for the runtime data plane.

Three distinct failures, because a caller acts differently on each and
collapsing them is how a platform starts fabricating science:

* the data is **not there**,
* the data is there but is **not what was asked for**,
* everything else.

None of these is ever *answered* with a fabricated array — invented empty,
zero-filled or silently substituted data. A missing field is a missing field.
(Genuinely empty data that was stored and verifies against its reference is a
legitimate answer, not a fabricated one; the prohibition is on inventing a
value, not on the value happening to be empty.)
"""

from __future__ import annotations


class BulkDataError(Exception):
    """Base class for every runtime data-plane failure."""


class BulkDataUnavailable(BulkDataError):
    """The referenced data could not be found in any consulted store.

    Deliberately distinct from :class:`BulkDataIntegrityError`: "the artifact
    was deleted or was never written here" and "the artifact is present but
    corrupt" call for different responses, and a caller that cannot tell them
    apart cannot decide whether to re-run, restore a backup, or stop.

    **This is not a failure of the scientific result.** The scalar values a
    result carries were computed, validated and attributed; they remain usable
    when bulk data is unavailable. Only the bulk claim is unanswerable.
    """


class BulkDataIntegrityError(BulkDataError):
    """Stored bytes do not match the content identity that was asked for.

    Raised on a digest mismatch or a length mismatch — corruption, truncation,
    or substitution of one artifact for another. Resolution fails loudly; it
    never returns data it cannot vouch for.
    """
