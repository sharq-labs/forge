"""Exact candidate search for field transfers (Phase 2 BR9).

Two structures, both used only to FIND candidates; every acceptance decision is
still the exact geometric test the mapping already makes, so an index can
change how fast a transfer runs and never which values it produces.

:class:`BoxIndex`
    A uniform bucket grid over axis-aligned boxes (2D or 3D).  ``query_box``
    returns a SUPERSET of the boxes that intersect a closed query box, in
    ascending id order.  Superset, because every coordinate is binned with
    the same monotone map ``floor((x - lower) / width)`` clipped to the grid:
    a point shared by two boxes falls in one bucket, and both boxes are
    registered in it.  Ascending order, so a caller that stops at the first
    accepted candidate stops where an exhaustive ascending scan would.

:func:`nearest_sites`
    Nearest source site for every target site via a KD-tree, reproducing the
    exhaustive rule exactly: among the sites at the minimal squared distance
    -- computed with the same arithmetic as the exhaustive scan -- the LOWEST
    index wins.  The tree's own distance only bounds the search radius.
"""

from __future__ import annotations

import math

import numpy as np

from ...scientific.errors import InvalidScientificProblem

#: Upper bound on buckets per axis; the grid never allocates more than this ** dim buckets.
_MAX_BUCKETS_PER_AXIS = 256


class BoxIndex:
    """Uniform-grid bucket index over ``n`` closed boxes ``[lower[i], upper[i]]``."""

    def __init__(self, lower: np.ndarray, upper: np.ndarray) -> None:
        lower = np.asarray(lower, dtype=np.float64)
        upper = np.asarray(upper, dtype=np.float64)
        if lower.ndim != 2 or lower.shape != upper.shape or lower.shape[1] not in (2, 3):
            raise InvalidScientificProblem("BoxIndex takes (n, 2) or (n, 3) lower/upper corner arrays")
        if not (np.all(np.isfinite(lower)) and np.all(np.isfinite(upper))) or np.any(upper < lower):
            raise InvalidScientificProblem("BoxIndex boxes must be finite with upper >= lower")
        count, dim = lower.shape
        self._dim = dim
        self._origin = lower.min(axis=0) if count else np.zeros(dim)
        extent = (upper.max(axis=0) - self._origin) if count else np.ones(dim)
        per_axis = max(1, min(_MAX_BUCKETS_PER_AXIS, int(math.ceil(max(count, 1) ** (1.0 / dim)))))
        self._buckets = per_axis
        self._width = np.where(extent > 0.0, extent / per_axis, 1.0)
        self._grid: dict[tuple[int, ...], list[int]] = {}
        low = self._bin(lower)
        high = self._bin(upper)
        for box in range(count):
            for key in self._keys(low[box], high[box]):
                self._grid.setdefault(key, []).append(box)

    def _bin(self, points: np.ndarray) -> np.ndarray:
        raw = np.floor((np.asarray(points, dtype=np.float64) - self._origin) / self._width)
        return np.clip(raw, 0, self._buckets - 1).astype(np.int64)

    @staticmethod
    def _keys(low: np.ndarray, high: np.ndarray):
        ranges = [range(int(a), int(b) + 1) for a, b in zip(low, high)]
        if len(ranges) == 2:
            return ((i, j) for i in ranges[0] for j in ranges[1])
        return ((i, j, k) for i in ranges[0] for j in ranges[1] for k in ranges[2])

    def query_box(self, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
        """Ids of every indexed box that may intersect ``[lower, upper]``, ascending (a superset)."""
        low = self._bin(np.asarray(lower, dtype=np.float64)[np.newaxis, :])[0]
        high = self._bin(np.asarray(upper, dtype=np.float64)[np.newaxis, :])[0]
        found: set[int] = set()
        for key in self._keys(low, high):
            found.update(self._grid.get(key, ()))
        return np.array(sorted(found), dtype=np.int64)

    def query_point(self, point: np.ndarray) -> np.ndarray:
        return self.query_box(point, point)


def nearest_sites(source_sites: np.ndarray, target_sites: np.ndarray) -> np.ndarray:
    """Index of the nearest source site for every target site (lowest index among exact ties)."""
    from scipy.spatial import cKDTree

    source = np.asarray(source_sites, dtype=np.float64)
    target = np.asarray(target_sites, dtype=np.float64)
    if source.ndim != 2 or target.ndim != 2 or source.shape[1] != target.shape[1] or not len(source):
        raise InvalidScientificProblem("nearest_sites takes non-empty (n, d) source and (m, d) target site arrays")
    tree = cKDTree(source)
    distance, _ = tree.query(target, k=1)
    chosen = np.empty(len(target), dtype=np.int64)
    eps = np.finfo(np.float64).eps
    for index, point in enumerate(target):
        # a radius that contains every site the exhaustive arithmetic could call nearest
        radius = float(distance[index]) * (1.0 + 16.0 * eps) + 16.0 * np.finfo(np.float64).tiny
        candidates = np.array(sorted(tree.query_ball_point(point, r=radius)), dtype=np.int64)
        if not len(candidates):
            candidates = np.arange(len(source))
        delta = source[candidates] - point
        distance2 = np.einsum("ij,ij->i", delta, delta)
        chosen[index] = int(candidates[int(np.argmin(distance2))])
    return chosen


__all__ = ["BoxIndex", "nearest_sites"]
