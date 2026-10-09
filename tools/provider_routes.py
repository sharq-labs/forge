"""Run a provider adapter's declared reference routes on the discovered build and print the run records.

Run it with the PROVIDER ENVIRONMENT's interpreter (the build being checked is
the one that interpreter discovers), e.g.::

    $FORGE_PROVIDER_ENVS/chrono/bin/python tools/provider_routes.py chrono --out runs.json

The output is a list of ``engcore.providers.route_run/1`` records.  A record
is a check of one translation on one build.  It is NOT a qualification: an
issuer creates a ``ProviderQualification`` citing the digests of PASSED runs,
and ``engcore.providers.qualification.admitted_qualifications`` admits it only
when every cited run resolves, passed, and ran that exact build and adapter.
A provider that is not available here produces no record and exit status 2.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _chrono():
    sys.path.insert(0, os.path.join(ROOT, "providers", "chrono"))
    from engcore.providers import ProviderRegistry

    import forge_chrono.descriptor as d
    from forge_chrono.routes import run_pendulum_route

    reg = ProviderRegistry()
    d.register(reg)
    status = reg.status("chrono")
    if not status.available:
        return status, []
    return status, [run_pendulum_route(status, ts) for ts in ("euler_implicit_linearized", "hht")]


ROUTES = {"chrono": _chrono}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("provider", choices=sorted(ROUTES))
    parser.add_argument("--out", help="write the run records as JSON here (default: stdout)")
    args = parser.parse_args(argv)
    status, runs = ROUTES[args.provider]()
    if not status.available:
        print(f"{args.provider} is not available here: {status.reason}; no route run is recorded", file=sys.stderr)
        return 2
    payload = {"provider": status.to_dict(), "runs": [dict(r.to_dict(), digest=r.digest) for r in runs]}
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    for r in runs:
        print(f"{r.route_id}: {r.outcome.value} (relative error {r.relative_error}) {r.digest}", file=sys.stderr)
    return 0 if all(r.outcome.value == "passed" for r in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
