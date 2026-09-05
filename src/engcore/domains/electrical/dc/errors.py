"""Electrical DC domain errors.

Kept in their own module so the IR mapping layer can raise binding errors
without importing the solver, which imports the mapping layer.
"""

from __future__ import annotations

from ....scientific.errors import ScientificCoreError


class ElectricalDCError(ScientificCoreError):
    """A domain-level failure in Electrical DC analysis."""


class CircuitBindingError(ElectricalDCError):
    """A ScientificProblem and a DCCircuit do not describe the same system.

    Raised before any assembly or numerical work. The two artifacts disagree
    about the physical system, and only the caller can say which one is
    right — silently trusting either would put a result's provenance in
    conflict with the circuit that produced it.
    """
