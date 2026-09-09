"""What the two DC solve routes are made of, and what their agreement earns.

This domain has had two ways of computing one operating point since the
heterogeneous-solver milestone: the native modified-nodal-analysis path, and an
external circuit simulator reached through :mod:`.ngspice`. Until now their
agreement lived entirely in the test suite — ``test_c`` in
``tests/test_heterogeneous_ngspice.py`` solved a divider both ways, asserted the
worst relative difference was under a preregistered bound, and measured it at
machine epsilon. That is a real measurement and it was never in a record.

A test assertion is not evidence a reader of a result can see. It runs on the
maintainer's machine, on the maintainer's circuit, and it leaves nothing behind:
no attained level, no declaration of why two answers agreeing should count for
anything. :mod:`engcore.scientific.consensus` is where that now lives, and this
module is this domain's declaration into it.

Why these two routes are declared independent
----------------------------------------------
They share the *problem* — one :class:`~.dc.circuit.Circuit`, with resistances
and topology this repository declares. Every consensus shares its problem; that
is what makes two answers comparable and it is not a shared component.

They also both realize modified nodal analysis, and ``dc_realizations`` says so
explicitly: ``test_m`` pins that the two solvers execute the **same
realization**. That is a shared *mathematical formulation* and it is
deliberately not declared as a shared component, because each route assembles
its own system from the circuit description and factors it with its own
arithmetic. A wrong conductance stamp on the native side is visible to the
external route, which builds no such stamp; a wrong branch-current row is
visible for the same reason. That visibility is the entire operational content
of the word independent, and it is what separates this pair from two
integrators sharing one right-hand side — see the kinetics gate, where the
declaration comes out the other way.

So each route declares its own formulation component under its own name. The
shared realization is a shared claim about *what is computed*; it is not shared
machinery for computing it.

What is deliberately not claimed
---------------------------------
Not that the external simulator is correct, and not that its numbers were
verified — that happens elsewhere and separately, in the adapter's own
admission gate and in the domain's ordinary validation report, which runs over
the external answer against this repository's own assembled equations.

Not that agreement makes either answer right. Two independent routes can be
wrong together about a circuit that was described wrongly, and no consensus
here or anywhere else can see that.

And nothing about a singular system. The realization's own precondition is
checked per solve, not here; outside it both routes return something and the
question of whether they agree is the wrong question to be asking.
"""

from __future__ import annotations

from typing import Any, Mapping

from ...scientific.consensus import (
    ComponentKind,
    CrossSolverConsensus,
    SharedComponent,
    SolveRoute,
)
from ...scientific.results.thresholds import VerificationThresholds
from ...scientific.solvers.protocol import SolverIdentity
from ...scientific.units.quantity import Quantity

__all__ = [
    "DC_CONSENSUS_THRESHOLDS",
    "EXTERNAL_ROUTE_ID",
    "NATIVE_ROUTE_ID",
    "dc_consensus",
    "external_route",
    "native_route",
    "route_values",
]

NATIVE_ROUTE_ID = "electrical.dc.native_mna"
EXTERNAL_ROUTE_ID = "electrical.dc.external_simulator"

#: The number two independent DC routes must agree to before the level is
#: awarded.
#:
#: Not a new decision. ``1e-9`` is this domain's own tolerance everywhere else —
#: ``DCValidationSettings`` uses it for the residual, for charge balance, for
#: the source relation and for power balance — and the heterogeneous milestone
#: preregistered the same bound for exactly this comparison. It is loose by
#: seven orders against what the comparison actually measures, which is stated
#: here rather than tightened: a bound chosen to sit just above the observed
#: value is a bound chosen from the answer.
DC_CONSENSUS_THRESHOLDS = VerificationThresholds(
    gate_id="electrical.dc.cross_solver",
    version="0.1.0",
    values={"agreement_rel_tol": 1e-9},
    basis=(
        "the DC domain's own tolerance, preregistered for this comparison in "
        "the heterogeneous-solver milestone; both routes solve a small linear "
        "system in double precision, so agreement is expected near machine "
        "epsilon and this bound is loose against that by orders of magnitude "
        "while still catching any convention error"
    ),
)


