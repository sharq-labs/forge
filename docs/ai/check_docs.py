#!/usr/bin/env python3
"""Bounded, stdlib-only, read-only syntax checks for FORGE's opted-in AI Markdown.

Not scientific validation, certificate authority, an exhaustive repository audit,
or evidence that a GitHub PR is mergeable. See docs/ai/DOCUMENT_SCHEMA.md.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOCSET = ROOT / "docs/ai/DOCSET.txt"

FIELDS = (
    "ai_schema_version",
    "doc_id",
    "doc_kind",
    "doc_status",
    "authority_scope",
    "source_ref",
    "evidence_level",
    "last_reviewed",
    "supersedes",
)
ENUMS = {
    "doc_kind": {
        "POLICY_GUIDE", "CONTEXT_INDEX", "SNAPSHOT", "DECISION_INDEX",
        "AUDIT_HANDOFF", "SCIENTIFIC_DESIGN", "EVIDENCE_REPORT",
    },
    "doc_status": {"ACTIVE", "PROPOSED", "SNAPSHOT", "SUPERSEDED", "ARCHIVED"},
    "authority_scope": {"NONE"},
    "evidence_level": {
        "NOT_EVIDENCE", "DERIVED", "REPORTED", "STATIC_REVIEW",
        "EXECUTED_BOUNDED", "MIXED",
    },
}
ID_RE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")


def _in_repo(path: Path) -> bool:
    return path.is_relative_to(ROOT)


def _manifest() -> tuple[list[Path], list[str]]:
    errors: list[str] = []
    if not DOCSET.is_file():
        return [], ["missing docs/ai/DOCSET.txt"]
    selected: list[Path] = []
    seen: set[Path] = set()
    for number, line in enumerate(DOCSET.read_text(encoding="utf-8").splitlines(), 1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if not raw.endswith(".md") or raw.startswith("/") or "\\" in raw:
            errors.append(f"DOCSET:{number}: expected relative .md file: {raw!r}")
            continue
        full = (ROOT / raw).resolve()
        if not _in_repo(full):
            errors.append(f"DOCSET:{number}: path escapes repository: {raw!r}")
        elif full in seen:
            errors.append(f"DOCSET:{number}: duplicate: {raw}")
        elif not full.is_file():
            errors.append(f"DOCSET:{number}: missing document: {raw}")
        else:
            seen.add(full)
            selected.append(full)
    if not selected:
        errors.append("DOCSET: no valid AI documents selected")
    return selected, errors


def _frontmatter(path: Path, body: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    lines = body.splitlines()
    display = path.relative_to(ROOT).as_posix()
    if not lines or lines[0] != "---":
        return {}, [f"{display}: expected metadata front matter on first line"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, [f"{display}: missing closing front matter marker"]
    if end < 2:
        errors.append(f"{display}: empty front matter")
    meta: dict[str, str] = {}
    for no, line in enumerate(lines[1:end], 2):
        if not line or ":" not in line or line[0].isspace():
            errors.append(f"{display}:{no}: expected 'key: scalar' (no YAML nesting)")
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if not key or key.strip() != key or not value:
            errors.append(f"{display}:{no}: invalid key or empty value")
        elif key in meta:
            errors.append(f"{display}:{no}: duplicate field {key}")
        elif any(mark in value for mark in ('"', "'", "[", "]", "{", "}")):
            errors.append(f"{display}:{no}: v1 fields are unquoted scalars")
        else:
            meta[key] = value
    for field in FIELDS:
        if field not in meta:
            errors.append(f"{display}: required field missing: {field}")
    for field in meta:
        if field not in FIELDS:
            errors.append(f"{display}: unexpected metadata field: {field}")
    if meta.get("ai_schema_version") not in (None, "1"):
        errors.append(f"{display}: unsupported schema version")
    if "doc_id" in meta and not ID_RE.fullmatch(meta["doc_id"]):
        errors.append(f"{display}: invalid doc_id")
    for key, allowed in ENUMS.items():
        if key in meta and meta[key] not in allowed:
            errors.append(f"{display}: invalid {key}={meta[key]!r}")
    source = meta.get("source_ref")
    if source and source not in {"not-applicable", "multiple"} and not SHA_RE.fullmatch(source):
        errors.append(f"{display}: source_ref must be a full SHA, multiple or not-applicable")
    old = meta.get("supersedes")
    if old and old != "none" and not ID_RE.fullmatch(old):
        errors.append(f"{display}: invalid supersedes ID")
    reviewed = meta.get("last_reviewed")
    if reviewed:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed):
            errors.append(f"{display}: last_reviewed must be YYYY-MM-DD")
        else:
            try:
                date.fromisoformat(reviewed)
            except ValueError:
                errors.append(f"{display}: invalid calendar date {reviewed}")
    return meta, errors


def _links(path: Path, body: str) -> list[str]:
    errors: list[str] = []
    display = path.relative_to(ROOT).as_posix()
    for raw in LINK_RE.findall(body):
        link = raw.strip()
        if not link or link.startswith("#"):
            continue
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc:
            # External links are not reachable/verified by this local static checker.
            continue
        target = unquote(parsed.path)
        if not target:
            continue
        if target.startswith("/") or "\\" in target:
            errors.append(f"{display}: non-relative local link: {link!r}")
            continue
        dest = (path.parent / target).resolve()
        if not _in_repo(dest):
            errors.append(f"{display}: link escapes repository: {link!r}")
        elif not dest.exists():
            errors.append(f"{display}: missing link target: {link!r}")
    return errors


def main() -> int:
    files, errors = _manifest()
    ids: dict[str, str] = {}
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{name}: cannot read: {exc}")
            continue
        meta, problems = _frontmatter(path, body)
        errors.extend(problems)
        errors.extend(_links(path, body))
        doc_id = meta.get("doc_id")
        if doc_id:
            if doc_id in ids:
                errors.append(f"{name}: doc_id {doc_id} duplicated by {ids[doc_id]}")
            ids[doc_id] = name
    if errors:
        for message in sorted(errors):
            print(f"AI_DOCS_ERROR: {message}", file=sys.stderr)
        print(f"AI_DOCS: FAIL ({len(errors)} errors, {len(files)} documents)", file=sys.stderr)
        return 1
    print(f"AI_DOCS: PASS ({len(files)} documents; metadata and local paths only; no scientific attestation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
