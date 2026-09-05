"""M5I — transactional budget accounting.

Two numbers that a naive loop conflates, kept apart on purpose:

**Predicted cost** is what the decision was made on. It comes from the M2 cost
model through the M4 score, it is recorded with the decision, and it is never
retroactively corrected — the decision genuinely was made on that number, and
rewriting it would destroy the audit trail of *why* the campaign chose what it
chose.

**Realized cost** is what the run actually consumed. It is the only thing that
charges the budget, the only thing that feeds calibration memory, and it is
what makes the next iteration's prediction better.

Subtracting predicted cost from the budget as though it were realized would let
a campaign that consistently under-predicts overspend without ever noticing, and
would make the overrun invisible to calibration. So :meth:`BudgetLedger.reserve`
records an intent and charges nothing; :meth:`BudgetLedger.settle` charges the
realized amount and records the overrun.

The reserved validation pool is fenced exactly as M4's :class:`BudgetPlan`
fences it: ordinary actions draw only on the general pool, and VALIDATE actions
may draw on the reservation. M5 adds the *liveness* half of that guarantee (see
:mod:`~engcore.sria.campaign.liveness`); this module only guarantees the money
is there.

**An incurred cost is a fact** (M5.1). M5 raised ``BudgetExhausted`` from
``settle`` when a realized cost overran the declaration — which refused to
record compute that had already been spent, and left the ledger claiming a
budget that reality had already broken. Selection is where a budget is
*enforced*; settlement is where it is *observed*. ``settle`` now records
everything and reports :attr:`BudgetLedger.overrun`, and the campaign halts
after the fact.

**Declared budget is not an enforced cap.** ``total_budget`` is what the
campaign said it would spend. Whether anything can stop a run mid-flight is a
property of the executor, and this module will not pretend otherwise:
:attr:`BudgetLedger.enforced_cap` is ``None`` unless an executor genuinely
enforces one, and :attr:`guarantee_statement` says plainly which of the two is
true. Without an enforced cap the honest claim is "overruns are detected and
halt the campaign", never "the declared amount was never exceeded".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..decision.actions import ActionFamily

LEDGER_SCHEMA = schema_string("sria_campaign_budget_ledger")
CHARGE_SCHEMA = schema_string("sria_campaign_budget_charge")


class BudgetExhausted(Exception):
    """The declared budget cannot fund a *proposed* action.

    Raised when selecting or reserving, never when settling. A cost that has
    already been incurred is recorded whatever it does to the ledger.
    """


class BudgetHistoryViolation(Exception):
    """Budget charge history was mutated outside ``BudgetLedger.settle``."""


@dataclass(frozen=True)
class BudgetCharge:
    """One settled cost, with the prediction it is measured against."""

    charge_id: str
    action_id: str
    iteration: int
    family: ActionFamily
    realized: float
    predicted: float | None = None
    #: How much of this charge came out of the validation reservation.
    from_validation_reservation: float = 0.0
    from_general_pool: float = 0.0
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", ActionFamily(self.family))
        if not str(self.charge_id).strip():
            raise ValueError("budget charge requires a charge_id")
        if self.realized < 0.0:
            raise ValueError("realized cost must be non-negative")
        total = self.from_validation_reservation + self.from_general_pool
        if abs(total - self.realized) > 1e-9:
            raise ValueError(
                f"charge {self.charge_id!r} splits {total} across pools but "
                f"realized {self.realized}; the split must account for all of it"
            )

    @property
    def overrun(self) -> float | None:
        if self.predicted is None:
            return None
        return self.realized - self.predicted

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHARGE_SCHEMA,
            "charge_id": self.charge_id,
            "action_id": self.action_id,
            "iteration": self.iteration,
            "family": self.family.value,
            "realized": self.realized,
            "predicted": self.predicted,
            "from_validation_reservation": self.from_validation_reservation,
            "from_general_pool": self.from_general_pool,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BudgetCharge":
        require_schema(payload, CHARGE_SCHEMA)
        return cls(
            charge_id=payload["charge_id"],
            action_id=payload.get("action_id", ""),
            iteration=int(payload.get("iteration", 0)),
            family=ActionFamily(payload["family"]),
            realized=float(payload["realized"]),
            predicted=payload.get("predicted"),
            from_validation_reservation=float(
                payload.get("from_validation_reservation", 0.0)
            ),
            from_general_pool=float(payload.get("from_general_pool", 0.0)),
            detail=payload.get("detail", ""),
        )


@dataclass
class BudgetLedger:
    """Auditable running account for one campaign run."""

    total_budget: float
    reserved_validation_budget: float = 0.0
    charges: tuple[BudgetCharge, ...] = ()
    cost_unit: str = "hour"
    #: A limit the *executor* genuinely enforces mid-run, if one exists. None
    #: means nothing can stop a run once started, and no claim is made that it
    #: could. Distinct from ``total_budget``, which is only a declaration.
    enforced_cap: float | None = None
    enforced_cap_source: str = ""

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "charges" and name in self.__dict__:
            raise BudgetHistoryViolation(
                "budget charges must be changed through BudgetLedger.settle"
            )
        super().__setattr__(name, value)

    def __post_init__(self) -> None:
        self.total_budget = float(self.total_budget)
        self.reserved_validation_budget = float(self.reserved_validation_budget)
        if self.enforced_cap is not None:
            self.enforced_cap = float(self.enforced_cap)
            if self.enforced_cap < 0.0:
                raise ValueError("enforced cap must be non-negative")
            if not str(self.enforced_cap_source).strip():
                raise ValueError(
                    "an enforced cap must name what enforces it; an unattributed "
                    "cap is a declaration wearing a stronger word"
                )
        if self.total_budget < 0.0 or self.reserved_validation_budget < 0.0:
            raise ValueError("budgets must be non-negative")
        if self.reserved_validation_budget > self.total_budget:
            raise ValueError("reserved validation budget exceeds the total budget")
        object.__setattr__(self, "charges", tuple(self.charges))
        seen: set[str] = set()
        duplicates: set[str] = set()
        for charge in self.charges:
            charge_id = charge.charge_id
            if charge_id in seen:
                duplicates.add(charge_id)
            else:
                seen.add(charge_id)
        if duplicates:
            raise ValueError(f"duplicate budget charges: {sorted(duplicates)}")

    # -- realized accounting ----------------------------------------------
    @property
    def spent_validation(self) -> float:
        return sum(c.from_validation_reservation for c in self.charges)

    @property
    def spent_general(self) -> float:
        return sum(c.from_general_pool for c in self.charges)

    @property
    def spent_total(self) -> float:
        return sum(c.realized for c in self.charges)

    @property
    def validation_pool(self) -> float:
        return max(0.0, self.reserved_validation_budget - self.spent_validation)

    @property
    def general_pool(self) -> float:
        return max(
            0.0,
            self.total_budget - self.reserved_validation_budget - self.spent_general,
        )

    @property
    def remaining(self) -> float:
        return max(0.0, self.total_budget - self.spent_total)

    @property
    def total_overrun(self) -> float:
        """Sum of per-action prediction errors. Not the budget overrun."""
        return sum(c.overrun or 0.0 for c in self.charges)

    @property
    def overrun(self) -> float:
        """How far realized spend has passed the declared budget."""
        return max(0.0, self.spent_total - self.total_budget)

    @property
    def is_overrun(self) -> bool:
        return self.spent_total > self.total_budget + 1e-9

    @property
    def guarantee_statement(self) -> str:
        """What this ledger can honestly claim about the declared budget."""
        if self.enforced_cap is None:
            return (
                "declared budget only: no executor-enforced resource cap exists, "
                "so an overrun can be detected and halt the campaign but cannot "
                "be prevented mid-run"
            )
        return (
            f"declared budget {self.total_budget} with an executor-enforced cap "
            f"of {self.enforced_cap} ({self.enforced_cap_source}); a run is "
            f"stopped by the executor at the cap"
        )

    def affordable(self, cost: float, *, family: ActionFamily) -> bool:
        """VALIDATE may draw on the reservation; nothing else may."""
        cost = float(cost)
        if ActionFamily(family) is ActionFamily.VALIDATE:
            return cost <= self.validation_pool + self.general_pool + 1e-12
        return cost <= self.general_pool + 1e-12

    def has_charge(self, charge_id: str) -> bool:
        return any(c.charge_id == charge_id for c in self.charges)

    def settle(
        self,
        *,
        charge_id: str,
        action_id: str,
        iteration: int,
        family: ActionFamily,
        realized: float,
        predicted: float | None = None,
        detail: str = "",
    ) -> BudgetCharge:
        """Record realized cost. Idempotent by ``charge_id``, and never refuses.

        A repeated settle for the same charge id returns the existing charge
        untouched rather than debiting twice — the property a resume depends on.

        An overrun is recorded, not rejected. The compute was spent; a ledger
        that refused to write it down would be reporting a budget that reality
        had already broken, and the campaign would carry on believing it had
        money it does not. Enforcement belongs at selection
        (:meth:`affordable`); this is observation.
        """
        for existing in self.charges:
            if existing.charge_id == charge_id:
                return existing

        family = ActionFamily(family)
        realized = float(realized)
        if realized < 0.0:
            raise ValueError("realized cost must be non-negative")

        # A validation action draws on its reservation first; everything else is
        # barred from the reservation entirely, even when overrunning — an
        # ordinary action must never quietly consume certification money.
        from_reservation = 0.0
        if family is ActionFamily.VALIDATE:
            from_reservation = min(realized, self.validation_pool)
        from_general = realized - from_reservation

        charge = BudgetCharge(
            charge_id=charge_id,
            action_id=action_id,
            iteration=iteration,
            family=family,
            realized=realized,
            predicted=predicted,
            from_validation_reservation=from_reservation,
            from_general_pool=from_general,
            detail=detail,
        )
        object.__setattr__(self, "charges", self.charges + (charge,))
        return charge

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LEDGER_SCHEMA,
            "total_budget": self.total_budget,
            "reserved_validation_budget": self.reserved_validation_budget,
            "cost_unit": self.cost_unit,
            "enforced_cap": self.enforced_cap,
            "enforced_cap_source": self.enforced_cap_source,
            "charges": [c.to_dict() for c in self.charges],
            "spent_general": self.spent_general,
            "spent_validation": self.spent_validation,
            "remaining": self.remaining,
            "overrun": self.overrun,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BudgetLedger":
        require_schema(payload, LEDGER_SCHEMA)
        return cls(
            total_budget=float(payload["total_budget"]),
            reserved_validation_budget=float(
                payload.get("reserved_validation_budget", 0.0)
            ),
            charges=tuple(
                BudgetCharge.from_dict(c) for c in payload.get("charges", ())
            ),
            cost_unit=payload.get("cost_unit", "hour"),
            enforced_cap=payload.get("enforced_cap"),
            enforced_cap_source=payload.get("enforced_cap_source", ""),
        )

    def to_plan(self):
        """Project onto M4's frozen :class:`BudgetPlan` for scoring."""
        from ..decision.recommendation import BudgetPlan

        return BudgetPlan(
            total_budget=self.total_budget,
            reserved_validation_budget=self.reserved_validation_budget,
            spent_general=self.spent_general,
            spent_validation=self.spent_validation,
        )