def native_route(solver: SolverIdentity) -> SolveRoute:
    """The in-process route: this repository assembles, and factors densely."""
    return SolveRoute(
        route_id=NATIVE_ROUTE_ID,
        solver=solver,
        components=frozenset(
            {
                SharedComponent(
                    ComponentKind.FORMULATION,
                    "engcore.domains.electrical.dc.mna:assemble",
                    "this repository's own stamping of the nodal rows and the "
                    "branch-current augmentation into a dense matrix",
                ),
                SharedComponent(
                    ComponentKind.LINEAR_ALGEBRA,
                    "numpy.linalg:solve",
                    "a dense LAPACK factorisation of the assembled system",
                ),
                SharedComponent(
                    ComponentKind.RUNTIME,
                    "engcore:in_process",
                    "executed inside this interpreter",
                ),
            }
        ),
        notes=(
            "assembles the system from the circuit description and solves it "
            "directly; no outer iteration"
        ),
    )


def external_route(solver: SolverIdentity) -> SolveRoute:
    """The out-of-process route: an external simulator, told only the circuit.

    What this repository hands over is a description of the circuit. Everything
    that turns it into numbers — the equations, their ordering, the sparse
    factorisation, the convergence aids — belongs to the external program and
    is named here as the external program rather than described, because this
    module does not know its internals and a declaration that guessed at them
    would be the fiction the whole mechanism exists to refuse.
    """
    return SolveRoute(
        route_id=EXTERNAL_ROUTE_ID,
        solver=solver,
        components=frozenset(
            {
                SharedComponent(
                    ComponentKind.FORMULATION,
                    f"{solver.backend or solver.solver_id}:internal_assembly",
                    "the external program builds its own equations from the "
                    "circuit description; this repository stamps nothing on "
                    "this route",
                ),
                SharedComponent(
                    ComponentKind.LINEAR_ALGEBRA,
                    f"{solver.backend or solver.solver_id}:internal_solver",
                    "the external program's own sparse factorisation and its "
                    "own convergence aids",
                ),
                SharedComponent(
                    ComponentKind.RUNTIME,
                    "external:separate_process",
                    "executed as a separate operating-system process",
                ),
            }
        ),
        notes=(
            "receives a description of the circuit and returns node "
            "potentials and element quantities; its equations, its ordering "
            "and its arithmetic are its own"
        ),
    )


def route_values(result: Any) -> dict[str, float]:
    """One route's answer as plain magnitudes, in each quantity's own unit.

    Comparing magnitudes requires a unit to compare them in, and picking one
    here would silently convert. Each metric is read in the unit its own
    :class:`~engcore.scientific.units.quantity.Quantity` carries, so a route
    that returned the right number in the wrong unit shows up as a
    disagreement rather than being normalised into an agreement.
    """
    values: dict[str, float] = {}
    for name, quantity in result.values.items():
        if not isinstance(quantity, Quantity):
            continue
        values[name] = float(quantity.magnitude_in(quantity.units))
    return values


def dc_consensus(
    *,
    native: Any,
    native_solver: SolverIdentity,
    external: Any,
    external_solver: SolverIdentity,
    consensus_id: str = "electrical.dc.operating_point",
    thresholds: VerificationThresholds = DC_CONSENSUS_THRESHOLDS,
) -> CrossSolverConsensus:
    """The two DC routes on one circuit, compared and declared.

    Takes two already-computed results rather than running anything. A
    consensus is a statement *between* results and cannot be produced by either
    solve, which is also why it is not a check inside either route's validation
    report: neither run is in a position to make it.

    The solver identities are passed rather than read off the results, because
    a :class:`~engcore.scientific.results.provenance.ProvenanceRecord` keeps
    only ``(solver_id, version)`` and drops the backend — and the backend is
    what names the external route's components. Reconstructing an identity from
    the pair would silently declare the external route's arithmetic under a
    name that is not the one that produced it.
    """
    native_values = route_values(native)
    return CrossSolverConsensus.over(
        consensus_id=consensus_id,
        routes=(
            native_route(native_solver),
            external_route(external_solver),
        ),
        values={
            NATIVE_ROUTE_ID: native_values,
            EXTERNAL_ROUTE_ID: route_values(external),
        },
        thresholds=thresholds,
        tolerance_key="agreement_rel_tol",
        # THE CONTRACT: the external route must reproduce the WHOLE operating
        # point this repository computed, not whichever part of it the adapter
        # happened to return.
        #
        # Taken from the native route because the operating point is what a DC
        # solve produces and its members depend on the circuit -- there is no
        # fixed list to write down here. That is a declaration, not a guess
        # from the intersection: it says the native result defines the question
        # and the external route is being asked to answer all of it. An
        # external route returning a subset has confirmed part of an operating
        # point, which is a different and weaker statement, and before this it
        # was awarded the same level as confirming the whole one.
        required_outputs=tuple(native_values),
        notes=(
            "one operating point, computed by this repository's own modified "
            "nodal analysis and by an external circuit simulator that shares "
            "none of its arithmetic"
        ),
    )
