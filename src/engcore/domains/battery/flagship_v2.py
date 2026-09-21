"""The recovery's cell model: same kernel, a different charge-state identity.

``battery.cell.electrothermal_1rc@0.2.0``.

What is the same as ``@0.1.0``
------------------------------
Everything the equations do. One RC branch, Arrhenius on both resistances, the
irreversible heat term only, the same closed-form update, the same solver, the
same realization arithmetic. The Sprint 3 kernel
:func:`~engcore.domains.battery.electrothermal.advance_electrothermal_step`
executes both versions, and a regression pins the older version's outputs so
this module's arrival could not have moved them.

Adding *parameters* was tried and rejected. A second RC branch was fitted on
calibration cells and judged on validation cells and did not earn its place, and
the measured rest relaxation is the reason it was refused rather than merely
found unhelpful: two exponentials fit every calibration tail better than one, but
the slower time constant scatters wider than its own median across trajectories,
so it is a free parameter absorbing residuals rather than a second physical
process.

What is different, and why it is a new version
-----------------------------------------------
**The charge-state identity.** ``@0.1.0`` declares that "the basis is a
constant, not a fitted capacity", and lists "any dependence of the usable
capacity on temperature or rate" among its exclusions. That constant is the
manufacturer's 2 Ah rating, which is 20-33 % above what these cells deliver, depending on which of them: 22 % at the median over this corpus's own trajectories and 33 % over the whole retained archive
and wrong by a different amount for each of them. This version's basis is a
**measured available charge**, established per run by
:mod:`engcore.domains.battery.capacity` from cycles that completed before the
run, and its charge state is a fraction of that. The basis still arrives as an
external input; what changed is what the model declares that input to mean, and
a model whose state variable means something else is a different model.

**A charge-state axis on the ohmic resistance, with no fitted parameter.** The
measured charge/discharge branch difference falls from 0.201 to 0.133 ohm across
charge state when warm and from 0.499 to 0.294 ohm when cold. That is carried as
a declared multiplicative shape normalized to one at charge state 0.5, so the
fitted reference resistance still means the resistance at that state. Every value
in it is a median of calibration measurements and no parameter is fitted for it.

What promoted it was **identifiability**, not fit. Without it the cold parameter
unit -- the one that predicts the locked holdout -- leaves the ohmic reference
resistance, the polarization reference resistance and the polarization activation
energy all unidentified, at a normal-matrix condition number of 1.6e20 and a
correlation of -0.9999 between R0 and its own activation energy: the fitter is
absorbing a real charge-state trend into a constant and its temperature slope.
With the shape that unit is fully identified and the condition number falls four
orders of magnitude. On validation the shape is close to neutral -- 2.4 mV of
mean absolute error gained, 2.1 mV of 95th percentile given back -- so fit alone
would not have promoted it and identifiability did.

The shape is a measurement only where the two branches overlap in charge state.
Outside that interval it is HELD at its end value, which is a declared
approximation: extrapolating the trend would invent a resistance the branches
never saw, and refusing there would refuse most of every trajectory.
``R0_SHAPE_MEASURED_INTERVALS`` says which part is measured.

**The open-circuit voltage authority.** A curve on a different charge-state axis
is a different relation, so it could not have been an amendment to the old
table. And it is not one curve: conditioned on the declared cell-temperature
band it is two, which differ by 80 mV at the median knot -- far outside the
frozen 50 mV acceptance tolerance. The band is a declared condition of the run,
read from the chamber ambient and the nominal load, both known before it starts;
it is never taken from the evolving state, so the curve a run is predicted with
cannot drift mid-run.

Because the curve is banded, ``open_circuit_voltage_band`` is a declared
condition of this model and appears in its validity domain. A run in neither
band is refused: nothing in the evidence lies between 13 and 23 degC.

What this version does not fix
------------------------------
It has no state that ages, no entropic heat, no hysteresis, no second time
constant, and no charge-state axis on the *polarization* resistance. Its
parameters are
still fitted per operating block rather than derived, and a block with one
calibration cell carries no cell-to-cell spread -- which is the limitation the
recovery's own validation evidence puts at 20 to 35 mV.
"""

