"""Moving-mesh kinematics for fixed-topology simplicial meshes (Phase 3 BR17, part B).

STATUS: kinematics and geometric-conservation infrastructure ONLY.  No
Arbitrary Lagrangian-Eulerian (ALE) formulation of any governing equation is
implemented in Forge (:data:`ALE_FORMULATION_IMPLEMENTED` is ``False``;
:func:`require_ale_formulation` refuses).  A stored displacement, a moved mesh
or a passing geometric-conservation check is NOT evidence that an ALE solve is
correct: the convective mesh-velocity terms, the conservative update of the
physical state and the coupling to the moving interface are absent.  What is
here is what such a formulation needs and what it must not get wrong:

Configurations and units
    A :class:`MovingMeshState` holds the REFERENCE configuration (coordinates
    in metres, fixed connectivity), the mesh DISPLACEMENT from it (metres) at an
    exact time (``Fraction`` seconds), and the MESH velocity of the step that
    produced it (metres per second).  Mesh motion is not material motion: the
    record says so, and nothing here moves material or transports a field.

Motion over a step
    Vertices move linearly in time between two states (constant mesh velocity
    ``w = (d1 - d0) / dt`` over the step).  On a simplex the signed measure is
    then a polynomial of degree ``d`` in the step fraction; :func:`advance_mesh`
    refuses a step during which ANY cell inverts or collapses -- checked over
    the whole step from the exact polynomial, not only at its ends -- and a
    final configuration below the declared shape quality.

Geometric conservation law (GCL)
    For this motion ``dV/dt = V div w`` holds exactly on every simplex, so
    ``V(t1) - V(t0) = int dV/dt dt``.  A time-integration rule satisfies the
    discrete GCL when it integrates that degree ``d - 1`` polynomial exactly:
    any rule in 1D, the midpoint (or trapezoid) rule in 2D, two-point
    Gauss-Legendre in 3D -- the midpoint rule VIOLATES it on tetrahedra.
    :func:`discrete_gcl_residual` measures the violation of a declared rule;
    :func:`minimal_exact_rule` names the cheapest exact one.

History, rollback, stale fields
    :class:`MovingMeshHistory` is append-only with digest-checked checkpoints;
    rollback truncates to a checkpoint it issued.  A field is bound to the
    mesh state it was computed on (:class:`MeshBoundField`); using it on any
    other state is refused (a stale field on a moved mesh is a different
    field).  Topology changes are refused; interface continuity between two
    moving meshes is checked node by node (:func:`require_interface_continuity`).

Quadrilaterals and hexahedra are refused (their measure is not a polynomial of
the vertex motion of this form, and their validity needs more than corner signs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import math
from typing import Any

import numpy as np

from ..scenarios.timeline import canonical_digest, exact_seconds
from ..scientific.units.quantity import Quantity
from .core import NumericalRefusal
from .mesh_quality import (
    DEGENERACY_ULPS, MeshQualityPolicy, MeshQualityRefusal, require_valid_mesh, shape_quality, signed_measures,
)

ALE_FORMULATION_IMPLEMENTED = False
SIMPLICES = {"interval": 1, "triangle": 2, "tetrahedron": 3}

#: time-integration rules over a step fraction tau in [0, 1]: (points, weights, exact polynomial degree)
GCL_RULES: dict[str, tuple[tuple[float, ...], tuple[float, ...], int]] = {
    "forward_euler": ((0.0,), (1.0,), 0),
    "backward_euler": ((1.0,), (1.0,), 0),
    "midpoint": ((0.5,), (1.0,), 1),
    "trapezoid": ((0.0, 1.0), (0.5, 0.5), 1),
    "gauss2": ((0.5 - 0.5 / math.sqrt(3.0), 0.5 + 0.5 / math.sqrt(3.0)), (0.5, 0.5), 3),
}


def require_ale_formulation() -> None:
    """Refuse: no ALE formulation of any governing equation exists (owner decision OD-P3-4)."""
    raise NumericalRefusal(
        "no Arbitrary Lagrangian-Eulerian formulation is implemented: the mesh-velocity convection terms, the "
        "conservative state update on moving cells and the moving-interface coupling are absent (owner decision "
        "OD-P3-4); a moved mesh or a satisfied geometric conservation law is not an ALE solve"
    )


def _bytes_digest(array: np.ndarray) -> str:
    a = np.ascontiguousarray(array)
    h = hashlib.sha256(f"{a.dtype}|{a.shape}|".encode())
    h.update(a.tobytes())
    return h.hexdigest()


def _frozen(array: Any, dtype: Any) -> np.ndarray:
    out = np.array(array, dtype=dtype, copy=True)
    out.setflags(write=False)
    return out


@dataclass(frozen=True, eq=False)  # array fields: identity is the digest, never ==
class MeshConfiguration:
    """One geometric configuration of a fixed-topology simplicial mesh (coordinates in metres)."""

    cell_type: str
    coordinates: np.ndarray
    connectivity: np.ndarray

    def __post_init__(self) -> None:
        if self.cell_type not in SIMPLICES:
            raise MeshQualityRefusal(f"moving-mesh kinematics are implemented for simplices {sorted(SIMPLICES)}; "
                                     f"{self.cell_type!r} is refused")
        coords = np.asarray(self.coordinates, dtype=np.float64)
        if coords.ndim == 1:
            coords = coords.reshape(-1, 1)
        object.__setattr__(self, "coordinates", _frozen(coords, np.float64))
        object.__setattr__(self, "connectivity", _frozen(self.connectivity, np.int64))
        signed_measures(self.cell_type, self.coordinates, self.connectivity)  # shape, index and finiteness refusals

    @property
    def dimension(self) -> int:
        return SIMPLICES[self.cell_type]

    @property
    def topology_digest(self) -> str:
        return canonical_digest({"cell_type": self.cell_type, "connectivity": _bytes_digest(self.connectivity)})

    @property
    def digest(self) -> str:
        return canonical_digest({"topology": self.topology_digest, "coordinates_m": _bytes_digest(self.coordinates)})

    def measures(self) -> np.ndarray:
        return signed_measures(self.cell_type, self.coordinates, self.connectivity)


def _edge_jacobians(cell_type: str, coordinates: np.ndarray, connectivity: np.ndarray) -> np.ndarray:
    """``E`` per cell: columns ``x_k - x_0`` (shape ``(cells, d, d)``)."""
    p = coordinates[connectivity]
    return np.stack([p[:, k] - p[:, 0] for k in range(1, SIMPLICES[cell_type] + 1)], axis=-1)


def _volume_times_divergence(cell_type: str, coordinates: np.ndarray, connectivity: np.ndarray,
                             velocity: np.ndarray) -> np.ndarray:
    """``V div w`` per cell for a P1 velocity field: ``det(E) / d! * trace(W E^-1)`` (exact on a simplex)."""
    d = SIMPLICES[cell_type]
    e = _edge_jacobians(cell_type, coordinates, connectivity)
    w = _edge_jacobians(cell_type, velocity, connectivity)
    det = np.linalg.det(e)
    with np.errstate(divide="ignore", invalid="ignore"):
        divergence = np.trace(w @ np.linalg.inv(e), axis1=1, axis2=2)
    return det / math.factorial(d) * divergence


@dataclass(frozen=True, eq=False)  # array fields: identity is the digest, never ==
class MovingMeshState:
    """Reference configuration + mesh displacement at an exact time (+ the mesh velocity of the step into it)."""

    mesh_id: str
    reference: MeshConfiguration
    displacement: np.ndarray
    time: Fraction
    velocity: np.ndarray | None = None
    parent_digest: str | None = None

    def __post_init__(self) -> None:
        if not str(self.mesh_id).strip():
            raise NumericalRefusal("a moving mesh needs a mesh_id")
        if not isinstance(self.reference, MeshConfiguration):
            raise NumericalRefusal("the reference configuration must be a MeshConfiguration")
        shape = self.reference.coordinates.shape
        displacement = np.asarray(self.displacement, dtype=np.float64).reshape(shape)
        if not np.all(np.isfinite(displacement)):
            raise NumericalRefusal("mesh displacement must be finite")
        object.__setattr__(self, "displacement", _frozen(displacement, np.float64))
        if not isinstance(self.time, Fraction):
            raise NumericalRefusal("the state time must be an exact Fraction of seconds")
        if self.velocity is not None:
            velocity = np.asarray(self.velocity, dtype=np.float64).reshape(shape)
            if not np.all(np.isfinite(velocity)):
                raise NumericalRefusal("mesh velocity must be finite")
            object.__setattr__(self, "velocity", _frozen(velocity, np.float64))

    @property
    def current(self) -> MeshConfiguration:
        return MeshConfiguration(self.reference.cell_type, self.reference.coordinates + self.displacement,
                                 self.reference.connectivity)

    @property
    def digest(self) -> str:
        return canonical_digest({
            "mesh_id": self.mesh_id, "reference": self.reference.digest,
            "displacement_m": _bytes_digest(self.displacement),
            "time_s": f"{self.time.numerator}/{self.time.denominator}",
            "velocity_m_per_s": None if self.velocity is None else _bytes_digest(self.velocity),
            "parent": self.parent_digest,
        })

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "mesh_motion_not_material_motion", "mesh_id": self.mesh_id,
                "cell_type": self.reference.cell_type, "reference_digest": self.reference.digest,
                "current_digest": self.current.digest, "topology_digest": self.reference.topology_digest,
                "time_s": f"{self.time.numerator}/{self.time.denominator}",
                "displacement_unit": "meter", "velocity_unit": "meter/second",
                "max_displacement_m": float(np.max(np.abs(self.displacement))) if self.displacement.size else 0.0,
                "parent_digest": self.parent_digest, "digest": self.digest,
                "notice": "mesh motion only; no ALE formulation is implemented"}


def start_moving_mesh(mesh_id: str, cell_type: str, coordinates_m: Any, connectivity: Any, time: Quantity,
                      policy: MeshQualityPolicy) -> MovingMeshState:
    """The reference state at ``time``: a valid (positively oriented, quality-checked) mesh with zero displacement."""
    reference = MeshConfiguration(cell_type, coordinates_m, connectivity)
    require_valid_mesh(cell_type, reference.coordinates, reference.connectivity,
                       MeshQualityPolicy(policy.minimum_quality, orientation="positive"))
    return MovingMeshState(mesh_id, reference, np.zeros_like(reference.coordinates), exact_seconds(time))


def _measure_polynomials(cell_type: str, x0: np.ndarray, x1: np.ndarray, connectivity: np.ndarray) -> np.ndarray:
    """Exact coefficients (highest power first) of each cell's signed measure in tau, x(tau) = x0 + tau (x1 - x0)."""
    d = SIMPLICES[cell_type]
    taus = np.linspace(0.0, 1.0, d + 1)
    samples = np.stack([signed_measures(cell_type, x0 + t * (x1 - x0), connectivity) for t in taus])
    vandermonde = np.vander(taus, d + 1)
    return np.linalg.solve(vandermonde, samples).T  # (cells, d + 1)


