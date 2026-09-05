"""How the Electrical DC models are computed: modified nodal analysis.

`HETERO-NGSPICE`. The DC domain has always declared *what* it claims — Kirchhoff's
current law, Ohm's law for a resistor, the ideal voltage source relation — and
never *how* those claims are computed. Every `ExecutionBinding` it produced
carried ``realization=None``, which `ET-VERTICAL` §11 recorded as honest rather
than as a gap: the package predates `MODEL0-R`.

It becomes a gap the moment a second, external solver computes the same claims.
Without a realization record, "ngspice and the native path do the same thing"
has nowhere to be stated, and the only thing that could distinguish them is the
solver identity — which would make *changing the linear solver* look like
changing the science. That is exactly the collapse `ModelRealizationDefinition`
exists to prevent.

Why this module sits beside ``dc/`` and not inside it
-----------------------------------------------------
``tests/test_min_foundation_electrothermal.py::test_i2`` pins the file set of
``domains/electrical/dc/`` by name. A new file inside that package would break a
pre-existing test. This is the pattern ``material.py`` and ``thermal_models/lumped.py``
already established: additive, beside the pinned tree, referencing it by
``ModelReference`` and editing nothing.

One record per model, and why that is a finding rather than a design
--------------------------------------------------------------------
``ModelRealizationDefinition.model`` is a **single** ``ModelReference``. One DC
analysis invokes three (KCL, Ohm, the ideal source), and modified nodal analysis
realizes them **jointly** — one assembly, one factorisation, all three claims
discharged together. The record cannot say "these three, together".

So three records are declared, each true on its own terms: KCL *is* realized by
the nodal balance, the resistor relation *is* realized by its conductance stamp,
the source relation *is* realized by its branch-current row. What is lost is that
they are one computation. That is the mirror of `model0r-differential-evidence.md`
known unknown 1 — several solvers, one computation — met from the other side, and
it is recorded as a measured limitation of the record's grain rather than
repaired by inventing a composite "DC analysis" model that no domain declares.
``ModelRealizationDefinition`` is `DESIGN-FROZEN` and gains no field.

What these records deliberately do not say
------------------------------------------
No concrete solver, no backend, no matrix format, no library. Dense LAPACK LU and
sparse KLU are two ways to factor one assembled system; the capability
vocabulary has one member for both (``core:linear_system``) and offers no
sparse/dense distinction. A realization that named a factorisation would make a
linear-algebra choice into a scientific identity.

The non-singularity assumption is stated explicitly, and it is load-bearing.
Outside it the two solvers genuinely diverge: the native path refuses a singular
system, and ngspice regularises it by gmin stepping and returns one of the
infinitely many solutions. That divergence is a property of each *solver* on an
inadmissible system, not of this realization — which is why the precondition is
declared here rather than left implicit.
"""

from __future__ import annotations

from ...scientific.capabilities import ScientificCapability
from ...scientific.ir.problem import ModelReference
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.realizations.registry import RealizationRegistry
from ...scientific.solvers.capability import CoreCapabilities, SolverCapabilityId
from .dc import (
    ELECTRICAL_DC_LINEAR,
    IDEAL_VOLTAGE_SOURCE_MODEL,
    KCL_MODEL,
    RESISTOR_OHM_MODEL,
)

__all__ = [
    "IDEAL_SOURCE_CONSTRAINT",
    "IDEAL_VOLTAGE_SOURCE_MNA_REALIZATION",
    "KCL_MNA_REALIZATION",
    "MNA_REALIZATIONS",
    "NODAL_CHARGE_BALANCE",
    "RESISTOR_CONSTITUTIVE_RELATION",
    "RESISTOR_OHM_MNA_REALIZATION",
    "dc_realizations",
    "realizations_for_models",
]

REALIZATION_VERSION = "0.1.0"

#: What each record's own model contributes to the assembled system.
#:
#: **One capability per record, each true of the record that declares it.** An
#: earlier form gave all three the single identity
#: ``electrical:dc_operating_point``, on the argument that MNA provides the
#: operating point jointly and that three identities nothing consumes would be
#: capability inflation. The adversarial pass killed it, and correctly:
#: ``RealizationRegistry.providing()`` is a real existing consumer, and it would
#: have returned three realizations for that identity — a caller taking the
#: first gets the KCL record, which alone computes nothing. Three false
#: statements plus a true docstring is not honesty; the docstring is not the
#: record. And the "nothing consumes them" objection was measured to apply
#: equally to the shared identity, so it did not discriminate.
#:
#: What is genuinely lost remains lost, and is recorded rather than encoded:
#: ``ModelRealizationDefinition`` cannot say that these three are discharged
#: **jointly**, in one assembly and one factorisation. No capability expresses
#: the operating point, because no single record may claim it.
NODAL_CHARGE_BALANCE = ScientificCapability.parse(
    "electrical:nodal_charge_balance"
)
RESISTOR_CONSTITUTIVE_RELATION = ScientificCapability.parse(
    "electrical:resistor_constitutive_relation"
)
IDEAL_SOURCE_CONSTRAINT = ScientificCapability.parse(
    "electrical:ideal_source_constraint"
)

