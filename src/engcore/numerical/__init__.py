"""Provider-neutral numerical execution (BIG 6).  Computes; holds no scientific authority."""

from .core import (
    NumericalAgreement, NumericalDiagnostics, NumericalExecutionRecord, NumericalMethod, NumericalProblem,
    NumericalProvider, NumericalRefusal, OperatorIdentity, ProblemKind, ProviderUnavailable, UnitBoundary,
    VariableSpec, array_digest, compare_executions, to_raw_solver_output,
)
from .providers import (
    NumPyDenseLinearProvider, PETScLinearProvider, SciPyLinearProvider, SciPyMinimizeProvider,
    SciPyODEProvider, SciPyRootProvider, SundialsProvider,
)
from .symbolic import SymbolicSystem

__all__ = [
    "NumericalAgreement", "NumericalDiagnostics", "NumericalExecutionRecord", "NumericalMethod", "NumericalProblem",
    "NumericalProvider", "NumericalRefusal", "OperatorIdentity", "ProblemKind", "ProviderUnavailable", "UnitBoundary",
    "VariableSpec", "array_digest", "compare_executions", "to_raw_solver_output",
    "NumPyDenseLinearProvider", "PETScLinearProvider", "SciPyLinearProvider", "SciPyMinimizeProvider",
    "SciPyODEProvider", "SciPyRootProvider", "SundialsProvider", "SymbolicSystem",
]
