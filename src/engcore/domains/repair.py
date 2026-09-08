"""What would have to change for a violated condition to enter the domain.

A verdict of OUTSIDE_VALIDATED_DOMAIN names the condition that failed. That is
already more than most tools say, and it is still not what the caller needs:
``violated: biot_number`` tells an engineer to stop, and does not tell them
which of the four numbers they wrote down is the one to move, or how far.

This module answers that second question **only where the answer is exact**.

WHAT A HINT IS
--------------
One line, for one declared input, holding every other declaration fixed::

    characteristic_length <= 2.4 mm   (declared 10 mm)

It is not advice. It does not say this is the input to change, it does not
rank the inputs by cost or plausibility, and several hints for one condition
are alternatives the caller chooses between, not a plan. Nothing here searches:
every threshold is the solution of one closed-form equation in one unknown,
and where that equation is not available the input is reported as one this
module cannot invert, with the reason, rather than as a number a solver found.

THE ONE FORM THIS MODULE INVERTS
--------------------------------
A derived group is admitted as invertible in an input ``x`` when the domain can
declare, from the algebra of its own derivation, that::

    g(x) = A + s * x**p          with p != 0, s != 0, and A, p fixed

holding every other declaration fixed. ``A`` is an offset the domain supplies
(zero for a pure power law, which is most of them) and ``p`` an exponent. The
domain never supplies ``s``: it is recovered from the point already assessed,
``s = (g0 - A) / x0**p``, so a declaration cannot disagree with the number the
run actually produced.

That form is strictly monotone in ``x`` wherever it is defined, so::

    x* = x0 * ((B - A) / (g0 - A))**(1/p)

is the unique value at which the group equals the bound ``B`` exactly, the
inequality in ``x`` has the same sense throughout, and — this is the part worth
stating — **the hint inherits the bound's own inclusivity**. A bound written
``<= 0.1`` is met exactly at ``x*``, so the hint reads ``x <= x*``; a bound
written ``> 0`` is not met at ``x*``, so the hint reads ``x > x*``. The
inclusivity is carried, never chosen: see :func:`invert_range_condition`.

Everything else is refused. Not "not yet supported" — refused, by name, with
the reason, so the report says which inputs it could not invert rather than
leaving the reader to assume the list was complete. Three kinds of refusal
recur, and they are different facts:

* the input **does not move the group at all** (``ambient_conductance``
  cancels out of the internal Fourier number exactly);
* the input moves it through a **max, an absolute value or a sum** — a
  piecewise or non-power-law map with no unique closed-form inverse
  (``ambient_conductance`` reaches the conductance excursion ratio through
  ``max(|T0 - Tamb|, |Tss - Tamb|)``; every fluid property reaches the
  Churchill-Chu agreement ratio through ``0.68 + 0.670 Ra**0.25 / D(Pr)``,
  which is a sum and not a power law);
* the input is **not a declaration at all** — the operating temperature is a
  state the run computed, and no hint about it is a hint the caller can act on.

WHY NO HINT CAN EVER NAME A BOUND, AND WHY THAT IS STRUCTURAL
--------------------------------------------------------------
The failure mode this module has to make impossible is a hint that reads
"raise the limit". It is the one suggestion that would invert the purpose of
every validity domain in this repository: a bound is the statement of what the
model was shown to cover, and moving it does not move the model.

This is not a hypothetical. Commit ``d57a88e`` removed ``damkohler_number``
from the CSTR domain as a validity condition. The bound was wrong — but it was
not wrong in its *value*. It constrained ``k*tau`` while the claim it was
standing in for was about ``k*t_mix``, so no adjustment of the number would
have repaired it, and raising it would have produced a condition that passed
while measuring the wrong ratio. A hint saying "raise the Damkohler ceiling"
would have been precisely the move that was rejected on physical grounds, and
it would have looked like help.

So the guarantee here is not a convention and not a test that fails to find a
counterexample. It is that **a bound has no name**:

* :class:`RepairHint` accepts only a :class:`RepairTarget` as its subject —
  ``isinstance`` is checked, a bare string is refused.
* :class:`RepairTarget` refuses construction unless its name is a declared
  ``ModelInputSpec`` of the model it is about, whose ``source_kind`` is
  ``PARAMETER``. A reserved derived quantity is refused; so is a ``VARIABLE``,
  because a solve result is not something a caller declares.
* A ``RangeCondition``'s ``minimum`` and ``maximum`` are ``Quantity`` literals
  held as attributes of the condition. They are in no namespace: not in
  ``ValidityDomain.context_keys``, which is the complete set of names the
  conditions read, and not in ``model.inputs``. **There is no string anywhere
  in the system that denotes a bound**, so there is no argument that could be
  passed to :class:`RepairTarget` to make it name one.

The impossibility is therefore a property of what names exist, not of what this
module remembers not to emit. ``tests/test_repair_guidance.py`` pins it from
both ends: that the constructible target set is exactly the declared parameter
inputs, and that no bound is reachable by name from a model record at all.

WHAT IS DELIBERATELY NOT HERE
------------------------------
No optimisation, no ranking, no cost model, no recommendation, and no
composition: a hint repairs **its own condition**, holding every other
declaration fixed. With two conditions violated, applying one hint does not
flip the verdict, and this module does not pretend otherwise — it emits one
independent line per invertible input and the caller decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..scientific.models.definition import (
    InputSourceKind,
    RangeCondition,
    UnknownReason,
    ValidityAssessment,
)
from ..scientific.units import Quantity

__all__ = [
    "RepairGuidanceError",
    "RepairDirection",
    "RepairTarget",
    "RepairHint",
    "RepairRefusal",
    "ConditionRepair",
    "MonotoneInversion",
    "RefusedInversion",
    "ConditionInversions",
    "ModelInversionTable",
    "invert_range_condition",
    "condition_repairs",
    "merge_repairs",
]


class RepairGuidanceError(Exception):
    """A repair hint that could not be constructed as stated."""


class RepairDirection(Enum):
    """Which way a declared input has to move."""

    AT_MOST = "at_most"
    AT_LEAST = "at_least"

    def symbol(self, *, inclusive: bool) -> str:
        if self is RepairDirection.AT_MOST:
            return "≤" if inclusive else "<"
        return "≥" if inclusive else ">"


@dataclass(frozen=True)
class RepairTarget:
    """A name a hint is allowed to be about.

    Constructible **only** for a declared ``PARAMETER`` input of the model it
    names. That is the whole of the guarantee described in this module's
    docstring: a bound is not a model input, a derived quantity is reserved,
    and a solve result is a ``VARIABLE``, so none of the three can be the
    subject of a hint. See the module docstring for why this is structural
    rather than conventional, and for the commit that motivates it.
    """

    model: Any
    name: str

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise RepairGuidanceError("a repair target requires a name")
        object.__setattr__(self, "name", name)

        inputs = getattr(self.model, "inputs", None)
        if inputs is None:
            raise RepairGuidanceError(
                f"a repair target must name an input of a model record; "
                f"{type(self.model).__name__} declares none"
            )
        specs = {spec.name: spec for spec in inputs}
        spec = specs.get(name)
        if spec is None:
            raise RepairGuidanceError(
                f"{name!r} is not a declared input of model "
                f"{getattr(self.model, 'model_id', self.model)!r}, so no hint "
                f"may be about it. A validity bound is not a declared input "
                f"and never will be: it is an anonymous Quantity on the "
                f"condition. Declared inputs here: {sorted(specs)}"
            )
        if spec.source_kind is not InputSourceKind.PARAMETER:
            raise RepairGuidanceError(
                f"{name!r} is a {spec.source_kind.value} of model "
                f"{getattr(self.model, 'model_id', self.model)!r}, not a "
                f"declared parameter. A hint states what the caller would have "
                f"to declare differently, and a solve result is not something "
                f"they declare"
            )
        if name in getattr(self.model, "derived_quantities", frozenset()):
            raise RepairGuidanceError(
                f"{name!r} is a reserved derived quantity of model "
                f"{getattr(self.model, 'model_id', self.model)!r}; no caller "
                f"supplies it, so no caller can change it"
            )

    @property
    def model_id(self) -> str:
        return str(getattr(self.model, "model_id", ""))

    @property
    def unit_exemplar(self) -> str | None:
        for spec in self.model.inputs:
            if spec.name == self.name:
                return spec.unit_exemplar
        return None  # pragma: no cover - __post_init__ guarantees a match


@dataclass(frozen=True)
class RepairHint:
    """One declared input, one direction, one threshold. Nothing else.

    ``threshold`` is the value at which *this* condition is exactly met, with
    every other declaration held fixed. ``inclusive`` is the violated bound's
    own inclusivity, carried through the strictly monotone inversion rather
    than chosen here.
    """

    condition: str
    target: RepairTarget
    direction: RepairDirection
    threshold: Quantity
    declared: Quantity
    inclusive: bool
    basis: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.target, RepairTarget):
            raise RepairGuidanceError(
                f"a repair hint's target must be a RepairTarget, got "
                f"{type(self.target).__name__}. A bare string would let a hint "
                f"name anything at all, including a bound"
            )
        for label in ("threshold", "declared"):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise RepairGuidanceError(
                    f"repair hint {label} must be a Quantity, got "
                    f"{type(value).__name__}"
                )
        if not self.threshold.is_compatible_with(self.declared):
            raise RepairGuidanceError(
                f"repair hint for {self.target.name!r} proposes "
                f"{self.threshold}, which does not share a dimension with the "
                f"declared {self.declared}"
            )
        if not math.isfinite(self.threshold.magnitude):
            raise RepairGuidanceError(
                f"repair hint for {self.target.name!r} has a non-finite "
                f"threshold; a bound reached only at infinity is not a repair"
            )
        object.__setattr__(self, "direction", RepairDirection(self.direction))
        object.__setattr__(self, "inclusive", bool(self.inclusive))
        object.__setattr__(self, "condition", str(self.condition).strip())
        object.__setattr__(self, "basis", str(self.basis).strip())

    @property
    def target_name(self) -> str:
        return self.target.name

    def line(self) -> str:
        """The one-line form. ``characteristic_length <= 2.4 mm (declared 10 mm)``."""
        symbol = self.direction.symbol(inclusive=self.inclusive)
        return (
            f"{self.target.name} {symbol} {self.threshold} "
            f"(declared {self.declared})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "target": self.target.name,
            "direction": self.direction.value,
            "inclusive": self.inclusive,
            "threshold": self.threshold.to_dict(),
            "declared": self.declared.to_dict(),
            "basis": self.basis,
        }


@dataclass(frozen=True)
class RepairRefusal:
    """An input this module will not invert, named, with the reason.

    Emitted rather than omitted. A report that listed only the inputs it could
    invert would read as though those were the only ones that move the group,
    which for every condition in this repository is false.
    """

    condition: str
    target: str
    reason: str

    def __post_init__(self) -> None:
        for label in ("condition", "target", "reason"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise RepairGuidanceError(
                    f"a repair refusal requires a non-empty {label}; a refusal "
                    f"with no reason is an omission wearing a label"
                )
            object.__setattr__(self, label, text)

    def line(self) -> str:
        return f"{self.target}: not invertible — {self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "target": self.target,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ConditionRepair:
    """Everything this module can say about one violated condition, at one site.

    ``subject`` is the thing assessed — a component id, a body id, a problem
    id. One model is applied to several of them in a coupled run and each has
    its own declarations, so each gets its own repair rather than having its
    hints merged with a neighbour's. Merging would require choosing between
    two thresholds, which is the ranking this module refuses to do.
    """

    model_id: str
    subject: str
    condition: str
    observed: Quantity
    bound: Quantity
    bound_side: str
    bound_inclusive: bool
    hints: tuple[RepairHint, ...] = ()
    refusals: tuple[RepairRefusal, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "hints", tuple(self.hints))
        object.__setattr__(self, "refusals", tuple(self.refusals))
        if self.bound_side not in ("minimum", "maximum"):
            raise RepairGuidanceError(
                f"bound_side must be 'minimum' or 'maximum', got "
                f"{self.bound_side!r}"
            )
        for hint in self.hints:
            if hint.condition != self.condition:
                raise RepairGuidanceError(
                    f"hint for {hint.condition!r} filed under condition "
                    f"{self.condition!r}"
                )
        if not self.hints and not self.refusals:
            raise RepairGuidanceError(
                f"repair for {self.condition!r} carries neither a hint nor a "
                f"refusal; silence is not a report"
            )

    @property
    def repairable(self) -> bool:
        """Whether any single declared input can carry this into the domain."""
        return bool(self.hints)

    def lines(self) -> tuple[str, ...]:
        symbol = "≤" if self.bound_inclusive else "<"
        if self.bound_side == "minimum":
            symbol = "≥" if self.bound_inclusive else ">"
        head = (
            f"{self.condition} = {self.observed} "
            f"(bound {symbol} {self.bound})"
        )
        if self.hints:
            body = ["To enter the validated domain, one of:"]
            body += [f"  · {hint.line()}" for hint in self.hints]
        else:
            body = [
                "Not repairable by any single declared input:",
            ]
        body += [f"  · {refusal.line()}" for refusal in self.refusals]
        return (head, *body)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "subject": self.subject,
            "condition": self.condition,
            "observed": self.observed.to_dict(),
            "bound": self.bound.to_dict(),
            "bound_side": self.bound_side,
            "bound_inclusive": self.bound_inclusive,
            "repairable": self.repairable,
            "hints": [hint.to_dict() for hint in self.hints],
            "not_invertible": [r.to_dict() for r in self.refusals],
        }


# =====================================================================
# What a domain declares
# =====================================================================

#: An exponent, or a pure function of the assessed context returning one. The
#: callable form exists because a few groups have a *route*: the Biot number
#: goes as ``1/A_s`` when a characteristic length was declared and as
#: ``1/A_s**2`` when it was derived from ``V/A_s``. Returning ``None`` means
#: this input does not admit the form on the route the caller declared, and
#: the declaration's ``unavailable`` text is reported as the reason.
ExponentRule = float | Callable[[Mapping[str, Any]], "float | None"]

#: The offset ``A`` in ``g = A + s x**p``, as a pure function of the assessed
#: context. ``None`` means ``A = 0``, which is every pure power law.
OffsetRule = Callable[[Mapping[str, Any]], "Quantity | None"] | None


@dataclass(frozen=True)
class MonotoneInversion:
    """``g = A + s * target**exponent``, every other declaration held fixed.

    The domain declares ``exponent`` and, where it is not zero, ``offset``. It
    does **not** declare ``s``: that is recovered from the assessed point, so
    the inversion is anchored to the number the run produced rather than to a
    second statement of the algebra that could drift from it.
    """

    target: str
    exponent: ExponentRule
    justification: str
    offset: OffsetRule = None
    unavailable: str = ""
    must_stay_positive: bool = False
    #: A ceiling the target may not be pushed past, with the reason. This is
    #: not a second validity bound and it is not negotiable arithmetic: it is
    #: where a declaration stops being a declaration.
    #:
    #: The motivating case is ``derating_factor``. It divides a rating, so the
    #: dissipation utilization is an exact reciprocal in it and the inversion
    #: is real — but ``ComponentRating`` admits only ``(0, 1]``, because a
    #: factor above 1 uses more of a component than it is rated for while
    #: reporting that it is inside its rating. Inverting a 4.5x overload gives
    #: 3.6, and a hint printing that number would have been the
    #: raise-the-limit move wearing a declared input's name — arithmetically
    #: right, and the exact failure this module exists to prevent. Caught by
    #: the applied-hint test, which could not construct the rating the hint
    #: proposed.
    admissible_maximum: Quantity | None = None
    beyond_admissible: str = ""

    def __post_init__(self) -> None:
        if not str(self.target).strip():
            raise RepairGuidanceError("an inversion requires a target name")
        object.__setattr__(self, "target", str(self.target).strip())
        if not str(self.justification).strip():
            raise RepairGuidanceError(
                f"inversion of {self.target!r} states no justification; the "
                f"exponent is an algebraic claim and has to be readable as one"
            )
        if callable(self.exponent) and not str(self.unavailable).strip():
            raise RepairGuidanceError(
                f"inversion of {self.target!r} resolves its exponent from the "
                f"context, so it must also say what it means when no exponent "
                f"resolves; set `unavailable`"
            )
        if self.admissible_maximum is not None:
            if not isinstance(self.admissible_maximum, Quantity):
                raise RepairGuidanceError(
                    f"inversion of {self.target!r}: admissible_maximum must be "
                    f"a Quantity"
                )
            if not str(self.beyond_admissible).strip():
                raise RepairGuidanceError(
                    f"inversion of {self.target!r} declares a ceiling on the "
                    f"target without saying what lies past it; a refusal with "
                    f"no reason is an omission wearing a label"
                )
        if not callable(self.exponent) and float(self.exponent) == 0.0:
            raise RepairGuidanceError(
                f"inversion of {self.target!r} declares exponent 0, which says "
                f"the group does not depend on it. Declare a RefusedInversion"
            )

    def resolve_exponent(self, context: Mapping[str, Any]) -> float | None:
        if callable(self.exponent):
            resolved = self.exponent(context)
            return None if resolved is None else float(resolved)
        return float(self.exponent)


@dataclass(frozen=True)
class RefusedInversion:
    """A declared input this domain will not invert for a condition, and why."""

    target: str
    reason: str

    def __post_init__(self) -> None:
        for label in ("target", "reason"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise RepairGuidanceError(
                    f"a refused inversion requires a non-empty {label}"
                )
            object.__setattr__(self, label, text)


@dataclass(frozen=True)
class ConditionInversions:
    """One condition's complete inversion decision, for every input it reads."""

    condition: str
    inversions: tuple[MonotoneInversion, ...] = ()
    refusals: tuple[RefusedInversion, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "inversions", tuple(self.inversions))
        object.__setattr__(self, "refusals", tuple(self.refusals))
        if not self.inversions and not self.refusals:
            raise RepairGuidanceError(
                f"condition {self.condition!r} declares no inversion and no "
                f"refusal; a row that says nothing should not be a row"
            )
        names = [i.target for i in self.inversions] + [
            r.target for r in self.refusals
        ]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise RepairGuidanceError(
                f"condition {self.condition!r} decides {sorted(duplicates)} "
                f"twice; one input, one decision"
            )


