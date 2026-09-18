# The Core Freeze V4 guard-mutation round

Four transcripts, one per shard of the 589-mutation V4 population
(`tests/mutation_population_v4.py`), produced by

    python -m tools.certification.mutation_v4_runner --scratch <DIR outside the repo> --index I --count 4 \
        --log benchmarks/core_v4_false_confidence/v4_round/shardI.log

Each line is one mutation: its id, the name of the ONE test whose failure counts as the kill, the verdict read
from that run's own JUnit report, the one-line pytest summary, and the note its batch wrote. Two entries are
NOT MUTATED with their reason, and three are declared SURVIVED with theirs. A round ends with the unmutated
control over the same tests; a round whose control is not green says nothing at all.

These bytes are the evidence `certification/core_freeze_v4_assurance.json` rests on, and nothing in that
record is copied from them: `tools.certification.core_freeze_v4.v4_mutation_problems` recomputes the
population's two digests from the tree, each transcript's digest from these bytes, and each verdict by
parsing these lines — which is the re-audit's finding 91, that a fabricated record with green flags and a
copied population sha passed every check.
