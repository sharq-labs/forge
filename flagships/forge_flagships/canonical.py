"""Canonical problem declarations for the flagships' cross-provider comparisons (Phase 3.5 WS1).

Same-problem admission is mandatory for corroboration
(``engcore.providers.compare.corroborate``).  Each canonical problem here is
derived from the PROBLEM OBJECT THAT ONE PROVIDER WAS HANDED -- the
``CavityProblem`` / ``CavityProblemSU2`` it ran, or the ``PDEProblem`` /
``ThermoelasticPlaneStressProblem`` it solved -- so two sides given different
viscosities, lid speeds, extents, materials, restraints, temperature fields or
equation classes declare different problems and are refused.

What is NOT derived from the object, and why: the equation class and model
assumptions are fixed BY THE ADAPTER TYPE (an OpenFOAM icoFoam cavity case and an
SU2 incompressible laminar case solve one equation class by construction; a
``ThermoelasticPlaneStressProblem`` and the ``linear_thermoelasticity_plane_stress``
template are plane stress by type).  They come from :data:`EQUATION_CLASS`, keyed
by that type, never from a shared constant -- a problem type with no entry is
refused.  That the adapter's input deck faithfully implements its type is the
adapter's claim; the binding names it (``declared_translation_not_verified``).
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from engcore.providers.compare import ExecutionRef
from engcore.providers.problem_identity import CanonicalProblem, ProblemAspect, ProblemBinding
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

#: equation class and assumptions per provider problem TYPE (what the adapter fixes by construction)
EQUATION_CLASS = {
    "CavityProblem": ("steady incompressible Navier-Stokes, two-dimensional",
                      "laminar; Newtonian; constant density and viscosity; isothermal; no body force"),
    "CavityProblemSU2": ("steady incompressible Navier-Stokes, two-dimensional",
                         "laminar; Newtonian; constant density and viscosity; isothermal; no body force"),
    "linear_thermoelasticity_plane_stress": ("linear thermoelasticity, static equilibrium, plane stress",
                                             "small strain; isotropic linear elastic; one-way thermal load"),
    "ThermoelasticPlaneStressProblem": ("linear thermoelasticity, static equilibrium, plane stress",
                                        "small strain; isotropic linear elastic; one-way thermal load"),
}


def _equations(key: str) -> tuple[str, str]:
    if key not in EQUATION_CLASS:
        raise InvalidScientificProblem(f"no declared equation class for provider problem type {key!r}; it is not admitted")
    return EQUATION_CLASS[key]


def array_digest(values: Any) -> str:
    a = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    h = hashlib.sha256(f"{a.shape}|".encode())
    h.update(a.tobytes())
    return h.hexdigest()


def _cavity(kind: str, side: Quantity, lid: Quantity, nu: Quantity, records: Any) -> CanonicalProblem:
    equations, assumptions = _equations(kind)
    A = ProblemAspect
    return CanonicalProblem("lid-driven-cavity", {
        A.GOVERNING_EQUATIONS: equations,
        A.MODEL_ASSUMPTIONS: assumptions,
        A.DOMAIN_GEOMETRY: {"shape": "square cavity", "side": side},
        A.MATERIALS: {"kinematic_viscosity": nu, "property_records": sorted([str(n), str(d)] for n, d in records)},
        A.INITIAL_CONDITIONS: "not applicable: the steady state is the declared solution",
        A.BOUNDARY_CONDITIONS: {"walls": "no slip on the bottom and side walls", "lid": {"tangential_velocity": lid}},
        A.SOURCES_AND_LOADS: "none",
        A.TIME_INTERVAL: "steady state",
        A.QUANTITIES_OF_INTEREST: "velocity field (x, y)",
        A.MODEL_VERSIONS: "forge cavity declaration 2",
    })


def cavity_problem_from_openfoam(prob: Any) -> CanonicalProblem:
    """From the ``forge_openfoam.CavityProblem`` OpenFOAM ran (its own side, lid speed, viscosity and records)."""
    return _cavity(type(prob).__name__, prob.side, prob.lid_velocity, prob.kinematic_viscosity, prob.viscosity_provenance)


def cavity_problem_from_su2(prob: Any) -> CanonicalProblem:
    """From the ``forge_su2.CavityProblemSU2`` SU2 ran (nu = mu / rho of the values it was given)."""
    nu = Quantity(prob.dynamic_viscosity.magnitude_in("Pa*s") / prob.density.magnitude_in("kg/m^3"), "m^2/s")
    return _cavity(type(prob).__name__, prob.side, prob.lid_velocity, nu, prob.property_provenance)


def _extent(mesh: Any) -> dict[str, Quantity]:
    coords = np.asarray(mesh.coordinates, dtype=float)
    lo, hi = coords.min(axis=0), coords.max(axis=0)
    return {"x_extent": Quantity(float(hi[0] - lo[0]), "m"), "y_extent": Quantity(float(hi[1] - lo[1]), "m")}


def _plate(kind: str, *, mesh: Any, thickness: Quantity, materials: dict, restraints: dict, other_boundaries: Any,
           temperature_digest: str, reference_temperature: Quantity) -> CanonicalProblem:
    equations, assumptions = _equations(kind)
    A = ProblemAspect
    return CanonicalProblem("thermoelastic-plate", {
        A.GOVERNING_EQUATIONS: equations,
        A.MODEL_ASSUMPTIONS: assumptions,
        A.DOMAIN_GEOMETRY: {**_extent(mesh), "thickness": thickness},
        A.MATERIALS: materials,
        A.INITIAL_CONDITIONS: "not applicable: static problem",
        A.BOUNDARY_CONDITIONS: {"restraints": restraints, "other_boundaries": other_boundaries},
        A.SOURCES_AND_LOADS: {"temperature_field": temperature_digest, "stress_free_temperature": reference_temperature},
        A.TIME_INTERVAL: "static",
        A.QUANTITIES_OF_INTEREST: "nodal displacement vector; element stress (sxx, syy, sxy)",
        A.MODEL_VERSIONS: "forge thermoelastic plate declaration 2",
    })


def plate_problem_from_pde(problem: Any) -> CanonicalProblem:
    """From the ``PDEProblem`` FEniCSx solved: its template, coefficients, Dirichlet restraints, Neumann data and temperature input."""
    coeff = {c.slot: c for c in problem.coefficients}

    def value(slot):
        constant = coeff[slot].constant
        if constant is None:
            raise InvalidScientificProblem(f"coefficient {slot!r} is a field; the plate declaration states constants only")
        return constant.value, constant.source_record.get("record")

    materials = {}
    for slot in ("youngs_modulus", "poisson_ratio", "thermal_expansion"):
        q, record = value(slot)
        materials[slot] = {"value": q, "record": record}
    restraints, other = {}, {}
    for bc in problem.boundary_conditions:
        if bc.kind.value == "dirichlet":
            if bc.value.value.magnitude != 0.0:
                raise InvalidScientificProblem(f"group {bc.group!r} prescribes a non-zero displacement; not a restraint")
            restraints[bc.group] = sorted(int(c) for c in (bc.components or (0, 1)))
        else:
            traction = bc.vector_value or (bc.value.value,)
            other[bc.group] = "traction free" if all(q.magnitude == 0.0 for q in traction) else [q for q in traction]
    return _plate(problem.operator.template_id, mesh=problem.mesh, thickness=value("thickness")[0], materials=materials,
                  restraints=restraints, other_boundaries=other or "none",
                  temperature_digest=problem.field_inputs["temperature"].digest,
                  reference_temperature=value("reference_temperature")[0])


def plate_problem_from_case(case: Any, boundary_groups: tuple[str, ...]) -> CanonicalProblem:
    """From the ``ThermoelasticPlaneStressProblem`` CalculiX / Code_Aster solved (unrestrained groups are traction free by type)."""
    if len(case.materials) != 1 or len(case.expansions) != 1:
        raise InvalidScientificProblem("the plate declaration states one region")
    m, e = case.materials[0], case.expansions[0]
    materials = {"youngs_modulus": {"value": m.youngs_modulus_record.value.value, "record": m.youngs_modulus_record.digest},
                 "poisson_ratio": {"value": m.poisson_ratio_record.value.value, "record": m.poisson_ratio_record.digest},
                 "thermal_expansion": {"value": e.expansion_record.value.value, "record": e.expansion_record.digest}}
    restraints = {r.group: sorted(int(c) for c in r.components) for r in case.restraints}
    free = {g: "traction free" for g in boundary_groups if g not in restraints}
    return _plate(type(case).__name__, mesh=case.mesh, thickness=case.thickness, materials=materials, restraints=restraints,
                  other_boundaries=free or "none", temperature_digest=case.temperature_digest,
                  reference_temperature=case.reference_temperature)


def bind(record: Any, problem: CanonicalProblem, translator: str) -> ProblemBinding:
    """The adapter's declared translation: this execution record solved this canonical problem."""
    return ProblemBinding(ExecutionRef.of(record).execution_identity, problem.digest, translator)


__all__ = [
    "EQUATION_CLASS", "array_digest", "bind", "cavity_problem_from_openfoam", "cavity_problem_from_su2",
    "plate_problem_from_case", "plate_problem_from_pde",
]
