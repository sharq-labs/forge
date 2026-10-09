"""Design grammar, compatibility rules and three-valued constraint evaluation.

A :class:`DesignGrammar` states which COMBINATIONS of choices are admissible
before anything is evaluated: "a hexacopter frame requires six motor mounts",
"a sealed housing excludes air cooling".  Rules are typed records over
design-variable values -- never executable code -- and the grammar is a
:class:`~.generation.ProposalGate`, so it plugs into the existing D2
generation boundary unchanged.

:func:`evaluate_constraints` checks declared constraints against measured
metrics with THREE outcomes: SATISFIED, VIOLATED, UNKNOWN.  A metric that is
absent is UNKNOWN; it is never read as satisfied, and a candidate with an
UNKNOWN constraint is not feasible -- it is undetermined.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.constraints import ConstraintCheck, ConstraintDefinition
from ..scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue, ScientificValue
from ..scientific.units.quantity import Quantity
from .generation import CandidateProposal, ProposalDecision
from .space import DesignSpace

DESIGN_GRAMMAR_SCHEMA = "engcore.design.grammar/1"


class RuleKind(str, Enum):
    REQUIRES = "requires"   # if <var> in <values> then <other> must be in <other_values>
    EXCLUDES = "excludes"   # if <var> in <values> then <other> must NOT be in <other_values>


def _plain(value: ScientificValue) -> Any:
    if isinstance(value, (CategoricalValue, IntegerValue, BooleanValue)):
        return value.value
    raise InvalidScientificProblem("compatibility rules range over categorical, integer or boolean choices only")


@dataclass(frozen=True)
class CompatibilityRule:
    rule_id: str
    kind: RuleKind
    variable: str
    values: tuple[Any, ...]
    other: str
    other_values: tuple[Any, ...]
    rationale: str

    def __post_init__(self) -> None:
        for label in ("rule_id", "variable", "other", "rationale"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"compatibility rule requires {label}")
        object.__setattr__(self, "kind", RuleKind(self.kind))
        if self.variable == self.other:
            raise InvalidScientificProblem(f"rule {self.rule_id!r} relates a variable to itself")
        if not self.values or not self.other_values:
            raise InvalidScientificProblem(f"rule {self.rule_id!r} needs trigger and consequence values")
        object.__setattr__(self, "values", tuple(sorted(set(self.values), key=repr)))
        object.__setattr__(self, "other_values", tuple(sorted(set(self.other_values), key=repr)))

    def violated_by(self, assignment: Mapping[str, ScientificValue]) -> bool:
        if _plain(assignment[self.variable]) not in self.values:
            return False
        inside = _plain(assignment[self.other]) in self.other_values
        return not inside if self.kind is RuleKind.REQUIRES else inside

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "kind": self.kind.value, "variable": self.variable, "values": list(self.values),
                "other": self.other, "other_values": list(self.other_values), "rationale": self.rationale}


@dataclass(frozen=True)
class DesignGrammar:
    """Admissible combinations over one exact design space.  Also a D2 ProposalGate."""

    grammar_id: str
    space: DesignSpace
    rules: tuple[CompatibilityRule, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.space, DesignSpace):
            raise InvalidScientificProblem("a design grammar ranges over one DesignSpace")
        rules = tuple(sorted(self.rules, key=lambda r: r.rule_id))
        if len({r.rule_id for r in rules}) != len(rules):
            raise InvalidScientificProblem("rule ids must be unique")
        vmap = self.space.variable_map
        for r in rules:
            for name in (r.variable, r.other):
                if name not in vmap:
                    raise InvalidScientificProblem(f"rule {r.rule_id!r} names undeclared variable {name!r}")
                if vmap[name].kind.value == "continuous":
                    raise InvalidScientificProblem(f"rule {r.rule_id!r} ranges over continuous {name!r}; express that as a constraint")
            v = vmap[r.variable]
            if v.kind.value == "categorical" and set(r.values) - set(v.categories):
                raise InvalidScientificProblem(f"rule {r.rule_id!r} names categories that {r.variable!r} does not declare")
        object.__setattr__(self, "rules", rules)

    @property
    def constraint_refs(self) -> tuple[str, ...]:
        return tuple(f"{self.grammar_id}:{r.rule_id}" for r in self.rules)

    def violations(self, assignment: Mapping[str, ScientificValue]) -> tuple[str, ...]:
        checked = self.space.validate_assignments(assignment)
        return tuple(f"{r.rule_id}: {r.rationale}" for r in self.rules if r.violated_by(checked))

    def decide(self, proposal: CandidateProposal) -> ProposalDecision:
        bad = self.violations(proposal.assignments)
        return ProposalDecision(False, bad) if bad else ProposalDecision(True, ())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": DESIGN_GRAMMAR_SCHEMA, "grammar_id": self.grammar_id, "space": list(self.space.reference.key),
                "rules": [r.to_dict() for r in self.rules]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


class ConstraintStatus(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConstraintOutcome:
    constraint: str
    status: ConstraintStatus
    check: ConstraintCheck | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"constraint": self.constraint, "status": self.status.value, "check": None if self.check is None else self.check.to_dict(),
                "reason": self.reason}


@dataclass(frozen=True)
class ConstraintEvaluation:
    outcomes: tuple[ConstraintOutcome, ...]

    @property
    def feasible(self) -> bool | None:
        """True only if every constraint is SATISFIED; False if any is VIOLATED; None (undetermined) otherwise."""
        states = {o.status for o in self.outcomes}
        if ConstraintStatus.VIOLATED in states:
            return False
        if ConstraintStatus.UNKNOWN in states:
            return None
        return True

    @property
    def violated(self) -> tuple[str, ...]:
        return tuple(o.constraint for o in self.outcomes if o.status is ConstraintStatus.VIOLATED)

    @property
    def unknown(self) -> tuple[str, ...]:
        return tuple(o.constraint for o in self.outcomes if o.status is ConstraintStatus.UNKNOWN)

    def to_dict(self) -> dict[str, Any]:
        return {"feasible": self.feasible, "outcomes": [o.to_dict() for o in self.outcomes]}


def evaluate_constraints(constraints: Iterable[ConstraintDefinition], metrics: Mapping[str, Quantity]) -> ConstraintEvaluation:
    """Three-valued feasibility.  A missing metric is UNKNOWN, never satisfied."""
    out = []
    for c in sorted(constraints, key=lambda c: c.name):
        if not isinstance(c, ConstraintDefinition):
            raise InvalidScientificProblem("constraints must be ConstraintDefinition records")
        value = metrics.get(c.metric)
        if value is None:
            out.append(ConstraintOutcome(c.name, ConstraintStatus.UNKNOWN, reason=f"metric {c.metric!r} was not produced"))
            continue
        check = c.check(value)
        out.append(ConstraintOutcome(c.name, ConstraintStatus.SATISFIED if check.satisfied else ConstraintStatus.VIOLATED, check))
    return ConstraintEvaluation(tuple(out))
