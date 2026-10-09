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
VERDICT_REFERENCE_SCHEMA = schema_string("sria_hypothesis_verdict_reference")


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


@dataclass(frozen=True)
class VerdictReference:
    """Why a hypothesis has a verdict-backed status: one falsifier verdict, bound to the exact hypothesis CONTENT it judged.

    Binding to :attr:`Hypothesis.content_digest` means a verdict about one revision's content cannot back another's.
    Whether the verdict record itself exists and says what this reference claims is checked against the sealed
    verdict store by the adjudicator (``engcore.design.falsifiers.verify_status``); a reference alone is not a verdict.
    """

    falsifier_ref: str
    verdict_digest: str
    verdict: str                       # "refuted" | "not_refuted" | "inconclusive" (as the verdict record states)
    content_digest: str

    def __post_init__(self) -> None:
        if not str(self.falsifier_ref).strip():
            raise ValueError("a verdict reference names its falsifier")
        for label in ("verdict_digest", "content_digest"):
            v = str(getattr(self, label))
            if len(v) != 64 or any(ch not in "0123456789abcdef" for ch in v):
                raise ValueError(f"a verdict reference binds {label} (sha256)")
        if self.verdict not in ("refuted", "not_refuted", "inconclusive"):
            raise ValueError("a verdict is refuted, not_refuted or inconclusive")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": VERDICT_REFERENCE_SCHEMA, "falsifier_ref": self.falsifier_ref, "verdict_digest": self.verdict_digest,
                "verdict": self.verdict, "content_digest": self.content_digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerdictReference":
        require_schema(payload, VERDICT_REFERENCE_SCHEMA)
        return cls(payload["falsifier_ref"], payload["verdict_digest"], payload["verdict"], payload["content_digest"])


