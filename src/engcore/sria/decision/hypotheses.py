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

Roadmap V2 (discovery authority consolidation): :class:`Hypothesis` is the
CANONICAL hypothesis record of the platform.  Other hypothesis-shaped records
adapt into it (``discovery_adapter``) rather than compete with it.  It was
extended with trailing, defaulted fields -- a record that uses none of them
serializes byte-identically to the M4G record:

* ``kind`` (:class:`HypothesisKind`) is fixed for the life of a hypothesis:
  :meth:`Hypothesis.revise` never changes it, and :func:`derive_hypothesis`
  refuses to turn an EQUATION (a fit) into a MECHANISM claim without separate
  mechanism basis references -- an equation that fits observations is not a
  mechanism;
* ``status`` (:class:`HypothesisStatus`) has no TRUE / VALIDATED / PROVEN
  member.  SURVIVING, REFUTED and INDISTINGUISHABLE must name the sealed
  falsifier verdicts that decided them;
* ``novelty_status`` is a separate axis from the scientific status;
* ``proposal`` records who proposed the hypothesis.  A language model may
  propose; it never decides a status (statuses are set from verdict records).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string

HYPOTHESIS_SCHEMA = schema_string("sria_hypothesis")
HYPOTHESIS_SET_SCHEMA = schema_string("sria_hypothesis_set")
PROPOSAL_PROVENANCE_SCHEMA = schema_string("sria_hypothesis_proposal")
HYPOTHESIS_PARAMETER_SCHEMA = schema_string("sria_hypothesis_parameter")
HYPOTHESIS_PREDICTION_SCHEMA = schema_string("sria_hypothesis_prediction")


class HypothesisKind(str, Enum):
    """What a hypothesis is a claim ABOUT.  Fixed for the life of the hypothesis."""

    MECHANISM = "mechanism"                    # a causal/physical mechanism
    EQUATION = "equation"                      # a functional relation that fits/predicts observables
    MODEL_STRUCTURE = "model_structure"        # which model form / terms / latent structure
    INTERVENTION_EFFECT = "intervention_effect"  # the effect of a declared intervention
    REGIME_BOUNDARY = "regime_boundary"        # where behaviour changes regime
    DESIGN_CLAIM = "design_claim"              # a design meets a declared requirement
    NULL = "null"                              # no effect / no relation beyond a declared baseline


class HypothesisStatus(str, Enum):
    """Scientific standing.  There is no TRUE: surviving a test is not being true."""

    PROPOSED = "proposed"
    ADMITTED_FOR_TEST = "admitted_for_test"
    SURVIVING = "surviving"                    # not refuted by its sealed falsifiers so far
    REFUTED = "refuted"
    INDISTINGUISHABLE = "indistinguishable"    # the admitted evidence cannot separate it from a rival
    OUT_OF_SCOPE = "out_of_scope"
    UNKNOWN = "unknown"


#: statuses that report a test outcome and must name the verdict records behind them
VERDICT_BACKED_STATUSES = frozenset({HypothesisStatus.SURVIVING, HypothesisStatus.REFUTED, HypothesisStatus.INDISTINGUISHABLE})


class NoveltyStatus(str, Enum):
    """Separate from scientific status.  There is deliberately no NOVEL member: novelty is only ever
    'possibly novel against a frozen prior-art snapshot', and an opinion is not a novelty check."""

    NOT_CHECKED = "not_checked"
    KNOWN_EQUIVALENT = "known_equivalent"
    POSSIBLY_NOVEL = "possibly_novel"
    NOVELTY_UNRESOLVED = "novelty_unresolved"


class ProposerKind(str, Enum):
    HUMAN = "human"
    ALGORITHM = "algorithm"            # a declared search/regression procedure
    LANGUAGE_MODEL = "language_model"  # proposer only: no authority over status, applicability or evidence
    DOMAIN_PACK = "domain_pack"
    LEGACY_ADAPTER = "legacy_adapter"  # adapted from a pre-V2 record


