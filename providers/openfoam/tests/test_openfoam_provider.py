"""Proof D (CFD): real OpenFOAM (icoFoam) lid-driven cavity; fluid viscosity from real CoolProp records.

Integration / numerical execution only.  Successful completion does not make the
laminar incompressible model, the schemes or the resolution valid.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from engcore.materials import FluidIdentity, FluidState
from engcore.providers import ProviderRefusal, ProviderRegistry
from engcore.scenarios import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from forge_openfoam import SEMANTICS, CavityProblem, OpenFOAMProvider, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("openfoam").available
pytestmark = pytest.mark.skipif(not OK, reason="OpenFOAM unavailable")


def water_nu():
    """Kinematic viscosity of water at 20 C, 1 atm from REAL CoolProp property records (provenance bound)."""
    from forge_coolprop import CoolPropProvider, descriptor as cp_descriptor
    from engcore.providers import ProviderRegistry as Reg
    reg = Reg()
    cp_descriptor.register(reg)
    state = FluidState(FluidIdentity("water"), (NamedQuantity("temperature", Quantity(20, "degC")), NamedQuantity("pressure", Quantity(101325, "Pa"))))
    prov = CoolPropProvider(reg)
    mu, rho = prov.resolve(state, "dynamic_viscosity"), prov.resolve(state, "density")
    assert mu.status == rho.status == "known"
    nu = Quantity(mu.value.magnitude / rho.value.magnitude, "m^2/s")
    return nu, (("dynamic_viscosity", mu.digest), ("density", rho.digest), ("provider", f"coolprop {mu.provider_version}"))


def cavity(cells=20, lid=1e-4, end=20000.0, dt=20.0, write_steps=250, steady=Quantity(1e-7, "m/s")):
    nu, prov = water_nu()
    return CavityProblem("cavity-water", Quantity(0.1, "m"), cells, Quantity(lid, "m/s"), nu, prov, Quantity(end, "s"), Quantity(dt, "s"),
                         write_steps=write_steps, steady_tolerance=steady)


def test_proof_d_openfoam_cavity_returns_forge_velocity_and_pressure_fields():
    problem = cavity()
    assert 5 < problem.reynolds < 20
    rec, fields = OpenFOAMProvider(REG).run_cavity(problem)
    assert rec.succeeded, rec.reason
    U = fields["velocity"]
    assert U.mesh.cell_type.value == "quadrilateral" and U.values.shape == (400, 2) and fields["pressure"].values.shape == (400,)
    centres = U.mesh.coordinates[U.mesh.cells].mean(axis=1)
    near = lambda x, y: int(np.argmin(np.linalg.norm(centres - [x, y], axis=1)))  # noqa: E731
    assert U.values[near(0.05, 0.095), 0] > 0 > U.values[near(0.05, 0.03), 0]  # forward flow under the lid, return flow below
    top = U.mesh.coordinates[U.mesh.cells].mean(axis=1)[:, 1] > 0.09
    assert U.values[top, 0].max() < 1e-4 and np.abs(U.values).max() <= 1e-4  # bounded by the lid speed
    assert rec.metrics["steadiness_max_dU_last_interval_m_s"] < 1e-7  # time-marched close to steady (diagnostic only)
    assert "icoFoam" in SEMANTICS["solver"] and rec.artifacts["constant/transportProperties"].count("nu ") == 1
    assert all(f"openfoam_execution:{rec.identity.digest}" in f.provenance for f in fields.values())
    print("OPENFOAM", {k: v for k, v in rec.metrics.items()}, "identity", rec.identity.digest[:16])


def test_laminar_bound_viscosity_provenance_and_stale_outputs_are_enforced():
    nu, prov = water_nu()
    with pytest.raises(ProviderRefusal, match="laminar icoFoam choice is refused"):
        CavityProblem("fast-lid", Quantity(0.1, "m"), 20, Quantity(1.0, "m/s"), nu, prov, Quantity(1, "s"), Quantity(0.001, "s"), write_steps=250)
    with pytest.raises(ProviderRefusal, match="provenance"):
        CavityProblem("anon-nu", Quantity(0.1, "m"), 20, Quantity(1e-4, "m/s"), nu, (), Quantity(20000, "s"), Quantity(20, "s"), write_steps=250)
    # a stale time directory from another run sits in the workspace; this run must not read it
    stale = {"99999/U": b"internalField nonuniform List<vector> 16 ( " + b"(9 9 0) " * 16 + b");"}
    rec, fields = OpenFOAMProvider(REG).run_cavity(cavity(cells=4, end=2000.0, dt=20.0, write_steps=50, steady=None), preexisting=stale)
    assert rec.succeeded and np.abs(fields["velocity"].values).max() <= 1e-4
    assert rec.metrics["end_state"] == "transient"  # no steadiness declared -> none claimed
    # 100 s into a ~1e4 s diffusion time the flow is still developing: a declared steadiness demand fails the run
    young, _ = OpenFOAMProvider(REG).run_cavity(cavity(cells=4, end=100.0, dt=20.0, write_steps=1))
    assert not young.succeeded and "declared steadiness not reached" in young.reason
