"""Reproduce a flagship:  python -m forge_flagships <battery|structure|cavity|chemistry> [case] --out DIR [--extras]

Runs the flagship through the BIG 12 system runtime, verifies the run bundle it writes (every file re-hashed, the result re-derived), and prints the
engineering summary.  ``--extras`` also runs the flagship's verification studies (battery: window refinement; structure: exact-limit runs and the
mesh study).  Each flagship needs its own provider environment - see ``docs/flagships/README.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(prog="forge_flagships")
    ap.add_argument("flagship", choices=("battery", "structure", "cavity", "chemistry"))
    ap.add_argument("case", nargs="?", default=None)
    ap.add_argument("--out", required=True, help="directory for the run bundle")
    ap.add_argument("--extras", action="store_true", help="also run the flagship's verification studies")
    args = ap.parse_args(argv)
    from engcore.engineering import committed_artifacts, verify_bundle, write_bundle

    if args.flagship == "battery":
        from .battery_cooling import run_flagship
        run = run_flagship(args.case or "normal", refinement=args.extras)
        request, files = run.flagship.request, run.flagship.store.files
        refs = list(run.references) + [r for r, _ in run.references_considered]
        name = f"flagship-a-{args.case or 'normal'}"
    elif args.flagship == "structure":
        from .thermo_mechanical import run_structure
        case = args.case or "flagship"
        run = run_structure(case, verification=args.extras, study=args.extras)
        request, files, refs = run.structure.request, run.structure.exchange.files, list(run.references)
        name = f"flagship-b-{case}"
    elif args.flagship == "cavity":
        from .cavity_cfd import run_cavity
        run = run_cavity()
        request, files, refs = run.cavity.request, run.cavity.exchange.files, list(run.references)
        name = "flagship-c-cavity-re100"
    else:
        from .chem_thermal import run_chemistry
        run = run_chemistry()
        request, files, refs = run.chemistry.request, run.chemistry.exchange.files, list(run.references)
        name = "flagship-d-chemistry"
    unique = list({r.reference_id: r for r in refs}.values())
    manifest = write_bundle(args.out, name=name, request=request, result=run.result, summary=run.summary, references=unique, artifacts=committed_artifacts(run.result, files))
    verify_bundle(args.out)
    sys.stdout.write(run.summary.render_text())
    sys.stdout.write(f"\nrun bundle {manifest.digest} verified in {os.path.abspath(args.out)}\n")
    extra = getattr(run, "study", None) or getattr(run, "verification", None)
    if extra:
        sys.stdout.write("extras: " + json.dumps(extra, default=str)[:2000] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
