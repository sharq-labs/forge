"""The formal guard-mutation population, its shards, and proof the shards cover it exactly.

    python -m tools.certification.mutation_population identity
    python -m tools.certification.mutation_population select --index I --count N --out IDS
    python -m tools.certification.mutation_population record --index I --count N \\
        --ids IDS --log LOG --out RECORD.json

WHY A COUNT IS NOT ENOUGH
-------------------------
The parallel pipeline checked that the four shard counts summed to 79. Shard 0
run twice and shard 1 never run also sums to 79 when the shards are the same
size, and the certificate would still say the whole family was executed. What
has to be proved is membership: the union of what the shards ran is the
population, no two shards ran the same mutation, nothing unknown ran, and every
mutation that ran was killed by the guard it names.

THE CANONICAL POPULATION, EXACTLY
---------------------------------
* Source: ``tests/mutation_guards.py`` -> ``MUTATIONS`` at the measured commit,
  loaded with :func:`runpy.run_path` (the module's ``__main__`` guard keeps the
  harness from running).
* Identity: the ORDERED tuple of mutation ids (element 0 of each entry).
* Order IS semantic and is bound, not normalized away: a shard is
  ``[id for position, id in enumerate(population) if position % count == index]``,
  so reordering the population moves mutations between shards. Two populations
  with the same ids in a different order are different populations.
* ``population_sha256`` = SHA-256 over ``"\\n".join(ids) + "\\n"`` in UTF-8.
* ``definitions_sha256`` = SHA-256 over the canonical JSON (sorted keys, no
  whitespace, ASCII) of the full ordered entries, so the same ids with a
  different mutation body are also a different population.
* ``selected_ids_sha256`` for a shard uses the population rule on that shard's
  ids, in population order.
* ``execution_log_sha256`` = SHA-256 over the exact bytes of the harness
  transcript the shard produced. Nothing is normalized.

THE LOG, AND HOW IT IS READ
---------------------------
The harness prints one verdict line per mutation, ``<id padded to 5> <verdict
padded to 20> <description>``. A mutation is KILLED only when its verdict is
``RED`` or ``RED (refused at import)`` -- the second is 23 characters and so
is followed by a SINGLE space, which a two-space pattern silently drops.
Every other verdict (``RED (NOT THE GUARD)``, ``GREEN -- DECORATION``,
``MUTATION DID NOT APPLY``, ``HARNESS TIMEOUT`` ...) is not a kill. The
transcript must contain one ``CONTROL GREEN`` line and the runner's own
``N/N mutations were killed`` tally, and the tally must agree with the lines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import runpy
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

HARNESS_PATH = "tests/mutation_guards.py"

#: The population the certificate claims. A harness change that adds or removes
#: a mutation must change this in the same (recertified) change, so the number
#: in the certificate is a decision rather than whatever the list held that day.
#: 79 through Core Freeze V2; 86 from GUARD 27, which added G27a-G27g against the
#: Hybrid UQ trust boundaries (supplied-sensitivity binding, covariance validity,
#: unchecked predictive linearity, derivative convergence, routed-record
#: consistency, dimensional reparameterization, serialized grid-moment binding).
#: 94 from GUARD 28, which added G28a-G28h for the core trust closure (admission
#: applicability, result/provenance attribution, exact model versions, SRIA
#: evidence integrity, belief and uncertainty isolation, solver session
#: freshness, calibration spec immutability).
EXPECTED_FORMAL_POPULATION = 94
SHARD_COUNT = 4

SHARD_RECORD_SCHEMA = "forge.formal_mutation_shard/1"

_ID_SHAPE = re.compile(r"^G\d+[a-z]+$")
_TALLY = re.compile(r"^(\d+)/(\d+) mutations were killed by the guard they name\.\s*$")
_CONTROL_GREEN = re.compile(r"^CONTROL\s+GREEN\b")
_CONTROL_RED = re.compile(r"^CONTROL\s+RED\b")


class PopulationError(RuntimeError):
    """The population or a shard's evidence cannot support the claim."""


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------
def sha256_lines(items: Iterable[str]) -> str:
    """SHA-256 over ``"\\n".join(items) + "\\n"``; the one digest rule for id lists."""
    return hashlib.sha256(("\n".join(items) + "\n").encode("utf-8")).hexdigest()


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def load_entries(root: pathlib.Path) -> tuple[tuple[str, ...], ...]:
    """``MUTATIONS`` from the harness at ``root``, as plain tuples of strings."""
    path = root / HARNESS_PATH
    if not path.is_file():
        raise PopulationError(f"no mutation harness at {path}")
    namespace = runpy.run_path(str(path), run_name="_mutation_population_probe")
    entries = namespace.get("MUTATIONS")
    if not isinstance(entries, tuple) or not entries:
        raise PopulationError(f"{HARNESS_PATH} defines no MUTATIONS tuple")
    normalized: list[tuple[str, ...]] = []
    for entry in entries:
        if not isinstance(entry, tuple) or not entry or not all(isinstance(f, str) for f in entry):
            raise PopulationError(f"malformed MUTATIONS entry: {entry!r}")
        normalized.append(tuple(entry))
    return tuple(normalized)


