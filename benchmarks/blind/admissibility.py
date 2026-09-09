"""What the boundary refuses to BUILD, before it assesses anything.

Transcribed from the domain constructors' own guards, the same way
:mod:`bound_registry` is transcribed from the bound register: as data, here,
because this module is part of the truth layer and may not reach into
``engcore``.

Why this exists as its own layer
--------------------------------

A declared validity condition and a construction guard are two different
things, and confusing them produces a truth that is confidently wrong.

``surface_emissivity`` is the case that forced this module to be written. It is
not a validity condition at all — no model declares a bound on it — but
``LumpedApplicabilityDeclaration`` refuses a value outside ``[0, 1]`` when the
body is *built*, because an emissivity is a fraction of the black-body emissive
power and a value outside that interval is not an extreme case, it is not an
emissivity. A first cut of this challenge's generator solved the radiation
ratio through the emissivity and produced values up to 5.8, and **118 of 207
electro-thermal cases would have been refused at the boundary while their
frozen truth said SUPPORTED**. Every one of those would have scored as a Forge
mismatch and measured nothing but the generator.

The same shape appears three more times, and each is a finding worth reporting
rather than a nuisance:

* the CSTR refuses all three declared temperatures outside ``[250, 1000] K`` at
  construction, so its ``temperature`` condition **can never be violated**
  through the ordinary path;
* ``Cell`` refuses ``coulombic_efficiency > 1`` at construction, so ``B-ETA``,
  the one HARD battery bound, is likewise unreachable as a violation;
* ``ConductionSlab`` refuses a non-positive diffusivity, so the ``alpha > 0``
  condition is unreachable too.

A declared condition that no admissible input can violate is a real property of
the current core. It is not a defect — refusing earlier is refusing better —
but a benchmark that did not know about it would report every such case as a
wrong verdict.

Sources, per system, are named on each function.
"""

from __future__ import annotations

import math
from typing import Any

from .oracles.units import UnknownUnitError, parse, to_si

__all__ = [
    "ADMISSIBILITY_VERSION",
    "electrothermal_refusal",
    "battery_refusal",
    "conduction_refusal",
]

ADMISSIBILITY_VERSION = "blind-admissibility/1.0.0"

#: Units whose zero is conventional. A temperature SPAN declared in one of
#: these is a state, not a difference, and `_require_span_scale` refuses it.
_AFFINE_UNITS = frozenset({"degC", "degF"})


def _q(section: Any, key: str, dimension: str) -> float | None:
    raw = None if not isinstance(section, dict) else section.get(key)
    if raw is None:
        return None
    return to_si(raw, dimension)


def _positive(value: float | None, label: str) -> str | None:
    if value is None:
        return None
    if not math.isfinite(value) or value <= 0.0:
        return f"{label}_not_positive"
    return None


