"""Apply an adjudication event to the cases it decides, and to the digests.

WHY THIS TOOL EXISTS
--------------------
A ground-truth revision is three edits that must agree, and the previous one
was made by hand:

  1. the case files whose truth was re-decided;
  2. ``GROUND_TRUTH_SCHEMA.json``, which pins the case-set digest;
  3. ``split_hard.json``, which pins the same digest and would otherwise stop
     describing the cases on disk -- at which point ``score_hard.py --split dev``
     refuses to run and the instruction it hands over is "regenerate the split",
     which reallocates sealed seats.

Doing that by hand is how a hold-out gets opened by accident. So the log is the
source of truth and the case files are derived from it: every revision is
written into ``ADJUDICATIONS.json`` first, with the previous value beside the
new one, and this applies it. A case is only touched when the log says so, and
only in the fields the log names.

**Membership is never recomputed.** ``split_hard.json``'s ``dev`` and
``holdout`` arrays are asserted byte-identical afterwards. Only
``case_set_digest`` and the derived ``verification`` composition block move --
the same two fields the 2026-09-09 adjudication moved, and for the same reason.

Usage
-----
    python benchmarks/hard/apply_adjudication.py --check
    python benchmarks/hard/apply_adjudication.py --event <adjudication_id>

``--check`` reports what is out of step without writing anything, and exits
non-zero if the cases on disk disagree with the log.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CASES = HERE / "cases_hard"
LOG = HERE / "ADJUDICATIONS.json"
SCHEMA = HERE / "GROUND_TRUTH_SCHEMA.json"
SPLIT = HERE / "split_hard.json"

#: Ground-truth fields an event may revise, each paired with the key that
#: carries its previous value. Nothing outside this mapping is writable: an
#: event cannot reach a payload, an id, or a defect family -- and `defect` is
#: excluded precisely because the split stratifies on it, so revising it would
#: move a case between the development set and the sealed hold-out.
REVISABLE = {
    "expected_verdict": "previous_expected_verdict",
    "label": "previous_label",
    "should_be_caught_by": "previous_declared_catcher",
    "reason": "previous_reason",
    # benchmark_ground_truth/2 fields. Each is OPTIONAL on a case, so its
    # `previous_` value is null where the case did not carry it -- which is a
    # statement ("the benchmark had no opinion") rather than a missing entry.
    "acceptable_catchers": "previous_acceptable_catchers",
    "expected_unknown_reason": "previous_expected_unknown_reason",
    "oracle": "previous_oracle",
    "needs_review": "previous_needs_review",
}

#: Where each revisable field's NEW value lives on a case entry.
NEW_VALUE = {
    "expected_verdict": "new_expected_verdict",
    "label": "label",
    "should_be_caught_by": "declared_catcher",
    "reason": "reason",
    "acceptable_catchers": "acceptable_catchers",
    "expected_unknown_reason": "expected_unknown_reason",
    "oracle": "oracle",
    "needs_review": "needs_review",
}


def case_set_digest(paths) -> str:
    """Identical to score_hard.case_set_digest and split_hard.case_set_digest."""
    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in paths]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def revisions_for(event: dict) -> dict[str, dict[str, object]]:
    """The fields this event revises, per case, read off the log."""
    out: dict[str, dict[str, object]] = {}
    for entry in event["cases"]:
        wanted = {}
        for field, previous_key in REVISABLE.items():
            new_key = NEW_VALUE[field]
            if previous_key in entry and new_key in entry:
                wanted[field] = entry[new_key]
        out[entry["case_id"]] = wanted
    return out


def apply_event(event: dict, *, write: bool) -> list[str]:
    """Bring the cases into line with the log. Returns what changed."""
    changed = []
    for case_id, fields in revisions_for(event).items():
        path = CASES / f"{case_id}.json"
        before = path.read_bytes()
        case = json.loads(before.decode("utf-8"))
        truth = case["ground_truth"]
        differing = {k: v for k, v in fields.items() if truth.get(k) != v}
        if not differing:
            continue
        for key, value in differing.items():
            if value is None:
                # An optional field revised back to "no opinion" is REMOVED,
                # not set to null. Absence is the schema's way of saying the
                # benchmark has nothing to say, and a null would be a value.
                truth.pop(key, None)
            else:
                truth[key] = value
        # The corpus' own serialization, written as BYTES: no trailing
        # newline, ensure_ascii=False, default separators. Text mode on
        # Windows would translate the line endings inside the payload strings
        # and move every digest below for a reason nobody intended.
        after = json.dumps(case, ensure_ascii=False).encode("utf-8")
        changed.append(
            f"{case_id}: " + ", ".join(sorted(differing)) +
            f" ({len(before)} -> {len(after)} bytes)"
        )
        if write:
            path.write_bytes(after)
    return changed


def refresh_digests(*, write: bool) -> tuple[str, str]:
    """Re-pin the case-set digest wherever it is recorded. Membership is not."""
    digest = case_set_digest(sorted(CASES.glob("*.json")))
    schema = _load(SCHEMA)
    was = schema["case_set_digests"]["cases_hard"]
    schema["case_set_digests"]["cases_hard"] = digest

    split = _load(SPLIT)
    dev_before, holdout_before = list(split["dev"]), list(split["holdout"])
    split["case_set_digest"] = digest

    spec = importlib.util.spec_from_file_location("split_hard", HERE / "split_hard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _files, cases = module.read_cases(CASES)
    split["verification"] = module.verify(
        cases, set(split["dev"]), set(split["holdout"]), seed=split["seed"]
    )

    if list(split["dev"]) != dev_before or list(split["holdout"]) != holdout_before:
        raise SystemExit(
            "REFUSED: the split's membership moved. Only the digest and the "
            "derived composition may change; reallocating seats is how a "
            "hold-out is opened without saying so."
        )

    if write:
        SCHEMA.write_bytes(
            (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        SPLIT.write_bytes(json.dumps(split, indent=1).encode("utf-8"))
    return was, digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", help="adjudication_id to apply")
    parser.add_argument("--check", action="store_true",
                        help="report drift between the log and the cases; write nothing")
    args = parser.parse_args()

    log = _load(LOG)
    events = log["events"]
    if args.check:
        drift = []
        for event in events:
            drift += apply_event(event, write=False)
        if drift:
            print("cases disagree with the log:")
            for line in drift:
                print(f"  {line}")
            return 1
        print(f"{len(events)} event(s); every case matches the log")
        return 0

    if not args.event:
        parser.error("give --event <adjudication_id> or --check")
    selected = [e for e in events if e["adjudication_id"] == args.event]
    if not selected:
        parser.error(
            f"no event {args.event!r}; the log has "
            f"{[e['adjudication_id'] for e in events]}"
        )

    changed = apply_event(selected[0], write=True)
    for line in changed:
        print(line)
    if not changed:
        print("nothing to apply; the cases already match the log")
    was, now = refresh_digests(write=True)
    print(f"case-set digest: {was[:16]} -> {now[:16]}")
    print("split: dev and hold-out membership byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