#: V2 extension fields and their defaults: emitted only when set, so an M4G record keeps its bytes.
_EXTENSION_DEFAULTS: Mapping[str, Any] = {
    "kind": None, "statement": "", "statement_payload": {}, "structure_digest": "", "predictions": (), "parameters": (),
    "complexity": None, "proposal": None, "knowledge_snapshot_ref": "", "parents": (), "novelty_status": NoveltyStatus.NOT_CHECKED,
    "falsifier_refs": (), "status": HypothesisStatus.PROPOSED, "status_basis": (), "mechanism_basis_refs": (), "revision": 0,
    "novelty_basis": "", "status_note": "",
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
    statement_payload: Mapping[str, Any] = field(default_factory=dict, hash=False)  # typed statement (e.g. a canonical equation)
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
    status_basis: tuple[VerdictReference, ...] = ()  # the falsifier verdicts that set the status, bound to this content
    mechanism_basis_refs: tuple[str, ...] = ()
    revision: int = 0
    novelty_basis: str = ""                # the novelty-check record (required for any novelty other than NOT_CHECKED)
    status_note: str = ""                  # OUT_OF_SCOPE / UNKNOWN: the applicability or check record behind it

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
        if any(not isinstance(b, VerdictReference) for b in self.status_basis):
            raise ValueError("status_basis holds VerdictReference records")
        if self.status in VERDICT_BACKED_STATUSES:
            if not self.falsifier_refs or not self.status_basis:
                raise ValueError(f"status {self.status.value} must name the sealed falsifiers and the verdict records that decided it; "
                                 "a status is never asserted")
            content = self.content_digest
            for b in self.status_basis:
                if b.content_digest != content:
                    raise ValueError(f"verdict {b.verdict_digest[:12]} judged other content than this revision; a verdict does not "
                                     "transfer to changed content")
                if b.falsifier_ref not in self.falsifier_refs:
                    raise ValueError(f"verdict names falsifier {b.falsifier_ref!r}, which is not one of this hypothesis's falsifiers")
            verdicts = {b.verdict for b in self.status_basis}
            if self.status is HypothesisStatus.REFUTED and "refuted" not in verdicts:
                raise ValueError("REFUTED needs a 'refuted' verdict")
            if self.status is HypothesisStatus.SURVIVING and verdicts != {"not_refuted"}:
                raise ValueError("SURVIVING needs every cited verdict to be not_refuted (a refuting or inconclusive verdict is not survival)")
        elif self.status_basis:
            raise ValueError(f"status {self.status.value} carries no verdict basis")
        if self.status is HypothesisStatus.OUT_OF_SCOPE and not str(self.status_note).strip():
            raise ValueError("OUT_OF_SCOPE names the applicability record behind it")
        if self.novelty_status is not NoveltyStatus.NOT_CHECKED and not (str(self.knowledge_snapshot_ref).strip()
                                                                           and str(self.novelty_basis).strip()):
            raise ValueError("a novelty status other than NOT_CHECKED names the frozen prior-art snapshot and the check record")
        if self.kind is HypothesisKind.MECHANISM and self.parents:
            if not self.mechanism_basis_refs:
                raise ValueError("a MECHANISM derived from other hypotheses names mechanism_basis_refs beyond any fit; an equation "
                                 "that fits observations is not a mechanism")
            fit_refs = set(self.evidence_links) | {p.source_ref for p in self.parameters if p.provenance is ParameterProvenance.FITTED}
            if fit_refs & set(self.mechanism_basis_refs):
                raise ValueError("the mechanism basis cannot be the fit itself")
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
            "status_basis": [b.to_dict() for b in self.status_basis], "mechanism_basis_refs": list(self.mechanism_basis_refs),
            "revision": self.revision, "novelty_basis": self.novelty_basis, "status_note": self.status_note,
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

    #: what a test of the hypothesis is ABOUT; any change is new content (status, novelty and narrative excluded)
    CONTENT_FIELDS = ("hypothesis_id", "model_ref", "scope_ref", "kind", "statement", "statement_payload", "structure_digest",
                      "predictions", "parameters", "falsifier_refs", "parents", "mechanism_basis_refs", "parameter_belief_ref")

    @property
    def content_digest(self) -> str:
        full = self.to_dict()
        content = {k: full.get(k) for k in self.CONTENT_FIELDS}
        return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

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
            status_basis=tuple(VerdictReference.from_dict(b) for b in payload.get("status_basis", ())),
            mechanism_basis_refs=tuple(payload.get("mechanism_basis_refs", ())),
            revision=int(payload.get("revision", 0)),
            novelty_basis=payload.get("novelty_basis", ""),
            status_note=payload.get("status_note", ""),
        )

    # ---- revisions --------------------------------------------------------------
    def revise(self, **changes: Any) -> "Hypothesis":
        """A new revision.  The id, kind and parents never change.  Any content change resets the status to PROPOSED
        and refuses a carried-over verdict basis: a test of the old content says nothing about the new."""
        for fixed in ("hypothesis_id", "kind", "parents", "revision"):
            if fixed in changes and changes[fixed] != getattr(self, fixed):
                raise ValueError(f"a revision keeps its {fixed}; a different {fixed} is a new hypothesis (derive_hypothesis)")
        content_changed = bool(set(changes) & set(self.CONTENT_FIELDS))
        if content_changed and ({"status", "status_basis"} & set(changes)):
            raise ValueError("a content change and a status cannot arrive together; the new content is untested (PROPOSED)")
        if content_changed:
            return replace(self, revision=self.revision + 1, **{"status": HypothesisStatus.PROPOSED, "status_basis": (),
                                                                "status_note": "", **changes})
        return replace(self, revision=self.revision + 1, **changes)

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

    A MECHANISM derived from anything (directly or through intermediate kinds) must name ``mechanism_basis_refs``
    beyond the fit; the constructor enforces it for every MECHANISM with parents, so a two-hop derivation
    (EQUATION -> MODEL_STRUCTURE -> MECHANISM) or a direct construction does not bypass it.
    """
    kind = HypothesisKind(kind)
    for forbidden in ("status", "status_basis", "falsifier_refs", "revision", "novelty_status", "novelty_basis"):
        if forbidden in fields:
            raise ValueError(f"a derived hypothesis starts PROPOSED with no inherited {forbidden}")
    if hypothesis_id == parent.hypothesis_id:
        raise ValueError("a derived hypothesis has its own id")
    return Hypothesis(hypothesis_id=hypothesis_id, kind=kind, parents=tuple(sorted({*fields.pop("parents", ()), parent.hypothesis_id})),
                      **fields)

__all__ = [
    "HYPOTHESIS_SCHEMA", "HYPOTHESIS_SET_SCHEMA", "Hypothesis", "HypothesisKind", "HypothesisParameter", "HypothesisPrediction",
    "HypothesisSet", "HypothesisStatus", "NoveltyStatus", "ParameterProvenance", "PredictionDisagreement", "ProposalProvenance",
    "ProposerKind", "VERDICT_BACKED_STATUSES", "VerdictReference", "derive_hypothesis",
]
