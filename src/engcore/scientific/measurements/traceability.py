from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

TRACEABILITY_REFERENCE_SCHEMA = schema_string("measurement_traceability_reference")
TRACEABILITY_CHAIN_SCHEMA = schema_string("measurement_traceability_chain")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TraceabilityKind(str, Enum):
    CALIBRATION_LAB = "calibration_lab"
    REFERENCE_STANDARD = "reference_standard"
    NATIONAL_STANDARD = "national_standard"
    PRIMARY_REALIZATION = "primary_realization"
    CERTIFICATE = "certificate"
    DATASET = "dataset"
    OTHER = "other"


@dataclass(frozen=True)
class TraceabilityReference:
    reference_id: str
    kind: TraceabilityKind
    issuer: str
    document_digest: str
    version: str = ""

    def __post_init__(self) -> None:
        rid = str(self.reference_id).strip()
        issuer = str(self.issuer).strip()
        digest = str(self.document_digest).strip().lower()
        if not rid or not issuer or not _SHA256.fullmatch(digest):
            raise InvalidScientificProblem(
                "traceability reference requires id, issuer and SHA-256 digest"
            )
        object.__setattr__(self, "reference_id", rid)
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "document_digest", digest)
        object.__setattr__(self, "version", str(self.version).strip())
        object.__setattr__(self, "kind", TraceabilityKind(self.kind))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TRACEABILITY_REFERENCE_SCHEMA,
            "reference_id": self.reference_id,
            "kind": self.kind.value,
            "issuer": self.issuer,
            "document_digest": self.document_digest,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TraceabilityReference":
        require_schema(payload, TRACEABILITY_REFERENCE_SCHEMA)
        return cls(
            payload["reference_id"],
            TraceabilityKind(payload["kind"]),
            payload["issuer"],
            payload["document_digest"],
            payload.get("version", ""),
        )


@dataclass(frozen=True)
class MeasurementTraceabilityChain:
    chain_id: str
    references: tuple[TraceabilityReference, ...]
    links: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        chain_id = str(self.chain_id).strip()
        references = tuple(self.references)
        links = tuple(
            (str(left).strip(), str(right).strip())
            for left, right in self.links
        )
        if not chain_id or not references:
            raise InvalidScientificProblem(
                "measurement traceability chain requires id and references"
            )
        if any(not isinstance(ref, TraceabilityReference) for ref in references):
            raise InvalidScientificProblem(
                "traceability chain requires TraceabilityReference records"
            )
        ids = [ref.reference_id for ref in references]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem(
                "traceability chain contains duplicate reference ids"
            )
        known = set(ids)
        if any(
            not left
            or not right
            or left == right
            or left not in known
            or right not in known
            for left, right in links
        ):
            raise InvalidScientificProblem(
                "traceability links must connect distinct known references"
            )
        if len(links) != len(set(links)):
            raise InvalidScientificProblem(
                "traceability chain contains duplicate links"
            )

        graph: dict[str, set[str]] = {item: set() for item in known}
        incoming: dict[str, int] = {item: 0 for item in known}
        for child, parent in links:
            graph[child].add(parent)
            incoming[parent] += 1

        visiting: set[str] = set()
        done: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise InvalidScientificProblem(
                    "measurement traceability chain contains a cycle"
                )
            if node in done:
                return
            visiting.add(node)
            for parent in sorted(graph[node]):
                visit(parent)
            visiting.remove(node)
            done.add(node)

        for node in sorted(known):
            visit(node)

        # At least one terminal anchor must exist; otherwise the chain names
        # intermediate certificates but never reaches a standard/realization.
        parent_ids = {parent for _, parent in links}
        anchors = [
            ref
            for ref in references
            if ref.reference_id in parent_ids
            and ref.kind
            in {
                TraceabilityKind.REFERENCE_STANDARD,
                TraceabilityKind.NATIONAL_STANDARD,
                TraceabilityKind.PRIMARY_REALIZATION,
            }
        ]
        if not anchors:
            raise InvalidScientificProblem(
                "measurement traceability chain reaches no declared reference standard"
            )
        object.__setattr__(self, "chain_id", chain_id)
        object.__setattr__(self, "references", references)
        object.__setattr__(self, "links", tuple(sorted(links)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TRACEABILITY_CHAIN_SCHEMA,
            "chain_id": self.chain_id,
            "references": [
                ref.to_dict()
                for ref in sorted(
                    self.references, key=lambda ref: ref.reference_id
                )
            ],
            "links": [list(link) for link in self.links],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "MeasurementTraceabilityChain":
        require_schema(payload, TRACEABILITY_CHAIN_SCHEMA)
        return cls(
            payload["chain_id"],
            tuple(
                TraceabilityReference.from_dict(ref)
                for ref in payload.get("references", ())
            ),
            tuple(tuple(link) for link in payload.get("links", ())),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
