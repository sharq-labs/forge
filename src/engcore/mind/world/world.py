"""The ScientificWorld: a read-only, content-addressed reasoning view over declared and authoritative records.

A world is a VIEW.  It holds the problem's declared variables (each carrying its reused repsem role declaration and,
if it has a current value, the owner record the value is bound to), the protocol's declared actions, constraints and
observation channels, the model records whose applicability gates model execution, verbatim provider status and
health reports, the budget as its owner records state it, and typed references to the records it summarizes.  It
authors no state, evidence, applicability verdict, hypothesis status or uncertainty: it computes no value, it fills
no gap, and every missing item stays missing.

Identity.  ``content_digest`` covers the material fields only (CORE_FREEZE_POLICY §6: labels and descriptions are not
material).  ``revision_id`` binds that content to its lineage (revision number, parent revision, changed fields).  The
narrative ``reason`` of a revision is recorded but is not identity, as ``TwinRevision`` excludes its change note.
A world is frozen; a material change is a new revision made by :meth:`ScientificWorld.derive`, which computes the
changed fields itself and refuses a revision that changes nothing.  :func:`verify_lineage` re-derives a chain.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from engcore.execution.orchestration.resources import ResourceBudget, ResourceUsage
from engcore.mind.repsem.roles import RoleRefused, RoleSource, RoleTable, VariableRole
from engcore.providers.catalog import Availability
from engcore.providers.health import HEALTH_SCHEMA, ProviderHealth, ProviderHealthReport
from engcore.providers.identity import content_digest
from engcore.scientific import ExperimentBudget, Quantity, ScientificCoreError, ScientificModelDefinition
from engcore.scientific.ir.values import as_context_value
from engcore.scientific.units.quantity import is_ratio_scale
from engcore.sria.campaign.budget import BudgetLedger
from engcore.scientific.results.immutable import detach, freeze
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.recommendation import BudgetPlan

from .actions import ActionSpec
from .authority import BINDING_SCHEMA, AuthorityBinding, OwnerKind, projection_digest
from .base import (
    HEX64, SOFTWARE_VERSION, RecordKind, RecordRef, WorldRefused, converts, digest, expect_schema, schema, text,
)
from .domains import ALL_ACTIONS, DeclaredConstraint, declared_source, membership
from .variables import (
    CHANNEL_ROLES, CONTROLLABILITY_BY_ROLE, Controllability, Entity, Observability, ObservationChannel, ValueOrigin,
    WorldVariable, value_projection,
)

WORLD_SCHEMA = schema("scientific_world")
APPLICABILITY_SCHEMA = schema("applicability_binding")
PROVIDER_SCHEMA = schema("provider_snapshot")
BUDGET_SCHEMA = schema("budget")
LINEAGE_SCHEMA = schema("lineage")
#: GEN2-BR1.1 (version decision): a lineage that records what its ancestors bound (``Lineage.bound``) is written as
#: version 2; one that records none is written, and reads, exactly as version 1 (BR1's records keep their bytes and
#: their revision ids).  ``verify_lineage`` checks a version-1 link by walking the store instead of the record.
LINEAGE_SCHEMA_V2 = schema("lineage", 2)

#: The fields a revision may change; each is material.  ``world_id`` names the world and never changes.
MATERIAL_FIELDS = ("actions", "applicability", "basis", "budget", "channels", "constraints", "declaration",
                   "declared_by", "entities", "providers", "references", "unit_registry", "variables")
#: Material fields that enter identity only when set, so a world that states none of them keeps its BR1 identity.
OPTIONAL_FIELDS = ("declaration", "unit_registry")


def _binding_identity(binding: AuthorityBinding | None) -> Any:
    return None if binding is None else {"schema": BINDING_SCHEMA, **binding.identity()}


def _binding_from(payload: Any) -> AuthorityBinding | None:
    return None if payload is None else AuthorityBinding.from_dict(payload)


def _require_binding(binding: Any, kind: OwnerKind, fields: tuple[str, ...], projected: Mapping[str, Any],
                     what: str) -> None:
    """A projected record's binding: the right owner, exactly these fields, and exactly this projection."""
    if binding is None:
        return
    if type(binding) is not AuthorityBinding or binding.owner_kind is not kind or binding.fields != fields:
        raise WorldRefused(f"{what}: bound to a {kind.value} owner record projecting exactly {fields}")
    if projection_digest(projected) != binding.projection:
        raise WorldRefused(f"{what}: the held record differs from what its authority binding projected")


#: Roles whose current value may enter a model-applicability context.  A latent parameter, a measurement or a derived
#: quantity is never a caller-declared fact about where a model is applied (Gen1 repsem refuses the same roles).
APPLICABILITY_CONTEXT_ROLES = frozenset({VariableRole.CONTROLLED_INPUT, VariableRole.FIXED_PROTOCOL_CONDITION,
                                         VariableRole.STATE_VARIABLE, VariableRole.NUISANCE_VARIABLE})
#: Roles a declared constraint may read: what an action sets or holds, the state, and the passive environment.
CONSTRAINT_ROLES = APPLICABILITY_CONTEXT_ROLES

BUDGET_DIMENSIONS = ("cost", "experiments", "solver_calls", "wall_time")


# ---- model applicability (the core owner, consulted, never re-implemented) ------------------------------------------------
@dataclass(frozen=True)
class ApplicabilityBinding:
    """A model record whose validity domain gates the actions that execute it.

    Evaluated only by ``ScientificModelDefinition.assess_validity(declared=..., record_values=True)``, so the verdict
    carries the model id and version.  The world does not author the domain: it carries the model record it was
    handed.  It gates MODEL_EXECUTION actions; for a SYSTEM_QUERY it is an annotation only."""

    model: ScientificModelDefinition
    authority: AuthorityBinding | None = None          # the model registry record it is a projection of

    def __post_init__(self) -> None:
        if type(self.model) is not ScientificModelDefinition:
            raise WorldRefused("an applicability binding carries exactly the ScientificModelDefinition that owns the "
                               "domain (a subclass could assess differently)")
        _require_binding(self.authority, OwnerKind.MODEL_RECORD, ("model",), {"model": self.model.to_dict()},
                         f"applicability {self.binding_id!r}")

    @property
    def binding_id(self) -> str:
        return f"{self.model.model_id}@{self.model.version}"

    @property
    def reads(self) -> frozenset[str]:
        validity = self.model.validity
        return frozenset(validity.context_keys) - frozenset(validity.derived_quantities)

    def assess(self, declared: Mapping[str, Any]):
        values = {k: as_context_value(v) for k, v in sorted(declared.items()) if k in self.reads}
        return self.model.assess_validity(declared=values, record_values=True)

    def identity(self) -> dict[str, Any]:
        out = {"binding_id": self.binding_id, "model_digest": digest(self.model.to_dict())}
        if self.authority is not None:
            out["authority"] = _binding_identity(self.authority)
        return out

    def to_dict(self) -> dict[str, Any]:
        out = {"schema": APPLICABILITY_SCHEMA, "model": self.model.to_dict()}
        if self.authority is not None:
            out["authority"] = self.authority.to_dict()
        return out

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ApplicabilityBinding":
        expect_schema(payload.get("schema"), APPLICABILITY_SCHEMA)
        return cls(ScientificModelDefinition.from_dict(payload["model"]), _binding_from(payload.get("authority")))


