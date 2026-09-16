"""Scientific domains built on the universal Scientific Core contracts.

A domain owns its physics, its components and its solver adapters. It never
adds domain-specific fields to the universal IR: everything here is a
*consumer* of ``engcore.scientific``, never a modifier of it.
"""

from types import MappingProxyType

from ..scientific.results.result import (
    UNASSESSED_DECLARATIONS_ATTRIBUTE as _UNASSESSED_ATTRIBUTE,
)
from ..scientific.consensus import (
    ROUTE_DECLARATIONS_ATTRIBUTE as _ROUTE_ATTRIBUTE,
)
from ..scientific.results.thresholds import (
    THRESHOLD_DECLARATIONS_ATTRIBUTE as _THRESHOLD_ATTRIBUTE,
)
from ..scientific.results.validation import (
    ANALYTIC_REFERENCE_DECLARATIONS_ATTRIBUTE as _ANALYTIC_REFERENCE_ATTRIBUTE,
)

#: Positions this package states on behalf of modules that cannot state their
#: own, keyed by module name. The core walks a constructing module's package
#: chain looking for exactly this attribute; it never learns what is in it.
#:
#: There is one entry, and it exists because of a freeze rather than because a
#: domain would rather not answer. ``thermal.conduction1d.solver`` builds
#: results that declare a model, and its source file is SHA-256 pinned by the
#: frozen ``thermal_t1`` experiment: adding an argument to the constructor call
#: inside it would break the pin that makes "T1 was not edited afterwards" a
#: checkable claim. So the position is stated here, one package above the
#: freeze, in the domain layer's own words rather than in the core's.
#:
#: One spelling. The frozen experiments' ``src.engcore`` is an alias for these
#: same module objects (see ``src/__init__.py``), so a constructing module's
#: name is always its ``engcore`` name. This table used to carry both, because
#: the two spellings were two module trees and a result constructed through one
#: must not be judged by which the reader used; an entry under the alias could
#: no longer be read by anything.
#:
#: This is not a place to be excused from answering. A guard in
#: ``tests/test_core_guards.py`` reads the frozen experiment configs and
#: refuses any entry here whose module is not actually pinned by one, so the
#: exemption is read off the freeze rather than remembered, and it expires the
#: day the freeze does.
_THERMAL_T1_FREEZE = (
    "not assessed: this result is produced by a module whose source is "
    "SHA-256 pinned by the frozen thermal_t1 experiment, so it cannot be "
    "edited to state its own position. The linear-diffusion model's validity "
    "domain is assessable and IS assessed on the unfrozen routes through the "
    "same physics (engcore.domains.thermal_models.conduction1d_schemes and "
    "conduction1d_bulk); this route reports the gap rather than the verdict"
)

#: The same statement, for the same freeze, about a different field.
#:
#: ``thermal.conduction1d.problem`` constructs the linear-diffusion model
#: record, and its source file is SHA-256 pinned by the frozen ``thermal_t1``
#: experiment -- so it cannot be edited to declare what that model excludes.
#: Its exclusions are real and are written in its own ``assumptions``: no
#: convection, no radiation, no phase change, no source term. A reader of a
#: credibility report still cannot see them, and that is the cost of the
#: freeze rather than a position this layer would rather not take.
#:
#: Closing it means editing a byte-pinned file and re-freezing three digest
#: tables, which would leave those digests attesting that the new bytes
#: produced the old recorded results. That is a worse record than an
#: undeclared exclusion list, and it is why this entry exists.
_THERMAL_T1_FREEZE_EXCLUSIONS = (
    "not declared: this model record is built by a module whose source is "
    "SHA-256 pinned by the frozen thermal_t1 experiment, so it cannot be "
    "edited to pass an exclusions argument. What it excludes is stated in its "
    "own assumptions -- one spatial dimension, no source term, no convection, "
    "no radiation, no phase change -- and is visible in the model record but "
    "not in a credibility report"
)

SCIENTIFIC_UNDECLARED_EXCLUSIONS: dict[str, str] = {
    "engcore.domains.thermal.conduction1d.problem": _THERMAL_T1_FREEZE_EXCLUSIONS,
}

SCIENTIFIC_UNASSESSED_DECLARATIONS: dict[str, str] = {
    "engcore.domains.thermal.conduction1d.solver": _THERMAL_T1_FREEZE,
}

# The core reads this by name. If the name it reads and the name defined here
# ever part company, the declaration above becomes invisible and every result
# from the frozen module starts failing construction -- so the disagreement is
# caught here, at import, rather than there.
assert _UNASSESSED_ATTRIBUTE == "SCIENTIFIC_UNASSESSED_DECLARATIONS", (
    f"the core looks for {_UNASSESSED_ATTRIBUTE!r}; this package defines "
    f"SCIENTIFIC_UNASSESSED_DECLARATIONS"
)