from __future__ import annotations

from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference
from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelType,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
)
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.units.quantity import Quantity
from . import context as ctx
from . import electrothermal as et
from . import flagship as v1
from .flagship_ocv_v2 import (
    CELL_TEMPERATURE_BANDS,
    COLD_R0_SHAPE_MEASURED_INTERVAL,
    OCV_V2_CURVES,
    R0_SHAPE_REFERENCE_Z,
    R0_V2_SHAPES,
    WARM_R0_SHAPE_MEASURED_INTERVAL,
    band_for,
)

#: Where each band's ohmic shape is a measurement rather than a held edge.
R0_SHAPE_MEASURED_INTERVALS = {
    "cold": COLD_R0_SHAPE_MEASURED_INTERVAL,
    "warm": WARM_R0_SHAPE_MEASURED_INTERVAL,
}

MODEL_ID = v1.MODEL_ID
MODEL_VERSION = "0.2.0"
REALIZATION_VERSION = "0.2.0"

#: The declared condition that selects the open-circuit voltage band. It is a
#: condition and not a state: it is fixed for a run before the run begins.
OPEN_CIRCUIT_VOLTAGE_BAND = "open_circuit_voltage_band"

#: Band names, as integers so a RangeCondition can carry them. ``cold`` is 0 and
#: ``warm`` is 1; the model refuses anything else, which is what makes the gap
#: between the bands a refusal rather than an interpolation.
BAND_CODES = {name: index for index, (name, _low, _high) in enumerate(CELL_TEMPERATURE_BANDS)}

_ASSUMPTIONS = (
    "one lumped cell at one temperature, which the thermal participant owns",
    "the load current is constant across each advanced interval",
    "one RC branch stands for the whole diffusion overpotential",
    "the ohmic and polarization resistances follow an Arrhenius law in the "
    "cell temperature, with the fitted activation energies",
    "the open-circuit voltage is the declared curve of the declared "
    "cell-temperature band, over that curve's declared charge-state interval "
    "and nowhere else",
    "the ohmic resistance carries the measured charge-state shape of its band "
    "as a multiplicative factor normalized at charge state 0.5, held at its end "
    "values outside the interval the branch difference measures. No parameter "
    "is fitted for it",
    "the charge state is a fraction of a MEASURED available charge, supplied "
    "per run from cycles that completed before it. It is not the "
    "manufacturer's rating and it is not fitted to the run being predicted",
    "the declared band is a property of the run's condition, fixed before the "
    "run begins, so the curve does not change while the cell self-heats",
)

_EXCLUSIONS = (
    "reversible entropic heat I T dU/dT, which is of the same order as the "
    "irreversible term at low rate and changes sign with current direction; "
    "no entropy coefficient is measured for this cell and none is assumed",
    "ageing as a state. The available charge the basis is built from carries "
    "the capacity that ageing has already taken, because it is measured on a "
    "recent cycle; the model still has no state that ages and predicts no "
    "further fade over the run it is asked about",
    "resistance growth with cycle count. Only the capacity part of ageing is "
    "carried, and the two are not the same",
    "hysteresis between charge and discharge. The declared curves carry the "
    "hysteresis of the branches they were averaged from and cannot separate "
    "it. The measured branch gap's rate dependence has the wrong sign for a "
    "rate-independent offset, so none is modelled",
    "any second, slower diffusion time constant. Two exponentials fit the "
    "measured rest relaxation better than one, but the slower constant is not "
    "reproducible across trajectories, so the branch is refused rather than "
    "fitted",
    "any charge-state axis on the polarization resistance. The branch "
    "difference measures one resistance and cannot separate the ohmic and "
    "polarization parts of it, so the shape is applied to the ohmic term alone "
    "and the polarization term carries none",
    "any measured charge-state dependence of the ohmic resistance outside the "
    "interval where the two branches overlap. There the shape is held at its "
    "end value and the record says so",
    "any interpolation of the open-circuit voltage between the declared bands. "
    "Nothing is measured between them and the model refuses there",
    "any dependence of the usable capacity on temperature or rate WITHIN a "
    "run. The basis is constant over one run; it differs between runs because "
    "it is measured for each",
    "charge acceptance. Negative current is admitted arithmetically but no "
    "charge-direction evidence supports the parameters",
    "internal temperature gradients. The cell is one lumped temperature and "
    "no Biot-number screen is stated for it",
)

