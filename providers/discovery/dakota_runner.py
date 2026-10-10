"""Dakota runner (runs INSIDE the provider environment): a Latin-hypercube sampling study of Dakota's built-in
``text_book`` driver.  Reports Dakota's own sample moments as raw provider output -- FORGE grants it no UQ authority."""

import json
import os
import re
import subprocess
import sys
import tempfile

DECK = """environment
  tabular_data
method
  sampling sample_type lhs samples = {samples} seed = {seed}
variables
  uniform_uncertain = 2
    lower_bounds = 0.5 0.5
    upper_bounds = 1.5 1.5
    descriptors = 'x1' 'x2'
interface
  analysis_drivers = 'text_book' direct
responses
  response_functions = 1
  no_gradients
  no_hessians
"""


def main() -> int:
    req = json.load(sys.stdin)
    with tempfile.TemporaryDirectory() as tmp:
        deck = os.path.join(tmp, "study.in")
        with open(deck, "w") as fh:
            fh.write(DECK.format(samples=int(req.get("samples", 20)), seed=int(req.get("seed", 1))))
        run = subprocess.run(["dakota", "-i", deck], cwd=tmp, capture_output=True, text=True, timeout=120)
        version = subprocess.run(["dakota", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    m = re.search(r"response_fn_1\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", run.stdout)
    out = {"provider": "dakota", "provider_version": version, "returncode": run.returncode,
           "moments": None if m is None else {"mean": float(m.group(1)), "std_dev": float(m.group(2)),
                                              "skewness": float(m.group(3)), "kurtosis": float(m.group(4))}}
    json.dump(out, sys.stdout)
    return 0 if run.returncode == 0 and m is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
