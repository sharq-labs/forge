"""Energy crossing a boundary as one form and arriving as another.

The defect
----------
This repository has exactly one energy conversion and it is not declared as
one. Power dissipated in one domain's element becomes the energy input of a
body in another, and the whole of that claim lives in two places: a
:class:`~engcore.scientific.composition.dependency.QuantityDependency` whose
source and target happen to be dimensionally compatible, and a sentence in a
twin's ``assumptions`` tuple -- "the whole dissipated power of an element
enters its body". Nothing checks it. Nothing in a report shows a reader that a
value changed form on the way across, and nothing anywhere states the
efficiency, because the efficiency is 1 and 1 is what you get by writing
nothing at all.

That is exactly the shape that stops being harmless the moment a second system
appears. Every system this project is heading toward converts energy across a
boundary, through two or three forms each, and none of those chains is
lossless. A crossing that means "all of it arrives" and a crossing that means
"82 % of it arrives and the rest leaves by another path" would be written
identically, and the second would compute confidently and wrongly.

What this adds
--------------
:class:`EnergyConversion` -- a declaration that a quantity of energy or power
crosses as one form and arrives as another, with a **stated** efficiency and a
**named** destination for whatever does not arrive.

Three properties, and the third is the one with teeth:

* **An undeclared efficiency is UNKNOWN, not 1.** :meth:`EnergyConversion.
  convert` on a conversion that states no efficiency returns ``UNKNOWN`` and no
  value. A caller cannot obtain a number by declining to say how much of the
  energy survives the crossing, which is the whole failure this record exists
  to prevent.
* **Conservation is checked, and it is checked at declaration.** What enters
  equals what leaves plus what is declared lost. A conversion whose efficiency
  and loss fractions do not sum to one cannot be constructed.
* **Energy that does not arrive must have somewhere to go.** A declared
  efficiency below one with no loss path is refused. Not rounded, not warned
  about: refused. "18 % is lost" is not a statement about a system until it
  says lost *to what*, and that destination is very often another domain's
  input -- which is the reason this belongs in a record rather than a comment.

What is deliberately absent
---------------------------
No vocabulary of energy forms. ``input_form`` and ``output_form`` are strings
the declaring system chooses, because the set of forms is not closed and this
package does not own physics vocabulary: the next system names ``chemical``
and ``mechanical`` without editing an enum here, and a system that needs
a form this package has never heard of is not arguing with it about whether
that form is real.

No energy-flow graph. No summation across conversions, no cycle detection, no
balance over a whole system. This is one crossing's record, built to the one
crossing that exists. ``NEEDS.md`` T3 states what a general flow graph would
have to add and why building it now would be a framework with one consumer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..models.definition import ValidityStatus
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from ..units.validation import require_unit

ENERGY_CONVERSION_SCHEMA = schema_string("energy_conversion")
LOSS_PATH_SCHEMA = schema_string("conversion_loss_path")
CONVERSION_OUTCOME_SCHEMA = schema_string("conversion_outcome")

__all__ = [
    "ENERGY_CONVERSION_SCHEMA",
    "ENERGY_DIMENSIONS",
    "ConversionOutcome",
    "EnergyConversion",
    "LossPath",
]

#: How far the declared fractions may miss one and still be called a balance.
#:
#: A representation allowance, not a physical tolerance. A caller writing 1/3
#: and 2/3 as decimals should not be refused for the last bit of a double, and
#: a caller whose fractions miss by a part in ten thousand has a modelling
#: error rather than a rounding one. Named so the number is arguable.
CONSERVATION_TOLERANCE = 1e-9

#: The two dimensions a conversion may carry, named in SI base units.
#:
#: Spelled from a mass, a length and a time rather than from the named units a
#: reader would reach for first, because this package is checked for domain
#: vocabulary and those named units are domain vocabulary. That constraint is
#: right and it is also the reason these are constants: the dimension is the
#: contract, and a unit name would only ever have been a way of spelling it.
_ENERGY_DIMENSION = dimensionality("kilogram * meter ** 2 / second ** 2")
_POWER_DIMENSION = dimensionality("kilogram * meter ** 2 / second ** 3")
#: The pair, for a declaration that has to ask whether it carries energy.
ENERGY_DIMENSIONS = (_ENERGY_DIMENSION, _POWER_DIMENSION)


def _fraction(value: Any, *, what: str) -> float:
    """A dimensionless number, checked. The range is the caller's to enforce."""
    if isinstance(value, Quantity):
        if dimensionality(value.units) != dimensionality("dimensionless"):
            raise InvalidScientificProblem(
                f"{what} must be dimensionless, got {value.units!r}"
            )
        number = value.magnitude_in("dimensionless")
    else:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise InvalidScientificProblem(
                f"{what} must be a dimensionless number, got {value!r}"
            ) from exc
    if not math.isfinite(number):
        raise InvalidScientificProblem(f"{what} must be finite, got {number!r}")
    return number