#: The threshold sets this layer's gates declare, pinned by gate.
#:
#: ``VerificationThresholds.is_declared`` is decided against this table and
#: nothing else. A gate's name is public, so a caller can build a set under it
#: with numbers of their own; the core awards a level only to a set whose gate
#: is registered here, whose version is the registered one, and whose values
#: hash to the registered digest. Any other set still runs every comparison and
#: awards nothing.
#:
#: Each digest is SHA-256 over the values exactly as
#: ``VerificationThresholds.threshold_digest`` serializes them. Changing a
#: declared number therefore means changing it in two places, on purpose: a
#: threshold that gates a level is a declaration, and a declaration that moves
#: should say so here. ``tests/test_trust_boundary_threshold_authority.py``
#: checks every entry against the constant it names, so a pin and its
#: declaration cannot drift apart silently.
#:
#: The conduction entry names a constant in a module byte-pinned by the frozen
#: thermal_t1 experiment. It is pinned from here, one package above the freeze,
#: for the reason the two tables above are.
SCIENTIFIC_THRESHOLD_DECLARATIONS = MappingProxyType({
    "electrical.dc.cross_solver": MappingProxyType({
        # 0.2.0 (NUM-03): declares an absolute floor per quantity kind; re-pinned
        # because the numbers moved. See DC_CONSENSUS_THRESHOLDS.
        "declared_by": "engcore.domains.electrical.dc_consensus.DC_CONSENSUS_THRESHOLDS",
        "version": "0.2.0",
        "threshold_digest": "aa1ca369a23744b731efa7945237741fe44953a87c4577861f559cb40cc94da9",
    }),
    "electrical.dc.linear_residual": MappingProxyType({
        # 0.2.0 (NUM-01): same values, now applied per row relative to the row's
        # own terms with a scaled floor; re-pinned because the meaning moved.
        "declared_by": "engcore.domains.electrical.dc.validation.DC_CONVERGENCE_THRESHOLDS",
        "version": "0.2.0",
        "threshold_digest": "3f5290aba1f08882446beba6cb794512ee335c408a0e4cb6ed07d1ac0a41e9f5",
    }),
    "kinetics.cstr.verification_gate": MappingProxyType({
        "declared_by": "engcore.domains.kinetics.cstr.validation.CSTR_GATE_THRESHOLDS",
        "version": "0.1.0",
        "threshold_digest": "eec365d1bfa9271f2e590c13dd845fae7c2948e1ae67a624b2becd2c98c8c1e3",
    }),
    "thermal.conduction1d.refinement": MappingProxyType({
        "declared_by": "engcore.domains.thermal.conduction1d.validation.CONDUCTION_GATE_THRESHOLDS",
        "version": "0.1.0",
        "threshold_digest": "88b2ce9f040139bf34e827904917dbe0ea534445b81b74a525800a877f83291e",
    }),
    "thermal_models.lumped.analytic_reference": MappingProxyType({
        # R-04 (core re-audit 2026-09-16): the lumped analytic check's tolerance was the
        # reference's own error bound plus a rounding budget the module held as a bare
        # constant, with nothing declared behind it -- and it is the check the one SUPPORTED
        # MCP report rests on. The budget is the part that IS a policy choice, so it gets an
        # owner. SOLVER_ROUNDING_ULPS keeps its name and its value; it is now read from here.
        "declared_by": "engcore.domains.thermal_models.lumped.LUMPED_ANALYTIC_REFERENCE_THRESHOLDS",
        "version": "0.1.0",
        "threshold_digest": "0e092d57b7d86e71ffc1bb28d122b44adaabe089e5d5c7a78defa191e911f0ca",
    }),
})

#: ``thermal_models.conduction2d`` is deliberately absent. Its gate declares
#: thresholds and reports every residual against them, and awards no level at
#: all — so registering it would grant an authority it does not exercise. See
#: that module's ``CONDUCTION2D_GATE_THRESHOLDS`` for the argument.

