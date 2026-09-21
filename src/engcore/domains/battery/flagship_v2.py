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

Adding parameters was tried and rejected. A second RC branch, and a
charge-state axis on the ohmic resistance taken from the measured branch
difference, were both fitted on calibration cells and judged on validation
cells; neither earned its place. The measured rest relaxation is the reason the
second branch was refused and not merely unhelpful: two exponentials fit every
calibration tail better than one, but the slower time constant scatters wider
than its own median across trajectories, so it is a free parameter absorbing
residuals rather than a second physical process.

What is different, and why it is a new version
-----------------------------------------------
**The charge-state identity.** ``@0.1.0`` declares that "the basis is a
constant, not a fitted capacity", and lists "any dependence of the usable
capacity on temperature or rate" among its exclusions. That constant is the
manufacturer's 2 Ah rating, which is about 30 % above what these cells deliver
and wrong by a different amount for each of them. This version's basis is a
**measured available charge**, established per run by
:mod:`engcore.domains.battery.capacity` from cycles that completed before the
run, and its charge state is a fraction of that. The basis still arrives as an
external input; what changed is what the model declares that input to mean, and
a model whose state variable means something else is a different model.

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
constant, and no charge-state axis on either resistance. Its parameters are
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
    OCV_V2_CURVES,
    band_for,
)

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
    "any charge-state axis on either resistance. The measured branch "
    "difference does have one; carrying it as a shape did not improve "
    "independent validation and is not promoted",
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
    if curve is None:
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
    )


ELECTROTHERMAL_V2_MODELS = (ELECTROTHERMAL_1RC_V2_MODEL,)
ELECTROTHERMAL_V2_REALIZATIONS = (ELECTROTHERMAL_1RC_V2_REALIZATION,)


__all__ = [
    "BAND_CODES",
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
