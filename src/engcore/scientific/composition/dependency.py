"""One quantity supplied by another — the directed dependency between problems.

A problem states what is to be computed. It does not state where its externally
imposed inputs come from, and for a single problem that is right: a control is
imposed, and by what is not the problem's business.

The moment two problems are composed it stops being right. Then there is a fact
with no home:

    the quantity named X, of problem P, supplies the quantity named Y of
    problem Q

Without it that fact survives only in an orchestration function's control flow,
which no record contains and no validator can read.

Why this is not a field on something that already exists
--------------------------------------------------------
``ScientificProblem``
    A composition fact is not part of what a problem asks. It also would force
    a schema version bump on the most widely written record in the platform,
    and ``require_schema`` is an exact string match: every stored payload would
    become unreadable by a pre-milestone reader. This record is standalone and
    additive, and **no existing schema version moves because of it**.

``ScientificModelDefinition``
    Worse than costly — wrong. A model is a reusable claim. Recording on it
    that its input is supplied by some other model would make the same claim,
    fed from a different source in a different system, a different model. The
    supplier is a property of the assembly, never of the science.

``ScientificTwin``
    A ``TwinDatum`` holds a typed *value*. Encoding a relation between two
    named quantities inside a value would be a string convention, which is the
    thing this record exists to avoid. The twin remains the sole authority for
    instance state, and this record holds no state at all.

``ProvenanceRecord``
    The decisive one. Provenance exists only *after* a run. A composition must
    be inspectable *before* anything executes — that is what a planner or
    validator reads. A representation that cannot exist before the run is not
    the representation.

What it deliberately does not carry
-----------------------------------
No value, no state, no solver, no backend, no tolerance, no mapping, no
interpolation, no coordinate transform, no relaxation factor, no convergence
criterion, no schedule and no execution order. Every one of those belongs to a
coupling *runtime*, and this is a *declaration*. A record that carried them
would have decided the shape of a coupling engine on the evidence of one
consumer.

It also carries no direction flag: ``source`` and ``target`` are the direction.
A dependency is causal and one-way, which is exactly the information a first
composition needs; a bidirectional physical connector with potential and flow
semantics is a different and much larger contract, and nothing here forecloses
it.

Names are references, not conventions
-------------------------------------
``source_quantity`` and ``target_quantity`` are names **into namespaces the
referenced records already enumerate** — a problem lists its variables and
parameters, a result lists its metrics. This record never parses a name's
internal structure and never infers meaning from its shape, exactly as
``InitialCondition.variable`` names a variable and ``ObjectiveDefinition.metric``
names a metric. Referencing an enumerated name is not a string convention;
deducing physics from the characters in it would be.

Endpoint resolution, and the invariant it depends on
----------------------------------------------------
An endpoint name resolves into

    ``result.values``  ∪  ``problem.variables``  ∪  ``problem.parameters``

**A name that resolves in more than one of those is a defect this record does
not arbitrate.** ``ScientificProblem`` guarantees uniqueness across variables
and parameters; result metrics are a third namespace with no such guarantee
against them, so the invariant a composing domain must hold is:

    one name means one thing, across a problem's declarations *and* the
    metrics of results computed from it.

``ScientificResult`` already enforces exactly this inside its own record — a
name may not be both a scalar value and a bulk reference. This is the same rule
one level out, and it is stated rather than enforced because enforcing it would
require this record to hold both sides, which it deliberately does not.

Violating it is silently harmful when the two meanings share a dimension. A
STATE variable holds its value at the start of an interval and an output metric
of the same name holds its value at the end; both carry the same unit, both
check clean, and nothing says which of the two an endpoint denoted. For a
transient composition the time level of the transported quantity is the whole
semantic content, so a dimension check cannot be the thing that protects it.

``ScientificResult.data_references`` is deliberately **not** consulted. A bulk
reference carries a name and a unit, so consulting it would make a field
endpoint check clean — while nothing in this record can state how a field is
transported between two supports. An honest ``MISSING`` is better than a clean
check that implies a transfer semantics no contract provides. Field endpoints
wait for the milestone that can describe them.

Absence is meaningful
---------------------
An externally imposed input with **no** dependency record is externally
imposed by the environment, and that is a complete answer rather than a
missing one. Nothing here infers a supplier for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..errors import InvalidScientificProblem
from ..models.definition import BindingIssue, BindingIssueKind
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from ..units.validation import require_unit

QUANTITY_DEPENDENCY_SCHEMA = schema_string("quantity_dependency")

__all__ = [
    "QUANTITY_DEPENDENCY_SCHEMA",
    "QuantityDependency",
    "externally_imposed",
    "unresolved_inputs",
]


@dataclass(frozen=True)
class QuantityDependency:
    """``target_problem.target_quantity`` is supplied by
    ``source_problem.source_quantity``.

    ``unit_exemplar`` names the *dimension* the transported quantity carries.
    It is checked by dimensionality and never by unit string, so a source in
    ``degC`` satisfies a dependency declared in ``kelvin`` and one in volts
    does not. It is what makes this record a scientific statement rather than
    a pair of strings: a wiring error between two quantities of different
    dimension is refused by :meth:`check_against` instead of surviving into a
    run.
    """

    source_problem_id: str
    source_quantity: str
    target_problem_id: str
    target_quantity: str
    unit_exemplar: str
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        for label in (
            "source_problem_id",
            "source_quantity",
            "target_problem_id",
            "target_quantity",
        ):
            raw = str(getattr(self, label)).strip()
            if not raw:
                raise InvalidScientificProblem(
                    f"quantity dependency requires a non-empty {label}"
                )
            object.__setattr__(self, label, raw)

        object.__setattr__(
            self,
            "unit_exemplar",
            require_unit(
                self.unit_exemplar,
                context=(
                    f"quantity dependency "
                    f"{self.source_quantity!r} -> {self.target_quantity!r}"
                ),
            ),
        )

        if (
            self.source_problem_id == self.target_problem_id
            and self.source_quantity == self.target_quantity
        ):
            raise InvalidScientificProblem(
                f"quantity dependency {self.source_quantity!r} supplies "
                f"itself in problem {self.source_problem_id!r}; a quantity "
                f"cannot be its own source"
            )

    # A ``key`` property was written here and deleted during the adversarial
    # pass: nothing read it, and no collection type exists that would dedup or
    # order these records. An identity accessor that no caller uses is a
    # guess about a future collection contract, and this milestone has no
    # evidence for one.

    @property
    def dimension(self) -> str:
        return dimensionality(self.unit_exemplar)

    # ---- checking ------------------------------------------------------
    def check_against(
        self,
        *,
        target_problem: Any = None,
        source_problem: Any = None,
        source_result: Any = None,
    ) -> tuple[BindingIssue, ...]:
        """Report why this dependency does not fit the records it names.

        Returns issues; an empty tuple means every check that could be run
        passed. It **decides nothing** and resolves nothing — reading a value
        across is execution, and execution is not this record's business.

        Reuses :class:`BindingIssue` rather than minting a parallel issue type:
        ``MISSING`` and ``WRONG_DIMENSION`` already mean here exactly what they
        mean when a model is checked against a problem.

        Every argument is optional because the two sides are knowable at
        different times. A **target** is checkable before anything runs — a
        problem enumerates its variables and parameters. A **source** may be a
        result metric, which does not exist until a solve has produced it. The
        asymmetry is real and is not papered over: passing nothing checks
        nothing and says so by returning no issues.

        ``source_result`` is a whole result rather than a bare mapping of
        values, so that the identity of what is being checked is *checkable*.
        A mapping would have made this an anonymous path: values from the wrong
        run would satisfy the check with nothing able to notice.
        """
        issues: list[BindingIssue] = []
        if target_problem is not None:
            issues.extend(
                self._check_side(
                    target_problem,
                    None,
                    self.target_problem_id,
                    self.target_quantity,
                    "target",
                )
            )
        if source_problem is not None or source_result is not None:
            issues.extend(
                self._check_side(
                    source_problem,
                    source_result,
                    self.source_problem_id,
                    self.source_quantity,
                    "source",
                )
            )
        return tuple(issues)

    def _check_side(
        self,
        problem: Any,
        result: Any,
        expected_problem_id: str,
        quantity: str,
        side: str,
    ) -> list[BindingIssue]:
        issues: list[BindingIssue] = []

        for record, label in ((problem, "problem"), (result, "result")):
            if record is not None and record.problem_id != expected_problem_id:
                issues.append(
                    BindingIssue(
                        quantity,
                        BindingIssueKind.MISSING,
                        f"{side} names problem {expected_problem_id!r} but the "
                        f"supplied {label} states {record.problem_id!r}",
                    )
                )
                return issues

        values = result.values if result is not None else None
        unit = self._declared_unit(problem, values, quantity)
        if unit is None:
            issues.append(
                BindingIssue(
                    quantity,
                    BindingIssueKind.MISSING,
                    f"{side} problem {expected_problem_id!r} declares no "
                    f"variable, parameter or metric named {quantity!r}",
                )
            )
            return issues

        if dimensionality(unit) != self.dimension:
            issues.append(
                BindingIssue(
                    quantity,
                    BindingIssueKind.WRONG_DIMENSION,
                    f"{side} {quantity!r} carries {unit!r} "
                    f"[{dimensionality(unit)}] but the dependency transports "
                    f"{self.unit_exemplar!r} [{self.dimension}]",
                )
            )
        return issues

    @staticmethod
    def _declared_unit(
        problem: Any, values: Mapping[str, Quantity] | None, quantity: str
    ) -> str | None:
        """The unit a named quantity carries, or ``None`` if it is not declared.

        Resolution order is metrics, then variables, then parameters — and it
        is only *an* order, not an arbitration. See the module docstring: a
        name that resolves in more than one namespace is a defect in the
        composing domain, which this record reports on rather than resolves.
        """
        if values is not None and quantity in values:
            return values[quantity].units
        if problem is None:
            return None
        for variable in problem.variables:
            if variable.name == quantity:
                return variable.unit
        for parameter in problem.parameters:
            if parameter.name == quantity and isinstance(parameter.value, Quantity):
                return parameter.value.units
        return None

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QUANTITY_DEPENDENCY_SCHEMA,
            "source_problem_id": self.source_problem_id,
            "source_quantity": self.source_quantity,
            "target_problem_id": self.target_problem_id,
            "target_quantity": self.target_quantity,
            "unit_exemplar": self.unit_exemplar,
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityDependency":
        require_schema(payload, QUANTITY_DEPENDENCY_SCHEMA)
        return cls(
            source_problem_id=payload["source_problem_id"],
            source_quantity=payload["source_quantity"],
            target_problem_id=payload["target_problem_id"],
            target_quantity=payload["target_quantity"],
            unit_exemplar=payload["unit_exemplar"],
            name=payload.get("name", ""),
            description=payload.get("description", ""),
        )


def unresolved_inputs(problems: Iterable[Any]) -> tuple[tuple[str, str, str], ...]:
    """Quantities a problem needs and does not itself supply.

    ``(problem_id, quantity_name, unit)`` for every ``CONTROL`` variable, and
    for every ``STATE`` variable that **no declared condition determines** —
    neither an initial condition nor a boundary condition. Both are typed facts
    already on the record: a control is imposed from outside by definition, and
    a state that no condition pins has no value to start from.

    Boundary conditions are consulted deliberately. An earlier form of this
    function tested only for an initial condition, which silently encoded the
    shape of one initial-value problem into universal core: a steady-state or
    boundary-value problem whose state is fixed by Dirichlet conditions would
    have been reported as needing an external supplier, and
    :func:`externally_imposed` would then have called it environment-imposed.
    That was a false positive produced by a core reader, and it is the kind of
    leak a scan for domain vocabulary cannot see.

    This is the set a composition has to account for. It is **not** the set of
    dependencies: a control legitimately supplied by the environment appears
    here and correctly has no dependency record.

    It is also **not complete**, and the incompleteness is a finding rather
    than a defect to hide. A quantity a domain models as a configured
    ``ScientificParameter`` carries a value, so it reads as resolved even when
    a composition in fact supplies it. Nothing in the contracts distinguishes
    "configured" from "computed elsewhere", so no reader can recover that case;
    only an explicit :class:`QuantityDependency` can state it.
    """
    from ..ir.variables import VariableRole

    found: list[tuple[str, str, str]] = []
    for problem in problems:
        determined = {c.variable for c in problem.initial_conditions}
        determined |= {c.variable for c in problem.boundary_conditions}
        for variable in problem.variables:
            if variable.role is VariableRole.CONTROL or (
                variable.role is VariableRole.STATE
                and variable.name not in determined
            ):
                found.append((problem.problem_id, variable.name, variable.unit))
    return tuple(found)


def externally_imposed(
    problems: Iterable[Any], dependencies: Iterable[QuantityDependency]
) -> tuple[tuple[str, str, str], ...]:
    """Unresolved inputs that no dependency supplies.

    The complement of the declared dependencies. These are imposed by the
    environment, and an empty result does not mean a system is closed — it
    means every input this reader could *see* has a supplier.
    """
    targets = {
        (d.target_problem_id, d.target_quantity) for d in dependencies
    }
    return tuple(
        entry
        for entry in unresolved_inputs(problems)
        if (entry[0], entry[1]) not in targets
    )
