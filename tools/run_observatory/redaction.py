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