class ParameterProvenance(str, Enum):
    DECLARED = "declared"
    FITTED = "fitted"                  # fitted to observations: carries the fit's data, not independent support
    LITERATURE = "literature"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProposalProvenance:
    proposer_kind: ProposerKind
    proposer_id: str
    proposal_digest: str = ""          # content address of the stored proposal (replay reuses it, never re-proposes)
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposer_kind", ProposerKind(self.proposer_kind))
        if not str(self.proposer_id).strip():
            raise ValueError("a proposal names its proposer")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROPOSAL_PROVENANCE_SCHEMA, "proposer_kind": self.proposer_kind.value, "proposer_id": self.proposer_id,
                "proposal_digest": self.proposal_digest, "note": self.note}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProposalProvenance":
        require_schema(payload, PROPOSAL_PROVENANCE_SCHEMA)
        return cls(payload["proposer_kind"], payload["proposer_id"], payload.get("proposal_digest", ""), payload.get("note", ""))


@dataclass(frozen=True)
class HypothesisParameter:
    name: str
    unit: str
    value: float | None = None         # None = not known (never a default)
    provenance: ParameterProvenance = ParameterProvenance.UNKNOWN
    source_ref: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip() or not str(self.unit).strip():
            raise ValueError("a hypothesis parameter has a name and a unit ('dimensionless' explicitly)")
        object.__setattr__(self, "provenance", ParameterProvenance(self.provenance))
        if self.value is not None:
            object.__setattr__(self, "value", float(self.value))
        if self.provenance in (ParameterProvenance.LITERATURE, ParameterProvenance.FITTED) and not str(self.source_ref).strip():
            raise ValueError(f"parameter {self.name!r}: a {self.provenance.value} value names its source")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HYPOTHESIS_PARAMETER_SCHEMA, "name": self.name, "unit": self.unit, "value": self.value, "provenance": self.provenance.value,
                "source_ref": self.source_ref}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisParameter":
        require_schema(payload, HYPOTHESIS_PARAMETER_SCHEMA)
        return cls(payload["name"], payload["unit"], payload.get("value"), payload.get("provenance", "unknown"), payload.get("source_ref", ""))


