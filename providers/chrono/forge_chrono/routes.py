"""The Chrono adapter's declared reference route: a simple pendulum against its analytic period.

The route builds its OWN model (a point-mass bob on a massless revolute
link, 1 m, released at 5 deg) -- no product input enters it.  Its record is
a check of this adapter's translation on one Chrono build, never validation
of a product model, and never a qualification by itself.
"""

from __future__ import annotations

import math

from engcore.providers import ProviderStatus
from engcore.providers.qualification import ReferenceRoute, RouteRun, record_route_run
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.spatial.geometry import Transform
from engcore.systems.assembly import AssemblyTopology, ConnectionPoint, InstanceLevel, JointDeclaration, JointKind, Placement
from engcore.systems.multibody import GravityDeclaration, MassProperties, MultibodyModel, MultibodyRequest
from engcore.systems.topology import ComponentDefinition, ComponentInstance, SystemDefinition

from . import ADAPTER_ID, ADAPTER_VERSION, ChronoProvider, reference_pendulum_period

PENDULUM_SCOPE = ("passive_revolute_joint_under_gravity",)


def _m(v: float) -> Quantity:
    return Quantity(v, "m")


def pendulum_model(length: float = 1.0, mass: float = 2.0, amplitude_deg: float = 5.0) -> MultibodyModel:
    """A point-mass pendulum hinged at the origin about +y, released at ``amplitude_deg`` (route fixture, declared here)."""
    a = math.radians(amplitude_deg)
    sx, cz = length * math.sin(a), length * math.cos(a)
    sysdef = SystemDefinition("pendulum", "1", (ComponentDefinition("frame", "1"), ComponentDefinition("bob", "1"), ComponentDefinition("rig", "1")), (
        ComponentInstance("rig", "rig", "1", TwinReference("rig", "1")),
        ComponentInstance("frame", "frame", "1", TwinReference("frame", "1"), parent_id="rig"),
        ComponentInstance("bob", "bob", "1", TwinReference("bob", "1"), parent_id="rig")))
    asm = AssemblyTopology(
        sysdef, (InstanceLevel("rig", "system"), InstanceLevel("frame", "component"), InstanceLevel("bob", "component")),
        placements=(Placement("frame", Transform()), Placement("bob", Transform.from_quantities((_m(sx), _m(0), _m(-cz))))),
        points=(ConnectionPoint("frame.pivot", "frame"), ConnectionPoint("bob.pivot", "bob", Transform.from_quantities((_m(-sx), _m(0), _m(cz))))),
        joints=(JointDeclaration("hinge", JointKind.REVOLUTE, "frame.pivot", "bob.pivot", axis=(0, 1, 0)),))
    zero, small = Quantity(0, "kg*m^2"), Quantity(1e-6, "kg*m^2")
    mp = MassProperties("bob", Quantity(mass, "kg"), (_m(0), _m(0), _m(0)), ((small, zero, zero), (zero, small, zero), (zero, zero, small)),
                        "route:point-mass-bob", ("bob", "1"))
    g = GravityDeclaration((Quantity(0, "m/s^2"), Quantity(0, "m/s^2"), Quantity(-9.81, "m/s^2")), "route:declared-gravity-9.81")
    return MultibodyModel(asm, "frame", (mp,), g)


def pendulum_request(timestepper: str, solver: str = "sparse_qr", length: float = 1.0) -> MultibodyRequest:
    return MultibodyRequest(pendulum_model(length=length), Quantity(2.0, "s"), Quantity(1, "ms"),
                            ("body:bob.position_x", "body:bob.position_z"), {"timestepper": timestepper, "solver": solver})


def pendulum_route(timestepper: str) -> ReferenceRoute:
    """Period from the mean zero-crossing interval of the bob's x position over 2 s, to 1e-3 relative.
    1e-3 is the crossing resolution (one 1 ms step in about 1 s), not a model accuracy."""
    reference = reference_pendulum_period(_m(1.0), Quantity(9.81, "m/s^2"), Quantity(5.0, "degree"))
    return ReferenceRoute(
        f"chrono.pendulum_period.{timestepper}", "chrono", (ADAPTER_ID, ADAPTER_VERSION), PENDULUM_SCOPE,
        "pendulum period (mean zero-crossing interval of bob x, doubled)", reference,
        "analytic: 2*pi*sqrt(L/g) * (1 + a^2/16 + 11 a^4/3072), L = 1 m, g = 9.81 m/s^2, a = 5 deg", 1e-3,
        {"request": pendulum_request(timestepper).to_dict()})


def measured_period(record) -> Quantity | None:
    """The route observable from an execution record; None when the bob never crossed twice (no period to measure)."""
    if not record.succeeded:
        return None
    s = record.series_for("body:bob.position_x")
    t, x = s.times_s, s.values
    crossings = [t[i + 1] for i in range(len(x) - 1) if (x[i] > 0) != (x[i + 1] > 0)]
    if len(crossings) < 2:
        return None
    gaps = [b - a for a, b in zip(crossings, crossings[1:])]
    return Quantity(2 * sum(gaps) / len(gaps), "s")


def run_pendulum_route(status: ProviderStatus, timestepper: str) -> RouteRun:
    """Execute the route on the discovered Chrono build and record the run (PASSED / FAILED / PROVIDER_FAILED)."""
    route = pendulum_route(timestepper)
    record = ChronoProvider(status).execute(pendulum_request(timestepper))
    return record_route_run(route, status, record, measured_period(record))


__all__ = ["PENDULUM_SCOPE", "measured_period", "pendulum_model", "pendulum_request", "pendulum_route", "run_pendulum_route"]