@dataclass(frozen=True)
class Population:
    """The ordered identity of a mutation population."""

    ids: tuple[str, ...]
    definitions_sha256: str = ""

    @property
    def count(self) -> int:
        return len(self.ids)

    @property
    def sha256(self) -> str:
        return sha256_lines(self.ids)

    def shard(self, index: int, count: int = SHARD_COUNT) -> tuple[str, ...]:
        if count < 1 or not 0 <= index < count:
            raise PopulationError(f"shard {index} of {count} does not exist")
        return tuple(mid for position, mid in enumerate(self.ids) if position % count == index)

    def problems(self, expected_count: int = EXPECTED_FORMAL_POPULATION) -> list[str]:
        found: list[str] = []
        duplicates = sorted({mid for mid in self.ids if self.ids.count(mid) > 1})
        if duplicates:
            found.append(f"the population declares duplicate ids {duplicates}")
        if self.count != expected_count:
            found.append(
                f"the population has {self.count} mutations and the certificate "
                f"claims {expected_count}"
            )
        return found


def canonical_population(root: pathlib.Path) -> Population:
    entries = load_entries(root)
    return Population(
        ids=tuple(entry[0] for entry in entries),
        definitions_sha256=hashlib.sha256(_canonical_json([list(e) for e in entries])).hexdigest(),
    )


# ---------------------------------------------------------------------------
# the harness transcript
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LogSummary:
    control_green: bool
    control_red: bool
    verdicts: Mapping[str, tuple[str, ...]]   # id -> every verdict printed for it
    unknown_ids: tuple[str, ...]
    tally: tuple[int, int] | None

    @property
    def killed(self) -> tuple[str, ...]:
        return tuple(sorted(
            mid for mid, verdicts in self.verdicts.items() if verdicts == ("RED",)
        ))


def _verdict(rest: str) -> str:
    if rest == "RED" or rest.startswith("RED  "):
        return "RED"
    if rest.startswith("RED (refused at import)"):
        return "RED"
    return rest.split("  ", 1)[0].split(" -- ")[0].strip() or "<empty>"


