"""Spatial laws as records: what a value is, as a function of where it is.

A boundary datum or a source that varies in space is still scientific data, and
it has to survive everything other scientific data survives here — being
written down, serialized, fingerprinted, compared, and refused when it does not
fit. The obvious implementation is a Python callable, and a callable satisfies
none of those: it cannot be serialized, two of them cannot be compared, and
nothing can check what it will do.

So a profile is a **declaration of a law**, not an executable object. Each form
below states its own shape in a handful of numbers with units, evaluates
deterministically from physical coordinates, round-trips through a payload, and
has a digest over the facts that make it what it is.

    ConstantProfile        one value, everywhere
    LinearProfile1D        intercept + slope * (c - origin) along one axis
    HarmonicProfile1D      offset + amplitude * sin(wavenumber*(c-origin) + phase)
    TabulatedProfile1D     sampled points along one axis, linearly interpolated
    SeparableProfile2D     amplitude * f(x) * g(y), with dimensionless factors

**No array library, on purpose.** This package is part of a core that imports
none, and a profile is a law rather than a grid of numbers: it evaluates one
point at a time in plain Python, and the runtime plane is what turns it into an
array over a support.

**Coordinates are physical, never indices.** Every ``evaluate`` takes ``x`` and
``y`` in canonical length units and a one-dimensional profile reads the axis it
declared. A profile written against one axis cannot be evaluated along the
other by accident, because it never sees a position in a sequence.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from typing import Any, ClassVar, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality, normalize_unit
from .mesh import CANONICAL_LENGTH
from .regions import BoundaryEdge

SPATIAL_PROFILE_SCHEMA = schema_string("spatial_profile")

#: Below this, two coordinates are the same point and a table has a duplicate.
COORDINATE_TOLERANCE = 1e-12


class ProfileAxis(str, Enum):
    """Which physical coordinate a one-dimensional law varies along."""

    X = "x"
    Y = "y"


class Interpolation(str, Enum):
    """How a tabulated profile reads between its samples.

    One member. A tabulated profile that did not say how it interpolates would
    be two different laws wearing one record, so the choice is declared, is part
    of the digest, and survives serialization. Anything else is refused rather
    than quietly approximated by this one.
    """

    LINEAR = "linear"


def edge_axis(edge: BoundaryEdge) -> ProfileAxis:
    """The coordinate that varies *along* an edge.

    Left and right edges run in y; bottom and top edges run in x. Stated once,
    here, so no consumer has to re-derive it and none can disagree.
    """
    return (
        ProfileAxis.Y
        if edge in (BoundaryEdge.LEFT, BoundaryEdge.RIGHT)
        else ProfileAxis.X
    )


def _finite(value: float, *, what: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise InvalidScientificProblem(
            f"{what} is {value!r}; a spatial law with a non-finite parameter "
            f"evaluates to nonsense everywhere rather than failing somewhere"
        )
    return number


def _require_quantity(value: Any, *, what: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{what} must be a Quantity, got {type(value).__name__}. A spatial "
            f"law is declared data, and an executable object is not data"
        )
    _finite(value.magnitude, what=what)
    return value


@dataclass(frozen=True)
class SpatialProfile:
    """What every spatial law can be asked, whatever its shape.

    Subclasses are frozen records. This base carries no state: it exists so the
    contract — evaluate, fingerprint, serialize, check your own dimension and
    your own coverage — is one contract rather than four similar ones.
    """

    #: Discriminator written into every payload and read back by `load_profile`.
    KIND: ClassVar[str] = ""

    @property
    def unit(self) -> str:
        """The unit this law's values carry."""
        raise NotImplementedError  # pragma: no cover

    @property
    def axes(self) -> tuple[ProfileAxis, ...]:
        """The coordinates this law actually reads. Empty for a constant."""
        raise NotImplementedError  # pragma: no cover

    def evaluate(self, *, x: float, y: float) -> float:
        """The magnitude, in :attr:`unit`, at a point given in canonical length.

        Keyword-only, so a caller cannot transpose the coordinates silently.
        """
        raise NotImplementedError  # pragma: no cover

    def payload(self) -> dict[str, Any]:
        """The law's own facts, without the schema or the description."""
        raise NotImplementedError  # pragma: no cover

    # ---- what every profile owes ------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SPATIAL_PROFILE_SCHEMA,
            "kind": self.KIND,
            "description": getattr(self, "description", ""),
            **self.payload(),
        }

    def fingerprint(self) -> str:
        """SHA-256 over the facts that make this law what it is.

        The description is excluded and everything else is included, so two
        profiles that display the same and evaluate differently have different
        identities, and renaming one changes nothing.
        """
        blob = json.dumps(
            {"kind": self.KIND, **self.payload()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def require_output_dimension(self, unit: str, *, context: str) -> None:
        """Refuse a law whose values are not of the dimension asked for."""
        if dimensionality(self.unit) != dimensionality(unit):
            raise InvalidScientificProblem(
                f"{context}: this law produces {self.unit!r} "
                f"[{dimensionality(self.unit)}] and {unit!r} "
                f"[{dimensionality(unit)}] was required. A numerically "
                f"plausible profile of the wrong dimension is still the wrong "
                f"law"
            )

    def require_axis(self, axis: ProfileAxis, *, context: str) -> None:
        """Refuse a law written against a coordinate that is not this one.

        A constant reads no coordinate and binds anywhere, which is the only
        reason this is not simply an equality.
        """
        wrong = [declared for declared in self.axes if declared is not axis]
        if wrong:
            raise InvalidScientificProblem(
                f"{context}: this law varies along "
                f"{', '.join(a.value for a in wrong)} and the requested "
                f"coordinate is {axis.value!r}. A profile written against one "
                f"axis does not become a profile of the other by being bound "
                f"to it"
            )

    def require_covers(self, lower: float, upper: float, *, context: str) -> None:
        """Refuse a law that is not defined across the whole span asked for.

        Only a sampled law can fail this; the closed forms are defined
        everywhere, and say so by not overriding it.
        """
        return None


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConstantProfile(SpatialProfile):
    """One value, at every point. The law a bare ``Quantity`` already was.

    Present so that "constant" and "varying" are the same kind of thing and a
    consumer never has to branch on which it was handed.
    """

    KIND: ClassVar[str] = "constant"

    value: Quantity
    description: str = ""

    def __post_init__(self) -> None:
        _require_quantity(self.value, what="a constant profile's value")

    @property
    def unit(self) -> str:
        return self.value.units

    @property
    def axes(self) -> tuple[ProfileAxis, ...]:
        return ()

    def evaluate(self, *, x: float, y: float) -> float:
        return float(self.value.magnitude)

    def payload(self) -> dict[str, Any]:
        return {"value": self.value.to_dict()}


@dataclass(frozen=True)
class LinearProfile1D(SpatialProfile):
    """``intercept + slope * (c - origin)`` along one axis.

    The smallest law that is not constant, and the one that covers a boundary
    datum rising evenly along its edge.
    """

    KIND: ClassVar[str] = "linear_1d"

    axis: ProfileAxis
    intercept: Quantity
    slope: Quantity
    origin: Quantity = dataclass_field(
        default_factory=lambda: Quantity(0.0, CANONICAL_LENGTH)
    )
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "axis", ProfileAxis(self.axis))
        _require_quantity(self.intercept, what="a linear profile's intercept")
        _require_quantity(self.slope, what="a linear profile's slope")
        _require_quantity(self.origin, what="a linear profile's origin")
        if dimensionality(self.origin.units) != dimensionality(CANONICAL_LENGTH):
            raise InvalidScientificProblem(
                f"a linear profile's origin is a position and is measured in "
                f"{self.origin.units!r}"
            )
        expected = f"({self.intercept.units})/({CANONICAL_LENGTH})"
        if dimensionality(self.slope.units) != dimensionality(expected):
            raise InvalidScientificProblem(
                f"a linear profile rising in {self.intercept.units!r} has a "
                f"slope per unit length; {self.slope.units!r} "
                f"[{dimensionality(self.slope.units)}] is not "
                f"[{dimensionality(expected)}]"
            )

    @property
    def unit(self) -> str:
        return self.intercept.units

    @property
    def axes(self) -> tuple[ProfileAxis, ...]:
        return (self.axis,)

    def evaluate(self, *, x: float, y: float) -> float:
        position = x if self.axis is ProfileAxis.X else y
        offset = position - self.origin.magnitude_in(CANONICAL_LENGTH)
        return float(
            self.intercept.magnitude
            + self.slope.magnitude_in(f"({self.unit})/({CANONICAL_LENGTH})") * offset
        )

    def payload(self) -> dict[str, Any]:
        return {
            "axis": self.axis.value,
            "intercept": self.intercept.to_dict(),
            "slope": self.slope.to_dict(),
            "origin": self.origin.to_dict(),
        }


@dataclass(frozen=True)
class HarmonicProfile1D(SpatialProfile):
    """``offset + amplitude * sin(wavenumber * (c - origin) + phase)``.

    Narrowly defined on purpose: one sine, with its own amplitude, wavenumber,
    phase and offset. It is not a step toward a symbolic expression language —
    there is no parser here and no way to compose one law out of arbitrary
    others. It exists because a sinusoidal boundary datum is the standard way
    to state a problem whose closed-form solution is known, and a law that can
    only be tabulated could not be stated exactly.
    """

    KIND: ClassVar[str] = "harmonic_1d"

    axis: ProfileAxis
    amplitude: Quantity
    wavenumber: Quantity
    phase: float = 0.0
    origin: Quantity = dataclass_field(
        default_factory=lambda: Quantity(0.0, CANONICAL_LENGTH)
    )
    offset: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "axis", ProfileAxis(self.axis))
        _require_quantity(self.amplitude, what="a harmonic profile's amplitude")
        _require_quantity(self.wavenumber, what="a harmonic profile's wavenumber")
        _require_quantity(self.origin, what="a harmonic profile's origin")
        object.__setattr__(self, "phase", _finite(self.phase, what="a phase"))
        if self.offset is None:
            object.__setattr__(self, "offset", Quantity(0.0, self.amplitude.units))
        _require_quantity(self.offset, what="a harmonic profile's offset")

        inverse_length = f"1/({CANONICAL_LENGTH})"
        if dimensionality(self.wavenumber.units) != dimensionality(inverse_length):
            raise InvalidScientificProblem(
                f"a wavenumber multiplies a position to give an angle; "
                f"{self.wavenumber.units!r} [{dimensionality(self.wavenumber.units)}] "
                f"is not [{dimensionality(inverse_length)}]"
            )
        if dimensionality(self.origin.units) != dimensionality(CANONICAL_LENGTH):
            raise InvalidScientificProblem(
                f"a harmonic profile's origin is a position and is measured in "
                f"{self.origin.units!r}"
            )
        if dimensionality(self.offset.units) != dimensionality(self.amplitude.units):
            raise InvalidScientificProblem(
                f"a harmonic profile's offset and amplitude are added and are "
                f"measured in {self.offset.units!r} and {self.amplitude.units!r}"
            )

    @property
    def unit(self) -> str:
        return self.amplitude.units

    @property
    def axes(self) -> tuple[ProfileAxis, ...]:
        return (self.axis,)

    def evaluate(self, *, x: float, y: float) -> float:
        position = x if self.axis is ProfileAxis.X else y
        offset = position - self.origin.magnitude_in(CANONICAL_LENGTH)
        angle = self.wavenumber.magnitude_in(f"1/({CANONICAL_LENGTH})") * offset
        return float(
            self.offset.magnitude_in(self.unit)
            + self.amplitude.magnitude * math.sin(angle + self.phase)
        )

    def payload(self) -> dict[str, Any]:
        return {
            "axis": self.axis.value,
            "amplitude": self.amplitude.to_dict(),
            "wavenumber": self.wavenumber.to_dict(),
            "phase": self.phase,
            "origin": self.origin.to_dict(),
            "offset": self.offset.to_dict(),
        }


