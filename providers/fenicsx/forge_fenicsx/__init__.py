"""forge-fenicsx: the FEniCSx (dolfinx + UFL + PETSc) provider for Forge PDE templates.

Packaged separately from ``crafty`` (see ``providers/fenicsx/pyproject.toml``):
FEniCSx is distributed through conda-forge / system packages, not as a pip
dependency of the core, and it is the first PDE provider -- not Forge's PDE
ontology.  ``engcore.pde`` holds the provider-neutral contracts.

Provider boundary: dolfinx/UFL/PETSc objects never leave this module.  The
provider receives a :class:`PDEProblem`, builds the form for the Forge
operator template (it does NOT accept user forms), solves with PETSc KSP, and
returns BIG 7 :class:`SpatialField` values inside a :class:`PDEExecutionRecord`.

Every solve is accepted only if (a) PETSc reports a positive converged reason
AND (b) the independently computed true relative residual ||A x - b|| / ||b||
is within ``residual_rtol``.  Otherwise the record is FAILED and exposes no
field.  All numbering between Forge and dolfinx is mapped explicitly
(``original_cell_index``, ``input_global_indices``, cell dofmaps).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from engcore.numerical.core import ProviderUnavailable
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from engcore.scientific.units.quantity import normalize_unit
from engcore.spatial import Rank
from engcore.pde.contracts import (
    BCKind, PDEDiagnostics, PDEExecutionRecord, PDEProblem, PDERefusal, computed_field,
)


def fenicsx_available() -> tuple[bool, str]:
    try:
        import dolfinx  # noqa: F401
        import dolfinx.fem.petsc  # noqa: F401
        from petsc4py import PETSc
        return True, f"dolfinx {dolfinx.__version__}, PETSc {'.'.join(map(str, PETSc.Sys.getVersion()))}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


class FenicsxProvider:
    def __init__(self) -> None:
        ok, detail = fenicsx_available()
        self._ok, self._detail = ok, detail
        if ok:
            import basix
            import dolfinx
            import petsc4py
            import ufl
            self.identity = SolverIdentity("fenicsx.dolfinx", dolfinx.__version__,
                                           backend=f"PETSc {petsc4py.__version__}; basix {basix.__version__}; ufl {ufl.__version__}")
        else:
            self.identity = SolverIdentity("fenicsx.dolfinx", "unavailable")

    def available(self) -> bool:
        return self._ok

    # ---- mesh translation -----------------------------------------------------

    def _translate(self, problem: PDEProblem):
        import basix.ufl
        import dolfinx
        from mpi4py import MPI

        m = problem.mesh
        el = basix.ufl.element("Lagrange", "triangle", 1, shape=(2,))
        dm = dolfinx.mesh.create_mesh(MPI.COMM_SELF, np.asarray(m.cells, dtype=np.int64), el, np.array(m.coordinates, dtype=np.float64))
        tdim = 2
        dm.topology.create_connectivity(tdim, 0)
        dm.topology.create_connectivity(tdim - 1, tdim)
        forge_cell = np.asarray(dm.topology.original_cell_index, dtype=np.int64)
        geom_to_forge = np.asarray(dm.geometry.input_global_indices, dtype=np.int64)
        c2v = dm.topology.connectivity(tdim, 0)
        forge_to_vertex = np.full(m.node_count, -1, dtype=np.int64)
        gdof = dm.geometry.dofmap
        for c in range(len(forge_cell)):
            for g, v in zip(gdof[c], c2v.links(c)):
                forge_to_vertex[geom_to_forge[g]] = v
        if np.any(forge_to_vertex < 0):
            raise PDERefusal("dolfinx dropped mesh nodes; refusing an incomplete translation")
        # facet tags for every group that has a declared role
        entities, values = [], []
        for name in dict(problem.facet_roles):
            region = m.region(name)
            for i in m.facet_indices(region):
                entities.append(forge_to_vertex[m.facets[i]])
                values.append(region.tag)
        if entities:
            ent = np.asarray(entities, dtype=np.int32)
            tags = dolfinx.mesh.meshtags_from_entities(dm, tdim - 1, dolfinx.graph.adjacencylist(ent), np.asarray(values, dtype=np.int32))
        else:
            tags = None
        return dm, forge_cell, geom_to_forge, tags

    def _dg0(self, dm, forge_cell, values):
        import dolfinx
        Q = dolfinx.fem.functionspace(dm, ("DG", 0))
        f = dolfinx.fem.Function(Q)
        f.x.array[:] = np.asarray(values, dtype=np.float64)[forge_cell]
        return f

    def _node_values(self, problem, dm, V, geom_to_forge, uh, comps):
        m = problem.mesh
        out = np.full((m.node_count, comps), np.nan)
        gdof = dm.geometry.dofmap
        arr = uh.x.array.reshape(-1, comps)
        for c in range(gdof.shape[0]):
            cell_dofs = V.dofmap.cell_dofs(c)
            for k in range(3):  # vertex dofs come first for Lagrange on triangles
                out[geom_to_forge[gdof[c][k]]] = arr[cell_dofs[k]]
        if np.any(np.isnan(out)):
            raise PDERefusal("could not map every mesh node to a solution dof")
        return out[:, 0] if comps == 1 else out

    # ---- solve ----------------------------------------------------------------

    def _linear_solve(self, a, L, bcs, problem, prefix):
        import dolfinx.fem.petsc
        s = problem.solver
        opts = {"ksp_type": s.options["ksp_type"], "pc_type": s.options["pc_type"],
                "ksp_rtol": float(s.tolerances["rtol"]), "ksp_atol": 0.0, "ksp_max_it": int(s.options["max_iterations"])}
        if s.options.get("pc_factor_mat_solver_type"):
            opts["pc_factor_mat_solver_type"] = s.options["pc_factor_mat_solver_type"]
        lp = dolfinx.fem.petsc.LinearProblem(a, L, bcs=bcs, petsc_options=opts, petsc_options_prefix=prefix)
        uh = lp.solve()
        if isinstance(uh, tuple):
            uh = uh[0]
        ksp = lp.solver
        reason, its = int(ksp.getConvergedReason()), int(ksp.getIterationNumber())
        r = lp.b.duplicate()
        lp.A.mult(uh.x.petsc_vec, r)
        r.axpy(-1.0, lp.b)
        bnorm = lp.b.norm()
        rel = float(r.norm() / bnorm) if bnorm > 0 else float(r.norm())
        return uh, reason, its, rel

    def execute(self, problem: PDEProblem) -> PDEExecutionRecord:
        if not isinstance(problem, PDEProblem):
            raise PDERefusal("execute requires a PDEProblem")
        if not self._ok:
            raise ProviderUnavailable(f"FEniCSx is not available here: {self._detail}")
        import dolfinx
        import ufl
        from petsc4py import PETSc

        op = problem.operator
        dm, forge_cell, geom_to_forge, tags = self._translate(problem)
        deg = problem.discretization.degree
        comps = 2 if op.rank is Rank.VECTOR else 1
        V = dolfinx.fem.functionspace(dm, ("Lagrange", deg, (2,)) if comps == 2 else ("Lagrange", deg))
        u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
        qd = {} if problem.discretization.quadrature_degree is None else {"quadrature_degree": problem.discretization.quadrature_degree}
        dx = ufl.Measure("dx", domain=dm, metadata=qd)
        ds = ufl.Measure("ds", domain=dm, subdomain_data=tags, metadata=qd)
        coeff = {c.slot: self._dg0(dm, forge_cell, c.normalized_cell_values(problem.mesh, op.slot(c.slot).reference_unit))
                 for c in problem.coefficients}
        unknown_unit = normalize_unit(op.unknown_unit)
        field_factor = 1.0  # solve in the template's unknown unit; convert back at the end
        warnings: list[str] = []

        def bc_forms(values_override=None):
            bcs, a_extra, L_extra = [], None, None
            add = lambda acc, term: term if acc is None else acc + term  # noqa: E731
            for bc in problem.boundary_conditions:
                tag = problem.mesh.region(bc.group).tag
                facets = tags.find(tag)
                val = values_override.get(bc.group, bc.value) if values_override else bc.value
                if bc.kind is BCKind.DIRICHLET:
                    if comps == 1:
                        dofs = dolfinx.fem.locate_dofs_topological(V, 1, facets)
                        bcs.append(dolfinx.fem.dirichletbc(PETSc.ScalarType(val.value.to(unknown_unit).magnitude), dofs, V))
                    else:
                        fixed = bc.components if bc.components is not None else (0, 1)
                        target = val.value.to(unknown_unit).magnitude
                        for i in fixed:
                            Vi = V.sub(i)
                            dofs = dolfinx.fem.locate_dofs_topological(Vi, 1, facets)
                            bcs.append(dolfinx.fem.dirichletbc(PETSc.ScalarType(target), dofs, Vi))
                elif bc.kind is BCKind.NEUMANN:
                    if comps == 1:
                        g = dolfinx.fem.Constant(dm, PETSc.ScalarType(val.value.to(normalize_unit(op.neumann_unit)).magnitude))
                        L_extra = add(L_extra, g * v * ds(tag))
                    else:
                        vec = bc.vector_value or ()
                        if len(vec) != 2:
                            raise PDERefusal("a vector Neumann condition needs two traction components in the mesh frame")
                        g = dolfinx.fem.Constant(dm, np.array([q.to(normalize_unit(op.neumann_unit)).magnitude for q in vec], dtype=PETSc.ScalarType))
                        L_extra = add(L_extra, coeff["thickness"] * ufl.dot(g, v) * ds(tag))
                else:  # Robin
                    h = dolfinx.fem.Constant(dm, PETSc.ScalarType(bc.coefficient.value.to("W/(m^2*K)").magnitude))
                    tinf = dolfinx.fem.Constant(dm, PETSc.ScalarType(val.value.to(unknown_unit).magnitude))
                    a_extra = add(a_extra, h * u * v * ds(tag))
                    L_extra = add(L_extra, h * tinf * v * ds(tag))
            return bcs, a_extra, L_extra

        diag = {"its": [], "reasons": [], "res": []}

        def accept(reason, its, rel):
            diag["its"].append(its); diag["reasons"].append(reason); diag["res"].append(rel)
            return reason > 0 and math.isfinite(rel) and rel <= float(problem.solver.tolerances["residual_rtol"])

        def fail(state, why):
            return PDEExecutionRecord(problem.digest, self.identity, state, self._diag(diag, V, warnings, 0), (), why)

        from engcore.scenarios.timeline import canonical_digest
        exec_id = canonical_digest({"problem": problem.digest, "provider": self.identity.to_dict()})

        if op.template_id == "scalar_diffusion_steady":
            k = coeff["conductivity"]
            f = coeff.get("source")
            bcs, a_e, L_e = bc_forms()
            a = k * ufl.dot(ufl.grad(u), ufl.grad(v)) * dx
            if a_e is not None:
                a = a + a_e
            L = (f if f is not None else dolfinx.fem.Constant(dm, PETSc.ScalarType(0.0))) * v * dx
            if L_e is not None:
                L = L + L_e
            uh, reason, its, rel = self._linear_solve(a, L, bcs, problem, "forge_steady_")
            if not accept(reason, its, rel):
                return fail(ConvergenceState.NOT_CONVERGED if reason > 0 else ConvergenceState.FAILED, f"KSP reason {reason}, true relative residual {rel}")
            values = self._node_values(problem, dm, V, geom_to_forge, uh, 1)
            values = np.asarray(values) * field_factor
            field = computed_field(problem, self._from_unknown_unit(problem, values), exec_id)
            return PDEExecutionRecord(problem.digest, self.identity, ConvergenceState.CONVERGED, self._diag(diag, V, warnings, 1), ((0.0, field),))

        if op.template_id == "linear_elasticity_plane_stress":
            E, nu, t = coeff["youngs_modulus"], coeff["poisson_ratio"], coeff["thickness"]
            eps = lambda w: ufl.sym(ufl.grad(w))  # noqa: E731
            sigma = lambda w: E / (1 - nu**2) * ((1 - nu) * eps(w) + nu * ufl.tr(eps(w)) * ufl.Identity(2))  # noqa: E731
            bcs, _, L_e = bc_forms()
            a = t * ufl.inner(sigma(u), eps(v)) * dx
            zero = dolfinx.fem.Constant(dm, np.zeros(2, dtype=PETSc.ScalarType))
            L = ufl.dot(zero, v) * dx
            if L_e is not None:
                L = L + L_e
            uh, reason, its, rel = self._linear_solve(a, L, bcs, problem, "forge_elastic_")
            if not accept(reason, its, rel):
                return fail(ConvergenceState.NOT_CONVERGED if reason > 0 else ConvergenceState.FAILED, f"KSP reason {reason}, true relative residual {rel}")
            values = self._node_values(problem, dm, V, geom_to_forge, uh, 2)
            field = computed_field(problem, self._from_unknown_unit(problem, values), exec_id)
            return PDEExecutionRecord(problem.digest, self.identity, ConvergenceState.CONVERGED, self._diag(diag, V, warnings, 1), ((0.0, field),))

        if op.template_id == "scalar_diffusion_transient":
            tr = problem.transient
            k, c = coeff["conductivity"], coeff["volumetric_heat_capacity"]
            f = coeff.get("source")
            dt_s = tr.step.to("s").magnitude
            dt = dolfinx.fem.Constant(dm, PETSc.ScalarType(dt_s))
            u_prev = dolfinx.fem.Function(V)
            u_prev.x.array[:] = tr.initial.value.to(unknown_unit).magnitude
            outs = sorted({round(q.to("s").magnitude, 12) for q in tr.output_times})
            results = []
            steps = 0
            for seg_start, seg_end in tr.segments():
                # BIG 2 breakpoints: the form is reassembled per segment with the
                # boundary values scheduled for that segment -- never stepped across.
                overrides = {}
                for group, schedule in dict(problem.boundary_schedule).items():
                    applicable = [sq for t0, sq in schedule if t0 <= seg_start + 1e-12]
                    if not applicable:
                        return fail(ConvergenceState.FAILED, f"no scheduled boundary value for {group!r} at {seg_start} s")
                    overrides[group] = applicable[-1]
                bcs, a_e, L_e = bc_forms(overrides)
                a = c * u * v * dx + dt * k * ufl.dot(ufl.grad(u), ufl.grad(v)) * dx
                if a_e is not None:
                    a = a + dt * a_e
                L = c * u_prev * v * dx
                if f is not None:
                    L = L + dt * f * v * dx
                if L_e is not None:
                    L = L + dt * L_e
                n = int(round((seg_end - seg_start) / dt_s))
                t = seg_start
                for _ in range(n):
                    uh, reason, its, rel = self._linear_solve(a, L, bcs, problem, f"forge_tr{steps}_")
                    if not accept(reason, its, rel):
                        return fail(ConvergenceState.NOT_CONVERGED if reason > 0 else ConvergenceState.FAILED, f"step {steps}: KSP reason {reason}, rel {rel}")
                    u_prev.x.array[:] = uh.x.array
                    t = seg_start + (_ + 1) * dt_s
                    steps += 1
                    if round(t, 12) in outs:
                        values = self._node_values(problem, dm, V, geom_to_forge, uh, 1)
                        results.append((t, computed_field(problem, self._from_unknown_unit(problem, values), exec_id)))
            if [round(t, 12) for t, _ in results] != outs:
                return fail(ConvergenceState.FAILED, "not every requested output time was produced")
            return PDEExecutionRecord(problem.digest, self.identity, ConvergenceState.CONVERGED, self._diag(diag, V, warnings, steps), tuple(results))

        raise PDERefusal(f"FEniCSx provider does not implement template {op.template_id!r}")

    def _from_unknown_unit(self, problem, values):
        from engcore.scientific.units.quantity import Quantity
        factor = Quantity(1.0, problem.operator.unknown_unit).magnitude_in(problem.unknown.unit)
        return np.asarray(values) * factor

    def _diag(self, diag, V, warnings, steps):
        dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
        return PDEDiagnostics(tuple(diag["its"]), tuple(diag["reasons"]), tuple(diag["res"]), steps, int(dofs), tuple(warnings))