def parse_log(text: str, population: Population) -> LogSummary:
    known = set(population.ids)
    verdicts: dict[str, list[str]] = {}
    unknown: set[str] = set()
    control_green = control_red = False
    tally: tuple[int, int] | None = None
    for line in text.splitlines():
        if _CONTROL_GREEN.match(line):
            control_green = True
            continue
        if _CONTROL_RED.match(line):
            control_red = True
            continue
        if (found := _TALLY.match(line)) is not None:
            tally = (int(found.group(1)), int(found.group(2)))
            continue
        if not line or line[0].isspace():
            continue
        token, _, rest = line.partition(" ")
        if token in known:
            verdicts.setdefault(token, []).append(_verdict(rest.lstrip(" ")))
        elif _ID_SHAPE.match(token):
            unknown.add(token)
    return LogSummary(
        control_green=control_green,
        control_red=control_red,
        verdicts={mid: tuple(v) for mid, v in verdicts.items()},
        unknown_ids=tuple(sorted(unknown)),
        tally=tally,
    )


def log_problems(text: str, population: Population, selected: Sequence[str]) -> list[str]:
    """Why a transcript does not show exactly ``selected`` run and killed."""
    summary = parse_log(text, population)
    problems: list[str] = []
    if not summary.control_green or summary.control_red:
        problems.append("the transcript has no green unmutated control, so no kill in it is evidence")
    if summary.unknown_ids:
        problems.append(f"the transcript reports mutations outside the population: {list(summary.unknown_ids)}")
    ran = set(summary.verdicts)
    wanted = set(selected)
    if ran - wanted:
        problems.append(f"the transcript ran mutations this shard did not select: {sorted(ran - wanted)}")
    if wanted - ran:
        problems.append(f"the transcript has no verdict for selected mutations: {sorted(wanted - ran)}")
    repeated = sorted(mid for mid, v in summary.verdicts.items() if len(v) > 1)
    if repeated:
        problems.append(f"the transcript reports a verdict more than once for {repeated}")
    not_killed = sorted(
        f"{mid} ({', '.join(v)})" for mid, v in summary.verdicts.items()
        if mid in wanted and v != ("RED",)
    )
    if not_killed:
        problems.append(f"selected mutations not killed by their guard: {not_killed}")
    expected_tally = (len(selected), len(selected))
    if summary.tally != expected_tally:
        problems.append(
            f"the runner's tally is {summary.tally} and a fully killed shard of "
            f"{len(selected)} reads {expected_tally}"
        )
    return problems


# ---------------------------------------------------------------------------
# shard records, and the coverage proof
# ---------------------------------------------------------------------------
def build_shard_record(
    root: pathlib.Path,
    *,
    index: int,
    count: int,
    ids_text: str,
    log_bytes: bytes,
    source_commit: str,
    expected_count: int = EXPECTED_FORMAL_POPULATION,
) -> dict[str, Any]:
    """The shard's evidence record. Refuses to write one that is not evidence."""
    population = canonical_population(root)
    problems = population.problems(expected_count)
    selected = population.shard(index, count)
    listed = tuple(line for line in ids_text.splitlines() if line)
    if listed != selected:
        problems.append(
            f"the id file for shard {index} lists {list(listed)} and the shard "
            f"rule selects {list(selected)}"
        )
    problems += log_problems(log_bytes.decode("utf-8", "replace"), population, selected)
    if problems:
        raise PopulationError(f"shard {index}/{count}: " + "; ".join(problems))
    return {
        "schema": SHARD_RECORD_SCHEMA,
        "source_commit": source_commit,
        "harness": HARNESS_PATH,
        "shard_index": index,
        "shard_count": count,
        "population_count": population.count,
        "population_sha256": population.sha256,
        "definitions_sha256": population.definitions_sha256,
        "selected_ids": list(selected),
        "selected_count": len(selected),
        "selected_ids_sha256": sha256_lines(selected),
        "execution_log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "execution_log_bytes": len(log_bytes),
        "killed_count": len(selected),
        "control": "GREEN",
    }


