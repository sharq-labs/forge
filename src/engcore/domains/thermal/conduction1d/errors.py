"""Errors for the 1D transient conduction domain."""

from __future__ import annotations

from ....scientific.errors import ScientificCoreError


class ThermalConduction1DError(ScientificCoreError):
    """Base error for the 1D transient conduction domain."""


class SlabConfigurationError(ThermalConduction1DError):
    """A slab or discretization was declared with values that cannot be solved.

    Raised at construction rather than at solve time. A negative diffusivity or
    a single-cell mesh is not a hard numerical problem the solver should try
    and fail at — it is a statement that was never well posed, and the earliest
    honest place to say so is where it was written down.
    """


class SlabBindingError(ThermalConduction1DError):
    """A problem id was rebound to a different physical slab."""
