"""Proof D (second CFD solver) + Proof E (cross-provider CFD comparison): SU2 vs OpenFOAM on one declared cavity.

Both runs take density/viscosity from the SAME real CoolProp records.  The
comparison maps SU2 nodal velocity onto OpenFOAM cell centres with a declared
4-corner average.  Agreement is corroboration between two CFD codes, not
validation of the laminar cavity model.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.materials import FluidIdentity, FluidState
from engcore.providers import ComparisonDeclaration, OutputSelection, ProviderRefusal, ProviderRegistry, compare_providers
from engcore.scenarios import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from forge_su2 import CavityProblemSU2, SU2Provider, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("su2").available
pytestmark = pytest.mark.skipif(not OK, reason="SU2 unavailable")
N, L, LID = 40, 0.1, 1e-4


def water():
    from forge_coolprop import CoolPropProvider, descriptor as cpd
    reg = ProviderRegistry()
    cpd.register(reg)
    s = FluidState(FluidIdentity("water"), (NamedQuantity("temperature", Quantity(20, "degC")), NamedQuantity("pressure", Quantity(101325, "Pa"))))
    prov = CoolPropProvider(reg)
    mu, rho = prov.resolve(s, "dynamic_viscosity"), prov.resolve(s, "density")
    return mu, rho


def su2_problem(cells=N):
    mu, rho = water()
    return CavityProblemSU2("cavity-water", Quantity(L, "m"), cells, Quantity(LID, "m/s"), rho.value, mu.value,
                            (("dynamic_viscosity", mu.digest), ("density", rho.digest)), iterations=6000, residual_log10_target=-10.0)


def test_proof_d_su2_cavity_converges_to_its_declared_residual():
    rec = SU2Provider(REG).run_cavity(su2_problem(20))
    assert rec.succeeded, rec.reason
    assert rec.metrics["final_log10_rms_p"] <= -10.0 and np.abs(np.asarray(rec.arrays["velocity"][1])).max() <= LID * (1 + 1e-9)
    cfg = rec.artifacts["cavity.cfg"]
    assert "SOLVER= INC_NAVIER_STOKES" in cfg and "% Forge execution " in cfg and "MARKER_MOVING= ( lid )" in cfg
    with pytest.raises(ProviderRefusal, match="laminar choice is refused"):
        mu, rho = water()
        CavityProblemSU2("fast", Quantity(L, "m"), 20, Quantity(1.0, "m/s"), rho.value, mu.value, (("x", "y"),))


def _paired(n, dt):
    from forge_openfoam import CavityProblem, OpenFOAMProvider, descriptor as ofd
    reg = ProviderRegistry()
    ofd.register(reg)
    if not reg.status("openfoam").available:
        pytest.skip("OpenFOAM unavailable")
    mu, rho = water()
    nu = Quantity(mu.value.magnitude / rho.value.magnitude, "m^2/s")
    of_rec, of_fields = OpenFOAMProvider(reg).run_cavity(
        CavityProblem("cavity-water", Quantity(L, "m"), n, Quantity(LID, "m/s"), nu, (("dynamic_viscosity", mu.digest), ("density", rho.digest)),
                      Quantity(30000, "s"), Quantity(dt, "s"), write_steps=500, steady_tolerance=Quantity(1e-7, "m/s")))
    su2 = SU2Provider(REG).run_cavity(su2_problem(n))
    assert of_rec.succeeded and su2.succeeded, (of_rec.reason, su2.reason)
    return of_rec, of_fields, su2, mu


def test_proof_e_openfoam_vs_su2_whole_field_disagrees_near_the_lid_recorded_negative_result():
    # Declared BEFORE looking: whole field, 3 % of lid speed.  Observed: FAILS (max ~25 % in lid-adjacent cells).
    of_rec, of_fields, su2, mu = _paired(N, 10.0)
    mesh = of_fields["velocity"].mesh
    mapped = np.asarray(su2.arrays["velocity"][1])[mesh.cells].mean(axis=1)  # declared 4-corner average
    decl = ComparisonDeclaration("cell-centre velocity (x, y) of the 2-D lid-driven cavity, whole field", "m/s",
                                 "SU2 nodal velocity -> OpenFOAM cell centres by the mean of the 4 cell corners",
                                 Quantity(0.03 * LID, "m/s"), 0.0, f"Re~10, {N}x{N}, water 20 C from CoolProp {mu.provider_version}")
    corners = tuple(tuple((int(n), 0.25) for n in cell) for cell in mesh.cells)
    cmp = compare_providers(decl, of_rec, "velocity", su2, "velocity", b_select=OutputSelection(weights=corners))
    assert cmp.max_absolute == float(np.abs(np.asarray(of_fields["velocity"].values) - mapped).max())
    print("PROOF_E_CFD_WHOLE", cmp.to_dict())
    assert not cmp.within_tolerance and cmp.max_absolute > 0.1 * LID  # disagreement is reported, never hidden


def test_proof_e_openfoam_vs_su2_lower_half_corroborate_and_converge_with_refinement():
    # Region y < L/2 (away from the lid-corner singularity) chosen AFTER the whole-field result: labelled post hoc.
    diffs = {}
    for n in (20, 40):
        of_rec, of_fields, su2, mu = _paired(n, 10.0)
        mesh = of_fields["velocity"].mesh
        lower = mesh.coordinates[mesh.cells].mean(axis=1)[:, 1] < L / 2
        mapped = np.asarray(su2.arrays["velocity"][1])[mesh.cells].mean(axis=1)
        decl = ComparisonDeclaration("cell-centre velocity (x, y), lower half y < L/2 (region chosen post hoc)", "m/s",
                                     "SU2 nodal velocity -> OpenFOAM cell centres by the mean of the 4 cell corners",
                                     Quantity(0.03 * LID, "m/s"), 0.0, f"Re~10, {n}x{n}, water 20 C from CoolProp {mu.provider_version}",
                                     post_hoc=True)
        rows = tuple(int(i) for i in np.flatnonzero(lower))
        corners = tuple(tuple((int(k), 0.25) for k in cell) for cell in mesh.cells)
        cmp = compare_providers(decl, of_rec, "velocity", su2, "velocity", a_select=OutputSelection(rows=rows),
                                b_select=OutputSelection(rows=rows, weights=corners))
        assert cmp.classification == "post_hoc_solver_corroboration_not_validation"
        print("PROOF_E_CFD_LOWER", n, cmp.to_dict()["max_absolute"], cmp.within_tolerance)
        diffs[n] = cmp.max_absolute
        assert cmp.within_tolerance
    assert diffs[40] < 0.7 * diffs[20]  # the two codes approach each other under refinement (not a proof of either)