@dataclass(frozen=True)
class ModelInversionTable:
    """One model's inversion decisions, checked against the model at import.

    Completeness is enforced: **every** ``RangeCondition`` on the model must
    have a row. A condition added without an inversion decision does not
    import, which is the same discipline the core applies to a condition that
    reads an unreserved name — the alternative is a report that silently says
    nothing about a condition nobody thought about.
    """

    model: Any
    rows: tuple[ConditionInversions, ...]
    _by_condition: dict[str, ConditionInversions] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        ranges = {
            c.name: c
            for c in self.model.validity.conditions
            if isinstance(c, RangeCondition)
        }
        declared = {row.condition for row in self.rows}
        unknown = sorted(declared - set(ranges))
        if unknown:
            raise RepairGuidanceError(
                f"inversion table for {self.model.model_id!r} names "
                f"{unknown}, which is no range condition of that model"
            )
        missing = sorted(set(ranges) - declared)
        if missing:
            raise RepairGuidanceError(
                f"inversion table for {self.model.model_id!r} says nothing "
                f"about {missing}. Every range condition needs a decision, "
                f"even if the decision is that nothing declared can repair it"
            )
        by_condition: dict[str, ConditionInversions] = {}
        for row in self.rows:
            if row.condition in by_condition:
                raise RepairGuidanceError(
                    f"inversion table for {self.model.model_id!r} decides "
                    f"{row.condition!r} twice"
                )
            by_condition[row.condition] = row
            # Minting the target here is what makes an impossible hint an
            # import error rather than a runtime one: a row naming a bound,
            # a derived quantity or a solve result cannot be loaded at all.
            for inversion in row.inversions:
                RepairTarget(self.model, inversion.target)
            reserved = set(self.model.derived_quantities)
            inputs = {spec.name for spec in self.model.inputs}
            for refusal in row.refusals:
                if refusal.target not in inputs | reserved:
                    raise RepairGuidanceError(
                        f"inversion table for {self.model.model_id!r} refuses "
                        f"{refusal.target!r} under {row.condition!r}, which is "
                        f"neither a declared input nor a reserved derived "
                        f"quantity of that model. A refusal is about something "
                        f"the derivation reads"
                    )
        object.__setattr__(self, "_by_condition", by_condition)

    def row(self, condition: str) -> ConditionInversions | None:
        return self._by_condition.get(condition)


