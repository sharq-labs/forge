"""A reproducible run bundle: the BIG 12 artifacts of one run, written once, verifiable byte for byte.

Contents (nothing is re-derived by a viewer; everything is a file with a recorded digest):

    request.json  plan.json  result.json  summary.json  summary.txt
    references/<id>.json      one per external / analytic reference used
    artifacts/<name>          bulk files (fields, series); NEVER inlined in the JSON above
    manifest.json             every file's sha256, the request / plan / result / summary identities

``verify_bundle`` re-hashes every file and re-loads ``result.json`` through ``SystemRunResult.from_dict``,
which re-derives its own digest, so a bundle edited after the fact - a value, a receipt, a reference - is
refused.  A bundle is a record of a run; it is not evidence and it cannot raise a scientific status.
Files are written as bytes with LF line endings so digests are stable across platforms.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..scientific.errors import InvalidScientificProblem
from ..system_runtime import SystemRunRequest, SystemRunResult
from .reference import ReferenceRecord
from .summary import EngineeringSummary

MANIFEST_SCHEMA = "engcore.engineering.bundle/1"


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class BundleRefused(InvalidScientificProblem):
    """A bundle does not verify."""


@dataclass(frozen=True)
class BundleManifest:
    name: str
    files: tuple[tuple[str, str], ...]
    request_digest: str
    plan_digest: str
    result_digest: str
    summary_digest: str
    reference_digests: tuple[tuple[str, str], ...]
    provider_identities: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        core = {"schema": MANIFEST_SCHEMA, "name": self.name, "files": [list(f) for f in self.files], "request_digest": self.request_digest,
                "plan_digest": self.plan_digest, "result_digest": self.result_digest, "summary_digest": self.summary_digest,
                "reference_digests": [list(r) for r in self.reference_digests], "provider_identities": list(self.provider_identities)}
        core["bundle_digest"] = _sha(_json_bytes(core))
        return core

    @property
    def digest(self) -> str:
        return self.to_dict()["bundle_digest"]


def write_bundle(directory: str, *, name: str, request: SystemRunRequest, result: SystemRunResult, summary: EngineeringSummary,
                 references: Sequence[ReferenceRecord] = (), artifacts: Mapping[str, bytes] | None = None) -> BundleManifest:
    if result.request_digest != request.digest or summary.to_dict()["identities"][2][1] != result.digest:
        raise BundleRefused("the request, result and summary of a bundle must describe one run")
    files: dict[str, bytes] = {
        "request.json": _json_bytes(request.to_dict()), "plan.json": _json_bytes(result.plan.to_dict()), "result.json": _json_bytes(result.to_dict()),
        "summary.json": _json_bytes(summary.to_dict()), "summary.txt": summary.render_text().encode("utf-8"),
    }
    for ref in references:
        files[f"references/{ref.reference_id}.json"] = _json_bytes(ref.to_dict())
    for artifact_name, data in sorted((artifacts or {}).items()):
        if "/" in artifact_name or artifact_name.startswith("."):
            raise BundleRefused(f"artifact name {artifact_name!r} must be a plain file name")
        files[f"artifacts/{artifact_name}"] = bytes(data)
    os.makedirs(directory, exist_ok=True)
    for rel, data in files.items():
        path = os.path.join(directory, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    manifest = BundleManifest(name, tuple(sorted((rel, _sha(data)) for rel, data in files.items())), request.digest, result.plan_digest, result.digest,
                              summary.digest, tuple(sorted((r.reference_id, r.digest) for r in references)),
                              tuple(sorted({p.execution_identity_digest for p in result.provider_records})))
    with open(os.path.join(directory, "manifest.json"), "wb") as fh:
        fh.write(_json_bytes(manifest.to_dict()))
    return manifest


def verify_bundle(directory: str) -> BundleManifest:
    """Re-hash every file and re-derive the result identity; raise :class:`BundleRefused` on any difference."""
    with open(os.path.join(directory, "manifest.json"), "rb") as fh:
        payload = json.loads(fh.read().decode("utf-8"))
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise BundleRefused("not a Forge run bundle manifest")
    claimed = payload.pop("bundle_digest")
    if _sha(_json_bytes(payload)) != claimed:
        raise BundleRefused("the manifest does not match its own digest")
    files = {rel: digest for rel, digest in payload["files"]}
    for rel, digest in sorted(files.items()):
        with open(os.path.join(directory, *rel.split("/")), "rb") as fh:
            if _sha(fh.read()) != digest:
                raise BundleRefused(f"{rel} was changed after the bundle was written")
    on_disk = {rel for rel, _ in _walk(directory)} - {"manifest.json"}
    if on_disk != set(files):
        raise BundleRefused(f"files not in the manifest: {sorted(on_disk - set(files))}; missing: {sorted(set(files) - on_disk)}")
    with open(os.path.join(directory, "result.json"), "rb") as fh:
        result = SystemRunResult.from_dict(json.loads(fh.read().decode("utf-8")))
    if result.digest != payload["result_digest"] or result.request_digest != payload["request_digest"] or result.plan_digest != payload["plan_digest"]:
        raise BundleRefused("the result does not carry the identities the manifest states")
    return BundleManifest(payload["name"], tuple(tuple(f) for f in payload["files"]), payload["request_digest"], payload["plan_digest"],
                          payload["result_digest"], payload["summary_digest"], tuple(tuple(r) for r in payload["reference_digests"]),
                          tuple(payload["provider_identities"]))


def _walk(directory: str):
    for root, _, names in os.walk(directory):
        for n in names:
            full = os.path.join(root, n)
            yield os.path.relpath(full, directory).replace(os.sep, "/"), full
