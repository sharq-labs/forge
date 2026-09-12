"""What a calibrated parameter IS, as distinct from what it is called.

The gap this closes
-------------------
Before this module the inference layer identified parameters by position in
``parameter_names: tuple[str, ...]`` — a tuple of display strings. Everything
downstream agreed with everything upstream because the *labels* lined up:

* a grid axis called ``"alpha"`` in ``1/kelvin`` and a grid axis called
  ``"alpha"`` in ``1/degC`` were the same parameter to every consumer, and a
  posterior built over one could be used to predict with the other;
* ``"reference_resistance"`` on the linear-TCR model and
  ``"reference_resistance"`` on some other model were the same parameter, so a
  posterior conditioned on one model's data could be handed to the other's
  forward evaluation and nothing would object;
* nothing carried the physical range a parameter is allowed to take, so an
  optimizer returning a negative resistance produced a posterior rather than a
  refusal.

None of those is a labelling nicety. Each one is a scientific claim about a
different quantity than the one the record says it is about.

So a parameter is identified here by everything that makes it that parameter:
its canonical name, the unit its magnitudes are in, the model it belongs to,
the bounds outside which it is not physical, and the transformation (if any)
the inference works in. Two identities are the same parameter only when every
one of those agrees.

What this module is NOT
-----------------------
It is not a prior. Bounds here are the *physical admissible range* — a
resistance is non-negative because resistance is non-negative, not because a
study believes it is. A prior is a statement about belief and belongs to
whatever does the inference; ``ParameterBounds`` is a statement about the
quantity, and a value outside it is refused rather than down-weighted.

It is also not a parameter *value*. An identity says what may be estimated;
``ParameterEstimate`` below binds an identity to one number.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from ..scientific.ir.problem import ModelReference
from ..scientific.sequences import duplicates
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity, normalize_unit

PARAMETER_IDENTITY_SCHEMA = schema_string("calibration_parameter_identity")
PARAMETER_SET_SCHEMA = schema_string("calibration_parameter_set")
PARAMETER_ESTIMATE_SCHEMA = schema_string("calibration_parameter_estimate")

#: Every field that makes an identity the identity it is. Used by both the
#: digest and :meth:`ParameterIdentity.differences`, so the two can never
#: disagree about what counts -- the failure mode where a field is compared but
#: not hashed, or hashed but not reported.
IDENTITY_FIELDS = (
    "name",
    "unit",
    "model_id",
    "model_version",
    "lower",
    "upper",
    "transform",
)


class ParameterIdentityError(ValueError):
    """A parameter declaration that does not describe one parameter."""


class ParameterTransform(str, Enum):
    """The space the inference works in, when it is not the natural one.

    ``LOG`` is here because a strictly positive scale parameter spanning orders
    of magnitude is badly served by a uniform grid in its natural units, and
    because saying so in the identity is the difference between a recorded
    modelling choice and an undocumented one. The transform is part of the
    identity: a posterior built in log space is not interchangeable with one
    built in linear space even for the same quantity with the same bounds.
    """

    IDENTITY = "identity"
    LOG = "log"

    def forward(self, value: float) -> float:
        if self is ParameterTransform.LOG:
            if not (value > 0.0):
                raise ParameterIdentityError(
                    f"a log-transformed parameter cannot take the value {value!r}; "
                    f"the transform is part of the parameter's identity, so this "
                    f"is a contradiction in the declaration rather than a "
                    f"numerical accident"
                )
            return math.log(value)
        return value

    def inverse(self, value: float) -> float:
        if self is ParameterTransform.LOG:
            return math.exp(value)
        return value


@dataclass(frozen=True)
class ParameterBounds:
    """The range outside which the quantity is not physical.

    Inclusive at both ends. A bound equal to the value it bounds is admissible
    -- a resistance of exactly zero is a degenerate conductor, not an invalid
    number -- and a study that wants a strict interior says so with its own
    bound, not by reinterpreting this one.
    """

    lower: Quantity
    upper: Quantity

    def __post_init__(self) -> None:
        for label in ("lower", "upper"):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise ParameterIdentityError(
                    f"parameter bound {label} must be a Quantity, got "
                    f"{type(value).__name__}; a bare number carries no unit and "
                    f"a bound without a unit bounds nothing"
                )
        self.lower.require_compatible(self.upper, context="parameter bounds")
        low = self.lower.magnitude_in(self.lower.units)
        high = self.upper.magnitude_in(self.lower.units)
        if not (math.isfinite(low) and math.isfinite(high)):
            raise ParameterIdentityError("parameter bounds must both be finite")
        if low > high:
            raise ParameterIdentityError(
                f"parameter bounds are inverted: lower {low!r} exceeds upper "
                f"{high!r} in {self.lower.units!r}"
            )

    def contains(self, value: Quantity) -> bool:
        """Whether ``value`` lies in range, compared in the bounds' own unit."""
        if not isinstance(value, Quantity):
            raise ParameterIdentityError("a bound is checked against a Quantity")
        self.lower.require_compatible(value, context="parameter bound check")
        magnitude = value.magnitude_in(self.lower.units)
        if not math.isfinite(magnitude):
            return False
        return (
            self.lower.magnitude_in(self.lower.units)
            <= magnitude
            <= self.upper.magnitude_in(self.lower.units)
        )


