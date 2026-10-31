"""The structure grammar ``y = scale x F(groups)`` (EXC-4, development).

F is built from the operators of :mod:`engcore.blindfold.expression` over MONOMIAL ATOMS of the dimensionless groups
(``a x prod_j pi_j^b_j`` with a fitted positive coefficient and fitted real exponents on a chosen subset of groups).
The combinators and their limits are fixed by EXC-4 before any data:

* at most 2 additive terms (``add``), at most 1 ``exp``, at most 1 ``piecewise`` (switching on one basis group below a
  fitted threshold), structure depth <= 4 and structure nodes <= 12 (counted below), at most 5,000 structures.

**The grammar is a DECLARED SET of five shapes, a strict subset of every composition those limits allow** (review H2,
2026-10-30): compositions such as ``(A + B) x exp(k C)``, ``exp(k (C1 + C2))``, ``(A + B)^p`` or a regime with an exp
branch also fit the limits and are NOT enumerated.  This narrows EXC-4 field 2 ("defined by operators and limits") and is
recorded as an owner decision; expressibility must be judged against the structures actually enumerated, on the actual
basis:

======== ================================================ depth
power    A                                                1
sum      A + B                                            2
exp      A x exp(k x C)                                   3
sum_exp  A + B x exp(k x C)                               4
regime   A if pi_s < t else B                             2
======== ================================================ =====

(A, B: atoms with a coefficient; C: a coefficient-free atom over a NON-EMPTY group subset, scaled by the fitted k.)
Node count at structure level: an atom with a coefficient is 1 + |subset|; ``C`` with ``k`` is 2 + |subset| (k and a
product); each add, mul, exp counts 1; a regime counts 3 (the switch, its group, its threshold).  No shape copies a
generator's constants or groups, but the shape list was chosen by hand and overlaps the Blindfold generator's
``power`` / ``two_term`` / ``regime`` families, and the ``exp`` shape partly overlaps its saturating ``exp`` form
(``engcore.blindfold.universe``): a representation-circularity risk that the pilot report must state.

Parameters are in log space (``ln a``, exponents, ``k``, ``ln t``): a structure's ln F at the rows' ln-group matrix L is
given by :func:`log_f`, and :func:`to_expression` writes the fitted law exactly in the escrow's expression grammar.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .dimensions import DimensionalBasis

SHAPES = ("power", "sum", "exp", "sum_exp", "regime")
MAX_NODES = 12
MAX_DEPTH = 4
MAX_STRUCTURES = 5000
DEPTH = {"power": 1, "sum": 2, "exp": 3, "sum_exp": 4, "regime": 2}
EXP_CLIP = 50.0


@dataclass(frozen=True)
class Structure:
    shape: str
    atoms: tuple[tuple[int, ...], ...]       # group-index subsets, in the shape's order (see the table)
    switch: int | None = None                # regime only

    @property
    def key(self) -> str:
        atoms = "|".join(",".join(map(str, a)) for a in self.atoms)
        return f"{self.shape}[{atoms}]" + (f"@{self.switch}" if self.switch is not None else "")

    def layout(self) -> list[tuple[str, int]]:
        """(role, number of parameters) per block, in parameter order."""
        a = self.atoms
        if self.shape == "power":
            return [("atom", 1 + len(a[0]))]
        if self.shape == "sum":
            return [("atom", 1 + len(a[0])), ("atom", 1 + len(a[1]))]
        if self.shape == "exp":
            return [("atom", 1 + len(a[0])), ("kexp", 1 + len(a[1]))]
        if self.shape == "sum_exp":
            return [("atom", 1 + len(a[0])), ("atom", 1 + len(a[1])), ("kexp", 1 + len(a[2]))]
        return [("atom", 1 + len(a[0])), ("atom", 1 + len(a[1])), ("threshold", 1)]

    @property
    def n_params(self) -> int:
        return sum(n for _, n in self.layout())

    @property
    def nodes(self) -> int:
        a = self.atoms
        atom = lambda s: 1 + len(s)                      # noqa: E731
        kexp = lambda s: 2 + len(s) + 1                  # k, its product, the exp
        if self.shape == "power":
            return atom(a[0])
        if self.shape == "sum":
            return 1 + atom(a[0]) + atom(a[1])
        if self.shape == "exp":
            return 1 + atom(a[0]) + kexp(a[1])
        if self.shape == "sum_exp":
            return 1 + atom(a[0]) + 1 + atom(a[1]) + kexp(a[2])
        return 3 + atom(a[0]) + atom(a[1])

    @property
    def depth(self) -> int:
        return DEPTH[self.shape]


def enumerate_structures(n_groups: int, *, max_structures: int = MAX_STRUCTURES) -> tuple[list[Structure], bool]:
    """Every structure inside the limits, simplest first; ``(structures, cap_hit)``. A cap hit is reported, never hidden."""
    subsets = [tuple(s) for k in range(n_groups + 1) for s in itertools.combinations(range(n_groups), k)]
    nonempty = [s for s in subsets if s]
    out: list[Structure] = [Structure("power", (s,)) for s in subsets]
    out += [Structure("sum", (a, b)) for a, b in itertools.combinations(subsets, 2)]
    out += [Structure("exp", (a, c)) for a in subsets for c in nonempty]
    out += [Structure("sum_exp", (a, b, c)) for a in subsets for b in subsets for c in nonempty]
    out += [Structure("regime", (a, b), s) for s in range(n_groups) for a in subsets for b in subsets]
    out = [s for s in out if s.nodes <= MAX_NODES and s.depth <= MAX_DEPTH]
    out.sort(key=lambda s: (s.n_params, s.nodes, SHAPES.index(s.shape), s.key))
    return out[:max_structures], len(out) > max_structures


def _split(structure: Structure, theta: np.ndarray) -> list[np.ndarray]:
    blocks, i = [], 0
    for _, n in structure.layout():
        blocks.append(np.asarray(theta[i:i + n], dtype=float))
        i += n
    return blocks


def _atom(block: np.ndarray, subset: Sequence[int], L: np.ndarray) -> np.ndarray:
    return block[0] + (L[:, list(subset)] @ block[1:] if subset else np.zeros(len(L)))


def _kexp(block: np.ndarray, subset: Sequence[int], L: np.ndarray) -> np.ndarray:
    return block[0] * np.exp(np.clip(L[:, list(subset)] @ block[1:], -EXP_CLIP, EXP_CLIP))


def exp_argument(structure: Structure, theta: np.ndarray, L: np.ndarray) -> np.ndarray | None:
    """The unclipped argument of the structure's exp at the rows (None when the shape has no exp)."""
    if structure.shape not in ("exp", "sum_exp"):
        return None
    block = _split(structure, theta)[-1]
    return L[:, list(structure.atoms[-1])] @ block[1:]