def coverage_problems(
    population: Population,
    records: Sequence[Mapping[str, Any]],
    *,
    shard_count: int = SHARD_COUNT,
    expected_count: int = EXPECTED_FORMAL_POPULATION,
    logs: Mapping[int, bytes] | None = None,
    source_commit: str | None = None,
) -> list[str]:
    """Why ``records`` do not prove the whole population ran exactly once.

    ``population`` is recomputed from the tree by the caller -- never read from
    a record -- so a record cannot vouch for the population it is checked
    against. With ``logs`` (shard index -> transcript bytes) every record's log
    digest and verdicts are re-derived from the transcript itself.
    """
    problems = list(population.problems(expected_count))
    indices = [record.get("shard_index") for record in records]
    duplicated = sorted({i for i in indices if indices.count(i) > 1}, key=str)
    if duplicated:
        problems.append(f"shard indices recorded more than once: {duplicated}")
    absent = [i for i in range(shard_count) if i not in indices]
    if absent:
        problems.append(f"no record for shard indices {absent}")
    foreign = sorted({i for i in indices if i not in range(shard_count)}, key=str)
    if foreign:
        problems.append(f"records for shard indices that do not exist: {foreign}")

    union: list[str] = []
    known = set(population.ids)
    for record in records:
        index = record.get("shard_index")
        label = f"shard {index}"
        selected = tuple(record.get("selected_ids") or ())
        union.extend(selected)
        if record.get("schema") != SHARD_RECORD_SCHEMA:
            problems.append(f"{label}: record schema {record.get('schema')!r}")
        if record.get("shard_count") != shard_count:
            problems.append(f"{label}: recorded shard_count {record.get('shard_count')}, expected {shard_count}")
        if source_commit is not None and record.get("source_commit") != source_commit:
            problems.append(f"{label}: measured {record.get('source_commit')!r}, not {source_commit}")
        if record.get("population_sha256") != population.sha256:
            problems.append(f"{label}: ran against population {record.get('population_sha256')!r}, not the canonical {population.sha256}")
        if population.definitions_sha256 and record.get("definitions_sha256") != population.definitions_sha256:
            problems.append(f"{label}: mutation definitions differ from the canonical population")
        if record.get("population_count") != population.count:
            problems.append(f"{label}: recorded population_count {record.get('population_count')}, canonical {population.count}")
        unknown = sorted(set(selected) - known)
        if unknown:
            problems.append(f"{label}: unknown mutation ids {unknown}")
        if len(set(selected)) != len(selected):
            problems.append(f"{label}: selects an id twice")
        if record.get("selected_count") != len(selected):
            problems.append(f"{label}: selected_count {record.get('selected_count')} for {len(selected)} ids")
        if record.get("selected_ids_sha256") != sha256_lines(selected):
            problems.append(f"{label}: selected_ids_sha256 does not match its own ids")
        if isinstance(index, int) and 0 <= index < shard_count:
            rule = population.shard(index, shard_count)
            if selected != rule:
                problems.append(f"{label}: selects {list(selected)}, the shard rule selects {list(rule)}")
        if logs is not None:
            log = logs.get(index) if isinstance(index, int) else None
            if log is None:
                problems.append(f"{label}: no transcript to re-derive its verdicts from")
            else:
                if hashlib.sha256(log).hexdigest() != record.get("execution_log_sha256"):
                    problems.append(f"{label}: transcript digest does not match execution_log_sha256")
                problems += [f"{label}: {p}" for p in log_problems(log.decode("utf-8", "replace"), population, selected)]

    duplicates = sorted({mid for mid in union if union.count(mid) > 1})
    if duplicates:
        problems.append(f"mutations executed by more than one shard: {duplicates}")
    missing = [mid for mid in population.ids if mid not in set(union)]
    if missing:
        problems.append(f"mutations no shard executed: {missing}")
    if len(union) != population.count:
        problems.append(f"shards executed {len(union)} mutation slots for a population of {population.count}")
    if sorted(union) != sorted(population.ids) and not (duplicates or missing):
        problems.append("the union of the shards is not the population")
    return problems


