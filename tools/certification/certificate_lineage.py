"""Is this certificate child bound to its exact parent, and produced by that parent's certify run?

    python -m tools.certification.certificate_lineage verify-child [--merge-preview SHA]
    python -m tools.certification.certificate_lineage verify-provenance --repository OWNER/REPO

THE GAP THIS CLOSES
-------------------
``core_certificate --verify`` proves the certified BYTES equal the tree. It does
not prove the certificate is about THIS commit. A certificate built for an
older source whose certified files happen to be unchanged is byte-valid on any
later commit, and the reserved commit subject says nothing about who wrote the
file. So a certificate child -- the one commit allowed to skip the source
gates -- could carry a stale certificate, or one assembled by hand with a
``passed: true`` nobody measured, and every check it ran would pass.

``verify-child`` (offline, deterministic) requires, for ``HEAD`` checked out:

* **shape** -- exactly one parent; the only change is adding or modifying
  ``certification/current_core_v2.json``; the reserved subject;
* **parent binding** -- ``repository.commit``, ``assurance.source_commit``,
  ``assurance.environment.source_commit``, ``assurance.lineage.source_commit``
  and ``assurance.lineage.certificate_parent`` are all present and all equal to
  ``HEAD^``. Absent is a failure, not a pass;
* **the file** -- the working-tree certificate is byte-identical to the
  committed one, the checkout is byte-identical to ``HEAD``, the certificate is
  not diagnostic and was built from a clean tree;
* **content and scope** -- the stored certificate verifies against the tree AND
  was written under the current scope table, control plane included;
* **assurance** -- the ``forge.core_hardening_assurance/3`` record re-validates
  against the tree: the formal population and its exact shard coverage, the
  trust population, the functional gate evidence, the dependency manifest and
  the control-plane digest are all recomputed here, not read from the record;
* optionally, **merge preview** -- the commit the workflow executed carries the
  same certified bytes as the child.

``verify-provenance`` (online) then asks GitHub whether the run the certificate
names exists in this repository, ran the recertify workflow for ``HEAD^`` on a
pull request, finished every source gate and the certify job successfully, and
uploaded a certificate whose bytes are exactly the committed certificate. A
certificate that did not come out of that job cannot satisfy it, whatever it
says about itself.
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from tools.certification import core_certificate
from tools.certification.assert_clean_tree import TreeCheckError, tree_problems
from tools.certification.hardening_assurance import (
    WORKFLOW_PATH,
    AssuranceError,
    Policy,
    assurance_problems,
    executed_scope_problems,
)
from tools.certification.recertification_scope import (
    CERTIFICATE_PATH,
    RECERTIFY_SOURCE_GATES,
    OwnershipError,
    certificate_child_problems,
)

CERTIFICATE_ARTIFACT_MEMBER = "current_core_v2.json"
PROVENANCE_REQUIRED_JOBS = ("classify", *RECERTIFY_SOURCE_GATES, "certify")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Verification:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, bool(ok), detail))

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    def failed(self) -> list[str]:
        return [check.name for check in self.checks if not check.ok]

    def render(self) -> str:
        lines = [
            f"  {'PASS' if check.ok else 'FAIL'}  {check.name}"
            + (f" -- {check.detail}" if check.detail else "")
            for check in self.checks
        ]
        lines.append("OK" if self.ok else "FAILED")
        return "\n".join(lines)


def _git(root: pathlib.Path, *args: str) -> bytes:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if done.returncode != 0:
        raise OwnershipError(
            f"git {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace').strip()}"
        )
    return done.stdout


def _lookup(document: Mapping[str, Any], dotted: str) -> Any:
    value: Any = document
    for key in dotted.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


#: Every field that names the commit a certificate was measured on. Each must
#: be the child's one parent. Listed rather than discovered, so removing a
#: field from the record fails verification instead of shrinking it.
PARENT_BOUND_FIELDS = (
    "repository.commit",
    "assurance.source_commit",
    "assurance.environment.source_commit",
    "assurance.lineage.source_commit",
    "assurance.lineage.certificate_parent",
)


def verify_certificate_child(
    root: pathlib.Path,
    *,
    policy: Policy = Policy(),
    merge_preview: str | None = None,
) -> Verification:
    """Verify the checked-out ``HEAD`` as a certificate-only child. See the module docstring."""
    v = Verification()
    head = _git(root, "rev-parse", "HEAD").decode().strip()

    shape = certificate_child_problems(root, head)
    v.add("child.shape", not shape, "; ".join(shape))
    parents = _git(root, "rev-list", "--parents", "-n", "1", head).decode().split()[1:]
    parent = parents[0] if len(parents) == 1 else ""

    try:
        dirty = tree_problems(root)
        v.add("child.checkout_is_head", not dirty,
              ", ".join(d.render().strip() for d in dirty[:8]))
    except TreeCheckError as exc:
        v.add("child.checkout_is_head", False, str(exc))

    try:
        committed = _git(root, "show", f"{head}:{CERTIFICATE_PATH}")
    except OwnershipError as exc:
        v.add("certificate.committed", False, str(exc))
        return v
    on_disk = (root / CERTIFICATE_PATH).read_bytes() if (root / CERTIFICATE_PATH).is_file() else b""
    v.add("certificate.working_copy_is_committed_bytes", on_disk == committed)
    try:
        certificate = json.loads(committed)
    except json.JSONDecodeError as exc:
        v.add("certificate.parses", False, str(exc))
        return v

    for dotted in PARENT_BOUND_FIELDS:
        value = _lookup(certificate, dotted)
        v.add(
            f"parent_binding.{dotted}",
            bool(parent) and value == parent,
            f"records {value or '<absent>'}, parent is {parent or '<not exactly one>'}",
        )

    repository = certificate.get("repository") or {}
    v.add("certificate.built_from_clean_tree",
          repository.get("clean") is True and not certificate.get("diagnostic"))

    result = core_certificate.verify_certificate(
        root, certificate, require_clean=True, require_commit=False,
        require_current_scope=True,
    )
    v.add("certificate.content_and_scope", result.ok,
          "; ".join(result.problems[:4]) or ("" if result.ok else "certified bytes differ"))

    assurance = certificate.get("assurance") or {}
    if parent:
        problems = assurance_problems(
            root, assurance, source_commit=parent, certificate=certificate, policy=policy
        )
        v.add("assurance.revalidated_against_tree", not problems, "; ".join(problems[:6]))

    if merge_preview:
        problems = executed_scope_problems(root, merge_preview, head)
        v.add("merge_preview.certified_bytes", not problems, "; ".join(problems))
    return v


# ---------------------------------------------------------------------------
# provenance -- pure validation, then the GitHub fetch
# ---------------------------------------------------------------------------
def provenance_problems(
    *,
    certificate_bytes: bytes,
    source_commit: str,
    repository: str,
    run: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    artifact_certificate: bytes | None,
) -> list[str]:
    """Why the named run did not produce this certificate for ``source_commit``."""
    problems: list[str] = []
    lineage = _lookup(json.loads(certificate_bytes), "assurance.lineage") or {}
    run_id, attempt = lineage.get("workflow_run_id"), lineage.get("workflow_run_attempt")

    if run.get("id") != run_id:
        problems.append(f"GitHub returned run {run.get('id')} for recorded run {run_id}")
    if lineage.get("repository") != repository:
        problems.append(f"the certificate names repository {lineage.get('repository')!r}, this is {repository!r}")
    if (run.get("repository") or {}).get("full_name") != repository:
        problems.append(f"run {run_id} belongs to {(run.get('repository') or {}).get('full_name')!r}")
    if run.get("path") != WORKFLOW_PATH:
        problems.append(f"run {run_id} ran workflow {run.get('path')!r}, not {WORKFLOW_PATH}")
    if run.get("event") != "pull_request":
        problems.append(f"run {run_id} was triggered by {run.get('event')!r}, not pull_request")
    if run.get("head_sha") != source_commit:
        problems.append(f"run {run_id} measured {run.get('head_sha')}, not the certificate's parent {source_commit}")
    if not isinstance(attempt, int) or not isinstance(run.get("run_attempt"), int) or attempt > run["run_attempt"]:
        problems.append(f"recorded attempt {attempt} does not exist for run {run_id}")

    for name in PROVENANCE_REQUIRED_JOBS:
        matching = [job for job in jobs if job.get("name") == name]
        if len(matching) != 1:
            problems.append(f"run {run_id} attempt {attempt} has {len(matching)} job(s) named {name!r}")
            continue
        job = matching[0]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            problems.append(f"job {name!r} is {job.get('status')}/{job.get('conclusion')}, not completed/success")
        if job.get("head_sha") not in (None, source_commit):
            problems.append(f"job {name!r} ran on {job.get('head_sha')}")

    if artifact_certificate is None:
        problems.append("the certify job's certificate artifact was not found")
    elif artifact_certificate != certificate_bytes:
        problems.append("the committed certificate is not byte-identical to the one the certify job uploaded")
    return problems


def _gh(args: Sequence[str]) -> bytes:
    done = subprocess.run(["gh", "api", *args], capture_output=True)
    if done.returncode != 0:
        raise OwnershipError(f"gh api {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def fetch_and_verify_provenance(
    root: pathlib.Path,
    *,
    repository: str,
    timeout: float = 900.0,
    interval: float = 15.0,
    gh: Callable[[Sequence[str]], bytes] = _gh,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    parent = _git(root, "rev-parse", f"{head}^").decode().strip()
    certificate_bytes = _git(root, "show", f"{head}:{CERTIFICATE_PATH}")
    lineage = _lookup(json.loads(certificate_bytes), "assurance.lineage") or {}
    run_id, attempt = lineage.get("workflow_run_id"), lineage.get("workflow_run_attempt")
    if not isinstance(run_id, int) or not isinstance(attempt, int):
        return ["the certificate records no workflow run to check its provenance against"]

    base = f"repos/{repository}/actions/runs/{run_id}"
    run = json.loads(gh([base]))
    deadline = time.monotonic() + timeout
    while True:
        listing = json.loads(gh([f"{base}/attempts/{attempt}/jobs?per_page=100"]))
        jobs = listing.get("jobs") or []
        if listing.get("total_count", 0) > len(jobs):
            return [f"run {run_id} has more jobs than one page; refusing to judge a partial list"]
        certify = [job for job in jobs if job.get("name") == "certify"]
        if certify and all(job.get("status") == "completed" for job in certify):
            break
        if time.monotonic() >= deadline:
            break
        print(f"waiting for run {run_id} attempt {attempt}'s certify job to complete ...", flush=True)
        sleep(interval)

    artifact_name = f"hardened-core-assurance-{parent}"
    listing = json.loads(gh([f"{base}/artifacts?per_page=100&name={artifact_name}"]))
    artifacts = [a for a in listing.get("artifacts") or [] if a.get("name") == artifact_name and not a.get("expired")]
    artifact_certificate = None
    if len(artifacts) == 1:
        archive = zipfile.ZipFile(io.BytesIO(gh([f"repos/{repository}/actions/artifacts/{artifacts[0]['id']}/zip"])))
        if CERTIFICATE_ARTIFACT_MEMBER in archive.namelist():
            artifact_certificate = archive.read(CERTIFICATE_ARTIFACT_MEMBER)
    problems = provenance_problems(
        certificate_bytes=certificate_bytes, source_commit=parent, repository=repository,
        run=run, jobs=jobs, artifact_certificate=artifact_certificate,
    )
    if len(artifacts) > 1:
        problems.append(f"run {run_id} holds {len(artifacts)} artifacts named {artifact_name}")
    return problems


# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    child = commands.add_parser("verify-child")
    child.add_argument("--merge-preview")
    provenance = commands.add_parser("verify-provenance")
    provenance.add_argument("--repository", required=True)
    provenance.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args(argv)
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")

    try:
        if args.command == "verify-child":
            verification = verify_certificate_child(root, merge_preview=args.merge_preview)
            print(verification.render())
            return 0 if verification.ok else 1
        problems = fetch_and_verify_provenance(root, repository=args.repository, timeout=args.timeout)
    except (OwnershipError, AssuranceError) as exc:
        print(f"LINEAGE ERROR: {exc}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"PROVENANCE PROBLEM: {problem}")
    print("OK" if not problems else "FAILED")
    return 0 if not problems else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
