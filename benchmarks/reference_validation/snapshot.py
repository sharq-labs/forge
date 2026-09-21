"""Content-addressed acquisition for external validation sources.

Live network data is never validation authority. Acquisition freezes bytes and
writes a manifest; later normalization reads that immutable snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from engcore.scientific.corpus import SourceSnapshot as CoreSnapshot

from .contracts import ReferenceSourceSpec

DEFAULT_MAX_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class SnapshotManifest:
    source_id: str
    source_version: str
    requested_url: str
    resolved_url: str
    retrieved_at_utc: str
    sha256: str
    byte_length: int
    content_type: str

    def core_snapshot(self) -> "CoreSnapshot":
        """The Core corpus record for these bytes.

        Acquisition happens here because the Scientific Core does not reach the
        network. Identity does not: the provenance chain a trust decision hangs
        off is one chain, and it is the Core one. The *resolved* URL is carried,
        not the requested one -- a redirect is where the bytes actually came
        from.
        """
        return CoreSnapshot(
            source_id=self.source_id,
            source_version=self.source_version,
            snapshot_sha256=self.sha256,
            snapshot_url=self.resolved_url,
            byte_length=self.byte_length,
            retrieved_at_utc=self.retrieved_at_utc,
            content_type=self.content_type,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "requested_url": self.requested_url,
            "resolved_url": self.resolved_url,
            "retrieved_at_utc": self.retrieved_at_utc,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SnapshotManifest":
        return cls(
            source_id=str(payload["source_id"]),
            source_version=str(payload["source_version"]),
            requested_url=str(payload["requested_url"]),
            resolved_url=str(payload["resolved_url"]),
            retrieved_at_utc=str(payload["retrieved_at_utc"]),
            sha256=str(payload["sha256"]),
            byte_length=int(payload["byte_length"]),
            content_type=str(payload.get("content_type", "")),
        )


def _allowed(url: str, source: ReferenceSourceSpec) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in source.allowed_hosts:
        raise ValueError(
            f"refusing acquisition from {url!r}; expected HTTPS host in {source.allowed_hosts}"
        )


def acquire_snapshot(
    source: ReferenceSourceSpec,
    url: str,
    destination_dir: str | os.PathLike[str],
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout_s: float = 60.0,
) -> tuple[Path, SnapshotManifest]:
    """Download once, hash bytes, and refuse silent replacement."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    _allowed(url, source)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ForgeReferenceValidation/1.0"},
        method="GET",
    )
    hasher = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        resolved = response.geturl()
        _allowed(resolved, source)
        content_type = str(response.headers.get("Content-Type", ""))
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"snapshot exceeds configured maximum of {max_bytes} bytes")
            hasher.update(chunk)
            chunks.append(chunk)

    digest = hasher.hexdigest()
    root = Path(destination_dir)
    root.mkdir(parents=True, exist_ok=True)
    data_path = root / f"{source.source_id}.{source.source_version}.{digest}.snapshot"
    manifest_path = data_path.with_suffix(data_path.suffix + ".manifest.json")
    if data_path.exists() or manifest_path.exists():
        raise FileExistsError(f"snapshot already exists; refusing replacement: {data_path}")

    payload = b"".join(chunks)
    data_path.write_bytes(payload)
    manifest = SnapshotManifest(
        source_id=source.source_id,
        source_version=source.source_version,
        requested_url=url,
        resolved_url=resolved,
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
        sha256=digest,
        byte_length=len(payload),
        content_type=content_type,
    )
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return data_path, manifest


def load_snapshot(
    data_path: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str] | None = None,
) -> tuple[bytes, SnapshotManifest]:
    path = Path(data_path)
    manifest_file = (
        Path(manifest_path)
        if manifest_path is not None
        else path.with_suffix(path.suffix + ".manifest.json")
    )
    manifest = SnapshotManifest.from_dict(
        json.loads(manifest_file.read_text(encoding="utf-8"))
    )
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != manifest.sha256:
        raise ValueError(f"snapshot digest mismatch: manifest={manifest.sha256}, actual={actual}")
    if len(payload) != manifest.byte_length:
        raise ValueError(
            f"snapshot length mismatch: manifest={manifest.byte_length}, actual={len(payload)}"
        )
    return payload, manifest


__all__ = ["DEFAULT_MAX_BYTES", "SnapshotManifest", "acquire_snapshot", "load_snapshot"]
