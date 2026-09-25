"""Environment Engine: provider-neutral environmental history on the Time Engine.

The environment is an *imposed input* to a system, not evidence about it.
Nothing here validates a model, and an environmental value is never more
certain than the source that declared it.

Authority reuse (no second timeline or state system):

* Time, basis, horizon, discontinuities and scenario identity come from the
  bound :class:`~engcore.scenarios.timeline.Timeline`.
* Interval-valued environmental loads (a daily chloride deposition, an hourly
  mean irradiance) are the timeline's own EXPOSURE
  :class:`~engcore.scenarios.timeline.QuantityHistory` records, referenced by
  id -- they are stored once, in the timeline.
* Values use :class:`~engcore.scenarios.contracts.NamedQuantity`, so missing
  uncertainty is UNKNOWN by construction.

What this module adds:

* :class:`EnvironmentQuantityKind` / :class:`EnvironmentKindRegistry` --
  typed, extensible quantity kinds (dimension, affine permission, required
  reference-context parameters).  New kinds are registered, not branched on.
* :class:`EnvironmentSource` -- the identity of the data a channel came from,
  bound by content digest so it survives serialization and replay.
* :class:`EnvironmentChannel` -- one kind, at one location/context, from one
  source, with an explicit validity window and an explicit
  :class:`InterpolationContract`.
* :class:`EnvironmentState` -- every channel's value at one instant, with
  UNKNOWN entries rather than omissions.
* :class:`EnvironmentTimeline` -- the deterministic, digest-bound whole.

Rules enforced here: missing data is UNKNOWN; interpolated values are labelled
INTERPOLATED and carry UNKNOWN uncertainty (interpolation error is not
quantified, and interpolation is not measurement); no extrapolation; no
interpolation across a gap larger than the contract authorizes or across a
declared discontinuity; overlapping channels for one kind/location/context are
refused rather than arbitrated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import re
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics.receipts import require_digest
from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity, dimensionality, is_ratio_scale, normalize_unit
from .contracts import NamedQuantity
from .timeline import (
    HistoryKind,
    QuantityHistory,
    TimelineEventKind,
    Timeline,
    TimePoint,
    TimeWindow,
    ValueStatus,
    WindowClosure,
    canonical_digest,
    exact_seconds,
)

ENV_KIND_SCHEMA = schema_string("environment_quantity_kind")
ENV_SOURCE_SCHEMA = schema_string("environment_source")
ENV_CONTEXT_SCHEMA = schema_string("environment_reference_context")
ENV_INTERPOLATION_SCHEMA = schema_string("environment_interpolation_contract")
ENV_SAMPLE_SCHEMA = schema_string("environment_sample")
ENV_CHANNEL_SCHEMA = schema_string("environment_channel")
ENV_VALUE_SCHEMA = schema_string("environment_value")
ENV_STATE_SCHEMA = schema_string("environment_state")
ENV_TIMELINE_SCHEMA = schema_string("environment_timeline")

#: Classification of a value no source supplied (an unsupplied required kind).
NO_SOURCE = "no_source"

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


def _identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise InvalidScientificProblem(f"{label} must be a non-empty typed identifier")
    return text


def _strict_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise InvalidScientificProblem(
            f"{label} shape mismatch; missing={sorted(expected - set(payload))}, "
            f"extra={sorted(set(payload) - expected)}"
        )


def _enum(cls, value, label):
    try:
        return cls(value)
    except ValueError as exc:
        raise InvalidScientificProblem(f"unsupported {label} {value!r}") from exc


# --------------------------------------------------------------------------
# Quantity kinds (typed, extensible)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvironmentQuantityKind:
    """What an environmental quantity *is*: its dimension and required context.

    ``reference_unit`` fixes the dimension only; channels may use any
    compatible unit.  ``affine`` states whether values are affine coordinates
    (temperature in degC); an affine kind is never integrated into a dose.
    ``context_parameters`` names reference-context quantities a channel of
    this kind must declare (e.g. the surface tilt/azimuth that makes an
    irradiance meaningful).  No code branches on a kind id.
    """

    kind_id: str
    reference_unit: str
    description: str
    affine: bool = False
    context_parameters: tuple[str, ...] = ()
    #: Periodic quantity (an angle): arithmetic interpolation is meaningless,
    #: so LINEAR contracts are refused for it.
    circular: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind_id", _identifier(self.kind_id, "environment kind_id"))
        object.__setattr__(self, "reference_unit", normalize_unit(self.reference_unit))
        if not str(self.description).strip():
            raise InvalidScientificProblem("environment kind requires a description")
        if not isinstance(self.circular, bool):
            raise InvalidScientificProblem("environment kind circular must be boolean")
        if not isinstance(self.affine, bool):
            raise InvalidScientificProblem("environment kind affine must be boolean")
        params = tuple(sorted(_identifier(p, "context parameter") for p in self.context_parameters))
        if len(set(params)) != len(params):
            raise InvalidScientificProblem("environment kind repeats a context parameter")
        object.__setattr__(self, "context_parameters", params)

    @property
    def dimension(self) -> str:
        return dimensionality(self.reference_unit)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENV_KIND_SCHEMA, "kind_id": self.kind_id, "reference_unit": self.reference_unit, "description": self.description, "affine": self.affine, "context_parameters": list(self.context_parameters), "circular": self.circular}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentQuantityKind":
        require_schema(payload, ENV_KIND_SCHEMA)
        _strict_keys(payload, {"schema", "kind_id", "reference_unit", "description", "affine", "context_parameters", "circular"}, "environment kind")
        return cls(payload["kind_id"], payload["reference_unit"], payload["description"], payload["affine"], tuple(payload["context_parameters"]), payload["circular"])


#: The initial environmental dimensions.  Generic physical quantities only; no
#: product, material or domain names.
STANDARD_ENVIRONMENT_KINDS: tuple[EnvironmentQuantityKind, ...] = (
    EnvironmentQuantityKind("ambient_temperature", "kelvin", "near-surface air temperature", affine=True),
    EnvironmentQuantityKind(
        "plane_irradiance", "watt / meter ** 2",
        "solar irradiance on a declared surface orientation",
        context_parameters=("surface_azimuth", "surface_tilt"),
    ),
    EnvironmentQuantityKind("global_horizontal_irradiance", "watt / meter ** 2", "solar irradiance on a horizontal plane"),
    EnvironmentQuantityKind("relative_humidity", "dimensionless", "relative humidity as a fraction"),
    EnvironmentQuantityKind("wind_speed", "meter / second", "wind speed at a declared height", context_parameters=("measurement_height",)),
    EnvironmentQuantityKind(
        "wind_direction", "degree", "direction the wind blows from, clockwise from the declared reference",
        affine=True, context_parameters=("direction_reference",), circular=True,
    ),
    EnvironmentQuantityKind("precipitation_rate", "meter / second", "liquid-water-equivalent precipitation rate"),
    EnvironmentQuantityKind("surface_wetness", "dimensionless", "fraction of time a surface is wet"),
    EnvironmentQuantityKind("chloride_deposition_rate", "kilogram / meter ** 2 / second", "airborne chloride deposition flux"),
    EnvironmentQuantityKind("particulate_concentration", "kilogram / meter ** 3", "airborne dust/sand mass concentration"),
    EnvironmentQuantityKind("ambient_pressure", "pascal", "static ambient pressure"),
    EnvironmentQuantityKind("altitude", "meter", "height above the declared datum", affine=True, context_parameters=("datum_offset",)),
    EnvironmentQuantityKind("gravitational_acceleration", "meter / second ** 2", "magnitude of the local body-force acceleration"),
)


@dataclass(frozen=True)
class EnvironmentKindRegistry:
    kinds: tuple[EnvironmentQuantityKind, ...]

    def __post_init__(self) -> None:
        kinds = tuple(self.kinds)
        if any(not isinstance(k, EnvironmentQuantityKind) for k in kinds):
            raise InvalidScientificProblem("registry holds EnvironmentQuantityKind records")
        if len({k.kind_id for k in kinds}) != len(kinds):
            raise InvalidScientificProblem("registry defines one kind id twice")
        object.__setattr__(self, "kinds", tuple(sorted(kinds, key=lambda k: k.kind_id)))

    @classmethod
    def standard(cls) -> "EnvironmentKindRegistry":
        return cls(STANDARD_ENVIRONMENT_KINDS)

    def register(self, kind: EnvironmentQuantityKind) -> "EnvironmentKindRegistry":
        """A new registry with one more kind; redefining an existing id is refused."""
        return EnvironmentKindRegistry(self.kinds + (kind,))

    def get(self, kind_id: str) -> EnvironmentQuantityKind:
        for kind in self.kinds:
            if kind.kind_id == kind_id:
                return kind
        raise InvalidScientificProblem(f"environment kind {kind_id!r} is not registered")


# --------------------------------------------------------------------------
# Sources, context, interpolation
# --------------------------------------------------------------------------


class EnvironmentSourceKind(str, Enum):
    #: Instrumented observations (the observation records live elsewhere; this
    #: names them by digest).
    MEASURED = "measured"
    #: A published dataset / reanalysis / climate record.
    DATASET = "dataset"
    #: A normative or standard profile (a test standard's cycle, an atmosphere model).
    STANDARD_PROFILE = "standard_profile"
    #: A provider's model output (weather forecast, simulation).
    MODEL_OUTPUT = "model_output"
    #: A caller's design assumption.  Declared, never evidence.
    DESIGN_ASSUMPTION = "design_assumption"


@dataclass(frozen=True)
class EnvironmentSource:
    """Identity of the data behind a channel, bound by content digest."""

    source_id: str
    kind: EnvironmentSourceKind
    issuer: str
    content_digest: str
    version: str
    license: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _identifier(self.source_id, "environment source_id"))
        object.__setattr__(self, "kind", _enum(EnvironmentSourceKind, self.kind, "environment source kind"))
        for label in ("issuer", "version"):
            text = str(getattr(self, label) or "").strip()
            if not text:
                raise InvalidScientificProblem(f"environment source requires {label}")
            object.__setattr__(self, label, text)
        object.__setattr__(self, "content_digest", require_digest(self.content_digest, "environment source content_digest"))
        object.__setattr__(self, "license", str(self.license or "").strip())

    @property
    def classification(self) -> str:
        return "declared_assumption_not_evidence" if self.kind is EnvironmentSourceKind.DESIGN_ASSUMPTION else "imposed_environment_input"

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENV_SOURCE_SCHEMA, "source_id": self.source_id, "kind": self.kind.value, "issuer": self.issuer, "content_digest": self.content_digest, "version": self.version, "license": self.license, "classification": self.classification}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentSource":
        require_schema(payload, ENV_SOURCE_SCHEMA)
        _strict_keys(payload, {"schema", "source_id", "kind", "issuer", "content_digest", "version", "license", "classification"}, "environment source")
        source = cls(payload["source_id"], payload["kind"], payload["issuer"], payload["content_digest"], payload["version"], payload["license"])
        if payload["classification"] != source.classification:
            raise InvalidScientificProblem("environment source classification mismatch")
        return source


@dataclass(frozen=True)
class ReferenceContext:
    """Where/how a value applies: location, frame and declared parameters."""

    context_id: str
    location_id: str
    frame_id: str
    parameters: tuple[NamedQuantity, ...] = ()

    def __post_init__(self) -> None:
        for label in ("context_id", "location_id", "frame_id"):
            object.__setattr__(self, label, _identifier(getattr(self, label), f"reference {label}"))
        params = tuple(self.parameters)
        if any(not isinstance(p, NamedQuantity) for p in params) or len({p.quantity_id for p in params}) != len(params):
            raise InvalidScientificProblem("reference context parameters must be unique NamedQuantity records")
        object.__setattr__(self, "parameters", tuple(sorted(params)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENV_CONTEXT_SCHEMA, "context_id": self.context_id, "location_id": self.location_id, "frame_id": self.frame_id, "parameters": [p.to_dict() for p in self.parameters]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceContext":
        require_schema(payload, ENV_CONTEXT_SCHEMA)
        _strict_keys(payload, {"schema", "context_id", "location_id", "frame_id", "parameters"}, "reference context")
        return cls(payload["context_id"], payload["location_id"], payload["frame_id"], tuple(NamedQuantity.from_dict(p) for p in payload["parameters"]))


class EnvironmentInterpolation(str, Enum):
    #: Values exist only at declared sample instants.
    NONE = "none"
    #: Hold the previous sample until the next one (zero-order hold).
    STEP_HOLD = "step_hold"
    #: Linear between two adjacent samples.
    LINEAR = "linear"


@dataclass(frozen=True)
class InterpolationContract:
    """What a channel's source authorizes between samples.

    ``max_gap`` bounds the distance between the two samples an interpolated
    value may be built from; a wider gap is UNKNOWN.  Extrapolation is never
    authorized.
    """

    method: EnvironmentInterpolation
    max_gap: Quantity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _enum(EnvironmentInterpolation, self.method, "environment interpolation"))
        if self.method is EnvironmentInterpolation.NONE:
            if self.max_gap is not None:
                raise InvalidScientificProblem("NONE interpolation takes no max_gap")
        else:
            if self.max_gap is None:
                raise InvalidScientificProblem(
                    f"{self.method.value} interpolation requires an explicit max_gap; "
                    f"an unbounded interpolation invents values across any hole"
                )
            if exact_seconds(self.max_gap, "interpolation max_gap") <= 0:
                raise InvalidScientificProblem("interpolation max_gap must be positive")

    @property
    def max_gap_seconds(self) -> Fraction | None:
        return None if self.max_gap is None else exact_seconds(self.max_gap)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENV_INTERPOLATION_SCHEMA, "method": self.method.value, "max_gap": None if self.max_gap is None else self.max_gap.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InterpolationContract":
        require_schema(payload, ENV_INTERPOLATION_SCHEMA)
        _strict_keys(payload, {"schema", "method", "max_gap"}, "interpolation contract")
        return cls(payload["method"], None if payload["max_gap"] is None else Quantity.from_dict(payload["max_gap"]))


# --------------------------------------------------------------------------
# Channels
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvironmentSample:
    at: TimePoint
    value: NamedQuantity

    def __post_init__(self) -> None:
        if not isinstance(self.at, TimePoint) or not isinstance(self.value, NamedQuantity):
            raise InvalidScientificProblem("environment sample needs a TimePoint and a NamedQuantity")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENV_SAMPLE_SCHEMA, "at": self.at.to_dict(), "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentSample":
        require_schema(payload, ENV_SAMPLE_SCHEMA)
        _strict_keys(payload, {"schema", "at", "value"}, "environment sample")
        return cls(TimePoint.from_dict(payload["at"]), NamedQuantity.from_dict(payload["value"]))


class ChannelRepresentation(str, Enum):
    #: Instantaneous samples plus an interpolation contract.
    POINT_SAMPLES = "point_samples"
    #: Interval values held by an EXPOSURE QuantityHistory in the bound timeline.
    INTERVAL_HISTORY = "interval_history"


@dataclass(frozen=True)
class EnvironmentChannel:
    """One environmental kind, at one reference context, from one source."""

    channel_id: str
    kind_id: str
    unit: str
    source_id: str
    context: ReferenceContext
    validity: TimeWindow
    representation: ChannelRepresentation
    samples: tuple[EnvironmentSample, ...] = ()
    interpolation: InterpolationContract | None = None
    history_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel_id", _identifier(self.channel_id, "environment channel_id"))
        object.__setattr__(self, "kind_id", _identifier(self.kind_id, "environment channel kind_id"))
        object.__setattr__(self, "source_id", _identifier(self.source_id, "environment channel source_id"))
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        if not isinstance(self.context, ReferenceContext):
            raise InvalidScientificProblem("environment channel requires a ReferenceContext; location is never defaulted")
        if not isinstance(self.validity, TimeWindow):
            raise InvalidScientificProblem("environment channel requires an explicit validity window")
        rep = _enum(ChannelRepresentation, self.representation, "channel representation")
        object.__setattr__(self, "representation", rep)
        samples = tuple(self.samples)
        if rep is ChannelRepresentation.POINT_SAMPLES:
            if not samples or any(not isinstance(s, EnvironmentSample) for s in samples):
                raise InvalidScientificProblem("a point-sample channel requires EnvironmentSample records")
            if not isinstance(self.interpolation, InterpolationContract):
                raise InvalidScientificProblem("a point-sample channel requires an explicit InterpolationContract")
            if self.history_id:
                raise InvalidScientificProblem("a point-sample channel does not reference a history")
            ordered = tuple(sorted(samples, key=lambda s: s.at.seconds))
            for a, b in zip(ordered, ordered[1:]):
                if a.at.seconds == b.at.seconds:
                    raise InvalidScientificProblem(
                        f"channel {self.channel_id!r} has two samples at {a.at.seconds} second"
                    )
            for s in ordered:
                if s.value.quantity_id != self.channel_id:
                    raise InvalidScientificProblem("channel samples must name the channel as quantity_id")
                s.value.value.require_compatible(self.unit, context=f"channel {self.channel_id!r}")
                if not self.validity.contains(s.at):
                    raise InvalidScientificProblem(f"channel {self.channel_id!r} sample lies outside its validity window")
            object.__setattr__(self, "samples", ordered)
            object.__setattr__(self, "history_id", "")
        else:
            if samples or self.interpolation is not None:
                raise InvalidScientificProblem("an interval-history channel takes no samples or interpolation")
            object.__setattr__(self, "history_id", _identifier(self.history_id, "channel history_id"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENV_CHANNEL_SCHEMA, "channel_id": self.channel_id, "kind_id": self.kind_id,
            "unit": self.unit, "source_id": self.source_id, "context": self.context.to_dict(),
            "validity": self.validity.to_dict(), "representation": self.representation.value,
            "samples": [s.to_dict() for s in self.samples],
            "interpolation": None if self.interpolation is None else self.interpolation.to_dict(),
            "history_id": self.history_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentChannel":
        require_schema(payload, ENV_CHANNEL_SCHEMA)
        _strict_keys(payload, {"schema", "channel_id", "kind_id", "unit", "source_id", "context", "validity", "representation", "samples", "interpolation", "history_id"}, "environment channel")
        return cls(
            payload["channel_id"], payload["kind_id"], payload["unit"], payload["source_id"],
            ReferenceContext.from_dict(payload["context"]), TimeWindow.from_dict(payload["validity"]),
            payload["representation"], tuple(EnvironmentSample.from_dict(s) for s in payload["samples"]),
            None if payload["interpolation"] is None else InterpolationContract.from_dict(payload["interpolation"]),
            payload["history_id"],
        )


# --------------------------------------------------------------------------
# Values and states
# --------------------------------------------------------------------------


class ValueDerivation(str, Enum):
    #: Exactly a declared sample.
    SAMPLED = "sampled"
    #: A declared interval value that holds over the queried instant.
    INTERVAL_DECLARED = "interval_declared"
    #: Built between samples under the channel's interpolation contract.
    INTERPOLATED = "interpolated"
    #: No value.
    NONE = "none"


@dataclass(frozen=True)
class EnvironmentValue:
    """One channel's (or one required kind's) value at an instant, or UNKNOWN."""

    kind_id: str
    location_id: str
    context_id: str
    channel_id: str
    source_id: str
    status: ValueStatus
    derivation: ValueDerivation
    value: NamedQuantity | None
    reason: str = ""
    #: The source's evidence class, copied so a consumer never has to look it
    #: up to tell a design assumption from a measurement.  Empty only when no
    #: source exists (UNKNOWN for an unsupplied required kind).
    source_classification: str = ""

    def __post_init__(self) -> None:
        status = _enum(ValueStatus, self.status, "value status")
        if not self.source_classification:
            raise InvalidScientificProblem("an environment value always states its source classification")
        if (not self.source_id) != (self.source_classification == NO_SOURCE):
            raise InvalidScientificProblem(
                f"an environment value without a source must say {NO_SOURCE!r}, and only such a value may"
            )
        derivation = _enum(ValueDerivation, self.derivation, "value derivation")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "derivation", derivation)
        if status is ValueStatus.KNOWN:
            if self.value is None or derivation is ValueDerivation.NONE or not self.source_id:
                raise InvalidScientificProblem("a KNOWN environment value needs a value, a derivation and a source")
        else:
            if self.value is not None or derivation is not ValueDerivation.NONE:
                raise InvalidScientificProblem("an UNKNOWN environment value carries no value and no derivation")
            if not str(self.reason).strip():
                raise InvalidScientificProblem("an UNKNOWN environment value must say why")

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind_id, self.location_id, self.context_id)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENV_VALUE_SCHEMA, "kind_id": self.kind_id, "location_id": self.location_id, "context_id": self.context_id, "channel_id": self.channel_id, "source_id": self.source_id, "status": self.status.value, "derivation": self.derivation.value, "value": None if self.value is None else self.value.to_dict(), "reason": self.reason, "source_classification": self.source_classification}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentValue":
        require_schema(payload, ENV_VALUE_SCHEMA)
        _strict_keys(payload, {"schema", "kind_id", "location_id", "context_id", "channel_id", "source_id", "status", "derivation", "value", "reason", "source_classification"}, "environment value")
        return cls(payload["kind_id"], payload["location_id"], payload["context_id"], payload["channel_id"], payload["source_id"], payload["status"], payload["derivation"], None if payload["value"] is None else NamedQuantity.from_dict(payload["value"]), payload["reason"], payload["source_classification"])


@dataclass(frozen=True)
class EnvironmentState:
    """The environment at one instant and location, bound to its timeline and sources."""

    at: TimePoint
    location_id: str
    environment_digest: str
    values: tuple[EnvironmentValue, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.at, TimePoint):
            raise InvalidScientificProblem("environment state requires a TimePoint")
        object.__setattr__(self, "location_id", _identifier(self.location_id, "environment state location_id"))
        object.__setattr__(self, "environment_digest", require_digest(self.environment_digest, "environment_digest"))
        values = tuple(self.values)
        if any(not isinstance(v, EnvironmentValue) for v in values) or len({v.key for v in values}) != len(values):
            raise InvalidScientificProblem("environment state holds one value per kind/location/context")
        object.__setattr__(self, "values", tuple(sorted(values, key=lambda v: v.key)))

    def value(self, kind_id: str, context_id: str = "") -> EnvironmentValue:
        matches = [v for v in self.values if v.kind_id == kind_id and (not context_id or v.context_id == context_id)]
        if len(matches) != 1:
            raise InvalidScientificProblem(
                f"environment state has {len(matches)} values for {kind_id!r}"
                f"{' in ' + context_id if context_id else ''}; name the context"
            )
        return matches[0]

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ENV_STATE_SCHEMA, "classification": "imposed_environment_not_evidence", "at": self.at.to_dict(), "location_id": self.location_id, "environment_digest": self.environment_digest, "values": [v.to_dict() for v in self.values]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentState":
        require_schema(payload, ENV_STATE_SCHEMA)
        _strict_keys(payload, {"schema", "classification", "at", "location_id", "environment_digest", "values"}, "environment state")
        if payload["classification"] != "imposed_environment_not_evidence":
            raise InvalidScientificProblem("environment state classification mismatch")
        return cls(TimePoint.from_dict(payload["at"]), payload["location_id"], payload["environment_digest"], tuple(EnvironmentValue.from_dict(v) for v in payload["values"]))


# --------------------------------------------------------------------------
# Environment timeline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvironmentTimeline:
    """Provenance-bound environmental history over one scenario-bound Timeline.

    ``required`` names ``(kind_id, location_id)`` pairs a consumer needs; a
    required pair with no channel appears in every state as UNKNOWN rather
    than being omitted.
    """

    environment_id: str
    timeline: Timeline
    registry: EnvironmentKindRegistry
    sources: tuple[EnvironmentSource, ...]
    channels: tuple[EnvironmentChannel, ...]
    required: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment_id", _identifier(self.environment_id, "environment_id"))
        if not isinstance(self.timeline, Timeline):
            raise InvalidScientificProblem("environment requires the Timeline it lives on; it owns no clock")
        if not self.timeline.scenario_digest:
            raise InvalidScientificProblem("environment requires a scenario-bound timeline; its context must be named")
        if not isinstance(self.registry, EnvironmentKindRegistry):
            raise InvalidScientificProblem("environment requires an EnvironmentKindRegistry")
        sources = tuple(self.sources)
        if any(not isinstance(s, EnvironmentSource) for s in sources) or len({s.source_id for s in sources}) != len(sources):
            raise InvalidScientificProblem("environment sources must be unique EnvironmentSource records")
        object.__setattr__(self, "sources", tuple(sorted(sources, key=lambda s: s.source_id)))
        source_ids = {s.source_id for s in sources}
        channels = tuple(self.channels)
        if any(not isinstance(c, EnvironmentChannel) for c in channels) or len({c.channel_id for c in channels}) != len(channels):
            raise InvalidScientificProblem("environment channels must be unique EnvironmentChannel records")
        basis = self.timeline.basis.basis_id
        for c in channels:
            kind = self.registry.get(c.kind_id)
            if dimensionality(c.unit) != kind.dimension:
                raise InvalidScientificProblem(
                    f"channel {c.channel_id!r} unit {c.unit!r} is not a {kind.kind_id} unit ({kind.reference_unit})"
                )
            if kind.circular and c.interpolation is not None and c.interpolation.method is EnvironmentInterpolation.LINEAR:
                raise InvalidScientificProblem(
                    f"channel {c.channel_id!r}: {kind.kind_id} is circular; LINEAR interpolation "
                    f"of an angle is not authorized"
                )
            if c.source_id not in source_ids:
                raise InvalidScientificProblem(f"channel {c.channel_id!r} names undeclared source {c.source_id!r}")
            declared = {p.quantity_id for p in c.context.parameters}
            missing = set(kind.context_parameters) - declared
            if missing:
                raise InvalidScientificProblem(
                    f"channel {c.channel_id!r} ({kind.kind_id}) lacks reference context {sorted(missing)}; "
                    f"a value without it is not interpretable"
                )
            if c.validity.basis_id != basis or not self.timeline.horizon.covers(c.validity):
                raise InvalidScientificProblem(f"channel {c.channel_id!r} validity is not inside the timeline horizon on its basis")
            if c.representation is ChannelRepresentation.INTERVAL_HISTORY:
                history = self.timeline.history(c.history_id)
                if history.kind is not HistoryKind.EXPOSURE:
                    raise InvalidScientificProblem(f"channel {c.channel_id!r} references a non-EXPOSURE history")
                if history.quantity_id != c.channel_id or dimensionality(history.unit) != kind.dimension:
                    raise InvalidScientificProblem(f"history {c.history_id!r} does not carry channel {c.channel_id!r}")
                if not c.validity.covers(history.span):
                    raise InvalidScientificProblem(f"history {c.history_id!r} extends outside channel validity")
        for a in channels:
            for b in channels:
                if a.channel_id < b.channel_id and (a.kind_id, a.context.location_id, a.context.context_id) == (b.kind_id, b.context.location_id, b.context.context_id) and a.validity.overlaps(b.validity):
                    raise InvalidScientificProblem(
                        f"channels {a.channel_id!r} and {b.channel_id!r} both supply {a.kind_id} at "
                        f"{a.context.location_id}/{a.context.context_id} over overlapping validity; "
                        f"the environment does not arbitrate between sources"
                    )
        object.__setattr__(self, "channels", tuple(sorted(channels, key=lambda c: c.channel_id)))
        required = tuple(sorted({(_identifier(k, "required kind"), _identifier(l, "required location")) for k, l in self.required}))
        for kind_id, _ in required:
            self.registry.get(kind_id)
        object.__setattr__(self, "required", required)

    # ---- evaluation --------------------------------------------------------

    def source(self, source_id: str) -> EnvironmentSource:
        for item in self.sources:
            if item.source_id == source_id:
                return item
        raise InvalidScientificProblem(f"environment has no source {source_id!r}")

    def channel(self, channel_id: str) -> EnvironmentChannel:
        for c in self.channels:
            if c.channel_id == channel_id:
                return c
        raise InvalidScientificProblem(f"environment has no channel {channel_id!r}")

    def _unknown(self, c: EnvironmentChannel, reason: str) -> EnvironmentValue:
        return EnvironmentValue(c.kind_id, c.context.location_id, c.context.context_id, c.channel_id, c.source_id, ValueStatus.UNKNOWN, ValueDerivation.NONE, None, reason, self.source(c.source_id).classification)

    def _known(self, c: EnvironmentChannel, derivation: ValueDerivation, value: NamedQuantity) -> EnvironmentValue:
        return EnvironmentValue(c.kind_id, c.context.location_id, c.context.context_id, c.channel_id, c.source_id, ValueStatus.KNOWN, derivation, value, "", self.source(c.source_id).classification)

    def channel_value(self, channel_id: str, at: TimePoint) -> EnvironmentValue:
        c = self.channel(channel_id)
        if at.basis_id != self.timeline.basis.basis_id:
            raise InvalidScientificProblem("environment query is not on the timeline basis")
        if not self.timeline.horizon.contains(at):
            raise InvalidScientificProblem("environment query lies outside the timeline horizon")
        if not c.validity.contains(at):
            return self._unknown(c, f"{at.seconds} second is outside the validity of channel {channel_id!r}")
        if c.representation is ChannelRepresentation.INTERVAL_HISTORY:
            result = self.timeline.history(c.history_id).value_at(at)
            if result.status is ValueStatus.UNKNOWN:
                return self._unknown(c, result.reason)
            return self._known(c, ValueDerivation.INTERVAL_DECLARED, result.value)
        s = at.seconds
        for sample in c.samples:
            if sample.at.seconds == s:
                return self._known(c, ValueDerivation.SAMPLED, sample.value)
        before = [x for x in c.samples if x.at.seconds < s]
        after = [x for x in c.samples if x.at.seconds > s]
        contract = c.interpolation
        if contract.method is EnvironmentInterpolation.NONE:
            return self._unknown(c, f"channel {channel_id!r} authorizes values only at its samples")
        if not before or not after:
            return self._unknown(c, f"channel {channel_id!r} would have to extrapolate to {s} second")
        lo, hi = before[-1], after[0]
        if hi.at.seconds - lo.at.seconds > contract.max_gap_seconds:
            return self._unknown(
                c, f"samples at {lo.at.seconds} and {hi.at.seconds} second are further apart than "
                   f"the authorized max_gap"
            )
        for event in self.timeline.events:
            if event.kind is TimelineEventKind.DISCONTINUITY and event.subject_id == channel_id and lo.at.seconds < event.at.seconds <= s:
                return self._unknown(c, f"declared discontinuity {event.event_id!r} lies between the sample and the query")
            if (event.kind is TimelineEventKind.DISCONTINUITY and event.subject_id == channel_id
                    and contract.method is EnvironmentInterpolation.LINEAR and s < event.at.seconds <= hi.at.seconds):
                return self._unknown(c, f"LINEAR interpolation would cross declared discontinuity {event.event_id!r}")
        uncertainty = Uncertainty.unknown(
            f"interpolated ({contract.method.value}) between samples of {channel_id!r}; interpolation "
            f"error is not quantified and an interpolated value is not a measurement"
        )
        if contract.method is EnvironmentInterpolation.STEP_HOLD:
            magnitude = lo.value.value.magnitude_in(c.unit)
        else:
            w = (s - lo.at.seconds) / (hi.at.seconds - lo.at.seconds)
            a, b = lo.value.value.magnitude_in(c.unit), hi.value.value.magnitude_in(c.unit)
            magnitude = a + float(w) * (b - a)
        return self._known(c, ValueDerivation.INTERPOLATED, NamedQuantity(channel_id, Quantity(magnitude, c.unit), uncertainty))

    def state_at(self, at: TimePoint, location_id: str) -> EnvironmentState:
        values = [self.channel_value(c.channel_id, at) for c in self.channels if c.context.location_id == location_id]
        covered = {(v.kind_id, v.location_id) for v in values}
        for kind_id, loc in self.required:
            if loc == location_id and (kind_id, loc) not in covered:
                values.append(EnvironmentValue(kind_id, loc, "", "", "", ValueStatus.UNKNOWN, ValueDerivation.NONE, None, f"no channel supplies required {kind_id!r} at {loc!r}", NO_SOURCE))
        return EnvironmentState(at, location_id, self.digest, tuple(values))

    def verify_state(self, state: EnvironmentState) -> None:
        """Refuse a (deserialized) state this environment does not reproduce exactly."""
        if not isinstance(state, EnvironmentState):
            raise InvalidScientificProblem("verify_state requires an EnvironmentState")
        if state.environment_digest != self.digest or state.digest != self.state_at(state.at, state.location_id).digest:
            raise InvalidScientificProblem("environment state is not the one this environment produces")

    def history(self, location_id: str, points: Iterable[TimePoint]) -> tuple[EnvironmentState, ...]:
        """A deterministic sequence of states; the query order is canonicalized."""
        ordered = sorted(set(points), key=lambda p: (p.basis_id, p.seconds))
        return tuple(self.state_at(p, location_id) for p in ordered)

    def dose(self, channel_id: str, window: TimeWindow) -> EnvironmentValue:
        """Time-integrated exposure for lifecycle consumers.

        Only interval-history channels of ratio-scale kinds have a dose; a
        point-sample channel would need its interpolation to be integrated,
        which would present interpolation as accumulated exposure.
        """
        c = self.channel(channel_id)
        kind = self.registry.get(c.kind_id)
        if c.representation is not ChannelRepresentation.INTERVAL_HISTORY:
            return self._unknown(c, f"channel {channel_id!r} holds point samples; no dose is declared")
        if kind.affine or not is_ratio_scale(c.unit):
            return self._unknown(c, f"{kind.kind_id} is an affine quantity; a time integral of it is not a dose")
        if not c.validity.covers(window):
            return self._unknown(c, f"window reaches outside the validity of {channel_id!r}")
        result = self.timeline.history(c.history_id).integrate(window)
        if result.status is ValueStatus.UNKNOWN:
            return self._unknown(c, result.reason)
        return self._known(c, ValueDerivation.INTERVAL_DECLARED, result.value)

    def window_mean(self, channel_id: str, window: TimeWindow) -> EnvironmentValue:
        """Time-weighted mean of an interval-history channel over ``window``.

        Allowed for affine kinds (a mean temperature is meaningful where its
        integral is not).  UNKNOWN for point-sample channels (no declared
        interval values; interpolation is not averaged into exposure), outside
        validity, or over any gap.  Uncertainty: sum(sigma_i*dt_i)/T, an upper
        bound for any correlation, only if every contribution is STANDARD;
        otherwise UNKNOWN.  Representation error is not included.
        """
        c = self.channel(channel_id)
        if c.representation is not ChannelRepresentation.INTERVAL_HISTORY:
            return self._unknown(c, f"channel {channel_id!r} holds point samples; no declared window mean")
        if not c.validity.covers(window):
            return self._unknown(c, f"window reaches outside the validity of {channel_id!r}")
        history = self.timeline.history(c.history_id)
        gaps = history.gaps_within(window)
        if gaps:
            return self._unknown(c, f"history {c.history_id!r} has no declared value over part of the window")
        total = Fraction(0)
        sigma = Fraction(0)
        standard = True
        for entry in history.entries:
            dt = max(Fraction(0), min(entry.window.end.seconds, window.end.seconds) - max(entry.window.start.seconds, window.start.seconds))
            if dt <= 0:
                continue
            total += Fraction(repr(entry.value.value.magnitude_in(c.unit))) * dt
            unc = entry.value.uncertainty
            if unc.kind.value == "standard":
                sigma += Fraction(repr(unc.standard_uncertainty.magnitude_as_spread_in(c.unit))) * dt
            else:
                standard = False
        duration = window.end.seconds - window.start.seconds
        # The only computable spread is a correlation-free UPPER BOUND, which is
        # not a 1-sigma; it is stated in the notes and the kind stays UNKNOWN.
        bound = (f"; a correlation-free upper bound on its spread is {float(sigma / duration)!r} {c.unit}"
                 if standard and is_ratio_scale(c.unit) else "")
        uncertainty = Uncertainty.unknown(
            f"window mean of {channel_id!r}: standard uncertainty not estimated (correlation "
            f"between entries undeclared; representation error not included){bound}"
        )
        return self._known(c, ValueDerivation.INTERVAL_DECLARED, NamedQuantity(f"{channel_id}.mean", Quantity(float(total / duration), c.unit), uncertainty))

    # ---- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENV_TIMELINE_SCHEMA, "environment_id": self.environment_id,
            "timeline": self.timeline.to_dict(),
            "registry": [k.to_dict() for k in self.registry.kinds],
            "sources": [s.to_dict() for s in self.sources],
            "channels": [c.to_dict() for c in self.channels],
            "required": [[k, l] for k, l in self.required],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentTimeline":
        require_schema(payload, ENV_TIMELINE_SCHEMA)
        _strict_keys(payload, {"schema", "environment_id", "timeline", "registry", "sources", "channels", "required"}, "environment timeline")
        return cls(
            payload["environment_id"], Timeline.from_dict(payload["timeline"]),
            EnvironmentKindRegistry(tuple(EnvironmentQuantityKind.from_dict(k) for k in payload["registry"])),
            tuple(EnvironmentSource.from_dict(s) for s in payload["sources"]),
            tuple(EnvironmentChannel.from_dict(c) for c in payload["channels"]),
            tuple((k, l) for k, l in payload["required"]),
        )