def assurance_section(
    population: Population, records: Sequence[Mapping[str, Any]], *, shard_count: int = SHARD_COUNT
) -> dict[str, Any]:
    """The ``formal_guard_mutations`` block for an assurance record already proved by :func:`coverage_problems`."""
    return {
        "harness": HARNESS_PATH,
        "population": population.count,
        "expected_population": EXPECTED_FORMAL_POPULATION,
        "population_sha256": population.sha256,
        "definitions_sha256": population.definitions_sha256,
        "ids": list(population.ids),
        "identity_rule": (
            "population_sha256 = sha256('\\n'.join(ids) + '\\n') over MUTATIONS ids "
            "in declaration order. Order is bound because shard membership is "
            "position % shard_count"
        ),
        "shard_count": shard_count,
        "sharding_rule": "shard i runs ids at positions p where p % shard_count == i",
        "shards": {
            str(record["shard_index"]): {
                "selected_ids": list(record["selected_ids"]),
                "selected_count": record["selected_count"],
                "selected_ids_sha256": record["selected_ids_sha256"],
                "execution_log_sha256": record["execution_log_sha256"],
                "killed_count": record["killed_count"],
                "control": record["control"],
            }
            for record in sorted(records, key=lambda r: r["shard_index"])
        },
        "coverage": {
            "union_equals_population": True,
            "pairwise_disjoint": True,
            "unknown_ids": [],
            "every_selected_mutation_killed": True,
        },
        "claim": (
            "Fresh execution of tests/mutation_guards.py on the source commit, "
            "partitioned by the sharding rule. Each shard re-ran the unmutated "
            "control before its mutations. The certify job re-derived every "
            "shard's verdicts from its downloaded transcript and proved the "
            "shards cover the canonical population exactly once"
        ),
    }


# ---------------------------------------------------------------------------
def _root() -> pathlib.Path:
    from tools.certification.core_certificate import repo_root

    return repo_root(pathlib.Path.cwd() / "x")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("identity")
    select = commands.add_parser("select")
    select.add_argument("--index", type=int, required=True)
    select.add_argument("--count", type=int, default=SHARD_COUNT)
    select.add_argument("--out", required=True)
    record = commands.add_parser("record")
    record.add_argument("--index", type=int, required=True)
    record.add_argument("--count", type=int, default=SHARD_COUNT)
    record.add_argument("--ids", required=True)
    record.add_argument("--log", required=True)
    record.add_argument("--source-commit", required=True)
    record.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root = _root()

    try:
        population = canonical_population(root)
        if args.command == "identity":
            problems = population.problems()
            print(json.dumps({
                "population": population.count,
                "population_sha256": population.sha256,
                "definitions_sha256": population.definitions_sha256,
                "shards": {str(i): list(population.shard(i)) for i in range(SHARD_COUNT)},
                "problems": problems,
            }, indent=2))
            return 0 if not problems else 1
        if args.command == "select":
            problems = population.problems()
            if problems:
                raise PopulationError("; ".join(problems))
            selected = population.shard(args.index, args.count)
            if not selected:
                raise PopulationError(f"shard {args.index}/{args.count} is empty")
            pathlib.Path(args.out).write_bytes(("\n".join(selected) + "\n").encode("utf-8"))
            print(f"shard {args.index}/{args.count}: {len(selected)} mutation(s) "
                  f"of population {population.sha256[:16]}")
            return 0
        shard = build_shard_record(
            root, index=args.index, count=args.count,
            ids_text=pathlib.Path(args.ids).read_bytes().decode("utf-8"),
            log_bytes=pathlib.Path(args.log).read_bytes(),
            source_commit=args.source_commit,
        )
    except PopulationError as exc:
        print(f"MUTATION POPULATION PROBLEM: {exc}", file=sys.stderr)
        return 1
    pathlib.Path(args.out).write_bytes((json.dumps(shard, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(f"shard {args.index}/{args.count}: {shard['selected_count']} killed, "
          f"log {shard['execution_log_sha256'][:16]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
