"""Pairing a problem with the physical artifact it describes.

The defect
----------
The universal IR carries quantities, units and model references. It does not
carry a network's topology, a body's geometry or a mixture's composition —
those live in a domain artifact, and the pairing between the two is what a domain
verifies before it computes anything. Every domain does it the same way: the
builder writes a digest of the artifact into ``problem.metadata`` and the
verifier compares it against the artifact it was handed.

Two of them compared like this::

    declared = problem.metadata.get("physics_fingerprint")
    if declared and declared != actual:      # WRONG
        raise ...

``declared`` is falsy when the key is absent, so a problem carrying **no**
fingerprint passed. An integrity check that fails open is not an integrity
check: it refuses the paired records that disagree and waves through the
unpaired one, which is the case it exists for. A problem assembled by hand, a
problem deserialized from a payload that dropped a metadata key, a problem
built by a future builder that forgot — each of those is a problem nobody can
say describes this artifact, and each passed.

The rule
--------
**Absence is a refusal.** A verifier asks "does this problem describe this
artifact", and a problem that says nothing has not answered. There is no third
outcome: a domain that genuinely wants to pair an unfingerprinted problem is
asking to skip the check, and skipping it is a decision that belongs at the
call, in the open, not inside the comparison.

Why here rather than in each domain
------------------------------------
Because five domains wrote this comparison and two of them wrote it wrong, in
the same way, independently. The comparison is four lines and it is the same
four lines every time; what varies is the metadata key, the artifact and the
error type, which are exactly the three things :func:`require_matching_fingerprint`
takes as arguments.

One site is still permissive
-----------------------------
A verifier in a byte-pinned domain file still has the ``if declared and ...``
form and this round could not edit it. Its two callers outside that file call
this function first, so the paths through them are closed; the path through the
pinned file's own solver is not. ``NEEDS.md`` G6.1 names it and records what
closing it costs.

Nothing here knows a domain, a metadata key or an error type: all three arrive
as arguments, which is what lets one rule serve every domain without the core
learning any of them.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

__all__ = ["require_matching_fingerprint"]


def require_matching_fingerprint(
    *,
    problem: Any,
    key: str,
    actual: str,
    error: Callable[[str], Exception],
    subject: str,
) -> None:
    """Refuse a problem that does not declare, or does not match, ``actual``.

    ``problem`` is a :class:`~engcore.scientific.ir.problem.ScientificProblem`
    (or anything with a ``metadata`` mapping and a ``problem_id``). ``key`` is
    the metadata entry the domain's builder writes. ``actual`` is the digest of
    the artifact the caller is pairing it with. ``error`` is the domain's own
    exception type, so a refusal arrives as the error a caller of that domain
    already catches. ``subject`` names the artifact in the message, in the
    domain's own words.

    Three outcomes, and only two of them return:

    * the key is absent or empty — **refused**. The problem has not said what it
      describes, so nothing here can say it describes this.
    * the key is present and differs — refused. Two records, two systems.
    * the key is present and matches — returns.
    """
    metadata: Mapping[str, Any] = getattr(problem, "metadata", {}) or {}
    problem_id = getattr(problem, "problem_id", "<unnamed>")
    declared = metadata.get(key)

    if not declared:
        raise error(
            f"problem {problem_id!r} declares no {key!r}, so nothing states "
            f"which {subject} it describes. It cannot be paired with the "
            f"{subject} whose digest is {_short(actual)}: an absent "
            f"fingerprint is an unanswered question, not an answer that "
            f"happens to match. Rebuild the problem from this {subject}"
        )

    if str(declared) != str(actual):
        raise error(
            f"problem {problem_id!r} declares {key} {_short(str(declared))} "
            f"but was paired with a {subject} whose digest is "
            f"{_short(actual)}; they describe different physical systems"
        )


def _short(fingerprint: str) -> str:
    """Enough of a digest to identify it, without a serialized artifact in a
    traceback."""
    return f"{fingerprint[:12]}…" if fingerprint else "<none>"
