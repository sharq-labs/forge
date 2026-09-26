"""Descriptive registration of the FEniCSx provider (capability, not applicability).

FEniCSx has been the PDE provider since BIG 8 (``forge_fenicsx.FenicsxProvider``); this descriptor makes it visible to the BIG 11 provider
registry, so a BIG 12 request can bind it explicitly by id and version like every other provider.  The versions and RECORD digests of
dolfinx and of the libraries that decide its numbers (PETSc, basix, UFL, FFCx) are part of the status digest.
"""

from engcore.providers import ProviderCapability, python_package_probe

CAPABILITY = ProviderCapability(
    "fenicsx", "pde", "library", "dolfinx",
    ("scalar_diffusion_steady", "scalar_diffusion_transient", "linear_elasticity_plane_stress", "linear_thermoelasticity_plane_stress"),
    dimensions=(2,), time_modes=("steady", "transient"), output_ranks=("scalar", "vector"), mesh_requirement="Forge triangle mesh (BIG 7)",
    property_forms=("cell fields with material provenance, or sourced constants",), restart=False, checkpoint=False, parallel="serial (MPI.COMM_SELF)",
    dependencies=("fenics-dolfinx", "petsc4py", "fenics-basix", "fenics-ufl", "fenics-ffcx"), license="LGPL-3.0-or-later",
    notes="P1 finite elements assembled through UFL/FFCx (JIT-compiled), solved with PETSc; accepted only if the true relative residual is within tolerance")


def register(registry, **_):
    registry.register(CAPABILITY, python_package_probe(CAPABILITY, "dolfinx", ("fenics-dolfinx", "dolfinx"),
                                                       dependencies=("petsc4py", "fenics-basix", "fenics-ufl", "fenics-ffcx")))