#: The band condition, added to the inputs the v1 model already declares.
_BAND_INPUT = ModelInputSpec(
    name=OPEN_CIRCUIT_VOLTAGE_BAND,
    source_kind=InputSourceKind.PARAMETER,
    unit_exemplar=ctx.DIMENSIONLESS,
    description=(
        "Which declared cell-temperature band's open-circuit voltage curve "
        "this run is predicted with, as a code: 0 cold, 1 warm. A declared "
        "condition of the run, read from the chamber ambient and the nominal "
        "load before it starts."
    ),
)

ELECTROTHERMAL_1RC_V2_MODEL = ScientificModelDefinition(
    model_id=MODEL_ID,
    version=MODEL_VERSION,
    name=(
        "One-RC Thevenin cell on a measured available-charge basis, with a "
        "band-conditioned declared OCV"
    ),
    domain="battery",
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "The same equations as 0.1.0 -- "
        "V = OCV_band(z) - I R0(T) - v_p, "
        "dv_p/dt = (I R1(T) - v_p) / (R1(T) C1), "
        "dz/dt = -I / (eta Q_available), "
        "Qdot = I^2 R0(T) + I <v_p> -- with two differences that make it a "
        "different model: the charge state is a fraction of a measured "
        "available charge rather than of the manufacturer's rating, and the "
        "open-circuit voltage authority is conditioned on a declared "
        "cell-temperature band."
    ),
    inputs=v1._PARAMETERS + v1._STATE + (_BAND_INPUT,),
    outputs=v1.ELECTROTHERMAL_1RC_MODEL.outputs,
    assumptions=_ASSUMPTIONS,
    exclusions=_EXCLUSIONS,
    validity=ValidityDomain(
        conditions=v1.ELECTROTHERMAL_1RC_MODEL.validity.conditions
        + (
            RangeCondition(
                name=OPEN_CIRCUIT_VOLTAGE_BAND,
                minimum=Quantity(0.0, ctx.DIMENSIONLESS),
                maximum=Quantity(float(len(BAND_CODES) - 1), ctx.DIMENSIONLESS),
                description=(
                    "A declared band code. There is no curve between the "
                    "bands, so a run that is in neither is refused rather "
                    "than interpolated."
                ),
            ),
        )
    ),
)

ELECTROTHERMAL_1RC_V2_REALIZATION = ModelRealizationDefinition(
    realization_id=f"{MODEL_ID}.exact_constant_current",
    version=REALIZATION_VERSION,
    model=ModelReference(MODEL_ID, MODEL_VERSION),
    formulation=ModelFormulation.ODE,
    name="Exact integration of the 1-RC cell over one constant-current interval",
    description=(
        "The same closed-form update 0.1.0's realization uses, on the same "
        "kernel. The realization is re-declared rather than shared because it "
        "names the model version it discharges, and this one discharges a "
        "different charge-state identity."
    ),
    provided_capabilities=frozenset({v1.ELECTROTHERMAL_CELL_STATE}),
    required_capabilities=frozenset({v1.REQUIRED_BODY_TEMPERATURE}),
    required_solver_capabilities=(
        v1.ELECTROTHERMAL_1RC_REALIZATION.required_solver_capabilities
    ),
    assumptions=(
        "the current is constant over the integrated interval",
        "the cell temperature is held over the integrated interval",
        "exact for the declared equations; no time-discretization error",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.battery.electrothermal",
        version=REALIZATION_VERSION,
        reference="advance_electrothermal_step; see the module docstring",
    ),
)


