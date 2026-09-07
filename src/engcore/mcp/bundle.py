"""The evidence bundle: one directory a reader can check without the code.

Every element of this is already computed and already transported. A caller of
``run_electrothermal`` receives the problem it posed, the provenance of the run,
a validity assessment per contributing model, every validation check including
the ones that did not run, the levels those checks attained, the repair
alternatives for each violated condition, and an advisory verdict with the rules
that produced it. What has never existed is **one artefact a buyer can check**:
the response is a single JSON object that arrives over a transport, is read once
by whatever asked for it, and leaves nothing behind.

A bundle is that object written to a directory, split along the seams it already
has, with a manifest carrying a digest per file — and a :func:`verify_bundle`
that reads one back and says whether it still hangs together.

What is in a bundle
-------------------
=========================  ====================================================
``manifest.json``          every other file, its SHA-256 and its byte length
``run.json``               the spine: system, response schema, stage index
``case.json``              the payload as submitted, unaltered
``coupling.json``          the coupling record, or an explicit statement of
                           its absence
``stages/NN-<id>/``        one directory per stage, in the payload's order
``  report.json``          the credibility report, exactly as ``to_dict``
                           emitted it
``  verdict.json``         the verdict, its guidance, and the rules that fired
``  repairs.json``         the repair alternatives, as the domain produced them
``README.md``              what this directory is, and what it is not
=========================  ====================================================

Nothing is reformatted and nothing is summarised. Each JSON file is a verbatim
sub-object of the response, re-serialised with sorted keys so that a bundle
written twice from one response is byte-identical, and so a reader diffing two
bundles sees content rather than key order.

Nothing is duplicated either, and that is a decision rather than an economy. A
bundle carrying both the whole response and a split copy of it would have two
statements of the same fact, and a verifier would then owe an answer about what
to do when they disagree. The files partition the response; between them they
are it.

What a bundle deliberately omits
---------------------------------
**Anything not in the record today.** If the runtime does not compute it, the
bundle does not contain it, and the honest form of that is an absent or empty
field rather than a value derived at bundle time. ``provenance.environment`` is
the standing example: it is a declared field of every provenance record and this
system's runs leave it empty, so a bundle's ``report.json`` carries an empty
environment and a reader can see that nobody recorded one. Filling it in here —
with an interpreter version, a platform string, an installed package list — would
be inventing evidence at the moment of writing it down, attributed to a run that
never observed it.

**A signature, and any claim of tamper resistance.** The manifest detects a file
that changed *after* it was written, which is what a corrupted or truncated
transfer looks like and is what :func:`verify_bundle` is for. It detects nothing
about someone who edits a file and recomputes the manifest, because they can:
the digests are over the same directory they describe, and there is no key here
and no chain to anywhere. A bundle is a record you can check for damage, not a
record you can check for honesty.

**The bundle's own digest.** ``manifest.json`` lists every file except itself,
which is not an oversight — a file cannot contain its own SHA-256 — and is
stated in the manifest rather than left for a reader to notice.

A view, never a source
----------------------
Nothing in the runtime reads a bundle back. There is no path by which a bundle
becomes an input to a solve, a validity assessment or a verdict, and
``tests/mcp/test_bundle.py`` asserts that no runtime module imports this one. A
directory a user can edit must never be able to influence what the runtime
concludes; the moment it can, every guarantee in
:mod:`engcore.mcp.evidence` about verdicts being derived rather than asserted
is worth what the file system is worth.

:func:`verify_bundle` does load a report back, and that is not an exception to
the rule. It is a checker: it reads the bundle in order to *disagree* with it,
and it returns a finding rather than a scientific record. Nothing it produces
reaches a solve.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..scientific.serialization import require_schema, schema_string
from .errors import CredibilityEvidenceError
from .evidence import CredibilityEvidenceReport, CredibilityVerdict

__all__ = [
    "BUNDLE_MANIFEST_SCHEMA",
    "BUNDLE_RUN_SCHEMA",
    "BundleFinding",
    "BundleVerification",
    "verify_bundle",
    "write_bundle",
]

BUNDLE_MANIFEST_SCHEMA = schema_string("mcp_evidence_bundle_manifest")
BUNDLE_RUN_SCHEMA = schema_string("mcp_evidence_bundle_run")

DIGEST_ALGORITHM = "sha256"

_MANIFEST_NAME = "manifest.json"
_README_NAME = "README.md"


# =====================================================================
# Writing
# =====================================================================

def _canonical(payload: Any) -> bytes:
    """One JSON encoding, chosen once so two bundles of one response match.

    Sorted keys and a trailing newline. This is a *serialisation* choice and
    not a reformatting of content: every value written is the value the record
    produced, and no key is added, dropped or renamed on the way through.
    """
    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stage_directory(index: int, component_id: str) -> str:
    """``stages/00-R1``. The index keeps the payload's order on a sorted listing.

    The component id is used as given except for the separators a path cannot
    carry. A stage whose id collides with another's after that substitution
    would silently share a directory, so :func:`write_bundle` refuses it rather
    than writing one stage over the other.
    """
    safe = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in str(component_id)
    )
    return f"stages/{index:02d}-{safe}"


def write_bundle(
    response: Mapping[str, Any],
    directory: str | pathlib.Path,
    *,
    case: Mapping[str, Any] | None = None,
    bundle_id: str = "",
) -> pathlib.Path:
    """Write one run's record to ``directory`` and return the path.

    ``response`` is the transport's own output — the object
    :func:`engcore.mcp.server.run_electrothermal` returns — and is written as
    it is. ``case`` is the payload that produced it, carried so a reader can
    see what was asked as well as what came back; it is the caller's own JSON
    and is not validated here, because a bundle records what happened rather
    than re-deciding whether it should have.

    The directory must not already exist. A bundle is a snapshot of one run,
    and writing a second run into a directory that already holds one would
    leave a manifest describing a mixture of the two.
    """
    root = pathlib.Path(directory)
    if root.exists():
        raise CredibilityEvidenceError(
            f"{root} already exists; a bundle is one run's record and writing "
            f"into an existing directory would leave a manifest describing a "
            f"mixture of two runs. Choose a new path or remove this one"
        )
    stages = list(response.get("stages") or ())
    if not stages:
        raise CredibilityEvidenceError(
            "the response carries no stages, so there is no record to bundle; "
            "an empty bundle would assert that a run produced nothing rather "
            "than that nothing was handed to this function"
        )

    directories: dict[str, str] = {}
    for index, stage in enumerate(stages):
        component_id = str(stage.get("component_id", index))
        relative = _stage_directory(index, component_id)
        if relative in directories:
            raise CredibilityEvidenceError(
                f"stages {directories[relative]!r} and {component_id!r} both "
                f"map to {relative!r}; one would be written over the other"
            )
        directories[relative] = component_id

    files: dict[str, bytes] = {
        "case.json": _canonical(
            case
            if case is not None
            else {
                "note": (
                    "no case payload was supplied to the bundle writer; the "
                    "problem as posed is not recorded here"
                )
            }
        ),
        "coupling.json": _canonical(
            response.get("coupling")
            if response.get("coupling") is not None
            else {
                "note": (
                    "this run reports no coupling record; the response's "
                    "coupling field is null"
                )
            }
        ),
        "run.json": _canonical(
            {
                "schema": BUNDLE_RUN_SCHEMA,
                "response_schema": response.get("schema"),
                "system": response.get("system"),
                "stages": [
                    {
                        "index": index,
                        "component_id": directories[relative],
                        "directory": relative,
                        "run_id": (
                            stages[index].get("report", {}).get("run_id")
                        ),
                    }
                    for index, relative in enumerate(directories)
                ],
            }
        ),
    }
    for index, (relative, _component_id) in enumerate(directories.items()):
        stage = stages[index]
        files[f"{relative}/report.json"] = _canonical(stage.get("report", {}))
        files[f"{relative}/verdict.json"] = _canonical(stage.get("verdict", {}))
        files[f"{relative}/repairs.json"] = _canonical(
            stage.get("repairs") or []
        )

    files[_README_NAME] = _readme(response, directories).encode("utf-8")

    root.mkdir(parents=True)
    for relative, data in sorted(files.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    manifest = {
        "schema": BUNDLE_MANIFEST_SCHEMA,
        "bundle_id": str(bundle_id) or str(response.get("system", "run")),
        "written": _datetime.datetime.now().isoformat(timespec="seconds"),
        "digest_algorithm": DIGEST_ALGORITHM,
        # Said here rather than left for a reader to work out: a file cannot
        # carry its own digest, so the manifest is the one file in the bundle
        # nothing vouches for.
        "manifest_excludes_itself": True,
        "detects": (
            "a file changed, truncated or removed after this manifest was "
            "written. It does not detect an edit followed by a rewritten "
            "manifest: the digests are over the same directory they describe, "
            "and there is no signature here"
        ),
        "files": [
            {
                "path": relative,
                DIGEST_ALGORITHM: _digest(data),
                "bytes": len(data),
            }
            for relative, data in sorted(files.items())
        ],
    }
    (root / _MANIFEST_NAME).write_bytes(_canonical(manifest))
    return root


def _readme(
    response: Mapping[str, Any], directories: Mapping[str, str]
) -> str:
    """Prose for a reader who opens the directory before running anything."""
    listing = "\n".join(
        f"- `{relative}/` — stage `{component_id}`"
        for relative, component_id in directories.items()
    )
    return f"""# Evidence bundle — {response.get('system', 'run')}

