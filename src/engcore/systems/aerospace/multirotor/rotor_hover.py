"""Ideal actuator-disk hover relations used by the multirotor reference study.

This module is intentionally small and explicit. It provides a reference
momentum-theory relation for steady hover. It is not a blade-element model,
CFD model, rotor-interference model, or physical certification boundary.
"""

from __future__ import annotations

import math

from ....scientific.errors import InvalidScientificProblem
from ....scientific.units.quantity import Quantity


def _positive(value: Quantity, unit: str, *, name: str) -> float:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(f"{name} must be Quantity")
    magnitude = value.magnitude_in(unit)
    if not magnitude > 0.0:
        raise InvalidScientificProblem(f"{name} must be > 0 {unit}")
    return magnitude


def ideal_induced_hover_power(
    *,
    thrust: Quantity,
    disk_area: Quantity,
    air_density: Quantity,
) -> Quantity:
    """Ideal induced power for a uniform actuator disk in steady hover.

    ``P_i = T^(3/2) / sqrt(2 rho A)``

    Inputs are converted through the Scientific Core unit contract before the
    numeric kernel is evaluated. The returned quantity is watts.
    """

    thrust_n = _positive(thrust, "N", name="thrust")
    area_m2 = _positive(disk_area, "m^2", name="disk_area")
    density = _positive(air_density, "kg/m^3", name="air_density")

    power_w = thrust_n**1.5 / math.sqrt(2.0 * density * area_m2)
    return Quantity(power_w, "W")


def disk_loading(*, thrust: Quantity, disk_area: Quantity) -> Quantity:
    """Reference total thrust divided by total actuator-disk area."""

    thrust_n = _positive(thrust, "N", name="thrust")
    area_m2 = _positive(disk_area, "m^2", name="disk_area")
    return Quantity(thrust_n / area_m2, "N/m^2")
