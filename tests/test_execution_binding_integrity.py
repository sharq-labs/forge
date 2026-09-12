"""A provenance binding must be authorised by the problem it claims to describe.

THE DEFECT
----------
``ExecutionBinding.from_execution`` promises, in its own docstring, that "the
model must be one the prepared problem actually names". It implemented that as::

    if named and model.key not in named:   # fails open on an empty `named`

so a problem naming NO models authorised every model in existence.
``ScientificProblem.models`` defaults to ``()``, so this is not an exotic state:
it is what any problem assembled without a model declaration carries.

WHY REFUSING IS THE RIGHT READING OF EMPTY
------------------------------------------
Nothing distinguishes a problem that deliberately imposes no constraint from one
that never declared its models. Inferring permission from an absent declaration
is the move this round removes everywhere else -- an undeclared component set
earns no independence, an undeclared required-output set earns no level -- and
this is that same rule at the provenance boundary. If an unconstrained binding
is ever wanted, it has to be asked for in the type rather than read out of a
missing field.

Checked against the tree before closing: every ``from_execution`` call on a live
path names a model its problem declares, so this refuses nothing that was
previously produced.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.results.provenance import ExecutionBinding
from engcore.scientific.solvers.protocol import SolverIdentity


class _Problem:
    def __init__(self, *models):
        self.models = tuple(models)


class _Prepared:
    def __init__(self, problem, solver=None):
        self.problem = problem
        self.solver = solver or SolverIdentity("solver.x", "1.0")


class _Raw:
    convergence = "converged"


AUTHORISED = ModelReference(model_id="declared.model", version="1")
UNAUTHORISED = ModelReference(model_id="a.model.nobody.declared", version="9")


def test_a_problem_that_names_no_models_authorises_none():
    """The fail-open, closed. Empty is a refusal, not a wildcard."""
    with pytest.raises(ScientificCoreError) as raised:
        ExecutionBinding.from_execution(
            _Prepared(_Problem()), _Raw(), model=UNAUTHORISED
        )
    message = str(raised.value)
    assert "names no models" in message
    assert "not a permission" in message


def test_an_empty_declaration_does_not_even_authorise_a_plausible_model():
    """Emptiness cannot be read as permission, however reasonable the model.

    The sharpest form: there is exactly one model anybody could have meant, and
    the problem still never said so. A record that guessed here would be
    stating a relation its author did not.
    """
    with pytest.raises(ScientificCoreError):
        ExecutionBinding.from_execution(
            _Prepared(_Problem()), _Raw(), model=AUTHORISED
        )


def test_a_declared_model_still_binds():
    """The path every live caller takes, asserted so the refusal is not blanket."""
    binding = ExecutionBinding.from_execution(
        _Prepared(_Problem(AUTHORISED)), _Raw(), model=AUTHORISED
    )
    assert binding.model == AUTHORISED
    assert binding.solver == SolverIdentity("solver.x", "1.0")
    assert binding.realization is None


def test_a_model_the_problem_did_not_name_is_still_refused():
    """The half that already worked, kept exercised."""
    with pytest.raises(ScientificCoreError) as raised:
        ExecutionBinding.from_execution(
            _Prepared(_Problem(AUTHORISED)), _Raw(), model=UNAUTHORISED
        )
    assert "does not name model" in str(raised.value)


def test_the_solver_identity_is_still_read_off_the_execution():
    """Unchanged by this fix, and load-bearing: a binding cannot name another solver."""
    prepared = _Prepared(_Problem(AUTHORISED), SolverIdentity("solver.real", "2.0"))
    binding = ExecutionBinding.from_execution(prepared, _Raw(), model=AUTHORISED)
    assert binding.solver == SolverIdentity("solver.real", "2.0")

    with pytest.raises(ScientificCoreError):
        ExecutionBinding.from_execution(
            _Prepared(_Problem(AUTHORISED), solver="not-an-identity"),
            _Raw(),
            model=AUTHORISED,
        )
    with pytest.raises(ScientificCoreError):
        ExecutionBinding.from_execution(
            _Prepared(_Problem(AUTHORISED)), object(), model=AUTHORISED
        )


def test_a_binding_constructed_directly_is_unaffected():
    """The escape hatch the refusal points at, asserted to exist.

    `from_execution` is the constructor that checks authorisation against a
    prepared problem. A caller who knows the association some other way builds
    the record directly -- and that is a visibly different act, which is the
    point.
    """
    binding = ExecutionBinding(
        model=UNAUTHORISED, solver=SolverIdentity("solver.x", "1.0")
    )
    assert binding.model == UNAUTHORISED