@dataclass(frozen=True)
class HypothesisPrediction:
    """A prediction the hypothesis makes: an observable under declared conditions."""

    observable: str
    unit: str
    condition_ref: str
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("observable", "unit", "condition_ref"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"a prediction requires {label}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HYPOTHESIS_PREDICTION_SCHEMA, "observable": self.observable, "unit": self.unit,
                "condition_ref": self.condition_ref, "description": self.description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisPrediction":
        require_schema(payload, HYPOTHESIS_PREDICTION_SCHEMA)
        return cls(payload["observable"], payload["unit"], payload["condition_ref"], payload.get("description", ""))


#: V2 extension fields and their defaults: emitted only when set, so an M4G record keeps its bytes.
_EXTENSION_DEFAULTS: Mapping[str, Any] = {
    "kind": None, "statement": "", "statement_payload": {}, "structure_digest": "", "predictions": (), "parameters": (),
    "complexity": None, "proposal": None, "knowledge_snapshot_ref": "", "parents": (), "novelty_status": NoveltyStatus.NOT_CHECKED,
    "falsifier_refs": (), "status": HypothesisStatus.PROPOSED, "status_basis": (), "mechanism_basis_refs": (), "revision": 0,
}


@dataclass(frozen=True)
class Hypothesis:
    """One candidate explanation, with pointers to what supports it.  The canonical hypothesis record."""

    hypothesis_id: str
    model_ref: str
    description: str = ""
    weight: float | None = None            # None = no inference produced one
    parameter_belief_ref: str = ""
    scope_ref: str = ""
    evidence_links: tuple[str, ...] = ()
    # ---- Roadmap V2 extension (trailing, defaulted) -------------------------
    kind: HypothesisKind | None = None
    statement: str = ""
    statement_payload: Mapping[str, Any] = field(default_factory=dict)  # typed statement (e.g. a canonical equation)
    structure_digest: str = ""             # canonical structure identity (dedup / novelty), when one exists
    predictions: tuple[HypothesisPrediction, ...] = ()
    parameters: tuple[HypothesisParameter, ...] = ()
    complexity: int | None = None
    proposal: ProposalProvenance | None = None
    knowledge_snapshot_ref: str = ""
    parents: tuple[str, ...] = ()
    novelty_status: NoveltyStatus = NoveltyStatus.NOT_CHECKED
    falsifier_refs: tuple[str, ...] = ()   # sealed falsifier identities (pre-registered)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    status_basis: tuple[str, ...] = ()     # verdict record identities that set the status
    mechanism_basis_refs: tuple[str, ...] = ()
    revision: int = 0

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
        if self.kind is not None:
            object.__setattr__(self, "kind", HypothesisKind(self.kind))
        object.__setattr__(self, "status", HypothesisStatus(self.status))
        object.__setattr__(self, "novelty_status", NoveltyStatus(self.novelty_status))
        object.__setattr__(self, "statement_payload", json.loads(json.dumps(dict(self.statement_payload), sort_keys=True)))
        for label in ("predictions", "parameters", "parents", "falsifier_refs", "status_basis", "mechanism_basis_refs"):
            object.__setattr__(self, label, tuple(getattr(self, label)))
        if any(not isinstance(p, HypothesisPrediction) for p in self.predictions):
            raise ValueError("predictions are HypothesisPrediction records")
        if any(not isinstance(p, HypothesisParameter) for p in self.parameters):
            raise ValueError("parameters are HypothesisParameter records")
        if len({p.name for p in self.parameters}) != len(self.parameters):
            raise ValueError("hypothesis parameter names must be unique")
        if self.proposal is not None and not isinstance(self.proposal, ProposalProvenance):
            raise ValueError("proposal is a ProposalProvenance")
        if self.complexity is not None and (isinstance(self.complexity, bool) or int(self.complexity) < 0):
            raise ValueError("complexity is a non-negative integer")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("revision is a non-negative integer")
        extended = self.kind is not None
        if self.status is not HypothesisStatus.PROPOSED and not extended:
            raise ValueError("a hypothesis with a scientific status declares its kind")
        if self.status in VERDICT_BACKED_STATUSES:
            if not self.falsifier_refs or not self.status_basis:
                raise ValueError(f"status {self.status.value} must name the sealed falsifiers and the verdict records that decided it; "
                                 "a status is never asserted")
        if self.status is HypothesisStatus.ADMITTED_FOR_TEST and not (self.predictions or self.falsifier_refs):
            raise ValueError("a hypothesis admitted for test states at least one prediction or falsifier")

    # ---- identity / serialization ---------------------------------------------
    def _extension(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        values = {
            "kind": None if self.kind is None else self.kind.value, "statement": self.statement,
            "statement_payload": dict(self.statement_payload), "structure_digest": self.structure_digest,
            "predictions": [p.to_dict() for p in self.predictions], "parameters": [p.to_dict() for p in self.parameters],
            "complexity": self.complexity, "proposal": None if self.proposal is None else self.proposal.to_dict(),
            "knowledge_snapshot_ref": self.knowledge_snapshot_ref, "parents": list(self.parents),
            "novelty_status": self.novelty_status.value, "falsifier_refs": list(self.falsifier_refs), "status": self.status.value,
            "status_basis": list(self.status_basis), "mechanism_basis_refs": list(self.mechanism_basis_refs), "revision": self.revision,
        }
        for key, default in _EXTENSION_DEFAULTS.items():
            d = default.value if isinstance(default, Enum) else (list(default) if isinstance(default, tuple) else default)
            if values[key] != d:
                out[key] = values[key]
        return out

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
            **self._extension(),
        }

    @property
    def digest(self) -> str:
        """Content identity of this revision (status and basis included)."""
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Hypothesis":
        require_schema(payload, HYPOTHESIS_SCHEMA)
        proposal = payload.get("proposal")
        return cls(
            hypothesis_id=payload["hypothesis_id"],
            model_ref=payload["model_ref"],
            description=payload.get("description", ""),
            weight=payload.get("weight"),
            parameter_belief_ref=payload.get("parameter_belief_ref", ""),
            scope_ref=payload.get("scope_ref", ""),
            evidence_links=tuple(payload.get("evidence_links", ())),
            kind=payload.get("kind"),
            statement=payload.get("statement", ""),
            statement_payload=payload.get("statement_payload", {}),
            structure_digest=payload.get("structure_digest", ""),
            predictions=tuple(HypothesisPrediction.from_dict(p) for p in payload.get("predictions", ())),
            parameters=tuple(HypothesisParameter.from_dict(p) for p in payload.get("parameters", ())),
            complexity=payload.get("complexity"),
            proposal=None if proposal is None else ProposalProvenance.from_dict(proposal),
            knowledge_snapshot_ref=payload.get("knowledge_snapshot_ref", ""),
            parents=tuple(payload.get("parents", ())),
            novelty_status=payload.get("novelty_status", "not_checked"),
            falsifier_refs=tuple(payload.get("falsifier_refs", ())),
            status=payload.get("status", "proposed"),
            status_basis=tuple(payload.get("status_basis", ())),
            mechanism_basis_refs=tuple(payload.get("mechanism_basis_refs", ())),
            revision=int(payload.get("revision", 0)),
        )

    # ---- revisions --------------------------------------------------------------
    def revise(self, **changes: Any) -> "Hypothesis":
        """A new revision.  The kind never changes; a changed statement, prediction, parameter or falsifier set
        resets the status to PROPOSED (a test of the old content says nothing about the new)."""
        if "kind" in changes and changes["kind"] != self.kind and self.kind is not None:
            raise ValueError("a hypothesis keeps its kind; a different kind of claim is a new hypothesis (derive_hypothesis)")
        if "hypothesis_id" in changes and changes["hypothesis_id"] != self.hypothesis_id:
            raise ValueError("a revision keeps the hypothesis id; a new id is a new hypothesis")
        content = {"statement", "statement_payload", "structure_digest", "predictions", "parameters", "falsifier_refs", "scope_ref"}
        new = replace(self, revision=self.revision + 1, **changes)
        if content & set(changes) and not ({"status", "status_basis"} & set(changes)):
            new = replace(new, status=HypothesisStatus.PROPOSED, status_basis=())
        return new


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


def derive_hypothesis(parent: Hypothesis, *, hypothesis_id: str, kind: HypothesisKind | str, **fields: Any) -> Hypothesis:
    """A new hypothesis derived from ``parent`` (a new id, status PROPOSED, no inherited falsifiers or verdicts).

    An EQUATION that fits observations is never upgraded to a MECHANISM: deriving a MECHANISM from an EQUATION
    parent requires ``mechanism_basis_refs`` naming support beyond the fit (e.g. intervention or structural evidence).
    """
    kind = HypothesisKind(kind)
    if parent.kind is HypothesisKind.EQUATION and kind is HypothesisKind.MECHANISM and not fields.get("mechanism_basis_refs"):
        raise ValueError("an equation that fits observations is not a mechanism: a MECHANISM derived from an EQUATION names "
                         "mechanism_basis_refs beyond the fit")
    for forbidden in ("status", "status_basis", "falsifier_refs", "revision"):
        if forbidden in fields:
            raise ValueError(f"a derived hypothesis starts PROPOSED with no inherited {forbidden}")
    if hypothesis_id == parent.hypothesis_id:
        raise ValueError("a derived hypothesis has its own id")
    return Hypothesis(hypothesis_id=hypothesis_id, kind=kind, parents=tuple(sorted({*fields.pop("parents", ()), parent.hypothesis_id})),
                      **fields)


__all__ = [
    "HYPOTHESIS_SCHEMA", "HYPOTHESIS_SET_SCHEMA", "Hypothesis", "HypothesisKind", "HypothesisParameter", "HypothesisPrediction",
    "HypothesisSet", "HypothesisStatus", "NoveltyStatus", "ParameterProvenance", "PredictionDisagreement", "ProposalProvenance",
    "ProposerKind", "VERDICT_BACKED_STATUSES", "derive_hypothesis",
]
