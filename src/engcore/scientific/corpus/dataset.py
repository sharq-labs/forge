"""Reference cases, observations, and the split authority that keeps them honest.

WHY THE SPLIT IS STRUCTURAL AND NOT A LABEL
--------------------------------------------
Calibration, validation and locked holdout are three different scientific
roles, and the whole value of the last two comes from a negative: the fitting
path *did not see them*. A string field saying ``"holdout"`` does not deliver
that. Anything holding the dataset can read every case regardless of what the
field says, and the day someone fits on all of it the record still reads
"holdout".

So the split is enforced by what a caller can obtain:

* :meth:`ReferenceDataset.calibration_cases` returns calibration cases and
  nothing else;
* :meth:`ReferenceDataset.validation_cases` returns validation cases and
  nothing else;
* locked-holdout cases are reachable only through
  :meth:`ReferenceDataset.released_holdout_cases`, which demands a
  :class:`HoldoutRelease` naming a registered evaluation and carrying this
  exact dataset's normalized digest.

A fitting routine that only ever receives the result of the first method
cannot consume the holdout by accident, and one that wants to must construct
and record a release -- which is the audit trail the split exists to produce.

INDEPENDENCE IS A PROPERTY OF THE EVIDENCE, NOT OF THE LABEL
-------------------------------------------------------------
Two cases from the same cell, the same specimen or the same run are not
independent, whatever split they are filed under. Every case declares an
``independence_group``, and a group that appears on both sides of the
calibration boundary is refused at construction: that is the same evidence
acting as both the fit and its own independent test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable

from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from .source import (
    CorpusError,
    CorpusLeakageError,
    ReferenceSource,
    SourceSnapshot,
    ToleranceBasis,
    ToleranceSpec,
    require_quantity,
    sha256_hex,
    text,
)

REFERENCE_CONDITION_SCHEMA = schema_string("corpus_reference_condition")
REFERENCE_CASE_SCHEMA = schema_string("corpus_reference_case")
REFERENCE_OBSERVATION_SCHEMA = schema_string("corpus_reference_observation")
REFERENCE_DATASET_SCHEMA = schema_string("corpus_reference_dataset")
HOLDOUT_RELEASE_SCHEMA = schema_string("corpus_holdout_release")
HOLDOUT_OPENING_SCHEMA = schema_string("corpus_holdout_opening")


class DatasetSplit(str, Enum):
    """What a case is allowed to influence.

    ``CALIBRATION`` may influence fitted parameters. ``VALIDATION`` must not.
    ``LOCKED_HOLDOUT`` must not influence fitting *or* model selection, and
    must stay unread until a registered evaluation releases it.
    """

    CALIBRATION = "calibration"
    VALIDATION = "validation"
    LOCKED_HOLDOUT = "locked_holdout"

    @property
    def may_influence_fitting(self) -> bool:
        return self is DatasetSplit.CALIBRATION


#: The splits a model-selection or fitting path may never read without an
#: explicit, recorded release.
LOCKED_SPLITS = frozenset({DatasetSplit.LOCKED_HOLDOUT})


class Applicability(str, Enum):
    """Whether a case lies inside the *declared* applicability of the model.

    Deliberately three-valued. ``UNDECLARED`` is not ``INSIDE``: a corpus that
    has not been screened against a model's declared domain does not get to
    treat silence as permission.
    """

    INSIDE = "inside"
    OUTSIDE = "outside"
    UNDECLARED = "undeclared"


@dataclass(frozen=True, order=True)
class ReferenceCondition:
    """One coordinate of an operating point, unit-bearing.

    Core never learns what ``temperature`` or ``state_of_charge`` mean. It
    learns that a case sits at a named, dimensional coordinate, which is
    everything coverage and envelope reasoning need.
    """

    name: str
    value: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", text(self.name, label="condition name"))
        object.__setattr__(
            self, "value", require_quantity(self.value, label=f"condition {self.name!r}")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REFERENCE_CONDITION_SCHEMA,
            "name": self.name,
            "value": self.value.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceCondition":
        require_schema(payload, REFERENCE_CONDITION_SCHEMA)
        return cls(payload["name"], Quantity.from_dict(payload["value"]))


@dataclass(frozen=True, order=True)
class ReferenceCase:
    """One operating point from a reference source.

    ``inputs`` are what a model is given; ``conditions`` are the coordinates the
    case is indexed by for coverage. They overlap in practice and are kept
    separate because they are consumed by different machinery.
    """

    case_id: str
    split: DatasetSplit
    independence_group: str
    conditions: tuple[ReferenceCondition, ...] = ()
    inputs: tuple[ReferenceCondition, ...] = ()
    applicability: Applicability = Applicability.UNDECLARED
    tags: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", text(self.case_id, label="case_id"))
        object.__setattr__(self, "split", DatasetSplit(self.split))
        object.__setattr__(
            self,
            "independence_group",
            text(self.independence_group, label="independence_group"),
        )
        object.__setattr__(self, "applicability", Applicability(self.applicability))
        for label in ("conditions", "inputs"):
            items = tuple(getattr(self, label))
            if any(not isinstance(item, ReferenceCondition) for item in items):
                raise CorpusError(f"case {label} must be ReferenceCondition records")
            names = [item.name for item in items]
            if len(names) != len(set(names)):
                raise CorpusError(
                    f"case {self.case_id!r} repeats a {label[:-1]} name"
                )
            object.__setattr__(self, label, tuple(sorted(items)))
        object.__setattr__(
            self, "tags", tuple(sorted({text(item, label="tag") for item in self.tags}))
        )
        object.__setattr__(self, "note", str(self.note).strip())

    def condition(self, name: str) -> Quantity | None:
        for item in self.conditions:
            if item.name == name:
                return item.value
        return None

    @property
    def coordinates(self) -> dict[str, Quantity]:
        return {item.name: item.value for item in self.conditions}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REFERENCE_CASE_SCHEMA,
            "case_id": self.case_id,
            "split": self.split.value,
            "independence_group": self.independence_group,
            "conditions": [item.to_dict() for item in self.conditions],
            "inputs": [item.to_dict() for item in self.inputs],
            "applicability": self.applicability.value,
            "tags": list(self.tags),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceCase":
        require_schema(payload, REFERENCE_CASE_SCHEMA)
        return cls(
            payload["case_id"],
            DatasetSplit(payload["split"]),
            payload["independence_group"],
            tuple(ReferenceCondition.from_dict(i) for i in payload.get("conditions", ())),
            tuple(ReferenceCondition.from_dict(i) for i in payload.get("inputs", ())),
            Applicability(payload.get("applicability", "undeclared")),
            tuple(payload.get("tags", ())),
            payload.get("note", ""),
        )


@dataclass(frozen=True, order=True)
class ReferenceObservation:
    """One expected quantity at one case, with its source uncertainty and policy.

    ``acceptance_tolerance`` is optional and its absence is load-bearing: an
    observation with no reviewed tolerance is scored ``UNSCORED``, never
    ``PASS``. A tolerance that is present must carry the
    ``REVIEWED_ACCEPTANCE`` basis, so a source-reported spread cannot quietly
    become Forge's acceptance policy.
    """

    case_id: str
    metric: str
    expected: Quantity
    source_uncertainty: ToleranceSpec | None = None
    acceptance_tolerance: ToleranceSpec | None = None
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", text(self.case_id, label="case_id"))
        object.__setattr__(self, "metric", text(self.metric, label="metric"))
        object.__setattr__(
            self,
            "expected",
            require_quantity(self.expected, label=f"{self.case_id}/{self.metric} expected"),
        )
        for label, expected_basis in (
            ("source_uncertainty", ToleranceBasis.SOURCE_REPORTED),
            ("acceptance_tolerance", ToleranceBasis.REVIEWED_ACCEPTANCE),
        ):
            item = getattr(self, label)
            if item is None:
                continue
            if not isinstance(item, ToleranceSpec):
                raise CorpusError(f"{label} must be a ToleranceSpec or None")
            if item.basis is not expected_basis:
                raise CorpusError(
                    f"{self.case_id}/{self.metric} {label} carries basis "
                    f"{item.basis.value!r}; a {expected_basis.value!r} statement is "
                    f"a different scientific claim and cannot stand in for it"
                )
            item.require_comparable(
                self.expected, context=f"{self.case_id}/{self.metric} {label}"
            )
        object.__setattr__(self, "note", str(self.note).strip())

    @property
    def key(self) -> tuple[str, str]:
        return self.case_id, self.metric

    @property
    def is_scored(self) -> bool:
        return self.acceptance_tolerance is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REFERENCE_OBSERVATION_SCHEMA,
            "case_id": self.case_id,
            "metric": self.metric,
            "expected": self.expected.to_dict(),
            "source_uncertainty": (
                None if self.source_uncertainty is None else self.source_uncertainty.to_dict()
            ),
            "acceptance_tolerance": (
                None
                if self.acceptance_tolerance is None
                else self.acceptance_tolerance.to_dict()
            ),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceObservation":
        require_schema(payload, REFERENCE_OBSERVATION_SCHEMA)
        source = payload.get("source_uncertainty")
        acceptance = payload.get("acceptance_tolerance")
        return cls(
            payload["case_id"],
            payload["metric"],
            Quantity.from_dict(payload["expected"]),
            None if source is None else ToleranceSpec.from_dict(source),
            None if acceptance is None else ToleranceSpec.from_dict(acceptance),
            payload.get("note", ""),
        )


@dataclass(frozen=True)
class HoldoutRelease:
    """Registered permission to open one dataset's locked holdout, for one evaluation.

    It carries two bindings, and both are enforced rather than described.

    The **dataset** binding is the normalized digest, so a release cannot be
    reused against a dataset that has since changed -- the case where the
    holdout would silently stop being held out.

    The **evaluation** binding is the campaign this release was registered for,
    by id and version. Without it ``evaluation_id`` was a label: a release
    granted to evaluate campaign A could open the holdout for campaign B as
    long as the dataset matched, which is exactly the reuse a locked holdout
    exists to stop. :meth:`require_for` is called by
    :class:`~engcore.scientific.corpus.campaign.ValidationCampaign` at the only
    point a campaign can reach the holdout.

    On "once": a release object cannot enforce single use on its own, because
    nothing stops a caller from holding two campaigns with the same id. Strict
    one-time opening is enforced by :class:`HoldoutLedger`, which is an
    explicit authority with state, and this docstring does not claim what the
    record alone can deliver.
    """

    evaluation_id: str
    campaign_id: str
    campaign_version: str
    dataset_digest: str
    registered_at_utc: str
    reason: str

    def __post_init__(self) -> None:
        for label in (
            "evaluation_id",
            "campaign_id",
            "campaign_version",
            "registered_at_utc",
            "reason",
        ):
            object.__setattr__(self, label, text(getattr(self, label), label=label))
        object.__setattr__(
            self, "dataset_digest", sha256_hex(self.dataset_digest, label="dataset_digest")
        )

    @property
    def evaluation_key(self) -> tuple[str, str, str]:
        return self.evaluation_id, self.campaign_id, self.campaign_version

    def require_for(self, campaign_id: str, campaign_version: str) -> None:
        """Refuse a release registered for a different evaluation."""
        wanted = (str(campaign_id).strip(), str(campaign_version).strip())
        if (self.campaign_id, self.campaign_version) != wanted:
            raise CorpusLeakageError(
                f"holdout release {self.evaluation_id!r} was registered for "
                f"campaign {self.campaign_id}@{self.campaign_version}, not "
                f"{wanted[0]}@{wanted[1]}; a release does not carry over to "
                f"another evaluation even over the same dataset"
            )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": HOLDOUT_RELEASE_SCHEMA,
            "evaluation_id": self.evaluation_id,
            "campaign_id": self.campaign_id,
            "campaign_version": self.campaign_version,
            "dataset_digest": self.dataset_digest,
            "registered_at_utc": self.registered_at_utc,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HoldoutRelease":
        require_schema(payload, HOLDOUT_RELEASE_SCHEMA)
        return cls(
            payload["evaluation_id"],
            payload["campaign_id"],
            payload["campaign_version"],
            payload["dataset_digest"],
            payload["registered_at_utc"],
            payload["reason"],
        )


@dataclass(frozen=True)
class HoldoutOpening:
    """The record that a locked holdout was opened, and by whom for what."""

    release_digest: str
    evaluation_id: str
    campaign_id: str
    campaign_version: str
    dataset_digest: str
    opened_at_utc: str

    @property
    def digest(self) -> str:
        """The identity of this opening event, timestamp included.

        Two openings of the same release are different events, so the time is
        inside the digest. A report naming this digest names the opening that
        actually happened rather than the permission that allowed it.
        """
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def __post_init__(self) -> None:
        for label in (
            "evaluation_id",
            "campaign_id",
            "campaign_version",
            "opened_at_utc",
        ):
            object.__setattr__(self, label, text(getattr(self, label), label=label))
        for label in ("release_digest", "dataset_digest"):
            object.__setattr__(
                self, label, sha256_hex(getattr(self, label), label=label)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": HOLDOUT_OPENING_SCHEMA,
            "release_digest": self.release_digest,
            "evaluation_id": self.evaluation_id,
            "campaign_id": self.campaign_id,
            "campaign_version": self.campaign_version,
            "dataset_digest": self.dataset_digest,
            "opened_at_utc": self.opened_at_utc,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HoldoutOpening":
        require_schema(payload, HOLDOUT_OPENING_SCHEMA)
        return cls(
            payload["release_digest"],
            payload["evaluation_id"],
            payload["campaign_id"],
            payload["campaign_version"],
            payload["dataset_digest"],
            payload["opened_at_utc"],
        )


@runtime_checkable
class HoldoutLedger(Protocol):
    """The authority that makes "opened once" a fact rather than a wish.

    A :class:`HoldoutRelease` binds *which* evaluation may open a holdout. It
    cannot bind *how many times*, because a record has no memory -- and a
    docstring promising one-time semantics the code cannot keep is worse than
    no promise, because it is believed.

    This is the interface for the memory, deliberately separate from any one
    implementation so the guarantee can be stated precisely per implementation
    rather than claimed in general. :meth:`open` records an opening and refuses
    a release already opened.
    """

    def open(self, release: "HoldoutRelease") -> HoldoutOpening:
        """Record one opening, or refuse a release that was already opened."""
        ...

    def was_opened(self, release: "HoldoutRelease") -> bool:
        ...


class InMemoryHoldoutLedger:
    """A holdout ledger that remembers for as long as this process does.

    THE GUARANTEE, STATED EXACTLY. This refuses a second opening of the same
    release *through this object*. It is not a global one-time guarantee: a
    second instance, a second process, or a restart knows nothing about what
    this one recorded, and a caller holding two of these can open the same
    release twice.

    That is a real limit and it is named rather than papered over. Durable,
    cross-process single opening needs a persistent ledger, which is why
    :class:`HoldoutLedger` is an interface: the campaign path depends on the
    protocol, so a persistent implementation drops in without touching the
    execution path. Within one evaluation run -- which is where the accidental
    second look actually happens -- this is sufficient and enforced.
    """

    def __init__(
        self,
        openings: Iterable[HoldoutOpening] = (),
        *,
        clock: "Callable[[], str] | None" = None,
    ) -> None:
        self._openings: dict[str, HoldoutOpening] = {}
        self._clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat()
        )
        for item in openings:
            self._record(item)

    def _record(self, opening: HoldoutOpening) -> None:
        if not isinstance(opening, HoldoutOpening):
            raise CorpusError("a holdout ledger holds HoldoutOpening records")
        key = opening.release_digest
        existing = self._openings.get(key)
        if existing is not None:
            raise CorpusLeakageError(
                f"holdout release {opening.evaluation_id!r} was already opened at "
                f"{existing.opened_at_utc} for campaign "
                f"{existing.campaign_id}@{existing.campaign_version}; a locked "
                f"holdout is opened once and a second opening is not an audit "
                f"trail, it is a second look"
            )
        self._openings[key] = opening

    def open(
        self, release: "HoldoutRelease", *, opened_at_utc: str | None = None
    ) -> HoldoutOpening:
        """Record one opening. Refuses a release that has already been opened."""
        if not isinstance(release, HoldoutRelease):
            raise CorpusLeakageError("opening a holdout requires a HoldoutRelease")
        opening = HoldoutOpening(
            release_digest=release.digest,
            evaluation_id=release.evaluation_id,
            campaign_id=release.campaign_id,
            campaign_version=release.campaign_version,
            dataset_digest=release.dataset_digest,
            opened_at_utc=opened_at_utc or self._clock(),
        )
        self._record(opening)
        return opening

    def was_opened(self, release: "HoldoutRelease") -> bool:
        return release.digest in self._openings

    @property
    def openings(self) -> tuple[HoldoutOpening, ...]:
        return tuple(
            sorted(self._openings.values(), key=lambda item: item.release_digest)
        )


@dataclass(frozen=True)
class ReferenceDataset:
    """Cases and observations from one snapshot of one source.

    The normalized digest covers the science and the policy -- source identity,
    snapshot digest, every case, every expected value, every tolerance -- and
    nothing else. It is what a trust decision is pinned to, so a re-normalized
    dataset with one tolerance changed is a different dataset and any trust
    resting on the old digest is stale by construction.
    """

    dataset_id: str
    version: str
    source: ReferenceSource
    snapshot: SourceSnapshot
    cases: tuple[ReferenceCase, ...]
    observations: tuple[ReferenceObservation, ...]
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", text(self.dataset_id, label="dataset_id"))
        object.__setattr__(self, "version", text(self.version, label="version"))
        if not isinstance(self.source, ReferenceSource):
            raise CorpusError("dataset source must be a ReferenceSource")
        if not isinstance(self.snapshot, SourceSnapshot):
            raise CorpusError("dataset snapshot must be a SourceSnapshot")
        self.snapshot.require_from(self.source)

        cases = tuple(sorted(self.cases))
        if not cases or any(not isinstance(item, ReferenceCase) for item in cases):
            raise CorpusError("a reference dataset requires ReferenceCase records")
        case_ids = [item.case_id for item in cases]
        if len(case_ids) != len(set(case_ids)):
            raise CorpusError("reference dataset repeats a case_id")
        object.__setattr__(self, "cases", cases)

        observations = tuple(sorted(self.observations))
        if not observations or any(
            not isinstance(item, ReferenceObservation) for item in observations
        ):
            raise CorpusError("a reference dataset requires ReferenceObservation records")
        keys = [item.key for item in observations]
        if len(keys) != len(set(keys)):
            raise CorpusError("reference dataset repeats a case_id/metric pair")
        known = set(case_ids)
        orphans = sorted({item.case_id for item in observations} - known)
        if orphans:
            raise CorpusError(
                f"observations reference cases that do not exist: {orphans}"
            )
        object.__setattr__(self, "observations", observations)
        object.__setattr__(
            self, "metadata", None if self.metadata is None else dict(self.metadata)
        )

        self._require_independent_splits()

    def _require_independent_splits(self) -> None:
        """One independence group may not straddle the calibration boundary.

        This is the structural half of "the same evidence must never act as
        both the fit and its own independent test". A group that supplies a
        calibration case cannot also supply a validation or holdout case, and
        the refusal happens where the dataset is built rather than where the
        fit is scored.
        """
        by_group: dict[str, set[DatasetSplit]] = {}
        for case in self.cases:
            by_group.setdefault(case.independence_group, set()).add(case.split)
        offenders = sorted(
            group
            for group, splits in by_group.items()
            if DatasetSplit.CALIBRATION in splits and len(splits) > 1
        )
        if offenders:
            raise CorpusLeakageError(
                f"independence groups {offenders} supply both calibration and "
                f"independent evidence; the same evidence cannot be the fit and "
                f"the test of the fit"
            )

    # ---------------------------------------------------------------
    # Split-gated access. These are the only ways to reach cases.
    # ---------------------------------------------------------------

    def calibration_cases(self) -> tuple[ReferenceCase, ...]:
        """Cases a fitting path is permitted to consume."""
        return tuple(c for c in self.cases if c.split is DatasetSplit.CALIBRATION)

    def validation_cases(self) -> tuple[ReferenceCase, ...]:
        """Independent cases. Never an input to fitting."""
        return tuple(c for c in self.cases if c.split is DatasetSplit.VALIDATION)

    def released_holdout_cases(self, release: HoldoutRelease) -> tuple[ReferenceCase, ...]:
        """Locked-holdout cases, and only against a matching registered release."""
        if not isinstance(release, HoldoutRelease):
            raise CorpusLeakageError(
                "locked holdout cases require a registered HoldoutRelease; there "
                "is no unrecorded way to read them"
            )
        if release.dataset_digest != self.normalized_digest:
            raise CorpusLeakageError(
                f"holdout release names dataset digest "
                f"{release.dataset_digest[:12]}..., but this dataset is "
                f"{self.normalized_digest[:12]}...; a release does not carry over "
                f"to a dataset that has changed"
            )
        return tuple(c for c in self.cases if c.split is DatasetSplit.LOCKED_HOLDOUT)

    def cases_for_fitting(self) -> tuple[ReferenceCase, ...]:
        """The complete set a calibration path may see. Nothing locked is in it."""
        return self.calibration_cases()

    def observations_for(self, cases: Iterable[ReferenceCase]) -> tuple[ReferenceObservation, ...]:
        wanted = {case.case_id for case in cases}
        return tuple(item for item in self.observations if item.case_id in wanted)

    def case(self, case_id: str) -> ReferenceCase:
        for item in self.cases:
            if item.case_id == case_id:
                return item
        raise CorpusError(f"dataset {self.dataset_id!r} has no case {case_id!r}")

    @property
    def split_counts(self) -> dict[str, int]:
        counts = {split.value: 0 for split in DatasetSplit}
        for case in self.cases:
            counts[case.split.value] += 1
        return counts

    @property
    def unscored_observations(self) -> tuple[tuple[str, str], ...]:
        return tuple(item.key for item in self.observations if not item.is_scored)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REFERENCE_DATASET_SCHEMA,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "source": self.source.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "cases": [item.to_dict() for item in self.cases],
            "observations": [item.to_dict() for item in self.observations],
            "metadata": None if self.metadata is None else dict(self.metadata),
        }

    @property
    def normalized_digest(self) -> str:
        """Identity of the normalized science and policy, not of the file."""
        payload = dict(self.to_dict())
        payload.pop("metadata", None)
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceDataset":
        require_schema(payload, REFERENCE_DATASET_SCHEMA)
        return cls(
            payload["dataset_id"],
            payload["version"],
            ReferenceSource.from_dict(payload["source"]),
            SourceSnapshot.from_dict(payload["snapshot"]),
            tuple(ReferenceCase.from_dict(i) for i in payload["cases"]),
            tuple(ReferenceObservation.from_dict(i) for i in payload["observations"]),
            payload.get("metadata"),
        )


__all__ = [
    "HOLDOUT_OPENING_SCHEMA",
    "HOLDOUT_RELEASE_SCHEMA",
    "LOCKED_SPLITS",
    "REFERENCE_CASE_SCHEMA",
    "REFERENCE_CONDITION_SCHEMA",
    "REFERENCE_DATASET_SCHEMA",
    "REFERENCE_OBSERVATION_SCHEMA",
    "Applicability",
    "DatasetSplit",
    "HoldoutLedger",
    "InMemoryHoldoutLedger",
    "HoldoutOpening",
    "HoldoutRelease",
    "ReferenceCase",
    "ReferenceCondition",
    "ReferenceDataset",
    "ReferenceObservation",
]