@dataclass(frozen=True)
class ParameterIdentity:
    """One calibrated parameter, identified by everything that makes it one.

    ``name`` is canonical, not a display string: it is the name the model's own
    declaration uses. ``unit`` is the unit this parameter's magnitudes are in
    everywhere downstream -- grid coordinates, estimates, bounds -- so that a
    number read out of a posterior means something without consulting anything
    else.
    """

    name: str
    unit: str
    model: ModelReference
    bounds: ParameterBounds
    transform: ParameterTransform = ParameterTransform.IDENTITY

    def __post_init__(self) -> None:
        text = str(self.name).strip()
        if not text:
            raise ParameterIdentityError("a parameter identity requires a name")
        object.__setattr__(self, "name", text)
        if not isinstance(self.model, ModelReference):
            raise ParameterIdentityError(
                f"a parameter identity requires a ModelReference, got "
                f"{type(self.model).__name__}; a parameter with no model is a "
                f"name, and two models' parameters share names routinely"
            )
        if not isinstance(self.bounds, ParameterBounds):
            raise ParameterIdentityError("a parameter identity requires ParameterBounds")
        if not isinstance(self.transform, ParameterTransform):
            raise ParameterIdentityError(
                f"transform must be a ParameterTransform, got {self.transform!r}"
            )
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        # The bounds are what the parameter's magnitudes are read against, so
        # they must be in the parameter's own dimension. Compatible, not
        # identical: a bound may be stated in millivolts for a parameter in
        # volts, and `contains` converts.
        probe = Quantity(0.0, self.unit)
        try:
            probe.require_compatible(self.bounds.lower, context="parameter bounds")
        except Exception as exc:  # noqa: BLE001 - re-raised with the reason
            raise ParameterIdentityError(
                f"parameter {self.name!r} is declared in {self.unit!r} but its "
                f"bounds are in {self.bounds.lower.units!r}, which is a "
                f"different dimension: {exc}"
            ) from None
        if self.transform is ParameterTransform.LOG:
            low = self.bounds.lower.magnitude_in(self.unit)
            if not (low > 0.0):
                raise ParameterIdentityError(
                    f"parameter {self.name!r} is log-transformed but its lower "
                    f"bound is {low!r} {self.unit}; a log transform and a "
                    f"non-positive admissible range contradict each other"
                )

    @property
    def model_id(self) -> str:
        return self.model.model_id

    @property
    def model_version(self) -> str:
        return self.model.version

    @property
    def key(self) -> str:
        """A readable handle. NOT an identity -- see :meth:`differences`."""
        return f"{self.model.model_id}@{self.model.version}:{self.name}"

    def _canonical(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "model_id": self.model.model_id,
            "model_version": self.model.version,
            # Bounds canonicalized into the parameter's own unit, so that the
            # same range stated in millivolts and in volts is the same
            # identity. A digest that disagreed with `contains` about whether
            # two declarations are the same range would be worse than no
            # digest.
            "lower": self.bounds.lower.magnitude_in(self.unit),
            "upper": self.bounds.upper.magnitude_in(self.unit),
            "transform": self.transform.value,
        }

    @property
    def digest(self) -> str:
        """SHA-256 over the identity fields, recomputed on every read."""
        blob = json.dumps(self._canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def differences(self, other: "ParameterIdentity") -> tuple[str, ...]:
        """The fields on which ``other`` is a different parameter.

        Empty means the same parameter. A shared ``name`` means nothing on its
        own, which is the whole point: same label with a different unit, and
        same name on a different model, both come back non-empty.
        """
        if not isinstance(other, ParameterIdentity):
            raise ParameterIdentityError("a parameter identity compares with another")
        mine, theirs = self._canonical(), other._canonical()
        return tuple(f for f in IDENTITY_FIELDS if mine.get(f) != theirs.get(f))

    def is_same_parameter(self, other: "ParameterIdentity") -> bool:
        return not self.differences(other)

    def require_in_bounds(self, value: Quantity) -> float:
        """The magnitude in this parameter's unit, or a refusal naming why."""
        if not isinstance(value, Quantity):
            raise ParameterIdentityError(
                f"parameter {self.key!r} takes a Quantity; a bare float has no "
                f"unit and this parameter is declared in {self.unit!r}"
            )
        try:
            value.require_compatible(Quantity(0.0, self.unit), context=self.key)
        except Exception as exc:  # noqa: BLE001 - re-raised with the reason
            raise ParameterIdentityError(
                f"parameter {self.key!r} is declared in {self.unit!r} and was "
                f"given {value.units!r}: {exc}"
            ) from None
        if not self.bounds.contains(value):
            low = self.bounds.lower.magnitude_in(self.unit)
            high = self.bounds.upper.magnitude_in(self.unit)
            raise ParameterIdentityError(
                f"parameter {self.key!r} = {value.magnitude_in(self.unit)!r} "
                f"{self.unit} lies outside its admissible range "
                f"[{low!r}, {high!r}] {self.unit}. The range is physical, not a "
                f"prior: a value outside it is refused rather than down-weighted"
            )
        return value.magnitude_in(self.unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_IDENTITY_SCHEMA,
            "name": self.name,
            "unit": self.unit,
            "model": self.model.to_dict(),
            "lower": self.bounds.lower.to_dict(),
            "upper": self.bounds.upper.to_dict(),
            "transform": self.transform.value,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParameterIdentity":
        require_schema(payload, PARAMETER_IDENTITY_SCHEMA)
        try:
            identity = cls(
                name=payload["name"],
                unit=payload["unit"],
                model=ModelReference.from_dict(payload["model"]),
                bounds=ParameterBounds(
                    lower=Quantity.from_dict(payload["lower"]),
                    upper=Quantity.from_dict(payload["upper"]),
                ),
                transform=ParameterTransform(payload["transform"]),
            )
        except KeyError as exc:
            raise ParameterIdentityError(
                f"serialized parameter identity is missing {exc.args[0]!r}"
            ) from None
        declared = payload.get("digest")
        if declared != identity.digest:
            raise ParameterIdentityError(
                f"serialized parameter identity for {identity.key!r} carries "
                f"digest {str(declared)[:12]}… but its fields hash to "
                f"{identity.digest[:12]}…; a parameter whose identity was "
                f"edited is not the parameter it names"
            )
        return identity


@dataclass(frozen=True)
class CalibrationParameterSet:
    """The declared set of parameters a calibration may estimate, in order.

    "In order" is load-bearing: the order here IS the column order of every
    grid, every posterior point and every estimate vector downstream. A
    consumer that reorders is a consumer that has relabelled the axes.

    This type is what makes "fit any free field on the model" impossible. A
    calibration takes one of these, and a parameter not in it is not estimated,
    whatever the model happens to expose.
    """

    parameters: tuple[ParameterIdentity, ...]

    def __post_init__(self) -> None:
        items = tuple(self.parameters)
        if not items:
            raise ParameterIdentityError(
                "a calibration must declare at least one parameter; an empty "
                "set is not a calibration with nothing to fit, it is a missing "
                "declaration"
            )
        for item in items:
            if not isinstance(item, ParameterIdentity):
                raise ParameterIdentityError(
                    f"a parameter set holds ParameterIdentity records, got "
                    f"{type(item).__name__}"
                )
        repeated = duplicates([item.name for item in items])
        if repeated:
            raise ParameterIdentityError(
                f"parameter set declares {sorted(repeated)!r} more than once. "
                f"Two declarations of one name are two different parameters or "
                f"one mistake, and neither is resolvable here"
            )
        object.__setattr__(self, "parameters", items)

    @property
    def names(self) -> tuple[str, ...]:
        """The canonical names, in column order. For binding to a grid."""
        return tuple(item.name for item in self.parameters)

    @property
    def units(self) -> tuple[str, ...]:
        return tuple(item.unit for item in self.parameters)

    @property
    def models(self) -> tuple[ModelReference, ...]:
        return tuple(item.model for item in self.parameters)

    @property
    def digest(self) -> str:
        blob = json.dumps(
            [item.digest for item in self.parameters], separators=(",", ":")
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def index_of(self, name: str) -> int:
        try:
            return self.names.index(str(name))
        except ValueError:
            raise ParameterIdentityError(
                f"{name!r} is not a declared calibration parameter; declared: "
                f"{list(self.names)!r}"
            ) from None

    def require_same_parameters(self, other: "CalibrationParameterSet") -> None:
        """Refuse two sets that are not the same parameters in the same order."""
        if not isinstance(other, CalibrationParameterSet):
            raise ParameterIdentityError("a parameter set compares with another")
        if len(other.parameters) != len(self.parameters):
            raise ParameterIdentityError(
                f"parameter sets differ in size: {len(self.parameters)} against "
                f"{len(other.parameters)}"
            )
        for position, (mine, theirs) in enumerate(
            zip(self.parameters, other.parameters)
        ):
            fields = mine.differences(theirs)
            if fields:
                raise ParameterIdentityError(
                    f"parameter {position} differs in {list(fields)!r}: "
                    f"{mine.key!r} against {theirs.key!r}. A shared name is a "
                    f"label; these are not the same parameter"
                )

    def require_all_in_bounds(self, values: Mapping[str, Quantity]) -> tuple[float, ...]:
        """Every declared parameter, in column order, as bounded magnitudes."""
        missing = [name for name in self.names if name not in values]
        if missing:
            raise ParameterIdentityError(
                f"no value supplied for declared parameter(s) {missing!r}"
            )
        extra = [str(name) for name in values if str(name) not in set(self.names)]
        if extra:
            raise ParameterIdentityError(
                f"value supplied for undeclared parameter(s) {sorted(extra)!r}; "
                f"a calibration estimates its declared set and nothing else"
            )
        return tuple(
            item.require_in_bounds(values[item.name]) for item in self.parameters
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_SET_SCHEMA,
            "parameters": [item.to_dict() for item in self.parameters],
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationParameterSet":
        require_schema(payload, PARAMETER_SET_SCHEMA)
        try:
            rows = payload["parameters"]
        except KeyError:
            raise ParameterIdentityError(
                "serialized parameter set is missing 'parameters'"
            ) from None
        built = cls(tuple(ParameterIdentity.from_dict(row) for row in rows))
        declared = payload.get("digest")
        if declared != built.digest:
            raise ParameterIdentityError(
                f"serialized parameter set carries digest {str(declared)[:12]}… "
                f"but its members hash to {built.digest[:12]}…"
            )
        return built


@dataclass(frozen=True)
class ParameterEstimate:
    """One estimated value, bound to the identity it is an estimate of.

    The binding is the point. A float called ``alpha`` is not an estimate of
    anything until it says which parameter, on which model, in which unit, it
    estimates -- and a consumer that wants the number gets it through
    :attr:`value`, which carries the unit with it.
    """

    identity: ParameterIdentity
    magnitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ParameterIdentity):
            raise ParameterIdentityError("an estimate requires a ParameterIdentity")
        magnitude = float(self.magnitude)
        if not math.isfinite(magnitude):
            raise ParameterIdentityError(
                f"estimate of {self.identity.key!r} is {magnitude!r}; a "
                f"non-finite estimate is a failed calibration, not a result"
            )
        object.__setattr__(self, "magnitude", magnitude)
        # Bounds are checked here rather than trusted from whatever produced
        # the number: an optimizer that returns outside its box is a documented
        # failure mode, and a record that stored it would make the violation
        # invisible from that point on.
        self.identity.require_in_bounds(Quantity(magnitude, self.identity.unit))

    @property
    def value(self) -> Quantity:
        return Quantity(self.magnitude, self.identity.unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_ESTIMATE_SCHEMA,
            "identity": self.identity.to_dict(),
            "magnitude": self.magnitude,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParameterEstimate":
        require_schema(payload, PARAMETER_ESTIMATE_SCHEMA)
        try:
            return cls(
                identity=ParameterIdentity.from_dict(payload["identity"]),
                magnitude=payload["magnitude"],
            )
        except KeyError as exc:
            raise ParameterIdentityError(
                f"serialized parameter estimate is missing {exc.args[0]!r}"
            ) from None


def require_parameter_set(value: object) -> CalibrationParameterSet:
    """Refuse anything that is not a declared parameter set."""
    if not isinstance(value, CalibrationParameterSet):
        raise ParameterIdentityError(
            f"a calibration operates on a CalibrationParameterSet, got "
            f"{type(value).__name__}; a sequence of names is what this type "
            f"exists to replace"
        )
    return value


def bind_parameter_set_to_grid(
    parameters: CalibrationParameterSet,
    grid_parameter_names: Sequence[str],
) -> None:
    """Refuse a grid whose axes are not the declared parameters, in order.

    The existing forward table and posterior identify their axes by name, and
    this is the seam where those names are held to a declaration. It refuses
    both a different set and the same set in a different order: a posterior
    whose columns are permuted relative to the declaration is a posterior about
    different parameters, and nothing downstream could detect it.
    """
    declared = parameters.names
    actual = tuple(str(name).strip() for name in grid_parameter_names)
    if actual == declared:
        return
    if sorted(actual) == sorted(declared):
        raise ParameterIdentityError(
            f"grid axes are the declared parameters in a different order: grid "
            f"{list(actual)!r} against declaration {list(declared)!r}. Column "
            f"order is the binding between a point and the parameter it is a "
            f"value of"
        )
    raise ParameterIdentityError(
        f"grid axes {list(actual)!r} are not the declared parameters "
        f"{list(declared)!r}"
    )