def log_f(structure: Structure, theta: np.ndarray, L: np.ndarray) -> np.ndarray:
    """ln F at the rows (L: rows x groups, natural logs of the group values)."""
    b = _split(structure, theta)
    a = structure.atoms
    with np.errstate(over="ignore", invalid="ignore"):
        if structure.shape == "power":
            return _atom(b[0], a[0], L)
        if structure.shape == "sum":
            return np.logaddexp(_atom(b[0], a[0], L), _atom(b[1], a[1], L))
        if structure.shape == "exp":
            return _atom(b[0], a[0], L) + _kexp(b[1], a[1], L)
        if structure.shape == "sum_exp":
            return np.logaddexp(_atom(b[0], a[0], L), _atom(b[1], a[1], L) + _kexp(b[2], a[2], L))
        below = L[:, structure.switch] < b[2][0]
        return np.where(below, _atom(b[0], a[0], L), _atom(b[1], a[1], L))


def _atom_jac(subset: Sequence[int], L: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(L))] + [L[:, j] for j in subset])


def _kexp_jac(block: np.ndarray, subset: Sequence[int], L: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    u = L[:, list(subset)] @ block[1:]
    inside = np.abs(u) < EXP_CLIP
    e = np.exp(np.clip(u, -EXP_CLIP, EXP_CLIP))
    dk = e
    dc = (block[0] * e * inside)[:, None] * L[:, list(subset)]
    return np.column_stack([dk, dc]), block[0] * e


def jacobian(structure: Structure, theta: np.ndarray, L: np.ndarray) -> np.ndarray:
    """d ln F / d theta at the rows (analytic; zero where the exp argument is clipped). Not defined for ``regime``."""
    b = _split(structure, theta)
    a = structure.atoms
    with np.errstate(over="ignore", invalid="ignore"):
        if structure.shape == "power":
            return _atom_jac(a[0], L)
        if structure.shape == "exp":
            jk, _ = _kexp_jac(b[1], a[1], L)
            return np.column_stack([_atom_jac(a[0], L), jk])
        la = _atom(b[0], a[0], L)
        if structure.shape == "sum":
            lb = _atom(b[1], a[1], L)
            wa = np.exp(la - np.logaddexp(la, lb))
            return np.column_stack([wa[:, None] * _atom_jac(a[0], L), (1 - wa)[:, None] * _atom_jac(a[1], L)])
        if structure.shape == "sum_exp":
            jk, ke = _kexp_jac(b[2], a[2], L)
            lb = _atom(b[1], a[1], L) + ke
            wa = np.exp(la - np.logaddexp(la, lb))
            wb = (1 - wa)[:, None]
            return np.column_stack([wa[:, None] * _atom_jac(a[0], L), wb * _atom_jac(a[1], L), wb * jk])
    raise ValueError("a regime structure has no smooth Jacobian (its threshold is chosen by an exact change-point search)")


# ---------------------------------------------------------------------------------------------- the escrow expression
def _c(x: float) -> dict:
    return {"const": float(x)}


def _monomial(exps: Mapping[str, float]) -> list[dict]:
    return [{"pow": [{"var": n}, _c(e)]} for n, e in sorted(exps.items()) if e != 0.0]


def _mul(factors: list[dict]) -> dict:
    return factors[0] if len(factors) == 1 else {"mul": factors}


def _merge(basis: DimensionalBasis, subset: Sequence[int], exponents: Sequence[float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for j, b in zip(subset, exponents):
        for name, e in basis.groups[j].items():
            out[name] = out.get(name, 0.0) + float(b) * e
    return {n: e for n, e in out.items() if e != 0.0}


def to_expression(structure: Structure, theta: np.ndarray, basis: DimensionalBasis) -> dict[str, Any]:
    """The fitted law ``scale x F`` in the escrow grammar (exact up to floating point)."""
    b = _split(structure, theta)
    a = structure.atoms

    def atom(block: np.ndarray, subset: Sequence[int]) -> dict:
        return _mul([_c(math.exp(block[0]))] + _monomial(_merge(basis, subset, block[1:])))

    def kexp(block: np.ndarray, subset: Sequence[int]) -> dict:
        return {"exp": _mul([_c(block[0])] + _monomial(_merge(basis, subset, block[1:])))}

    if structure.shape == "power":
        f = atom(b[0], a[0])
    elif structure.shape == "sum":
        f = {"add": [atom(b[0], a[0]), atom(b[1], a[1])]}
    elif structure.shape == "exp":
        f = {"mul": [atom(b[0], a[0]), kexp(b[1], a[1])]}
    elif structure.shape == "sum_exp":
        f = {"add": [atom(b[0], a[0]), {"mul": [atom(b[1], a[1]), kexp(b[2], a[2])]}]}
    else:
        switch = _mul(_monomial({n: float(e) for n, e in basis.groups[structure.switch].items()}))
        f = {"piecewise": {"if_below": [switch, _c(math.exp(b[2][0]))], "then": atom(b[0], a[0]), "else": atom(b[1], a[1])}}
    scale = _monomial({n: float(e) for n, e in basis.scale.items()})
    return _mul(scale + [f]) if scale else f


__all__ = ["DEPTH", "EXP_CLIP", "exp_argument", "MAX_DEPTH", "MAX_NODES", "MAX_STRUCTURES", "SHAPES", "Structure", "enumerate_structures", "log_f",
           "to_expression"]
