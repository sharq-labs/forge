"""Errors raised when assembling a problem, or reading a credibility report.

Two families, and the difference between them is the difference between the
two boundaries this layer owns.

**Reading a report: one type.** The V&V layer has exactly one failure mode
worth distinguishing from the rest of the platform — "this report does not say
what it claims to say" — and splitting that into a taxonomy would suggest a
caller could usefully branch on which way a report was malformed. It cannot:
every one of them means the report must not be read as evidence.

**Building a problem: one type per failure class.** The opposite argument
applies, for the opposite reason. The caller here is upstream of the run and is
frequently an agent assembling a payload it has never seen validated. Every
distinction below maps to a *different repair*: add a unit, change a unit, fix
a spelling, supply a missing field, fix the shape. A caller can branch on these
usefully, which is the test the report side fails and this side passes. Each
carries the field, what arrived and what was expected, so that the repair needs
no second attempt to discover.

Subclasses ``ScientificCoreError`` so a caller catching the platform's root
error still catches these, which is the same choice ``ElectricalDCError`` makes
in the DC domain.
"""

from __future__ import annotations

from ..scientific.errors import ScientificCoreError

__all__ = [
    "CredibilityEvidenceError",
    "EvidencePackageError",
    "MalformedPayloadError",
    "MissingFieldError",
    "MissingUnitError",
    "ProblemPayloadError",
    "UnknownFieldError",
    "WrongDimensionError",
]


class CredibilityEvidenceError(ScientificCoreError):
    """The report is malformed, or claims a verdict its contents do not support."""


class ProblemPayloadError(ScientificCoreError):
    """A payload could not be turned into a problem. Base of the five below.

    Exported so a caller who only wants "did the build fail" can catch one
    thing, and so the five subclasses stay a refinement rather than a
    requirement. Never raised directly: a failure this layer cannot classify
    is a gap in the classification, not a sixth case.
    """


class MalformedPayloadError(ProblemPayloadError):
    """The shape is wrong: a mapping was expected and something else arrived.

    Structural, not scientific — it fires before any field is looked at.
    """


class MissingFieldError(ProblemPayloadError):
    """A required field is absent.

    Only ever raised for a field the model record marks ``required=True``. An
    *optional* field that is absent is not an error and must never become one:
    the applicability conditions are built so that a missing declaration yields
    UNKNOWN rather than IN_DOMAIN, and inventing a default here would convert
    an honest gap into a false verdict.
    """


class UnknownFieldError(ProblemPayloadError):
    """A field is not one this boundary accepts.

    Refused rather than ignored, and the reason is the whole point of the
    boundary. Dropping ``conductivty`` silently would present downstream as a
    body whose conductivity was never declared — an UNKNOWN Biot number that
    the caller did not ask for, cannot see, and would read as a property of
    their case rather than of their spelling.
    """


class MissingUnitError(ProblemPayloadError):
    """A value that must be a physical quantity is not one.

    A bare number, a null, or a string the units backend cannot parse. No
    implicit SI and no reasonable default: a caller who wrote ``10`` has not
    stated a physical quantity, and choosing the unit for them is exactly the
    substitution this platform exists to refuse.
    """


class WrongDimensionError(ProblemPayloadError):
    """A quantity parsed, and its dimension is not the one the field needs.

    Carries **both** dimensions, because "expected a temperature" is not
    actionable when the caller believes they supplied one.
    """


#: Deprecated alias, kept for one release alongside
#: :class:`~engcore.mcp.evidence.EvidencePackage`. New code should use
#: :class:`CredibilityEvidenceError`.
EvidencePackageError = CredibilityEvidenceError
