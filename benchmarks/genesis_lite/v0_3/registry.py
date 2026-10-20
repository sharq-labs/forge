"""Genesis-lite v0.3 DRAFT: one attempt per root, enforced by a durable operator-side registry.

A root's commitment (sha256 of the root; never the root itself) is ADMITTED to the registry before the first world of
an attempt is derived. A formal root is consumed by its first admission, whatever happens afterwards (crash, abort,
refusal), so:

* a second formal attempt with the same root is refused, after a restart too;
* the key is the root commitment, not an output directory or a run label, so copying an output directory or renaming
  the run changes nothing;
* a root admitted under ANY preregistration identity is refused under every other one;
* a root that any committed preregistration names (pilot roots, revealed with their results) is refused for the formal
  tier (``formal.retired_root_commitments``, checked by the caller);
* DEVELOPMENT roots are recorded separately (tier ``development``). They may be re-used for development, but a root
  ever seen in development can never be admitted formally, and a formal root can never be used for development.

The registry is one append-only JSON-lines file in an operator-only directory OUTSIDE every run directory. Each line
carries the sha256 of the previous line and its own digest. Every entry carries a random NONCE and the admission time,
so two admissions are never identical, and the formal masters mix in the nonce (``formal.master_for``): a second
attempt, even through a fresh registry, can neither reproduce the first attempt's identity nor replay its worlds.
Admission takes an exclusive lock file created with O_EXCL. A lock left by a crash is never broken automatically: the
registry refuses until the operator removes it after inspection, which fails closed.

This module cannot stop an operator from deleting the registry or starting a fresh one. What makes that visible is
outside the operator's control: the formal driver PUBLISHES each admission to the external evaluator (OD-8) before the
first world is derived, and the evaluator refuses a second admission of one root commitment.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets
from typing import Any, Mapping

REGISTRY_SCHEMA = "forge.genesis_lite.attempt_registry/1"
TIERS = ("formal", "development")
_GENESIS = "0" * 64


class AttemptRefused(RuntimeError):
    """An attempt may not start under this root, identity and tier."""


class AttemptRegistry:
    def __init__(self, directory: pathlib.Path) -> None:
        self._dir = pathlib.Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.path = self._dir / "attempts.jsonl"
        self._lock = self._dir / "attempts.lock"

    def entries(self) -> list[dict[str, Any]]:
        """Every admitted attempt, after checking the whole chain (refuses a broken one)."""
        if not self.path.exists():
            return []
        prev, out = _GENESIS, []
        for n, line in enumerate(self.path.read_bytes().splitlines(), start=1):
            row = json.loads(line)
            if row.get("prev_sha256") != prev or row.get("schema") != REGISTRY_SCHEMA \
                    or row.get("attempt_sha256") != entry_digest(row):
                raise AttemptRefused(f"the attempt registry is broken at line {n}: refusing every admission")
            prev = hashlib.sha256(line).hexdigest()
            out.append(row)
        return out

    def head(self) -> str:
        if not self.path.exists():
            return _GENESIS
        lines = self.path.read_bytes().splitlines()
        self.entries()
        return hashlib.sha256(lines[-1]).hexdigest() if lines else _GENESIS

    def admit(self, *, root_commitment_sha256: str, prereg_sha256: str, campaign_set_sha256: str, tier: str,
              attempt_label: str = "") -> dict[str, Any]:
        """Record one attempt and return its entry, or refuse. Call BEFORE any world of the attempt is derived."""
        if tier not in TIERS:
            raise AttemptRefused(f"unknown tier {tier!r}")
        for name, value in (("root commitment", root_commitment_sha256), ("preregistration", prereg_sha256),
                            ("campaign set", campaign_set_sha256)):
            if not (isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)):
                raise AttemptRefused(f"the {name} is a sha256 hex digest")
        try:
            fd = os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise AttemptRefused(f"the registry is locked ({self._lock}); a lock left by a crash is removed by the "
                                 f"operator after inspection, never automatically") from None
        try:
            os.close(fd)
            seen = [e for e in self.entries() if e["root_commitment_sha256"] == root_commitment_sha256]
            if tier == "formal" and seen:
                raise AttemptRefused(f"this root was already admitted ({seen[0]['tier']}, attempt "
                                     f"{seen[0]['attempt_sha256'][:12]}...): one formal attempt per root")
            if tier == "development" and any(e["tier"] == "formal" for e in seen):
                raise AttemptRefused("this root is a formal root; it is never used for development")
            entry = {"schema": REGISTRY_SCHEMA, "prev_sha256": self.head(), "tier": tier,
                     "root_commitment_sha256": root_commitment_sha256, "prereg_sha256": prereg_sha256,
                     "campaign_set_sha256": campaign_set_sha256, "attempt_label": str(attempt_label),
                     "nonce": secrets.token_hex(16),
                     "admitted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
            entry["attempt_sha256"] = entry_digest(entry)
            line = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            with open(self.path, "ab") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            return entry
        finally:
            self._lock.unlink(missing_ok=True)


def entry_digest(entry: Mapping[str, Any]) -> str:
    """An entry's own digest: sha256 of every field except ``attempt_sha256``."""
    body = {k: v for k, v in entry.items() if k != "attempt_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class EvaluatorInbox:
    """The EXTERNAL evaluator's append-only record of the admissions it received (OD-8). It accepts a formal admission
    only if no admission of the same root commitment arrived before; ``first_admission`` is what
    ``formal.verify_attempt`` accepts. It runs on the evaluator's side; the operator cannot rewrite it."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = pathlib.Path(path)

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return [json.loads(line) for line in self.path.read_bytes().splitlines() if line.strip()]
        except ValueError as exc:
            raise AttemptRefused("the evaluator inbox is corrupt: refusing every admission") from exc

    def _append(self, row: Mapping[str, Any]) -> None:
        lock = self.path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise AttemptRefused(f"the evaluator inbox is locked ({lock})") from None
        try:
            os.close(fd)
            with open(self.path, "ab") as fh:
                fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n")
                fh.flush()
                os.fsync(fh.fileno())
        finally:
            lock.unlink(missing_ok=True)

    def receive(self, entry: Mapping[str, Any]) -> None:
        if entry.get("schema") != REGISTRY_SCHEMA or entry_digest(entry) != entry.get("attempt_sha256"):
            raise AttemptRefused("not a well-formed admission")
        if entry.get("tier") == "formal" and self.first_admission(str(entry["root_commitment_sha256"])) is not None:
            self._append({"refused_second_admission": dict(entry)})   # kept as evidence, never accepted
            raise AttemptRefused("the evaluator already received an admission of this root: one formal attempt per root")
        self._append({"admission": dict(entry)})

    def receive_heads(self, attempt_sha256: str, *, run_log: str, registry: str) -> None:
        """The final run-log and registry heads of an admitted attempt, once."""
        if not any(isinstance(r.get("admission"), Mapping) and r["admission"].get("attempt_sha256") == attempt_sha256
                   for r in self._rows()):
            raise AttemptRefused("heads for an attempt the evaluator never admitted")
        if self.published_heads(attempt_sha256) is not None:
            raise AttemptRefused("this attempt's heads were already published")
        self._append({"heads": {"attempt_sha256": attempt_sha256, "run_log": run_log, "registry": registry}})

    def published_heads(self, attempt_sha256: str) -> dict[str, Any] | None:
        for row in self._rows():
            heads = row.get("heads")
            if isinstance(heads, Mapping) and heads.get("attempt_sha256") == attempt_sha256:
                return dict(heads)
        return None

    def first_admission(self, root_commitment_sha256: str) -> dict[str, Any] | None:
        for row in self._rows():
            entry = row.get("admission")
            if isinstance(entry, Mapping) and entry.get("root_commitment_sha256") == root_commitment_sha256:
                return dict(entry)
        return None


def campaign_set_sha256(world_sets: Any) -> str:
    """The digest of the world-set plan an attempt covers (order-independent)."""
    return hashlib.sha256(json.dumps(sorted(list(w) for w in world_sets)).encode()).hexdigest()


def describe(entry: Mapping[str, Any]) -> str:
    return f"{entry['tier']} attempt {entry['attempt_sha256'][:12]}... on root {entry['root_commitment_sha256'][:12]}..."