# =====================================================================
# The inversion
# =====================================================================

#: Significant figures the printed threshold is rounded to, **into** the
#: admissible side of the bound.
#:
#: WHY A HINT IS ROUNDED AT ALL, AND WHY IT IS ROUNDED THIS WAY.
#:
#: The inversion is exact in the reals: at ``x*`` the group equals the bound,
#: and an inclusive bound admits it. In floating point it need not. The Biot
#: number of a body declared with ``L_c = 10 mm``, ``k = 100 W/m/K``,
#: ``A_s = 1.19e-3 m^2`` and ``hA = 5 W/K`` is 0.42; the exact repair is
#: ``L_c = 0.1 k A_s / hA``, and a caller who declares the nearest double to
#: that value re-derives ``Bi = 0.10000000000000002`` — one ulp above an
#: inclusive bound of 0.1, and still violated. The hint would have been right
#: about the mathematics and useless in practice.
#:
#: So the printed threshold is the exact solution rounded toward the side the
#: bound admits: down for an ``AT_MOST`` hint, up for an ``AT_LEAST`` one.
#: This is one deterministic arithmetic step and not a search — nothing is
#: evaluated, tried or refined, and the direction is known before the rounding
#: from the sign of the derivative that produced it.
#:
#: TWELVE, and not a number chosen to make a test pass. A double carries about
#: 15.95 decimal digits. The derivations these thresholds invert compose a
#: handful of multiplications and divisions, so re-deriving the group from a
#: rounded declaration carries a relative error of a few ulps, order 1e-15.
#: Discarding the last four digits places the printed threshold about 1e-12
#: relative inside the boundary: three orders of magnitude clear of that
#: round-off, and far finer than the precision of any declaration a caller
#: writes down — a conductivity is known to three figures, not twelve.
_HINT_SIGNIFICANT_FIGURES = 12