# ---- provider snapshots: the providers' own records, verbatim ---------------------------------------------------------------
@dataclass(frozen=True)
class ProviderSnapshot:
    """A provider's ``ProviderStatus.to_dict()`` and ``ProviderHealthReport.to_dict()``, embedded verbatim.

    Replayable where a live probe is not.  Construction re-derives the report's status digest by the owner's rule
    (``content_digest`` of the status minus its location) and refuses a pair that does not belong together."""

    status: Mapping[str, Any]
    report: Mapping[str, Any]
    authority: AuthorityBinding | None = None          # the provider registry status it is a projection of

    def __post_init__(self) -> None:
        if not isinstance(self.status, Mapping) or not isinstance(self.report, Mapping):
            raise WorldRefused("a provider snapshot embeds the status and health report records")
        if self.report.get("schema") != HEALTH_SCHEMA:
            raise WorldRefused(f"not a provider health report: {self.report.get('schema')!r}")
        try:
            pid = self.status["capability"]["provider_id"]
            Availability(self.status["availability"])
            ProviderHealth(self.report["health"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WorldRefused(f"malformed provider status or report: {exc}") from None
        if self.report.get("provider_id") != pid:
            raise WorldRefused(f"the health report is for {self.report.get('provider_id')!r}, the status for {pid!r}")
        expected = content_digest({k: v for k, v in detach(self.status).items() if k != "location"})
        if self.report.get("status_digest") != expected:
            raise WorldRefused(f"provider {pid!r}: the report's status digest does not match this status")
        _require_binding(self.authority, OwnerKind.PROVIDER_STATUS, ("report", "status"),
                         {"status": detach(self.status), "report": detach(self.report)}, f"provider {pid!r}")
        if self.authority is not None and self.authority.record_id != pid:
            raise WorldRefused(f"provider {pid!r}: bound to the status of {self.authority.record_id!r}")
        object.__setattr__(self, "status", freeze(detach(self.status)))
        object.__setattr__(self, "report", freeze(detach(self.report)))

    @classmethod
    def from_status(cls, status: Any, report: Any) -> "ProviderSnapshot":
        return cls(status.to_dict(), report.to_dict())

    @property
    def provider_id(self) -> str:
        return self.status["capability"]["provider_id"]

    @property
    def version(self) -> str:
        return self.status.get("version", "")

    @property
    def build_digest(self) -> str:
        return self.status.get("digest", "")

    @property
    def availability(self) -> Availability:
        return Availability(self.status["availability"])

    @property
    def health(self) -> ProviderHealth:
        return ProviderHealth(self.report["health"])

    @property
    def reason(self) -> str:
        return self.report.get("reason", "")

    @property
    def executable(self) -> bool:
        """The owner's rule, read from the owner's record rebuilt from its embedded payload."""
        r = self.report
        report = ProviderHealthReport(r["provider_id"], ProviderHealth(r["health"]), r.get("reason", ""),
                                      r["status_digest"], tuple(r.get("requested_scope", ())),
                                      r.get("qualification_digest", ""), r.get("probe_digest", ""))
        return self.availability is Availability.AVAILABLE and report.executable

    def identity(self) -> dict[str, Any]:
        out = {"schema": PROVIDER_SCHEMA, "status": detach(self.status), "report": detach(self.report)}
        if self.authority is not None:
            out["authority"] = _binding_identity(self.authority)
        return out

    def to_dict(self) -> dict[str, Any]:
        out = {"schema": PROVIDER_SCHEMA, "status": detach(self.status), "report": detach(self.report)}
        if self.authority is not None:
            out["authority"] = self.authority.to_dict()
        return out

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProviderSnapshot":
        expect_schema(payload.get("schema"), PROVIDER_SCHEMA)
        return cls(payload["status"], payload["report"], _binding_from(payload.get("authority")))


# ---- budget: owner records, every dimension declared ---------------------------------------------------------------------------
STATEMENT_SCHEMA = schema("budget_statement")
#: The unit a ledger stating a dimension must account in (convertible by the unit owner): a duration for wall time, a
#: count (exactly dimensionless: a count is never rescaled, so not percent) for solver calls.  A cost ledger accounts
#: in any unit the unit owner knows into which the declaration's stated cost unit (``BudgetSource.unit``) converts;
#: cost amounts are converted, never read raw.  An amount is a quantity whose zero means none of it, so every ledger
#: and declared cost unit is ratio-scale (``is_ratio_scale``): on an offset scale a conversion moves an amount's zero.
LEDGER_UNIT_FITS = {"wall_time": "second", "solver_calls": "dimensionless"}
#: Which owner states which budget dimension, and the fields each projection carries.
STATEMENT_OWNERS = {"ledger": (OwnerKind.BUDGET_LEDGER, ("ledger",)),
                    "experiment": (OwnerKind.EXPERIMENT, ("accounting", "budget"))}


@dataclass(frozen=True)
class BudgetStatement:
    """One budget dimension exactly as its owner record states it now: a projection bound to that record.

    A ledger dimension is decided by the owner's own rule (``BudgetLedger.affordable``) on the amount converted into
    the ledger's unit by the unit owner; one ledger states one dimension.  The observation dimension is decided on the
    experiment's projected accounting by the rule ``ScientificExperiment.record`` enforces (remaining observations and
    the attempt cap): the experiment owner exposes no affordability query, so the rule is restated here and pinned to
    the owner by a differential test.  The world never counts or settles a budget."""

    dimension: str
    kind: str
    payload: Mapping[str, Any]
    authority: AuthorityBinding
    unit: str = ""                     # cost: the unit the declaration states its cost amounts in (declared content)

    def __post_init__(self) -> None:
        if self.dimension not in BUDGET_DIMENSIONS:
            raise WorldRefused(f"{self.dimension!r} is not a budget dimension {BUDGET_DIMENSIONS}")
        if self.kind not in STATEMENT_OWNERS or (self.kind == "experiment") != (self.dimension == "experiments"):
            raise WorldRefused(f"{self.dimension!r} is not stated by a {self.kind!r} owner")
        if not isinstance(self.payload, Mapping):
            raise WorldRefused("a budget statement carries its owner record's payload")
        kind, fields_ = STATEMENT_OWNERS[self.kind]
        payload = detach(dict(self.payload))
        if type(self.authority) is not AuthorityBinding:
            raise WorldRefused(f"budget {self.dimension!r}: a statement is bound to its owner record")
        _require_binding(self.authority, kind, fields_, payload, f"budget {self.dimension!r}")
        try:
            if self.kind == "ledger":
                owner = BudgetLedger.from_dict(payload["ledger"])
                try:
                    unit_ = Quantity(1.0, owner.cost_unit)
                except ScientificCoreError:
                    raise WorldRefused(f"budget {self.dimension!r}: the ledger accounts in {owner.cost_unit!r}, which "
                                       "the unit owner does not know (an amount in it cannot be converted)") from None
                fits = LEDGER_UNIT_FITS.get(self.dimension)
                if fits is not None and not converts(unit_, fits):
                    raise WorldRefused(f"budget {self.dimension!r}: a ledger stating it accounts in a unit convertible "
                                       f"to {fits!r} (the unit owner's rule), not {owner.cost_unit!r}")
                if not is_ratio_scale(unit_.units):
                    raise WorldRefused(f"budget {self.dimension!r}: the ledger accounts in {owner.cost_unit!r}, an "
                                       "offset scale on which an amount's zero is a convention (not an amount unit)")
                if self.dimension == "solver_calls" and unit_.units != "dimensionless":
                    raise WorldRefused(f"budget 'solver_calls': a count is accounted exactly in 'dimensionless', not "
                                       f"{owner.cost_unit!r} (a count is never rescaled)")
                if self.dimension == "cost":
                    if type(self.unit) is not str or not self.unit:
                        raise WorldRefused("a cost ledger statement carries the unit the declaration states its cost "
                                           "amounts in (an amount is never read in whatever unit the ledger uses)")
                    if not is_ratio_scale(Quantity(1.0, self.unit).units):
                        raise WorldRefused(f"budget 'cost': the declared cost unit {self.unit!r} is an offset scale")
                    if not converts(Quantity(1.0, self.unit), owner.cost_unit):
                        raise WorldRefused(f"budget 'cost': the declared cost unit {self.unit!r} does not convert into "
                                           f"the ledger's {owner.cost_unit!r} (the unit owner's rule)")
                elif self.unit:
                    raise WorldRefused(f"budget {self.dimension!r}: only a cost statement carries a declared unit")
            elif self.unit:
                raise WorldRefused("an experiment's observations are counts; no declared unit")
            else:
                ExperimentBudget.from_dict(payload["budget"])
                acc = payload["accounting"]
                for key in ("attempts", "observations", "failures", "remaining_observations"):
                    _count(acc[key], f"experiment accounting {key}", minimum=0)
        except (KeyError, TypeError, ValueError) as exc:
            raise WorldRefused(f"budget {self.dimension!r}: malformed owner record: {exc}") from None
        object.__setattr__(self, "payload", freeze(payload))

    def decide(self, requested: Any, family: Any) -> tuple[bool, Any, Any, str]:
        """(affordable, remaining, the amount as decided, what remaining is) by the owner's rule; nothing is clamped.
        Every amount is converted into the ledger's own unit by the unit owner: a duration as stated, a count as a
        dimensionless quantity, a cost (by the action's contract a plain number) in the unit the declaration states for
        cost.  The amount and the remainder the owner compared it with are returned in the ledger's unit (a VALIDATE
        action may draw on the validation reservation too; an experiment states which of its limits refused).  An amount
        the unit owner cannot convert is refused (``WorldRefused``), never compared raw."""
        payload = detach(self.payload)
        if self.kind == "ledger":
            owner = BudgetLedger.from_dict(payload["ledger"])
            if self.dimension == "cost":                   # a plain number in the DECLARED cost unit
                magnitude = requested.magnitude if isinstance(requested, Quantity) else float(requested)
                amount = Quantity(magnitude, self.unit)
            else:
                amount = requested if isinstance(requested, Quantity) else Quantity(float(requested), "dimensionless")
            if not converts(amount, owner.cost_unit):
                raise WorldRefused(f"an amount in {amount.units!r} does not convert into the ledger's "
                                   f"{owner.cost_unit!r} (the unit owner's rule)")
            accounted = Quantity(amount.magnitude_in(owner.cost_unit), owner.cost_unit)
            validate = family is not None and ActionFamily(family) is ActionFamily.VALIDATE
            pool, basis = ((owner.validation_pool + owner.general_pool, "validation_pool+general_pool") if validate
                           else (owner.general_pool, "general_pool"))
            return (owner.affordable(accounted.magnitude, family=family), Quantity(pool, owner.cost_unit), accounted,
                    basis)
        budget = ExperimentBudget.from_dict(payload["budget"])
        acc = payload["accounting"]
        remaining = acc["remaining_observations"]
        attempts_ok = budget.max_attempts is None or acc["attempts"] + requested <= budget.max_attempts
        if not attempts_ok:
            return False, budget.max_attempts - acc["attempts"], requested, "attempt_cap"
        return requested <= remaining, remaining, requested, "remaining_observations"

    def identity(self) -> dict[str, Any]:
        return {"schema": STATEMENT_SCHEMA, "dimension": self.dimension, "kind": self.kind,
                "payload": detach(self.payload), "authority": _binding_identity(self.authority),
                **({"unit": self.unit} if self.unit else {})}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": STATEMENT_SCHEMA, "dimension": self.dimension, "kind": self.kind,
                "payload": detach(self.payload), "authority": self.authority.to_dict(),
                **({"unit": self.unit} if self.unit else {})}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BudgetStatement":
        expect_schema(payload.get("schema"), STATEMENT_SCHEMA)
        return cls(payload["dimension"], payload["kind"], payload["payload"], AuthorityBinding.from_dict(
            payload["authority"]), payload.get("unit", ""))
def _count(value: Any, field_name: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise WorldRefused(f"{field_name} must be an int >= {minimum} (no bool, no float, no coercion), got {value!r}")
    return value


def _seconds(value: Any, field_name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise WorldRefused(f"{field_name} must be a finite non-negative number of seconds, got {value!r}")
    return float(value)


def _resource_payload(budget: ResourceBudget) -> dict[str, Any]:
    return {"max_wall_seconds": budget.max_wall_seconds, "max_function_evaluations": budget.max_function_evaluations}


@dataclass(frozen=True)
class WorldBudget:
    """The budget as its owner records state it.  Every dimension is LIMITED by a record or declared UNBOUNDED with a
    basis; a dimension that is neither is undeclared, and an action then cannot be shown affordable.

    * experiments: a raw observation count, type-checked here and then held as an ``ExperimentBudget`` (which would
      silently coerce 2.7 to 2 or True to 1); attempt caps are not tracked in BR1; with the observations already spent;
    * solver_calls and wall_time: an execution ``ResourceBudget`` (``max_function_evaluations`` is the solver-call
      limit, ``max_wall_seconds`` the wall-time limit) with its ``ResourceUsage``, whose amounts are restated in
      ``compute_spent`` (a usage record's fields default to 0, so an unstated usage would read as nothing used);
    * cost: a ``BudgetPlan`` (its validation-pool fence is called, never copied) in a stated cost unit, whose spent
      amounts are restated in ``cost_spent`` (a plan's spent fields default to 0.0, so an unstated spend would read as
      nothing spent).

    The spent amounts, and every LIMITED or UNBOUNDED declaration, are the owner's statement cited by ``authority``;
    the Mind never counts them, and a revision changes them only by citing the owner's newer statement."""

    experiments: int | None = None
    observations_spent: int | None = None
    compute: ResourceBudget | None = None
    compute_used: ResourceUsage | None = None
    cost: BudgetPlan | None = None
    cost_spent: tuple[float, float] | None = None
    cost_unit: str = ""
    unbounded: Any = ()
    authority: RecordRef | None = None
    compute_spent: tuple[float, int] | None = None
    statements: tuple[BudgetStatement, ...] = ()        # projected: each dimension bound to its owner record
    projected: bool = False                             # a projection of a declaration (unbounded is declared there)

    def __post_init__(self) -> None:
        statements = tuple(self.statements)
        if any(type(x) is not BudgetStatement for x in statements):
            raise WorldRefused("budget statements are BudgetStatement records")
        dims = [x.dimension for x in statements]
        if len(set(dims)) != len(dims):
            raise WorldRefused("a budget dimension is stated once")
        accounts = [(x.authority.owner_kind, x.authority.owner_id, x.authority.record_id) for x in statements]
        if len(set(accounts)) != len(accounts):
            raise WorldRefused("one budget account states one dimension: its owner decides on one pool, so two "
                               "dimensions drawn from it would each be checked against the whole of it")
        object.__setattr__(self, "statements", tuple(sorted(statements, key=lambda x: x.dimension)))
        if type(self.projected) is not bool:
            raise WorldRefused("projected is a bool")
        if self.projected and (self.experiments is not None or self.compute is not None or self.cost is not None
                               or self.authority is not None):
            raise WorldRefused("a projected budget is stated only by its owner records (no restated copies)")
        if statements and not self.projected:
            raise WorldRefused("owner budget statements belong to a projected budget")
        if self.experiments is not None:
            _count(self.experiments, "experiments (an observation count)", minimum=1)
            _count(self.observations_spent, "observations_spent", minimum=0)
        elif self.observations_spent is not None:
            raise WorldRefused("observations_spent without an experiment budget")
        if self.compute is not None:
            if not isinstance(self.compute, ResourceBudget) or not isinstance(self.compute_used, ResourceUsage):
                raise WorldRefused("a compute budget is a ResourceBudget with its ResourceUsage")
            if self.compute.max_cpu_seconds is not None or self.compute.max_peak_memory_bytes is not None:
                raise WorldRefused("only solver calls and wall time are BR1 budget dimensions")
            if self.compute.max_function_evaluations is not None:
                _count(self.compute.max_function_evaluations, "max_function_evaluations", minimum=1)
                _count(self.compute_used.function_evaluations, "function_evaluations used", minimum=0)
            if self.compute.max_wall_seconds is not None:
                _seconds(self.compute.max_wall_seconds, "max_wall_seconds")
                _seconds(self.compute_used.wall_seconds, "wall_seconds used")
            if self.compute.max_function_evaluations is None and self.compute.max_wall_seconds is None:
                raise WorldRefused("a compute budget limits solver calls or wall time")
            spent = self.compute_spent
            if (not isinstance(spent, tuple) or len(spent) != 2 or type(spent[0]) not in (int, float)
                    or type(spent[1]) is not int
                    or (float(spent[0]), spent[1]) != (self.compute_used.wall_seconds,
                                                       self.compute_used.function_evaluations)):
                raise WorldRefused("a compute budget restates its usage (compute_spent = (wall_seconds, "
                                   "function_evaluations)); an unstated usage would read as zero")
        elif self.compute_used is not None or self.compute_spent is not None:
            raise WorldRefused("compute usage without a compute budget")
        if self.cost is not None:
            if not isinstance(self.cost, BudgetPlan):
                raise WorldRefused("cost must be a BudgetPlan")
            text(self.cost_unit, "cost_unit (the cost budget states its unit)")
            spent = self.cost_spent
            if (not isinstance(spent, tuple) or len(spent) != 2
                    or tuple(float(x) for x in spent) != (self.cost.spent_general, self.cost.spent_validation)):
                raise WorldRefused("a cost budget restates its spent amounts (cost_spent = (general, validation)); "
                                   "an unstated spend would read as zero")
        elif self.cost_unit or self.cost_spent is not None:
            raise WorldRefused("cost_unit or cost_spent without a cost budget")
        pairs = tuple(sorted(dict(self.unbounded).items())) if not isinstance(self.unbounded, tuple) else tuple(
            sorted(self.unbounded))
        for dim, basis in pairs:
            if dim not in BUDGET_DIMENSIONS:
                raise WorldRefused(f"{dim!r} is not a budget dimension {BUDGET_DIMENSIONS}")
            text(basis, f"unbounded {dim!r} basis")
        object.__setattr__(self, "unbounded", pairs)
        both = set(self._limited()) & {d for d, _ in pairs}
        if both:
            raise WorldRefused(f"dimensions {sorted(both)} are both limited and unbounded")
        if not self.projected and (self._limited() or pairs) and not isinstance(self.authority, RecordRef):
            raise WorldRefused("a declared budget (limited or unbounded) cites the owner record that states it "
                               "(authority RecordRef)")

    @property
    def experiment_budget(self) -> ExperimentBudget | None:
        return None if self.experiments is None else ExperimentBudget(self.experiments)

    def _limited(self) -> tuple[str, ...]:
        out = []
        if self.experiments is not None:
            out.append("experiments")
        if self.compute is not None and self.compute.max_function_evaluations is not None:
            out.append("solver_calls")
        if self.compute is not None and self.compute.max_wall_seconds is not None:
            out.append("wall_time")
        if self.cost is not None:
            out.append("cost")
        out += [x.dimension for x in self.statements]
        return tuple(sorted(out))

    def statement(self, dimension: str) -> BudgetStatement | None:
        for x in self.statements:
            if x.dimension == dimension:
                return x
        return None

    def status(self, dimension: str) -> str:
        """'limited', 'unbounded' (declared, with a basis) or 'undeclared'."""
        if dimension in self._limited():
            return "limited"
        if dimension in {d for d, _ in self.unbounded}:
            return "unbounded"
        return "undeclared"

    def remaining(self, dimension: str) -> Any:
        """Signed remaining amount of a limited dimension (an overrun stays negative; nothing is clamped)."""
        if self.status(dimension) != "limited":
            return None
        if self.statement(dimension) is not None:
            return None                                   # the owner's rule states what remains (decide)
        if dimension == "experiments":
            return self.experiment_budget.max_observations - self.observations_spent
        if dimension == "solver_calls":
            return self.compute.max_function_evaluations - self.compute_used.function_evaluations
        if dimension == "wall_time":
            return float(self.compute.max_wall_seconds) - float(self.compute_used.wall_seconds)
        return self.cost.general_pool

    def identity(self) -> dict[str, Any]:
        out = self._payload()
        if self.statements:
            out["statements"] = [x.identity() for x in self.statements]
        return out

    def to_dict(self) -> dict[str, Any]:
        out = self._payload()
        if self.statements:
            out["statements"] = [x.to_dict() for x in self.statements]
        return out

    def _payload(self) -> dict[str, Any]:
        extra = {"projected": True} if self.projected else {}
        return {"schema": BUDGET_SCHEMA, **extra,
                "experiments": None if self.experiments is None else self.experiment_budget.to_dict(),
                "observations_spent": self.observations_spent,
                "compute": None if self.compute is None else _resource_payload(self.compute),
                "compute_used": None if self.compute_used is None else {
                    "wall_seconds": self.compute_used.wall_seconds,
                    "function_evaluations": self.compute_used.function_evaluations},
                "cost": None if self.cost is None else self.cost.to_dict(), "cost_unit": self.cost_unit,
                "unbounded": [list(p) for p in self.unbounded],
                "authority": None if self.authority is None else self.authority.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorldBudget":
        expect_schema(payload.get("schema"), BUDGET_SCHEMA)
        cost = payload.get("cost")
        if cost is not None and not {"spent_general", "spent_validation"} <= set(cost):
            raise WorldRefused("a cost budget states what was spent; a missing spent amount is never zero")
        experiments = payload.get("experiments")
        if experiments is not None and experiments.get("max_attempts") is not None:
            raise WorldRefused("an attempt cap is not tracked in BR1")
        compute = payload.get("compute")
        used = payload.get("compute_used")
        plan = None if cost is None else BudgetPlan.from_dict(cost)
        return cls(None if experiments is None else experiments["max_observations"], payload.get("observations_spent"),
                   None if compute is None else ResourceBudget(**compute),
                   None if used is None else ResourceUsage(wall_seconds=used["wall_seconds"],
                                                           function_evaluations=used["function_evaluations"]),
                   plan, None if plan is None else (cost["spent_general"], cost["spent_validation"]),
                   payload.get("cost_unit", ""), tuple((d, b) for d, b in payload.get("unbounded", ())),
                   None if payload.get("authority") is None else RecordRef.from_dict(payload["authority"]),
                   None if used is None else (used["wall_seconds"], used["function_evaluations"]),
                   tuple(BudgetStatement.from_dict(x) for x in payload.get("statements", ())),
                   payload.get("projected", False))


# ---- lineage --------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Lineage:
    revision: int = 0
    parent: str = ""
    reason: str = ""
    changed_fields: tuple[str, ...] = ()
    #: Every (owner-statement key, statement digest) an ANCESTOR bound: an owner reference never carries two values
    #: anywhere in a lineage, even across a revision that unbound it (README section 6, requirement 3).
    bound: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _count(self.revision, "revision", minimum=0)
        object.__setattr__(self, "changed_fields", tuple(sorted(self.changed_fields)))
        bound = tuple(tuple(p) for p in self.bound)
        if any(len(p) != 2 or any(type(x) is not str or not HEX64.match(x) for x in p) for p in bound) or \
                len({k for k, _ in bound}) != len(bound):
            raise WorldRefused("lineage bound statements are distinct (key, statement) 64-hex pairs")
        object.__setattr__(self, "bound", tuple(sorted(bound)))
        if self.revision == 0 and bound:
            raise WorldRefused("a root world has no ancestors and so no ancestor statements")
        if not isinstance(self.reason, str):
            raise WorldRefused("reason is text")
        if self.revision == 0:
            if self.parent or self.changed_fields:
                raise WorldRefused("a root world has no parent and no changed fields")
        else:
            if not isinstance(self.parent, str) or not HEX64.match(self.parent):
                raise WorldRefused("a revision names its parent revision id")
            text(self.reason, "a revision states its reason")
            if not self.changed_fields or set(self.changed_fields) - set(MATERIAL_FIELDS):
                raise WorldRefused(f"changed_fields must be a non-empty subset of {MATERIAL_FIELDS}")

    def identity(self) -> dict[str, Any]:
        out = {"revision": self.revision, "parent": self.parent, "changed_fields": list(self.changed_fields)}
        if self.bound:
            out["bound"] = [list(p) for p in self.bound]
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LINEAGE_SCHEMA_V2 if self.bound else LINEAGE_SCHEMA, **self.identity(), "reason": self.reason}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Lineage":
        found = payload.get("schema")
        if found == LINEAGE_SCHEMA and "bound" in payload:
            raise WorldRefused(f"a {LINEAGE_SCHEMA} record carries no bound statements (introduced with version 2)")
        if found == LINEAGE_SCHEMA_V2 and not payload.get("bound"):
            raise WorldRefused(f"a {LINEAGE_SCHEMA_V2} record states its ancestors' bound statements")
        if found not in (LINEAGE_SCHEMA, LINEAGE_SCHEMA_V2):
            expect_schema(found, LINEAGE_SCHEMA_V2)
        return cls(payload["revision"], payload["parent"], payload.get("reason", ""), tuple(payload["changed_fields"]),
                   tuple(tuple(p) for p in payload.get("bound", ())))


def _sorted_unique(items: Iterable[Any], key: Any, what: str, kind: type) -> tuple[Any, ...]:
    items = tuple(items)
    for item in items:
        if not isinstance(item, kind):
            raise WorldRefused(f"{what} must be {kind.__name__} records, got {type(item).__name__}")
    keyf = key if callable(key) else (lambda i: getattr(i, key))
    ids = [keyf(i) for i in items]
    if len(set(ids)) != len(ids):
        raise WorldRefused(f"{what} repeat an id: {sorted({i for i in ids if ids.count(i) > 1})}")
    return tuple(sorted(items, key=keyf))


# ---- the world --------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ScientificWorld:
    world_id: str
    variables: tuple[WorldVariable, ...]
    entities: tuple[Entity, ...] = ()
    constraints: tuple[DeclaredConstraint, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    channels: tuple[ObservationChannel, ...] = ()
    applicability: tuple[ApplicabilityBinding, ...] = ()
    providers: tuple[ProviderSnapshot, ...] = ()
    budget: WorldBudget = field(default_factory=WorldBudget)
    references: tuple[RecordRef, ...] = ()
    declared_by: RoleSource | None = None
    basis: str = ""
    lineage: Lineage = field(default_factory=Lineage)
    description: str = ""                                   # non-material
    declaration: AuthorityBinding | None = None             # the declaration in force this world is a projection of
    unit_registry: AuthorityBinding | None = None           # the sealed unit registry its quantities were read under
    _roles: Any = field(init=False, repr=False, compare=False, default=None)
    _content: str = field(init=False, repr=False, compare=False, default="")
    _revision: str = field(init=False, repr=False, compare=False, default="")

    def __post_init__(self) -> None:
        text(self.world_id, "world_id")
        object.__setattr__(self, "declared_by", declared_source(self.declared_by, f"world {self.world_id!r}"))
        text(self.basis, f"world {self.world_id!r} basis")
        variables = _sorted_unique(self.variables, "name", "variables", WorldVariable)
        if not variables:
            raise WorldRefused("a world declares its variables")
        object.__setattr__(self, "variables", variables)
        try:
            roles = RoleTable(tuple(v.declaration for v in variables))
        except RoleRefused as exc:
            raise WorldRefused(f"role table: {exc}") from None
        if roles.is_legacy:
            raise WorldRefused("a world is never built on the legacy adapter's inferred roles")
        object.__setattr__(self, "_roles", roles)
        declared = {v.name for v in variables}

        object.__setattr__(self, "entities", _sorted_unique(self.entities, "entity_id", "entities", Entity))
        for e in self.entities:
            if set(e.variables) - declared:
                raise WorldRefused(f"entity {e.entity_id!r} groups undeclared variables {sorted(set(e.variables) - declared)}")

        object.__setattr__(self, "channels", _sorted_unique(self.channels, "variable", "channels", ObservationChannel))
        for c in self.channels:
            if c.variable not in declared:
                raise WorldRefused(f"observation channel {c.variable!r} is not a declared variable")
            role = roles.role(c.variable)
            if role not in CHANNEL_ROLES:
                what = "a latent parameter is estimated" if role is VariableRole.LATENT_PARAMETER else \
                    "a derived quantity is computed, never an independent observation"
                raise WorldRefused(f"channel {c.variable!r}: {what}, never observed through a channel")
        for v in variables:
            if v.origin is ValueOrigin.OBSERVED and not self.has_channel(v.name):
                raise WorldRefused(f"{v.name!r}: an OBSERVED value needs a declared observation channel")

        object.__setattr__(self, "applicability", _sorted_unique(
            self.applicability, lambda a: a.binding_id, "applicability bindings", ApplicabilityBinding))
        for a in self.applicability:
            for name in sorted(a.reads):
                if name not in declared:
                    raise WorldRefused(f"applicability {a.binding_id!r} reads {name!r}, which the world does not declare")
                spec = next((i for i in a.model.inputs if i.name == name), None)
                exemplar = getattr(spec, "unit_exemplar", None)
                var = self.variable(name)
                if exemplar and not converts(Quantity(1.0, exemplar), var.unit):
                    raise WorldRefused(f"applicability {a.binding_id!r}: input {name!r} is in {exemplar!r}, the world "
                                       f"declares {var.unit!r}")

        object.__setattr__(self, "providers", _sorted_unique(self.providers, lambda p: p.provider_id, "providers",
                                                             ProviderSnapshot))
        if not isinstance(self.budget, WorldBudget):
            raise WorldRefused("budget must be a WorldBudget")
        refs = tuple(self.references)
        if any(not isinstance(r, RecordRef) for r in refs) or len(set(refs)) != len(refs):
            raise WorldRefused("references must be unique RecordRef records")
        object.__setattr__(self, "references", tuple(sorted(refs)))
        if not isinstance(self.lineage, Lineage):
            raise WorldRefused("lineage must be a Lineage record")
        if not isinstance(self.description, str):
            raise WorldRefused("description is text")
        for name, kind in (("declaration", OwnerKind.DECLARATION), ("unit_registry", OwnerKind.UNIT_REGISTRY)):
            b = getattr(self, name)
            if b is not None and (type(b) is not AuthorityBinding or b.owner_kind is not kind):
                raise WorldRefused(f"the world's {name} binding is an AuthorityBinding to the {kind.value} owner")

        object.__setattr__(self, "actions", _sorted_unique(self.actions, "action_id", "actions", ActionSpec))
        for a in self.actions:
            a.bind(self)
        action_ids = {a.action_id for a in self.actions}
        object.__setattr__(self, "constraints",
                           _sorted_unique(self.constraints, "constraint_id", "constraints", DeclaredConstraint))
        for c in self.constraints:
            self._check_constraint(c)
            unknown = set(c.applies_to) - action_ids - {ALL_ACTIONS}
            if unknown:
                raise WorldRefused(f"constraint {c.constraint_id!r} applies to undeclared actions {sorted(unknown)}")
        content = digest(self._material())
        object.__setattr__(self, "_content", content)
        object.__setattr__(self, "_revision", digest({"world_id": self.world_id, "content": content,
                                                      **self.lineage.identity()}))

    # ---- construction checks ------------------------------------------------------------------------------------------------
    def _check_constraint(self, c: DeclaredConstraint) -> None:
        for name in c.reads:
            if not self.declares(name):
                raise WorldRefused(f"constraint {c.constraint_id!r} reads undeclared variable {name!r}")
            if self.role(name) not in CONSTRAINT_ROLES:
                raise WorldRefused(f"constraint {c.constraint_id!r} reads {name!r}, a {self.role(name).value}: a "
                                   "constraint limits what is set, held, or the state and environment it acts in")
        metric = self.variable(c.consequence.metric)
        if not converts(c.consequence.bound, metric.unit):
            raise WorldRefused(f"constraint {c.constraint_id!r}: bound {c.consequence.bound} is not compatible with "
                               f"{metric.name!r} in {metric.unit!r}")
        if c.guard is not None:
            self._check_guard(c.guard, f"constraint {c.constraint_id!r}")

    def _check_guard(self, guard: Any, where: str) -> None:
        if not self.declares(guard.variable):
            raise WorldRefused(f"{where}: guard reads undeclared variable {guard.variable!r}")
        var = self.variable(guard.variable)
        if var.domain is None:
            raise WorldRefused(f"{where}: guard variable {guard.variable!r} has no declared domain to check values in")
        for value in guard.values:
            if membership(var.domain, value) is not None:
                raise WorldRefused(f"{where}: guard value {value!r} is not in the declared domain of {guard.variable!r}")

    # ---- identity ----------------------------------------------------------------------------------------------------------
    def _sections(self) -> dict[str, Any]:
        return {
            "variables": {"roles": self._roles.to_dict(), "fields": [v.identity() for v in self.variables]},
            "entities": [e.to_dict() for e in self.entities],
            "constraints": [c.identity() for c in self.constraints],
            "actions": [a.identity() for a in self.actions],
            "channels": [c.to_dict() for c in self.channels],
            "applicability": [a.identity() for a in self.applicability],
            "providers": [p.identity() for p in self.providers],
            "budget": self.budget.identity(),
            "references": [r.to_dict() for r in self.references],
            "declared_by": self.declared_by.value,
            "basis": self.basis,
            **({"declaration": _binding_identity(self.declaration)} if self.declaration is not None else {}),
            **({"unit_registry": _binding_identity(self.unit_registry)} if self.unit_registry is not None else {}),
        }

    def _material(self) -> dict[str, Any]:
        return {"schema": WORLD_SCHEMA, "world_id": self.world_id, **self._sections()}

    @property
    def content_digest(self) -> str:
        return self._content

    @property
    def revision_id(self) -> str:
        return self._revision

    @property
    def revision(self) -> int:
        return self.lineage.revision

    def intact(self) -> bool:
        """Whether this object still holds the content and revision its identity names.  A frozen record edited in
        place (``object.__setattr__``) keeps its cached identity; decisions are therefore made on a world rebuilt from
        its payload, and verification refuses one that is not intact."""
        try:
            if RoleTable(tuple(v.declaration for v in self.variables)).to_dict() != self._roles.to_dict():
                return False                              # a role relabelled in place behind the cached role table
            content = digest(self._material())
            return content == self._content and self._revision == digest(
                {"world_id": self.world_id, "content": content, **self.lineage.identity()})
        except Exception:  # noqa: BLE001 - an object that cannot even be serialized is not intact
            return False

    def changed_from(self, other: "ScientificWorld") -> tuple[str, ...]:
        before, after = other._sections(), self._sections()
        return tuple(sorted(k for k in MATERIAL_FIELDS if digest(before.get(k)) != digest(after.get(k))))

    def derive(self, *, reason: str, **changes: Any) -> "ScientificWorld":
        """A new revision with these material changes.  The parent is this world; the changed fields are computed."""
        unknown = set(changes) - set(MATERIAL_FIELDS)
        if unknown:
            raise WorldRefused(f"a revision changes material fields only; not {sorted(unknown)}")
        text(reason, "a revision states its reason")
        if digest(self._material()) != self._content:
            raise WorldRefused("this world no longer matches its content digest; it is not derived from")
        candidate = dataclasses.replace(self, **changes)
        changed = candidate.changed_from(self)
        if not changed:
            raise WorldRefused("no material change: a revision must change what the world states")
        problem = restatement_problem(self, candidate)
        if problem:
            raise WorldRefused(problem)
        return dataclasses.replace(candidate, lineage=Lineage(self.lineage.revision + 1, self.revision_id, reason, changed,
                                                              tuple(sorted(_inherited(self).items()))))

    # ---- owner-record verification --------------------------------------------------------------------------------------
    @property
    def synthetic(self) -> bool:
        """True when any reference is a synthetic contract fixture: such a world is development evidence only.  A
        synthetic value reference is a copy no owner can verify, so it never supports admission; a synthetic channel,
        entity or protocol reference is declared content, carried to the executor in the admitted action."""
        refs = [v.source for v in self.variables if type(v.source) is RecordRef] + [c.reference for c in self.channels]
        refs += [e.reference for e in self.entities if e.reference is not None] + list(self.references)
        if self.budget.authority is not None:
            refs.append(self.budget.authority)
        return any(r.kind is RecordKind.SYNTHETIC_FIXTURE for r in refs)

    def bound_values(self) -> tuple[tuple[str, Any], ...]:
        return tuple((v.name, v.source) for v in self.variables if v.source is not None)

    def authority_bindings(self) -> tuple[AuthorityBinding, ...]:
        return tuple(b for _, b, _ in self.projected_facts() if b is not None)

    def projected_facts(self) -> tuple[tuple[str, Any, Any], ...]:
        """(subject, binding or None, what the world holds under it) for every fact read from an owner.

        A subject whose binding is None, or a RecordRef, is a copy nothing can verify: it never supports admission."""
        out: list[tuple[str, Any, Any]] = [("declaration", self.declaration, None),
                                           ("unit_registry", self.unit_registry, None)]
        for v in self.variables:
            if v.value is not None and v.origin is not ValueOrigin.DECLARED:
                held = value_projection(v.value, v.uncertainty)
                out.append((f"variable:{v.name}", v.source if type(v.source) is AuthorityBinding else None, held))
        for a in self.applicability:
            out.append((f"model:{a.binding_id}", a.authority, {"model": a.model.to_dict()}))
        for p in self.providers:
            out.append((f"provider:{p.provider_id}", p.authority,
                        {"status": detach(p.status), "report": detach(p.report)}))
        for x in self.budget.statements:
            out.append((f"budget:{x.dimension}", x.authority, detach(x.payload)))
        for dim in BUDGET_DIMENSIONS:
            if self.budget.status(dim) == "limited" and self.budget.statement(dim) is None:
                out.append((f"budget:{dim}", None, None))
        return tuple(out)

    # ---- read-only views ------------------------------------------------------------------------------------------------------
    @property
    def roles(self) -> RoleTable:
        return self._roles

    def declares(self, name: str) -> bool:
        return any(v.name == name for v in self.variables)

    def variable(self, name: str) -> WorldVariable:
        for v in self.variables:
            if v.name == name:
                return v
        raise WorldRefused(f"variable {name!r} is not declared in world {self.world_id!r} (never inferred from a name)")

    def role(self, name: str) -> VariableRole:
        return self.variable(name).role

    def has_channel(self, name: str) -> bool:
        return any(c.variable == name for c in self.channels)

    def controllability(self, name: str) -> Controllability:
        return CONTROLLABILITY_BY_ROLE[self.role(name)]

    def observability(self, name: str) -> Observability:
        role = self.role(name)
        if role is VariableRole.LATENT_PARAMETER:
            return Observability.NOT_OBSERVABLE
        if role is VariableRole.DERIVED_QUANTITY:
            return Observability.DERIVED_ONLY
        return Observability.OBSERVED_CHANNEL if self.has_channel(name) else Observability.NO_CHANNEL

    def observables(self) -> tuple[str, ...]:
        return tuple(c.variable for c in self.channels)

    def latent_quantities(self) -> tuple[str, ...]:
        return self._roles.names(VariableRole.LATENT_PARAMETER)

    def relationships(self) -> tuple[tuple[str, str, str], ...]:
        """Derived, never declared separately: role-table driven_by / derived_from edges and entity membership."""
        out = []
        for d in self._roles.declarations:
            out += [("driven_by", d.name, src) for src in d.driven_by]
            out += [("derived_from", d.name, src) for src in d.derived_from]
        for e in self.entities:
            out += [("member_of", n, e.entity_id) for n in e.variables]
        return tuple(sorted(out))

    def uncertainty_summary(self) -> dict[str, str]:
        """Per-variable uncertainty kind as the records state it ('unknown' unless quantified)."""
        return {v.name: v.uncertainty.kind.value for v in self.variables}

    def units(self) -> dict[str, str]:
        return {v.name: v.unit for v in self.variables}

    def action(self, action_id: str) -> ActionSpec | None:
        for a in self.actions:
            if a.action_id == action_id:
                return a
        return None

    def available_actions(self) -> tuple[str, ...]:
        return tuple(a.action_id for a in self.actions)

    def applicability_binding(self, binding_id: str) -> ApplicabilityBinding | None:
        for a in self.applicability:
            if a.binding_id == binding_id:
                return a
        return None

    def applicability_of(self, name: str) -> tuple[str, ...]:
        return tuple(a.binding_id for a in self.applicability if name in a.reads)

    def provider(self, provider_id: str) -> ProviderSnapshot | None:
        for p in self.providers:
            if p.provider_id == provider_id:
                return p
        return None

    # ---- serialization --------------------------------------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"schema": WORLD_SCHEMA, "software_version": SOFTWARE_VERSION, "world_id": self.world_id,
                "declared_by": self.declared_by.value, "basis": self.basis, "description": self.description,
                "roles": self._roles.to_dict(), "variables": [v.to_dict() for v in self.variables],
                "entities": [e.to_dict() for e in self.entities],
                "constraints": [c.to_dict() for c in self.constraints], "actions": [a.to_dict() for a in self.actions],
                "channels": [c.to_dict() for c in self.channels],
                "applicability": [a.to_dict() for a in self.applicability],
                "providers": [p.to_dict() for p in self.providers], "budget": self.budget.to_dict(),
                "references": [r.to_dict() for r in self.references], "lineage": self.lineage.to_dict(),
                **({"declaration": self.declaration.to_dict()} if self.declaration is not None else {}),
                **({"unit_registry": self.unit_registry.to_dict()} if self.unit_registry is not None else {}),
                "content_digest": self.content_digest, "revision_id": self.revision_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificWorld":
        expect_schema(payload.get("schema"), WORLD_SCHEMA)
        try:
            roles = RoleTable.from_dict(payload["roles"])
        except RoleRefused as exc:
            raise WorldRefused(f"role table: {exc}") from None
        decls = {d.name: d for d in roles.declarations}
        variables = []
        for v in payload["variables"]:
            if v.get("name") not in decls:
                raise WorldRefused(f"variable {v.get('name')!r} has no role declaration")
            variables.append(WorldVariable.from_dict(v, decls[v["name"]]))
        if len(variables) != len(decls):
            raise WorldRefused("the role table declares variables the world does not carry")
        world = cls(payload["world_id"], tuple(variables),
                    tuple(Entity.from_dict(e) for e in payload.get("entities", ())),
                    tuple(DeclaredConstraint.from_dict(c) for c in payload.get("constraints", ())),
                    tuple(ActionSpec.from_dict(a) for a in payload.get("actions", ())),
                    tuple(ObservationChannel.from_dict(c) for c in payload.get("channels", ())),
                    tuple(ApplicabilityBinding.from_dict(a) for a in payload.get("applicability", ())),
                    tuple(ProviderSnapshot.from_dict(p) for p in payload.get("providers", ())),
                    WorldBudget.from_dict(payload["budget"]),
                    tuple(RecordRef.from_dict(r) for r in payload.get("references", ())),
                    RoleSource(payload["declared_by"]), payload["basis"],
                    Lineage.from_dict(payload["lineage"]), payload.get("description", ""),
                    _binding_from(payload.get("declaration")), _binding_from(payload.get("unit_registry")))
        for key, value in (("content_digest", world.content_digest), ("revision_id", world.revision_id)):
            if key in payload and payload[key] != value:
                raise WorldRefused(f"stored {key} {payload[key]!r} does not match the recomputed {value!r}")
        return world


def _statements(world: "ScientificWorld") -> dict[str, str]:
    """(owner-statement key -> statement digest) for everything this world states on an owner's behalf."""
    out: dict[str, str] = {}
    for v in world.variables:
        if v.source is None:
            continue
        if type(v.source) is AuthorityBinding:
            out[digest(["binding", *v.source.key])] = v.source.projection
        else:
            out[digest(["ref", v.source.kind.value, v.source.ref, v.name])] = digest(
                {"value": None if v.value is None else v.value.to_dict(),
                 "origin": None if v.origin is None else v.origin.value, "uncertainty": v.uncertainty.to_dict()})
    for _, b, _ in world.projected_facts():
        if b is not None and b.owner_kind is not OwnerKind.SYSTEM_STATE:
            out[digest(["binding", *b.key])] = b.projection
    if world.budget.authority is not None:
        out[digest(["budget", world.budget.authority.kind.value, world.budget.authority.ref])] = digest(
            world.budget.identity())
    return out


def _inherited(world: "ScientificWorld") -> dict[str, str]:
    """Every statement this world's lineage has made, ancestors and itself."""
    return {**dict(world.lineage.bound), **_statements(world)}


def restatement_problem(parent: "ScientificWorld", child: "ScientificWorld") -> str | None:
    """Why ``child`` restates an owner's statement that its lineage already bound with another value, or None.

    A bound value, a projected record or a budget statement changes only with its owner record: under one owner
    reference (or one authority binding key) the lineage carries exactly one statement, even across a revision that
    unbound it.  Declarations (domains, constraints, actions) are the declarer's and may change in a revision.  The
    message names the owner's statement, so a reader sees which rule refused."""
    seen = _inherited(parent)
    for key, statement in _statements(child).items():
        if key in seen and seen[key] != statement:
            return ("an owner record (or binding) already carried another value in this lineage; a bound value or "
                    "budget changes only with its owner record (cite the newer record): the world never edits an "
                    "owner's statement")
    return None


def verify_lineage(world: ScientificWorld, store: Mapping[str, ScientificWorld]) -> tuple[str, ...]:
    """Walk parents from ``store`` (revision id -> world) to the root; refuse a missing, tampered or forged link.

    The restatement rule is checked over the WHOLE chain from the store (an owner statement carries one value from the
    root to ``world``, across any revision that unbound it), and a link that records its ancestors' statements
    (lineage version 2) must record exactly what they bound.  A version-1 link (BR1, written before the record existed)
    records none and is checked by the walk alone."""
    chain = [world]
    seen = {world.revision_id}
    while chain[-1].lineage.revision > 0:
        child = chain[-1]
        parent = store.get(child.lineage.parent)
        if parent is None:
            raise WorldRefused(f"revision {child.revision_id[:12]} names a parent the store does not hold")
        if parent.revision_id != child.lineage.parent or parent.revision_id in seen:
            raise WorldRefused("the lineage is tampered or cyclic")
        if parent.world_id != child.world_id or parent.lineage.revision + 1 != child.lineage.revision:
            raise WorldRefused("a revision continues another world or skips a revision number")
        changed = child.changed_from(parent)
        if changed != child.lineage.changed_fields:
            raise WorldRefused(f"stated changed fields {child.lineage.changed_fields} differ from the real change {changed}")
        problem = restatement_problem(parent, child)
        if problem:
            raise WorldRefused(f"revision {child.revision_id[:12]}: {problem}")
        if child.lineage.bound and dict(child.lineage.bound) != _inherited(parent):
            raise WorldRefused("the lineage's record of what its ancestors bound is not what they bound")
        seen.add(parent.revision_id)
        chain.append(parent)
    ledger: dict[str, str] = {}
    for w in reversed(chain):                                 # root first: one statement per owner key, chain-wide
        for key, statement in _statements(w).items():
            if ledger.setdefault(key, statement) != statement:
                raise WorldRefused(f"revision {w.revision_id[:12]}: an owner record (or binding) already carried "
                                   "another value in this lineage")
    return tuple(w.revision_id for w in reversed(chain))


__all__ = [
    "APPLICABILITY_CONTEXT_ROLES", "ApplicabilityBinding", "BUDGET_DIMENSIONS", "BudgetStatement", "Lineage",
    "MATERIAL_FIELDS", "ProviderSnapshot", "ScientificWorld", "WorldBudget", "restatement_problem", "verify_lineage",
]
