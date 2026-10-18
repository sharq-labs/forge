"""Phase 1 BR6 -- sparse operands stay sparse; conditioning says whether it is exact or estimated.

Before BR6 ``NumericalProblem`` densified every sparse matrix to check its
finiteness, ``condition_of`` densified it again for a full SVD, and
``array_digest`` hashed whatever storage order the caller happened to use.

NOT RUN (Phase 1 build phase): docs/work/DEFERRED_VALIDATION.md, DV-42.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest
import scipy.sparse as sp

from engcore.numerical import (
    NumericalMethod, NumericalProblem, NumericalRefusal, NumPyDenseLinearProvider, OperatorIdentity, ProblemKind,
    UnitBoundary, VariableSpec, array_digest,
)
from engcore.numerical.core import (
    DENSE_CONVERSION_LIMIT, SPARSE_EXACT_CONDITION_LIMIT, canonical_csr, condition_of,
)
from engcore.scientific.numerics.conditioning import ConditioningStatus
from engcore.scientific.solvers.protocol import SolverSettings


class NeverDense(sp.csr_matrix):
    """A sparse matrix that fails the test if anything converts it to a dense array."""

    def toarray(self, *args, **kwargs):
        raise AssertionError("a sparse operand was densified")

    def todense(self, *args, **kwargs):
        raise AssertionError("a sparse operand was densified")


def _problem(matrix, rhs):
    n = matrix.shape[0]
    operator = OperatorIdentity("op", "1", array_digest(matrix, rhs), "array_bytes")
    return NumericalProblem("p", ProblemKind.LINEAR, operator, UnitBoundary((VariableSpec("x", "K", size=n),)),
                            operands={"matrix": matrix, "rhs": rhs})


# ---- admission reads stored entries only -------------------------------------------------------


def test_a_large_sparse_problem_is_admitted_without_densifying():
    n = 200_000
    matrix = NeverDense(sp.identity(n, format="csr"))
    problem = _problem(matrix, np.ones(n))
    assert problem.identity()["operand_digest"] == array_digest(matrix, np.ones(n))


def test_a_non_finite_stored_entry_is_refused():
    matrix = sp.csr_matrix((np.array([1.0, np.nan]), np.array([0, 1]), np.array([0, 1, 2])), shape=(2, 2))
    with pytest.raises(NumericalRefusal, match="non-finite"):
        _problem(matrix, np.ones(2))


def test_an_invalid_sparse_structure_is_refused():
    matrix = sp.identity(3, format="csr").copy()
    matrix.indices[0] = 99  # column out of range; only a full structural check sees it
    with pytest.raises(NumericalRefusal, match="invalid structure"):
        canonical_csr(matrix)


@pytest.mark.parametrize("dtype", [complex, bool])
def test_complex_and_boolean_sparse_operands_are_refused(dtype):
    with pytest.raises(NumericalRefusal, match="real numeric"):
        canonical_csr(sp.identity(3, format="csr", dtype=dtype))


def test_a_sparse_rhs_is_refused():
    matrix = sp.identity(3, format="csr")
    with pytest.raises(NumericalRefusal, match="dense vector"):
        NumericalProblem("p", ProblemKind.LINEAR, OperatorIdentity("op", "1", "0" * 64, "declared"),
                         UnitBoundary((VariableSpec("x", "K", size=3),)),
                         operands={"matrix": matrix, "rhs": sp.csr_matrix(np.ones((3, 1)))})


# ---- deterministic identity ----------------------------------------------------------------------


def _pre_br6_encoding(matrix, rhs):
    h = hashlib.sha256()
    a = matrix.tocsr()
    for part in (a.data, a.indices, a.indptr):
        arr = np.ascontiguousarray(part)
        h.update(str(arr.dtype).encode() + str(arr.shape).encode() + arr.tobytes())
    h.update(str(a.shape).encode())
    arr = np.ascontiguousarray(np.asarray(rhs, dtype=float))
    h.update(str(arr.shape).encode() + arr.tobytes())
    return h.hexdigest()


def test_a_canonical_matrix_keeps_its_pre_br6_digest():
    matrix = sp.csr_matrix(np.array([[4.0, 1.0, 0.0], [0.0, 3.0, 2.0], [1.0, 0.0, 5.0]]))
    assert matrix.has_canonical_format
    assert array_digest(matrix, np.ones(3)) == _pre_br6_encoding(matrix, np.ones(3))


def test_one_operator_has_one_digest_whatever_its_storage_order():
    canonical = sp.csr_matrix(np.array([[4.0, 1.0], [0.0, 3.0]]))
    # the same operator: unsorted column indices and a duplicate entry (2 + 2 = 4)
    messy = sp.csr_matrix((np.array([1.0, 2.0, 2.0, 3.0]), np.array([1, 0, 0, 1]), np.array([0, 3, 4])), shape=(2, 2))
    assert not messy.has_canonical_format
    before = (messy.data.copy(), messy.indices.copy())
    assert array_digest(messy, np.ones(2)) == array_digest(canonical, np.ones(2))
    # the caller's matrix is untouched
    np.testing.assert_array_equal(messy.data, before[0])
    np.testing.assert_array_equal(messy.indices, before[1])


# ---- conditioning: exact, estimated, or unresolved -------------------------------------------------


def test_a_small_sparse_matrix_gets_the_same_exact_number_as_its_dense_form():
    dense = np.array([[2.0, 0.0], [0.0, 0.5]])
    sparse_estimate = condition_of(sp.csr_matrix(dense))
    dense_estimate = condition_of(dense)
    assert sparse_estimate == dense_estimate
    assert sparse_estimate.method == "numpy.linalg.cond (2-norm)"
    assert sparse_estimate.condition_number == pytest.approx(4.0)


def _large_diagonal(values):
    n = SPARSE_EXACT_CONDITION_LIMIT + 500
    diagonal = np.ones(n)
    diagonal[: len(values)] = values
    return NeverDense(sp.diags(diagonal, format="csr"))


def test_a_lower_bound_estimate_below_the_threshold_is_unresolved_never_well_conditioned():
    estimate = condition_of(_large_diagonal([2.0]))  # kappa_1 = 2 exactly
    assert estimate.condition_number is None
    assert estimate.status is ConditioningStatus.SINGULAR_OR_UNRESOLVED
    assert "ESTIMATED" in estimate.method and "does not establish" in estimate.method


def test_a_lower_bound_estimate_above_the_threshold_proves_ill_conditioning():
    estimate = condition_of(_large_diagonal([1e-14]))  # kappa_1 = 1e14 exactly; Hager is exact on a diagonal
    assert estimate.status is ConditioningStatus.ILL_CONDITIONED
    assert estimate.condition_number == pytest.approx(1e14, rel=1e-12)
    assert "ESTIMATED" in estimate.method


def test_an_exactly_singular_large_sparse_matrix_is_reported_singular():
    estimate = condition_of(_large_diagonal([0.0]))
    assert estimate.status is ConditioningStatus.SINGULAR_OR_UNRESOLVED
    assert estimate.condition_number == float("inf")


def test_an_iterative_method_is_never_made_to_factorize():
    estimate = condition_of(_large_diagonal([2.0]), allow_factorization=False)
    assert estimate.condition_number is None and "iterative" in estimate.method


def test_the_estimate_is_deterministic():
    matrix = _large_diagonal([1e-14, 3.0, 7.0])
    assert condition_of(matrix) == condition_of(matrix)


# ---- a dense method densifies only within its bound ---------------------------------------------


def test_the_dense_provider_refuses_a_sparse_operand_above_its_conversion_limit():
    n = DENSE_CONVERSION_LIMIT + 1
    matrix = NeverDense(sp.identity(n, format="csr"))
    problem = _problem(matrix, np.ones(n))
    method = NumericalMethod("dense_lu", SolverSettings(tolerances={"residual_rtol": 1e-10}))
    with pytest.raises(NumericalRefusal, match="dense conversion limit"):
        NumPyDenseLinearProvider().execute(problem, method)


# ---- 2026-10-18 remediation C2: a singular sparse-direct solve is named singular ---------------


def test_an_exactly_singular_sparse_direct_solve_is_named_singular_not_a_residual_failure():
    import warnings

    from engcore.numerical.providers import SciPyLinearProvider
    from engcore.scientific.solvers.protocol import ConvergenceState

    # [[1, 1], [1, 1]] has rank 1: Gaussian elimination leaves the second pivot exactly 0
    matrix = sp.csr_matrix(np.array([[1.0, 1.0], [1.0, 1.0]]))
    problem = _problem(matrix, np.array([1.0, 2.0]))
    method = NumericalMethod("sparse_direct", SolverSettings(tolerances={"residual_rtol": 1e-10}))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # SuperLU's MatrixRankWarning is not what this test asserts
        record = SciPyLinearProvider().execute(problem, method)
    assert record.convergence is ConvergenceState.FAILED
    assert "singular" in record.reason
    assert record.diagnostics.condition.status is not ConditioningStatus.WELL_CONDITIONED
    assert not record.outputs