def recovery_cell(
    *,
    cell_id: str,
    band: str,
    ohmic_resistance_reference: Quantity,
    ohmic_activation_energy: Quantity,
    polarization_resistance_reference: Quantity,
    polarization_activation_energy: Quantity,
    polarization_capacitance: Quantity,
    reference_temperature: Quantity,
    available_charge: Quantity,
    coulombic_efficiency: Quantity | None = None,
) -> et.ElectrothermalCell:
    """Build the recovery cell around the band's declared curve.

    ``band`` is a declared condition, not an argument a caller may pick freely:
    :func:`~engcore.domains.battery.flagship_ocv_v2.band_for` derives it from
    the run's ambient and nominal load. Passing a band the authority has no
    curve for is refused here rather than silently falling back to the other
    one, because a fallback would answer at a temperature nothing was measured
    at.

    ``available_charge`` is the charge-state basis, and this version's whole
    point is that it is a measurement of this cell rather than the rating. A
    caller that has no measured available charge has no basis and should not
    have a cell.
    """
    curve = OCV_V2_CURVES.get(band)
    shape = R0_V2_SHAPES.get(band)
    if curve is None or shape is None:
        raise InvalidScientificProblem(
            f"no declared open-circuit voltage curve for band {band!r}; the "
            f"declared bands are {sorted(OCV_V2_CURVES)} and there is no curve "
            "between them"
        )
    return et.ElectrothermalCell(
        cell_id=cell_id,
        nominal_capacity=available_charge,
        coulombic_efficiency=(
            Quantity(1.0, ctx.DIMENSIONLESS)
            if coulombic_efficiency is None
            else coulombic_efficiency
        ),
        ohmic_resistance=et.ArrheniusResistance(
            ohmic_resistance_reference,
            ohmic_activation_energy,
            reference_temperature,
        ),
        polarization_resistance=et.ArrheniusResistance(
            polarization_resistance_reference,
            polarization_activation_energy,
            reference_temperature,
        ),
        polarization_capacitance=polarization_capacitance,
        open_circuit_voltage_curve=curve,
        ohmic_charge_state_shape=shape,
    )


SOLVER_ID = f"{v1.SOLVER_ID}_v2"
SOLVER_VERSION = "0.2.0"


class RecoveryElectrothermalCellSolver(v1.ElectrothermalCellSolver):
    """The Sprint 3 solver, declared for the recovery model version.

    The kernel is not reimplemented and not wrapped: this class overrides the
    two declarations that name a version -- the model it serves and the
    realization it binds -- and inherits everything that does arithmetic. A
    domain pack requires an in-pack solver covering each realization's exact
    model, and that requirement is what this class exists to satisfy.

    It carries its own solver identity because a solver id is an identity: two
    solvers that serve different model versions are not interchangeable, and a
    record naming one must not resolve to the other.
    """

    served_models = (ELECTROTHERMAL_1RC_V2_MODEL,)
    realization = ELECTROTHERMAL_1RC_V2_REALIZATION

    @property
    def identity(self):
        from ...scientific.solvers.protocol import SolverIdentity

        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=v1.BACKEND)


ELECTROTHERMAL_V2_MODELS = (ELECTROTHERMAL_1RC_V2_MODEL,)
ELECTROTHERMAL_V2_REALIZATIONS = (ELECTROTHERMAL_1RC_V2_REALIZATION,)
ELECTROTHERMAL_V2_SOLVERS = (RecoveryElectrothermalCellSolver,)


__all__ = [
    "BAND_CODES",
    "ELECTROTHERMAL_V2_SOLVERS",
    "RecoveryElectrothermalCellSolver",
    "SOLVER_ID",
    "SOLVER_VERSION",
    "R0_SHAPE_MEASURED_INTERVALS",
    "R0_SHAPE_REFERENCE_Z",
    "ELECTROTHERMAL_1RC_V2_MODEL",
    "ELECTROTHERMAL_1RC_V2_REALIZATION",
    "ELECTROTHERMAL_V2_MODELS",
    "ELECTROTHERMAL_V2_REALIZATIONS",
    "MODEL_ID",
    "MODEL_VERSION",
    "OPEN_CIRCUIT_VOLTAGE_BAND",
    "REALIZATION_VERSION",
    "band_for",
    "recovery_cell",
]
