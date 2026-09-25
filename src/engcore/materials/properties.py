"""Material property data and resolution on top of ``scientific.knowledge``.

A :class:`PropertyDatum` is a ``KnowledgeClaim`` (kind MATERIAL_PROPERTY)
whose ``subject`` names an exact :class:`MaterialIdentity` and whose
``applicability_context_digest`` IS the digest of a declared
:class:`PropertyApplicability` -- the frozen claim contract already carried
that digest; this module gives it a checkable meaning.

Resolution (:meth:`MaterialPropertySet.resolve`) is fail-closed:

* a state that does not declare a condition a datum is stated at is UNKNOWN
  (a 20 degC value is never used at 500 degC, or at an unstated temperature);
* exactly one admissible datum -> SOURCED, with the claim's own uncertainty
  (UNKNOWN when the claim states none);
* two admissible data -> UNKNOWN (sources are not arbitrated);
* otherwise, only an explicit :class:`InterpolationRule` may produce a value,
  strictly between two tabulated points, never across a declared breakpoint
  (phase change / discontinuity), never by extrapolation; the result is
  INTERPOLATED with UNKNOWN uncertainty -- interpolation error is not
  quantified and tabulated spreads are not re-used as if they bounded it.

Constitutive *models* (a property computed by a realization, e.g. R(T) in
``domains.electrical.material``) stay ``ScientificModelDefinition`` claims.
This layer holds sourced data, not a parallel model hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Any, Mapping

from ..scenarios.contracts import NamedQuantity
from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.knowledge.claim import KnowledgeClaim, KnowledgeKind
from ..scientific.knowledge.snapshot import KnowledgeSnapshot
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity
from .identity import (
    ApplicabilityRange, MaterialIdentity, MaterialState, SourceIdentity, _exact, _identifier,
    _ranges, _strict_keys, source_identity,
)

APPLICABILITY_SCHEMA = schema_string("property_applicability")
DATUM_SCHEMA = schema_string("material_property_datum")
TRANSFORMATION_SCHEMA = schema_string("data_transformation")
RULE_SCHEMA = schema_string("property_interpolation_rule")
SET_SCHEMA = schema_string("material_property_set")
RESOLVED_SCHEMA = schema_string("resolved_material_property")


@dataclass(frozen=True)
class PropertyApplicability:
    """Where one property datum applies: exact material, property, ranges, phase."""

    material_digest: str
    property_id: str
    ranges: tuple[ApplicabilityRange, ...]
    phase: str = ""

    def __post_init__(self) -> None:
        digest = str(self.material_digest).strip().lower()
        if len(digest) != 64:
            raise InvalidScientificProblem("applicability requires the material identity digest")
        object.__setattr__(self, "material_digest", digest)
        object.__setattr__(self, "property_id", _identifier(self.property_id, "property_id"))
        ranges = _ranges(self.ranges, "applicability ranges")
        if not ranges and not str(self.phase).strip():
            raise InvalidScientificProblem(
                f"datum for {self.property_id!r} declares no applicability; a property value is "
                f"never universally applicable"
            )
        object.__setattr__(self, "ranges", ranges)
        object.__setattr__(self, "phase", str(self.phase or "").strip())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": APPLICABILITY_SCHEMA, "material_digest": self.material_digest, "property_id": self.property_id, "ranges": [r.to_dict() for r in self.ranges], "phase": self.phase}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "PropertyApplicability":
        require_schema(p, APPLICABILITY_SCHEMA)
        _strict_keys(p, {"schema", "material_digest", "property_id", "ranges", "phase"}, "property applicability")
        return cls(p["material_digest"], p["property_id"], tuple(ApplicabilityRange.from_dict(r) for r in p["ranges"]), p["phase"])


class DatumOrigin(str, Enum):
    MEASURED = "measured"          # reported measurement
    COMPILED = "compiled"          # a reference compilation's recommended value
    FITTED = "fitted"              # evaluated from a fitted correlation
    DERIVED = "derived"            # computed from other data
    ASSUMED = "assumed"            # a declared assumption; never evidence


@dataclass(frozen=True)
class TransformationRecord:
    """How a FITTED/DERIVED datum was produced from other claims."""

    transformation_id: str
    version: str
    input_claim_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "transformation_id", _identifier(self.transformation_id, "transformation_id"))
        if not str(self.version).strip():
            raise InvalidScientificProblem("transformation requires a version")
        digests = tuple(sorted(str(d).strip().lower() for d in self.input_claim_digests))
        if not digests or any(len(d) != 64 for d in digests):
            raise InvalidScientificProblem("transformation requires the digests of its input claims")
        object.__setattr__(self, "input_claim_digests", digests)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TRANSFORMATION_SCHEMA, "transformation_id": self.transformation_id, "version": self.version, "input_claim_digests": list(self.input_claim_digests)}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "TransformationRecord":
        require_schema(p, TRANSFORMATION_SCHEMA)
        return cls(p["transformation_id"], p["version"], tuple(p["input_claim_digests"]))


@dataclass(frozen=True)
class PropertyDatum:
    claim: KnowledgeClaim
    applicability: PropertyApplicability
    origin: DatumOrigin
    transformation: TransformationRecord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.claim, KnowledgeClaim) or not isinstance(self.applicability, PropertyApplicability):
            raise InvalidScientificProblem("property datum requires a KnowledgeClaim and PropertyApplicability")
        object.__setattr__(self, "origin", DatumOrigin(self.origin))
        c = self.claim
        if c.kind is not KnowledgeKind.MATERIAL_PROPERTY or c.numeric_value is None:
            raise InvalidScientificProblem("property datum claim must be a numeric MATERIAL_PROPERTY claim")
        if c.quantity_name != self.applicability.property_id:
            raise InvalidScientificProblem(f"claim states {c.quantity_name!r}, applicability names {self.applicability.property_id!r}")
        if c.subject != f"material:{self.applicability.material_digest}":
            raise InvalidScientificProblem("claim subject does not name the applicability's exact material")
        if c.applicability_context_digest != self.applicability.digest:
            raise InvalidScientificProblem("claim applicability_context_digest is not this applicability record")
        needs = self.origin in (DatumOrigin.FITTED, DatumOrigin.DERIVED)
        if needs != (self.transformation is not None):
            raise InvalidScientificProblem("FITTED/DERIVED data require a transformation record; other origins must not carry one")

    def admits(self, state: MaterialState) -> tuple[bool, str]:
        if self.applicability.phase and self.applicability.phase != state.phase:
            return False, f"datum is stated for phase {self.applicability.phase!r}, state is {state.phase or 'undeclared'!r}"
        for r in self.applicability.ranges:
            cond = state.condition(r.variable_id)
            if cond is None:
                return False, f"state does not declare {r.variable_id!r}; it is never assumed"
            if not r.admits(cond.value):
                return False, f"{r.variable_id} is outside the datum's declared range"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return {"schema": DATUM_SCHEMA, "claim": self.claim.to_dict(), "applicability": self.applicability.to_dict(), "origin": self.origin.value, "transformation": None if self.transformation is None else self.transformation.to_dict()}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "PropertyDatum":
        require_schema(p, DATUM_SCHEMA)
        _strict_keys(p, {"schema", "claim", "applicability", "origin", "transformation"}, "property datum")
        return cls(KnowledgeClaim.from_dict(p["claim"]), PropertyApplicability.from_dict(p["applicability"]), p["origin"], None if p["transformation"] is None else TransformationRecord.from_dict(p["transformation"]))


@dataclass(frozen=True)
class InterpolationRule:
    """Explicit authorization to interpolate one property along one variable.

    Only LINEAR between adjacent point data; ``breakpoints`` are declared
    discontinuities (phase changes) that interpolation may not cross or touch.
    """

    property_id: str
    variable_id: str
    method: str
    breakpoints: tuple[Quantity, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "property_id", _identifier(self.property_id, "rule property_id"))
        object.__setattr__(self, "variable_id", _identifier(self.variable_id, "rule variable_id"))
        if self.method != "linear":
            raise InvalidScientificProblem(f"unsupported property interpolation {self.method!r}")
        breakpoints = tuple(self.breakpoints)
        if any(not isinstance(b, Quantity) for b in breakpoints):
            raise InvalidScientificProblem("breakpoints must be Quantity records")
        for b in breakpoints[1:]:
            b.require_compatible(breakpoints[0].units, context=f"breakpoints of {self.property_id!r}")
        object.__setattr__(self, "breakpoints", breakpoints)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RULE_SCHEMA, "property_id": self.property_id, "variable_id": self.variable_id, "method": self.method, "breakpoints": [b.to_dict() for b in self.breakpoints]}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "InterpolationRule":
        require_schema(p, RULE_SCHEMA)
        return cls(p["property_id"], p["variable_id"], p["method"], tuple(Quantity.from_dict(b) for b in p["breakpoints"]))


class PropertyDerivation(str, Enum):
    SOURCED = "sourced"
    #: A single admissible datum whose origin is ASSUMED: a declared assumption.
    ASSUMED = "assumed"
    INTERPOLATED = "interpolated"
    NONE = "none"


@dataclass(frozen=True)
class ResolvedProperty:
    """A resolution result bound to set, snapshot, material state, data and rule."""

    property_id: str
    status: str  # "known" | "unknown"
    derivation: PropertyDerivation
    value: NamedQuantity | None
    set_digest: str
    snapshot_digest: str
    state_digest: str
    claim_digests: tuple[str, ...]
    origins: tuple[str, ...]
    sources: tuple[SourceIdentity, ...]
    rule: InterpolationRule | None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in ("known", "unknown"):
            raise InvalidScientificProblem("resolved property status is known or unknown")
        if (self.status == "known") != (self.value is not None) or (self.status == "unknown") != (self.derivation is PropertyDerivation.NONE):
            raise InvalidScientificProblem("resolved property status, value and derivation disagree")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RESOLVED_SCHEMA, "classification": "resolved_input_not_evidence", "property_id": self.property_id, "status": self.status, "derivation": self.derivation.value, "value": None if self.value is None else self.value.to_dict(), "set_digest": self.set_digest, "snapshot_digest": self.snapshot_digest, "state_digest": self.state_digest, "claim_digests": list(self.claim_digests), "origins": list(self.origins), "sources": [s.to_dict() for s in self.sources], "rule": None if self.rule is None else self.rule.to_dict(), "reason": self.reason}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class MaterialPropertySet:
    """Property data for ONE material from ONE knowledge snapshot, with its rules."""

    set_id: str
    material: MaterialIdentity
    snapshot: KnowledgeSnapshot
    data: tuple[PropertyDatum, ...]
    rules: tuple[InterpolationRule, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_id", _identifier(self.set_id, "set_id"))
        if not isinstance(self.material, MaterialIdentity) or not isinstance(self.snapshot, KnowledgeSnapshot):
            raise InvalidScientificProblem("property set requires a MaterialIdentity and a KnowledgeSnapshot")
        in_snapshot = {c.digest for c in self.snapshot.claims}
        data = tuple(self.data)
        for d in data:
            if not isinstance(d, PropertyDatum):
                raise InvalidScientificProblem("property set data must be PropertyDatum records")
            if d.applicability.material_digest != self.material.digest:
                raise InvalidScientificProblem(f"datum {d.claim.claim_id!r} is for a different material")
            if d.claim.digest not in in_snapshot:
                raise InvalidScientificProblem(f"datum {d.claim.claim_id!r} is not a claim of the snapshot")
            if d.transformation is not None and not set(d.transformation.input_claim_digests) <= in_snapshot:
                raise InvalidScientificProblem(f"datum {d.claim.claim_id!r} derives from claims outside the snapshot")
        if len({d.claim.claim_id for d in data}) != len(data):
            raise InvalidScientificProblem("property set repeats a claim")
        object.__setattr__(self, "data", tuple(sorted(data, key=lambda d: d.claim.claim_id)))
        rules = tuple(self.rules)
        if any(not isinstance(r, InterpolationRule) for r in rules) or len({r.property_id for r in rules}) != len(rules):
            raise InvalidScientificProblem("one InterpolationRule per property")
        object.__setattr__(self, "rules", tuple(sorted(rules, key=lambda r: r.property_id)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SET_SCHEMA, "set_id": self.set_id, "material": self.material.to_dict(), "snapshot": self.snapshot.to_dict(), "data": [d.to_dict() for d in self.data], "rules": [r.to_dict() for r in self.rules]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "MaterialPropertySet":
        require_schema(p, SET_SCHEMA)
        _strict_keys(p, {"schema", "set_id", "material", "snapshot", "data", "rules"}, "material property set")
        return cls(p["set_id"], MaterialIdentity.from_dict(p["material"]), KnowledgeSnapshot.from_dict(p["snapshot"]), tuple(PropertyDatum.from_dict(d) for d in p["data"]), tuple(InterpolationRule.from_dict(r) for r in p["rules"]))

    # ---- resolution -------------------------------------------------------

    def _sources(self, data: tuple[PropertyDatum, ...]) -> tuple[SourceIdentity, ...]:
        ids = {d.claim.source_id for d in data}
        return tuple(source_identity(s) for s in sorted(self.snapshot.sources, key=lambda s: s.source_id) if s.source_id in ids)

    def _result(self, pid, state, derivation, value, used, rule=None, reason=""):
        return ResolvedProperty(
            pid, "unknown" if value is None else "known", derivation, value, self.digest, self.snapshot.digest,
            state.digest, tuple(sorted(d.claim.digest for d in used)), tuple(sorted({d.origin.value for d in used})),
            self._sources(used), rule, reason,
        )

    def resolve(self, property_id: str, state: MaterialState) -> ResolvedProperty:
        if not isinstance(state, MaterialState):
            raise InvalidScientificProblem("resolve requires a MaterialState")
        if state.material.digest != self.material.digest:
            raise InvalidScientificProblem("state is for a different material than this property set")
        candidates = tuple(d for d in self.data if d.applicability.property_id == property_id)
        if not candidates:
            return self._result(property_id, state, PropertyDerivation.NONE, None, (), reason=f"no data for {property_id!r}")
        verdicts = [(d, *d.admits(state)) for d in candidates]
        admitted = tuple(d for d, ok, _ in verdicts if ok)
        if len(admitted) == 1:
            d = admitted[0]
            uq = d.claim.uncertainty or Uncertainty.unknown(f"claim {d.claim.claim_id} states no uncertainty")
            derivation = PropertyDerivation.ASSUMED if d.origin is DatumOrigin.ASSUMED else PropertyDerivation.SOURCED
            return self._result(property_id, state, derivation, NamedQuantity(property_id, d.claim.numeric_value, uq), admitted)
        if len(admitted) > 1:
            return self._result(property_id, state, PropertyDerivation.NONE, None, admitted,
                                reason="several data admit this state; sources are not arbitrated")
        rule = next((r for r in self.rules if r.property_id == property_id), None)
        if rule is None:
            return self._result(property_id, state, PropertyDerivation.NONE, None, (),
                                reason="; ".join(sorted({why for _, _, why in verdicts})) + "; no interpolation is authorized")
        cond = state.condition(rule.variable_id)
        if cond is None:
            return self._result(property_id, state, PropertyDerivation.NONE, None, (), rule, f"state does not declare {rule.variable_id!r}")
        points = []
        for d in candidates:
            along = next((r for r in d.applicability.ranges if r.variable_id == rule.variable_id), None)
            if along is None or not along.is_point:
                continue
            ok = all(
                (r.variable_id == rule.variable_id) or (state.condition(r.variable_id) is not None and r.admits(state.condition(r.variable_id).value))
                for r in d.applicability.ranges
            ) and (not d.applicability.phase or d.applicability.phase == state.phase)
            if ok:
                # Every position is expressed in the STATE condition's unit, so the
                # sort, bracket, breakpoints and weight compare like with like.
                along.lower.require_compatible(cond.value.units, context=f"interpolation along {rule.variable_id!r}")
                points.append((_exact(along.lower, cond.value.units), cond.value.units, d))
        if not points:
            return self._result(property_id, state, PropertyDerivation.NONE, None, (), rule, "no tabulated points admit the other conditions of this state")
        unit = points[0][1]
        v = _exact(cond.value, unit)
        points.sort(key=lambda p: p[0])
        below = [p for p in points if p[0] < v]
        above = [p for p in points if p[0] > v]
        if not below or not above:
            return self._result(property_id, state, PropertyDerivation.NONE, None, (), rule,
                                f"{rule.variable_id} lies outside the tabulated domain; extrapolation is not authorized")
        lo, hi = below[-1], above[0]
        if DatumOrigin.ASSUMED in (lo[2].origin, hi[2].origin):
            return self._result(property_id, state, PropertyDerivation.NONE, None, (lo[2], hi[2]), rule,
                                "interpolation between assumed data is not authorized; it would read as a sourced trend")
        for b in rule.breakpoints:
            b.require_compatible(unit, context=f"breakpoint of {property_id!r}")
            bv = _exact(b, unit)
            if lo[0] <= bv <= hi[0]:
                return self._result(property_id, state, PropertyDerivation.NONE, None, (lo[2], hi[2]), rule,
                                    f"a declared breakpoint at {b.magnitude} {b.units} lies in the interpolation bracket")
        a, c = lo[2].claim.numeric_value, hi[2].claim.numeric_value
        w = (v - lo[0]) / (hi[0] - lo[0])
        magnitude = a.magnitude + float(w) * (c.magnitude_in(a.units) - a.magnitude)
        uq = Uncertainty.unknown("linearly interpolated between tabulated data; interpolation error not quantified, and the tabulated uncertainties do not bound it")
        return self._result(property_id, state, PropertyDerivation.INTERPOLATED, NamedQuantity(property_id, Quantity(magnitude, a.units), uq), (lo[2], hi[2]), rule)