#: What a backend must be able to do to execute any of these. Identical for
#: every one of them, and identical for both the native and the external solver:
#: the domain's own linear-DC capability plus a linear system solve. There is no
#: finer capability to declare — ``CoreCapabilities`` has ``LINEAR_SYSTEM`` and
#: nothing about sparsity, ordering or factorisation.
_SOLVER_CAPABILITIES = frozenset(
    {
        SolverCapabilityId.coerce(ELECTRICAL_DC_LINEAR),
        SolverCapabilityId.coerce(CoreCapabilities.LINEAR_SYSTEM),
    }
)

_MNA_ASSUMPTIONS = (
    "modified nodal analysis: one equation per non-reference node, plus one "
    "branch-current unknown per ideal voltage source",
    # A claim about the MODEL's mathematical form, not about a procedure.
    # An earlier form said "solved directly, not iterated", which is an
    # execution property — the category this record excludes — and which was
    # never measured for the external solver. ngspice recovers a difficult DC
    # operating point by gmin and source stepping, an outer iteration, so the
    # claim was also false. A Krylov realization of the same system would have
    # contradicted it outright.
    "linear elements only; the model imposes no outer nonlinear iteration",
    # The precondition, declared because the two concrete solvers behave
    # differently outside it and neither behaviour is this realization's claim.
    "the assembled system is non-singular; behaviour on a singular system is a "
    "property of the concrete solver and is not claimed by this realization",
)

_IMPLEMENTATION = ImplementationReference(
    implementation_id="engcore.domains.electrical.dc_realizations",
    version=REALIZATION_VERSION,
    reference="modified nodal analysis of a linear resistive network",
)


def _mna_realization(
    model, *, provides, name: str, description: str
) -> ModelRealizationDefinition:
    return ModelRealizationDefinition(
        realization_id=f"{model.model_id}.modified_nodal_analysis",
        version=REALIZATION_VERSION,
        model=ModelReference(model.model_id, model.version),
        # The mathematical form of the computation: a linear algebraic system.
        # Not a statement about how it is factored.
        formulation=ModelFormulation.ALGEBRAIC,
        name=name,
        description=description,
        provided_capabilities=frozenset({provides}),
        required_capabilities=frozenset(),
        required_solver_capabilities=_SOLVER_CAPABILITIES,
        assumptions=_MNA_ASSUMPTIONS,
        implementation=_IMPLEMENTATION,
    )


KCL_MNA_REALIZATION = _mna_realization(
    KCL_MODEL,
    provides=NODAL_CHARGE_BALANCE,
    name="Kirchhoff's current law by nodal balance",
    description=(
        "Charge conservation is discharged as one row per non-reference node: "
        "the sum of stamped conductances into that node, balanced against the "
        "currents imposed on it."
    ),
)

RESISTOR_OHM_MNA_REALIZATION = _mna_realization(
    RESISTOR_OHM_MODEL,
    provides=RESISTOR_CONSTITUTIVE_RELATION,
    name="Resistor constitutive relation by conductance stamp",
    description=(
        "V = IR is discharged by stamping 1/R into the four positions its two "
        "terminals index, so the relation is enforced by the assembled system "
        "rather than evaluated after it."
    ),
)

IDEAL_VOLTAGE_SOURCE_MNA_REALIZATION = _mna_realization(
    IDEAL_VOLTAGE_SOURCE_MODEL,
    provides=IDEAL_SOURCE_CONSTRAINT,
    name="Ideal voltage source by branch-current augmentation",
    description=(
        "An ideal source imposes a potential difference and admits any current, "
        "which a pure nodal formulation cannot express. The relation is "
        "discharged by adding one branch-current unknown and one constraint "
        "row — the 'modified' in modified nodal analysis."
    ),
)

#: Every realization this module declares. The ideal *current* source model has
#: none: no circuit executed by this repository uses one, and a realization
#: record for a computation nothing performs would be a guess.
MNA_REALIZATIONS = (
    KCL_MNA_REALIZATION,
    RESISTOR_OHM_MNA_REALIZATION,
    IDEAL_VOLTAGE_SOURCE_MNA_REALIZATION,
)

_BY_MODEL_ID = {r.model.model_id: r for r in MNA_REALIZATIONS}


def dc_realizations() -> RealizationRegistry:
    """A fresh registry. No global singleton exists."""
    return RealizationRegistry(MNA_REALIZATIONS)


def realizations_for_models(models) -> tuple[ModelRealizationDefinition, ...]:
    """The MNA realization of each supplied model, where one is declared.

    Returns nothing for a model this module does not realize, rather than
    raising or substituting: a model with no declared realization is the state
    the whole DC domain was in before this module existed, and it is honest.
    """
    found = []
    for model in models:
        realization = _BY_MODEL_ID.get(
            getattr(model, "model_id", getattr(model, "model_id", None))
        )
        if realization is not None:
            found.append(realization)
    return tuple(found)
