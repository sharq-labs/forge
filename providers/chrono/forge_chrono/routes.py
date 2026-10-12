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

#: one scope per translated integrator + solver: a route speaks only for the settings it ran
SOLVERS = ("sparse_qr", "sparse_lu")
TIMESTEPPER = "euler_implicit_linearized"
END_TIME_S = 10.0
STEP_S = 1e-3


def scope_for(solver: str) -> str:
    return f"passive_revolute_point_mass_identity_orientation_under_gravity:{TIMESTEPPER}+{solver}"


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


def pendulum_request(timestepper: str = TIMESTEPPER, solver: str = "sparse_qr", length: float = 1.0) -> MultibodyRequest:
    return MultibodyRequest(pendulum_model(length=length), Quantity(END_TIME_S, "s"), Quantity(STEP_S, "s"),
                            ("body:bob.position_x", "body:bob.position_z"), {"timestepper": timestepper, "solver": solver})


def pendulum_route(solver: str) -> ReferenceRoute:
    """Period from the mean interval between LINEARLY INTERPOLATED zero crossings of the bob's x over 10 s (about 10
    crossings), against the finite-amplitude analytic period, to 1e-5 relative.

    Not exercised by this route (so not in its scope): rotated bodies, non-negligible inertia, more than one joint,
    other joint kinds, other gravity directions, actuators, contacts."""
    reference = reference_pendulum_period(_m(1.0), Quantity(9.81, "m/s^2"), Quantity(5.0, "degree"))
    return ReferenceRoute(
        f"chrono.pendulum_period.{TIMESTEPPER}+{solver}", "chrono", (ADAPTER_ID, ADAPTER_VERSION), (scope_for(solver),),
        "pendulum period (2 x mean interval between linearly interpolated zero crossings of bob x)", reference,
        "analytic: 2*pi*sqrt(L/g) * (1 + a^2/16 + 11 a^4/3072), L = 1 m, g = 9.81 m/s^2, a = 5 deg", 1e-5,
        {"request": pendulum_request(TIMESTEPPER, solver).to_dict()},
        tolerance_basis=("error budget, relative: implicit-Euler phase error <= (omega dt)^2/3 = 3.3e-6 at dt = 1 ms; bob inertia "
                         "1e-6 kg m^2 vs m L^2 = 2 kg m^2 -> 2.5e-7; linear crossing interpolation <= 1e-6; series truncation "
                         "< 1e-8; total < 5e-6, tolerance 1e-5"))


def declared_routes() -> tuple[ReferenceRoute, ...]:
    """The routes this adapter version declares (what a qualification may bind)."""
    return tuple(pendulum_route(s) for s in SOLVERS)


def measured_period(record) -> Quantity | None:
    """The route observable from an execution record; None when fewer than three crossings exist (no period measured)."""
    if not record.succeeded:
        return None
    s = record.series_for("body:bob.position_x")
    t, x = s.times_s, s.values
    crossings = [t[i] + (t[i + 1] - t[i]) * x[i] / (x[i] - x[i + 1]) for i in range(len(x) - 1)
                 if (x[i] > 0) != (x[i + 1] > 0) and x[i] != x[i + 1]]
    if len(crossings) < 3:
        return None
    return Quantity(2 * (crossings[-1] - crossings[0]) / (len(crossings) - 1), "s")


def run_pendulum_route(status: ProviderStatus, solver: str) -> RouteRun:
    """Execute the route on the discovered Chrono build and record the run (outcome computed, never declared)."""
    route = pendulum_route(solver)
    record = ChronoProvider(status).execute(pendulum_request(TIMESTEPPER, solver))
    return record_route_run(route, status, record, measured_period)


__all__ = ["SOLVERS", "declared_routes", "measured_period", "pendulum_model", "pendulum_request", "pendulum_route", "run_pendulum_route",
           "scope_for"]
