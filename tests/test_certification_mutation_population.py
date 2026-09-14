"""The formal mutation shards must cover the canonical population exactly -- not just sum to 79.

Finding E of the certification trust-closure round. The parallel pipeline proved
coverage with ``sum(shard_counts) == 79``; shard 0 run twice and shard 1 never
run satisfies that whenever the two are the same size. Every case below keeps
the total count right and breaks membership, and must still fail.
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest

from tests import certification_fixtures as fx
from tools.certification import mutation_population as mp

REPO = pathlib.Path(__file__).resolve().parents[1]


def _records(population, *, count=mp.SHARD_COUNT, source="s" * 40, shards=None):
    """Well-formed shard records, as the shard jobs write them, plus their transcripts."""
    records, logs = [], {}
    for index in range(count):
        selected = tuple(shards[index]) if shards is not None else population.shard(index, count)
        log = fx.harness_log(selected)
        logs[index] = log
        records.append({
            "schema": mp.SHARD_RECORD_SCHEMA, "source_commit": source,
            "shard_index": index, "shard_count": count,
            "population_count": population.count, "population_sha256": population.sha256,
            "definitions_sha256": population.definitions_sha256,
            "selected_ids": list(selected), "selected_count": len(selected),
            "selected_ids_sha256": mp.sha256_lines(selected),
            "execution_log_sha256": hashlib.sha256(log).hexdigest(),
            "killed_count": len(selected), "control": "GREEN",
        })
    return records, logs


@pytest.fixture(scope="module")
def population():
    return mp.canonical_population(REPO)


def _coverage(population, records, logs=None):
    return mp.coverage_problems(population, records, logs=logs)


# ---- the real population -------------------------------------------------------------
def test_the_real_population_is_the_certified_79_and_shards_20_20_20_19(population):
    assert population.count == mp.EXPECTED_FORMAL_POPULATION == 79
    assert population.problems() == []
    assert [len(population.shard(i)) for i in range(4)] == [20, 20, 20, 19]
    union = [mid for i in range(4) for mid in population.shard(i)]
    assert sorted(union) == sorted(population.ids) and len(set(union)) == 79


def test_the_population_identity_is_deterministic(population):
    again = mp.canonical_population(REPO)
    assert again.sha256 == population.sha256
    assert again.definitions_sha256 == population.definitions_sha256
    assert population.sha256 == hashlib.sha256(("\n".join(population.ids) + "\n").encode()).hexdigest()


# ---- 6: the exact union ------------------------------------------------------------------
def test_the_exact_union_succeeds_with_every_transcript_re_read(population):
    records, logs = _records(population)
    assert _coverage(population, records, logs) == []


# ---- 1: a missing mutation ---------------------------------------------------------------
def test_a_missing_mutation_fails(population):
    shards = [list(population.shard(i)) for i in range(4)]
    dropped = shards[2].pop()
    records, logs = _records(population, shards=shards)
    problems = _coverage(population, records, logs)
    assert any("no shard executed" in p and dropped in p for p in problems), problems


# ---- 2: a mutation run by two shards -----------------------------------------------------
def test_a_mutation_duplicated_across_shards_fails(population):
    shards = [list(population.shard(i)) for i in range(4)]
    shards[1].append(shards[0][0])
    records, logs = _records(population, shards=shards)
    problems = _coverage(population, records, logs)
    assert any("more than one shard" in p and shards[0][0] in p for p in problems), problems


# ---- 3: an unknown mutation id -----------------------------------------------------------
def test_an_unknown_mutation_id_fails(population):
    shards = [list(population.shard(i)) for i in range(4)]
    shards[3][-1] = "G99z"
    records, logs = _records(population, shards=shards)
    problems = _coverage(population, records, logs)
    assert any("unknown mutation ids ['G99z']" in p for p in problems), problems


# ---- 4: a duplicated shard, with the total count still 79 ------------------------------------
def test_a_duplicated_shard_fails_even_when_the_count_is_right(population):
    records, logs = _records(population)
    # shard 0 (20) twice and shard 1 (20) never: the counts still sum to 79.
    duplicate = dict(records[0])
    records = [records[0], duplicate, records[2], records[3]]
    assert sum(r["selected_count"] for r in records) == 79
    problems = _coverage(population, records, {0: logs[0], 2: logs[2], 3: logs[3]})
    assert any("recorded more than once: [0]" in p for p in problems), problems
    assert any("no record for shard indices [1]" in p for p in problems), problems
    assert any("no shard executed" in p for p in problems), problems


# ---- 5: a reordered population ---------------------------------------------------------------
def test_a_reordered_population_is_a_different_population(population):
    records, logs = _records(population)
    reordered = mp.Population(ids=tuple(reversed(population.ids)),
                              definitions_sha256=population.definitions_sha256)
    assert sorted(reordered.ids) == sorted(population.ids)
    assert reordered.sha256 != population.sha256
    problems = _coverage(reordered, records, logs)
    assert any("not the canonical" in p for p in problems), problems
    assert any("the shard rule selects" in p for p in problems), problems


def test_the_same_count_with_the_wrong_membership_fails(population):
    """A union that IS the population, disjoint, right counts -- and the wrong shards."""
    shards = [list(population.shard(i)) for i in range(4)]
    shards[0][0], shards[1][0] = shards[1][0], shards[0][0]
    records, logs = _records(population, shards=shards)
    assert sorted(m for s in shards for m in s) == sorted(population.ids)
    problems = _coverage(population, records, logs)
    assert problems and all("more than one shard" not in p and "no shard executed" not in p for p in problems)
    assert any("the shard rule selects" in p for p in problems), problems


def test_a_record_against_different_mutation_definitions_fails(population):
    records, logs = _records(population)
    records[1]["definitions_sha256"] = "0" * 64
    assert any("definitions differ" in p for p in _coverage(population, records, logs))


def test_a_record_from_another_commit_fails(population):
    records, logs = _records(population)
    problems = mp.coverage_problems(population, records, logs=logs, source_commit="t" * 40)
    assert any("measured" in p for p in problems)


def test_a_wrong_population_size_fails_even_when_consistent():
    small = mp.Population(ids=("G1a", "G1b", "G2a", "G2b"))
    records, logs = _records(small)
    assert any("claims 79" in p for p in mp.coverage_problems(small, records, logs=logs))


# ---- the transcript, which is where the verdicts actually live ----------------------------------
def test_a_transcript_that_does_not_match_its_digest_fails(population):
    records, logs = _records(population)
    logs[2] = logs[2].replace(b"CONTROL GREEN", b"CONTROL GREEN ")
    assert any("transcript digest" in p for p in _coverage(population, records, logs))


@pytest.mark.parametrize("verdict", ["GREEN -- DECORATION", "RED (NOT THE GUARD)",
                                     "RED (expected a refusal)", "HARNESS TIMEOUT"])
def test_a_mutation_that_was_not_killed_by_its_guard_fails(population, verdict):
    ids = population.shard(0)
    log = fx.harness_log(ids, verdicts={ids[3]: verdict}, tally=(len(ids), len(ids)))
    problems = mp.log_problems(log.decode(), population, ids)
    assert any("not killed" in p and ids[3] in p for p in problems), problems


def test_refused_at_import_with_its_single_space_counts_as_a_kill(population):
    """The parse trap from the Sprint 7 closure: 23 characters, one space after it."""
    ids = population.shard(0)
    log = fx.harness_log(ids, verdicts={ids[0]: "RED (refused at import)"}).decode()
    assert f"{ids[0]:5} RED (refused at import) mutation" in log
    assert mp.log_problems(log, population, ids) == []


def test_a_transcript_without_a_green_control_fails(population):
    ids = population.shard(1)
    log = fx.harness_log(ids, control="RED -- ROUND VOID").decode()
    assert any("control" in p for p in mp.log_problems(log, population, ids))


def test_a_transcript_whose_tally_disagrees_with_its_lines_fails(population):
    ids = population.shard(1)
    log = fx.harness_log(ids, tally=(len(ids) - 1, len(ids))).decode()
    assert any("tally" in p for p in mp.log_problems(log, population, ids))


def test_a_transcript_that_ran_something_else_fails(population):
    ids = population.shard(1)
    other = population.shard(2)[0]
    log = fx.harness_log((*ids, other), tally=(len(ids), len(ids))).decode()
    assert any("did not select" in p for p in mp.log_problems(log, population, ids))
    log = fx.harness_log(ids, extra_lines=["G77q  RED                  not ours"]).decode()
    assert any("outside the population" in p for p in mp.log_problems(log, population, ids))


def test_a_transcript_reporting_a_mutation_twice_fails(population):
    ids = population.shard(3)
    log = fx.harness_log((*ids, ids[0]), tally=(len(ids), len(ids))).decode()
    assert any("more than once" in p for p in mp.log_problems(log, population, ids))


def test_crlf_transcripts_parse_identically(population):
    ids = population.shard(0)
    log = fx.harness_log(ids).decode().replace("\n", "\r\n")
    assert mp.log_problems(log, population, ids) == []


# ---- the shard job's record and selection commands ------------------------------------------------
def test_a_shard_record_is_refused_when_the_id_file_is_not_the_rule(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    fx.make_repo(root)
    small = mp.canonical_population(root)
    ids = small.shard(0, 4)
    with pytest.raises(mp.PopulationError, match="shard rule selects"):
        mp.build_shard_record(root, index=0, count=4, ids_text="\n".join(reversed(ids)) + "\n",
                              log_bytes=fx.harness_log(ids), source_commit="s",
                              expected_count=small.count)
    record = mp.build_shard_record(root, index=0, count=4, ids_text="\n".join(ids) + "\n",
                                   log_bytes=fx.harness_log(ids), source_commit="s",
                                   expected_count=small.count)
    assert record["selected_ids"] == list(ids)
    assert record["execution_log_sha256"] == hashlib.sha256(fx.harness_log(ids)).hexdigest()


def test_select_writes_exactly_the_shard(tmp_path, monkeypatch, population):
    monkeypatch.chdir(REPO)
    out = tmp_path / "ids.txt"
    assert mp.main(["select", "--index", "2", "--count", "4", "--out", str(out)]) == 0
    assert tuple(out.read_bytes().decode().splitlines()) == population.shard(2)
