"""Vendor exactly the selected trajectories, and nothing else.

``trajectories.json`` holds every trajectory that passed the acquisition screen
and is 58 MB. What the campaign reads is the preregistered selection, which is
small enough to live in the repository so the run reproduces from the tree
alone. The full file stays out of git and is regenerated from the archive.

Each vendored trajectory carries the member digest it came from, and the file
carries the archive digest, so the chain archive -> member -> trajectory ->
normalized dataset digest is checkable end to end.
"""

from __future__ import annotations

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EVIDENCE = os.path.join(os.path.dirname(HERE), "evidence")


def main() -> int:
    with open(os.path.join(EVIDENCE, "trajectories.json"), encoding="utf-8") as handle:
        full = json.load(handle)
    with open(os.path.join(EVIDENCE, "DATA_SELECTION.json"), encoding="utf-8") as handle:
        selection = json.load(handle)

    wanted = {item["trajectory_id"] for item in selection["selected"]}
    by_id = {item["trajectory_id"]: item for item in full["trajectories"]}
    missing = sorted(wanted - set(by_id))
    if missing:
        raise SystemExit(f"selected trajectories absent from the acquisition: {missing}")

    kept = [by_id[key] for key in sorted(wanted)]
    payload = {
        "schema": "battery_thermal_flagship_s3_selected_trajectories/1",
        "archive_sha256": full["archive_sha256"],
        "selection_count": len(kept),
        "trajectories": kept,
    }
    text = json.dumps(payload, indent=1, allow_nan=False)
    out = os.path.join(EVIDENCE, "selected_trajectories.json")
    with open(out, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print(f"vendored {len(kept)} trajectories, {os.path.getsize(out)} bytes")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
