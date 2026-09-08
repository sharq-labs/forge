"""A model input that is a declared function of one variable, not a constant.

The defect
----------
A model input is a single :class:`~engcore.scientific.units.quantity.Quantity`.
That is right for a quantity that does not move, and it is a **claim** for one
that does. An audit of this repository found seven inputs held fixed which the
owning model's own prose says vary with state: an open-circuit voltage against
charge, a heat capacity against temperature, a conductance against temperature
difference, a resistance against voltage, a temperature coefficient's higher
order, a vessel volume against time.

None of those is a coding error. Each computes exactly what it says. The claim
is simply wider than the capability: the record says "this input is this
number", and the model's own description says the number moves. A caller
reading the record cannot see the difference.

What this adds
--------------
:class:`DeclaredCurve` -- an input **declared as a function of one named
variable, over a stated interval, in a stated form**. It is evidence about the
interval it covers and about nothing else.

Four properties, each of which exists because its absence is a way to be
confidently wrong:

* **The independent variable is declared, never inferred.** A table of pairs
  is not a curve; it is a table of pairs. Which axis it is against is a fact
  about the measurement, and a caller who hands over a table and lets the
  consumer guess has not declared anything. :attr:`DeclaredCurve.against`
  carries the name and refuses to be empty.
* **The interval is declared, and outside it there is no number.** Evaluation
  outside the declared interval returns ``OUTSIDE_VALIDATED_DOMAIN`` and **no
  value**. Not an extrapolation, not the nearest endpoint. A curve measured
  from 0 to 1 says nothing at 1.2, and the honest report of that is a refusal
  to answer.
* **Absence is still UNKNOWN.** Evaluating with no input returns ``UNKNOWN``
  and no value, which is what every other unsupplied input in this core does.
  This mechanism widens what a caller *may* declare; it requires nothing.
* **It is structured data, so it can be written down.** No callable is ever
  stored. This is the same rule the record-writability refusal states -- a
  record that cannot be written down cannot be built -- reaching the one place
  where "a function" would have been the obvious implementation and would have
  produced a model record that no reader could reconstruct and no digest could
  cover. Every form here serializes to primitives, round-trips, and hashes.

The forms, and why exactly these
--------------------------------
Two primitives and one composition. The set is chosen to express the audited
seven and stops there; it is deliberately not an expression language.

* :class:`TabulatedForm` -- sample pairs plus a **stated** interpolation.
  Measured curves arrive this way. The interpolation is part of the
  declaration because linear and previous-value interpolation of the same
  samples are different claims about what happens between them.
* :class:`PolynomialForm` -- coefficients in ascending order about a stated
  reference point. Fitted correlations arrive this way, and a coefficient
  series is how a first-order model states the higher order it is dropping.
* :class:`PiecewiseForm` -- ordered polynomial pieces over declared
  breakpoints. Regime changes arrive this way: a stage that fills and then
  holds, a response with a knee. It is a composition of the second primitive
  rather than a third one.

What is deliberately absent: exponentials, logarithms, arbitrary expressions,
and functions of more than one variable. The first three would make the record
unreadable without an evaluator and unbounded to validate. The fourth is a real
limit and is named in ``NEEDS.md``: one of the audited seven varies with two
variables at once and cannot be expressed here.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Union

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_unit

CURVE_SCHEMA = schema_string("declared_curve")
TABULATED_FORM_SCHEMA = schema_string("curve_tabulated_form")
POLYNOMIAL_FORM_SCHEMA = schema_string("curve_polynomial_form")
PIECEWISE_FORM_SCHEMA = schema_string("curve_piecewise_form")
CURVE_EVALUATION_SCHEMA = schema_string("curve_evaluation")

__all__ = [
    "CURVE_SCHEMA",
    "CurveEvaluation",
    "DeclaredCurve",
    "Interpolation",
    "PiecewiseForm",
    "PolynomialForm",
    "TabulatedForm",
    "decode_curve_form",
]


def _finite(value: Any, *, what: str) -> float:
    """A coefficient, a sample or a bound. Non-finite is refused here.

    The same rule ``Quantity`` applies to a magnitude, applied to the numbers
    that *make* a magnitude. A curve holding a NaN produces a NaN from an
    input well inside its declared interval, which is the failure this whole
    module exists to prevent, arriving by a different door.
    """
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidScientificProblem(
            f"{what} must be a real number, got {value!r}"
        ) from exc
    if not math.isfinite(number):
        raise InvalidScientificProblem(f"{what} must be finite, got {number!r}")
    return number


class Interpolation(str, Enum):
    """What a tabulated curve claims happens *between* its samples."""

    LINEAR = "linear"
    #: Zero-order hold: the value holds at the last sample at or below the
    #: input. For a curve whose samples are step changes rather than points
    #: on a continuum.
    PREVIOUS = "previous"


@dataclass(frozen=True)
class PolynomialForm:
    """``sum(c[i] * (x - reference) ** i)`` -- coefficients ascending.

    ``reference`` is part of the declaration rather than a convenience: a
    series about 0 and the same series about 298.15 are different functions,
    and a correlation published about a reference point loses its meaning if
    the point is dropped.
    """

    coefficients: tuple[float, ...]
    reference: float = 0.0

    def __post_init__(self) -> None:
        coefficients = tuple(
            _finite(c, what=f"polynomial coefficient {i}")
            for i, c in enumerate(self.coefficients)
        )
        if not coefficients:
            raise InvalidScientificProblem(
                "a polynomial form needs at least one coefficient; a form "
                "with none is not a constant, it is an undeclared function"
            )
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(
            self, "reference", _finite(self.reference, what="polynomial reference")
        )

    @property
    def degree(self) -> int:
        return len(self.coefficients) - 1

    def evaluate(self, x: float) -> float:
        """Horner's rule, so the arithmetic does not depend on the degree."""
        shifted = x - self.reference
        total = 0.0
        for coefficient in reversed(self.coefficients):
            total = total * shifted + coefficient
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": POLYNOMIAL_FORM_SCHEMA,
            "form": "polynomial",
            "coefficients": list(self.coefficients),
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PolynomialForm":
        require_schema(payload, POLYNOMIAL_FORM_SCHEMA)
        return cls(
            coefficients=tuple(payload["coefficients"]),
            reference=float(payload.get("reference", 0.0)),
        )


