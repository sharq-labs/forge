"""Secret redaction for everything the observatory persists: command lines, declared values, logs.

The rules are deliberately greedy. An over-redacted argument costs a little workload precision; an
under-redacted one leaks a credential into a ledger that is meant to be copied around. The full
environment map is never persisted at all -- only the values of secret-named variables are read,
and only so they can be found and removed from the child's output.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping

from tools.run_observatory import REDACTED

#: A name (flag, variable, key) whose value is a secret.
SECRET_NAME = re.compile(
    r"(?i)(?:password|passwd|passphrase|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|"
    r"credential|authorization|cookie|signature|(?:^|[_-])auth(?:$|[_-])|(?:^|[_-])pwd(?:$|[_-]))")

_NAME_CHARS = r"[A-Za-z0-9_.-]"

#: Self-identifying credential formats, wherever they appear.
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)
_BEARER = re.compile(r"(?i)\b(bearer|basic)(\s+)(?!<REDACTED>)[A-Za-z0-9._~+/=-]+")
_AUTH_HEADER = re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(?:(?:bearer|basic|token|digest)\s+)?"
                          r"(?!<REDACTED>)[^\s\"',;]+")
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^/\s@]+)(@)")
_ASSIGNMENT = re.compile(
    rf"(?i)((?:{_NAME_CHARS})*(?:password|passwd|passphrase|secret|token|api[_-]?key|apikey|access[_-]?key|"
    rf"private[_-]?key|credential)(?:{_NAME_CHARS})*[\"']?\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&\"']+)")

#: Shorter values are too likely to occur by accident to be searched for in output.
_MIN_KNOWN_VALUE = 6


class StreamRedactor:
    """Hold incomplete records/secrets across reads before writing any persisted bytes.

    A record over 1 MiB fails closed: the rest of that stream is omitted. Raw
    passthrough and hashing remain unaffected. No raw spool file is created.
    """

    MAX_PENDING = 1024 * 1024
    _BEGIN = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    _END = re.compile(rb"-----END [A-Z ]*PRIVATE KEY-----")

    def __init__(self, redactor: "Redactor") -> None:
        self.redactor = redactor
        self.pending = b""
        self.omitted = False
        self.known = tuple(v.encode("utf-8", "surrogateescape") for v in redactor.known_values)

    def feed(self, chunk: bytes, *, final: bool = False) -> tuple[bytes, int]:
        if self.omitted:
            return b"", 0
        self.pending += chunk
        boundary = len(self.pending) if final else self.pending.rfind(b"\n") + 1
        # Never split a known value, including values containing newlines.
        for value in self.known:
            start = self.pending.find(value)
            while start >= 0:
                if start < boundary < start + len(value):
                    boundary = self.pending.rfind(b"\n", 0, start) + 1
                start = self.pending.find(value, start + 1)
            if not final:
                for size in range(min(len(value) - 1, len(self.pending)), 0, -1):
                    if self.pending.endswith(value[:size]):
                        start = len(self.pending) - size
                        boundary = min(boundary, self.pending.rfind(b"\n", 0, start) + 1)
                        break
        # A PEM block is one record even when it spans many lines. At EOF an
        # unterminated block is still secret and must never be flushed raw.
        for match in self._BEGIN.finditer(self.pending):
            end = self._END.search(self.pending, match.end())
            if end is None:
                if final:
                    self.pending = self.pending[:match.start()] + REDACTED.encode()
                    boundary = len(self.pending)
                else:
                    boundary = min(boundary, self.pending.rfind(b"\n", 0, match.start()) + 1)
                break
            if match.start() < boundary < end.end():
                boundary = self.pending.rfind(b"\n", 0, match.start()) + 1
        clean, count = self.redactor.redact_bytes(self.pending[:boundary])
        self.pending = self.pending[boundary:]
        if len(self.pending) > self.MAX_PENDING:
            self.pending = b""
            self.omitted = True
            clean += b"<REDACTED: remaining log omitted; redaction buffer limit>\n"
            count += 1
        return clean, count


def is_secret_name(name: str) -> bool:
    return bool(SECRET_NAME.search(name.lstrip("-")))


@dataclass(frozen=True)
class Redactor:
    """Removes secrets from text. ``known_values`` are the live values of secret-named variables."""

    known_values: tuple[str, ...] = ()

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "Redactor":
        values = {v for k, v in environ.items() if is_secret_name(k) and v and len(v) >= _MIN_KNOWN_VALUE}
        return cls(tuple(sorted(values, key=len, reverse=True)))

    def redact_text(self, text: str) -> tuple[str, int]:
        """``text`` with every recognised secret replaced, and how many replacements were made."""
        count = 0
        for value in self.known_values:
            if value in text:
                count += text.count(value)
                text = text.replace(value, REDACTED)
        for pattern in _TOKEN_PATTERNS:
            text, n = pattern.subn(REDACTED, text)
            count += n
        for pattern, repl in ((_AUTH_HEADER, rf"\1{REDACTED}"), (_BEARER, rf"\1\2{REDACTED}"),
                              (_URL_USERINFO, rf"\1{REDACTED}\3"), (_ASSIGNMENT, rf"\1{REDACTED}")):
            text, n = pattern.subn(repl, text)
            count += n
        return text, count

    def redact_bytes(self, data: bytes) -> tuple[bytes, int]:
        text, count = self.redact_text(data.decode("utf-8", "surrogateescape"))
        return (text.encode("utf-8", "surrogateescape"), count) if count else (data, 0)

    def redact_argv(self, argv: Iterable[str]) -> list[str]:
        """A command line with secret values removed and every other token left exactly as it was."""
        out: list[str] = []
        redact_next = False
        for token in argv:
            if redact_next:
                out.append(REDACTED)
                redact_next = False
                continue
            text, _ = self.redact_text(token)
            if token.startswith("-") and "=" not in token and len(token.lstrip("-")) > 1 and is_secret_name(token):
                redact_next = True
            elif "=" in text and not text.startswith(REDACTED):
                name, _, value = text.partition("=")
                if value and value != REDACTED and is_secret_name(name):
                    text = f"{name}={REDACTED}"
            out.append(text)
        return out

    def redact_mapping(self, mapping: Mapping[str, object]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in mapping.items():
            if is_secret_name(str(key)):
                out[key] = REDACTED
            elif isinstance(value, str):
                out[key] = self.redact_text(value)[0]
            else:
                out[key] = value
        return out
