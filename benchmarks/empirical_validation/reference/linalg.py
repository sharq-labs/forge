"""Dense linear algebra written here: Gaussian elimination, partial pivoting.

No LAPACK, no numpy, no scipy. Plain Python lists of floats.

The algorithm is the textbook one. For each column k, the row with the largest
remaining magnitude in that column is swapped into the pivot position, the rows
below are eliminated, and the system is then back-substituted. Partial pivoting
is what keeps the growth factor bounded in practice; without it a matrix with a
small leading entry loses digits that the physics never lost.

An infinity norm condition estimate is returned with every solve. It is
computed the honest way -- by forming the inverse column by column with the
same elimination -- rather than estimated, because these systems are small and
a reported condition number that was itself approximate would be a poor basis
for deciding whether a residual is round-off.
"""

from __future__ import annotations


def _copy(matrix: list[list[float]]) -> list[list[float]]:
    return [list(row) for row in matrix]


def lu_solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve A x = b by Gaussian elimination with partial pivoting."""
    n = len(matrix)
    if n == 0:
        return []
    if any(len(row) != n for row in matrix):
        raise ValueError("matrix must be square")
    if len(rhs) != n:
        raise ValueError("right-hand side length must match the matrix")

    a = _copy(matrix)
    b = list(rhs)

    for k in range(n):
        pivot_row = max(range(k, n), key=lambda r: abs(a[r][k]))
        if a[pivot_row][k] == 0.0:
            raise ZeroDivisionError(
                f"singular system: column {k} has no non-zero pivot"
            )
        if pivot_row != k:
            a[k], a[pivot_row] = a[pivot_row], a[k]
            b[k], b[pivot_row] = b[pivot_row], b[k]
        pivot = a[k][k]
        for r in range(k + 1, n):
            factor = a[r][k] / pivot
            if factor == 0.0:
                continue
            a[r][k] = 0.0
            for c in range(k + 1, n):
                a[r][c] -= factor * a[k][c]
            b[r] -= factor * b[k]

    x = [0.0] * n
    for k in range(n - 1, -1, -1):
        total = b[k]
        for c in range(k + 1, n):
            total -= a[k][c] * x[c]
        x[k] = total / a[k][k]
    return x


def infinity_norm(matrix: list[list[float]]) -> float:
    return max((sum(abs(v) for v in row) for row in matrix), default=0.0)


def condition_number(matrix: list[list[float]]) -> float:
    """kappa_inf(A) = ||A||_inf ||A^-1||_inf, with the inverse formed explicitly."""
    n = len(matrix)
    if n == 0:
        return 0.0
    columns = []
    for j in range(n):
        unit = [1.0 if i == j else 0.0 for i in range(n)]
        columns.append(lu_solve(matrix, unit))
    inverse = [[columns[j][i] for j in range(n)] for i in range(n)]
    return infinity_norm(matrix) * infinity_norm(inverse)


def residual_infinity_norm(
    matrix: list[list[float]], rhs: list[float], solution: list[float]
) -> float:
    worst = 0.0
    for row, target in zip(matrix, rhs):
        value = sum(c * x for c, x in zip(row, solution)) - target
        worst = max(worst, abs(value))
    return worst