@dataclass(frozen=True)
class TabulatedProfile1D(SpatialProfile):
    """Sampled values along one axis, read between samples by a declared rule.

    The law a measurement produces. Its samples are its identity, its
    interpolation is declared rather than assumed, and **it does not
    extrapolate**: asked for a point outside the span it was given, it refuses
    rather than inventing one. A table that silently continued its last segment
    would be answering a question nobody had checked it could answer.
    """

    KIND: ClassVar[str] = "tabulated_1d"

    axis: ProfileAxis
    coordinates: tuple[float, ...]
    values: tuple[float, ...]
    unit: str = "dimensionless"
    coordinate_unit: str = CANONICAL_LENGTH
    interpolation: Interpolation = Interpolation.LINEAR
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "axis", ProfileAxis(self.axis))
        object.__setattr__(self, "interpolation", Interpolation(self.interpolation))
        object.__setattr__(self, "unit", normalize_unit(str(self.unit)))
        object.__setattr__(
            self, "coordinate_unit", normalize_unit(str(self.coordinate_unit))
        )
        if dimensionality(self.coordinate_unit) != dimensionality(CANONICAL_LENGTH):
            raise InvalidScientificProblem(
                f"a tabulated profile is sampled at positions; its coordinate "
                f"unit {self.coordinate_unit!r} is not a length"
            )

        coordinates = tuple(
            _finite(c, what=f"tabulated coordinate {index}")
            for index, c in enumerate(self.coordinates)
        )
        values = tuple(
            _finite(v, what=f"tabulated value {index}")
            for index, v in enumerate(self.values)
        )
        if len(coordinates) != len(values):
            raise InvalidScientificProblem(
                f"a tabulated profile pairs a coordinate with a value; it was "
                f"given {len(coordinates)} coordinates and {len(values)} values"
            )
        if len(coordinates) < 2:
            raise InvalidScientificProblem(
                "a tabulated profile needs at least two samples; one sample is "
                "a constant and should say so"
            )
        for index in range(1, len(coordinates)):
            step = coordinates[index] - coordinates[index - 1]
            if abs(step) <= COORDINATE_TOLERANCE:
                raise InvalidScientificProblem(
                    f"a tabulated profile repeats the coordinate "
                    f"{coordinates[index]!r} at samples {index - 1} and "
                    f"{index}; two values at one point is a contradiction with "
                    f"a silent winner"
                )
            if step < 0.0:
                raise InvalidScientificProblem(
                    f"a tabulated profile's coordinates run backwards at "
                    f"sample {index} ({coordinates[index - 1]!r} then "
                    f"{coordinates[index]!r}); the order is material to how it "
                    f"is read and is not sorted here on the caller's behalf"
                )
        object.__setattr__(self, "coordinates", coordinates)
        object.__setattr__(self, "values", values)

    @property
    def axes(self) -> tuple[ProfileAxis, ...]:
        return (self.axis,)

    @property
    def span(self) -> tuple[float, float]:
        """The closed interval this law is defined on, in canonical length."""
        scale = Quantity(1.0, self.coordinate_unit).magnitude_in(CANONICAL_LENGTH)
        return (self.coordinates[0] * scale, self.coordinates[-1] * scale)

    def evaluate(self, *, x: float, y: float) -> float:
        position = x if self.axis is ProfileAxis.X else y
        lower, upper = self.span
        if position < lower - COORDINATE_TOLERANCE or position > upper + COORDINATE_TOLERANCE:
            raise InvalidScientificProblem(
                f"this tabulated law is defined on [{lower:g}, {upper:g}] "
                f"{CANONICAL_LENGTH} and was asked for {position:g}. "
                f"Extrapolation is not declared for it, and continuing the "
                f"last segment would be answering a question nobody checked"
            )
        scale = Quantity(1.0, self.coordinate_unit).magnitude_in(CANONICAL_LENGTH)
        target = position / scale if scale else position
        coordinates = self.coordinates
        if target <= coordinates[0]:
            return self.values[0]
        if target >= coordinates[-1]:
            return self.values[-1]
        # Linear is the only declared rule; `interpolation` is validated to it.
        for index in range(1, len(coordinates)):
            right = coordinates[index]
            if target <= right:
                left = coordinates[index - 1]
                weight = (target - left) / (right - left)
                return float(
                    self.values[index - 1]
                    + weight * (self.values[index] - self.values[index - 1])
                )
        return self.values[-1]  # pragma: no cover - covered by the bounds above

    def require_covers(self, lower: float, upper: float, *, context: str) -> None:
        span_lower, span_upper = self.span
        if (
            span_lower > lower + COORDINATE_TOLERANCE
            or span_upper < upper - COORDINATE_TOLERANCE
        ):
            raise InvalidScientificProblem(
                f"{context}: this tabulated law is defined on "
                f"[{span_lower:g}, {span_upper:g}] and must cover "
                f"[{lower:g}, {upper:g}] {CANONICAL_LENGTH}. A table that stops "
                f"short of the span it is bound to leaves part of it undefined, "
                f"and the part it leaves is exactly where nobody looked"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "axis": self.axis.value,
            "coordinates": list(self.coordinates),
            "values": list(self.values),
            "unit": self.unit,
            "coordinate_unit": self.coordinate_unit,
            "interpolation": self.interpolation.value,
        }


