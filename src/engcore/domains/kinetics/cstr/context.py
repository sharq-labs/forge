"""Computed validity context for the non-isothermal CSTR.

Why this module exists
----------------------
``ScientificProblem.validity_context`` is built from **typed parameters**. A
dimensionless group is not a parameter: nobody declares a Damkohler number,
they declare a pre-exponential factor, an activation energy, a feed temperature
and a residence time, and the number *follows*. This module is the kinetics
domain's supplier of those derived quantities, and it is the direct analogue of
``domains/thermal_models/context.py`` and of the derivation half of
``domains/electrical/material.py``.

Nothing here is registered with, imported by, or known to
``engcore.scientific``. The core knows ranges, categories and flags; it does
not know what a Damkohler number is, and after this module it still does not.

Three rules the functions below all obey
----------------------------------------
1. **A missing input omits its key.** Every function returns ``None`` when it
   was not given what it needs, and :func:`derived_cstr_quantities` drops the
   key rather than inventing a value. A dropped key reaches
   ``ValidityDomain.assess`` as UNKNOWN, which is the honest verdict: absence
   of information is not evidence of validity. No function here has a physical
   default.
2. **Every derivation is unit-checked.** Inputs are converted through
   :class:`Quantity`, so an activation energy handed in as ``kJ/mol`` and one
   handed in as ``J/mol`` produce the same number, and a rate constant handed
   in where a residence time belongs raises instead of producing a
   plausible-looking wrong answer.
3. **Pure.** No state, no registry, no I/O, no mutation of an argument.

Why the unit table and the gas constant live here
--------------------------------------------------
``problem.py`` imports both from this module and re-exports them, so there is
exactly one definition of each. The alternative -- restating them here to avoid
a cycle -- is what :mod:`.reference` deliberately does, and for a reason that
does not apply here: that module restates the constant *so that it shares no
arithmetic with the solve path*, because it is an independent check on it. This
module is not an independent check on anything; it derives the groups the
model's own conditions are stated over, and a second copy of ``8.314462618``
here would be drift with no benefit.

Sources
-------
The Damkohler number and the segregation argument that bounds it follow
Levenspiel, O., *Chemical Reaction Engineering*, 3rd ed. (Wiley, 1999), Ch. 16
("Earliness of Mixing, Segregation and RTD"). The temperature ceiling follows
from the reactor's own exact invariant ``Z = T + beta C_A``, which
:mod:`.reference` already implements and which the module docstring of
:mod:`.problem` states.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from ....scientific.errors import InvalidScientificProblem
from ....scientific.units.quantity import Quantity
from ...derived_context import assembled_validity_context, caller_declared

__all__ = [
    "ACTIVATION_ENERGY",
    "ADIABATIC_CEILING_TEMPERATURE",
    "ASSEMBLED_QUANTITIES",
    "CONCENTRATION_UNIT",
    "COOLANT_TEMPERATURE",
    "DAMKOHLER_NUMBER",
    "DENSITY",
    "DENSITY_UNIT",
    "DIMENSIONLESS",
    "FEED_CONCENTRATION",
    "FEED_TEMPERATURE",
    "FLOW_UNIT",
    "GAS_CONSTANT_UNIT",
    "HEAT_CAPACITY",
    "HEAT_CAPACITY_UNIT",
    "HEAT_OF_REACTION",
    "INITIAL_CONCENTRATION",
    "INITIAL_TEMPERATURE",
    "K0",
    "MAX_WELL_MIXED_DAMKOHLER",
    "MOLAR_ENERGY_UNIT",
    "MOLAR_GAS_CONSTANT",
    "RATE_CONSTANT_UNIT",
    "RESIDENCE_TIME",
    "TEMPERATURE_UNIT",
    "TIME_UNIT",
    "UA_UNIT",
    "VOLUME_UNIT",
    "adiabatic_ceiling_temperature",
    "cstr_validity_context",
    "damkohler_number",
    "derived_cstr_quantities",
]

# =====================================================================
# Units -- every one of these is a real physical dimension
# =====================================================================
# Declared here rather than in ``problem.py`` so that this module, the lower
# layer, does not have to import the upper one. ``problem.py`` imports and
# re-exports every name below, so the table still has exactly one home.

CONCENTRATION_UNIT = "mol/m**3"
TEMPERATURE_UNIT = "kelvin"
TIME_UNIT = "second"
VOLUME_UNIT = "m**3"
FLOW_UNIT = "m**3/s"
RATE_CONSTANT_UNIT = "1/s"
MOLAR_ENERGY_UNIT = "J/mol"
DENSITY_UNIT = "kg/m**3"
HEAT_CAPACITY_UNIT = "J/(kg*K)"
UA_UNIT = "W/K"
GAS_CONSTANT_UNIT = "J/(mol*K)"
DIMENSIONLESS = "dimensionless"

#: CODATA / SI-exact molar gas constant. Declared as a Quantity because it
#: enters the Arrhenius exponent and must be dimensionally checkable like every
#: other input. It is a defining constant of the SI and carries no uncertainty.
MOLAR_GAS_CONSTANT = Quantity(8.314462618, GAS_CONSTANT_UNIT)

# =====================================================================
# Names of the declarations this module reads
# =====================================================================
# The key each declared value occupies in a validity context.
# ``INITIAL_TEMPERATURE`` and ``INITIAL_CONCENTRATION`` are the plain names
# ``temperature`` and ``concentration`` because the model's two oldest
# conditions are named that and are assessed at the initial state; see
# ``ReactorRun.validity_context``.

K0 = "k0"
ACTIVATION_ENERGY = "activation_energy"
HEAT_OF_REACTION = "heat_of_reaction"
DENSITY = "density"
HEAT_CAPACITY = "heat_capacity"
FEED_CONCENTRATION = "feed_concentration"
FEED_TEMPERATURE = "feed_temperature"
COOLANT_TEMPERATURE = "coolant_temperature"
RESIDENCE_TIME = "residence_time"
INITIAL_TEMPERATURE = "temperature"
INITIAL_CONCENTRATION = "concentration"

# --- names of the quantities this module derives ------------------------------
DAMKOHLER_NUMBER = "damkohler_number"
ADIABATIC_CEILING_TEMPERATURE = "adiabatic_ceiling_temperature"


# =====================================================================
# Envelope bounds -- DOMAIN-OWNED, declared here and nowhere else
# =====================================================================

#: Da <= 10, and **the 10 is a convention**, recorded as one.
#:
#: **What is established, and by whom.** The direction is. This model's first
#: declared assumption is a perfectly mixed tank with no spatial gradient in
#: concentration or temperature. A tank is called stirred because it
#: homogenizes in a blend time ``t_m`` short compared with its residence time
#: ``tau``; the perfect-mixing idealization additionally requires that it
#: homogenizes at least as fast as the reaction changes the local state,
#: ``t_m <= 1/k``. Combining the two gives ``Da = k tau <= tau / t_m``, so the
#: admissible Damkohler number is bounded above by the tank's own mixing
#: quality and by nothing else. Levenspiel, O., *Chemical Reaction
#: Engineering*, 3rd ed. (Wiley, 1999), Ch. 16 ("Earliness of Mixing,
#: Segregation and RTD") is the standard treatment of what happens past that
#: point: the fluid reacts in partially segregated parcels rather than at one
#: composition, and the tank has a residence-time distribution but not a single
#: state for these balances to be written over.
#:
#: **What is not established: the number.** ``tau / t_m`` is not declared
#: anywhere in this model. There is no impeller, no power input and no blend
#: time in the declaration, so the ceiling has to be set by an assumed mixing
#: quality. **10 is the conventional well-stirred design reading** -- a blend
#: time of a tenth of the residence time -- read together with the weakest form
#: of the mixing requirement, ``t_m <= 1/k`` rather than ``t_m << 1/k``. No
#: source prints 10 as a threshold for this quantity, and it is recorded here
#: as a convention rather than dressed as a citation. It is deliberately the
#: permissive reading of a chain that has a convention in it: a bound that
#: refused the standard worked example of this very reactor would be a
#: statement about the convention rather than about the tank.
#:
#: **What this condition claims, and what it does not.** It claims the
#: declaration is one a perfectly mixed tank can describe. It does *not* claim
#: that a faster reaction makes the answer wrong; OUTSIDE_VALIDATED_DOMAIN
#: means outside the domain we have validated, not wrong.
#:
#: **The caveat that decides which field this is about.** For the concentration
#: field alone this bound would be unfounded: the rate is first order in
#: ``C_A``, hence linear in it, and the classical result is that the degree of
#: segregation does not change the conversion of a first-order reaction
#: (Levenspiel, Ch. 16). The bound is about the **temperature** field.
#: ``k(T) = k0 exp(-E/(R T))`` is convex in ``T``, so a tank with any spread in
#: temperature reacts faster on average than a tank at the mean temperature,
#: and the discrepancy grows with ``E/(R T)`` -- the same exponential the energy
#: balance feeds back into. The one temperature this model asserts is not a
#: harmless average, and Da is the measure of how hard the reaction is driving
#: the tank away from having one.
MAX_WELL_MIXED_DAMKOHLER = Quantity(10.0, DIMENSIONLESS)


def _as_quantity(value: Any, unit: str, label: str) -> Quantity | None:
    """A supplied value, checked against ``unit``; ``None`` stays ``None``.

    A non-``Quantity`` that is not ``None`` is a specification error rather
    than missing data, and is refused instead of being silently skipped: the
    two cases must not collapse, because one means UNKNOWN and the other means
    the caller declared something wrong.
    """
    if value is None:
        return None
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} -- a bare number is not a declaration"
        )
    value.require_compatible(unit, context=label)
    return value


def _positive(value: Quantity | None, unit: str, label: str) -> Quantity | None:
    """``value`` when it is strictly positive; refuses zero and negatives.

    Every quantity this module divides by is a residence time, an absolute
    temperature, a density or a heat capacity. Zero is not a small value
    there -- it is a different physical situation, or none at all -- and
    dividing by it would report infinity as though it were a measurement.
    """
    if value is None:
        return None
    if value.magnitude_in(unit) <= 0.0:
        raise InvalidScientificProblem(
            f"{label} must be strictly positive, got {value}"
        )
    return value


# =====================================================================
# The derived groups
# =====================================================================

def damkohler_number(
    *,
    k0: Quantity | None,
    activation_energy: Quantity | None,
    feed_temperature: Quantity | None,
    residence_time: Quantity | None,
) -> Quantity | None:
    """Da = k(T_f) tau -- reaction rate against the rate the tank turns over.

    **Definition.** ``Da = k(T_f) / (q/V) = k(T_f) tau`` with
    ``k(T) = k0 exp(-E/(R T))``: the ratio of the residence time to the
    reaction time ``1/k``, or equivalently how many reaction times a parcel of
    fluid spends in the tank. Evaluated at the **feed** temperature because it
    is then a property of the *declaration*, decidable before any integration,
    and because the tank temperature is what the solve produces.

    **What it bounds.** See :data:`MAX_WELL_MIXED_DAMKOHLER`: the perfect
    mixing this model asserts requires the tank to homogenize at least as fast
    as the reaction changes the local state, and Da is the only measure of that
    available from the declaration.

    **The bound is one-sided, and that is a claim.** There is no minimum. As
    ``Da -> 0`` the tank becomes a mixing vessel: conversion falls to zero, the
    species balance relaxes to the feed on the residence time, and the
    equations this model integrates are still exactly the equations that
    describe it. That limit is not merely applicable -- it is where the model is
    easiest to verify, and this repository's own
    ``test_a_reactor_that_cannot_react_still_solves_and_conserves`` runs at
    ``Da ~ 1e-30`` and checks the trajectory against an elementary exponential.
    A lower bound would call that run inapplicable, and it is not.

    **Nor is it a band to exclude.** ``Da`` of order unity is where steady-state
    multiplicity, ignition and extinction live, and that behaviour is what this
    model is *for* -- the Aris & Amundson and Uppal, Ray & Poore references in
    the model record are about nothing else. "Order unity is where the
    interesting behaviour is" is a statement about where to look, not about
    where the equations stop describing the tank, and converting it into a
    validity bound would exclude the model's own subject matter.

    Returns ``None`` if any of the four is absent.
    """
    checked_k0 = _positive(
        _as_quantity(k0, RATE_CONSTANT_UNIT, K0), RATE_CONSTANT_UNIT, K0
    )
    energy = _as_quantity(
        activation_energy, MOLAR_ENERGY_UNIT, ACTIVATION_ENERGY
    )
    temperature = _positive(
        _as_quantity(feed_temperature, TEMPERATURE_UNIT, FEED_TEMPERATURE),
        TEMPERATURE_UNIT,
        FEED_TEMPERATURE,
    )
    tau = _positive(
        _as_quantity(residence_time, TIME_UNIT, RESIDENCE_TIME),
        TIME_UNIT,
        RESIDENCE_TIME,
    )
    if (
        checked_k0 is None
        or energy is None
        or temperature is None
        or tau is None
    ):
        return None
    # E/(R T) is dimensionless by construction, and is formed as a Quantity so
    # that an activation energy carrying the wrong dimension is caught here
    # rather than by producing an exponent that happens to be a float.
    exponent = (
        energy / (MOLAR_GAS_CONSTANT * temperature)
    ).magnitude_in(DIMENSIONLESS)
    rate = checked_k0 * math.exp(-exponent)
    return (rate * tau).to(DIMENSIONLESS)


def adiabatic_ceiling_temperature(
    *,
    heat_of_reaction: Quantity | None,
    density: Quantity | None,
    heat_capacity: Quantity | None,
    feed_concentration: Quantity | None,
    initial_concentration: Quantity | None,
    feed_temperature: Quantity | None,
    initial_temperature: Quantity | None,
    coolant_temperature: Quantity | None,
) -> Quantity | None:
    """The hottest temperature this declaration can reach, whatever it does.

    **Definition.**
    ``T_ceiling = max(T_0, T_f, T_c) + beta max(C_A0, C_Af)`` with
    ``beta = (-dH)/(rho cp)``, the adiabatic temperature rise per unit
    concentration. The second term is the domain's own ``adiabatic_rise_k``
    evaluated at the richer of the two declared concentrations.

    **Why it is an upper bound and not an estimate.** The reactor has an exact
    invariant, ``Z = T + beta C_A``, which :mod:`.reference` implements and the
    :mod:`.problem` docstring states::

        dZ/dt = a (Z_f - Z) - gamma (T - T_c),   a = q/V,  Z_f = T_f + beta C_Af

    With ``gamma = 0`` this integrates exactly and ``Z`` stays between ``Z_0``
    and ``Z_f``; since ``C_A >= 0`` and ``beta > 0`` for an exothermic
    reaction, ``T = Z - beta C_A <= Z``, so ``T <= max(Z_0, Z_f)``. With cooling
    the jacket term can only add heat while ``T < T_c``, and bounding it by
    ``gamma (T_c + beta C_max - Z)`` gives ``dZ/dt <= (a + gamma)(U - Z)`` with
    ``U = max(Z_f, T_c + beta C_max)``, hence
    ``T <= Z <= max(Z_0, Z_f, T_c + beta C_max)``. Each of those three is at
    most ``max(T_0, T_f, T_c) + beta C_max``, which is the value returned.
    ``C_A <= C_max = max(C_A0, C_Af)`` comes from the species balance directly,
    since ``dC/dt <= a (C_Af - C)``.

    **What it is for.** The model declares a 250-1000 K single-phase
    constant-property envelope, and the ``temperature`` condition asks whether
    the *declared initial state* sits inside it. This asks whether any state the
    declaration can reach does. It is the same question the electrical material
    model's ``ceiling_reduced_debye_temperature`` asks -- a condition evaluated
    at the extreme the declaration permits, decidable before a solver runs --
    and it introduces no new threshold: the bound is the envelope ceiling the
    model already declares, reused unchanged.

    **Conservative, and deliberately so.** A strongly cooled reactor will not
    approach this ceiling, and this condition will still report it as
    reachable. That is the honest reading of a bound derived without solving:
    the domain does not certify that the cooling holds, and
    OUTSIDE_VALIDATED_DOMAIN means outside the domain we have validated, not
    wrong. Where the trajectory actually went is what the post-solve
    state-admissibility check reports.

    **An endothermic reaction returns the feed-side maximum, and that is
    right.** ``beta <= 0`` there, the reaction can only cool the tank, and the
    hottest state available is whichever of the three declared temperatures is
    highest. The ``beta C_max`` term is clamped at zero rather than allowed to
    lower the ceiling below a temperature the tank is actually fed at.

    Returns ``None`` if any of the eight is absent.
    """
    enthalpy = _as_quantity(
        heat_of_reaction, MOLAR_ENERGY_UNIT, HEAT_OF_REACTION
    )
    rho = _positive(
        _as_quantity(density, DENSITY_UNIT, DENSITY), DENSITY_UNIT, DENSITY
    )
    cp = _positive(
        _as_quantity(heat_capacity, HEAT_CAPACITY_UNIT, HEAT_CAPACITY),
        HEAT_CAPACITY_UNIT,
        HEAT_CAPACITY,
    )
    concentrations = [
        _as_quantity(feed_concentration, CONCENTRATION_UNIT, FEED_CONCENTRATION),
        _as_quantity(
            initial_concentration, CONCENTRATION_UNIT, INITIAL_CONCENTRATION
        ),
    ]
    temperatures = [
        _positive(_as_quantity(value, TEMPERATURE_UNIT, label),
                  TEMPERATURE_UNIT, label)
        for value, label in (
            (feed_temperature, FEED_TEMPERATURE),
            (initial_temperature, INITIAL_TEMPERATURE),
            (coolant_temperature, COOLANT_TEMPERATURE),
        )
    ]
    if enthalpy is None or rho is None or cp is None:
        return None
    if any(value is None for value in concentrations + temperatures):
        return None

    # No unary minus on a Quantity: the sign is carried into the
    # magnitude, and (-dH) is the exothermic convention.
    beta = (enthalpy * -1.0) / (rho * cp)              # K m**3 / mol
    richest = max(
        value.magnitude_in(CONCENTRATION_UNIT) for value in concentrations
    )
    rise = (beta * Quantity(richest, CONCENTRATION_UNIT)).magnitude_in(
        TEMPERATURE_UNIT
    )
    hottest = max(
        value.magnitude_in(TEMPERATURE_UNIT) for value in temperatures
    )
    return Quantity(hottest + max(rise, 0.0), TEMPERATURE_UNIT)


# =====================================================================
# Assembly
# =====================================================================

#: Every name this module assembles, and which a caller parameter may therefore
#: never occupy. See ``engcore.domains.derived_context`` for what reserving a
#: name means and why it is enforced at assembly rather than at problem
#: construction.
ASSEMBLED_QUANTITIES = frozenset(
    {DAMKOHLER_NUMBER, ADIABATIC_CEILING_TEMPERATURE}
)


def derived_cstr_quantities(base: Mapping[str, Any]) -> dict[str, Quantity]:
    """Every group derivable from a reactor's declared quantities.

    ``base`` is the declaration expressed as a mapping of names to Quantities:
    the chemistry, the operation and the initial state. No state coordinate has
    to be handed in separately, because both groups here are decidable from the
    declaration alone -- which is what makes them assessable before a solver
    runs.

    **A key that could not be derived is absent from the result.** It is never
    present with a placeholder, a zero or a typical value, so a condition that
    depends on it reaches ``ValidityDomain.assess`` as UNKNOWN. There is no
    path through this function by which omitting an input yields IN_DOMAIN.
    """
    derived: dict[str, Quantity | None] = {
        DAMKOHLER_NUMBER: damkohler_number(
            k0=base.get(K0),
            activation_energy=base.get(ACTIVATION_ENERGY),
            feed_temperature=base.get(FEED_TEMPERATURE),
            residence_time=base.get(RESIDENCE_TIME),
        ),
        ADIABATIC_CEILING_TEMPERATURE: adiabatic_ceiling_temperature(
            heat_of_reaction=base.get(HEAT_OF_REACTION),
            density=base.get(DENSITY),
            heat_capacity=base.get(HEAT_CAPACITY),
            feed_concentration=base.get(FEED_CONCENTRATION),
            initial_concentration=base.get(INITIAL_CONCENTRATION),
            feed_temperature=base.get(FEED_TEMPERATURE),
            initial_temperature=base.get(INITIAL_TEMPERATURE),
            coolant_temperature=base.get(COOLANT_TEMPERATURE),
        ),
    }
    return {name: value for name, value in derived.items() if value is not None}


def cstr_validity_context(declared: Mapping[str, Any]) -> dict[str, Any]:
    """The context ``CSTR_MODEL`` is assessed against, in two namespaces.

    ``declared`` is what the caller stated. Every reserved name is stripped
    from it before anything is derived, so a group that could not be derived is
    **absent** rather than caller-supplied, and the condition that reads it
    reaches ``assess`` as UNKNOWN. A caller cannot assert a Damkohler number.
    """
    stripped = caller_declared(declared, ASSEMBLED_QUANTITIES)
    return assembled_validity_context(
        declared=stripped,
        assembled=derived_cstr_quantities(stripped),
        reserved=ASSEMBLED_QUANTITIES,
    )
