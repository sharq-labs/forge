"""Generate and seal the Blind v2 corpus. Run once, before any Forge run."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
BLIND = HERE.parent
REPO = BLIND.parent.parent
sys.path.insert(0, str(BLIND))

from challenge import freeze  # noqa: E402


def core_tree_digest() -> str:
    root = REPO / "src/engcore/scientific"
    h = hashlib.sha256()
    for p in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(b"\x00")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def main() -> int:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    result = freeze.generate()
    manifest = freeze.build_manifest(
        result, core_tree_sha256=core_tree_digest(), core_commit=commit
    )
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (BLIND / "FREEZE.json").write_text(text, encoding="utf-8")
    print(f"primary={manifest['primary_case_count']} shadows={manifest['shadow_count']}")
    print(f"decided={manifest['scientifically_decided']} dual={manifest['dual_oracle_cases']} "
          f"({manifest['dual_oracle_share_of_decided']:.1%})")
    print("outcomes:", manifest["outcome_counts"])
    print("truth classes:", manifest["truth_class_counts"])
    print("unresolved:", manifest["unresolved_truth"])
    print("no-peek clean:", manifest["no_peek_audit"]["clean"])
    missing = [k for k, v in manifest["artifacts"].items() if v is None]
    if missing:
        print("artifacts not yet present:", missing)
    print("FREEZE.json sha256:", hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