def _round_into(value: float, direction: RepairDirection) -> float:
    """``value`` at :data:`_HINT_SIGNIFICANT_FIGURES`, toward the admissible side.

    Direction is in the *target's* space, so this is correct for a negative
    threshold too: ``AT_MOST`` admits everything below, and rounding down is
    into that set whatever the sign.

    **The step is strict, never a no-op.** Rounding alone fixes nothing when
    the exact solution already lies on the grid, which is not a rare case: the
    Biot repair for a body at 12x its limit is ``hA = 0.004 W/K`` exactly, so
    rounding down at twelve figures returns 0.004, and re-deriving from 0.004
    lands one ulp above an inclusive 0.1 again. So a value already on the grid
    is moved one grid step further in, and the printed threshold is strictly
    inside the boundary by about 1e-12 relative in every case rather than in
    the ones where the decimal happened not to be round.

    Zero is the exception and is returned unchanged. A threshold of zero comes
    from a condition bounding a declaration directly -- ``heat_capacity > 0``
    -- where the bound *is* the answer and stepping off it would print a
    number the physics did not ask for.
    """
    if value == 0.0 or not math.isfinite(value):
        return value
    exponent = math.floor(math.log10(abs(value)))
    scale = 10.0 ** (exponent - (_HINT_SIGNIFICANT_FIGURES - 1))
    scaled = value / scale
    if direction is RepairDirection.AT_MOST:
        stepped = math.floor(scaled)
        if stepped == scaled:
            stepped -= 1
    else:
        stepped = math.ceil(scaled)
        if stepped == scaled:
            stepped += 1
    return stepped * scale


