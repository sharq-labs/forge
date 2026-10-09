"""Record-chain anchors: commit the head of an external append-only chain into the campaign event log.

SRIA does not know what the chain is (a design search memory, a run ledger,
...): it records ``chain_kind``, the chain's ``head`` digest and its ``length``
in a ``RECORD_CHAIN_ANCHORED`` event, so the hash chain campaign persistence
verifies on resume also commits to that external head.  The owner of the
chain checks that a stored copy contains the anchored head at the anchored
length.  An anchor is never evidence and no assurance derivation reads it.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .events import CampaignEvent, CampaignEventType

RECORD_CHAIN_ANCHOR_SCHEMA = "engcore.sria.record_chain_anchor/1"
_HEX64 = re.compile(r"[0-9a-f]{64}")


class AnchorRefused(ValueError):
    """An anchor that would not describe an append-only chain."""


def anchor_payload(chain_kind: str, chain_schema: str, head: str, length: int) -> dict[str, Any]:
    kind, schema = str(chain_kind).strip(), str(chain_schema).strip()
    if not kind or not schema:
        raise AnchorRefused("a record-chain anchor names the chain kind and the chain's schema")
    if not _HEX64.fullmatch(str(head)):
        raise AnchorRefused("a record-chain anchor binds a sha256 head")
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise AnchorRefused("a record-chain anchor states a non-negative integer length")
    return {"schema": RECORD_CHAIN_ANCHOR_SCHEMA, "chain_kind": kind, "chain_schema": schema, "head": str(head), "length": length}


def chain_anchors(events: Iterable[CampaignEvent], chain_kind: str) -> tuple[Mapping[str, Any], ...]:
    """The anchors of ``chain_kind`` in the log, oldest first (each schema-checked)."""
    out = []
    for e in events:
        if e.event_type is CampaignEventType.RECORD_CHAIN_ANCHORED and e.payload.get("chain_kind") == chain_kind:
            if e.payload.get("schema") != RECORD_CHAIN_ANCHOR_SCHEMA:
                raise AnchorRefused(f"event {e.sequence} is not a supported record-chain anchor")
            out.append(e.payload)
    return tuple(out)


def require_growth(events: Iterable[CampaignEvent], payload: Mapping[str, Any]) -> None:
    """A new anchor of a chain never shrinks it, and an unchanged length keeps the same head."""
    previous = chain_anchors(events, payload["chain_kind"])
    if not previous:
        return
    last = previous[-1]
    if payload["chain_schema"] != last["chain_schema"]:
        raise AnchorRefused("the chain's schema changed between anchors")
    if payload["length"] < last["length"]:
        raise AnchorRefused(f"the chain shrank from {last['length']} to {payload['length']} records; an anchored chain only grows")
    if payload["length"] == last["length"] and payload["head"] != last["head"]:
        raise AnchorRefused("the chain was rewritten at the anchored length")


__all__ = ["AnchorRefused", "RECORD_CHAIN_ANCHOR_SCHEMA", "anchor_payload", "chain_anchors", "require_growth"]
