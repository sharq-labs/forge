"""Run the isolated Blindfold deployment demo and print its report (Big Rock 2, 2G).

    python -m tools.blindfold_isolation_demo [--workdir DIR] [--json PATH]

Needs root on the launcher side (namespaces + uid switch).  Reports OS_ISOLATION_BOUNDARY_VERIFIED only if every attack
from the Discovery domain failed and no escrow secret was readable there; never a container or host boundary.
"""

from __future__ import annotations

import argparse
import json
import tempfile

from engcore.blindfold.isolation import run_isolation_demo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)
    report = run_isolation_demo(args.workdir or tempfile.mkdtemp(prefix="blindfold-isolation-"))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if report["security_boundary_status"] != "SECURITY_BOUNDARY_NOT_PROVEN" or not report["isolation_available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