def invert_range_condition(
    *,
    condition: RangeCondition,
    observed: Quantity,
    declared: Quantity,
    target: RepairTarget,
    exponent: float,
    offset: Quantity | None,
    must_stay_positive: bool,
    justification: str,
    admissible_maximum: Quantity | None = None,
    beyond_admissible: str = "",
) -> RepairHint | str:
    """The value of ``target`` at which ``condition`` is exactly met.

    Returns a :class:`RepairHint`, or a string saying why the inversion does
    not exist at this point. Nothing is searched: the returned threshold is the
    single solution of ``A + s x**p = B``, and the direction and inclusivity
    follow from the sign of ``dg/dx`` and from the bound's own flag.
    """
    unit = observed.units
    g0 = observed.magnitude
    if condition.maximum is not None and observed.compare(condition.maximum) > 0:
        side, bound_q, inclusive = (
            "maximum", condition.maximum, condition.maximum_inclusive
        )
    elif condition.minimum is not None and observed.compare(condition.minimum) < 0:
        side, bound_q, inclusive = (
            "minimum", condition.minimum, condition.minimum_inclusive
        )
    else:
        return (
            "the observed value does not violate either bound, so there is "
            "nothing to invert"
        )
    bound = bound_q.magnitude_in(unit)

    shift = 0.0 if offset is None else offset.magnitude_in(unit)
    x0 = declared.magnitude
    if x0 == 0.0:
        return (
            f"the declared {target.name} is zero, so the coefficient of the "
            f"declared form cannot be recovered from this point"
        )
    if exponent != 1.0 and x0 < 0.0:
        return (
            f"the declared {target.name} is negative and the declared form "
            f"has a non-unit exponent, which is not single-valued there"
        )

    numerator = bound - shift
    denominator = g0 - shift
    if denominator == 0.0:
        return (
            "the group already sits at the declared offset, so the "
            "coefficient of the declared form cannot be recovered from it"
        )
    ratio = numerator / denominator

    if exponent == 1.0:
        threshold = x0 * ratio
    else:
        if ratio < 0.0:
            return (
                f"no positive {target.name} carries this group to its bound: "
                f"the declared form would have to change sign to reach it"
            )
        if ratio == 0.0 and exponent < 0.0:
            return (
                f"the bound is reached only as {target.name} grows without "
                f"limit, which is not a value anyone can declare"
            )
        threshold = x0 * (ratio ** (1.0 / exponent))

    if not math.isfinite(threshold):
        return (
            f"the value of {target.name} that meets this bound is not finite"
        )

    # dg/dx = s p x**(p-1), with s = (g0 - A) / x0**p. At the declared point
    # the sign is sign(s) * sign(p) * sign(x0**(p-1)); x0 > 0 for every
    # non-unit exponent, and for p == 1 the last factor is 1.
    slope = denominator / (x0 ** exponent)
    increasing = (slope * exponent) > 0.0

    if side == "maximum":
        direction = (
            RepairDirection.AT_MOST if increasing else RepairDirection.AT_LEAST
        )
    else:
        direction = (
            RepairDirection.AT_LEAST if increasing else RepairDirection.AT_MOST
        )

    # Rounded only once the direction is known, because "into the admissible
    # side" is a statement about the direction. See _HINT_SIGNIFICANT_FIGURES.
    threshold = _round_into(threshold, direction)
    if must_stay_positive and threshold <= 0.0:
        return (
            f"the {target.name} that would meet this bound is not positive, "
            f"and this quantity has no non-positive values"
        )
    if admissible_maximum is not None:
        ceiling = admissible_maximum.magnitude_in(declared.units)
        if threshold > ceiling:
            return (
                f"meeting this bound would need {target.name} = "
                f"{Quantity(threshold, declared.units)}, past "
                f"{admissible_maximum}: {beyond_admissible}"
            )

    return RepairHint(
        condition=condition.name,
        target=target,
        direction=direction,
        threshold=Quantity(threshold, declared.units),
        declared=declared,
        inclusive=inclusive,
        basis=justification,
    )