def _minimum_over_step(coefficients: np.ndarray) -> np.ndarray:
    """min over tau in [0, 1] of each polynomial (ends and interior critical points)."""
    out = np.empty(coefficients.shape[0])
    for i, c in enumerate(coefficients):
        candidates = [0.0, 1.0]
        derivative = np.polyder(c)
        if derivative.size and np.any(derivative != 0.0):
            for root in np.roots(derivative):
                if abs(root.imag) <= 1e-14 and 0.0 < root.real < 1.0:
                    candidates.append(float(root.real))
        out[i] = min(float(np.polyval(c, t)) for t in candidates)
    return out


@dataclass(frozen=True)
class MeshMotionStep:
    """What one mesh step did: its exact duration, the worst cell over the step, and the end quality."""

    start_digest: str
    end_digest: str
    dt: Fraction
    minimum_signed_measure_ratio: float
    minimum_quality: float
    max_displacement_increment_m: float

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "mesh_motion_not_material_motion", "start_digest": self.start_digest,
                "end_digest": self.end_digest, "dt_s": f"{self.dt.numerator}/{self.dt.denominator}",
                "minimum_signed_measure_ratio": self.minimum_signed_measure_ratio,
                "minimum_quality": self.minimum_quality,
                "max_displacement_increment_m": self.max_displacement_increment_m}


