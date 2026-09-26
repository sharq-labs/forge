"""Small, generic postprocessing of P1 plane-stress solutions: element stress recovery, von Mises, cross-section force.

The recovery uses the SAME constitutive law every plane-stress provider applies (isotropic, plane stress, small strain,
isotropic thermal strain ``alpha (T - T_ref)`` with T taken at the element centroid) on the provider's OWN nodal
displacement.  It is arithmetic on a solution, not a solver, and it is a common yardstick for providers that do not
export stress (FEniCSx displacement, Code_Aster displacement).  A provider that does export stress (CalculiX) can be
checked against it: the two should agree to the arithmetic of the recovery.  Nothing here is evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..scientific.errors import InvalidScientificProblem


@dataclass(frozen=True)
class ElementStress:
    #: per element: sigma_xx, sigma_yy, sigma_xy (Pa) and the plane-stress von Mises equivalent (Pa)
    sxx: np.ndarray
    syy: np.ndarray
    sxy: np.ndarray
    von_mises: np.ndarray
    #: total mechanical strain per element (exx, eyy, gxy), thermal strain NOT subtracted
    strain: np.ndarray
    area: np.ndarray


def plane_stress_recovery(mesh, u, E, nu, alpha=None, temperature_K=None, reference_K=None) -> ElementStress:
    """Element stress of a P1 triangle displacement field ``u`` (n_nodes x 2, metres).

    ``E``, ``nu`` and ``alpha`` are scalars or one value per element.  With ``alpha`` given, ``temperature_K`` (per node) and
    ``reference_K`` are required: a thermal load is never assumed zero.
    """
    xy = np.asarray(mesh.coordinates, dtype=float)
    cells = np.asarray(mesh.cells, dtype=int)
    if cells.shape[1] != 3:
        raise InvalidScientificProblem("stress recovery here is for P1 triangles")
    u = np.asarray(u, dtype=float)
    if u.shape != (xy.shape[0], 2) or not np.all(np.isfinite(u)):
        raise InvalidScientificProblem("stress recovery needs finite nodal displacements, n_nodes x 2")
    n_cells = cells.shape[0]
    E = np.broadcast_to(np.asarray(E, dtype=float), (n_cells,))
    nu = np.broadcast_to(np.asarray(nu, dtype=float), (n_cells,))
    if alpha is not None:
        if temperature_K is None or reference_K is None:
            raise InvalidScientificProblem("a thermal expansion coefficient needs the temperature field and the reference temperature")
        alpha = np.broadcast_to(np.asarray(alpha, dtype=float), (n_cells,))
        t_elem = np.asarray(temperature_K, dtype=float)[cells].mean(axis=1)
        eth = alpha * (t_elem - float(reference_K))
    else:
        eth = np.zeros(n_cells)
    a, b, c = xy[cells[:, 0]], xy[cells[:, 1]], xy[cells[:, 2]]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    area = 0.5 * np.abs(det)
    # gradients of the P1 shape functions (per element, independent of orientation sign)
    bx = np.stack([b[:, 1] - c[:, 1], c[:, 1] - a[:, 1], a[:, 1] - b[:, 1]], axis=1) / det[:, None]
    by = np.stack([c[:, 0] - b[:, 0], a[:, 0] - c[:, 0], b[:, 0] - a[:, 0]], axis=1) / det[:, None]
    ue = u[cells]  # (m, 3, 2)
    exx = (bx * ue[:, :, 0]).sum(axis=1)
    eyy = (by * ue[:, :, 1]).sum(axis=1)
    gxy = (by * ue[:, :, 0]).sum(axis=1) + (bx * ue[:, :, 1]).sum(axis=1)
    mx, my = exx - eth, eyy - eth  # mechanical strain
    k = E / (1.0 - nu**2)
    sxx = k * (mx + nu * my)
    syy = k * (my + nu * mx)
    sxy = k * (1.0 - nu) / 2.0 * gxy
    vm = np.sqrt(np.maximum(sxx**2 - sxx * syy + syy**2 + 3.0 * sxy**2, 0.0))
    return ElementStress(sxx, syy, sxy, vm, np.stack([exx, eyy, gxy], axis=1), area)


def cross_section_force(mesh, sxx: np.ndarray, x0: float, thickness: float, half_width: float) -> float:
    """Axial force (N) through the plane x = x0 of a plate symmetric about y = 0 whose modelled half-width is ``half_width``.

    The area-weighted mean of ``sxx`` over the elements whose centroids lie within one median element width of ``x0`` times
    the FULL cross-section (2 * half_width * thickness).  An EQUILIBRIUM DIAGNOSTIC: with the top edge traction free and
    the bottom a symmetry line, the force must not change from section to section.  It is not a support reaction.
    """
    xy = np.asarray(mesh.coordinates, dtype=float)
    cells = np.asarray(mesh.cells, dtype=int)
    xs = xy[cells][:, :, 0]
    cx = xs.mean(axis=1)
    dx = float(np.median(xs.max(axis=1) - xs.min(axis=1)))
    m = np.abs(cx - x0) <= dx
    if not m.any():
        raise InvalidScientificProblem("no element lies near the requested section")
    a, b, c = xy[cells[:, 0]], xy[cells[:, 1]], xy[cells[:, 2]]
    area = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    mean = float((np.asarray(sxx)[m] * area[m]).sum() / area[m].sum())
    return mean * thickness * 2.0 * half_width
