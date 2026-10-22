"""Sealing, verifying and writing receipts. A sealed receipt is immutable: any edit is detectable.

The seal is a SHA-256 over the canonical JSON of the whole receipt, including who sealed it, with
only the digest itself left out. A receipt edited and re-sealed is self-consistent again, which is
why the ledger keeps every digest it indexed (``Ledger.verify_receipt``): the receipt file is the
canonical record, the index is the witness.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import uuid

from tools.run_observatory.identity import canonical_json, sha256_json

ALGORITHM = "sha256"
CANONICALIZATION = "json-sort_keys-compact-ascii-v1"
SEALERS = ("RUNNER", "RECOVERY")


def seal(body: dict, *, sealed_by: str = "RUNNER") -> dict:
    if sealed_by not in SEALERS:
        raise ValueError(f"unknown sealer {sealed_by!r}")
    sealed = {k: v for k, v in copy.deepcopy(body).items() if k != "integrity"}
    sealed["integrity"] = {"algorithm": ALGORITHM, "canonicalization": CANONICALIZATION, "sealed_by": sealed_by}
    canonical_json(sealed)  # refuses NaN / infinity before anything is written
    sealed["integrity"]["receipt_sha256"] = sha256_json(sealed)
    return sealed


def digest_of(receipt: dict) -> str | None:
    try:
        return receipt["integrity"]["receipt_sha256"]
    except (KeyError, TypeError):
        return None


def verify(receipt: dict) -> bool:
    """Whether the receipt still matches its own seal."""
    try:
        claimed = receipt["integrity"]["receipt_sha256"]
        content = copy.deepcopy(receipt)
        del content["integrity"]["receipt_sha256"]
        integrity = content["integrity"]
        if integrity.get("algorithm") != ALGORITHM or integrity.get("canonicalization") != CANONICALIZATION:
            return False
        return sha256_json(content) == claimed
    except (KeyError, TypeError, ValueError):
        return False


def _temp_beside(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")


def _write_temp(path: Path, text: str) -> Path:
    tmp = _temp_beside(path)
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    return tmp


def write_sealed(path: Path, receipt: dict) -> None:
    """Write a sealed receipt atomically, never over an existing one, and mark it read-only.

    A hard link publishes the complete file under its final name and fails if that name exists,
    so two writers can never interleave and a finished receipt can never be replaced.
    """
    if not verify(receipt):
        raise ValueError("refusing to write a receipt that does not verify")
    path = Path(path)
    tmp = _write_temp(path, json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    try:
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise
        except OSError:  # a filesystem without hard links: check, then rename
            if path.exists():
                raise FileExistsError(str(path)) from None
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        os.chmod(path, 0o444)
    except OSError:
        pass


def write_replace(path: Path, payload: dict) -> None:
    """Atomically replace a mutable file (a pending receipt while its run is still going)."""
    path = Path(path)
    tmp = _write_temp(path, json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def create_once(path: Path, data: bytes) -> bytes:
    """Create ``path`` with ``data`` unless it exists; either way return its complete contents."""
    path = Path(path)
    if not path.exists():
        tmp = _temp_beside(path)
        tmp.write_bytes(data)
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
        except OSError:
            if not path.exists():
                os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return path.read_bytes()
