"""BR1's own per-case decisions (status and reason codes), exported by running BR1's code on BR1's frozen cases.

BR1's committed results (``benchmarks/mind_gen2_world_v1/results/BENCHMARK.json``) hold its scores and the digest of
its 515 decisions, not the decisions.  The BR1.1 re-score (``rescore.py``) compares against what BR1 actually decided,
so this module runs BR1's code in a checkout of the BR1 commit and writes ``results/BR1_DECISIONS.json`` only if the
decisions it read reproduce BR1's committed ``decisions_digest`` byte for byte (the digest is over BR1's full decision
records; the export keeps their status and codes).

    python -m benchmarks.mind_gen2_authority_v1.br1_decisions /path/to/a/checkout/of/1202ea6c
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PATH = HERE / "results" / "BR1_DECISIONS.json"
BR1_COMMIT = "1202ea6c3d96f5c31d0b142a32438da75e020cae"
SCHEMA = "forge.mind.gen2_authority.br1_decisions/1"

_EXPORT = """
import json
from benchmarks.mind_gen2_world_v1 import cases as C, run_benchmark as rb
cases = C.load()["cases"]
rows = rb.decisions(cases, rb._worlds(cases))
print(json.dumps({"decisions_digest": rb.decisions_digest(rows),
                  "decisions": {r["case"]["case_id"]: {"status": r["gen2"]["status"],
                                                       "codes": sorted(r["gen2"]["codes"])} for r in rows}}))
"""


def export(checkout: pathlib.Path) -> dict:
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    if head != BR1_COMMIT:
        raise SystemExit(f"{checkout} is at {head}, not the BR1 commit {BR1_COMMIT}")
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONPATH=os.pathsep.join([str(checkout / "src"), str(checkout)]))
    out = subprocess.run([sys.executable, "-c", _EXPORT], capture_output=True, text=True, env=env, cwd=checkout,
                         check=True).stdout
    found = json.loads(out.strip().splitlines()[-1])
    committed = json.loads((checkout / "benchmarks" / "mind_gen2_world_v1" / "results" / "BENCHMARK.json").read_bytes())
    if found["decisions_digest"] != committed["decisions_digest"]:
        raise SystemExit("BR1's code did not reproduce its committed decisions_digest; nothing is written")
    benchmark = HERE.parent / "mind_gen2_world_v1" / "results" / "BENCHMARK.json"
    return {"schema": SCHEMA, "br1_commit": BR1_COMMIT, "decisions_digest": found["decisions_digest"],
            "benchmark_sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest(),
            "statement": ("BR1's own decisions on its 515 frozen cases, produced by BR1's code at the commit above; "
                          "the full decision records hashed to BR1's committed decisions_digest."),
            "decisions": found["decisions"]}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    payload = export(pathlib.Path(argv[0]).resolve())
    PATH.write_bytes((json.dumps(payload, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    print(f"wrote {PATH.relative_to(HERE.parents[1])}: {len(payload['decisions'])} decisions, digest "
          f"{payload['decisions_digest'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
