"""Canonical problem declarations for the flagships' cross-provider comparisons (Phase 3.5 WS1).

Same-problem admission is mandatory for corroboration
(``engcore.providers.compare.corroborate``).  Each provider node states the
canonical problem FROM ITS OWN INPUTS (the values it was actually given), and
the comparison node derives SAME_PROBLEM / DIFFERENT_PROBLEM / UNDETERMINED
from the two declarations -- so two sides fed different viscosities, materials
or temperature fields are refused, never corroborated.

What this does NOT establish: that each provider input is a faithful
translation of the declaration.  The binding names the translating adapter; its
fidelity is the adapter's claim (``ProblemBinding`` is classified
``declared_translation_not_verified``).
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from engcore.providers.compare import ExecutionRef
from engcore.providers.problem_identity import CanonicalProblem, ProblemAspect, ProblemBinding
from engcore.scientific.units.quantity import Quantity


def array_digest(values: Any) -> str:
    a = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    h = hashlib.sha256(f"{a.shape}|".encode())
    h.update(a.tobytes())
    return h.hexdigest()


def cavity_problem(*, side_m: float, lid_velocity_m_s: float, kinematic_viscosity_m2_s: float,
                   density_record: str, viscosity_record: str) -> CanonicalProblem:
    """The lid-driven cavity as one provider was asked to solve it (steady, laminar, 2D, isothermal)."""
    A = ProblemAspect
    return CanonicalProblem("lid-driven-cavity", {
        A.GOVERNING_EQUATIONS: "steady incompressible Navier-Stokes, two-dimensional",
        A.MODEL_ASSUMPTIONS: "laminar; Newtonian; constant density and viscosity; isothermal; no body force",
        A.DOMAIN_GEOMETRY: {"shape": "square cavity", "side": Quantity(side_m, "m")},
        A.MATERIALS: {"kinematic_viscosity": Quantity(kinematic_viscosity_m2_s, "m^2/s"),
                      "density_record": density_record, "dynamic_viscosity_record": viscosity_record},
        A.INITIAL_CONDITIONS: "not applicable: the steady state is the declared solution",
        A.BOUNDARY_CONDITIONS: {"walls": "no slip on the bottom and side walls",
                                "lid": {"tangential_velocity": Quantity(lid_velocity_m_s, "m/s")}},
        A.SOURCES_AND_LOADS: "none",
        A.TIME_INTERVAL: "steady state",
        A.QUANTITIES_OF_INTEREST: "velocity field (x, y)",
        A.MODEL_VERSIONS: "forge cavity declaration 1",
    })


def plate_problem(*, declared: dict, t_ref_k: float, temperature_values: Any, material_records: tuple[str, ...]) -> CanonicalProblem:
    """The thermoelastic plate as one structural provider was asked to solve it (plane stress, one-way thermal load)."""
    A = ProblemAspect
    return CanonicalProblem("thermoelastic-plate", {
        A.GOVERNING_EQUATIONS: "linear thermoelasticity, static equilibrium, plane stress",
        A.MODEL_ASSUMPTIONS: "small strain; isotropic linear elastic; one-way thermal coupling (temperature given)",
        A.DOMAIN_GEOMETRY: {"length_m": declared["length_m"], "half_width_m": declared["half_width_m"]},
        A.MATERIALS: {"records": list(material_records)},
        A.INITIAL_CONDITIONS: "not applicable: static problem",
        A.BOUNDARY_CONDITIONS: {"support": declared["support"]},
        A.SOURCES_AND_LOADS: {"temperature_field": array_digest(temperature_values),
                              "stress_free_temperature": Quantity(t_ref_k, "K")},
        A.TIME_INTERVAL: "static",
        A.QUANTITIES_OF_INTEREST: "nodal displacement vector; element stress (sxx, syy, sxy)",
        A.MODEL_VERSIONS: "forge thermoelastic plate declaration 1",
    })


def bind(record: Any, problem: CanonicalProblem, translator: str) -> ProblemBinding:
    """The adapter's declared translation: this execution record solved this canonical problem."""
    return ProblemBinding(ExecutionRef.of(record).execution_identity, problem.digest, translator)


__all__ = ["array_digest", "bind", "cavity_problem", "plate_problem"]
