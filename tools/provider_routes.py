"""Run a provider adapter's declared reference routes on the discovered build and print the run records.

Run it with the PROVIDER ENVIRONMENT's interpreter (the build being checked is
the one that interpreter discovers), e.g.::

    $FORGE_PROVIDER_ENVS/chrono/bin/python tools/provider_routes.py chrono --out runs.json

The output is an ``engcore.providers.route_run_ledger/1`` hash chain of the
runs (``--ledger`` appends to an existing one, which must verify).  A run is
a check of one translation on one build.  It is NOT a qualification: an
issuer creates a ``ProviderQualification`` citing the digests of PASSED runs,
the route digest and the ledger head, and ``assess_health`` admits it only
when every committed run of that route and build passed.
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
    from forge_chrono.routes import SOLVERS, run_pendulum_route

    reg = ProviderRegistry()
    d.register(reg)
    status = reg.status("chrono")
    if not status.available:
        return status, []
    return status, [run_pendulum_route(status, solver) for solver in SOLVERS]


ROUTES = {"chrono": _chrono}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("provider", choices=sorted(ROUTES))
    parser.add_argument("--ledger", help="an existing run ledger (JSON) to append to; it must hash to its recorded head")
    parser.add_argument("--out", help="write the run ledger as JSON here (default: stdout)")
    args = parser.parse_args(argv)
    status, runs = ROUTES[args.provider]()
    if not status.available:
        print(f"{args.provider} is not available here: {status.reason}; no route run is recorded", file=sys.stderr)
        return 2
    from engcore.providers.qualification import RouteRunLedger

    ledger = RouteRunLedger()
    if args.ledger:
        with open(args.ledger, "r", encoding="utf-8") as fh:
            ledger = RouteRunLedger.from_dict(json.load(fh))
    for r in runs:
        ledger = ledger.append(r)
    text = json.dumps(ledger.to_dict(), indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    for r in runs:
        print(f"{r.route_id}: {r.outcome.value} (relative error {r.relative_error}) run {r.digest}", file=sys.stderr)
    print(f"provider {status.version} {status.digest}; adapter {runs[0].adapter[1] if runs else ''}; ledger head {ledger.head}",
          file=sys.stderr)
    return 0 if all(r.outcome.value == "passed" for r in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