def electrothermal_refusal(payload: dict) -> str | None:
    """Why ``build_electrothermal_system`` would refuse this payload.

    Transcribed from ``engcore/mcp/problem.py`` (payload shape),
    ``domains/thermal_models/context.py::LumpedApplicabilityDeclaration``,
    ``domains/thermal_models/lumped.py::ThermalBody`` and
    ``domains/electrical/material.py`` (conductor and limits).
    """
    if not isinstance(payload, dict):
        return "payload_not_a_mapping"
    stages = payload.get("stages")
    if stages is None:
        return "stages_missing"
    if not isinstance(stages, list):
        return "stages_not_a_list"
    if not stages:
        return "stages_empty"
    try:
        if _positive(to_si(payload["source_voltage"], "V"), "source_voltage"):
            # A source of zero volts is a legal circuit; only the PARSE is
            # checked here, and the parse is what the try/except catches.
            pass
    except (KeyError, UnknownUnitError, TypeError):
        return "source_voltage_unreadable"

    for stage in stages:
        if not isinstance(stage, dict):
            return "stage_not_a_mapping"
        conductor = stage.get("conductor")
        body = stage.get("body")
        if not isinstance(conductor, dict) or not isinstance(body, dict):
            return "stage_missing_conductor_or_body"
        try:
            for section, key, dimension, label in (
                (conductor, "reference_resistance", "ohm", "reference_resistance"),
                (conductor, "reference_temperature", "K", "reference_temperature"),
                (body, "heat_capacity", "J/K", "heat_capacity"),
                (body, "ambient_conductance", "W/K", "ambient_conductance"),
                (body, "duration", "s", "duration"),
                (body, "ambient_temperature", "K", "ambient_temperature"),
                (body, "initial_temperature", "K", "initial_temperature"),
            ):
                if key not in section:
                    return f"{label}_missing"
                value = to_si(section[key], dimension)
                if label == "reference_temperature":
                    if not math.isfinite(value):
                        return "reference_temperature_not_finite"
                    continue
                failure = _positive(value, label)
                if failure:
                    return failure

            limits = conductor.get("limits") or {}
            for key, dimension in (("linearization_band", "K"),
                                   ("maximum_operating_temperature", "K"),
                                   ("debye_temperature", "K")):
                failure = _positive(_q(limits, key, dimension), key)
                if failure:
                    return failure

            ratings = conductor.get("ratings") or {}
            for key, dimension in (("rated_power", "W"),
                                   ("maximum_working_voltage", "V")):
                failure = _positive(_q(ratings, key, dimension), key)
                if failure:
                    return failure

            app = body.get("applicability") or {}
            for key, dimension in (
                ("characteristic_length", "m"), ("body_volume", "m3"),
                ("surface_area", "m2"), ("body_conductivity", "W/m/K"),
                ("conductance_excursion_bound", "K"),
                ("capacity_excursion_bound", "K"),
                ("melting_temperature", "K"), ("fluid_conductivity", "W/m/K"),
                ("fluid_kinematic_viscosity", "m2/s"),
                ("fluid_prandtl_number", "1"),
                ("fluid_expansion_coefficient", "1/K"),
                ("fluid_velocity", "m/s"), ("convection_length", "m"),
            ):
                failure = _positive(_q(app, key, dimension), key)
                if failure:
                    return failure

            # A fraction of the black-body emissive power. Outside [0, 1] it is
            # not an emissivity, and the declaration says so at construction.
            emissivity = _q(app, "surface_emissivity", "1")
            if emissivity is not None and not 0.0 <= emissivity <= 1.0:
                return "surface_emissivity_outside_unit_interval"

            # An excursion BOUND is a span. Declared on an affine scale its
            # zero is conventional, so a difference expressed in it is not a
            # value of that unit.
            for key in ("conductance_excursion_bound",
                        "capacity_excursion_bound"):
                raw = app.get(key)
                if isinstance(raw, str):
                    unit = raw.strip().partition(" ")[2].strip()
                    if unit in _AFFINE_UNITS:
                        return f"{key}_on_an_affine_scale"

            # Free convection or forced convection, not both: that is mixed
            # convection and neither declared correlation covers it.
            if (app.get("fluid_expansion_coefficient") is not None
                    and app.get("fluid_velocity") is not None):
                return "both_convection_routes_declared"
        except UnknownUnitError:
            return "unreadable_quantity"
        except (TypeError, KeyError):
            return "malformed_stage"

    try:
        source_ratings = payload.get("source_ratings") or {}
        failure = _positive(_q(source_ratings, "maximum_current", "A"),
                            "maximum_current")
        if failure:
            return failure
    except UnknownUnitError:
        return "unreadable_quantity"
    return None


