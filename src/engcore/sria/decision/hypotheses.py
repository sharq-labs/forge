"""M4G — the minimum hypothesis contract DISCRIMINATE needs.

Just enough to say "these two models disagree about this observable, and the
disagreement matters for the decision". Deliberately not a model-averaging
framework: this repository has no real posterior over models, and building the
machinery for one would mean inventing the numbers it consumes.

Weights are optional. When absent, :class:`HypothesisSet` reports
``weights_available = False`` and the discrimination generator still works —
it proposes where predictions diverge, which needs no prior. What it will not
do is fabricate a prior to make a formula look complete.

Automated hypothesis *generation* is out of scope. Hypotheses are declared by
the campaign or a Domain Pack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string

HYPOTHESIS_SCHEMA = schema_string("sria_hypothesis")
HYPOTHESIS_SET_SCHEMA = schema_string("sria_hypothesis_set")


@dataclass(frozen=True)
class Hypothesis:
    """One candidate explanation, with pointers to what supports it."""

    hypothesis_id: str
    model_ref: str
    description: str = ""
    weight: float | None = None            # None = no inference produced one
    parameter_belief_ref: str = ""
    scope_ref: str = ""
    evidence_links: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("hypothesis_id", "model_ref"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"hypothesis requires {label}")
        if self.weight is not None:
            weight = float(self.weight)
            if not 0.0 <= weight <= 1.0:
                raise ValueError(
                    f"hypothesis weight must lie in [0, 1], got {weight}"
                )
            object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "evidence_links", tuple(self.evidence_links))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": HYPOTHESIS_SCHEMA,
            "hypothesis_id": self.hypothesis_id,
            "model_ref": self.model_ref,
            "description": self.description,
            "weight": self.weight,
            "parameter_belief_ref": self.parameter_belief_ref,
            "scope_ref": self.scope_ref,
            "evidence_links": list(self.evidence_links),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Hypothesis":
        require_schema(payload, HYPOTHESIS_SCHEMA)
        return cls(
            hypothesis_id=payload["hypothesis_id"],
            model_ref=payload["model_ref"],
            description=payload.get("description", ""),
            weight=payload.get("weight"),
            parameter_belief_ref=payload.get("parameter_belief_ref", ""),
            scope_ref=payload.get("scope_ref", ""),
            evidence_links=tuple(payload.get("evidence_links", ())),
        )


@dataclass(frozen=True)
class PredictionDisagreement:
    """How far two hypotheses diverge on one observable.

    Supplied by the campaign or Domain Pack — SRIA cannot evaluate a physical
    model to find out.
    """

    observable: str
    hypothesis_a: str
    hypothesis_b: str
    separation: float                # in the observable's own units
    decision_relevant: bool = True

    def __post_init__(self) -> None:
        if self.hypothesis_a == self.hypothesis_b:
            raise ValueError("a hypothesis cannot disagree with itself")
        if float(self.separation) < 0.0:
            raise ValueError("separation must be non-negative")
        object.__setattr__(self, "separation", float(self.separation))
        if not isinstance(self.decision_relevant, bool):
            raise ValueError("decision_relevant must be an explicit bool")


@dataclass(frozen=True)
class HypothesisSet:
    """The competing explanations a campaign is currently entertaining."""

    hypotheses: tuple[Hypothesis, ...] = ()
    disagreements: tuple[PredictionDisagreement, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(self, "disagreements", tuple(self.disagreements))
        ids = [h.hypothesis_id for h in self.hypotheses]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate hypothesis ids: {sorted(duplicates)}")
        known = set(ids)
        for disagreement in self.disagreements:
            missing = {disagreement.hypothesis_a, disagreement.hypothesis_b} - known
            if missing:
                raise ValueError(
                    f"disagreement references unknown hypotheses {sorted(missing)}"
                )

    @property
    def weights_available(self) -> bool:
        return bool(self.hypotheses) and all(
            h.weight is not None for h in self.hypotheses
        )

    def decision_relevant_disagreements(
        self,
    ) -> tuple[PredictionDisagreement, ...]:
        """Divergences worth paying to resolve, largest separation first."""
        return tuple(
            sorted(
                (d for d in self.disagreements if d.decision_relevant),
                key=lambda d: (-d.separation, d.observable),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": HYPOTHESIS_SET_SCHEMA,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "disagreements": [
                {
                    "observable": d.observable,
                    "hypothesis_a": d.hypothesis_a,
                    "hypothesis_b": d.hypothesis_b,
                    "separation": d.separation,
                    "decision_relevant": d.decision_relevant,
                }
                for d in self.disagreements
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisSet":
        require_schema(payload, HYPOTHESIS_SET_SCHEMA)
        return cls(
            hypotheses=tuple(
                Hypothesis.from_dict(h) for h in payload.get("hypotheses", ())
            ),
            disagreements=tuple(
                PredictionDisagreement(
                    observable=d["observable"],
                    hypothesis_a=d["hypothesis_a"],
                    hypothesis_b=d["hypothesis_b"],
                    separation=d["separation"],
                    decision_relevant=bool(d.get("decision_relevant", True)),
                )
                for d in payload.get("disagreements", ())
            ),
        )