def advance_mesh(state: MovingMeshState, displacement_m: Any, time: Quantity,
                 policy: MeshQualityPolicy) -> tuple[MovingMeshState, MeshMotionStep]:
    """The state at ``time`` with the new displacement, refusing inversion or collapse at ANY instant of the step."""
    t1 = exact_seconds(time)
    dt = t1 - state.time
    if dt <= 0:
        raise NumericalRefusal(f"a mesh step must advance time; got dt = {float(dt)!r} s")
    reference = state.reference
    new_displacement = np.asarray(displacement_m, dtype=np.float64).reshape(reference.coordinates.shape)
    if not np.all(np.isfinite(new_displacement)):
        raise NumericalRefusal("mesh displacement must be finite")
    x0 = reference.coordinates + state.displacement
    x1 = reference.coordinates + new_displacement
    reference_sign = np.sign(reference.measures())
    coefficients = _measure_polynomials(reference.cell_type, x0, x1, reference.connectivity)
    worst = _minimum_over_step(coefficients * reference_sign[:, None])
    scale = np.abs(reference.measures())
    p = x1[reference.connectivity]
    longest = np.max(np.stack([np.linalg.norm(p[:, b] - p[:, a], axis=-1)
                               for a in range(p.shape[1]) for b in range(a + 1, p.shape[1])], axis=1), axis=1)
    floor = DEGENERACY_ULPS * np.finfo(np.float64).eps * longest ** reference.dimension
    bad = np.flatnonzero(worst <= floor)
    if bad.size:
        raise MeshQualityRefusal(
            f"mesh {state.mesh_id!r}: {bad.size} cell(s) invert or collapse during the step "
            f"[{float(state.time)}, {float(t1)}] s (first: {bad[:5].tolist()}); the motion is refused"
        )
    quality = shape_quality(reference.cell_type, x1, reference.connectivity)
    low = np.flatnonzero(quality < policy.minimum_quality)
    if low.size:
        raise MeshQualityRefusal(
            f"mesh {state.mesh_id!r}: {low.size} cell(s) fall below the declared quality {policy.minimum_quality:g} "
            f"(minimum {float(np.min(quality)):.3g}); the motion is refused"
        )
    velocity = (new_displacement - state.displacement) / float(dt)
    new = MovingMeshState(state.mesh_id, reference, new_displacement, t1, velocity, state.digest)
    step = MeshMotionStep(state.digest, new.digest, dt, float(np.min(worst / scale)), float(np.min(quality)),
                          float(np.max(np.abs(new_displacement - state.displacement))))
    return new, step