def battery_refusal(payload: dict) -> str | None:
    """Why ``build_battery_case`` would refuse this payload.

    Transcribed from ``domains/battery/cell.py`` — ``Cell.__post_init__`` and
    ``Load.__post_init__``.
    """
    if not isinstance(payload, dict):
        return "payload_not_a_mapping"
    cell = payload.get("cell")
    load = payload.get("load")
    if not isinstance(cell, dict) or not isinstance(load, dict):
        return "cell_or_load_missing"
    try:
        for section, key, dimension, label in (
            (cell, "nominal_capacity", "Ah", "nominal_capacity"),
            (cell, "internal_resistance", "ohm", "internal_resistance"),
            (load, "discharge_current", "A", "discharge_current"),
            (load, "duration", "s", "duration"),
        ):
            if key not in section:
                return f"{label}_missing"
            failure = _positive(to_si(section[key], dimension), label)
            if failure:
                return failure

        efficiency = _q(cell, "coulombic_efficiency", "1")
        if efficiency is None:
            return "coulombic_efficiency_missing"
        # (0, 1]. Above 1 credits the cell with more charge than crossed its
        # terminals -- not an optimistic number, a violated charge balance.
        if not 0.0 < efficiency <= 1.0:
            return "coulombic_efficiency_outside_unit_interval"

        full = _q(cell, "open_circuit_voltage_at_full", "V")
        empty = _q(cell, "open_circuit_voltage_at_empty", "V")
        if full is None or empty is None:
            return "open_circuit_voltage_endpoints_missing"
        # A flat or falling chord makes the voltage-to-charge relation
        # non-invertible, so a cutoff voltage would name no state of charge.
        if not full > empty:
            return "open_circuit_voltage_chord_not_rising"

        for key in ("state_of_charge", "cutoff_state_of_charge"):
            fraction = _q(load, key, "1")
            if fraction is not None and not 0.0 <= fraction <= 1.0:
                return f"{key}_outside_unit_interval"

        limits = cell.get("limits") or {}
        for key, dimension in (
            ("continuous_discharge_c_rate", "1/s"),
            ("pulse_discharge_c_rate", "1/s"),
            ("rated_pulse_duration", "s"),
            ("resistance_temperature_span", "K"),
            ("capacity_temperature_span", "K"),
            ("peukert_temperature_span", "K"),
            ("cell_thermal_conductance", "W/K"),
            ("self_heating_rise_bound", "K"),
            ("polarization_time_constant", "s"),
            ("soc_step_resolution", "1"),
            ("peukert_reference_current", "A"),
            ("peukert_fit_decades", "1"),
            ("minimum_discharge_temperature", "K"),
            ("maximum_discharge_temperature", "K"),
            ("capacity_reference_temperature", "K"),
            ("resistance_reference_temperature", "K"),
            ("peukert_reference_temperature", "K"),
        ):
            failure = _positive(_q(limits, key, dimension), key)
            if failure:
                return failure
        for key in ("usable_soc_minimum", "usable_soc_maximum"):
            fraction = _q(limits, key, "1")
            if fraction is not None and not 0.0 <= fraction <= 1.0:
                return f"{key}_outside_unit_interval"

        thermal = payload.get("thermal") or {}
        for key, dimension, label in (("heat_capacity", "J/K", "heat_capacity"),
                                      ("ambient_temperature", "K",
                                       "ambient_temperature")):
            failure = _positive(_q(thermal, key, dimension),
                                f"thermal_{label}")
            if failure:
                return failure
    except UnknownUnitError:
        return "unreadable_quantity"
    except (TypeError, KeyError):
        return "malformed_payload"
    return None


def conduction_refusal(payload: dict) -> str | None:
    """Why ``ConductionSlab`` / ``SlabDiscretization`` would refuse this slab.

    Transcribed from ``domains/thermal/conduction1d/problem.py``. ``n_cells``
    must be EVEN because the midpoint QoI is read as a nodal value.
    """
    try:
        for key, dimension, label in (("length", "m", "length"),
                                      ("diffusivity", "m2/s", "diffusivity"),
                                      ("end_time", "s", "end_time")):
            if key not in payload:
                return f"{label}_missing"
            failure = _positive(to_si(payload[key], dimension), label)
            if failure:
                return failure
    except UnknownUnitError:
        return "unreadable_quantity"
    n_cells = payload.get("n_cells")
    n_steps = payload.get("n_steps")
    for label, raw in (("n_cells", n_cells), ("n_steps", n_steps)):
        if isinstance(raw, bool) or not isinstance(raw, int):
            return f"{label}_not_an_int"
    if n_cells < 2:
        return "n_cells_below_two"
    if n_cells % 2 != 0:
        return "n_cells_not_even"
    if n_steps < 1:
        return "n_steps_below_one"
    return None