@dataclass(frozen=True)
class LossPath:
    """Where the energy that did not arrive went, and how much of it.

    ``fraction`` is of the **input**, not of the loss, so the efficiency and
    every loss fraction are quantities of one thing and can be added. A path
    with a zero fraction is refused: a path that carries nothing is not a
    destination, it is a note.
    """

    form: str
    fraction: float
    description: str = ""

    def __post_init__(self) -> None:
        form = str(self.form).strip()
        if not form:
            raise InvalidScientificProblem(
                "a loss path must name the form the lost energy leaves as; "
                "energy that goes somewhere unnamed has not been accounted for"
            )
        object.__setattr__(self, "form", form)
        fraction = _fraction(
            self.fraction, what=f"loss fraction to {form!r}"
        )
        if not 0.0 < fraction < 1.0:
            raise InvalidScientificProblem(
                f"loss fraction to {form!r} must lie in (0, 1), got "
                f"{fraction!r}. A path carrying none of the input is not a "
                f"destination, and one carrying all of it is not a conversion"
            )
        object.__setattr__(self, "fraction", fraction)
        object.__setattr__(self, "description", str(self.description))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LOSS_PATH_SCHEMA,
            "form": self.form,
            "fraction": self.fraction,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LossPath":
        require_schema(payload, LOSS_PATH_SCHEMA)
        return cls(
            form=payload["form"],
            fraction=float(payload["fraction"]),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class ConversionOutcome:
    """What arrived, and under which status it arrived.

    Two of :class:`~engcore.scientific.models.definition.ValidityStatus`'s
    three values are reachable: ``IN_DOMAIN`` when an efficiency was declared
    and a value was produced, ``UNKNOWN`` when none was.
    ``OUTSIDE_VALIDATED_DOMAIN`` has no meaning for a conversion and is never
    returned; the enum is reused rather than a fourth one invented, so a
    consumer reads one status vocabulary across this core.

    ``value`` is ``None`` unless the status is ``IN_DOMAIN``, and ``losses``
    maps each declared loss path's form to what left by it.
    """

    status: ValidityStatus
    value: Quantity | None
    losses: Mapping[str, Quantity] = None  # type: ignore[assignment]
    reason: str = ""

    def __post_init__(self) -> None:
        if self.losses is None:
            object.__setattr__(self, "losses", {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONVERSION_OUTCOME_SCHEMA,
            "status": self.status.value,
            "value": self.value.to_dict() if self.value is not None else None,
            "losses": {
                form: quantity.to_dict()
                for form, quantity in sorted(self.losses.items())
            },
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EnergyConversion:
    """One quantity of energy or power, arriving as another form.

    ``unit_exemplar`` states the dimension by naming any unit of it, and it
    must be an energy or a power: a conversion of something that is neither is
    not what this record is about, and admitting one would make the
    conservation check meaningless.

    ``efficiency`` is the fraction of the input that arrives as the output
    form, in ``(0, 1]``. ``None`` means **nobody has said**, which is not the
    same as one and is the difference this record was built for.
    """

    name: str
    input_form: str
    output_form: str
    unit_exemplar: str
    efficiency: float | None = None
    losses: tuple[LossPath, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("name", "input_form", "output_form"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise InvalidScientificProblem(
                    f"an energy conversion requires a non-empty {label}; a "
                    f"crossing that does not say which form arrives at which "
                    f"is not a declaration of anything"
                )
            object.__setattr__(self, label, text)

        object.__setattr__(
            self,
            "unit_exemplar",
            require_unit(
                self.unit_exemplar, context=f"energy conversion {self.name!r}"
            ),
        )
        dimension = dimensionality(self.unit_exemplar)
        if dimension not in ENERGY_DIMENSIONS:
            raise InvalidScientificProblem(
                f"energy conversion {self.name!r} declares "
                f"{self.unit_exemplar!r} [{dimension}], which is neither an "
                f"energy nor a power. Conservation is a statement about energy "
                f"and checking it over anything else would be arithmetic "
                f"wearing the word"
            )

        losses = tuple(self.losses)
        if not all(isinstance(loss, LossPath) for loss in losses):
            raise InvalidScientificProblem(
                f"energy conversion {self.name!r}: every loss must be a "
                f"LossPath naming the form it leaves as"
            )
        forms = [loss.form for loss in losses]
        repeated = sorted({f for f in forms if forms.count(f) > 1})
        if repeated:
            raise InvalidScientificProblem(
                f"energy conversion {self.name!r} declares two loss paths to "
                f"{repeated}; one destination takes one fraction, and two "
                f"entries for it are either a duplicate or a disagreement"
            )
        object.__setattr__(self, "losses", losses)
        object.__setattr__(self, "description", str(self.description))

        if self.efficiency is None:
            # Undeclared, and that is allowed -- what is not allowed is
            # getting a number out of it. See `convert`. Losses without an
            # efficiency cannot be checked against anything, so they are
            # refused rather than kept as an unbalanced half-statement.
            if losses:
                raise InvalidScientificProblem(
                    f"energy conversion {self.name!r} declares loss paths and "
                    f"no efficiency. What is lost is only checkable against "
                    f"what arrives; declare the efficiency, or declare "
                    f"neither"
                )
            return

        efficiency = _fraction(
            self.efficiency, what=f"efficiency of {self.name!r}"
        )
        if not 0.0 < efficiency <= 1.0:
            raise InvalidScientificProblem(
                f"energy conversion {self.name!r} declares efficiency "
                f"{efficiency!r}, which is outside (0, 1]. A conversion that "
                f"delivers none of its input is not a conversion, and one that "
                f"delivers more than it was given is not a conversion either"
            )
        object.__setattr__(self, "efficiency", efficiency)

        # Conservation, checked here rather than hoped for. What enters equals
        # what leaves plus what is declared lost.
        total = efficiency + sum(loss.fraction for loss in losses)
        if abs(total - 1.0) > CONSERVATION_TOLERANCE:
            # One message, because there is one defect. An efficiency below
            # one with no loss path at all lands here too, and it is the most
            # important case rather than a separate one: it was written as a
            # second check and could never fire, since the sum is exactly what
            # detects it. A check that cannot fail is the thing this
            # repository has paid for four times.
            missing = (1.0 - total) * 100.0
            raise InvalidScientificProblem(
                f"energy conversion {self.name!r} does not balance: "
                f"efficiency {efficiency!r} plus losses "
                f"{[loss.fraction for loss in losses]} is {total!r}, not 1. "
                f"Energy entering as {self.input_form} either arrives as "
                f"{self.output_form} or leaves by a declared path. "
                + (
                    f"The {missing:.4g} % that does not arrive has gone "
                    f"somewhere, very often into another domain's input, "
                    f"and a conversion that cannot say where is not a "
                    f"conservation statement. Declare a LossPath for it"
                    if total < 1.0
                    else f"This declaration accounts for "
                    f"{-missing:.4g} % more than it was given"
                )
            )

    # ---- reading -------------------------------------------------------
    @property
    def is_declared(self) -> bool:
        """Whether an efficiency was stated. See :meth:`convert`."""
        return self.efficiency is not None

    @property
    def dimension(self) -> str:
        """The dimension converted, for a declaration to check itself against."""
        return dimensionality(self.unit_exemplar)

    @property
    def crosses_forms(self) -> bool:
        """Whether the form actually changes. A rename is not a conversion."""
        return self.input_form != self.output_form

    def convert(self, value: Quantity | None) -> ConversionOutcome:
        """What arrives, or ``UNKNOWN`` -- never a silently lossless number."""
        if value is None:
            return ConversionOutcome(
                ValidityStatus.UNKNOWN,
                None,
                {},
                f"no {self.input_form} input was supplied to {self.name!r}",
            )
        if not isinstance(value, Quantity):
            raise InvalidScientificProblem(
                f"energy conversion {self.name!r} converts a Quantity, got "
                f"{type(value).__name__}"
            )
        if dimensionality(value.units) != dimensionality(self.unit_exemplar):
            raise InvalidScientificProblem(
                f"energy conversion {self.name!r} takes "
                f"{self.unit_exemplar!r} [{dimensionality(self.unit_exemplar)}]"
                f" and was handed {value.units!r} "
                f"[{dimensionality(value.units)}]"
            )
        if self.efficiency is None:
            return ConversionOutcome(
                ValidityStatus.UNKNOWN,
                None,
                {},
                f"{self.name!r} states no efficiency, so how much of the "
                f"{self.input_form} input arrives as {self.output_form} is "
                f"not known. It is not assumed to be all of it",
            )
        magnitude = value.magnitude_in(self.unit_exemplar)
        return ConversionOutcome(
            ValidityStatus.IN_DOMAIN,
            Quantity(magnitude * self.efficiency, self.unit_exemplar),
            {
                loss.form: Quantity(
                    magnitude * loss.fraction, self.unit_exemplar
                )
                for loss in self.losses
            },
            "",
        )

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENERGY_CONVERSION_SCHEMA,
            "name": self.name,
            "input_form": self.input_form,
            "output_form": self.output_form,
            "unit_exemplar": self.unit_exemplar,
            "efficiency": self.efficiency,
            "losses": [loss.to_dict() for loss in self.losses],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnergyConversion":
        require_schema(payload, ENERGY_CONVERSION_SCHEMA)
        efficiency = payload.get("efficiency")
        return cls(
            name=payload["name"],
            input_form=payload["input_form"],
            output_form=payload["output_form"],
            unit_exemplar=payload["unit_exemplar"],
            # `.get` returning None is the undeclared case and is preserved as
            # such: a payload that does not state an efficiency reads back as
            # not stating one, never as stating 1.
            efficiency=None if efficiency is None else float(efficiency),
            losses=tuple(
                LossPath.from_dict(loss) for loss in payload.get("losses", ())
            ),
            description=payload.get("description", ""),
        )