def minimal_exact_rule(dimension: int) -> str:
    """The cheapest rule of :data:`GCL_RULES` that satisfies the discrete GCL for linear vertex motion in ``dimension``."""
    if dimension not in (1, 2, 3):
        raise NumericalRefusal("dimension must be 1, 2 or 3")
    # dV/dtau has degree d - 1
    return {1: "backward_euler", 2: "midpoint", 3: "gauss2"}[dimension]


@dataclass(frozen=True)
class GCLResidual:
    rule: str
    exact_for_this_dimension: bool
    max_abs_m: float
    max_relative: float

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "geometric_conservation_check_not_ale_evidence", "rule": self.rule,
                "exact_for_this_dimension": self.exact_for_this_dimension,
                "max_abs_measure_residual": self.max_abs_m, "max_relative": self.max_relative}


def discrete_gcl_residual(before: MovingMeshState, after: MovingMeshState, rule: str) -> GCLResidual:
    """``|V(t1) - V(t0) - dt sum_q w_q (V div w)(tau_q)|`` per cell, for a declared time rule (see the module docstring)."""
    if rule not in GCL_RULES:
        raise NumericalRefusal(f"unknown GCL rule {rule!r}; known: {sorted(GCL_RULES)}")
    if before.reference.digest != after.reference.digest or before.mesh_id != after.mesh_id:
        raise NumericalRefusal("a GCL residual compares two states of one mesh")
    if after.parent_digest != before.digest or after.velocity is None:
        raise NumericalRefusal("the later state must be the direct successor of the earlier one")
    reference = before.reference
    dt = float(after.time - before.time)
    x0 = reference.coordinates + before.displacement
    x1 = reference.coordinates + after.displacement
    points, weights, degree = GCL_RULES[rule]
    integral = np.zeros(reference.connectivity.shape[0])
    for tau, weight in zip(points, weights):
        integral += weight * _volume_times_divergence(reference.cell_type, x0 + tau * (x1 - x0),
                                                      reference.connectivity, after.velocity)
    change = signed_measures(reference.cell_type, x1, reference.connectivity) - \
        signed_measures(reference.cell_type, x0, reference.connectivity)
    residual = np.abs(change - dt * integral)
    scale = np.maximum(np.abs(signed_measures(reference.cell_type, x0, reference.connectivity)), np.finfo(np.float64).tiny)
    return GCLResidual(rule, degree >= reference.dimension - 1, float(np.max(residual)), float(np.max(residual / scale)))


