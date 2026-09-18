"""What the claim layer raises.

One root, so a caller can separate "this request is not a well-formed claim or
capability declaration" from a defect in the scientific stack underneath. The
root subclasses :class:`ValueError` because every member is a refusal of a
value a caller supplied, never an internal failure.

Expected scientific outcomes -- NEEDS_INPUT, AMBIGUOUS, an OUTSIDE model, an
INSUFFICIENT_EVIDENCE verdict -- are **records**, not exceptions. An exception
here always means the input itself could not be read as the contract it claims
to be.
"""

from __future__ import annotations


class ClaimLayerError(ValueError):
    """Root of every refusal raised by :mod:`engcore.claims`."""


class ClaimContractError(ClaimLayerError):
    """A scientific claim is malformed, ambiguous in its own fields, or forged."""


class CapabilityDeclarationError(ClaimLayerError):
    """A capability declaration contradicts itself or the records it derives from."""


class CapabilityRegistryError(ClaimLayerError):
    """A registry was built from conflicting declarations or queried with a bad key."""


class CapabilityInputError(ClaimLayerError):
    """A supplied input cannot be written into a capability's case as declared."""


class CapabilityExecutionRefused(ClaimLayerError):
    """A capability's executor refused a case before running any physics."""


__all__ = [
    "CapabilityDeclarationError",
    "CapabilityExecutionRefused",
    "CapabilityInputError",
    "CapabilityRegistryError",
    "ClaimContractError",
    "ClaimLayerError",
]
