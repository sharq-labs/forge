"""SRIA errors.

Deliberately *not* subclasses of ``ScientificCoreError``. SRIA sits above the
Scientific Core, and a caller writing ``except ScientificCoreError`` to handle
a unit problem must not silently swallow a trust-boundary violation.
"""

from __future__ import annotations


class SRIAError(Exception):
    """Base for every SRIA contract violation."""


class CharterError(SRIAError):
    """Malformed campaign charter or illegal amendment."""


class EvidenceError(SRIAError):
    """Malformed evidence envelope."""


class LifecycleViolation(EvidenceError):
    """An illegal evidence lifecycle transition."""


class AdmissionError(EvidenceError):
    """Admission declaration missing or inconsistent."""


class AdmissionAuthorityError(AdmissionError):
    """An admission declaration could not be attributed to a trusted issuer.

    Distinct from a scientific verdict: failing to establish *who admitted
    this* says nothing about whether the claim is true. Evidence keeps its
    scientific standing when this is raised.
    """


class BeliefWriteViolation(SRIAError):
    """Something tried to write scientific belief outside the Gateway.

    This is the central architectural invariant of SRIA. It is an error type
    rather than a comment because the boundary must be testable.
    """


class UncertaintyContractError(SRIAError):
    """Uncertainty declaration missing a required channel or discrepancy."""


class OutcomeContractError(SRIAError):
    """Structurally invalid run outcome."""


class ActionContractError(SRIAError):
    """Malformed research action."""


class FeasibilityViolation(ActionContractError):
    """A hard feasibility/safety constraint rejected an action."""


class SignatureError(SRIAError):
    """Malformed structure or environment signature."""


class CalibrationKeyContamination(SignatureError):
    """Scientific domain semantics leaked into a computational calibration key.

    Computational calibration is keyed by *structure and environment*. Keying
    it by scientific domain name would make cost/failure learning
    un-transferable between domains that share a computational shape.
    """


class DomainPackContractError(SRIAError):
    """A domain pack violates the ownership boundary."""


class ReservedNotImplemented(SRIAError):
    """A reserved-but-unimplemented capability was invoked.

    Reserved enum members exist so that storage formats and interfaces are
    stable before the capability is built. Reaching one at runtime is a
    programming error, not a scientific one.
    """


class TrustBoundaryViolation(SRIAError):
    """A forbidden dependency was found in the scientific import graph."""