@dataclass(frozen=True)
class MeshCheckpoint:
    index: int
    digest: str


@dataclass
class MovingMeshHistory:
    """Append-only states of one moving mesh, with digest-checked checkpoints and rollback."""

    states: list[MovingMeshState] = field(default_factory=list)

    def append(self, state: MovingMeshState) -> None:
        if self.states:
            last = self.states[-1]
            if state.parent_digest != last.digest or state.reference.digest != last.reference.digest:
                raise NumericalRefusal("a state may only be appended after its parent, on the same reference mesh")
        elif state.parent_digest is not None:
            raise NumericalRefusal("the first state of a history is a reference state (no parent)")
        self.states.append(state)

    @property
    def current(self) -> MovingMeshState:
        if not self.states:
            raise NumericalRefusal("an empty moving-mesh history has no current state")
        return self.states[-1]

    def checkpoint(self) -> MeshCheckpoint:
        return MeshCheckpoint(len(self.states) - 1, self.current.digest)

    def rollback(self, checkpoint: MeshCheckpoint) -> MovingMeshState:
        if not isinstance(checkpoint, MeshCheckpoint) or not 0 <= checkpoint.index < len(self.states) \
                or self.states[checkpoint.index].digest != checkpoint.digest:
            raise NumericalRefusal("rollback to a checkpoint this history did not issue (or whose state is gone)")
        del self.states[checkpoint.index + 1:]
        return self.current


@dataclass(frozen=True)
class MeshBoundField:
    """A field digest bound to the mesh state it was computed on."""

    field_digest: str
    state_digest: str

    def require_on(self, state: MovingMeshState) -> None:
        if state.digest != self.state_digest:
            raise NumericalRefusal(
                f"field {self.field_digest[:12]}... was computed on mesh state {self.state_digest[:12]}...; the "
                f"current state is {state.digest[:12]}... -- a field on a moved mesh is stale until recomputed or "
                f"conservatively transferred"
            )


def require_same_topology(a: MovingMeshState, b: MovingMeshState) -> None:
    if a.reference.topology_digest != b.reference.topology_digest:
        raise NumericalRefusal("the mesh topology changed; topology changes are not supported by moving-mesh kinematics")


def require_interface_continuity(a: MovingMeshState, nodes_a: Any, b: MovingMeshState, nodes_b: Any,
                                 *, tolerance_m: float) -> float:
    """Shared interface nodes of two moving meshes must coincide in the current configuration; returns the gap."""
    ia, ib = np.asarray(nodes_a, dtype=np.int64), np.asarray(nodes_b, dtype=np.int64)
    if ia.shape != ib.shape or ia.ndim != 1 or not ia.size:
        raise NumericalRefusal("interface node lists must be non-empty and paired one to one")
    if not math.isfinite(tolerance_m) or tolerance_m < 0.0:
        raise NumericalRefusal("tolerance_m must be finite and non-negative")
    xa, xb = a.current.coordinates[ia], b.current.coordinates[ib]
    if xa.shape[1] != xb.shape[1]:
        raise NumericalRefusal("the two meshes have different spatial dimensions")
    gap = float(np.max(np.linalg.norm(xa - xb, axis=1)))
    if gap > tolerance_m:
        raise NumericalRefusal(f"the moving interface opened by {gap:.3e} m > {tolerance_m:g} m; the two meshes no "
                               f"longer share it")
    return gap


__all__ = [
    "ALE_FORMULATION_IMPLEMENTED",
    "GCLResidual",
    "GCL_RULES",
    "MeshBoundField",
    "MeshCheckpoint",
    "MeshConfiguration",
    "MeshMotionStep",
    "MovingMeshHistory",
    "MovingMeshState",
    "advance_mesh",
    "discrete_gcl_residual",
    "minimal_exact_rule",
    "require_ale_formulation",
    "require_interface_continuity",
    "require_same_topology",
    "start_moving_mesh",
]