def _violated_range_conditions(
    model: Any, assessment: ValidityAssessment
) -> tuple[RangeCondition, ...]:
    violated = set(assessment.violated)
    return tuple(
        c
        for c in model.validity.conditions
        if isinstance(c, RangeCondition) and c.name in violated
    )


def condition_repairs(
    *,
    model: Any,
    context: Any,
    table: ModelInversionTable,
    subject: str,
    assessment: ValidityAssessment | None = None,
) -> tuple[ConditionRepair, ...]:
    """One :class:`ConditionRepair` per violated range condition of ``model``.

    ``context`` is the same ``DomainValidityContext`` the assessment was made
    over — the hints are anchored to the numbers that produced the verdict, not
    to a second assembly that could differ from it. ``assessment`` defaults to
    re-asking the model over that context.
    """
    if table.model is not model:
        raise RepairGuidanceError(
            f"inversion table is for {table.model.model_id!r}, not "
            f"{model.model_id!r}"
        )
    verdict = assessment if assessment is not None else context.assess(model)
    values = context.merged() if hasattr(context, "merged") else dict(context)

    repairs: list[ConditionRepair] = []
    for condition in _violated_range_conditions(model, verdict):
        observed = values.get(condition.name)
        if not isinstance(observed, Quantity):
            # A condition can only be violated over a Quantity, so this is
            # unreachable from an assessment made over this same context.
            continue  # pragma: no cover
        row = table.row(condition.name)
        if row is None:  # pragma: no cover - the table refuses to omit one
            continue
        if condition.maximum is not None and observed.compare(condition.maximum) > 0:
            side, bound, inclusive = (
                "maximum", condition.maximum, condition.maximum_inclusive
            )
        else:
            side, bound, inclusive = (
                "minimum", condition.minimum, condition.minimum_inclusive
            )

        hints: list[RepairHint] = []
        refusals: list[RepairRefusal] = [
            RepairRefusal(condition.name, r.target, r.reason)
            for r in row.refusals
        ]
        for inversion in row.inversions:
            target = RepairTarget(model, inversion.target)
            # The route is resolved first. "This input does not enter the
            # group on the route you declared" is a stronger and more useful
            # statement than "you did not declare it", and when both are true
            # the first is the one that explains the second.
            exponent = inversion.resolve_exponent(values)
            if exponent is None:
                refusals.append(
                    RepairRefusal(
                        condition.name, inversion.target, inversion.unavailable
                    )
                )
                continue
            declared = values.get(inversion.target)
            if not isinstance(declared, Quantity):
                refusals.append(
                    RepairRefusal(
                        condition.name,
                        inversion.target,
                        "not declared here, so there is no value to change",
                    )
                )
                continue
            # A declared offset that cannot be formed is refused, never read
            # as zero. Zero is a different algebraic claim — it would turn an
            # affine form into a power law — and defaulting to it would emit a
            # confident hint from an inversion that was never available.
            offset: Quantity | None = None
            if inversion.offset is not None:
                offset = inversion.offset(values)
                if not isinstance(offset, Quantity):
                    refusals.append(
                        RepairRefusal(
                            condition.name,
                            inversion.target,
                            "the offset of the declared form could not be "
                            "formed from this context, so the form is not "
                            "anchored and nothing here is invertible",
                        )
                    )
                    continue
            outcome = invert_range_condition(
                condition=condition,
                observed=observed,
                declared=declared,
                target=target,
                exponent=exponent,
                offset=offset,
                must_stay_positive=inversion.must_stay_positive,
                justification=inversion.justification,
                admissible_maximum=inversion.admissible_maximum,
                beyond_admissible=inversion.beyond_admissible,
            )
            if isinstance(outcome, RepairHint):
                hints.append(outcome)
            else:
                refusals.append(
                    RepairRefusal(condition.name, inversion.target, outcome)
                )

        repairs.append(
            ConditionRepair(
                model_id=model.model_id,
                subject=subject,
                condition=condition.name,
                observed=observed,
                bound=bound,
                bound_side=side,
                bound_inclusive=inclusive,
                hints=tuple(hints),
                refusals=tuple(refusals),
            )
        )
    return tuple(repairs)


