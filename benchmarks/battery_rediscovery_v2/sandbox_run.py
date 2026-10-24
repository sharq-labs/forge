"""Run the candidate under a file-access audit hook and record every path it opened or listed, and every module loaded.

    python -m benchmarks.battery_rediscovery_v2.sandbox_run <access-log.json> -- <candidate.run arguments>

The hook is installed before any candidate module is imported.  ``leakage.runtime_findings`` then refuses any opened
path outside the declared roots (the candidate package and pack, the engcore platform, the Python installation and
the output directory) and any loaded module from the evaluator side or a historical battery package.
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


sys.addaudithook(_hook)


def main(argv: list[str]) -> int:
    log, rest = argv[0], argv[argv.index("--") + 1:]
    from .candidate import run  # imported only after the hook is installed

    rc = 1
    try:
        rc = run.main(rest)
    finally:
        payload = {"schema": "forge.battery_rediscovery_v2.access_log/1", "exit": rc,
                   "opened": sorted([p, m] for p, m in _OPENED), "modules": sorted(sys.modules)}
        with open(log, "wb") as fh:
            fh.write((json.dumps(payload, indent=1, sort_keys=True) + "\n").encode())
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