@dataclass(frozen=True)
class TabulatedForm:
    """Measured samples plus the interpolation the declarer claims between them.

    Samples are ``(independent, dependent)`` pairs in the curve's declared
    units, strictly ascending in the independent value. Strictly, not merely
    non-decreasing: two samples at one input are two contradicting
    measurements, and choosing between them by list order is not a decision
    this record will make on a caller's behalf.
    """

    samples: tuple[tuple[float, float], ...]
    interpolation: Interpolation = Interpolation.LINEAR

    def __post_init__(self) -> None:
        samples = tuple(
            (
                _finite(pair[0], what=f"sample {i} independent value"),
                _finite(pair[1], what=f"sample {i} dependent value"),
            )
            for i, pair in enumerate(self.samples)
        )
        if len(samples) < 2:
            raise InvalidScientificProblem(
                f"a tabulated form needs at least two samples to describe a "
                f"function of anything, got {len(samples)}"
            )
        for earlier, later in zip(samples, samples[1:]):
            if later[0] <= earlier[0]:
                raise InvalidScientificProblem(
                    f"tabulated samples must ascend strictly in the "
                    f"independent value; {later[0]!r} does not follow "
                    f"{earlier[0]!r}"
                )
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "interpolation", Interpolation(self.interpolation))

    @property
    def covers(self) -> tuple[float, float]:
        """The interval the samples actually span."""
        return (self.samples[0][0], self.samples[-1][0])

    def evaluate(self, x: float) -> float:
        lo_x, lo_y = self.samples[0]
        if x <= lo_x:
            return lo_y
        for (left_x, left_y), (right_x, right_y) in zip(
            self.samples, self.samples[1:]
        ):
            if x <= right_x:
                if self.interpolation is Interpolation.PREVIOUS:
                    return left_y if x < right_x else right_y
                span = right_x - left_x
                return left_y + (right_y - left_y) * (x - left_x) / span
        return self.samples[-1][1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TABULATED_FORM_SCHEMA,
            "form": "tabulated",
            "samples": [[x, y] for x, y in self.samples],
            "interpolation": self.interpolation.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TabulatedForm":
        require_schema(payload, TABULATED_FORM_SCHEMA)
        return cls(
            samples=tuple(
                (float(pair[0]), float(pair[1])) for pair in payload["samples"]
            ),
            interpolation=Interpolation(payload.get("interpolation", "linear")),
        )


@dataclass(frozen=True)
class PiecewiseForm:
    """Polynomial pieces over declared breakpoints -- for a curve with regimes.

    ``breakpoints`` are the interior boundaries, strictly ascending. There is
    one more piece than there are breakpoints, and piece ``i`` applies where
    the input is below ``breakpoints[i]`` (the last piece applies at and above
    the last breakpoint). Each piece carries its own reference point, so a
    piece fitted about its own regime does not have to be re-expressed about
    the curve's origin.

    Continuity at a breakpoint is **not** required and not checked. A regime
    change that is genuinely a step -- a stage ending, a device switching --
    is a discontinuity, and a record that refused one could not express it.
    """

    breakpoints: tuple[float, ...]
    pieces: tuple[PolynomialForm, ...]

    def __post_init__(self) -> None:
        breakpoints = tuple(
            _finite(b, what=f"breakpoint {i}")
            for i, b in enumerate(self.breakpoints)
        )
        for earlier, later in zip(breakpoints, breakpoints[1:]):
            if later <= earlier:
                raise InvalidScientificProblem(
                    f"piecewise breakpoints must ascend strictly, "
                    f"{later!r} does not follow {earlier!r}"
                )
        pieces = tuple(self.pieces)
        if not all(isinstance(p, PolynomialForm) for p in pieces):
            raise InvalidScientificProblem(
                "every piecewise piece must be a PolynomialForm"
            )
        if len(pieces) != len(breakpoints) + 1:
            raise InvalidScientificProblem(
                f"a piecewise form needs one more piece than it has "
                f"breakpoints; got {len(pieces)} piece(s) and "
                f"{len(breakpoints)} breakpoint(s)"
            )
        object.__setattr__(self, "breakpoints", breakpoints)
        object.__setattr__(self, "pieces", pieces)

    def evaluate(self, x: float) -> float:
        for index, boundary in enumerate(self.breakpoints):
            if x < boundary:
                return self.pieces[index].evaluate(x)
        return self.pieces[-1].evaluate(x)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PIECEWISE_FORM_SCHEMA,
            "form": "piecewise",
            "breakpoints": list(self.breakpoints),
            "pieces": [piece.to_dict() for piece in self.pieces],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PiecewiseForm":
        require_schema(payload, PIECEWISE_FORM_SCHEMA)
        return cls(
            breakpoints=tuple(float(b) for b in payload["breakpoints"]),
            pieces=tuple(PolynomialForm.from_dict(p) for p in payload["pieces"]),
        )


#: The closed set. A payload naming anything else is refused rather than
#: guessed at, which is what makes the set a contract instead of a convention.
_FORM_READERS = {
    "tabulated": TabulatedForm.from_dict,
    "polynomial": PolynomialForm.from_dict,
    "piecewise": PiecewiseForm.from_dict,
}

CurveForm = Union[TabulatedForm, PolynomialForm, PiecewiseForm]


def decode_curve_form(payload: Mapping[str, Any]) -> CurveForm:
    """Read one form back, by its declared tag."""
    tag = payload.get("form")
    reader = _FORM_READERS.get(str(tag))
    if reader is None:
        raise InvalidScientificProblem(
            f"unknown curve form {tag!r}; expected one of {sorted(_FORM_READERS)}"
        )
    return reader(payload)


@dataclass(frozen=True)
class CurveEvaluation:
    """What a curve answered, and under which of the three statuses.

    ``value`` is ``None`` unless ``status`` is ``IN_DOMAIN``. That is the
    whole point: a caller that reads ``value`` without reading ``status``
    gets nothing rather than an extrapolation.
    """

    status: Any
    value: Quantity | None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CURVE_EVALUATION_SCHEMA,
            "status": getattr(self.status, "value", self.status),
            "value": self.value.to_dict() if self.value is not None else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DeclaredCurve:
    """One quantity, declared as a function of one named variable.

    ``against`` names the independent variable; ``against_unit`` states its
    dimension by naming any unit of it; ``unit`` states the dimension of the
    value the curve gives. ``lower`` and ``upper`` bound the declared interval
    **in ``against_unit``** and are the edge of the evidence, not of the
    arithmetic -- the form would happily produce a number outside them, and
    this record will not hand it over.
    """

    quantity: str
    against: str
    against_unit: str
    unit: str
    lower: float
    upper: float
    form: CurveForm
    source: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("quantity", "against"):
            name = str(getattr(self, label)).strip()
            if not name:
                raise InvalidScientificProblem(
                    f"a declared curve requires a non-empty {label!r}: a "
                    f"curve that does not say what it gives and what it "
                    f"varies with is a table of numbers, and a consumer "
                    f"would have to guess which axis is which"
                )
            object.__setattr__(self, label, name)
        object.__setattr__(
            self,
            "against_unit",
            require_unit(
                self.against_unit,
                context=f"curve {self.quantity!r} independent unit",
            ),
        )
        object.__setattr__(
            self,
            "unit",
            require_unit(self.unit, context=f"curve {self.quantity!r} value unit"),
        )
        lower = _finite(self.lower, what=f"curve {self.quantity!r} lower bound")
        upper = _finite(self.upper, what=f"curve {self.quantity!r} upper bound")
        if upper <= lower:
            raise InvalidScientificProblem(
                f"curve {self.quantity!r} declares the interval "
                f"[{lower!r}, {upper!r}] in {self.against_unit!r}, which is "
                f"empty or inverted; a curve is evidence over an interval and "
                f"an empty one is evidence about nothing"
            )
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)

        form = self.form
        if not isinstance(form, (TabulatedForm, PolynomialForm, PiecewiseForm)):
            raise InvalidScientificProblem(
                f"curve {self.quantity!r} form must be one of the declared "
                f"forms, got {type(form).__name__}"
            )

        # A declared interval wider than the samples is a claim of evidence
        # that was never taken. The form would interpolate happily out to the
        # last sample and then hold flat, and holding flat past the data is
        # exactly the silent extrapolation this record exists to refuse -- so
        # it is refused at declaration rather than at evaluation, where the
        # caller could no longer tell it from a real measurement.
        if isinstance(form, TabulatedForm):
            first, last = form.covers
            if lower < first or upper > last:
                raise InvalidScientificProblem(
                    f"curve {self.quantity!r} declares the interval "
                    f"[{lower!r}, {upper!r}] but its samples cover only "
                    f"[{first!r}, {last!r}]; a declared interval reaching "
                    f"past the samples claims evidence that was not measured"
                )

        # A breakpoint outside the declared interval divides a region the
        # curve refuses to answer in, so it is either a mistake about the
        # interval or a mistake about the breakpoint. Either way it is not
        # this record's job to decide which.
        if isinstance(form, PiecewiseForm):
            stray = [b for b in form.breakpoints if not lower < b < upper]
            if stray:
                raise InvalidScientificProblem(
                    f"curve {self.quantity!r} has breakpoint(s) {stray} "
                    f"outside its declared interval [{lower!r}, {upper!r}]"
                )

        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "description", str(self.description))

    # ---- evaluation ----------------------------------------------------
    def evaluate(self, value: Quantity | None) -> CurveEvaluation:
        """Three outcomes, and only one of them carries a number.

        The status enum is imported here rather than at module scope: it
        lives in the model-definition module, which imports this one, and a
        module-scope import in this direction would close the cycle.
        """
        from .definition import ValidityStatus

        if value is None:
            return CurveEvaluation(
                ValidityStatus.UNKNOWN,
                None,
                f"{self.against} was not supplied, so {self.quantity} "
                f"cannot be evaluated",
            )
        if not value.is_compatible_with(self.against_unit):
            raise InvalidScientificProblem(
                f"curve {self.quantity!r} varies with {self.against!r} in "
                f"{self.against_unit!r}, but was handed {value.units!r}"
            )
        x = value.magnitude_in(self.against_unit)
        if x < self.lower or x > self.upper:
            return CurveEvaluation(
                ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
                None,
                f"{self.against} = {x} {self.against_unit} is outside the "
                f"interval [{self.lower}, {self.upper}] this curve was "
                f"declared over; {self.quantity} is not extrapolated",
            )
        return CurveEvaluation(
            ValidityStatus.IN_DOMAIN,
            Quantity(self.form.evaluate(x), self.unit),
            "",
        )

    # ---- identity ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CURVE_SCHEMA,
            "quantity": self.quantity,
            "against": self.against,
            "against_unit": self.against_unit,
            "unit": self.unit,
            "lower": self.lower,
            "upper": self.upper,
            "form": self.form.to_dict(),
            "source": self.source,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeclaredCurve":
        require_schema(payload, CURVE_SCHEMA)
        return cls(
            quantity=payload["quantity"],
            against=payload["against"],
            against_unit=payload["against_unit"],
            unit=payload["unit"],
            lower=float(payload["lower"]),
            upper=float(payload["upper"]),
            form=decode_curve_form(payload["form"]),
            source=payload.get("source", ""),
            description=payload.get("description", ""),
        )

    @property
    def fingerprint(self) -> str:
        """A digest over everything that changes what this curve answers.

        ``source`` and ``description`` are excluded: they say where the
        evidence came from and what it is for, and neither changes a value.
        Two curves with the same digest give the same answer to every input,
        which is the property a physical identity needs from this.
        """
        payload = self.to_dict()
        payload.pop("source", None)
        payload.pop("description", None)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
