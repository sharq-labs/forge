"""Calibration memory — versioned, replayable, and required to name a consumer.

Every entry declares ``consumed_by``: which future prediction or decision will
read it. An entry with no consumer is archive data and is stored as such,
explicitly. This is not bookkeeping fussiness — a calibration store that
accumulates summaries nobody reads becomes impossible to change safely,
because no one can tell which numbers still matter.

Entries are immutable and versioned by signature versions as well as model
version: a stored cost summary is only valid for the structure and environment
signature schemes it was fitted under. When those change, old entries do not
silently mis-apply; :meth:`CalibrationMemory.lookup` filters them out.

Persistence is JSON on disk, deliberately: the store must be replayable and
diffable by a human reviewing why a prediction changed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..signatures import (
    ENVIRONMENT_SIGNATURE_VERSION,
    STRUCTURE_SIGNATURE_VERSION,
)

MEMORY_ENTRY_SCHEMA = schema_string("sria_calibration_memory_entry")
MEMORY_STORE_SCHEMA = schema_string("sria_calibration_memory_store")


class MemoryKind(str, Enum):
    COST_MODEL = "cost_model"
    FAILURE_MODEL = "failure_model"
    FIDELITY_OBSERVATION = "fidelity_observation"
    CALIBRATION_DIAGNOSTIC = "calibration_diagnostic"


class Consumer(str, Enum):
    """Who reads this entry. ARCHIVE means: nothing does, and we admit it."""

    COST_PREDICTION = "cost_prediction"
    FAILURE_PREDICTION = "failure_prediction"
    FIDELITY_RELATIONSHIP_LOOKUP = "fidelity_relationship_lookup"
    CALIBRATION_AUDIT = "calibration_audit"
    ARCHIVE = "archive"


@dataclass(frozen=True)
class CalibrationMemoryEntry:
    """One immutable, versioned calibration fact."""

    entry_id: str
    kind: MemoryKind
    model_version: str
    dataset_id: str
    payload: Mapping[str, Any]
    consumed_by: tuple[Consumer, ...]
    structure_signature_version: int = STRUCTURE_SIGNATURE_VERSION
    environment_signature_version: int = ENVIRONMENT_SIGNATURE_VERSION
    metrics: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    def __post_init__(self) -> None:
        entry_id = str(self.entry_id).strip()
        if not entry_id:
            raise ValueError("calibration memory entry requires an entry_id")
        object.__setattr__(self, "entry_id", entry_id)
        object.__setattr__(self, "kind", MemoryKind(self.kind))
        object.__setattr__(
            self, "consumed_by", tuple(Consumer(c) for c in self.consumed_by)
        )
        if not self.consumed_by:
            raise ValueError(
                f"entry {entry_id!r} declares no consumer; if nothing reads it, "
                f"say so with Consumer.ARCHIVE rather than leaving it blank"
            )
        if not str(self.dataset_id).strip():
            raise ValueError(
                f"entry {entry_id!r} requires a dataset_id: a calibration fact "
                f"whose training data cannot be identified is not replayable"
            )
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "metrics", dict(self.metrics))
        object.__setattr__(self, "diagnostics", dict(self.diagnostics))

    @property
    def is_archive_only(self) -> bool:
        return self.consumed_by == (Consumer.ARCHIVE,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_ENTRY_SCHEMA,
            "entry_id": self.entry_id,
            "kind": self.kind.value,
            "model_version": self.model_version,
            "dataset_id": self.dataset_id,
            "payload": dict(self.payload),
            "consumed_by": [c.value for c in self.consumed_by],
            "structure_signature_version": self.structure_signature_version,
            "environment_signature_version": self.environment_signature_version,
            "metrics": dict(self.metrics),
            "diagnostics": dict(self.diagnostics),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationMemoryEntry":
        require_schema(payload, MEMORY_ENTRY_SCHEMA)
        return cls(
            entry_id=payload["entry_id"],
            kind=MemoryKind(payload["kind"]),
            model_version=payload["model_version"],
            dataset_id=payload["dataset_id"],
            payload=payload.get("payload", {}),
            consumed_by=tuple(Consumer(c) for c in payload.get("consumed_by", ())),
            structure_signature_version=payload.get(
                "structure_signature_version", STRUCTURE_SIGNATURE_VERSION
            ),
            environment_signature_version=payload.get(
                "environment_signature_version", ENVIRONMENT_SIGNATURE_VERSION
            ),
            metrics=payload.get("metrics", {}),
            diagnostics=payload.get("diagnostics", {}),
            created_at=payload.get("created_at"),
        )


class CalibrationMemory:
    """An append-only, replayable store of versioned calibration facts."""

    def __init__(self) -> None:
        self._entries: list[CalibrationMemoryEntry] = []

    def record(self, entry: CalibrationMemoryEntry) -> CalibrationMemoryEntry:
        if not isinstance(entry, CalibrationMemoryEntry):
            raise TypeError("only CalibrationMemoryEntry may be recorded")
        if any(e.entry_id == entry.entry_id for e in self._entries):
            raise ValueError(f"duplicate calibration entry id {entry.entry_id!r}")
        self._entries.append(entry)
        return entry

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[CalibrationMemoryEntry, ...]:
        return tuple(self._entries)

    def lookup(
        self,
        kind: MemoryKind,
        *,
        consumer: Consumer | None = None,
        structure_signature_version: int = STRUCTURE_SIGNATURE_VERSION,
        environment_signature_version: int = ENVIRONMENT_SIGNATURE_VERSION,
    ) -> tuple[CalibrationMemoryEntry, ...]:
        """Entries valid under the *current* signature schemes only."""
        kind = MemoryKind(kind)
        out = []
        for entry in self._entries:
            if entry.kind is not kind:
                continue
            if entry.structure_signature_version != structure_signature_version:
                continue
            if entry.environment_signature_version != environment_signature_version:
                continue
            if consumer is not None and Consumer(consumer) not in entry.consumed_by:
                continue
            out.append(entry)
        return tuple(out)

    def active_lookup(
        self,
        kind: MemoryKind,
        *,
        consumer: Consumer,
        structure_signature_version: int = STRUCTURE_SIGNATURE_VERSION,
        environment_signature_version: int = ENVIRONMENT_SIGNATURE_VERSION,
    ) -> tuple[CalibrationMemoryEntry, ...]:
        """The decision path's only lookup. ARCHIVE entries can never appear.

        Kept separate from :meth:`lookup` so the exclusion is a property of the
        API rather than of every caller remembering to filter. Archive storage
        becoming active intelligence by accident is exactly the failure mode
        this guards: an entry someone parked "for reference" silently starts
        informing predictions.
        """
        if Consumer(consumer) is Consumer.ARCHIVE:
            raise ValueError(
                "ARCHIVE is not a decision consumer; archived entries are "
                "records, not inputs to prediction"
            )
        return tuple(
            entry
            for entry in self.lookup(
                kind,
                consumer=consumer,
                structure_signature_version=structure_signature_version,
                environment_signature_version=environment_signature_version,
            )
            if not entry.is_archive_only
        )

    def archive_only(self) -> tuple[CalibrationMemoryEntry, ...]:
        return tuple(e for e in self._entries if e.is_archive_only)

    # ---- persistence ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_STORE_SCHEMA,
            "entries": [e.to_dict() for e in self._entries],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )
        return path

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationMemory":
        require_schema(payload, MEMORY_STORE_SCHEMA)
        memory = cls()
        for raw in payload.get("entries", ()):
            memory.record(CalibrationMemoryEntry.from_dict(raw))
        return memory

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationMemory":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