One run of this scientific runtime, written as it was reported. Nothing in
here was computed at the time of writing: every file is a verbatim part of the
response the runtime produced, re-serialised with sorted keys so two bundles of
one run are byte-identical.

## What is here

- `manifest.json` — every other file with its {DIGEST_ALGORITHM} digest and byte
  length. It does not list itself; a file cannot carry its own digest.
- `run.json` — the system, the response schema, and the stage index.
- `case.json` — the payload as submitted.
- `coupling.json` — the coupling record, or a statement that there was none.
{listing}

Each stage directory holds `report.json` (the credibility report: values with
units, validity per contributing model with its satisfied, violated and unknown
conditions, every validation check including those that did not run, provenance,
and the caller's own asserted context under its `caller_asserted` marking),
`verdict.json` (the advisory verdict, what it means, and the rules that produced
it) and `repairs.json` (what would have to change for each violated condition,
as alternatives — never a plan, never a bound).

## What is not here

Anything the runtime does not record. `provenance.environment` is a declared
field that this system's runs leave empty; it is empty here too, rather than
filled in at bundle time with facts nobody observed during the run.

No signature, and no claim of tamper resistance. The manifest detects a file
that changed after it was written. It detects nothing about an edit followed by
a recomputed manifest.

## Checking it

```
python -m engcore.mcp.bundle verify <this directory>
```

It reports four independent things: whether every digest matches, whether any
file is present that the manifest does not list, whether each report still loads
through its schema, and whether each recorded verdict is the one its own report's
contents derive. It exits non-zero on any finding.

## What a verdict is

Advisory input to an engineer of record, not a decision. A `supported` verdict
says nothing in this record argues against relying on the result. It does not
say the result is right, and it discharges nobody's professional judgement.
"""


# =====================================================================
# Verifying
# =====================================================================

@dataclass(frozen=True)
class BundleFinding:
    """One reason a bundle is not what its manifest says it is."""

    category: str
    path: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.category}] {self.path}: {self.detail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "path": self.path,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BundleVerification:
    """What a verifier found, and what it managed to check.

    ``checked`` is reported alongside ``findings`` deliberately. A verifier that
    reported only findings would return the same empty answer for a bundle that
    passed every check and for a bundle whose checks never ran — and this
    project has three recorded instances of a guard that had never been seen to
    fail turning out to be incapable of failing. A reader can see how many
    digests were compared, how many reports were loaded and how many verdicts
    were re-derived, and notice when that number is zero.
    """

    root: str
    findings: tuple[BundleFinding, ...] = ()
    checked: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "checked", dict(self.checked))

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "ok": self.ok,
            "checked": dict(sorted(self.checked.items())),
            "findings": [f.to_dict() for f in self.findings],
        }

    def report(self) -> str:
        counts = ", ".join(
            f"{name} {count}" for name, count in sorted(self.checked.items())
        )
        head = f"bundle {self.root}\nchecked: {counts or 'nothing'}"
        if self.ok:
            return f"{head}\nVERIFIED: every check passed"
        lines = "\n".join(f"  {finding}" for finding in self.findings)
        return (
            f"{head}\nREFUSED: {len(self.findings)} finding(s)\n{lines}"
        )


def _bundle_files(root: pathlib.Path) -> set[str]:
    return {
        str(path.relative_to(root)).replace("\\", "/")
        for path in root.rglob("*")
        if path.is_file()
    }


def verify_bundle(directory: str | pathlib.Path) -> BundleVerification:
    """Read a bundle back and report whether it still hangs together.

    Four independent questions, and each can fail on its own:

    1. **Do the digests match?** Every file the manifest lists must exist and
       must hash to the digest recorded for it, at the byte length recorded
       for it.
    2. **Is anything here the manifest does not know about?** An added file is
       a finding too. A verifier that only checked what it was told to look at
       would pass a bundle with an extra `report.json` in it.
    3. **Does the schema load?** Each ``report.json`` is rebuilt through
       :meth:`CredibilityEvidenceReport.from_dict`, which refuses an unknown
       schema and recomputes the report's derived fields.
    4. **Is the verdict consistent with the contents it came from?** The
       verdict recorded in ``verdict.json`` must equal the verdict the loaded
       report *derives* from its own validity records and checks. This is the
       one that catches an edit inside a report that a digest would also have
       caught, and that survives a recomputed manifest.

    Findings accumulate; the verifier does not stop at the first. A reader
    fixing a damaged transfer wants the whole list.
    """
    root = pathlib.Path(directory)
    findings: list[BundleFinding] = []
    checked: dict[str, int] = {
        "digests": 0,
        "reports_loaded": 0,
        "verdicts_rederived": 0,
    }

    manifest_path = root / _MANIFEST_NAME
    if not manifest_path.is_file():
        return BundleVerification(
            root=str(root),
            findings=(
                BundleFinding(
                    "missing_manifest",
                    _MANIFEST_NAME,
                    "no manifest, so there is nothing to check the bundle "
                    "against; this is not an empty pass",
                ),
            ),
            checked=checked,
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require_schema(manifest, BUNDLE_MANIFEST_SCHEMA)
    except Exception as error:  # noqa: BLE001 - reported, never swallowed
        return BundleVerification(
            root=str(root),
            findings=(
                BundleFinding(
                    "unreadable_manifest", _MANIFEST_NAME, str(error)
                ),
            ),
            checked=checked,
        )

    # ---- 1. digests ---------------------------------------------------
    listed: set[str] = set()
    for entry in manifest.get("files", ()):
        relative = str(entry.get("path", ""))
        listed.add(relative)
        path = root / relative
        if not path.is_file():
            findings.append(
                BundleFinding(
                    "missing_file", relative, "listed in the manifest, absent"
                )
            )
            continue
        data = path.read_bytes()
        checked["digests"] += 1
        actual = _digest(data)
        expected = str(entry.get(DIGEST_ALGORITHM, ""))
        if actual != expected:
            findings.append(
                BundleFinding(
                    "digest_mismatch",
                    relative,
                    f"manifest records {DIGEST_ALGORITHM} {expected}, file "
                    f"hashes to {actual}",
                )
            )
        recorded_bytes = entry.get("bytes")
        if recorded_bytes is not None and int(recorded_bytes) != len(data):
            findings.append(
                BundleFinding(
                    "size_mismatch",
                    relative,
                    f"manifest records {recorded_bytes} bytes, file is "
                    f"{len(data)}",
                )
            )

    # ---- 2. files nobody listed ----------------------------------------
    for relative in sorted(_bundle_files(root) - listed - {_MANIFEST_NAME}):
        findings.append(
            BundleFinding(
                "unlisted_file",
                relative,
                "present in the bundle and absent from the manifest; a "
                "verifier that ignored it would pass a bundle with a second, "
                "unaccounted report in it",
            )
        )

    # ---- 3 and 4. the reports, and their verdicts ------------------------
    for relative in sorted(listed):
        if not relative.endswith("/report.json"):
            continue
        path = root / relative
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            report = CredibilityEvidenceReport.from_dict(payload)
        except Exception as error:  # noqa: BLE001 - reported, never swallowed
            findings.append(
                BundleFinding("unloadable_report", relative, str(error))
            )
            continue
        checked["reports_loaded"] += 1

        verdict_path = path.parent / "verdict.json"
        verdict_relative = relative.replace("report.json", "verdict.json")
        if not verdict_path.is_file():
            findings.append(
                BundleFinding(
                    "missing_verdict",
                    verdict_relative,
                    "a report with no recorded verdict beside it",
                )
            )
            continue
        try:
            recorded = json.loads(verdict_path.read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001
            findings.append(
                BundleFinding("unloadable_verdict", verdict_relative, str(error))
            )
            continue
        checked["verdicts_rederived"] += 1
        stated = recorded.get("value")
        derived = report.verdict.value
        if stated != derived:
            findings.append(
                BundleFinding(
                    "verdict_inconsistent",
                    verdict_relative,
                    f"the bundle records the verdict {stated!r}, but the "
                    f"contents of {relative} derive {derived!r}; a verdict "
                    f"describes the record it came from or it describes "
                    f"nothing",
                )
            )
        # The report's own embedded verdict is derived on access, so a payload
        # whose stored verdict disagreed with its contents would already have
        # been refused by `from_dict`. Checking the *sibling file* is the part
        # that record cannot do for itself.
        if stated is not None and stated not in {
            verdict.value for verdict in CredibilityVerdict
        }:
            findings.append(
                BundleFinding(
                    "unknown_verdict",
                    verdict_relative,
                    f"{stated!r} is not a verdict this platform issues",
                )
            )

    return BundleVerification(
        root=str(root), findings=tuple(findings), checked=checked
    )


# =====================================================================
# The command
# =====================================================================

def main(argv: Sequence[str] | None = None) -> int:
    """``python -m engcore.mcp.bundle verify <directory>``.

    Exits non-zero on any finding, so a bundle can be checked in a pipeline
    without anybody reading the output.
    """
    parser = argparse.ArgumentParser(
        prog="engcore.mcp.bundle",
        description="Write and check evidence bundles.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="check a bundle's integrity")
    verify.add_argument("directory", help="the bundle directory")
    verify.add_argument(
        "--json", action="store_true", help="emit the result as JSON"
    )

    # `write` takes a response that already exists rather than producing one.
    # Running a case is the transport's job and reaching for it here would give
    # this module a dependency on the optional server SDK -- and, worse, would
    # put a bundle writer inside the path that produces the thing it records.
    write = sub.add_parser(
        "write", help="write a bundle from a response this runtime produced"
    )
    write.add_argument("--response", required=True, help="the response JSON")
    write.add_argument("--case", help="the payload that produced it")
    write.add_argument("directory", help="the directory to create")

    args = parser.parse_args(argv)

    if args.command == "write":
        response = json.loads(
            pathlib.Path(args.response).read_text(encoding="utf-8")
        )
        case = (
            json.loads(pathlib.Path(args.case).read_text(encoding="utf-8"))
            if args.case
            else None
        )
        root = write_bundle(response, args.directory, case=case)
        print(f"wrote {root}")
        return 0

    result = verify_bundle(args.directory)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(result.report())
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
