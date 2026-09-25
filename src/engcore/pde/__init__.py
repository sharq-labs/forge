"""Provider-neutral PDE/FEM layer (BIG 8).

Providers live outside the core distribution (the first is ``forge_fenicsx``
under ``providers/fenicsx``); they receive a :class:`PDEProblem` and return a
:class:`PDEExecutionRecord`.  FEniCSx is the first provider, not the ontology.
"""

from .contracts import (
    PLANE_STRESS_ELASTICITY, STEADY_DIFFUSION, TEMPLATES, TRANSIENT_DIFFUSION, BCKind, BoundaryCondition,
    CoefficientBinding, CoefficientSlot, DiscretizationSpec, FacetRole, OperatorTemplate, PDEDiagnostics,
    PDEExecutionRecord, PDEProblem, PDERefusal, PhysicalModel, SourcedQuantity, TransientSpec, facet_cell_counts,
)

__all__ = [
    "PLANE_STRESS_ELASTICITY", "STEADY_DIFFUSION", "TEMPLATES", "TRANSIENT_DIFFUSION", "BCKind", "BoundaryCondition",
    "CoefficientBinding", "CoefficientSlot", "DiscretizationSpec", "FacetRole", "OperatorTemplate", "PDEDiagnostics",
    "PDEExecutionRecord", "PDEProblem", "PDERefusal", "PhysicalModel", "SourcedQuantity", "TransientSpec",
    "facet_cell_counts",
]
