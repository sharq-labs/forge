"""Ground truth is versioned, and a revision to it is auditable.

THE DEFECT THIS CLOSES
----------------------
The thermal adjudication moved 23 expected verdicts from ``NOT_SUPPORTED`` to
``INSUFFICIENT_EVIDENCE`` and the development score went from 1291/1400 to
1360/1400 in the same commit. Everything a reader needs in order to tell those
two facts apart -- which cases moved, what they said before, which condition
decided it, and whether any independent violation existed -- lived in a commit
message. A commit message is not a queryable record: nothing checks it, nothing
can be diffed against it, and the next revision has no obligation to write one.

That is the shape of the problem, not a complaint about one commit. **A
benchmark whose truth can move without a record cannot distinguish "the tree
got better" from "the answer key changed."** Both appear as a higher score.

WHAT IS HERE
------------
``GROUND_TRUTH_SCHEMA.json`` names the parts of a case and says which are
ground truth. ``ADJUDICATIONS.json`` is an append-only log of every revision to
it. This module checks that both describe the cases actually on disk, that a
landed adjudication cannot be edited, and -- the load-bearing one -- that split
membership is derived from case identity and defect family and **never** from
the expected verdict, so re-deciding a verdict can never move a case between
the development set and the sealed hold-out.

WHAT IS NOT HERE
----------------
No judgement about whether the adjudication was scientifically right. That is
recorded in the log's ``adjudication_basis``, in prose, for a reader to
disagree with. A test that tried to re-derive the decision would be asserting
the conclusion it was checking.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCH = REPO_ROOT / "benchmarks" / "hard"
SCHEMA_FILE = BENCH / "GROUND_TRUTH_SCHEMA.json"
LOG_FILE = BENCH / "ADJUDICATIONS.json"

GROUND_TRUTH_SCHEMA = "benchmark_ground_truth/1"
ADJUDICATION_LOG_SCHEMA = "benchmark_adjudication_log/1"

#: Every adjudication event that has LANDED, pinned by a digest over its own
#: bytes. Appending a new event leaves these untouched; editing one that is
#: already here fails. That is the whole of what "append-only" means for a
#: tracked JSON document, and it is checked rather than declared in a README.
LANDED_EVENT_DIGESTS = {
    "2026-09-09.internal-fourier-number.screen":
        "4f7a0de9d587e4d7d2de6f3de9be5f91ecc3feabf7835a9a236b598537b546c2",
    "2026-09-09.u00204.runaway-that-does-not-run-away":
        "0b0a06a71fa5457a4f60b5cded301a178d4ce7658fe80b1cbfb46a9015ed71d9",
    "2026-09-09.u01001.ceiling-sized-against-the-asymptote":
        "a6a59004267189fd0b9dc14771751f3e461a443ec3f966a2708d7e9e5d17eef1",
}


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases(directory: str) -> dict[str, dict]:
    return {
        path.stem: _load(path)
        for path in sorted((BENCH / directory).glob("*.json"))
    }


def _case_set_digest(paths) -> str:
    """Identical to the scorer's and the splitter's. Duplicated deliberately.

    A helper imported from one of them would go green if that one's definition
    drifted; this is the third independent statement of the same rule, which is
    what makes the agreement between the three meaningful.
    """
    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in paths]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _event_digest(event: dict) -> str:
    """SHA-256 over the event's canonical JSON.

    ``sort_keys`` and a fixed separator, so the digest is about the event's
    *content* and not about how the file happens to be indented today.
    """
    blob = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _split_module():
    spec = importlib.util.spec_from_file_location(
        "_split_hard_under_test", BENCH / "split_hard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- schema


def test_the_ground_truth_schema_describes_the_cases_that_are_on_disk():
    """A schema naming fields no case has is decoration.

    Checked in both directions: every case carries exactly the declared
    top-level and ground-truth fields, and every declared field is carried by
    some case. A one-directional check passes over a schema that has grown a
    field nothing writes.
    """
    schema = _load(SCHEMA_FILE)
    assert schema["schema"] == GROUND_TRUTH_SCHEMA

    roles = schema["roles"]
    ground_truth_fields = set(roles["ground_truth"]["fields"])
    identity_fields = set(roles["case_identity"]["fields"])
    payload_fields = set(roles["case_payload"]["fields"])

    for directory in ("cases_hard", "cases_battery"):
        cases = _cases(directory)
        assert cases, directory
        seen_top: set[str] = set()
        seen_ground_truth: set[str] = set()
        for case_id, case in cases.items():
            top = set(case) - {"ground_truth"}
            assert top <= identity_fields | payload_fields, (
                f"{directory}/{case_id} carries {sorted(top - identity_fields - payload_fields)}, "
                f"which {GROUND_TRUTH_SCHEMA} does not name"
            )
            assert set(case["ground_truth"]) == ground_truth_fields, (
                f"{directory}/{case_id} ground truth is "
                f"{sorted(case['ground_truth'])}, not {sorted(ground_truth_fields)}"
            )
            seen_top |= top
            seen_ground_truth |= set(case["ground_truth"])
        assert seen_ground_truth == ground_truth_fields

    # `system` is absent on every electro-thermal case and present on every
    # battery one; the union over both sets is what makes the declaration true.
    assert "system" in payload_fields


def test_the_schema_pins_the_case_sets_it_describes():
    """A schema that does not say which bytes it describes describes nothing."""
    schema = _load(SCHEMA_FILE)
    for directory, declared in schema["case_set_digests"].items():
        actual = _case_set_digest(sorted((BENCH / directory).glob("*.json")))
        assert declared == actual, (
            f"{GROUND_TRUTH_SCHEMA} describes {directory} at digest "
            f"{declared[:16]}, but the cases on disk digest to {actual[:16]}. "
            f"The case set moved without the schema being re-stated"
        )


def test_the_declared_soundness_invariant_holds_over_every_case():
    """`label == 'valid'` and `expected_verdict == 'SUPPORTED'` are one fact.

    The scorer computes false accepts from `label` and exact match from
    `expected_verdict`. If the two ever disagreed, those two figures would be
    describing different populations while being printed side by side.
    """
    schema = _load(SCHEMA_FILE)
    verdicts = set(schema["vocabulary"]["expected_verdict"])
    labels = set(schema["vocabulary"]["label"])
    for directory in ("cases_hard", "cases_battery"):
        for case_id, case in _cases(directory).items():
            ground_truth = case["ground_truth"]
            assert ground_truth["expected_verdict"] in verdicts, case_id
            assert ground_truth["label"] in labels, case_id
            assert (ground_truth["label"] == "valid") == (
                ground_truth["expected_verdict"] == "SUPPORTED"
            ), f"{directory}/{case_id} is sound-labelled and not SUPPORTED, or the reverse"


def test_no_case_file_carries_its_own_adjudication_basis():
    """Why the reasoning lives in one log and not in 2400 files.

    A case that carried the reason its verdict was chosen could be re-decided
    by editing one file, losing the previous verdict and the reason for the
    change in the same edit. The schema declares this field set EMPTY on
    purpose; this is the check that keeps it empty.
    """
    schema = _load(SCHEMA_FILE)
    assert schema["roles"]["adjudication_basis"]["fields"] == []

    forbidden = {
        "adjudication_basis", "adjudication", "adjudicated",
        "previous_expected_verdict", "revision",
    }
    for directory in ("cases_hard", "cases_battery"):
        for case_id, case in _cases(directory).items():
            found = (set(case) | set(case["ground_truth"])) & forbidden
            assert not found, (
                f"{directory}/{case_id} carries {sorted(found)}; an "
                f"adjudication basis belongs in ADJUDICATIONS.json, where the "
                f"previous verdict survives the edit that changes the new one"
            )


# ---------------------------------------------------------------- the log


def test_the_adjudication_log_is_internally_coherent():
    """Every field a reader needs to re-open the decision, on every entry."""
    log = _load(LOG_FILE)
    assert log["schema"] == ADJUDICATION_LOG_SCHEMA
    assert log["events"], "an adjudication log with no events proves nothing"

    required_event = {
        "adjudication_id", "recorded_utc", "commit", "benchmark_schema",
        "deciding_condition", "field_revised", "adjudication_basis",
        "independent_violation_search", "not_revised", "classification",
        "runtime_behaviour_changed", "cases",
    }
    required_case = {
        "case_id", "previous_expected_verdict", "new_expected_verdict",
        "defect_family", "label", "declared_catcher",
        "independent_violation",
    }

    identifiers = [event["adjudication_id"] for event in log["events"]]
    assert len(identifiers) == len(set(identifiers)), identifiers

    for event in log["events"]:
        missing = required_event - set(event)
        assert not missing, f"{event.get('adjudication_id')} lacks {sorted(missing)}"
        assert event["benchmark_schema"] == GROUND_TRUTH_SCHEMA
        assert event["adjudication_basis"].strip()
        assert event["cases"]
        for entry in event["cases"]:
            absent = required_case - set(entry)
            assert not absent, f"{entry.get('case_id')} lacks {sorted(absent)}"
            assert (
                entry["previous_expected_verdict"]
                != entry["new_expected_verdict"]
            ), (
                f"{entry['case_id']} is recorded as adjudicated but its "
                f"verdict did not move; an entry that changes nothing makes "
                f"the log's own count wrong"
            )


def test_a_landed_adjudication_cannot_be_edited():
    """Append-only, enforced rather than asserted in prose.

    A new event may be appended freely -- it simply is not in the pinned map
    and nothing here objects. What fails is editing an event that has already
    landed, which is the move that would let a second revision overwrite the
    record of the first.
    """
    log = _load(LOG_FILE)
    present = {event["adjudication_id"]: event for event in log["events"]}

    for adjudication_id, digest in LANDED_EVENT_DIGESTS.items():
        assert adjudication_id in present, (
            f"adjudication {adjudication_id!r} has been REMOVED from the log. "
            f"An append-only record does not lose entries: a decision that "
            f"was wrong is superseded by a new event, not deleted"
        )
        assert _event_digest(present[adjudication_id]) == digest, (
            f"adjudication {adjudication_id!r} has been EDITED after landing. "
            f"Its previous verdicts and its stated basis are the only record "
            f"of what the benchmark used to claim. Supersede it with a new "
            f"event instead"
        )


def test_every_adjudicated_case_carries_the_verdict_the_log_says_it_does():
    """The log and the cases are two records of one decision; they must agree.

    This is the check that catches a case quietly re-edited afterwards: the
    log still says the verdict moved to X and the case on disk says Y.
    """
    log = _load(LOG_FILE)
    cases = _cases("cases_hard")
    for event in log["events"]:
        for entry in event["cases"]:
            case = cases.get(entry["case_id"])
            assert case is not None, (
                f"the log adjudicates {entry['case_id']}, which is not in "
                f"cases_hard. Either the case was deleted or the log names a "
                f"case set it does not describe"
            )
            ground_truth = case["ground_truth"]
            assert ground_truth["expected_verdict"] == entry["new_expected_verdict"], (
                f"{entry['case_id']}: the log records an adjudication to "
                f"{entry['new_expected_verdict']!r}, the case on disk says "
                f"{ground_truth['expected_verdict']!r}"
            )
            # The fields the event declares it did NOT revise really were not.
            assert ground_truth["defect"] == entry["defect_family"]
            assert ground_truth["label"] == entry["label"]
            assert ground_truth["should_be_caught_by"] == entry["declared_catcher"]


def test_an_adjudication_to_insufficient_evidence_found_no_independent_violation():
    """The one substantive invariant the log can actually enforce.

    ``NOT_SUPPORTED`` asserts evidence against a design. Moving a case off it
    is only honest when no condition was *observed* to fail -- if one was, the
    old verdict was right and the screen was never the reason. So an entry that
    weakens a verdict while recording an independent violation is a
    contradiction in its own terms, and fails here.
    """
    log = _load(LOG_FILE)
    weakened = {
        ("NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE"),
        ("NOT_SUPPORTED", "SUPPORTED"),
        ("INSUFFICIENT_EVIDENCE", "SUPPORTED"),
    }
    checked = 0
    for event in log["events"]:
        for entry in event["cases"]:
            move = (
                entry["previous_expected_verdict"],
                entry["new_expected_verdict"],
            )
            if move not in weakened:
                continue
            checked += 1
            assert entry["independent_violation"] is False, (
                f"{entry['case_id']} was weakened from "
                f"{move[0]} to {move[1]} while recording an INDEPENDENT "
                f"violation. A condition that was evaluated and failed is "
                f"evidence against the design, and the stronger verdict was "
                f"the right one"
            )
    assert checked, "no weakening adjudication was exercised; this guard is vacuous"


def test_the_log_classifies_itself_as_truth_correction_and_not_as_improvement():
    """The distinction the whole record exists to preserve.

    A benchmark truth revision and a runtime improvement both raise the score.
    An event that claimed to be a runtime improvement would be describing a
    code change, which belongs in a commit and a re-scored record -- not in
    the answer key.
    """
    log = _load(LOG_FILE)
    for event in log["events"]:
        assert event["classification"] == "benchmark truth correction"
        assert event["runtime_behaviour_changed"] is False


# ------------------------------------------------------- split stability


def test_split_membership_ignores_the_expected_verdict_entirely():
    """THE guard that makes adjudication safe.

    If the partition depended on the expected verdict, re-deciding one would
    silently reallocate sealed seats: cases would move from hold-out into dev
    and be scored, opening the seal with no line in the openings log and no
    way to notice.

    Asserted by construction rather than by reading the rule: the split is
    built twice from the same ids and defect families, once with the real
    verdicts and labels and once with every one of them replaced by a
    constant, and the two partitions must be identical.
    """
    split_hard = _split_module()
    _files, cases = split_hard.read_cases(BENCH / "cases_hard")
    assert len(cases) == 2000

    real_dev, real_holdout = split_hard.build_split(cases)
    scrambled = [
        (case_id, defect, "OBLITERATED_LABEL", "OBLITERATED_VERDICT")
        for case_id, defect, _label, _verdict in cases
    ]
    other_dev, other_holdout = split_hard.build_split(scrambled)

    assert real_dev == other_dev
    assert real_holdout == other_holdout
    assert len(real_dev) == 1400 and len(real_holdout) == 600


def test_split_membership_does_depend_on_identity_and_defect():
    """The complement, so the test above is not passing over a constant.

    A split that ignored everything would also be verdict-independent. These
    two inputs must actually move it.
    """
    split_hard = _split_module()
    _files, cases = split_hard.read_cases(BENCH / "cases_hard")
    real_dev, _ = split_hard.build_split(cases)

    renamed = [(f"{c}-x", d, l, v) for c, d, l, v in cases]
    assert split_hard.build_split(renamed)[0] != real_dev

    one_stratum = [(c, "single-defect", l, v) for c, d, l, v in cases]
    assert split_hard.build_split(one_stratum)[0] != real_dev


def test_the_adjudicated_cases_did_not_change_partition():
    """The seal did not move, checked against the committed split.

    Editing case bytes changes the case-set digest, which forces the split file
    to be regenerated -- and regenerating a split is precisely the operation
    that can reallocate sealed seats. So the 23 adjudicated ids are asserted to
    sit in the partition the committed split assigns them, and the split file
    is asserted to describe these exact bytes.
    """
    split = _load(BENCH / "split_hard.json")
    assert split["case_set_digest"] == _case_set_digest(
        sorted((BENCH / "cases_hard").glob("*.json"))
    ), (
        "split_hard.json was computed over different case bytes than are on "
        "disk. Every dev/hold-out statement it makes describes another case set"
    )

    dev, holdout = set(split["dev"]), set(split["holdout"])
    assert not (dev & holdout)
    assert len(dev) == 1400 and len(holdout) == 600

    log = _load(LOG_FILE)
    adjudicated = {
        entry["case_id"]
        for event in log["events"]
        for entry in event["cases"]
    }
    assert adjudicated <= (dev | holdout)
    # Every adjudicated case is in exactly one partition, and the scored
    # development figure is the one a reader sees.
    for case_id in sorted(adjudicated):
        assert (case_id in dev) != (case_id in holdout), case_id


# ------------------------------------------------------------ mechanics


def test_the_case_set_digest_actually_moves_when_a_case_byte_moves():
    """A digest that never changes is a field, not a guard.

    Exercised over a perturbed copy in memory rather than by writing to the
    repository, so this cannot leave the tree dirty.
    """
    paths = sorted((BENCH / "cases_hard").glob("*.json"))[:5]
    baseline = _case_set_digest(paths)
    assert baseline == _case_set_digest(paths), "digest is not deterministic"

    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in paths]
    perturbed = list(lines)
    perturbed[0] = perturbed[0][:-1] + ("0" if perturbed[0][-1] != "0" else "1")
    assert (
        hashlib.sha256("\n".join(perturbed).encode("utf-8")).hexdigest()
        != baseline
    )

    reordered = [lines[1], lines[0], *lines[2:]]
    assert (
        hashlib.sha256("\n".join(reordered).encode("utf-8")).hexdigest()
        != baseline
    ), "the digest ignores case order, so a reordering would be invisible"


@pytest.mark.parametrize("path", [SCHEMA_FILE, LOG_FILE])
def test_the_records_are_deterministically_serializable(path: pathlib.Path):
    """Round-trips as the same document, and lands LF-terminated.

    The line-ending half is not fussiness. This repository pins artifacts by
    SHA-256 over raw bytes, and `write_text` on Windows turns a line feed into
    a carriage-return pair -- so a record regenerated on the wrong platform is
    byte-different with every field identical.
    """
    raw = path.read_bytes()
    assert b"\r\n" not in raw, f"{path.name} carries CRLF line endings"
    assert raw.endswith(b"\n")

    document = json.loads(raw.decode("utf-8"))
    once = json.dumps(document, indent=2, ensure_ascii=False)
    twice = json.dumps(json.loads(once), indent=2, ensure_ascii=False)
    assert once == twice
    assert once.encode("utf-8") + b"\n" == raw, (
        f"{path.name} is not in the canonical form this test round-trips to; "
        f"regenerate it rather than hand-editing"
    )