#: Which closed forms this layer stands behind, pinned by reference id (R-04, core re-audit 2026-09-16).
#:
#: ``ANALYTICALLY_VERIFIED`` is a claim that a solve agrees with an independent closed form, and it needed
#: no issuer at all: ``ValidationCheck(PASS, establishes=ANALYTICALLY_VERIFIED, evidence=("trust me",))``
#: was constructed, attained, survived ``from_dict`` and carried a SUPPORTED verdict, while the same
#: construction claiming BENCHMARK_VALIDATED was refused. The one SUPPORTED report either MCP tool can
#: return rests on exactly this level.
#:
#: So the level is now held to its issuer's record, the way the oracle and consensus levels are:
#: ``validation._analytic_issuer_gap`` requires the check's evidence to name a reference registered here,
#: carry the SHA-256 of that reference's own expression, claim repository authority, and name the declared
#: threshold set of the gate this table says awards it.
#:
#: **What is pinned is the STATEMENT, not the code.** What makes the level meaningful is WHICH closed form
#: the solve was compared against, and that is the expression. A digest of the implementing module's bytes
#: would move on every edit to the file, including edits that do not touch the formula, and would make the
#: level brittle rather than bound.
#:
#: Each digest is recomputed at import from the constant the entry names, so this table and the constant
#: cannot drift apart silently -- the same discipline ``SCIENTIFIC_THRESHOLD_DECLARATIONS`` uses.
SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS = MappingProxyType({
    "thermal_models.lumped.series_recurrence": MappingProxyType({
        "declared_by": "engcore.domains.thermal_models.lumped.REFERENCE_EXPRESSION",
        "version": "0.1.0",
        "expression": (
            "T(t) = sum a_n t^n with a_0 = T0, C a_1 = Q - hA (a_0 - T_amb), "
            "C (n+1) a_{n+1} = -hA a_n"
        ),
        "expression_digest": "2534eb18c91ca70e9dbd156ce76b824a75c2f595f3cb05f16eaab77352fd5ba4",
        "thresholds_gate": "thermal_models.lumped.analytic_reference",
    }),
    "thermal.conduction1d.single_mode_analytic": MappingProxyType({
        "declared_by": "engcore.domains.thermal.conduction1d.validation.REFERENCE_EXPRESSION",
        "version": "0.1.0",
        "expression": "u(x,t) = sin(pi*x/L) * exp(-alpha*pi^2*t/L^2)",
        "expression_digest": "a8564c9933fbad5abed6e16fd6f12188a3318872b27b8489f0222a04aee5f1c6",
        "thresholds_gate": "thermal.conduction1d.refinement",
    }),
    "kinetics.cstr.adiabatic_reaction_free_invariant": MappingProxyType({
        "declared_by": "engcore.domains.kinetics.cstr.validation.INVARIANT_EXPRESSION",
        "version": "0.1.0",
        "expression": (
            "Z = T + beta C_A;  Z(t) = Z_f + (Z_0 - Z_f) exp(-a t)  [exact when UA = 0]"
        ),
        "expression_digest": "0fb7efc02108e3d14f7b0369ea83ddbdfebcbc7834b153c11bee14161681693b",
        "thresholds_gate": "kinetics.cstr.verification_gate",
    }),
})

assert _ANALYTIC_REFERENCE_ATTRIBUTE == "SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS", (
    f"the core looks for {_ANALYTIC_REFERENCE_ATTRIBUTE!r}; this package defines "
    f"SCIENTIFIC_ANALYTIC_REFERENCE_DECLARATIONS"
)

assert _THRESHOLD_ATTRIBUTE == "SCIENTIFIC_THRESHOLD_DECLARATIONS", (
    f"the core looks for {_THRESHOLD_ATTRIBUTE!r}; this package defines "
    f"SCIENTIFIC_THRESHOLD_DECLARATIONS"
)

