"""Genesis-lite v0.3 DRAFT, P-5: the environment manifest a formal run is bound to.

The v0.2 pilot recorded only ``python``, ``platform`` and ``cpu_count`` after the fact. Nothing froze the interpreter
or the third-party packages the benchmark imports, so a formal run on another numpy or scipy (whose generator streams
NEP 19 does not promise to keep) would carry the same identity.

The manifest is measured in a FRESH interpreter (``-I``, this tree on ``sys.path``). That interpreter imports the
modules a formal run imports and records:

* the interpreter's implementation, version and platform;
* every third-party distribution that provided a loaded module, with its version;
* any loaded non-stdlib top-level module that no distribution claims, listed and never dropped.

Its digest is what a FROZEN v0.3 preregistration commits (``formal.environment_manifest_sha256``), and the formal
driver refuses a mismatch. Which machine and interpreter the formal tier runs on is an owner decision (OD-18 / OD-3).
The draft records it as ``OWNER_DECISION_REQUIRED`` and does not record this machine's manifest.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any, Mapping

MANIFEST_SCHEMA = "forge.genesis_lite.environment_manifest/1"
ROOT = pathlib.Path(__file__).resolve().parents[3]
#: what a formal run imports: the harness (escrow, presentation, evaluator), the arm registry, the v0.3 analysis
PROBE_MODULES = ("benchmarks.genesis_lite.harness", "benchmarks.genesis_lite.arms", "benchmarks.genesis_lite.proposer_host",
                 "benchmarks.genesis_lite.v0_3.analysis", "benchmarks.genesis_lite.v0_3.evaluator")

_PROBE = r"""
import importlib, importlib.metadata as md, json, platform, sys
sys.path[:0] = [sys.argv[1] + "/src", sys.argv[1]]
for name in json.loads(sys.argv[2]):
    importlib.import_module(name)
first_party = {"benchmarks", "engcore", "crafty", "tests", "__main__"}
tops = sorted({m.split(".")[0] for m in list(sys.modules)} - set(sys.stdlib_module_names) - first_party)
owners = md.packages_distributions()
dists, unmapped = {}, []
for top in tops:
    names = owners.get(top)
    if not names:
        unmapped.append(top)
        continue
    for dist in names:
        dists[dist] = md.version(dist)
print(json.dumps({"python": {"implementation": sys.implementation.name, "version": platform.python_version(),
                             "system": platform.system(), "machine": platform.machine()},
                  "distributions": dict(sorted(dists.items())), "unmapped_modules": unmapped}))
"""


def build_manifest(python: str | None = None) -> dict[str, Any]:
    """Measure the manifest of ``python`` (default: this interpreter) for this tree."""
    out = subprocess.run([python or sys.executable, "-I", "-c", _PROBE, str(ROOT), json.dumps(PROBE_MODULES)],
                         capture_output=True, text=True, check=True).stdout
    return {"schema": MANIFEST_SCHEMA, "probe_modules": list(PROBE_MODULES), **json.loads(out)}


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compare(frozen: Mapping[str, Any], now: Mapping[str, Any]) -> list[str]:
    """Every difference between a frozen manifest and the current one, as 'path: frozen != now'."""
    diffs: list[str] = []

    def walk(a: Any, b: Any, path: str) -> None:
        if isinstance(a, Mapping) and isinstance(b, Mapping):
            for k in sorted(set(a) | set(b)):
                walk(a.get(k, "<absent>"), b.get(k, "<absent>"), f"{path}.{k}" if path else str(k))
        elif a != b:
            diffs.append(f"{path}: {a} != {b}")

    walk(frozen, now, "")
    return diffs


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="print the Genesis-lite v0.3 environment manifest and its digest")
    parser.add_argument("--python", default=None, help="interpreter to measure (default: this one)")
    args = parser.parse_args(argv)
    manifest = build_manifest(args.python)
    sys.stdout.write(json.dumps(manifest, sort_keys=True, indent=1) + "\n" + manifest_digest(manifest) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
