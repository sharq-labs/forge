"""A reproducible run bundle: the BIG 12 artifacts of one run, written once, verifiable byte for byte.

Contents (nothing is re-derived by a viewer; everything is a file with a recorded digest):

    request.json  plan.json  result.json  summary.json  summary.txt
    references/<id>.json      one per external / analytic reference used
    artifacts/<name>          bulk files (fields, series); NEVER inlined in the JSON above
    manifest.json             every file's sha256, the request / plan / result / summary identities

``verify_bundle`` re-hashes every file and then RE-DERIVES what the bundle already holds, so that an edit is refused even when the manifest
and every digest it states are regenerated to match:

* ``result.json`` and ``request.json`` through their own ``from_dict`` (each re-derives its digest); ``plan.json`` against the result's plan;
* the scientific status, by the existing credibility authority (``trust_handoff``), compared with ``summary.json``;
* ``summary.txt``, re-rendered from ``summary.json`` and compared byte for byte (and against the hash the summary states);
* key outputs, execution status and provider list of the summary against the result;
* level 1 of the ladder, re-derived from the result's own preflight report;
* every reference comparison, REBUILT from its shipped reference, criterion, conditions and value (applicability, tolerance outcome, kind
  and classification are derived, never read), and every ladder link that claims to be a comparison must be one of them, and every
  comparison must be cited by the ladder;
* every provider comparison (level 5): it must name two different providers whose executions the result recorded, carry a post-hoc flag that matches its
  classification and, for a purely absolute tolerance, an outcome that follows from its own maximum difference (a relative tolerance is judged per point and is refused);
* the uncertainty statement (its guards re-run; it may not be emptied while outputs are UNKNOWN) and the trace (re-derived from the result);
* the ladder itself, rebuilt with every guard, each evidence link's digest re-derived from the kind, classification, outcome and record it carries.

What this does NOT do: levels 2-4 evidence that is not a comparison (a conservation residual, a mesh or window study, an equilibrium
diagnostic) is a JUDGMENT the flagship recorded with its record; it cannot be re-derived from the bundle, and neither can the constraint and
conservation lines or the free-text notes.  The INPUTS of a reference comparison (the compared difference, the conditions, the tolerance, the
identity of what was compared) are stated by the flagship: the bundle re-derives what follows from them (outcome, applicability, kind,
classification) but not the inputs themselves. And the manifest is unkeyed: someone who consistently rewrites summary.json, summary.txt and the manifest together
produces a bundle that verifies.  Authenticity needs the ``bundle_digest`` recorded somewhere the bundle's author cannot edit (a commit, a
signed report).  A bundle is a record of a run; it is not evidence and it cannot raise a scientific status.
Files are written as bytes with LF line endings so digests are stable across platforms.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..scientific.errors import InvalidScientificProblem
from ..scenarios.timeline import canonical_digest
from ..system_runtime import NodeStatus, RunStatus, SystemRunRequest, SystemRunResult, trace_result, trust_handoff
from .ladder import VerificationLadder, check_provider_comparison, contract_integrity_entry
from .reference import ReferenceComparison, ReferenceRecord
from .summary import EngineeringSummary, UncertaintyStatement, _uncertainty_text, render_summary_text

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


def committed_artifacts(result: SystemRunResult, files: Mapping[str, bytes]) -> dict[str, bytes]:
    """The subset of ``files`` that a SUCCEEDED node's receipt references (same name AND same sha256).

    A node that was later REFUSED or FAILED may already have written a file into a side store; that file is not evidence of anything
    and must never travel in a run bundle."""
    allowed = {(a.name, a.digest) for r in result.node_receipts if r.status is NodeStatus.SUCCEEDED for a in r.artifacts}
    return {n: d for n, d in files.items() if (n, hashlib.sha256(d).hexdigest()) in allowed}


def write_bundle(directory: str, *, name: str, request: SystemRunRequest, result: SystemRunResult, summary: EngineeringSummary,
                 references: Sequence[ReferenceRecord] = (), artifacts: Mapping[str, bytes] | None = None) -> BundleManifest:
    if result.request_digest != request.digest or summary.to_dict()["identities"][2][1] != result.digest:
        raise BundleRefused("the request, result and summary of a bundle must describe one run")
    unbundled = {c.reference_digest for c in summary.comparisons} - {r.digest for r in references}
    if unbundled:
        raise BundleRefused(f"the summary's comparisons name references that are not supplied to the bundle: {sorted(unbundled)}")
    stray = sorted(set(artifacts or {}) - set(committed_artifacts(result, artifacts or {})))
    if stray:
        raise BundleRefused(f"artifacts {stray} are not referenced by any SUCCEEDED node of this run (a refused or failed node's side files are not bundled); use committed_artifacts()")
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
    if "bundle_digest" not in payload:
        raise BundleRefused("the manifest states no digest of itself")
    claimed = payload.pop("bundle_digest")
    if _sha(_json_bytes(payload)) != claimed:
        raise BundleRefused("the manifest does not match its own digest")
    files = {rel: digest for rel, digest in payload["files"]}
    for rel, digest in sorted(files.items()):
        try:
            with open(os.path.join(directory, *rel.split("/")), "rb") as fh:
                data = fh.read()
        except OSError as exc:
            raise BundleRefused(f"{rel} is named by the manifest but cannot be read: {exc}") from exc
        if _sha(data) != digest:
            raise BundleRefused(f"{rel} was changed after the bundle was written")
    on_disk = {rel for rel, _ in _walk(directory)} - {"manifest.json"}
    if on_disk != set(files):
        raise BundleRefused(f"files not in the manifest: {sorted(on_disk - set(files))}; missing: {sorted(set(files) - on_disk)}")
    try:
        with open(os.path.join(directory, "result.json"), "rb") as fh:
            result = SystemRunResult.from_dict(json.loads(fh.read().decode("utf-8")))
    except BundleRefused:
        raise
    except Exception as exc:
        raise BundleRefused(f"result.json does not load as a run result: {exc}") from exc
    if result.digest != payload["result_digest"] or result.request_digest != payload["request_digest"] or result.plan_digest != payload["plan_digest"]:
        raise BundleRefused("the result does not carry the identities the manifest states")
    # the rest of the bundle must agree with the result it claims to describe (a re-generated manifest is not enough)
    try:
        with open(os.path.join(directory, "request.json"), "rb") as fh:
            request = SystemRunRequest.from_dict(json.loads(fh.read().decode("utf-8")))
    except Exception as exc:
        raise BundleRefused(f"request.json does not load as a run request: {exc}") from exc
    if request.digest != payload["request_digest"] or request.digest != result.request_digest:
        raise BundleRefused("request.json is not the request this result was produced for")
    with open(os.path.join(directory, "plan.json"), "rb") as fh:
        if canonical_digest(json.loads(fh.read().decode("utf-8"))) != canonical_digest(result.plan.to_dict()):
            raise BundleRefused("plan.json is not the plan of this result")
    try:
        return _verify_rest(directory, payload, files, result, request)
    except BundleRefused:
        raise
    except Exception as exc:                # any other failure to re-derive is a refusal, never a crash and never a pass
        raise BundleRefused(f"the bundle does not re-derive: {exc!r}") from exc


def _verify_rest(directory: str, payload: dict, files: Mapping[str, str], result: SystemRunResult, request: SystemRunRequest) -> BundleManifest:
    def read(rel: str) -> bytes:
        with open(os.path.join(directory, *rel.split("/")), "rb") as fh:
            return fh.read()

    summary = json.loads(read("summary.json").decode("utf-8"))
    if canonical_digest(summary) != payload["summary_digest"] or dict(map(tuple, summary["identities"])).get("result") != result.digest:
        raise BundleRefused("summary.json is not the summary the manifest names, or it describes another run")
    identities = dict(map(tuple, summary["identities"]))
    if identities.get("request") != request.digest or identities.get("plan") != result.plan_digest:
        raise BundleRefused("summary.json describes another request or plan")
    try:
        verdict = trust_handoff(result, request, allow_partial=result.status is not RunStatus.SUCCEEDED).verdict.value
    except Exception as exc:  # the existing authority refused: the summary's status cannot be re-derived
        raise BundleRefused(f"the scientific status cannot be re-derived from the bundled request and result: {exc}") from exc
    if summary["scientific_status"] != verdict:
        raise BundleRefused(f"summary.json states scientific status {summary['scientific_status']!r} but the existing credibility authority derives {verdict!r}")
    # the text is rendered from the record: the two cannot disagree, and neither can be edited alone
    text = read("summary.txt")
    core = {k: v for k, v in summary.items() if k != "text_sha256"}
    if text != render_summary_text(core).encode("utf-8") or _sha(text) != summary.get("text_sha256"):
        raise BundleRefused("summary.txt is not the text rendered from summary.json")
    # what the summary states about the run must be what the result says
    if summary["execution"] != result.status.value:
        raise BundleRefused("summary.json states another execution status than the result")
    if sorted(summary["providers"]) != sorted({f"{p.provider_id} {p.provider_version}" for p in result.provider_records}):
        raise BundleRefused("summary.json lists other providers than the result executed")
    if sorted(payload["provider_identities"]) != sorted({p.execution_identity_digest for p in result.provider_records}):
        raise BundleRefused("the manifest lists other provider identities than the result recorded")
    for key in summary["key_outputs"]:
        observed = result.observable(key["observable_id"])
        if observed.availability.value == "available":
            if key["availability"] != "available" or key["value"] != json.loads(json.dumps(observed.value.value.to_dict())) or key["uncertainty"] != _uncertainty_text(observed.value):
                raise BundleRefused(f"key output {key['observable_id']!r} is not the value the result recorded")
        elif key["availability"] != observed.availability.value or key["value"] is not None:
            raise BundleRefused(f"key output {key['observable_id']!r} states a value for an output the result did not make available")
    # the ladder: every guard re-runs, every link re-derives its digest, level 1 is re-derived from the result's own preflight
    try:
        ladder = VerificationLadder.from_dict(summary["verification"])
    except (InvalidScientificProblem, KeyError, ValueError, TypeError) as exc:
        raise BundleRefused(f"the summary's verification ladder does not re-validate: {exc}") from exc
    recorded_identities = {p.execution_identity_digest for p in result.provider_records}
    for entry in ladder.entries:
        for link in entry.evidence:
            if link.kind == "provider_comparison":
                try:
                    check_provider_comparison(link.record, recorded_identities)
                except InvalidScientificProblem as exc:
                    raise BundleRefused(f"level {entry.level}: {exc}") from exc
    # the uncertainty statement re-runs its own guards, and may not be emptied while outputs are UNKNOWN; the trace is re-derived
    uncertainty = summary["uncertainty"]
    try:
        statement = UncertaintyStatement(tuple(uncertainty["known_input_uncertainty"]), tuple(uncertainty["unknown_input_uncertainty"]), uncertainty["model_discrepancy"],
                                         tuple(uncertainty["material_provenance"]), uncertainty["model_applicability"], uncertainty["benchmark_applicability"])
    except InvalidScientificProblem as exc:
        raise BundleRefused(f"the summary's uncertainty statement does not re-validate: {exc}") from exc
    if result.trust_inputs.unknown_uncertainty_outputs and not statement.unknown_input_uncertainty:
        raise BundleRefused("outputs with UNKNOWN uncertainty exist, but the summary names no UNKNOWN input uncertainty")
    traced = trace_result(result, summary["trace_observable"])
    if summary["trace"] != {"complete": traced.complete, "gaps": list(traced.gaps)}:
        raise BundleRefused("the summary's trace is not the trace the result derives")
    expected_l1 = json.loads(json.dumps(contract_integrity_entry(result.preflight, result).to_dict()))
    if canonical_digest(summary["verification"]["levels"][0]) != canonical_digest(expected_l1):
        raise BundleRefused("level 1 is not what the result's own preflight report and status derive")
    # references and comparisons: rebuilt from what is shipped
    references: dict[str, ReferenceRecord] = {}
    for ref_id, digest in payload["reference_digests"]:
        record = json.loads(read(f"references/{ref_id}.json").decode("utf-8"))
        if canonical_digest(record) != digest or record.get("reference_id") != ref_id:
            raise BundleRefused(f"reference {ref_id!r} does not have the digest the manifest names")
        try:
            references[digest] = ReferenceRecord.from_dict(record)
        except (InvalidScientificProblem, KeyError, ValueError, TypeError) as exc:
            raise BundleRefused(f"reference {ref_id!r} does not re-validate: {exc}") from exc
    rebuilt: set[str] = set()
    for cmp_record in summary["reference_comparisons"]:
        reference = references.get(cmp_record["reference_digest"])
        if reference is None:
            raise BundleRefused(f"comparison {cmp_record['criterion']['criterion_id']!r} names a reference that is not in the bundle")
        try:
            ReferenceComparison.from_dict(cmp_record, reference)
        except (InvalidScientificProblem, KeyError, ValueError, TypeError) as exc:
            raise BundleRefused(f"comparison {cmp_record['criterion']['criterion_id']!r} is not what its bundled reference and stated inputs derive: {exc}") from exc
        rebuilt.add(canonical_digest(cmp_record))
    cited: set[str] = set()
    for entry in ladder.entries:
        for link in entry.evidence:
            if link.kind == "reference_comparison":
                if link.record_digest not in rebuilt:
                    raise BundleRefused(f"level {entry.level} cites a reference comparison that is not among the summary's comparisons")
                cited.add(link.record_digest)
    if rebuilt - cited:
        raise BundleRefused("a reference comparison is reported but no ladder level cites it")
    allowed = {(a.name, a.digest) for r in result.node_receipts if r.status is NodeStatus.SUCCEEDED for a in r.artifacts}
    for rel in files:
        if rel.startswith("artifacts/"):
            if (rel.split("/", 1)[1], _sha(read(rel))) not in allowed:
                raise BundleRefused(f"{rel} is not an artifact referenced (name and sha256) by a SUCCEEDED node of the result")
    return BundleManifest(payload["name"], tuple(tuple(f) for f in payload["files"]), payload["request_digest"], payload["plan_digest"],
                          payload["result_digest"], payload["summary_digest"], tuple(tuple(r) for r in payload["reference_digests"]),
                          tuple(payload["provider_identities"]))


def _walk(directory: str):
    for root, _, names in os.walk(directory):
        for n in names:
            full = os.path.join(root, n)
            yield os.path.relpath(full, directory).replace(os.sep, "/"), full