@dataclass(frozen=True)
class SeparableProfile2D(SpatialProfile):
    """``amplitude * f(x) * g(y)``, with dimensionless factors.

    The minimum coherent two-dimensional extension: it reuses the
    one-dimensional laws rather than introducing a second vocabulary, and the
    unit lives in one place instead of being multiplied out of two. Products of
    this shape are what the standard closed-form source terms are made of.

    Requiring the factors to be dimensionless is what keeps the unit arithmetic
    from becoming a second thing to get wrong.
    """

    KIND: ClassVar[str] = "separable_2d"

    amplitude: Quantity
    x_factor: SpatialProfile
    y_factor: SpatialProfile
    description: str = ""

    def __post_init__(self) -> None:
        _require_quantity(self.amplitude, what="a separable profile's amplitude")
        for label, factor, axis in (
            ("x_factor", self.x_factor, ProfileAxis.X),
            ("y_factor", self.y_factor, ProfileAxis.Y),
        ):
            if not isinstance(factor, SpatialProfile):
                raise InvalidScientificProblem(
                    f"a separable profile's {label} is a SpatialProfile, got "
                    f"{type(factor).__name__}"
                )
            if isinstance(factor, SeparableProfile2D):
                raise InvalidScientificProblem(
                    f"a separable profile's {label} is a one-dimensional law; "
                    f"nesting two-dimensional ones would make the coordinate "
                    f"each factor reads ambiguous"
                )
            factor.require_output_dimension(
                "dimensionless",
                context=f"a separable profile's {label}",
            )
            factor.require_axis(
                axis, context=f"a separable profile's {label}"
            )

    @property
    def unit(self) -> str:
        return self.amplitude.units

    @property
    def axes(self) -> tuple[ProfileAxis, ...]:
        return tuple(
            axis
            for axis in (ProfileAxis.X, ProfileAxis.Y)
            if axis in self.x_factor.axes + self.y_factor.axes
        )

    def evaluate(self, *, x: float, y: float) -> float:
        return float(
            self.amplitude.magnitude
            * self.x_factor.evaluate(x=x, y=y)
            * self.y_factor.evaluate(x=x, y=y)
        )

    def require_covers(self, lower: float, upper: float, *, context: str) -> None:
        # Deliberately not forwarded: the span asked for is along one axis and
        # this law reads two, so which factor it constrains is not knowable
        # here. `require_covers_box` is the two-dimensional question.
        return None

    def require_covers_box(
        self, x_span: tuple[float, float], y_span: tuple[float, float], *, context: str
    ) -> None:
        self.x_factor.require_covers(*x_span, context=f"{context} (x factor)")
        self.y_factor.require_covers(*y_span, context=f"{context} (y factor)")

    def payload(self) -> dict[str, Any]:
        return {
            "amplitude": self.amplitude.to_dict(),
            "x_factor": self.x_factor.to_dict(),
            "y_factor": self.y_factor.to_dict(),
        }


