"""Run the GEN1 candidate under a file-access audit hook; record every path opened or listed, and every module loaded.

    python -m benchmarks.battery_rediscovery_v3.sandbox_run <access-log.json> -- <GEN1 candidate.run arguments>

The hook is installed before any candidate module is imported.  The candidate is the GEN1 code itself
(``benchmarks.battery_rediscovery_v2.candidate.run``), called with ``--pack`` pointing at the v3 CandidateBundle; nothing
in it is changed.  ``leakage.runtime_findings`` then refuses any opened path outside the declared roots, any path under a
forbidden root (the evaluator's vault and truth directories, the v2 pack, every v0/v1/v2 results and evaluator
directory), any loaded
evaluator-side module, and (during a run) any read of an output path.
"""

from __future__ import annotations

import json
import os
import sys

_OPENED: set[tuple[str, str]] = set()


def _hook(event: str, args: tuple) -> None:
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        _OPENED.add((os.path.abspath(os.fsdecode(args[0])), str(args[1]) if len(args) > 1 else ""))
    elif event in ("os.listdir", "os.scandir") and args:
        target = args[0] if args[0] is not None else "."
        if isinstance(target, (str, bytes, os.PathLike)):
            _OPENED.add((os.path.abspath(os.fsdecode(target)), "list"))


def install() -> None:
    sys.addaudithook(_hook)


def write_log(log: str, rc: int) -> None:
    payload = {"schema": "forge.battery_rediscovery_v3.access_log/1", "exit": rc,
               "opened": sorted([p, m] for p, m in _OPENED), "modules": sorted(sys.modules)}
    with open(log, "wb") as fh:
        fh.write((json.dumps(payload, indent=1, sort_keys=True) + "\n").encode())


def main(argv: list[str]) -> int:
    log, rest = argv[0], argv[argv.index("--") + 1:]
    install()
    from benchmarks.battery_rediscovery_v2.candidate import run  # GEN1, imported only after the hook is installed

    rc = 1
    try:
        rc = run.main(rest)
    finally:
        write_log(log, rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