#: What each solve route this layer declares is made of, pinned by route id.
#:
#: ``CrossSolverConsensus`` reads independence from these and from nothing a
#: caller supplies. A route counts only when its id is registered here, the
#: solver that ran is the implementation the entry is for, and its dependencies
#: hash to the pinned digest -- so a route named after a declared one, or a
#: declaration edited after it was pinned, earns nothing.
#:
#: Each digest is SHA-256 over the canonical identities exactly as
#: ``RouteDependencies.digest`` serializes them, which resolves every
#: importable identity to its defining module and qualified name. Changing a
#: route's dependencies therefore means changing them in two places, on
#: purpose: what a route is made of is a declaration, and a declaration that
#: moves should say so here.
#:
#: ``identities`` lists what the route declares, per dimension, exactly as
#: declared (IND-05). The core compares a route's declaration against this list
#: BEFORE hashing it, because hashing imports every ``py:`` module an identity
#: names -- and a consensus read from a payload would otherwise import whatever
#: module the payload chose. Only a declaration listed here is ever resolved.
#: ``tests/test_audit_consensus_resolution_and_floor.py`` checks each list against
#: the constant it restates.
#:
#: ``threshold_gate_id`` and ``tolerance_key`` name the threshold a comparison
#: between these routes is judged under (CONS-01). A declared set is declared
#: for one gate; without this, routes 40 % apart judged against another
#: domain's declared refinement contraction earned the level, because that set
#: IS declared -- for a different gate. A consensus under any other set or key
#: establishes nothing.
SCIENTIFIC_ROUTE_DECLARATIONS = MappingProxyType({
    "electrical.dc.native_mna": MappingProxyType({
        "declared_by": "engcore.domains.electrical.dc_consensus.NATIVE_ROUTE_DEPENDENCIES",
        "solver_id": "electrical.dc.mna",
        "backend": "scipy.linalg.solve",
        "dependency_digest": "c23fff6bdbda0b6038ffcf4ee78bc994bad03aee511191445efec1a55329fd70",
        "identities": MappingProxyType({
            "problem_declaration": ("py:engcore.domains.electrical.dc.circuit:DCCircuit",),
            "preprocessing": ("py:engcore.domains.electrical.dc.mna:assemble",),
            "numerical_method": ("ext:lapack:gesv",),
            "implementation": ("py:engcore.domains.electrical.dc.solver:ElectricalDCSolver",),
            "backend": ("py:scipy.linalg:solve",),
        }),
        "threshold_gate_id": "electrical.dc.cross_solver",
        "tolerance_key": "agreement_rel_tol",
    }),
    "electrical.dc.external_simulator": MappingProxyType({
        "declared_by": "engcore.domains.electrical.dc_consensus.EXTERNAL_ROUTE_DEPENDENCIES",
        "solver_id": "engcore.electrical.dc.ngspice",
        "backend": "ngspice",
        "dependency_digest": "81156a57562add4c56a9a470c6039c0e0a52c9e2fbcf0fef3fc8ab0be8b39d43",
        "identities": MappingProxyType({
            "problem_declaration": ("py:engcore.domains.electrical.dc.circuit:DCCircuit",),
            "preprocessing": ("ext:ngspice:internal_assembly", "py:engcore.domains.electrical.ngspice:build_netlist",),
            "numerical_method": ("ext:ngspice:sparse_lu",),
            "implementation": ("py:engcore.domains.electrical.ngspice:NgspiceDCSolver",),
            "backend": ("ext:ngspice",),
        }),
        "threshold_gate_id": "electrical.dc.cross_solver",
        "tolerance_key": "agreement_rel_tol",
    }),
    # The two integration entries pin no backend, and the DC entries above do.
    # This solver names its backend with the library version it ran against
    # (solve_ivp/scipy-<version>), which is execution provenance: pinning it
    # would pin one environment and refuse the same route on the next upgrade.
    # What independence reads is the backend *dependency* the declaration names,
    # and the digest pins that.
    "kinetics.cstr.integration:BDF": MappingProxyType({
        "declared_by": "engcore.domains.kinetics.cstr.validation.INTEGRATION_ROUTE_DEPENDENCIES",
        "declared_key": "BDF",
        "solver_id": "kinetics.cstr.scipy_implicit_ivp",
        "dependency_digest": "00f2410046eeb60a7fe3f6532da938b50493e0d3c49c20c2c124b727fc6e9288",
        "identities": MappingProxyType({
            "problem_declaration": ("py:engcore.domains.kinetics.cstr.problem:ReactorRun",),
            "preprocessing": ("py:engcore.domains.kinetics.cstr.solver:assemble",),
            "numerical_method": ("py:scipy.integrate:BDF",),
            "implementation": ("py:engcore.domains.kinetics.cstr.solver:CSTRSolver",),
            "backend": ("py:scipy.integrate:solve_ivp",),
        }),
        "threshold_gate_id": "kinetics.cstr.verification_gate",
        "tolerance_key": "tolerance_rel_tol",
    }),
    "kinetics.cstr.integration:Radau": MappingProxyType({
        "declared_by": "engcore.domains.kinetics.cstr.validation.INTEGRATION_ROUTE_DEPENDENCIES",
        "declared_key": "Radau",
        "solver_id": "kinetics.cstr.scipy_implicit_ivp",
        "dependency_digest": "496c729764e156accba69ef31ec13556eb861e4b343a829a53d52a9c2d702c93",
        "identities": MappingProxyType({
            "problem_declaration": ("py:engcore.domains.kinetics.cstr.problem:ReactorRun",),
            "preprocessing": ("py:engcore.domains.kinetics.cstr.solver:assemble",),
            "numerical_method": ("py:scipy.integrate:Radau",),
            "implementation": ("py:engcore.domains.kinetics.cstr.solver:CSTRSolver",),
            "backend": ("py:scipy.integrate:solve_ivp",),
        }),
        "threshold_gate_id": "kinetics.cstr.verification_gate",
        "tolerance_key": "tolerance_rel_tol",
    }),
})

assert _ROUTE_ATTRIBUTE == "SCIENTIFIC_ROUTE_DECLARATIONS", (
    f"the core looks for {_ROUTE_ATTRIBUTE!r}; this package defines "
    f"SCIENTIFIC_ROUTE_DECLARATIONS"
)
