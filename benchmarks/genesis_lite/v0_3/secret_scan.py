"""Genesis-lite v0.3 DRAFT, FDA-19: a proposer-side scan for the Genesis-lite secret inventory.

FDA-19 / D-05 (deep audit 2026-10-19): the certified isolation probe (``engcore.blindfold.isolation_probe``) looks only
for the escrow journal canary in recently changed files. It cannot see the Genesis-lite leak class: the root file, the
derived masters, the run log and the attempt registry. This scan closes that gap on the benchmark side, without a
certified change. It runs as the PROPOSER's account inside the OD-20 deployment and reports every readable file that
holds a secret. The deployment counts as verified only when it reports nothing.

The scanner never receives a secret. It receives sha256 DIGESTS of the hex secrets (the root and every master). It
hashes each 64-hex-character token in every readable file and compares the digests; raw 32-byte secrets are checked the
same way over every 32-byte window of files up to :data:`RAW_WINDOW_LIMIT` bytes. It also flags the run log and the
attempt registry by their schema markers, which appear in no other file. Unreadable files and directories are skipped:
being refused is the desired result.

    python -m benchmarks.genesis_lite.v0_3.secret_scan --digests digests.json ROOT_DIR [ROOT_DIR ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from typing import Iterable

#: compact-JSON forms that only a real registry line or run-log line contains (assembled here, so that no source file,
#: this one included, holds them literally)
MARKERS = {b'"schema":"' + b'forge.genesis_lite.attempt_registry/1"': "attempt registry",
           b'{"prev_sha256' + b'":"': "run log"}
MAX_FILE_BYTES = 64 * 1024 * 1024
RAW_WINDOW_LIMIT = 4096                                   # raw roots live in tiny files; larger files are hex-scanned
_HEX64 = re.compile(rb"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")


def digests_for(secrets: Iterable[bytes]) -> list[str]:
    """What the operator hands the scanner: sha256 of each secret's lowercase hex form and of its raw bytes."""
    out = set()
    for raw in secrets:
        out.add(hashlib.sha256(raw.hex().encode()).hexdigest())
        out.add(hashlib.sha256(raw).hexdigest())
    return sorted(out)


def _scan_bytes(data: bytes, digests: frozenset[str]) -> list[str]:
    found = []
    for m in _HEX64.finditer(data):
        if hashlib.sha256(m.group(0).lower()).hexdigest() in digests:
            found.append("hex secret")
            break
    if len(data) <= RAW_WINDOW_LIMIT:
        for i in range(0, max(0, len(data) - 31)):
            if hashlib.sha256(data[i:i + 32]).hexdigest() in digests:
                found.append("raw secret")
                break
    found += [what for marker, what in MARKERS.items() if marker in data]
    return found


def scan(roots: Iterable[pathlib.Path], digests: Iterable[str]) -> list[dict[str, str]]:
    """Every readable file under ``roots`` that holds a secret or an inventory marker."""
    wanted = frozenset(digests)
    findings = []
    for root in roots:
        for dirpath, _dirs, files in os.walk(root, onerror=lambda _exc: None):
            for name in files:
                path = pathlib.Path(dirpath) / name
                try:
                    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                        continue
                    data = path.read_bytes()
                except OSError:
                    continue
                for what in _scan_bytes(data, wanted):
                    findings.append({"path": str(path), "found": what})
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="scan readable files for the Genesis-lite secret inventory")
    parser.add_argument("--digests", required=True, type=pathlib.Path, help="JSON list of sha256 digests (digests_for)")
    parser.add_argument("roots", nargs="+", type=pathlib.Path)
    args = parser.parse_args(argv)
    findings = scan(args.roots, json.loads(args.digests.read_bytes()))
    sys.stdout.write(json.dumps(findings, indent=1) + "\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