# ---------------------------------------------------------------------------
_PROFILE_KINDS: dict[str, type[SpatialProfile]] = {
    cls.KIND: cls
    for cls in (
        ConstantProfile,
        LinearProfile1D,
        HarmonicProfile1D,
        TabulatedProfile1D,
        SeparableProfile2D,
    )
}


def load_profile(payload: Mapping[str, Any]) -> SpatialProfile:
    """Rebuild a law from its payload, or refuse it.

    The only way a profile enters this process from outside. There is no
    fallback branch that evaluates a string and no hook that imports a name:
    a payload naming a law this version does not have is refused, because the
    alternative is a deserializer that can be talked into running something.
    """
    require_schema(payload, SPATIAL_PROFILE_SCHEMA)
    kind = str(payload.get("kind", ""))
    cls = _PROFILE_KINDS.get(kind)
    if cls is None:
        raise InvalidScientificProblem(
            f"no spatial law of kind {kind!r} is declared by this version; "
            f"known: {sorted(_PROFILE_KINDS)}"
        )
    description = payload.get("description", "")
    if cls is ConstantProfile:
        return ConstantProfile(
            value=Quantity.from_dict(payload["value"]), description=description
        )
    if cls is LinearProfile1D:
        return LinearProfile1D(
            axis=ProfileAxis(payload["axis"]),
            intercept=Quantity.from_dict(payload["intercept"]),
            slope=Quantity.from_dict(payload["slope"]),
            origin=Quantity.from_dict(payload["origin"]),
            description=description,
        )
    if cls is HarmonicProfile1D:
        return HarmonicProfile1D(
            axis=ProfileAxis(payload["axis"]),
            amplitude=Quantity.from_dict(payload["amplitude"]),
            wavenumber=Quantity.from_dict(payload["wavenumber"]),
            phase=payload["phase"],
            origin=Quantity.from_dict(payload["origin"]),
            offset=Quantity.from_dict(payload["offset"]),
            description=description,
        )
    if cls is TabulatedProfile1D:
        return TabulatedProfile1D(
            axis=ProfileAxis(payload["axis"]),
            coordinates=tuple(payload["coordinates"]),
            values=tuple(payload["values"]),
            unit=payload["unit"],
            coordinate_unit=payload["coordinate_unit"],
            interpolation=Interpolation(payload["interpolation"]),
            description=description,
        )
    return SeparableProfile2D(
        amplitude=Quantity.from_dict(payload["amplitude"]),
        x_factor=load_profile(payload["x_factor"]),
        y_factor=load_profile(payload["y_factor"]),
        description=description,
    )


def as_profile(value: Any, *, context: str) -> SpatialProfile:
    """A profile, or a ``Quantity`` promoted to a constant one. Nothing else.

    The one place a bare value becomes a law, so that every consumer downstream
    handles exactly one type and the Sprint 4 spelling of a constant boundary
    value keeps working unchanged.
    """
    if isinstance(value, SpatialProfile):
        return value
    if isinstance(value, Quantity):
        return ConstantProfile(value=value)
    raise InvalidScientificProblem(
        f"{context}: a spatial law is a Quantity or a SpatialProfile, got "
        f"{type(value).__name__}. Executable objects are refused here — a law "
        f"that cannot be serialized, compared or fingerprinted is not a "
        f"scientific record, whatever it computes"
    )
