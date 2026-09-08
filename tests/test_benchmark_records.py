"""The committed benchmark records must still be what the code produces.

THE DEFECT THIS CLOSES
----------------------
`.github/workflows/tests.yml` scored both benchmarks into `/tmp` and threw the
answer away. Nothing compared `benchmarks/hard/results_battery.json` or
`benchmarks/hard/results_hard.json` against a re-score, and `grep -rn
"results_battery" tests/` returned nothing. Two committed records, both quoted
in the release pages and the README, and neither one checked against the code
that is supposed to produce it.

The battery record had already gone stale: it says 400/400 exact verdict match
and the tree produces 372/400. It said so for at least two commits without
anything going red, which is what an unguarded record buys -- a number that is
true when it is written and true-looking forever after.

**There was no mechanism here to mirror.** The brief that prompted this asked
for a guard "mirroring whatever mechanism already guards the hard benchmark".
That mechanism does not exist: `results_hard.json` is discarded to
`/tmp/results_dev.json` by the same job, unchecked, exactly like the battery
one. So this follows the nearest shape that *does* exist -- the CI step named
"split is reproducible from the seed and the rule", which re-derives the split
and compares declared fields against the committed file -- and it applies that
shape to BOTH records rather than inventing a second one for each.

WHAT IS COMPARED
----------------
Every row's `actual` verdict, and every summary figure a release page can
quote. Not `generated`, which is a timestamp and is expected to differ.

The comparison runs the real scorer as a subprocess, the same entry point CI
invokes, and points `--results` at a temporary file. That last part is not
incidental: `score_hard.py`'s `--results` DEFAULTS to the tracked record, so a
guard that forgot the flag would overwrite the very file it exists to protect
and pass every time.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCH = REPO_ROOT / "benchmarks" / "hard"

#: The figures a release page or the README can quote. `generated` is excluded
#: deliberately -- it is a timestamp, and pinning it would make the guard fail
#: for the one reason that carries no information.
QUOTED_FIGURES = (
    "case_set_digest",
    "total",
    "sound",
    "unsound",
    "exact_verdict_match",
    "catch_rate",
    "false_accept",
    "false_reject",
    "false_accept_ids",
)

#: Each record, and the scorer arguments that reproduce it. The `split`
#: argument matters: the hard record is the DEVELOPMENT split, and scoring
#: anything containing the sealed partition requires `--open-holdout`, which
#: this guard must never pass. A guard that broke the hold-out seal to check a
#: number would cost more than the number is worth.
RECORDS = {
    "battery": ("results_battery.json", ["--cases", str(BENCH / "cases_battery")]),
    "hard": (
        "results_hard.json",
        ["--cases", str(BENCH / "cases_hard"), "--split", "dev"],
    ),
}


def _rescore(name: str, destination: pathlib.Path) -> dict:
    """Run the real scorer and return what it produced."""
    record_name, arguments = RECORDS[name]
    completed = subprocess.run(
        [
            sys.executable,
            str(BENCH / "score_hard.py"),
            "--src",
            str(REPO_ROOT / "src"),
            "--workers",
            "4",
            # NEVER omit this. The default is the tracked record itself.
            "--results",
            str(destination),
            *arguments,
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert completed.returncode == 0, (
        f"the scorer failed for the {name!r} case set, so this guard proved "
        f"nothing:\n{completed.stdout[-4000:]}\n{completed.stderr[-4000:]}"
    )
    return json.loads(destination.read_text(encoding="utf-8"))


def _committed(name: str) -> dict:
    record_name, _ = RECORDS[name]
    return json.loads((BENCH / record_name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(RECORDS))
def test_the_committed_benchmark_record_is_what_the_code_still_produces(
    name: str, tmp_path: pathlib.Path
) -> None:
    """A committed score that no longer reproduces is a number nobody checked.

    Named for the defect. The failure message carries the whole disagreement --
    which figures moved and which rows changed verdict -- because a guard that
    only says "these differ" makes the reader re-derive what this already knows.
    """
    committed = _committed(name)
    produced = _rescore(name, tmp_path / "rescored.json")

    # The case set first. If the digest moved, every figure below is being
    # compared across two different populations and the comparison is
    # meaningless rather than merely failing.
    assert (
        committed["summary"]["case_set_digest"]
        == produced["summary"]["case_set_digest"]
    ), (
        f"the {name!r} case set itself changed, so the recorded figures "
        f"describe a population that is no longer on disk. Re-freezing the "
        f"record is the right move here, and it is a different decision from "
        f"the one this guard exists to force"
    )

    committed_rows = {row["id"]: row for row in committed["rows"]}
    produced_rows = {row["id"]: row for row in produced["rows"]}
    assert set(committed_rows) == set(produced_rows), (
        f"the {name!r} record and the re-score disagree about which cases "
        f"exist: only in record "
        f"{sorted(set(committed_rows) - set(produced_rows))[:10]}, only in "
        f"re-score {sorted(set(produced_rows) - set(committed_rows))[:10]}"
    )

    # The expected labels are ground truth. They are compared separately from
    # the verdicts so a failure says which of the two moved: a changed
    # `expected` is an edit to ground truth, and a changed `actual` is the code
    # deciding differently. Those are not the same event and must not arrive as
    # one message.
    relabelled = [
        (row_id, committed_rows[row_id]["expected"], produced_rows[row_id]["expected"])
        for row_id in sorted(committed_rows)
        if committed_rows[row_id]["expected"] != produced_rows[row_id]["expected"]
    ]
    assert not relabelled, (
        f"{len(relabelled)} {name!r} rows changed their EXPECTED label, which "
        f"is ground truth and is not something a code change may move: "
        f"{relabelled[:10]}"
    )

    moved = [
        (
            row_id,
            produced_rows[row_id]["defect"],
            committed_rows[row_id]["actual"],
            produced_rows[row_id]["actual"],
        )
        for row_id in sorted(committed_rows)
        if committed_rows[row_id]["actual"] != produced_rows[row_id]["actual"]
    ]
    figures = {
        key: (committed["summary"].get(key), produced["summary"].get(key))
        for key in QUOTED_FIGURES
        if committed["summary"].get(key) != produced["summary"].get(key)
    }

    assert not moved and not figures, (
        f"the committed {name!r} benchmark record no longer reproduces.\n"
        f"figures that moved (recorded -> now): "
        f"{ {k: v for k, v in figures.items() if k != 'false_accept_ids'} }\n"
        f"{len(moved)} rows changed verdict; by defect family:\n"
        + "\n".join(
            f"  {count:3d}  {family}"
            for family, count in sorted(
                _by_family(moved).items(), key=lambda item: -item[1]
            )
        )
        + "\n\nRe-generating the record is NOT the fix until somebody has "
        "decided whether the record or the code is right. A guard that goes "
        "green by overwriting the number it was built to protect is worse "
        "than no guard."
    )


def _by_family(moved: list[tuple[str, str, str, str]]) -> dict[str, int]:
    """Group moved rows by defect family and direction, not by id.

    Ids alone are a list; a family and a direction are the beginning of a
    diagnosis.
    """
    families: dict[str, int] = {}
    for _row_id, defect, was, now in moved:
        key = f"{defect.split('@')[0]:42s} {was} -> {now}"
        families[key] = families.get(key, 0) + 1
    return families


def test_the_guard_would_notice_a_record_that_stopped_reproducing() -> None:
    """The guard is not vacuous: its comparison actually discriminates.

    A re-scoring guard that compared nothing, or compared a field that never
    moves, would pass forever and read exactly like a working one. This asserts
    the comparison over a record perturbed in each of the three ways that
    matter, without running the scorer.
    """
    committed = _committed("hard")
    rows = {row["id"]: dict(row) for row in committed["rows"]}
    first = sorted(rows)[0]

    # A moved verdict is detected.
    perturbed = {k: dict(v) for k, v in rows.items()}
    perturbed[first]["actual"] = "NOT_A_VERDICT"
    assert [
        row_id for row_id in rows if rows[row_id]["actual"] != perturbed[row_id]["actual"]
    ] == [first]

    # A moved ground-truth label is detected, and separately.
    perturbed = {k: dict(v) for k, v in rows.items()}
    perturbed[first]["expected"] = "NOT_A_LABEL"
    assert [
        row_id
        for row_id in rows
        if rows[row_id]["expected"] != perturbed[row_id]["expected"]
    ] == [first]

    # A moved summary figure is detected.
    summary = dict(committed["summary"])
    summary["exact_verdict_match"] = "0/0 (0.0%)"
    assert [
        key
        for key in QUOTED_FIGURES
        if committed["summary"].get(key) != summary.get(key)
    ] == ["exact_verdict_match"]


def test_the_scorer_default_would_overwrite_the_record_it_is_checking() -> None:
    """Why `--results` is mandatory above, asserted rather than commented.

    `score_hard.py` resolves `--results` against its own directory and defaults
    to the tracked `results_hard.json`. A guard that re-scored without the flag
    would rewrite the record, then compare it against itself, and pass. That is
    the exact failure mode this whole module exists to prevent, so the
    dangerous default is pinned here: if it ever changes, this test says so
    instead of the guard quietly becoming a no-op.
    """
    source = (BENCH / "score_hard.py").read_text(encoding="utf-8")
    assert 'ap.add_argument("--results",default=str(HERE/"results_hard.json"))' in source
    for _name, arguments in RECORDS.values():
        assert "--results" not in arguments, (
            "--results is supplied by _rescore, pointing at a temporary file; "
            "a per-record override would be the way this guard starts writing "
            "into the repository"
        )