def merge_repairs(
    groups: Iterable[Sequence[ConditionRepair]],
) -> tuple[ConditionRepair, ...]:
    """Every repair from every site, in a stable order and never combined.

    Two sites that violate the same condition keep two repairs, because their
    declarations differ and so do their thresholds. Choosing between them would
    be the ranking this module refuses to do.
    """
    collected: list[ConditionRepair] = []
    for group in groups:
        collected.extend(group)
    return tuple(
        sorted(collected, key=lambda r: (r.model_id, r.subject, r.condition))
    )


# =====================================================================
# Conditions that were never assessed — guidance, and the refusal to invent it
# =====================================================================
#
# Everything above this line is about a **violated** condition: one that was
# assessed, found outside its bound, and can therefore be inverted into "move
# this declaration to here". A condition that was never assessed has no bound
# to invert toward and no observed value to invert from, and the single most
# damaging thing this module could do is produce a number for one anyway.
#
# It never has: `condition_repairs` iterates `_violated_range_conditions`, so
# an unknown condition has never reached a hint. What was missing is the other
# half — saying anything useful about it at all. Before reasons existed there
# was nothing useful to say: every unknown arrived as a bare name, and
# "declare `body_conductivity` and `biot_number` becomes assessable" was
# indistinguishable from "this cannot be assessed at all".


