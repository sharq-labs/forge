from __future__ import annotations

from dataclasses import dataclass
import math, re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity

OUTPUT_EXPECTATION_SCHEMA=schema_string("replay_output_expectation")
OUTPUT_OBSERVATION_SCHEMA=schema_string("replay_output_observation")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OutputExpectation:
    output_id:str
    expected:Quantity
    absolute_tolerance:Quantity
    relative_tolerance:float=0.0

    def __post_init__(self)->None:
        output_id=str(self.output_id).strip()
        if not output_id or not isinstance(self.expected,Quantity) or not isinstance(self.absolute_tolerance,Quantity):
            raise InvalidScientificProblem("output expectation requires id and typed quantities")
        if self.absolute_tolerance.magnitude<0:
            raise InvalidScientificProblem("output absolute tolerance must be non-negative")
        try: self.absolute_tolerance.magnitude_as_spread_in(self.expected.units)
        except Exception as exc: raise InvalidScientificProblem(f"output tolerance dimension differs from expected output: {exc}") from exc
        relative=float(self.relative_tolerance)
        if not math.isfinite(relative) or relative<0:
            raise InvalidScientificProblem("output relative tolerance must be finite and non-negative")
        object.__setattr__(self,"output_id",output_id);object.__setattr__(self,"relative_tolerance",relative)

    def to_dict(self)->dict[str,Any]:
        return {"schema":OUTPUT_EXPECTATION_SCHEMA,"output_id":self.output_id,
                "expected":self.expected.to_dict(),"absolute_tolerance":self.absolute_tolerance.to_dict(),
                "relative_tolerance":self.relative_tolerance}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"OutputExpectation":
        require_schema(payload,OUTPUT_EXPECTATION_SCHEMA)
        return cls(payload["output_id"],Quantity.from_dict(payload["expected"]),
                   Quantity.from_dict(payload["absolute_tolerance"]),payload.get("relative_tolerance",0.0))


@dataclass(frozen=True)
class OutputObservation:
    output_id:str
    actual:Quantity
    evidence_digest:str

    def __post_init__(self)->None:
        output_id=str(self.output_id).strip();digest=str(self.evidence_digest).strip().lower()
        if not output_id or not isinstance(self.actual,Quantity) or not _SHA256.fullmatch(digest):
            raise InvalidScientificProblem("output observation requires id Quantity and evidence SHA-256")
        if not math.isfinite(float(self.actual.magnitude)):
            raise InvalidScientificProblem("output observation magnitude must be finite")
        object.__setattr__(self,"output_id",output_id);object.__setattr__(self,"evidence_digest",digest)

    def to_dict(self)->dict[str,Any]:
        return {"schema":OUTPUT_OBSERVATION_SCHEMA,"output_id":self.output_id,
                "actual":self.actual.to_dict(),"evidence_digest":self.evidence_digest}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"OutputObservation":
        require_schema(payload,OUTPUT_OBSERVATION_SCHEMA)
        return cls(payload["output_id"],Quantity.from_dict(payload["actual"]),payload["evidence_digest"])


@dataclass(frozen=True)
class OutputComparison:
    output_id:str
    matched:bool
    absolute_error:float|None
    allowed_error:float|None
    unit:str
    problem:str=""


def compare_output(expectation:OutputExpectation,observation:OutputObservation)->OutputComparison:
    if expectation.output_id!=observation.output_id:
        raise InvalidScientificProblem("output comparison ids differ")
    try:
        actual=observation.actual.to(expectation.expected.units)
        absolute=abs(actual.magnitude-expectation.expected.magnitude)
        absolute_tol=expectation.absolute_tolerance.magnitude_as_spread_in(expectation.expected.units)
    except Exception as exc:
        return OutputComparison(expectation.output_id,False,None,None,expectation.expected.units,
                                f"output dimension mismatch: {exc}")
    relative=expectation.relative_tolerance*max(abs(actual.magnitude),abs(expectation.expected.magnitude))
    allowed=max(absolute_tol,relative)
    return OutputComparison(expectation.output_id,absolute<=allowed,absolute,allowed,expectation.expected.units)
