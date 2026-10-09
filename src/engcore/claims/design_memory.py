"""Design memory anchored in an SRIA campaign's hash-chained event log.

A :class:`~engcore.design.history.DesignHistory` is the search's memory: every
attempt, and in particular every DETERMINISTIC NEGATIVE (refused, constraint
violated, contradicted) that lets a later search skip a known failure.  It is
search history, not evidence -- but losing part of it silently changes what a
resumed search does (a dropped negative is re-tried, a dropped contradiction
is forgotten).  Removing memory must never look like a fresh start.

This module (above both ``design`` and ``sria``; SRIA itself imports neither)
makes campaign persistence commit to that memory through SRIA's generic
record-chain anchor (:mod:`engcore.sria.campaign.anchors`):

* :func:`anchor_design_history` checks the history extends the latest anchored
  head, then has the campaign runner append a ``RECORD_CHAIN_ANCHORED`` event
  (head + length, never the attempts) and checkpoint it;
* :func:`restore_design_history` rebuilds a stored history and refuses it
  unless its chain contains the LATEST anchored head at the anchored length:
  a truncated or rewritten memory is refused; a memory that has grown past the
  anchor is returned with its unanchored tail counted.

The digests are unkeyed SHA-256, like the rest of campaign persistence: they
detect truncation, partial writes and accidental edits, not a deliberate
rewrite of every stored byte (see ``sria/campaign/persistence.py``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..design.history import GENESIS, HISTORY_SCHEMA, DesignHistory
from ..sria.campaign.anchors import chain_anchors
from ..sria.campaign.events import CampaignEvent
from .errors import ClaimLayerError

CHAIN_KIND = "engcore.design.history"


class DesignMemoryRefused(ClaimLayerError):
    """A stored design memory that the campaign's anchors do not support."""


def _head_at(history: DesignHistory, length: int) -> str:
    return GENESIS if length == 0 else history.entries[length - 1].digest


def require_extends(history: DesignHistory, anchor: Mapping[str, Any]) -> None:
    """``history`` must contain ``anchor``'s head at ``anchor``'s length (append-only growth)."""
    if anchor.get("chain_schema") != HISTORY_SCHEMA:
        raise DesignMemoryRefused(f"the anchor names chain schema {anchor.get('chain_schema')!r}, not {HISTORY_SCHEMA!r}")
    length = int(anchor["length"])
    if len(history) < length:
        raise DesignMemoryRefused(f"the design history has {len(history)} attempts but {length} were anchored: it was truncated")
    if _head_at(history, length) != anchor["head"]:
        raise DesignMemoryRefused("the design history does not contain the anchored head at the anchored length: it was rewritten")


def anchor_design_history(runner: Any, history: DesignHistory) -> CampaignEvent:
    """Commit ``history``'s head into ``runner``'s campaign chain (an IncrementalCampaignRunner, between iterations)."""
    if not isinstance(history, DesignHistory):
        raise DesignMemoryRefused("only a DesignHistory is anchored as design memory")
    previous = chain_anchors(runner.events, CHAIN_KIND)
    if previous:
        require_extends(history, previous[-1])
    return runner.anchor_record_chain(CHAIN_KIND, HISTORY_SCHEMA, history.head, len(history))


@dataclass(frozen=True)
class RestoredDesignMemory:
    history: DesignHistory
    anchored_length: int
    unanchored_attempts: int


def restore_design_history(events: Iterable[CampaignEvent], payload: Mapping[str, Any]) -> RestoredDesignMemory:
    """Rebuild ``payload`` (``DesignHistory.to_dict()``) and check it against the campaign's latest design anchor."""
    anchors = chain_anchors(events, CHAIN_KIND)
    if not anchors:
        raise DesignMemoryRefused("the campaign log anchors no design history; nothing establishes this memory is complete")
    history = DesignHistory.from_dict(payload)  # verifies every entry digest and the chain
    latest = anchors[-1]
    require_extends(history, latest)
    return RestoredDesignMemory(history, int(latest["length"]), len(history) - int(latest["length"]))


def save_design_history(path: str | os.PathLike[str], history: DesignHistory) -> str:
    """Write the history atomically (temp file + replace); returns its head."""
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(history.to_dict(), sort_keys=True), encoding="utf-8")
    os.replace(tmp, target)
    return history.head


def load_design_history(path: str | os.PathLike[str], events: Iterable[CampaignEvent]) -> RestoredDesignMemory:
    """Read a stored history and check it against the campaign's anchors (a missing file is refused, not empty)."""
    target = Path(path)
    if not target.exists():
        raise DesignMemoryRefused(f"no stored design history at {target}; an absent memory is not an empty one")
    return restore_design_history(events, json.loads(target.read_text(encoding="utf-8")))


__all__ = ["CHAIN_KIND", "DesignMemoryRefused", "RestoredDesignMemory", "anchor_design_history", "load_design_history",
           "require_extends", "restore_design_history", "save_design_history"]