@dataclass(frozen=True)
class Unassessable:
    """One condition that was not assessed, and what the caller can do.

    ``actionable`` is the whole point of this record. It is true for exactly
    one reason — ``NOT_SUPPLIED`` — and a consumer that shows a user "here is
    what to fix" should show these and only these.
    """

    condition: str
    reason: UnknownReason
    actionable: bool
    guidance: str


#: What to tell a reader for each declared situation. A mapping rather than a
#: chain of `if`s so that a new `UnknownReason` member fails loudly here —
#: `unassessable_guidance` raises on a reason it has no sentence for, instead
#: of falling through to a default that would quietly say the wrong thing
#: about a situation nobody had considered.
_GUIDANCE: dict[UnknownReason, tuple[bool, str]] = {
    UnknownReason.NOT_SUPPLIED: (
        True,
        "declare {condition} and this condition becomes assessable",
    ),
    UnknownReason.UNREADABLE_SHAPE: (
        False,
        "{condition} was supplied in a shape this core cannot evaluate a "
        "condition over. Declaring it again will not help: the gap is in the "
        "core, not in the declaration",
    ),
    UnknownReason.CONSERVATIVE_SCREEN: (
        False,
        "{condition} is a deliberately conservative screen and this run did "
        "not clear it. That is not a finding against the run — it was not "
        "shown wrong, and may still be fine",
    ),
    UnknownReason.PREREQUISITE_NOT_ESTABLISHED: (
        False,
        "{condition} cannot be assessed until its prerequisite is established. "
        "Repair the prerequisite; there is nothing to change about this one",
    ),
}


def unassessable_guidance(
    assessment: ValidityAssessment,
) -> tuple[Unassessable, ...]:
    """What to say about each condition the assessment could not evaluate.

    **No numbers, ever.** This returns guidance and never a
    :class:`RepairHint`: a hint states the value a declaration would have to
    take for a bound to be met, and a condition that was never assessed has
    neither a bound it failed nor an observed value to move. Fabricating one
    would be the most damaging thing this module could do, because it would
    look exactly like the hints that are real.

    Ordered by condition name so two runs of the same assessment produce the
    same guidance.
    """
    out: list[Unassessable] = []
    for entry in sorted(assessment.unknown_reasons, key=lambda e: e.name):
        try:
            actionable, template = _GUIDANCE[entry.reason]
        except KeyError as exc:  # pragma: no cover - a new enum member
            raise RepairGuidanceError(
                f"no guidance is written for unknown-reason "
                f"{entry.reason.value!r}. A reason without a sentence must "
                f"fail here rather than fall through to a default that would "
                f"say the wrong thing about a situation nobody considered"
            ) from exc
        out.append(
            Unassessable(
                condition=entry.name,
                reason=entry.reason,
                actionable=actionable,
                guidance=template.format(condition=entry.name),
            )
        )
    return tuple(out)


def actionable_declarations(
    assessment: ValidityAssessment,
) -> tuple[str, ...]:
    """The conditions a caller could unlock by declaring something.

    The short answer to "what should I supply?", and the reason this gate
    exists: before reasons, this list could not be computed at all without
    guessing, because a condition the core cannot read looks identical to one
    nobody declared.
    """
    return tuple(
        item.condition for item in unassessable_guidance(assessment) if item.actionable
    )
